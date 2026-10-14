import json
from copy import deepcopy
from pathlib import Path
from time import time

import jwt
import pytest
from fastapi.testclient import TestClient
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

import sdp.authz as app_authz
import sdp.catalog as app_catalog
import sdp.domain as app_domain
import sdp.evidence as app_evidence
import sdp.observability as app_observability
import sdp.ontology as app_ontology
import sdp_core
from sdp.api import app
from sdp.connectors import get_source_connector
from sdp.demo_smoke import smoke_summary
from sdp.policy import evaluate


client = TestClient(app)


@pytest.fixture(autouse=True)
def isolate_in_memory_app_state():
    data = {dataset_id: dataset.model_copy(deep=True) for dataset_id, dataset in app_catalog._DATA.items()}
    audit_log = list(app_catalog._AUDIT_LOG)
    schema_history = deepcopy(app_catalog._SCHEMA_HISTORY)
    policy_log = list(app_evidence._POLICY_DECISION_LOG)
    audit_event_log = list(app_evidence._AUDIT_EVENT_LOG)
    ontology_patches = [patch.model_copy(deep=True) for patch in app_ontology._ONTOLOGY_PATCHES]
    request_observations = app_observability.list_request_observations()
    export_errors = app_observability.list_observability_export_errors()
    yield
    app_catalog._DATA.clear()
    app_catalog._DATA.update(data)
    app_catalog._AUDIT_LOG[:] = audit_log
    app_catalog._SCHEMA_HISTORY.clear()
    app_catalog._SCHEMA_HISTORY.update(schema_history)
    app_evidence._POLICY_DECISION_LOG[:] = policy_log
    app_evidence._AUDIT_EVENT_LOG[:] = audit_event_log
    app_ontology._ONTOLOGY_PATCHES[:] = ontology_patches
    app_observability.reset_request_observability()
    for observation in request_observations:
        app_observability.record_request_observation(observation, export=False)
    for error in export_errors:
        app_observability.record_observability_export_error(error)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_enterprise_readiness_manifest_exposes_saleable_gates():
    response = client.get("/enterprise/readiness")
    assert response.status_code == 200

    body = response.json()
    assert body["valuation_target_krw"] == 2_000_000_000
    assert body["submodule_decision"]["decision"] == "monorepo_package_split_first"

    packages = {package["id"]: package for package in body["package_boundary"]}
    assert packages["sdp_core"]["kind"] == "library"
    assert "store protocols" in packages["sdp_core"]["owns"]
    assert packages["sdp_app"]["kind"] == "application"

    stores = {store["id"]: store for store in body["storage_capabilities"]}
    assert stores["audit_events"]["durability_required"] is True
    assert stores["policy_decisions"]["scale_gate"].startswith("100 percent")

    connectors = {connector["id"]: connector for connector in body["connector_capabilities"]}
    assert {"sql_connector", "rdf_connector", "rest_connector", "file_lake_connector"} <= set(connectors)
    assert "policy_before_query" in connectors["sql_connector"]["required_controls"]

    gates = {gate["id"]: gate for gate in body["enterprise_gates"]}
    assert gates["policy_audit_coverage"]["status"] == "implemented"
    assert gates["operational_due_diligence"]["status"] == "external"
    assert any(artifact["code_connect"] == "disabled" for artifact in body["design_artifacts"])
    artifacts = {artifact["id"]: artifact for artifact in body["design_artifacts"]}
    assert artifacts["operator_console_design_capture"]["url"].startswith("https://www.figma.com/design/")
    assert "node-id=3-2" in artifacts["operator_console_design_capture"]["url"]
    assert artifacts["operator_console_design_capture"]["code_connect"] == "disabled"


def test_enterprise_demo_plan_supports_buyer_activation_path():
    response = client.get(
        "/enterprise/demo-plan",
        params={"domain": "insurance claims", "connector": ["sql_connector", "rest_connector"]},
    )
    assert response.status_code == 200

    body = response.json()
    assert body["priority_domain"] == "insurance claims"
    assert body["activation_days"] == 10
    assert [connector["id"] for connector in body["selected_connectors"]] == ["sql_connector", "rest_connector"]
    assert any(step["id"] == "governed_browse_query" for step in body["workflow"])
    assert any("/enterprise/demo-plan" in artifact for artifact in body["handoff_artifacts"])
    assert any("policy_decision_id" in criterion for criterion in body["acceptance_criteria"])


def test_enterprise_demo_plan_uses_core_buyer_demo_fixture():
    response = client.get("/enterprise/demo-plan")
    assert response.status_code == 200

    body = response.json()
    fixture_ids = {dataset.id for dataset in sdp_core.buyer_demo_datasets()}
    response_ids = {dataset["id"] for dataset in body["demo_datasets"]}
    catalog_ids = {dataset["id"] for dataset in client.get("/catalog/datasets", params={"user": "analyst"}).json()}

    assert body["domain_fixture_id"] == "customer_intelligence"
    assert fixture_ids == response_ids
    assert fixture_ids <= catalog_ids
    assert "semantic-glossary" in fixture_ids
    assert body["analyst_questions"]
    assert body["governance_questions"]


def test_enterprise_demo_plan_rejects_unsupported_connector():
    response = client.get("/enterprise/demo-plan", params={"connector": "warehouse_admin_shell"})
    assert response.status_code == 400
    assert "unsupported connector ids" in response.json()["detail"]


def test_enterprise_kpis_expose_saleability_measurement_plan():
    response = client.get("/enterprise/kpis")
    assert response.status_code == 200

    body = response.json()
    assert body["valuation_target_krw"] == 2_000_000_000

    all_kpis = body["primary_kpis"] + body["guardrail_kpis"]
    kpis = {item["id"]: item for item in all_kpis}
    assert kpis["discovery_time_reduction"]["target"] == ">=50 percent reduction"
    assert kpis["metadata_completeness"]["target"] == ">=90 percent display coverage"
    assert kpis["policy_audit_coverage"]["target"] == "100 percent"
    assert kpis["nl_catalog_search_success"]["target"] == ">=80 percent"
    assert kpis["ontology_mapping_coverage"]["target"] == ">=70 percent"
    assert kpis["validation_pass_rate"]["target"] == ">=95 percent"
    assert kpis["demo_setup_minutes"]["target"] == "<=15 minutes"
    assert kpis["clean_pr_queue"]["target"] == "0 blocking PRs"
    assert kpis["clean_pr_queue"]["status"] == "external"
    assert "/enterprise/connectors/{connector_id}/probe" in kpis["demo_setup_minutes"]["source_endpoints"]


def test_catalog_dataset_semantic_validation_exposes_shacl_report():
    # The per-dataset discovery surface is tenant scoped, so the SHACL report
    # needs a resolvable actor; this call site pinned an anonymous read of it.
    response = client.get(
        "/catalog/datasets/crm-customer-master/semantic-validation",
        params={"user": "analyst"},
    )
    assert response.status_code == 200

    body = response.json()
    assert body["dataset_id"] == "crm-customer-master"
    assert body["shacl_compatible"] is True
    assert body["conforms"] is True
    assert body["approved_mapping_count"] >= 1
    assert {shape["id"] for shape in body["shapes"]} >= {"DatasetShape", "BusinessMappingShape"}
    assert body["violations"] == []


def test_enterprise_shacl_validation_summary_tracks_saleability_target():
    response = client.get("/enterprise/shacl-validation")
    assert response.status_code == 200

    body = response.json()
    assert body["shacl_compatible"] is True
    assert body["target_pass_rate"] == 0.95
    assert body["validation_pass_rate"] >= 0.95
    assert body["dataset_count"] >= 5
    assert body["conforming_datasets"] == body["dataset_count"]
    assert body["shape_count"] >= 3


def test_enterprise_steward_review_summarizes_governance_queue():
    # `requestor` is now derived from the authorized actor: a proposal writes to a
    # shared process-lifetime queue, so it is a governed write rather than an open
    # endpoint. This call used to pass no actor at all.
    proposed = client.post(
        "/ontology/patches",
        json={
            "actor": "analyst",
            "concept": "고객",
            "suggestion": "VIP 고객 세그먼트를 구매자 데모 glossary 후보로 추가",
        },
    )
    assert proposed.status_code == 200

    response = client.get("/enterprise/steward-review")
    assert response.status_code == 200

    body = response.json()
    assert body["feature_gate"] == "sdp_enterprise"
    assert body["validation_pass_rate"] >= 0.95
    assert body["validation_review_count"] == 0
    assert body["ontology_patch_count"] >= 1
    assert body["review_queue_count"] >= 1
    assert body["buyer_handoff_ready"] is False
    assert any(item["type"] == "ontology_patch" and item["id"] == proposed.json()["id"] for item in body["review_items"])
    assert "/enterprise/shacl-validation" in body["proof_endpoints"]
    assert "/ontology/patches" in body["proof_endpoints"]

    client.post(
        f"/ontology/patches/{proposed.json()['id']}/review",
        json={"decision": "approve", "reviewer": "admin", "comment": "테스트 queue 정리"},
    )


def test_enterprise_console_renders_operator_surface():
    response = client.get("/enterprise/console")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")

    body = response.text
    assert "<title>Enterprise Data Trust Console | Semantic Data Portal</title>" in body
    assert "Enterprise Data Trust Console" in body
    assert "KRW 2B enterprise readiness" in body
    assert 'href="/docs"' in body
    assert 'aria-label="Evidence scorecard"' in body
    assert "/enterprise/production-readiness" in body
    assert "/enterprise/evidence-pack" in body
    assert "/enterprise/steward-review" in body
    assert "/enterprise/connectors/sql_connector/probe" in body
    assert "Figma Code Connect disabled" in body


def test_enterprise_controls_expose_feature_gate_manifest():
    response = client.get("/enterprise/controls")
    assert response.status_code == 200

    body = response.json()
    controls = {control["id"]: control for control in body["controls"]}

    assert body["feature_gate"] == "sdp_enterprise"
    assert body["implemented_controls"] >= 2
    assert body["planned_controls"] == 0
    assert body["status"] == "pilot_ready"
    assert controls["tenant_authorization"]["status"] == "implemented"
    assert controls["local_evidence_retention"]["status"] == "implemented"
    assert controls["sso_oidc_adapter"]["status"] == "implemented"
    assert "SDP_OIDC_GROUP_ROLE_MAP" in controls["sso_oidc_adapter"]["evidence"]
    assert "POST /enterprise/auth/oidc-verify" in controls["sso_oidc_adapter"]["evidence"]
    assert controls["rbac_matrix"]["feature_gate"] == "sdp_enterprise"
    assert controls["rbac_matrix"]["status"] == "implemented"
    assert "GET /enterprise/rbac-matrix" in controls["rbac_matrix"]["evidence"]
    assert "GET /enterprise/controls" in controls["rbac_matrix"]["evidence"]
    assert controls["deployment_template"]["status"] == "implemented"
    assert "Dockerfile" in controls["deployment_template"]["evidence"]
    assert controls["operational_observability"]["status"] == "implemented"
    assert "GET /metrics" in controls["operational_observability"]["evidence"]
    assert controls["central_workflow_due_diligence"]["status"] == "external"


