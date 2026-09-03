"""Tests for invariants that must hold outside the composition-root app."""

from __future__ import annotations

import asyncio
import json

import pytest
from fastapi import FastAPI

from openmetadata_test_support import table_payload
from sdp import openmetadata_routes
from sdp.openmetadata import (
    OpenMetadataCompatibilityProfile,
    OpenMetadataContractError,
)


def _invoke_chunked_json(
    app: FastAPI,
    payload: dict[str, object],
) -> list[dict[str, object]]:
    """Invoke an ASGI app without Content-Length to exercise receive limits."""

    encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    midpoint = max(1, len(encoded) // 2)
    incoming: list[dict[str, object]] = [
        {
            "type": "http.request",
            "body": encoded[:midpoint],
            "more_body": True,
        },
        {
            "type": "http.request",
            "body": encoded[midpoint:],
            "more_body": False,
        },
    ]
    outgoing: list[dict[str, object]] = []

    async def receive() -> dict[str, object]:
        if incoming:
            return incoming.pop(0)
        return {"type": "http.disconnect"}

    async def send(message: dict[str, object]) -> None:
        outgoing.append(message)

    scope: dict[str, object] = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "https",
        "path": "/integrations/openmetadata/v1/table-snapshots:normalize",
        "raw_path": b"/integrations/openmetadata/v1/table-snapshots:normalize",
        "query_string": b"",
        "headers": [(b"content-type", b"application/json")],
        "client": ("127.0.0.1", 50000),
        "server": ("testserver", 443),
        "root_path": "",
    }

    asyncio.run(app(scope, receive, send))
    return outgoing


def test_direct_router_embedding_enforces_chunked_body_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Including the router directly must not bypass request-size admission."""

    direct_app = FastAPI()
    direct_app.include_router(openmetadata_routes.router)
    monkeypatch.setattr(
        openmetadata_routes,
        "OPENMETADATA_REQUEST_BODY_MAX_BYTES",
        128,
        raising=False,
    )

    messages = _invoke_chunked_json(
        direct_app,
        {
            "tenant_id": "tenant_acme",
            "source_release": "2.0.1",
            "table": table_payload(),
        },
    )

    response_start = next(
        message
        for message in messages
        if message["type"] == "http.response.start"
    )
    assert response_start["status"] == 413
    response_body = b"".join(
        message.get("body", b"")
        for message in messages
        if message["type"] == "http.response.body"
    )
    assert json.loads(response_body) == {
        "detail": "OpenMetadata request body exceeds 128 bytes"
    }


def test_compatibility_profile_rejects_invalid_direct_construction() -> None:
    """The immutable profile validates itself, not only helper callers."""

    with pytest.raises(
        OpenMetadataContractError,
        match="profile canonical release must be 2.0.1",
    ):
        OpenMetadataCompatibilityProfile(
            profile_id="openmetadata-table-lineage-2.0.1",
            canonical_release="2.1.0",
            accepted_release_labels=frozenset(
                {"2.0.1", "2.0.1-release"}
            ),
            upstream_repository="open-metadata/OpenMetadata",
            upstream_tag="2.0.1-release",
            upstream_revision=(
                "bf621b166ec12e8c99fcb1c1443442723386fa41"
            ),
        )
