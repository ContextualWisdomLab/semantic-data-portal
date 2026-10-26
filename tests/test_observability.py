"""Observability telemetry seam: header extraction, log-sink export (file/http),
and export-error recording.

Covers the ops/security-relevant sink paths of ``observability.py`` — including
the http(s) POST sink (SSRF-adjacent) via a mocked ``urlopen`` and the file sink
via a temp path — plus the case-insensitive header lookup and its defensive
fallbacks. No network or external sink is contacted.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
from urllib.parse import urlparse

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sdp import observability as obs  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_buffers():
    """Reset the in-process observation/export ring buffers around each test."""
    obs.reset_request_observability()
    try:
        yield
    finally:
        obs.reset_request_observability()


# --- _header_value -------------------------------------------------------


def test_header_value_default_for_empty_headers() -> None:
    assert obs._header_value(None, "X-Y", "dflt") == "dflt"
    assert obs._header_value({}, "X-Y", "dflt") == "dflt"


def test_header_value_direct_and_case_insensitive() -> None:
    assert obs._header_value({"X-Y": "v"}, "X-Y") == "v"
    # get() misses the differently-cased key; the items() fallback matches.
    assert obs._header_value({"x-y": "lower"}, "X-Y") == "lower"


def test_header_value_attributeerror_fallback_returns_default() -> None:
    """A headers object with neither usable get nor items falls back to default."""
    assert obs._header_value(["not-a-mapping"], "X-Y", "dflt") == "dflt"


# --- _file_sink_path -----------------------------------------------------


def test_file_sink_path_refuses_every_form_that_cannot_be_written() -> None:
    """These forms used to resolve to a path, and the wrong one.

    The authority was folded into the path and a scheme-less value defaulted to
    ``file``, so the shipped container wrote - or rather failed to write -
    somewhere nobody intended:

        file://.local/sdp-requests.jsonl  ->  //.local/sdp-requests.jsonl
        configured                        ->  configured   (a file in the CWD)
        .local/x.jsonl                    ->  .local/x.jsonl

    README documented the first one. The image runs ``USER 10001`` with only
    ``/data`` writable, so every export raised ``PermissionError``, the breaker
    opened after five, and the manifest still said ``implemented``.
    """
    for value in (
        "file://logs",
        "file://host/var/log",
        "file://.local/sdp-requests.jsonl",
        "configured",
        ".local/x.jsonl",
        "relative/path.jsonl",
    ):
        with pytest.raises(obs.SinkConfigurationError):
            obs._file_sink_path(value, urlparse(value))


def test_file_sink_path_accepts_an_absolute_file_url() -> None:
    assert obs._file_sink_path(
        "file:///data/sdp-requests.jsonl", urlparse("file:///data/sdp-requests.jsonl")
    ) == Path("/data/sdp-requests.jsonl")


# --- _sink_status --------------------------------------------------------


def test_sink_status_unconfigured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SDP_LOG_SINK_URL", raising=False)
    status = obs._sink_status()
    assert status["configured"] is False
    assert status["scheme"] == "memory"


def test_sink_status_http_and_other_scheme(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SDP_LOG_SINK_URL", "https://sink.example/ingest")
    status = obs._sink_status()
    assert status["configured"] is True and status["scheme"] == "https"
    assert status["target"] == "sink.example"
    monkeypatch.setenv("SDP_LOG_SINK_URL", "tcp://opaque-target")
    other = obs._sink_status()
    # The scheme is reported as written, but the target is reduced to host(:port)
    # for every scheme: echoing the raw URL would publish userinfo and query
    # credentials on an unauthenticated manifest.
    assert other["scheme"] == "tcp" and other["target"] == "opaque-target"


def test_sink_status_never_publishes_sink_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """The manifest that carries this field is unauthenticated, and
    ``urlparse().netloc`` keeps the userinfo component, so reporting netloc
    publishes any credential an operator put in the sink URL.
    """
    monkeypatch.setenv(
        "SDP_LOG_SINK_URL",
        "https://sdp-ingest:s3cr3t-token@logs.example.net/loki/api/v1/push",
    )
    status = obs._sink_status()
    assert status["target"] == "logs.example.net"
    assert "s3cr3t-token" not in json.dumps(status)

    monkeypatch.setenv("SDP_LOG_SINK_URL", "syslog://user:pw@logs.example.net/path?api-key=TOPSECRET")
    other = obs._sink_status()
    assert other["target"] == "logs.example.net"
    assert "TOPSECRET" not in json.dumps(other)
    assert "user:pw" not in json.dumps(other)


def test_sink_status_keeps_port_and_survives_a_malformed_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A port identifies the sink and is kept; an unparsable port must not raise."""
    monkeypatch.setenv("SDP_LOG_SINK_URL", "https://logs.example.net:8443/push")
    assert obs._sink_status()["target"] == "logs.example.net:8443"

    monkeypatch.setenv("SDP_LOG_SINK_URL", "https://logs.example.net:notaport/push")
    assert obs._sink_status()["target"] == "logs.example.net"

    monkeypatch.setenv("SDP_LOG_SINK_URL", "https://")
    assert obs._sink_status()["target"] == "redacted"


