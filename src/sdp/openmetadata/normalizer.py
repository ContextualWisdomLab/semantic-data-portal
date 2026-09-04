"""Deterministic OpenMetadata Table and EntityLineage normalization."""

from __future__ import annotations

from collections.abc import Mapping
from math import isfinite
from typing import Any

from .compatibility import resolve_openmetadata_release_profile
from .errors import OpenMetadataContractError
from .source_identity import validate_source_instance_id
from .models import (
    OPENMETADATA_LINEAGE_SCHEMA_URI,
    OpenMetadataColumnLineageProjection,
    OpenMetadataColumnProjection,
    OpenMetadataLineageEdgeProjection,
    OpenMetadataProfileSummary,
    OpenMetadataReferenceProjection,
    OpenMetadataTableProjection,
)
from .validation import (
    _epoch_milliseconds,
    _optional_list,
    _optional_mapping,
    _optional_non_negative_int,
    _require_list,
    _require_mapping,
    _required_text,
    _safe_url,
    _stable_unique,
    _text,
    _uuid_text,
    _validate_payload_budget,
    _validate_tenant_id,
)

_MAX_COLUMN_DEPTH = 16
_MAX_COLUMNS = 10_000
_MAX_REFERENCES = 1_000
_MAX_LINEAGE_EDGES = 20_000
_MAX_COLUMN_MAPPINGS = 20_000
_REFERENCE_IDENTITY_FIELDS = ("name", "fully_qualified_name")
_REFERENCE_ENRICHMENT_FIELDS = ("display_name", "href")


def _reference_label(reference: OpenMetadataReferenceProjection) -> str | None:
    """Return the best non-invented label carried by one external reference."""

    return (
        reference.display_name
        or reference.name
        or reference.fully_qualified_name
    )


def _register_reference(
    references: dict[str, OpenMetadataReferenceProjection],
    reference: OpenMetadataReferenceProjection,
    field_name: str,
) -> OpenMetadataReferenceProjection:
    """Register or enrich one UUID while rejecting snapshot-wide conflicts."""

    prior = references.get(reference.external_entity_id)
    if prior is None:
        reference.label = _reference_label(reference)
        references[reference.external_entity_id] = reference
        return reference

    if prior.entity_type != reference.entity_type:
        raise OpenMetadataContractError(
            f"{field_name} conflicts with reference id: "
            f"{reference.external_entity_id}"
        )
    for attribute_name in _REFERENCE_IDENTITY_FIELDS:
        prior_value = getattr(prior, attribute_name)
        candidate_value = getattr(reference, attribute_name)
        if (
            prior_value is not None
            and candidate_value is not None
            and prior_value != candidate_value
        ):
            raise OpenMetadataContractError(
                f"{field_name} conflicts with reference id: "
                f"{reference.external_entity_id}"
            )
        if prior_value is None and candidate_value is not None:
            setattr(prior, attribute_name, candidate_value)
    for attribute_name in _REFERENCE_ENRICHMENT_FIELDS:
        if getattr(prior, attribute_name) is None:
            candidate_value = getattr(reference, attribute_name)
            if candidate_value is not None:
                setattr(prior, attribute_name, candidate_value)
    prior.label = _reference_label(prior)
    return prior


def _reference(
    value: object,
    field_name: str,
    *,
    references: dict[str, OpenMetadataReferenceProjection] | None = None,
) -> OpenMetadataReferenceProjection:
    """Normalize one schema-valid OpenMetadata entity reference."""

    payload = _require_mapping(value, field_name)
    reference = OpenMetadataReferenceProjection(
        external_entity_id=_uuid_text(
            payload.get("id"),
            f"{field_name}.id",
        ),
        entity_type=_required_text(
            payload.get("type"),
            f"{field_name}.type",
            maximum=128,
        ),
        name=_text(
            payload.get("name"),
            f"{field_name}.name",
            maximum=512,
        ),
        display_name=_text(
            payload.get("displayName"),
            f"{field_name}.displayName",
            maximum=512,
        ),
        fully_qualified_name=_text(
            payload.get("fullyQualifiedName"),
            f"{field_name}.fullyQualifiedName",
            maximum=2_048,
        ),
        href=_safe_url(payload.get("href"), f"{field_name}.href"),
    )
    reference.label = _reference_label(reference)
    if references is None:
        return reference
    return _register_reference(references, reference, field_name)


