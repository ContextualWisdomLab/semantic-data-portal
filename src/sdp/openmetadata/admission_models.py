"""Typed contracts for non-mutating OpenMetadata admission previews."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .models import OpenMetadataTableProjection

_DIGEST_PATTERN = r"^sha256:[0-9a-f]{64}$"
_IDENTIFIER_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$"
_RELEASE_PATTERN = (
    r"^2\.(?:0|[1-9]\d*)"
    r"(?:\.(?:0|[1-9]\d*))?(?:-release)?$"
)


class OpenMetadataAdmissionPreviewRequest(BaseModel):
    """Request a deterministic receipt without mutating the catalog."""

    model_config = ConfigDict(extra="forbid")

    tenant_id: str = Field(
        min_length=1,
        max_length=128,
        pattern=_IDENTIFIER_PATTERN,
    )
    source_instance_id: str = Field(
        min_length=1,
        max_length=128,
        pattern=_IDENTIFIER_PATTERN,
    )
    source_release: str = Field(
        min_length=3,
        max_length=64,
        pattern=_RELEASE_PATTERN,
    )
    observed_at: datetime
    table: dict[str, Any]
    lineage: dict[str, Any] | None = None

    @field_validator("observed_at")
    @classmethod
    def require_observation_timezone(cls, value: datetime) -> datetime:
        """Normalize a timezone-qualified observation instant to UTC."""

        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("observed_at must include a timezone")
        return value.astimezone(timezone.utc)


class OpenMetadataAdmissionReceipt(BaseModel):
    """Evidence for one observation of a deterministic admission candidate."""

    model_config = ConfigDict(extra="forbid")

    receipt_contract_version: Literal["1.0.0"] = "1.0.0"
    digest_profile_id: Literal["cwl-json-structural-sha256-v1"] = (
        "cwl-json-structural-sha256-v1"
    )
    admission_candidate_id: str
    receipt_id: str
    admission_status: Literal["accepted_for_review"] = "accepted_for_review"
    tenant_id: str
    source_instance_id: str
    source_authority: Literal["openmetadata"] = "openmetadata"
    source_release: str
    compatibility_profile_id: str
    upstream_repository: str
    upstream_revision: str
    observed_at: datetime
    external_entity_id: str
    source_snapshot_digest: str = Field(pattern=_DIGEST_PATTERN)
    projection_digest: str = Field(pattern=_DIGEST_PATTERN)
    replay_key: str = Field(pattern=_DIGEST_PATTERN)
    omitted_fields: list[str] = Field(default_factory=list)
    raw_payload_persisted: Literal[False] = False
    catalog_mutation_performed: Literal[False] = False
    omitted_source_values_copied: Literal[False] = False
    projection: OpenMetadataTableProjection
