"""The PRD declares six p95 latency budgets; this is what relates code to them.

Before ``sdp.latency_budgets`` existed, none of NFR-PERF-001..006 had anything
in the repository that named its target. The middleware had recorded
``latency_ms`` per request all along and ``/enterprise/observability`` published
it, but no code compared any of it to a budget - and a target nothing compares
to is not a gate. CAT-001's acceptance criterion names the same 2-second figure
and was in the same state.

The measurement is deliberately **one-sided**. These observations come from this
process: in-memory stores, seed data, one worker, no client-to-app network. A
deployment adds a database, a real dataset population, concurrency and network
hops, none of which make a request faster. So an over-budget result here is
conclusive and an under-budget result establishes nothing about production,
which is why the published field is ``budget_refuted`` and not
``within_budget``. These tests hold that asymmetry in place, prove the
refutation path actually fires (a gate that cannot fail is not a gate), and keep
the report inside the same disclosure boundary the unauthenticated manifest
already enforces.
"""

from __future__ import annotations

import json
import re

import pytest
from fastapi.testclient import TestClient

from sdp import observability
from sdp.api import app
from sdp.latency_budgets import (
    LATENCY_BUDGETS,
    MIN_SAMPLE_FOR_PERCENTILE,
    budgeted_route_templates,
    latency_budget_report,
    nearest_rank_percentile,
    route_template_for,
)
from sdp_core.requirements import parse_prd_requirements

client = TestClient(app)

# Enough to clear MIN_SAMPLE_FOR_PERCENTILE on every surface with room to spare,
# so the gate below is evaluating a percentile rather than a sample maximum.
_DRIVE_COUNT = MIN_SAMPLE_FOR_PERCENTILE + 5

_PREVIEW_BODY = {"user": "analyst", "purpose": "analysis", "offset": 0, "limit": 2}
_LLM_SEARCH_BODY = {
    "question": "활성 고객 데이터를 찾아줘",
    "user": "analyst",
    "purpose": "analysis",
}
_DRAFT_BODY = {
    "question": "최근 90일 활성 고객 수 주별 집계",
    "user": "analyst",
    "purpose": "analysis",
    "dataset_id": "crm-event",
    "columns": ["customer_id", "event_timestamp"],
    "date_window_days": 30,
    "row_limit": 50,
}
_RESOLVE_BODY = {"text": "활성 고객 데이터를 찾아줘"}


def _drive_every_budgeted_surface() -> None:
    """Issue successful requests against each governed route.

    Asserts each response is 2xx: the report counts only successful responses,
    so a surface that started refusing would otherwise silently contribute no
    sample and read as ``insufficient_sample`` rather than as a broken route.
    """
    calls = [
        lambda: client.get(
            "/catalog/search", params={"q": "customer", "user": "analyst"}
        ),
        lambda: client.get(
            "/catalog/datasets/crm-customer-master", params={"user": "analyst"}
        ),
        lambda: client.get(
            "/browse/crm-customer-master/schema",
            params={"user": "analyst", "purpose": "analysis"},
        ),
        lambda: client.post(
            "/browse/crm-customer-master/preview", json=_PREVIEW_BODY
        ),
        lambda: client.post("/llm/search", json=_LLM_SEARCH_BODY),
        lambda: client.post("/llm/draft-query", json=_DRAFT_BODY),
        lambda: client.post("/ontology/resolve", json=_RESOLVE_BODY),
    ]
    for _ in range(_DRIVE_COUNT):
        for call in calls:
            response = call()
            assert 200 <= response.status_code <= 299, (
                f"a budgeted surface refused: {response.status_code} "
                f"{response.request.method} {response.request.url}"
            )


@pytest.fixture()
def driven_report() -> dict:
    """A report measured over freshly driven traffic on every budgeted surface."""
    observability.reset_request_observability()
    _drive_every_budgeted_surface()
    return latency_budget_report()