def test_enterprise_rbac_matrix_exposes_roles_actions_and_tenant_scope():
    response = client.get("/enterprise/rbac-matrix")
    assert response.status_code == 200

    body = response.json()
    roles = {role["role"]: role for role in body["roles"]}

    assert body["feature_gate"] == "sdp_enterprise"
    assert body["policy_source"] == "sdp.policy.evaluate"
    assert "run_governed_query" in body["action_catalog"]
    assert "publish_dataset" in roles["admin"]["allowed_actions"]
    assert "publish_dataset" in roles["data-analyst"]["denied_actions"]
    assert roles["data-analyst"]["tenant_scope"] == "own_tenant_only"
    assert roles["platform-admin"]["tenant_scope"] == "all_tenants"


def test_enterprise_observability_and_metrics_endpoints():
    observability = client.get("/enterprise/observability")
    assert observability.status_code == 200
    body = observability.json()

    assert body["service"] == "semantic-data-portal"
    assert body["health_endpoint"] == "/health"
    assert body["metrics_endpoint"] == "/metrics"
    assert body["metrics"]["catalog_datasets_total"] >= 3
    assert body["metrics"]["enterprise_controls_implemented"] >= 5
    assert any(alert["id"] == "policy_audit_gap" for alert in body["alerts"])

    metrics = client.get("/metrics")
    assert metrics.status_code == 200
    text = metrics.text
    assert "sdp_catalog_datasets_total" in text
    assert "sdp_enterprise_controls_implemented" in text


def test_request_observability_export_writes_bodyless_jsonl(tmp_path, monkeypatch):
    log_path = tmp_path / "requests.jsonl"
    monkeypatch.setenv("SDP_LOG_SINK_URL", f"file://{log_path}")
    monkeypatch.setenv("SDP_REQUEST_ID_HEADER", "X-Correlation-Id")

    response = client.post(
        "/browse/crm-customer-master/preview",
        headers={"X-Correlation-Id": "buyer-trace-001", "X-SDP-Actor": "analyst@example.com", "X-SDP-Tenant": "demo"},
        json={"user": "analyst", "purpose": "analysis", "limit": 1},
    )

    assert response.status_code == 200
    assert response.headers["X-Correlation-Id"] == "buyer-trace-001"

    records = [json.loads(line) for line in log_path.read_text().splitlines()]
    assert len(records) == 1
    record = records[0]
    assert record["request_id"] == "buyer-trace-001"
    assert record["route"] == "/browse/crm-customer-master/preview"
    assert record["method"] == "POST"
    assert record["status_code"] == 200
    assert record["actor"] == "analyst@example.com"
    assert record["tenant_id"] == "demo"
    assert "latency_ms" in record
    assert "purpose" not in record
    assert "analysis" not in json.dumps(record)

    manifest = client.get("/enterprise/observability").json()
    assert manifest["structured_logs"]["status"] == "implemented"
    assert manifest["structured_logs"]["sink"]["scheme"] == "file"
    assert manifest["metrics"]["request_observations_total"] >= 1
    # The manifest no longer publishes a per-request feed: it is served with no
    # actor, and each observation names the caller and the dataset route. The
    # trace stays verifiable where it belongs - in the configured sink, read above
    # from the log file - and the manifest reports the count.
    assert manifest["recent_request_count"] >= 1
    assert "recent_requests" not in manifest

    metrics = client.get("/metrics").text
    assert "sdp_request_observations_total" in metrics


def test_enterprise_production_readiness_tracks_paid_pilot_integrations():
    response = client.get("/enterprise/production-readiness")
    assert response.status_code == 200

    body = response.json()
    assert body["valuation_target_krw"] == 2_000_000_000
    assert body["current_stage"] == "pilot_candidate"
    assert body["demo_release_ready"] is True
    # paid_pilot_ready is measured, not authored: it was derived from each
    # integration's hardcoded status literal (all "implemented"), so no real
    # change could make it false. With no SDP_* configuration in this test
    # environment the honest answer is False, and the manifest names which
    # variables are missing per integration. See
    # tests/test_production_readiness_measurement.py.
    assert body["paid_pilot_ready"] is False
    assert body["paid_pilot_blockers"], "an unconfigured deployment must name its blockers"

    integrations = {item["id"]: item for item in body["integrations"]}
    assert integrations["postgres_evidence_store"]["status"] == "implemented"
    assert "SDP_DATABASE_URL" in integrations["postgres_evidence_store"]["required_environment"]
    assert "sdp_core.PostgresEvidenceStore" in integrations["postgres_evidence_store"]["current_evidence"]
    assert any("policy decisions and audit events" in item for item in integrations["postgres_evidence_store"]["acceptance_criteria"])

    assert integrations["oidc_jwks_verification"]["status"] == "implemented"
    assert "SDP_OIDC_JWKS_URL" in integrations["oidc_jwks_verification"]["required_environment"]
    assert any("direct role claims" in item for item in integrations["oidc_jwks_verification"]["acceptance_criteria"])

    assert integrations["connector_credential_vault"]["status"] == "implemented"
    assert "SDP_CONNECTOR_SECRET_REF_PREFIX" in integrations["connector_credential_vault"]["required_environment"]
    assert any("raw connector credentials" in item for item in integrations["connector_credential_vault"]["acceptance_criteria"])

    assert integrations["request_observability_export"]["status"] == "implemented"
    assert "/enterprise/observability" in integrations["request_observability_export"]["current_evidence"]

    assert sorted(body["paid_pilot_blockers"]) == sorted(body["unconfigured_integrations"]), (
        "with every integration built, the only blockers are unconfigured ones"
    )
    # It blocks on configuration, not on being unbuilt: its status is
    # "implemented" and only its SDP_OIDC_* variables are unset here.
    assert integrations["oidc_jwks_verification"]["status"] == "implemented"
    assert "oidc_jwks_verification" in body["unconfigured_integrations"]
    assert body["missing_environment"]["oidc_jwks_verification"]
    assert integrations["connector_credential_vault"]["status"] == "implemented"
    assert "connector_credential_vault" in body["unconfigured_integrations"]
    assert integrations["request_observability_export"]["status"] == "implemented"
    assert "request_observability_export" in body["unconfigured_integrations"]
    # Every integration is built; all four block only on configuration.
    assert sorted(body["unconfigured_integrations"]) == sorted(body["paid_pilot_blockers"])
    assert all(
        item["status"] == "implemented" for item in body["integrations"]
    ), "no integration should be unbuilt here; blockers must be configuration only"
    assert body["demo_blockers"] == []


def test_oidc_preview_maps_claims_to_actor_context():
    response = client.post(
        "/enterprise/auth/oidc-preview",
        json={
            "claims": {
                "email": "analyst@example.com",
                "tenant_id": "demo",
                "groups": ["sdp-analysts"],
                "exp": int(time()) + 3600,
            }
        },
    )
    assert response.status_code == 200

    body = response.json()
    assert body["mode"] == "claim_mapping_preview"
    assert body["token_verification"] == "external_signature_required_claim_shape_validated"
    assert body["actor_context"]["subject"] == "analyst@example.com"
    assert body["actor_context"]["tenant_id"] == "demo"
    assert body["actor_context"]["roles"] == ["data-analyst"]


def test_oidc_preview_rejects_unverified_claim_shape():
    response = client.post(
        "/enterprise/auth/oidc-preview",
        json={
            "claims": {
                "email": "analyst@example.com",
                "tenant_id": "demo",
                "groups": ["sdp-analysts"],
            }
        },
    )

    assert response.status_code == 400
    assert "missing exp" in response.json()["detail"]


