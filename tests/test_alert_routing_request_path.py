"""An unreachable alert webhook must not slow, fail, or hide inside a governed request.

On the parent head ``SDP_ALERT_WEBHOOK_URL`` was declared-unimplemented: the
only read of it in the whole package was ``observability._sink_status`` taking
``bool()`` of it for the ``alert_webhook_configured`` field. Delivery makes it
the first outbound call this service makes *while serving a request*, hooked on the
evaluation event of the connector-probe-failure rule inside
``connectors.connector_probe`` — and the request that carries it is a governed
one. Three ways that can go wrong, each measured at HEAD on the surfaces that
already exist.

**Which request fires the rule.** This file first claimed the firing request was
``rest_connector``/``marketing-campaign``, "from seed state alone". That was
wrong, and ``tests/test_connector_probe_alert_rule.py`` is the family that
settles it: that pair probes ``contract_only`` because the optional
``SDP_CONNECTOR_SECRET_REST_CONNECTOR_MARKETING_CAMPAIGN_TOKEN`` is unset, and
``sdp/demo_smoke.py``'s ready gate asserts that exact state and reports
``ready: True``, so a rule firing on it fires on the shipped demo image. Nothing
in seed state makes the rule fire, deliberately — the condition is a build-owned
verdict-basis failure and reports zero on a correct deployment. So these tests
inject the build defect the rule is for, by the same monkeypatch that family
uses: ``audit_event``'s declared proof endpoint pointed at a path this app does
not serve. The request stays governed and audited and still answers 200; what
changes is that its probe now reports a failure the build owns.

* **It can slow the request.** The log sink is the precedent: the middleware
  awaits its own export before returning, so a dead sink is paid by the
  response. Measured against a socket that accepts the handshake and never
  answers, ``SDP_LOG_SINK_URL=http://127.0.0.1:<port>/ingest`` at the default
  ``SDP_LOG_SINK_TIMEOUT_MS=500``, ``GET /health`` (median 8.52 ms, max
  16.29 ms with no sink configured)::

      req  latency_ms  status  fails   open  skipped
        1      514.52     200      1  False        0
        2      509.88     200      2  False        0
        3      508.90     200      3  False        0
        4      507.76     200      4  False        0
        5      510.83     200      5   True        0
        6        4.46     200      5   True        1
       12        2.62     200      5   True        7

  Five requests pay one full timeout each (507.8-514.5 ms), then
  ``_SINK_BREAKER`` opens and the cost falls to 2.62-4.46 ms for
  ``SINK_COOLDOWN_SECONDS = 30``. So the breaker bounds a dead sink to
  5 x ~510 ms per 30 s rather than removing the cost — the status stayed 200
  throughout, but the response waited. An alert path that copies this shape
  charges the same toll to a *governed* request.

* **It can fail the request.** ``api.py::enterprise_connector_probe`` records
  its "allowed" audit event only **after** ``connectors.connector_probe``
  returns, so anything raising inside the probe loses the audit row and keeps
  the policy decision. Measured by wrapping ``connectors.connector_probe`` in a
  hook that raises ``OSError`` after the real probe succeeds, on
  ``GET /enterprise/connectors/sql_connector/probe?dataset_id=crm-customer-master&user=admin``
  with the broken proof endpoint installed (a clean 200/``contract_only``
  without the hook)::

      TestClient(app)                              -> OSError raised into the test
      TestClient(app, raise_server_exceptions=False) -> HTTP 500
      both:  policy_decisions +1   audit_events +0

  Note the first line: with this repo's default client the exception does not
  become a 500 at all, it propagates into the test, so a pin written only
  against the default client would assert the wrong artifact.

* **It can hide.** The middleware stamps ``latency_ms`` in its ``finally``
  block and exports afterwards, so everything after that stamp is invisible to
  the ``latency_budgets`` report ``GET /enterprise/observability`` publishes.
  Measured on the same probe route with the dead sink above::

      client wall clock           512.95 ms
      observation latency_ms        2.91 ms
      invisible to the report     510.03 ms

  A published p95 that under-reports by half a second is the "published number
  disagrees with the code enforcing it" shape this product exists to refuse.

**How delivery is observed here, and why nothing in this file touches asyncio.**
A fire-and-forget ``asyncio.create_task`` POST cannot be measured under
``TestClient``, in two different ways, both measured:

* from the middleware's async scope, the task is cancelled when the test
  portal tears the request down — ``outcome == ['CancelledError']``, never
  delivered;
* from ``connector_probe``, which FastAPI runs in an ``anyio`` worker thread
  because the route handler is ``def``, there is no loop to attach to at all:
  ``asyncio.get_running_loop()`` raises ``RuntimeError: no running event loop``.

Every test in this repository uses ``TestClient``, so a request-driven delivery
assertion would measure the harness and a non-delivery assertion would pass
vacuously. These tests therefore assert nothing about a coroutine. They inject
faults **by configuration only** — an environment variable and a real local
socket — and read the outcome from the published synchronous counters, polling
them to a deadline so the same assertion holds whether delivery is inline, on a
worker thread, or drained from a queue. Each test also asserts that the alert
path actually ran, so "no alert routing exists" fails loudly instead of passing
as "no alert latency was added".
"""

