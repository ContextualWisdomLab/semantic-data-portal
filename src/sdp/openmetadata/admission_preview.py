"""Deterministic admission-preview receipts for OpenMetadata snapshots."""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from .admission_models import OpenMetadataAdmissionReceipt
from .errors import OpenMetadataContractError
from .structural_digest import DIGEST_PROFILE_ID, structural_sha256
from .validation import (
    _required_text,
    _validate_payload_budget,
    _validate_tenant_id,
)
from .verified_normalizer import normalize_openmetadata_table_snapshot

_SOURCE_INSTANCE_PATTERN = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$"
)
_RECEIPT_CONTRACT_VERSION = "1.0.0"


def _validate_source_instance_id(source_instance_id: object) -> str:
    """Validate the tenant-local identity of one OpenMetadata installation."""

    value = _required_text(
        source_instance_id,
        "source_instance_id",
        maximum=128,
    )
    if not _SOURCE_INSTANCE_PATTERN.fullmatch(value):
        raise OpenMetadataContractError(
            "source_instance_id contains unsupported characters"
        )
    return value


def _normalize_observed_at(observed_at: object) -> datetime:
    """Require an unambiguous observation instant and normalize it to UTC."""

    if not isinstance(observed_at, datetime):
        raise OpenMetadataContractError(
            "observed_at must be a datetime"
        )
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise OpenMetadataContractError(
            "observed_at must include a timezone"
        )
    return observed_at.astimezone(timezone.utc)


def preview_openmetadata_table_admission(
    *,
    tenant_id: str,
    source_instance_id: str,
    source_release: str,
    observed_at: datetime,
    table: Mapping[str, Any],
    lineage: Mapping[str, Any] | None = None,
) -> OpenMetadataAdmissionReceipt:
    """Create replay-safe evidence for a valid non-mutating table candidate.

    The source digest covers the submitted Table and optional EntityLineage
    values, including values intentionally omitted from the safe projection.
    The receipt never embeds that source object. The projection digest covers
    only the validated safe projection.
    """

    tenant = _validate_tenant_id(tenant_id)
    source_instance = _validate_source_instance_id(source_instance_id)
    observation_time = _normalize_observed_at(observed_at)
    _validate_payload_budget(table, lineage)

    source_snapshot = {
        "table": table,
        "lineage": lineage,
    }
    source_snapshot_digest = structural_sha256(
        source_snapshot,
        "source snapshot",
    )

    projection = normalize_openmetadata_table_snapshot(
        tenant_id=tenant,
        source_release=source_release,
        table=table,
        lineage=lineage,
    )
    projection_digest = structural_sha256(
        projection.model_dump(mode="json"),
        "projection",
    )

    replay_material = {
        "receipt_contract_version": _RECEIPT_CONTRACT_VERSION,
        "digest_profile_id": DIGEST_PROFILE_ID,
        "tenant_id": tenant,
        "source_instance_id": source_instance,
        "source_authority": projection.source_authority,
        "compatibility_profile_id": projection.compatibility_profile_id,
        "external_entity_id": projection.external_entity_id,
        "source_snapshot_digest": source_snapshot_digest,
        "projection_digest": projection_digest,
    }
    replay_key = structural_sha256(
        replay_material,
        "replay material",
    )
    receipt_suffix = replay_key.removeprefix("sha256:")

    return OpenMetadataAdmissionReceipt(
        digest_profile_id=DIGEST_PROFILE_ID,
        receipt_id=(
            f"urn:cwl:{tenant}:sdp:openmetadata_admission_preview:"
            f"{receipt_suffix}"
        ),
        tenant_id=tenant,
        source_instance_id=source_instance,
        source_release=projection.source_release,
        compatibility_profile_id=projection.compatibility_profile_id,
        upstream_repository=projection.upstream_repository,
        upstream_revision=projection.upstream_revision,
        observed_at=observation_time,
        external_entity_id=projection.external_entity_id,
        source_snapshot_digest=source_snapshot_digest,
        projection_digest=projection_digest,
        replay_key=replay_key,
        omitted_fields=list(projection.omitted_fields),
        projection=projection,
    )
