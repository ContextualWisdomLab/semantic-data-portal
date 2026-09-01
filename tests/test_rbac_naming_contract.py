from __future__ import annotations

from sdp_core.rbac import RBACMatrix, RolePermission, enterprise_rbac_matrix


def test_role_permission_owns_semantic_fields() -> None:
    assert "role_name" in RolePermission.model_fields
    assert "permission_evidence" in RolePermission.model_fields
    assert "role" not in RolePermission.model_fields
    assert "evidence" not in RolePermission.model_fields


def test_rbac_matrix_owns_semantic_role_collection() -> None:
    assert "role_permissions" in RBACMatrix.model_fields
    assert "roles" not in RBACMatrix.model_fields


def test_rbac_matrix_preserves_public_wire_contract() -> None:
    matrix_payload = enterprise_rbac_matrix().model_dump(mode="json")

    assert "roles" in matrix_payload
    assert "role_permissions" not in matrix_payload
    role_payload = matrix_payload["roles"][0]
    assert role_payload["role"] == "data-analyst"
    assert "evidence" in role_payload
    assert "role_name" not in role_payload
    assert "permission_evidence" not in role_payload
