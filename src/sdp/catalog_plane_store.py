"""Persistence backends for the tenant-bound catalog/ontology plane.

The in-memory store is the CI / pytest default. When ``SDP_DATABASE_DSN`` is
set, the relational store reads and writes the 0002 3NF tables. Production DSN
is Postgres; SQLite is accepted only so unit tests can exercise the same SQL
mapping without a live Apache AGE instance. This module does not open AGE
graphs or pgvector indexes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any, Iterator

from sdp.config import load_bootstrap
from sdp_core.catalog_plane import (
    CatalogObjectRecord,
    ConceptBindingRecord,
    DocumentKgLinkRecord,
    ObjectAliasRecord,
    ObjectDefinitionRecord,
    ObjectStewardRecord,
    ScoreReferenceRecord,
)

try:
    from sqlalchemy import create_engine, event, text
    from sqlalchemy.engine import Connection, Engine
    from sqlalchemy.exc import IntegrityError
except ImportError:  # pragma: no cover - optional graph extra
    create_engine = None  # type: ignore[assignment]
    event = None  # type: ignore[assignment]
    text = None  # type: ignore[assignment]
    Connection = Any  # type: ignore[misc,assignment]
    Engine = Any  # type: ignore[misc,assignment]

    class IntegrityError(Exception):  # type: ignore[no-redef]
        """Placeholder used only when SQLAlchemy is not installed."""


_MIGRATION_0002 = (
    Path(__file__).resolve().parents[2] / "migrations" / "0002_ontology_catalog_plane.sql"
)
_MEMORY_ROWS: dict[str, CatalogObjectRecord] = {}
_MEMORY_LOCK = RLock()
_GRAPH_EXTRA_HINT = (
    "Install the optional graph extra so SQLAlchemy can open SDP_DATABASE_DSN."
)


def _now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


def _as_datetime(value: Any) -> datetime:
    """Coerce a driver timestamp or ISO string into aware UTC datetime."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _sql_timestamp(value: datetime) -> str:
    """Render a timestamp as ISO-8601 for Postgres TIMESTAMPTZ and SQLite TEXT."""
    return _as_datetime(value).isoformat()


def _open_engine(database_dsn: str) -> Engine:
    """Open a SQLAlchemy engine or fail loud when the graph extra is missing."""
    if create_engine is None:
        raise RuntimeError(
            "SDP_DATABASE_DSN is set but the catalog plane store could not open. "
            f"{_GRAPH_EXTRA_HINT}"
        )
    return create_engine(database_dsn, future=True)


def _raise_unique_violation(exc: Exception, fallback: str) -> None:
    """Map a SQL UNIQUE failure onto the buyer-facing ValueError text."""
    detail = str(exc).lower()
    if "object_slug" in detail:
        raise ValueError("object_slug already exists in this tenant") from exc
    if "document_kg_links" in detail or "source_object_id" in detail:
        raise ValueError("duplicate document-KG link in this catalog object") from exc
    if "concept_object_bindings" in detail or "concept_key" in detail:
        raise ValueError("duplicate concept binding in this catalog object") from exc
    if "object_aliases" in detail or "alias_text" in detail:
        raise ValueError("duplicate object alias in this catalog object") from exc
    raise ValueError(fallback) from exc


def catalog_plane_sqlite_ddl() -> str:
    """Return 0002 DDL rewritten so SQLite can host the same 3NF tables.

    Postgres remains the production path (``TIMESTAMPTZ``, ``search_path``,
    ``schema_migrations``). This helper only substitutes tokens SQLite cannot
    execute so unit tests can exercise the SQL mapping without Apache AGE.
    """
    sql_text = _MIGRATION_0002.read_text(encoding="utf-8")
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


def apply_catalog_plane_sqlite_schema(engine: Engine) -> None:
    """Create the 0002 table names on a SQLite engine for unit tests."""
    if text is None:  # pragma: no cover - SQLAlchemy is a dev extra
        raise RuntimeError(_GRAPH_EXTRA_HINT)
    statements: list[str] = []
    buffer: list[str] = []
    for line in catalog_plane_sqlite_ddl().splitlines():
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


