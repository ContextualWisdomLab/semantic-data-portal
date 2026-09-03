"""Verified public normalization entry point for OpenMetadata payloads."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .compatibility import resolve_openmetadata_release_profile
from .models import OpenMetadataTableProjection
from .normalizer import (
    normalize_openmetadata_table_snapshot as _normalize_table_snapshot,
)


def normalize_openmetadata_table_snapshot(
    *,
    tenant_id: str,
    source_release: str,
    table: Mapping[str, Any],
    lineage: Mapping[str, Any] | None = None,
) -> OpenMetadataTableProjection:
    """Normalize only payloads covered by an exact verified release profile."""

    profile = resolve_openmetadata_release_profile(source_release)
    projection = _normalize_table_snapshot(
        tenant_id=tenant_id,
        source_release=profile.canonical_release,
        table=table,
        lineage=lineage,
    )
    return projection.model_copy(
        update={
            "source_release": profile.canonical_release,
            "compatibility_profile_id": profile.profile_id,
            "upstream_repository": profile.upstream_repository,
            "upstream_revision": profile.upstream_revision,
        }
    )
