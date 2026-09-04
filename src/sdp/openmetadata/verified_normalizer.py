"""Verified public normalization entry point for OpenMetadata payloads."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .models import OpenMetadataTableProjection
from .normalizer import (
    normalize_openmetadata_table_snapshot as _normalize_table_snapshot,
)


def normalize_openmetadata_table_snapshot(
    *,
    tenant_id: str,
    source_instance_id: str,
    source_release: str,
    table: Mapping[str, Any],
    lineage: Mapping[str, Any] | None = None,
) -> OpenMetadataTableProjection:
    """Delegate to the verified normalization sink without a weaker bypass."""

    return _normalize_table_snapshot(
        tenant_id=tenant_id,
        source_instance_id=source_instance_id,
        source_release=source_release,
        table=table,
        lineage=lineage,
    )