def _reference_list(
    value: object,
    field_name: str,
    *,
    references: dict[str, OpenMetadataReferenceProjection] | None = None,
) -> list[OpenMetadataReferenceProjection]:
    """Normalize a bounded reference array with stable local deduplication."""

    source_items = _optional_list(
        value,
        field_name,
        maximum=_MAX_REFERENCES,
    )
    registry = references if references is not None else {}
    normalized: list[OpenMetadataReferenceProjection] = []
    local_identities: set[str] = set()
    for index, item in enumerate(source_items):
        reference = _reference(
            item,
            f"{field_name}[{index}]",
            references=registry,
        )
        if reference.external_entity_id not in local_identities:
            local_identities.add(reference.external_entity_id)
            normalized.append(reference)
    return normalized


def _optional_reference(
    value: object,
    field_name: str,
    *,
    references: dict[str, OpenMetadataReferenceProjection] | None = None,
) -> OpenMetadataReferenceProjection | None:
    """Normalize an optional entity reference."""

    if value is None:
        return None
    return _reference(value, field_name, references=references)


def _tags(value: object, field_name: str) -> list[str]:
    """Extract stable tag FQNs without copying descriptions or extensions."""

    items = _optional_list(value, field_name, maximum=_MAX_REFERENCES)
    tag_fqns: list[str] = []
    for index, item in enumerate(items):
        payload = _require_mapping(item, f"{field_name}[{index}]")
        tag_fqns.append(
            _required_text(
                payload.get("tagFQN"),
                f"{field_name}[{index}].tagFQN",
                maximum=1_024,
            )
        )
    return _stable_unique(tag_fqns)


def _column_nullable(constraint: object, field_name: str) -> bool | None:
    """Map explicit null constraints without inventing a default."""

    value = _text(constraint, field_name, maximum=64)
    if value in {"PRIMARY_KEY", "NOT_NULL"}:
        return False
    if value == "NULL":
        return True
    return None


def _flatten_columns(
    value: object,
    omitted_fields: set[str],
) -> list[OpenMetadataColumnProjection]:
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
            raise OpenMetadataContractError(
                f"column nesting exceeds {_MAX_COLUMN_DEPTH}"
            )
        if len(normalized) >= _MAX_COLUMNS:
            raise OpenMetadataContractError(
                f"table.columns exceeds {_MAX_COLUMNS} items"
            )

        column = _require_mapping(raw_column, field_name)
        name = _required_text(
            column.get("name"),
            f"{field_name}.name",
            maximum=512,
        )
        data_type = _required_text(
            column.get("dataType"),
            f"{field_name}.dataType",
            maximum=128,
        )
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
                nullable=_column_nullable(
                    column.get("constraint"),
                    f"{field_name}.constraint",
                ),
                description=_text(
                    column.get("description"),
                    f"{field_name}.description",
                ),
                ordinal_position=_optional_non_negative_int(
                    column.get("ordinalPosition"),
                    f"{field_name}.ordinalPosition",
                ),
                fully_qualified_name=_text(
                    column.get("fullyQualifiedName"),
                    f"{field_name}.fullyQualifiedName",
                    maximum=2_048,
                ),
                tag_fqns=_tags(
                    column.get("tags"),
                    f"{field_name}.tags",
                ),
            )
        )

        children = _optional_list(
            column.get("children"),
            f"{field_name}.children",
            maximum=_MAX_COLUMNS,
        )
        stack.extend(
            (
                child,
                path,
                depth + 1,
                f"{field_name}.children[{index}]",
            )
            for index, child in reversed(list(enumerate(children)))
        )

    return normalized


def _profile_summary(value: object) -> OpenMetadataProfileSummary:
    """Normalize only safe table-level profile aggregates."""

    profile = _optional_mapping(value, "table.profile")
    if profile is None:
        return OpenMetadataProfileSummary()
    return OpenMetadataProfileSummary(
        captured_at=_epoch_milliseconds(
            profile.get("timestamp"),
            "table.profile.timestamp",
        ),
        row_count=_optional_non_negative_int(
            profile.get("rowCount"),
            "table.profile.rowCount",
        ),
        column_count=_optional_non_negative_int(
            profile.get("columnCount"),
            "table.profile.columnCount",
        ),
        size_in_bytes=_optional_non_negative_int(
            profile.get("sizeInByte"),
            "table.profile.sizeInByte",
        ),
    )


