"""Security tests for the graph engine (no database required).

Proves, without a live Postgres, that:

* user values are passed to Apache AGE as bound agtype **parameters** and never
  interpolated into the cypher/SQL text -- the proven ``$$`` dollar-quote
  breakout payload is neutralized (no stacked ``DROP TABLE`` reaches the text);
* the relationship-type identifier allowlist rejects non-identifier labels
  (both backends, for parity);
* raw openCypher is no longer part of the traversal request surface;
* graph ingest/query/semantic-search endpoints enforce policy authz -- an
  unauthenticated (anonymous) subject is refused, writes require admin;
* ``build_store`` fails loud on a configured-but-unavailable database instead of
  silently downgrading to the in-memory backend.

The live-AGE end-to-end equivalents (an actual ``DROP TABLE`` attempt that does
nothing) live in ``tests/test_integration_age.py``.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from sdp import config as config_module
from sdp import graph_store as gs
from sdp.api import app
from sdp.config import AppConfig, override_app_config
from sdp.graph_store import (
    InMemoryGraphStore,
    PostgresGraphStore,
    _relationship_label,
    build_store,
)

client = TestClient(app)

# The exact stacked-SQL breakout payload proven in the adversarial review: it
# tries to close the ``$$`` dollar-quote body, terminate the cypher(), and run a
# second statement dropping a table.
INJECTION = "x$$)AS(v agtype); DROP TABLE graph_nodes; --"


# --- fake DB plumbing so the Postgres backend can be exercised with no server --


class _FakeResult:
    def __init__(self, rows=None, row=None, scalar=None):
        self._rows = rows if rows is not None else []
        self._row = row
        self._scalar = scalar

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._row

    def scalar(self):
        return self._scalar


class _RecordingCursor:
    """Render psycopg composed SQL and record the real driver parameters."""

    def __init__(self, owner):
        self._owner = owner

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, statement, params=None):
        self._owner.driver_calls.append((statement.as_string(None), params or ()))

    def fetchall(self):
        return []


class _RecordingDriverConnection:
    def __init__(self, owner):
        self._owner = owner

    def cursor(self):
        return _RecordingCursor(self._owner)


class _ConnectionFacade:
    def __init__(self, owner):
        self.driver_connection = _RecordingDriverConnection(owner)


class _RecordingConn:
    """Records every statement so tests can assert what reached the DB text."""

    def __init__(self, node_row=None):
        self.driver_calls: list[tuple[str, tuple]] = []
        self.execute_calls: list[tuple[str, dict]] = []
        self._node_row = node_row
        self.connection = _ConnectionFacade(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, clause, params=None):
        self.execute_calls.append((str(clause), params))
        return _FakeResult(row=self._node_row, rows=[])

class _FakeEngine:
    def __init__(self, conn):
        self._conn = conn

    def begin(self):
        return self._conn

    def connect(self):
        return self._conn


def _pg_store_with(conn) -> PostgresGraphStore:
    store = PostgresGraphStore("postgresql+psycopg://u:p@localhost/db")
    store._engine = _FakeEngine(conn)
    return store


def _cypher_statements(conn: _RecordingConn) -> list[str]:
    return [stmt for stmt, _ in conn.driver_calls if "cypher(" in stmt]


# --- backend contract ---------------------------------------------------------


def test_graph_store_contract_is_abstract():
    with pytest.raises(TypeError, match="abstract class GraphStore"):
        gs.GraphStore()


# --- injection: values are bound as parameters, never interpolated -----------


def test_upsert_node_binds_payload_as_agtype_param_not_text():
    conn = _RecordingConn()
    store = _pg_store_with(conn)

    store.upsert_node(INJECTION, INJECTION, label=INJECTION, text="node")

    cyphers = _cypher_statements(conn)
    assert cyphers, "a cypher statement should have been issued"
    for stmt, params in [(s, p) for s, p in conn.driver_calls if "cypher(" in s]:
        # the payload never appears in the SQL/cypher text ...
        assert INJECTION not in stmt
        assert "DROP TABLE" not in stmt
        # ... the fixed ``$$`` wrapper is gone (random per-call dollar tag) ...
        assert "$$" not in stmt
        # ... and the values are carried in the bound agtype JSON parameter.
        assert params and INJECTION in params[0]
        bound = json.loads(params[0])
        assert bound["node_id"] == INJECTION


def test_upsert_edge_binds_endpoints_as_params():
    conn = _RecordingConn()
    store = _pg_store_with(conn)

    store.upsert_edge("related", INJECTION, "고객")

    for stmt, params in [(s, p) for s, p in conn.driver_calls if "cypher(" in s]:
        assert INJECTION not in stmt
        assert "DROP TABLE" not in stmt
        bound = json.loads(params[0])
        assert bound["source_id"] == INJECTION
        assert bound["target_id"] == "고객"


def test_traverse_binds_start_id_as_param():
    node_row = (INJECTION, "concept", INJECTION, "{}")
    conn = _RecordingConn(node_row=node_row)
    store = _pg_store_with(conn)

    result = store.traverse(INJECTION, direction="both", max_depth=2)
    assert result["backend"] == "postgres_age"

    match_stmts = [
        (s, p) for s, p in conn.driver_calls if "cypher(" in s and "MATCH" in s
    ]
    assert match_stmts
    for stmt, params in match_stmts:
        assert INJECTION not in stmt
        assert "$$" not in stmt
        assert json.loads(params[0])["start_id"] == INJECTION


def test_cypher_quotes_graph_name_and_body_with_psycopg_composition():
    conn = _RecordingConn()
    store = _pg_store_with(conn)
    store.graph_name = "graph'); DROP TABLE graph_nodes; --"

    store._cypher(conn, "RETURN 'quoted'", "v agtype", {"a": 1})

    statement, params = conn.driver_calls[0]
    assert "cypher('graph''); DROP TABLE graph_nodes; --'" in statement
    assert "'RETURN ''quoted'''" in statement
    assert json.loads(params[0]) == {"a": 1}


def test_cypher_rejects_unknown_result_declaration():
    conn = _RecordingConn()
    store = _pg_store_with(conn)

    with pytest.raises(ValueError, match="unsupported AGE result declaration"):
        store._cypher(conn, "RETURN 1", INJECTION, {})

    assert conn.driver_calls == []


# --- identifier allowlist -----------------------------------------------------


@pytest.mark.parametrize("good", ["broader", "has_column", "related_dataset", "_x"])
def test_relationship_label_accepts_identifiers(good):
    assert _relationship_label(good) == good.upper()


@pytest.mark.parametrize(
    "bad",
    [
        INJECTION,
        "bad-type",
        "1leading",
        "has column",
        "x]->(n) DELETE n //",
        "",
    ],
)
def test_relationship_label_rejects_non_identifiers(bad):
    with pytest.raises(ValueError):
        _relationship_label(bad)


def test_in_memory_edge_rejects_bad_label_for_parity():
    store = InMemoryGraphStore()
    store.upsert_node("a", "concept")
    store.upsert_node("b", "concept")
    with pytest.raises(ValueError):
        store.upsert_edge("bad-type", "a", "b")


def test_in_memory_traverse_rejects_bad_edge_type():
    store = InMemoryGraphStore()
    store.upsert_node("a", "concept")
    with pytest.raises(ValueError):
        store.traverse("a", edge_types=["bad-type"])


def test_graph_edge_endpoint_rejects_bad_label():
    resp = client.post(
        "/graph/edges",
        json={"edge_type": "bad-type", "source_id": "svc-A", "target_id": "고객", "actor": "admin"},
    )
    assert resp.status_code == 400


# --- raw cypher removed from the request surface ------------------------------


def test_traversal_request_has_no_raw_cypher_field():
    from sdp.graph_models import GraphTraversalRequest

    assert "cypher" not in GraphTraversalRequest.model_fields


def test_raw_cypher_in_body_is_ignored_not_executed():
    # An attacker-supplied ``cypher`` key is silently dropped (extra field), and
    # the safe parameterized traversal runs instead.
    resp = client.post(
        "/graph/query",
        json={
            "start_id": "고객",
            "max_depth": 1,
            "actor": "analyst",
            "cypher": "MATCH (n) DETACH DELETE n RETURN n",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["nodes"]


# --- authz on graph endpoints -------------------------------------------------


def test_graph_node_write_refused_for_anonymous():
    resp = client.post(
        "/graph/nodes",
        json={"node_id": "unauth-node", "kind": "service"},
    )
    assert resp.status_code == 403


def test_graph_node_write_refused_for_non_admin_reader():
    resp = client.post(
        "/graph/nodes",
        json={"node_id": "unauth-node", "kind": "service", "actor": "analyst"},
    )
    assert resp.status_code == 403


def test_graph_edge_write_refused_for_anonymous():
    resp = client.post(
        "/graph/edges",
        json={"edge_type": "related", "source_id": "a", "target_id": "b"},
    )
    assert resp.status_code == 403


def test_concept_write_refused_for_anonymous():
    resp = client.post("/ontology/concepts", json={"concept": "무단개념"})
    assert resp.status_code == 403


def test_graph_query_refused_for_anonymous():
    resp = client.post("/graph/query", json={"start_id": "고객", "max_depth": 1})
    assert resp.status_code == 403


def test_semantic_search_refused_for_anonymous():
    resp = client.post("/search/semantic", json={"query": "고객"})
    assert resp.status_code == 403


def test_graph_write_allowed_for_admin():
    resp = client.post(
        "/graph/nodes",
        json={"node_id": "authz-node", "kind": "service", "actor": "admin"},
    )
    assert resp.status_code == 200


# --- build_store: fail loud, no silent downgrade ------------------------------


def test_build_store_memory_backend_explicit(monkeypatch):
    monkeypatch.setattr(gs, "get_app_config", lambda: override_app_config(graph_backend="memory"))
    assert isinstance(build_store(), InMemoryGraphStore)


def test_build_store_auto_without_dsn_uses_memory(monkeypatch):
    monkeypatch.setattr(gs, "get_app_config", lambda: override_app_config(graph_backend="auto"))
    monkeypatch.setattr(
        gs, "load_bootstrap", lambda: config_module.BootstrapSettings(None, "default", "test")
    )
    assert isinstance(build_store(), InMemoryGraphStore)


def test_build_store_postgres_without_dsn_fails_loud(monkeypatch):
    monkeypatch.setattr(gs, "get_app_config", lambda: override_app_config(graph_backend="postgres"))
    monkeypatch.setattr(
        gs, "load_bootstrap", lambda: config_module.BootstrapSettings(None, "default", "test")
    )
    with pytest.raises(RuntimeError):
        build_store()


def test_build_store_configured_db_not_ready_fails_loud(monkeypatch):
    monkeypatch.setattr(gs, "get_app_config", lambda: override_app_config(graph_backend="auto"))
    monkeypatch.setattr(
        gs,
        "load_bootstrap",
        lambda: config_module.BootstrapSettings("postgresql+psycopg://u:p@nohost/db", "default", "test"),
    )

    class _DownStore:
        def __init__(self, dsn, config=None):
            pass

        def readiness(self):
            return {"ready": False, "error": "unreachable"}

    monkeypatch.setattr(gs, "PostgresGraphStore", _DownStore)
    with pytest.raises(RuntimeError):
        build_store()


# --- config: graph_backend validation ----------------------------------------


def test_invalid_graph_backend_rejected():
    with pytest.raises(ValueError):
        AppConfig.from_mapping({"graph_backend": "nope"}, source="test")