class CatalogPlaneStore(ABC):
    """Read/write surface for catalog objects and their 0002 child rows."""

    @abstractmethod
    def insert_catalog_object(self, record: CatalogObjectRecord) -> None:
        """Persist a new catalog object and every child collection."""

    @abstractmethod
    def list_catalog_objects(
        self,
        *,
        tenant_reference: str,
        object_kind: str | None = None,
    ) -> list[CatalogObjectRecord]:
        """Return tenant-scoped objects, optionally filtered by kind."""

    @abstractmethod
    def get_catalog_object(
        self,
        *,
        tenant_reference: str,
        catalog_object_id: str,
    ) -> CatalogObjectRecord | None:
        """Return one tenant-owned object or None."""

    @abstractmethod
    def attach_document_kg_link(
        self,
        *,
        tenant_reference: str,
        catalog_object_id: str,
        link: DocumentKgLinkRecord,
    ) -> CatalogObjectRecord | None:
        """Append a document-KG link. None means the parent object is missing."""

    @abstractmethod
    def attach_concept_binding(
        self,
        *,
        tenant_reference: str,
        catalog_object_id: str,
        binding: ConceptBindingRecord,
    ) -> CatalogObjectRecord | None:
        """Append a concept binding. None means the parent object is missing."""

    @abstractmethod
    def query_catalog_objects(
        self,
        *,
        tenant_reference: str,
        query_text: str,
    ) -> list[CatalogObjectRecord]:
        """Return tenant objects matching title, slug, alias, concept, or KG id."""


class InMemoryCatalogPlaneStore(CatalogPlaneStore):
    """Process-local store used when ``SDP_DATABASE_DSN`` is unset."""

    def insert_catalog_object(self, record: CatalogObjectRecord) -> None:
        """Append a catalog object after enforcing tenant slug uniqueness."""
        with _MEMORY_LOCK:
            if any(
                existing.tenant_reference == record.tenant_reference
                and existing.object_slug == record.object_slug
                for existing in _MEMORY_ROWS.values()
            ):
                raise ValueError("object_slug already exists in this tenant")
            _MEMORY_ROWS[record.catalog_object_id] = record

    def list_catalog_objects(
        self,
        *,
        tenant_reference: str,
        object_kind: str | None = None,
    ) -> list[CatalogObjectRecord]:
        """Return tenant-scoped in-memory objects."""
        with _MEMORY_LOCK:
            rows = [
                row.model_copy(deep=True)
                for row in _MEMORY_ROWS.values()
                if row.tenant_reference == tenant_reference
                and (object_kind is None or row.object_kind == object_kind)
            ]
            return rows

    def get_catalog_object(
        self,
        *,
        tenant_reference: str,
        catalog_object_id: str,
    ) -> CatalogObjectRecord | None:
        """Return one in-memory object owned by the tenant."""
        with _MEMORY_LOCK:
            record = _MEMORY_ROWS.get(catalog_object_id)
            if record is None or record.tenant_reference != tenant_reference:
                return None
            return record.model_copy(deep=True)

    def attach_document_kg_link(
        self,
        *,
        tenant_reference: str,
        catalog_object_id: str,
        link: DocumentKgLinkRecord,
    ) -> CatalogObjectRecord | None:
        """Append a document-KG link after enforcing the unique child key."""
        with _MEMORY_LOCK:
            record = _MEMORY_ROWS.get(catalog_object_id)
            if record is None or record.tenant_reference != tenant_reference:
                return None
            if any(
                existing.source_system == link.source_system
                and existing.source_object_id == link.source_object_id
                for existing in record.document_kg_links
            ):
                raise ValueError("duplicate document-KG link in this catalog object")
            record.document_kg_links.append(link)
            record.updated_at = _now()
            return record.model_copy(deep=True)

    def attach_concept_binding(
        self,
        *,
        tenant_reference: str,
        catalog_object_id: str,
        binding: ConceptBindingRecord,
    ) -> CatalogObjectRecord | None:
        """Append a concept binding after enforcing the unique child key."""
        with _MEMORY_LOCK:
            record = _MEMORY_ROWS.get(catalog_object_id)
            if record is None or record.tenant_reference != tenant_reference:
                return None
            if any(
                existing.concept_key == binding.concept_key
                and existing.binding_role == binding.binding_role
                for existing in record.concept_bindings
            ):
                raise ValueError("duplicate concept binding in this catalog object")
            record.concept_bindings.append(binding)
            record.updated_at = _now()
            return record.model_copy(deep=True)

    def query_catalog_objects(
        self,
        *,
        tenant_reference: str,
        query_text: str,
    ) -> list[CatalogObjectRecord]:
        """Filter in-memory objects by needle across identity and child text."""
        needle = query_text.strip().lower()
        with _MEMORY_LOCK:
            matches: list[CatalogObjectRecord] = []
            for row in _MEMORY_ROWS.values():
                if row.tenant_reference != tenant_reference:
                    continue
                haystacks = [
                    row.display_title,
                    row.object_slug,
                    row.definition.definition_text,
                    row.steward.steward_display_name,
                    *[alias.alias_text for alias in row.aliases],
                    *[binding.concept_key for binding in row.concept_bindings],
                    *[link.source_object_id for link in row.document_kg_links],
                ]
                if any(needle in value.lower() for value in haystacks):
                    matches.append(row.model_copy(deep=True))
            return matches


