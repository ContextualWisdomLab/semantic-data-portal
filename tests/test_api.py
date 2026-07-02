from fastapi.testclient import TestClient

from sdp.api import app


client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


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
            "query": "SELECT count(*) AS active_count FROM event",
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


def test_browse_query_denied_without_user():
    response = client.post(
        "/browse/query",
        json={
            "user": "guest",
            "purpose": "analysis",
            "dataset_ids": ["crm-event"],
            "language": "SQL",
            "query": "SELECT count(*) AS active_count FROM event",
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