def test_every_budget_names_routes_this_app_serves() -> None:
    """A renamed route must break the suite, not quietly stop being measured."""
    served = {
        f"{method} {route.path}"
        for route in app.routes
        for method in (getattr(route, "methods", None) or set())
    }
    missing = sorted(
        f"{method} {template}"
        for method, template in budgeted_route_templates()
        if f"{method} {template}" not in served
    )
    assert missing == [], f"budgets name routes this app does not serve: {missing}"


def test_every_prd_performance_requirement_has_exactly_one_budget() -> None:
    """A new NFR-PERF row in the PRD may not land unbudgeted."""
    stated = sorted(
        requirement.id
        for requirement in parse_prd_requirements()
        if requirement.id.startswith("NFR-PERF-")
    )
    budgeted = sorted(budget.requirement_id for budget in LATENCY_BUDGETS)
    assert budgeted == stated, (
        "the PRD's performance requirements and the declared budgets disagree: "
        f"PRD={stated} budgets={budgeted}"
    )
    assert len(budgeted) == len(set(budgeted)), "a requirement has two budgets"


def test_every_budget_is_evaluated_once_traffic_exists(driven_report: dict) -> None:
    """With a real sample on every surface, no budget may remain unevaluated."""
    unevaluated = [
        row["requirement_id"] for row in driven_report["surfaces"] if not row["evaluated"]
    ]
    assert unevaluated == [], (
        f"these budgets were not evaluated despite driven traffic: {unevaluated}"
    )
    assert driven_report["evaluated_count"] == len(LATENCY_BUDGETS)
    assert driven_report["unevaluated_count"] == 0
    for row in driven_report["surfaces"]:
        assert row["sample_size"] >= MIN_SAMPLE_FOR_PERCENTILE
        assert row["measurement_status"] == "measured_in_process"


def test_no_declared_budget_is_refuted_in_process(driven_report: dict) -> None:
    """The regression gate: an in-process p95 over budget is conclusive.

    This is the check that would have caught the one latency figure this
    repository records against its own target - a 2000-token catalog query
    measured at 5.10s against a 2-second budget (``src/sdp/catalog.py``).
    """
    refuted = [
        (row["requirement_id"], row["observed_p95_ms"], row["budget_ms"])
        for row in driven_report["surfaces"]
        if row["budget_refuted"]
    ]
    assert refuted == [], (
        "an in-process p95 exceeds its declared budget, which is conclusive "
        f"(production can only be slower): {refuted}"
    )
    assert driven_report["refuted_requirement_ids"] == []


def test_the_refutation_path_actually_fires() -> None:
    """A gate that cannot fail is not a gate.

    Drives the real surface, then records one observation slower than the
    tightest budget and shows the verdict flips. Without this, every
    ``budget_refuted: False`` above could be a comparison that never happens.
    """
    observability.reset_request_observability()
    for _ in range(MIN_SAMPLE_FOR_PERCENTILE + 5):
        assert client.post("/ontology/resolve", json=_RESOLVE_BODY).status_code == 200

    before = next(
        row
        for row in latency_budget_report()["surfaces"]
        if row["requirement_id"] == "NFR-PERF-006"
    )
    assert before["evaluated"] is True
    assert before["budget_refuted"] is False

    # One observation per sample slot, so nearest-rank p95 lands on the slow ones.
    for _ in range(MIN_SAMPLE_FOR_PERCENTILE + 5):
        observability.record_request_observation(
            {
                "method": "POST",
                "route": "/ontology/resolve",
                "status_code": 200,
                "latency_ms": 900.0,
            },
            export=False,
        )

    after = next(
        row
        for row in latency_budget_report()["surfaces"]
        if row["requirement_id"] == "NFR-PERF-006"
    )
    assert after["evaluated"] is True
    assert after["budget_refuted"] is True, after
    assert after["observed_p95_ms"] > after["budget_ms"]
    assert "NFR-PERF-006" in latency_budget_report()["refuted_requirement_ids"]


