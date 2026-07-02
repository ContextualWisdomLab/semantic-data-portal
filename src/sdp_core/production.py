from __future__ import annotations

from pydantic import BaseModel, Field


class ProductionIntegration(BaseModel):
    id: str
    label: str
    status: str = Field(pattern="^(implemented|planned|external)$")
    buyer_risk: str
    current_evidence: list[str]
    required_environment: list[str]
    acceptance_criteria: list[str]


class ProductionReadinessManifest(BaseModel):
    product: str
    valuation_target_krw: int
    current_stage: str
    demo_release_ready: bool
    paid_pilot_ready: bool
    integrations: list[ProductionIntegration]
    demo_blockers: list[str]
    paid_pilot_blockers: list[str]


def production_integration_registry() -> list[ProductionIntegration]:
    return [
        ProductionIntegration(
            id="postgres_evidence_store",
            label="Postgres evidence store",
            status="implemented",
            buyer_risk="SQLite remains available for local demo fallback; paid pilots can use managed, backed-up, tenant-indexed Postgres evidence retention.",
            current_evidence=[
                "SDP_DATABASE_URL",
                "SDP_DATABASE_SSLMODE",
                "SDP_SQLITE_PATH",
                "sdp_core.SQLiteEvidenceStore",
                "sdp_core.PostgresEvidenceStore",
                "GET /audit/events",
                "GET /policy/decisions",
                "tests/test_api.py::test_postgres_evidence_store_uses_tenant_columns_and_store_protocol",
                "tests/test_api.py::test_configured_evidence_store_prefers_postgres_over_sqlite",
                "tests/test_api.py::test_audit_events_endpoint_reads_configured_evidence_store_after_memory_clear",
            ],
            required_environment=[
                "SDP_DATABASE_URL",
                "SDP_DATABASE_SSLMODE",
                "SDP_EVIDENCE_RETENTION_DAYS",
            ],
            acceptance_criteria=[
                "policy decisions and audit events persist through the same store protocol under Postgres.",
                "Every stored row carries tenant, resource, decision id, created_at, and immutable payload snapshot.",
                "The application can run demo smoke checks without production credentials.",
            ],
        ),
        ProductionIntegration(
            id="oidc_jwks_verification",
            label="OIDC JWKS verification",
            status="implemented",
            buyer_risk="Claim-shape preview proves the role-mapping contract, but production login needs signed token verification.",
            current_evidence=[
                "POST /enterprise/auth/oidc-preview",
                "POST /enterprise/auth/oidc-verify",
                "SDP_OIDC_GROUP_ROLE_MAP",
                "SDP_OIDC_ISSUER",
                "SDP_OIDC_AUDIENCE",
                "SDP_OIDC_JWKS_URL",
                "sdp.authz.verify_oidc_jwks_token",
                "tests/test_api.py::test_oidc_jwks_verification_maps_verified_token_without_token_leak",
                "tests/test_api.py::test_oidc_jwks_verification_rejects_wrong_audience",
                "tests/test_api.py::test_oidc_preview_rejects_unverified_claim_shape",
                "tests/test_api.py::test_oidc_preview_ignores_direct_role_escalation_claims",
            ],
            required_environment=[
                "SDP_OIDC_ISSUER",
                "SDP_OIDC_AUDIENCE",
                "SDP_OIDC_JWKS_URL",
                "SDP_OIDC_GROUP_ROLE_MAP",
            ],
            acceptance_criteria=[
                "Signed tokens are verified against issuer, audience, expiry, and JWKS key id.",
                "Only group allow-list mappings produce SDP roles; direct role claims are ignored for privilege elevation.",
                "Rejected identity tokens emit audit evidence without logging raw tokens.",
            ],
        ),
        ProductionIntegration(
            id="connector_credential_vault",
            label="Connector credential vault",
            status="implemented",
            buyer_risk="Connector contracts are implemented for demo, but real source credentials must never live in catalog metadata or LLM prompts.",
            current_evidence=[
                "SDP_CONNECTOR_SECRET_REF_PREFIX",
                "SDP_CONNECTOR_VAULT_PROVIDER",
                "sdp.credentials.connector_secret_status",
                "GET /enterprise/connectors/{connector_id}/probe",
                "sdp_core.SourceConnector",
                "tests/test_api.py::test_enterprise_rest_connector_probe_uses_vault_reference_without_secret_leak",
            ],
            required_environment=[
                "SDP_CONNECTOR_SECRET_REF_PREFIX",
                "SDP_CONNECTOR_VAULT_PROVIDER",
                "SDP_CONNECTOR_TIMEOUT_MS",
            ],
            acceptance_criteria=[
                "raw connector credentials are never stored in dataset records, prompt context, audit payloads, or logs.",
                "Connector probes use secret references and fail closed when a secret reference is missing.",
                "SQL/RDF/REST/file connectors enforce read-only scope, row limits, and audit events.",
            ],
        ),
        ProductionIntegration(
            id="request_observability_export",
            label="Request observability export",
            status="implemented",
            buyer_risk="Local metrics are enough for pilot review, but paid operation needs tenant-scoped logs and external alert routing.",
            current_evidence=[
                "SDP_LOG_SINK_URL",
                "SDP_REQUEST_ID_HEADER",
                "sdp.observability.record_request_observation",
                "/enterprise/observability",
                "/metrics",
                "tests/test_api.py::test_enterprise_observability_and_metrics_endpoints",
                "tests/test_api.py::test_request_observability_export_writes_bodyless_jsonl",
            ],
            required_environment=[
                "SDP_LOG_SINK_URL",
                "SDP_ALERT_WEBHOOK_URL",
                "SDP_REQUEST_ID_HEADER",
            ],
            acceptance_criteria=[
                "Request logs include request id, tenant, actor, route, status, latency, and evidence ids without request bodies.",
                "Policy/audit gaps, failed connector probes, and queue drift emit alertable signals.",
                "Operators can correlate health, metrics, audit events, and policy decisions for a buyer pilot.",
            ],
        ),
    ]


def enterprise_production_readiness_manifest() -> ProductionReadinessManifest:
    integrations = production_integration_registry()
    paid_pilot_blockers = [item.id for item in integrations if item.status != "implemented"]
    return ProductionReadinessManifest(
        product="Semantic Data Portal",
        valuation_target_krw=2_000_000_000,
        current_stage="pilot_candidate",
        demo_release_ready=True,
        paid_pilot_ready=not paid_pilot_blockers,
        integrations=integrations,
        demo_blockers=[],
        paid_pilot_blockers=paid_pilot_blockers,
    )
