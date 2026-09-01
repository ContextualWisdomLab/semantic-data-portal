from __future__ import annotations

from sdp_core.kpis import KPIFramework, SaleabilityKPI, enterprise_kpi_framework


def test_saleability_kpi_owns_semantic_fields() -> None:
    assert "kpi_id" in SaleabilityKPI.model_fields
    assert "kpi_label" in SaleabilityKPI.model_fields
    assert "kpi_definition" in SaleabilityKPI.model_fields
    assert "kpi_target" in SaleabilityKPI.model_fields
    assert "review_cadence" in SaleabilityKPI.model_fields
    assert "kpi_owner" in SaleabilityKPI.model_fields
    assert "kpi_guardrails" in SaleabilityKPI.model_fields
    assert "implementation_status" in SaleabilityKPI.model_fields

    for legacy_field_name in (
        "id",
        "label",
        "definition",
        "target",
        "cadence",
        "owner",
        "guardrails",
        "status",
    ):
        assert legacy_field_name not in SaleabilityKPI.model_fields


def test_kpi_framework_owns_semantic_product_name() -> None:
    assert "product_name" in KPIFramework.model_fields
    assert "product" not in KPIFramework.model_fields


def test_kpi_framework_preserves_public_wire_contract() -> None:
    framework_payload = enterprise_kpi_framework().model_dump(mode="json")

    assert framework_payload["product"] == "Semantic Data Portal"
    assert "product_name" not in framework_payload

    kpi_payload = framework_payload["primary_kpis"][0]
    assert set(("id", "label", "definition", "target", "cadence", "owner", "guardrails", "status")) <= kpi_payload.keys()
    assert "kpi_id" not in kpi_payload
    assert "implementation_status" not in kpi_payload
