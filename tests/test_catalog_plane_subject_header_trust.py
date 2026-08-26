"""Regression tests for the catalog-plane subject-header trust boundary."""

from __future__ import annotations

from fastapi.testclient import TestClient

from sdp.api import app
from sdp.tenant_binding import PURPOSE_HEADER, SUBJECT_HEADER, TENANT_HEADER


client = TestClient(app)


def _headers() -> dict[str, str]:
    """Return a complete catalog browse request using the demo subject header."""

    return {
        SUBJECT_HEADER: "analyst",
        TENANT_HEADER: "demo",
        PURPOSE_HEADER: "catalog_browse",
    }


def _clear_jwks(monkeypatch) -> None:
    """Remove production OIDC coordinates so only the demo boundary is tested."""

    monkeypatch.delenv("SDP_OIDC_ISSUER", raising=False)
    monkeypatch.delenv("SDP_OIDC_AUDIENCE", raising=False)
    monkeypatch.delenv("SDP_OIDC_JWKS_URL", raising=False)


def test_subject_header_is_rejected_without_explicit_demo_opt_in(monkeypatch) -> None:
    """A directly reachable deployment must not trust a raw subject header by default."""

    _clear_jwks(monkeypatch)
    monkeypatch.delenv("SDP_ALLOW_UNVERIFIED_SUBJECT_HEADER", raising=False)

    response = client.get("/plane/catalog-objects", headers=_headers())

    assert response.status_code == 401
    detail = response.json()["detail"]
    assert detail["error"] == "oidc_subject_header_rejected"
    assert "Authorization: Bearer" in detail["customer_next_action"]


def test_subject_header_is_accepted_with_explicit_demo_opt_in(monkeypatch) -> None:
    """Local demo and CI may opt in without weakening the production default."""

    _clear_jwks(monkeypatch)
    monkeypatch.setenv("SDP_ALLOW_UNVERIFIED_SUBJECT_HEADER", "true")

    response = client.get("/plane/catalog-objects", headers=_headers())

    assert response.status_code == 200
    assert response.json()["tenant_reference"] == "demo"
