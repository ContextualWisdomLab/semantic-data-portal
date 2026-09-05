from __future__ import annotations

from sdp_core.enterprise import EnterpriseControl, EnterpriseControlsManifest, enterprise_controls_manifest


def test_enterprise_control_owns_semantic_fields() -> None:
    assert "enterprise_control_id" in EnterpriseControl.model_fields
    assert "control_label" in EnterpriseControl.model_fields
    assert "control_status" in EnterpriseControl.model_fields
    assert "control_evidence" in EnterpriseControl.model_fields

    assert "id" not in EnterpriseControl.model_fields
    assert "label" not in EnterpriseControl.model_fields
    assert "status" not in EnterpriseControl.model_fields
    assert "evidence" not in EnterpriseControl.model_fields


def test_enterprise_controls_manifest_owns_semantic_fields() -> None:
    assert "manifest_status" in EnterpriseControlsManifest.model_fields
    assert "enterprise_controls" in EnterpriseControlsManifest.model_fields
    assert "status" not in EnterpriseControlsManifest.model_fields
    assert "controls" not in EnterpriseControlsManifest.model_fields


def test_enterprise_controls_preserve_public_wire_contract() -> None:
    manifest_payload = enterprise_controls_manifest().model_dump(mode="json")

    assert "status" in manifest_payload
    assert "controls" in manifest_payload
    assert "manifest_status" not in manifest_payload
    assert "enterprise_controls" not in manifest_payload

    control_payload = manifest_payload["controls"][0]
    assert set(("id", "label", "status", "evidence")) <= control_payload.keys()
    assert "enterprise_control_id" not in control_payload
    assert "control_status" not in control_payload
