"""Regression tests for OIDC JWKS transport security boundaries.

The OIDC verifier accepts a deployment-configured JWKS URL. These tests prove
that local-file and plaintext HTTP transports are rejected before any resource
is opened, while a standards-compliant HTTPS endpoint keeps the existing
configurable timeout behavior.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import sdp.authz as authz


class _JsonResponse:
    """Minimal context-managed response used by the HTTPS control test."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = json.dumps(payload).encode("utf-8")

    def __enter__(self) -> _JsonResponse:
        return self

    def __exit__(self, *_exc: object) -> bool:
        return False

    def read(self) -> bytes:
        """Return the encoded JSON response body."""

        return self._payload


def test_jwks_loader_rejects_local_file_url(tmp_path: Path) -> None:
    """A deployment value must not turn the verifier into a local-file reader."""

    local_jwks = tmp_path / "jwks.json"
    local_jwks.write_text('{"keys": []}', encoding="utf-8")

    with pytest.raises(ValueError, match="HTTPS"):
        authz._load_jwks_from_url(local_jwks.as_uri())


def test_jwks_loader_rejects_plain_http_before_opening(monkeypatch: pytest.MonkeyPatch) -> None:
    """Plain HTTP must be rejected without attempting an outbound connection."""

    def unexpected_open(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("urlopen must not be called for a plaintext JWKS URL")

    monkeypatch.setattr(authz, "urlopen", unexpected_open)

    with pytest.raises(ValueError, match="HTTPS"):
        authz._load_jwks_from_url("http://identity.example.test/.well-known/jwks.json")


def test_jwks_loader_reads_https_with_configured_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """The secure transport path preserves the operator-configured timeout."""

    captured: dict[str, Any] = {}

    def fake_open(url: str, *, timeout: float) -> _JsonResponse:
        captured.update(url=url, timeout=timeout)
        return _JsonResponse({"keys": []})

    monkeypatch.setenv("SDP_OIDC_JWKS_TIMEOUT_SECONDS", "1.25")
    monkeypatch.setattr(authz, "urlopen", fake_open)

    result = authz._load_jwks_from_url("https://identity.example.test/.well-known/jwks.json")

    assert result == {"keys": []}
    assert captured == {
        "url": "https://identity.example.test/.well-known/jwks.json",
        "timeout": 1.25,
    }
