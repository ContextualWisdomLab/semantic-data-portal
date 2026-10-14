from __future__ import annotations

import os
from collections.abc import Mapping

from pydantic import BaseModel, Field


class ProductionIntegration(BaseModel):
    id: str
    label: str
    status: str = Field(pattern="^(implemented|planned|external)$")
    buyer_risk: str
    current_evidence: list[str]
    required_environment: list[str]
    acceptance_criteria: list[str]
    # Variables an operator may reasonably expect this integration to honour and
    # that it does **not** yet read. They are listed here instead of in
    # ``required_environment``, because a readiness gate that a no-op variable
    # satisfies measures nothing - see
    # :func:`enterprise_production_readiness_manifest`. Naming them rather than
    # deleting them keeps the gap visible to a buyer; silently dropping the
    # variable would remove the false claim *and* the information.
    declared_unimplemented_environment: list[str] = []


class ProductionReadinessManifest(BaseModel):
    product: str
    valuation_target_krw: int
    current_stage: str
    demo_release_ready: bool
    paid_pilot_ready: bool
    integrations: list[ProductionIntegration]
    demo_blockers: list[str]
    paid_pilot_blockers: list[str]
    # Measured, not authored: which integrations have their declared environment
    # present in this deployment, and which do not.
    configured_integrations: list[str] = []
    unconfigured_integrations: list[str] = []
    missing_environment: dict[str, list[str]] = {}
    # Declared-but-unimplemented configuration, surfaced so the readiness
    # document says what it cannot yet honour instead of staying silent.
    unimplemented_environment: dict[str, list[str]] = {}


def production_integration_registry() -> list[ProductionIntegration]:
    return [
        ProductionIntegration(
            id="postgres_evidence_store",
            label="Postgres evidence store",
            status="implemented",
            buyer_risk=(
                "SQLite remains available for local demo fallback; paid pilots can use "
                "managed, backed-up, tenant-indexed Postgres evidence storage. "
                "Age-based retention is NOT implemented: neither evidence store has a "
                "prune or purge path, so rows are kept until an operator removes them "
                "out of band. SDP_EVIDENCE_RETENTION_DAYS is declared but unread."
            ),
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
            ],
            declared_unimplemented_environment=["SDP_EVIDENCE_RETENTION_DAYS"],
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
                "tests/test_api.py::test_oidc_verify_refuses_request_supplied_trust_anchors",
                "tests/test_api.py::test_oidc_jwks_verification_maps_verified_token_without_token_leak",
                "tests/test_api.py::test_oidc_jwks_verification_rejects_wrong_audience",
                "tests/test_api.py::test_oidc_preview_rejects_unverified_claim_shape",
                "tests/test_api.py::test_oidc_preview_ignores_direct_role_escalation_claims",
            ],
            required_environment=[
                "SDP_OIDC_ISSUER",
                "SDP_OIDC_AUDIENCE",
                "SDP_OIDC_JWKS_URL",
                "SDP_OIDC_JWKS",
                "SDP_OIDC_GROUP_ROLE_MAP",
            ],
            acceptance_criteria=[
                "Signed tokens are verified against issuer, audience, expiry, and JWKS key id.",
                "Trust anchors come from operator configuration; a request body that carries issuer, audience, JWKS, or role map is refused.",
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
                "rest_connector probes use a secret reference and fail closed when it is missing "
                "(credential_vault is in required_controls for rest_connector only, so the sql, rdf and "
                "file_lake probes do not check the vault - extending it to all four would require three "
                "more operator-configured secret references to reach ready_for_demo).",
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
                "sdp.observability.record_request_observation_async",
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


def _missing_required_environment(
    integration: ProductionIntegration, environment: Mapping[str, str]
) -> list[str]:
    """Name the declared environment variables this deployment does not set."""
    return [
        name
        for name in integration.required_environment
        if not (environment.get(name) or "").strip()
    ]


def enterprise_production_readiness_manifest(
    environment: Mapping[str, str] | None = None,
) -> ProductionReadinessManifest:
    """Report production readiness, separating what is built from what is configured.

    ``paid_pilot_ready`` was derived solely from each integration's authored
    ``status`` literal, every one of which is ``"implemented"``. Nothing a buyer
    or operator could do made it false: with zero configuration and its own named
    proof endpoints failing, the manifest still published
    ``paid_pilot_ready: true`` with ``paid_pilot_blockers: []``. A flag that
    cannot be falsified is not evidence.

    The two claims it conflated are genuinely different and both are kept:

    * ``status`` is a statement about the **codebase** - this integration is
      built - and stays as authored, because it is true.
    * ``configured_integrations`` / ``missing_environment`` are measured from the
      **deployment**, by checking the variables each integration already declares
      in ``required_environment``.

    A paid pilot needs a configured deployment, not only shipped code, so
    ``paid_pilot_ready`` now requires both. ``demo_release_ready`` is unchanged:
    the demo path runs on in-memory defaults by design, which is why
    ``sdp.demo_smoke`` does not gate on this flag.

    Making the flag falsifiable was not enough on its own: the gate still turned
    on the *presence of a non-blank string*, and one of the declared variables
    had no consumer anywhere in ``src/``. Measured before this change, with
    everything else configured, the last variable standing between
    ``paid_pilot_ready: false`` and ``true`` was ``SDP_EVIDENCE_RETENTION_DAYS``,
    and it was satisfied by ``'banana'``, ``'0'``, ``'-1'`` and ``'   x'`` alike,
    while neither ``SQLiteEvidenceStore`` nor ``PostgresEvidenceStore`` has any
    prune, purge or expiry path at all. So the gate could be cleared by setting
    a variable that does nothing, and an operator reading
    ``required_environment`` concluded that evidence retention was configurable
    and enforced when it was neither.

    A gate may only measure capabilities that exist. The variable moved to
    ``declared_unimplemented_environment``, which the manifest publishes, so the
    gap is stated rather than either falsely gated or silently dropped.
    Implementing retention was deliberately not done here: deleting compliance
    evidence on a timer is a product decision about the destruction of audit
    records, not a defect fix, and it would also need a Postgres path this
    environment cannot verify.
    ``tests/test_production_readiness_measurement.py`` now scans ``src/`` for a
    consumer of every ``required_environment`` name, so the next no-op variable
    fails there instead of quietly becoming a gate.
    """
    resolved_environment = os.environ if environment is None else environment
    integrations = production_integration_registry()

    unbuilt = [item.id for item in integrations if item.status != "implemented"]
    missing_environment = {
        item.id: missing
        for item in integrations
        if (missing := _missing_required_environment(item, resolved_environment))
    }
    unconfigured = sorted(missing_environment)
    paid_pilot_blockers = sorted({*unbuilt, *unconfigured})

    return ProductionReadinessManifest(
        product="Semantic Data Portal",
        valuation_target_krw=2_000_000_000,
        current_stage="pilot_candidate",
        demo_release_ready=True,
        paid_pilot_ready=not paid_pilot_blockers,
        integrations=integrations,
        demo_blockers=[],
        paid_pilot_blockers=paid_pilot_blockers,
        configured_integrations=[
            item.id for item in integrations if item.id not in missing_environment
        ],
        unconfigured_integrations=unconfigured,
        missing_environment=missing_environment,
        unimplemented_environment={
            item.id: list(item.declared_unimplemented_environment)
            for item in integrations
            if item.declared_unimplemented_environment
        },
    )
