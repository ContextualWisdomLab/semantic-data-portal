"""Config loading seam: the DB-backed key-value config loader.

``_load_from_kv_table`` is the sanctioned path that reads application config from
the ``config_entries`` table (never ``os.getenv`` at runtime). These cover it
with a fake SQLAlchemy engine (no live database): the no-DB short-circuit, the
row-parsing branches (JSON string, non-string passthrough, invalid-JSON
fallback), and the fail-soft behavior when the database is unreachable.
"""

from __future__ import annotations

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sdp import config as cfg  # noqa: E402


def _bootstrap(dsn):
    return cfg.BootstrapSettings(database_dsn=dsn, config_namespace="default", environment="local")


def test_load_from_kv_table_none_without_database() -> None:
    """No DSN configured -> None (caller falls back to bundled defaults)."""
    assert cfg._load_from_kv_table(_bootstrap(None)) is None


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _FakeConn:
    def __init__(self, rows):
        self._rows = rows

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, _stmt, _params):
        return _FakeResult(self._rows)


class _FakeEngine:
    def __init__(self, rows):
        self._rows = rows

    def connect(self):
        return _FakeConn(self._rows)


def test_load_from_kv_table_parses_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    """JSON-string values are decoded; non-strings pass through; invalid JSON
    falls back to the raw value."""
    rows = [
        ("cors_allow_origins", '["https://app.example"]'),  # valid JSON string -> decoded
        ("embedding_dimension", 256),  # non-string -> passthrough
        ("graph_name", "{not-valid-json"),  # invalid JSON string -> raw fallback
    ]
    monkeypatch.setattr("sqlalchemy.create_engine", lambda *a, **k: _FakeEngine(rows))
    values = cfg._load_from_kv_table(_bootstrap("postgresql://localhost/sdp"))
    assert values == {
        "cors_allow_origins": ["https://app.example"],
        "embedding_dimension": 256,
        "graph_name": "{not-valid-json",
    }


def test_load_from_kv_table_none_on_db_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """A database/connection failure is swallowed and yields None (fail-soft)."""
    def _boom(*_a, **_k):
        raise RuntimeError("db unreachable")

    monkeypatch.setattr("sqlalchemy.create_engine", _boom)
    assert cfg._load_from_kv_table(_bootstrap("postgresql://localhost/sdp")) is None


def test_from_mapping_kv_values_override_defaults() -> None:
    """AppConfig.from_mapping applies KV overrides on top of the safe defaults."""
    conf = cfg.AppConfig.from_mapping({"embedding_dimension": 256}, source="kv")
    assert conf.embedding_dimension == 256
    assert conf.source == "kv"
    # Untouched keys keep their bundled defaults.
    assert conf.graph_backend == "auto"


def test_from_mapping_rejects_invalid_graph_backend() -> None:
    """An out-of-domain graph_backend value is rejected."""
    with pytest.raises(ValueError):
        cfg.AppConfig.from_mapping({"graph_backend": "cassandra"}, source="kv")


def test_default_config_seed_returns_a_defaults_copy() -> None:
    """default_config_seed returns the bundled defaults as an independent copy."""
    seed = cfg.default_config_seed()
    assert seed["graph_backend"] == "auto"
    seed["graph_backend"] = "mutated"
    assert cfg.default_config_seed()["graph_backend"] == "auto"  # copy, not the shared dict


def test_load_config_entry_queries_one_key_and_disposes_engine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Hot-path credential reads must not scan a namespace or leak an engine."""

    observed: dict[str, object] = {}

    class Result:
        def fetchone(self):
            return ('"750"',)

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def execute(self, statement, params):
            observed["statement"] = str(statement)
            observed["params"] = params
            return Result()

    class Engine:
        def connect(self):
            return Connection()

        def dispose(self):
            observed["disposed"] = True

    monkeypatch.setattr("sqlalchemy.create_engine", lambda *a, **k: Engine())

    value = cfg._load_config_entry(
        _bootstrap("postgresql://localhost/sdp"),
        "SDP_LOG_SINK_TIMEOUT_MS",
    )

    assert value == "750"
    assert "config_key = :key" in str(observed["statement"])
    assert observed["params"] == {
        "ns": "default",
        "key": "SDP_LOG_SINK_TIMEOUT_MS",
    }
    assert observed["disposed"] is True
