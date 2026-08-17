"""Validation and graph ingestion for DiskSage semantic catalog batches.

DiskSage deliberately exports a path-free, metadata-first preview contract.  This
adapter keeps that boundary intact: it accepts only the versioned contract,
rejects unknown/path-bearing fields, and stores candidates as governed graph
nodes rather than touching a filesystem or a cloud provider.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .graph_store import GraphStore


MAX_EPOCH_MS = 253_402_300_799_999
MAX_BODY_BYTES = 2 * 1024 * 1024
MAX_CANDIDATES = 200
PRODUCTION_TIME_PRECEDENCE = (
    "embedded_metadata",
    "explicit_filename_date",
    "filesystem_created",
    "filesystem_modified",
)

Provider = Literal["icloud", "onedrive", "google-drive"]
AccountScope = Literal["personal", "organization", "shared", "unknown"]
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
# Reject absolute local-path tokens without a delimiter allowlist.  http(s)
# URLs are stripped first so ``https://example.com/path`` is not treated as
# ``/path``.  ``file:`` URIs are rejected before that strip.
_URL_RE = re.compile(
    r"[a-zA-Z][a-zA-Z0-9+.-]*://[^/\s]+(?:/[A-Za-z0-9._~%+-]*)*",
    re.IGNORECASE,
)
_FILE_URI_RE = re.compile(r"file:(?://)?", re.IGNORECASE)
_ABSOLUTE_POSIX_RE = re.compile(r"(?<![A-Za-z0-9])/[^/\s]")
_HOME_OR_WINDOWS_RE = re.compile(r"(?:~/|[A-Za-z]:[\\/]|\\\\)")


def _contains_local_path(value: object) -> bool:
    """Return True when *value* embeds a local path, file URI, or NUL byte.

    Absolute POSIX tokens (`/etc`, `/tmp`, `/var`, `/Users`, and so on) are
    rejected after any non-alphanumeric boundary, including `;` and `|`.
    Nested dicts and sequences are scanned so leaked paths cannot hide in
    metadata evidence or context lists.
    """

    if isinstance(value, str):
        if "\x00" in value or _FILE_URI_RE.search(value) is not None:
            return True
        stripped = _URL_RE.sub(" ", value)
        return (
            _ABSOLUTE_POSIX_RE.search(stripped) is not None
            or _HOME_OR_WINDOWS_RE.search(stripped) is not None
        )
    if isinstance(value, dict):
        return any(_contains_local_path(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_local_path(item) for item in value)
    return False


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class MetadataEvidence(_StrictModel):
    field: Annotated[str, Field(min_length=1, max_length=128)]
    value: Annotated[str, Field(min_length=1, max_length=2048)]
    source: Annotated[str, Field(min_length=1, max_length=256)]
    confidence: Confidence


class DatasetColumnProfile(_StrictModel):
    name: Annotated[str, Field(min_length=1, max_length=256)]
    inferred_type: Annotated[str, Field(min_length=1, max_length=64)]
    observed_values: int = Field(ge=0)
    missing_values: int = Field(ge=0)
    sensitive_name: bool


class DatasetProfile(_StrictModel):
    format: Annotated[str, Field(min_length=1, max_length=64)]
    sampled_rows: int = Field(ge=0)
    sampled_worksheets: int = Field(ge=0)
    worksheet_names: list[Annotated[str, Field(min_length=1, max_length=256)]] = Field(
        default_factory=list, max_length=128
    )
    profile_complete: bool
    sample_truncated: bool
    columns: list[DatasetColumnProfile] = Field(default_factory=list, max_length=512)
    quality_warnings: list[Annotated[str, Field(min_length=1, max_length=256)]] = Field(
        default_factory=list, max_length=128
    )


class Candidate(_StrictModel):
    candidate_fingerprint: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    review_fingerprint: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    destination_provider: Provider
    destination_account_scope: AccountScope
    archive_kind: ArchiveKind
    bytes: int = Field(ge=0)
    created_ms: int = Field(ge=0, le=MAX_EPOCH_MS)
    modified_ms: int = Field(gt=0, le=MAX_EPOCH_MS)
    production_time_ms: int = Field(gt=0, le=MAX_EPOCH_MS)
    production_time_source: Annotated[str, Field(min_length=1, max_length=256)]
    production_time_confidence: Confidence
    requires_review: bool
    review_reasons: list[Annotated[str, Field(min_length=1, max_length=256)]] = Field(
        default_factory=list, max_length=128
    )
    content_title: str | None = Field(default=None, max_length=1024)
    content_authors: list[Annotated[str, Field(min_length=1, max_length=256)]] = Field(
        default_factory=list, max_length=64
    )
    content_context: list[Annotated[str, Field(min_length=1, max_length=1024)]] = Field(
        default_factory=list, max_length=128
    )
    duration_ms: int | None = Field(default=None, ge=0)
    dataset_profile: DatasetProfile | None = None
    metadata_evidence: list[MetadataEvidence] = Field(
        default_factory=list, max_length=256
    )
    blocked_reason: str | None = Field(default=None, max_length=256)

    @model_validator(mode="after")
    def validate_lineage_evidence(self) -> "Candidate":
        if _contains_local_path(self.model_dump(mode="json")):
            raise ValueError("path-bearing metadata is not allowed")
        if self.requires_review != bool(self.review_reasons):
            raise ValueError("requires_review must match review_reasons")

        source_class = _production_source_class(self.production_time_source)
        if (
            source_class != "embedded_metadata"
            and self.production_time_confidence != "low"
        ):
            raise ValueError("non-embedded production time must have low confidence")

        selected_date = (
            datetime.fromtimestamp(self.production_time_ms / 1000, tz=timezone.utc)
            .date()
            .isoformat()
        )
        expected_field, expected_source = {
            "embedded_metadata": ("production-date", self.production_time_source),
            "explicit_filename_date": ("filename-date-hint", "filename:path-token"),
            "filesystem_created": ("filesystem-created-date", "filesystem:created"),
            "filesystem_modified": ("filesystem-modified-date", "filesystem:modified"),
        }[source_class]
        if not any(
            evidence.field == expected_field
            and evidence.source == expected_source
            and evidence.value == selected_date
            for evidence in self.metadata_evidence
        ):
            raise ValueError("selected production-time evidence is missing")

        selected_rank = PRODUCTION_TIME_PRECEDENCE.index(source_class)
        for evidence in self.metadata_evidence:
            evidence_class = _evidence_source_class(evidence)
            if (
                evidence_class is not None
                and PRODUCTION_TIME_PRECEDENCE.index(evidence_class) < selected_rank
            ):
                raise ValueError("production-time precedence violation")
        return self


class CandidateBatch(_StrictModel):
    schema_kind: Literal["disksage.file-catalog-candidate-batch"] = Field(
        alias="schema"
    )
    version: Literal[1]
    production_time_precedence: list[str] = Field(min_length=4, max_length=4)
    generated_at_ms: int = Field(gt=0, le=MAX_EPOCH_MS)
    candidates: list[Candidate] = Field(min_length=1, max_length=MAX_CANDIDATES)

    @model_validator(mode="after")
    def validate_batch(self) -> "CandidateBatch":
        if tuple(self.production_time_precedence) != PRODUCTION_TIME_PRECEDENCE:
            raise ValueError("unsupported production_time_precedence")
        fingerprints = [
            candidate.candidate_fingerprint for candidate in self.candidates
        ]
        if len(fingerprints) != len(set(fingerprints)):
            raise ValueError("candidate_fingerprint must be unique")
        encoded = json.dumps(
            self.model_dump(mode="json", by_alias=True),
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        if len(encoded) > MAX_BODY_BYTES:
            raise ValueError("DiskSage catalog batch exceeds body limit")
        return self


class DiskSageCatalogRequest(_StrictModel):
    actor: Annotated[str, Field(min_length=1, max_length=256)]
    catalog: CandidateBatch


def _production_source_class(source: str) -> str:
    if source.startswith("embedded:"):
        return "embedded_metadata"
    mapping = {
        "filename:path-token": "explicit_filename_date",
        "filesystem:created": "filesystem_created",
        "filesystem:modified-fallback": "filesystem_modified",
    }
    try:
        return mapping[source]
    except KeyError as exc:
        raise ValueError("unsupported production_time_source") from exc


def _evidence_source_class(evidence: MetadataEvidence) -> str | None:
    if evidence.field == "production-date" and evidence.source.startswith("embedded:"):
        return "embedded_metadata"
    mapping = {
        ("filename-date-hint", "filename:path-token"): "explicit_filename_date",
        ("filesystem-created-date", "filesystem:created"): "filesystem_created",
        ("filesystem-modified-date", "filesystem:modified"): "filesystem_modified",
    }
    return mapping.get((evidence.field, evidence.source))


def _canonical_batch_fingerprint(batch: CandidateBatch) -> str:
    encoded = json.dumps(
        batch.model_dump(mode="json", by_alias=True),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _candidate_properties(
    batch: CandidateBatch, candidate: Candidate
) -> dict[str, object]:
    properties = candidate.model_dump(mode="json")
    properties.update(
        {
            "source_system": "disksage",
            "catalog_schema": batch.schema_kind,
            "catalog_version": batch.version,
            "catalog_generated_at_ms": batch.generated_at_ms,
            "production_time_precedence": list(batch.production_time_precedence),
        }
    )
    return properties


def ingest_catalog_batch(store: GraphStore, batch: CandidateBatch) -> dict[str, object]:
    """Upsert a validated, path-free batch into the active graph store."""

    batch_fingerprint = _canonical_batch_fingerprint(batch)
    batch_id = f"disksage:batch:{batch_fingerprint}"
    store.upsert_node(
        batch_id,
        "catalog_batch",
        label=f"DiskSage catalog {batch.generated_at_ms}",
        properties={
            "source_system": "disksage",
            "catalog_schema": batch.schema_kind,
            "catalog_version": batch.version,
            "generated_at_ms": batch.generated_at_ms,
            "candidate_count": len(batch.candidates),
            "batch_fingerprint": batch_fingerprint,
            "production_time_precedence": list(batch.production_time_precedence),
        },
        text="DiskSage file catalog candidate batch",
    )

    candidate_ids: list[str] = []
    for candidate in batch.candidates:
        candidate_id = f"disksage:candidate:{candidate.candidate_fingerprint}"
        candidate_ids.append(candidate_id)
        store.upsert_node(
            candidate_id,
            "file_candidate",
            label=candidate.content_title or f"{candidate.archive_kind} candidate",
            properties=_candidate_properties(batch, candidate),
            text=" ".join(
                filter(
                    None,
                    [
                        candidate.content_title,
                        candidate.archive_kind,
                        *candidate.content_authors,
                        *candidate.content_context,
                        *candidate.review_reasons,
                    ],
                )
            ),
        )
        store.upsert_edge(
            "cataloged_in",
            candidate_id,
            batch_id,
            properties={
                "source_system": "disksage",
                "batch_fingerprint": batch_fingerprint,
            },
        )

    return {
        "status": "upserted",
        "batch_id": batch_id,
        "batch_fingerprint": batch_fingerprint,
        "candidate_count": len(candidate_ids),
        "candidate_ids": candidate_ids,
    }
