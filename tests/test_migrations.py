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


def test_file_copy_lineage_migration_defines_normalized_fk_graph():
    sql = (MIGRATIONS_DIR / "0002_file_copy_lineage.sql").read_text(
        encoding="utf-8"
    )
    for table in [
        "file_asset_records",
        "file_distribution_records",
        "cloud_copy_receipts",
        "file_metadata_evidence_records",
        "cloud_sync_evidence_records",
    ]:
        assert f"CREATE TABLE IF NOT EXISTS {table}" in sql
    assert sql.count("REFERENCES") == 7
    assert sql.count("ON DELETE RESTRICT") == 7
    assert "source_locator_sha256" in sql
    assert "source_relative_path" not in sql
    assert "provider_sync_confirmed" in sql
    assert "local_copy_verified" in sql
    assert "content_blake3" in sql
    assert "production_time_source" in sql
    assert "file_metadata_evidence_selected_idx" in sql


def test_all_migration_files_are_statement_splitter_compatible():
    runner = _load_runner()
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        statements = runner._statements(path.read_text(encoding="utf-8"))
        assert statements, f"migration {path.name} must contain executable statements"
        assert statements[-1].startswith("INSERT INTO schema_migrations")
