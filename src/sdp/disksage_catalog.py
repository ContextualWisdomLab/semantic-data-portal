"""Bounded, non-persisting DiskSage pre-copy catalog preview contracts."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


DISKSAGE_CATALOG_SCHEMA = "disksage.file-catalog-candidate-batch"
DISKSAGE_CATALOG_VERSION = 1
MAX_DISKSAGE_CATALOG_BODY_BYTES = 2 * 1024 * 1024
PRODUCTION_TIME_PRECEDENCE = (
    "embedded_metadata",
    "explicit_filename_date",
    "filesystem_created",
    "filesystem_modified",
)

CloudProvider = Literal["icloud", "onedrive", "google-drive"]
CloudAccountScope = Literal["personal", "organization", "shared", "unknown"]
ArchiveKind = Literal[
    "document",
    "media",
    "archive",
    "dataset",
    "backup",
    "creative",
    "incomplete-download",
]
Confidence = Literal["high", "medium", "low", "unknown"]
ProductionTimeSourceClass = Literal[
    "embedded_metadata",
    "explicit_filename_date",
    "filesystem_created",
    "filesystem_modified",
]

_HEX_64_PATTERN = r"^[0-9a-f]{64}$"
_MAX_DATETIME_EPOCH_MS = 253_402_300_799_999
_ARTIFACT_TYPE_LABELS: dict[str, str] = {
    "document": "Document",
    "media": "Media asset",
    "archive": "Archive package",
    "dataset": "Dataset",
    "backup": "Backup",
    "creative": "Creative work",
    "incomplete-download": "Incomplete download",
}


class _StrictModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )


class DiskSageMetadataEvidence(_StrictModel):
    field: str = Field(min_length=1, max_length=128)
    value: str = Field(min_length=1, max_length=2048)
    source: str = Field(min_length=1, max_length=256)
    confidence: Confidence


class DiskSageDatasetColumnProfile(_StrictModel):
    name: str = Field(min_length=1, max_length=256)
    inferred_type: str = Field(min_length=1, max_length=64)
    observed_values: int = Field(ge=0)
    missing_values: int = Field(ge=0)
    sensitive_name: bool


class DiskSageDatasetProfile(_StrictModel):
    format: str = Field(min_length=1, max_length=64)
    sampled_rows: int = Field(ge=0)
    sampled_worksheets: int = Field(ge=0)
    worksheet_names: list[str] = Field(default_factory=list, max_length=128)
    profile_complete: bool
    sample_truncated: bool
    columns: list[DiskSageDatasetColumnProfile] = Field(default_factory=list, max_length=512)
    quality_warnings: list[str] = Field(default_factory=list, max_length=128)

    @model_validator(mode="after")
    def bound_nested_strings(self) -> "DiskSageDatasetProfile":
        if any(not value or len(value) > 256 for value in self.worksheet_names):
            raise ValueError("worksheet_names entries must contain 1..256 characters")
        if any(not value or len(value) > 256 for value in self.quality_warnings):
            raise ValueError("quality_warnings entries must contain 1..256 characters")
        return self


def production_time_source_class(source: str) -> ProductionTimeSourceClass:
    if source.startswith("embedded:"):
        return "embedded_metadata"
    if source == "filename:path-token":
        return "explicit_filename_date"
    if source == "filesystem:created":
        return "filesystem_created"
    if source == "filesystem:modified-fallback":
        return "filesystem_modified"
    raise ValueError("unsupported production_time_source")


class DiskSageCatalogCandidate(_StrictModel):
    candidate_fingerprint: str = Field(pattern=_HEX_64_PATTERN)
    review_fingerprint: str = Field(pattern=_HEX_64_PATTERN)
    destination_provider: CloudProvider
    destination_account_scope: CloudAccountScope
    archive_kind: ArchiveKind
    bytes: int = Field(ge=0)
    created_ms: int = Field(ge=0, le=_MAX_DATETIME_EPOCH_MS)
    modified_ms: int = Field(gt=0, le=_MAX_DATETIME_EPOCH_MS)
    production_time_ms: int = Field(gt=0, le=_MAX_DATETIME_EPOCH_MS)
    production_time_source: str = Field(min_length=1, max_length=256)
    production_time_confidence: Confidence
    requires_review: bool
    review_reasons: list[str] = Field(default_factory=list, max_length=128)
    content_title: str | None = Field(default=None, min_length=1, max_length=1024)
    content_authors: list[str] = Field(default_factory=list, max_length=64)
    content_context: list[str] = Field(default_factory=list, max_length=128)
    duration_ms: int | None = Field(default=None, ge=0)
    dataset_profile: DiskSageDatasetProfile | None = None
    metadata_evidence: list[DiskSageMetadataEvidence] = Field(
        default_factory=list,
        max_length=256,
    )
    blocked_reason: str | None = Field(default=None, min_length=1, max_length=256)

    @model_validator(mode="after")
    def validate_metadata_lineage(self) -> "DiskSageCatalogCandidate":
        bounded_lists = (
            ("review_reasons", self.review_reasons, 256),
            ("content_authors", self.content_authors, 256),
            ("content_context", self.content_context, 1024),
        )
        for field_name, values, max_length in bounded_lists:
            if any(not value or len(value) > max_length for value in values):
                raise ValueError(
                    f"{field_name} entries must contain 1..{max_length} characters"
                )

        source_class = production_time_source_class(self.production_time_source)
        expected_field, evidence_source = {
            "embedded_metadata": ("production-date", self.production_time_source),
            "explicit_filename_date": ("filename-date-hint", "filename:path-token"),
            "filesystem_created": ("filesystem-created-date", "filesystem:created"),
            "filesystem_modified": (
                "filesystem-modified-date",
                "filesystem:modified",
            ),
        }[source_class]
        selected_date = (
            datetime(1970, 1, 1, tzinfo=timezone.utc)
            + timedelta(milliseconds=self.production_time_ms)
        ).date().isoformat()
        selected_evidence = [
            evidence
            for evidence in self.metadata_evidence
            if evidence.field == expected_field and evidence.source == evidence_source
        ]
        if not any(evidence.value == selected_date for evidence in selected_evidence):
            raise ValueError(
                "selected production time must bind to matching metadata evidence"
            )

        evidence_classes: set[ProductionTimeSourceClass] = set()
        for evidence in self.metadata_evidence:
            if evidence.field == "production-date" and evidence.source.startswith(
                "embedded:"
            ):
                evidence_classes.add("embedded_metadata")
            elif (
                evidence.field == "filename-date-hint"
                and evidence.source == "filename:path-token"
            ):
                evidence_classes.add("explicit_filename_date")
            elif (
                evidence.field == "filesystem-created-date"
                and evidence.source == "filesystem:created"
            ):
                evidence_classes.add("filesystem_created")
            elif (
                evidence.field == "filesystem-modified-date"
                and evidence.source == "filesystem:modified"
            ):
                evidence_classes.add("filesystem_modified")
        selected_rank = PRODUCTION_TIME_PRECEDENCE.index(source_class)
        if any(
            PRODUCTION_TIME_PRECEDENCE.index(evidence_class) < selected_rank
            for evidence_class in evidence_classes
        ):
            raise ValueError(
                "selected production time violates metadata precedence"
            )
        if source_class != "embedded_metadata" and self.production_time_confidence != "low":
            raise ValueError("non-embedded production time must remain low confidence")
        if self.requires_review != bool(self.review_reasons):
            raise ValueError("requires_review must match the presence of review_reasons")
        return self


class DiskSageCatalogCandidateBatch(_StrictModel):
    schema_id: Literal["disksage.file-catalog-candidate-batch"] = Field(alias="schema")
    version: Literal[1]
    production_time_precedence: tuple[
        Literal["embedded_metadata"],
        Literal["explicit_filename_date"],
        Literal["filesystem_created"],
        Literal["filesystem_modified"],
    ]
    generated_at_ms: int = Field(gt=0, le=_MAX_DATETIME_EPOCH_MS)
    candidates: list[DiskSageCatalogCandidate] = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def validate_batch(self) -> "DiskSageCatalogCandidateBatch":
        if self.production_time_precedence != PRODUCTION_TIME_PRECEDENCE:
            raise ValueError("production_time_precedence must use the fixed policy order")
        fingerprints = [item.candidate_fingerprint for item in self.candidates]
        if len(fingerprints) != len(set(fingerprints)):
            raise ValueError("candidate_fingerprint values must be unique within a batch")
        return self


class DiskSageOntologyMatch(_StrictModel):
    relation: Literal["hasArtifactType"] = "hasArtifactType"
    target_kind: Literal["artifact_type"] = "artifact_type"
    target_label: str
    confidence: Literal[1.0] = 1.0
    method: Literal["disksage-archive-kind-v1"] = "disksage-archive-kind-v1"
    review_status: Literal["proposed"] = "proposed"


class DiskSageCatalogProjection(_StrictModel):
    candidate_fingerprint: str = Field(pattern=_HEX_64_PATTERN)
    source_class: ProductionTimeSourceClass
    ontology_matches: list[DiskSageOntologyMatch]
    dataset_profile_present: bool
    persistable_as_file_asset: Literal[False] = False
    missing_file_asset_requirements: tuple[
        Literal["content_sha256"],
        Literal["verified_distribution"],
    ] = ("content_sha256", "verified_distribution")


class DiskSageCatalogPreviewResponse(_StrictModel):
    schema_id: Literal["disksage.file-catalog-preview"] = Field(alias="schema")
    version: Literal[1]
    preview_id: str = Field(pattern=r"^urn:sha256:[0-9a-f]{64}$")
    structural_validation: Literal["accepted"]
    candidate_count: int = Field(ge=1, le=200)
    total_bytes: int = Field(ge=0)
    requires_review_count: int = Field(ge=0)
    blocked_count: int = Field(ge=0)
    production_source_counts: dict[ProductionTimeSourceClass, int]
    projections: list[DiskSageCatalogProjection]
    persisted: Literal[False] = False
    llm_used: Literal[False] = False
    copy_authorized: Literal[False] = False
    eviction_authorized: Literal[False] = False
    persistable_as_file_asset: Literal[False] = False
    content_sha256_required: Literal[True] = True
    notices: tuple[str, ...]


def preview_id(batch: DiskSageCatalogCandidateBatch) -> str:
    """Bind the response to non-sensitive candidate/review identities only."""

    identity = {
        "schema": batch.schema_id,
        "version": batch.version,
        "precedence": batch.production_time_precedence,
        "generated_at_ms": batch.generated_at_ms,
        "candidates": [
            {
                "candidate_fingerprint": candidate.candidate_fingerprint,
                "review_fingerprint": candidate.review_fingerprint,
            }
            for candidate in batch.candidates
        ],
    }
    digest = hashlib.sha256(
        json.dumps(
            identity,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    return f"urn:sha256:{digest}"


def build_disksage_catalog_preview(
    batch: DiskSageCatalogCandidateBatch,
) -> DiskSageCatalogPreviewResponse:
    """Build a deterministic ontology preview without persistence or LLM calls."""

    projections: list[DiskSageCatalogProjection] = []
    source_counts: Counter[ProductionTimeSourceClass] = Counter()
    for candidate in batch.candidates:
        source_class = production_time_source_class(candidate.production_time_source)
        source_counts[source_class] += 1
        projections.append(
            DiskSageCatalogProjection(
                candidate_fingerprint=candidate.candidate_fingerprint,
                source_class=source_class,
                ontology_matches=[
                    DiskSageOntologyMatch(
                        target_label=_ARTIFACT_TYPE_LABELS[candidate.archive_kind]
                    )
                ],
                dataset_profile_present=candidate.dataset_profile is not None,
            )
        )

    return DiskSageCatalogPreviewResponse(
        schema="disksage.file-catalog-preview",
        version=1,
        preview_id=preview_id(batch),
        structural_validation="accepted",
        candidate_count=len(batch.candidates),
        total_bytes=sum(candidate.bytes for candidate in batch.candidates),
        requires_review_count=sum(candidate.requires_review for candidate in batch.candidates),
        blocked_count=sum(candidate.blocked_reason is not None for candidate in batch.candidates),
        production_source_counts={
            source: source_counts[source] for source in PRODUCTION_TIME_PRECEDENCE
        },
        projections=projections,
        notices=(
            "preview-only-no-persistence",
            "preview-does-not-authorize-copy-or-eviction",
            "content-sha256-and-verified-distribution-required-before-file-asset-ingest",
            "ontology-matches-remain-proposed-until-steward-review",
            "response-omits-content-metadata-and-storage-coordinates",
        ),
    )
