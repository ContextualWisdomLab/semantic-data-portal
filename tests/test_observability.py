"""Observability telemetry seam: header extraction, log-sink export (file/http),
and export-error recording.

Covers the ops/security-relevant sink paths of ``observability.py`` — including
the http(s) POST sink (SSRF-adjacent) via a mocked ``urlopen`` and the file sink
via a temp path — plus the case-insensitive header lookup and its defensive
fallbacks. No network or external sink is contacted.
"""

from __future__ import annotations

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


def test_file_sink_path_netloc_only_and_with_path() -> None:
    netloc_only = obs._file_sink_path("file://logs", urlparse("file://logs"))
    assert netloc_only == Path("logs")
    with_netloc_path = obs._file_sink_path("file://host/var/log", urlparse("file://host/var/log"))
    assert str(with_netloc_path).startswith("//host/")


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
    assert other["scheme"] == "tcp" and other["target"] == "tcp://opaque-target"


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
