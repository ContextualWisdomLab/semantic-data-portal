import json
from copy import deepcopy
from pathlib import Path
from time import time

import pytest
from fastapi.testclient import TestClient

import sdp.catalog as app_catalog
import sdp.domain as app_domain
import sdp.evidence as app_evidence
import sdp.observability as app_observability
import sdp_core
from sdp.api import app
from sdp.connectors import get_source_connector
from sdp.demo_smoke import smoke_summary
from sdp.evidence import configure_evidence_store, list_persisted_audit_events, list_persisted_policy_decisions
from sdp.policy import evaluate


client = TestClient(app)


@pytest.fixture(autouse=True)
def isolate_in_memory_app_state():
    data = {dataset_id: dataset.model_copy(deep=True) for dataset_id, dataset in app_catalog._DATA.items()}
    audit_log = list(app_catalog._AUDIT_LOG)
    schema_history = deepcopy(app_catalog._SCHEMA_HISTORY)
    policy_log = list(app_evidence._POLICY_DECISION_LOG)
    request_observations = app_observability.list_request_observations()
    export_errors = app_observability.list_observability_export_errors()
    yield
    app_catalog._DATA.clear()
    app_catalog._DATA.update(data)
    app_catalog._AUDIT_LOG[:] = audit_log
    app_catalog._SCHEMA_HISTORY.clear()
    app_catalog._SCHEMA_HISTORY.update(schema_history)
    app_evidence._POLICY_DECISION_LOG[:] = policy_log
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
    catalog_ids = {dataset["id"] for dataset in client.get("/catalog/datasets").json()}

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
    response = client.get("/catalog/datasets/crm-customer-master/semantic-validation")
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
    proposed = client.post(
        "/ontology/patches",
        json={
            "concept": "고객",
            "suggestion": "VIP 고객 세그먼트를 구매자 데모 glossary 후보로 추가",
            "requestor": "governance-analyst",
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
    assert body["planned_controls"] >= 1
    assert controls["tenant_authorization"]["status"] == "implemented"
    assert controls["local_evidence_retention"]["status"] == "implemented"
    assert controls["sso_oidc_adapter"]["status"] == "planned"
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
    assert any(item["request_id"] == "buyer-trace-001" for item in manifest["recent_requests"])

    metrics = client.get("/metrics").text
    assert "sdp_request_observations_total" in metrics


def test_enterprise_production_readiness_tracks_paid_pilot_integrations():
    response = client.get("/enterprise/production-readiness")
    assert response.status_code == 200

    body = response.json()
    assert body["valuation_target_krw"] == 2_000_000_000
    assert body["current_stage"] == "pilot_candidate"
    assert body["demo_release_ready"] is True
    assert body["paid_pilot_ready"] is False

    integrations = {item["id"]: item for item in body["integrations"]}
    assert integrations["postgres_evidence_store"]["status"] == "planned"
    assert "SDP_DATABASE_URL" in integrations["postgres_evidence_store"]["required_environment"]
    assert "SDP_SQLITE_PATH" in integrations["postgres_evidence_store"]["current_evidence"]
    assert any("policy decisions and audit events" in item for item in integrations["postgres_evidence_store"]["acceptance_criteria"])

    assert integrations["oidc_jwks_verification"]["status"] == "planned"
    assert "SDP_OIDC_JWKS_URL" in integrations["oidc_jwks_verification"]["required_environment"]
    assert any("direct role claims" in item for item in integrations["oidc_jwks_verification"]["acceptance_criteria"])

    assert integrations["connector_credential_vault"]["status"] == "implemented"
    assert "SDP_CONNECTOR_SECRET_REF_PREFIX" in integrations["connector_credential_vault"]["required_environment"]
    assert any("raw connector credentials" in item for item in integrations["connector_credential_vault"]["acceptance_criteria"])

    assert integrations["request_observability_export"]["status"] == "implemented"
    assert "/enterprise/observability" in integrations["request_observability_export"]["current_evidence"]

    assert set(body["paid_pilot_blockers"]) >= {
        "postgres_evidence_store",
        "oidc_jwks_verification",
    }
    assert "connector_credential_vault" not in body["paid_pilot_blockers"]
    assert "request_observability_export" not in body["paid_pilot_blockers"]
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


def test_deployment_template_files_define_local_demo_runtime():
    project_root = Path(__file__).resolve().parents[1]
    dockerfile = (project_root / "Dockerfile").read_text()
    compose = (project_root / "docker-compose.yml").read_text()

    assert "uvicorn" in dockerfile
    assert "SDP_SQLITE_PATH=/data/sdp-evidence.sqlite3" in dockerfile
    assert "semantic-data-portal" in compose
    assert "8000:8000" in compose
    assert "sdp-evidence" in compose


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
    assert body["production_paid_pilot_ready"] is False
    assert body["production_paid_pilot_blockers"] == 2
    assert body["saleability_gates"]["metadata_validation_pass_rate"] == "pass"
    assert body["saleability_gates"]["shacl_validation_pass_rate"] == "pass"
    assert body["saleability_gates"]["steward_review_queue"] == "pass"
    assert body["saleability_gates"]["ontology_mapping_coverage"] == "pass"
    assert body["saleability_gates"]["production_demo_release"] == "pass"
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
    previous = configure_evidence_store(store)
    try:
        decision = evaluate(subject="analyst", resource="crm-customer-master", action="preview", purpose="analysis")
        preview = client.post(
            "/browse/crm-customer-master/preview",
            json={"user": "analyst", "purpose": "analysis", "limit": 1},
        )
        assert preview.status_code == 200
    finally:
        configure_evidence_store(previous)

    reopened = sdp_core.SQLiteEvidenceStore(tmp_path / "evidence.sqlite3")
    assert reopened.get_decision(decision.decision_id) == decision
    persisted_decisions = reopened.list_decisions(resource="crm-customer-master", limit=10)
    assert any(row.decision_id == decision.decision_id for row in persisted_decisions)
    persisted_events = reopened.list_events(resource="crm-customer-master", limit=10)
    assert any(event.action == "browse.preview" and event.decision_id for event in persisted_events)


def test_persisted_audit_list_uses_configured_store(tmp_path):
    store = sdp_core.SQLiteEvidenceStore(tmp_path / "audit.sqlite3")
    previous = configure_evidence_store(store)
    try:
        response = client.post(
            "/browse/crm-customer-master/preview",
            json={"user": "analyst", "purpose": "analysis", "limit": 1},
        )
        assert response.status_code == 200
        events = list_persisted_audit_events(resource="crm-customer-master", limit=5)
        assert any(event.action == "browse.preview" for event in events)
        decisions = list_persisted_policy_decisions(resource="crm-customer-master", limit=5)
        assert any(decision.action == "preview" for decision in decisions)
    finally:
        configure_evidence_store(previous)


def test_audit_events_endpoint_reads_configured_evidence_store_after_memory_clear(tmp_path):
    store = sdp_core.SQLiteEvidenceStore(tmp_path / "audit-endpoint.sqlite3")
    previous = configure_evidence_store(store)
    try:
        response = client.post(
            "/browse/crm-customer-master/preview",
            json={"user": "analyst", "purpose": "analysis", "limit": 1},
        )
        assert response.status_code == 200

        app_catalog._AUDIT_LOG.clear()

        events_response = client.get("/audit/events", params={"resource": "crm-customer-master", "limit": 10})
        assert events_response.status_code == 200
        assert any(event["action"] == "browse.preview" for event in events_response.json())
    finally:
        configure_evidence_store(previous)


def test_policy_decision_store_does_not_duplicate_configured_store_in_memory(tmp_path):
    store = sdp_core.SQLiteEvidenceStore(tmp_path / "policy-memory.sqlite3")
    previous_log = list(app_evidence._POLICY_DECISION_LOG)
    previous = configure_evidence_store(store)
    try:
        decision = evaluate(subject="analyst", resource="crm-customer-master", action="preview", purpose="analysis")
    finally:
        configure_evidence_store(previous)

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

    response = client.get("/policy/decisions", params={"resource": "crm-customer-master", "limit": 10})
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
    assert summary["production_paid_pilot_ready"] is False
    assert summary["production_paid_pilot_blockers"] == 2
    assert summary["ready"] is True


def test_enterprise_connector_probe_exposes_demo_evidence():
    response = client.get(
        "/enterprise/connectors/sql_connector/probe",
        params={"dataset_id": "crm-customer-master"},
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
        params={"dataset_id": "semantic-glossary"},
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
        params={"dataset_id": "crm-event"},
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
        params={"dataset_id": "marketing-campaign"},
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
        params={"dataset_id": "marketing-campaign"},
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
        params={"dataset_id": "crm-event"},
    )
    assert unsupported.status_code == 400

    missing_dataset = client.get(
        "/enterprise/connectors/sql_connector/probe",
        params={"dataset_id": "unknown"},
    )
    assert missing_dataset.status_code == 404


def test_catalog_search_and_detail():
    response = client.get("/catalog/search", params={"q": "활성 고객"})
    assert response.status_code == 200
    body = response.json()
    assert body["count"] >= 1
    assert "id" in body["items"][0]

    detail = client.get("/catalog/datasets/crm-customer-master")
    assert detail.status_code == 200
    detail_body = detail.json()
    assert detail_body["id"] == "crm-customer-master"
    assert detail_body["status"] in {"published", "registered", "deprecated"}


def test_catalog_search_filter_by_quality():
    response = client.get("/catalog/search", params={"q": "고객", "min_quality": 0.9})
    assert response.status_code == 200
    assert all(item["quality"] >= 0.9 for item in response.json()["items"])


def test_catalog_dataset_detail_exposes_recommendation_score():
    response = client.get("/catalog/datasets/crm-customer-master")
    assert response.status_code == 200
    body = response.json()
    assert "metadata_recommendation_score" in body
    assert body["metadata_recommendation_score"] >= 0


def test_catalog_facets_and_audit_events():
    response = client.get("/catalog/facets", params={"field": "sensitivity"})
    assert response.status_code == 200
    assert response.json()["field"] == "sensitivity"

    events = client.get("/audit/events")
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
    response = client.get("/catalog/datasets/crm-customer-master/join-candidates")
    assert response.status_code == 200
    body = response.json()
    assert body["dataset_id"] == "crm-customer-master"
    assert "join_candidates" in body
    assert any(item["dataset_id"] == "crm-event" for item in body["join_candidates"])


def test_dataset_profile_endpoint():
    response = client.get("/catalog/datasets/crm-customer-master/profile")
    assert response.status_code == 200
    body = response.json()
    assert body["dataset_id"] == "crm-customer-master"
    assert "schema_profile" in body
    assert body["schema_profile"]


def test_preview_policy_denies_missing_dataset():
    response = client.post("/browse/unknown/preview", json={"user": "user1", "purpose": "analysis"})
    assert response.status_code == 404

    events = client.get("/audit/events", params={"resource": "unknown"})
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
    response = client.post(
        "/browse/crm-customer-master/preview",
        json={"user": "guest", "purpose": "analysis"},
    )
    assert response.status_code == 403


def test_audit_event_includes_policy_decision_id_for_preview():
    response = client.post(
        "/browse/crm-event/preview",
        json={"user": "analyst", "purpose": "analysis", "limit": 1},
    )
    assert response.status_code == 200
    body = response.json()
    decision_id = body["policy_decision_id"]

    events = client.get("/audit/events", params={"resource": "crm-event"})
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
    versions = client.get("/catalog/datasets/crm-event/schema-versions")
    assert versions.status_code == 200
    payload = versions.json()
    assert "versions" in payload
    assert payload["versions"]

    history = client.get("/catalog/datasets/crm-event/schema-history")
    assert history.status_code == 200
    history_payload = history.json()
    assert history_payload["history"]
    first_version = history_payload["history"][0]["schema_version"]
    last_version = history_payload["history"][-1]["schema_version"]

    diff = client.get(
        "/catalog/datasets/crm-event/schema-diff",
        params={"from_version": first_version, "to_version": last_version},
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

    lineage = client.get("/catalog/datasets/temp-dataset/lineage")
    assert lineage.status_code == 200
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

    denied = client.post(
        "/browse/external-tenant-dataset/preview",
        json={"user": "analyst", "purpose": "analysis", "limit": 1},
    )
    assert denied.status_code == 403
    assert "tenant boundary denied" in denied.json()["detail"]

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

    review = client.post(
        f"/ontology/patches/{patch['id']}/review",
        json={"decision": "approve", "reviewer": "admin", "comment": "적절한 제안"},
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

    events = client.get("/audit/events", params={"resource": "crm-event"})
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

    events = client.get("/audit/events", params={"resource": "crm-event"})
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
    assert response.status_code == 403

    events = client.get("/audit/events", params={"resource": "crm-event"})
    assert events.status_code == 200
    assert any(
        event["action"] == "browse.query"
        and event["result"] == "denied"
        and event["actor"] == "guest"
        for event in events.json()
    )