def test_a_thin_sample_yields_no_verdict_in_either_direction() -> None:
    """Fail-closed: below the minimum sample, nothing is claimed."""
    observability.reset_request_observability()
    for _ in range(MIN_SAMPLE_FOR_PERCENTILE - 1):
        assert client.post("/ontology/resolve", json=_RESOLVE_BODY).status_code == 200

    row = next(
        item
        for item in latency_budget_report()["surfaces"]
        if item["requirement_id"] == "NFR-PERF-006"
    )
    assert row["sample_size"] == MIN_SAMPLE_FOR_PERCENTILE - 1
    assert row["evaluated"] is False
    assert row["measurement_status"] == "insufficient_sample"
    # Neither a pass nor a fail - a thin sample may not produce either.
    assert row["observed_p95_ms"] is None
    assert row["budget_refuted"] is None


def test_no_surface_reports_a_verdict_without_an_evaluated_sample(
    driven_report: dict,
) -> None:
    """The invariant behind the two tests above, asserted as a rule."""
    observability.reset_request_observability()
    for report in (latency_budget_report(), driven_report):
        for row in report["surfaces"]:
            if not row["evaluated"]:
                assert row["budget_refuted"] is None, row
                assert row["observed_p95_ms"] is None, row
            else:
                assert isinstance(row["budget_refuted"], bool), row
                assert isinstance(row["observed_p95_ms"], float), row


def test_only_successful_responses_count_toward_a_budget() -> None:
    """A refusal is not a search: counting fast 4xx would flatter every p95."""
    observability.reset_request_observability()
    for _ in range(MIN_SAMPLE_FOR_PERCENTILE + 5):
        observability.record_request_observation(
            {
                "method": "POST",
                "route": "/ontology/resolve",
                "status_code": 403,
                "latency_ms": 0.2,
            },
            export=False,
        )
    row = next(
        item
        for item in latency_budget_report()["surfaces"]
        if item["requirement_id"] == "NFR-PERF-006"
    )
    assert row["sample_size"] == 0, "a refused request contributed a latency sample"
    assert row["evaluated"] is False


def test_an_unbudgeted_route_contributes_to_no_budget() -> None:
    """Traffic on a route no budget governs may not move any surface's sample."""
    observability.reset_request_observability()
    for _ in range(MIN_SAMPLE_FOR_PERCENTILE + 5):
        assert client.get("/health").status_code == 200
    report = latency_budget_report()
    assert report["observation_window"]["observations_available"] > 0
    assert all(row["sample_size"] == 0 for row in report["surfaces"])
    assert report["evaluated_count"] == 0


def test_route_template_for_classifies_with_the_apps_own_router() -> None:
    """A concrete path resolves to its template; an unrouted path to None."""
    assert (
        route_template_for("GET", "/browse/crm-customer-master/schema")
        == "/browse/{dataset_id}/schema"
    )
    assert route_template_for("GET", "/catalog/search") == "/catalog/search"
    # Method matters: the same path is a different route under PATCH.
    assert (
        route_template_for("GET", "/catalog/datasets/crm-event")
        == "/catalog/datasets/{dataset_id}"
    )
    assert route_template_for("DELETE", "/catalog/datasets/crm-event") is None
    assert route_template_for("GET", "/no/such/path") is None


