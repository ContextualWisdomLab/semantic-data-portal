from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .contracts import AuditEvent, PolicyDecision


_SQLITE_POLICY_COLUMN_RENAMES = (
    ("subject", "policy_subject", "ALTER TABLE policy_decisions RENAME COLUMN subject TO policy_subject"),
    ("resource", "policy_resource", "ALTER TABLE policy_decisions RENAME COLUMN resource TO policy_resource"),
    ("action", "policy_action", "ALTER TABLE policy_decisions RENAME COLUMN action TO policy_action"),
    ("effect", "policy_effect", "ALTER TABLE policy_decisions RENAME COLUMN effect TO policy_effect"),
    ("payload", "decision_payload", "ALTER TABLE policy_decisions RENAME COLUMN payload TO decision_payload"),
)
_SQLITE_AUDIT_COLUMN_RENAMES = (
    ("id", "audit_event_id", "ALTER TABLE audit_events RENAME COLUMN id TO audit_event_id"),
    ("actor", "audit_actor", "ALTER TABLE audit_events RENAME COLUMN actor TO audit_actor"),
    ("action", "audit_action", "ALTER TABLE audit_events RENAME COLUMN action TO audit_action"),
    ("resource", "audit_resource", "ALTER TABLE audit_events RENAME COLUMN resource TO audit_resource"),
    ("result", "audit_result", "ALTER TABLE audit_events RENAME COLUMN result TO audit_result"),
    ("payload", "audit_payload", "ALTER TABLE audit_events RENAME COLUMN payload TO audit_payload"),
)

_POSTGRES_SEMANTIC_COLUMN_MIGRATION = """
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema() AND table_name = 'policy_decisions' AND column_name = 'subject'
    ) THEN
        IF EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = current_schema() AND table_name = 'policy_decisions' AND column_name = 'policy_subject'
        ) THEN
            RAISE EXCEPTION 'policy_decisions has both subject and policy_subject; refusing ambiguous migration';
        END IF;
        ALTER TABLE policy_decisions RENAME COLUMN subject TO policy_subject;
    END IF;
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema() AND table_name = 'policy_decisions' AND column_name = 'resource'
    ) THEN
        IF EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = current_schema() AND table_name = 'policy_decisions' AND column_name = 'policy_resource'
        ) THEN
            RAISE EXCEPTION 'policy_decisions has both resource and policy_resource; refusing ambiguous migration';
        END IF;
        ALTER TABLE policy_decisions RENAME COLUMN resource TO policy_resource;
    END IF;
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema() AND table_name = 'policy_decisions' AND column_name = 'action'
    ) THEN
        IF EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = current_schema() AND table_name = 'policy_decisions' AND column_name = 'policy_action'
        ) THEN
            RAISE EXCEPTION 'policy_decisions has both action and policy_action; refusing ambiguous migration';
        END IF;
        ALTER TABLE policy_decisions RENAME COLUMN action TO policy_action;
    END IF;
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema() AND table_name = 'policy_decisions' AND column_name = 'effect'
    ) THEN
        IF EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = current_schema() AND table_name = 'policy_decisions' AND column_name = 'policy_effect'
        ) THEN
            RAISE EXCEPTION 'policy_decisions has both effect and policy_effect; refusing ambiguous migration';
        END IF;
        ALTER TABLE policy_decisions RENAME COLUMN effect TO policy_effect;
    END IF;
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema() AND table_name = 'policy_decisions' AND column_name = 'payload'
    ) THEN
        IF EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = current_schema() AND table_name = 'policy_decisions' AND column_name = 'decision_payload'
        ) THEN
            RAISE EXCEPTION 'policy_decisions has both payload and decision_payload; refusing ambiguous migration';
        END IF;
        ALTER TABLE policy_decisions RENAME COLUMN payload TO decision_payload;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema() AND table_name = 'audit_events' AND column_name = 'id'
    ) THEN
        IF EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = current_schema() AND table_name = 'audit_events' AND column_name = 'audit_event_id'
        ) THEN
            RAISE EXCEPTION 'audit_events has both id and audit_event_id; refusing ambiguous migration';
        END IF;
        ALTER TABLE audit_events RENAME COLUMN id TO audit_event_id;
    END IF;
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema() AND table_name = 'audit_events' AND column_name = 'actor'
    ) THEN
        IF EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = current_schema() AND table_name = 'audit_events' AND column_name = 'audit_actor'
        ) THEN
            RAISE EXCEPTION 'audit_events has both actor and audit_actor; refusing ambiguous migration';
        END IF;
        ALTER TABLE audit_events RENAME COLUMN actor TO audit_actor;
    END IF;
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema() AND table_name = 'audit_events' AND column_name = 'action'
    ) THEN
        IF EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = current_schema() AND table_name = 'audit_events' AND column_name = 'audit_action'
        ) THEN
            RAISE EXCEPTION 'audit_events has both action and audit_action; refusing ambiguous migration';
        END IF;
        ALTER TABLE audit_events RENAME COLUMN action TO audit_action;
    END IF;
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema() AND table_name = 'audit_events' AND column_name = 'resource'
    ) THEN
        IF EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = current_schema() AND table_name = 'audit_events' AND column_name = 'audit_resource'
        ) THEN
            RAISE EXCEPTION 'audit_events has both resource and audit_resource; refusing ambiguous migration';
        END IF;
        ALTER TABLE audit_events RENAME COLUMN resource TO audit_resource;
    END IF;
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema() AND table_name = 'audit_events' AND column_name = 'result'
    ) THEN
        IF EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = current_schema() AND table_name = 'audit_events' AND column_name = 'audit_result'
        ) THEN
            RAISE EXCEPTION 'audit_events has both result and audit_result; refusing ambiguous migration';
        END IF;
        ALTER TABLE audit_events RENAME COLUMN result TO audit_result;
    END IF;
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema() AND table_name = 'audit_events' AND column_name = 'payload'
    ) THEN
        IF EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = current_schema() AND table_name = 'audit_events' AND column_name = 'audit_payload'
        ) THEN
            RAISE EXCEPTION 'audit_events has both payload and audit_payload; refusing ambiguous migration';
        END IF;
        ALTER TABLE audit_events RENAME COLUMN payload TO audit_payload;
    END IF;
END $$;
"""


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


