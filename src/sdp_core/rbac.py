from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class RolePermission(BaseModel):
    """Role-permission contract with semantic internal names and stable wire keys."""

    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    role_name: str = Field(alias="role")
    allowed_actions: list[str]
    denied_actions: list[str]
    tenant_scope: str
    permission_evidence: list[str] = Field(alias="evidence")

    @property
    def role(self) -> str:
        """Return the historical role compatibility attribute."""

        return self.role_name

    @role.setter
    def role(self, legacy_role_name: str) -> None:
        self.role_name = legacy_role_name

    @property
    def evidence(self) -> list[str]:
        """Return the historical role-permission evidence list."""

        return self.permission_evidence

    @evidence.setter
    def evidence(self, legacy_permission_evidence: list[str]) -> None:
        self.permission_evidence = legacy_permission_evidence


class RBACMatrix(BaseModel):
    """RBAC matrix with semantic internal role-permission collection naming."""

    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    feature_gate: str = "sdp_enterprise"
    role_permissions: list[RolePermission] = Field(alias="roles")
    action_catalog: list[str]
    policy_source: str

    @property
    def roles(self) -> list[RolePermission]:
        """Return the historical role-permissions compatibility collection."""

        return self.role_permissions

    @roles.setter
    def roles(self, legacy_role_permissions: list[RolePermission]) -> None:
        self.role_permissions = legacy_role_permissions


def enterprise_rbac_matrix() -> RBACMatrix:
    action_catalog = [
        "discover_catalog",
        "view_schema",
        "preview_data",
        "run_governed_query",
        "register_dataset",
        "patch_dataset",
        "publish_dataset",
        "deprecate_dataset",
        "review_security_evidence",
        "administer_tenants",
    ]
    return RBACMatrix(
        action_catalog=action_catalog,
        policy_source="sdp.policy.evaluate",
        role_permissions=[
            RolePermission(
                role_name="data-analyst",
                allowed_actions=[
                    "discover_catalog",
                    "view_schema",
                    "preview_data",
                    "run_governed_query",
                ],
                denied_actions=[
                    "register_dataset",
                    "patch_dataset",
                    "publish_dataset",
                    "deprecate_dataset",
                    "administer_tenants",
                ],
                tenant_scope="own_tenant_only",
                permission_evidence=["sdp.authz.can_access_tenant", "tests/test_api.py::test_preview_denies_low_privilege_actor"],
            ),
            RolePermission(
                role_name="admin",
                allowed_actions=[
                    "discover_catalog",
                    "view_schema",
                    "preview_data",
                    "run_governed_query",
                    "register_dataset",
                    "patch_dataset",
                    "publish_dataset",
                    "deprecate_dataset",
                ],
                denied_actions=["administer_tenants"],
                tenant_scope="own_tenant_only",
                permission_evidence=["sdp.policy.evaluate", "tests/test_api.py::test_catalog_mutation_flow"],
            ),
            RolePermission(
                role_name="security",
                allowed_actions=[
                    "discover_catalog",
                    "view_schema",
                    "review_security_evidence",
                ],
                denied_actions=[
                    "preview_data",
                    "run_governed_query",
                    "register_dataset",
                    "patch_dataset",
                    "publish_dataset",
                    "deprecate_dataset",
                    "administer_tenants",
                ],
                tenant_scope="platform_evidence_only",
                permission_evidence=["GET /enterprise/controls", "GET /enterprise/evidence-pack"],
            ),
            RolePermission(
                role_name="platform-admin",
                allowed_actions=action_catalog,
                denied_actions=[],
                tenant_scope="all_tenants",
                permission_evidence=[
                    "sdp.authz.can_access_tenant",
                    "tests/test_api.py::test_tenant_boundary_denies_cross_tenant_preview",
                ],
            ),
        ],
    )
