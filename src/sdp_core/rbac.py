from __future__ import annotations

from pydantic import BaseModel


class RolePermission(BaseModel):
    role: str
    allowed_actions: list[str]
    denied_actions: list[str]
    tenant_scope: str
    evidence: list[str]


class RBACMatrix(BaseModel):
    feature_gate: str = "sdp_enterprise"
    roles: list[RolePermission]
    action_catalog: list[str]
    policy_source: str


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
        roles=[
            RolePermission(
                role="data-analyst",
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
                evidence=["sdp.authz.can_access_tenant", "tests/test_api.py::test_preview_denies_low_privilege_actor"],
            ),
            RolePermission(
                role="admin",
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
                evidence=["sdp.policy.evaluate", "tests/test_api.py::test_catalog_mutation_flow"],
            ),
            RolePermission(
                role="security",
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
                evidence=["GET /enterprise/controls", "GET /enterprise/evidence-pack"],
            ),
            RolePermission(
                role="platform-admin",
                allowed_actions=action_catalog,
                denied_actions=[],
                tenant_scope="all_tenants",
                evidence=[
                    "sdp.authz.can_access_tenant",
                    "tests/test_api.py::test_tenant_boundary_denies_cross_tenant_preview",
                ],
            ),
        ],
    )
