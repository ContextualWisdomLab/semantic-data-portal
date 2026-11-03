from __future__ import annotations

from pydantic import BaseModel


class RolePermission(BaseModel):
    role: str
    allowed_actions: list[str]
    denied_actions: list[str]
    tenant_scope: str
    evidence: list[str]
    # Actions this role is *intended* to hold that the policy engine does not
    # yet enforce. They are published here instead of in ``allowed_actions``,
    # because the matrix declares ``policy_source="sdp.policy.evaluate"`` - it
    # claims to describe what that engine does.
    #
    # ``review_security_evidence`` and ``administer_tenants`` are in
    # ``policy.UNMAPPED_CATALOG_ACTIONS``: ``evaluate`` returns deny with
    # "이 action은 아직 정책 엔진에 매핑되지 않았습니다." before any role is
    # consulted. Enumerating the four roles against the engine with a real
    # in-tenant dataset, 37 of 40 cells agreed and these 3 did not:
    #
    #     security        review_security_evidence  -> deny (unmapped)
    #     platform-admin  review_security_evidence  -> deny (unmapped)
    #     platform-admin  administer_tenants        -> deny (unmapped)
    #
    # Removing them outright would hide the intent; leaving them in
    # ``allowed_actions`` published a grant nobody can exercise. Declaring them
    # keeps both facts, the way ``declared_unimplemented_environment`` does for
    # the readiness manifest.
    declared_unenforced_actions: list[str] = []


class RBACMatrix(BaseModel):
    feature_gate: str = "sdp_enterprise"
    roles: list[RolePermission]
    action_catalog: list[str]
    policy_source: str


# Mirrors ``sdp.policy.UNMAPPED_CATALOG_ACTIONS``. Duplicated as a literal
# rather than imported because ``sdp_core`` must not depend on the application
# layer; ``tests/test_api.py`` enumerates every role x action against the real
# engine, so the two cannot drift silently.
_UNENFORCED_ACTIONS = frozenset({"review_security_evidence", "administer_tenants"})


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
                evidence=[
                    "sdp.policy.evaluate",
                    "tests/test_api.py::test_dataset_mutation_policy_and_lifecycle",
                    "tests/test_api.py::test_catalog_mutation_guard_denies_non_admin_actors",
                ],
            ),
            RolePermission(
                role="security",
                allowed_actions=[
                    "discover_catalog",
                    "view_schema",
                ],
                declared_unenforced_actions=["review_security_evidence"],
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
                allowed_actions=[
                    action
                    for action in action_catalog
                    if action not in _UNENFORCED_ACTIONS
                ],
                declared_unenforced_actions=[
                    action for action in action_catalog if action in _UNENFORCED_ACTIONS
                ],
                denied_actions=[],
                tenant_scope="all_tenants",
                evidence=[
                    "sdp.authz.can_access_tenant",
                    "tests/test_api.py::test_tenant_boundary_denies_cross_tenant_preview",
                ],
            ),
        ],
    )
