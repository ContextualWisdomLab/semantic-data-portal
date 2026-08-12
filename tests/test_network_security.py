"""Regression tests for configuration-driven outbound request boundaries."""

from __future__ import annotations

import json
from typing import Any
from urllib.request import Request

import pytest

from sdp import authz, network_security, observability
from sdp.network_security import validate_outbound_https_url


@pytest.mark.parametrize(
    ("raw_url", "expected"),
    [
        ("https://example.com", "https://example.com/"),
        (" HTTPS://EXAMPLE.COM:8443/jwks?tenant=demo ", "https://example.com:8443/jwks?tenant=demo"),
        ("https://bücher.example/keys", "https://xn--bcher-kva.example/keys"),
        ("https://8.8.8.8/dns-query", "https://8.8.8.8/dns-query"),
        ("https://８．８．８．８/dns-query", "https://8.8.8.8/dns-query"),
        ("https://０x８.８.８.８/dns-query", "https://8.8.8.8/dns-query"),
        ("https://[2001:4860:4860::8888]/dns-query", "https://[2001:4860:4860::8888]/dns-query"),
    ],
)
def test_validate_outbound_https_url_accepts_public_targets(raw_url: str, expected: str) -> None:
    assert validate_outbound_https_url(raw_url, setting_name="TEST_URL") == expected


@pytest.mark.parametrize(
    "raw_url",
    [
        "",
        "http://example.com/keys",
        "file:///etc/passwd",
        "https://user:secret@example.com/keys",
        "https://example.com/keys#fragment",
        "https://localhost/keys",
        "https://api.localhost/keys",
        "https://internal-service/keys",
        "https://127.0.0.1/keys",
        "https://127.1/keys",
        "https://0177.0.0.1/keys",
        "https://0x7f.1/keys",
        "https://１２７．０．０．１/keys",
        "https://０x７f.１/keys",
        "https://10.0.0.1/keys",
        "https://169.254.169.254/latest/meta-data",
        "https://[::1]/keys",
        "https://example.com:invalid/keys",
        "https:///missing-host",
        "https://./keys",
        "https://[broken",
        "https://\ud800.example/keys",
    ],
)
def test_validate_outbound_https_url_rejects_unsafe_targets(raw_url: str) -> None:
    with pytest.raises(ValueError, match="TEST_URL"):
        validate_outbound_https_url(raw_url, setting_name="TEST_URL")


def test_load_jwks_rejects_unsafe_url_before_network(monkeypatch: pytest.MonkeyPatch) -> None:
    called = False

    def fail_if_called(*_args: Any, **_kwargs: Any) -> None:
        nonlocal called
        called = True
        raise AssertionError("network client must not receive an unsafe URL")

    monkeypatch.setattr(authz, "open_url_without_redirects", fail_if_called)

    with pytest.raises(ValueError, match="SDP_OIDC_JWKS_URL must use https"):
        authz._load_jwks_from_url("file:///etc/passwd")

    assert called is False


def test_load_jwks_uses_normalized_https_url(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    class Response:
        def __enter__(self) -> "Response":
            return self

        def __exit__(self, *_args: Any) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps({"keys": []}).encode("utf-8")

    def fake_urlopen(url: str, *, timeout: float) -> Response:
        captured.update(url=url, timeout=timeout)
        return Response()

    monkeypatch.setattr(authz, "open_url_without_redirects", fake_urlopen)
    monkeypatch.setattr(authz, "get_credential", lambda _name, default: "1.25")

    assert authz._load_jwks_from_url(" HTTPS://EXAMPLE.COM/jwks ") == {"keys": []}
    assert captured == {"url": "https://example.com/jwks", "timeout": 1.25}


def test_observability_rejects_plain_http_sink(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SDP_LOG_SINK_URL", "http://example.com/logs")

    with pytest.raises(ValueError, match="SDP_LOG_SINK_URL must use https"):
        observability._export_to_sink({"request_id": "request-1"})


def test_observability_sink_status_normalizes_https(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SDP_LOG_SINK_URL", " HTTPS://EXAMPLE.COM:8443/logs ")
    monkeypatch.setenv("SDP_ALERT_WEBHOOK_URL", "https://alerts.example/hook")

    assert observability._sink_status() == {
        "configured": True,
        "scheme": "https",
        "target": "example.com:8443",
        "alert_webhook_configured": True,
    }


def test_observability_posts_only_to_validated_https_sink(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class Response:
        def __enter__(self) -> "Response":
            return self

        def __exit__(self, *_args: Any) -> None:
            return None

    def fake_urlopen(request: Request, *, timeout: float) -> Response:
        captured.update(
            url=request.full_url,
            timeout=timeout,
            body=request.data,
            method=request.method,
        )
        return Response()

    monkeypatch.setenv("SDP_LOG_SINK_URL", " HTTPS://EXAMPLE.COM:8443/logs ")
    monkeypatch.setattr(observability, "get_credential", lambda _name, default: "750")
    monkeypatch.setattr(observability, "open_url_without_redirects", fake_urlopen)

    observability._export_to_sink({"request_id": "request-2"})

    assert captured == {
        "url": "https://example.com:8443/logs",
        "timeout": 0.75,
        "body": b'{"request_id": "request-2"}',
        "method": "POST",
    }


def test_redirect_handler_rejects_every_follow_up_url() -> None:
    """A validated public URL must never trigger urllib's automatic follow-up."""

    handler = network_security._RejectRedirects()
    request = Request("https://public.example/jwks")

    for target in (
        "http://127.0.0.1/internal",
        "https://169.254.169.254/latest/meta-data",
        "https://other-public.example/jwks",
    ):
        with pytest.raises(ValueError, match="redirect"):
            handler.redirect_request(request, None, 302, "Found", {}, target)


def test_outbound_client_installs_redirect_rejection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The production opener must contain the rejecting redirect handler."""

    captured: dict[str, Any] = {}
    response = object()

    class Opener:
        def open(self, request: str, *, timeout: float) -> object:
            captured.update(request=request, timeout=timeout)
            return response

    def fake_build_opener(handler: Any) -> Opener:
        captured["handler"] = handler
        return Opener()

    monkeypatch.setattr(network_security, "build_opener", fake_build_opener)

    result = network_security.open_url_without_redirects(
        "https://public.example/resource",
        timeout=1.5,
    )

    assert result is response
    assert isinstance(captured["handler"], network_security._RejectRedirects)
    assert captured["request"] == "https://public.example/resource"
    assert captured["timeout"] == 1.5
