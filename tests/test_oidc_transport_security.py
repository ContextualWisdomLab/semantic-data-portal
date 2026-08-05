"""Regression tests for OIDC JWKS and outbound sink transport boundaries.

The OIDC verifier accepts a deployment-configured JWKS URL. These tests prove
that local-file and plaintext HTTP transports are rejected before any resource
is opened, malformed or credential-bearing HTTPS URLs are refused, and a
standards-compliant HTTPS endpoint keeps the existing configurable timeout.
They also preserve the intentionally separate HTTPS observability-export path
that is documented beside its rule-specific SAST annotation.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import sdp.authz as authz
import sdp.observability as observability


class _JsonResponse:
    """Minimal context-managed response used by successful transport tests."""

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


@pytest.mark.parametrize(
    ("jwks_url", "message"),
    [
        ("https:///jwks.json", "host"),
        ("https://operator:secret@identity.example.test/jwks.json", "credentials"),
        ("https://:secret@identity.example.test/jwks.json", "credentials"),
        ("https://identity.example.test/jwks.json#keys", "fragment"),
    ],
)
def test_jwks_loader_rejects_ambiguous_https_urls_before_opening(
    monkeypatch: pytest.MonkeyPatch,
    jwks_url: str,
    message: str,
) -> None:
    """Ambiguous authorities and client-side URL components fail closed."""

    def unexpected_open(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("urlopen must not receive an invalid JWKS URL")

    monkeypatch.setattr(authz, "urlopen", unexpected_open)

    with pytest.raises(ValueError, match=message):
        authz._load_jwks_from_url(jwks_url)


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


def test_observability_https_sink_posts_bodyless_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The reviewed HTTP(S) sink branch still emits only observation metadata."""

    captured: dict[str, Any] = {}

    def fake_open(request: Any, *, timeout: float) -> _JsonResponse:
        captured.update(
            url=request.full_url,
            method=request.get_method(),
            body=json.loads(request.data.decode("utf-8")),
            timeout=timeout,
        )
        return _JsonResponse({})

    monkeypatch.setenv("SDP_LOG_SINK_URL", "https://logs.example.test/ingest")
    monkeypatch.setenv("SDP_LOG_SINK_TIMEOUT_MS", "750")
    monkeypatch.setattr(observability, "urlopen", fake_open)

    observability._export_to_sink({"request_id": "buyer-trace-001", "status_code": 200})

    assert captured == {
        "url": "https://logs.example.test/ingest",
        "method": "POST",
        "body": {"request_id": "buyer-trace-001", "status_code": 200},
        "timeout": 0.75,
    }
