"""Buyer acceptance for framework-neutral data-management evidence profiles."""

from __future__ import annotations

from fastapi.testclient import TestClient

from sdp.api import app
from sdp.tenant_binding import PURPOSE_HEADER, SUBJECT_HEADER, TENANT_HEADER


client = TestClient(app)


def _headers(
    *,
    subject: str = "admin",
    tenant: str = "demo",
    purpose: str = "glossary_stewardship",
) -> dict[str, str]:
    """Return an explicitly opted-in demo identity for one tenant."""

    return {
        SUBJECT_HEADER: subject,
        TENANT_HEADER: tenant,
        PURPOSE_HEADER: purpose,
    }


def _create_catalog_dataset() -> str:
    """Create one governed dataset parent and return its catalog identifier."""

    response = client.post(
        "/plane/catalog-objects",
        headers=_headers(),
        json={
            "object_kind": "catalog_dataset",
            "object_slug": "billing-settlement-evidence",
            "display_title": "Billing settlement evidence",
            "definition_text": "Usage, invoice, payment, refund, and settlement evidence for reconciliation.",
            "preferred_language": "en",
            "steward_display_name": "Billing Data Steward",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["catalog_object"]["catalog_object_id"]


def test_buyer_builds_evidence_complete_data_management_profile() -> None:
    """Owner, CDE, rule, and observation create an explainable complete profile."""

    catalog_object_id = _create_catalog_dataset()
    profile_url = f"/plane/catalog-objects/{catalog_object_id}/data-management-profile"

    initial = client.get(
        profile_url,
        headers=_headers(subject="analyst", purpose="catalog_browse"),
    )
    assert initial.status_code == 200, initial.text
    assert initial.json()["evidence_complete"] is False
    assert initial.json()["factors"] == {
        "data_owner_present": False,
        "critical_data_element_present": False,
        "quality_rule_present": False,
        "quality_observation_present": False,
    }
    assert "data-owner-assignments" in initial.json()["customer_next_action"]
    assert initial.json()["policy_decision_id"]

    owner = client.post(
        f"/plane/catalog-objects/{catalog_object_id}/data-owner-assignments",
        headers=_headers(),
        json={
            "owner_subject": "billing-operations-owner",
            "owner_display_name": "Billing Operations Owner",
            "valid_from": "2026-08-18T00:00:00Z",
            "evidence_reference": "https://evidence.example.test/decisions/billing-owner-2026",
            "truth_status": "authoritative",
        },
    )
    assert owner.status_code == 200, owner.text
    assert owner.json()["data_owner_assignment"]["owner_display_name"] == "Billing Operations Owner"

    duplicate_owner = client.post(
        f"/plane/catalog-objects/{catalog_object_id}/data-owner-assignments",
        headers=_headers(),
        json={
            "owner_subject": "billing-operations-owner",
            "owner_display_name": "Billing Operations Owner",
            "valid_from": "2026-08-18T00:00:00Z",
            "evidence_reference": "https://evidence.example.test/decisions/billing-owner-2026",
            "truth_status": "authoritative",
        },
    )
    assert duplicate_owner.status_code == 400

    cde = client.post(
        f"/plane/catalog-objects/{catalog_object_id}/critical-data-elements",
        headers=_headers(),
        json={
            "element_key": "settlement_amount",
            "display_name": "Settlement amount",
            "definition_text": "Cash amount paid out by the commerce provider for one settlement.",
            "data_classification": "restricted_financial",
            "evidence_reference": "https://evidence.example.test/dictionary/settlement-amount",
            "truth_status": "authoritative",
        },
    )
    assert cde.status_code == 200, cde.text
    critical_data_element_id = cde.json()["critical_data_element"]["critical_data_element_id"]

    duplicate_cde = client.post(
        f"/plane/catalog-objects/{catalog_object_id}/critical-data-elements",
        headers=_headers(),
        json={
            "element_key": "settlement_amount",
            "display_name": "Settlement amount duplicate",
            "definition_text": "Duplicate definition that must fail closed.",
            "data_classification": "restricted_financial",
            "evidence_reference": "https://evidence.example.test/dictionary/duplicate",
            "truth_status": "proposed",
        },
    )
    assert duplicate_cde.status_code == 400

    rule = client.post(
        f"/plane/critical-data-elements/{critical_data_element_id}/quality-rules",
        headers=_headers(),
        json={
            "rule_code": "settlement_matches_expected_amount",
            "rule_description": "Provider settlement plus provider fee equals the captured invoice amount.",
            "metric_code": "reconciliation_difference",
            "threshold_operator": "equal_to",
            "threshold_value": "0",
            "unit_code": "KRW",
            "evidence_reference": "https://evidence.example.test/controls/three-way-reconciliation",
            "truth_status": "authoritative",
        },
    )
    assert rule.status_code == 200, rule.text
    data_quality_rule_id = rule.json()["data_quality_rule"]["data_quality_rule_id"]

    duplicate_rule = client.post(
        f"/plane/critical-data-elements/{critical_data_element_id}/quality-rules",
        headers=_headers(),
        json={
            "rule_code": "settlement_matches_expected_amount",
            "rule_description": "Duplicate rule that must fail closed.",
            "metric_code": "reconciliation_difference",
            "threshold_operator": "equal_to",
            "threshold_value": "0",
            "unit_code": "KRW",
            "evidence_reference": "https://evidence.example.test/controls/duplicate",
            "truth_status": "proposed",
        },
    )
    assert duplicate_rule.status_code == 400

    observation = client.post(
        f"/plane/quality-rules/{data_quality_rule_id}/observations",
        headers=_headers(),
        json={
            "source_observation_id": "reconciliation_run_2026_08_18",
            "observed_value": "0",
            "observed_at": "2026-08-18T01:00:00Z",
            "quality_status": "passed",
            "evidence_reference": "https://evidence.example.test/runs/reconciliation-2026-08-18",
            "truth_status": "observed",
        },
    )
    assert observation.status_code == 200, observation.text
    assert observation.json()["data_quality_observation"]["quality_status"] == "passed"

    duplicate_observation = client.post(
        f"/plane/quality-rules/{data_quality_rule_id}/observations",
        headers=_headers(),
        json={
            "source_observation_id": "reconciliation_run_2026_08_18",
            "observed_value": "0",
            "observed_at": "2026-08-18T01:00:00Z",
            "quality_status": "passed",
            "evidence_reference": "https://evidence.example.test/runs/reconciliation-2026-08-18",
            "truth_status": "observed",
        },
    )
    assert duplicate_observation.status_code == 400

    complete = client.get(
        profile_url,
        headers=_headers(subject="analyst", purpose="catalog_browse"),
    )
    assert complete.status_code == 200, complete.text
    body = complete.json()
    assert body["evidence_complete"] is True
    assert body["factors"] == {
        "data_owner_present": True,
        "critical_data_element_present": True,
        "quality_rule_present": True,
        "quality_observation_present": True,
    }
    assert body["counts"] == {
        "data_owner_assignments": 1,
        "critical_data_elements": 1,
        "data_quality_rules": 1,
        "data_quality_observations": 1,
    }
    assert body["data_quality_observations"][0]["evidence_reference"].startswith("https://")
    assert "evidence" in body["customer_next_action"].lower()
    assert body["policy_decision_id"]


def test_data_management_profile_is_tenant_isolated() -> None:
    """A foreign tenant cannot discover a catalog object's governance profile."""

    catalog_object_id = _create_catalog_dataset()
    response = client.get(
        f"/plane/catalog-objects/{catalog_object_id}/data-management-profile",
        headers=_headers(subject="external-analyst", tenant="external", purpose="catalog_browse"),
    )
    assert response.status_code == 404
