"""Three governance boundaries that held in one direction and failed in another.

**Purpose binding was defeated by one space.** ``policy.evaluate`` normalizes
``action`` with ``.strip().lower()`` and compared the other caller-controlled
dimension, ``purpose``, with ``.lower()`` and no ``.strip()``. Measured against a
data-analyst with no export approval::

    preview purpose='external-export'    -> 403 (operator approval required)
    preview purpose='EXTERNAL-EXPORT'    -> 403
    preview purpose=' external-export'   -> 200
    preview purpose='external-export '   -> 200
    preview purpose='external-export\\t'  -> 200
    query   purpose='external-export'    -> 403 DENIED
    query   purpose=' external-export'   -> 200 SUCCEEDED

The recorded decision then read ``effect: allow``, so the evidence ledger a
compliance team reads affirmatively certified the export as policy-approved.
Because the *casing* variant was blocked, nothing told an integrator the field
was whitespace-sensitive.

The row-filter obligation had the mirror-image bug on the same field: it compared
``purpose == "analysis"`` exactly, so the only row filter the engine emits
silently vanished for ``'Analysis'`` or ``' analysis'`` - no refusal, just a
missing obligation.

**The graph write boundary failed open.** ``_authorize_graph_write`` evaluated
the ``create`` action with no ``target_tenant_id``, and ``create`` is the one
policy branch that cannot resolve the owning tenant from the catalog itself, so
it skipped the tenant check entirely. Measured with a tenant-``zeta`` dataset and
a ``data-admin`` whose tenant is ``demo``::

    READ  /graph/nodes/zeta-secret:customer_email  -> 404 node not found
    WRITE /graph/nodes {node_id: zeta-secret:customer_email, properties:{pii:false}}
                                                   -> 200 upserted
    platform-admin read, before -> {'datatype': 'string', 'pii': True}
    platform-admin read, after  -> {'pii': False, 'datatype': 'string'}

So a foreign admin could flip the ``pii`` classification of a column it cannot
read, on governed metadata that feeds ``POST /search/semantic`` and
``POST /graph/query``.

**The preview refusal leaked existence through the ledger.** The HTTP bodies were
already identical; the caller's own ``GET /policy/decisions`` was not::

    POST /browse/{foreign}/preview -> 404   decisions visible to prober: 0
    POST /browse/{absent}/preview  -> 404   decisions visible to prober: 1

Every sibling dataset-resolving route already routes its refusals through
``policy.evaluate_dataset_scope_refusal``; preview was the one caller that did
not.
"""

from __future__ import annotations

from pathlib import Path
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sdp import catalog, evidence, policy  # noqa: E402
from sdp.api import app  # noqa: E402

client = TestClient(app, raise_server_exceptions=False)

FOREIGN = {
    "actor": "admin",
    "id": "zeta-secret",
    "tenant_id": "zeta",
    "title": "Z",
    "description": "d",
    "owner": "o",
    "steward": "s",
    "domain": "z",
    "source_system": "pg://zeta/secret",
    "sensitivity": "medium",
    "update_frequency": "daily",
    "quality_score": 0.9,
    "freshness_score": 0.9,
    "schema": [
        {
            "name": "customer_email",
            "datatype": "string",
            "nullable_ratio": 0.0,
            "distinct_ratio": 1.0,
            "pii": True,
        }
    ],
    "distributions": [{"id": "d1", "format": "table", "endpoint": "https://x/y"}],
}


@pytest.fixture
def foreign_dataset() -> str:
    created = client.post("/catalog/datasets", json=FOREIGN)
    assert created.status_code == 200, created.text
    return FOREIGN["id"]


# --------------------------------------------------------------------------- #
# Purpose binding
# --------------------------------------------------------------------------- #

PURPOSE_VARIANTS = (
    "external-export",
    "EXTERNAL-EXPORT",
    " external-export",
    "external-export ",
    "external-export\t",
    "\nexternal-export\n",
    "  ExTeRnAl-ExPoRt  ",
)


