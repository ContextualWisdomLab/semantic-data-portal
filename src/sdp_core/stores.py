from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .contracts import AuditEvent, PolicyDecision


_POLICY_DECISION_COLUMN_RENAMES = (
    ("subject", "decision_subject"),
    ("resource", "policy_resource"),
    ("action", "policy_action"),
    ("effect", "decision_effect"),
    ("payload", "decision_payload"),
)
_AUDIT_EVENT_COLUMN_RENAMES = (
    ("id", "audit_event_id"),
    ("actor", "actor_subject"),
    ("action", "audit_action"),
    ("resource", "audit_resource"),
    ("result", "audit_result"),
    ("payload", "audit_payload"),
)
_SQLITE_TABLE_INFO_QUERIES = {
    "policy_decisions": 'PRAGMA table_info("policy_decisions")',
    "audit_events": 'PRAGMA table_info("audit_events")',
}
_EVIDENCE_COLUMN_RENAME_SQL = {
    ("policy_decisions", "subject", "decision_subject"): (
        'ALTER TABLE "policy_decisions" RENAME COLUMN "subject" TO "decision_subject"'
    ),
    ("policy_decisions", "resource", "policy_resource"): (
        'ALTER TABLE "policy_decisions" RENAME COLUMN "resource" TO "policy_resource"'
    ),
    ("policy_decisions", "action", "policy_action"): (
        'ALTER TABLE "policy_decisions" RENAME COLUMN "action" TO "policy_action"'
    ),
    ("policy_decisions", "effect", "decision_effect"): (
        'ALTER TABLE "policy_decisions" RENAME COLUMN "effect" TO "decision_effect"'
    ),
    ("policy_decisions", "payload", "decision_payload"): (
        'ALTER TABLE "policy_decisions" RENAME COLUMN "payload" TO "decision_payload"'
    ),
    ("audit_events", "id", "audit_event_id"): (
        'ALTER TABLE "audit_events" RENAME COLUMN "id" TO "audit_event_id"'
    ),
    ("audit_events", "actor", "actor_subject"): (
        'ALTER TABLE "audit_events" RENAME COLUMN "actor" TO "actor_subject"'
    ),
    ("audit_events", "action", "audit_action"): (
        'ALTER TABLE "audit_events" RENAME COLUMN "action" TO "audit_action"'
    ),
    ("audit_events", "resource", "audit_resource"): (
        'ALTER TABLE "audit_events" RENAME COLUMN "resource" TO "audit_resource"'
    ),
    ("audit_events", "result", "audit_result"): (
        'ALTER TABLE "audit_events" RENAME COLUMN "result" TO "audit_result"'
    ),
    ("audit_events", "payload", "audit_payload"): (
        'ALTER TABLE "audit_events" RENAME COLUMN "payload" TO "audit_payload"'
    ),
}


def _payload_to_dict(evidence_payload: object) -> dict[str, Any]:
    if isinstance(evidence_payload, dict):
        return evidence_payload
    if isinstance(evidence_payload, str):
        return json.loads(evidence_payload)
    raise TypeError(f"unsupported evidence payload type: {type(evidence_payload).__name__}")


def _policy_tenant_id(policy_decision: PolicyDecision) -> str:
    return str(policy_decision.obligations.get("tenant_id") or "demo")


def _audit_tenant_id(audit_event: AuditEvent) -> str:
    return str(audit_event.details.get("tenant_id") or audit_event.details.get("tenant") or "demo")


def _closed_column_rename_sql(
    table_name: str,
    legacy_column_name: str,
    semantic_column_name: str,
) -> str:
    """Return the literal DDL for an Evidence Store-owned schema rename."""

    rename_key = (table_name, legacy_column_name, semantic_column_name)
    try:
        return _EVIDENCE_COLUMN_RENAME_SQL[rename_key]
    except KeyError as exc:
        raise ValueError(
            "unsupported evidence-store column rename: "
            f"{table_name}.{legacy_column_name}->{semantic_column_name}"
        ) from exc


