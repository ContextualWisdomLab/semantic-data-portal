"""Unit tests for the graph engine on the in-memory backend (no database).

Covers ingestion (nodes/edges/concepts), graph traversal, semantic-search
ranking, /healthz readiness, and the config-from-KV loading contract.
"""

from fastapi.testclient import TestClient

from sdp import api as api_module
from sdp import config as config_module
from sdp.api import app
from sdp.embeddings import cosine_similarity, embed_text
from sdp.graph_store import InMemoryGraphStore
from sdp.seed import seed_store


client = TestClient(app)


# --- readiness ---------------------------------------------------------------


def test_healthz_reports_ready_and_seeded_stats():
    response = client.get("/healthz")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["store"]["ready"] is True
    # At least the 5 seeded ontology concepts (a shared persistent backend may
    # have accumulated more from other tests; the in-memory default has exactly 5).
    assert body["stats"]["concepts"] >= 5
    assert body["stats"]["nodes"] >= 5
    assert body["stats"]["embeddings"] == body["stats"]["nodes"]


def test_healthz_logs_backend_exception_without_exposing_details(monkeypatch, caplog):
    class FailingStore:
        def readiness(self):
            raise RuntimeError("postgresql://user:secret@internal.example/private")

    monkeypatch.setattr(api_module, "get_store", lambda: FailingStore())

    with caplog.at_level("ERROR"):
        response = client.get("/healthz")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "unavailable"
    assert body["store"] == {
        "ready": False,
        "backend": "unavailable",
        "error": "backend unreachable",
    }
    assert body["stats"] == {}
    assert "secret" not in response.text
    assert "internal.example" not in response.text
    assert "graph health probe failed" in caplog.text
    assert "internal.example" in caplog.text


def test_health_still_present():
    assert client.get("/health").json()["status"] == "ok"


# --- ingestion ---------------------------------------------------------------


def test_ingest_node_edge_and_fetch():
    node = client.post(
        "/graph/nodes",
        json={"node_id": "svc-A", "kind": "service", "label": "Billing", "text": "billing invoices", "actor": "admin"},
    )
    assert node.status_code == 200
    assert node.json()["node"]["node_id"] == "svc-A"

    fetched = client.get("/graph/nodes/svc-A")
    assert fetched.status_code == 200
    assert fetched.json()["kind"] == "service"

    edge = client.post(
        "/graph/edges",
        json={"edge_type": "depends_on", "source_id": "svc-A", "target_id": "고객", "actor": "admin"},
    )
    assert edge.status_code == 200
    assert edge.json()["edge"]["target_id"] == "고객"


def test_ingest_concept_creates_traversable_node():
    resp = client.post(
        "/ontology/concepts",
        json={
            "concept": "구독",
            "definition": "정기 결제 기반 서비스 이용 관계",
            "aliases": ["subscription", "정기결제"],
            "related": ["매출"],
            "multilingual": ["subscription"],
            "actor": "admin",
        },
    )
    assert resp.status_code == 200
    graph = client.get("/ontology/term/subscription/graph")
    assert graph.status_code == 200
    assert graph.json()["canonical"] == "구독"
    assert "매출" in graph.json()["related"]


def test_missing_node_returns_404():
    assert client.get("/graph/nodes/does-not-exist").status_code == 404


# --- traversal ---------------------------------------------------------------


def test_graph_query_traverses_concept_hierarchy():
    resp = client.post(
        "/graph/query",
        json={"start_id": "고객", "direction": "both", "max_depth": 1, "actor": "analyst"},
    )
    assert resp.status_code == 200
    body = resp.json()
    node_ids = {n["node_id"] for n in body["nodes"]}
    # broader/narrower neighbours of 고객
    assert "활성 고객" in node_ids
    assert "이탈 고객" in node_ids
    edge_types = {e["edge_type"] for e in body["edges"]}
    assert "narrower" in edge_types


def test_graph_query_edge_type_filter():
    resp = client.post(
        "/graph/query",
        json={"start_id": "고객", "edge_types": ["narrower"], "direction": "out", "max_depth": 1, "actor": "analyst"},
    )
    assert resp.status_code == 200
    for edge in resp.json()["edges"]:
        assert edge["edge_type"] == "narrower"


def test_graph_query_unknown_start_is_404():
    resp = client.post("/graph/query", json={"start_id": "nope", "max_depth": 1, "actor": "analyst"})
    assert resp.status_code == 404


# --- semantic search ---------------------------------------------------------


def test_semantic_search_ranks_churn_concept_first():
    resp = client.post(
        "/search/semantic", json={"query": "churn 이탈한 고객", "kind": "concept", "limit": 3, "actor": "analyst"}
    )
    assert resp.status_code == 200
    results = resp.json()["results"]
    assert results
    assert results[0]["node_id"] in {"이탈", "이탈 고객"}
    # scores are sorted descending
    scores = [r["score"] for r in results]
    assert scores == sorted(scores, reverse=True)


def test_semantic_search_kind_filter_only_returns_datasets():
    resp = client.post(
        "/search/semantic", json={"query": "고객 프로필 데이터", "kind": "dataset", "limit": 5, "actor": "analyst"}
    )
    assert resp.status_code == 200
    results = resp.json()["results"]
    assert results
    assert all(r["kind"] == "dataset" for r in results)


def test_embedding_similarity_is_meaningful():
    a = embed_text("고객 이탈 churn")
    b = embed_text("이탈한 고객 churned customer")
    c = embed_text("매출 revenue sales 판매")
    assert cosine_similarity(a, b) > cosine_similarity(a, c)


# --- seed idempotency --------------------------------------------------------


def test_seed_is_idempotent():
    store = InMemoryGraphStore()
    first = seed_store(store)
    second = seed_store(store)
    assert first == second  # re-running seed does not duplicate nodes/edges


# --- config from KV ----------------------------------------------------------


def test_app_config_defaults_tighten_cors():
    cfg = config_module.get_app_config()
    assert "*" not in cfg.cors_allow_origins
    assert cfg.cors_allow_origins  # non-empty allowlist
    assert cfg.embedding_dimension == 128


def test_config_loads_from_kv_mapping(monkeypatch):
    # Simulate the KV (config_entries) returning an override; app config must
    # reflect it without ever reading os.getenv for the value itself.
    override = {
        "cors_allow_origins": ["https://portal.example.org"],
        "embedding_dimension": 128,
        "orchestrator_base_url": "https://orchestrator.example",
        "semantic_model": "semantic-model-v1",
        "embedding_model": "embedding-model-v1",
    }
    monkeypatch.setattr(config_module, "_load_from_kv_table", lambda bootstrap: override)
    config_module.reset_config_cache()
    try:
        cfg = config_module.get_app_config()
        assert cfg.cors_allow_origins == ["https://portal.example.org"]
        assert cfg.orchestrator_base_url == "https://orchestrator.example"
        assert cfg.semantic_model == "semantic-model-v1"
        assert cfg.embedding_model == "embedding-model-v1"
        assert cfg.source == "config_entries"
    finally:
        config_module.reset_config_cache()
