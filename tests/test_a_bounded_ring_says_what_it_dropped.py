"""Three published counters were a bounded ring's ``len()`` with no disclosure.

``/enterprise/observability`` publishes five quantities in one ``metrics`` block.
Two of them already carried the honest-count treatment this branch built -
``audit_events_observed_total`` beside ``audit_events_observed_total_is_lower_bound``,
``audit_events_withheld_total`` and ``withheld_count_scope``. Three did not, and
each was the length of a bounded ``deque``::

    _REQUEST_OBSERVATIONS   maxlen=500  -> metrics.request_observations_total
    _EXPORT_ERRORS          maxlen=50   -> metrics.observability_export_errors_total
    _ALERT_ERRORS           maxlen=50   -> alert_delivery.retained_failures

So a reader of one block got an exact count for two quantities and a saturating
length for three, with nothing in the payload to tell them apart. Measured before
the repair, driving the alert ring past its cap::

    60 governed requests, raising rule
      -> evaluation_failures 60, retained_failures 50
      -> ten rows dropped, and the block carried no flag, no withheld count and
         no published cap. The only published cap anywhere in the payload was
         ``latency_budgets.observation_window.buffer_capacity``.

This was **not** a new discovery. ``README.md`` and
``docs/product-technical-gap-baseline.md`` both name all three and state that the
round which found them did not close it. What this file guards is the closing.
"""

from __future__ import annotations

from pathlib import Path
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sdp import observability  # noqa: E402
from sdp.api import app  # noqa: E402

client = TestClient(app, raise_server_exceptions=False)

# Each bounded ring, how to append one row to it, and the three names its
# disclosure is published under. Parametrized rather than one test per ring:
# three hand-written copies of one tally is the shape that put this repository
# in the position of publishing three undisclosed counters in the first place.
RINGS = [
    (
        "request_observations",
        "_REQUEST_OBSERVATIONS",
        lambda i: observability.record_request_observation({"i": i}, export=False),
        ("request_observations_total", "request_observations_cap",
         "request_observations_withheld_total",
         "request_observations_total_is_lower_bound"),
    ),
    (
        "export_errors",
        "_EXPORT_ERRORS",
        lambda i: observability.record_observability_export_error(f"probe-{i}"),
        ("observability_export_errors_total", "observability_export_errors_cap",
         "observability_export_errors_withheld_total",
         "observability_export_errors_total_is_lower_bound"),
    ),
    (
        "alert_errors",
        "_ALERT_ERRORS",
        lambda i: observability.record_alert_routing_error(
            "probe_rule", "evaluation", f"Probe{i}"
        ),
        ("retained_failures", "retained_failures_cap",
         "retained_failures_withheld_total", "retained_failures_is_lower_bound"),
    ),
]
RING_IDS = [ring[0] for ring in RINGS]


def _empty(ring_name: str) -> None:
    """Empty one ring and its drop count before driving it.

    Measured: without this, two of these tests failed by exactly one row in the
    full suite while passing when the file ran alone. ``_REQUEST_OBSERVATIONS``
    is fed by the request middleware, so every ``TestClient`` call anywhere in
    the suite - including this file's own publication test - puts a row in it.
    A test that assumes a clean bounded ring is measuring the suite's traffic,
    not its own.
    """
    if ring_name == "alert_errors":
        observability.reset_alert_routing()
    else:
        observability.reset_request_observability()


@pytest.mark.parametrize("ring", RINGS, ids=RING_IDS)
def test_every_bounded_ring_publishes_its_cap_and_its_loss(ring) -> None:
    """The names must exist on the payload, or the disclosure is not published."""
    name, attr, _append, published = ring
    body = client.get("/enterprise/observability").json()
    flat = {**body["metrics"], **body["alert_delivery"]}
    missing = [key for key in published if key not in flat]
    assert not missing, f"{name} does not publish: {missing}"
    assert flat[published[1]] == getattr(observability, attr).maxlen


@pytest.mark.parametrize("ring", RINGS, ids=RING_IDS)
def test_a_ring_past_its_cap_publishes_the_rows_it_dropped(ring) -> None:
    """visible saturates, withheld counts the drops, and the flag follows withheld."""
    name, attr, append, _published = ring
    _empty(name)
    container = getattr(observability, attr)
    cap = container.maxlen
    assert cap, f"{name} is not bounded, so this guard does not apply to it"
    for index in range(cap + 7):
        append(index)
    counted = observability._counted_ring(container, name)
    assert counted.visible_count == cap
    assert counted.withheld_count == 7, (name, counted)
    assert counted.is_lower_bound is True


