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


def _audit_tenant_id(audit_event: AuditEvent) -> str:
    return str(
        audit_event.audit_details.get("tenant_id")
        or audit_event.audit_details.get("tenant")
        or "demo"
    )


def _audit_resource_reference(
    resource_reference: str | None,
    compatibility_filters: dict[str, object],
) -> str | None:
    """Translate the legacy ``resource=`` filter at the store adapter boundary."""

    legacy_resource = compatibility_filters.pop("resource", None)
    if compatibility_filters:
        unexpected_names = ", ".join(sorted(compatibility_filters))
        raise TypeError(f"unexpected audit-event filter(s): {unexpected_names}")
    if resource_reference is not None and legacy_resource is not None:
        if resource_reference != legacy_resource:
            raise TypeError("resource_reference and legacy resource filter disagree")
    if resource_reference is not None:
        return resource_reference
    if legacy_resource is None:
        return None
    return str(legacy_resource)


class SQLiteEvidenceStore:
    """Local evidence store for demo and pilot auditability."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    @staticmethod
    def _migrate_audit_event_columns(connection: sqlite3.Connection) -> None:
        """Rename legacy audit columns transactionally without rewriting event rows."""

        column_names = {
            column_row[1]
            for column_row in connection.execute("PRAGMA table_info(audit_events)").fetchall()
        }
        if "id" in column_names and "audit_event_id" not in column_names:
            connection.execute("ALTER TABLE audit_events RENAME COLUMN id TO audit_event_id")
        if "actor" in column_names and "actor_subject" not in column_names:
            connection.execute("ALTER TABLE audit_events RENAME COLUMN actor TO actor_subject")
        if "action" in column_names and "audit_action" not in column_names:
            connection.execute("ALTER TABLE audit_events RENAME COLUMN action TO audit_action")
        if "resource" in column_names and "resource_reference" not in column_names:
            connection.execute(
                "ALTER TABLE audit_events RENAME COLUMN resource TO resource_reference"
            )
        if "result" in column_names and "audit_result" not in column_names:
            connection.execute("ALTER TABLE audit_events RENAME COLUMN result TO audit_result")
        if "decision_id" in column_names and "policy_decision_id" not in column_names:
            connection.execute(
                "ALTER TABLE audit_events RENAME COLUMN decision_id TO policy_decision_id"
            )
        if "payload" in column_names and "event_payload" not in column_names:
            connection.execute("ALTER TABLE audit_events RENAME COLUMN payload TO event_payload")

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
                    audit_event_id TEXT PRIMARY KEY,
                    actor_subject TEXT NOT NULL,
                    audit_action TEXT NOT NULL,
                    resource_reference TEXT NOT NULL,
                    audit_result TEXT NOT NULL,
                    policy_decision_id TEXT,
                    event_payload TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            self._migrate_audit_event_columns(connection)

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

    def append_event(self, audit_event: AuditEvent) -> AuditEvent:
        audit_event_payload = audit_event.model_dump(mode="json", by_alias=True)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO audit_events
                (audit_event_id, actor_subject, audit_action, resource_reference,
                 audit_result, policy_decision_id, event_payload, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    audit_event.audit_event_id,
                    audit_event.actor_subject,
                    audit_event.audit_action,
                    audit_event.resource_reference,
                    audit_event.audit_result,
                    audit_event.policy_decision_id,
                    json.dumps(audit_event_payload, ensure_ascii=False, sort_keys=True),
                    audit_event.created_at.isoformat(),
                ),
            )
        return audit_event

    def list_events(
        self,
        *,
        resource_reference: str | None = None,
        limit: int = 100,
        **compatibility_filters: object,
    ) -> list[AuditEvent]:
        resource_reference = _audit_resource_reference(
            resource_reference, compatibility_filters
        )
        sql = "SELECT event_payload FROM audit_events"
        params: tuple[object, ...] = ()
        if resource_reference:
            sql += " WHERE resource_reference = ?"
            params = (resource_reference,)
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
                    audit_event_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    actor_subject TEXT NOT NULL,
                    audit_action TEXT NOT NULL,
                    resource_reference TEXT NOT NULL,
                    audit_result TEXT NOT NULL,
                    policy_decision_id TEXT,
                    event_payload JSONB NOT NULL,
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
            connection.execute(
                """
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'audit_events' AND column_name = 'id'
                    ) AND NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'audit_events' AND column_name = 'audit_event_id'
                    ) THEN
                        ALTER TABLE audit_events RENAME COLUMN id TO audit_event_id;
                    END IF;
                    IF EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'audit_events' AND column_name = 'actor'
                    ) AND NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'audit_events' AND column_name = 'actor_subject'
                    ) THEN
                        ALTER TABLE audit_events RENAME COLUMN actor TO actor_subject;
                    END IF;
                    IF EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'audit_events' AND column_name = 'action'
                    ) AND NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'audit_events' AND column_name = 'audit_action'
                    ) THEN
                        ALTER TABLE audit_events RENAME COLUMN action TO audit_action;
                    END IF;
                    IF EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'audit_events' AND column_name = 'resource'
                    ) AND NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'audit_events' AND column_name = 'resource_reference'
                    ) THEN
                        ALTER TABLE audit_events RENAME COLUMN resource TO resource_reference;
                    END IF;
                    IF EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'audit_events' AND column_name = 'result'
                    ) AND NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'audit_events' AND column_name = 'audit_result'
                    ) THEN
                        ALTER TABLE audit_events RENAME COLUMN result TO audit_result;
                    END IF;
                    IF EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'audit_events' AND column_name = 'decision_id'
                    ) AND NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'audit_events' AND column_name = 'policy_decision_id'
                    ) THEN
                        ALTER TABLE audit_events RENAME COLUMN decision_id TO policy_decision_id;
                    END IF;
                    IF EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'audit_events' AND column_name = 'payload'
                    ) AND NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'audit_events' AND column_name = 'event_payload'
                    ) THEN
                        ALTER TABLE audit_events RENAME COLUMN payload TO event_payload;
                    END IF;
                END $$;
                """
            )
            connection.execute("ALTER TABLE audit_events ADD COLUMN IF NOT EXISTS tenant_id TEXT")
            connection.execute(
                """
                UPDATE audit_events
                SET tenant_id = COALESCE(NULLIF(tenant_id, ''), event_payload -> 'details' ->> 'tenant_id', 'demo')
                WHERE tenant_id IS NULL OR tenant_id = ''
                """
            )
            connection.execute("ALTER TABLE audit_events ALTER COLUMN tenant_id SET NOT NULL")
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_policy_decisions_tenant_resource_created ON policy_decisions (tenant_id, resource, created_at DESC)"
            )
            connection.execute("DROP INDEX IF EXISTS idx_audit_events_tenant_resource_created")
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_audit_events_tenant_resource_reference_created ON audit_events (tenant_id, resource_reference, created_at DESC)"
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

    def append_event(self, audit_event: AuditEvent) -> AuditEvent:
        audit_event_payload = audit_event.model_dump(mode="json", by_alias=True)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO audit_events
                (audit_event_id, tenant_id, actor_subject, audit_action, resource_reference,
                 audit_result, policy_decision_id, event_payload, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (audit_event_id) DO UPDATE SET
                    tenant_id = EXCLUDED.tenant_id,
                    actor_subject = EXCLUDED.actor_subject,
                    audit_action = EXCLUDED.audit_action,
                    resource_reference = EXCLUDED.resource_reference,
                    audit_result = EXCLUDED.audit_result,
                    policy_decision_id = EXCLUDED.policy_decision_id,
                    event_payload = EXCLUDED.event_payload,
                    created_at = EXCLUDED.created_at
                """,
                (
                    audit_event.audit_event_id,
                    _audit_tenant_id(audit_event),
                    audit_event.actor_subject,
                    audit_event.audit_action,
                    audit_event.resource_reference,
                    audit_event.audit_result,
                    audit_event.policy_decision_id,
                    self._jsonb(audit_event_payload),
                    audit_event.created_at,
                ),
            )
        return audit_event

    def list_events(
        self,
        *,
        resource_reference: str | None = None,
        limit: int = 100,
        **compatibility_filters: object,
    ) -> list[AuditEvent]:
        resource_reference = _audit_resource_reference(
            resource_reference, compatibility_filters
        )
        sql = "SELECT event_payload FROM audit_events"
        params: tuple[object, ...] = ()
        if resource_reference:
            sql += " WHERE resource_reference = %s"
            params = (resource_reference,)
        sql += " ORDER BY created_at DESC LIMIT %s"
        params = (*params, limit)

        with self._connect() as connection:
            rows = connection.execute(sql, params).fetchall()
        return [AuditEvent.model_validate(_payload_to_dict(row[0])) for row in rows]
