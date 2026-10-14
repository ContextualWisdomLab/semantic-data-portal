"""Counters must report real counts, and parsers must raise their documented type.

Measured at HEAD before these contracts:

* ``sdp_request_observations_total`` saturated at **25** while the ring buffer
  holds 500, because the gauge was ``len()`` of a page capped at 25. The audit and
  policy gauges saturated at 500 and the export-error gauge at 50 — every evidence
  counter on ``/metrics`` and ``/enterprise/observability`` was a page size.
* ``graph_store._relationship_label("broader\\n")`` raised ``KeyError('\\n')``
  instead of the ``ValueError`` its docstring promises: ``re.match`` with a
  trailing ``$`` also matches before a final newline, so the input passed the
  regex guard and then failed the alphabet lookup. ``POST /graph/edges`` turned
  that into a 500.
* ``/browse/{id}/preview`` coerced pagination with a bare ``int(...)`` inside a
  ``try`` catching only ``ValueError``/``KeyError``/``PermissionError``, so a JSON
  array, object or null for ``limit``/``offset`` produced a 500 instead of a 400.
* ``_sink_status`` routed only non-``file`` schemes through the redaction helper,
  so a ``file://`` sink published its absolute server path — and, for the UNC form
  the parser deliberately supports, an internal hostname.
"""

from __future__ import annotations

from pathlib import Path
import sys
import time
from typing import Any

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sdp import graph_store, observability as obs  # noqa: E402
from sdp.api import app  # noqa: E402

client = TestClient(app)


@pytest.fixture(autouse=True)
def _clean():
    obs.reset_request_observability()
    try:
        yield
    finally:
        obs.reset_request_observability()


def test_request_observation_gauge_is_not_a_page_size() -> None:
    """It was ``len(list_request_observations(limit=25))``, so it stuck at 25."""
    for index in range(60):
        obs.record_request_observation(
            {"event": "http_request", "status_code": 200, "n": index}, export=False
        )
    manifest = obs.build_observability_manifest()
    assert manifest["metrics"]["request_observations_total"] == 60

    metrics_text = obs.prometheus_metrics_text()
    assert "sdp_request_observations_total 60" in metrics_text


def test_export_error_gauge_is_not_a_page_size() -> None:
    for index in range(55):
        obs.record_observability_export_error(f"boom-{index}")
    manifest = obs.build_observability_manifest()
    # The buffer itself is a bounded ring (maxlen 50), so the honest count is the
    # buffer size, not the page size — and never more than the buffer holds.
    assert manifest["metrics"]["observability_export_errors_total"] == len(obs._EXPORT_ERRORS)
    assert manifest["metrics"]["observability_export_errors_total"] > 5


def test_relationship_label_raises_its_documented_error_type() -> None:
    """``$`` also matches before a trailing newline, so the guard let it through."""
    with pytest.raises(ValueError):
        graph_store._relationship_label("broader\n")
    with pytest.raises(ValueError):
        graph_store._relationship_label("bro der")
    assert graph_store._relationship_label("broader") == "BROADER"


def test_graph_edge_with_a_trailing_newline_is_a_400_not_a_500() -> None:
    response = client.post(
        "/graph/edges",
        json={"edge_type": "broader\n", "source_id": "고객", "target_id": "이탈", "actor": "admin"},
    )
    assert response.status_code == 400, response.text


@pytest.mark.parametrize("bad", [[], {}, [1], {"a": 1}, True])
def test_preview_pagination_type_error_is_a_400_not_a_500(bad) -> None:
    """A non-numeric JSON value for a pagination field is a bad request, not a 500."""
    response = client.post(
        "/browse/crm-customer-master/preview",
        json={"user": "analyst", "purpose": "analysis", "limit": bad},
    )
    assert response.status_code == 400, f"{bad!r} -> {response.status_code}"


def test_preview_pagination_null_means_unset() -> None:
    """``null`` is how many clients serialize an absent field, so it takes the
    default rather than being refused. The defect being fixed was the 500; this
    distinction is deliberate, not an oversight."""
    response = client.post(
        "/browse/crm-customer-master/preview",
        json={"user": "analyst", "purpose": "analysis", "limit": None, "offset": None},
    )
    assert response.status_code == 200, response.text