def _column_mappings(
    value: object,
    omitted_fields: set[str],
) -> list[OpenMetadataColumnLineageProjection]:
    """Normalize column identities while omitting transformation expressions."""

    items = _optional_list(
        value,
        "lineage.lineageDetails.columnsLineage",
        maximum=_MAX_COLUMN_MAPPINGS,
    )
    mappings: list[OpenMetadataColumnLineageProjection] = []
    for index, item in enumerate(items):
        field_name = f"lineage.lineageDetails.columnsLineage[{index}]"
        payload = _require_mapping(item, field_name)
        source_items = _require_list(
            payload.get("fromColumns"),
            f"{field_name}.fromColumns",
            maximum=_MAX_REFERENCES,
        )
        from_columns = [
            _required_text(
                source_column,
                f"{field_name}.fromColumns[{source_index}]",
                maximum=2_048,
            )
            for source_index, source_column in enumerate(source_items)
        ]
        to_column = _required_text(
            payload.get("toColumn"),
            f"{field_name}.toColumn",
            maximum=2_048,
        )
        if payload.get("function") is not None:
            omitted_fields.add(
                "lineage.lineageDetails.columnsLineage.function"
            )
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
    references: dict[str, OpenMetadataReferenceProjection],
) -> list[OpenMetadataLineageEdgeProjection]:
    """Normalize bounded lineage while preserving snapshot-wide identities."""

    if value is None:
        return []

    lineage = _require_mapping(value, "lineage")
    primary = _reference(
        lineage.get("entity"),
        "lineage.entity",
        references=references,
    )
    if primary.external_entity_id != table_id:
        raise OpenMetadataContractError(
            "lineage entity does not match table id"
        )

    lineage_endpoint_ids = {primary.external_entity_id}
    nodes = _optional_list(
        lineage.get("nodes"),
        "lineage.nodes",
        maximum=_MAX_REFERENCES,
    )
    for index, item in enumerate(nodes):
        reference = _reference(
            item,
            f"lineage.nodes[{index}]",
            references=references,
        )
        lineage_endpoint_ids.add(reference.external_entity_id)

    edge_payloads: list[tuple[object, str]] = []
    for group_name in ("upstreamEdges", "downstreamEdges"):
        group = _optional_list(
            lineage.get(group_name),
            f"lineage.{group_name}",
            maximum=_MAX_LINEAGE_EDGES,
        )
        edge_payloads.extend(
            (edge, f"lineage.{group_name}[{index}]")
            for index, edge in enumerate(group)
        )
    if len(edge_payloads) > _MAX_LINEAGE_EDGES:
        raise OpenMetadataContractError(
            f"lineage edges exceed {_MAX_LINEAGE_EDGES} items"
        )

    normalized: list[OpenMetadataLineageEdgeProjection] = []
    for raw_edge, field_name in edge_payloads:
        edge = _require_mapping(raw_edge, field_name)
        from_id = _uuid_text(
            edge.get("fromEntity"),
            f"{field_name}.fromEntity",
        )
        to_id = _uuid_text(
            edge.get("toEntity"),
            f"{field_name}.toEntity",
        )
        if (
            from_id not in lineage_endpoint_ids
            or to_id not in lineage_endpoint_ids
        ):
            raise OpenMetadataContractError("unknown lineage endpoint")

        details = _optional_mapping(
            edge.get("lineageDetails"),
            f"{field_name}.lineageDetails",
        )
        source = "Manual"
        pipeline = None
        column_mappings: list[OpenMetadataColumnLineageProjection] = []
        transformation_text_omitted = False
        if details is not None:
            source = (
                _text(
                    details.get("source"),
                    f"{field_name}.lineageDetails.source",
                    maximum=128,
                )
                or "Manual"
            )
            pipeline = _optional_reference(
                details.get("pipeline"),
                f"{field_name}.lineageDetails.pipeline",
                references=references,
            )
            column_mappings = _column_mappings(
                details.get("columnsLineage"),
                omitted_fields,
            )
            if details.get("sqlQuery") is not None:
                omitted_fields.add("lineage.lineageDetails.sqlQuery")
                transformation_text_omitted = True
            column_lineage = _optional_list(
                details.get("columnsLineage"),
                f"{field_name}.lineageDetails.columnsLineage",
                maximum=_MAX_COLUMN_MAPPINGS,
            )
            if any(
                isinstance(item, Mapping)
                and item.get("function") is not None
                for item in column_lineage
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


def _record_omitted_table_fields(
    table: Mapping[str, Any],
    omitted_fields: set[str],
) -> None:
    """Record sensitive or unbounded source fields not projected."""

    for source_field in (
        "joins",
        "queries",
        "sampleData",
        "schemaDefinition",
        "extension",
    ):
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
    source_instance_id: str,
    source_release: str,
    table: Mapping[str, Any],
    lineage: Mapping[str, Any] | None = None,
) -> OpenMetadataTableProjection:
    """Normalize a Table only under an exact verified compatibility profile."""

    tenant = _validate_tenant_id(tenant_id)
    source_instance = validate_source_instance_id(source_instance_id)
    profile = resolve_openmetadata_release_profile(source_release)
    _validate_payload_budget(table, lineage)

    table_payload = _require_mapping(table, "table")
    table_id = _uuid_text(table_payload.get("id"), "table.id")
    name = _required_text(
        table_payload.get("name"),
        "table.name",
        maximum=512,
    )
    display_name = _text(
        table_payload.get("displayName"),
        "table.displayName",
        maximum=512,
    )
    fully_qualified_name = _text(
        table_payload.get("fullyQualifiedName"),
        "table.fullyQualifiedName",
        maximum=2_048,
    )
    title = display_name or name

    references: dict[str, OpenMetadataReferenceProjection] = {}
    _register_reference(
        references,
        OpenMetadataReferenceProjection(
            external_entity_id=table_id,
            entity_type="table",
            name=name,
            display_name=display_name,
            label=title,
            fully_qualified_name=fully_qualified_name,
            href=_safe_url(table_payload.get("href"), "table.href"),
        ),
        "table",
    )

    owner_references = _reference_list(
        table_payload.get("owners"),
        "table.owners",
        references=references,
    )
    domain_references = _reference_list(
        table_payload.get("domains"),
        "table.domains",
        references=references,
    )
    data_product_references = _reference_list(
        table_payload.get("dataProducts"),
        "table.dataProducts",
        references=references,
    )
    data_contract_reference = _optional_reference(
        table_payload.get("dataContract"),
        "table.dataContract",
        references=references,
    )
    database_schema_reference = _optional_reference(
        table_payload.get("databaseSchema"),
        "table.databaseSchema",
        references=references,
    )
    database_reference = _optional_reference(
        table_payload.get("database"),
        "table.database",
        references=references,
    )
    service_reference = _optional_reference(
        table_payload.get("service"),
        "table.service",
        references=references,
    )

    omitted_fields: set[str] = set()
    _record_omitted_table_fields(table_payload, omitted_fields)
    columns = _flatten_columns(
        table_payload.get("columns"),
        omitted_fields,
    )
    lineage_edges = _lineage_edges(
        lineage,
        table_id=table_id,
        omitted_fields=omitted_fields,
        references=references,
    )

    entity_version = table_payload.get("version")
    if entity_version is not None:
        if (
            isinstance(entity_version, bool)
            or not isinstance(entity_version, (int, float))
        ):
            raise OpenMetadataContractError(
                "table.version must be numeric"
            )
        if isinstance(entity_version, float) and not isfinite(entity_version):
            raise OpenMetadataContractError(
                "table.version must be finite"
            )

    return OpenMetadataTableProjection(
        projection_id=(
            f"urn:cwl:{tenant}:sdp:openmetadata_table:"
            f"{source_instance}:{table_id}"
        ),
        source_instance_id=source_instance,
        source_release=profile.canonical_release,
        compatibility_profile_id=profile.profile_id,
        upstream_repository=profile.upstream_repository,
        upstream_revision=profile.upstream_revision,
        lineage_schema_uri=(
            OPENMETADATA_LINEAGE_SCHEMA_URI
            if lineage is not None
            else None
        ),
        external_entity_id=table_id,
        name=name,
        title=title,
        fully_qualified_name=fully_qualified_name,
        description=_text(
            table_payload.get("description"),
            "table.description",
        ),
        entity_version=(
            str(entity_version)
            if entity_version is not None
            else None
        ),
        entity_status=_text(
            table_payload.get("entityStatus"),
            "table.entityStatus",
            maximum=128,
        ),
        table_type=_text(
            table_payload.get("tableType"),
            "table.tableType",
            maximum=128,
        ),
        service_type=_text(
            table_payload.get("serviceType"),
            "table.serviceType",
            maximum=128,
        ),
        updated_at=_epoch_milliseconds(
            table_payload.get("updatedAt"),
            "table.updatedAt",
        ),
        updated_by=_text(
            table_payload.get("updatedBy"),
            "table.updatedBy",
            maximum=512,
        ),
        source_hash=_text(
            table_payload.get("sourceHash"),
            "table.sourceHash",
            maximum=128,
        ),
        source_url=_safe_url(
            table_payload.get("sourceUrl"),
            "table.sourceUrl",
        ),
        owner_references=owner_references,
        domain_references=domain_references,
        data_product_references=data_product_references,
        data_contract_reference=data_contract_reference,
        database_schema_reference=database_schema_reference,
        database_reference=database_reference,
        service_reference=service_reference,
        tag_fqns=_tags(
            table_payload.get("tags"),
            "table.tags",
        ),
        columns=columns,
        profile_summary=_profile_summary(table_payload.get("profile")),
        lineage_edges=lineage_edges,
        omitted_fields=sorted(omitted_fields),
    )
