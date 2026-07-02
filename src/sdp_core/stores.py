from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .contracts import AuditEvent, PolicyDecision


def _payload_to_dict(payload: object) -> dict[str, Any]:
    if isinstance(payload, dict):
        return payload
    if isinstance(payload, str):
        return json.loads(payload)
    raise TypeError(f"unsupported evidence payload type: {type(payload).__name__}")


def _policy_tenant_id(decision: PolicyDecision) -> str:
    return str(decision.obligations.get("tenant_id") or "demo")


def _audit_tenant_id(event: AuditEvent) -> str:
    return str(event.details.get("tenant_id") or event.details.get("tenant") or "demo")


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


class PostgresEvidenceStore:
    """Managed Postgres evidence store for paid pilots."""

    def __init__(
        self,
        dsn: str,
        *,
        sslmode: str | None = None,
        connect_factory: Callable[..., Any] | None = None,
    ):
        self.dsn = dsn
        self.sslmode = sslmode
        self._connect_factory = connect_factory
        self._initialize()

    def _connect(self) -> Any:
        connect_factory = self._connect_factory
        if connect_factory is None:
            import psycopg

            connect_factory = psycopg.connect

        kwargs: dict[str, str] = {}
        if self.sslmode and "sslmode=" not in self.dsn:
            kwargs["sslmode"] = self.sslmode
        return connect_factory(self.dsn, **kwargs)

    def _jsonb(self, payload: dict[str, Any]) -> Any:
        try:
            from psycopg.types.json import Jsonb
        except Exception:
            return payload
        return Jsonb(payload)

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS policy_decisions (
                    decision_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    resource TEXT NOT NULL,
                    action TEXT NOT NULL,
                    effect TEXT NOT NULL,
                    payload JSONB NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_events (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    action TEXT NOT NULL,
                    resource TEXT NOT NULL,
                    result TEXT NOT NULL,
                    decision_id TEXT,
                    payload JSONB NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL
                )
                """
            )
            connection.execute("ALTER TABLE policy_decisions ADD COLUMN IF NOT EXISTS tenant_id TEXT")
            connection.execute("ALTER TABLE policy_decisions ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ")
            connection.execute(
                """
                UPDATE policy_decisions
                SET tenant_id = COALESCE(NULLIF(tenant_id, ''), payload -> 'obligations' ->> 'tenant_id', 'demo')
                WHERE tenant_id IS NULL OR tenant_id = ''
                """
            )
            connection.execute(
                """
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'policy_decisions' AND column_name = 'recorded_at'
                    ) THEN
                        UPDATE policy_decisions
                        SET created_at = COALESCE(created_at, recorded_at, NOW())
                        WHERE created_at IS NULL;
                    ELSE
                        UPDATE policy_decisions
                        SET created_at = COALESCE(created_at, NOW())
                        WHERE created_at IS NULL;
                    END IF;
                END $$;
                """
            )
            connection.execute(
                """
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'policy_decisions' AND column_name = 'recorded_at'
                    ) THEN
                        ALTER TABLE policy_decisions ALTER COLUMN recorded_at DROP NOT NULL;
                    END IF;
                END $$;
                """
            )
            connection.execute("ALTER TABLE policy_decisions ALTER COLUMN tenant_id SET NOT NULL")
            connection.execute("ALTER TABLE policy_decisions ALTER COLUMN created_at SET NOT NULL")
            connection.execute("ALTER TABLE audit_events ADD COLUMN IF NOT EXISTS tenant_id TEXT")
            connection.execute(
                """
                UPDATE audit_events
                SET tenant_id = COALESCE(NULLIF(tenant_id, ''), payload -> 'details' ->> 'tenant_id', 'demo')
                WHERE tenant_id IS NULL OR tenant_id = ''
                """
            )
            connection.execute("ALTER TABLE audit_events ALTER COLUMN tenant_id SET NOT NULL")
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_policy_decisions_tenant_resource_created ON policy_decisions (tenant_id, resource, created_at DESC)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_audit_events_tenant_resource_created ON audit_events (tenant_id, resource, created_at DESC)"
            )

    def record_decision(self, decision: PolicyDecision) -> PolicyDecision:
        payload = decision.model_dump(mode="json")
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO policy_decisions
                (decision_id, tenant_id, subject, resource, action, effect, payload, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (decision_id) DO UPDATE SET
                    tenant_id = EXCLUDED.tenant_id,
                    subject = EXCLUDED.subject,
                    resource = EXCLUDED.resource,
                    action = EXCLUDED.action,
                    effect = EXCLUDED.effect,
                    payload = EXCLUDED.payload,
                    created_at = EXCLUDED.created_at
                """,
                (
                    decision.decision_id,
                    _policy_tenant_id(decision),
                    decision.subject,
                    decision.resource,
                    decision.action,
                    decision.effect,
                    self._jsonb(payload),
                    datetime.now(timezone.utc),
                ),
            )
        return decision

    def get_decision(self, decision_id: str) -> PolicyDecision | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM policy_decisions WHERE decision_id = %s",
                (decision_id,),
            ).fetchone()
        if not row:
            return None
        return PolicyDecision.model_validate(_payload_to_dict(row[0]))

    def list_decisions(self, *, resource: str | None = None, limit: int = 100) -> list[PolicyDecision]:
        sql = "SELECT payload FROM policy_decisions"
        params: tuple[object, ...] = ()
        if resource:
            sql += " WHERE resource = %s"
            params = (resource,)
        sql += " ORDER BY created_at DESC LIMIT %s"
        params = (*params, limit)

        with self._connect() as connection:
            rows = connection.execute(sql, params).fetchall()
        return [PolicyDecision.model_validate(_payload_to_dict(row[0])) for row in rows]

    def append_event(self, event: AuditEvent) -> AuditEvent:
        payload = event.model_dump(mode="json")
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO audit_events
                (id, tenant_id, actor, action, resource, result, decision_id, payload, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    tenant_id = EXCLUDED.tenant_id,
                    actor = EXCLUDED.actor,
                    action = EXCLUDED.action,
                    resource = EXCLUDED.resource,
                    result = EXCLUDED.result,
                    decision_id = EXCLUDED.decision_id,
                    payload = EXCLUDED.payload,
                    created_at = EXCLUDED.created_at
                """,
                (
                    event.id,
                    _audit_tenant_id(event),
                    event.actor,
                    event.action,
                    event.resource,
                    event.result,
                    event.decision_id,
                    self._jsonb(payload),
                    event.created_at,
                ),
            )
        return event

    def list_events(self, *, resource: str | None = None, limit: int = 100) -> list[AuditEvent]:
        sql = "SELECT payload FROM audit_events"
        params: tuple[object, ...] = ()
        if resource:
            sql += " WHERE resource = %s"
            params = (resource,)
        sql += " ORDER BY created_at DESC LIMIT %s"
        params = (*params, limit)

        with self._connect() as connection:
            rows = connection.execute(sql, params).fetchall()
        return [AuditEvent.model_validate(_payload_to_dict(row[0])) for row in rows]
