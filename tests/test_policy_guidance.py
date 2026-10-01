"""Denial guidance must describe an effective, authorized next action."""

import pytest

from sdp import evidence, policy


@pytest.fixture(autouse=True)
def isolate_policy_evidence():
    decisions = list(evidence._POLICY_DECISION_LOG)
    yield
    evidence._POLICY_DECISION_LOG[:] = decisions


def test_tenant_denial_does_not_suggest_an_ineffective_header():
    decision = policy.evaluate("external-analyst", "crm-customer-master", "query", "analysis")
    assert decision.effect == "deny"
    assert "X-CWL-Tenant-Reference" not in decision.reason
    assert "거버넌스" in decision.reason
    assert decision.obligations["actor_tenant_id"] == "external"
    assert evidence._POLICY_DECISION_LOG[-1].decision_id == decision.decision_id


def test_export_denial_does_not_suggest_relabeling_the_purpose():
    decision = policy.evaluate("analyst", "crm-customer-master", "query", "external-export")
    assert decision.effect == "deny"
    assert "purpose=analysis" not in decision.reason
    assert "분석 목적" not in decision.reason
    assert "admin/platform-admin" in decision.reason
    assert decision.obligations == {"required_role": "admin"}
    assert evidence._POLICY_DECISION_LOG[-1].decision_id == decision.decision_id


def test_authorized_admin_export_still_succeeds():
    decision = policy.evaluate("admin", "crm-customer-master", "query", "external-export")
    assert decision.effect == "allow"
    assert evidence._POLICY_DECISION_LOG[-1].decision_id == decision.decision_id
