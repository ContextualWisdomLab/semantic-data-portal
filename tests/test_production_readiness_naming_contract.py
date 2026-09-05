from __future__ import annotations

from sdp_core.production import (
    ProductionIntegration,
    ProductionReadinessManifest,
    enterprise_production_readiness_manifest,
)


def test_production_integration_owns_semantic_fields() -> None:
    assert "production_integration_id" in ProductionIntegration.model_fields
    assert "integration_label" in ProductionIntegration.model_fields
    assert "integration_status" in ProductionIntegration.model_fields
    assert "id" not in ProductionIntegration.model_fields
    assert "label" not in ProductionIntegration.model_fields
    assert "status" not in ProductionIntegration.model_fields


def test_production_manifest_owns_semantic_fields() -> None:
    assert "product_name" in ProductionReadinessManifest.model_fields
    assert "production_integrations" in ProductionReadinessManifest.model_fields
    assert "product" not in ProductionReadinessManifest.model_fields
    assert "integrations" not in ProductionReadinessManifest.model_fields


def test_production_readiness_preserves_public_wire_contract() -> None:
    manifest_payload = enterprise_production_readiness_manifest().model_dump(mode="json")

    assert manifest_payload["product"] == "Semantic Data Portal"
    assert "product_name" not in manifest_payload
    assert "integrations" in manifest_payload
    assert "production_integrations" not in manifest_payload

    integration_payload = manifest_payload["integrations"][0]
    assert set(("id", "label", "status")) <= integration_payload.keys()
    assert "production_integration_id" not in integration_payload
    assert "integration_status" not in integration_payload