@pytest.mark.parametrize("purpose", PURPOSE_VARIANTS)
def test_no_purpose_spelling_bypasses_the_export_denial(purpose: str) -> None:
    """Enumerated over the variants, because the casing one was already blocked.

    Blocking case but not whitespace is what made this invisible: an integrator
    testing ``EXTERNAL-EXPORT`` concludes the field is normalized.
    """
    preview = client.post(
        "/browse/crm-customer-master/preview",
        json={"user": "analyst", "purpose": purpose, "limit": 2},
    )
    assert preview.status_code == 403, (purpose, preview.text)

    query = client.post(
        "/browse/query",
        json={
            "user": "analyst",
            "purpose": purpose,
            "dataset_ids": ["crm-customer-master"],
            "query": "SELECT count(*) FROM customer",
            "language": "sql",
        },
    )
    assert query.status_code == 403, (purpose, query.text)


def test_the_ledger_does_not_certify_a_bypassed_export() -> None:
    """The second half of the defect: the row said ``allow``.

    A refusal that is bypassed leaves the compliance ledger asserting the export
    was policy-approved, which is worse than the bypass - it is the record a
    buyer's auditor trusts.
    """
    before = len(evidence._POLICY_DECISION_LOG)
    client.post(
        "/browse/crm-customer-master/preview",
        json={"user": "analyst", "purpose": " external-export", "limit": 2},
    )
    new = evidence._POLICY_DECISION_LOG[before:]
    assert new, "the refusal must still be recorded"
    for row in new:
        record = row if isinstance(row, dict) else row.model_dump()
        if record.get("action") == "preview":
            assert record["effect"] == "deny", record


@pytest.mark.parametrize("purpose", ("analysis", "Analysis", "ANALYSIS", " analysis", "  Analysis\t"))
def test_the_row_filter_obligation_survives_purpose_spelling(purpose: str) -> None:
    """The mirror-image bug on the same field.

    ``crm-event`` is the high-sensitivity dataset, and this is the only row
    filter the engine ever emits. It compared the raw string, so the obligation
    disappeared on any variant - silently, with a 200.
    """
    response = client.post(
        "/browse/crm-event/preview", json={"user": "admin", "purpose": purpose, "limit": 2}
    )
    assert response.status_code == 200, response.text
    # The field this read was ``applied_row_filter``, which asserted the predicate
    # governed the rows; nothing applies it, so the claim moved to
    # ``row_filter_summary`` with its enforcement status beside it (see
    # ``tests/test_row_filter_is_declared_not_applied.py``). What this test is
    # about - that the obligation survives the spelling of ``purpose`` - is
    # unchanged, and is now read where the obligation is actually published.
    summary = response.json()["row_filter_summary"]
    assert summary["declared_predicates"] == ["business_unit = current_user_unit"], (
        purpose,
        summary,
    )
    assert summary["filter_enforced"] is False, summary


def test_purpose_is_normalized_once_at_the_entry_point() -> None:
    """One normalization, so the two branches cannot drift apart again.

    Comment lines are stripped before the check: the function's own comment
    quotes the old ``purpose == "analysis"`` comparison as the measurement, and
    the first version of this test matched that quotation.
    """
    import inspect

    source = inspect.getsource(policy.evaluate)
    code = "\n".join(
        line for line in source.splitlines() if not line.lstrip().startswith("#")
    )
    assert "purpose_key = purpose.strip().lower()" in code
    for raw in ("purpose.lower() ==", "purpose ==", "purpose.strip() =="):
        assert raw not in code, f"a raw purpose comparison reappeared: {raw}"
    # And every branch that reads the field reads the normalized one.
    assert code.count("purpose_key") >= 3, code.count("purpose_key")


# --------------------------------------------------------------------------- #
# The graph write boundary
# --------------------------------------------------------------------------- #