class RelationalCatalogPlaneStore(CatalogPlaneStore):
    """SQLAlchemy store mapped onto the 0002 catalog/ontology tables."""

    def __init__(self, database_dsn: str) -> None:
        """Open a SQLAlchemy engine against the given DSN."""
        self._engine = _open_engine(database_dsn)
        self._is_sqlite = str(self._engine.url.drivername).startswith("sqlite")
        if self._is_sqlite:
            self._enable_sqlite_foreign_keys()

    def _enable_sqlite_foreign_keys(self) -> None:
        """Turn on SQLite foreign-key enforcement for this engine."""

        @event.listens_for(self._engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, _connection_record) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    @contextmanager
    def _transaction(self) -> Iterator[Connection]:
        """Yield a connection and commit, or roll back on error."""
        with self._engine.begin() as connection:
            yield connection

    def insert_catalog_object(self, record: CatalogObjectRecord) -> None:
        """Insert a catalog object and all child rows in one transaction."""
        try:
            with self._transaction() as conn:
                conn.execute(
                    text(
                        """
                        INSERT INTO catalog_objects (
                            catalog_object_id, tenant_reference, object_kind, object_slug,
                            display_title, object_status, created_by_subject,
                            created_at, updated_at
                        ) VALUES (
                            :catalog_object_id, :tenant_reference, :object_kind, :object_slug,
                            :display_title, :object_status, :created_by_subject,
                            :created_at, :updated_at
                        )
                        """
                    ),
                    {
                        "catalog_object_id": record.catalog_object_id,
                        "tenant_reference": record.tenant_reference,
                        "object_kind": record.object_kind,
                        "object_slug": record.object_slug,
                        "display_title": record.display_title,
                        "object_status": record.object_status,
                        "created_by_subject": record.created_by_subject,
                        "created_at": _sql_timestamp(record.created_at),
                        "updated_at": _sql_timestamp(record.updated_at),
                    },
                )
                conn.execute(
                    text(
                        """
                        INSERT INTO object_definitions (
                            definition_id, catalog_object_id, definition_text,
                            preferred_language, definition_status, recorded_at
                        ) VALUES (
                            :definition_id, :catalog_object_id, :definition_text,
                            :preferred_language, :definition_status, :recorded_at
                        )
                        """
                    ),
                    {
                        "definition_id": record.definition.definition_id,
                        "catalog_object_id": record.catalog_object_id,
                        "definition_text": record.definition.definition_text,
                        "preferred_language": record.definition.preferred_language,
                        "definition_status": record.definition.definition_status,
                        "recorded_at": _sql_timestamp(record.definition.recorded_at),
                    },
                )
                conn.execute(
                    text(
                        """
                        INSERT INTO object_stewards (
                            steward_record_id, catalog_object_id, steward_subject,
                            steward_display_name, recorded_at
                        ) VALUES (
                            :steward_record_id, :catalog_object_id, :steward_subject,
                            :steward_display_name, :recorded_at
                        )
                        """
                    ),
                    {
                        "steward_record_id": record.steward.steward_record_id,
                        "catalog_object_id": record.catalog_object_id,
                        "steward_subject": record.steward.steward_subject,
                        "steward_display_name": record.steward.steward_display_name,
                        "recorded_at": _sql_timestamp(record.steward.recorded_at),
                    },
                )
                for alias in record.aliases:
                    conn.execute(
                        text(
                            """
                            INSERT INTO object_aliases (
                                alias_id, catalog_object_id, alias_text, alias_language
                            ) VALUES (
                                :alias_id, :catalog_object_id, :alias_text, :alias_language
                            )
                            """
                        ),
                        {
                            "alias_id": alias.alias_id,
                            "catalog_object_id": record.catalog_object_id,
                            "alias_text": alias.alias_text,
                            "alias_language": alias.alias_language,
                        },
                    )
                for link in record.document_kg_links:
                    conn.execute(
                        text(
                            """
                            INSERT INTO document_kg_links (
                                document_kg_link_id, catalog_object_id, source_system,
                                source_object_kind, source_object_id, provenance_uri,
                                link_status, recorded_at
                            ) VALUES (
                                :document_kg_link_id, :catalog_object_id, :source_system,
                                :source_object_kind, :source_object_id, :provenance_uri,
                                :link_status, :recorded_at
                            )
                            """
                        ),
                        {
                            "document_kg_link_id": link.document_kg_link_id,
                            "catalog_object_id": record.catalog_object_id,
                            "source_system": link.source_system,
                            "source_object_kind": link.source_object_kind,
                            "source_object_id": link.source_object_id,
                            "provenance_uri": link.provenance_uri,
                            "link_status": link.link_status,
                            "recorded_at": _sql_timestamp(link.recorded_at),
                        },
                    )
                for binding in record.concept_bindings:
                    conn.execute(
                        text(
                            """
                            INSERT INTO concept_object_bindings (
                                binding_id, catalog_object_id, concept_key,
                                binding_role, recorded_at
                            ) VALUES (
                                :binding_id, :catalog_object_id, :concept_key,
                                :binding_role, :recorded_at
                            )
                            """
                        ),
                        {
                            "binding_id": binding.binding_id,
                            "catalog_object_id": record.catalog_object_id,
                            "concept_key": binding.concept_key,
                            "binding_role": binding.binding_role,
                            "recorded_at": _sql_timestamp(binding.recorded_at),
                        },
                    )
                for score in record.score_references:
                    conn.execute(
                        text(
                            """
                            INSERT INTO commons_score_references (
                                score_reference_id, catalog_object_id, score_system,
                                score_endpoint, recorded_at
                            ) VALUES (
                                :score_reference_id, :catalog_object_id, :score_system,
                                :score_endpoint, :recorded_at
                            )
                            """
                        ),
                        {
                            "score_reference_id": score.score_reference_id,
                            "catalog_object_id": record.catalog_object_id,
                            "score_system": score.score_system,
                            "score_endpoint": score.score_endpoint,
                            "recorded_at": _sql_timestamp(score.recorded_at),
                        },
                    )
        except IntegrityError as exc:
            _raise_unique_violation(exc, "object_slug already exists in this tenant")

    def list_catalog_objects(
        self,
        *,
        tenant_reference: str,
        object_kind: str | None = None,
    ) -> list[CatalogObjectRecord]:
        """Load tenant-scoped catalog objects from the 0002 tables."""
        with self._transaction() as conn:
            if object_kind:
                rows = list(
                    conn.execute(
                        text(
                            """
                            SELECT catalog_object_id FROM catalog_objects
                            WHERE tenant_reference = :tenant_reference
                              AND object_kind = :object_kind
                            ORDER BY created_at ASC
                            """
                        ),
                        {
                            "tenant_reference": tenant_reference,
                            "object_kind": object_kind,
                        },
                    ).mappings()
                )
            else:
                rows = list(
                    conn.execute(
                        text(
                            """
                            SELECT catalog_object_id FROM catalog_objects
                            WHERE tenant_reference = :tenant_reference
                            ORDER BY created_at ASC
                            """
                        ),
                        {"tenant_reference": tenant_reference},
                    ).mappings()
                )
            loaded: list[CatalogObjectRecord] = []
            for row in rows:
                record = self._load_record(
                    conn,
                    tenant_reference=tenant_reference,
                    catalog_object_id=row["catalog_object_id"],
                )
                if record is not None:
                    loaded.append(record)
            return loaded

    def get_catalog_object(
        self,
        *,
        tenant_reference: str,
        catalog_object_id: str,
    ) -> CatalogObjectRecord | None:
        """Load one catalog object owned by the tenant."""
        with self._transaction() as conn:
            return self._load_record(
                conn,
                tenant_reference=tenant_reference,
                catalog_object_id=catalog_object_id,
            )

    def attach_document_kg_link(
        self,
        *,
        tenant_reference: str,
        catalog_object_id: str,
        link: DocumentKgLinkRecord,
    ) -> CatalogObjectRecord | None:
        """Insert a document-KG link and bump the parent updated_at."""
        try:
            with self._transaction() as conn:
                parent = self._load_record(
                    conn,
                    tenant_reference=tenant_reference,
                    catalog_object_id=catalog_object_id,
                )
                if parent is None:
                    return None
                conn.execute(
                    text(
                        """
                        INSERT INTO document_kg_links (
                            document_kg_link_id, catalog_object_id, source_system,
                            source_object_kind, source_object_id, provenance_uri,
                            link_status, recorded_at
                        ) VALUES (
                            :document_kg_link_id, :catalog_object_id, :source_system,
                            :source_object_kind, :source_object_id, :provenance_uri,
                            :link_status, :recorded_at
                        )
                        """
                    ),
                    {
                        "document_kg_link_id": link.document_kg_link_id,
                        "catalog_object_id": catalog_object_id,
                        "source_system": link.source_system,
                        "source_object_kind": link.source_object_kind,
                        "source_object_id": link.source_object_id,
                        "provenance_uri": link.provenance_uri,
                        "link_status": link.link_status,
                        "recorded_at": _sql_timestamp(link.recorded_at),
                    },
                )
                conn.execute(
                    text(
                        """
                        UPDATE catalog_objects
                        SET updated_at = :updated_at
                        WHERE catalog_object_id = :catalog_object_id
                          AND tenant_reference = :tenant_reference
                        """
                    ),
                    {
                        "updated_at": _sql_timestamp(_now()),
                        "catalog_object_id": catalog_object_id,
                        "tenant_reference": tenant_reference,
                    },
                )
                return self._load_record(
                    conn,
                    tenant_reference=tenant_reference,
                    catalog_object_id=catalog_object_id,
                )
        except IntegrityError as exc:
            _raise_unique_violation(exc, "duplicate document-KG link in this catalog object")

    def attach_concept_binding(
        self,
        *,
        tenant_reference: str,
        catalog_object_id: str,
        binding: ConceptBindingRecord,
    ) -> CatalogObjectRecord | None:
        """Insert a concept binding and bump the parent updated_at."""
        try:
            with self._transaction() as conn:
                parent = self._load_record(
                    conn,
                    tenant_reference=tenant_reference,
                    catalog_object_id=catalog_object_id,
                )
                if parent is None:
                    return None
                conn.execute(
                    text(
                        """
                        INSERT INTO concept_object_bindings (
                            binding_id, catalog_object_id, concept_key,
                            binding_role, recorded_at
                        ) VALUES (
                            :binding_id, :catalog_object_id, :concept_key,
                            :binding_role, :recorded_at
                        )
                        """
                    ),
                    {
                        "binding_id": binding.binding_id,
                        "catalog_object_id": catalog_object_id,
                        "concept_key": binding.concept_key,
                        "binding_role": binding.binding_role,
                        "recorded_at": _sql_timestamp(binding.recorded_at),
                    },
                )
                conn.execute(
                    text(
                        """
                        UPDATE catalog_objects
                        SET updated_at = :updated_at
                        WHERE catalog_object_id = :catalog_object_id
                          AND tenant_reference = :tenant_reference
                        """
                    ),
                    {
                        "updated_at": _sql_timestamp(_now()),
                        "catalog_object_id": catalog_object_id,
                        "tenant_reference": tenant_reference,
                    },
                )
                return self._load_record(
                    conn,
                    tenant_reference=tenant_reference,
                    catalog_object_id=catalog_object_id,
                )
        except IntegrityError as exc:
            _raise_unique_violation(exc, "duplicate concept binding in this catalog object")

    def query_catalog_objects(
        self,
        *,
        tenant_reference: str,
        query_text: str,
    ) -> list[CatalogObjectRecord]:
        """Search 0002 rows with a portable case-insensitive LIKE needle."""
        needle = f"%{query_text.strip().lower()}%"
        sql = """
            SELECT o.catalog_object_id
            FROM catalog_objects o
            WHERE o.tenant_reference = :tenant_reference
              AND (
                lower(o.object_slug) LIKE :needle
                OR lower(o.display_title) LIKE :needle
                OR EXISTS (
                    SELECT 1 FROM object_definitions d
                    WHERE d.catalog_object_id = o.catalog_object_id
                      AND lower(d.definition_text) LIKE :needle
                )
                OR EXISTS (
                    SELECT 1 FROM object_aliases a
                    WHERE a.catalog_object_id = o.catalog_object_id
                      AND lower(a.alias_text) LIKE :needle
                )
                OR EXISTS (
                    SELECT 1 FROM object_stewards s
                    WHERE s.catalog_object_id = o.catalog_object_id
                      AND lower(s.steward_display_name) LIKE :needle
                )
                OR EXISTS (
                    SELECT 1 FROM document_kg_links l
                    WHERE l.catalog_object_id = o.catalog_object_id
                      AND lower(l.source_object_id) LIKE :needle
                )
                OR EXISTS (
                    SELECT 1 FROM concept_object_bindings b
                    WHERE b.catalog_object_id = o.catalog_object_id
                      AND lower(b.concept_key) LIKE :needle
                )
              )
            ORDER BY o.created_at ASC
        """
        with self._transaction() as conn:
            rows = list(
                conn.execute(
                    text(sql),
                    {"tenant_reference": tenant_reference, "needle": needle},
                ).mappings()
            )
            loaded: list[CatalogObjectRecord] = []
            for row in rows:
                record = self._load_record(
                    conn,
                    tenant_reference=tenant_reference,
                    catalog_object_id=row["catalog_object_id"],
                )
                if record is not None:
                    loaded.append(record)
            return loaded

    def _load_record(
        self,
        conn: Connection,
        *,
        tenant_reference: str,
        catalog_object_id: str,
    ) -> CatalogObjectRecord | None:
        """Hydrate one catalog object and its children from 0002 tables."""
        parent = (
            conn.execute(
                text(
                    """
                    SELECT catalog_object_id, tenant_reference, object_kind, object_slug,
                           display_title, object_status, created_by_subject,
                           created_at, updated_at
                    FROM catalog_objects
                    WHERE catalog_object_id = :catalog_object_id
                      AND tenant_reference = :tenant_reference
                    """
                ),
                {
                    "catalog_object_id": catalog_object_id,
                    "tenant_reference": tenant_reference,
                },
            )
            .mappings()
            .first()
        )
        if parent is None:
            return None
        definition_row = (
            conn.execute(
                text(
                    """
                    SELECT definition_id, catalog_object_id, definition_text,
                           preferred_language, definition_status, recorded_at
                    FROM object_definitions
                    WHERE catalog_object_id = :catalog_object_id
                    ORDER BY recorded_at ASC
                    """
                ),
                {"catalog_object_id": catalog_object_id},
            )
            .mappings()
            .first()
        )
        steward_row = (
            conn.execute(
                text(
                    """
                    SELECT steward_record_id, catalog_object_id, steward_subject,
                           steward_display_name, recorded_at
                    FROM object_stewards
                    WHERE catalog_object_id = :catalog_object_id
                    ORDER BY recorded_at ASC
                    """
                ),
                {"catalog_object_id": catalog_object_id},
            )
            .mappings()
            .first()
        )
        if definition_row is None or steward_row is None:
            raise RuntimeError(
                "catalog object is missing required 0002 definition or steward rows"
            )
        aliases = [
            ObjectAliasRecord(
                alias_id=row["alias_id"],
                catalog_object_id=row["catalog_object_id"],
                alias_text=row["alias_text"],
                alias_language=row["alias_language"],
            )
            for row in conn.execute(
                text(
                    """
                    SELECT alias_id, catalog_object_id, alias_text, alias_language
                    FROM object_aliases
                    WHERE catalog_object_id = :catalog_object_id
                    """
                ),
                {"catalog_object_id": catalog_object_id},
            ).mappings()
        ]
        links = [
            DocumentKgLinkRecord(
                document_kg_link_id=row["document_kg_link_id"],
                catalog_object_id=row["catalog_object_id"],
                source_system=row["source_system"],
                source_object_kind=row["source_object_kind"],
                source_object_id=row["source_object_id"],
                provenance_uri=row["provenance_uri"],
                link_status=row["link_status"],
                recorded_at=_as_datetime(row["recorded_at"]),
            )
            for row in conn.execute(
                text(
                    """
                    SELECT document_kg_link_id, catalog_object_id, source_system,
                           source_object_kind, source_object_id, provenance_uri,
                           link_status, recorded_at
                    FROM document_kg_links
                    WHERE catalog_object_id = :catalog_object_id
                    ORDER BY recorded_at ASC
                    """
                ),
                {"catalog_object_id": catalog_object_id},
            ).mappings()
        ]
        bindings = [
            ConceptBindingRecord(
                binding_id=row["binding_id"],
                catalog_object_id=row["catalog_object_id"],
                concept_key=row["concept_key"],
                binding_role=row["binding_role"],
                recorded_at=_as_datetime(row["recorded_at"]),
            )
            for row in conn.execute(
                text(
                    """
                    SELECT binding_id, catalog_object_id, concept_key,
                           binding_role, recorded_at
                    FROM concept_object_bindings
                    WHERE catalog_object_id = :catalog_object_id
                    ORDER BY recorded_at ASC
                    """
                ),
                {"catalog_object_id": catalog_object_id},
            ).mappings()
        ]
        scores = [
            ScoreReferenceRecord(
                score_reference_id=row["score_reference_id"],
                catalog_object_id=row["catalog_object_id"],
                score_system=row["score_system"],
                score_endpoint=row["score_endpoint"],
                recorded_at=_as_datetime(row["recorded_at"]),
            )
            for row in conn.execute(
                text(
                    """
                    SELECT score_reference_id, catalog_object_id, score_system,
                           score_endpoint, recorded_at
                    FROM commons_score_references
                    WHERE catalog_object_id = :catalog_object_id
                    ORDER BY recorded_at ASC
                    """
                ),
                {"catalog_object_id": catalog_object_id},
            ).mappings()
        ]
        return CatalogObjectRecord(
            catalog_object_id=parent["catalog_object_id"],
            tenant_reference=parent["tenant_reference"],
            object_kind=parent["object_kind"],
            object_slug=parent["object_slug"],
            display_title=parent["display_title"],
            object_status=parent["object_status"],
            created_by_subject=parent["created_by_subject"],
            created_at=_as_datetime(parent["created_at"]),
            updated_at=_as_datetime(parent["updated_at"]),
            definition=ObjectDefinitionRecord(
                definition_id=definition_row["definition_id"],
                catalog_object_id=definition_row["catalog_object_id"],
                definition_text=definition_row["definition_text"],
                preferred_language=definition_row["preferred_language"],
                definition_status=definition_row["definition_status"],
                recorded_at=_as_datetime(definition_row["recorded_at"]),
            ),
            steward=ObjectStewardRecord(
                steward_record_id=steward_row["steward_record_id"],
                catalog_object_id=steward_row["catalog_object_id"],
                steward_subject=steward_row["steward_subject"],
                steward_display_name=steward_row["steward_display_name"],
                recorded_at=_as_datetime(steward_row["recorded_at"]),
            ),
            aliases=aliases,
            document_kg_links=links,
            concept_bindings=bindings,
            score_references=scores,
        )


