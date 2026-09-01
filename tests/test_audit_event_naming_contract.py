from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

from sdp_core import AuditEvent, SQLiteEvidenceStore


LEGACY_AUDIT_PAYLOAD = {
    "id": "audit-legacy-1",
    "actor": "analyst",
    "action": "browse.preview",
    "resource": "dataset-1",
    "result": "success",
    "decision_id": "decision-1",
    "reason": "ok",
    "details": {"tenant_id": "demo"},
    "created_at": "2026-09-02T00:00:00+00:00",
}


def test_audit_event_owns_semantic_fields_and_preserves_legacy_wire_contract() -> None:
    event = AuditEvent(
        audit_event_id="audit-1",
        actor_subject="analyst",
        audit_action="browse.preview",
        resource_reference="dataset-1",
        audit_result="success",
        policy_decision_id="decision-1",
        audit_reason="ok",
        audit_details={"tenant_id": "demo"},
        created_at=datetime(2026, 9, 2, tzinfo=timezone.utc),
    )

    assert {
        "audit_event_id",
        "actor_subject",
        "audit_action",
        "resource_reference",
        "audit_result",
        "policy_decision_id",
        "audit_reason",
        "audit_details",
        "created_at",
    } == set(AuditEvent.model_fields)

    legacy_wire = event.model_dump(mode="json", by_alias=True)
    assert legacy_wire == {
        "id": "audit-1",
        "actor": "analyst",
        "action": "browse.preview",
        "resource": "dataset-1",
        "result": "success",
        "decision_id": "decision-1",
        "reason": "ok",
        "details": {"tenant_id": "demo"},
        "created_at": "2026-09-02T00:00:00Z",
    }

    replayed = AuditEvent.model_validate(LEGACY_AUDIT_PAYLOAD)
    assert replayed.audit_event_id == "audit-legacy-1"
    assert replayed.actor_subject == "analyst"
    assert replayed.audit_action == "browse.preview"
    assert replayed.resource_reference == "dataset-1"
    assert replayed.audit_result == "success"
    assert replayed.policy_decision_id == "decision-1"
    assert replayed.audit_reason == "ok"
    assert replayed.audit_details == {"tenant_id": "demo"}


def test_sqlite_store_migrates_legacy_audit_columns_without_data_loss(tmp_path) -> None:
    database_path = tmp_path / "evidence.sqlite3"
    with sqlite3.connect(database_path) as connection:
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
            INSERT INTO audit_events
            (id, actor, action, resource, result, decision_id, payload, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "audit-legacy-1",
                "analyst",
                "browse.preview",
                "dataset-1",
                "success",
                "decision-1",
                json.dumps(LEGACY_AUDIT_PAYLOAD),
                "2026-09-02T00:00:00+00:00",
            ),
        )

    store = SQLiteEvidenceStore(database_path)

    with sqlite3.connect(database_path) as connection:
        column_names = {
            row[1] for row in connection.execute("PRAGMA table_info(audit_events)").fetchall()
        }

    assert {
        "audit_event_id",
        "actor_subject",
        "audit_action",
        "resource_reference",
        "audit_result",
        "policy_decision_id",
        "event_payload",
        "created_at",
    }.issubset(column_names)
    assert not {
        "id",
        "actor",
        "action",
        "resource",
        "result",
        "decision_id",
        "payload",
    }.intersection(column_names)

    migrated_event = store.list_events(resource_reference="dataset-1")[0]
    assert migrated_event.audit_event_id == "audit-legacy-1"
    assert migrated_event.resource_reference == "dataset-1"

    # The previous Python keyword remains a compatibility-only adapter input.
    assert store.list_events(resource="dataset-1")[0].audit_event_id == "audit-legacy-1"
