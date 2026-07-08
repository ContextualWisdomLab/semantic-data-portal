"""Apply SQL migrations and load config + seed data (idempotent).

Bootstrap transport only: the database DSN is read once from the environment
(``SDP_DATABASE_DSN``) to *reach* the database. Application config is then
written into the ``config_entries`` KV table so the running service never reads
app config/secrets from the environment.

Usage:
    SDP_DATABASE_DSN=postgresql+psycopg://sdp:sdp@localhost:5432/sdp \
        python -m migrations.run_migrations
"""

from __future__ import annotations

import glob
import json
import os
import re
import sys
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parent

# The embedding column is declared ``vector(128)`` in the SQL (the default
# ``embedding_dimension``). The pgvector column dimension MUST match the
# configured embedding dimension, otherwise inserts of a differently-sized
# vector fail at runtime. We render the configured dimension into the DDL at
# apply time so the migration and the inserts always agree.
_DEFAULT_EMBEDDING_DIMENSION = 128
_VECTOR_DIM_RE = re.compile(r"vector\(\d+\)")


def _embedding_dimension() -> int:
    """Read the configured embedding dimension (falls back to the default)."""

    try:
        sys.path.insert(0, str(MIGRATIONS_DIR.parent / "src"))
        from sdp.config import get_app_config  # noqa: E402

        return int(get_app_config().embedding_dimension)
    except Exception:  # pragma: no cover - config always importable in practice
        return _DEFAULT_EMBEDDING_DIMENSION


def _render_sql(sql_text: str, embedding_dimension: int) -> str:
    """Substitute the configured pgvector dimension into the migration DDL."""

    return _VECTOR_DIM_RE.sub(f"vector({int(embedding_dimension)})", sql_text)


def _statements(sql_text: str):
    # Split on ';' but keep DO $$ ... $$ blocks intact.
    statements = []
    buffer = []
    in_dollar = False
    for line in sql_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("--"):
            continue
        if "$$" in line:
            in_dollar = not in_dollar if line.count("$$") % 2 == 1 else in_dollar
        buffer.append(line)
        if not in_dollar and stripped.endswith(";"):
            statements.append("\n".join(buffer).strip())
            buffer = []
    tail = "\n".join(buffer).strip()
    if tail:
        statements.append(tail)
    return [s for s in statements if s]


def apply_migrations(dsn: str) -> None:
    from sqlalchemy import create_engine, text

    engine = create_engine(dsn, future=True)
    files = sorted(glob.glob(str(MIGRATIONS_DIR / "*.sql")))
    dimension = _embedding_dimension()
    with engine.begin() as conn:
        for path in files:
            sql_text = _render_sql(Path(path).read_text(encoding="utf-8"), dimension)
            for statement in _statements(sql_text):
                conn.execute(text(statement))
            print(f"applied migration: {os.path.basename(path)}")


def load_config(dsn: str) -> None:
    """Persist bundled default config into the config_entries KV table."""

    from sqlalchemy import create_engine, text

    # Imported here so migrations work even without the package installed on path
    sys.path.insert(0, str(MIGRATIONS_DIR.parent / "src"))
    from sdp.config import default_config_seed  # noqa: E402

    namespace = os.environ.get("SDP_CONFIG_NAMESPACE", "default")
    engine = create_engine(dsn, future=True)
    with engine.begin() as conn:
        for key, value in default_config_seed().items():
            conn.execute(
                text(
                    "INSERT INTO config_entries (config_namespace, config_key, config_value) "
                    "VALUES (:ns, :key, CAST(:value AS jsonb)) "
                    "ON CONFLICT (config_namespace, config_key) DO NOTHING"
                ),
                {"ns": namespace, "key": key, "value": json.dumps(value)},
            )
    print(f"loaded default config into config_entries (namespace={namespace})")


def seed_graph(dsn: str) -> None:
    sys.path.insert(0, str(MIGRATIONS_DIR.parent / "src"))
    from sdp.graph_store import PostgresGraphStore, set_store  # noqa: E402
    from sdp.seed import seed_store  # noqa: E402

    store = PostgresGraphStore(dsn)
    set_store(store)
    stats = seed_store(store)
    print(f"seeded graph store: {stats}")


def main() -> int:
    dsn = os.environ.get("SDP_DATABASE_DSN")
    if not dsn:
        print("SDP_DATABASE_DSN is required (bootstrap transport).", file=sys.stderr)
        return 2
    apply_migrations(dsn)
    load_config(dsn)
    seed_graph(dsn)
    print("migrations + seed complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