@pytest.mark.parametrize("ring", RINGS, ids=RING_IDS)
def test_an_exactly_full_ring_claims_no_loss(ring) -> None:
    """The boundary that defeated an earlier draft of this idiom.

    Deriving the flag from ``len(ring) == ring.maxlen`` publishes
    ``is_lower_bound: true`` beside ``withheld: 0`` at exactly ``maxlen``
    appends - a ring that is exactly full has lost nothing. That artefact was
    measured and withdrawn once already in this branch, so the flag is derived
    from the drop count instead, and this is what pins that.
    """
    name, attr, append, _published = ring
    _empty(name)
    container = getattr(observability, attr)
    cap = container.maxlen
    for index in range(cap):
        append(index)
    counted = observability._counted_ring(container, name)
    assert counted.visible_count == cap
    assert counted.withheld_count == 0, (name, counted)
    assert counted.is_lower_bound is False


@pytest.mark.parametrize("ring", RINGS, ids=RING_IDS)
def test_reading_the_drop_count_does_not_change_it(ring) -> None:
    """A counter that moves when read is what a sibling repair shipped once.

    An earlier version of a loss counter in this branch used
    ``itertools.count``, so every read advanced it and the published loss grew
    on an unchanged ring (measured 149 -> 153).
    """
    name, _attr, append, _published = ring
    for index in range(3):
        append(index)
    assert [observability.ring_withheld_count(name) for _ in range(5)] == [0] * 5


def test_the_drop_count_and_the_visible_count_come_from_one_sample() -> None:
    """Two separately sampled names disagreed by 13,850 rows in one payload once.

    ``_counted_ring`` reads the ring's length and its drop count inside one
    critical section, so the pair a reader sees was true at one instant. This
    checks the pair is internally consistent for a ring driven past its cap:
    visible + withheld must equal what was appended.
    """
    observability.reset_alert_routing()
    appended = (observability._ALERT_ERRORS.maxlen or 0) + 23
    for index in range(appended):
        observability.record_alert_routing_error("probe_rule", "delivery", f"P{index}")
    counted = observability._counted_ring(observability._ALERT_ERRORS, "alert_errors")
    assert counted.visible_count + (counted.withheld_count or 0) == appended


def _overflow(ring_name: str, attr: str, append) -> None:
    """Drive one ring past whatever its cap currently is.

    Derived from the deque rather than written as a literal. The first version of
    this file drove 60 / 505 / 53 appends against caps of 50 / 500 / 50, and a
    legitimate-repair mutation - raising ``MAX_RETAINED_ALERT_ERRORS`` from 50 to
    80, and the observation ring from 500 to 900 - turned the reset test red on
    both. That is the pinned-magnitude trap this branch recorded in round 22 and
    wrote a rule about in round 25, repeated here one round later and caught by
    the rule's own probe rather than by review.
    """
    cap = getattr(observability, attr).maxlen
    assert cap, ring_name
    for index in range(cap + 3):
        append(index)
    assert observability.ring_withheld_count(ring_name) > 0, ring_name


def test_a_reset_that_empties_a_ring_also_zeroes_its_drop_count() -> None:
    """Otherwise a fresh episode publishes a loss that belongs to the last one.

    This is the sibling of a defect already recorded in this branch: a restart
    republished a permanent store-path loss as though it were current.
    """
    alert = next(r for r in RINGS if r[0] == "alert_errors")
    _overflow(alert[0], alert[1], alert[2])
    observability.reset_alert_routing()
    assert observability.ring_withheld_count("alert_errors") == 0
    counted = observability._counted_ring(observability._ALERT_ERRORS, "alert_errors")
    assert counted.is_lower_bound is False

    for ring_name, attr, append, _published in RINGS:
        if ring_name == "alert_errors":
            continue
        _overflow(ring_name, attr, append)
    observability.reset_request_observability()
    for ring_name, _attr, _append, _published in RINGS:
        if ring_name == "alert_errors":
            continue
        assert observability.ring_withheld_count(ring_name) == 0, ring_name


def test_the_disclosed_rings_are_every_bounded_ring_this_module_declares() -> None:
    """Mechanical, so a fourth bounded ring cannot be added undisclosed.

    The existing records named one of these three, then two, then three - the
    count grew twice because each pass enumerated by hand. This enumerates from
    the module.
    """
    declared = {
        name
        for name in dir(observability)
        if name.startswith("_")
        and getattr(getattr(observability, name, None), "maxlen", None)
    }
    covered = {attr for _name, attr, _append, _published in RINGS}
    assert declared == covered, (
        f"bounded rings with no disclosure guard: {sorted(declared - covered)}; "
        f"guarded names that are no longer bounded rings: {sorted(covered - declared)}"
    )
