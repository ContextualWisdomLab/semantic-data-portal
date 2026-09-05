from __future__ import annotations

from sdp_core.readiness import (
    ConnectorCapability,
    DemoWorkflowStep,
    EnterpriseGate,
    EnterpriseReadinessManifest,
    PackageBoundary,
    StoreCapability,
    enterprise_readiness_manifest,
)


def test_readiness_models_own_semantic_identifier_fields() -> None:
    assert "package_boundary_id" in PackageBoundary.model_fields
    assert "id" not in PackageBoundary.model_fields
    assert "package_kind" in PackageBoundary.model_fields
    assert "kind" not in PackageBoundary.model_fields
    assert "owned_responsibilities" in PackageBoundary.model_fields
    assert "owns" not in PackageBoundary.model_fields

    assert "store_capability_id" in StoreCapability.model_fields
    assert "id" not in StoreCapability.model_fields
    assert "store_responsibility" in StoreCapability.model_fields
    assert "responsibility" not in StoreCapability.model_fields

    assert "connector_capability_id" in ConnectorCapability.model_fields
    assert "id" not in ConnectorCapability.model_fields
    assert "connector_protocol" in ConnectorCapability.model_fields
    assert "protocol" not in ConnectorCapability.model_fields
    assert "connector_proof" in ConnectorCapability.model_fields
    assert "proof" not in ConnectorCapability.model_fields

    assert "enterprise_gate_id" in EnterpriseGate.model_fields
    assert "id" not in EnterpriseGate.model_fields
    assert "gate_label" in EnterpriseGate.model_fields
    assert "label" not in EnterpriseGate.model_fields
    assert "gate_target" in EnterpriseGate.model_fields
    assert "target" not in EnterpriseGate.model_fields
    assert "gate_evidence" in EnterpriseGate.model_fields
    assert "evidence" not in EnterpriseGate.model_fields
    assert "gate_status" in EnterpriseGate.model_fields
    assert "status" not in EnterpriseGate.model_fields

    assert "workflow_step_id" in DemoWorkflowStep.model_fields
    assert "id" not in DemoWorkflowStep.model_fields
    assert "step_owner" in DemoWorkflowStep.model_fields
    assert "owner" not in DemoWorkflowStep.model_fields
    assert "step_outcome" in DemoWorkflowStep.model_fields
    assert "outcome" not in DemoWorkflowStep.model_fields

    assert "product_name" in EnterpriseReadinessManifest.model_fields
    assert "product" not in EnterpriseReadinessManifest.model_fields
    assert "package_boundaries" in EnterpriseReadinessManifest.model_fields
    assert "package_boundary" not in EnterpriseReadinessManifest.model_fields


def test_readiness_manifest_keeps_established_wire_keys() -> None:
    manifest_payload = enterprise_readiness_manifest().model_dump(mode="json")

    assert manifest_payload["product"] == "Semantic Data Portal"
    assert "product_name" not in manifest_payload
    assert "package_boundary" in manifest_payload
    assert "package_boundaries" not in manifest_payload

    package_payload = manifest_payload["package_boundary"][0]
    assert set(("id", "kind", "owns")) <= package_payload.keys()
    assert "package_boundary_id" not in package_payload
    assert "package_kind" not in package_payload
    assert "owned_responsibilities" not in package_payload

    connector_payload = manifest_payload["connector_capabilities"][0]
    assert set(("id", "protocol", "proof")) <= connector_payload.keys()
    assert "connector_capability_id" not in connector_payload

    gate_payload = manifest_payload["enterprise_gates"][0]
    assert set(("id", "label", "target", "evidence", "status")) <= gate_payload.keys()
    assert "enterprise_gate_id" not in gate_payload
    assert "gate_status" not in gate_payload
