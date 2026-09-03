"""HTTP surface for the OpenMetadata anti-corruption layer."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .openmetadata import (
    OpenMetadataAdmissionPreviewRequest,
    OpenMetadataAdmissionReceipt,
    OpenMetadataContractError,
    OpenMetadataNormalizationRequest,
    OpenMetadataTableProjection,
    normalize_openmetadata_table_snapshot,
    preview_openmetadata_table_admission,
)

router = APIRouter(
    prefix="/integrations/openmetadata/v1",
    tags=["OpenMetadata"],
)


@router.post(
    "/table-snapshots:normalize",
    response_model=OpenMetadataTableProjection,
    summary="Normalize a verified OpenMetadata table snapshot",
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


@router.post(
    "/table-snapshots:admission-preview",
    response_model=OpenMetadataAdmissionReceipt,
    summary="Preview deterministic OpenMetadata admission evidence",
)
def preview_table_snapshot_admission(
    request: OpenMetadataAdmissionPreviewRequest,
) -> OpenMetadataAdmissionReceipt:
    """Return replay-safe receipt evidence without persisting or publishing."""

    try:
        return preview_openmetadata_table_admission(
            tenant_id=request.tenant_id,
            source_instance_id=request.source_instance_id,
            source_release=request.source_release,
            observed_at=request.observed_at,
            table=request.table,
            lineage=request.lineage,
        )
    except OpenMetadataContractError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