def test_file_sink_path_is_not_published(monkeypatch: pytest.MonkeyPatch) -> None:
    """A UNC file sink published its internal hostname — the very authority
    component the redaction helper exists to suppress."""
    # The UNC form is now refused outright rather than redacted: on POSIX a
    # ``file://host/path`` URL is not a path the container can write, and
    # folding the authority into the path is what made README's own documented
    # value resolve to the filesystem root. The manifest must still not publish
    # the hostname or the tenant segment in saying so.
    monkeypatch.setenv(
        "SDP_LOG_SINK_URL", "file://logs.internal.corp/sdp-prod/tenant-acme/requests.ndjson"
    )
    status = obs._sink_status()
    assert status["scheme"] == "file"
    assert status["configured"] is False
    assert status["invalid_configuration"]
    assert "logs.internal.corp" not in str(status)
    assert "tenant-acme" not in str(status)

    monkeypatch.setenv("SDP_LOG_SINK_URL", "file:///srv/sdp/private/requests.ndjson")
    local = obs._sink_status()
    assert "/srv/sdp/private" not in str(local)
    assert local["configured"] is True


# --- the sink must not bound API throughput when it is down ---------------


def test_sink_breaker_stops_paying_the_timeout_for_a_dead_sink(monkeypatch: pytest.MonkeyPatch) -> None:
    """Moving the export off the event loop removed the *serialization*, but every
    request still paid the full ``SDP_LOG_SINK_TIMEOUT_MS`` in a worker thread, and
    the same bounded anyio threadpool serves every sync route. Measured against a
    socket that accepts and never answers, 40 concurrent ``/health`` took 1.95s
    with a 500ms timeout, and one episode filled all 50 export-error slots.

    After a run of failures the breaker opens and the export is skipped until the
    cooldown expires, so a telemetry outage stops being an API throughput ceiling.
    """
    import time

    monkeypatch.setenv("SDP_LOG_SINK_URL", "https://sink.example/ingest")
    attempts = {"n": 0}

    def _always_fails(request, timeout=None):
        attempts["n"] += 1
        raise OSError("sink unreachable")

    monkeypatch.setattr(obs, "urlopen", _always_fails)

    for _ in range(obs.SINK_FAILURE_THRESHOLD):
        obs.record_request_observation({"event": "http_request"}, export=True)
    assert attempts["n"] == obs.SINK_FAILURE_THRESHOLD

    state = obs.sink_breaker_state()
    assert state["open"] is True
    assert state["consecutive_failures"] >= obs.SINK_FAILURE_THRESHOLD

    # Further observations are buffered but no longer touch the sink.
    before = attempts["n"]
    for _ in range(20):
        obs.record_request_observation({"event": "http_request"}, export=True)
    assert attempts["n"] == before, "the breaker is open; the sink must not be attempted"
    assert obs.sink_breaker_state()["skipped_exports"] == 20

    # The skip is reported, not silent.
    manifest = obs.build_observability_manifest()
    assert manifest["structured_logs"]["sink_breaker"]["open"] is True


