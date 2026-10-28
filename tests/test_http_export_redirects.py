"""A redirecting sink or webhook must not be handed the credential again.

Both http(s) export paths in ``sdp.observability`` lift the credential out of
the configured URL's userinfo into an ``Authorization`` header, because urllib
cannot connect to an authority that contains one. ``urllib.request.urlopen``
then follows a 301/302/303 answer to a POST, rewrites it as a GET, and re-sends
every header it was given to whatever host the response's ``Location`` names.

Measured on the default opener before the repair, two loopback servers, the
first answering 302 with ``Location: http://127.0.0.2:<port>/exfiltrated``::

    POST /webhook      Host 127.0.0.1:35661  Authorization: Basic c2VjcmV0...
    GET  /exfiltrated  Host 127.0.0.2:39469  Authorization: Basic c2VjcmV0...

Three separate consequences, which is why this is its own family: the
operator's credential reached a second authority; the alert body was dropped
with the method, so nothing was delivered; and the exchange ended 204, so
``_deliver_alert`` counted it ``succeeded`` and the manifest published a
delivery that never happened.

These tests let the **real** opener run against loopback servers. The
disclosure family deliberately does not - it replaces the seam to see what the
seam is handed - so the two cannot be merged: this one is about what urllib
does with a response, which a double cannot show.

The second server here is a second port on 127.0.0.1 rather than a second host.
A port is part of an origin, so it is a different authority for every purpose
this test is about, and it needs no non-default loopback alias to be bindable.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest

from sdp import observability as obs


class _Recorder(BaseHTTPRequestHandler):
    """The host a redirect names. Records every request, answers 204."""

    arrivals: list[dict[str, Any]] = []

    def _record(self, method: str) -> None:
        """Retain one arrival, whatever method urllib used to make it."""
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        type(self).arrivals.append(
            {
                "method": method,
                "host": self.headers.get("Host"),
                "authorization": self.headers.get("Authorization"),
                "path": self.path,
                "body": body.decode("utf-8", "replace"),
            }
        )
        self.send_response(204)
        self.end_headers()

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler's spelling
        """Record a POST that arrived here."""
        self._record("POST")

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler's spelling
        """Record a GET that arrived here - what a followed 302 becomes."""
        self._record("GET")

    def log_message(self, *args: Any) -> None:
        """Keep the handler quiet under pytest."""


class _Redirector(BaseHTTPRequestHandler):
    """The configured endpoint. Answers 302 pointing at the recorder."""

    location = ""
    arrivals: list[dict[str, Any]] = []

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler's spelling
        """Answer the export with a redirect to another authority."""
        length = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(length)
        type(self).arrivals.append({"authorization": self.headers.get("Authorization")})
        self.send_response(302)
        self.send_header("Location", type(self).location)
        self.end_headers()

    def log_message(self, *args: Any) -> None:
        """Keep the handler quiet under pytest."""


@pytest.fixture
def redirecting_endpoint() -> Any:
    """Two loopback servers: one redirects to the other, which records.

    Yields the configured URL template, which the test fills with a credential.
    """
    _Recorder.arrivals = []
    _Redirector.arrivals = []
    recorder = ThreadingHTTPServer(("127.0.0.1", 0), _Recorder)
    redirector = ThreadingHTTPServer(("127.0.0.1", 0), _Redirector)
    _Redirector.location = f"http://127.0.0.1:{recorder.server_address[1]}/exfiltrated"
    threads = [
        threading.Thread(target=server.serve_forever, daemon=True)
        for server in (recorder, redirector)
    ]
    for thread in threads:
        thread.start()
    try:
        yield f"127.0.0.1:{redirector.server_address[1]}"
    finally:
        for server in (recorder, redirector):
            server.shutdown()
            server.server_close()
        for thread in threads:
            thread.join(2)


def test_the_alert_credential_is_not_re_sent_to_the_host_a_redirect_names(
    monkeypatch: pytest.MonkeyPatch,
    redirecting_endpoint: str,
) -> None:
    """The redirect is refused, nothing reaches the second authority.

    Drives the real delivery function rather than a firing rule, so the
    assertion is about the opener and not about the latch.
    """
    obs.reset_alert_routing()
    monkeypatch.setenv(
        "SDP_ALERT_WEBHOOK_URL",
        f"http://sdp-alerts:s3cr3t@{redirecting_endpoint}/webhook",
    )
    obs._deliver_alert(
        "policy_audit_gap",
        f"http://sdp-alerts:s3cr3t@{redirecting_endpoint}/webhook",
        json.dumps({"rule_id": "policy_audit_gap"}).encode("utf-8"),
        obs._ALERT_ROUTING["generation"],
    )

    assert _Redirector.arrivals, "the configured endpoint was never reached"
    assert _Redirector.arrivals[0]["authorization"] == "Basic c2RwLWFsZXJ0czpzM2NyM3Q="
    assert _Recorder.arrivals == [], (
        "the host named by the webhook's own Location header received a "
        f"request: {_Recorder.arrivals}"
    )

    state = obs.alert_routing_state()
    assert state["deliveries_attempted"] == 1
    assert state["deliveries_succeeded"] == 0, (
        "a redirect is not a delivery: the body was never accepted"
    )
    assert state["deliveries_failed"] == 1
    assert [row["error_type"] for row in obs.list_alert_routing_errors()] == [
        "SinkRedirectRefused"
    ]


def test_the_sink_credential_is_not_re_sent_to_the_host_a_redirect_names(
    monkeypatch: pytest.MonkeyPatch,
    redirecting_endpoint: str,
) -> None:
    """The same for the log sink, which carried this defect for longer.

    The sink is the older of the two paths and the userinfo lift lives in its
    helper, so a repair on the alert path alone would have left the original
    leak open.
    """
    obs.reset_request_observability()
    monkeypatch.setenv(
        "SDP_LOG_SINK_URL",
        f"http://sdp-ingest:s3cr3t@{redirecting_endpoint}/push",
    )
    monkeypatch.setenv("SDP_LOG_SINK_TIMEOUT_MS", "4000")
    obs.record_request_observation(
        {"route": "/catalog/datasets", "status_code": 200, "duration_ms": 1.0}
    )

    assert _Redirector.arrivals, "the configured sink was never reached"
    assert _Recorder.arrivals == [], (
        "the host named by the sink's own Location header received a request: "
        f"{_Recorder.arrivals}"
    )
    recorded = obs.list_observability_export_errors()
    assert len(recorded) == 1, recorded
    message = recorded[0]["message"]
    assert "redirect" in message
    assert "s3cr3t" not in message and "sdp-ingest" not in message, (
        "the retained export failure carries the sink credential, which is the "
        f"defect _http_sink_request_parts closed once already: {message}"
    )
    assert obs.count_observability_export_errors() == 1


def test_the_refusal_carries_no_url_and_no_credential() -> None:
    """The refusal message may be read by an operator; it names neither.

    ``_EXPORT_ERRORS`` and ``_ALERT_ERRORS`` retain a type and a stage rather
    than a message, but the message reaches logs, so it is checked here too.
    """
    with pytest.raises(obs.SinkRedirectRefused) as raised:
        obs._RefuseRedirect().redirect_request(
            None, None, 302, "Found", {}, "http://elsewhere.example/stolen"
        )
    text = str(raised.value)
    assert "elsewhere.example" not in text
    assert "s3cr3t" not in text
    assert "redirect" in text
