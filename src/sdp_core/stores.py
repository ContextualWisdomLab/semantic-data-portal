from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .contracts import AuditEvent, PolicyDecision


class SQLiteEvidenceStore:
    """Local evidence store for demo and pilot auditability."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS policy_decisions (
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
                CREATE TABLE IF NOT EXISTS audit_events (
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

    def record_decision(self, decision: PolicyDecision) -> PolicyDecision:
        payload = decision.model_dump(mode="json")
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO policy_decisions
                (decision_id, subject, resource, action, effect, payload, recorded_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    decision.decision_id,
                    decision.subject,
                    decision.resource,
                    decision.action,
                    decision.effect,
                    json.dumps(payload, ensure_ascii=False, sort_keys=True),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
        return decision

    def get_decision(self, decision_id: str) -> PolicyDecision | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM policy_decisions WHERE decision_id = ?",
                (decision_id,),
            ).fetchone()
        if not row:
            return None
        return PolicyDecision.model_validate(json.loads(row[0]))

    def list_decisions(self, *, resource: str | None = None, limit: int = 100) -> list[PolicyDecision]:
        sql = "SELECT payload FROM policy_decisions"
        params: tuple[object, ...] = ()
        if resource:
            sql += " WHERE resource = ?"
            params = (resource,)
        sql += " ORDER BY recorded_at DESC LIMIT ?"
        params = (*params, limit)

        with self._connect() as connection:
            rows = connection.execute(sql, params).fetchall()
        return [PolicyDecision.model_validate(json.loads(row[0])) for row in rows]

    def append_event(self, event: AuditEvent) -> AuditEvent:
        payload = event.model_dump(mode="json")
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO audit_events
                (id, actor, action, resource, result, decision_id, payload, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.id,
                    event.actor,
                    event.action,
                    event.resource,
                    event.result,
                    event.decision_id,
                    json.dumps(payload, ensure_ascii=False, sort_keys=True),
                    event.created_at.isoformat(),
                ),
            )
        return event

    def list_events(self, *, resource: str | None = None, limit: int = 100) -> list[AuditEvent]:
        sql = "SELECT payload FROM audit_events"
        params: tuple[object, ...] = ()
        if resource:
            sql += " WHERE resource = ?"
            params = (resource,)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params = (*params, limit)

        with self._connect() as connection:
            rows = connection.execute(sql, params).fetchall()
        return [AuditEvent.model_validate(json.loads(row[0])) for row in rows]
