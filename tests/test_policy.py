"""Governance policy deny-path regression tests.

``sdp.policy.evaluate`` is the single choke point every data-access route passes
through, and each decision is recorded as evidence. These pin the security-
critical *deny* branches directly (nonexistent resource, critical-sensitivity
gating, mutation-role gating) so a future refactor cannot silently downgrade a
deny to an allow. Every evaluation still records a PolicyDecision, so the
in-memory evidence log is snapshot/restored to keep tests isolated.
"""

from __future__ import annotations

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sdp import catalog, evidence, policy  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate_state():
    """Snapshot/restore the module-level catalog + policy-decision evidence log."""
    data = {k: v.model_copy(deep=True) for k, v in catalog._DATA.items()}
    decisions = list(evidence._POLICY_DECISION_LOG)
    try:
        yield
    finally:
        catalog._DATA.clear()
        catalog._DATA.update(data)
        evidence._POLICY_DECISION_LOG.clear()
        evidence._POLICY_DECISION_LOG.extend(decisions)


def test_evaluate_denies_nonexistent_dataset() -> None:
    """A data-access action on a missing resource is denied (not silently allowed)."""
    decision = policy.evaluate(
        subject="admin", resource="__no_such_dataset__", action="query", purpose="analysis"
    )
    assert decision.effect == "deny"
    assert "존재하지 않는" in decision.reason


def test_evaluate_denies_critical_sensitivity_for_non_admin() -> None:
    """A non-admin cannot access a `critical`-sensitivity asset; masking is obligated."""
    base = catalog._DATA["crm-customer-master"]
    catalog._DATA["critical-asset"] = base.model_copy(
        update={"id": "critical-asset", "sensitivity": "critical"}
    )
    decision = policy.evaluate(
        subject="analyst", resource="critical-asset", action="query", purpose="analysis"
    )
    assert decision.effect == "deny"
    assert decision.obligations.get("redact") is True
    # An admin is allowed through the same critical asset (the branch is role-gated, not blanket).
    admin_decision = policy.evaluate(
        subject="admin", resource="critical-asset", action="query", purpose="analysis"
    )
    assert admin_decision.effect == "allow"


def test_evaluate_denies_mutation_for_non_admin() -> None:
    """publish/patch/deprecate on an accessible asset require admin; a reader is denied."""
    decision = policy.evaluate(
        subject="analyst", resource="crm-customer-master", action="patch", purpose="analysis"
    )
    assert decision.effect == "deny"
    assert decision.obligations.get("required_role") == "admin"


def test_is_mutable_reflects_allow_deny() -> None:
    """`is_mutable` is True only when the underlying evaluation allows the mutation."""
    assert policy.is_mutable("admin", "create", "crm-customer-master") is True
    assert policy.is_mutable("analyst", "create", "crm-customer-master") is False


def test_evaluate_records_evidence_for_every_decision() -> None:
    """Each evaluation appends exactly one PolicyDecision to the evidence log."""
    before = len(evidence._POLICY_DECISION_LOG)
    policy.evaluate(subject="analyst", resource="crm-customer-master", action="query", purpose="analysis")
    assert len(evidence._POLICY_DECISION_LOG) == before + 1


# --- tenant attribution of evidence rows ---------------------------------


def _external_dataset(**overrides: object) -> None:
    """Seed a dataset owned by tenant ``external`` (where ``external-analyst`` lives).

    An in-tenant actor is what makes the non-tenant-boundary deny branches
    reachable: a cross-tenant resource short-circuits all of them.
    """
    base = catalog._DATA["crm-customer-master"]
    catalog._DATA["external-customer-master"] = base.model_copy(
        update={"id": "external-customer-master", "tenant_id": "external", **overrides}
    )


@pytest.mark.parametrize(
    "subject,action,purpose,sensitivity,expected_effect",
    [
        ("external-analyst", "preview", "analysis", "medium", "allow"),
        ("analyst", "preview", "analysis", "medium", "deny"),           # tenant boundary
        ("external-analyst", "preview", "analysis", "critical", "deny"),  # critical sensitivity
        ("external-analyst", "preview", "external-export", "medium", "deny"),  # export purpose
        ("external-analyst", "publish", "analysis", "medium", "deny"),   # mutation role
    ],
)
def test_every_decision_branch_stamps_the_owning_tenant(
    subject: str, action: str, purpose: str, sensitivity: str, expected_effect: str
) -> None:
    """The evidence store scopes rows by ``obligations['tenant_id']`` (and marks
    the column ``NOT NULL`` with a tenant-leading index), so every branch must
    stamp it. Before this contract only the tenant-boundary deny did, and the
    store's ``or "demo"`` fallback filed the rest under the real ``demo``
    tenant - a cross-tenant misattribution, not a missing value.
    """
    _external_dataset(sensitivity=sensitivity)
    decision = policy.evaluate(
        subject=subject, resource="external-customer-master", action=action, purpose=purpose
    )
    assert decision.effect == expected_effect
    assert decision.obligations.get("tenant_id") == "external"


def test_decision_without_a_resolvable_tenant_is_not_attributed_to_demo() -> None:
    """An unknown subject acting on an unknown resource belongs to no tenant.
    Recording that honestly beats claiming the real ``demo`` tenant owns it."""
    decision = policy.evaluate(
        subject="__nobody__", resource="__no_such_dataset__", action="query", purpose="analysis"
    )
    assert decision.obligations.get("tenant_id") == policy.UNRESOLVED_TENANT_ID
    assert decision.obligations.get("tenant_id") != "demo"


def test_decision_on_a_tenantless_resource_uses_the_actor_tenant() -> None:
    """``create`` and catalog discovery name no existing dataset, so the row
    belongs to the actor's tenant."""
    decision = policy.evaluate(
        subject="admin", resource="brand-new-dataset", action="create", purpose="analysis"
    )
    assert decision.obligations.get("tenant_id") == "demo"  # the admin's own tenant


def test_create_denies_a_tenant_the_actor_cannot_access() -> None:
    """``create`` names a dataset that does not exist yet, so the owning tenant
    cannot be read from the catalog — it comes from the request. The create branch
    returned before the tenant check, so an admin in one tenant could register a
    dataset owned by another: measured with ``data-admin`` (tenant ``demo``, roles
    ['admin','data-analyst'], NOT platform-admin) planting ``tenant_id=acme-bank``
    and getting 200, while PATCH and PREVIEW on that same dataset returned 403.
    """
    decision = policy.evaluate(
        subject="data-admin",
        resource="planted-in-acme",
        action="create",
        purpose="catalog",
        target_tenant_id="acme-bank",
    )
    assert decision.effect == "deny"
    assert decision.reason == "tenant boundary denied"
    # The evidence row belongs to the tenant whose namespace was targeted.
    assert decision.obligations.get("tenant_id") == "acme-bank"


def test_create_allows_the_actor_own_tenant_and_platform_admin_crossing() -> None:
    """The fix must not break legitimate creates: an actor's own tenant, and the
    explicit platform-admin cross-tenant path."""
    own = policy.evaluate(
        subject="data-admin", resource="new-ds", action="create", purpose="catalog",
        target_tenant_id="demo",
    )
    assert own.effect == "allow"

    crossing = policy.evaluate(
        subject="admin", resource="new-ds", action="create", purpose="catalog",
        target_tenant_id="acme-bank",
    )
    assert crossing.effect == "allow"  # admin holds platform-admin

    # Omitting the target keeps the previous behaviour for callers that cannot name one.
    legacy = policy.evaluate(
        subject="data-admin", resource="new-ds", action="create", purpose="catalog"
    )
    assert legacy.effect == "allow"