def test_each_surface_publishes_the_window_its_sample_covers(
    driven_report: dict,
) -> None:
    """A p95 is not judgeable without the width of the window behind it.

    The observation buffer is one ring across all routes, so a busy surface
    evicts a quiet one's rows: twenty requests spread over days and twenty from
    the last minute would otherwise publish the same-looking number.
    """
    for row in driven_report["surfaces"]:
        assert "sample_window_seconds" in row, row
        span = row["sample_window_seconds"]
        assert isinstance(span, float), row
        assert span >= 0.0, row
    # The span grows with a genuinely wider window, so the field is live.
    observability.reset_request_observability()
    for stamp in (
        "2026-10-01T00:00:00+00:00",
        "2026-10-01T00:00:30+00:00",
        "2026-10-08T00:00:00+00:00",
    ):
        observability.record_request_observation(
            {
                "timestamp": stamp,
                "method": "POST",
                "route": "/ontology/resolve",
                "status_code": 200,
                "latency_ms": 1.0,
            },
            export=False,
        )
    row = next(
        item
        for item in latency_budget_report()["surfaces"]
        if item["requirement_id"] == "NFR-PERF-006"
    )
    # 2026-10-01T00:00:00 .. 2026-10-08T00:00:00 is exactly seven days.
    assert row["sample_window_seconds"] == 7 * 24 * 60 * 60.0, row


def test_the_window_is_a_span_not_a_set_of_timestamps(driven_report: dict) -> None:
    """The reader needs the width, not the hour a governed read happened.

    This report is served on the unauthenticated observability manifest, which
    withholds the per-request feed for exactly that reason.
    """
    serialized = json.dumps(driven_report, ensure_ascii=False)
    assert "timestamp" not in serialized
    # No ISO-8601 date anywhere: a span carries no calendar date, a stamp does.
    assert not re.search(r"\d{4}-\d{2}-\d{2}", serialized), serialized[:400]
    for row in driven_report["surfaces"]:
        assert "oldest_observation" not in row
        assert "newest_observation" not in row


def test_an_unusable_timestamp_leaves_the_span_unreported_not_raising() -> None:
    """A stamp that is absent, non-string or unparseable must not 500 a read."""
    observability.reset_request_observability()
    for stamp in (None, 12345, "not-a-timestamp", "2026-13-45T99:99:99"):
        observability.record_request_observation(
            {
                "timestamp": stamp,
                "method": "POST",
                "route": "/ontology/resolve",
                "status_code": 200,
                "latency_ms": 1.0,
            },
            export=False,
        )
    row = next(
        item
        for item in latency_budget_report()["surfaces"]
        if item["requirement_id"] == "NFR-PERF-006"
    )
    assert row["sample_size"] == 4, row
    # The latencies still count; only the span is unavailable.
    assert row["sample_window_seconds"] is None, row


def test_a_mix_of_aware_and_naive_stamps_does_not_raise() -> None:
    """Subtracting an aware from a naive datetime raises; a read may not."""
    observability.reset_request_observability()
    for stamp in (
        "2026-10-01T00:00:00+00:00",
        "2026-10-01T00:00:10+00:00",
        "2026-10-01T00:00:20",
        "2026-10-01T00:00:40",
        "2026-10-01T00:00:50",
    ):
        observability.record_request_observation(
            {
                "timestamp": stamp,
                "method": "POST",
                "route": "/ontology/resolve",
                "status_code": 200,
                "latency_ms": 1.0,
            },
            export=False,
        )
    row = next(
        item
        for item in latency_budget_report()["surfaces"]
        if item["requirement_id"] == "NFR-PERF-006"
    )
    assert row["sample_size"] == 5, row
    # Three naive stamps outnumber two aware ones, so the naive set is measured:
    # 00:00:20 .. 00:00:50 is 30 seconds.
    assert row["sample_window_seconds"] == 30.0, row


def test_the_classification_cache_is_bounded_and_does_not_change_the_answer() -> None:
    """A ``{dataset_id}`` path is caller-supplied, so its cache must be bounded.

    One report classifies up to the buffer capacity of paths against every
    route, and ``prometheus_metrics_text`` reaches that through the
    observability manifest, so the work repeats on every scrape. Measured with
    a full buffer of 500 distinct paths, before and after the cache::

        GET /metrics                     37.0 ms -> 5.8 ms
        GET /enterprise/latency-budgets  73.6 ms -> 6.2 ms

    An unbounded map keyed on a caller-supplied path would be a way to grow
    process memory from outside, which is why the size is asserted here.
    """
    info = route_template_for.cache_info()
    assert info.maxsize is not None and info.maxsize > 0, (
        "the classification cache must be bounded"
    )
    # Correct through the cache, on both a hit and a miss, and for a template
    # and a non-route alike.
    for _ in range(2):
        assert (
            route_template_for("GET", "/browse/crm-event/schema")
            == "/browse/{dataset_id}/schema"
        )
        assert route_template_for("GET", "/no/such/path") is None
    # Many distinct caller-supplied ids may not grow it past its bound.
    for index in range(info.maxsize + 50):
        route_template_for("GET", f"/catalog/datasets/probe-{index}")
    assert route_template_for.cache_info().currsize <= info.maxsize


