"""OpenMetadata 2.x read-only anti-corruption contracts.

The adapter converts untrusted OpenMetadata table and lineage payloads into a
bounded, tenant-scoped observation. It deliberately excludes data samples,
SQL/DDL, query text, join statistics, and transformation expressions from the
catalog projection.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

OPENMETADATA_TABLE_SCHEMA_URI = "https://open-metadata.org/schema/entity/data/table.json"
OPENMETADATA_LINEAGE_SCHEMA_URI = "https://open-metadata.org/schema/type/entityLineage.json"

_MAX_COLUMN_DEPTH = 16
_MAX_COLUMNS = 10_000
_MAX_REFERENCES = 1_000
_MAX_LINEAGE_EDGES = 20_000
_MAX_COLUMN_MAPPINGS = 20_000
_MAX_PAYLOAD_CONTAINERS = 100_000
_MAX_PAYLOAD_TEXT_BYTES = 8 * 1024 * 1024
_MAX_TEXT_LENGTH = 16_384
_TENANT_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
_RELEASE_PATTERN = re.compile(r"^2\.(?:0|[1-9]\d*)(?:\.(?:0|[1-9]\d*))?(?:-release)?$")


class OpenMetadataContractError(ValueError):
    """Raised when an OpenMetadata payload violates the bounded contract."""


class OpenMetadataReferenceProjection(BaseModel):
    """Safe reference to an entity owned by OpenMetadata."""

    model_config = ConfigDict(extra="forbid")

    external_entity_id: str
    entity_type: str
    label: str
    fully_qualified_name: str | None = None
    href: str | None = None


class OpenMetadataColumnProjection(BaseModel):
    """Flattened, non-sample metadata for one OpenMetadata column."""

    model_config = ConfigDict(extra="forbid")

    column_path: str
    name: str
    data_type: str
    data_type_display: str | None = None
    nullable: bool | None = None
    description: str | None = None
    ordinal_position: int | None = None
    fully_qualified_name: str | None = None
    tag_fqns: list[str] = Field(default_factory=list)


class OpenMetadataColumnLineageProjection(BaseModel):
    """Column identities participating in a lineage edge."""

    model_config = ConfigDict(extra="forbid")

    from_columns: list[str]
    to_column: str


class OpenMetadataLineageEdgeProjection(BaseModel):
    """Safe table-level edge and optional column mappings."""

    model_config = ConfigDict(extra="forbid")

    from_reference: OpenMetadataReferenceProjection
    to_reference: OpenMetadataReferenceProjection
    source: str
    pipeline_reference: OpenMetadataReferenceProjection | None = None
    column_mappings: list[OpenMetadataColumnLineageProjection] = Field(default_factory=list)
    transformation_text_omitted: bool = False


class OpenMetadataProfileSummary(BaseModel):
    """Aggregate-only table profile safe for the general catalog."""

    model_config = ConfigDict(extra="forbid")

    captured_at: datetime | None = None
    row_count: int | None = None
    column_count: int | None = None
    size_in_bytes: int | None = None


class OpenMetadataTableProjection(BaseModel):
    """Tenant-scoped observation derived from one OpenMetadata table."""

    model_config = ConfigDict(extra="forbid")

    projection_id: str
    source_authority: str = "openmetadata"
    source_release: str
    source_schema_uri: str = OPENMETADATA_TABLE_SCHEMA_URI
    lineage_schema_uri: str | None = None
    truth_status: str = "observed"
    external_entity_type: str = "table"
    external_entity_id: str
    name: str
    title: str
    fully_qualified_name: str
    description: str | None = None
    entity_version: str | None = None
    entity_status: str | None = None
    table_type: str | None = None
    service_type: str | None = None
    updated_at: datetime | None = None
    updated_by: str | None = None
    source_hash: str | None = None
    source_url: str | None = None
    owner_references: list[OpenMetadataReferenceProjection] = Field(default_factory=list)
    domain_references: list[OpenMetadataReferenceProjection] = Field(default_factory=list)
    data_product_references: list[OpenMetadataReferenceProjection] = Field(default_factory=list)
    data_contract_reference: OpenMetadataReferenceProjection | None = None
    database_schema_reference: OpenMetadataReferenceProjection | None = None
    database_reference: OpenMetadataReferenceProjection | None = None
    service_reference: OpenMetadataReferenceProjection | None = None
    tag_fqns: list[str] = Field(default_factory=list)
    columns: list[OpenMetadataColumnProjection] = Field(default_factory=list)
    profile_summary: OpenMetadataProfileSummary = Field(default_factory=OpenMetadataProfileSummary)
    lineage_edges: list[OpenMetadataLineageEdgeProjection] = Field(default_factory=list)
    omitted_fields: list[str] = Field(default_factory=list)


class OpenMetadataNormalizationRequest(BaseModel):
    """HTTP request for deterministic OpenMetadata table normalization."""

    model_config = ConfigDict(extra="forbid")

    tenant_id: str = Field(min_length=1, max_length=128, pattern=_TENANT_ID_PATTERN.pattern)
    source_release: str = Field(min_length=3, max_length=64, pattern=_RELEASE_PATTERN.pattern)
    table: dict[str, Any]
    lineage: dict[str, Any] | None = None


def _require_mapping(value: object, field_name: str) -> Mapping[str, Any]:
    """Return a mapping or raise a stable contract error."""

    if not isinstance(value, Mapping):
        raise OpenMetadataContractError(f"{field_name} must be an object")
    return value


def _optional_mapping(value: object, field_name: str) -> Mapping[str, Any] | None:
    """Return an optional mapping while rejecting wrong container types."""

    if value is None:
        return None
    return _require_mapping(value, field_name)


def _require_list(value: object, field_name: str, *, maximum: int) -> list[Any]:
    """Return a JSON-array-like list with a deterministic size bound."""

    if not isinstance(value, list):
        raise OpenMetadataContractError(f"{field_name} must be an array")
    if len(value) > maximum:
        raise OpenMetadataContractError(f"{field_name} exceeds {maximum} items")
    return value


def _optional_list(value: object, field_name: str, *, maximum: int) -> list[Any]:
    """Return an optional list, treating a missing value as an empty array."""

    if value is None:
        return []
    return _require_list(value, field_name, maximum=maximum)


def _text(
    value: object,
    field_name: str,
    *,
    required: bool = False,
    maximum: int = _MAX_TEXT_LENGTH,
) -> str | None:
    """Validate bounded text without coercing foreign scalar values."""

    if value is None:
        if required:
            raise OpenMetadataContractError(f"{field_name} is required")
        return None
    if not isinstance(value, str):
        raise OpenMetadataContractError(f"{field_name} must be a string")
    if required and not value:
        raise OpenMetadataContractError(f"{field_name} is required")
    if len(value) > maximum:
        raise OpenMetadataContractError(f"{field_name} exceeds {maximum} characters")
    if any(ord(character) < 32 and character not in "\t\n\r" for character in value):
        raise OpenMetadataContractError(f"{field_name} contains control characters")
    return value


def _uuid_text(value: object, field_name: str) -> str:
    """Validate an external UUID while preserving its canonical string form."""

    text = _text(value, field_name, required=True, maximum=64)
    assert text is not None
    try:
        return str(UUID(text))
    except (ValueError, AttributeError) as exc:
        raise OpenMetadataContractError(f"{field_name} must be a UUID") from exc


def _safe_url(value: object, field_name: str) -> str | None:
    """Allow only bounded HTTP(S) references in the general projection."""

    text = _text(value, field_name, maximum=2_048)
    if text is None:
        return None
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise OpenMetadataContractError(f"{field_name} must be an HTTP(S) URL")
    if parsed.username is not None or parsed.password is not None:
        raise OpenMetadataContractError(f"{field_name} must not contain credentials")
    return text


def _optional_non_negative_int(value: object, field_name: str) -> int | None:
    """Validate optional non-negative integer aggregates without bool coercion."""

    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise OpenMetadataContractError(f"{field_name} must be a non-negative integer")
    return value


def _epoch_milliseconds(value: object, field_name: str) -> datetime | None:
    """Convert an optional Unix epoch-millisecond timestamp to UTC."""

    milliseconds = _optional_non_negative_int(value, field_name)
    if milliseconds is None:
        return None
    try:
        return datetime.fromtimestamp(milliseconds / 1_000, tz=timezone.utc)
    except (OverflowError, OSError, ValueError) as exc:
        raise OpenMetadataContractError(f"{field_name} is outside the supported timestamp range") from exc


def _validate_source_release(source_release: object) -> str:
    """Limit the first adapter contract to explicitly declared 2.x releases."""

    release = _text(source_release, "source_release", required=True, maximum=64)
    assert release is not None
    if not _RELEASE_PATTERN.fullmatch(release):
        raise OpenMetadataContractError("source_release must identify an OpenMetadata 2.x release")
    return release


def _validate_tenant_id(tenant_id: object) -> str:
    """Validate the tenant token embedded in canonical CWL identifiers."""

    value = _text(tenant_id, "tenant_id", required=True, maximum=128)
    assert value is not None
    if not _TENANT_ID_PATTERN.fullmatch(value):
        raise OpenMetadataContractError("tenant_id contains unsupported characters")
    return value


def _validate_payload_budget(*payloads: object) -> None:
    """Bound direct-call payload complexity before extracting any metadata."""

    stack: list[tuple[object, int]] = [(payload, 1) for payload in payloads if payload is not None]
    seen_containers: set[int] = set()
    container_count = 0
    text_bytes = 0
    while stack:
        value, depth = stack.pop()
        if depth > 64:
            raise OpenMetadataContractError("payload nesting exceeds 64")
        if isinstance(value, str):
            text_bytes += len(value.encode("utf-8"))
            if text_bytes > _MAX_PAYLOAD_TEXT_BYTES:
                raise OpenMetadataContractError("payload text exceeds 8388608 bytes")
            continue
        if isinstance(value, Mapping):
            identity = id(value)
            if identity in seen_containers:
                raise OpenMetadataContractError("payload contains a cyclic container")
            seen_containers.add(identity)
            container_count += 1
            if container_count > _MAX_PAYLOAD_CONTAINERS:
                raise OpenMetadataContractError("payload exceeds 100000 containers")
            stack.extend((item, depth + 1) for pair in value.items() for item in pair)
            continue
        if isinstance(value, list):
            identity = id(value)
            if identity in seen_containers:
                raise OpenMetadataContractError("payload contains a cyclic container")
            seen_containers.add(identity)
            container_count += 1
            if container_count > _MAX_PAYLOAD_CONTAINERS:
                raise OpenMetadataContractError("payload exceeds 100000 containers")
            stack.extend((item, depth + 1) for item in value)


def _stable_unique(values: Sequence[str]) -> list[str]:
    """Deduplicate strings without changing source order."""

    return list(dict.fromkeys(values))


def _reference(value: object, field_name: str) -> OpenMetadataReferenceProjection:
    """Normalize one OpenMetadata entity reference."""

    payload = _require_mapping(value, field_name)
    entity_id = _uuid_text(payload.get("id"), f"{field_name}.id")
    entity_type = _text(payload.get("type"), f"{field_name}.type", required=True, maximum=128)
    name = _text(payload.get("name"), f"{field_name}.name", required=True, maximum=512)
    label = _text(payload.get("displayName"), f"{field_name}.displayName", maximum=512) or name
    assert entity_type is not None and name is not None and label is not None
    return OpenMetadataReferenceProjection(
        external_entity_id=entity_id,
        entity_type=entity_type,
        label=label,
        fully_qualified_name=_text(
            payload.get("fullyQualifiedName"),
            f"{field_name}.fullyQualifiedName",
            maximum=2_048,
        ),
        href=_safe_url(payload.get("href"), f"{field_name}.href"),
    )


def _reference_list(value: object, field_name: str) -> list[OpenMetadataReferenceProjection]:
    """Normalize a bounded reference array and reject ambiguous duplicate IDs."""

    references = _optional_list(value, field_name, maximum=_MAX_REFERENCES)
    normalized: list[OpenMetadataReferenceProjection] = []
    identities: dict[str, OpenMetadataReferenceProjection] = {}
    for index, item in enumerate(references):
        reference = _reference(item, f"{field_name}[{index}]")
        prior = identities.get(reference.external_entity_id)
        if prior is not None and prior != reference:
            raise OpenMetadataContractError(
                f"{field_name} contains conflicting reference id: {reference.external_entity_id}"
            )
        if prior is None:
            identities[reference.external_entity_id] = reference
            normalized.append(reference)
    return normalized


def _tags(value: object, field_name: str) -> list[str]:
    """Extract stable tag FQNs without copying tag descriptions or extensions."""

    items = _optional_list(value, field_name, maximum=_MAX_REFERENCES)
    tag_fqns: list[str] = []
    for index, item in enumerate(items):
        payload = _require_mapping(item, f"{field_name}[{index}]")
        tag_fqn = _text(payload.get("tagFQN"), f"{field_name}[{index}].tagFQN", required=True, maximum=1_024)
        assert tag_fqn is not None
        tag_fqns.append(tag_fqn)
    return _stable_unique(tag_fqns)


def _column_nullable(constraint: object, field_name: str) -> bool | None:
    """Map explicit OpenMetadata null constraints without inventing a default."""

    value = _text(constraint, field_name, maximum=64)
    if value in {"PRIMARY_KEY", "NOT_NULL"}:
        return False
    if value == "NULL":
        return True
    return None


def _flatten_columns(value: object, omitted_fields: set[str]) -> list[OpenMetadataColumnProjection]:
    """Flatten nested OpenMetadata columns using bounded iterative traversal."""

    roots = _require_list(value, "table.columns", maximum=_MAX_COLUMNS)
    stack: list[tuple[object, str, int, str]] = [
        (column, "", 1, f"table.columns[{index}]")
        for index, column in reversed(list(enumerate(roots)))
    ]
    paths: set[str] = set()
    normalized: list[OpenMetadataColumnProjection] = []
    while stack:
        raw_column, parent_path, depth, field_name = stack.pop()
        if depth > _MAX_COLUMN_DEPTH:
            raise OpenMetadataContractError(f"column nesting exceeds {_MAX_COLUMN_DEPTH}")
        if len(normalized) >= _MAX_COLUMNS:
            raise OpenMetadataContractError(f"table.columns exceeds {_MAX_COLUMNS} items")
        column = _require_mapping(raw_column, field_name)
        name = _text(column.get("name"), f"{field_name}.name", required=True, maximum=512)
        data_type = _text(column.get("dataType"), f"{field_name}.dataType", required=True, maximum=128)
        assert name is not None and data_type is not None
        path = f"{parent_path}.{name}" if parent_path else name
        if path in paths:
            raise OpenMetadataContractError(f"duplicate column path: {path}")
        paths.add(path)
        if column.get("profile") is not None:
            omitted_fields.add("table.columns[].profile")
        if column.get("customMetrics") is not None:
            omitted_fields.add("table.columns[].customMetrics")
        if column.get("extension") is not None:
            omitted_fields.add("table.columns[].extension")
        normalized.append(
            OpenMetadataColumnProjection(
                column_path=path,
                name=name,
                data_type=data_type,
                data_type_display=_text(
                    column.get("dataTypeDisplay"),
                    f"{field_name}.dataTypeDisplay",
                    maximum=2_048,
                ),
                nullable=_column_nullable(column.get("constraint"), f"{field_name}.constraint"),
                description=_text(column.get("description"), f"{field_name}.description"),
                ordinal_position=_optional_non_negative_int(
                    column.get("ordinalPosition"),
                    f"{field_name}.ordinalPosition",
                ),
                fully_qualified_name=_text(
                    column.get("fullyQualifiedName"),
                    f"{field_name}.fullyQualifiedName",
                    maximum=2_048,
                ),
                tag_fqns=_tags(column.get("tags"), f"{field_name}.tags"),
            )
        )
        children = _optional_list(column.get("children"), f"{field_name}.children", maximum=_MAX_COLUMNS)
        stack.extend(
            (child, path, depth + 1, f"{field_name}.children[{index}]")
            for index, child in reversed(list(enumerate(children)))
        )
    return normalized


def _profile_summary(value: object) -> OpenMetadataProfileSummary:
    """Normalize only safe table-level profile aggregates."""

    profile = _optional_mapping(value, "table.profile")
    if profile is None:
        return OpenMetadataProfileSummary()
    return OpenMetadataProfileSummary(
        captured_at=_epoch_milliseconds(profile.get("timestamp"), "table.profile.timestamp"),
        row_count=_optional_non_negative_int(profile.get("rowCount"), "table.profile.rowCount"),
        column_count=_optional_non_negative_int(profile.get("columnCount"), "table.profile.columnCount"),
        size_in_bytes=_optional_non_negative_int(profile.get("sizeInByte"), "table.profile.sizeInByte"),
    )


def _optional_reference(value: object, field_name: str) -> OpenMetadataReferenceProjection | None:
    """Normalize an optional entity reference."""

    if value is None:
        return None
    return _reference(value, field_name)


def _register_reference(
    references: dict[str, OpenMetadataReferenceProjection],
    reference: OpenMetadataReferenceProjection,
    field_name: str,
) -> None:
    """Add a lineage reference or reject conflicting reuse of the same UUID."""

    prior = references.get(reference.external_entity_id)
    if prior is not None and prior != reference:
        raise OpenMetadataContractError(
            f"{field_name} conflicts with reference id: {reference.external_entity_id}"
        )
    references[reference.external_entity_id] = reference


def _column_mappings(value: object, omitted_fields: set[str]) -> list[OpenMetadataColumnLineageProjection]:
    """Normalize column identities while intentionally omitting transformations."""

    items = _optional_list(value, "lineage.lineageDetails.columnsLineage", maximum=_MAX_COLUMN_MAPPINGS)
    mappings: list[OpenMetadataColumnLineageProjection] = []
    for index, item in enumerate(items):
        field_name = f"lineage.lineageDetails.columnsLineage[{index}]"
        payload = _require_mapping(item, field_name)
        source_items = _require_list(
            payload.get("fromColumns"),
            f"{field_name}.fromColumns",
            maximum=_MAX_REFERENCES,
        )
        from_columns: list[str] = []
        for source_index, source_column in enumerate(source_items):
            normalized = _text(
                source_column,
                f"{field_name}.fromColumns[{source_index}]",
                required=True,
                maximum=2_048,
            )
            assert normalized is not None
            from_columns.append(normalized)
        to_column = _text(payload.get("toColumn"), f"{field_name}.toColumn", required=True, maximum=2_048)
        assert to_column is not None
        if payload.get("function") is not None:
            omitted_fields.add("lineage.lineageDetails.columnsLineage.function")
        mappings.append(
            OpenMetadataColumnLineageProjection(
                from_columns=_stable_unique(from_columns),
                to_column=to_column,
            )
        )
    return mappings


def _lineage_edges(
    value: object,
    *,
    table_id: str,
    omitted_fields: set[str],
) -> list[OpenMetadataLineageEdgeProjection]:
    """Normalize a complete bounded lineage response for the supplied table."""

    if value is None:
        return []
    lineage = _require_mapping(value, "lineage")
    primary = _reference(lineage.get("entity"), "lineage.entity")
    if primary.external_entity_id != table_id:
        raise OpenMetadataContractError("lineage entity does not match table id")

    references = {primary.external_entity_id: primary}
    for index, item in enumerate(_optional_list(lineage.get("nodes"), "lineage.nodes", maximum=_MAX_REFERENCES)):
        reference = _reference(item, f"lineage.nodes[{index}]")
        _register_reference(references, reference, f"lineage.nodes[{index}]")

    edge_payloads: list[tuple[object, str]] = []
    for group_name in ("upstreamEdges", "downstreamEdges"):
        group = _optional_list(lineage.get(group_name), f"lineage.{group_name}", maximum=_MAX_LINEAGE_EDGES)
        edge_payloads.extend((edge, f"lineage.{group_name}[{index}]") for index, edge in enumerate(group))
    if len(edge_payloads) > _MAX_LINEAGE_EDGES:
        raise OpenMetadataContractError(f"lineage edges exceed {_MAX_LINEAGE_EDGES} items")

    normalized: list[OpenMetadataLineageEdgeProjection] = []
    for raw_edge, field_name in edge_payloads:
        edge = _require_mapping(raw_edge, field_name)
        from_id = _uuid_text(edge.get("fromEntity"), f"{field_name}.fromEntity")
        to_id = _uuid_text(edge.get("toEntity"), f"{field_name}.toEntity")
        if from_id not in references or to_id not in references:
            raise OpenMetadataContractError("unknown lineage endpoint")
        details = _optional_mapping(edge.get("lineageDetails"), f"{field_name}.lineageDetails")
        source = "Manual"
        pipeline = None
        column_mappings: list[OpenMetadataColumnLineageProjection] = []
        transformation_text_omitted = False
        if details is not None:
            source = _text(details.get("source"), f"{field_name}.lineageDetails.source", maximum=128) or "Manual"
            pipeline = _optional_reference(details.get("pipeline"), f"{field_name}.lineageDetails.pipeline")
            column_mappings = _column_mappings(details.get("columnsLineage"), omitted_fields)
            if details.get("sqlQuery") is not None:
                omitted_fields.add("lineage.lineageDetails.sqlQuery")
                transformation_text_omitted = True
            if any(
                isinstance(item, Mapping) and item.get("function") is not None
                for item in _optional_list(
                    details.get("columnsLineage"),
                    f"{field_name}.lineageDetails.columnsLineage",
                    maximum=_MAX_COLUMN_MAPPINGS,
                )
            ):
                transformation_text_omitted = True
        normalized.append(
            OpenMetadataLineageEdgeProjection(
                from_reference=references[from_id],
                to_reference=references[to_id],
                source=source,
                pipeline_reference=pipeline,
                column_mappings=column_mappings,
                transformation_text_omitted=transformation_text_omitted,
            )
        )
    return normalized


def _record_omitted_table_fields(table: Mapping[str, Any], omitted_fields: set[str]) -> None:
    """Record sensitive or unbounded source fields intentionally not projected."""

    for source_field in ("joins", "queries", "sampleData", "schemaDefinition", "extension"):
        if table.get(source_field) is not None:
            omitted_fields.add(f"table.{source_field}")
    data_model = table.get("dataModel")
    if isinstance(data_model, Mapping):
        for source_field in ("rawSql", "sql"):
            if data_model.get(source_field) is not None:
                omitted_fields.add(f"table.dataModel.{source_field}")


def normalize_openmetadata_table_snapshot(
    *,
    tenant_id: str,
    source_release: str,
    table: Mapping[str, Any],
    lineage: Mapping[str, Any] | None = None,
) -> OpenMetadataTableProjection:
    """Normalize one OpenMetadata 2.x Table and optional EntityLineage payload.

    The result is an `observed` projection suitable for policy review. It is not
    an authoritative replacement for the source system or any CWL domain owner.
    """

    tenant = _validate_tenant_id(tenant_id)
    release = _validate_source_release(source_release)
    _validate_payload_budget(table, lineage)
    table_payload = _require_mapping(table, "table")
    table_id = _uuid_text(table_payload.get("id"), "table.id")
    name = _text(table_payload.get("name"), "table.name", required=True, maximum=512)
    assert name is not None
    fully_qualified_name = _text(
        table_payload.get("fullyQualifiedName"),
        "table.fullyQualifiedName",
        required=True,
        maximum=2_048,
    )
    assert fully_qualified_name is not None
    title = _text(table_payload.get("displayName"), "table.displayName", maximum=512) or name

    omitted_fields: set[str] = set()
    _record_omitted_table_fields(table_payload, omitted_fields)
    columns = _flatten_columns(table_payload.get("columns"), omitted_fields)
    lineage_edges = _lineage_edges(lineage, table_id=table_id, omitted_fields=omitted_fields)

    entity_version = table_payload.get("version")
    if entity_version is not None and (isinstance(entity_version, bool) or not isinstance(entity_version, (int, float))):
        raise OpenMetadataContractError("table.version must be numeric")

    source_hash = _text(table_payload.get("sourceHash"), "table.sourceHash", maximum=128)
    updated_by = _text(table_payload.get("updatedBy"), "table.updatedBy", maximum=512)
    return OpenMetadataTableProjection(
        projection_id=f"urn:cwl:{tenant}:sdp:openmetadata_table:{table_id}",
        source_release=release,
        lineage_schema_uri=OPENMETADATA_LINEAGE_SCHEMA_URI if lineage is not None else None,
        external_entity_id=table_id,
        name=name,
        title=title,
        fully_qualified_name=fully_qualified_name,
        description=_text(table_payload.get("description"), "table.description"),
        entity_version=str(entity_version) if entity_version is not None else None,
        entity_status=_text(table_payload.get("entityStatus"), "table.entityStatus", maximum=128),
        table_type=_text(table_payload.get("tableType"), "table.tableType", maximum=128),
        service_type=_text(table_payload.get("serviceType"), "table.serviceType", maximum=128),
        updated_at=_epoch_milliseconds(table_payload.get("updatedAt"), "table.updatedAt"),
        updated_by=updated_by,
        source_hash=source_hash,
        source_url=_safe_url(table_payload.get("sourceUrl"), "table.sourceUrl"),
        owner_references=_reference_list(table_payload.get("owners"), "table.owners"),
        domain_references=_reference_list(table_payload.get("domains"), "table.domains"),
        data_product_references=_reference_list(table_payload.get("dataProducts"), "table.dataProducts"),
        data_contract_reference=_optional_reference(table_payload.get("dataContract"), "table.dataContract"),
        database_schema_reference=_optional_reference(table_payload.get("databaseSchema"), "table.databaseSchema"),
        database_reference=_optional_reference(table_payload.get("database"), "table.database"),
        service_reference=_optional_reference(table_payload.get("service"), "table.service"),
        tag_fqns=_tags(table_payload.get("tags"), "table.tags"),
        columns=columns,
        profile_summary=_profile_summary(table_payload.get("profile")),
        lineage_edges=lineage_edges,
        omitted_fields=sorted(omitted_fields),
    )
