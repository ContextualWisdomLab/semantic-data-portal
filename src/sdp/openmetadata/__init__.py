"""OpenMetadata 2.x read-only anti-corruption boundary."""

from .errors import OpenMetadataContractError
from .models import (
    OPENMETADATA_LINEAGE_SCHEMA_URI,
    OPENMETADATA_TABLE_SCHEMA_URI,
    OpenMetadataColumnLineageProjection,
    OpenMetadataColumnProjection,
    OpenMetadataLineageEdgeProjection,
    OpenMetadataNormalizationRequest,
    OpenMetadataProfileSummary,
    OpenMetadataReferenceProjection,
    OpenMetadataTableProjection,
)
from .normalizer import normalize_openmetadata_table_snapshot

__all__ = [
    "OPENMETADATA_LINEAGE_SCHEMA_URI",
    "OPENMETADATA_TABLE_SCHEMA_URI",
    "OpenMetadataColumnLineageProjection",
    "OpenMetadataColumnProjection",
    "OpenMetadataContractError",
    "OpenMetadataLineageEdgeProjection",
    "OpenMetadataNormalizationRequest",
    "OpenMetadataProfileSummary",
    "OpenMetadataReferenceProjection",
    "OpenMetadataTableProjection",
    "normalize_openmetadata_table_snapshot",
]
