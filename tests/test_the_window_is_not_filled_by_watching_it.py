"""The surfaces that publish the observation ring are not recorded into it.

Measured before this contract: a fresh ring held 1 row after one
``GET /enterprise/observability`` and 2 after one further ``GET /metrics``. With
60 authorised schema reads followed by 500 scrapes of ``/metrics`` - an ordinary
ten-second dashboard poll for about eighty minutes - the window held 498 scrape
rows and 2 manifest rows, none of the governed traffic, and
``latency_budgets`` for ``schema_browsing`` fell from a real
``observed_p95_ms: 2.721`` to ``insufficient_sample``.

That is the product's only in-process evidence for the six NFR-PERF budgets, and
``budget_confirmation_possible: false`` already says an in-process p95 cannot
confirm a production budget - only refute it. Destroying the sample removes even
the refutation. So the operator who looked most often could see least, which
inverts what a dashboard is for.

The exclusion narrows ``request_observations_total`` from "requests served" to
"product requests served". Silently narrowing a published number's meaning is
the defect class this product refuses, so the narrowing is published next to the
count rather than left for a reader to infer from traffic that never appears.
"""

from __future__ import annotations

from collections import Counter

from fastapi.testclient import TestClient

from sdp import observability as obs
from sdp.api import app


client = TestClient(app)

_GOVERNED = {"user": "analyst", "purpose": "analysis"}
_DATASET = "crm-customer-master"


def _window_routes() -> Counter[str]:
    """How the ring's rows break down by route."""
    return Counter(
        str(row.get("route") or "?")
        for row in obs.list_request_observations(limit=obs.observation_buffer_capacity())
    )


def test_watching_the_manifest_does_not_put_rows_in_the_window() -> None:
    """One read of each publishing surface leaves the ring empty."""
    obs.reset_request_observability()
    assert client.get("/enterprise/observability").status_code == 200
    assert client.get("/metrics").status_code == 200
    assert _window_routes() == Counter()


def test_a_scrape_storm_does_not_destroy_a_governed_measurement() -> None:
    """The headline behaviour: polling the dashboard preserves the evidence.

    Before the exclusion this same sequence took ``schema_browsing`` from a
    measured p95 to ``insufficient_sample``.
    """
    obs.reset_request_observability()
    for _ in range(60):
        assert client.get(f"/browse/{_DATASET}/schema", params=_GOVERNED).status_code == 200

    def schema_surface() -> dict[str, object]:
        budgets = client.get("/enterprise/observability").json()["latency_budgets"]
        return next(
            surface
            for surface in budgets["surfaces"]
            if surface["surface"] == "schema_browsing"
        )

    before = schema_surface()
    assert before["sample_size"] == 60
    assert before["evaluated"] is True
    assert before["measurement_status"] == "measured_in_process"

    for _ in range(120):
        assert client.get("/metrics").status_code == 200

    after = schema_surface()
    assert after["sample_size"] == 60, after
    assert after["evaluated"] is True
    assert after["observed_p95_ms"] == before["observed_p95_ms"]
    assert _window_routes() == Counter({f"/browse/{_DATASET}/schema": 60})


def test_the_manifest_declares_which_routes_it_leaves_out() -> None:
    """The narrowing is published, so the count's meaning is readable."""
    metrics = client.get("/enterprise/observability").json()["metrics"]
    assert metrics["request_observations_excluded_routes"] == [
        "GET /enterprise/observability",
        "GET /metrics",
    ]


def test_a_request_that_matches_no_route_is_still_observed() -> None:
    """A 404 has no matched template, and that is not an exclusion.

    ``route_is_monitoring`` is asked about every request, so the no-template
    case has to answer ``False`` rather than raise or silently exclude.
    """
    assert obs.route_is_monitoring("GET", None) is False
    obs.reset_request_observability()
    assert client.get("/no-such-route-at-all").status_code == 404
    assert sum(_window_routes().values()) == 1


def test_excluding_the_observation_does_not_drop_the_correlation_header() -> None:
    """Only the ring append is skipped - the rest of the middleware still runs."""
    response = client.get("/metrics")
    assert response.status_code == 200
    assert obs.request_id_header() in response.headers
