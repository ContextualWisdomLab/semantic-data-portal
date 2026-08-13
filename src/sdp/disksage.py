"""Path-free DiskSage catalog preview contract.

The portal may enrich a candidate for semantic search, but this boundary never
registers a dataset or authorizes a local eviction.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

DISKSAGE_SCHEMA = "disksage.file-catalog-candidate-batch"
DISKSAGE_VERSION = 1
MAX_CANDIDATES = 200
MAX_EPOCH_MS = 253_402_300_799_999
PRODUCTION_TIME_PRECEDENCE = (
    "embedded_metadata",
    "explicit_filename_date",
    "filesystem_created",
    "filesystem_modified",
)
_FINGERPRINT = r"^[0-9a-f]{64}$"


class DiskSageMetadataEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: str = Field(min_length=1, max_length=128)
    value: str = Field(min_length=1, max_length=2048)
    source: str = Field(min_length=1, max_length=256)
    confidence: Literal["high", "medium", "low", "unknown"]


class DiskSageCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_fingerprint: str = Field(pattern=_FINGERPRINT)
    review_fingerprint: str = Field(pattern=_FINGERPRINT)
    destination_provider: Literal["icloud", "onedrive", "google-drive"]
    destination_account_scope: Literal["personal", "organization", "shared", "unknown"]
    archive_kind: Literal[
        "document",
        "media",
        "archive",
        "dataset",
        "backup",
        "creative",
        "incomplete-download",
    ]
    bytes: int = Field(ge=0)
    created_ms: int = Field(gt=0, le=MAX_EPOCH_MS)
    modified_ms: int = Field(gt=0, le=MAX_EPOCH_MS)
    production_time_ms: int = Field(gt=0, le=MAX_EPOCH_MS)
    production_time_source: str = Field(min_length=1, max_length=256)
    production_time_confidence: Literal["high", "medium", "low", "unknown"]
    requires_review: bool
    review_reasons: list[str] = Field(max_length=128)
    content_title: str | None = Field(default=None, max_length=1024)
    content_authors: list[str] = Field(default_factory=list, max_length=64)
    content_context: list[str] = Field(default_factory=list, max_length=128)
    duration_ms: int | None = Field(default=None, ge=0)
    dataset_profile: dict[str, Any] | None = None
    metadata_evidence: list[DiskSageMetadataEvidence] = Field(max_length=256)
    blocked_reason: str | None = Field(default=None, max_length=256)

    @model_validator(mode="after")
    def validate_review_state(self) -> "DiskSageCandidate":
        if self.requires_review != bool(self.review_reasons):
            raise ValueError("requires_review must match review_reasons")
        if any(not value or len(value) > 256 for value in self.review_reasons):
            raise ValueError("review reason out of bounds")
        if any(not value or len(value) > 256 for value in self.content_authors):
            raise ValueError("content author out of bounds")
        if any(not value or len(value) > 1024 for value in self.content_context):
            raise ValueError("content context out of bounds")
        source_class = (
            "embedded_metadata"
            if self.production_time_source.startswith("embedded:")
            else {
                "filename:path-token": "explicit_filename_date",
                "filesystem:created": "filesystem_created",
                "filesystem:modified-fallback": "filesystem_modified",
            }.get(self.production_time_source)
        )
        if source_class is None:
            raise ValueError("unsupported production time source")
        if source_class != "embedded_metadata" and self.production_time_confidence != "low":
            raise ValueError("non-embedded production time must be low confidence")
        expected_field, expected_source = {
            "embedded_metadata": ("production-date", self.production_time_source),
            "explicit_filename_date": ("filename-date-hint", "filename:path-token"),
            "filesystem_created": ("filesystem-created-date", "filesystem:created"),
            "filesystem_modified": ("filesystem-modified-date", "filesystem:modified"),
        }[source_class]
        selected_date = datetime.fromtimestamp(
            self.production_time_ms / 1000, tz=timezone.utc
        ).date().isoformat()
        if not any(
            item.field == expected_field
            and item.source == expected_source
            and item.value == selected_date
            for item in self.metadata_evidence
        ):
            raise ValueError("selected production evidence mismatch")
        return self


class DiskSageCatalogBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema: Literal[DISKSAGE_SCHEMA]
    version: Literal[DISKSAGE_VERSION]
    production_time_precedence: tuple[str, ...]
    generated_at_ms: int = Field(gt=0, le=MAX_EPOCH_MS)
    candidates: list[DiskSageCandidate] = Field(min_length=1, max_length=MAX_CANDIDATES)

    @model_validator(mode="after")
    def validate_batch(self) -> "DiskSageCatalogBatch":
        if self.production_time_precedence != PRODUCTION_TIME_PRECEDENCE:
            raise ValueError("production time precedence mismatch")
        fingerprints = [candidate.candidate_fingerprint for candidate in self.candidates]
        if len(fingerprints) != len(set(fingerprints)):
            raise ValueError("duplicate candidate fingerprint")
        return self


def catalog_preview(batch: DiskSageCatalogBatch) -> dict[str, Any]:
    """Return a deterministic semantic projection without catalog persistence."""

    datasets = []
    for candidate in batch.candidates:
        profile = candidate.dataset_profile or {}
        datasets.append(
            {
                "id": f"disksage:{candidate.candidate_fingerprint}",
                "title": f"DiskSage {candidate.archive_kind} candidate",
                "description": "Path-free cloud archive candidate preview",
                "domain": "storage",
                "source_system": "disksage",
                "sensitivity": "private",
                "archive_kind": candidate.archive_kind,
                "provider": candidate.destination_provider,
                "account_scope": candidate.destination_account_scope,
                "bytes": candidate.bytes,
                "production_time_ms": candidate.production_time_ms,
                "production_time_source": candidate.production_time_source,
                "production_time_confidence": candidate.production_time_confidence,
                "content_metadata_present": bool(
                    candidate.content_title
                    or candidate.content_authors
                    or candidate.content_context
                ),
                "metadata_evidence_count": len(candidate.metadata_evidence),
                "profile_present": bool(profile),
                "ontology_class": "disksage:CloudArchiveCandidate",
                "hasArtifactType": "disksage:CloudArchiveCandidate",
                "ontology_relations": [
                    "disksage:candidate --disksage:targetsProvider--> provider",
                    "disksage:candidate --disksage:hasProductionTime--> time",
                ],
                "requires_review": candidate.requires_review,
                "blocked_reason": candidate.blocked_reason,
            }
        )
    return {
        "schema": "semantic-data-portal.disksage.catalog-preview",
        "source_schema": DISKSAGE_SCHEMA,
        "source_version": DISKSAGE_VERSION,
        "generated_at_ms": batch.generated_at_ms,
        "candidate_count": len(datasets),
        "datasets": datasets,
        "catalog_write_executed": False,
        "eviction_authorized": False,
        "storage_coordinates_present": False,
        "copy_authorized": False,
        "persistable_as_file_asset": False,
    }
