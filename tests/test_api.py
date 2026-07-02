from fastapi.testclient import TestClient

import sdp.domain as app_domain
import sdp_core
from sdp.api import app
from sdp.connectors import get_source_connector
from sdp.demo_smoke import smoke_summary
from sdp.evidence import configure_evidence_store, list_persisted_audit_events, list_persisted_policy_decisions
from sdp.policy import evaluate


client = TestClient(app)


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


def test_enterprise_controls_expose_feature_gate_manifest():
    response = client.get("/enterprise/controls")
    assert response.status_code == 200

    body = response.json()
    controls = {control["id"]: control for control in body["controls"]}

    assert body["feature_gate"] == "sdp_enterprise"
    assert body["implemented_controls"] >= 2
    assert body["planned_controls"] >= 3
    assert controls["tenant_authorization"]["status"] == "implemented"
    assert controls["local_evidence_retention"]["status"] == "implemented"
    assert controls["sso_oidc_adapter"]["status"] == "planned"
    assert controls["rbac_matrix"]["feature_gate"] == "sdp_enterprise"
    assert "GET /enterprise/controls" in controls["rbac_matrix"]["evidence"]
    assert controls["central_workflow_due_diligence"]["status"] == "external"


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
    assert body["ontology_mapping_coverage"] >= 0.7
    assert body["policy_decision_count"] >= 1
    assert body["audit_event_count"] >= 1
    assert body["saleability_gates"]["metadata_validation_pass_rate"] == "pass"
    assert body["saleability_gates"]["ontology_mapping_coverage"] == "pass"
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
    assert summary["ontology_mapping_coverage"] >= 0.7
    assert summary["primary_kpis"] >= 3
    assert summary["guardrail_kpis"] >= 3
    assert summary["enterprise_controls"] >= 6
    assert summary["implemented_enterprise_controls"] >= 2
    assert summary["connector_probe_status"] == "ready_for_demo"
    assert summary["connector_probe_domain"] == "customer_intelligence"
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


def test_sql_connector_adapter_implements_source_connector_contract():
    connector = get_source_connector("sql_connector")
    schema = connector.inspect_schema("crm-customer-master")
    rows = connector.preview("crm-customer-master", limit=1, offset=0)

    assert connector.connector_id == "sql_connector"
    assert schema["source_system"].startswith("postgresql://")
    assert schema["columns"]
    assert rows
    assert rows[0]["customer_email"] == "***"


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