def test_oidc_preview_ignores_direct_role_escalation_claims():
    response = client.post(
        "/enterprise/auth/oidc-preview",
        json={
            "claims": {
                "email": "analyst@example.com",
                "tenant_id": "demo",
                "roles": ["sdp-platform-admins"],
                "exp": int(time()) + 3600,
            }
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["actor_context"]["roles"] == []
    assert body["ignored_role_claims"] == ["sdp-platform-admins"]


def test_oidc_jwks_verification_maps_verified_token_without_token_leak(monkeypatch):
    token, jwks = _signed_identity_token(
        issuer="https://idp.example.com/",
        audience="semantic-data-portal",
        kid="buyer-key-1",
        claims_extra={"roles": ["sdp-platform-admins"]},
    )
    monkeypatch.setenv("SDP_OIDC_ISSUER", "https://idp.example.com/")
    monkeypatch.setenv("SDP_OIDC_AUDIENCE", "semantic-data-portal")
    monkeypatch.setenv("SDP_OIDC_JWKS", json.dumps(jwks))

    response = client.post("/enterprise/auth/oidc-verify", json={"token": token})

    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "jwks_signature_verification"
    assert body["token_verification"] == "jwks_signature_verified"
    assert body["actor_context"]["subject"] == "analyst@example.com"
    assert body["actor_context"]["tenant_id"] == "buyer-demo"
    assert body["actor_context"]["roles"] == ["data-analyst"]
    assert body["ignored_role_claims"] == ["sdp-platform-admins"]
    assert token not in json.dumps(body)


def test_oidc_jwks_verification_rejects_wrong_audience(monkeypatch):
    token, jwks = _signed_identity_token(
        issuer="https://idp.example.com/",
        audience="wrong-audience",
        kid="buyer-key-1",
    )
    monkeypatch.setenv("SDP_OIDC_ISSUER", "https://idp.example.com/")
    monkeypatch.setenv("SDP_OIDC_AUDIENCE", "semantic-data-portal")
    monkeypatch.setenv("SDP_OIDC_JWKS", json.dumps(jwks))

    response = client.post("/enterprise/auth/oidc-verify", json={"token": token})

    assert response.status_code == 400
    assert "invalid token" in response.json()["detail"]


def test_deployment_template_files_define_local_demo_runtime():
    project_root = Path(__file__).resolve().parents[1]
    dockerfile = (project_root / "Dockerfile").read_text()
    compose = (project_root / "docker-compose.yml").read_text()

    assert "uvicorn" in dockerfile
    assert "SDP_SQLITE_PATH=/data/sdp-evidence.sqlite3" in dockerfile
    assert "semantic-data-portal" in compose
    assert "8000:8000" in compose
    assert "sdp-evidence" in compose


def test_deployment_template_files_require_database_secrets():
    project_root = Path(__file__).resolve().parents[1]
    compose = (project_root / "docker-compose.yml").read_text()

    assert "sdp:sdp" not in compose
    assert "${SDP_DATABASE_URL:-}" in compose
    assert "${SDP_DATABASE_DSN:-}" in compose
    assert "${POSTGRES_USER:-sdp_app}" in compose
    assert "${POSTGRES_PASSWORD:-}" in compose
    assert "${GRAPH_POSTGRES_USER:-sdp_graph_app}" in compose
    assert "${GRAPH_POSTGRES_PASSWORD:-}" in compose
    assert "SDP_DATABASE_URL is required for the postgres profile" in compose
    assert "POSTGRES_PASSWORD is required for the postgres profile" in compose
    assert "GRAPH_POSTGRES_PASSWORD is required for the graph profile" in compose
    assert "SDP_DATABASE_DSN is required for the graph profile" in compose
    assert "postgres:16-alpine@sha256:" in compose
    assert '"127.0.0.1:${POSTGRES_HOST_PORT:-54329}:5432"' in compose
    assert '"127.0.0.1:${GRAPH_POSTGRES_HOST_PORT:-5432}:5432"' in compose
    assert 'pg_isready -U "$${POSTGRES_USER}" -d "$${POSTGRES_DB}"' in compose


def test_fuzz_workflow_avoids_persisted_checkout_tokens_and_editable_install():
    project_root = Path(__file__).resolve().parents[1]
    workflow = (project_root / ".github" / "workflows" / "fuzz.yml").read_text()

    assert workflow.count("persist-credentials: false") == 2
    assert 'pip install -e ".[dev]"' not in workflow
    assert 'pip install -e ".[fuzz]"' not in workflow
    assert "--require-hashes -r requirements-test.txt" in workflow
    assert "--require-hashes -r fuzz-requirements.txt" in workflow
    assert "PYTHONPATH: src" in workflow
    assert "PYTHONPATH: src:." in workflow


def test_enterprise_evidence_pack_summarizes_buyer_diligence():
    client.post(
        "/policy/decision",
        json={
            "subject": "analyst",
            "resource": "crm-customer-master",
            "action": "preview",
            "purpose": "analysis",
        },
    )
    client.post(
        "/browse/crm-customer-master/preview",
        json={"user": "analyst", "purpose": "analysis", "limit": 1},
    )

    response = client.get("/enterprise/evidence-pack")
    assert response.status_code == 200

    body = response.json()
    assert body["valuation_target_krw"] == 2_000_000_000
    assert body["metadata_validation_pass_rate"] >= 0.95
    assert body["shacl_validation_pass_rate"] >= 0.95
    assert body["steward_review_queue_count"] == 0
    assert body["steward_buyer_handoff_ready"] is True
    assert body["ontology_mapping_coverage"] >= 0.7
    assert body["policy_decision_count"] >= 1
    assert body["audit_event_count"] >= 1
    assert body["production_demo_release_ready"] is True
    # paid_pilot_ready is measured, not authored: it was derived from each
    # integration's hardcoded status literal (all "implemented"), so no real
    # change could make it false. With no SDP_* configuration in this test
    # environment the honest answer is False, and the manifest names which
    # variables are missing per integration. See
    # tests/test_production_readiness_measurement.py.
    assert body["production_paid_pilot_ready"] is False
    assert body["production_paid_pilot_blockers"] > 0, (
        "an unconfigured deployment must report its blockers"
    )
    assert body["saleability_gates"]["metadata_validation_pass_rate"] == "pass"
    assert body["saleability_gates"]["shacl_validation_pass_rate"] == "pass"
    assert body["saleability_gates"]["steward_review_queue"] == "pass"
    assert body["saleability_gates"]["ontology_mapping_coverage"] == "pass"
    assert body["saleability_gates"]["production_demo_release"] == "pass"
    # "needs_integration", not "pass": the gate now reflects the measured
    # configuration state, and this suite runs with no SDP_* variables set.
    # That the evidence pack propagates it is the point of this assertion.
    assert body["saleability_gates"]["production_paid_pilot"] == "needs_integration"
    assert "/enterprise/production-readiness" in body["proof_endpoints"]
    assert "/enterprise/shacl-validation" in body["proof_endpoints"]
    assert "/enterprise/steward-review" in body["proof_endpoints"]
    assert "/policy/decisions" in body["proof_endpoints"]


def test_sdp_core_owns_stable_contracts_with_app_compatibility_exports():
    assert app_domain.ActorContext is sdp_core.ActorContext
    assert app_domain.Dataset is sdp_core.Dataset
    assert app_domain.PolicyDecision is sdp_core.PolicyDecision
    assert app_domain.AuditEvent is sdp_core.AuditEvent
    assert app_domain.QueryExecutionRequest is sdp_core.QueryExecutionRequest


def test_sqlite_evidence_store_persists_policy_and_audit_events(tmp_path):
    store = sdp_core.SQLiteEvidenceStore(tmp_path / "evidence.sqlite3")
    previous = app_evidence.configure_evidence_store(store)
    try:
        decision = evaluate(subject="analyst", resource="crm-customer-master", action="preview", purpose="analysis")
        preview = client.post(
            "/browse/crm-customer-master/preview",
            json={"user": "analyst", "purpose": "analysis", "limit": 1},
        )
        assert preview.status_code == 200
    finally:
        app_evidence.configure_evidence_store(previous)

    reopened = sdp_core.SQLiteEvidenceStore(tmp_path / "evidence.sqlite3")
    assert reopened.get_decision(decision.decision_id) == decision
    persisted_decisions = reopened.list_decisions(resource="crm-customer-master", limit=10)
    assert any(row.decision_id == decision.decision_id for row in persisted_decisions)
    persisted_events = reopened.list_events(resource="crm-customer-master", limit=10)
    assert any(event.action == "browse.preview" and event.decision_id for event in persisted_events)


def test_configured_evidence_store_prefers_postgres_over_sqlite(monkeypatch, tmp_path):
    built = {}

    class FakePostgresEvidenceStore:
        def __init__(self, dsn: str, *, sslmode: str | None = None):
            built["dsn"] = dsn
            built["sslmode"] = sslmode

    monkeypatch.setattr(app_evidence, "PostgresEvidenceStore", FakePostgresEvidenceStore)

    store = app_evidence._build_configured_evidence_store(
        {
            "SDP_DATABASE_URL": "postgresql://buyer:secret@db.example.com:5432/sdp",
            "SDP_DATABASE_SSLMODE": "require",
            "SDP_SQLITE_PATH": str(tmp_path / "fallback.sqlite3"),
        }
    )

    assert isinstance(store, FakePostgresEvidenceStore)
    assert built == {
        "dsn": "postgresql://buyer:secret@db.example.com:5432/sdp",
        "sslmode": "require",
    }


def test_postgres_evidence_store_uses_tenant_columns_and_store_protocol():
    connections = []

    class FakeCursor:
        def __init__(self):
            self.rows = []

        def execute(self, sql, params=()):
            if "SELECT payload FROM policy_decisions" in sql:
                self.rows = [
                    (
                        {
                            "subject": "analyst",
                            "resource": "crm-customer-master",
                            "action": "preview",
                            "effect": "allow",
                            "decision_id": "decision-1",
                            "obligations": {"tenant_id": "buyer-demo"},
                            "reason": "ok",
                        },
                    )
                ]
            elif "SELECT payload FROM audit_events" in sql:
                self.rows = [
                    (
                        {
                            "id": "audit-1",
                            "actor": "analyst",
                            "action": "browse.preview",
                            "resource": "crm-customer-master",
                            "result": "allowed",
                            "decision_id": "decision-1",
                            "details": {"tenant_id": "buyer-demo"},
                            "reason": "ok",
                            "created_at": "2026-07-02T00:00:00Z",
                        },
                    )
                ]
            return self

        def fetchone(self):
            return self.rows[0] if self.rows else None

        def fetchall(self):
            return self.rows

    class FakeConnection:
        def __init__(self):
            self.statements = []

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def cursor(self):
            return FakeCursorContext(self)

        def execute(self, sql, params=()):
            self.statements.append((sql, params))
            return FakeCursor().execute(sql, params)

    class FakeCursorContext:
        def __init__(self, connection):
            self.connection = connection
            self.cursor = FakeCursor()

        def __enter__(self):
            return self.cursor

        def __exit__(self, exc_type, exc, tb):
            return False

    def connect_factory(dsn, **kwargs):
        connection = FakeConnection()
        connections.append((dsn, kwargs, connection))
        return connection

    store = sdp_core.PostgresEvidenceStore(
        "postgresql://buyer:secret@localhost:5432/sdp",
        sslmode="require",
        connect_factory=connect_factory,
    )
    decision = sdp_core.PolicyDecision(
        subject="analyst",
        resource="crm-customer-master",
        action="preview",
        effect="allow",
        decision_id="decision-1",
        obligations={"tenant_id": "buyer-demo"},
        reason="ok",
    )
    event = sdp_core.AuditEvent(
        id="audit-1",
        actor="analyst",
        action="browse.preview",
        resource="crm-customer-master",
        result="allowed",
        decision_id="decision-1",
        details={"tenant_id": "buyer-demo"},
        reason="ok",
    )

    assert store.record_decision(decision) == decision
    assert store.get_decision("decision-1") == decision
    assert store.append_event(event) == event
    assert store.list_decisions(resource="crm-customer-master", limit=5)[0].decision_id == "decision-1"
    assert store.list_events(resource="crm-customer-master", limit=5)[0].id == "audit-1"

    statements = "\n".join(sql for _, _, connection in connections for sql, _ in connection.statements)
    assert "tenant_id TEXT NOT NULL" in statements
    assert "payload JSONB NOT NULL" in statements
    assert "created_at TIMESTAMPTZ NOT NULL" in statements
    assert "idx_policy_decisions_tenant_resource_created" in statements
    assert "idx_audit_events_tenant_resource_created" in statements
    assert "ON CONFLICT" in statements
    assert any(kwargs == {"sslmode": "require"} for _, kwargs, _ in connections)


def test_persisted_audit_list_uses_configured_store(tmp_path):
    store = sdp_core.SQLiteEvidenceStore(tmp_path / "audit.sqlite3")
    previous = app_evidence.configure_evidence_store(store)
    try:
        response = client.post(
            "/browse/crm-customer-master/preview",
            json={"user": "analyst", "purpose": "analysis", "limit": 1},
        )
        assert response.status_code == 200
        events = app_evidence.list_persisted_audit_events(resource="crm-customer-master", limit=5)
        assert any(event.action == "browse.preview" for event in events)
        decisions = app_evidence.list_persisted_policy_decisions(resource="crm-customer-master", limit=5)
        assert any(decision.action == "preview" for decision in decisions)
    finally:
        app_evidence.configure_evidence_store(previous)


def test_audit_events_endpoint_reads_configured_evidence_store_after_memory_clear(tmp_path):
    store = sdp_core.SQLiteEvidenceStore(tmp_path / "audit-endpoint.sqlite3")
    previous = app_evidence.configure_evidence_store(store)
    try:
        response = client.post(
            "/browse/crm-customer-master/preview",
            json={"user": "analyst", "purpose": "analysis", "limit": 1},
        )
        assert response.status_code == 200

        app_catalog._AUDIT_LOG.clear()

        events_response = client.get("/audit/events", params={"resource": "crm-customer-master", "limit": 10, "user": "admin"})
        assert events_response.status_code == 200
        assert any(event["action"] == "browse.preview" for event in events_response.json())
    finally:
        app_evidence.configure_evidence_store(previous)


def test_policy_decision_store_does_not_duplicate_configured_store_in_memory(tmp_path):
    store = sdp_core.SQLiteEvidenceStore(tmp_path / "policy-memory.sqlite3")
    previous_log = list(app_evidence._POLICY_DECISION_LOG)
    previous = app_evidence.configure_evidence_store(store)
    try:
        decision = evaluate(subject="analyst", resource="crm-customer-master", action="preview", purpose="analysis")
    finally:
        app_evidence.configure_evidence_store(previous)

    assert app_evidence._POLICY_DECISION_LOG == previous_log
    assert store.get_decision(decision.decision_id) == decision


def test_policy_decisions_endpoint_exposes_decision_evidence():
    decision_response = client.post(
        "/policy/decision",
        json={
            "subject": "analyst",
            "resource": "crm-customer-master",
            "action": "preview",
            "purpose": "analysis",
        },
    )
    assert decision_response.status_code == 200
    decision_id = decision_response.json()["decision_id"]

    response = client.get("/policy/decisions", params={"resource": "crm-customer-master", "limit": 10, "user": "admin"})
    assert response.status_code == 200

    decisions = response.json()
    assert any(decision["decision_id"] == decision_id for decision in decisions)


def test_enterprise_demo_smoke_summary_is_ready():
    summary = smoke_summary()
    assert summary["valuation_target_krw"] == 2_000_000_000
    assert summary["demo_activation_days"] <= 10
    assert summary["demo_seed_datasets"] >= 3
    assert summary["metadata_validation_pass_rate"] >= 0.95
    assert summary["shacl_validation_pass_rate"] >= 0.95
    assert summary["steward_review_queue_count"] == 0
    assert summary["steward_buyer_handoff_ready"] is True
    assert summary["ontology_mapping_coverage"] >= 0.7
    assert summary["primary_kpis"] >= 3
    assert summary["guardrail_kpis"] >= 3
    assert summary["enterprise_controls"] >= 6
    assert summary["implemented_enterprise_controls"] >= 2
    assert summary["connector_probe_status"] == "ready_for_demo"
    assert summary["connector_probe_domain"] == "customer_intelligence"
    assert summary["rdf_connector_probe_status"] == "ready_for_demo"
    assert summary["rdf_connector_probe_dataset"] == "semantic-glossary"
    assert summary["file_lake_connector_probe_status"] == "ready_for_demo"
    assert summary["file_lake_connector_probe_dataset"] == "crm-event"
    assert summary["rest_connector_probe_status"] == "contract_only"
    assert summary["rest_connector_adapter_status"] == "implemented"
    assert summary["production_current_stage"] == "pilot_candidate"
    assert summary["production_demo_release_ready"] is True
    # Measured from the environment; this suite runs with no SDP_* set.
    assert summary["production_paid_pilot_ready"] is False
    assert summary["production_paid_pilot_blockers"] > 0
    assert summary["ready"] is True


def test_enterprise_connector_probe_exposes_demo_evidence():
    response = client.get(
        "/enterprise/connectors/sql_connector/probe",
        params={"dataset_id": "crm-customer-master", "user": "admin"},
    )
    assert response.status_code == 200

    body = response.json()
    assert body["connector_id"] == "sql_connector"
    assert body["dataset_id"] == "crm-customer-master"
    assert body["status"] == "ready_for_demo"
    assert body["adapter_status"] == "implemented"
    assert body["data_contract"]["schema_fields"] > 0
    assert body["demo_context"]["domain_id"] == "customer_intelligence"

    controls = {item["control"]: item for item in body["control_evidence"]}
    assert controls["policy_before_query"]["status"] == "implemented"
    assert "/browse/query" in controls["policy_before_query"]["proof_endpoints"]
    assert controls["audit_event"]["status"] == "implemented"


def test_enterprise_rdf_connector_probe_exposes_semantic_store_evidence():
    response = client.get(
        "/enterprise/connectors/rdf_connector/probe",
        params={"dataset_id": "semantic-glossary", "user": "admin"},
    )
    assert response.status_code == 200

    body = response.json()
    assert body["connector_id"] == "rdf_connector"
    assert body["dataset_id"] == "semantic-glossary"
    assert body["status"] == "ready_for_demo"
    assert body["adapter_status"] == "implemented"
    assert body["source_system"].startswith("sparql://")
    assert body["data_contract"]["schema_fields"] >= 3

    controls = {item["control"]: item for item in body["control_evidence"]}
    assert controls["ontology_version_pin"]["status"] == "implemented"
    assert "/ontology/search" in controls["ontology_version_pin"]["proof_endpoints"]


def test_enterprise_file_lake_connector_probe_exposes_manifest_evidence():
    response = client.get(
        "/enterprise/connectors/file_lake_connector/probe",
        params={"dataset_id": "crm-event", "user": "admin"},
    )
    assert response.status_code == 200

    body = response.json()
    assert body["connector_id"] == "file_lake_connector"
    assert body["dataset_id"] == "crm-event"
    assert body["status"] == "ready_for_demo"
    assert body["adapter_status"] == "implemented"
    assert body["source_system"].startswith("s3://")

    controls = {item["control"]: item for item in body["control_evidence"]}
    assert controls["sample_budget"]["status"] == "implemented"
    assert controls["pii_profile"]["status"] == "implemented"
    assert "/catalog/datasets/{dataset_id}/profile" in controls["pii_profile"]["proof_endpoints"]


def test_enterprise_rest_connector_probe_exposes_api_contract_gap():
    response = client.get(
        "/enterprise/connectors/rest_connector/probe",
        params={"dataset_id": "marketing-campaign", "user": "admin"},
    )
    assert response.status_code == 200

    body = response.json()
    assert body["connector_id"] == "rest_connector"
    assert body["dataset_id"] == "marketing-campaign"
    assert body["status"] == "contract_only"
    assert body["adapter_status"] == "implemented"
    assert body["source_system"].startswith("https://")

    controls = {item["control"]: item for item in body["control_evidence"]}
    assert controls["credential_vault"]["status"] == "implemented"
    assert controls["credential_vault"]["secret_present"] is False
    assert controls["credential_vault"]["secret_ref"] == "SDP_CONNECTOR_SECRET_REST_CONNECTOR_MARKETING_CAMPAIGN_TOKEN"
    assert controls["purpose_binding"]["status"] == "implemented"


def test_enterprise_rest_connector_probe_uses_vault_reference_without_secret_leak(monkeypatch):
    monkeypatch.setenv("SDP_CONNECTOR_SECRET_REF_PREFIX", "SDP_CONNECTOR_SECRET_")
    monkeypatch.setenv("SDP_CONNECTOR_SECRET_REST_CONNECTOR_MARKETING_CAMPAIGN_TOKEN", "buyer-api-token-secret")

    response = client.get(
        "/enterprise/connectors/rest_connector/probe",
        params={"dataset_id": "marketing-campaign", "user": "admin"},
    )
    assert response.status_code == 200

    body = response.json()
    assert body["status"] == "ready_for_demo"
    controls = {item["control"]: item for item in body["control_evidence"]}
    assert controls["credential_vault"]["status"] == "implemented"
    assert controls["credential_vault"]["secret_present"] is True
    assert controls["credential_vault"]["secret_ref"] == "SDP_CONNECTOR_SECRET_REST_CONNECTOR_MARKETING_CAMPAIGN_TOKEN"
    assert "buyer-api-token-secret" not in json.dumps(body)


def test_sql_connector_adapter_implements_source_connector_contract():
    connector = get_source_connector("sql_connector")
    schema = connector.inspect_schema("crm-customer-master")
    rows = connector.preview("crm-customer-master", limit=1, offset=0)

    assert connector.connector_id == "sql_connector"
    assert schema["source_system"].startswith("postgresql://")
    assert schema["columns"]
    assert rows
    assert rows[0]["customer_email"] == "***"


def test_rdf_connector_adapter_implements_source_connector_contract():
    connector = get_source_connector("rdf_connector")
    schema = connector.inspect_schema("semantic-glossary")
    rows = connector.preview("semantic-glossary", limit=2, offset=0)

    assert connector.connector_id == "rdf_connector"
    assert schema["source_system"].startswith("sparql://")
    assert schema["named_graph"] == "semantic.graph/customer-intelligence"
    assert rows
    assert rows[0]["concept_uri"].startswith("https://semantic-data-portal.local/concepts/")


def test_file_lake_connector_adapter_implements_source_connector_contract():
    connector = get_source_connector("file_lake_connector")
    schema = connector.inspect_schema("crm-event")
    rows = connector.preview("crm-event", limit=1, offset=0)

    assert connector.connector_id == "file_lake_connector"
    assert schema["source_system"].startswith("s3://")
    assert schema["manifest_path"].endswith("/_manifest.json")
    assert rows
    assert rows[0]["event_id"] == "evt-1001"


def test_rest_connector_adapter_implements_source_connector_contract():
    connector = get_source_connector("rest_connector")
    schema = connector.inspect_schema("marketing-campaign")
    rows = connector.preview("marketing-campaign", limit=1, offset=0)

    assert connector.connector_id == "rest_connector"
    assert schema["source_system"].startswith("https://")
    assert schema["auth_mode"] == "service_account_reference"
    assert rows
    assert rows[0]["campaign_id"] == "cmp-1001"


def test_enterprise_connector_probe_fails_closed():
    unsupported = client.get(
        "/enterprise/connectors/admin_shell/probe",
        params={"dataset_id": "crm-event", "user": "admin"},
    )
    assert unsupported.status_code == 400

    # An unauthorized caller is refused before it learns whether the connector id
    # is supported: authorization runs ahead of connector resolution.
    unauthorized = client.get(
        "/enterprise/connectors/admin_shell/probe",
        params={"dataset_id": "crm-event"},
    )
    assert unauthorized.status_code == 403

    # A missing dataset stays 404 for everyone, matching the browse convention
    # (test_preview_policy_denies_missing_dataset).
    missing_dataset = client.get(
        "/enterprise/connectors/sql_connector/probe",
        params={"dataset_id": "unknown", "user": "admin"},
    )
    assert missing_dataset.status_code == 404


def test_catalog_search_and_detail():
    response = client.get("/catalog/search", params={"q": "활성 고객", "user": "analyst"})
    assert response.status_code == 200
    body = response.json()
    assert body["count"] >= 1
    assert "id" in body["items"][0]

    detail = client.get("/catalog/datasets/crm-customer-master", params={"user": "analyst"})
    assert detail.status_code == 200
    detail_body = detail.json()
    assert detail_body["id"] == "crm-customer-master"
    assert detail_body["status"] in {"published", "registered", "deprecated"}


def test_catalog_search_filter_by_quality():
    response = client.get("/catalog/search", params={"q": "고객", "min_quality": 0.9, "user": "analyst"})
    assert response.status_code == 200
    assert all(item["quality"] >= 0.9 for item in response.json()["items"])


def test_catalog_dataset_detail_exposes_recommendation_score():
    response = client.get("/catalog/datasets/crm-customer-master", params={"user": "analyst"})
    assert response.status_code == 200
    body = response.json()
    assert "metadata_recommendation_score" in body
    assert body["metadata_recommendation_score"] >= 0


def test_catalog_facets_and_audit_events():
    response = client.get("/catalog/facets", params={"field": "sensitivity", "user": "analyst"})
    assert response.status_code == 200
    assert response.json()["field"] == "sensitivity"

    events = client.get("/audit/events", params={"user": "admin"})
    assert events.status_code == 200
    assert isinstance(events.json(), list)


def test_ontology_resolve():
    response = client.post("/ontology/resolve", json={"text": "활성 고객 데이터를 찾아줘"})
    assert response.status_code == 200
    body = response.json()
    assert body["resolved"]
    assert body["resolved"][0]["term"] in {"활성 고객", "고객"}


def test_llm_search_uses_catalog_discovery_policy_scope():
    response = client.post(
        "/llm/search",
        json={"question": "활성 고객 데이터를 찾아줘", "user": "analyst", "purpose": "analysis"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["policy_scope"] == "catalog_discovery"
    assert body["policy"]["action"] == "discover"
    assert body["policy"]["resource"] == "catalog"
    assert body["policy"]["effect"] == "allow"


def test_ontology_concept_graph():
    response = client.get("/ontology/term/활성 고객/graph")
    assert response.status_code == 200
    body = response.json()
    assert "broader" in body
    assert body["canonical"] in {"활성 고객", "고객", "이탈"}


def test_ontology_search():
    response = client.get("/ontology/search", params={"q": "churn"})
    assert response.status_code == 200
    body = response.json()
    assert body["count"] >= 1
    assert any(item["concept"] in {"이탈", "이탈 고객"} for item in body["matches"])


def test_join_candidate_endpoint():
    response = client.get("/catalog/datasets/crm-customer-master/join-candidates", params={"user": "analyst"})
    assert response.status_code == 200
    body = response.json()
    assert body["dataset_id"] == "crm-customer-master"
    assert "join_candidates" in body
    assert any(item["dataset_id"] == "crm-event" for item in body["join_candidates"])


def test_dataset_profile_endpoint():
    # This test used to call the route with no actor at all, which is what pinned
    # the ungated behaviour: the route published dataset `profile` and per-column
    # `quality_issues` - both governed fields - to an anonymous caller.
    response = client.get(
        "/catalog/datasets/crm-customer-master/profile", params={"user": "analyst"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["dataset_id"] == "crm-customer-master"
    assert "schema_profile" in body
    assert body["schema_profile"]


def test_preview_policy_denies_missing_dataset():
    response = client.post("/browse/unknown/preview", json={"user": "user1", "purpose": "analysis"})
    assert response.status_code == 404

    events = client.get("/audit/events", params={"resource": "unknown", "user": "admin"})
    assert events.status_code == 200
    assert any(
        event["action"] == "browse.preview"
        and event["result"] == "denied"
        and event["reason"] == "dataset_not_found"
        for event in events.json()
    )


def test_preview_pagination_and_decision_traceability():
    response = client.post(
        "/browse/crm-customer-master/preview",
        json={"user": "analyst", "purpose": "analysis", "offset": 1, "limit": 1},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["offset"] == 1
    assert body["row_count"] == 1
    assert body["policy_decision_id"] == body["policy_decision"]["decision_id"]
    assert body["rows"]
    assert body["sampling_note"]


def test_preview_denies_low_privilege_actor():
    """A caller with no resolvable tenant is refused, and learns nothing.

    404, not 403: ``guest`` resolves to no tenant and no roles, so it cannot
    reach this dataset's tenant, and 403-for-foreign plus 404-for-missing is an
    existence oracle over an enumerable id space. The refusal is still recorded -
    the audit row below carries the real reason - so denial remains evidence.

    Note the fixture gap this exposes: no seeded subject is *inside* the tenant
    and *lacking* read rights, so the "insufficient role" refusal (which does
    stay a 403) has no representative actor here. See
    ``tests/test_browse.py::test_a_denial_inside_the_tenant_still_raises_permission_error``
    for that case, which uses sensitivity instead of role.
    """
    before = len(app_catalog._AUDIT_LOG)
    response = client.post(
        "/browse/crm-customer-master/preview",
        json={"user": "guest", "purpose": "analysis"},
    )
    assert response.status_code == 404, response.text
    audited = app_catalog._AUDIT_LOG[before:]
    assert [event.result for event in audited] == ["denied"]
    assert audited[0].reason == "tenant boundary denied"


def test_audit_event_includes_policy_decision_id_for_preview():
    response = client.post(
        "/browse/crm-event/preview",
        json={"user": "analyst", "purpose": "analysis", "limit": 1},
    )
    assert response.status_code == 200
    body = response.json()
    decision_id = body["policy_decision_id"]

    events = client.get("/audit/events", params={"resource": "crm-event", "user": "admin"})
    assert events.status_code == 200
    matching = [event for event in events.json() if event["action"] == "browse.preview" and event["details"].get("policy_decision_id") == decision_id]
    assert matching, "preview audit event should record policy decision id"


def test_draft_query():
    payload = {
        "question": "최근 90일 활성 고객 수 주별 집계",
        "user": "analyst",
        "purpose": "analysis",
        "dataset_id": "crm-event",
        "group_by": "customer_id",
        "columns": ["customer_id", "event_timestamp"],
        "date_window_days": 30,
        "row_limit": 50,
        "timeout_ms": 8000,
    }
    response = client.post("/llm/draft-query", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert "query" in body
    assert "policy_decision_id" in body
    assert body["policy_decision_id"] == body["policy_decision"]["decision_id"]
    assert body["timeout_ms"] == 8000
    assert body["estimated_cost"] > 0
    assert "LIMIT 50" in body["query"]


def test_draft_query_sanitizes_group_by_identifier():
    create_payload = {
        "actor": "admin",
        "id": "hyphenated-column-dataset",
        "title": "하이픈 컬럼 데이터셋",
        "description": "SQL 식별자 sanitization 검증용 데이터셋",
        "owner": "data-platform",
        "steward": "qa",
        "domain": "테스트",
        "source_system": "postgresql://analytics.dw/hyphen_table",
        "sensitivity": "low",
        "update_frequency": "daily",
        "quality_score": 0.91,
        "freshness_score": 0.93,
        "tags": ["테스트"],
        "terms": ["테스트"],
        "related_datasets": [],
        "schema": [
            {
                "name": "segment-name",
                "datatype": "string",
                "nullable_ratio": 0.0,
                "distinct_ratio": 0.5,
                "pii": False,
            }
        ],
        "distributions": [
            {
                "id": "dist-hyphenated-column",
                "format": "postgresql.table",
                "endpoint": "https://example.internal/api/table/hyphen_table",
            }
        ],
        "mappings": [],
        "profile": {},
    }
    created = client.post("/catalog/datasets", json=create_payload)
    assert created.status_code == 200
    published = client.post("/catalog/datasets/hyphenated-column-dataset/publish", json={"actor": "admin"})
    assert published.status_code == 200

    response = client.post(
        "/llm/draft-query",
        json={
            "question": "세그먼트별 고객 수",
            "user": "analyst",
            "purpose": "analysis",
            "dataset_id": "hyphenated-column-dataset",
            "group_by": "segment-name",
            "date_window_days": 30,
            "row_limit": 25,
        },
    )
    assert response.status_code == 200
    query = response.json()["query"]
    assert "SELECT segment_name" in query
    assert "GROUP BY segment_name" in query
    assert "segment-name" not in query


def test_catalog_schema_history_and_diff():
    patch = client.patch("/catalog/datasets/crm-event", json={"actor": "admin", "schema": []})
    assert patch.status_code == 200
    versions = client.get(
        "/catalog/datasets/crm-event/schema-versions", params={"user": "analyst"}
    )
    assert versions.status_code == 200, versions.text
    payload = versions.json()
    assert "versions" in payload
    assert payload["versions"]

    history = client.get(
        "/catalog/datasets/crm-event/schema-history", params={"user": "analyst"}
    )
    assert history.status_code == 200, history.text
    history_payload = history.json()
    assert history_payload["history"]
    first_version = history_payload["history"][0]["schema_version"]
    last_version = history_payload["history"][-1]["schema_version"]

    diff = client.get(
        "/catalog/datasets/crm-event/schema-diff",
        params={
            "from_version": first_version,
            "to_version": last_version,
            "user": "analyst",
        },
    )
    assert diff.status_code == 200
    diff_payload = diff.json()
    assert diff_payload["diff"]["from_version"] == first_version
    assert diff_payload["diff"]["to_version"] == last_version


def test_dataset_mutation_policy_and_lifecycle():
    create_payload = {
        "actor": "admin",
        "id": "temp-dataset",
        "title": "테스트 데이터셋",
        "description": "테스트를 위한 임시 데이터셋",
        "owner": "data-platform",
        "steward": "qa",
        "domain": "테스트",
        "source_system": "postgresql://analytics/tmp",
        "sensitivity": "low",
        "update_frequency": "daily",
        "quality_score": 0.75,
        "freshness_score": 0.88,
        "tags": ["테스트"],
        "terms": ["테스트"],
        "related_datasets": [],
        "schema": [
            {
                "name": "sample_id",
                "datatype": "string",
                "nullable_ratio": 0.0,
                "distinct_ratio": 1.0,
                "pii": False,
            }
        ],
        "distributions": [
            {
                "id": "dist-temp-dataset",
                "format": "postgresql.table",
                "endpoint": "https://example.internal/api/table/temp_dataset",
            }
        ],
        "mappings": [],
        "profile": {},
    }
    created = client.post("/catalog/datasets", json=create_payload)
    assert created.status_code == 200
    assert created.json()["dataset"]["id"] == "temp-dataset"

    publish_payload = {"actor": "admin"}
    published = client.post("/catalog/datasets/temp-dataset/publish", json=publish_payload)
    assert published.status_code == 200
    assert published.json()["dataset"]["status"] == "published"

    patched = client.patch("/catalog/datasets/temp-dataset", json={"actor": "admin", "title": "테스트 데이터셋 v2"})
    assert patched.status_code == 200
    assert patched.json()["dataset"]["title"] == "테스트 데이터셋 v2"

    lineage = client.get(
        "/catalog/datasets/temp-dataset/lineage", params={"user": "analyst"}
    )
    assert lineage.status_code == 200, lineage.text
    assert lineage.json()["dataset_id"] == "temp-dataset"

    deprecated = client.post("/catalog/datasets/temp-dataset/deprecate", json={"actor": "admin", "reason": "e2e cleanup"})
    assert deprecated.status_code == 200
    assert deprecated.json()["dataset"]["status"] == "deprecated"


def test_tenant_boundary_denies_cross_tenant_preview():
    create_payload = {
        "actor": "admin",
        "id": "external-tenant-dataset",
        "tenant_id": "external",
        "title": "외부 테넌트 데이터셋",
        "description": "tenant isolation 검증용 데이터셋",
        "owner": "external-data-platform",
        "steward": "external-steward",
        "domain": "테스트",
        "source_system": "postgresql://external.dw/customer",
        "sensitivity": "low",
        "update_frequency": "daily",
        "quality_score": 0.88,
        "freshness_score": 0.9,
        "tags": ["테스트"],
        "terms": ["테스트"],
        "related_datasets": [],
        "schema": [
            {
                "name": "customer_id",
                "datatype": "string",
                "nullable_ratio": 0.0,
                "distinct_ratio": 1.0,
                "pii": False,
            }
        ],
        "distributions": [
            {
                "id": "dist-external-tenant-dataset",
                "format": "postgresql.table",
                "endpoint": "https://example.internal/api/table/external_customer",
            }
        ],
        "mappings": [],
        "profile": {},
    }
    created = client.post("/catalog/datasets", json=create_payload)
    assert created.status_code == 200
    assert created.json()["dataset"]["tenant_id"] == "external"
    # The cross-tenant refusal below is a 404, not a 403: the two answers
    # together would tell an outside caller which ids exist.

    denied = client.post(
        "/browse/external-tenant-dataset/preview",
        json={"user": "analyst", "purpose": "analysis", "limit": 1},
    )
    assert denied.status_code == 404, denied.text
    assert "tenant" not in denied.text, "the refusal must not explain itself to an outsider"
    # The real reason moved from the response body to the ledger, where it
    # belongs: the client learns nothing, the auditor learns everything.
    decisions = app_evidence._POLICY_DECISION_LOG
    boundary_denials = [
        decision
        for decision in decisions
        if decision.resource == "external-tenant-dataset" and decision.effect == "deny"
    ]
    assert boundary_denials, "the denial must still be recorded as a policy decision"
    assert boundary_denials[-1].reason == "tenant boundary denied"

    allowed = client.post(
        "/browse/external-tenant-dataset/preview",
        json={"user": "external-analyst", "purpose": "analysis", "limit": 1},
    )
    assert allowed.status_code == 200
    assert allowed.json()["policy_decision"]["obligations"]["tenant_id"] == "external"


def test_publish_requires_schema_and_distribution_metadata():
    create_payload = {
        "actor": "admin",
        "id": "invalid-publish-dataset",
        "title": "불완전한 데이터셋",
        "description": "publish gate 실패 검증",
        "owner": "data-platform",
        "steward": "qa",
        "domain": "테스트",
        "source_system": "postgresql://analytics/tmp_invalid",
        "sensitivity": "low",
        "update_frequency": "daily",
        "quality_score": 0.75,
        "freshness_score": 0.88,
        "tags": ["테스트"],
        "terms": ["테스트"],
        "related_datasets": [],
        "schema": [],
        "distributions": [],
        "mappings": [],
        "profile": {},
    }
    created = client.post("/catalog/datasets", json=create_payload)
    assert created.status_code == 200

    published = client.post("/catalog/datasets/invalid-publish-dataset/publish", json={"actor": "admin"})
    assert published.status_code == 400
    assert "metadata validation failed" in published.json()["detail"]


def test_browse_schema_requires_purpose():
    response = client.get("/browse/crm-customer-master/schema", params={"user": "analyst"})
    assert response.status_code == 200
    body = response.json()
    assert "policy_decision_id" in body


def test_create_requires_admin():
    create_payload = {
        "actor": "analyst",
        "title": "권한 없는 데이터셋",
        "description": "권한 테스트",
        "owner": "data-platform",
        "steward": "qa",
        "domain": "테스트",
        "source_system": "postgresql://analytics/tmp",
        "sensitivity": "low",
        "update_frequency": "daily",
        "quality_score": 0.81,
        "freshness_score": 0.78,
        "tags": ["테스트"],
        "terms": ["테스트"],
        "related_datasets": [],
        "schema": [],
        "distributions": [],
        "mappings": [],
        "profile": {},
    }
    response = client.post("/catalog/datasets", json=create_payload)
    assert response.status_code == 403


def test_ontology_patch_workflow():
    propose = client.post(
        "/ontology/patches",
        json={
            "actor": "analyst",
            "concept": "이탈",
            "suggestion": "탈퇴한 고객은 최근 30일 주문 비율이 감소하는 segment로 분류 제안",
            "requestor": "analyst",
        },
    )
    assert propose.status_code == 200
    patch = propose.json()
    assert patch["status"] == "proposed"

    patches = client.get("/ontology/patches")
    assert patches.status_code == 200
    patch_list = patches.json()["patches"]
    assert any(item["id"] == patch["id"] for item in patch_list)

    # This call used to pass `reviewer` with no actor at all, which is what
    # pinned the unauthenticated, body-supplied-reviewer behaviour.
    review = client.post(
        f"/ontology/patches/{patch['id']}/review",
        json={"decision": "approve", "actor": "admin", "comment": "적절한 제안"},
    )
    assert review.status_code == 200
    assert review.json()["status"] == "approved"


def test_browse_query_success():
    response = client.post(
        "/browse/query",
        json={
            "user": "analyst",
            "purpose": "analysis",
            "dataset_ids": ["crm-event"],
            "language": "SQL",
            "query": "SELECT count(*) AS active_count FROM crm",
            "dry_run": False,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "SUCCEEDED"
    assert body["dataset_id"] == "crm-event"
    assert body["policy_decision_id"] is not None
    assert "request_id" in body

    events = client.get("/audit/events", params={"resource": "crm-event", "user": "admin"})
    assert events.status_code == 200
    assert any(
        event["action"] == "browse.query"
        and event["result"] == "allowed"
        and event["decision_id"] == body["policy_decision_id"]
        and event["details"].get("request_id") == body["request_id"]
        for event in events.json()
    )


def test_browse_query_rejects_table_outside_dataset_binding():
    response = client.post(
        "/browse/query",
        json={
            "user": "analyst",
            "purpose": "analysis",
            "dataset_ids": ["crm-event"],
            "language": "SQL",
            "query": "SELECT count(*) AS active_count FROM customer",
        },
    )
    assert response.status_code == 400
    assert "unauthorized_table_reference" in response.json()["detail"]["warnings"]

    events = client.get("/audit/events", params={"resource": "crm-event", "user": "admin"})
    assert events.status_code == 200
    assert any(
        event["action"] == "browse.query"
        and event["result"] == "rejected"
        and event["reason"] == "query_safety_validation_failed"
        for event in events.json()
    )


def test_browse_query_rejects_literal_tautology_injection():
    response = client.post(
        "/browse/query",
        json={
            "user": "analyst",
            "purpose": "analysis",
            "dataset_ids": ["crm-event"],
            "language": "SQL",
            "query": "SELECT count(*) AS active_count FROM crm WHERE customer_id = 'x' OR '1'='1'",
        },
    )

    assert response.status_code == 400
    warnings = response.json()["detail"]["warnings"]
    assert "literal_values_not_allowed" in warnings
    assert "boolean_operator_not_allowed" in warnings


def test_browse_query_denied_without_user():
    """An unresolvable actor is refused, and told nothing about the dataset.

    ``guest`` resolves to no tenant, so it cannot reach this dataset's tenant and
    the refusal collapses into the route's own "not found" answer - 400 REJECTED
    ``dataset_not_found``, the same thing this route returns for a dataset that
    is not there. Previously it was 403 ``tenant boundary denied`` for a dataset
    that exists and 400 ``dataset_not_found`` for one that does not, which told
    an outsider which ids exist. The real reason is in the ledger; the audit
    assertion below is unchanged.
    """
    response = client.post(
        "/browse/query",
        json={
            "user": "guest",
            "purpose": "analysis",
            "dataset_ids": ["crm-event"],
            "language": "SQL",
            "query": "SELECT count(*) AS active_count FROM crm",
        },
    )
    assert response.status_code == 400, response.text
    assert response.json()["detail"]["warnings"] == ["dataset_not_found"]
    assert "tenant" not in response.text

    events = client.get("/audit/events", params={"resource": "crm-event", "user": "admin"})
    assert events.status_code == 200
    assert any(
        event["action"] == "browse.query"
        and event["result"] == "denied"
        and event["actor"] == "guest"
        for event in events.json()
    )


def test_oidc_preview_scopes_group_roles_to_claimed_tenant():
    """A group that grants roles under one tenant must grant nothing under
    another, so a shared identity provider group cannot cross a tenant
    boundary."""
    role_map = {
        "demo": {"sdp-analysts": ["data-analyst"]},
        "external": {"sdp-analysts": []},
    }
    granted = client.post(
        "/enterprise/auth/oidc-preview",
        json={
            "claims": {
                "email": "analyst@example.com",
                "tenant_id": "demo",
                "groups": ["sdp-analysts"],
                "exp": int(time()) + 3600,
            },
            "role_map": role_map,
        },
    )
    revoked = client.post(
        "/enterprise/auth/oidc-preview",
        json={
            "claims": {
                "email": "analyst@example.com",
                "tenant_id": "external",
                "groups": ["sdp-analysts"],
                "exp": int(time()) + 3600,
            },
            "role_map": role_map,
        },
    )
    unscoped = client.post(
        "/enterprise/auth/oidc-preview",
        json={
            "claims": {
                "email": "analyst@example.com",
                "tenant_id": "unscoped-tenant",
                "groups": ["sdp-analysts"],
                "exp": int(time()) + 3600,
            },
            "role_map": role_map,
        },
    )

    assert granted.status_code == 200
    assert granted.json()["actor_context"]["roles"] == ["data-analyst"]
    assert revoked.status_code == 200
    assert revoked.json()["actor_context"]["roles"] == []
    assert unscoped.status_code == 200
    assert unscoped.json()["actor_context"]["roles"] == []


def test_oidc_preview_reports_group_role_bindings_with_granting_scope():
    """The preview must explain which tenant scope granted each role and must
    list groups that no scope maps, so the mapping is reviewable."""
    response = client.post(
        "/enterprise/auth/oidc-preview",
        json={
            "claims": {
                "email": "analyst@example.com",
                "tenant_id": "demo",
                "groups": ["sdp-analysts", "unknown-group"],
                "exp": int(time()) + 3600,
            },
            "role_map": {"demo": {"sdp-analysts": ["data-analyst"]}},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["group_role_bindings"] == [
        {"group_name": "sdp-analysts", "tenant_scope": "demo", "granted_roles": ["data-analyst"]},
        {"group_name": "unknown-group", "tenant_scope": "", "granted_roles": []},
    ]
    assert body["audit_event_id"]


def test_oidc_preview_rejects_mixed_shape_role_map():
    """A role map that mixes flat and tenant-scoped entries must fail the
    request instead of silently reading a tenant identifier as a group."""
    response = client.post(
        "/enterprise/auth/oidc-preview",
        json={
            "claims": {
                "email": "analyst@example.com",
                "tenant_id": "demo",
                "groups": ["sdp-analysts"],
                "exp": int(time()) + 3600,
            },
            "role_map": {"demo": {"sdp-analysts": ["data-analyst"]}, "sdp-admins": ["admin"]},
        },
    )

    assert response.status_code == 400
    assert "must not mix flat and tenant-scoped" in response.json()["detail"]


def test_oidc_mapping_audit_event_records_bindings_without_claim_leak(tmp_path):
    """Every mapping must persist an audit event carrying the granting scope and
    resolved roles, and must not persist the claim payload or the token."""
    store = sdp_core.SQLiteEvidenceStore(tmp_path / "oidc-evidence.sqlite3")
    previous = app_evidence.configure_evidence_store(store)
    try:
        response = client.post(
            "/enterprise/auth/oidc-preview",
            json={
                "claims": {
                    "email": "analyst@example.com",
                    "tenant_id": "demo",
                    "groups": ["sdp-analysts"],
                    "roles": ["sdp-platform-admins"],
                    "exp": int(time()) + 3600,
                },
                "role_map": {"demo": {"sdp-analysts": ["data-analyst"]}},
            },
        )
        assert response.status_code == 200
    finally:
        app_evidence.configure_evidence_store(previous)

    reopened = sdp_core.SQLiteEvidenceStore(tmp_path / "oidc-evidence.sqlite3")
    events = reopened.list_events(resource="enterprise/auth/oidc", limit=10)
    assert len(events) == 1
    event = events[0]
    assert event.action == "oidc_group_role_mapping"
    assert event.result == "mapped"
    assert event.actor == "analyst@example.com"
    assert event.details["mapping_mode"] == "claim_mapping_preview"
    assert event.details["tenant_id"] == "demo"
    assert event.details["granted_roles"] == ["data-analyst"]
    assert event.details["ignored_role_claims"] == ["sdp-platform-admins"]
    assert event.details["group_bindings"] == [
        {"group_name": "sdp-analysts", "tenant_scope": "demo", "granted_roles": ["data-analyst"]}
    ]
    assert set(event.details) == {
        "mapping_mode",
        "tenant_id",
        "granted_roles",
        "group_bindings",
        "ignored_role_claims",
    }


def test_oidc_jwks_verification_records_group_role_bindings(tmp_path, monkeypatch):
    """The signature-verified path must produce the same auditable binding
    evidence as the preview path, labelled with its own mapping mode."""
    token, jwks = _signed_identity_token(
        issuer="https://idp.example.com/",
        audience="semantic-data-portal",
        kid="buyer-key-2",
    )
    monkeypatch.setenv("SDP_OIDC_ISSUER", "https://idp.example.com/")
    monkeypatch.setenv("SDP_OIDC_AUDIENCE", "semantic-data-portal")
    monkeypatch.setenv("SDP_OIDC_JWKS", json.dumps(jwks))
    monkeypatch.setenv(
        "SDP_OIDC_GROUP_ROLE_MAP",
        json.dumps({"buyer-demo": {"sdp-analysts": ["data-analyst"]}}),
    )

    store = sdp_core.SQLiteEvidenceStore(tmp_path / "oidc-verify-evidence.sqlite3")
    previous = app_evidence.configure_evidence_store(store)
    try:
        response = client.post("/enterprise/auth/oidc-verify", json={"token": token})
        assert response.status_code == 200
    finally:
        app_evidence.configure_evidence_store(previous)

    body = response.json()
    assert body["group_role_bindings"] == [
        {
            "group_name": "sdp-analysts",
            "tenant_scope": "buyer-demo",
            "granted_roles": ["data-analyst"],
        }
    ]
    assert token not in json.dumps(body)

    reopened = sdp_core.SQLiteEvidenceStore(tmp_path / "oidc-verify-evidence.sqlite3")
    events = reopened.list_events(resource="enterprise/auth/oidc", limit=10)
    assert len(events) == 1
    assert events[0].details["mapping_mode"] == "jwks_signature_verification"
    assert token not in json.dumps(events[0].model_dump(), default=str)


def test_oidc_preview_rejects_non_object_claims_and_role_map():
    """Both preview payload shapes must fail as bad requests, so a malformed
    integration cannot reach claim validation with an unusable payload."""
    non_object_claims = client.post("/enterprise/auth/oidc-preview", json={"claims": "analyst"})
    non_object_role_map = client.post(
        "/enterprise/auth/oidc-preview",
        json={
            "claims": {
                "email": "analyst@example.com",
                "tenant_id": "demo",
                "exp": int(time()) + 3600,
            },
            "role_map": [["sdp-analysts", "data-analyst"]],
        },
    )

    assert non_object_claims.status_code == 400
    assert non_object_claims.json()["detail"] == "claims must be an object"
    assert non_object_role_map.status_code == 400
    assert non_object_role_map.json()["detail"] == "role_map must be an object"


def test_oidc_verify_rejects_malformed_payload_fields():
    """A missing token fails before verification, and a body that carries the
    operator-owned trust anchors is refused whatever shape they are in."""
    missing_token = client.post("/enterprise/auth/oidc-verify", json={})
    supplied_jwks = client.post(
        "/enterprise/auth/oidc-verify",
        json={"token": "header.payload.signature", "jwks": "keys"},
    )
    supplied_role_map = client.post(
        "/enterprise/auth/oidc-verify",
        json={"token": "header.payload.signature", "role_map": ["sdp-analysts"]},
    )

    assert missing_token.status_code == 400
    assert missing_token.json()["detail"] == "token is required"
    assert supplied_jwks.status_code == 400
    assert supplied_jwks.json()["detail"].endswith("in the request body: jwks")
    assert supplied_role_map.status_code == 400
    assert supplied_role_map.json()["detail"].endswith("in the request body: role_map")


def _signed_identity_token(*, issuer, audience, kid, claims_extra=None):
    """Mint an RSA-signed identity token and return it with its public JWKS."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(RSAAlgorithm.to_jwk(private_key.public_key()))
    jwk.update({"kid": kid, "alg": "RS256", "use": "sig"})
    claims = {
        "iss": issuer,
        "aud": audience,
        "email": "analyst@example.com",
        "tenant_id": "buyer-demo",
        "groups": ["sdp-analysts"],
        "exp": int(time()) + 3600,
    }
    claims.update(claims_extra or {})
    token = jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": kid})
    return token, {"keys": [jwk]}


def test_oidc_verify_refuses_request_supplied_trust_anchors(monkeypatch):
    """A caller must not be able to name the issuer, audience, signing keys or
    role map that its own token is verified against.

    Without this guard any anonymous caller self-signs a token, posts its own
    public JWKS alongside it, and receives a `jwks_signature_verified` verdict
    plus whatever tenant and roles the token claims - the operator's configured
    identity provider is never consulted.
    """
    monkeypatch.setenv("SDP_OIDC_ISSUER", "https://idp.example.com/")
    monkeypatch.setenv("SDP_OIDC_AUDIENCE", "semantic-data-portal")
    monkeypatch.setenv("SDP_OIDC_JWKS_URL", "https://idp.example.com/.well-known/jwks.json")

    forged_token, forged_jwks = _signed_identity_token(
        issuer="https://attacker.example/",
        audience="anything",
        kid="attacker-key",
        claims_extra={"email": "attacker@evil.test", "tenant_id": "victim-tenant", "groups": ["made-up"]},
    )

    response = client.post(
        "/enterprise/auth/oidc-verify",
        json={
            "token": forged_token,
            "issuer": "https://attacker.example/",
            "audience": "anything",
            "jwks": forged_jwks,
            "role_map": {"made-up": ["platform-admin"]},
        },
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    for field in ("issuer", "audience", "jwks", "role_map"):
        assert field in detail
    assert "actor_context" not in response.json()


def test_oidc_verify_trusts_only_operator_configured_jwks(monkeypatch):
    """With the trust anchors configured by the operator, a token signed by the
    configured key verifies from a body that carries the token alone."""
    token, jwks = _signed_identity_token(
        issuer="https://idp.example.com/",
        audience="semantic-data-portal",
        kid="operator-key-1",
    )
    monkeypatch.setenv("SDP_OIDC_ISSUER", "https://idp.example.com/")
    monkeypatch.setenv("SDP_OIDC_AUDIENCE", "semantic-data-portal")
    monkeypatch.setenv("SDP_OIDC_JWKS", json.dumps(jwks))

    response = client.post("/enterprise/auth/oidc-verify", json={"token": token})

    assert response.status_code == 200
    body = response.json()
    assert body["token_verification"] == "jwks_signature_verified"
    assert body["actor_context"]["subject"] == "analyst@example.com"
    assert body["actor_context"]["tenant_id"] == "buyer-demo"
    assert token not in json.dumps(body)


def test_observability_manifest_does_not_publish_sink_credentials(monkeypatch):
    """`GET /enterprise/observability` is unauthenticated, so the sink endpoint
    it reports must never carry the sink credential."""
    monkeypatch.setenv(
        "SDP_LOG_SINK_URL",
        "https://sdp-ingest:s3cr3t-token@logs.example.net/loki/api/v1/push",
    )

    response = client.get("/enterprise/observability")

    assert response.status_code == 200
    rendered = json.dumps(response.json())
    assert "s3cr3t-token" not in rendered
    assert "sdp-ingest" not in rendered
    assert response.json()["structured_logs"]["sink"]["target"] == "logs.example.net"


def test_catalog_discovery_routes_do_not_publish_governed_dataset_internals():
    """``/browse/{id}/schema`` denies an out-of-tenant caller and audits the denial,
    so the ungated catalog surface must not hand the same caller that dataset's
    column schema with its ``pii`` flags, its source-system connection string, or
    its row-count profile. Before this contract the detail payload was a full
    ``Dataset.model_dump()`` and the browse denial protected nothing.
    """
    denied = client.get(
        "/browse/crm-customer-master/schema",
        params={"user": "nobody", "purpose": "analysis"},
    )
    # 404: an actor with no resolvable tenant must not be able to distinguish a
    # dataset it may not see from one that is not there. The point of this test -
    # that the ungated catalog surface may not hand over what browse refuses -
    # is unchanged.
    assert denied.status_code == 404, denied.text

    detail = client.get("/catalog/datasets/crm-customer-master", params={"user": "analyst"})
    assert detail.status_code == 200
    body = detail.json()
    for governed in ("schema", "source_system", "profile", "tenant_id"):
        assert governed not in body, f"{governed} must stay behind the governed path"
    assert "analytics.dw" not in json.dumps(body)
    # Discovery still describes the shape, without the per-column PII flags.
    assert body["schema_field_count"] == 3

    listed = client.get("/catalog/datasets", params={"user": "analyst"})
    assert listed.status_code == 200
    for row in listed.json():
        for governed in ("schema", "source_system", "profile", "tenant_id"):
            assert governed not in row


def test_catalog_discovery_payload_field_set_is_pinned():
    """A new ``Dataset`` field must be an explicit publish-or-withhold decision,
    not an automatic addition to an unauthenticated payload."""
    body = client.get("/catalog/datasets/crm-customer-master", params={"user": "analyst"}).json()
    assert set(body) == {
        "id",
        "title",
        "description",
        "owner",
        "steward",
        "domain",
        "sensitivity",
        "update_frequency",
        "quality_score",
        "freshness_score",
        "tags",
        "terms",
        "license",
        "related_datasets",
        "distributions",
        "mappings",
        "lineage_inputs",
        "lineage_outputs",
        "completeness_score",
        "recommended_score",
        "version",
        "schema_version",
        "status",
        "created_at",
        "updated_at",
        "schema_field_count",
        "metadata_completeness",
        "metadata_recommendation_score",
        "completeness_badge",
    }


@pytest.mark.parametrize("actor", ["analyst", "guest", "anonymous", None])
@pytest.mark.parametrize("verb", ["publish", "patch", "deprecate"])
def test_catalog_mutation_guard_denies_non_admin_actors(verb: str, actor: str | None):
    """``publish``/``patch``/``deprecate`` authorization was defended by no test.

    ``test_create_requires_admin`` covers only ``create``, and
    ``test_dataset_mutation_policy_and_lifecycle`` drives all three mutation
    verbs as ``admin`` — the happy path only. The guard itself is correct (this
    was verified against the running app before adding the test, for every verb
    and actor class including a payload with no ``actor`` key), so this is
    regression protection, not a fix for a live hole.
    """
    base = app_catalog._DATA["crm-customer-master"]
    app_catalog._DATA["guard-probe"] = base.model_copy(
        update={"id": "guard-probe", "status": "draft", "title": "원래 제목"}
    )

    payload: dict = {} if actor is None else {"actor": actor}
    if verb == "publish":
        response = client.post("/catalog/datasets/guard-probe/publish", json=payload)
    elif verb == "patch":
        response = client.patch("/catalog/datasets/guard-probe", json={**payload, "title": "탈취된 제목"})
    else:
        response = client.post("/catalog/datasets/guard-probe/deprecate", json={**payload, "reason": "probe"})

    assert response.status_code == 403, response.text
    # A guard that denies *after* mutating would be worse than no guard.
    unchanged = app_catalog._DATA["guard-probe"]
    assert unchanged.status == "draft"
    assert unchanged.title == "원래 제목"


@pytest.mark.parametrize("verb", ["publish", "patch", "deprecate"])
def test_catalog_mutation_denial_is_recorded_as_evidence(verb: str):
    """A refused mutation is exactly the event an auditor looks for, so the
    denial must leave a policy decision behind rather than only an HTTP 403."""
    base = app_catalog._DATA["crm-customer-master"]
    app_catalog._DATA["guard-probe"] = base.model_copy(update={"id": "guard-probe", "status": "draft"})

    before = len(app_evidence._POLICY_DECISION_LOG)
    if verb == "publish":
        client.post("/catalog/datasets/guard-probe/publish", json={"actor": "analyst"})
    elif verb == "patch":
        client.patch("/catalog/datasets/guard-probe", json={"actor": "analyst", "title": "x"})
    else:
        client.post("/catalog/datasets/guard-probe/deprecate", json={"actor": "analyst", "reason": "x"})

    recorded = app_evidence._POLICY_DECISION_LOG[before:]
    denials = [d for d in recorded if d.effect != "allow" and d.resource == "guard-probe"]
    assert denials, f"{verb} denial left no policy decision"
    assert denials[-1].action.lower() == verb
    assert denials[-1].subject == "analyst"


def test_create_route_refuses_to_plant_a_dataset_in_another_tenant():
    """End-to-end form of the create-branch tenant hole: a non-platform-admin
    could write into another tenant's catalog namespace."""
    payload = {
        "actor": "data-admin",
        "id": "planted-in-acme",
        "tenant_id": "acme-bank",
        "title": "planted",
        "description": "cross-tenant create probe",
        "owner": "x",
        "steward": "y",
        "domain": "t",
        "source_system": "postgresql://analytics/tmp",
        "sensitivity": "low",
        "update_frequency": "daily",
        "quality_score": 0.8,
        "freshness_score": 0.8,
        "tags": [],
        "terms": [],
        "related_datasets": [],
        "schema": [],
        "distributions": [],
        "mappings": [],
        "profile": {},
    }
    response = client.post("/catalog/datasets", json=payload)
    assert response.status_code == 403, response.text
    assert "planted-in-acme" not in app_catalog._DATA

    # The actor's own tenant still works.
    own = dict(payload, id="own-tenant-ds", tenant_id="demo")
    assert client.post("/catalog/datasets", json=own).status_code == 200


def test_profile_route_refuses_an_out_of_tenant_caller():
    """End-to-end: the profile route no longer serves governed profiling data to a
    caller the governed schema path refuses.

    The refusal is 404, not 403: this is the discovery surface, where the defect
    being fixed is existence disclosure. A 403 would answer "this dataset exists
    and is not yours", which is the disclosure itself. ``/browse`` keeps 403
    because reaching it already requires knowing the dataset.
    """
    base = app_catalog._DATA["crm-customer-master"]
    app_catalog._DATA["external-profile-ds"] = base.model_copy(
        update={"id": "external-profile-ds", "tenant_id": "external"}
    )
    denied = client.get(
        "/catalog/datasets/external-profile-ds/profile", params={"user": "analyst"}
    )
    assert denied.status_code == 404, denied.text
    assert "external-profile-ds" not in denied.text

    allowed = client.get(
        "/catalog/datasets/external-profile-ds/profile", params={"user": "external-analyst"}
    )
    assert allowed.status_code == 200
    assert allowed.json()["row_count"] is not None


def test_ontology_patch_review_requires_an_authorized_steward():
    """A steward sign-off is a governance mutation on a platform sold on
    "policy-before-data-access with auditable evidence", yet the review route
    took the reviewer identity verbatim from the request body with no
    authorization at all. Measured: an anonymous caller approved its own patch
    and stamped ``reviewed_by: biz-admin`` — a record naming a steward who never
    saw it, with zero evidence rows. The structurally identical write
    ``POST /ontology/concepts`` already enforced admin.
    """
    proposal = client.post(
        "/ontology/patches", json={"actor": "analyst", "concept": "고객", "suggestion": "redefine"}
    )
    assert proposal.status_code == 200
    patch_id = proposal.json()["id"]

    anonymous = client.post(
        f"/ontology/patches/{patch_id}/review",
        json={"decision": "approve", "reviewer": "biz-admin", "comment": "lgtm"},
    )
    assert anonymous.status_code == 403, anonymous.text

    non_admin = client.post(
        f"/ontology/patches/{patch_id}/review",
        json={"decision": "approve", "actor": "analyst"},
    )
    assert non_admin.status_code == 403


def test_ontology_patch_review_refuses_a_body_supplied_reviewer():
    """The reviewer is the authorized actor. A caller-chosen ``reviewer`` would
    name somebody who never reviewed it, so the field is refused outright rather
    than silently ignored."""
    proposal = client.post(
        "/ontology/patches", json={"actor": "analyst", "concept": "고객", "suggestion": "redefine"}
    )
    patch_id = proposal.json()["id"]

    spoofed = client.post(
        f"/ontology/patches/{patch_id}/review",
        json={"decision": "approve", "actor": "admin", "reviewer": "biz-admin"},
    )
    assert spoofed.status_code == 400
    assert "reviewer" in spoofed.json()["detail"]

    approved = client.post(
        f"/ontology/patches/{patch_id}/review",
        json={"decision": "approve", "actor": "admin", "comment": "ok"},
    )
    assert approved.status_code == 200
    assert approved.json()["reviewed_by"] == "admin"


def test_ontology_patch_review_records_evidence():
    """A governance sign-off leaves an audit record, like every other mutation."""
    proposal = client.post(
        "/ontology/patches", json={"actor": "analyst", "concept": "고객", "suggestion": "redefine"}
    )
    patch_id = proposal.json()["id"]
    before = len(app_catalog._AUDIT_LOG)
    client.post(
        f"/ontology/patches/{patch_id}/review",
        json={"decision": "reject", "actor": "admin", "comment": "no"},
    )
    recorded = app_catalog._AUDIT_LOG[before:]
    assert any(event.action == "ontology.patch_review" for event in recorded), recorded


def test_rbac_matrix_publishes_the_seeded_subject_role_bundling():
    """The matrix is per-*role* and internally correct: ``platform-admin`` is
    honestly documented as ``all_tenants`` with every action. What it could not
    show is that the demo seed *bundles* that role into two subjects whose names
    imply a narrower purpose:

        admin     roles=['admin', 'data-analyst', 'platform-admin']  crosses tenants
        security  roles=['security', 'platform-admin']               crosses tenants

    So a buyer reads ``security -> platform_evidence_only`` and then measures the
    ``security`` subject previewing (200) and deprecating (200) another tenant's
    ``critical`` dataset. Both are true at once — the subject holds a second role —
    but nothing on the page said so. Publishing the bundling closes the gap
    without deciding whether ``security`` *should* hold ``platform-admin``.
    """
    response = client.get("/enterprise/rbac-matrix")
    assert response.status_code == 200
    body = response.json()

    bindings = {entry["subject"]: entry for entry in body["seeded_subject_bindings"]}
    assert bindings["security"]["roles"] == ["security", "platform-admin"]
    assert bindings["security"]["crosses_tenant_boundary"] is True
    assert bindings["admin"]["crosses_tenant_boundary"] is True
    assert bindings["analyst"]["crosses_tenant_boundary"] is False

    # Every subject the manifest reports as crossing really does hold the role
    # whose published row grants it.
    crossing = {e["subject"] for e in body["seeded_subject_bindings"] if e["crosses_tenant_boundary"]}
    for subject in crossing:
        assert "platform-admin" in app_authz.resolve_actor_context(subject).roles


def test_rbac_matrix_scope_claims_match_the_seeded_grants():
    """A per-role scope claim must not be narrower than what a subject holding
    that role actually gets. This is the mechanical guard: if a future seed gives
    ``platform-admin`` to another subject, or a row's scope is tightened without
    changing the grants, this fails rather than shipping a false claim.
    """
    body = client.get("/enterprise/rbac-matrix").json()
    rows = {row["role"]: row for row in body["roles"]}
    assert rows["platform-admin"]["tenant_scope"] == "all_tenants"

    for entry in body["seeded_subject_bindings"]:
        narrow = [
            rows[role]["tenant_scope"]
            for role in entry["roles"]
            if role in rows and rows[role]["tenant_scope"] != "all_tenants"
        ]
        if entry["crosses_tenant_boundary"]:
            # The subject crosses tenants, so at least one of its rows must say so.
            assert any(
                rows[role]["tenant_scope"] == "all_tenants"
                for role in entry["roles"]
                if role in rows
            ), f"{entry['subject']} crosses tenants but no row claims all_tenants: {narrow}"


def test_published_test_evidence_references_all_exist():
    """Manifests cite ``tests/<file>.py::test_name`` strings as proof, and
    ``GET /enterprise/rbac-matrix`` served ``tests/test_api.py::test_catalog_mutation_flow``
    — a test that does not exist anywhere in the repository — under a control whose
    release criterion is "Roles, actions, and denied cases are documented and
    test-covered". A dangling proof reference is worse than none: it reads as
    evidence.
    """
    import re

    root = Path(__file__).resolve().parents[1]
    defined = set()
    for path in (root / "tests").rglob("*.py"):
        for match in re.finditer(r"^def (test_\w+)", path.read_text(encoding="utf-8"), re.M):
            defined.add(f"tests/{path.relative_to(root / 'tests')}::{match.group(1)}")
            defined.add(match.group(1))

    referenced = set()
    for path in list((root / "src").rglob("*.py")):
        for match in re.finditer(r"tests/[\w/]+\.py::(test_\w+)", path.read_text(encoding="utf-8")):
            referenced.add((str(path.relative_to(root)), match.group(0), match.group(1)))

    dangling = [(src, ref) for src, ref, name in referenced if name not in defined]
    assert not dangling, f"published evidence references no such test: {dangling}"
