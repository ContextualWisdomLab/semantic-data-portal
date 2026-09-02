"""Regression contracts for evidence-only catalog retrieval."""

from __future__ import annotations

import inspect
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sdp import catalog  # noqa: E402

_CRM = "crm-customer-master"
_REPO = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _isolate_state():
    data = {key: value.model_copy(deep=True) for key, value in catalog._DATA.items()}
    try:
        yield
    finally:
        catalog._DATA.clear()
        catalog._DATA.update(data)


def test_catalog_source_contains_no_hand_weighted_term_score() -> None:
    source = inspect.getsource(catalog)
    for forbidden in (
        "score += 1.0",
        "score += 0.8",
        "score += 0.5",
        "score += 0.7",
        "score += 0.6",
        "score += 0.1",
        "score += 0.4",
        "len(overlap_terms) * 2 + len(overlap_columns)",
        "metadata_completeness < 0.8",
        "by_token.sort(key=lambda row: row.score, reverse=True)",
        "candidates.sort(key=lambda row: row[\"score\"], reverse=True)",
    ):
        assert forbidden not in source


def test_api_contains_no_repository_authored_completeness_badge_cutoff() -> None:
    source = (_REPO / "src/sdp/api.py").read_text(encoding="utf-8")
    assert "metadata_recommendation_score >= 0.8" not in source
    assert "Query(default=20, ge=1, le=100)" not in source
    assert "Query(default=10, ge=1, le=100)" not in source


def test_search_returns_unranked_boolean_matches_without_score() -> None:
    base = catalog._DATA[_CRM]
    catalog._DATA["aaa-title-match"] = base.model_copy(
        update={
            "id": "aaa-title-match",
            "title": "customer evidence",
            "description": "unrelated",
            "tags": [],
            "terms": [],
            "mappings": [],
            "sensitivity": "high",
        }
    )
    catalog._DATA["zzz-term-match"] = base.model_copy(
        update={
            "id": "zzz-term-match",
            "title": "unrelated",
            "description": "unrelated",
            "tags": [],
            "terms": ["customer"],
            "mappings": [],
            "sensitivity": "low",
        }
    )
    rows = catalog.search_catalog("customer", include_inactive=True)
    selected = [row for row in rows if row.dataset.id in {"aaa-title-match", "zzz-term-match"}]
    assert [row.dataset.id for row in selected] == ["aaa-title-match", "zzz-term-match"]
    assert all(row.score is None for row in selected)


def test_search_fails_closed_when_limit_would_require_ranking() -> None:
    rows = catalog.search_catalog("customer", include_inactive=True)
    assert len(rows) > 1
    with pytest.raises(ValueError, match="ranking evidence"):
        catalog.search_catalog("customer", include_inactive=True, limit=1)


def test_metadata_completeness_is_not_an_implicit_admission_threshold() -> None:
    base = catalog._DATA[_CRM]
    catalog._DATA["published-incomplete"] = base.model_copy(
        update={
            "id": "published-incomplete",
            "owner": "",
            "steward": "",
            "title": "customer incomplete",
            "status": "published",
        }
    )
    ids = {row.dataset.id for row in catalog.search_catalog("customer")}
    assert "published-incomplete" in ids


def test_deprecated_lifecycle_state_controls_inactive_filter() -> None:
    base = catalog._DATA[_CRM]
    catalog._DATA["deprecated-customer"] = base.model_copy(
        update={"id": "deprecated-customer", "title": "customer deprecated", "status": "deprecated"}
    )
    assert "deprecated-customer" not in {
        row.dataset.id for row in catalog.search_catalog("customer")
    }
    assert "deprecated-customer" in {
        row.dataset.id
        for row in catalog.search_catalog("customer", include_inactive=True)
    }


def test_join_candidates_are_unranked_evidence_rows() -> None:
    rows = catalog.get_join_candidates(_CRM)
    assert rows
    assert [row["dataset_id"] for row in rows] == sorted(row["dataset_id"] for row in rows)
    assert all(row["score"] is None for row in rows)
    assert all("overlap_term_count" in row and "overlap_column_count" in row for row in rows)


def test_join_candidate_limit_fails_closed_instead_of_truncating() -> None:
    rows = catalog.get_join_candidates(_CRM)
    if len(rows) < 2:
        pytest.skip("fixture does not contain two join candidates")
    with pytest.raises(ValueError, match="ranking evidence"):
        catalog.get_join_candidates(_CRM, limit=1)
