"""Integration tests against a live Postgres with Apache AGE + pgvector.

Skipped unless ``SDP_DATABASE_DSN`` points at a reachable database with the
``age`` and ``vector`` extensions. Run locally with::

    docker compose up --build graph_db
    SDP_DATABASE_DSN=postgresql+psycopg://sdp:sdp@localhost:5432/sdp \
        python -m pytest tests/test_integration_age.py -m integration
"""

import os

import pytest

pytestmark = pytest.mark.integration

DSN = os.environ.get("SDP_DATABASE_DSN")


@pytest.fixture(scope="module")
def seeded_store():
    if not DSN:
        pytest.skip("SDP_DATABASE_DSN not set")
    try:
        from sqlalchemy import create_engine, text

        with create_engine(DSN).connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        pytest.skip(f"database not reachable: {exc}")

    from migrations.run_migrations import apply_migrations, load_config
    from sdp.graph_store import PostgresGraphStore
    from sdp.seed import seed_store

    # Migrations install the age + vector extensions and create the schema.
    apply_migrations(DSN)
    load_config(DSN)
    store = PostgresGraphStore(DSN)
    readiness = store.readiness()
    if not readiness.get("ready"):
        pytest.skip(f"database not ready (AGE/pgvector missing): {readiness}")
    seed_store(store)
    return store


def test_postgres_readiness(seeded_store):
    readiness = seeded_store.readiness()
    assert readiness["database"] is True
    assert readiness["age"] is True
    assert readiness["pgvector"] is True
    assert readiness["backend"] == "postgres_age"


def test_postgres_cypher_traversal(seeded_store):
    result = seeded_store.traverse("고객", direction="both", max_depth=2)
    assert result["backend"] == "postgres_age"
    node_ids = {n["node_id"] for n in result["nodes"]}
    assert "활성 고객" in node_ids


def test_postgres_pgvector_semantic_search(seeded_store):
    results = seeded_store.semantic_search("churn 이탈한 고객", kind="concept", limit=3)
    assert results
    assert results[0]["node_id"] in {"이탈", "이탈 고객"}


def test_postgres_concept_graph(seeded_store):
    graph = seeded_store.concept_graph("active customer")
    assert graph["canonical"] == "활성 고객"
    assert graph["broader"] == "고객"


def test_postgres_traversal_edge_type_filter(seeded_store):
    result = seeded_store.traverse("고객", edge_types=["narrower"], direction="out", max_depth=1)
    assert result["edges"]
    assert all(e["edge_type"] == "narrower" for e in result["edges"])


def test_postgres_unknown_start_raises(seeded_store):
    import pytest as _pytest

    with _pytest.raises(KeyError):
        seeded_store.traverse("no-such-node", max_depth=1)
