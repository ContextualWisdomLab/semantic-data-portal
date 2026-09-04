"""Deterministic, non-mutating OpenMetadata admission preview service."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from .admission_identity import (
    build_admission_candidate_id,
    build_admission_receipt_id,
    build_admission_replay_key,
    normalize_observed_at,
)
from .admission_models import OpenMetadataAdmissionReceipt
from .source_identity import validate_openmetadata_source_instance_id
from .structural_digest import structural_sha256
from .verified_normalizer import normalize_openmetadata_table_snapshot


def preview_openmetadata_table_admission(
    *,
    tenant_id: str,
    source_instance_id: str,
    source_release: str,
    observed_at: datetime,
    table: Mapping[str, Any],
    lineage: Mapping[str, Any] | None = None,
) -> OpenMetadataAdmissionReceipt:
    """Return digest-bound review evidence without persisting source content."""

    source_instance = validate_openmetadata_source_instance_id(
        source_instance_id
    )
    observation_time = normalize_observed_at(observed_at)
    projection = normalize_openmetadata_table_snapshot(
        tenant_id=tenant_id,
        source_instance_id=source_instance,
        source_release=source_release,
        table=table,
        lineage=lineage,
    )
    source_snapshot_digest = structural_sha256(
        {
            "table": table,
            "lineage": lineage,
        },
        "source snapshot",
    )
    detached_projection = projection.model_copy(deep=True)
    projection_digest = structural_sha256(
        detached_projection.model_dump(mode="json"),
        "projection",
    )
    replay_key = build_admission_replay_key(
        tenant_id=tenant_id,
        source_instance_id=source_instance,
        source_authority=detached_projection.source_authority,
        source_release=detached_projection.source_release,
        compatibility_profile_id=(
            detached_projection.compatibility_profile_id
        ),
        upstream_repository=detached_projection.upstream_repository,
        upstream_revision=detached_projection.upstream_revision,
        external_entity_id=detached_projection.external_entity_id,
        source_snapshot_digest=source_snapshot_digest,
        projection_digest=projection_digest,
    )
    admission_candidate_id = build_admission_candidate_id(
        tenant_id=tenant_id,
        replay_key=replay_key,
    )
    receipt_id = build_admission_receipt_id(
        tenant_id=tenant_id,
        admission_candidate_id=admission_candidate_id,
        observed_at=observation_time,
    )
    return OpenMetadataAdmissionReceipt(
        admission_candidate_id=admission_candidate_id,
        receipt_id=receipt_id,
        tenant_id=tenant_id,
        source_instance_id=source_instance,
        source_release=detached_projection.source_release,
        compatibility_profile_id=(
            detached_projection.compatibility_profile_id
        ),
        upstream_repository=detached_projection.upstream_repository,
        upstream_revision=detached_projection.upstream_revision,
        observed_at=observation_time,
        external_entity_id=detached_projection.external_entity_id,
        source_snapshot_digest=source_snapshot_digest,
        projection_digest=projection_digest,
        replay_key=replay_key,
        omitted_fields=list(detached_projection.omitted_fields),
        projection=detached_projection,
    )
