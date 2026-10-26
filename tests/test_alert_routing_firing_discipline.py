"""Alert routing's firing discipline: one POST per episode, never per increment.

These tests were written against the parent head, where nothing delivered.
``src/sdp_core/production.py``'s ``request_observability_export`` entry listed
``SDP_ALERT_WEBHOOK_URL`` in ``declared_unimplemented_environment``, and measured
there, the only read of the variable anywhere in ``src/`` was one ``bool()`` for
a published field::

    $ grep -rn SDP_ALERT_WEBHOOK_URL src/ | wc -l
    4
    src/sdp/observability.py:392  alert_webhook_url = os.getenv("SDP_ALERT_WEBHOOK_URL", "").strip()
    (the other three were comments and the production.py declaration)

So the question these tests answer is not "does delivery work" but "how often
does it happen", and it had to be settled **before** the first POST existed,
because the increment site makes a naive answer catastrophic. The
``policy_audit_gap`` counter is incremented from ``sdp.api``'s observability
middleware, once per governed 2xx that recorded no evidence - a per-request
event on an unauthenticated surface. Measured on this head, 25 anonymous
requests to::

    GET /enterprise/connectors/rest_connector/probe
        ?dataset_id=marketing-campaign&user=analyst

answered ``200`` 25 times with ``status: contract_only`` 25 times in **197.1 ms**
with no credential of any kind. A "POST on every increment" rule turns that loop
into 25 outbound POSTs at the operator's webhook per 200 ms of anonymous
traffic, from one connection.

THE RULE PINNED HERE. One POST per transition of a rule from not-firing into
firing, per worker, and nothing on the 2nd..Nth increment while it is already
firing. Re-arm is tied to the rule's own ``firing`` flag going back to false, not
to a timer: ``governed_evidence_gap_report()["firing"]`` is ``observed_total > 0``
over a counter with no decay path in ``src/`` - ``reset_request_observability()``
is the only thing that zeroes it - so in a deployed worker a rule that has fired
once stays firing for the worker's lifetime. A minimum-interval rule would
therefore re-post forever on a condition that can never clear, which is the
flood this file exists to refuse; and "first transition only, never re-arm" would
make a genuinely new episode after a reset silent. The consequence is a number
rather than a hope: between resets, total alert POSTs are bounded by the count of
routable rules - ``len(ROUTABLE_ALERT_RULE_IDS)``, which is 2 - no matter how
large the burst.

HOW THESE TESTS AVOID MEASURING NOTHING. Two distinct traps.

*Fire-and-forget.* Every test in this repository drives the app with
``TestClient``, so a POST scheduled beyond the request that triggered it is
unobservable here. Measured on this head against a reference routing
implementation, with the module-level ``TestClient`` these tests use - no
``with`` block, so each request gets its own portal - delivery written three
ways::

    implementation                              posts seen when the test asserts
                                                 1 request        25 requests
    synchronous at the evaluation site            1                1
    create_task(coroutine that posts)             1                1
    create_task(coroutine that awaits first -
        a backoff pause, a to_thread hop)         0 CancelledError 0 CancelledError

The third shape is cancelled at portal teardown and never posts at all, so a
delivery test written against it reads 0 and a non-delivery test passes for the
wrong reason. Both the single-request test and the 25-request burst test below
assert ``== 1`` and fail on it (measured: both do). The rule is only pinnable if
delivery is synchronous at the evaluation site or awaited off the loop the way
``record_request_observation_async`` already awaits the log export.

*Vacuous non-delivery.* "The read path posts nothing" is satisfied today by a
product that posts nothing anywhere. Every non-delivery test below therefore
proves the counting seam is **live in the same test** - it drives one real
transition and asserts the POST arrived - before asserting that the read path
adds none. That is also what keeps them meaningful after the feature lands.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from sdp import api, observability as obs
from sdp.api import app


client = TestClient(app, raise_server_exceptions=False)

WEBHOOK = "https://alerts.example.net/hooks/sdp"

# The names this family needs in order to count anything. Collected into one
# list so the RED failure names the whole missing capability instead of dying on
# whichever attribute the test happened to touch first.
REQUIRED_ROUTING_NAMES = (
    "alert_urlopen",
    "alert_routing_state",
    "reset_alert_routing",
    "ROUTABLE_ALERT_RULE_IDS",
)


def _alert_seam(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Install a counting double over alert routing's own ``urlopen`` seam.

    Returns the list every attempted alert POST is appended to, so a test
    counts deliveries rather than inspecting them.

    The seam is deliberately **not** ``obs.urlopen``: that name is the log
    sink's, and ``tests/test_observability.py`` and
    ``tests/test_honest_metrics.py`` already assert on what the log sink sent
    through it. A shared name would make a webhook POST indistinguishable from a
    log export in those tests' ``sent[-1]``.
    """
    missing = [name for name in REQUIRED_ROUTING_NAMES if not hasattr(obs, name)]
    assert not missing, (
        "alert routing is gone, so there is nothing to count: "
        f"sdp.observability is missing {missing}. On the parent head these names "
        "were all absent and the variable was read once, for bool()."
    )
    posts: list[dict[str, Any]] = []

    def _capture(request, timeout=None):
        """Record one attempted alert POST and answer like a healthy webhook."""
        posts.append(
            {
                "url": request.full_url,
                "method": request.get_method(),
                "headers": dict(request.headers),
                "body": request.data,
                "timeout": timeout,
            }
        )
        return _AcceptingResponse()

    monkeypatch.setattr(obs, "alert_urlopen", _capture)
    return posts