from __future__ import annotations

import asyncio
from pathlib import Path
import re
import socket
import sys
import time
from typing import Any

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sdp import api, catalog, connectors as conn, evidence, observability as obs  # noqa: E402
from sdp.api import app  # noqa: E402

# The repo-default client re-raises a server exception into the test; the second
# one answers the way a real uvicorn worker does. The measurement above shows
# the same defect presents differently through each, so both are pinned.
client = TestClient(app)
raw_client = TestClient(app, raise_server_exceptions=False)

# The governed request these tests fire, with ``broken_proof_endpoint``
# installed: a policy-gated, audited route whose probe reports a build-owned
# verdict-basis failure. Measured, it answers 200 with ``status: contract_only``
# and records one policy decision and one audit event.
PROBE_ROUTE = "/enterprise/connectors/sql_connector/probe"
PROBE_PARAMS = {"dataset_id": "crm-customer-master", "user": "admin"}

# Measured baseline for that request with no sink and no webhook configured, 30
# requests after one warm-up, the alert latch reset before each so every one of
# them is a transition: min 6.06, median 7.79, p95 10.22, max 10.86 ms. The
# bound below is ~90x the slowest observed baseline and one fifth of the alert
# timeout the tests configure, so it cannot fail on scheduling noise and cannot
# pass if the response waited for the webhook.
#
# It is also well clear of the one cost the alert path does charge:
# ``observability.ALERT_HANDSHAKE_BUDGET_SECONDS`` is how long the evaluating
# request joins the delivery thread, and a wedged webhook therefore costs that
# budget once per firing episode rather than the full alert timeout per request.
PROBE_BASELINE_MAX_MS = 10.86
REQUEST_LATENCY_BOUND_MS = 1000.0

# Long on purpose. If delivery is awaited by the request, the response cannot
# come back inside REQUEST_LATENCY_BOUND_MS; if it is off the request path, the
# value is irrelevant to the response. A 5x gap is the margin that makes the
# test a measurement rather than a race.
ALERT_TIMEOUT_MS = "5000"

# The event loop's own responsiveness, as the gap between successive 10 ms
# ticks. Measured with a wedged webhook at the timeout above: the repaired path
# gapped 11.50-20.69 ms over eight runs, the defect 262.00 ms, and the control
# with no webhook configured 11.82 ms. The bound sits ~5x above the worst
# repaired measurement and ~2.6x below the defect, so it cannot fail on
# scheduling noise and cannot pass if the wait is back on the loop.
TICK_INTERVAL_S = 0.01
LOOP_BLOCK_BOUND_MS = 100.0


@pytest.fixture(autouse=True)
def broken_proof_endpoint(monkeypatch: pytest.MonkeyPatch) -> str:
    """Make this build stop serving a declared proof endpoint, for every test here.

    ``audit_event`` is required by all four registry connectors and its declared
    proof endpoint is ``/audit/events``. Pointing it at a path the app does not
    serve reproduces the build defect the rule is for - a route renamed or
    dropped while the control still claims it - without editing the route table,
    and is the same device
    ``tests/test_connector_probe_alert_rule.py::test_a_build_that_lost_a_declared_proof_endpoint_is_counted``
    uses. Autouse because every test in this file needs the rule to fire: with a
    correct build it reports zero, which is the point of the rule and would make
    all four assertions here vacuous.
    """
    monkeypatch.setitem(conn._IMPLEMENTED_PROOF, "audit_event", ["/audit/events-renamed"])
    return "/audit/events-renamed"


