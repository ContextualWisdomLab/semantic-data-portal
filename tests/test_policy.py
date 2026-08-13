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