class _AcceptingResponse:
    """A context-manager stand-in for a webhook that accepts the POST."""

    def __enter__(self) -> "_AcceptingResponse":
        """Enter the ``with urlopen(...)`` block the export path uses."""
        return self

    def __exit__(self, *exc_info) -> bool:
        """Leave it without suppressing anything."""
        return False

    def read(self) -> bytes:
        """Answer an empty body, as an accepting webhook may."""
        return b""


def _configured_alert_seam(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """An operator-configured webhook plus the counting seam over it.

    Both halves are needed together: routing must be a no-op when the operator
    configured nothing (pinned separately by
    ``test_nothing_is_posted_when_the_operator_configured_no_webhook``), so a
    delivery test that forgets the variable measures the unconfigured path.

    Called from each test body rather than installed as a fixture so the missing
    capability is reported as a failing test rather than a fixture error, and so
    each test's own measurement is the thing that fails.
    """
    monkeypatch.setenv("SDP_ALERT_WEBHOOK_URL", WEBHOOK)
    return _alert_seam(monkeypatch)


def _disarm_the_latch() -> None:
    """Leave the rule firing and the latch clear, so a read-path send is possible.

    Reaching into module state, which is what makes these two tests
    measurements rather than restatements of the latch. Without this the
    read-path assertions pass against an implementation that routes from
    ``build_observability_manifest`` - measured, 23 passed - because the
    transition that proved the seam live had already latched the rule and the
    read-path call hit the suppressed branch.

    The product never reaches this state on its own: every increment routes, and
    routing latches whatever it finds firing. That is the point - the state has
    to be constructed for the call site to be observable at all, the same way
    ``tests/test_honest_metrics.py`` pokes ``_SINK_BREAKER["open_until"]`` to
    reach the breaker's cooldown edge.
    """
    obs._ALERT_ROUTING["latched"].clear()
    assert obs.alert_routing_state()["firing_rules"], (
        "the rule must still be firing after the latch is cleared, or a "
        "read-path send would be refused for the right reason by accident"
    )


def _drive_gap_increments(count: int) -> None:
    """Increment the ``policy_audit_gap`` counter ``count`` times, in process.

    This is the evaluation event itself - the function ``sdp.api``'s middleware
    calls - so a test can exercise the firing rule without an HTTP burst.
    """
    for index in range(count):
        obs.note_governed_request_without_evidence(f"GET /probe-{index:03d}")


def test_one_alert_post_per_transition_into_firing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """25 increments are one firing episode, so they are one POST.

    The defect this forecloses: the counter is incremented per request from the
    middleware, so "POST when the rule is firing" evaluated at the increment
    site sends one POST per request. Measured on this head, 25 anonymous probe
    requests complete in 197.1 ms, so the naive rule is 25 POSTs per 200 ms of
    uncredentialed traffic.
    """
    configured_webhook = _configured_alert_seam(monkeypatch)
    _drive_gap_increments(25)
    assert obs.governed_evidence_gap_report()["observed_total"] == 25
    assert obs.governed_evidence_gap_report()["firing"] is True
    assert len(configured_webhook) == 1, (
        "one firing episode must deliver one alert; "
        f"{len(configured_webhook)} POSTs were attempted for 25 increments"
    )
    state = obs.alert_routing_state()
    assert state["transitions_observed"] == 1
    assert state["deliveries_attempted"] == 1
    assert state["firing_rules"] == ["policy_audit_gap"]


def test_the_second_through_nth_increment_while_firing_are_suppressed_and_counted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """What happens to increments 2..N, stated rather than left implicit.

    They change the published count and send nothing, and the number suppressed
    is itself published - the same discipline ``sink_breaker_state`` already
    applies to ``skipped_exports``, so an operator seeing one alert for a
    thousand gap requests can tell suppression from a dropped POST.
    """
    configured_webhook = _configured_alert_seam(monkeypatch)
    _drive_gap_increments(1)
    assert len(configured_webhook) == 1, "the first increment is the transition"
    _drive_gap_increments(24)
    assert len(configured_webhook) == 1, (
        "increments after the transition must not re-post while the rule is "
        f"still firing; {len(configured_webhook)} POSTs were attempted"
    )
    state = obs.alert_routing_state()
    assert state["deliveries_attempted"] == 1
    assert state["suppressed_increments"] == 24
    assert obs.governed_evidence_gap_report()["observed_total"] == 25


def test_a_healthy_observation_is_not_counted_as_a_suppressed_increment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The suppression count has to be made of increments, not of traffic.

    Found by reverse-verification: passing ``observed_increment=True``
    unconditionally from ``note_connector_probe`` - so every probe counts as
    suppressed once the rule is firing - left the whole alert and probe suite
    **passing** (28 passed). The gap rule could not catch it, because every call
    to ``note_governed_request_without_evidence`` really is an increment; the
    probe rule is the one whose evaluation site is called by healthy traffic too,
    on every single probe.

    It matters because the number is published next to a single delivered alert.
    An operator reading "1 alert, 499 increments suppressed" should be able to
    conclude 500 governed failures happened; if healthy probes are in that total
    the figure is traffic volume wearing a failure's name, which is the
    "published number disagrees with the code enforcing it" shape in miniature.

    Driven with a mix, which is what the broken-proof-endpoint fixture cannot
    produce: ``audit_event`` is required by all four registry connectors, so
    breaking its proof endpoint fails every probe. Removing one connector's
    adapter instead fails exactly that connector and leaves the other three
    healthy - measured, ``sql_connector`` reports ``adapter_status: planned``
    and a non-empty reason while ``rdf_connector``, ``file_lake_connector`` and
    ``rest_connector`` all report ``""``.
    """
    from sdp import connectors as conn

    configured_webhook = _configured_alert_seam(monkeypatch)
    monkeypatch.delitem(conn._SOURCE_CONNECTORS, "sql_connector")

    conn.connector_probe("sql_connector", "crm-customer-master")
    assert len(configured_webhook) == 1, "the one build-owned failure is the transition"

    healthy = (
        ("rdf_connector", "semantic-glossary"),
        ("file_lake_connector", "crm-event"),
        ("rest_connector", "marketing-campaign"),
    )
    for _ in range(8):
        for connector_id, dataset_id in healthy:
            conn.connector_probe(connector_id, dataset_id)

    state = obs.alert_routing_state()
    assert state["deliveries_attempted"] == 1
    assert state["suppressed_increments"] == 0, (
        "24 probes that reported no failure were counted as suppressed alerts; "
        f"{state['suppressed_increments']} increments are published as having "
        "been held back when the condition never moved"
    )
    assert obs.connector_probe_failure_report()["observed_total"] == 1


def test_the_firing_latch_re_arms_only_when_the_rule_stops_firing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Re-arm is tied to the rule's own flag, not to a timer.

    ``governed_evidence_gap_report()["firing"]`` is ``observed_total > 0`` and
    nothing in ``src/`` decrements that counter, so in a deployed worker the
    only false->true->false->true sequence available is the one driven by
    ``reset_request_observability()``. A minimum-interval rule would re-post on
    a condition that never clears; "never re-arm" would make the episode after
    a reset silent. Both halves are asserted here, in order.
    """
    configured_webhook = _configured_alert_seam(monkeypatch)
    _drive_gap_increments(40)
    assert len(configured_webhook) == 1
    assert obs.alert_routing_state()["firing_rules"] == ["policy_audit_gap"]

    obs.reset_request_observability()
    assert obs.governed_evidence_gap_report()["firing"] is False
    assert obs.alert_routing_state()["firing_rules"] == [], (
        "the latch must follow the counter the rule reads; a latch left set "
        "across a reset silences the next genuine episode"
    )

    _drive_gap_increments(40)
    assert len(configured_webhook) == 2, (
        "a new firing episode after the rule stopped firing is a new alert; "
        f"{len(configured_webhook)} POSTs were attempted across two episodes"
    )
    assert obs.alert_routing_state()["deliveries_attempted"] == 1


def test_nothing_is_posted_when_the_operator_configured_no_webhook(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unset variable must make routing a no-op, not a failed POST.

    This is the test-suite guard as much as the deployment one. Measured on this
    head with a probe wrapped around ``note_governed_request_without_evidence``,
    the existing suite increments the gap counter **38 times** from exactly two
    tests - 37 direct calls in
    ``test_the_counted_routes_are_bounded_without_losing_the_total`` and 1 through
    the real middleware in ``test_a_governed_two_hundred_without_evidence_is_counted``
    - and because ``tests/conftest.py`` restores ``_GOVERNED_EVIDENCE_GAPS`` per
    test, each of those two tests starts at zero and is therefore a transition
    into firing. Under the rule pinned in this file that is **2 alert POSTs per
    suite run** the moment ``SDP_ALERT_WEBHOOK_URL`` is set in the environment
    CI runs in. A rule that posts during the test suite is a rule that will post
    in CI, so the unconfigured path has to be silent and the latch still has to
    advance, which the second half proves is distinguishable.
    """
    monkeypatch.delenv("SDP_ALERT_WEBHOOK_URL", raising=False)
    posts = _alert_seam(monkeypatch)
    _drive_gap_increments(25)
    assert posts == [], f"routing posted with no webhook configured: {posts}"
    unconfigured = obs.alert_routing_state()
    assert unconfigured["webhook_configured"] is False
    assert unconfigured["transitions_observed"] == 1, (
        "the transition is a fact about the rule, not about the operator's "
        "configuration; it must still be observed and published"
    )
    assert unconfigured["deliveries_attempted"] == 0

    # The same seam, proven live, so the assertions above cannot pass merely
    # because nothing in this product ever posts.
    monkeypatch.setenv("SDP_ALERT_WEBHOOK_URL", WEBHOOK)
    obs.reset_request_observability()
    _drive_gap_increments(1)
    assert len(posts) == 1, "the counting seam measured nothing in this test"


def test_the_read_path_posts_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    """``build_observability_manifest`` and ``prometheus_metrics_text`` are reads.

    Both are reached by ``GET /enterprise/observability`` and ``GET /metrics``,
    which take no credential, so routing wired into the read path makes any
    anonymous GET trigger an outbound POST to the operator's endpoint - an
    unauthenticated amplifier pointed at a URL the operator supplied. The
    manifest already publishes the rule's ``firing`` flag, which is exactly the
    value a read-path implementation would be tempted to act on.

    The seam is proven live first, by one real transition, so this cannot pass
    for want of any delivery at all - and the latch that transition set is then
    cleared, so the read path is the only thing left that could send. See
    ``_disarm_the_latch``: without it this test passed against the very
    implementation it names.
    """
    configured_webhook = _configured_alert_seam(monkeypatch)
    _drive_gap_increments(1)
    assert len(configured_webhook) == 1, "the counting seam measured nothing"
    _disarm_the_latch()

    for _ in range(25):
        manifest = obs.build_observability_manifest()
        obs.prometheus_metrics_text()
    gap = next(
        alert for alert in manifest["alerts"] if alert["id"] == "policy_audit_gap"
    )
    assert gap["firing"] is True, "the read path must still publish the firing rule"
    assert len(configured_webhook) == 1, (
        "25 manifest reads and 25 metrics renders of an already-firing rule "
        f"attempted {len(configured_webhook) - 1} alert POSTs; the read path "
        "must route nothing"
    )


def test_an_anonymous_read_burst_on_the_published_routes_posts_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The same guarantee over HTTP, on the two routes that take no credential.

    Measured, both answer 200 with no headers at all, so this is the reachable
    amplification surface rather than a hypothetical one. The latch is cleared
    after the liveness transition for the reason ``_disarm_the_latch`` records.
    """
    configured_webhook = _configured_alert_seam(monkeypatch)
    _drive_gap_increments(1)
    assert len(configured_webhook) == 1, "the counting seam measured nothing"
    _disarm_the_latch()

    for _ in range(25):
        assert client.get("/enterprise/observability").status_code == 200
        assert client.get("/metrics").status_code == 200
    assert len(configured_webhook) == 1, (
        "50 anonymous GETs attempted "
        f"{len(configured_webhook) - 1} alert POSTs at the operator's webhook"
    )


def test_an_http_burst_on_the_governed_surface_delivers_exactly_one_alert(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The bound, as a number, driven through the middleware that increments.

    ``/health`` evaluates no policy and records no evidence, so widening the
    governed surface to include it is the smallest honest way to make the real
    middleware produce the condition 25 times - the same device
    ``tests/test_request_evidence_correlation.py::test_a_governed_two_hundred_without_evidence_is_counted``
    uses for one request.

    This also forecloses one fire-and-forget shape. Measured against a
    reference routing implementation, a delivery written as
    ``loop.create_task(coro)`` where ``coro`` awaits anything before posting was
    cancelled at portal teardown and posted **0** times for this exact 25-request
    burst, failing here with "attempted 0 alert POSTs". A ``create_task`` whose
    coroutine posts without awaiting first did deliver (1), because the
    middleware awaits ``record_request_observation_async`` after the increment
    and that yields - so this test does not distinguish that shape, and
    ``test_the_alert_is_attempted_before_the_triggering_response_returns`` is
    the one that pins delivery to the triggering request.
    """
    configured_webhook = _configured_alert_seam(monkeypatch)
    monkeypatch.setattr(api, "_POLICY_GATED_ROUTES", frozenset({("GET", "/health")}))
    for _ in range(25):
        assert client.get("/health").status_code == 200
    assert obs.governed_evidence_gap_report()["observed_total"] == 25
    assert len(configured_webhook) == 1, (
        "25 governed 2xx responses with no evidence attempted "
        f"{len(configured_webhook)} alert POSTs; one firing episode is one alert"
    )
    assert configured_webhook[0]["method"] == "POST"
    assert configured_webhook[0]["url"] == WEBHOOK


def test_the_alert_is_attempted_before_the_triggering_response_returns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One request, asserted the instant it returns - the anti-vacuity pin.

    Every test in this repository drives the app with ``TestClient``, so a
    delivery scheduled beyond the request that triggered it is unobservable
    here, and both a delivery test and a non-delivery test written against such
    an implementation would report whatever the scheduler happened to do.
    Measured on this head against a reference routing implementation, with the
    module-level ``TestClient`` these tests use (no ``with`` block, so each
    request gets its own portal), delivery written three ways::

        implementation                      posts seen when the test asserts
                                            1 request      25 requests
        synchronous at the evaluation site   1              1
        create_task(coroutine that posts)    1              1
        create_task(coroutine that awaits
            anything first - a backoff, a
            to_thread hop with a pause)      0 (CancelledError)   0 (CancelledError)

    So the third shape is cancelled by the portal teardown and never posts at
    all, which is the shape this test refuses. ``== 1`` after a single request
    is the only assertion that distinguishes "delivered within the request"
    from "scheduled and lost", and it is what makes every other number in this
    file measurable.
    """
    configured_webhook = _configured_alert_seam(monkeypatch)
    monkeypatch.setattr(api, "_POLICY_GATED_ROUTES", frozenset({("GET", "/health")}))
    assert client.get("/health").status_code == 200
    assert obs.governed_evidence_gap_report()["observed_total"] == 1
    assert len(configured_webhook) == 1, (
        "the alert for a transition observed while serving this request had not "
        "been attempted when the response returned; delivery must be "
        "synchronous at the evaluation site or awaited off the loop the way "
        "record_request_observation_async awaits the log sink, never "
        "fire-and-forget"
    )


def test_the_process_wide_ceiling_is_the_routable_rule_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The burst bound stated as a number an operator can budget against.

    Two rules are routable, so between resets a worker sends at most two alert
    POSTs however long the burst is. ``central_workflow_backlog`` is about
    GitHub Actions run state this service does not observe, so it is published
    and not routable; listing it as routable would promise a delivery that can
    never be triggered.
    """
    configured_webhook = _configured_alert_seam(monkeypatch)
    assert sorted(obs.ROUTABLE_ALERT_RULE_IDS) == [
        "connector_probe_failure",
        "policy_audit_gap",
    ]
    _drive_gap_increments(500)
    for _ in range(25):
        obs.build_observability_manifest()
    assert len(configured_webhook) <= len(obs.ROUTABLE_ALERT_RULE_IDS)
    assert len(configured_webhook) == 1, (
        "only one of the two routable rules was driven, so the ceiling for this "
        f"burst is 1, not {len(configured_webhook)}"
    )
    assert obs.alert_routing_state()["routable_rules"] == 2


def test_the_manifest_publishes_delivery_rather_than_claiming_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Routing must replace the declared-unimplemented claim with a measurement.

    On the parent head ``alert_routing`` read ``declared_unimplemented`` and the
    ``policy_audit_gap`` rule published no delivery fact at all, so an operator
    reading the manifest after an episode could not tell a suppressed increment
    from a webhook that refused the POST. The published value has to be the
    measurement, next to the counts that justify it - the same rule the sink's
    ``configured`` field already follows ("a sink that raises on every export is
    not a configured sink").
    """
    configured_webhook = _configured_alert_seam(monkeypatch)
    _drive_gap_increments(25)
    manifest = obs.build_observability_manifest()
    assert manifest["alert_routing"] == "implemented"
    gap = next(
        alert for alert in manifest["alerts"] if alert["id"] == "policy_audit_gap"
    )
    assert gap["routable"] is True
    assert gap["alerts_attempted"] == 1
    assert gap["alerts_succeeded"] == 1
    assert gap["alerts_failed"] == 0
    assert gap["increments_suppressed"] == 24
    assert len(configured_webhook) == 1


def test_a_refused_post_is_not_published_as_a_delivered_alert(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The counter a published name reads has to be the counter it names.

    ``alerts_delivered`` read ``attempted``, so one POST the webhook refused
    published ``alerts_delivered: 1`` beside ``alerts_failed: 1`` - the same
    single POST counted as both - while ``deliveries_succeeded``, which held the
    honest number, was read by nothing. ``metrics.alerts_delivered_total`` and
    the ``sdp_alerts_delivered_total`` gauge read the same attempt count, so an
    operator paging on the gauge's absence of movement had no signal at all.

    Driven against a webhook that refuses every POST, which is the state the
    old names could not express.
    """

    def _refuse(request, timeout=None):
        """Refuse the POST the way an unreachable webhook does."""
        raise OSError("connection refused")

    monkeypatch.setattr(obs, "alert_urlopen", _refuse)
    monkeypatch.setenv("SDP_ALERT_WEBHOOK_URL", "https://alerts.example.net/hook")
    _drive_gap_increments(1)

    manifest = obs.build_observability_manifest()
    gap = next(
        alert for alert in manifest["alerts"] if alert["id"] == "policy_audit_gap"
    )
    assert gap["alerts_attempted"] == 1
    assert gap["alerts_succeeded"] == 0, (
        "the webhook refused the POST; nothing was delivered"
    )
    assert gap["alerts_failed"] == 1
    assert "alerts_delivered" not in gap, (
        "a key named for a delivery must not be published from the attempt count"
    )

    metrics = manifest["metrics"]
    assert metrics["alerts_attempted_total"] == 1
    assert metrics["alerts_succeeded_total"] == 0
    assert metrics["alerts_failed_total"] == 1
    assert "alerts_delivered_total" not in metrics

    exported = obs.prometheus_metrics_text()
    assert "sdp_alerts_attempted_total 1" in exported
    assert "sdp_alerts_succeeded_total 0" in exported
    assert "sdp_alerts_failed_total 1" in exported
    assert "sdp_alerts_delivered_total" not in exported, (
        "a gauge whose HELP text said attempted and whose name said delivered"
    )


def test_a_reset_episodes_thread_writes_into_neither_ring(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A delivery whose episode was reset mid-flight records nothing.

    The counter writes were already guarded by the generation; the retained
    failure ring was not, so a thread still waiting on a webhook from a reset
    episode had its counter write discarded and appended its failure anyway. The
    published block then held ``deliveries_failed: 0`` beside a retained failure
    for a rule whose counters were all zero - a document disagreeing with
    itself, which is the shape this field exists to refuse.

    The reset has to land **while the POST is in flight**, which is the only
    way the failure path is reached with a stale generation: the attempt is
    counted before the POST, and a thread that is already stale at that point
    returns without sending. A first attempt at this test passed a stale
    generation in from the start and was green with the guard deleted - it never
    reached the ring at all. The webhook double resets the episode and then
    refuses, which is exactly the race.
    """

    def _reset_then_refuse(request, timeout=None):
        """Reset the episode mid-flight, then refuse the POST."""
        obs.reset_alert_routing()
        raise OSError("connection refused")

    monkeypatch.setattr(obs, "alert_urlopen", _reset_then_refuse)
    obs.reset_alert_routing()
    current = obs._ALERT_ROUTING["generation"]

    obs._deliver_alert(
        "policy_audit_gap", "https://alerts.example.net/hook", b"{}", current
    )

    state = obs.alert_routing_state()
    assert state["deliveries_attempted"] == 0, (
        "the reset cleared the attempt, so nothing from that episode is counted"
    )
    assert state["deliveries_failed"] == 0
    assert state["retained_failures"] == 0, (
        "the failure ring kept a row for an episode whose counters were "
        f"discarded: {obs.list_alert_routing_errors()}"
    )


def test_a_stale_thread_does_not_post_at_all(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Nothing is sent for an episode nothing is counting.

    The POST has not left the process when the generation is first checked, so
    the honest outcome is not to send it. In this suite the alternative is
    visible: the POST arrives at the *next* test's double.
    """
    posts = _alert_seam(monkeypatch)
    obs.reset_alert_routing()
    stale = obs._ALERT_ROUTING["generation"] - 1

    obs._deliver_alert(
        "policy_audit_gap", "https://alerts.example.net/hook", b"{}", stale
    )

    assert posts == [], f"a reset episode's thread still POSTed: {posts}"
