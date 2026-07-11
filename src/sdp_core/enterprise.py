from __future__ import annotations

from pydantic import BaseModel, Field


class EnterpriseControl(BaseModel):
    id: str
    label: str
    feature_gate: str = "sdp_enterprise"
    status: str = Field(pattern="^(implemented|planned|external)$")
    risk_reduced: str
    evidence: list[str]
    release_criteria: list[str]


class EnterpriseControlsManifest(BaseModel):
    feature_gate: str
    status: str
    implemented_controls: int
    planned_controls: int
    external_controls: int
    controls: list[EnterpriseControl]


def enterprise_control_registry() -> list[EnterpriseControl]:
    return [
        EnterpriseControl(
            id="tenant_authorization",
            label="Tenant authorization boundary",
            status="implemented",
            risk_reduced="Cross-tenant preview, query, and schema access is denied before source data is touched.",
            evidence=[
                "sdp.authz.resolve_actor_context",
                "sdp.policy.evaluate",
                "tests/test_api.py::test_tenant_boundary_denies_cross_tenant_preview",
            ],
            release_criteria=[
                "Every data-access path resolves ActorContext.",
                "Platform-admin bypass is explicit and test-covered.",
            ],
        ),
        EnterpriseControl(
            id="local_evidence_retention",
            label="Local evidence retention",
            status="implemented",
            risk_reduced="Policy decisions and audit events survive process restart in demo or pilot environments.",
            evidence=[
                "SDP_SQLITE_PATH",
                "sdp_core.SQLiteEvidenceStore",
                "GET /policy/decisions",
                "tests/test_api.py::test_sqlite_evidence_store_persists_policy_and_audit_events",
            ],
            release_criteria=[
                "Preview/query/catalog mutation flows persist policy_decision_id and audit event payloads.",
                "Production backend can replace SQLite through the same evidence-store boundary.",
            ],
        ),
        EnterpriseControl(
            id="sso_oidc_adapter",
            label="SSO/OIDC adapter",
            status="planned",
            risk_reduced="Enterprise users can map identity provider groups to SDP roles without local code changes.",
            evidence=[
                "sdp_core.ActorContext",
                "sdp.authz",
                "POST /enterprise/auth/oidc-preview",
                "docs/enterprise-readiness.md",
                "tests/test_api.py::test_oidc_preview_rejects_unverified_claim_shape",
                "tests/test_api.py::test_oidc_preview_ignores_direct_role_escalation_claims",
            ],
            release_criteria=[
                "OIDC issuer, audience, and JWKS are environment-configured.",
                "Group-to-role mapping is tenant scoped and auditable.",
                "Preview rejects missing or expired identity claims and ignores direct role escalation claims.",
            ],
        ),
        EnterpriseControl(
            id="rbac_matrix",
            label="RBAC matrix",
            status="implemented",
            risk_reduced="Buyer security review can inspect who may discover, preview, query, mutate, and administer datasets.",
            evidence=[
                "GET /enterprise/rbac-matrix",
                "sdp.policy.evaluate",
                "GET /enterprise/controls",
                "docs/enterprise-readiness.md",
            ],
            release_criteria=[
                "Roles, actions, and denied cases are documented and test-covered.",
                "Admin actions require explicit role checks and audit events.",
            ],
        ),
        EnterpriseControl(
            id="deployment_template",
            label="Deployment template",
            status="implemented",
            risk_reduced="Pilot setup can move from local demo to reproducible container deployment with predictable configuration.",
            evidence=[
                "Dockerfile",
                "docker-compose.yml",
                "README.md",
                "docs/enterprise-readiness.md",
                "PYTHONPATH=src python -m sdp.demo_smoke",
            ],
            release_criteria=[
                "Container, env var, healthcheck, evidence store path, and read-only connector config are documented.",
                "Local demo setup remains under 15 minutes.",
            ],
        ),
        EnterpriseControl(
            id="operational_observability",
            label="Operational observability",
            status="implemented",
            risk_reduced="Pilot operators can inspect health, minimal metrics, evidence counts, request logs, and alert conditions before production integration.",
            evidence=[
                "SDP_LOG_SINK_URL",
                "SDP_REQUEST_ID_HEADER",
                "GET /health",
                "GET /metrics",
                "GET /enterprise/observability",
                "tests/test_api.py::test_enterprise_observability_and_metrics_endpoints",
                "tests/test_api.py::test_request_observability_export_writes_bodyless_jsonl",
            ],
            release_criteria=[
                "Health and metrics endpoints are exposed without source credentials.",
                "Audit, policy, catalog, request observation, and enterprise control counts are visible to operators.",
                "Request logs include id, tenant, actor, route, status, latency, and evidence ids without request bodies.",
            ],
        ),
        EnterpriseControl(
            id="central_workflow_due_diligence",
            label="Central workflow due diligence",
            status="external",
            risk_reduced="Org-level coverage, security, PR queue, and review controls remain enforced outside this repo.",
            evidence=[
                "ContextualWisdomLab org ruleset",
                "PR #2",
                "PR #4",
            ],
            release_criteria=[
                "Required checks pass on current head.",
                "Open PR queue has no source-code blocker.",
            ],
        ),
    ]


def enterprise_controls_manifest() -> EnterpriseControlsManifest:
    controls = enterprise_control_registry()
    implemented = sum(1 for control in controls if control.status == "implemented")
    planned = sum(1 for control in controls if control.status == "planned")
    external = sum(1 for control in controls if control.status == "external")
    return EnterpriseControlsManifest(
        feature_gate="sdp_enterprise",
        status="pilot_ready_with_planned_controls",
        implemented_controls=implemented,
        planned_controls=planned,
        external_controls=external,
        controls=controls,
    )
