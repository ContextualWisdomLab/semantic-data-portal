"""Tenant attribution of evidence rows in the ``sdp_core`` evidence stores.

``PostgresEvidenceStore`` declares ``tenant_id TEXT NOT NULL`` and indexes it
first (``idx_*_tenant_resource_created``), so consumers scope evidence by it.
The producer-side helpers must therefore never invent a value: a row that
cannot be attributed is marked unresolved rather than filed under ``demo``,
which is a *real* tenant in this product (the seeded datasets live in it).
These tests pin the helpers directly — no database is contacted.
"""

from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sdp_core import stores  # noqa: E402
from sdp_core.contracts import AuditEvent, PolicyDecision  # noqa: E402


def _decision(**obligations: object) -> PolicyDecision:
    return PolicyDecision(
        decision_id="d-1",
        subject="someone",
        resource="some-dataset",
        action="preview",
        effect="allow",
        reason="ok",
        obligations=obligations,
    )


def _event(**details: object) -> AuditEvent:
    return AuditEvent(
        id="e-1",
        actor="someone",
        action="browse.preview",
        resource="some-dataset",
        result="allowed",
        details=details,
    )


def test_policy_tenant_id_uses_the_stamped_tenant() -> None:
    assert stores._policy_tenant_id(_decision(tenant_id="acme-corp")) == "acme-corp"


def test_audit_tenant_id_accepts_either_detail_key() -> None:
    assert stores._audit_tenant_id(_event(tenant_id="acme-corp")) == "acme-corp"
    assert stores._audit_tenant_id(_event(tenant="acme-corp")) == "acme-corp"


def test_unattributable_rows_are_never_filed_under_the_real_demo_tenant() -> None:
    """The old fallback was ``or "demo"``: an unstamped row silently claimed the
    seeded ``demo`` tenant, so a tenant-scoped reader saw rows that were not
    theirs and missed rows that were."""
    assert stores._policy_tenant_id(_decision()) == stores.UNRESOLVED_TENANT_ID
    assert stores._audit_tenant_id(_event()) == stores.UNRESOLVED_TENANT_ID
    assert stores.UNRESOLVED_TENANT_ID != "demo"
    # An empty tenant claim is unresolved too, not demo.
    assert stores._policy_tenant_id(_decision(tenant_id="")) == stores.UNRESOLVED_TENANT_ID
    assert stores._audit_tenant_id(_event(tenant_id="")) == stores.UNRESOLVED_TENANT_ID


def test_postgres_migration_backfill_does_not_claim_the_demo_tenant() -> None:
    """The legacy-row backfill in the Postgres DDL has the same misattribution
    risk as the runtime fallback, so it uses the same unresolved marker."""
    ddl = Path(__file__).resolve().parents[1] / "src" / "sdp_core" / "stores.py"
    source = ddl.read_text(encoding="utf-8")
    assert "'demo')" not in source, "the DDL must not backfill legacy rows into the demo tenant"
    assert source.count("UNRESOLVED_TENANT_ID") >= 3


def test_append_audit_event_does_not_discard_the_event_without_a_store() -> None:
    """``append_audit_event`` returned the event but wrote nothing when no store
    was configured, so the OIDC group-to-role mapping audit events — the record of
    who was granted admin or platform-admin — were lost while the API still
    handed back an ``audit_event_id``. Catalog events survived the same
    configuration only because ``catalog._record_audit_event`` has its own
    in-memory fallback that this path did not use.
    """
    from sdp import evidence

    previous = evidence.configure_evidence_store(None)
    try:
        evidence._AUDIT_EVENT_LOG.clear()
        event = AuditEvent(
            id="oidc-1",
            actor="someone@example.com",
            action="oidc_group_role_mapping",
            resource="enterprise/auth/oidc",
            result="mapped",
            details={"tenant_id": "demo", "granted_roles": ["platform-admin"]},
        )
        evidence.append_audit_event(event)
        stored = evidence.list_persisted_audit_events(limit=10)
        assert [e.id for e in stored] == ["oidc-1"]
    finally:
        evidence._AUDIT_EVENT_LOG.clear()
        evidence.configure_evidence_store(previous)


