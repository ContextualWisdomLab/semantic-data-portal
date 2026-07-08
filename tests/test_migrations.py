"""AGE-independent tests for the migration SQL and its statement splitter."""

import importlib.util
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


def _load_runner():
    spec = importlib.util.spec_from_file_location(
        "run_migrations", MIGRATIONS_DIR / "run_migrations.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_defines_expected_snake_case_objects():
    sql = (MIGRATIONS_DIR / "0001_init_graph_vector.sql").read_text(encoding="utf-8")
    for obj in [
        "ontology_concepts",
        "concept_edges" if "concept_edges" in sql else "graph_edges",
        "dataset_nodes",
        "embedding_vectors",
        "graph_nodes",
        "config_entries",
        "schema_migrations",
    ]:
        assert obj in sql, f"expected object {obj} in migration"
    assert "CREATE EXTENSION IF NOT EXISTS age" in sql
    assert "CREATE EXTENSION IF NOT EXISTS vector" in sql
    assert "vector(128)" in sql


def test_statement_splitter_keeps_dollar_blocks_intact():
    runner = _load_runner()
    sql = (MIGRATIONS_DIR / "0001_init_graph_vector.sql").read_text(encoding="utf-8")
    statements = runner._statements(sql)
    assert statements
    # The DO $$ ... $$ block must be a single statement, not split on inner ';'
    do_blocks = [s for s in statements if s.strip().upper().startswith("DO")]
    assert len(do_blocks) == 1
    assert "create_graph" in do_blocks[0]
    assert do_blocks[0].count("$$") == 2


def test_render_sql_substitutes_configured_embedding_dimension():
    runner = _load_runner()
    sql = (MIGRATIONS_DIR / "0001_init_graph_vector.sql").read_text(encoding="utf-8")
    # Default dimension leaves the DDL unchanged ...
    assert "vector(128)" in runner._render_sql(sql, 128)
    # ... a non-default dimension is rendered into the pgvector column so the
    # migration and the (config-driven) inserts always agree.
    rendered = runner._render_sql(sql, 256)
    assert "vector(256)" in rendered
    assert "vector(128)" not in rendered


def test_embedding_dimension_reads_config_default():
    runner = _load_runner()
    assert runner._embedding_dimension() == 128
