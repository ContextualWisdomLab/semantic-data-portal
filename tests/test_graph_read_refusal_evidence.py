"""A refused cross-tenant graph read must be recorded as a refusal, in the owner's scope.

The graph read routes evaluate the ``search`` (catalog-discovery) policy branch,
which returns **before** the engine's tenant check, and then enforce the tenant
boundary outside ``evaluate()`` with a bare ``HTTPException(404)``. Measured at
``bc2ebb2`` on a ``pii: true`` column of a ``zeta-bank``-owned dataset, probed
by ``data-admin`` (tenant ``demo``, roles ``[admin, data-analyst]``, no
platform-admin)::

    READ  GET /graph/nodes/zeta-ledger:holder_rrn?actor=data-admin
       HTTP 404 "node not found"
       DECISION effect=allow  reason='카탈로그 발견 정책 통과'  tenant='demo'
       AUDIT  (none)

    WRITE same node, same actor - structurally identical refusal
       HTTP 403 "tenant boundary denied"
       DECISION effect=deny   reason='tenant boundary denied'  tenant='zeta-bank'
       AUDIT  graph.node_upsert result=denied tenant='zeta-bank'

Three consequences, each pinned below.

1. The ledger **contradicts the outcome**: the request was refused and the only
   row says ``allow``. The ``policy_audit_coverage`` guardrail is "every
   governed data action can be explained and audited".
2. **No audit event at all**, while the write refusal against the very same node
   writes one - so the owner can see an attempted write and not an attempted
   read.
3. The row is filed in the **prober's** tenant. ``_effective_tenant_id``
   resolves the stamp with ``get_dataset(resource)``, and a column-node id
   ``<dataset>:<column>`` is not a dataset id - even though
   ``policy.graph_node_dataset_id()`` exists in the same module to strip that
   suffix and is already used by ``can_see_graph_node`` and
   ``graph_node_target_tenant``. Because the stamp therefore depends on whether
   the id happens to resolve, a foreign-but-existing id files to the owner
   (invisible to the prober) while an absent id files to the prober (visible),
   which makes the prober's own ``/policy/decisions`` a dataset-existence
   oracle.

The HTTP response stays a bare 404. That is deliberate and already recorded:
answering 403 for a foreign node and 404 for an absent one is the existence
oracle the browse, catalog and llm families were repaired to close. What changes
is the **evidence**, not the channel.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sdp.api import app  # noqa: E402
from sdp import catalog, evidence  # noqa: E402
from sdp import policy  # noqa: E402


client = TestClient(app)

FOREIGN_DATASET = "zeta-ledger"
FOREIGN_TENANT = "zeta-bank"
FOREIGN_NODE = f"{FOREIGN_DATASET}:holder_rrn"
# tenant ``demo``, roles [admin, data-analyst] - an authenticated reader who is
# NOT platform-admin, so the tenant boundary applies to it.
PROBER = "data-admin"


@pytest.fixture
def foreign_pii_column() -> str:
    """Onboard a dataset owned by another tenant, with one PII column.

    Created through the API by a platform-admin, so the mirror into the graph
    happens the way it does in production. The actor travels in the **body** on
    this route, not in ``?user=``.
    """
    column = {
        "name": "holder_rrn",
        "datatype": "string",
        "description": "resident registration number",
        "pii": True,
        "nullable_ratio": 0.0,
        "distinct_ratio": 1.0,
        "classification": ["restricted"],
    }
    created = client.post(
        "/catalog/datasets",
        json={
            "id": FOREIGN_DATASET,
            "title": "Zeta Ledger",
            "description": "zeta bank ledger",
            "owner": "zeta",
            "steward": "zeta-steward",
            "domain": "finance",
            "tenant_id": FOREIGN_TENANT,
            "source_system": "postgresql://zeta.dw/ledger",
            "sensitivity": "restricted",
            "update_frequency": "daily",
            "quality_score": 0.9,
            "freshness_score": 0.9,
            "schema": [column],
            "actor": "admin",
        },
    )
    assert created.status_code == 200, created.text
    assert policy.graph_node_target_tenant(FOREIGN_NODE) == FOREIGN_TENANT
    assert not policy.can_see_graph_node(PROBER, FOREIGN_NODE), (
        "the premise of this family is that the prober may not see this node"
    )
    return FOREIGN_NODE


def _new_rows(before_decisions: int, before_audits: int):
    """The decision and audit rows a call added, newest first."""
    decisions = evidence.list_policy_decisions(limit=500)
    audits = catalog.list_audit_events(limit=500)
    return (
        decisions[: len(decisions) - before_decisions],
        audits[: len(audits) - before_audits],
    )


def test_the_refused_read_is_recorded_as_a_refusal(foreign_pii_column: str) -> None:
    """A 404 must not be filed as ``allow``."""
    before_d = len(evidence.list_policy_decisions(limit=500))
    before_a = len(catalog.list_audit_events(limit=500))

    response = client.get(
        f"/graph/nodes/{foreign_pii_column}", params={"actor": PROBER}
    )
    assert response.status_code == 404, response.text

    decisions, _ = _new_rows(before_d, before_a)
    about_node = [row for row in decisions if row.resource == foreign_pii_column]
    assert about_node, [row.resource for row in decisions]
    assert any(row.effect == "deny" for row in about_node), (
        "the request was refused and the ledger records only "
        f"{[row.effect for row in about_node]}"
    )


def test_the_refused_read_writes_an_audit_event(foreign_pii_column: str) -> None:
    """The write refusal writes one for the same node; the read must too."""
    before_d = len(evidence.list_policy_decisions(limit=500))
    before_a = len(catalog.list_audit_events(limit=500))

    client.get(f"/graph/nodes/{foreign_pii_column}", params={"actor": PROBER})

    _, audits = _new_rows(before_d, before_a)
    assert audits, (
        "a refused governed read recorded no audit event, so the owner can see "
        "an attempted write on this node and not an attempted read"
    )
    assert any(
        event.result in {"denied", "refused"} for event in audits
    ), [(event.action, event.result) for event in audits]


def test_the_refusal_is_filed_in_the_owners_tenant(foreign_pii_column: str) -> None:
    """The scope a tenant-scoped auditor queries is the owner's, not the prober's."""
    before_d = len(evidence.list_policy_decisions(limit=500))
    before_a = len(catalog.list_audit_events(limit=500))

    client.get(f"/graph/nodes/{foreign_pii_column}", params={"actor": PROBER})

    decisions, audits = _new_rows(before_d, before_a)
    about_node = [row for row in decisions if row.resource == foreign_pii_column]
    tenants = {(row.obligations or {}).get("tenant_id") for row in about_node}
    assert FOREIGN_TENANT in tenants, (
        f"the refusal is filed under {tenants} rather than the owning tenant "
        f"{FOREIGN_TENANT!r}, so the owner's auditor cannot see the attempt"
    )
    assert all(
        event.details.get("tenant_id") == FOREIGN_TENANT for event in audits
    ), [event.details.get("tenant_id") for event in audits]


def test_the_tenant_stamp_reads_a_column_node_as_its_dataset(
    foreign_pii_column: str,
) -> None:
    """The stamp resolver must use the suffix-stripping helper that exists.

    ``_effective_tenant_id`` called ``get_dataset(resource)``, which returns
    ``None`` for ``<dataset>:<column>``, so the row fell through to the actor's
    tenant. The helper it needed - ``graph_node_dataset_id`` - is in the same
    module and already used by two of its neighbours.

    Driven on the **foreign** dataset deliberately. The first version of this
    test compared the stamps for ``crm-customer-master:email`` and
    ``crm-customer-master``, and passed against the defect: that dataset is
    owned by ``demo``, which is also the prober's tenant, so both sides read
    ``demo`` whichever path produced them. A test of a tenant stamp needs two
    different tenants to say anything.
    """
    assert policy.graph_node_dataset_id(foreign_pii_column) == FOREIGN_DATASET
    stamp = policy._effective_tenant_id(PROBER, foreign_pii_column)
    owner = policy._effective_tenant_id(PROBER, FOREIGN_DATASET)
    assert owner == FOREIGN_TENANT, (
        f"the premise failed: the bare dataset id stamps {owner!r}"
    )
    assert stamp == FOREIGN_TENANT, (
        "a column node of a foreign dataset is stamped with the prober's "
        f"tenant instead of the owner's: {stamp!r} vs {FOREIGN_TENANT!r}"
    )


def test_the_http_channel_still_says_nothing_about_existence(
    foreign_pii_column: str,
) -> None:
    """The evidence changes; the response must not.

    Answering 403 for a foreign node and 404 for an absent one is the existence
    oracle this repository already closed on three other families. The refusal
    body and status for both cases have to stay identical.
    """
    foreign = client.get(
        f"/graph/nodes/{foreign_pii_column}", params={"actor": PROBER}
    )
    absent = client.get(
        "/graph/nodes/no-such-dataset:no_such_column", params={"actor": PROBER}
    )
    assert foreign.status_code == absent.status_code == 404
    assert foreign.json() == absent.json(), (
        f"foreign {foreign.json()} vs absent {absent.json()} - the status code "
        "or body distinguishes an existing foreign node from an absent one"
    )
