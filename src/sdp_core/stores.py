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


# Marker for an evidence row whose owning tenant could not be resolved.
#
# ``demo`` is a real tenant in this product - the seeded datasets live in it -
# so defaulting to it does not merely lose information, it files the row under
# somebody else's tenant. Since ``PostgresEvidenceStore`` declares
# ``tenant_id TEXT NOT NULL`` and indexes it first, a tenant-scoped reader would
# then see rows that are not theirs and miss rows that are. An unattributable
# row is marked instead, so it is claimed by no tenant and stays visible as a
# data-quality signal.
UNRESOLVED_TENANT_ID = "unresolved"


def _policy_tenant_id(decision: PolicyDecision) -> str:
    """Resolve the tenant a policy-decision row belongs to, or mark it unresolved."""
    return str(decision.obligations.get("tenant_id") or UNRESOLVED_TENANT_ID)


def _audit_tenant_id(event: AuditEvent) -> str:
    """Resolve the tenant an audit row belongs to, or mark it unresolved."""
    return str(event.details.get("tenant_id") or event.details.get("tenant") or UNRESOLVED_TENANT_ID)


def _tenant_scope_clause(
    tenant_ids: list[str] | None, placeholder: str
) -> tuple[str, tuple[object, ...]]:
    """Build the tenant predicate for an evidence read.

    ``None`` means "every tenant" and is reserved for the explicit platform-admin
    crossing; an empty list means "no tenant", which yields no rows rather than
    all of them - a reader with no resolvable tenant must not fall through to an
    unscoped read.
    """
    if tenant_ids is None:
        return "", ()
    if not tenant_ids:
        return "1 = 0", ()
    marks = ", ".join(placeholder for _ in tenant_ids)
    return f"tenant_id IN ({marks})", tuple(tenant_ids)


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
                f"""
                CREATE TABLE IF NOT EXISTS policy_decisions (
                    decision_id TEXT PRIMARY KEY,
                    subject TEXT NOT NULL,
                    resource TEXT NOT NULL,
                    action TEXT NOT NULL,
                    effect TEXT NOT NULL,
                    tenant_id TEXT NOT NULL DEFAULT '{UNRESOLVED_TENANT_ID}',
                    payload TEXT NOT NULL,
                    recorded_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                f"""
                CREATE TABLE IF NOT EXISTS audit_events (
                    id TEXT PRIMARY KEY,
                    actor TEXT NOT NULL,
                    action TEXT NOT NULL,
                    resource TEXT NOT NULL,
                    result TEXT NOT NULL,
                    decision_id TEXT,
                    tenant_id TEXT NOT NULL DEFAULT '{UNRESOLVED_TENANT_ID}',
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            self._add_tenant_column(connection, "policy_decisions")
            self._add_tenant_column(connection, "audit_events")
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_sqlite_decisions_tenant_resource "
                "ON policy_decisions (tenant_id, resource)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_sqlite_events_tenant_resource "
                "ON audit_events (tenant_id, resource)"
            )

    # Where each table's legacy rows keep their tenant inside the stored payload.
    # ``_audit_tenant_id`` honours ``details.tenant`` as well as
    # ``details.tenant_id``, so the backfill honours both - the Postgres
    # equivalent reads only ``tenant_id`` and silently drops the other spelling.
    _TENANT_BACKFILL_PATHS = {
        "policy_decisions": ("$.obligations.tenant_id",),
        "audit_events": ("$.details.tenant_id", "$.details.tenant"),
    }

    def _add_tenant_column(self, connection: Any, table: str) -> None:
        """Add ``tenant_id`` to an evidence table created before it existed, and backfill it.

        SQLite has no ``ADD COLUMN IF NOT EXISTS``, so the column list is read
        first.

        The backfill is the point. This method used to add the column with the
        unresolved default and stop, while ``PostgresEvidenceStore._initialize``
        recovers the tenant from the stored payload
        (``COALESCE(..., payload -> 'obligations' ->> 'tenant_id', ...)``). The
        two backends ship as protocol-equivalent - ``docker-compose`` runs an
        instance of each to check exactly that - so the same upgrade on the same
        row produced ``unresolved`` on SQLite and ``demo`` on Postgres. Measured
        on a hand-built pre-tenant_id database whose payloads carry
        ``tenant_id: "demo"``::

            after upgrade, policy_decisions.tenant_id -> ['unresolved']
            after upgrade, audit_events.tenant_id     -> ['unresolved']

        On SQLite the row then becomes invisible to its owning tenant's auditor
        (``GET /audit/events``, ``GET /policy/decisions``,
        ``GET /catalog/datasets/{id}/audit``) and visible only to platform-admin
        - the ledger loses recoverable attribution for all of its history. And
        SQLite is the documented demo/pilot deployment
        (``SDP_SQLITE_PATH=/data/sdp-evidence.sqlite3`` on a persistent volume),
        i.e. precisely the upgrade-in-place case.
        """
        columns = {row[1] for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}
        if "tenant_id" in columns:
            return
        connection.execute(
            f"ALTER TABLE {table} ADD COLUMN tenant_id TEXT NOT NULL "
            f"DEFAULT '{UNRESOLVED_TENANT_ID}'"
        )
        paths = self._TENANT_BACKFILL_PATHS.get(table, ())
        if not paths:
            return
        extracted = ", ".join(f"NULLIF(json_extract(payload, '{path}'), '')" for path in paths)
        connection.execute(
            f"UPDATE {table} SET tenant_id = COALESCE({extracted}, '{UNRESOLVED_TENANT_ID}') "
            f"WHERE tenant_id = '{UNRESOLVED_TENANT_ID}' OR tenant_id IS NULL OR tenant_id = ''"
        )

    def record_decision(self, decision: PolicyDecision) -> PolicyDecision:
        payload = decision.model_dump(mode="json")
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO policy_decisions
                (decision_id, subject, resource, action, effect, tenant_id, payload, recorded_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    decision.decision_id,
                    decision.subject,
                    decision.resource,
                    decision.action,
                    decision.effect,
                    _policy_tenant_id(decision),
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

    def list_decisions(
        self,
        *,
        resource: str | None = None,
        limit: int = 100,
        tenant_ids: list[str] | None = None,
    ) -> list[PolicyDecision]:
        """List policy decisions, optionally scoped to a set of tenants."""
        conditions: list[str] = []
        params: tuple[object, ...] = ()
        if resource:
            conditions.append("resource = ?")
            params = (*params, resource)
        clause, tenant_params = _tenant_scope_clause(tenant_ids, "?")
        if clause:
            conditions.append(clause)
            params = (*params, *tenant_params)
        sql = "SELECT payload FROM policy_decisions"
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
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
                (id, actor, action, resource, result, decision_id, tenant_id, payload, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.id,
                    event.actor,
                    event.action,
                    event.resource,
                    event.result,
                    event.decision_id,
                    _audit_tenant_id(event),
                    json.dumps(payload, ensure_ascii=False, sort_keys=True),
                    event.created_at.isoformat(),
                ),
            )
        return event

    def list_events(
        self,
        *,
        resource: str | None = None,
        limit: int = 100,
        tenant_ids: list[str] | None = None,
    ) -> list[AuditEvent]:
        """List audit events, optionally scoped to a set of tenants."""
        conditions: list[str] = []
        params: tuple[object, ...] = ()
        if resource:
            conditions.append("resource = ?")
            params = (*params, resource)
        clause, tenant_params = _tenant_scope_clause(tenant_ids, "?")
        if clause:
            conditions.append(clause)
            params = (*params, *tenant_params)
        sql = "SELECT payload FROM audit_events"
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
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
                f"""
                UPDATE policy_decisions
                SET tenant_id = COALESCE(
                    NULLIF(tenant_id, ''),
                    NULLIF(payload -> 'obligations' ->> 'tenant_id', ''),
                    '{UNRESOLVED_TENANT_ID}'
                )
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
                f"""
                UPDATE audit_events
                SET tenant_id = COALESCE(
                    NULLIF(tenant_id, ''),
                    NULLIF(payload -> 'details' ->> 'tenant_id', ''),
                    -- ``_audit_tenant_id`` honours this spelling too, so a row
                    -- carrying only ``details.tenant`` was being dropped to
                    -- unresolved by the backfill that is supposed to recover it.
                    NULLIF(payload -> 'details' ->> 'tenant', ''),
                    '{UNRESOLVED_TENANT_ID}'
                )
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

    def list_decisions(
        self,
        *,
        resource: str | None = None,
        limit: int = 100,
        tenant_ids: list[str] | None = None,
    ) -> list[PolicyDecision]:
        """List policy decisions, optionally scoped to a set of tenants.

        The tenant predicate leads ``idx_policy_decisions_tenant_resource_created``,
        which is why that index is ordered tenant-first.
        """
        conditions: list[str] = []
        params: tuple[object, ...] = ()
        if resource:
            conditions.append("resource = %s")
            params = (*params, resource)
        clause, tenant_params = _tenant_scope_clause(tenant_ids, "%s")
        if clause:
            conditions.append(clause)
            params = (*params, *tenant_params)
        sql = "SELECT payload FROM policy_decisions"
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
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

    def list_events(
        self,
        *,
        resource: str | None = None,
        limit: int = 100,
        tenant_ids: list[str] | None = None,
    ) -> list[AuditEvent]:
        """List audit events, optionally scoped to a set of tenants.

        The tenant predicate leads ``idx_audit_events_tenant_resource_created``,
        which is why that index is ordered tenant-first.
        """
        conditions: list[str] = []
        params: tuple[object, ...] = ()
        if resource:
            conditions.append("resource = %s")
            params = (*params, resource)
        clause, tenant_params = _tenant_scope_clause(tenant_ids, "%s")
        if clause:
            conditions.append(clause)
            params = (*params, *tenant_params)
        sql = "SELECT payload FROM audit_events"
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        sql += " ORDER BY created_at DESC LIMIT %s"
        params = (*params, limit)

        with self._connect() as connection:
            rows = connection.execute(sql, params).fetchall()
        return [AuditEvent.model_validate(_payload_to_dict(row[0])) for row in rows]