@pytest.fixture(autouse=True)
def _clean_observability():
    """Clear the observation buffers and any alert-routing state around each test.

    ``tests/conftest.py``'s autouse fixture covers alert-routing state now, by a
    restore line placed **after** ``reset_request_observability()`` - which
    clears what the lines before it put back - with the names declared in
    ``RESTORED_BY_FIXTURE`` in ``tests/test_module_state_coverage.py``. This
    fixture stays because these tests leave a delivery thread blocked on a
    wedged webhook for the whole alert timeout, and resetting on the way in as
    well as out means the next test in this file starts from a clean latch even
    while that thread is still waiting.
    """
    obs.reset_request_observability()
    _reset_alert_routing()
    try:
        yield
    finally:
        obs.reset_request_observability()
        _reset_alert_routing()


def _reset_alert_routing() -> None:
    """Reset alert-routing state if the capability exists, else do nothing."""
    reset = getattr(obs, "reset_alert_routing", None)
    if reset is not None:
        reset()


def _alert_routing_snapshot() -> dict[str, Any]:
    """Read the published alert-routing counters, or report that none exist.

    Returned as a dict with an ``exists`` flag rather than raising, so a test
    that needs "the alert path ran" fails on an assertion naming the missing
    capability instead of erroring on ``AttributeError`` - the defect is that
    nothing routes, not that a symbol is absent.
    """
    state = getattr(obs, "alert_routing_state", None)
    if state is None:
        return {
            "exists": False,
            "deliveries_attempted": 0,
            "deliveries_succeeded": 0,
            "deliveries_failed": 0,
            "reason": (
                "sdp.observability publishes no alert_routing_state(), so nothing "
                "delivered to SDP_ALERT_WEBHOOK_URL and no alert was routed by "
                "this request"
            ),
        }
    snapshot = dict(state())
    snapshot["exists"] = True
    return snapshot


def _alert_errors() -> list[Any]:
    """The retained alert-routing failures, or an empty list if there is no ring."""
    lister = getattr(obs, "list_alert_routing_errors", None)
    return list(lister()) if lister is not None else []


def _wait_for_alert(key: str, minimum: int = 1, deadline_s: float = 3.0) -> dict[str, Any]:
    """Poll the published alert counters until ``key`` reaches ``minimum``.

    Mechanism-agnostic on purpose: an inline implementation satisfies this on
    the first read, a worker-thread or queue-drained one satisfies it a few
    milliseconds later, and neither requires this test to know which. The
    deadline is what replaces awaiting a coroutine that ``TestClient`` would
    cancel. Returns the last snapshot read, so the caller asserts against the
    same values the poll saw.
    """
    deadline = time.monotonic() + deadline_s
    snapshot = _alert_routing_snapshot()
    while snapshot.get(key, 0) < minimum and time.monotonic() < deadline:
        time.sleep(0.01)
        snapshot = _alert_routing_snapshot()
    return snapshot


@pytest.fixture
def black_hole_webhook():
    """A local TCP endpoint that completes the handshake and never answers.

    The kernel accepts into the listen backlog without the test ever calling
    ``accept()``, so ``connect()`` succeeds and the POST then waits for the full
    timeout - the same fault the log-sink measurement in this module's docstring
    used, and the one an operator's webhook presents when it is wedged rather
    than down. 127.0.0.1 is in this environment's ``no_proxy``, so urllib
    connects directly and the measurement is of this socket, not of a proxy.
    """
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(128)
    try:
        yield f"http://127.0.0.1:{listener.getsockname()[1]}/alerts"
    finally:
        listener.close()


@pytest.fixture
def refused_webhook():
    """A local TCP endpoint nothing is listening on, so connecting is refused.

    Bound and closed so the port was really ours and is really free: a hardcoded
    port could belong to something else. This is the fault that raises inside
    the alert path promptly, where ``black_hole_webhook`` hangs.
    """
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    return f"http://127.0.0.1:{port}/alerts"


def _evidence_counts() -> tuple[int, int]:
    """The policy-decision and audit-event totals, as the published counters read them."""
    return catalog.count_audit_events()[0], evidence.count_policy_decisions()[0]