# --------------------------------------------------------------------------- #
# The producer side: who gets to choose the tenant a row is filed under.
#
# ``_effective_tenant_id`` honoured a caller-supplied ``target_tenant_id``
# unconditionally, and ``evaluate``'s role check runs *after* the stamp. So a
# caller with no actor at all could pick another tenant's ledger. Measured with
# an unauthenticated ``POST /catalog/datasets`` carrying
# ``tenant_id: "zeta-bank"``:
#
#     response -> 403 "create 작업은 admin 권한만 가능"
#     decision -> subject=anonymous action=create resource=forged-probe
#                 effect=deny   filed under tenant: zeta-bank
#
# readable by that tenant's auditor, invisible to the caller's own. ``tenant_id``
# is a free-form string, so rows could be filed under tenants that do not exist.
# --------------------------------------------------------------------------- #


def test_a_caller_cannot_file_a_decision_under_a_tenant_it_cannot_reach() -> None:
    from sdp.policy import _effective_tenant_id

    # An unauthenticated caller naming someone else's tenant.
    assert _effective_tenant_id("anonymous", "forged-probe", "zeta-bank") == (
        stores.UNRESOLVED_TENANT_ID
    )
    # A reader scoped to its own tenant naming another one.
    assert _effective_tenant_id("analyst", "forged-probe", "zeta-bank") == "demo"
    # Its own tenant is honoured.
    assert _effective_tenant_id("analyst", "forged-probe", "demo") == "demo"
    # A platform-admin crosses deliberately, which is the documented exception.
    assert _effective_tenant_id("admin", "forged-probe", "zeta-bank") == "zeta-bank"


def test_an_unauthenticated_create_leaves_its_refusal_in_no_ones_ledger() -> None:
    """End to end, through the route that passes the body's tenant_id."""
    from fastapi.testclient import TestClient

    from sdp import evidence
    from sdp.api import app

    client = TestClient(app, raise_server_exceptions=False)
    body = {
        "id": "forged-probe-ds",
        "tenant_id": "zeta-bank",
        "title": "제목",
        "description": "설명",
        "domain": "customer_intelligence",
        "owner": "owner",
        "steward": "steward",
        "tags": ["tag_one"],
        "terms": ["고객"],
        "sensitivity": "internal",
        "source_system": "postgresql://analytics.dw/crm",
        "update_frequency": "daily",
        "quality_score": 0.9,
        "freshness_score": 0.9,
        "schema": [
            {
                "name": "column_one",
                "datatype": "string",
                "nullable_ratio": 0.0,
                "distinct_ratio": 1.0,
                "quality_issues": [],
                "pii": False,
            }
        ],
        "distributions": [],
        "mappings": [],
        "related_datasets": [],
        "profile": {},
    }
    before = len(evidence._POLICY_DECISION_LOG)
    refused = client.post("/catalog/datasets", json=body)  # no actor at all
    assert refused.status_code == 403, refused.text

    planted = evidence._POLICY_DECISION_LOG[before:]
    assert planted, "the refusal must still be recorded"
    for decision in planted:
        assert decision.obligations["tenant_id"] == stores.UNRESOLVED_TENANT_ID, (
            f"filed under {decision.obligations['tenant_id']!r}"
        )


# --------------------------------------------------------------------------- #
# Upgrade in place: the two backends must recover the same tenant.
#
# ``SQLiteEvidenceStore._add_tenant_column`` added the column with the
# unresolved default and stopped, while ``PostgresEvidenceStore._initialize``
# recovers the tenant from the stored payload. The two ship as
# protocol-equivalent - docker-compose runs an instance of each to check exactly
# that - so the same upgrade on the same row gave ``unresolved`` on SQLite and
# ``demo`` on Postgres. Measured on a pre-tenant_id database whose payloads
# carry ``tenant_id: "demo"``:
#
#     after upgrade, policy_decisions.tenant_id -> ['unresolved']
#     after upgrade, audit_events.tenant_id     -> ['unresolved']
#
# On SQLite the row then became invisible to its owning tenant's auditor and
# visible only to platform-admin, and SQLite is the documented demo/pilot
# deployment on a persistent volume - the upgrade-in-place case.
# --------------------------------------------------------------------------- #

LEGACY_DECISION_COLUMNS = (
    "decision_id TEXT PRIMARY KEY, subject TEXT NOT NULL, resource TEXT NOT NULL, "
    "action TEXT NOT NULL, effect TEXT NOT NULL, payload TEXT NOT NULL, "
    "recorded_at TEXT NOT NULL"
)
LEGACY_EVENT_COLUMNS = (
    "id TEXT PRIMARY KEY, actor TEXT NOT NULL, action TEXT NOT NULL, "
    "resource TEXT NOT NULL, result TEXT NOT NULL, decision_id TEXT, "
    "payload TEXT NOT NULL, created_at TEXT NOT NULL"
)


