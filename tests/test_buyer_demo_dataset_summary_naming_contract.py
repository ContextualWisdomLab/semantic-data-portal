from __future__ import annotations

from sdp_core.demo_seed import BuyerDemoDatasetSummary, buyer_demo_dataset_summaries
from sdp_core.readiness import buyer_demo_activation_plan


def test_buyer_demo_dataset_summary_owns_semantic_catalog_fields() -> None:
    assert "dataset_id" in BuyerDemoDatasetSummary.model_fields
    assert "dataset_title" in BuyerDemoDatasetSummary.model_fields
    assert "dataset_domain" in BuyerDemoDatasetSummary.model_fields
    assert "dataset_sensitivity" in BuyerDemoDatasetSummary.model_fields
    assert "dataset_steward" in BuyerDemoDatasetSummary.model_fields

    assert "id" not in BuyerDemoDatasetSummary.model_fields
    assert "title" not in BuyerDemoDatasetSummary.model_fields
    assert "domain" not in BuyerDemoDatasetSummary.model_fields
    assert "sensitivity" not in BuyerDemoDatasetSummary.model_fields
    assert "steward" not in BuyerDemoDatasetSummary.model_fields


def test_buyer_demo_dataset_summary_preserves_legacy_wire_keys() -> None:
    summary = BuyerDemoDatasetSummary(
        id="crm-customer-master",
        title="Customer master",
        domain="customer",
        source_type="sql",
        source_system="postgresql://analytics.dw/customer",
        sensitivity="medium",
        steward="data-steward",
        acceptance_role="priority_dataset",
    )

    assert summary.dataset_id == "crm-customer-master"
    assert summary.dataset_title == "Customer master"
    assert summary.dataset_domain == "customer"
    assert summary.dataset_sensitivity == "medium"
    assert summary.dataset_steward == "data-steward"

    wire_payload = summary.model_dump(mode="json")
    assert wire_payload["id"] == "crm-customer-master"
    assert wire_payload["title"] == "Customer master"
    assert wire_payload["domain"] == "customer"
    assert wire_payload["sensitivity"] == "medium"
    assert wire_payload["steward"] == "data-steward"
    assert "dataset_id" not in wire_payload


def test_seeded_and_nested_demo_payload_keep_catalog_wire_contract() -> None:
    summary = buyer_demo_dataset_summaries()[0]
    assert summary.dataset_id == "crm-customer-master"

    plan_payload = buyer_demo_activation_plan().model_dump(mode="json")
    nested_summary = plan_payload["demo_datasets"][0]
    assert nested_summary["id"] == "crm-customer-master"
    assert "dataset_id" not in nested_summary
