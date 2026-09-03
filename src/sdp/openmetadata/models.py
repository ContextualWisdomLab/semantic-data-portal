"""Typed projections for the OpenMetadata 2.x boundary."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

OPENMETADATA_TABLE_SCHEMA_URI = "https://open-metadata.org/schema/entity/data/table.json"
OPENMETADATA_LINEAGE_SCHEMA_URI = "https://open-metadata.org/schema/type/entityLineage.json"


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
    source_authority: Literal["openmetadata"] = "openmetadata"
    source_release: str
    source_schema_uri: str = OPENMETADATA_TABLE_SCHEMA_URI
    lineage_schema_uri: str | None = None
    truth_status: Literal["observed"] = "observed"
    external_entity_type: Literal["table"] = "table"
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

    tenant_id: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$",
    )
    source_release: str = Field(
        min_length=3,
        max_length=64,
        pattern=r"^2\.(?:0|[1-9]\d*)(?:\.(?:0|[1-9]\d*))?(?:-release)?$",
    )
    table: dict[str, Any]
    lineage: dict[str, Any] | None = None
