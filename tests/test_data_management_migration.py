"""Static migration contract for the data-management evidence profile."""

from __future__ import annotations

from pathlib import Path


MIGRATION = Path(__file__).resolve().parents[1] / "migrations" / "0003_data_management_evidence.sql"


def test_data_management_evidence_migration_declares_normalized_tables() -> None:
    """The evidence profile persists normalized owner, CDE, rule, and observation rows."""

    assert MIGRATION.exists(), "0003 data-management evidence migration is required"
    sql = MIGRATION.read_text(encoding="utf-8")

    for table_name in (
        "data_owner_assignments",
        "critical_data_elements",
        "data_quality_rules",
        "data_quality_observations",
    ):
        assert f"CREATE TABLE IF NOT EXISTS {table_name}" in sql

    assert "UNIQUE (catalog_object_id, owner_subject, valid_from)" in sql
    assert "UNIQUE (catalog_object_id, element_key)" in sql
    assert "UNIQUE (critical_data_element_id, rule_code)" in sql
    assert "UNIQUE (data_quality_rule_id, source_observation_id)" in sql


def test_data_management_evidence_migration_preserves_authority_and_provenance() -> None:
    """Every governance fact carries tenant, truth, time, and HTTPS evidence fields."""

    assert MIGRATION.exists(), "0003 data-management evidence migration is required"
    sql = MIGRATION.read_text(encoding="utf-8")

    assert sql.count("tenant_reference TEXT NOT NULL") >= 4
    assert sql.count("truth_status TEXT NOT NULL") >= 4
    assert sql.count("evidence_reference TEXT NOT NULL") >= 4
    assert "CHECK (truth_status IN ('authoritative', 'observed', 'inferred', 'proposed'))" in sql
    assert "CHECK (evidence_reference LIKE 'https://%')" in sql
    assert "FOREIGN KEY (catalog_object_id) REFERENCES catalog_objects" in sql
