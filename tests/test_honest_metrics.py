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