def test_a_foreign_tenant_admin_cannot_overwrite_a_node_it_cannot_read(
    foreign_dataset: str,
) -> None:
    node_id = f"{foreign_dataset}:customer_email"
    before = client.get("/graph/nodes/" + node_id, params={"actor": "admin"})
    assert before.status_code == 200, before.text
    assert before.json()["properties"]["pii"] is True

    # The read boundary already held.
    assert client.get("/graph/nodes/" + node_id, params={"actor": "data-admin"}).status_code == 404

    audits = len(catalog._AUDIT_LOG)
    write = client.post(
        "/graph/nodes",
        json={
            "actor": "data-admin",
            "node_id": node_id,
            "kind": "column",
            "label": "customer_email",
            "properties": {"pii": False, "datatype": "string"},
        },
    )
    assert write.status_code == 403, write.text
    assert len(catalog._AUDIT_LOG) > audits, "the denial must be audited"

    after = client.get("/graph/nodes/" + node_id, params={"actor": "admin"})
    assert after.json()["properties"]["pii"] is True, "the classification was overwritten"


def test_an_edge_to_a_foreign_node_is_refused(foreign_dataset: str) -> None:
    """An edge touches two nodes and only its source was checked.

    An edge attached to a foreign tenant's node is then withheld from that
    tenant on read, so it would exist and be invisible to the tenant whose graph
    it altered.
    """
    refused = client.post(
        "/graph/edges",
        json={
            "actor": "data-admin",
            "edge_type": "related_dataset",
            "source_id": "crm-customer-master",
            "target_id": foreign_dataset,
        },
    )
    assert refused.status_code == 403, refused.text


def test_the_write_boundary_did_not_close_legitimate_writes(foreign_dataset: str) -> None:
    """Three writes that must still work."""
    own = client.post(
        "/graph/nodes",
        json={
            "actor": "data-admin",
            "node_id": "crm-customer-master:customer_id",
            "kind": "column",
            "label": "customer_id",
            "properties": {"datatype": "string"},
        },
    )
    assert own.status_code == 200, own.text

    crossing = client.post(
        "/graph/nodes",
        json={
            "actor": "admin",
            "node_id": f"{foreign_dataset}:customer_email",
            "kind": "column",
            "label": "customer_email",
            "properties": {"pii": True, "datatype": "string"},
        },
    )
    assert crossing.status_code == 200, crossing.text

    # Shared vocabulary has no owning tenant, matching the read predicate.
    concept = client.post(
        "/graph/nodes", json={"actor": "data-admin", "node_id": "고객", "kind": "concept", "label": "고객"}
    )
    assert concept.status_code == 200, concept.text

    edge = client.post(
        "/graph/edges",
        json={
            "actor": "data-admin",
            "edge_type": "related_dataset",
            "source_id": "crm-customer-master",
            "target_id": "crm-event",
        },
    )
    assert edge.status_code == 200, edge.text


def test_the_write_and_read_boundaries_agree(foreign_dataset: str) -> None:
    """They disagreed, which is the whole defect.

    Enumerated over the node ids a dataset owns, so a node shape that is
    readable-but-writable cannot reappear.
    """
    dataset = catalog._DATA[foreign_dataset]
    node_ids = [foreign_dataset] + [
        f"{foreign_dataset}:{column.name}" for column in dataset.schema
    ]
    assert len(node_ids) >= 2
    for node_id in node_ids:
        readable = client.get("/graph/nodes/" + node_id, params={"actor": "data-admin"})
        writable = client.post(
            "/graph/nodes",
            json={"actor": "data-admin", "node_id": node_id, "kind": "column", "label": "x"},
        )
        assert (readable.status_code == 200) == (writable.status_code == 200), (
            node_id,
            readable.status_code,
            writable.status_code,
        )


