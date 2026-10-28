"""``source_system``'s credential is dropped on every path; a distribution's is not.

``redacted_source_system``'s docstring states the rule this product holds itself
to - the credential is dropped "on every path - including the authorized one,
since no caller needs the credential" - and ``catalog.mutation_view`` exists
because four mutation responses were handing the DSN back. ``DatasetDistribution``
carries an ``endpoint`` of the same shape and escaped all of it. Measured at
``dba2403`` with one dataset registered with
``endpoint: https://dsnuser:SUPERSEKRET123@files.internal/x.csv?token=TOKEN1``::

    POST /catalog/datasets           -> 200, secret in response: True
    GET  /catalog/datasets/{id}      -> secret in response: True, token: True
    redacted_source_system(endpoint) -> 'https://files.internal/x.csv'

The redactor already handles this exact URL correctly, so the field was simply
never routed through it. The same credential in ``source_system`` is withheld
from the identical responses.

Found while verifying that the remedy a refusal names actually works: declaring a
``postgresql.table`` distribution is what ``/llm/draft-query`` tells a steward to
do, which made the distribution write path worth driving end to end.
"""

from __future__ import annotations

import json

from typing import Any

import pytest

from fastapi.testclient import TestClient

from sdp.api import app


client = TestClient(app)

USERINFO_SECRET = "SUPERSEKRET123"
QUERY_SECRET = "TOKENINQUERY"
CREDENTIAL_ENDPOINT = (
    f"https://dsnuser:{USERINFO_SECRET}@files.example.internal/export.csv?token={QUERY_SECRET}"
)
DATASET_ID = "distribution-credential-probe"


def _register() -> dict[str, Any]:
    """Register one dataset whose distribution endpoint carries a credential."""
    body: dict[str, Any] = {
        "id": DATASET_ID,
        "tenant_id": "demo",
        "title": "배포 엔드포인트 자격증명 프로브",
        "description": "엔드포인트 자격증명이 공표되는지 측정하는 프로브",
        "owner": "data-admin",
        "steward": "data-admin",
        "domain": "고객",
        "source_system": f"postgresql://dsnuser:{USERINFO_SECRET}@analytics.dw:5432/crm",
        "sensitivity": "low",
        "update_frequency": "daily",
        "quality_score": 0.9,
        "freshness_score": 0.9,
        "schema": [
            {"name": "customer_id", "datatype": "string", "nullable_ratio": 0.0, "distinct_ratio": 1.0}
        ],
        "distributions": [
            {"id": "export-csv", "format": "csv", "endpoint": CREDENTIAL_ENDPOINT}
        ],
        "actor": "data-admin",
        "reason": "probe",
    }
    created = client.post("/catalog/datasets", json=body)
    assert created.status_code == 200, created.text
    return created.json()


# Every response that carries a dataset, named as (label, callable). The list is
# the point: the ``source_system`` repair had to cover mutation responses *and*
# reads, and this field escaped both.
def _surfaces() -> list[tuple[str, Any]]:
    """Each dataset-bearing response, as ``(label, response)`` pairs."""
    return [
        ("POST /catalog/datasets/{id}/publish", client.post(
            f"/catalog/datasets/{DATASET_ID}/publish", json={"actor": "data-admin", "reason": "p"}
        )),
        ("GET /catalog/datasets/{id}", client.get(f"/catalog/datasets/{DATASET_ID}?user=data-admin")),
        ("GET /catalog/datasets", client.get("/catalog/datasets?user=data-admin")),
        ("GET /catalog/datasets/{id}/jsonld", client.get(f"/catalog/datasets/{DATASET_ID}/jsonld?user=data-admin")),
        ("GET /catalog/search", client.get("/catalog/search?q=프로브&user=data-admin")),
        ("PATCH /catalog/datasets/{id}", client.patch(
            f"/catalog/datasets/{DATASET_ID}",
            json={"actor": "data-admin", "reason": "제목 수정", "title": "프로브 v2"},
        )),
        ("GET /catalog/datasets/{id}/audit", client.get(f"/catalog/datasets/{DATASET_ID}/audit?user=data-admin")),
    ]


def test_the_write_echo_does_not_hand_the_credential_back() -> None:
    """The registration response is the first surface and was the first leak."""
    created = json.dumps(_register(), ensure_ascii=False)
    assert USERINFO_SECRET not in created, "the registration response echoed the endpoint credential"
    assert QUERY_SECRET not in created, "the registration response echoed the endpoint query secret"


def test_no_dataset_bearing_response_publishes_the_endpoint_credential() -> None:
    """Driven over every surface, because the sibling field needed all of them."""
    _register()
    leaking: list[str] = []
    for label, response in _surfaces():
        assert response.status_code == 200, (label, response.text)
        if USERINFO_SECRET in response.text or QUERY_SECRET in response.text:
            leaking.append(label)
    assert not leaking, f"these responses publish the distribution endpoint's credential: {leaking}"


def test_the_locator_itself_is_still_published() -> None:
    """Redaction, not removal: the endpoint is how a consumer fetches the data."""
    _register()
    body = client.get(f"/catalog/datasets/{DATASET_ID}?user=data-admin").json()
    endpoints = [distribution["endpoint"] for distribution in body["distributions"]]
    assert endpoints == ["https://files.example.internal/export.csv"], endpoints


def test_a_credential_free_endpoint_is_unchanged() -> None:
    """The seeded catalogue must read back exactly as declared."""
    seeded = client.get("/catalog/datasets/crm-customer-master?user=data-admin").json()
    for distribution in seeded["distributions"]:
        assert "@" not in distribution["endpoint"].split("//", 1)[-1].split("/", 1)[0], distribution
        assert distribution["endpoint"].startswith("https://"), distribution


def test_the_patched_endpoint_does_not_reach_the_audit_record() -> None:
    """``audited_patch_values`` redacts a patched ``source_system`` already."""
    _register()
    patched = client.patch(
        f"/catalog/datasets/{DATASET_ID}",
        json={
            "actor": "data-admin",
            "reason": "배포 경로 교체",
            "distributions": [
                {
                    "id": "export-csv",
                    "format": "csv",
                    "endpoint": f"https://rotated:{USERINFO_SECRET}@files.example.internal/v2.csv",
                }
            ],
        },
    )
    assert patched.status_code == 200, patched.text
    audit = client.get(f"/catalog/datasets/{DATASET_ID}/audit?user=data-admin")
    assert audit.status_code == 200, audit.text
    assert USERINFO_SECRET not in audit.text, "the audit record stored the endpoint credential"
    assert "files.example.internal/v2.csv" in audit.text, "the change itself must stay auditable"
