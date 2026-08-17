import pytest
from fastapi.testclient import TestClient

from sdp.api import app


client = TestClient(app)


def _candidate(seed: str = "a") -> dict:
    return {
        "candidate_fingerprint": seed * 64,
        "review_fingerprint": "b" * 64,
        "destination_provider": "icloud",
        "destination_account_scope": "personal",
        "archive_kind": "document",
        "bytes": 4096,
        "created_ms": 1767355001000,
        "modified_ms": 1767355002000,
        "production_time_ms": 1767355000000,
        "production_time_source": "embedded:ooxml:created",
        "production_time_confidence": "high",
        "requires_review": False,
        "review_reasons": [],
        "content_title": "Report",
        "content_authors": [],
        "content_context": [],
        "duration_ms": None,
        "dataset_profile": None,
        "metadata_evidence": [
            {
                "field": "production-date",
                "value": "2026-01-02",
                "source": "embedded:ooxml:created",
                "confidence": "high",
            }
        ],
        "blocked_reason": None,
    }


def _batch() -> dict:
    return {
        "schema": "disksage.file-catalog-candidate-batch",
        "version": 1,
        "production_time_precedence": [
            "embedded_metadata",
            "explicit_filename_date",
            "filesystem_created",
            "filesystem_modified",
        ],
        "generated_at_ms": 1767355003000,
        "candidates": [_candidate()],
    }


def test_disksage_catalog_preview_is_path_free_and_non_mutating():
    response = client.post("/integrations/disksage/catalog-preview", json=_batch())
    assert response.status_code == 200
    body = response.json()
    assert body["candidate_count"] == 1
    assert body["catalog_write_executed"] is False
    assert body["eviction_authorized"] is False
    assert body["storage_coordinates_present"] is False
    assert body["copy_authorized"] is False
    assert body["persistable_as_file_asset"] is False
    assert body["datasets"][0]["ontology_class"] == "disksage:CloudArchiveCandidate"
    assert body["datasets"][0]["title"] == "DiskSage document 후보"
    assert body["datasets"][0]["description"] == "경로 비노출 cloud archive candidate preview"
    assert "metadata_evidence" not in body["datasets"][0]


def test_disksage_catalog_preview_rejects_unknown_path_fields():
    payload = _batch()
    payload["candidates"][0]["relative_path"] = "secret.txt"
    response = client.post("/integrations/disksage/catalog-preview", json=payload)
    assert response.status_code == 400


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("production_time_source", "embedded:/Users/example/metadata"),
        ("production_time_source", "embedded:Users.alice.secret.txt"),
        ("blocked_reason", "blocked:/Users/example/file"),
        ("blocked_reason", "Users.alice.secret.txt"),
    ],
)
def test_disksage_catalog_preview_rejects_path_bearing_classification_values(
    field: str, value: str
):
    payload = _batch()
    payload["candidates"][0][field] = value
    response = client.post("/integrations/disksage/catalog-preview", json=payload)
    assert response.status_code == 400
    assert "/Users/example" not in response.text
    assert "Users.alice" not in response.text


def test_disksage_catalog_preview_returns_closed_production_time_and_blocked_codes():
    payload = _batch()
    payload["candidates"][0]["blocked_reason"] = "policy-denied"
    response = client.post("/integrations/disksage/catalog-preview", json=payload)
    assert response.status_code == 200
    dataset = response.json()["datasets"][0]
    assert dataset["production_time_source"] == "embedded_metadata"
    assert dataset["blocked_reason"] == "policy-denied"


def test_disksage_file_asset_preview_alias_is_available():
    response = client.post("/file-assets/preview/disksage", json=_batch())
    assert response.status_code == 200
