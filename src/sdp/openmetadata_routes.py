"""HTTP surface for the OpenMetadata anti-corruption layer."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.routing import APIRoute
from sdp_core import ActorContext
from starlette.responses import JSONResponse
from starlette.types import Message, Receive, Scope, Send

from .authz import verify_oidc_jwks_token
from .openmetadata import (
    OpenMetadataAdmissionPreviewRequest,
    OpenMetadataAdmissionReceipt,
    OpenMetadataContractError,
    OpenMetadataNormalizationRequest,
    OpenMetadataTableProjection,
    normalize_openmetadata_table_snapshot,
    preview_openmetadata_table_admission,
)
from .openmetadata.strict_json import (
    REQUEST_BODY_MAX_BYTES,
    validate_strict_json_bytes,
)

OPENMETADATA_REQUEST_BODY_MAX_BYTES = REQUEST_BODY_MAX_BYTES
_OPENMETADATA_ALLOWED_ROLES = frozenset(
    {"data-analyst", "admin", "platform-admin"}
)


class OpenMetadataBodyLimitRoute(APIRoute):
    """Enforce the request-body budget for every embedding of this router."""

    async def handle(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        """Buffer at most the bounded request body, then replay it to FastAPI."""

        buffered_messages: list[Message] = []
        received_bytes = 0
        while True:
            message = await receive()
            buffered_messages.append(message)
            if message["type"] != "http.request":
                break
            received_bytes += len(message.get("body", b""))
            if received_bytes > OPENMETADATA_REQUEST_BODY_MAX_BYTES:
                response = JSONResponse(
                    status_code=413,
                    content={
                        "detail": (
                            "OpenMetadata request body exceeds "
                            f"{OPENMETADATA_REQUEST_BODY_MAX_BYTES} bytes"
                        )
                    },
                )
                await response(scope, receive, send)
                return
            if not message.get("more_body", False):
                break

        buffered_iterator = iter(buffered_messages)

        async def replay_receive() -> Message:
            try:
                return next(buffered_iterator)
            except StopIteration:
                return await receive()

        await super().handle(scope, replay_receive, send)


router = APIRouter(
    prefix="/integrations/openmetadata/v1",
    tags=["OpenMetadata"],
    route_class=OpenMetadataBodyLimitRoute,
)


async def require_strict_json_request(request: Request) -> None:
    """Reject ambiguous transport JSON before an integration operation runs."""

    try:
        validate_strict_json_bytes(await request.body())
    except OpenMetadataContractError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def resolve_openmetadata_actor(
    authorization: Annotated[
        str | None,
        Header(alias="Authorization"),
    ] = None,
) -> ActorContext:
    """Verify a bearer token and require an integration-facing actor role."""

    scheme, separator, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not separator or not token:
        raise HTTPException(
            status_code=401,
            detail="Bearer authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        actor, _claims = verify_oidc_jwks_token(token)
    except ValueError as exc:
        raise HTTPException(
            status_code=401,
            detail="Bearer token is invalid",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    if not _OPENMETADATA_ALLOWED_ROLES.intersection(actor.roles):
        raise HTTPException(
            status_code=403,
            detail="OpenMetadata normalization permission required",
        )
    return actor


def _require_matching_tenant(
    actor: ActorContext,
    requested_tenant_id: str,
) -> None:
    """Hide cross-tenant integration resources from an authenticated caller."""

    if actor.tenant_id != requested_tenant_id:
        raise HTTPException(status_code=404, detail="resource not found")


@router.post(
    "/table-snapshots:normalize",
    response_model=OpenMetadataTableProjection,
    summary="Normalize an OpenMetadata 2.x table snapshot",
    dependencies=[Depends(require_strict_json_request)],
)
def normalize_table_snapshot(
    request: OpenMetadataNormalizationRequest,
    actor: Annotated[ActorContext, Depends(resolve_openmetadata_actor)],
) -> OpenMetadataTableProjection:
    """Return a safe projection only within the actor's verified tenant."""

    _require_matching_tenant(actor, request.tenant_id)
    try:
        return normalize_openmetadata_table_snapshot(
            tenant_id=actor.tenant_id,
            source_instance_id=request.source_instance_id,
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
    dependencies=[Depends(require_strict_json_request)],
)
def preview_table_snapshot_admission(
    request: OpenMetadataAdmissionPreviewRequest,
    actor: Annotated[ActorContext, Depends(resolve_openmetadata_actor)],
) -> OpenMetadataAdmissionReceipt:
    """Return tamper-evident review evidence within the verified tenant."""

    _require_matching_tenant(actor, request.tenant_id)
    try:
        return preview_openmetadata_table_admission(
            tenant_id=actor.tenant_id,
            source_instance_id=request.source_instance_id,
            source_release=request.source_release,
            observed_at=request.observed_at,
            table=request.table,
            lineage=request.lineage,
        )
    except OpenMetadataContractError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