def _sqlite_column_names(connection: sqlite3.Connection, table_name: str) -> set[str]:
    """Read columns only for the Evidence Store's closed SQLite table set."""

    try:
        table_info_query = _SQLITE_TABLE_INFO_QUERIES[table_name]
    except KeyError as exc:
        raise ValueError(f"unsupported evidence-store table: {table_name}") from exc
    return {
        str(column_record[1])
        for column_record in connection.execute(table_info_query).fetchall()
    }


def _migrate_sqlite_columns(
    connection: sqlite3.Connection,
    table_name: str,
    column_renames: tuple[tuple[str, str], ...],
) -> None:
    """Rename legacy evidence-store columns in place without rewriting rows."""

    current_columns = _sqlite_column_names(connection, table_name)
    for legacy_column_name, semantic_column_name in column_renames:
        rename_sql = _closed_column_rename_sql(table_name, legacy_column_name, semantic_column_name)
        legacy_exists = legacy_column_name in current_columns
        semantic_exists = semantic_column_name in current_columns
        if legacy_exists and semantic_exists:
            raise RuntimeError(
                f"ambiguous {table_name} schema contains both "
                f"{legacy_column_name} and {semantic_column_name}"
            )
        if not legacy_exists:
            continue
        connection.execute(rename_sql)
        current_columns.remove(legacy_column_name)
        current_columns.add(semantic_column_name)


