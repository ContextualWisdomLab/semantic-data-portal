"""``GET /catalog/search`` published ``count`` as if it were the whole answer.

The route caps ``limit`` at 100, ``catalog.search_catalog`` returns
``by_token[:limit]``, and the body is ``{query, count, items}`` - no total, no
truncation flag, and **no ``offset``**, so a caller cannot reach match 101. The
product's own sibling contradicts it: ``GET /catalog/facets`` counts the same
matched population and reports more than the page.

Measured at ``e55292a`` after onboarding enough matching datasets::

    GET /catalog/search?q=고객&user=admin&limit=100   -> count 100, items 100
    GET /catalog/facets?user=admin                    -> (the same population) 150
    GET /catalog/search?q=고객&user=admin&offset=100   -> 422 (no such parameter)

A diligence reader asking "how many of my datasets mention 고객?" is handed 100
and nothing says otherwise. This repository has repaired the same class three
times on the evidence routes (``/policy/decisions``, ``/audit/events``,
``/catalog/datasets/{id}/audit`` gained ``offset``), and
``GET /ontology/change-log`` already publishes the honest shape this route now
follows: a page length in ``count`` beside an explicit total, a withheld count
and a truncation flag.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from sdp.api import app


client = TestClient(app)

QUERY = "경계탐침용어"
PAGE_CAP = 100
SEEDED = 120


def _seed_matching_datasets(count: int) -> None:
    """Onboard ``count`` datasets that all match ``QUERY`` through their terms."""
    schema = client.get("/browse/crm-customer-master/schema?user=admin").json()["schema"]
    base = client.get("/catalog/datasets/crm-customer-master?user=admin").json()
    for index in range(count):
        created = client.post(
            "/catalog/datasets",
            json={
                "actor": "admin",
                "id": f"search-page-probe-{index:04d}",
                "tenant_id": "demo",
                "title": f"{QUERY} 데이터셋 {index:04d}",
                "description": f"{QUERY} 를 담은 탐침 데이터셋입니다",
                "domain": base.get("domain", "고객"),
                "owner": "owner@example.com",
                "steward": "steward@example.com",
                "update_frequency": "daily",
                "quality_score": 0.9,
                "freshness_score": 0.9,
                "source_system": "warehouse/search_page_probe",
                "sensitivity": "low",
                "terms": [QUERY],
                "schema": schema,
                "distributions": base.get("distributions") or [],
            },
        )
        assert created.status_code == 200, created.text[:200]


def _search(**params) -> dict:
    query = "&".join(f"{key}={value}" for key, value in params.items())
    response = client.get(f"/catalog/search?q={QUERY}&user=admin&{query}")
    assert response.status_code == 200, (response.status_code, response.text[:300])
    return response.json()


def test_a_truncated_page_says_it_is_truncated() -> None:
    """``count`` is a page length; the total has to be published beside it."""
    _seed_matching_datasets(SEEDED)
    body = _search(limit=PAGE_CAP)
    assert body["count"] == PAGE_CAP, body["count"]
    assert body["total_match_count"] >= SEEDED, body.get("total_match_count")
    assert body["withheld_match_count"] == body["total_match_count"] - PAGE_CAP, body
    assert body["search_is_truncated"] is True, body


def test_an_untruncated_page_says_that_too() -> None:
    """The flag must be derived, not pinned to the default page size."""
    _seed_matching_datasets(3)
    body = _search(limit=PAGE_CAP)
    assert body["search_is_truncated"] is False, body
    assert body["withheld_match_count"] == 0, body
    assert body["total_match_count"] == body["count"], body


def test_the_row_past_the_first_page_is_reachable() -> None:
    """The defect's sharp end: rows the product counted and served to nobody."""
    _seed_matching_datasets(SEEDED)
    first = _search(limit=PAGE_CAP)
    second = _search(limit=PAGE_CAP, offset=PAGE_CAP)

    total = first["total_match_count"]
    assert second["count"] == total - PAGE_CAP, (second["count"], total)
    assert second["search_is_truncated"] is False, second
    assert second["withheld_match_count"] == 0, second

    first_ids = [item["id"] for item in first["items"]]
    second_ids = [item["id"] for item in second["items"]]
    assert not set(first_ids) & set(second_ids), "the two pages overlap"
    assert len(set(first_ids) | set(second_ids)) == total, (
        len(first_ids), len(second_ids), total
    )


def test_a_query_that_matches_nothing_claims_no_withholding() -> None:
    """``q`` only needs one character, so a whitespace query yields no tokens.

    That branch returns early with its own page, and a wrong total there is a
    **false truncation claim on an empty result** - the mutation that set it to
    1 came back green until this test existed, because every other assertion
    here drives a query that does match.
    """
    response = client.get("/catalog/search?q=%20&user=admin")
    assert response.status_code == 200, (response.status_code, response.text[:200])
    body = response.json()
    assert body["count"] == 0, body
    assert body["items"] == [], body
    assert body["total_match_count"] == 0, body
    assert body["withheld_match_count"] == 0, body
    assert body["search_is_truncated"] is False, body


def test_the_offset_is_rejected_when_negative() -> None:
    """A bounded parameter, like every other selector on this surface."""
    response = client.get(f"/catalog/search?q={QUERY}&user=admin&offset=-1")
    assert response.status_code == 422, response.status_code


def test_the_sibling_that_contradicted_this_route_no_longer_does() -> None:
    """``/catalog/facets`` counts the caller's datasets; the search total must fit.

    The facet route counts **every** dataset in scope by domain, not only the
    ones matching the query, so it is a superset - that is the direction
    asserted. (The first version of this test read ``counts["domain"]``; the
    route publishes ``{field, counts}`` with ``counts`` keyed by the domain value
    directly, so the nesting was my error and not the product's.)
    """
    _seed_matching_datasets(SEEDED)
    total = _search(limit=1)["total_match_count"]
    assert total >= SEEDED, total
    facets = client.get("/catalog/facets?user=admin").json()
    assert facets["field"] == "domain", facets
    assert sum(facets["counts"].values()) >= total, (facets["counts"], total)