def test_nearest_rank_percentile_returns_an_observation_that_happened() -> None:
    """Hand-computed: nearest-rank p95 is the ceil(0.95*n)-th smallest value."""
    assert nearest_rank_percentile([5.0], 0.95) == 5.0
    assert nearest_rank_percentile([1.0, 2.0], 0.95) == 2.0
    # n=20 -> rank ceil(19) = 19, i.e. the 19th of 20 sorted values.
    twenty = [float(value) for value in range(1, 21)]
    assert nearest_rank_percentile(twenty, 0.95) == 19.0
    # Order of the input must not matter.
    assert nearest_rank_percentile(list(reversed(twenty)), 0.95) == 19.0
    # The result is always a member of the input, never an interpolation.
    assert nearest_rank_percentile([1.0, 100.0], 0.95) in {1.0, 100.0}


def test_the_report_states_what_it_measured_and_what_it_cannot(
    driven_report: dict,
) -> None:
    """The one-sided limitation is published, not left to be inferred."""
    assert driven_report["budget_confirmation_possible"] is False
    assert "lower bound" in driven_report["measurement_basis"]
    assert "only an over-budget result is conclusive" in (
        driven_report["confirmation_limitation"]
    )
    assert driven_report["percentile"] == 0.95
    assert driven_report["percentile_method"] == "nearest_rank_inclusive"
    assert driven_report["minimum_sample"] == MIN_SAMPLE_FOR_PERCENTILE
    assert driven_report["counted_status_range"] == [200, 299]
    # The window is bounded; a reader cannot judge a p95 without knowing it.
    assert driven_report["observation_window"]["buffer_capacity"] > 0
    assert (
        driven_report["observation_window"]["observations_available"]
        <= driven_report["observation_window"]["buffer_capacity"]
    )
    # No surface claims to be within budget - that field does not exist.
    for row in driven_report["surfaces"]:
        assert "within_budget" not in row


def test_the_report_stays_inside_the_manifests_disclosure_boundary(
    driven_report: dict,
) -> None:
    """Route *templates* only: the per-request feed is withheld for this reason.

    ``build_observability_manifest`` deliberately does not publish observations,
    because each carries the caller's actor and tenant and a route that embeds
    the dataset id. This report is published on that same unauthenticated
    manifest, so it must carry none of those.
    """
    serialized = json.dumps(driven_report, ensure_ascii=False)
    for leaked in (
        "crm-customer-master",
        "crm-event",
        "analyst",
        "X-SDP-Tenant",
        "request_id",
    ):
        assert leaked not in serialized, f"{leaked!r} reached the latency report"
    for row in driven_report["surfaces"]:
        for route in row["routes"]:
            assert "crm" not in route


def test_the_manifest_and_the_dedicated_route_publish_the_same_contract() -> None:
    """One report, two read surfaces; their shape may not drift apart."""
    observability.reset_request_observability()
    _drive_every_budgeted_surface()
    standalone = client.get("/enterprise/latency-budgets")
    assert standalone.status_code == 200
    embedded = client.get("/enterprise/observability").json()["latency_budgets"]
    assert set(standalone.json()) == set(embedded)
    assert [row["requirement_id"] for row in standalone.json()["surfaces"]] == [
        row["requirement_id"] for row in embedded["surfaces"]
    ]