def test_sink_breaker_closes_after_the_cooldown(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SDP_LOG_SINK_URL", "https://sink.example/ingest")

    def _always_fails(request, timeout=None):
        raise OSError("sink unreachable")

    monkeypatch.setattr(obs, "urlopen", _always_fails)
    for _ in range(obs.SINK_FAILURE_THRESHOLD):
        obs.record_request_observation({"event": "http_request"}, export=True)
    assert obs.sink_breaker_state()["open"] is True

    # Expire the cooldown rather than sleeping through it.
    monkeypatch.setattr(obs, "SINK_COOLDOWN_SECONDS", 0.0)
    obs._SINK_BREAKER["open_until"] = 0.0
    assert obs.sink_breaker_state()["open"] is False

    class _Ok:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(obs, "urlopen", lambda request, timeout=None: _Ok())
    obs.record_request_observation({"event": "http_request"}, export=True)
    assert obs.sink_breaker_state()["consecutive_failures"] == 0


# --------------------------------------------------------------------------- #
# A sink URL that carries its own credential must work, and the credential must
# not reach the connection host, the published status, or the retained errors.
#
# ``urllib.request.Request`` keeps the authority verbatim, userinfo included, as
# the connection host, so the documented push-URL form of every common log sink
# could not work. Measured before the repair with
# ``SDP_LOG_SINK_URL=https://sdp-ingest:s3cr3t-token@logs.example.net/push``:
#
#     urllib connects to   sdp-ingest:s3cr3t-token@logs.example.net
#     http.client         -> InvalidURL: nonnumeric port
#     _sink_status()      -> {"configured": true, "target": "logs.example.net"}
#
# Every export failed while the manifest reported a configured sink, and the
# InvalidURL message quotes the authority, so ``str(exc)`` carried the credential
# into the retained _EXPORT_ERRORS ring.
# --------------------------------------------------------------------------- #


def _sink_requests(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    """Capture what the export would actually put on the wire."""
    sent: list[Any] = []

    class _Ok:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def _capture(request, timeout=None):
        sent.append(request)
        return _Ok()

    monkeypatch.setattr(obs, "urlopen", _capture)
    return sent


def test_a_credential_bearing_sink_url_is_connectable(monkeypatch: pytest.MonkeyPatch) -> None:
    sent = _sink_requests(monkeypatch)
    monkeypatch.setenv(
        "SDP_LOG_SINK_URL", "https://sdp-ingest:s3cr3t-token@logs.example.net/loki/api/v1/push"
    )
    obs.record_request_observation({"event": "http_request"}, export=True)

    assert obs.sink_breaker_state()["consecutive_failures"] == 0, (
        f"the export failed: {obs.list_observability_export_errors()}"
    )
    assert len(sent) == 1
    request = sent[0]
    # The host urllib dials - this was the userinfo-bearing authority.
    assert request.host == "logs.example.net"
    assert "s3cr3t-token" not in request.full_url
    assert "sdp-ingest" not in request.full_url
    assert request.full_url == "https://logs.example.net/loki/api/v1/push"


def test_the_sink_credential_moves_into_the_authorization_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Where it belongs, and in both forms a sink URL expresses it."""
    import base64

    sent = _sink_requests(monkeypatch)
    monkeypatch.setenv("SDP_LOG_SINK_URL", "https://user:p%40ss%3Aword@logs.example.net/push")
    obs.record_request_observation({"event": "http_request"}, export=True)
    header = sent[-1].get_header("Authorization")
    assert header.startswith("Basic ")
    # Percent-decoded: a password containing @ or : has to be encoded in the URL.
    assert base64.b64decode(header.split()[1]).decode() == "user:p@ss:word"

    monkeypatch.setenv("SDP_LOG_SINK_URL", "https://deadbeefcafe@logs.example.net/push")
    obs.record_request_observation({"event": "http_request"}, export=True)
    assert sent[-1].get_header("Authorization") == "Bearer deadbeefcafe"

    monkeypatch.setenv("SDP_LOG_SINK_URL", "https://logs.example.net/push")
    obs.record_request_observation({"event": "http_request"}, export=True)
    assert sent[-1].get_header("Authorization") is None, (
        "a credential-free sink URL must not grow an empty Authorization header"
    )


def test_no_sink_credential_reaches_the_published_status_or_the_error_ring(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The reason the credential is split out before urllib sees it."""
    monkeypatch.setenv(
        "SDP_LOG_SINK_URL", "https://sdp-ingest:s3cr3t-token@logs.example.net/push"
    )

    def _fails(request, timeout=None):
        # A real failure quotes the URL it was given; that URL is now
        # credential-free, so the retained message cannot carry the secret.
        raise OSError(f"cannot reach {request.full_url}")

    monkeypatch.setattr(obs, "urlopen", _fails)
    obs.record_request_observation({"event": "http_request"}, export=True)

    published = str(obs.build_observability_manifest())
    retained = str(obs.list_observability_export_errors())
    for secret in ("s3cr3t-token", "sdp-ingest"):
        assert secret not in published, "the manifest is unauthenticated"
        assert secret not in retained, "export errors are retained for the process lifetime"


def test_an_unconnectable_http_sink_is_not_reported_as_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``configured`` means "set AND writable" for http, as it already did for file."""
    for sink_url, expected in (
        ("https:///push", "must name a host"),
        ("https://host:notaport/push", "port that is not a number"),
    ):
        monkeypatch.setenv("SDP_LOG_SINK_URL", sink_url)
        status = obs._sink_status()
        assert status["configured"] is False, sink_url
        assert expected in status["invalid_configuration"], status


# --------------------------------------------------------------------------- #
# A gate may only measure capabilities that exist - the alert path.
# --------------------------------------------------------------------------- #


def test_the_alert_webhook_is_declared_unimplemented_rather_than_required() -> None:
    """``SDP_ALERT_WEBHOOK_URL`` gated paid-pilot readiness and does nothing.

    Measured: its only read in the whole package is
    ``observability._sink_status`` taking ``bool()`` of it for the
    ``alert_webhook_configured`` field. Nothing posts to the URL, and nothing
    evaluates the alert conditions the manifest publishes next to it - so the
    gate could be cleared by setting a variable that routes nothing, exactly like
    ``SDP_EVIDENCE_RETENTION_DAYS`` before it.
    """
    from sdp_core.production import (
        enterprise_production_readiness_manifest,
        production_integration_registry,
    )

    integration = next(
        item
        for item in production_integration_registry()
        if item.id == "request_observability_export"
    )
    assert "SDP_ALERT_WEBHOOK_URL" not in integration.required_environment
    assert integration.declared_unimplemented_environment == ["SDP_ALERT_WEBHOOK_URL"]
    # The gap stays visible to a buyer rather than being deleted with the claim.
    manifest = enterprise_production_readiness_manifest({})
    assert manifest.unimplemented_environment["request_observability_export"] == [
        "SDP_ALERT_WEBHOOK_URL"
    ]
    assert "Alert routing is NOT implemented" in integration.buyer_risk
    # No acceptance criterion may still claim the capability.
    claims = [item for item in integration.acceptance_criteria if "alertable signals" in item]
    assert not claims, claims


def test_setting_the_alert_webhook_cannot_clear_the_readiness_gate() -> None:
    from sdp_core.production import enterprise_production_readiness_manifest

    base = {"SDP_LOG_SINK_URL": "file:///data/requests.jsonl", "SDP_REQUEST_ID_HEADER": "X-Request-Id"}
    without = enterprise_production_readiness_manifest(base)
    for value in ("https://alerts.example/hook", "banana", "0"):
        with_variable = enterprise_production_readiness_manifest(
            {**base, "SDP_ALERT_WEBHOOK_URL": value}
        )
        assert with_variable.paid_pilot_ready == without.paid_pilot_ready
        assert with_variable.missing_environment == without.missing_environment


def test_the_published_alert_rules_say_they_are_not_evaluated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A list named "alerts" beside ``alert_webhook_configured: true`` read as monitoring.

    The conditions are kept - they are the right ones and an operator can wire
    them into their own stack - but every surface now says so.
    """
    monkeypatch.setenv("SDP_ALERT_WEBHOOK_URL", "https://alerts.example/hook")
    manifest = obs.build_observability_manifest()

    assert manifest["alert_evaluation"] == "declared_not_evaluated"
    assert manifest["alert_routing"] == "declared_unimplemented"
    assert manifest["alerts"], "the declared conditions must stay published"
    for alert in manifest["alerts"]:
        assert alert["evaluated"] is False, alert
        assert alert["evaluation"] == "declared_not_evaluated", alert

    sink = manifest["structured_logs"]["sink"]
    assert sink["alert_webhook_configured"] is True
    assert sink["alert_webhook_routing"] == "declared_unimplemented", (
        "the configuration fact must not stand alone as a capability claim"
    )


def test_nothing_posts_to_the_alert_webhook() -> None:
    """The reason the variable is declared-unimplemented, pinned.

    ``test_every_required_variable_has_a_consumer`` did not catch this one and
    cannot: ``_sink_status`` *is* a consumer, it just reads the variable to
    report whether the variable is set. A name read solely for its own presence
    passes an "is it read anywhere" check while routing nothing - so the proof
    has to be about the capability, not the name.

    If a routing path is ever added, this fails and whoever added it moves the
    variable back into ``required_environment`` deliberately.
    """
    import pathlib

    source_root = pathlib.Path(obs.__file__).resolve().parents[1]
    mentions = {
        path.relative_to(source_root).as_posix(): [
            line.strip()
            for line in path.read_text().splitlines()
            if "SDP_ALERT_WEBHOOK_URL" in line
        ]
        for path in source_root.rglob("*.py")
        if "SDP_ALERT_WEBHOOK_URL" in path.read_text()
    }
    # Only the declaration site and the single presence check.
    assert sorted(mentions) == ["sdp/observability.py", "sdp_core/production.py"], mentions
    reads = [line for line in mentions["sdp/observability.py"] if "os.getenv" in line]
    assert len(reads) == 1, reads
    assert 'alert_webhook_url = os.getenv("SDP_ALERT_WEBHOOK_URL", "").strip()' in reads[0]


# --------------------------------------------------------------------------- #
# The breaker's missing third state.
#
# It had only closed and open. Once ``open_until`` elapsed, every request
# attempted the dead sink again, concurrently, each paying the full
# SDP_LOG_SINK_TIMEOUT_MS from the same bounded anyio threadpool that serves
# every sync route. Measured on the real async path against a sink that accepts
# and never answers, 20 concurrent requests arriving the instant the cooldown
# expired: 8 sink attempts with an 8-slot pool, 20 with an unbounded one - once
# per cooldown, for as long as the outage lasts.
# --------------------------------------------------------------------------- #


def _trip_the_breaker(monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
    monkeypatch.setenv("SDP_LOG_SINK_URL", "https://sink.example/ingest")
    attempts = {"n": 0}

    def _always_fails(request, timeout=None):
        attempts["n"] += 1
        raise OSError("sink unreachable")

    monkeypatch.setattr(obs, "urlopen", _always_fails)
    for _ in range(obs.SINK_FAILURE_THRESHOLD):
        obs.record_request_observation({"event": "http_request"}, export=True)
    assert obs.sink_breaker_state()["open"] is True
    attempts["n"] = 0
    return attempts


def test_a_cooldown_expiry_costs_one_probe_not_one_per_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = _trip_the_breaker(monkeypatch)

    # Expire the cooldown rather than sleeping through it.
    obs._SINK_BREAKER["open_until"] = 0.0
    assert obs.sink_breaker_state()["half_open"] is True

    for _ in range(20):
        obs.record_request_observation({"event": "http_request"}, export=True)
    assert attempts["n"] == 1, (
        "every request after the cooldown attempted the dead sink; the half-open "
        "state exists so exactly one does"
    )
    state = obs.sink_breaker_state()
    assert state["probes_started"] == 1
    assert state["open"] is True, "the failed probe must re-arm the cooldown"
    assert state["skipped_exports"] == 19


def test_each_cooldown_expiry_gets_a_fresh_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    """A failed probe must not latch the breaker shut forever."""
    attempts = _trip_the_breaker(monkeypatch)
    for expected in (1, 2, 3):
        obs._SINK_BREAKER["open_until"] = 0.0
        obs.record_request_observation({"event": "http_request"}, export=True)
        assert attempts["n"] == expected
        assert obs.sink_breaker_state()["probes_started"] == expected


def test_a_successful_probe_closes_the_breaker_for_everyone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Recovery must still be immediate, not one request per cooldown."""
    _trip_the_breaker(monkeypatch)

    class _Ok:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    sent = {"n": 0}

    def _recovered(request, timeout=None):
        sent["n"] += 1
        return _Ok()

    monkeypatch.setattr(obs, "urlopen", _recovered)
    obs._SINK_BREAKER["open_until"] = 0.0

    for _ in range(10):
        obs.record_request_observation({"event": "http_request"}, export=True)
    assert sent["n"] == 10, "the probe succeeded; every later export must go through"
    state = obs.sink_breaker_state()
    assert state["open"] is False
    assert state["half_open"] is False
    assert state["consecutive_failures"] == 0
    assert state["probe_in_flight"] is False


def test_only_one_of_many_concurrent_callers_probes(monkeypatch: pytest.MonkeyPatch) -> None:
    """The property the single-probe claim rests on, exercised concurrently.

    Exports run in worker threads via ``to_thread.run_sync``, so the
    read-decide-write on the breaker counters is genuinely concurrent and
    "exactly one probe" cannot hold without the lock.
    """
    import threading

    monkeypatch.setenv("SDP_LOG_SINK_URL", "https://sink.example/ingest")
    attempts = {"n": 0}
    counter_lock = threading.Lock()
    release = threading.Event()

    def _slow_dead_sink(request, timeout=None):
        with counter_lock:
            attempts["n"] += 1
        release.wait(timeout=5)  # hold the probe open while the others arrive
        raise OSError("sink unreachable")

    monkeypatch.setattr(obs, "urlopen", _slow_dead_sink)
    for _ in range(obs.SINK_FAILURE_THRESHOLD):
        release.set()
        obs.record_request_observation({"event": "http_request"}, export=True)
    release.clear()
    attempts["n"] = 0
    obs._SINK_BREAKER["open_until"] = 0.0

    threads = [
        threading.Thread(
            target=obs.record_request_observation, args=({"event": "http_request"},)
        )
        for _ in range(20)
    ]
    for thread in threads:
        thread.start()
    # The probe is blocked in the sink; every other caller must have skipped.
    for _ in range(500):
        if obs.sink_breaker_state()["skipped_exports"] >= 19:
            break
        time.sleep(0.01)
    assert attempts["n"] == 1, attempts
    assert obs.sink_breaker_state()["probe_in_flight"] is True
    release.set()
    for thread in threads:
        thread.join(timeout=5)
    assert attempts["n"] == 1, "a second caller probed while the first was in flight"


# --------------------------------------------------------------------------- #
# A published count must not be the size of the page it was read from.
#
# ``sdp_request_observations_total`` had this defect and was fixed; the audit and
# policy gauges were read the same way and were left behind. Measured with 700
# governed mutations in the ledger:
#
#     catalog._AUDIT_LOG                               700
#     /metrics sdp_audit_events_observed_total          500
#     /enterprise/evidence-pack audit_event_count       500
#     /enterprise/observability audit_events_observed   500
#
# Three published surfaces reported 500 for 700 events, each taking ``len()`` of
# a ``list_*(limit=500)`` page. These are the numbers a procurement reader uses
# to judge whether the governance trail is real.
# --------------------------------------------------------------------------- #


def _flood_audit_events(count: int) -> int:
    from sdp import catalog

    for index in range(count):
        catalog.ingest_event(
            event_type="probe.event",
            actor="admin",
            dataset_id="crm-event",
            decision="allowed",
            reason="probe",
            decision_id=f"count-probe-{index}",
            details={},
        )
    return len(catalog._AUDIT_LOG)


def test_the_audit_gauge_exceeds_the_page_it_is_read_from() -> None:
    real = _flood_audit_events(700)
    assert real >= 700, real

    metrics = {
        line.split()[0]: float(line.split()[1])
        for line in client.get("/metrics").text.splitlines()
        if line and not line.startswith("#") and len(line.split()) == 2
    }
    assert metrics["sdp_audit_events_observed_total"] == real, metrics

    pack = client.get("/enterprise/evidence-pack").json()
    assert pack["audit_event_count"] == real, pack["audit_event_count"]
    assert pack["audit_event_count_is_lower_bound"] is False

    observability = client.get("/enterprise/observability").json()["metrics"]
    assert observability["audit_events_observed_total"] == real


def test_a_saturated_count_is_declared_a_lower_bound(monkeypatch: pytest.MonkeyPatch) -> None:
    """The ceiling exists for the store-backed path; hitting it must not lie.

    A count that reaches its bound is published as a lower bound rather than as
    the count - the rule this product applies to every truncated list.
    """
    from sdp import catalog

    _flood_audit_events(20)
    monkeypatch.setattr(catalog, "EVIDENCE_COUNT_CEILING", 5)
    count, is_lower_bound = catalog.count_audit_events()
    assert count == 5
    assert is_lower_bound is True


def test_no_published_count_is_the_length_of_a_paged_read() -> None:
    """The enumeration that catches the next instance, by AST rather than by eye.

    The defect shape is: a variable assigned from ``list_*(..., limit=N)`` whose
    ``len()`` is then published under a ``*_count`` or ``*_total`` key. It has
    now appeared three times (request observations, audit events, policy
    decisions) and been fixed twice, each time for the surface that was
    reported.
    """
    import ast
    import pathlib

    source_root = pathlib.Path(__file__).resolve().parents[1] / "src"
    offenders: list[str] = []

    for path in source_root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        paged: set[str] = set()
        for node in ast.walk(tree):
            # X = list_something(..., limit=...)
            if (
                isinstance(node, ast.Assign)
                and isinstance(node.value, ast.Call)
                and any(kw.arg == "limit" for kw in node.value.keywords)
            ):
                callee = node.value.func
                name = getattr(callee, "id", None) or getattr(callee, "attr", None) or ""
                if name.startswith("list_"):
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            paged.add(target.id)
        if not paged:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            for key, value in zip(node.keys, node.values):
                if not isinstance(key, ast.Constant) or not isinstance(key.value, str):
                    continue
                if not (key.value.endswith("_count") or key.value.endswith("_total")):
                    continue
                if (
                    isinstance(value, ast.Call)
                    and getattr(value.func, "id", "") == "len"
                    and value.args
                    and isinstance(value.args[0], ast.Name)
                    and value.args[0].id in paged
                ):
                    offenders.append(
                        f"{path.relative_to(source_root)}:{key.lineno} "
                        f"{key.value} = len({value.args[0].id}) (a paged read)"
                    )

    assert not offenders, (
        "these published counts are the size of the page they were read from, "
        f"so they saturate instead of counting: {offenders}"
    )