def _legacy_sqlite_evidence(path, *, detail_key: str = "tenant_id"):
    """Build a pre-``tenant_id`` evidence database with attributable payloads."""
    import json
    import sqlite3

    connection = sqlite3.connect(path)
    connection.execute(f"CREATE TABLE policy_decisions ({LEGACY_DECISION_COLUMNS})")
    connection.execute(f"CREATE TABLE audit_events ({LEGACY_EVENT_COLUMNS})")
    connection.execute(
        "INSERT INTO policy_decisions VALUES (?,?,?,?,?,?,?)",
        (
            "d-legacy",
            "analyst",
            "crm-customer-master",
            "preview",
            "allow",
            json.dumps(
                {
                    "decision_id": "d-legacy",
                    "subject": "analyst",
                    "resource": "crm-customer-master",
                    "action": "preview",
                    "effect": "allow",
                    "reason": "ok",
                    "obligations": {"tenant_id": "demo", "masking": []},
                }
            ),
            "2026-01-01T00:00:00Z",
        ),
    )
    connection.execute(
        "INSERT INTO audit_events VALUES (?,?,?,?,?,?,?,?)",
        (
            "a-legacy",
            "analyst",
            "browse.preview",
            "crm-customer-master",
            "allowed",
            "d-legacy",
            json.dumps(
                {
                    "id": "a-legacy",
                    "actor": "analyst",
                    "action": "browse.preview",
                    "resource": "crm-customer-master",
                    "result": "allowed",
                    "reason": "ok",
                    "decision_id": "d-legacy",
                    "details": {detail_key: "demo"},
                    "created_at": "2026-01-01T00:00:00Z",
                }
            ),
            "2026-01-01T00:00:00Z",
        ),
    )
    connection.commit()
    connection.close()


def test_the_sqlite_upgrade_recovers_the_tenant_from_the_payload(tmp_path) -> None:
    from sdp_core import SQLiteEvidenceStore

    path = tmp_path / "legacy-evidence.sqlite3"
    _legacy_sqlite_evidence(path)

    store = SQLiteEvidenceStore(path)  # upgrade in place

    # The row belongs to its owning tenant's auditor, not only to platform-admin.
    assert len(store.list_decisions(tenant_ids=["demo"])) == 1
    assert len(store.list_events(tenant_ids=["demo"])) == 1
    # and is not readable by another tenant
    assert store.list_decisions(tenant_ids=["other"]) == []
    assert store.list_events(tenant_ids=["other"]) == []


def test_the_sqlite_upgrade_honours_the_tenant_spelling_the_reader_honours(tmp_path) -> None:
    """``_audit_tenant_id`` accepts ``details.tenant`` as well as ``tenant_id``.

    A backfill that recovers only one spelling drops rows the reader would have
    attributed correctly. The Postgres statement had the same gap.
    """
    from sdp_core import SQLiteEvidenceStore

    path = tmp_path / "legacy-evidence-alt-key.sqlite3"
    _legacy_sqlite_evidence(path, detail_key="tenant")

    store = SQLiteEvidenceStore(path)
    assert len(store.list_events(tenant_ids=["demo"])) == 1


def test_an_unattributable_legacy_row_still_falls_back_to_unresolved(tmp_path) -> None:
    """Recovering what is there must not invent what is not."""
    import json
    import sqlite3

    from sdp_core import SQLiteEvidenceStore

    path = tmp_path / "legacy-evidence-no-tenant.sqlite3"
    connection = sqlite3.connect(path)
    connection.execute(f"CREATE TABLE policy_decisions ({LEGACY_DECISION_COLUMNS})")
    connection.execute(f"CREATE TABLE audit_events ({LEGACY_EVENT_COLUMNS})")
    connection.execute(
        "INSERT INTO policy_decisions VALUES (?,?,?,?,?,?,?)",
        (
            "d-anon",
            "analyst",
            "some-dataset",
            "preview",
            "deny",
            json.dumps(
                {
                    "decision_id": "d-anon",
                    "subject": "analyst",
                    "resource": "some-dataset",
                    "action": "preview",
                    "effect": "deny",
                    "reason": "no tenant recorded",
                    "obligations": {},
                }
            ),
            "2026-01-01T00:00:00Z",
        ),
    )
    connection.commit()
    connection.close()

    store = SQLiteEvidenceStore(path)
    assert store.list_decisions(tenant_ids=["demo"]) == []
    assert len(store.list_decisions(tenant_ids=None)) == 1
