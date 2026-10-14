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
