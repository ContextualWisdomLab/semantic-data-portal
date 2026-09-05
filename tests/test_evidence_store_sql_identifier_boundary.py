"""Security regressions for evidence-store schema identifier composition."""

from __future__ import annotations

import sqlite3

import pytest

from sdp_core.stores import (
    _migrate_postgres_columns,
    _migrate_sqlite_columns,
    _sqlite_column_names,
)


def test_sqlite_schema_introspection_rejects_unknown_table_identifier() -> None:
    """Schema introspection accepts only the Evidence Store's closed table set."""
    with sqlite3.connect(":memory:") as connection:
        with pytest.raises(ValueError, match="unsupported evidence-store table"):
            _sqlite_column_names(connection, 'policy_decisions"; DROP TABLE audit_events; --')


def test_sqlite_migration_rejects_unknown_column_rename_before_ddl() -> None:
    """A caller cannot extend the owned rename set through generic identifiers."""
    with sqlite3.connect(":memory:") as connection:
        connection.execute('CREATE TABLE "policy_decisions" ("subject" TEXT)')

        with pytest.raises(ValueError, match="unsupported evidence-store column rename"):
            _migrate_sqlite_columns(
                connection,
                "policy_decisions",
                (("subject", "unowned_subject_name"),),
            )

        assert _sqlite_column_names(connection, "policy_decisions") == {"subject"}


def test_sqlite_migration_rejects_ambiguous_dual_schema_without_rename() -> None:
    """A partial migration fails closed instead of choosing one persisted column."""
    with sqlite3.connect(":memory:") as connection:
        connection.execute(
            'CREATE TABLE "policy_decisions" ("subject" TEXT, "decision_subject" TEXT)'
        )

        with pytest.raises(RuntimeError, match="ambiguous policy_decisions schema"):
            _migrate_sqlite_columns(
                connection,
                "policy_decisions",
                (("subject", "decision_subject"),),
            )

        assert _sqlite_column_names(connection, "policy_decisions") == {
            "subject",
            "decision_subject",
        }


def test_postgres_schema_lookup_uses_bound_values_before_literal_ddl() -> None:
    """Metadata values are parameters; only a closed literal rename may be DDL."""
    calls: list[tuple[str, tuple[object, ...]]] = []

    class FakeCursor:
        def fetchall(self):
            return [("subject",)]

    class FakeConnection:
        def execute(self, sql, params=()):
            calls.append((sql, tuple(params)))
            return FakeCursor()

    _migrate_postgres_columns(
        FakeConnection(),
        "policy_decisions",
        (("subject", "decision_subject"),),
    )

    metadata_calls = [call for call in calls if "information_schema.columns" in call[0]]
    assert metadata_calls
    for sql, params in metadata_calls:
        assert "policy_decisions" not in sql
        assert "subject" not in sql
        assert "decision_subject" not in sql
        assert params == ("policy_decisions", "subject", "decision_subject")

    ddl_calls = [call for call in calls if "ALTER TABLE" in call[0]]
    assert ddl_calls == [
        (
            'ALTER TABLE "policy_decisions" RENAME COLUMN "subject" TO "decision_subject"',
            (),
        )
    ]


def test_postgres_migration_rejects_ambiguous_dual_schema_without_ddl() -> None:
    """Postgres migration preserves the existing both-columns ambiguity guard."""
    calls: list[tuple[str, tuple[object, ...]]] = []

    class FakeCursor:
        def fetchall(self):
            return [("subject",), ("decision_subject",)]

    class FakeConnection:
        def execute(self, sql, params=()):
            calls.append((sql, tuple(params)))
            return FakeCursor()

    with pytest.raises(RuntimeError, match="ambiguous policy_decisions schema"):
        _migrate_postgres_columns(
            FakeConnection(),
            "policy_decisions",
            (("subject", "decision_subject"),),
        )

    assert [call for call in calls if "ALTER TABLE" in call[0]] == []