def _fire_probe(using: TestClient = client) -> Any:
    """Issue the one governed request that makes the connector-probe rule fire."""
    return using.get(PROBE_ROUTE, params=PROBE_PARAMS)


def test_a_wedged_alert_webhook_does_not_slow_a_governed_request(
    monkeypatch: pytest.MonkeyPatch, black_hole_webhook: str
) -> None:
    """A firing governed request must not wait for the webhook.

    The defect this refuses: the log sink's shape applied to alerts. Measured,
    an awaited export against a socket that accepts and never answers cost
    507.8-514.5 ms per request at a 500 ms timeout while still answering 200,
    and ``_SINK_BREAKER`` only bounds that to five such requests per 30 s
    cooldown. Here the timeout is set to 5000 ms, so an awaited alert cannot
    answer inside the 1000 ms bound; the same probe measured 4.50-13.10 ms over
    30 requests with nothing configured.

    The last assertion is what stops this passing vacuously: with no routing at
    all every response is fast, so "fast" only means something once the alert
    path is shown to have run.
    """
    monkeypatch.setenv("SDP_ALERT_WEBHOOK_URL", black_hole_webhook)
    monkeypatch.setenv("SDP_ALERT_TIMEOUT_MS", ALERT_TIMEOUT_MS)

    latencies = []
    for _ in range(5):
        started = time.perf_counter()
        response = _fire_probe()
        latencies.append((time.perf_counter() - started) * 1000)
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "contract_only"

    assert max(latencies) < REQUEST_LATENCY_BOUND_MS, (
        f"a governed request waited for the wedged webhook: {latencies} ms against a "
        f"{ALERT_TIMEOUT_MS} ms alert timeout; the same request measured "
        f"{PROBE_BASELINE_MAX_MS} ms at worst with nothing configured"
    )

    snapshot = _wait_for_alert("deliveries_attempted")
    assert snapshot["deliveries_attempted"] >= 1, snapshot.get(
        "reason", f"no alert was attempted, so the latency above measures nothing: {snapshot}"
    )


def test_an_alert_path_failure_never_becomes_the_requests_response(
    monkeypatch: pytest.MonkeyPatch, refused_webhook: str
) -> None:
    """An unreachable webhook must not turn a governed 200 into a 500.

    ``api.py::enterprise_connector_probe`` calls ``catalog.ingest_event`` with
    ``decision="allowed"`` only after ``connectors.connector_probe`` returns, so
    a raise from inside the probe takes the audit row with it. Measured with a
    hook that raises ``OSError`` after the real probe succeeded: the default
    client re-raised into the test, ``raise_server_exceptions=False`` answered
    HTTP 500, and both left ``policy_decisions +1`` and ``audit_events +0`` - the
    governed request recorded a decision it never audited.

    So this pins the response *and* both evidence rows, through the client that
    answers the way a real worker does, and asserts the failure was retained
    rather than swallowed silently.
    """
    monkeypatch.setenv("SDP_ALERT_WEBHOOK_URL", refused_webhook)
    monkeypatch.setenv("SDP_ALERT_TIMEOUT_MS", ALERT_TIMEOUT_MS)

    audit_before, decisions_before = _evidence_counts()
    response = _fire_probe(using=raw_client)
    audit_after, decisions_after = _evidence_counts()

    assert response.status_code == 200, (
        f"the refused webhook became the governed request's response: "
        f"{response.status_code} {response.text[:200]}"
    )
    assert response.json()["status"] == "contract_only"
    assert audit_after - audit_before == 1, (
        "the governed probe must still record its audit event; the measured "
        "precedent lost exactly this row (+1 decision, +0 audit) when something "
        "raised inside connector_probe"
    )
    assert decisions_after - decisions_before == 1

    snapshot = _wait_for_alert("deliveries_failed")
    assert snapshot["deliveries_failed"] >= 1, snapshot.get(
        "reason", f"the refused webhook produced no recorded alert failure: {snapshot}"
    )
    assert _alert_errors(), "an alert failure must be retained, not swallowed"


