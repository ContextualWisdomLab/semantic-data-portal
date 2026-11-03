"""A refused catalog mutation leaves both halves of the evidence, not one.

``CLAUDE.md`` states this product's governance invariant: a policy evaluation
**and** an evidence record accompany every catalog mutation and every
browse/query path. The browse paths honoured both halves on a denial -
``browse.py`` calls ``ingest_event(decision="denied", ...)`` - and the four
catalog mutations evaluated policy and then raised, so a refused attempt left a
decision and no audit row. Measured per verb as an unauthorized actor::

    PATCH  /catalog/datasets/{id}            -> 403  decisions +1  audits +0
    POST   /catalog/datasets/{id}/publish    -> 403  decisions +1  audits +0
    POST   /catalog/datasets/{id}/deprecate  -> 403  decisions +1  audits +0
    POST   /catalog/datasets                 -> 403  decisions +1  audits +0

A refused attempt is exactly what an auditor looks for, and it was absent from
``/audit/events`` and from ``/catalog/datasets/{id}/audit``.

``tests/test_governed_write_evidence.py`` already asserted the pairing, but its
``GOVERNED_WRITES`` list covers ``/ontology/concepts``, ``/ontology/patches``
and ``/graph/edges`` - the three routes that share ``_authorize_graph_write``,
which audits. The four catalog mutations authorize inline, and a hand-written
list of governed writes is exactly the shape that leaves them out. This module
derives its coverage from the route table instead: every catalog mutation the
app serves must appear here, so a fifth one cannot be added without either a
case or an explicit decision.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from sdp import catalog, evidence
from sdp.api import app

client = TestClient(app, raise_server_exceptions=False)

_DATASET = "crm-customer-master"
_UNAUTHORIZED = "analyst"

_VALID_CREATE = {
    "title": "거부 증빙 픽스처",
    "description": "d",
    "owner": "owner@example.org",
    "steward": "steward@example.org",
    "domain": "customer",
    "source_system": "postgresql://analytics.dw:5432/crm",
    "sensitivity": "internal",
    "update_frequency": "daily",
    "quality_score": 0.9,
    "freshness_score": 0.9,
}

# (route, method, body, the action the audit row must carry)
CATALOG_MUTATIONS = (
    ("/catalog/datasets", "POST", {**_VALID_CREATE, "actor": _UNAUTHORIZED},
     "dataset.register"),
    (f"/catalog/datasets/{_DATASET}", "PATCH", {"actor": _UNAUTHORIZED, "title": "t"},
     "dataset.patch"),
    (f"/catalog/datasets/{_DATASET}/publish", "POST", {"actor": _UNAUTHORIZED},
     "dataset.publish"),
    (f"/catalog/datasets/{_DATASET}/deprecate", "POST", {"actor": _UNAUTHORIZED},
     "dataset.deprecate"),
)


def _call(path: str, method: str, body: dict):
    """Issue one mutation request."""
    if method == "POST":
        return client.post(path, json=body, params={"user": _UNAUTHORIZED})
    return client.patch(path, json=body, params={"user": _UNAUTHORIZED})


@pytest.mark.parametrize(
    "path,method,body,action",
    CATALOG_MUTATIONS,
    ids=[row[3] for row in CATALOG_MUTATIONS],
)
def test_a_refused_catalog_mutation_records_both_halves(
    path: str, method: str, body: dict, action: str
) -> None:
    """One decision and one audit row, for a refusal as much as for a write."""
    decisions_before = len(evidence.list_policy_decisions(limit=5000, tenant_ids=None))
    audits_before = len(catalog.list_audit_events(limit=5000, tenant_ids=None))

    response = _call(path, method, body)
    assert response.status_code in {403, 404}, response.text

    decisions_after = len(evidence.list_policy_decisions(limit=5000, tenant_ids=None))
    audits_after = len(catalog.list_audit_events(limit=5000, tenant_ids=None))
    assert decisions_after - decisions_before == 1, "the decision half is missing"
    assert audits_after - audits_before == 1, (
        f"{method} {path} was refused without an audit row"
    )

    row = catalog.list_audit_events(limit=5000, tenant_ids=None)[0]
    assert row.action == action, row
    assert row.result == "denied", row
    assert row.reason, "the row records no reason"
    assert row.decision_id, "the row is not linked to its decision"


@pytest.mark.parametrize(
    "path,method,body,action",
    CATALOG_MUTATIONS,
    ids=[row[3] for row in CATALOG_MUTATIONS],
)
def test_the_refusal_row_is_linked_to_the_decision_it_records(
    path: str, method: str, body: dict, action: str
) -> None:
    """A row and a decision that cannot be joined are two unrelated facts."""
    response = _call(path, method, body)
    assert response.status_code in {403, 404}, response.text
    row = catalog.list_audit_events(limit=5000, tenant_ids=None)[0]
    decision_ids = {
        decision.decision_id
        for decision in evidence.list_policy_decisions(limit=5000, tenant_ids=None)
    }
    assert row.decision_id in decision_ids, (
        "the audit row names a decision id that is not in the decision feed"
    )
    assert row.details.get("policy_decision_id") == row.decision_id


def test_every_catalog_mutation_route_is_covered_here() -> None:
    """Derived from the route table, because a hand-written list left these out.

    ``test_governed_write_evidence.GOVERNED_WRITES`` is such a list, and it
    covers only the three routes that share the auditing gate. Enumerating the
    app's own mutation routes means a fifth one fails this test until it is
    either given a case or consciously excluded.
    """
    served = {
        (method, route.path)
        for route in app.routes
        for method in (getattr(route, "methods", None) or set())
        if route.path.startswith("/catalog/datasets") and method in {"POST", "PATCH"}
    }
    covered = {
        ("POST", "/catalog/datasets"),
        ("PATCH", "/catalog/datasets/{dataset_id}"),
        ("POST", "/catalog/datasets/{dataset_id}/publish"),
        ("POST", "/catalog/datasets/{dataset_id}/deprecate"),
    }
    assert served == covered, (
        "the catalog mutation routes this app serves and the ones covered here "
        f"disagree; uncovered: {sorted(served - covered)}, "
        f"stale: {sorted(covered - served)}"
    )


def test_an_authorized_mutation_still_records_one_pair() -> None:
    """The denial row must not double-count an allowed write."""
    decisions_before = len(evidence.list_policy_decisions(limit=5000, tenant_ids=None))
    audits_before = len(catalog.list_audit_events(limit=5000, tenant_ids=None))

    allowed = client.patch(
        f"/catalog/datasets/{_DATASET}",
        json={"actor": "admin", "title": "허용된 변경"},
        params={"user": "admin"},
    )
    assert allowed.status_code == 200, allowed.text

    decisions_after = len(evidence.list_policy_decisions(limit=5000, tenant_ids=None))
    audits_after = len(catalog.list_audit_events(limit=5000, tenant_ids=None))
    assert decisions_after - decisions_before == 1
    assert audits_after - audits_before == 1
    row = catalog.list_audit_events(limit=5000, tenant_ids=None)[0]
    assert row.result == "success", row


def test_an_out_of_scope_refusal_is_recorded_with_its_real_reason() -> None:
    """The response withholds the reason; the ledger keeps it.

    An out-of-scope dataset answers 404 with a generic detail so neither the
    status nor the body is an existence oracle. The audit row - which the
    refused caller cannot read - keeps the reason the engine gave, which is the
    split ``browse`` already makes.
    """
    base = catalog._DATA[_DATASET]
    catalog._DATA["refusal-evidence-foreign"] = base.model_copy(
        update={"id": "refusal-evidence-foreign", "tenant_id": "unreachable-tenant"}
    )
    audits_before = len(catalog.list_audit_events(limit=5000, tenant_ids=None))

    response = client.patch(
        "/catalog/datasets/refusal-evidence-foreign",
        json={"actor": _UNAUTHORIZED, "title": "t"},
        params={"user": _UNAUTHORIZED},
    )
    assert response.status_code == 404, response.text
    assert "tenant" not in response.json()["detail"].lower()

    assert len(catalog.list_audit_events(limit=5000, tenant_ids=None)) == (
        audits_before + 1
    ), "an out-of-scope refusal left no audit row"
    row = catalog.list_audit_events(limit=5000, tenant_ids=None)[0]
    assert row.result == "denied"
    assert row.reason and row.reason != response.json()["detail"], (
        "the ledger records the same generic string the response returned, so "
        "the real reason was lost"
    )
