"""Buyer-facing tests for the ontology/catalog plane above the document KG."""

from __future__ import annotations

from time import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from sdp.api import app
from sdp.catalog_plane import reset_catalog_plane
from sdp.tenant_binding import (
    PURPOSE_HEADER,
    SUBJECT_HEADER,
    TENANT_HEADER,
    TenantBindingError,
    bind_keyverse_tenant,
)


client = TestClient(app)


@pytest.fixture(autouse=True)
def _isolate_catalog_plane():
    """Keep plane rows from leaking across tests."""

    reset_catalog_plane()
    yield
    reset_catalog_plane()


def _headers(
    *,
    subject: str = "admin",
    tenant: str = "demo",
    purpose: str = "glossary_stewardship",
) -> dict[str, str]:
    """Build the fail-closed Keyverse header set used by a buyer steward."""

    return {
        SUBJECT_HEADER: subject,
        TENANT_HEADER: tenant,
        PURPOSE_HEADER: purpose,
    }


def _create_payload(**overrides: object) -> dict[str, object]:
    """Return a realistic glossary-term payload above a naruon content node."""

    payload: dict[str, object] = {
        "object_kind": "glossary_term",
        "object_slug": "active-customer",
        "display_title": "활성 고객",
        "definition_text": "최근 활성이 확인된 고객 집합. 문서 KG의 해당 content_node를 해석한다.",
        "preferred_language": "ko",
        "steward_display_name": "Mina Park",
        "aliases": [{"alias_text": "active customer", "alias_language": "en"}],
        "document_kg_links": [
            {
                "source_system": "naruon",
                "source_object_kind": "content_node",
                "source_object_id": "cn_buyer_active_customer_2026",
                "provenance_uri": "https://www.w3.org/TR/prov-o/",
            }
        ],
        "concept_bindings": [{"concept_key": "활성 고객", "binding_role": "preferred"}],
        "score_references": [
            {
                "score_system": "tepp",
                "score_endpoint": "https://commons.example.test/tepp/items/active-customer",
            }
        ],
    }
    payload.update(overrides)
    return payload


def test_buyer_can_create_list_get_and_query_catalog_object():
    """A steward registers a glossary term and finds it again in the same tenant."""

    created = client.post(
        "/plane/catalog-objects",
        json=_create_payload(),
        headers=_headers(),
    )
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["status"] == "created"
    assert body["tenant_reference"] == "demo"
    assert body["pii_handling"] == "usable_purpose_limited_no_masking"
    assert body["catalog_object"]["steward"]["steward_display_name"] == "Mina Park"
    assert "***" not in created.text
    assert "cn_buyer_active_customer_2026" in created.text
    assert "customer_next_action" in body
    catalog_object_id = body["catalog_object"]["catalog_object_id"]

    listed = client.get("/plane/catalog-objects", headers=_headers(subject="analyst", purpose="catalog_browse"))
    assert listed.status_code == 200
    assert listed.json()["count"] == 1
    assert listed.json()["catalog_objects"][0]["catalog_object_id"] == catalog_object_id

    fetched = client.get(
        f"/plane/catalog-objects/{catalog_object_id}",
        headers=_headers(subject="analyst", purpose="catalog_browse"),
    )
    assert fetched.status_code == 200
    assert fetched.json()["catalog_object"]["object_slug"] == "active-customer"
    assert fetched.json()["catalog_object"]["steward"]["steward_display_name"] == "Mina Park"

    queried = client.get(
        "/plane/query",
        params={"q": "cn_buyer_active_customer_2026"},
        headers=_headers(subject="analyst", purpose="ontology_query"),
    )
    assert queried.status_code == 200
    assert queried.json()["count"] == 1
    assert queried.json()["catalog_objects"][0]["display_title"] == "활성 고객"


def test_plane_rejects_missing_tenant_header_fail_closed():
    """Missing X-CWL-Tenant-Reference is 401, not an implicit demo tenant."""

    response = client.post(
        "/plane/catalog-objects",
        json=_create_payload(),
        headers={SUBJECT_HEADER: "admin", PURPOSE_HEADER: "glossary_stewardship"},
    )
    assert response.status_code == 401
    detail = response.json()["detail"]
    assert detail["error"] == "missing_tenant_reference"
    assert "X-CWL-Tenant-Reference" in detail["customer_next_action"]


def test_plane_rejects_missing_access_purpose():
    """Purpose limitation is required; the plane will not infer a purpose."""

    response = client.get(
        "/plane/catalog-objects",
        headers={SUBJECT_HEADER: "analyst", TENANT_HEADER: "demo"},
    )
    assert response.status_code == 401
    assert response.json()["detail"]["error"] == "missing_access_purpose"


def test_plane_rejects_duplicate_slug_in_same_tenant():
    """A second glossary term cannot reuse the tenant-local slug."""

    first = client.post("/plane/catalog-objects", json=_create_payload(), headers=_headers())
    assert first.status_code == 200
    second = client.post("/plane/catalog-objects", json=_create_payload(), headers=_headers())
    assert second.status_code == 400
    assert "object_slug already exists" in second.json()["detail"]


def test_plane_rejects_missing_oidc_subject_fail_closed():
    """A tenant header alone is not enough to enter the plane."""

    response = client.get(
        "/plane/catalog-objects",
        headers={TENANT_HEADER: "demo", PURPOSE_HEADER: "catalog_browse"},
    )
    assert response.status_code == 401
    assert response.json()["detail"]["error"] == "missing_oidc_subject"


