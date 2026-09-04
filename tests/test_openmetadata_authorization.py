"""Authorization tests for the OpenMetadata HTTP boundary."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sdp_core import ActorContext

from openmetadata_test_support import table_payload
from sdp import openmetadata_routes


def _client() -> TestClient:
    """Create a minimal app containing only the integration router."""

    app = FastAPI()
    app.include_router(openmetadata_routes.router)
    return TestClient(app)


def _payload(tenant_id: str = "tenant_acme") -> dict[str, object]:
    """Return a valid normalization request for one source installation."""

    return {
        "tenant_id": tenant_id,
        "source_instance_id": "metadata_primary",
        "source_release": "2.0.1",
        "table": table_payload(),
    }


def _verified_actor(
    monkeypatch: pytest.MonkeyPatch,
    *,
    tenant_id: str = "tenant_acme",
    roles: list[str] | None = None,
) -> None:
    """Replace cryptographic verification with a typed verified actor fixture."""

    def verify_actor(_token: str) -> tuple[ActorContext, dict[str, object]]:
        return (
            ActorContext(
                subject="user_001",
                tenant_id=tenant_id,
                roles=roles or ["data-analyst"],
            ),
            {"sub": "user_001", "tenant_id": tenant_id},
        )

    monkeypatch.setattr(
        openmetadata_routes,
        "verify_oidc_jwks_token",
        verify_actor,
    )


def test_missing_bearer_authentication_is_rejected() -> None:
    """An unauthenticated caller cannot choose a tenant namespace."""

    response = _client().post(
        "/integrations/openmetadata/v1/table-snapshots:normalize",
        json=_payload(),
    )

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json() == {"detail": "Bearer authentication required"}


def test_invalid_bearer_token_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OIDC verification failure remains a bounded 401 response."""

    def reject_token(_token: str) -> tuple[ActorContext, dict[str, object]]:
        raise ValueError("signature detail must not escape")

    monkeypatch.setattr(
        openmetadata_routes,
        "verify_oidc_jwks_token",
        reject_token,
    )
    response = _client().post(
        "/integrations/openmetadata/v1/table-snapshots:normalize",
        headers={"Authorization": "Bearer invalid"},
        json=_payload(),
    )

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json() == {"detail": "Bearer token is invalid"}
    assert "signature detail" not in response.text


def test_insufficient_role_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A verified identity still requires an integration-facing role."""

    _verified_actor(monkeypatch, roles=["viewer"])
    response = _client().post(
        "/integrations/openmetadata/v1/table-snapshots:normalize",
        headers={"Authorization": "Bearer valid"},
        json=_payload(),
    )

    assert response.status_code == 403
    assert response.json() == {
        "detail": "OpenMetadata normalization permission required"
    }


def test_cross_tenant_request_is_hidden(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A verified actor cannot project data into another tenant namespace."""

    _verified_actor(monkeypatch, tenant_id="tenant_acme")
    response = _client().post(
        "/integrations/openmetadata/v1/table-snapshots:normalize",
        headers={"Authorization": "Bearer valid"},
        json=_payload(tenant_id="tenant_other"),
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "resource not found"}


@pytest.mark.parametrize(
    "roles",
    [["data-analyst"], ["admin"], ["platform-admin"]],
)
def test_authorized_same_tenant_actor_can_normalize(
    monkeypatch: pytest.MonkeyPatch,
    roles: list[str],
) -> None:
    """Supported roles can use the non-mutating boundary in their own tenant."""

    _verified_actor(monkeypatch, roles=roles)
    response = _client().post(
        "/integrations/openmetadata/v1/table-snapshots:normalize",
        headers={"Authorization": "Bearer valid"},
        json=_payload(),
    )

    assert response.status_code == 200
    assert response.json()["source_instance_id"] == "metadata_primary"
