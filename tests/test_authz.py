"""Tests for OIDC JWKS loading, focused on the URL-scheme hardening."""

from __future__ import annotations

import json

import pytest

from sdp import authz


def test_load_jwks_from_url_rejects_non_http_schemes():
    """A misconfigured non-http(s) JWKS URL must be rejected before any fetch,
    so urllib's ``file://`` support cannot be turned into local file disclosure."""
    for bad_url in ("file:///etc/passwd", "ftp://host/keys.json", "gopher://x", ""):
        with pytest.raises(ValueError):
            authz._load_jwks_from_url(bad_url)


def test_load_jwks_from_url_fetches_over_https(monkeypatch):
    """An https JWKS URL passes the scheme allow-list and its JSON body is
    parsed and returned."""
    payload = {"keys": [{"kid": "abc", "kty": "RSA"}]}

    class _FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return json.dumps(payload).encode("utf-8")

    captured = {}

    def _fake_urlopen(url, timeout=None):
        captured["url"] = url
        captured["timeout"] = timeout
        return _FakeResponse()

    monkeypatch.setattr(authz, "urlopen", _fake_urlopen)
    result = authz._load_jwks_from_url("https://idp.example/.well-known/jwks.json")

    assert result == payload
    assert captured["url"] == "https://idp.example/.well-known/jwks.json"
    assert captured["timeout"] == pytest.approx(2.0)


def test_load_jwks_from_url_honours_timeout_override(monkeypatch):
    """The JWKS fetch timeout is configurable via SDP_OIDC_JWKS_TIMEOUT_SECONDS."""
    monkeypatch.setenv("SDP_OIDC_JWKS_TIMEOUT_SECONDS", "5")

    class _FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return b"{}"

    seen = {}

    def _fake_urlopen(url, timeout=None):
        seen["timeout"] = timeout
        return _FakeResponse()

    monkeypatch.setattr(authz, "urlopen", _fake_urlopen)
    assert authz._load_jwks_from_url("http://localhost:8080/jwks") == {}
    assert seen["timeout"] == pytest.approx(5.0)
