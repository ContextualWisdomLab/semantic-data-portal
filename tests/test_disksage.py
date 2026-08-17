"""DiskSage catalog preview boundary tests."""

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from sdp import api as api_module
from sdp.api import app
from sdp.disksage import (
    DiskSageCandidate,
    DiskSageCatalogBatch,
    _is_closed_code,
    _production_time_source_class,
    catalog_preview,
)


client = TestClient(app)

_PRODUCTION_MS = 1767355000000
_PRODUCTION_DATE = datetime.fromtimestamp(
    _PRODUCTION_MS / 1000, tz=timezone.utc
).date().isoformat()


def _candidate(seed: str = "a", **overrides: object) -> dict:
    """Return a valid candidate payload, applying field overrides last."""

    payload: dict[str, object] = {
        "candidate_fingerprint": seed * 64,
        "review_fingerprint": "b" * 64,
        "destination_provider": "icloud",
        "destination_account_scope": "personal",
        "archive_kind": "document",
        "bytes": 4096,
        "created_ms": 1767355001000,
        "modified_ms": 1767355002000,
        "production_time_ms": _PRODUCTION_MS,
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
                "value": _PRODUCTION_DATE,
                "source": "embedded:ooxml:created",
                "confidence": "high",
            }
        ],
        "blocked_reason": None,
    }
    payload.update(overrides)
    return payload


def _batch(candidates: list[dict] | None = None) -> dict:
    """Return a valid batch payload."""

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
        "candidates": candidates or [_candidate()],
    }


def _non_embedded(
    source: str,
    field: str,
    evidence_source: str,
    seed: str = "c",
) -> dict:
    """Return a low-confidence non-embedded candidate for the given closed source."""

    return _candidate(
        seed,
        production_time_source=source,
        production_time_confidence="low",
        metadata_evidence=[
            {
                "field": field,
                "value": _PRODUCTION_DATE,
                "source": evidence_source,
                "confidence": "low",
            }
        ],
    )


def test_closed_code_helpers_accept_classification_values_only():
    assert _production_time_source_class("embedded:ooxml:created") == "embedded_metadata"
    assert _production_time_source_class("filename:path-token") == "explicit_filename_date"
    assert _production_time_source_class("filesystem:created") == "filesystem_created"
    assert (
        _production_time_source_class("filesystem:modified-fallback")
        == "filesystem_modified"
    )
    assert _production_time_source_class("embedded:/Users/example") is None
    assert _is_closed_code("policy-denied") is True
    assert _is_closed_code("Users.alice.secret.txt") is False


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
    assert body["datasets"][0]["production_time_source"] == "embedded_metadata"
    assert "metadata_evidence" not in body["datasets"][0]


@pytest.mark.parametrize(
    ("source", "field", "evidence_source", "expected_class"),
    [
        (
            "filename:path-token",
            "filename-date-hint",
            "filename:path-token",
            "explicit_filename_date",
        ),
        (
            "filesystem:created",
            "filesystem-created-date",
            "filesystem:created",
            "filesystem_created",
        ),
        (
            "filesystem:modified-fallback",
            "filesystem-modified-date",
            "filesystem:modified",
            "filesystem_modified",
        ),
    ],
)
def test_disksage_catalog_preview_projects_closed_non_embedded_classes(
    source: str, field: str, evidence_source: str, expected_class: str
):
    payload = _batch([_non_embedded(source, field, evidence_source)])
    response = client.post("/integrations/disksage/catalog-preview", json=payload)
    assert response.status_code == 200
    assert response.json()["datasets"][0]["production_time_source"] == expected_class


def test_disksage_catalog_preview_returns_closed_production_time_and_blocked_codes():
    payload = _batch(
        [
            _candidate(
                blocked_reason="policy-denied",
                dataset_profile={"kind": "tabular"},
                requires_review=True,
                review_reasons=["steward-hold"],
                content_title=None,
                content_authors=["analyst"],
                content_context=["quarterly-close"],
            )
        ]
    )
    response = client.post("/integrations/disksage/catalog-preview", json=payload)
    assert response.status_code == 200
    dataset = response.json()["datasets"][0]
    assert dataset["production_time_source"] == "embedded_metadata"
    assert dataset["blocked_reason"] == "policy-denied"
    assert dataset["profile_present"] is True
    assert dataset["content_metadata_present"] is True
    assert dataset["requires_review"] is True


def test_disksage_catalog_preview_rejects_unknown_path_fields():
    payload = _batch()
    payload["candidates"][0]["relative_path"] = "secret.txt"
    response = client.post("/integrations/disksage/catalog-preview", json=payload)
    assert response.status_code == 400
    assert response.json()["detail"] == "invalid DiskSage catalog batch"


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
    assert response.json()["detail"] == "invalid DiskSage catalog batch"
    assert value not in response.text
    assert "/Users/example" not in response.text
    assert "Users.alice" not in response.text


def test_disksage_catalog_preview_redacts_unexpected_errors(monkeypatch):
    def _boom(_batch: object) -> dict:
        raise RuntimeError("secret /Users/example/file")

    monkeypatch.setattr(api_module, "catalog_preview", _boom)
    response = client.post("/integrations/disksage/catalog-preview", json=_batch())
    assert response.status_code == 500
    assert response.json()["detail"] == "DiskSage catalog preview unavailable"
    assert "/Users/example" not in response.text
    assert "secret" not in response.text


def test_disksage_file_asset_preview_alias_is_available():
    response = client.post("/file-assets/preview/disksage", json=_batch())
    assert response.status_code == 200


@pytest.mark.parametrize(
    "overrides",
    [
        {"requires_review": True, "review_reasons": []},
        {"requires_review": True, "review_reasons": [""]},
        {"content_authors": [""]},
        {"content_context": [""]},
        {
            "production_time_source": "filename:path-token",
            "production_time_confidence": "high",
            "metadata_evidence": [
                {
                    "field": "filename-date-hint",
                    "value": _PRODUCTION_DATE,
                    "source": "filename:path-token",
                    "confidence": "high",
                }
            ],
        },
        {
            "metadata_evidence": [
                {
                    "field": "wrong-field",
                    "value": _PRODUCTION_DATE,
                    "source": "embedded:ooxml:created",
                    "confidence": "high",
                }
            ]
        },
    ],
)
def test_disksage_candidate_rejects_inconsistent_review_and_evidence(overrides: dict):
    with pytest.raises(ValidationError):
        DiskSageCandidate.model_validate(_candidate(**overrides))


def test_disksage_batch_rejects_precedence_mismatch_and_duplicate_fingerprints():
    with pytest.raises(ValidationError):
        DiskSageCatalogBatch.model_validate(
            {**_batch(), "production_time_precedence": ["embedded_metadata"]}
        )
    with pytest.raises(ValidationError):
        DiskSageCatalogBatch.model_validate(_batch([_candidate("a"), _candidate("a")]))


def test_catalog_preview_projects_closed_codes_without_persistence():
    batch = DiskSageCatalogBatch.model_validate(
        _batch([_candidate(blocked_reason="needs-review", dataset_profile={"rows": 1})])
    )
    preview = catalog_preview(batch)
    assert preview["catalog_write_executed"] is False
    assert preview["datasets"][0]["blocked_reason"] == "needs-review"
    assert preview["datasets"][0]["profile_present"] is True
    assert preview["datasets"][0]["production_time_source"] == "embedded_metadata"
