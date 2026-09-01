from __future__ import annotations

import json
import sqlite3

import sdp_core


def _sqlite_columns(database_path, table_name: str) -> set[str]:
    with sqlite3.connect(database_path) as connection:
        return {row[1] for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()}


def test_fresh_sqlite_evidence_schema_uses_semantic_multiword_columns(tmp_path) -> None:
    database_path = tmp_path / "evidence.sqlite3"

    sdp_core.SQLiteEvidenceStore(database_path)

    assert _sqlite_columns(database_path, "policy_decisions") == {
        "decision_id",
        "decision_subject",
        "policy_resource",
        "policy_action",
        "decision_effect",
        "decision_payload",
        "recorded_at",
    }
    assert _sqlite_columns(database_path, "audit_events") == {
        "audit_event_id",
        "actor_subject",
        "audit_action",
        "audit_resource",
        "audit_result",
        "decision_id",
        "audit_payload",
        "created_at",
    }


def test_sqlite_evidence_schema_migrates_legacy_columns_without_data_loss(tmp_path) -> None:
    database_path = tmp_path / "legacy-evidence.sqlite3"
    policy_payload = {
        "subject": "analyst",
        "resource": "crm-customer-master",
        "action": "preview",
        "effect": "allow",
        "decision_id": "decision-legacy",
        "obligations": {"tenant_id": "buyer-demo"},
        "reason": "legacy row",
    }
    audit_payload = {
        "id": "audit-legacy",
        "actor": "analyst",
        "action": "browse.preview",
        "resource": "crm-customer-master",
        "result": "allowed",
        "decision_id": "decision-legacy",
        "details": {"tenant_id": "buyer-demo"},
        "reason": "legacy row",
        "created_at": "2026-09-01T00:00:00Z",
    }

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE policy_decisions (
                decision_id TEXT PRIMARY KEY,
                subject TEXT NOT NULL,
                resource TEXT NOT NULL,
                action TEXT NOT NULL,
                effect TEXT NOT NULL,
                payload TEXT NOT NULL,
                recorded_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE audit_events (
                id TEXT PRIMARY KEY,
                actor TEXT NOT NULL,
                action TEXT NOT NULL,
                resource TEXT NOT NULL,
                result TEXT NOT NULL,
                decision_id TEXT,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "INSERT INTO policy_decisions VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                "decision-legacy",
                "analyst",
                "crm-customer-master",
                "preview",
                "allow",
                json.dumps(policy_payload),
                "2026-09-01T00:00:00Z",
            ),
        )
        connection.execute(
            "INSERT INTO audit_events VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "audit-legacy",
                "analyst",
                "browse.preview",
                "crm-customer-master",
                "allowed",
                "decision-legacy",
                json.dumps(audit_payload),
                "2026-09-01T00:00:00Z",
            ),
        )

    store = sdp_core.SQLiteEvidenceStore(database_path)

    policy_columns = _sqlite_columns(database_path, "policy_decisions")
    audit_columns = _sqlite_columns(database_path, "audit_events")
    assert {"subject", "resource", "action", "effect", "payload"}.isdisjoint(policy_columns)
    assert {"id", "actor", "action", "resource", "result", "payload"}.isdisjoint(audit_columns)
    assert store.get_decision("decision-legacy") == sdp_core.PolicyDecision.model_validate(policy_payload)
    assert store.list_events(resource="crm-customer-master", limit=10) == [
        sdp_core.AuditEvent.model_validate(audit_payload)
    ]


def test_fresh_postgres_evidence_schema_uses_semantic_multiword_columns() -> None:
    statements: list[str] = []

    class FakeCursor:
        def fetchone(self):
            return None

        def fetchall(self):
            return []

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, sql, params=()):
            statements.append(sql)
            return FakeCursor()

    def connect_factory(dsn, **kwargs):
        return FakeConnection()

    sdp_core.PostgresEvidenceStore(
        "postgresql://buyer:secret@localhost:5432/sdp",
        connect_factory=connect_factory,
    )

    policy_create = next(sql for sql in statements if "CREATE TABLE IF NOT EXISTS policy_decisions" in sql)
    audit_create = next(sql for sql in statements if "CREATE TABLE IF NOT EXISTS audit_events" in sql)

    assert "decision_subject TEXT NOT NULL" in policy_create
    assert "policy_resource TEXT NOT NULL" in policy_create
    assert "policy_action TEXT NOT NULL" in policy_create
    assert "decision_effect TEXT NOT NULL" in policy_create
    assert "decision_payload JSONB NOT NULL" in policy_create
    assert "audit_event_id TEXT PRIMARY KEY" in audit_create
    assert "actor_subject TEXT NOT NULL" in audit_create
    assert "audit_action TEXT NOT NULL" in audit_create
    assert "audit_resource TEXT NOT NULL" in audit_create
    assert "audit_result TEXT NOT NULL" in audit_create
    assert "audit_payload JSONB NOT NULL" in audit_create
