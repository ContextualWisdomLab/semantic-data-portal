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


def test_preview_policy_denies_missing_dataset():
    response = client.post("/browse/unknown/preview", json={"user": "user1", "purpose": "analysis"})
    assert response.status_code == 404


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
    }
    response = client.post("/llm/draft-query", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert "query" in body
    assert "policy_decision_id" in body
    assert body["policy_decision_id"] == body["policy_decision"]["decision_id"]
    assert "LIMIT 50" in body["query"]


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
        "schema": [],
        "distributions": [],
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
