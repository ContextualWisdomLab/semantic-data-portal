from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class EnterpriseControl(BaseModel):
    """Enterprise control contract with semantic internal names and stable wire keys."""

    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    enterprise_control_id: str = Field(alias="id")
    control_label: str = Field(alias="label")
    feature_gate: str = "sdp_enterprise"
    control_status: str = Field(alias="status", pattern="^(implemented|planned|external)$")
    risk_reduced: str
    control_evidence: list[str] = Field(alias="evidence")
    release_criteria: list[str]

    @property
    def id(self) -> str:  # noqa: A003 - legacy Python compatibility attribute
        """Return the historical enterprise-control identifier."""

        return self.enterprise_control_id

    @id.setter
    def id(self, legacy_control_id: str) -> None:  # noqa: A003
        self.enterprise_control_id = legacy_control_id

    @property
    def label(self) -> str:
        """Return the historical enterprise-control label."""

        return self.control_label

    @label.setter
    def label(self, legacy_control_label: str) -> None:
        self.control_label = legacy_control_label

    @property
    def status(self) -> str:
        """Return the historical enterprise-control status."""

        return self.control_status

    @status.setter
    def status(self, legacy_control_status: str) -> None:
        self.control_status = legacy_control_status

    @property
    def evidence(self) -> list[str]:
        """Return the historical enterprise-control evidence list."""

        return self.control_evidence

    @evidence.setter
    def evidence(self, legacy_control_evidence: list[str]) -> None:
        self.control_evidence = legacy_control_evidence


class EnterpriseControlsManifest(BaseModel):
    """Enterprise-controls manifest with semantic internal names and stable wire keys."""

    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    feature_gate: str
    manifest_status: str = Field(alias="status")
    implemented_controls: int
    planned_controls: int
    external_controls: int
    enterprise_controls: list[EnterpriseControl] = Field(alias="controls")

    @property
    def status(self) -> str:
        """Return the historical manifest status."""

        return self.manifest_status

    @status.setter
    def status(self, legacy_manifest_status: str) -> None:
        self.manifest_status = legacy_manifest_status

    @property
    def controls(self) -> list[EnterpriseControl]:
        """Return the historical enterprise-controls collection."""

        return self.enterprise_controls

    @controls.setter
    def controls(self, legacy_enterprise_controls: list[EnterpriseControl]) -> None:
        self.enterprise_controls = legacy_enterprise_controls


def enterprise_control_registry() -> list[EnterpriseControl]:
    return [
        EnterpriseControl(
            enterprise_control_id="tenant_authorization",
            control_label="Tenant authorization boundary",
            control_status="implemented",
            risk_reduced="Cross-tenant preview, query, and schema access is denied before source data is touched.",
            control_evidence=[
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
            enterprise_control_id="local_evidence_retention",
            control_label="Local evidence retention",
            control_status="implemented",
            risk_reduced="Policy decisions and audit events survive process restart in demo or pilot environments.",
            control_evidence=[
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
            enterprise_control_id="sso_oidc_adapter",
            control_label="SSO/OIDC adapter",
            control_status="planned",
            risk_reduced="Enterprise users can map identity provider groups to SDP roles without local code changes.",
            control_evidence=[
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
            enterprise_control_id="rbac_matrix",
            control_label="RBAC matrix",
            control_status="implemented",
            risk_reduced="Buyer security review can inspect who may discover, preview, query, mutate, and administer datasets.",
            control_evidence=[
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
            enterprise_control_id="deployment_template",
            control_label="Deployment template",
            control_status="implemented",
            risk_reduced="Pilot setup can move from local demo to reproducible container deployment with predictable configuration.",
            control_evidence=[
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
            enterprise_control_id="operational_observability",
            control_label="Operational observability",
            control_status="implemented",
            risk_reduced="Pilot operators can inspect health, minimal metrics, evidence counts, request logs, and alert conditions before production integration.",
            control_evidence=[
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
            enterprise_control_id="central_workflow_due_diligence",
            control_label="Central workflow due diligence",
            control_status="external",
            risk_reduced="Org-level coverage, security, PR queue, and review controls remain enforced outside this repo.",
            control_evidence=[
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
    implemented = sum(1 for control in controls if control.control_status == "implemented")
    planned = sum(1 for control in controls if control.control_status == "planned")
    external = sum(1 for control in controls if control.control_status == "external")
    return EnterpriseControlsManifest(
        feature_gate="sdp_enterprise",
        manifest_status="pilot_ready_with_planned_controls",
        implemented_controls=implemented,
        planned_controls=planned,
        external_controls=external,
        enterprise_controls=controls,
    )
