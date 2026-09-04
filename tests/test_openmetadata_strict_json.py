"""Strict transport-JSON tests for the OpenMetadata integration boundary."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sdp_core import ActorContext

import sdp.openmetadata.strict_json as strict_json
from sdp import openmetadata_routes
from sdp.openmetadata import OpenMetadataContractError


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (b'{"value":1,"value":2}', "duplicate JSON object key"),
        (b'{"value":NaN}', "non-standard JSON number"),
        (b'{"value":Infinity}', "non-standard JSON number"),
        (b'{"value":"\\ud800"}', "valid Unicode scalar"),
        (b"\xff", "request body must be UTF-8 JSON"),
        (b'{"value":', "request body must be strict JSON"),
    ],
)
def test_strict_json_validator_rejects_ambiguous_payloads(
    payload: bytes,
    message: str,
) -> None:
    """Ambiguous or non-standard transport bytes fail with stable errors."""

    with pytest.raises(OpenMetadataContractError, match=message):
        strict_json.validate_strict_json_bytes(payload)


def test_strict_json_validator_returns_standard_json_value() -> None:
    """A standard UTF-8 document is returned without type coercion."""

    value = strict_json.validate_strict_json_bytes(
        b'{"array":[null,true,false,1,1.5,"text","\\ud83d\\ude00"]}'
    )

    assert value == {
        "array": [None, True, False, 1, 1.5, "text", "😀"],
    }


def test_strict_json_validator_bounds_transport_size_and_depth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Whitespace floods and decoder recursion cannot bypass payload controls."""

    monkeypatch.setattr(strict_json, "REQUEST_BODY_MAX_BYTES", 4)
    with pytest.raises(
        OpenMetadataContractError,
        match="request body exceeds 4 bytes",
    ):
        strict_json.validate_strict_json_bytes(b'{"a":1}')

    monkeypatch.setattr(strict_json, "REQUEST_BODY_MAX_BYTES", 1_000_000)
    deeply_nested = b"[" * 1_100 + b"0" + b"]" * 1_100
    with pytest.raises(
        OpenMetadataContractError,
        match="request body must be strict JSON",
    ):
        strict_json.validate_strict_json_bytes(deeply_nested)


def _verified_actor(_token: str) -> tuple[ActorContext, dict[str, object]]:
    """Return one integration-facing actor for transport-boundary tests."""

    return (
        ActorContext(
            subject="user_001",
            tenant_id="tenant_acme",
            roles=["data-analyst"],
        ),
        {"sub": "user_001", "tenant_id": "tenant_acme"},
    )


@pytest.mark.parametrize(
    "endpoint",
    [
        "/integrations/openmetadata/v1/table-snapshots:normalize",
        "/integrations/openmetadata/v1/table-snapshots:admission-preview",
    ],
)
def test_openmetadata_routes_reject_duplicate_nested_members(
    endpoint: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No OpenMetadata route may normalize a last-key-wins request."""

    monkeypatch.setattr(
        openmetadata_routes,
        "verify_oidc_jwks_token",
        _verified_actor,
    )
    common = (
        '"tenant_id":"tenant_acme",'
        '"source_instance_id":"metadata_primary",'
        '"source_release":"2.0.1",'
    )
    admission = (
        '"observed_at":"2026-09-04T00:00:00Z",'
        if endpoint.endswith("admission-preview")
        else ""
    )
    table = (
        '"table":{'
        '"id":"11111111-1111-4111-8111-111111111111",'
        '"name":"orders",'
        '"name":"shadow_orders",'
        '"columns":[]}'
    )
    body = "{" + common + admission + table + "}"

    app = FastAPI()
    app.include_router(openmetadata_routes.router)
    response = TestClient(app).post(
        endpoint,
        content=body.encode("utf-8"),
        headers={
            "content-type": "application/json",
            "Authorization": "Bearer valid",
        },
    )

    assert response.status_code == 400
    assert response.json() == {
        "detail": "request body contains duplicate JSON object key"
    }
