"""The PRD's six latency budgets, and what this service can honestly say about them.

``docs/prd-trd.md`` declares a p95 budget per surface::

    NFR-PERF-001 | catalog keyword search latency     | p95 2초 이하
    NFR-PERF-002 | dataset detail API latency         | p95 1.5초 이하
    NFR-PERF-003 | schema browsing latency            | p95 3초 이하
    NFR-PERF-004 | preview latency                    | p95 10초 이하
    NFR-PERF-005 | LLM catalog answer latency         | p95 15초 이하
    NFR-PERF-006 | ontology term resolution latency   | p95 500ms 이하

Nothing in this repository related to any of them. The middleware has recorded
``latency_ms`` per request all along and ``/enterprise/observability`` published
it, but no code named a budget, so the six declared targets had nothing to
compare against - a target nothing compares to is not a gate. CAT-001's
acceptance criterion names the same 2-second figure, and the only latency number
this repository records runs *against* it (``catalog.py`` measures 5.10s for a
2000-token query over 1005 datasets, which is why the query length is bounded).

**What this measurement can and cannot establish.** The observations come from
this process: in-memory stores, synthetic seed data, one worker, no network
between client and app. A production deployment adds a database, a real dataset
population, concurrency and network hops - every one of which makes requests
slower, never faster. So an in-process p95 is a *lower bound* on the production
p95, and the test is one-sided:

* in-process p95 **above** the budget refutes the budget - if it is already over
  budget here, it is over budget in production;
* in-process p95 **below** the budget establishes nothing about production.

That asymmetry is published as ``budget_refuted`` rather than
``within_budget``, and ``budget_confirmation_possible`` is ``False`` with the
reason attached. A field named ``within_budget: true`` would be read as "the SLO
is met", which this measurement cannot support in the direction that matters.

A p95 over a handful of requests is the sample maximum wearing a percentile's
name, so a surface under ``MIN_SAMPLE_FOR_PERCENTILE`` observations reports
``insufficient_sample`` and refutes nothing. Fail-closed here means a thin
sample may never produce a verdict - in either direction.

Each surface also publishes ``sample_window_seconds``: the observation buffer is
one ring across *all* routes, so a busy surface evicts a quiet one's rows, and a
p95 over twenty requests spread across days would otherwise sit next to a p95
over twenty requests from the last minute looking like the same kind of number.
The span is given in seconds rather than as timestamps, because a reader needs
the width of the window and not the hour at which someone read a governed
dataset - which is what the unauthenticated manifest withholds the per-request
feed to avoid saying.
"""

from __future__ import annotations

import functools
import math
from datetime import datetime
from typing import Any

from .observability import list_request_observations, observation_buffer_capacity

# Nearest-rank p95 of a short series is just its maximum under another name. The
# threshold is the sample size at which the 95th percentile has at least one
# observation above it (ceil(0.95 * n) < n first holds at n = 20), so the number
# reported is a percentile of the sample rather than its extreme value.
MIN_SAMPLE_FOR_PERCENTILE = 20

PERCENTILE_METHOD = "nearest_rank_inclusive"

# Only successful responses count toward a surface's latency. A refusal is not a
# search: 403s and 404s return before the work the budget is about, so counting
# them would pull every p95 down by exactly the requests that did the least.
# Published, because "which requests were measured" changes what the number
# means.
COUNTED_STATUS_RANGE = (200, 299)

MEASUREMENT_BASIS = (
    "in-process observations of requests this worker actually served "
    "(in-memory stores, seed data, one worker, no client-to-app network); "
    "a lower bound on production latency, not a load test"
)

CONFIRMATION_LIMITATION = (
    "A production deployment adds a database, a real dataset population, "
    "concurrency and network hops, each of which can only increase latency. "
    "An in-process p95 under budget therefore does not establish that the "
    "deployed p95 is under budget; only an over-budget result is conclusive."
)


class LatencyBudget:
    """One PRD latency budget, bound to the routes it governs."""

    def __init__(
        self,
        *,
        requirement_id: str,
        surface: str,
        budget_ms: float,
        routes: tuple[tuple[str, str], ...],
    ) -> None:
        """Bind a requirement id and budget to ``(method, route template)`` pairs."""
        self.requirement_id = requirement_id
        self.surface = surface
        self.budget_ms = budget_ms
        self.routes = routes