def test_the_residual_write_path_distinction_is_declared() -> None:
    """What the fix does *not* close, measured and stated rather than implied.

    Refusing a foreign node while allowing a node whose dataset does not exist
    is distinguishable, so an authenticated **admin** can learn that an id names
    a dataset in a tenant it cannot access. It is not closed here because the
    only way to collapse it is to refuse the creation of any node whose prefix
    is not an accessible dataset, which would forbid legitimate non-dataset
    nodes - a product decision, not a defect fix.

    It is strictly narrower than the oracles this product does close: those were
    reachable anonymously or by any analyst, and this one needs the ``admin``
    role, which ``create`` demands before the tenant check runs.
    """
    anonymous = client.post(
        "/graph/nodes", json={"actor": "anonymous", "node_id": "zeta-secret", "kind": "dataset", "label": "x"}
    )
    analyst = client.post(
        "/graph/nodes", json={"actor": "analyst", "node_id": "zeta-secret", "kind": "dataset", "label": "x"}
    )
    for response in (anonymous, analyst):
        assert response.status_code == 403
        assert "admin" in response.json()["detail"], response.json()
        # The role refusal comes first, so neither learns anything about the id.
        assert "tenant" not in response.json()["detail"]


# --------------------------------------------------------------------------- #
# The preview existence oracle
# --------------------------------------------------------------------------- #


def _prober_visible_rows(prober: str) -> tuple[int, int]:
    decisions = client.get("/policy/decisions", params={"user": prober, "limit": 500})
    audits = client.get("/audit/events", params={"user": prober, "limit": 500})
    return len(decisions.json()), len(audits.json())


def test_a_foreign_and_an_absent_dataset_are_identical_on_every_channel(
    foreign_dataset: str,
) -> None:
    prober = "external-analyst"
    baseline = _prober_visible_rows(prober)
    foreign = client.post(
        f"/browse/{foreign_dataset}/preview",
        json={"user": prober, "purpose": "analysis", "limit": 2},
    )
    after_foreign = _prober_visible_rows(prober)
    absent = client.post(
        "/browse/absent-id-xyz/preview",
        json={"user": prober, "purpose": "analysis", "limit": 2},
    )
    after_absent = _prober_visible_rows(prober)

    assert (foreign.status_code, foreign.text) == (absent.status_code, absent.text)
    foreign_delta = (after_foreign[0] - baseline[0], after_foreign[1] - baseline[1])
    absent_delta = (after_absent[0] - after_foreign[0], after_absent[1] - after_foreign[1])
    assert foreign_delta == absent_delta, (foreign_delta, absent_delta)


def test_neither_refusal_is_filed_in_the_probers_own_scope(foreign_dataset: str) -> None:
    """The mechanism, asserted directly.

    A row naming the probed id in the prober's readable ledger is the oracle,
    whatever the counts happen to be.
    """
    prober = "external-analyst"
    for dataset_id in (foreign_dataset, "absent-id-abc"):
        client.post(
            f"/browse/{dataset_id}/preview",
            json={"user": prober, "purpose": "analysis", "limit": 2},
        )
    readable = client.get("/policy/decisions", params={"user": prober, "limit": 500}).json()
    named = [row for row in readable if row.get("resource") in {foreign_dataset, "absent-id-abc"}]
    assert not named, named


def test_the_owning_tenant_still_sees_attempts_on_its_assets(foreign_dataset: str) -> None:
    """Closing the oracle must not blind the auditor who should see it."""
    prober = "external-analyst"
    client.post(
        f"/browse/{foreign_dataset}/preview",
        json={"user": prober, "purpose": "analysis", "limit": 2},
    )
    crossing = client.get("/policy/decisions", params={"user": "admin", "limit": 500}).json()
    attempts = [
        row
        for row in crossing
        if row.get("subject") == prober and row.get("resource") == foreign_dataset
    ]
    assert attempts, "a platform-admin auditor must see the refused attempt"
    assert all(row["effect"] == "deny" for row in attempts), attempts


