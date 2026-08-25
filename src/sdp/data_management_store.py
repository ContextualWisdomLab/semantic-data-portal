"""Persistence backends for data-management evidence profiles.

The in-memory backend is the CI/pytest default. When ``SDP_DATABASE_DSN`` is
set, the relational backend uses migration 0003. Both backends enforce the
same tenant and uniqueness contracts and preserve observations append-only.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from threading import RLock
from typing import Any, TypeAlias

from sdp.config import load_bootstrap
from sdp_core.data_management_evidence import (
    CriticalDataElementRecord,
    DataOwnerAssignmentRecord,
    DataQualityObservationRecord,
    DataQualityRuleRecord,
)

try:
    from sqlalchemy import create_engine, event, text
    from sqlalchemy.engine import Engine
    from sqlalchemy.exc import IntegrityError
except ImportError:  # pragma: no cover - optional graph extra
    create_engine = None  # type: ignore[assignment]
    event = None  # type: ignore[assignment]
    text = None  # type: ignore[assignment]
    Engine = Any  # type: ignore[misc,assignment]

    class IntegrityError(Exception):  # type: ignore[no-redef]
        """Placeholder used only when SQLAlchemy is not installed."""


ProfileRows: TypeAlias = tuple[
    list[DataOwnerAssignmentRecord],
    list[CriticalDataElementRecord],
    list[DataQualityRuleRecord],
    list[DataQualityObservationRecord],
]

_MIGRATION_0003 = (
    Path(__file__).resolve().parents[2] / "migrations" / "0003_data_management_evidence.sql"
)
_GRAPH_EXTRA_HINT = (
    "Install the optional graph extra so SQLAlchemy can open SDP_DATABASE_DSN."
)
_MEMORY_OWNER_ROWS: dict[str, DataOwnerAssignmentRecord] = {}
_MEMORY_ELEMENT_ROWS: dict[str, CriticalDataElementRecord] = {}
_MEMORY_RULE_ROWS: dict[str, DataQualityRuleRecord] = {}
_MEMORY_OBSERVATION_ROWS: dict[str, DataQualityObservationRecord] = {}
_MEMORY_LOCK = RLock()


def _as_datetime(value: Any) -> datetime:
    """Coerce a driver timestamp or ISO string into an aware UTC datetime."""

    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)


def _sql_timestamp(value: datetime | None) -> str | None:
    """Render an optional timestamp for Postgres TIMESTAMPTZ and SQLite TEXT."""

    if value is None:
        return None
    return _as_datetime(value).isoformat()


def _open_engine(database_dsn: str) -> Engine:
    """Open a SQLAlchemy engine or fail loud when the graph extra is absent.

    SQLite engines get ``PRAGMA foreign_keys=ON`` so relational cross-tenant
    and parent-row guarantees hold during unit tests exactly as they do under
    Postgres in production.
    """

    if create_engine is None:
        raise RuntimeError(_GRAPH_EXTRA_HINT)
    engine = create_engine(database_dsn, future=True)
    if engine.dialect.name == "sqlite":

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, _connection_record) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def _decimal(value: Any) -> Decimal:
    """Coerce database numeric output into an exact Decimal."""

    return Decimal(str(value))


def _raise_unique_violation(exc: Exception, fallback: str) -> None:
    """Map relational uniqueness failures to stable buyer-facing errors."""

    detail = str(exc).lower()
    if "data_owner_assignments" in detail or "owner_subject" in detail:
        raise ValueError("duplicate data-owner assignment for this catalog object") from exc
    if "critical_data_elements" in detail or "element_key" in detail:
        raise ValueError("duplicate critical data element in this catalog object") from exc
    if "data_quality_rules" in detail or "rule_code" in detail:
        raise ValueError("duplicate data-quality rule for this critical data element") from exc
    if "data_quality_observations" in detail or "source_observation_id" in detail:
        raise ValueError("duplicate data-quality observation for this rule") from exc
    raise ValueError(fallback) from exc


def data_management_sqlite_ddl() -> str:
    """Return migration 0003 rewritten for SQLite unit-test execution."""

    sql_text = _MIGRATION_0003.read_text(encoding="utf-8")
    rewritten = (
        sql_text.replace("SET search_path = public;", "")
        .replace("TIMESTAMPTZ", "TEXT")
        .replace("DEFAULT now()", "DEFAULT CURRENT_TIMESTAMP")
    )
    statements: list[str] = []
    buffer: list[str] = []
    for line in rewritten.splitlines():
        buffer.append(line)
        if line.strip().endswith(";"):
            statement = "\n".join(buffer).strip()
            buffer = []
            if statement and "schema_migrations" not in statement:
                statements.append(statement)
    tail = "\n".join(buffer).strip()
    if tail and "schema_migrations" not in tail:
        statements.append(tail)
    return "\n\n".join(statements) + "\n"


def apply_data_management_sqlite_schema(engine: Engine) -> None:
    """Create migration 0003 table names on a SQLite test engine."""

    if text is None:  # pragma: no cover - SQLAlchemy is a dev extra
        raise RuntimeError(_GRAPH_EXTRA_HINT)
    statements: list[str] = []
    buffer: list[str] = []
    for line in data_management_sqlite_ddl().splitlines():
        stripped = line.strip()
        if stripped.startswith("--"):
            continue
        buffer.append(line)
        if stripped.endswith(";"):
            statements.append("\n".join(buffer).strip())
            buffer = []
    tail = "\n".join(buffer).strip()
    if tail:
        statements.append(tail)
    with engine.begin() as connection:
        for statement in statements:
            if statement:
                connection.execute(text(statement))


class DataManagementStore(ABC):
    """Tenant-scoped persistence surface for evidence-profile records."""

    @abstractmethod
    def insert_owner_assignment(self, record: DataOwnerAssignmentRecord) -> None:
        """Persist one effective-dated owner assignment."""

    @abstractmethod
    def insert_critical_data_element(self, record: CriticalDataElementRecord) -> None:
        """Persist one critical data element."""

    @abstractmethod
    def insert_data_quality_rule(self, record: DataQualityRuleRecord) -> None:
        """Persist one quality rule whose parent belongs to the same tenant."""

    @abstractmethod
    def insert_data_quality_observation(self, record: DataQualityObservationRecord) -> None:
        """Persist one immutable quality observation."""

    @abstractmethod
    def get_critical_data_element(
        self,
        *,
        tenant_reference: str,
        critical_data_element_id: str,
    ) -> CriticalDataElementRecord | None:
        """Return one tenant-owned critical data element."""

    @abstractmethod
    def get_data_quality_rule(
        self,
        *,
        tenant_reference: str,
        data_quality_rule_id: str,
    ) -> DataQualityRuleRecord | None:
        """Return one tenant-owned quality rule."""

    @abstractmethod
    def profile_rows(
        self,
        *,
        tenant_reference: str,
        catalog_object_id: str,
    ) -> ProfileRows:
        """Return every evidence row for one tenant-owned catalog object."""


class InMemoryDataManagementStore(DataManagementStore):
    """Process-local evidence store used when no database DSN is configured."""

    def insert_owner_assignment(self, record: DataOwnerAssignmentRecord) -> None:
        """Insert an owner assignment after enforcing its natural key."""

        with _MEMORY_LOCK:
            if any(
                row.catalog_object_id == record.catalog_object_id
                and row.owner_subject == record.owner_subject
                and row.valid_from == record.valid_from
                for row in _MEMORY_OWNER_ROWS.values()
            ):
                raise ValueError("duplicate data-owner assignment for this catalog object")
            _MEMORY_OWNER_ROWS[record.data_owner_assignment_id] = record.model_copy(deep=True)

    def insert_critical_data_element(self, record: CriticalDataElementRecord) -> None:
        """Insert a CDE after enforcing the tenant-local element key."""

        with _MEMORY_LOCK:
            if any(
                row.catalog_object_id == record.catalog_object_id
                and row.element_key == record.element_key
                for row in _MEMORY_ELEMENT_ROWS.values()
            ):
                raise ValueError("duplicate critical data element in this catalog object")
            _MEMORY_ELEMENT_ROWS[record.critical_data_element_id] = record.model_copy(deep=True)

    def insert_data_quality_rule(self, record: DataQualityRuleRecord) -> None:
        """Insert a rule only when its CDE exists in the same tenant."""

        with _MEMORY_LOCK:
            parent = _MEMORY_ELEMENT_ROWS.get(record.critical_data_element_id)
            if parent is None or parent.tenant_reference != record.tenant_reference:
                raise KeyError("critical data element not found in this tenant")
            if any(
                row.critical_data_element_id == record.critical_data_element_id
                and row.rule_code == record.rule_code
                for row in _MEMORY_RULE_ROWS.values()
            ):
                raise ValueError("duplicate data-quality rule for this critical data element")
            _MEMORY_RULE_ROWS[record.data_quality_rule_id] = record.model_copy(deep=True)

    def insert_data_quality_observation(self, record: DataQualityObservationRecord) -> None:
        """Append an observation only when its rule exists in the same tenant."""

        with _MEMORY_LOCK:
            parent = _MEMORY_RULE_ROWS.get(record.data_quality_rule_id)
            if parent is None or parent.tenant_reference != record.tenant_reference:
                raise KeyError("data-quality rule not found in this tenant")
            if any(
                row.data_quality_rule_id == record.data_quality_rule_id
                and row.source_observation_id == record.source_observation_id
                for row in _MEMORY_OBSERVATION_ROWS.values()
            ):
                raise ValueError("duplicate data-quality observation for this rule")
            _MEMORY_OBSERVATION_ROWS[record.data_quality_observation_id] = record.model_copy(
                deep=True
            )

    def get_critical_data_element(
        self,
        *,
        tenant_reference: str,
        critical_data_element_id: str,
    ) -> CriticalDataElementRecord | None:
        """Return a deep copy of one tenant-owned CDE."""

        with _MEMORY_LOCK:
            row = _MEMORY_ELEMENT_ROWS.get(critical_data_element_id)
            if row is None or row.tenant_reference != tenant_reference:
                return None
            return row.model_copy(deep=True)

    def get_data_quality_rule(
        self,
        *,
        tenant_reference: str,
        data_quality_rule_id: str,
    ) -> DataQualityRuleRecord | None:
        """Return a deep copy of one tenant-owned quality rule."""

        with _MEMORY_LOCK:
            row = _MEMORY_RULE_ROWS.get(data_quality_rule_id)
            if row is None or row.tenant_reference != tenant_reference:
                return None
            return row.model_copy(deep=True)

    def profile_rows(
        self,
        *,
        tenant_reference: str,
        catalog_object_id: str,
    ) -> ProfileRows:
        """Return deep copies of all rows attached to one catalog object."""

        with _MEMORY_LOCK:
            owners = [
                row.model_copy(deep=True)
                for row in _MEMORY_OWNER_ROWS.values()
                if row.tenant_reference == tenant_reference
                and row.catalog_object_id == catalog_object_id
            ]
            elements = [
                row.model_copy(deep=True)
                for row in _MEMORY_ELEMENT_ROWS.values()
                if row.tenant_reference == tenant_reference
                and row.catalog_object_id == catalog_object_id
            ]
            rules = [
                row.model_copy(deep=True)
                for row in _MEMORY_RULE_ROWS.values()
                if row.tenant_reference == tenant_reference
                and row.catalog_object_id == catalog_object_id
            ]
            observations = [
                row.model_copy(deep=True)
                for row in _MEMORY_OBSERVATION_ROWS.values()
                if row.tenant_reference == tenant_reference
                and row.catalog_object_id == catalog_object_id
            ]
        owners.sort(key=lambda row: (row.valid_from, row.data_owner_assignment_id))
        elements.sort(key=lambda row: (row.element_key, row.critical_data_element_id))
        rules.sort(key=lambda row: (row.rule_code, row.data_quality_rule_id))
        observations.sort(key=lambda row: (row.observed_at, row.source_observation_id))
        return owners, elements, rules, observations


class RelationalDataManagementStore(DataManagementStore):
    """SQLAlchemy mapping onto migration 0003 tables."""

    def __init__(self, database_dsn: str) -> None:
        """Open the configured relational database."""

        self._engine = _open_engine(database_dsn)

    def insert_owner_assignment(self, record: DataOwnerAssignmentRecord) -> None:
        """Insert one owner assignment."""

        try:
            with self._engine.begin() as conn:
                conn.execute(
                    text(
                        """
                        INSERT INTO data_owner_assignments (
                            data_owner_assignment_id, catalog_object_id, tenant_reference,
                            owner_subject, owner_display_name, valid_from, valid_to,
                            evidence_reference, truth_status, recorded_at
                        ) VALUES (
                            :data_owner_assignment_id, :catalog_object_id, :tenant_reference,
                            :owner_subject, :owner_display_name, :valid_from, :valid_to,
                            :evidence_reference, :truth_status, :recorded_at
                        )
                        """
                    ),
                    {
                        "data_owner_assignment_id": record.data_owner_assignment_id,
                        "catalog_object_id": record.catalog_object_id,
                        "tenant_reference": record.tenant_reference,
                        "owner_subject": record.owner_subject,
                        "owner_display_name": record.owner_display_name,
                        "valid_from": _sql_timestamp(record.valid_from),
                        "valid_to": _sql_timestamp(record.valid_to),
                        "evidence_reference": record.evidence_reference,
                        "truth_status": record.truth_status,
                        "recorded_at": _sql_timestamp(record.recorded_at),
                    },
                )
        except IntegrityError as exc:
            _raise_unique_violation(exc, "data-owner assignment could not be stored")

    def insert_critical_data_element(self, record: CriticalDataElementRecord) -> None:
        """Insert one critical data element."""

        try:
            with self._engine.begin() as conn:
                conn.execute(
                    text(
                        """
                        INSERT INTO critical_data_elements (
                            critical_data_element_id, catalog_object_id, tenant_reference,
                            element_key, display_name, definition_text,
                            data_classification, evidence_reference, truth_status, recorded_at
                        ) VALUES (
                            :critical_data_element_id, :catalog_object_id, :tenant_reference,
                            :element_key, :display_name, :definition_text,
                            :data_classification, :evidence_reference, :truth_status, :recorded_at
                        )
                        """
                    ),
                    {
                        "critical_data_element_id": record.critical_data_element_id,
                        "catalog_object_id": record.catalog_object_id,
                        "tenant_reference": record.tenant_reference,
                        "element_key": record.element_key,
                        "display_name": record.display_name,
                        "definition_text": record.definition_text,
                        "data_classification": record.data_classification,
                        "evidence_reference": record.evidence_reference,
                        "truth_status": record.truth_status,
                        "recorded_at": _sql_timestamp(record.recorded_at),
                    },
                )
        except IntegrityError as exc:
            _raise_unique_violation(exc, "critical data element could not be stored")

    def insert_data_quality_rule(self, record: DataQualityRuleRecord) -> None:
        """Insert one quality rule after checking the tenant-owned parent CDE."""

        try:
            with self._engine.begin() as conn:
                parent = conn.execute(
                    text(
                        """
                        SELECT critical_data_element_id
                        FROM critical_data_elements
                        WHERE critical_data_element_id = :critical_data_element_id
                          AND tenant_reference = :tenant_reference
                        """
                    ),
                    {
                        "critical_data_element_id": record.critical_data_element_id,
                        "tenant_reference": record.tenant_reference,
                    },
                ).first()
                if parent is None:
                    raise KeyError("critical data element not found in this tenant")
                conn.execute(
                    text(
                        """
                        INSERT INTO data_quality_rules (
                            data_quality_rule_id, critical_data_element_id,
                            catalog_object_id, tenant_reference, rule_code,
                            rule_description, metric_code, threshold_operator,
                            threshold_value, unit_code, evidence_reference,
                            truth_status, recorded_at
                        ) VALUES (
                            :data_quality_rule_id, :critical_data_element_id,
                            :catalog_object_id, :tenant_reference, :rule_code,
                            :rule_description, :metric_code, :threshold_operator,
                            :threshold_value, :unit_code, :evidence_reference,
                            :truth_status, :recorded_at
                        )
                        """
                    ),
                    {
                        "data_quality_rule_id": record.data_quality_rule_id,
                        "critical_data_element_id": record.critical_data_element_id,
                        "catalog_object_id": record.catalog_object_id,
                        "tenant_reference": record.tenant_reference,
                        "rule_code": record.rule_code,
                        "rule_description": record.rule_description,
                        "metric_code": record.metric_code,
                        "threshold_operator": record.threshold_operator,
                        "threshold_value": str(record.threshold_value),
                        "unit_code": record.unit_code,
                        "evidence_reference": record.evidence_reference,
                        "truth_status": record.truth_status,
                        "recorded_at": _sql_timestamp(record.recorded_at),
                    },
                )
        except IntegrityError as exc:
            _raise_unique_violation(exc, "data-quality rule could not be stored")

    def insert_data_quality_observation(self, record: DataQualityObservationRecord) -> None:
        """Insert one immutable observation after checking its tenant-owned rule."""

        try:
            with self._engine.begin() as conn:
                parent = conn.execute(
                    text(
                        """
                        SELECT data_quality_rule_id
                        FROM data_quality_rules
                        WHERE data_quality_rule_id = :data_quality_rule_id
                          AND tenant_reference = :tenant_reference
                        """
                    ),
                    {
                        "data_quality_rule_id": record.data_quality_rule_id,
                        "tenant_reference": record.tenant_reference,
                    },
                ).first()
                if parent is None:
                    raise KeyError("data-quality rule not found in this tenant")
                conn.execute(
                    text(
                        """
                        INSERT INTO data_quality_observations (
                            data_quality_observation_id, data_quality_rule_id,
                            critical_data_element_id, catalog_object_id,
                            tenant_reference, source_observation_id, observed_value,
                            observed_at, quality_status, evidence_reference,
                            truth_status, recorded_at
                        ) VALUES (
                            :data_quality_observation_id, :data_quality_rule_id,
                            :critical_data_element_id, :catalog_object_id,
                            :tenant_reference, :source_observation_id, :observed_value,
                            :observed_at, :quality_status, :evidence_reference,
                            :truth_status, :recorded_at
                        )
                        """
                    ),
                    {
                        "data_quality_observation_id": record.data_quality_observation_id,
                        "data_quality_rule_id": record.data_quality_rule_id,
                        "critical_data_element_id": record.critical_data_element_id,
                        "catalog_object_id": record.catalog_object_id,
                        "tenant_reference": record.tenant_reference,
                        "source_observation_id": record.source_observation_id,
                        "observed_value": str(record.observed_value),
                        "observed_at": _sql_timestamp(record.observed_at),
                        "quality_status": record.quality_status,
                        "evidence_reference": record.evidence_reference,
                        "truth_status": record.truth_status,
                        "recorded_at": _sql_timestamp(record.recorded_at),
                    },
                )
        except IntegrityError as exc:
            _raise_unique_violation(exc, "data-quality observation could not be stored")

    def get_critical_data_element(
        self,
        *,
        tenant_reference: str,
        critical_data_element_id: str,
    ) -> CriticalDataElementRecord | None:
        """Load one tenant-owned CDE."""

        with self._engine.begin() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT * FROM critical_data_elements
                    WHERE critical_data_element_id = :critical_data_element_id
                      AND tenant_reference = :tenant_reference
                    """
                ),
                {
                    "critical_data_element_id": critical_data_element_id,
                    "tenant_reference": tenant_reference,
                },
            ).mappings().first()
        if row is None:
            return None
        return self._critical_data_element(row)

    def get_data_quality_rule(
        self,
        *,
        tenant_reference: str,
        data_quality_rule_id: str,
    ) -> DataQualityRuleRecord | None:
        """Load one tenant-owned quality rule."""

        with self._engine.begin() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT * FROM data_quality_rules
                    WHERE data_quality_rule_id = :data_quality_rule_id
                      AND tenant_reference = :tenant_reference
                    """
                ),
                {
                    "data_quality_rule_id": data_quality_rule_id,
                    "tenant_reference": tenant_reference,
                },
            ).mappings().first()
        if row is None:
            return None
        return self._data_quality_rule(row)

    def profile_rows(
        self,
        *,
        tenant_reference: str,
        catalog_object_id: str,
    ) -> ProfileRows:
        """Hydrate all 0003 rows for one tenant-owned catalog object."""

        with self._engine.begin() as conn:
            owners = [
                self._owner_assignment(row)
                for row in conn.execute(
                    text(
                        """
                        SELECT * FROM data_owner_assignments
                        WHERE tenant_reference = :tenant_reference
                          AND catalog_object_id = :catalog_object_id
                        ORDER BY valid_from, data_owner_assignment_id
                        """
                    ),
                    {
                        "tenant_reference": tenant_reference,
                        "catalog_object_id": catalog_object_id,
                    },
                ).mappings()
            ]
            elements = [
                self._critical_data_element(row)
                for row in conn.execute(
                    text(
                        """
                        SELECT * FROM critical_data_elements
                        WHERE tenant_reference = :tenant_reference
                          AND catalog_object_id = :catalog_object_id
                        ORDER BY element_key, critical_data_element_id
                        """
                    ),
                    {
                        "tenant_reference": tenant_reference,
                        "catalog_object_id": catalog_object_id,
                    },
                ).mappings()
            ]
            rules = [
                self._data_quality_rule(row)
                for row in conn.execute(
                    text(
                        """
                        SELECT * FROM data_quality_rules
                        WHERE tenant_reference = :tenant_reference
                          AND catalog_object_id = :catalog_object_id
                        ORDER BY rule_code, data_quality_rule_id
                        """
                    ),
                    {
                        "tenant_reference": tenant_reference,
                        "catalog_object_id": catalog_object_id,
                    },
                ).mappings()
            ]
            observations = [
                self._data_quality_observation(row)
                for row in conn.execute(
                    text(
                        """
                        SELECT * FROM data_quality_observations
                        WHERE tenant_reference = :tenant_reference
                          AND catalog_object_id = :catalog_object_id
                        ORDER BY observed_at, source_observation_id
                        """
                    ),
                    {
                        "tenant_reference": tenant_reference,
                        "catalog_object_id": catalog_object_id,
                    },
                ).mappings()
            ]
        return owners, elements, rules, observations

    @staticmethod
    def _owner_assignment(row: Any) -> DataOwnerAssignmentRecord:
        """Map one relational owner row into its contract."""

        return DataOwnerAssignmentRecord(
            data_owner_assignment_id=row["data_owner_assignment_id"],
            catalog_object_id=row["catalog_object_id"],
            tenant_reference=row["tenant_reference"],
            owner_subject=row["owner_subject"],
            owner_display_name=row["owner_display_name"],
            valid_from=_as_datetime(row["valid_from"]),
            valid_to=_as_datetime(row["valid_to"]) if row["valid_to"] is not None else None,
            evidence_reference=row["evidence_reference"],
            truth_status=row["truth_status"],
            recorded_at=_as_datetime(row["recorded_at"]),
        )

    @staticmethod
    def _critical_data_element(row: Any) -> CriticalDataElementRecord:
        """Map one relational CDE row into its contract."""

        return CriticalDataElementRecord(
            critical_data_element_id=row["critical_data_element_id"],
            catalog_object_id=row["catalog_object_id"],
            tenant_reference=row["tenant_reference"],
            element_key=row["element_key"],
            display_name=row["display_name"],
            definition_text=row["definition_text"],
            data_classification=row["data_classification"],
            evidence_reference=row["evidence_reference"],
            truth_status=row["truth_status"],
            recorded_at=_as_datetime(row["recorded_at"]),
        )

    @staticmethod
    def _data_quality_rule(row: Any) -> DataQualityRuleRecord:
        """Map one relational quality-rule row into its contract."""

        return DataQualityRuleRecord(
            data_quality_rule_id=row["data_quality_rule_id"],
            critical_data_element_id=row["critical_data_element_id"],
            catalog_object_id=row["catalog_object_id"],
            tenant_reference=row["tenant_reference"],
            rule_code=row["rule_code"],
            rule_description=row["rule_description"],
            metric_code=row["metric_code"],
            threshold_operator=row["threshold_operator"],
            threshold_value=_decimal(row["threshold_value"]),
            unit_code=row["unit_code"],
            evidence_reference=row["evidence_reference"],
            truth_status=row["truth_status"],
            recorded_at=_as_datetime(row["recorded_at"]),
        )

    @staticmethod
    def _data_quality_observation(row: Any) -> DataQualityObservationRecord:
        """Map one relational observation row into its contract."""

        return DataQualityObservationRecord(
            data_quality_observation_id=row["data_quality_observation_id"],
            data_quality_rule_id=row["data_quality_rule_id"],
            critical_data_element_id=row["critical_data_element_id"],
            catalog_object_id=row["catalog_object_id"],
            tenant_reference=row["tenant_reference"],
            source_observation_id=row["source_observation_id"],
            observed_value=_decimal(row["observed_value"]),
            observed_at=_as_datetime(row["observed_at"]),
            quality_status=row["quality_status"],
            evidence_reference=row["evidence_reference"],
            truth_status=row["truth_status"],
            recorded_at=_as_datetime(row["recorded_at"]),
        )


_ACTIVE_STORE: DataManagementStore | None = None


def reset_memory_data_management() -> None:
    """Clear every process-local evidence row."""

    with _MEMORY_LOCK:
        _MEMORY_OWNER_ROWS.clear()
        _MEMORY_ELEMENT_ROWS.clear()
        _MEMORY_RULE_ROWS.clear()
        _MEMORY_OBSERVATION_ROWS.clear()


def snapshot_memory_data_management() -> dict[str, dict[str, Any]]:
    """Copy process-local evidence rows for test isolation."""

    with _MEMORY_LOCK:
        return {
            "owners": deepcopy(_MEMORY_OWNER_ROWS),
            "elements": deepcopy(_MEMORY_ELEMENT_ROWS),
            "rules": deepcopy(_MEMORY_RULE_ROWS),
            "observations": deepcopy(_MEMORY_OBSERVATION_ROWS),
        }


def restore_memory_data_management(snapshot: dict[str, dict[str, Any]]) -> None:
    """Replace process-local rows from a prior snapshot."""

    with _MEMORY_LOCK:
        _MEMORY_OWNER_ROWS.clear()
        _MEMORY_OWNER_ROWS.update(deepcopy(snapshot.get("owners", {})))
        _MEMORY_ELEMENT_ROWS.clear()
        _MEMORY_ELEMENT_ROWS.update(deepcopy(snapshot.get("elements", {})))
        _MEMORY_RULE_ROWS.clear()
        _MEMORY_RULE_ROWS.update(deepcopy(snapshot.get("rules", {})))
        _MEMORY_OBSERVATION_ROWS.clear()
        _MEMORY_OBSERVATION_ROWS.update(deepcopy(snapshot.get("observations", {})))


def build_data_management_store() -> DataManagementStore:
    """Return the in-memory store or migration-0003 relational store."""

    dsn = load_bootstrap().database_dsn
    if not dsn:
        return InMemoryDataManagementStore()
    try:
        return RelationalDataManagementStore(dsn)
    except RuntimeError as exc:
        raise RuntimeError(
            "SDP_DATABASE_DSN is set but the data-management store could not open. "
            f"{_GRAPH_EXTRA_HINT}"
        ) from exc


def get_data_management_store() -> DataManagementStore:
    """Return the process-wide evidence store, building it once."""

    global _ACTIVE_STORE
    if _ACTIVE_STORE is None:
        _ACTIVE_STORE = build_data_management_store()
    return _ACTIVE_STORE


def set_data_management_store(store: DataManagementStore | None) -> None:
    """Replace or clear the process-wide evidence store for tests."""

    global _ACTIVE_STORE
    _ACTIVE_STORE = store
