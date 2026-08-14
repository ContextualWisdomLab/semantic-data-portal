"""Configuration and secret loading for the Semantic Data Portal.

Org rule: application secrets/config are NOT read from ``os.getenv`` at runtime.
Instead there is a single *bootstrap transport* step whose only job is to reach
the datastore / key-value backend. Every application-level setting (CORS
allowlist, embedding dimension, graph name, feature flags) is then loaded from
a database-backed key-value table (``config_entries``) or, when no database is
reachable, from bundled safe defaults.

The ONLY place ``os.environ`` is consulted is :func:`load_bootstrap` and it may
only read *transport* values (where the DB/KV lives), never an application
secret. Application code calls :func:`get_app_config` which never touches the
environment.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, replace
from functools import lru_cache
from typing import Any, Dict, List, Optional


# --- Bundled safe defaults (used when the KV/DB has no override) -------------

_DEFAULT_CONFIG: Dict[str, Any] = {
    # Tightened from the previous "*" wildcard. Overridable via the KV table.
    "cors_allow_origins": [
        "http://localhost:3000",
        "http://localhost:8000",
        "http://127.0.0.1:3000",
    ],
    "cors_allow_methods": ["GET", "POST", "PATCH", "OPTIONS"],
    "cors_allow_headers": ["*"],
    "embedding_dimension": 128,
    "graph_name": "semantic_graph",
    "semantic_search_default_limit": 5,
    "traversal_max_depth": 4,
    # Backend selection for the graph store:
    #   "auto"     -- Postgres+AGE+pgvector when a DB DSN is configured (and it
    #                 must be ready, else bootstrap fails loud), otherwise the
    #                 in-memory backend (standalone / submodule / CI).
    #   "postgres" -- require the database backend (fail loud if unavailable).
    #   "memory"   -- always use the in-memory backend.
    "graph_backend": "auto",
}


# --- Bootstrap transport (the ONLY env access in the whole app) --------------


@dataclass(frozen=True)
class BootstrapSettings:
    """Where the datastore / KV backend lives.

    These are *transport* coordinates, not application secrets. Reading them
    from the environment is the sanctioned bootstrap escape hatch.
    """

    database_dsn: Optional[str]
    config_namespace: str
    environment: str

    @property
    def has_database(self) -> bool:
        return bool(self.database_dsn)


@lru_cache(maxsize=1)
def load_bootstrap() -> BootstrapSettings:
    """Read bootstrap transport coordinates from the environment.

    Recognised variables (transport only):

    * ``SDP_DATABASE_DSN`` -- SQLAlchemy DSN to reach Postgres+AGE+pgvector.
    * ``SDP_CONFIG_NAMESPACE`` -- logical namespace/tenant for config rows.
    * ``SDP_ENV`` -- deployment environment label.
    """

    return BootstrapSettings(
        database_dsn=os.environ.get("SDP_DATABASE_DSN") or None,
        config_namespace=os.environ.get("SDP_CONFIG_NAMESPACE", "default"),
        environment=os.environ.get("SDP_ENV", "local"),
    )


# --- Application configuration ------------------------------------------------


@dataclass(frozen=True)
class AppConfig:
    cors_allow_origins: List[str] = field(default_factory=list)
    cors_allow_methods: List[str] = field(default_factory=list)
    cors_allow_headers: List[str] = field(default_factory=list)
    embedding_dimension: int = 128
    graph_name: str = "semantic_graph"
    semantic_search_default_limit: int = 5
    traversal_max_depth: int = 4
    graph_backend: str = "auto"
    source: str = "defaults"

    @classmethod
    def from_mapping(cls, values: Dict[str, Any], *, source: str) -> "AppConfig":
        merged = dict(_DEFAULT_CONFIG)
        merged.update({k: v for k, v in values.items() if v is not None})
        backend = str(merged["graph_backend"]).lower()
        if backend not in {"auto", "postgres", "memory"}:
            raise ValueError(f"invalid graph_backend: {merged['graph_backend']!r}")
        return cls(
            cors_allow_origins=list(merged["cors_allow_origins"]),
            cors_allow_methods=list(merged["cors_allow_methods"]),
            cors_allow_headers=list(merged["cors_allow_headers"]),
            embedding_dimension=int(merged["embedding_dimension"]),
            graph_name=str(merged["graph_name"]),
            semantic_search_default_limit=int(merged["semantic_search_default_limit"]),
            traversal_max_depth=int(merged["traversal_max_depth"]),
            graph_backend=backend,
            source=source,
        )


def _load_from_kv_table(bootstrap: BootstrapSettings) -> Optional[Dict[str, Any]]:
    """Load config rows from the ``config_entries`` key-value table.

    Returns ``None`` when the database is unreachable so the caller can fall
    back to bundled defaults. Never raises on connection problems.
    """

    if not bootstrap.has_database:
        return None
    try:  # imported lazily so the core app has no hard DB dependency
        from sqlalchemy import create_engine, text
    except Exception:  # pragma: no cover - sqlalchemy always present in graph extra
        return None

    try:
        engine = create_engine(bootstrap.database_dsn, pool_pre_ping=True)
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT config_key, config_value FROM config_entries "
                    "WHERE config_namespace = :ns"
                ),
                {"ns": bootstrap.config_namespace},
            ).fetchall()
    except Exception:
        return None

    values: Dict[str, Any] = {}
    for key, raw in rows:
        values[key] = _decode_config_value(raw)
    return values


def _decode_config_value(raw: Any) -> Any:
    """Decode one JSON-backed config value, preserving legacy raw values."""

    try:
        return json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, json.JSONDecodeError):
        return raw


def _load_config_entry(
    bootstrap: BootstrapSettings,
    name: str,
    default: Any = None,
) -> Any:
    """Load exactly one config value and release its short-lived DB engine."""

    if not bootstrap.has_database:
        return default
    try:  # imported lazily so core-only installations keep their safe default
        from sqlalchemy import create_engine, text
    except ImportError:
        return default

    try:
        engine = create_engine(bootstrap.database_dsn, pool_pre_ping=True)
        try:
            with engine.connect() as conn:
                row = conn.execute(
                    text(
                        "SELECT config_value FROM config_entries "
                        "WHERE config_namespace = :ns AND config_key = :key"
                    ),
                    {"ns": bootstrap.config_namespace, "key": name},
                ).fetchone()
        finally:
            engine.dispose()
    except Exception:
        return default

    if row is None:
        return default
    return _decode_config_value(row[0])


@lru_cache(maxsize=1)
def get_app_config() -> AppConfig:
    """Return the effective application configuration.

    Order of precedence: ``config_entries`` KV table (if the DB is reachable)
    then bundled safe defaults. The environment is never read here.
    """

    bootstrap = load_bootstrap()
    kv_values = _load_from_kv_table(bootstrap)
    if kv_values:
        return AppConfig.from_mapping(kv_values, source="config_entries")
    return AppConfig.from_mapping({}, source="defaults")


def get_config_entry(name: str, default: Any = None) -> Any:
    """Read one application value from the database-backed configuration KV.

    Environment variables are deliberately not a fallback here.  They are only
    bootstrap transport for locating the KV; application settings must remain
    governed by ``config_entries`` or an explicit safe caller default.
    """

    return _load_config_entry(load_bootstrap(), name, default)


def reset_config_cache() -> None:
    """Clear cached config (used by tests that swap the KV backend)."""

    load_bootstrap.cache_clear()
    get_app_config.cache_clear()


def default_config_seed() -> Dict[str, Any]:
    """Rows that the migration/bootstrap loads into ``config_entries``."""

    return dict(_DEFAULT_CONFIG)


def override_app_config(**overrides: Any) -> AppConfig:
    """Build an AppConfig from defaults plus explicit overrides (test helper)."""

    base = AppConfig.from_mapping({}, source="override")
    return replace(base, **overrides)