# --------------------------------------------------------------------------- #
# A hypothetical answer must not read as a real access attempt.
#
# ``POST /policy/decision`` exists to answer "what would policy say for this
# subject", so ``subject`` is deliberately caller-supplied. The answer was then
# persisted into the compliance ledger unlabelled, attributed to the named
# subject, with no record of who asked. Measured as ``analyst`` asking about
# ``external-analyst``:
#
#     POST /policy/decision {"user": "analyst", "subject": "external-analyst",
#                            "resource": "crm-event", "action": "preview"}
#     -> 200 {"subject": "external-analyst", "effect": "deny",
#             "reason": "tenant boundary denied"}
#     rows readable naming external-analyst:
#       [{"subject": "external-analyst", "resource": "crm-event",
#         "action": "preview", "effect": "deny", ...}]
#
# An auditor reads a refused preview attempt by a different identity in a
# different tenant. No such attempt happened, and the row did not name the
# caller who manufactured it.
# --------------------------------------------------------------------------- #


def test_a_hypothetical_decision_says_so_and_names_who_asked() -> None:
    response = client.post(
        "/policy/decision",
        json={
            "user": "analyst",
            "subject": "external-analyst",
            "resource": "crm-event",
            "action": "preview",
            "purpose": "analysis",
        },
    )
    assert response.status_code == 200, response.text
    obligations = response.json()["obligations"]
    assert obligations["evaluation_mode"] == "hypothetical"
    assert obligations["asked_by"] == "analyst"
    assert obligations["subject_is_caller"] is False

    rows = client.get("/policy/decisions", params={"user": "analyst", "limit": 500}).json()
    named = [row for row in rows if row.get("subject") == "external-analyst"]
    assert named, "the row is still recorded - it is evidence, just labelled"
    for row in named:
        assert row["obligations"]["evaluation_mode"] == "hypothetical", row
        assert row["obligations"]["asked_by"] == "analyst", row


def test_a_real_access_attempt_is_distinguishable_from_a_hypothetical_one() -> None:
    """The property the labelling exists for.

    Without it the two rows are byte-identical in shape, and the only way to
    tell them apart was a missing audit event - which needs cross-surface
    correlation an auditor has no reason to perform.
    """
    client.post(
        "/browse/crm-event/preview", json={"user": "analyst", "purpose": "analysis", "limit": 2}
    )
    client.post(
        "/policy/decision",
        json={"user": "analyst", "subject": "analyst", "resource": "crm-event", "action": "preview"},
    )
    rows = client.get("/policy/decisions", params={"user": "analyst", "limit": 500}).json()
    previews = [row for row in rows if row.get("action") == "preview"]
    real = [row for row in previews if "evaluation_mode" not in (row.get("obligations") or {})]
    hypothetical = [
        row
        for row in previews
        if (row.get("obligations") or {}).get("evaluation_mode") == "hypothetical"
    ]
    assert real, "a genuine attempt must stay unlabelled"
    assert hypothetical, "the hypothetical one must be labelled"


def test_asking_about_yourself_is_marked_as_such() -> None:
    body = client.post(
        "/policy/decision",
        json={"user": "analyst", "resource": "crm-event", "action": "preview"},
    ).json()
    assert body["obligations"]["subject_is_caller"] is True
    assert body["obligations"]["asked_by"] == "analyst"


def test_only_the_hypothetical_route_labels_its_rows() -> None:
    """``provenance`` is opt-in, so no other caller's rows change shape.

    Threading an optional parameter through every branch of ``evaluate`` is the
    kind of change that silently relabels unrelated evidence, so this asserts
    the default stays empty.
    """
    decision = policy.evaluate(
        subject="analyst", resource="crm-event", action="preview", purpose="analysis"
    )
    assert "evaluation_mode" not in decision.obligations
    assert "asked_by" not in decision.obligations