# Route *templates*, not concrete paths: a template carries no dataset id, so the
# report stays publishable on the unauthenticated manifest, which deliberately
# withholds the per-request feed for exactly that reason. The templates are
# checked against the running app by
# tests/test_latency_budget_measurement.py, so renaming a route breaks the
# suite instead of quietly measuring nothing.
LATENCY_BUDGETS: tuple[LatencyBudget, ...] = (
    LatencyBudget(
        requirement_id="NFR-PERF-001",
        surface="catalog_keyword_search",
        budget_ms=2000.0,
        routes=(("GET", "/catalog/search"),),
    ),
    LatencyBudget(
        requirement_id="NFR-PERF-002",
        surface="dataset_detail",
        budget_ms=1500.0,
        routes=(("GET", "/catalog/datasets/{dataset_id}"),),
    ),
    LatencyBudget(
        requirement_id="NFR-PERF-003",
        surface="schema_browsing",
        budget_ms=3000.0,
        routes=(("GET", "/browse/{dataset_id}/schema"),),
    ),
    LatencyBudget(
        requirement_id="NFR-PERF-004",
        surface="sample_preview",
        budget_ms=10000.0,
        routes=(("POST", "/browse/{dataset_id}/preview"),),
    ),
    LatencyBudget(
        requirement_id="NFR-PERF-005",
        surface="llm_catalog_answer",
        budget_ms=15000.0,
        # Both LLM-facing surfaces: the question-to-datasets answer and the
        # draft it produces. Either one is "the LLM catalog answer" a user waits
        # on, so both are held to the same budget.
        routes=(("POST", "/llm/search"), ("POST", "/llm/draft-query")),
    ),
    LatencyBudget(
        requirement_id="NFR-PERF-006",
        surface="ontology_term_resolution",
        budget_ms=500.0,
        routes=(("POST", "/ontology/resolve"),),
    ),
)


def budgeted_route_templates() -> set[tuple[str, str]]:
    """Every ``(method, route template)`` pair some budget governs."""
    return {pair for budget in LATENCY_BUDGETS for pair in budget.routes}


# One report classifies up to ``observation_buffer_capacity()`` paths, each
# against every route, and ``prometheus_metrics_text`` reaches this through the
# observability manifest - so a scrape paid for 500 x ~60 pattern matches.
# Measured with a full buffer of distinct paths before this cache:
#
#     GET /metrics                     37.0 ms/request
#     GET /enterprise/observability    42.7 ms/request
#     GET /enterprise/latency-budgets  73.6 ms/request
#
# Real traffic repeats a small set of paths, so memoising collapses almost all
# of it. The cache is bounded, like every other retained collection here: a
# ``{dataset_id}`` path is caller-supplied, so an unbounded map keyed on it is a
# way to grow process memory from outside. The route table is fixed at import -
# nothing registers a route later - so a cached classification cannot go stale.
@functools.lru_cache(maxsize=4096)
def route_template_for(method: str, path: str) -> str | None:
    """The route template this concrete path routes to, or ``None``.

    Matched with Starlette's own compiled pattern rather than a parser written
    here, so the classification cannot disagree with the dispatch that produced
    the observation. ``request.url.path`` is what the middleware records, and it
    carries the dataset id - the template is what may be published.
    """
    from .api import app

    for route in app.routes:
        pattern = getattr(route, "path_regex", None)
        if pattern is None:
            continue
        if method.upper() not in (getattr(route, "methods", None) or set()):
            continue
        if pattern.fullmatch(path):
            return str(route.path)
    return None


def nearest_rank_percentile(values: list[float], percentile: float) -> float:
    """The nearest-rank percentile of ``values`` (which must be non-empty).

    Nearest-rank is used rather than interpolation because it returns an
    observation that actually happened; an interpolated p95 is a number no
    request produced, which is the wrong kind of figure to publish next to a
    budget.
    """
    ordered = sorted(values)
    rank = max(1, math.ceil(percentile * len(ordered)))
    return ordered[min(rank, len(ordered)) - 1]


def _observation_moment(observation: dict[str, Any]) -> datetime | None:
    """The observation's own timestamp, or ``None`` when it is unusable.

    ``build_request_observation`` always stamps one, but an observation can also
    be recorded directly (tests do, and so could a future caller), so an absent
    or unparseable stamp must not raise inside a published read.
    """
    stamp = observation.get("timestamp")
    if not isinstance(stamp, str):
        return None
    try:
        return datetime.fromisoformat(stamp)
    except ValueError:
        return None