_ACTIVE_STORE: CatalogPlaneStore | None = None


def reset_memory_catalog_plane() -> None:
    """Clear the process-local in-memory catalog plane."""
    with _MEMORY_LOCK:
        _MEMORY_ROWS.clear()


def snapshot_memory_catalog_plane() -> dict[str, CatalogObjectRecord]:
    """Copy in-memory catalog objects for test isolation."""
    with _MEMORY_LOCK:
        return {key: value.model_copy(deep=True) for key, value in _MEMORY_ROWS.items()}


def restore_memory_catalog_plane(rows: dict[str, CatalogObjectRecord]) -> None:
    """Replace in-memory catalog objects from a snapshot."""
    with _MEMORY_LOCK:
        _MEMORY_ROWS.clear()
        _MEMORY_ROWS.update(deepcopy(rows))


def build_catalog_plane_store() -> CatalogPlaneStore:
    """Return the in-memory store, or the 0002 store when a DSN is set."""
    dsn = load_bootstrap().database_dsn
    if not dsn:
        return InMemoryCatalogPlaneStore()
    try:
        return RelationalCatalogPlaneStore(dsn)
    except RuntimeError as exc:
        raise RuntimeError(
            "SDP_DATABASE_DSN is set but the catalog plane store could not open. "
            f"{_GRAPH_EXTRA_HINT}"
        ) from exc


def get_catalog_plane_store() -> CatalogPlaneStore:
    """Return the process-wide catalog plane store, building it once."""
    global _ACTIVE_STORE
    if _ACTIVE_STORE is None:
        _ACTIVE_STORE = build_catalog_plane_store()
    return _ACTIVE_STORE


def set_catalog_plane_store(store: CatalogPlaneStore | None) -> None:
    """Replace or clear the process-wide catalog plane store (tests)."""
    global _ACTIVE_STORE
    _ACTIVE_STORE = store
