"""Tenant scoping on the evidence READ path.

Today's producer-side repair stamps every policy decision and audit event with
its owning tenant, and ``tests/test_evidence_tenant_scope.py`` states the reason:
``PostgresEvidenceStore`` declares ``tenant_id TEXT NOT NULL`` and indexes it
first so "consumers scope evidence by it". No consumer could. ``GET
/audit/events`` and ``GET /policy/decisions`` took no actor, and no function on
the read path accepted a tenant argument at all — so one unauthenticated call
returned every tenant's evidence rows. Measured against a real SQLite store:

    GET /audit/events?limit=20  ->  200
    tenants visible in one unauthenticated read: {'bank-b': 1, 'bank-a': 1}

That made the stamp decorative: the column existed, nothing could read by it.
"""

from __future__ import annotations

import inspect
from pathlib import Path
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sdp import catalog, evidence, policy  # noqa: E402
from sdp.api import app  # noqa: E402
from sdp_core import stores  # noqa: E402

client = TestClient(app)


@pytest.fixture(autouse=True)
def _two_tenants():
    """Seed one dataset per tenant and record evidence for each."""
    data = {k: v.model_copy(deep=True) for k, v in catalog._DATA.items()}
    audit = list(catalog._AUDIT_LOG)
    decisions = list(evidence._POLICY_DECISION_LOG)
    base = catalog._DATA["crm-customer-master"]
    for ds_id, tenant in (("bank-a-ds", "bank-a"), ("bank-b-ds", "bank-b")):
        catalog._DATA[ds_id] = base.model_copy(update={"id": ds_id, "tenant_id": tenant})
    for ds_id in ("bank-a-ds", "bank-b-ds"):
        client.post(f"/browse/{ds_id}/preview", json={"user": "admin", "purpose": "analysis"})
    try:
        yield
    finally:
        catalog._DATA.clear()
        catalog._DATA.update(data)
        catalog._AUDIT_LOG.clear()
        catalog._AUDIT_LOG.extend(audit)
        evidence._POLICY_DECISION_LOG.clear()
        evidence._POLICY_DECISION_LOG.extend(decisions)


def _tenants_of(events: list[dict]) -> set[str]:
    return {(e.get("details") or {}).get("tenant_id", "(none)") for e in events}


def test_the_read_path_accepts_a_tenant_scope_at_every_layer() -> None:
    """The stamp is only usable if the whole read path can filter by it."""
    for func in (
        stores.SQLiteEvidenceStore.list_events,
        stores.SQLiteEvidenceStore.list_decisions,
        stores.PostgresEvidenceStore.list_events,
        stores.PostgresEvidenceStore.list_decisions,
        evidence.list_persisted_audit_events,
        evidence.list_policy_decisions,
        catalog.list_audit_events,
    ):
        assert "tenant_ids" in inspect.signature(func).parameters, func.__qualname__


def test_audit_events_require_an_authorized_reader() -> None:
    assert client.get("/audit/events").status_code == 403


def test_audit_events_are_scoped_to_the_reader_tenant() -> None:
    response = client.get("/audit/events", params={"user": "external-analyst", "limit": 50})
    assert response.status_code == 200
    assert _tenants_of(response.json()) <= {"external"}, response.json()


def test_policy_decisions_require_an_authorized_reader_and_are_scoped() -> None:
    assert client.get("/policy/decisions").status_code == 403
    scoped = client.get("/policy/decisions", params={"user": "external-analyst", "limit": 50})
    assert scoped.status_code == 200
    tenants = {(d.get("obligations") or {}).get("tenant_id") for d in scoped.json()}
    assert tenants <= {"external", None}, scoped.json()


def test_platform_admin_reads_every_tenant() -> None:
    """The explicit platform-admin crossing stays explicit."""
    response = client.get("/audit/events", params={"user": "admin", "limit": 100})
    assert response.status_code == 200
    assert {"bank-a", "bank-b"} <= _tenants_of(response.json())


def test_dataset_audit_feed_is_scoped_too() -> None:
    """The per-dataset audit feed is the same ledger behind a different path."""
    assert client.get("/catalog/datasets/bank-a-ds/audit").status_code == 403
    refused = client.get(
        "/catalog/datasets/bank-a-ds/audit", params={"user": "external-analyst"}
    )
    # An actor outside the owning tenant gets 404, matching the rest of the
    # per-dataset discovery surface: a 403 here would confirm the dataset
    # exists, which is the disclosure this scoping exists to prevent. The
    # anonymous 403 above is a different answer to a different question -
    # "no actor at all" is refused before any dataset is looked up.
    assert refused.status_code == 404
    allowed = client.get("/catalog/datasets/bank-a-ds/audit", params={"user": "admin"})
    assert allowed.status_code == 200


def test_accessible_tenant_ids_contract() -> None:
    assert policy.accessible_tenant_ids("admin") is None          # platform-admin: all
    assert policy.accessible_tenant_ids("analyst") == ["demo"]
    assert policy.accessible_tenant_ids("external-analyst") == ["external"]
    assert policy.accessible_tenant_ids("__nobody__") == []