def _migrate_postgres_columns(
    connection: Any,
    table_name: str,
    column_renames: tuple[tuple[str, str], ...],
) -> None:
    """Rename legacy Postgres columns and fail closed on partial dual-schema drift."""

    for legacy_column_name, semantic_column_name in column_renames:
        rename_sql = _closed_column_rename_sql(table_name, legacy_column_name, semantic_column_name)
        column_rows = connection.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = %s
              AND column_name IN (%s, %s)
            """,
            (table_name, legacy_column_name, semantic_column_name),
        ).fetchall()
        current_columns = {str(column_row[0]) for column_row in column_rows}
        legacy_exists = legacy_column_name in current_columns
        semantic_exists = semantic_column_name in current_columns
        if legacy_exists and semantic_exists:
            raise RuntimeError(
                f"ambiguous {table_name} schema contains both "
                f"{legacy_column_name} and {semantic_column_name}"
            )
        if legacy_exists:
            connection.execute(rename_sql)


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
                    decision_subject TEXT NOT NULL,
                    policy_resource TEXT NOT NULL,
                    policy_action TEXT NOT NULL,
                    decision_effect TEXT NOT NULL,
                    decision_payload TEXT NOT NULL,
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
                    audit_resource TEXT NOT NULL,
                    audit_result TEXT NOT NULL,
                    decision_id TEXT,
                    audit_payload TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            _migrate_sqlite_columns(connection, "policy_decisions", _POLICY_DECISION_COLUMN_RENAMES)
            _migrate_sqlite_columns(connection, "audit_events", _AUDIT_EVENT_COLUMN_RENAMES)

    def record_decision(self, decision: PolicyDecision) -> PolicyDecision:
        decision_payload = decision.model_dump(mode="json")
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO policy_decisions
                (decision_id, decision_subject, policy_resource, policy_action, decision_effect, decision_payload, recorded_at)
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
        decision_query = "SELECT decision_payload FROM policy_decisions"
        query_parameters: tuple[object, ...] = ()
        if resource:
            decision_query += " WHERE policy_resource = ?"
            query_parameters = (resource,)
        decision_query += " ORDER BY recorded_at DESC LIMIT ?"
        query_parameters = (*query_parameters, limit)

        with self._connect() as connection:
            decision_rows = connection.execute(decision_query, query_parameters).fetchall()
        return [PolicyDecision.model_validate(json.loads(decision_row[0])) for decision_row in decision_rows]

    def append_event(self, event: AuditEvent) -> AuditEvent:
        audit_payload = event.model_dump(mode="json")
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO audit_events
                (audit_event_id, actor_subject, audit_action, audit_resource, audit_result, decision_id, audit_payload, created_at)
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
        audit_query = "SELECT audit_payload FROM audit_events"
        query_parameters: tuple[object, ...] = ()
        if resource:
            audit_query += " WHERE audit_resource = ?"
            query_parameters = (resource,)
        audit_query += " ORDER BY created_at DESC LIMIT ?"
        query_parameters = (*query_parameters, limit)

        with self._connect() as connection:
            audit_rows = connection.execute(audit_query, query_parameters).fetchall()
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

        connection_kwargs: dict[str, str] = {}
        if self.sslmode and "sslmode=" not in self.dsn:
            connection_kwargs["sslmode"] = self.sslmode
        return connect_factory(self.dsn, **connection_kwargs)

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
                    decision_subject TEXT NOT NULL,
                    policy_resource TEXT NOT NULL,
                    policy_action TEXT NOT NULL,
                    decision_effect TEXT NOT NULL,
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
                    actor_subject TEXT NOT NULL,
                    audit_action TEXT NOT NULL,
                    audit_resource TEXT NOT NULL,
                    audit_result TEXT NOT NULL,
                    decision_id TEXT,
                    audit_payload JSONB NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL
                )
                """
            )
            _migrate_postgres_columns(connection, "policy_decisions", _POLICY_DECISION_COLUMN_RENAMES)
            _migrate_postgres_columns(connection, "audit_events", _AUDIT_EVENT_COLUMN_RENAMES)
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
                SET tenant_id = COALESCE(NULLIF(tenant_id, ''), audit_payload -> 'details' ->> 'tenant_id', 'demo')
                WHERE tenant_id IS NULL OR tenant_id = ''
                """
            )
            connection.execute("ALTER TABLE audit_events ALTER COLUMN tenant_id SET NOT NULL")
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_policy_decisions_tenant_resource_created ON policy_decisions (tenant_id, policy_resource, created_at DESC)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_audit_events_tenant_resource_created ON audit_events (tenant_id, audit_resource, created_at DESC)"
            )

    def record_decision(self, decision: PolicyDecision) -> PolicyDecision:
        decision_payload = decision.model_dump(mode="json")
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO policy_decisions
                (decision_id, tenant_id, decision_subject, policy_resource, policy_action, decision_effect, decision_payload, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (decision_id) DO UPDATE SET
                    tenant_id = EXCLUDED.tenant_id,
                    decision_subject = EXCLUDED.decision_subject,
                    policy_resource = EXCLUDED.policy_resource,
                    policy_action = EXCLUDED.policy_action,
                    decision_effect = EXCLUDED.decision_effect,
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
        decision_query = "SELECT decision_payload FROM policy_decisions"
        query_parameters: tuple[object, ...] = ()
        if resource:
            decision_query += " WHERE policy_resource = %s"
            query_parameters = (resource,)
        decision_query += " ORDER BY created_at DESC LIMIT %s"
        query_parameters = (*query_parameters, limit)

        with self._connect() as connection:
            decision_rows = connection.execute(decision_query, query_parameters).fetchall()
        return [PolicyDecision.model_validate(_payload_to_dict(decision_row[0])) for decision_row in decision_rows]

    def append_event(self, event: AuditEvent) -> AuditEvent:
        audit_payload = event.model_dump(mode="json")
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO audit_events
                (audit_event_id, tenant_id, actor_subject, audit_action, audit_resource, audit_result, decision_id, audit_payload, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (audit_event_id) DO UPDATE SET
                    tenant_id = EXCLUDED.tenant_id,
                    actor_subject = EXCLUDED.actor_subject,
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
        audit_query = "SELECT audit_payload FROM audit_events"
        query_parameters: tuple[object, ...] = ()
        if resource:
            audit_query += " WHERE audit_resource = %s"
            query_parameters = (resource,)
        audit_query += " ORDER BY created_at DESC LIMIT %s"
        query_parameters = (*query_parameters, limit)

        with self._connect() as connection:
            audit_rows = connection.execute(audit_query, query_parameters).fetchall()
        return [AuditEvent.model_validate(_payload_to_dict(audit_row[0])) for audit_row in audit_rows]
