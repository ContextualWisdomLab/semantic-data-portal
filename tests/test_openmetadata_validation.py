"""Primitive and HTTP-boundary tests for OpenMetadata validation."""

from __future__ import annotations

from typing import Callable

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from sdp.openmetadata import OpenMetadataContractError
from sdp.openmetadata import validation
from sdp.openmetadata_routes import router

from openmetadata_test_support import table_payload


def _assert_contract(
    message: str,
    function: Callable[..., object],
    *args: object,
    **kwargs: object,
) -> None:
    """Assert a direct validator call fails with the bounded error type."""

    with pytest.raises(OpenMetadataContractError, match=message):
        function(*args, **kwargs)


def test_mapping_and_array_guards() -> None:
    """Foreign container types and excessive arrays fail closed."""

    _assert_contract(
        "must be an object",
        validation._require_mapping,
        [],
        "value",
    )
    assert validation._require_mapping({"x": 1}, "value") == {"x": 1}
    assert validation._optional_mapping(None, "value") is None
    _assert_contract(
        "must be an array",
        validation._require_list,
        {},
        "value",
        maximum=1,
    )
    _assert_contract(
        "exceeds 1 items",
        validation._require_list,
        [1, 2],
        "value",
        maximum=1,
    )
    assert validation._optional_list(None, "value", maximum=1) == []


def test_text_uuid_and_url_guards() -> None:
    """Text and references are bounded without scalar coercion."""

    _assert_contract(
        "is required",
        validation._text,
        None,
        "value",
        required=True,
    )
    _assert_contract(
        "must be a string",
        validation._text,
        1,
        "value",
    )
    _assert_contract(
        "is required",
        validation._text,
        "",
        "value",
        required=True,
    )
    _assert_contract(
        "exceeds 1 characters",
        validation._text,
        "xx",
        "value",
        maximum=1,
    )
    _assert_contract(
        "control characters",
        validation._text,
        "x\x00",
        "value",
    )
    assert validation._text("x\n", "value") == "x\n"
    assert validation._required_text("x", "value", maximum=1) == "x"

    assert (
        validation._uuid_text(
            "11111111-1111-4111-8111-111111111111",
            "entity.id",
        )
        == "11111111-1111-4111-8111-111111111111"
    )
    _assert_contract(
        "must be a UUID",
        validation._uuid_text,
        "not-a-uuid",
        "entity.id",
    )

    assert validation._safe_url(None, "url") is None
    _assert_contract(
        r"HTTP\(S\)",
        validation._safe_url,
        "file:///tmp/x",
        "url",
    )
    _assert_contract(
        r"HTTP\(S\)",
        validation._safe_url,
        "https://[",
        "url",
    )
    _assert_contract(
        "must not contain credentials",
        validation._safe_url,
        "https://user:pass@example.com/x",
        "url",
    )
    assert (
        validation._safe_url("http://example.com/x", "url")
        == "http://example.com/x"
    )


def test_number_time_release_and_tenant_guards() -> None:
    """Counts, time, release syntax, and tenant IDs keep strict types."""

    assert validation._optional_non_negative_int(None, "count") is None
    assert validation._optional_non_negative_int(0, "count") == 0
    for value in (True, -1, 1.2, "1"):
        _assert_contract(
            "non-negative integer",
            validation._optional_non_negative_int,
            value,
            "count",
        )

    assert validation._epoch_milliseconds(None, "when") is None
    assert validation._epoch_milliseconds(0, "when") is not None
    _assert_contract(
        "outside the supported",
        validation._epoch_milliseconds,
        10**30,
        "when",
    )

    assert validation._validate_source_release("2.0-release") == "2.0-release"
    assert validation._validate_source_release("2.1.0") == "2.1.0"
    _assert_contract(
        "OpenMetadata 2.x",
        validation._validate_source_release,
        "3.0.0",
    )
    assert validation._validate_tenant_id("tenant-1") == "tenant-1"
    _assert_contract(
        "unsupported characters",
        validation._validate_tenant_id,
        "tenant:1",
    )
    assert validation._stable_unique(["a", "a", "b"]) == ["a", "b"]


def test_payload_budget_guards(monkeypatch: pytest.MonkeyPatch) -> None:
    """Deep, cyclic, text-heavy, and container-heavy payloads are bounded."""

    too_deep = current = []
    for _ in range(65):
        child: list[object] = []
        current.append(child)
        current = child
    _assert_contract(
        "nesting exceeds 64",
        validation._validate_payload_budget,
        too_deep,
    )

    monkeypatch.setattr(validation, "_MAX_PAYLOAD_TEXT_BYTES", 1)
    _assert_contract(
        "payload text exceeds 1 bytes",
        validation._validate_payload_budget,
        {"a": "xx"},
    )

    list_cycle: list[object] = []
    list_cycle.append(list_cycle)
    _assert_contract(
        "cyclic container",
        validation._validate_payload_budget,
        list_cycle,
    )

    mapping_cycle: dict[str, object] = {}
    mapping_cycle["self"] = mapping_cycle
    _assert_contract(
        "cyclic container",
        validation._validate_payload_budget,
        mapping_cycle,
    )

    monkeypatch.setattr(validation, "_MAX_PAYLOAD_CONTAINERS", 1)
    _assert_contract(
        "exceeds 1 containers",
        validation._validate_payload_budget,
        {"a": {}},
    )
    _assert_contract(
        "exceeds 1 containers",
        validation._validate_payload_budget,
        [[]],
    )


def test_http_contract_rejects_expansion_and_malformed_url() -> None:
    """Request-shape and parser errors remain bounded at the HTTP surface."""

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    extra = {
        "tenant_id": "tenant_acme",
        "source_release": "2.0.1",
        "table": table_payload(),
        "unexpected": True,
    }
    assert (
        client.post(
            "/integrations/openmetadata/v1/table-snapshots:normalize",
            json=extra,
        ).status_code
        == 422
    )

    malformed = table_payload()
    malformed["sourceUrl"] = "https://["
    response = client.post(
        "/integrations/openmetadata/v1/table-snapshots:normalize",
        json={
            "tenant_id": "tenant_acme",
            "source_release": "2.0.1",
            "table": malformed,
        },
    )
    assert response.status_code == 400
    assert response.json() == {
        "detail": "table.sourceUrl must be an HTTP(S) URL"
    }