def _counted_sample(
    budget: LatencyBudget, observations: list[dict[str, Any]]
) -> tuple[list[float], float | None]:
    """Latencies for this budget, and the span of wall-clock time they cover.

    The span is what a reader needs and could not otherwise have. The buffer is
    one ring across *all* routes, so a busy surface evicts a quiet one's
    observations: a surface with exactly its minimum sample may be reporting a
    p95 over twenty requests spread across days, which sits next to a busy
    surface's p95 over twenty requests from the last minute and reads as the
    same kind of number. It is not.

    The span is published in seconds rather than as timestamps on purpose. A
    reader needs to know the window is 40 seconds or six days; they do not need
    to know *when* a governed read happened, and this report is served on the
    unauthenticated manifest, which withholds the per-request feed precisely to
    avoid saying that.
    """
    governed = set(budget.routes)
    latencies: list[float] = []
    moments: list[datetime] = []
    low, high = COUNTED_STATUS_RANGE
    for observation in observations:
        status = observation.get("status_code")
        if not isinstance(status, int) or not low <= status <= high:
            continue
        method = str(observation.get("method", ""))
        path = str(observation.get("route", ""))
        template = route_template_for(method, path)
        if template is None:
            continue
        if (method.upper(), template) not in governed:
            continue
        latency = observation.get("latency_ms")
        if isinstance(latency, bool) or not isinstance(latency, (int, float)):
            continue
        if not math.isfinite(float(latency)):
            continue
        latencies.append(float(latency))
        moment = _observation_moment(observation)
        if moment is not None:
            moments.append(moment)

    span: float | None = None
    if len(moments) >= 2:
        # Only comparable moments: a mix of aware and naive stamps would raise
        # on subtraction, and this runs inside a published read.
        aware = [moment for moment in moments if moment.tzinfo is not None]
        naive = [moment for moment in moments if moment.tzinfo is None]
        comparable = aware if len(aware) >= len(naive) else naive
        if len(comparable) >= 2:
            span = round(
                (max(comparable) - min(comparable)).total_seconds(), 3
            )
    return latencies, span


def latency_budget_report() -> dict[str, Any]:
    """Compare each declared budget to what this process actually observed."""
    observations = list_request_observations(limit=observation_buffer_capacity())
    surfaces: list[dict[str, Any]] = []
    for budget in LATENCY_BUDGETS:
        latencies, span_seconds = _counted_sample(budget, observations)
        row: dict[str, Any] = {
            "requirement_id": budget.requirement_id,
            "surface": budget.surface,
            "routes": [f"{method} {template}" for method, template in budget.routes],
            "budget_ms": budget.budget_ms,
            "sample_size": len(latencies),
            # How much wall-clock time this surface's sample covers. The ring
            # buffer is shared across routes, so a quiet surface's p95 can be
            # over a window orders of magnitude longer than a busy one's.
            "sample_window_seconds": span_seconds,
        }
        if len(latencies) < MIN_SAMPLE_FOR_PERCENTILE:
            row.update(
                {
                    "evaluated": False,
                    "measurement_status": "insufficient_sample",
                    "observed_p95_ms": None,
                    "budget_refuted": None,
                    "minimum_sample": MIN_SAMPLE_FOR_PERCENTILE,
                }
            )
        else:
            observed = round(nearest_rank_percentile(latencies, 0.95), 3)
            row.update(
                {
                    "evaluated": True,
                    "measurement_status": "measured_in_process",
                    "observed_p95_ms": observed,
                    "budget_refuted": observed > budget.budget_ms,
                    "minimum_sample": MIN_SAMPLE_FOR_PERCENTILE,
                }
            )
        surfaces.append(row)

    refuted = [row["requirement_id"] for row in surfaces if row["budget_refuted"]]
    evaluated = [row for row in surfaces if row["evaluated"]]
    return {
        "budget_count": len(LATENCY_BUDGETS),
        "evaluated_count": len(evaluated),
        "unevaluated_count": len(surfaces) - len(evaluated),
        "refuted_requirement_ids": refuted,
        "percentile": 0.95,
        "percentile_method": PERCENTILE_METHOD,
        "minimum_sample": MIN_SAMPLE_FOR_PERCENTILE,
        "counted_status_range": list(COUNTED_STATUS_RANGE),
        "observation_window": {
            "buffer_capacity": observation_buffer_capacity(),
            "observations_available": len(observations),
        },
        "measurement_basis": MEASUREMENT_BASIS,
        # The one-sided direction, published as a field so a reader does not have
        # to infer it from the absence of a "within_budget" claim.
        "budget_confirmation_possible": False,
        "confirmation_limitation": CONFIRMATION_LIMITATION,
        "surfaces": surfaces,
    }