def _sqlite_column_names(connection: sqlite3.Connection, pragma_sql: str) -> set[str]:
    return {str(column_row[1]) for column_row in connection.execute(pragma_sql)}


def _rename_sqlite_columns(
    connection: sqlite3.Connection,
    existing_columns: set[str],
    rename_specs: tuple[tuple[str, str, str], ...],
) -> None:
    for legacy_name, semantic_name, rename_sql in rename_specs:
        if legacy_name not in existing_columns:
            continue
        if semantic_name in existing_columns:
            raise RuntimeError(
                f"database has both {legacy_name} and {semantic_name}; refusing ambiguous migration"
            )
        connection.execute(rename_sql)
        existing_columns.remove(legacy_name)
        existing_columns.add(semantic_name)


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
                    policy_subject TEXT NOT NULL,
                    policy_resource TEXT NOT NULL,
                    policy_action TEXT NOT NULL,
                    policy_effect TEXT NOT NULL,
                    decision_payload TEXT NOT NULL,
                    recorded_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_events (
                    audit_event_id TEXT PRIMARY KEY,
                    audit_actor TEXT NOT NULL,
                    audit_action TEXT NOT NULL,
                    audit_resource TEXT NOT NULL,
                    audit_result TEXT NOT NULL,
                    decision_id TEXT,
                    audit_payload TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            policy_columns = _sqlite_column_names(
                connection,
                "PRAGMA table_info(policy_decisions)",
            )
            audit_columns = _sqlite_column_names(
                connection,
                "PRAGMA table_info(audit_events)",
            )
            _rename_sqlite_columns(
                connection,
                policy_columns,
                _SQLITE_POLICY_COLUMN_RENAMES,
            )
            _rename_sqlite_columns(
                connection,
                audit_columns,
                _SQLITE_AUDIT_COLUMN_RENAMES,
            )

    def record_decision(self, decision: PolicyDecision) -> PolicyDecision:
        decision_payload = decision.model_dump(mode="json")
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO policy_decisions
                (decision_id, policy_subject, policy_resource, policy_action, policy_effect, decision_payload, recorded_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    decision.decision_id,
                    decision.subject,
                    decision.resource,
                    decision.action,
                    decision.effect,
                    json.dumps(decision_payload, ensure_ascii=False, sort_keys=True),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
        return decision

    def get_decision(self, decision_id: str) -> PolicyDecision | None:
        with self._connect() as connection:
            decision_row = connection.execute(
                "SELECT decision_payload FROM policy_decisions WHERE decision_id = ?",
                (decision_id,),
            ).fetchone()
        if not decision_row:
            return None
        return PolicyDecision.model_validate(json.loads(decision_row[0]))

    def list_decisions(self, *, resource: str | None = None, limit: int = 100) -> list[PolicyDecision]:
        query_sql = "SELECT decision_payload FROM policy_decisions"
        query_parameters: tuple[object, ...] = ()
        if resource:
            query_sql += " WHERE policy_resource = ?"
            query_parameters = (resource,)
        query_sql += " ORDER BY recorded_at DESC LIMIT ?"
        query_parameters = (*query_parameters, limit)

        with self._connect() as connection:
            decision_rows = connection.execute(query_sql, query_parameters).fetchall()
        return [PolicyDecision.model_validate(json.loads(decision_row[0])) for decision_row in decision_rows]

    def append_event(self, event: AuditEvent) -> AuditEvent:
        audit_payload = event.model_dump(mode="json")
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO audit_events
                (audit_event_id, audit_actor, audit_action, audit_resource, audit_result, decision_id, audit_payload, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.id,
                    event.actor,
                    event.action,
                    event.resource,
                    event.result,
                    event.decision_id,
                    json.dumps(audit_payload, ensure_ascii=False, sort_keys=True),
                    event.created_at.isoformat(),
                ),
            )
        return event

    def list_events(self, *, resource: str | None = None, limit: int = 100) -> list[AuditEvent]:
        query_sql = "SELECT audit_payload FROM audit_events"
        query_parameters: tuple[object, ...] = ()
        if resource:
            query_sql += " WHERE audit_resource = ?"
            query_parameters = (resource,)
        query_sql += " ORDER BY created_at DESC LIMIT ?"
        query_parameters = (*query_parameters, limit)

        with self._connect() as connection:
            audit_rows = connection.execute(query_sql, query_parameters).fetchall()
        return [AuditEvent.model_validate(json.loads(audit_row[0])) for audit_row in audit_rows]


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

        connection_options: dict[str, str] = {}
        if self.sslmode and "sslmode=" not in self.dsn:
            connection_options["sslmode"] = self.sslmode
        return connect_factory(self.dsn, **connection_options)

    def _jsonb(self, evidence_payload: dict[str, Any]) -> Any:
        try:
            from psycopg.types.json import Jsonb
        except Exception:
            return evidence_payload
        return Jsonb(evidence_payload)

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS policy_decisions (
                    decision_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    policy_subject TEXT NOT NULL,
                    policy_resource TEXT NOT NULL,
                    policy_action TEXT NOT NULL,
                    policy_effect TEXT NOT NULL,
                    decision_payload JSONB NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_events (
                    audit_event_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    audit_actor TEXT NOT NULL,
                    audit_action TEXT NOT NULL,
                    audit_resource TEXT NOT NULL,
                    audit_result TEXT NOT NULL,
                    decision_id TEXT,
                    audit_payload JSONB NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL
                )
                """
            )
            connection.execute(_POSTGRES_SEMANTIC_COLUMN_MIGRATION)
            connection.execute("ALTER TABLE policy_decisions ADD COLUMN IF NOT EXISTS tenant_id TEXT")
            connection.execute("ALTER TABLE policy_decisions ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ")
            connection.execute(
                """
                UPDATE policy_decisions
                SET tenant_id = COALESCE(NULLIF(tenant_id, ''), decision_payload -> 'obligations' ->> 'tenant_id', 'demo')
                WHERE tenant_id IS NULL OR tenant_id = ''
                """
            )
            connection.execute(
                """
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_schema = current_schema() AND table_name = 'policy_decisions' AND column_name = 'recorded_at'
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
                        WHERE table_schema = current_schema() AND table_name = 'policy_decisions' AND column_name = 'recorded_at'
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
                SET tenant_id = COALESCE(NULLIF(tenant_id, ''), audit_payload -> 'details' ->> 'tenant_id', 'demo')
                WHERE tenant_id IS NULL OR tenant_id = ''
                """
            )
            connection.execute("ALTER TABLE audit_events ALTER COLUMN tenant_id SET NOT NULL")
            connection.execute("DROP INDEX IF EXISTS idx_policy_decisions_tenant_resource_created")
            connection.execute("DROP INDEX IF EXISTS idx_audit_events_tenant_resource_created")
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_policy_decisions_tenant_policy_resource_created ON policy_decisions (tenant_id, policy_resource, created_at DESC)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_audit_events_tenant_audit_resource_created ON audit_events (tenant_id, audit_resource, created_at DESC)"
            )

    def record_decision(self, decision: PolicyDecision) -> PolicyDecision:
        decision_payload = decision.model_dump(mode="json")
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO policy_decisions
                (decision_id, tenant_id, policy_subject, policy_resource, policy_action, policy_effect, decision_payload, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (decision_id) DO UPDATE SET
                    tenant_id = EXCLUDED.tenant_id,
                    policy_subject = EXCLUDED.policy_subject,
                    policy_resource = EXCLUDED.policy_resource,
                    policy_action = EXCLUDED.policy_action,
                    policy_effect = EXCLUDED.policy_effect,
                    decision_payload = EXCLUDED.decision_payload,
                    created_at = EXCLUDED.created_at
                """,
                (
                    decision.decision_id,
                    _policy_tenant_id(decision),
                    decision.subject,
                    decision.resource,
                    decision.action,
                    decision.effect,
                    self._jsonb(decision_payload),
                    datetime.now(timezone.utc),
                ),
            )
        return decision

    def get_decision(self, decision_id: str) -> PolicyDecision | None:
        with self._connect() as connection:
            decision_row = connection.execute(
                "SELECT decision_payload FROM policy_decisions WHERE decision_id = %s",
                (decision_id,),
            ).fetchone()
        if not decision_row:
            return None
        return PolicyDecision.model_validate(_payload_to_dict(decision_row[0]))

    def list_decisions(self, *, resource: str | None = None, limit: int = 100) -> list[PolicyDecision]:
        query_sql = "SELECT decision_payload FROM policy_decisions"
        query_parameters: tuple[object, ...] = ()
        if resource:
            query_sql += " WHERE policy_resource = %s"
            query_parameters = (resource,)
        query_sql += " ORDER BY created_at DESC LIMIT %s"
        query_parameters = (*query_parameters, limit)

        with self._connect() as connection:
            decision_rows = connection.execute(query_sql, query_parameters).fetchall()
        return [PolicyDecision.model_validate(_payload_to_dict(decision_row[0])) for decision_row in decision_rows]

    def append_event(self, event: AuditEvent) -> AuditEvent:
        audit_payload = event.model_dump(mode="json")
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO audit_events
                (audit_event_id, tenant_id, audit_actor, audit_action, audit_resource, audit_result, decision_id, audit_payload, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (audit_event_id) DO UPDATE SET
                    tenant_id = EXCLUDED.tenant_id,
                    audit_actor = EXCLUDED.audit_actor,
                    audit_action = EXCLUDED.audit_action,
                    audit_resource = EXCLUDED.audit_resource,
                    audit_result = EXCLUDED.audit_result,
                    decision_id = EXCLUDED.decision_id,
                    audit_payload = EXCLUDED.audit_payload,
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
                    self._jsonb(audit_payload),
                    event.created_at,
                ),
            )
        return event

    def list_events(self, *, resource: str | None = None, limit: int = 100) -> list[AuditEvent]:
        query_sql = "SELECT audit_payload FROM audit_events"
        query_parameters: tuple[object, ...] = ()
        if resource:
            query_sql += " WHERE audit_resource = %s"
            query_parameters = (resource,)
        query_sql += " ORDER BY created_at DESC LIMIT %s"
        query_parameters = (*query_parameters, limit)

        with self._connect() as connection:
            audit_rows = connection.execute(query_sql, query_parameters).fetchall()
        return [AuditEvent.model_validate(_payload_to_dict(audit_row[0])) for audit_row in audit_rows]