@pytest.mark.parametrize("unusable_scheme", ["ftp", "file"])
def test_a_misconfigured_alert_webhook_never_becomes_the_requests_response(
    unusable_scheme: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A webhook URL the scheme gate refuses must fail the alert, not the request.

    The settled design routes the webhook through
    ``observability._http_sink_request_parts`` - which resolves userinfo into an
    ``Authorization`` header but does **not** validate the scheme - plus the
    alert path's own scheme gate. That gate runs on the request thread in every
    delivery design, inline or otherwise, which is why this case is pinned
    separately from the unreachable-host one: a design that moves delivery off
    the request can still raise here.

    Both unusable schemes are driven, because only one of them measures the
    gate. Reverse-verification: with the gate deleted, the ``ftp://`` case still
    passed - the value reaches ``_http_sink_request_parts``, which resolves the
    host and builds a connectable URL, and the delivery then fails at DNS
    (measured, ``URLError [Errno -2] Name or service not known``). "The alert
    failed and the request did not" held for a reason unrelated to the gate.

    ``file://`` is the fault that separates them, and it is the reason the alert
    path's acceptable set is narrower than the sink's - ``_sink_status`` names
    "the file, http or https scheme", and a file is not an outbound POST.
    Measured with the real urllib, a POST to a ``file://`` URL does **not**
    fail: ``FileHandler`` opens the local path and returns its contents, so
    without the gate every firing episode becomes a local-file read on the
    server, counted and published as a *successful* delivery. Hence the
    succeeded-count assertion below, which is the half a "did it fail" check
    cannot make.

    The URL is built with an explicit ``localhost`` authority rather than from
    ``Path.as_uri()``, and that detail is the test. Measured with the gate
    deleted::

        file:///tmp/.../t.txt            SinkConfigurationError
                                         "must name a host (https://host/path)"
        file://localhost/tmp/.../t.txt   ('file://localhost/tmp/.../t.txt', ...)

    ``as_uri()`` produces the empty-authority form, which
    ``_http_sink_request_parts`` refuses for having no host - so a test written
    with it measures the host requirement and reports the scheme gate as
    present when it is not. The authority form is also the realistic
    misconfiguration: ``_file_sink_path`` deliberately supports
    ``file://host/share/...``, so an operator copying their working
    ``SDP_LOG_SINK_URL`` into ``SDP_ALERT_WEBHOOK_URL`` arrives here.
    """
    if unusable_scheme == "ftp":
        webhook = "ftp://alerts.example.net/hook"
    else:
        readable = tmp_path / "local-target.txt"
        readable.write_text("a local file is not a webhook\n", encoding="utf-8")
        webhook = f"file://localhost{readable.as_posix()}"
    monkeypatch.setenv("SDP_ALERT_WEBHOOK_URL", webhook)
    monkeypatch.setenv("SDP_ALERT_TIMEOUT_MS", ALERT_TIMEOUT_MS)

    audit_before, decisions_before = _evidence_counts()
    response = _fire_probe(using=raw_client)
    audit_after, decisions_after = _evidence_counts()

    assert response.status_code == 200, (
        f"a refused webhook scheme became the governed request's response: "
        f"{response.status_code} {response.text[:200]}"
    )
    assert audit_after - audit_before == 1
    assert decisions_after - decisions_before == 1

    snapshot = _wait_for_alert("deliveries_failed")
    assert snapshot["deliveries_failed"] >= 1, snapshot.get(
        "reason",
        f"an unusable webhook scheme was neither routed nor refused: {snapshot}",
    )
    assert snapshot["deliveries_succeeded"] == 0, (
        f"a {unusable_scheme}:// webhook was counted as a delivered alert: "
        f"{snapshot}; for file:// that means the alert path read a local path on "
        "this server and published the read as a successful delivery"
    )
    assert _alert_errors(), (
        "the refused scheme must be retained as an alert-routing failure, so an "
        "operator can see the alert did not leave"
    )


def test_the_alert_wait_does_not_block_the_event_loop(
    monkeypatch: pytest.MonkeyPatch, black_hole_webhook: str
) -> None:
    """The one evaluation site that runs on the loop must not wait on it.

    ``sdp.api``'s observability middleware is ``async``, and
    ``note_governed_request_without_evidence`` - called from its ``finally``
    block - waits for the alert delivery it starts. So the first implementation
    put a bounded join on the loop thread, which does not slow the request that
    triggered it any more than the budget allows but **serializes every other
    request behind it**. Measured against a socket that accepts the handshake
    and never answers, at a 5000 ms alert timeout, with a 10 ms asyncio ticker:

        async entry point (the repair)    worst tick gap  11.50-20.69 ms (8 runs)
        sync entry point on a loop        worst tick gap         262.00 ms
        no webhook configured (control)   worst tick gap          11.82 ms

    This is not a new hazard. ``docs/product-technical-gap-baseline.md`` records
    it as audit finding 7 against the log sink - a synchronous export on the
    loop serializing every request - and the middleware carries the comment
    "The sink write is blocking, so it is awaited off the event loop" two lines
    below the alert call. The repair is the same device, not a new one:
    ``anyio.to_thread.run_sync`` around the join, with the latch bookkeeping
    (a few dict writes under a lock) left inline.

    The ticker is what makes this a measurement of the loop rather than of the
    request: the call's own duration is ~255 ms either way, because the request
    does pay the handshake budget. What distinguishes repair from defect is
    whether anything else could run while it waited.
    """
    monkeypatch.setenv("SDP_ALERT_WEBHOOK_URL", black_hole_webhook)
    monkeypatch.setenv("SDP_ALERT_TIMEOUT_MS", ALERT_TIMEOUT_MS)

    async def _tick_until(stop: asyncio.Event, gaps: list[float]) -> None:
        """Record the gap between successive ticks; a large gap is a blocked loop."""
        last = time.perf_counter()
        while not stop.is_set():
            await asyncio.sleep(TICK_INTERVAL_S)
            now = time.perf_counter()
            gaps.append((now - last) * 1000)
            last = now

    async def _drive() -> tuple[list[float], float]:
        """Fire the rule through the async entry point while the ticker runs."""
        stop: asyncio.Event = asyncio.Event()
        gaps: list[float] = []
        ticker = asyncio.create_task(_tick_until(stop, gaps))
        await asyncio.sleep(0.05)
        started = time.perf_counter()
        await obs.note_governed_request_without_evidence_async(
            "GET /catalog/datasets/{dataset_id}"
        )
        elapsed = (time.perf_counter() - started) * 1000
        await asyncio.sleep(0.05)
        stop.set()
        await ticker
        return gaps, elapsed

    gaps, elapsed = asyncio.run(_drive())

    assert gaps, "the ticker recorded nothing, so this measured no loop at all"
    assert max(gaps) < LOOP_BLOCK_BOUND_MS, (
        f"the alert wait blocked the event loop for {max(gaps):.2f} ms (the call "
        f"itself took {elapsed:.2f} ms); every concurrent request serializes "
        "behind one firing request, which is the defect already fixed for the "
        "sink write in the same middleware function"
    )

    snapshot = _wait_for_alert("deliveries_attempted")
    assert snapshot["deliveries_attempted"] >= 1, snapshot.get(
        "reason",
        f"no alert was attempted, so the unblocked loop above measures nothing: {snapshot}",
    )


def test_the_middleware_awaits_the_alert_instead_of_calling_it_inline() -> None:
    """The site, not only the function - the half a timing test cannot reach.

    ``test_the_alert_wait_does_not_block_the_event_loop`` calls the async entry
    point directly, so it proves that function keeps the wait off the loop and
    says nothing about what the middleware calls. Reverting the call site to the
    synchronous form would leave that test green and restore the defect, which
    is the shape this repository keeps finding: a guard checked against
    something adjacent to the thing it describes.

    Read from the source because the middleware is a decorated closure: the call
    is a fact about the code, and asserting it here is cheaper and more direct
    than driving concurrent requests through ``TestClient``, which issues them
    one at a time and therefore cannot observe serialization at all.
    """
    source = Path(api.__file__).read_text(encoding="utf-8")
    assert "await note_governed_request_without_evidence_async(" in source, (
        "the observability middleware no longer awaits the async alert entry "
        "point; a synchronous call there puts the delivery wait back on the "
        "event loop"
    )
    inline = [
        line.strip()
        for line in source.splitlines()
        if re.search(r"(?<!_async)note_governed_request_without_evidence\(", line)
    ]
    assert inline == [], (
        f"sdp.api calls the synchronous gap-counting entry point: {inline}. It "
        "waits for the alert it starts, and every call site in this module is "
        "on the event loop."
    )


def test_alert_latency_cannot_hide_outside_the_published_latency_report(
    monkeypatch: pytest.MonkeyPatch, black_hole_webhook: str
) -> None:
    """Latency the published report cannot see must not be where the alert path lives.

    The middleware computes ``latency_ms = (monotonic() - started) * 1000`` in
    its ``finally`` block and exports afterwards, so the window between that
    stamp and the response reaching the client is invisible to the
    ``latency_budgets`` report. Measured on this route with a dead log sink:
    wall clock 512.95 ms, published ``latency_ms`` 2.91 ms, **510.03 ms
    invisible**.

    The decision pinned here: that blind spot is acceptable for the alert path
    *only* because the alert path must contribute nothing to it. Moving the
    stamp would be the wrong fix - it would start charging the log sink's export
    to the published p95 of every surface, changing six published budget
    comparisons to repair a window that should be empty. Keeping the stamp and
    requiring the window to stay empty fixes the same risk without moving a
    published number: a reader of ``observed_p95_ms`` is then not being told a
    figure that omits a 5-second webhook timeout.

    So: with a wedged webhook at a 5000 ms timeout, the gap between what the
    client waited and what the report publishes for that request must stay
    inside the bound. Asserting the alert ran keeps the empty window meaningful
    rather than merely absent.
    """
    monkeypatch.setenv("SDP_ALERT_WEBHOOK_URL", black_hole_webhook)
    monkeypatch.setenv("SDP_ALERT_TIMEOUT_MS", ALERT_TIMEOUT_MS)

    started = time.perf_counter()
    response = _fire_probe()
    wall_clock_ms = (time.perf_counter() - started) * 1000
    assert response.status_code == 200, response.text

    rows = [
        row for row in obs.list_request_observations(limit=50) if row["route"] == PROBE_ROUTE
    ]
    assert rows, "the governed request recorded no observation to compare against"
    published_ms = rows[-1]["latency_ms"]

    unmeasured_ms = wall_clock_ms - published_ms
    assert unmeasured_ms < REQUEST_LATENCY_BOUND_MS, (
        f"the alert path put {unmeasured_ms:.2f} ms into the window the published "
        f"latency report cannot see (client waited {wall_clock_ms:.2f} ms, "
        f"/enterprise/observability publishes {published_ms:.2f} ms); the log sink's "
        "own measured blind spot on this route is 510.03 ms and is why the alert "
        "path must not be in that window at all"
    )

    snapshot = _wait_for_alert("deliveries_attempted")
    assert snapshot["deliveries_attempted"] >= 1, snapshot.get(
        "reason",
        f"no alert was routed, so the empty window above is absence, not a bound: {snapshot}",
    )


def test_the_handshake_budget_bounds_the_middleware_site_and_the_join_happens(
    monkeypatch: pytest.MonkeyPatch, black_hole_webhook: str
) -> None:
    """Both halves of the wait, at the site that had neither pinned.

    ``ALERT_HANDSHAKE_BUDGET_SECONDS`` is the whole reason a firing request can
    be charged for a wedged webhook at all, and no test asserted on the cost at
    the middleware site. Measured with the budget deleted - ``worker.join()``
    with no argument - this call took **5012.93 ms** against the 5000 ms alert
    timeout and the whole suite stayed green, because the loop-block test above
    measures tick gaps and the probe-route test measures a route this evaluation
    site is not on.

    The floor is the other half. Without the join the call returns in under a
    millisecond, and "exactly one POST per episode is observable at the
    evaluation site" - the property the join exists for - would be a claim with
    nothing behind it. Against a socket that accepts and never answers, the
    worker cannot finish, so the join waits the whole budget and the measured
    cost is the budget.
    """
    monkeypatch.setenv("SDP_ALERT_WEBHOOK_URL", black_hole_webhook)
    monkeypatch.setenv("SDP_ALERT_TIMEOUT_MS", ALERT_TIMEOUT_MS)
    budget_ms = obs.ALERT_HANDSHAKE_BUDGET_SECONDS * 1000

    async def _drive() -> float:
        """Fire the rule through the async entry point once, timed."""
        started = time.perf_counter()
        await obs.note_governed_request_without_evidence_async(
            "GET /catalog/datasets/{dataset_id}"
        )
        return (time.perf_counter() - started) * 1000

    elapsed = asyncio.run(_drive())

    assert elapsed < REQUEST_LATENCY_BOUND_MS, (
        f"the middleware-site wait cost {elapsed:.2f} ms against a "
        f"{ALERT_TIMEOUT_MS} ms alert timeout and a {budget_ms:.0f} ms handshake "
        "budget, so the budget is not bounding this site"
    )
    assert elapsed >= budget_ms * 0.6, (
        f"the middleware-site wait cost {elapsed:.2f} ms against a "
        f"{budget_ms:.0f} ms budget on a webhook that cannot answer, so the "
        "delivery was not joined at all and nothing makes one POST per episode "
        "observable here"
    )

    snapshot = _wait_for_alert("deliveries_attempted")
    assert snapshot["deliveries_attempted"] >= 1, snapshot.get(
        "reason", f"no alert was attempted, so the timing above measures nothing: {snapshot}"
    )


def test_the_probe_routes_first_firing_request_also_waits_for_its_delivery(
    monkeypatch: pytest.MonkeyPatch, black_hole_webhook: str
) -> None:
    """The sync site's join, measured on the transition rather than the burst.

    ``test_a_wedged_alert_webhook_does_not_slow_a_governed_request`` fires five
    requests and bounds the slowest; only the first is a transition, so four of
    the five pay nothing and the ceiling holds whether or not the first one
    waited. The floor has to be read off the transition alone.
    """
    monkeypatch.setenv("SDP_ALERT_WEBHOOK_URL", black_hole_webhook)
    monkeypatch.setenv("SDP_ALERT_TIMEOUT_MS", ALERT_TIMEOUT_MS)
    budget_ms = obs.ALERT_HANDSHAKE_BUDGET_SECONDS * 1000

    started = time.perf_counter()
    response = _fire_probe()
    first_ms = (time.perf_counter() - started) * 1000
    assert response.status_code == 200, response.text

    started = time.perf_counter()
    assert _fire_probe().status_code == 200
    second_ms = (time.perf_counter() - started) * 1000

    assert first_ms >= budget_ms * 0.6, (
        f"the transition request cost {first_ms:.2f} ms against a "
        f"{budget_ms:.0f} ms budget on a webhook that cannot answer: the "
        "delivery was not joined"
    )
    assert first_ms < REQUEST_LATENCY_BOUND_MS, f"{first_ms:.2f} ms"
    assert second_ms < PROBE_BASELINE_MAX_MS * 10, (
        f"the suppressed request cost {second_ms:.2f} ms; only the transition "
        "may be charged for the webhook"
    )


def test_an_alert_evaluation_that_raises_leaves_the_governed_request_audited(
    monkeypatch: pytest.MonkeyPatch, refused_webhook: str
) -> None:
    """The guard has to sit on the thread the request is on.

    ``_deliver_alert``'s broad ``except`` wraps the spawned thread's body, which
    cannot reach the request anyway. Everything the request thread itself does
    after latching - the rule's report, building the payload, starting the
    thread - was unguarded, so a raise there escaped into the governed request
    and reproduced the precedent that ``except``'s own comment says it
    forecloses: a 500 with +1 policy decision and +0 audit events, because
    ``api.py`` records the audit event only after ``connector_probe`` returns.

    Driven by making ``_alert_payload`` raise, which is evaluated on the request
    thread inside the ``args`` tuple of the delivery thread's constructor.
    """

    def _raise(rule_id: str) -> bytes:
        """Fail where the request thread builds the payload."""
        raise OSError("payload serialisation failed")

    monkeypatch.setattr(obs, "_alert_payload", _raise)
    monkeypatch.setenv("SDP_ALERT_WEBHOOK_URL", refused_webhook)
    before_audit, before_decisions = _evidence_counts()

    response = _fire_probe(using=raw_client)

    assert response.status_code == 200, response.text
    after_audit, after_decisions = _evidence_counts()
    assert (after_audit - before_audit, after_decisions - before_decisions) == (1, 1), (
        "a governed request that answered through the alert path recorded a "
        "policy decision it never audited"
    )

    snapshot = obs.alert_routing_state()
    assert snapshot["evaluation_failures"] == 1, snapshot
    assert snapshot["deliveries_attempted"] == 0, (
        "no POST was attempted, so counting one would publish a delivery that "
        "did not happen"
    )
    assert snapshot["deliveries_failed"] == 0, (
        "an evaluation failure is not a delivery failure: failed without a "
        "matching attempted is a document disagreeing with itself"
    )
    stages = [row["stage"] for row in obs.list_alert_routing_errors()]
    assert stages == ["evaluation"], stages
