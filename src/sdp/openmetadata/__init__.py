"""OpenMetadata 2.x read-only anti-corruption boundary."""

from .admission_models import (
    OpenMetadataAdmissionPreviewRequest,
    OpenMetadataAdmissionReceipt,
)
from .admission_preview import preview_openmetadata_table_admission
from .compatibility import (
    OPENMETADATA_2_0_1_PROFILE,
    OpenMetadataReleaseProfile,
    resolve_openmetadata_release_profile,
)
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
from .structural_digest import (
    DIGEST_PROFILE_ID,
    encode_structural_json,
    structural_sha256,
)
from .verified_normalizer import normalize_openmetadata_table_snapshot

__all__ = [
    "DIGEST_PROFILE_ID",
    "OPENMETADATA_2_0_1_PROFILE",
    "OPENMETADATA_LINEAGE_SCHEMA_URI",
    "OPENMETADATA_TABLE_SCHEMA_URI",
    "OpenMetadataAdmissionPreviewRequest",
    "OpenMetadataAdmissionReceipt",
    "OpenMetadataColumnLineageProjection",
    "OpenMetadataColumnProjection",
    "OpenMetadataContractError",
    "OpenMetadataLineageEdgeProjection",
    "OpenMetadataNormalizationRequest",
    "OpenMetadataProfileSummary",
    "OpenMetadataReferenceProjection",
    "OpenMetadataReleaseProfile",
    "OpenMetadataTableProjection",
    "encode_structural_json",
    "normalize_openmetadata_table_snapshot",
    "preview_openmetadata_table_admission",
    "resolve_openmetadata_release_profile",
    "structural_sha256",
]
