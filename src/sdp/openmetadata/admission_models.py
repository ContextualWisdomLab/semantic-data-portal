"""Typed contracts for non-mutating OpenMetadata admission previews."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from .admission_identity import (
    RECEIPT_CONTRACT_VERSION,
    build_admission_candidate_id,
    build_admission_receipt_id,
    build_admission_replay_key,
    normalize_observed_at,
)
from .models import OpenMetadataTableProjection
from .source_identity import build_openmetadata_projection_id
from .structural_digest import DIGEST_PROFILE_ID, structural_sha256

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

        try:
            return normalize_observed_at(value)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc


class OpenMetadataAdmissionReceipt(BaseModel):
    """Unsigned self-consistency evidence for one candidate observation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    receipt_contract_version: Literal["1.0.0"] = RECEIPT_CONTRACT_VERSION
    digest_profile_id: Literal["cwl-json-structural-sha256-v1"] = (
        DIGEST_PROFILE_ID
    )
    admission_candidate_id: str
    receipt_id: str
    admission_status: Literal["accepted_for_review"] = "accepted_for_review"
    integrity_assurance: Literal["unsigned_self_consistency"] = (
        "unsigned_self_consistency"
    )
    source_origin_attested: Literal[False] = False
    catalog_admission_performed: Literal[False] = False
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

    @field_validator("observed_at")
    @classmethod
    def normalize_receipt_time(cls, value: datetime) -> datetime:
        """Normalize transported observation time before identity checks."""

        try:
            return normalize_observed_at(value)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc

    @model_validator(mode="after")
    def validate_evidence_integrity(self) -> OpenMetadataAdmissionReceipt:
        """Recompute every receipt identity derivable from transported evidence."""

        projection = self.projection
        comparisons = (
            (
                self.source_instance_id,
                projection.source_instance_id,
                "source_instance_id does not match projection",
            ),
            (
                self.source_authority,
                projection.source_authority,
                "source_authority does not match projection",
            ),
            (
                self.source_release,
                projection.source_release,
                "source_release does not match projection",
            ),
            (
                self.compatibility_profile_id,
                projection.compatibility_profile_id,
                "compatibility_profile_id does not match projection",
            ),
            (
                self.upstream_repository,
                projection.upstream_repository,
                "upstream_repository does not match projection",
            ),
            (
                self.upstream_revision,
                projection.upstream_revision,
                "upstream_revision does not match projection",
            ),
            (
                self.external_entity_id,
                projection.external_entity_id,
                "external_entity_id does not match projection",
            ),
            (
                self.omitted_fields,
                projection.omitted_fields,
                "omitted_fields do not match projection",
            ),
        )
        for receipt_value, projection_value, message in comparisons:
            if receipt_value != projection_value:
                raise ValueError(message)

        expected_projection_id = build_openmetadata_projection_id(
            tenant_id=self.tenant_id,
            source_instance_id=self.source_instance_id,
            external_entity_id=self.external_entity_id,
        )
        if projection.projection_id != expected_projection_id:
            raise ValueError("projection_id does not match receipt scope")

        expected_projection_digest = structural_sha256(
            projection.model_dump(mode="json"),
            "projection",
        )
        if self.projection_digest != expected_projection_digest:
            raise ValueError("projection_digest does not match projection")

        expected_replay_key = build_admission_replay_key(
            tenant_id=self.tenant_id,
            source_instance_id=self.source_instance_id,
            source_authority=self.source_authority,
            source_release=self.source_release,
            compatibility_profile_id=self.compatibility_profile_id,
            upstream_repository=self.upstream_repository,
            upstream_revision=self.upstream_revision,
            external_entity_id=self.external_entity_id,
            source_snapshot_digest=self.source_snapshot_digest,
            projection_digest=self.projection_digest,
        )
        if self.replay_key != expected_replay_key:
            raise ValueError("replay_key does not match receipt fields")

        expected_candidate_id = build_admission_candidate_id(
            tenant_id=self.tenant_id,
            replay_key=self.replay_key,
        )
        if self.admission_candidate_id != expected_candidate_id:
            raise ValueError(
                "admission_candidate_id does not match replay_key"
            )

        expected_receipt_id = build_admission_receipt_id(
            tenant_id=self.tenant_id,
            admission_candidate_id=self.admission_candidate_id,
            observed_at=self.observed_at,
        )
        if self.receipt_id != expected_receipt_id:
            raise ValueError(
                "receipt_id does not match candidate and observation time"
            )
        return self