def test_plane_rejects_tenant_mismatch():
    """Admin in tenant demo cannot act as tenant acme by swapping the header."""

    response = client.post(
        "/plane/catalog-objects",
        json=_create_payload(),
        headers=_headers(tenant="acme"),
    )
    assert response.status_code == 403
    assert response.json()["detail"]["error"] == "tenant_reference_mismatch"
    assert "X-CWL-Tenant-Reference" in response.json()["detail"]["customer_next_action"]


def test_plane_isolates_objects_across_tenants():
    """Objects created in demo are invisible to an external-analyst tenant."""

    created = client.post(
        "/plane/catalog-objects",
        json=_create_payload(),
        headers=_headers(),
    )
    assert created.status_code == 200
    catalog_object_id = created.json()["catalog_object"]["catalog_object_id"]

    listed = client.get(
        "/plane/catalog-objects",
        headers=_headers(subject="external-analyst", tenant="external", purpose="catalog_browse"),
    )
    assert listed.status_code == 200
    assert listed.json()["count"] == 0

    fetched = client.get(
        f"/plane/catalog-objects/{catalog_object_id}",
        headers=_headers(subject="external-analyst", tenant="external", purpose="catalog_browse"),
    )
    assert fetched.status_code == 404


def test_plane_create_requires_admin_role():
    """An analyst may browse but may not register catalog-plane objects."""

    denied = client.post(
        "/plane/catalog-objects",
        json=_create_payload(),
        headers=_headers(subject="analyst"),
    )
    assert denied.status_code == 403


def test_plane_rejects_filesystem_path_as_document_kg_id():
    """The plane stores opaque KG ids, not local file paths."""

    payload = _create_payload(
        document_kg_links=[
            {
                "source_system": "naruon",
                "source_object_kind": "content_node",
                "source_object_id": "/home/analyst/private.eml",
                "provenance_uri": "https://www.w3.org/TR/prov-o/",
            }
        ]
    )
    response = client.post("/plane/catalog-objects", json=payload, headers=_headers())
    assert response.status_code == 422


def test_plane_attaches_document_kg_link_and_concept_after_create():
    """A steward can grow an object without re-ingesting DiskSage batches."""

    created = client.post(
        "/plane/catalog-objects",
        json=_create_payload(document_kg_links=[], concept_bindings=[]),
        headers=_headers(),
    )
    catalog_object_id = created.json()["catalog_object"]["catalog_object_id"]
    assert "document-kg-links" in created.json()["customer_next_action"]

    linked = client.post(
        f"/plane/catalog-objects/{catalog_object_id}/document-kg-links",
        json={
            "source_system": "disksage",
            "source_object_kind": "catalog_batch_ref",
            "source_object_id": "disksage:batch:preview-ref-not-ingest",
            "provenance_uri": "https://www.w3.org/TR/prov-o/",
        },
        headers=_headers(purpose="document_kg_alignment"),
    )
    assert linked.status_code == 200
    assert linked.json()["catalog_object"]["document_kg_links"][0]["source_system"] == "disksage"

    bound = client.post(
        f"/plane/catalog-objects/{catalog_object_id}/concept-bindings",
        json={"concept_key": "매출", "binding_role": "related"},
        headers=_headers(),
    )
    assert bound.status_code == 200
    assert bound.json()["catalog_object"]["concept_bindings"][0]["concept_key"] == "매출"


def test_bind_keyverse_tenant_rejects_unknown_purpose():
    """Purpose limitation is enforced before any catalog row is touched."""

    with pytest.raises(TenantBindingError) as exc_info:
        bind_keyverse_tenant(
            {
                SUBJECT_HEADER: "admin",
                TENANT_HEADER: "demo",
                PURPOSE_HEADER: "export-all-pii",
            }
        )
    assert exc_info.value.error_code == "unsupported_access_purpose"


def test_plane_oidc_bearer_matches_tenant_claim(monkeypatch):
    """A signed Keyverse JWT is accepted only when the tenant header matches."""

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    token = jwt.encode(
        {
            "iss": "https://idp.example.com/",
            "aud": "semantic-data-portal",
            "email": "steward@example.com",
            "tenant_id": "demo",
            "groups": ["sdp-admins"],
            "exp": int(time()) + 3600,
        },
        private_key,
        algorithm="RS256",
        headers={"kid": "plane-key-1"},
    )
    monkeypatch.setenv("SDP_OIDC_ISSUER", "https://idp.example.com/")
    monkeypatch.setenv("SDP_OIDC_AUDIENCE", "semantic-data-portal")

    def _verify(token_value: str, **_kwargs):
        from sdp.authz import resolve_oidc_actor_context

        claims = jwt.decode(token_value, options={"verify_signature": False})
        return resolve_oidc_actor_context(claims), claims

    monkeypatch.setattr("sdp.tenant_binding.verify_oidc_jwks_token", _verify)

    matched = client.post(
        "/plane/catalog-objects",
        json=_create_payload(),
        headers={
            "Authorization": f"Bearer {token}",
            TENANT_HEADER: "demo",
            PURPOSE_HEADER: "glossary_stewardship",
        },
    )
    assert matched.status_code == 200, matched.text
    assert matched.json()["catalog_object"]["created_by_subject"] == "steward@example.com"

    mismatched = client.get(
        "/plane/catalog-objects",
        headers={
            "Authorization": f"Bearer {token}",
            TENANT_HEADER: "acme",
            PURPOSE_HEADER: "catalog_browse",
        },
    )
    assert mismatched.status_code == 403
    assert mismatched.json()["detail"]["error"] == "tenant_reference_mismatch"