# --- _export_to_sink -----------------------------------------------------


def test_export_to_sink_writes_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sink = tmp_path / "nested" / "obs.ndjson"
    monkeypatch.setenv("SDP_LOG_SINK_URL", sink.as_uri())
    obs._export_to_sink({"event": "http_request", "status_code": 200})
    body = sink.read_text(encoding="utf-8").strip()
    assert '"event"' in body and '"status_code"' in body


def test_export_to_sink_http_post_is_invoked(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SDP_LOG_SINK_URL", "https://sink.example/ingest")
    captured = {}

    class _FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def _fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["body"] = request.data
        return _FakeResp()

    monkeypatch.setattr(obs, "urlopen", _fake_urlopen)
    obs._export_to_sink({"event": "http_request", "route": "/parse"})
    assert captured["url"] == "https://sink.example/ingest"
    assert b"http_request" in captured["body"]


def test_export_to_sink_rejects_unsupported_scheme(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SDP_LOG_SINK_URL", "ftp://sink.example/ingest")
    with pytest.raises(ValueError):
        obs._export_to_sink({"event": "http_request"})


# --- record_* ------------------------------------------------------------


def test_record_export_error_accepts_str_and_dict() -> None:
    obs.record_observability_export_error("boom")
    obs.record_observability_export_error({"message": "structured", "code": "x"})
    errors = obs.list_observability_export_errors()
    assert errors[-2]["message"] == "boom" and "timestamp" in errors[-2]
    assert errors[-1]["code"] == "x" and "timestamp" in errors[-1]


def test_record_request_observation_export_false_skips_sink(monkeypatch: pytest.MonkeyPatch) -> None:
    """With export=False, the observation is buffered but the sink is never touched."""
    def _boom(*_a, **_k):
        raise AssertionError("sink must not be called when export=False")

    monkeypatch.setattr(obs, "_export_to_sink", _boom)
    obs.record_request_observation({"event": "http_request", "status_code": 200}, export=False)
    assert obs.list_request_observations()[-1]["status_code"] == 200


def test_record_request_observation_records_sink_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """A sink failure is swallowed and captured as an export error, not raised."""
    def _boom(_obs):
        raise RuntimeError("sink down")

    monkeypatch.setattr(obs, "_export_to_sink", _boom)
    obs.record_request_observation({"event": "http_request"}, export=True)
    assert any("sink down" in e.get("message", "") for e in obs.list_observability_export_errors())


# --- the request path must not block the event loop on the sink -----------


def test_sink_export_does_not_serialize_concurrent_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    """The observability middleware is ``async def`` and exported to the sink with
    a blocking ``urlopen``/file write, so the export ran on the event loop thread:
    every concurrent request queued behind the sink round-trip. Measured before
    this contract, 8 concurrent ``/health`` calls against a 0.2s sink took 1.63s
    — 8.1x one round-trip, fully serialized.

    The threshold is deliberately loose (half of fully-serialized) so the test
    measures the blocking property rather than machine speed.
    """
    import asyncio
    import time

    import httpx

    from sdp.api import app

    sink_delay = 0.2
    concurrency = 8
    monkeypatch.setenv("SDP_LOG_SINK_URL", "https://sink.example/ingest")

    class _FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def _blocking_urlopen(request, timeout=None):
        time.sleep(sink_delay)
        return _FakeResp()

    monkeypatch.setattr(obs, "urlopen", _blocking_urlopen)

    async def _drive() -> float:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            started = time.monotonic()
            responses = await asyncio.gather(*(client.get("/health") for _ in range(concurrency)))
            elapsed = time.monotonic() - started
        assert all(response.status_code == 200 for response in responses)
        return elapsed

    elapsed = asyncio.run(_drive())
    fully_serialized = sink_delay * concurrency
    assert elapsed < fully_serialized / 2, (
        f"{concurrency} concurrent requests took {elapsed:.2f}s against a "
        f"{sink_delay:.2f}s sink; the export is still blocking the event loop"
    )
    # Every request is still exported - offloading must not drop observations.
    assert len(obs.list_request_observations()) >= concurrency


def test_record_request_observation_async_export_false_skips_sink(monkeypatch: pytest.MonkeyPatch) -> None:
    """The async recorder honours export=False exactly as the sync one does."""
    import asyncio

    def _boom(*_a, **_k):
        raise AssertionError("sink must not be called when export=False")

    monkeypatch.setattr(obs, "_export_to_sink", _boom)
    asyncio.run(obs.record_request_observation_async({"event": "http_request", "status_code": 204}, export=False))
    assert obs.list_request_observations()[-1]["status_code"] == 204


def test_record_request_observation_async_records_sink_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """A sink failure inside the worker thread is captured, not raised into the
    request path — the response must not fail because telemetry did."""
    import asyncio

    def _boom(_obs):
        raise RuntimeError("async sink down")

    monkeypatch.setattr(obs, "_export_to_sink", _boom)
    asyncio.run(obs.record_request_observation_async({"event": "http_request"}, export=True))
    assert any("async sink down" in e.get("message", "") for e in obs.list_observability_export_errors())


def test_manifest_does_not_publish_a_per_request_activity_feed(monkeypatch: pytest.MonkeyPatch) -> None:
    """``/enterprise/observability`` is served with no actor, and the manifest
    published the last 10 request observations verbatim under ``recent_requests``.
    Each carries ``route`` (which embeds the dataset id), plus the caller's
    ``actor`` and ``tenant_id``, so one tenant's governed-access activity was
    readable by anyone. Measured: an unauthenticated GET mentioned
    ``acme-payroll`` after another tenant previewed it.

    This cannot be fixed by filtering on the observation's ``tenant_id``: that
    value comes from the caller-supplied ``X-SDP-Tenant`` header
    (``observability.build_request_observation``), so it is self-asserted by the
    very caller whose rows would be filtered. The per-request detail is therefore
    withheld from the unauthenticated manifest and only aggregates are published —
    which is what the manifest's buyer-evidence purpose actually needs.
    """
    obs.record_request_observation(
        {
            "event": "http_request",
            "route": "/browse/acme-payroll/preview",
            "actor": "someone@acme.example",
            "tenant_id": "acme-bank",
            "status_code": 200,
        },
        export=False,
    )
    manifest = obs.build_observability_manifest()
    rendered = json.dumps(manifest, ensure_ascii=False, default=str)

    assert "acme-payroll" not in rendered
    assert "someone@acme.example" not in rendered
    assert "recent_requests" not in manifest

    # The evidence the manifest exists for is still there.
    assert manifest["metrics"]["request_observations_total"] >= 1
    assert manifest["structured_logs"]["fields"]


# --------------------------------------------------------------------------- #
# The ring buffer was bounded in rows but not in bytes.
#
# uvicorn accepts a header of roughly 64 KB, and the caller-supplied tenant,
# actor and evidence-id values were copied verbatim. Measured with 500
# ``GET /health`` requests - no credentials, no body, nothing reaching policy
# evaluation - carrying 60,000-character headers and twenty evidence ids:
#
#     rows retained 500   bytes retained 70.2 MB   largest row 137 KB
#
# The deque never shrinks, so that is pinned for the process lifetime, and with
# a sink configured the same bytes leave as POSTs.
# --------------------------------------------------------------------------- #


def test_a_caller_cannot_pin_unbounded_bytes_in_the_observation_buffer() -> None:
    obs.reset_request_observability()
    oversized = "x" * 60_000
    observation = obs.build_request_observation(
        method="GET",
        route="/health",
        status_code=200,
        latency_ms=1.0,
        headers={
            "X-SDP-Tenant": oversized,
            "X-SDP-Actor": oversized,
            # Ignored now, and that is the point: a caller cannot put anything
            # into ``evidence_ids``, oversized or not. The field used to be read
            # from this header, which let the caller a log line is about choose
            # the line's correlation key - see
            # ``tests/test_request_evidence_correlation.py``.
            "X-SDP-Evidence-Ids": ",".join([oversized] * 100),
        },
        request_id=oversized,
        # Server-recorded ids, which is the only source left. The bound still
        # matters: one request can record many evidence rows.
        evidence_ids=[oversized] * 100,
    )
    for field in ("request_id", "tenant_id", "actor"):
        assert len(observation[field]) <= obs.MAX_OBSERVATION_FIELD_CHARS, field
        assert observation[field].endswith("...[truncated]"), field
    assert len(observation["evidence_ids"]) == obs.MAX_OBSERVATION_EVIDENCE_IDS
    for item in observation["evidence_ids"]:
        assert len(item) <= obs.MAX_OBSERVATION_FIELD_CHARS
    # Declared rather than silently dropped, like every other bounded list here.
    assert observation["withheld_evidence_id_count"] == 100 - obs.MAX_OBSERVATION_EVIDENCE_IDS

    row_bytes = len(repr(observation))
    ceiling = (3 + obs.MAX_OBSERVATION_EVIDENCE_IDS) * obs.MAX_OBSERVATION_FIELD_CHARS + 512
    assert row_bytes <= ceiling, f"{row_bytes} > {ceiling}"


def test_an_ordinary_observation_is_not_truncated() -> None:
    """The cap must not mark a normal value as cut."""
    observation = obs.build_request_observation(
        method="GET",
        route="/health",
        status_code=200,
        latency_ms=1.0,
        headers={
            "X-SDP-Tenant": "demo",
            "X-SDP-Actor": "analyst",
            "X-SDP-Evidence-Ids": "forged-1, forged-2",
        },
        request_id="sdp-abc",
        evidence_ids=["d-1", "d-2"],
    )
    assert observation["tenant_id"] == "demo"
    assert observation["actor"] == "analyst"
    assert observation["evidence_ids"] == ["d-1", "d-2"]
    # The header is not a source for this field any more.
    assert "forged-1" not in observation["evidence_ids"]
    assert "withheld_evidence_id_count" not in observation
