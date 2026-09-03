"""HTTP surface for the OpenMetadata anti-corruption layer."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .openmetadata import (
    OpenMetadataContractError,
    OpenMetadataNormalizationRequest,
    OpenMetadataTableProjection,
    normalize_openmetadata_table_snapshot,
)

router = APIRouter(prefix="/integrations/openmetadata/v1", tags=["OpenMetadata"])


@router.post(
    "/table-snapshots:normalize",
    response_model=OpenMetadataTableProjection,
    summary="Normalize an OpenMetadata 2.x table snapshot",
)
def normalize_table_snapshot(
    request: OpenMetadataNormalizationRequest,
) -> OpenMetadataTableProjection:
    """Return a safe, read-only projection of an OpenMetadata table snapshot."""

    try:
        return normalize_openmetadata_table_snapshot(
            tenant_id=request.tenant_id,
            source_release=request.source_release,
            table=request.table,
            lineage=request.lineage,
        )
    except OpenMetadataContractError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
