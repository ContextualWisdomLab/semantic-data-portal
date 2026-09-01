from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import sdp_core


def _sqlite_columns(database_path: Path, table_name: str) -> set[str]:
    with sqlite3.connect(database_path) as connection:
        return {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table_name})")}


def test_sqlite_evidence_schema_uses_semantic_multiword_columns(tmp_path: Path) -> None:
    database_path = tmp_path / "evidence.sqlite3"
    sdp_core.SQLiteEvidenceStore(database_path)

    assert _sqlite_columns(database_path, "policy_decisions") == {
        "decision_id",
        "policy_subject",
        "policy_resource",
        "policy_action",
        "policy_effect",
        "decision_payload",
        "recorded_at",
    }
    assert _sqlite_columns(database_path, "audit_events") == {
        "audit_event_id",
        "audit_actor",
        "audit_action",
        "audit_resource",
        "audit_result",
        "decision_id",
        "audit_payload",
        "created_at",
    }


def test_sqlite_legacy_schema_migrates_without_losing_evidence(tmp_path: Path) -> None:
    database_path = tmp_path / "legacy.sqlite3"
    decision_payload = {
        "subject": "analyst",
        "resource": "crm-customer-master",
        "action": "preview",
        "effect": "allow",
        "decision_id": "decision-legacy",
        "obligations": {},
        "reason": "ok",
    }
    audit_payload = {
        "id": "audit-legacy",
        "actor": "analyst",
        "action": "browse.preview",
        "resource": "crm-customer-master",
        "result": "allowed",
        "decision_id": "decision-legacy",
        "reason": "ok",
        "details": {},
        "created_at": "2026-07-02T00:00:00Z",
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
            """
            INSERT INTO policy_decisions
            (decision_id, subject, resource, action, effect, payload, recorded_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "decision-legacy",
                "analyst",
                "crm-customer-master",
                "preview",
                "allow",
                json.dumps(decision_payload),
                "2026-07-02T00:00:00Z",
            ),
        )
        connection.execute(
            """
            INSERT INTO audit_events
            (id, actor, action, resource, result, decision_id, payload, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "audit-legacy",
                "analyst",
                "browse.preview",
                "crm-customer-master",
                "allowed",
                "decision-legacy",
                json.dumps(audit_payload),
                "2026-07-02T00:00:00Z",
            ),
        )

    store = sdp_core.SQLiteEvidenceStore(database_path)

    assert "subject" not in _sqlite_columns(database_path, "policy_decisions")
    assert "resource" not in _sqlite_columns(database_path, "policy_decisions")
    assert "action" not in _sqlite_columns(database_path, "policy_decisions")
    assert "effect" not in _sqlite_columns(database_path, "policy_decisions")
    assert "payload" not in _sqlite_columns(database_path, "policy_decisions")
    assert "id" not in _sqlite_columns(database_path, "audit_events")
    assert "actor" not in _sqlite_columns(database_path, "audit_events")
    assert "action" not in _sqlite_columns(database_path, "audit_events")
    assert "resource" not in _sqlite_columns(database_path, "audit_events")
    assert "result" not in _sqlite_columns(database_path, "audit_events")
    assert "payload" not in _sqlite_columns(database_path, "audit_events")

    assert store.get_decision("decision-legacy") == sdp_core.PolicyDecision.model_validate(decision_payload)
    events = store.list_events(resource="crm-customer-master", limit=10)
    assert [event.id for event in events] == ["audit-legacy"]


def test_postgres_evidence_sql_uses_semantic_multiword_columns() -> None:
    class FakeCursor:
        def fetchone(self):
            return None

        def fetchall(self):
            return []

    class FakeConnection:
        def __init__(self) -> None:
            self.statements: list[tuple[str, tuple[object, ...]]] = []

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, sql: str, params: tuple[object, ...] = ()):
            self.statements.append((sql, params))
            return FakeCursor()

    connections: list[FakeConnection] = []

    def connect_factory(dsn: str, **kwargs: str) -> FakeConnection:
        connection = FakeConnection()
        connections.append(connection)
        return connection

    store = sdp_core.PostgresEvidenceStore(
        "postgresql://buyer:secret@localhost:5432/sdp",
        connect_factory=connect_factory,
    )
    decision = sdp_core.PolicyDecision(
        subject="analyst",
        resource="crm-customer-master",
        action="preview",
        effect="allow",
        decision_id="decision-1",
        reason="ok",
    )
    event = sdp_core.AuditEvent(
        id="audit-1",
        actor="analyst",
        action="browse.preview",
        resource="crm-customer-master",
        result="allowed",
        decision_id="decision-1",
        reason="ok",
    )

    store.record_decision(decision)
    store.append_event(event)

    statements = "\n".join(sql for connection in connections for sql, _ in connection.statements)
    assert "policy_subject TEXT NOT NULL" in statements
    assert "policy_resource TEXT NOT NULL" in statements
    assert "policy_action TEXT NOT NULL" in statements
    assert "policy_effect TEXT NOT NULL" in statements
    assert "decision_payload JSONB NOT NULL" in statements
    assert "audit_event_id TEXT PRIMARY KEY" in statements
    assert "audit_actor TEXT NOT NULL" in statements
    assert "audit_action TEXT NOT NULL" in statements
    assert "audit_resource TEXT NOT NULL" in statements
    assert "audit_result TEXT NOT NULL" in statements
    assert "audit_payload JSONB NOT NULL" in statements
    assert "idx_policy_decisions_tenant_policy_resource_created" in statements
    assert "idx_audit_events_tenant_audit_resource_created" in statements
    assert "(decision_id, tenant_id, policy_subject, policy_resource, policy_action, policy_effect, decision_payload, created_at)" in statements
    assert "(audit_event_id, tenant_id, audit_actor, audit_action, audit_resource, audit_result, decision_id, audit_payload, created_at)" in statements
    assert "ON CONFLICT (audit_event_id)" in statements
