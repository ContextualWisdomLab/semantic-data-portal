from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from sdp.api import app


client = TestClient(app)


def _candidate(fingerprint: str = "a" * 64) -> dict:
    return {
        "candidate_fingerprint": fingerprint,
        "review_fingerprint": "b" * 64,
        "destination_provider": "icloud",
        "destination_account_scope": "personal",
        "archive_kind": "media",
        "bytes": 61386624,
        "created_ms": 1779274205000,
        "modified_ms": 1779274205000,
        "production_time_ms": 1765324800000,
        "production_time_source": "embedded:ffprobe:comment-date",
        "production_time_confidence": "high",
        "requires_review": True,
        "review_reasons": ["recording-may-contain-sensitive-speech"],
        "content_title": "251210_1631",
        "content_authors": ["My Recording"],
        "content_context": ["download-agent=Bandizip"],
        "duration_ms": 4608791,
        "dataset_profile": None,
        "metadata_evidence": [
            {
                "field": "production-date",
                "value": "2025-12-10",
                "source": "embedded:ffprobe:comment-date",
                "confidence": "high",
            }
        ],
        "blocked_reason": None,
    }


def _request(candidate: dict | None = None, *, actor: str = "admin") -> dict:
    return {
        "actor": actor,
        "catalog": {
            "schema": "disksage.file-catalog-candidate-batch",
            "version": 1,
            "production_time_precedence": [
                "embedded_metadata",
                "explicit_filename_date",
                "filesystem_created",
                "filesystem_modified",
            ],
            "generated_at_ms": int(datetime.now(timezone.utc).timestamp() * 1000),
            "candidates": [candidate or _candidate()],
        },
    }


def test_ingests_path_free_disksage_batch_as_graph_nodes_and_edge():
    response = client.post("/integrations/disksage/catalog", json=_request())

    assert response.status_code == 200
    body = response.json()
    assert body["candidate_count"] == 1
    assert body["batch_id"].startswith("disksage:batch:")

    candidate = client.get("/graph/nodes/disksage:candidate:" + "a" * 64)
    assert candidate.status_code == 200
    assert candidate.json()["kind"] == "file_candidate"
    assert (
        candidate.json()["properties"]["production_time_source"]
        == "embedded:ffprobe:comment-date"
    )
    assert "/Users/" not in candidate.text

    graph = client.post(
        "/graph/query",
        json={
            "start_id": "disksage:candidate:" + "a" * 64,
            "edge_types": ["cataloged_in"],
            "direction": "out",
            "max_depth": 1,
            "actor": "analyst",
        },
    )
    assert graph.status_code == 200
    assert graph.json()["edges"][0]["edge_type"] == "cataloged_in"


def test_disksage_catalog_write_requires_admin():
    response = client.post(
        "/integrations/disksage/catalog", json=_request(actor="analyst")
    )
    assert response.status_code == 403


def test_disksage_catalog_rejects_filename_date_when_embedded_evidence_exists():
    candidate = _candidate("c" * 64)
    candidate["production_time_ms"] = 1775001600000
    candidate["production_time_source"] = "filename:path-token"
    candidate["production_time_confidence"] = "low"
    candidate["metadata_evidence"] = [
        {
            "field": "production-date",
            "value": "2025-12-10",
            "source": "embedded:ffprobe:comment-date",
            "confidence": "high",
        },
        {
            "field": "filename-date-hint",
            "value": "2026-04-01",
            "source": "filename:path-token",
            "confidence": "low",
        },
    ]
    response = client.post("/integrations/disksage/catalog", json=_request(candidate))
    assert response.status_code == 422


def test_disksage_catalog_rejects_path_bearing_unknown_field():
    body = _request()
    body["catalog"]["candidates"][0]["relative_path"] = "private/report.pdf"

    response = client.post("/integrations/disksage/catalog", json=body)

    assert response.status_code == 422


def test_disksage_catalog_rejects_absolute_path_in_metadata_value():
    body = _request()
    body["catalog"]["candidates"][0]["content_context"] = [
        "source=/Users/seonghobae/Downloads/private.m4a"
    ]

    response = client.post("/integrations/disksage/catalog", json=body)

    assert response.status_code == 422


def test_disksage_catalog_rejects_file_uri_and_linux_home_paths():
    for leaked_context in (
        "source=file:///Users/private/Downloads/private.m4a",
        "source=/home/analyst/private.m4a",
    ):
        body = _request()
        body["catalog"]["candidates"][0]["content_context"] = [leaked_context]

        response = client.post("/integrations/disksage/catalog", json=body)

        assert response.status_code == 422
