from __future__ import annotations

import json
import os
import threading
import time
from base64 import b64encode
from collections import deque
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse, urlunsplit
from urllib.request import Request as UrlRequest, urlopen
from urllib.request import url2pathname
from uuid import uuid4

from anyio import to_thread

from sdp_core import enterprise_controls_manifest

from .catalog import count_audit_events, list_audit_events, list_datasets
from .evidence import count_policy_decisions, list_policy_decisions


_REQUEST_OBSERVATIONS: deque[dict[str, Any]] = deque(maxlen=500)
_EXPORT_ERRORS: deque[dict[str, Any]] = deque(maxlen=50)


def request_id_header() -> str:
    return os.getenv("SDP_REQUEST_ID_HEADER", "X-Request-Id")


def _header_value(headers: Any, name: str, default: str | None = None) -> str | None:
    if not headers:
        return default

    value = headers.get(name) if hasattr(headers, "get") else None
    if value:
        return str(value)

    lower_name = name.lower()
    try:
        for key, candidate in headers.items():
            if str(key).lower() == lower_name:
                return str(candidate)
    except AttributeError:
        return default

    return default


def request_id_from_headers(headers: Any) -> str:
    return _header_value(headers, request_id_header()) or f"sdp-{uuid4().hex}"


class SinkConfigurationError(ValueError):
    """The configured observability sink can never be written."""


def _file_sink_path(sink_url: str, parsed: Any) -> Path:
    """Resolve a ``file://`` sink to an absolute path, or refuse the configuration.

    This folded a ``file://`` URL's authority into the path
    (``raw_path = f"//{parsed.netloc}{raw_path}"``), and ``_export_to_sink``
    defaulted a scheme-less value to ``file``. So README's own documented value
    did not mean what it reads as:

        file://.local/sdp-requests.jsonl  ->  //.local/sdp-requests.jsonl
        configured                        ->  configured   (a file in the CWD)
        .local/x.jsonl                    ->  .local/x.jsonl

    The first is ``.local`` at the **filesystem root**. The shipped image runs
    ``USER 10001:10001`` with only ``/data`` writable, so the open raises
    ``PermissionError`` on every request, the breaker opens after five, and the
    rest are dropped silently - while ``GET /enterprise/observability`` kept
    reporting ``structured_logs.status: "implemented"`` and a configured sink.
    The reason lived only in ``_EXPORT_ERRORS``, which the manifest withholds,
    so no surface could tell an operator the log was empty. The relative forms
    also explain the stray files that appeared in the repository root during
    development.

    Failing closed at resolution time, with the reason named, is the point: a
    sink that cannot be written is a configuration error, not a per-request
    exception to swallow.
    """
    if os.name == "nt":
        # Windows keeps the UNC and drive-letter forms the original supported.
        if parsed.netloc and not parsed.path:
            return Path(url2pathname(parsed.netloc))
        raw_path = url2pathname(parsed.path or sink_url)
        if len(raw_path) >= 3 and raw_path[0] in {"\\", "/"} and raw_path[2] == ":":
            raw_path = raw_path[1:]
        if parsed.netloc:
            raw_path = f"//{parsed.netloc}{raw_path}"
        return Path(raw_path)

    # None of these messages echo the configured value. ``_sink_status`` is
    # published unauthenticated, and the value carries the sink's internal host
    # and path - the authority component ``_redacted_sink_target`` exists to
    # suppress. The first draft of this repair interpolated ``sink_url`` and a
    # retained test caught it publishing ``logs.internal.corp`` and a tenant
    # path segment.
    if not parsed.scheme:
        raise SinkConfigurationError(
            "SDP_LOG_SINK_URL must name a scheme: use file:///absolute/path for a "
            "local file sink, or an http(s) URL"
        )
    if parsed.netloc:
        raise SinkConfigurationError(
            "a file:// sink must have an empty authority: file://host/path is not "
            "supported, and file://relative/path is not a relative path"
        )
    raw_path = url2pathname(parsed.path or "")
    path = Path(raw_path)
    if not path.is_absolute():
        raise SinkConfigurationError(
            "SDP_LOG_SINK_URL must be an absolute path (file:///data/...)"
        )
    return path


def _http_sink_request_parts(sink_url: str, parsed: Any) -> tuple[str, dict[str, str]]:
    """Resolve an ``http(s)`` sink to a connectable URL plus request headers.

    The whole configured value was handed to ``urlopen``, and
    ``urllib.request.Request`` keeps the authority verbatim - userinfo
    included - as the connection host. So the documented form of a push URL for
    every common log sink (Loki, Elastic, a signed webhook) could not work.
    Measured before the repair with
    ``SDP_LOG_SINK_URL=https://sdp-ingest:s3cr3t-token@logs.example.net/push``::

        urllib connects to      sdp-ingest:s3cr3t-token@logs.example.net
        http.client            -> InvalidURL: nonnumeric port
        _sink_status()         -> {"configured": true, "target": "logs.example.net"}

    Every export failed, the breaker opened after five, and the manifest kept
    reporting a configured sink - the exact "published number disagrees with the
    code enforcing it" shape this product exists to refuse. Worse, the
    ``InvalidURL`` message quotes the authority, so ``str(exc)`` carried the sink
    credential into the retained ``_EXPORT_ERRORS`` ring. Removing the userinfo
    before the value reaches urllib closes that too.

    The credential moves to the header it belongs in: ``Basic`` when a password
    is present, ``Bearer`` when the userinfo is a single token. Both
    subcomponents are percent-decoded, because a password containing ``@`` or
    ``:`` has to be encoded in the URL. The returned URL is rebuilt from the
    parsed parts with the userinfo and fragment dropped, so nothing downstream
    re-derives them.
    """
    try:
        host = parsed.hostname
    except ValueError as exc:  # pragma: no cover - defensive: malformed authority
        raise SinkConfigurationError(
            "SDP_LOG_SINK_URL has an authority that cannot be parsed as a host"
        ) from exc
    if not host:
        raise SinkConfigurationError(
            "an http(s) SDP_LOG_SINK_URL must name a host (https://host/path)"
        )
    try:
        port = parsed.port
    except ValueError as exc:
        raise SinkConfigurationError(
            "SDP_LOG_SINK_URL has a port that is not a number"
        ) from exc

    headers = {"Content-Type": "application/json"}
    username = unquote(parsed.username) if parsed.username else ""
    password = unquote(parsed.password) if parsed.password else ""
    if password:
        credential = b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
        headers["Authorization"] = f"Basic {credential}"
    elif username:
        headers["Authorization"] = f"Bearer {username}"

    netloc = f"{host}:{port}" if port is not None else host
    url = urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, ""))
    return url, headers


# A caller-supplied observation field is bounded in length, and the evidence-id
# list in count. The ring buffer is bounded at 500 *rows* and the rows were
# unbounded in bytes: uvicorn accepts a header of roughly 64 KB, so one
# unauthenticated request produced a six-figure row. Measured with 500
# ``GET /health`` requests - no credentials, no body, nothing that reaches
# policy evaluation - carrying 60,000-character tenant and actor headers and
# twenty evidence ids:
#
#     rows retained 500   bytes retained 70.2 MB   largest row 137 KB
#
# The deque never shrinks, so that is pinned for the process lifetime, and with
# a sink configured the same bytes go out as POSTs - the service becomes an
# amplifier aimed at the operator's log sink. ``docker-compose.yml`` sets no
# memory limit, so the ceiling is the host's.
# With these caps a row's caller-supplied content is at most
# (3 + 32) * 256 bytes, so the 500-row buffer has a ceiling near 4.5 MB instead
# of none. Measured after the cap, same 500 requests: 3.0 MB retained, largest
# row 6 KB (was 70.2 MB and 137 KB).
MAX_OBSERVATION_FIELD_CHARS = 256
MAX_OBSERVATION_EVIDENCE_IDS = 32
_TRUNCATION_MARKER = "...[truncated]"


def _bounded_field(value: str) -> str:
    """Cap one caller-supplied observation field, marking what was cut.

    The marker keeps the row honest: a silently shortened value reads as the
    whole value.
    """
    if len(value) <= MAX_OBSERVATION_FIELD_CHARS:
        return value
    keep = MAX_OBSERVATION_FIELD_CHARS - len(_TRUNCATION_MARKER)
    return value[:keep] + _TRUNCATION_MARKER


def build_request_observation(
    *,
    method: str,
    route: str,
    status_code: int,
    latency_ms: float,
    headers: Any,
    request_id: str,
    evidence_ids: Sequence[str] = (),
    withheld_evidence_id_count: int = 0,
) -> dict[str, Any]:
    """Build one request observation from server-side facts and request headers.

    ``evidence_ids`` is passed in by the caller because it is the one field here
    that must **not** come from the request: it was read from a caller-supplied
    ``X-SDP-Evidence-Ids`` header, which made the governance log's correlation
    key assertable by the caller the line is about - measured, a governed
    preview exported two forged ids while the decision the server recorded was
    absent. ``evidence.collect_request_evidence_ids`` supplies them now, and
    this function no longer reads that header at all.

    ``tenant_id`` and ``actor`` are still header-derived and still
    caller-asserted; that is why the unauthenticated manifest publishes only
    aggregates of these rows (see ``build_observability_manifest``).
    """
    evidence_ids = list(evidence_ids)
    withheld_evidence_ids = (
        max(0, len(evidence_ids) - MAX_OBSERVATION_EVIDENCE_IDS) + withheld_evidence_id_count
    )
    observation = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "request_id": _bounded_field(request_id),
        "tenant_id": _bounded_field(_header_value(headers, "X-SDP-Tenant", "unknown")),
        "actor": _bounded_field(_header_value(headers, "X-SDP-Actor", "anonymous")),
        "route": route,
        "method": method,
        "status_code": status_code,
        "latency_ms": round(latency_ms, 3),
        "evidence_ids": [
            _bounded_field(item) for item in evidence_ids[:MAX_OBSERVATION_EVIDENCE_IDS]
        ],
    }
    if withheld_evidence_ids:
        # Declared rather than silently dropped, like every other bounded list
        # in this product.
        observation["withheld_evidence_id_count"] = withheld_evidence_ids
    return observation


# The alert conditions below are authored rules, not evaluated ones. No code
# computes any of them and no code posts to ``SDP_ALERT_WEBHOOK_URL`` - its only
# read in the whole package is ``bool()`` of it for ``alert_webhook_configured``.
# Published as a list named "alerts" next to ``alert_webhook_configured: true``,
# they read as monitoring that exists. The rules are kept because the conditions
# are the right ones and an operator can wire them up in their own stack; what
# changes is that every surface now says they are declared rather than live.
ALERT_ROUTING_STATUS = "declared_unimplemented"
ALERT_EVALUATION_STATUS = "declared_not_evaluated"

# One of the two rules is evaluated now, so a single blanket status at the top
# of the manifest would be wrong either way it was written. The per-rule
# ``evaluated`` flag is the truth; this says to read it.
ALERT_EVALUATION_SCOPE = "per_rule"

# ``policy_audit_gap`` evaluated. The declared condition is "preview/query count
# exceeds policy decision or audit event count"; what is computed is its
# per-request form - a policy-gated route answered 2xx while recording no
# evidence at all - which is the same violation seen at the moment it happens
# and names the route it happened on. It is **narrower** than the declared
# comparison: evidence rows removed out of band after the fact are not visible
# here, and the published rule says so rather than letting the id imply
# coverage it does not have.
#
# This could not be evaluated before the request log's ``evidence_ids`` became a
# server fact: the field was read from a caller-supplied header, so "did this
# request record evidence" had no honest answer in process.
MAX_TRACKED_EVIDENCE_GAP_ROUTES = 32
_OTHER_GAP_ROUTES = "...[other routes]"
_GOVERNED_EVIDENCE_GAPS: dict[str, int] = {}


def note_governed_request_without_evidence(route: str) -> None:
    """Count one policy-gated 2xx that recorded no correlatable evidence.

    Bounded by route, like every other map this module publishes: past the cap
    the counts collapse into one declared bucket rather than letting a caller
    that can reach many templates grow the manifest without limit.
    """
    if route in _GOVERNED_EVIDENCE_GAPS:
        _GOVERNED_EVIDENCE_GAPS[route] += 1
        return
    if len(_GOVERNED_EVIDENCE_GAPS) < MAX_TRACKED_EVIDENCE_GAP_ROUTES:
        _GOVERNED_EVIDENCE_GAPS[route] = 1
        return
    _GOVERNED_EVIDENCE_GAPS[_OTHER_GAP_ROUTES] = (
        _GOVERNED_EVIDENCE_GAPS.get(_OTHER_GAP_ROUTES, 0) + 1
    )


def governed_evidence_gap_report() -> dict[str, Any]:
    """What this worker observed for the ``policy_audit_gap`` condition."""
    routes = dict(sorted(_GOVERNED_EVIDENCE_GAPS.items()))
    total = sum(routes.values())
    return {
        "observed_total": total,
        "firing": total > 0,
        "routes": routes,
        "measurement_window": "this worker, since start",
    }


def _redacted_sink_target(parsed: Any) -> str:
    """Describe a sink endpoint without the credentials its URL may carry.

    ``urlparse().netloc`` keeps the userinfo component, so reporting it would
    publish a sink credential such as ``https://user:token@host/push`` on the
    unauthenticated observability manifest; a query string can carry one too.
    Only the host and port identify the sink, so only those are reported, and an
    authority that cannot be read becomes an explicit redaction marker rather
    than the raw URL.
    """
    try:
        host = parsed.hostname
    except ValueError:  # pragma: no cover - defensive: malformed authority
        return "redacted"
    if not host:
        return "redacted"
    try:
        port = parsed.port
    except ValueError:
        port = None
    return f"{host}:{port}" if port else host


def _sink_status() -> dict[str, Any]:
    sink_url = os.getenv("SDP_LOG_SINK_URL", "").strip()
    alert_webhook_url = os.getenv("SDP_ALERT_WEBHOOK_URL", "").strip()
    if not sink_url:
        return {
            "configured": False,
            "scheme": "memory",
            "target": "in_process_ring_buffer",
            "alert_webhook_configured": bool(alert_webhook_url),
            "alert_webhook_routing": ALERT_ROUTING_STATUS,
        }

    parsed = urlparse(sink_url)
    scheme = parsed.scheme
    # A configuration that can never be written is reported as such, rather than
    # as a configured sink whose failures are invisible outside _EXPORT_ERRORS.
    invalid_reason: str | None = None
    if scheme == "file":
        try:
            _file_sink_path(sink_url, parsed)
        except SinkConfigurationError as exc:
            invalid_reason = str(exc)
    elif scheme in {"http", "https"}:
        # Validated through the same resolver the export uses, so "configured"
        # cannot mean "set but unconnectable" for an http sink either. A
        # credential-bearing URL used to report configured and fail every export.
        try:
            _http_sink_request_parts(sink_url, parsed)
        except SinkConfigurationError as exc:
            invalid_reason = str(exc)
    else:
        invalid_reason = "SDP_LOG_SINK_URL must use the file, http or https scheme"
    if scheme == "file":
        # A file sink published its absolute server path verbatim, and for the UNC
        # form _file_sink_path deliberately supports (file://host/share/...) that
        # path carries the sink's internal hostname - the same authority component
        # _redacted_sink_target exists to suppress. The manifest is
        # unauthenticated, so only the fact that a local sink is configured is
        # published.
        target = "local_file"
    else:
        target = _redacted_sink_target(parsed)

    status = {
        # ``configured`` means "a sink is set AND it can be written". A sink that
        # raises on every export is not a configured sink, and reporting it as
        # one is how an empty audit log went unnoticed.
        "configured": invalid_reason is None,
        "scheme": scheme,
        "target": target,
        "alert_webhook_configured": bool(alert_webhook_url),
        # ``alert_webhook_configured`` reports whether the variable is set, which
        # a reader took for "alerts reach this endpoint". Nothing posts to it, so
        # the capability is stated next to the configuration fact.
        "alert_webhook_routing": ALERT_ROUTING_STATUS,
    }
    if invalid_reason is not None:
        status["invalid_configuration"] = invalid_reason
    return status


def _export_to_sink(observation: dict[str, Any]) -> None:
    sink_url = os.getenv("SDP_LOG_SINK_URL", "").strip()
    if not sink_url:
        return

    parsed = urlparse(sink_url)
    # No scheme default: a bare value used to be treated as ``file`` and written
    # relative to the working directory.
    scheme = parsed.scheme
    payload = json.dumps(observation, ensure_ascii=False, sort_keys=True)

    if scheme == "file":
        path = _file_sink_path(sink_url, parsed)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(payload + "\n")
        return

    if scheme in {"http", "https"}:
        timeout_ms = int(os.getenv("SDP_LOG_SINK_TIMEOUT_MS", "500"))
        url, headers = _http_sink_request_parts(sink_url, parsed)
        request = UrlRequest(
            url,
            data=payload.encode("utf-8"),
            headers=headers,
            method="POST",
        )
        # nosemgrep: python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected -- scheme is allow-listed to {http,https} at the guard above (file:// et al. raise below)
        with urlopen(request, timeout=timeout_ms / 1000):
            return

    raise ValueError(f"unsupported SDP_LOG_SINK_URL scheme: {scheme}")


def record_observability_export_error(error: dict[str, Any] | str) -> None:
    if isinstance(error, str):
        payload = {"timestamp": datetime.now(timezone.utc).isoformat(), "message": error}
    else:
        payload = dict(error)
        payload.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
    _EXPORT_ERRORS.append(payload)


def record_request_observation(observation: dict[str, Any], *, export: bool = True) -> None:
    """Buffer one request observation and export it to the configured sink.

    This is the synchronous entry point. Callers already on an event loop must
    use :func:`record_request_observation_async` instead: ``_export_to_sink``
    does a blocking socket write or file append, which would otherwise run on
    the loop thread and serialize every concurrent request behind it.
    """
    _REQUEST_OBSERVATIONS.append(dict(observation))
    if not export:
        return
    _export_buffered_observation(observation)


# A telemetry sink that is down must not become an API throughput ceiling.
# Moving the export off the event loop removed the serialization, but every
# request still paid the full SDP_LOG_SINK_TIMEOUT_MS in a worker thread drawn
# from the same bounded anyio pool that serves every sync route: measured against
# a socket that accepts and never answers, 40 concurrent requests took 1.95s at a
# 500ms timeout, and one episode filled all 50 export-error slots.
SINK_FAILURE_THRESHOLD = 5
SINK_COOLDOWN_SECONDS = 30.0
# The breaker had two states, and the missing third one gave back the throughput
# ceiling it was added to remove. Once ``open_until`` elapsed, *every* request
# attempted the sink again, concurrently, each paying the full
# ``SDP_LOG_SINK_TIMEOUT_MS`` from the same bounded anyio threadpool that serves
# every sync route - so a sink that stays down turns each cooldown expiry into a
# fresh stampede. Measured on the real path (``record_request_observation_async``
# -> ``anyio.to_thread``) against a sink that accepts and never answers, 20
# concurrent requests arriving the instant the cooldown expired:
#
#     pool slots   sink attempts (before)   sink attempts (after)
#     8                                8                       1
#     unbounded                       20                       1
#
# Wall-clock for the burst is unchanged (~205ms, one timeout) because the
# attempts run in parallel; what the stampede costs is *threadpool slots* - it
# occupies every free slot of the pool that serves every sync route, for the full
# ``SDP_LOG_SINK_TIMEOUT_MS``, once per cooldown for as long as the outage lasts.
#
# Half-open fixes it: when the cooldown expires on a tripped breaker, exactly one
# caller probes the sink and everyone else keeps skipping until that probe
# answers. Recovery is still immediate - the probe's success closes the breaker
# for all subsequent callers - and it costs one request's timeout per cooldown
# instead of every concurrent request's.
#
# The lock is not optional: exports run in worker threads via
# ``to_thread.run_sync``, so the read-decide-write on these counters is genuinely
# concurrent, and "exactly one probe" cannot be expressed without it.
_SINK_BREAKER: dict[str, Any] = {
    "consecutive_failures": 0,
    "open_until": 0.0,
    "skipped_exports": 0,
    "probe_in_flight": False,
    "probes_started": 0,
}
_SINK_BREAKER_LOCK = threading.Lock()


def sink_breaker_state() -> dict[str, Any]:
    """Report the export breaker, so an outage is visible rather than silent."""
    with _SINK_BREAKER_LOCK:
        return {
            "open": _SINK_BREAKER["open_until"] > time.monotonic(),
            "half_open": _sink_breaker_is_half_open_locked(),
            "consecutive_failures": _SINK_BREAKER["consecutive_failures"],
            "skipped_exports": _SINK_BREAKER["skipped_exports"],
            # How many single-probe recovery attempts the cooldown has allowed.
            # A rising count with the breaker still tripped is a sink that is
            # still down, distinguishable from one that never recovered because
            # nothing retried.
            "probes_started": _SINK_BREAKER["probes_started"],
            "probe_in_flight": _SINK_BREAKER["probe_in_flight"],
            "failure_threshold": SINK_FAILURE_THRESHOLD,
            "cooldown_seconds": SINK_COOLDOWN_SECONDS,
        }


def reset_sink_breaker() -> None:
    """Clear the breaker (used by tests and by reset_request_observability)."""
    with _SINK_BREAKER_LOCK:
        _SINK_BREAKER["consecutive_failures"] = 0
        _SINK_BREAKER["open_until"] = 0.0
        _SINK_BREAKER["skipped_exports"] = 0
        _SINK_BREAKER["probe_in_flight"] = False
        _SINK_BREAKER["probes_started"] = 0


def _sink_breaker_is_half_open_locked() -> bool:
    """Whether a tripped breaker's cooldown has elapsed without a success yet.

    Caller holds ``_SINK_BREAKER_LOCK``.
    """
    return (
        _SINK_BREAKER["consecutive_failures"] >= SINK_FAILURE_THRESHOLD
        and _SINK_BREAKER["open_until"] <= time.monotonic()
    )


def _claim_sink_export() -> bool:
    """Whether this caller may attempt the sink now, counting what it skips.

    Three outcomes, all decided under one lock:

    * closed - the sink has not failed enough to trip; attempt it.
    * open - the cooldown has not elapsed; skip, and count the skip.
    * half-open - the cooldown elapsed on a tripped breaker; the first caller
      claims the single probe, every other caller skips.
    """
    with _SINK_BREAKER_LOCK:
        if _SINK_BREAKER["open_until"] > time.monotonic():
            _SINK_BREAKER["skipped_exports"] += 1
            return False
        if not _sink_breaker_is_half_open_locked():
            return True
        if _SINK_BREAKER["probe_in_flight"]:
            _SINK_BREAKER["skipped_exports"] += 1
            return False
        _SINK_BREAKER["probe_in_flight"] = True
        _SINK_BREAKER["probes_started"] += 1
        return True


def _record_sink_failure(message: str) -> None:
    """Count one export failure and open the breaker once the run is long enough."""
    with _SINK_BREAKER_LOCK:
        _SINK_BREAKER["consecutive_failures"] += 1
        if _SINK_BREAKER["consecutive_failures"] >= SINK_FAILURE_THRESHOLD:
            _SINK_BREAKER["open_until"] = time.monotonic() + SINK_COOLDOWN_SECONDS
        # A failed probe re-arms the cooldown above; releasing the claim here
        # lets the *next* expiry probe again rather than deadlocking recovery.
        _SINK_BREAKER["probe_in_flight"] = False
    record_observability_export_error(message)


def _record_sink_success() -> None:
    with _SINK_BREAKER_LOCK:
        _SINK_BREAKER["consecutive_failures"] = 0
        _SINK_BREAKER["open_until"] = 0.0
        _SINK_BREAKER["probe_in_flight"] = False


def _export_buffered_observation(observation: dict[str, Any]) -> None:
    """Export one already-buffered observation, recording a sink failure.

    While the breaker is open the sink is not attempted at all, so a dead sink
    costs nothing per request instead of a timeout and a threadpool slot. After
    the cooldown it costs exactly one probe, not one per concurrent request.
    """
    if not _claim_sink_export():
        return
    try:
        _export_to_sink(observation)
    except Exception as exc:
        _record_sink_failure(str(exc))
    else:
        _record_sink_success()


async def record_request_observation_async(
    observation: dict[str, Any], *, export: bool = True
) -> None:
    """Buffer one request observation, exporting it off the event loop.

    The ring buffer is appended synchronously so an observation is visible the
    moment the request finishes, with no ordering surprise for readers of
    ``/metrics``. Only the sink write - a blocking ``urlopen`` or file append -
    is moved to a worker thread. Running it inline on the loop blocked every
    other in-flight request for the duration of the sink round-trip: measured at
    8 concurrent requests against a 0.2s sink, the request path took 1.63s
    instead of ~0.2s.

    The response still waits for its own export, bounded by
    ``SDP_LOG_SINK_TIMEOUT_MS``; what this removes is the serialization of
    *other* requests behind it.
    """
    _REQUEST_OBSERVATIONS.append(dict(observation))
    if not export:
        return
    await to_thread.run_sync(_export_buffered_observation, observation)


def list_request_observations(limit: int = 100) -> list[dict[str, Any]]:
    return list(_REQUEST_OBSERVATIONS)[-limit:]


def observation_buffer_capacity() -> int:
    """How many observations the ring buffer retains.

    Published rather than assumed: every latency figure derived from this buffer
    is over a bounded recent window, and a reader cannot judge the figure
    without knowing the window. Read from the deque itself so the published
    number cannot drift from the structure.
    """
    return _REQUEST_OBSERVATIONS.maxlen or 0


def count_request_observations() -> int:
    """Return how many observations the ring buffer actually holds.

    The gauges used ``len()`` of a *page*, so ``sdp_request_observations_total``
    saturated at the page size (25) while the buffer held up to 500. A counter
    that cannot exceed its page is not a counter.
    """
    return len(_REQUEST_OBSERVATIONS)


def list_observability_export_errors(limit: int = 50) -> list[dict[str, Any]]:
    return list(_EXPORT_ERRORS)[-limit:]


def count_observability_export_errors() -> int:
    """Return how many export errors the ring buffer actually holds."""
    return len(_EXPORT_ERRORS)


def reset_request_observability() -> None:
    _REQUEST_OBSERVATIONS.clear()
    _EXPORT_ERRORS.clear()
    _GOVERNED_EVIDENCE_GAPS.clear()
    reset_sink_breaker()


def _latency_budget_report() -> dict[str, Any]:
    """The latency-budget report, imported at call time to break an import cycle.

    ``latency_budgets`` classifies a concrete request path with the app's own
    compiled route patterns, so it imports ``sdp.api``, which imports this
    module. The local import is the same pattern ``connectors`` uses for its
    served-route check.
    """
    from .latency_budgets import latency_budget_report

    return latency_budget_report()


def build_observability_manifest() -> dict[str, Any]:
    datasets = list_datasets()
    audit_events = list_audit_events(limit=500)
    policy_decisions = list_policy_decisions(limit=500)
    audit_event_count, audit_count_is_lower_bound = count_audit_events()
    policy_decision_count, policy_count_is_lower_bound = count_policy_decisions()
    controls = enterprise_controls_manifest()
    request_observations = list_request_observations(limit=25)
    export_errors = list_observability_export_errors()

    return {
        "service": "semantic-data-portal",
        "health_endpoint": "/health",
        "metrics_endpoint": "/metrics",
        "structured_logs": {
            "status": "implemented",
            "request_id_header": request_id_header(),
            "sink": _sink_status(),
            "fields": [
                "request_id",
                "tenant_id",
                "actor",
                "route",
                "method",
                "status_code",
                "latency_ms",
                "evidence_ids",
            ],
            # Which of those fields the server owns. ``evidence_ids`` is the key
            # that ties a row to /policy/decisions and /audit/events, and it was
            # read from the caller-supplied X-SDP-Evidence-Ids header - so the
            # caller a row is about chose the row's correlation key, and the id
            # the server recorded never appeared. It now comes from the two
            # evidence chokepoints (see evidence.collect_request_evidence_ids).
            # ``tenant_id`` and ``actor`` are still caller-asserted, which is why
            # only aggregates of these rows are published here.
            "evidence_id_source": "server_recorded",
            "caller_asserted_fields": ["tenant_id", "actor", "request_id"],
            "body_logging": "disabled",
            "sink_breaker": sink_breaker_state(),
        },
        "metrics": {
            "catalog_datasets_total": len(datasets),
            # Real counts; these were ``len()`` of the 500-row page above and
            # reported 500 for 700 events on three published surfaces.
            "audit_events_observed_total": audit_event_count,
            "policy_decisions_observed_total": policy_decision_count,
            "audit_events_observed_total_is_lower_bound": audit_count_is_lower_bound,
            "policy_decisions_observed_total_is_lower_bound": policy_count_is_lower_bound,
            "enterprise_controls_implemented": controls.implemented_controls,
            "enterprise_controls_planned": controls.planned_controls,
            "enterprise_controls_external": controls.external_controls,
            # Real buffer occupancy, not the size of the page rendered below.
            "request_observations_total": count_request_observations(),
            "observability_export_errors_total": count_observability_export_errors(),
            # The ``policy_audit_gap`` condition as a number, so an operator's
            # own monitoring can alert on it without parsing the manifest.
            "governed_requests_without_evidence_total": governed_evidence_gap_report()[
                "observed_total"
            ],
        },
        # No per-request feed on an unauthenticated manifest. Each observation
        # carries the caller's actor and tenant plus the route - which embeds the
        # dataset id - so publishing them made one tenant's governed-access
        # activity readable by anyone. Filtering by the observation's tenant_id
        # would not help: that value comes from the caller-supplied X-SDP-Tenant
        # header, so it is asserted by the very caller whose rows would be
        # filtered. Export errors are withheld for the same reason - a sink
        # exception string can quote the sink URL.
        "recent_request_count": count_request_observations(),
        "export_error_count": count_observability_export_errors(),
        "retention": {
            "local_evidence_store": "SDP_SQLITE_PATH",
            "production_target": "tenant-configurable append-only log sink plus queryable hot store",
        },
        # The PRD's six p95 budgets, compared to what this worker observed.
        "latency_budgets": _latency_budget_report(),
        # One rule is measured in process, one is still a declared condition an
        # operator implements in their own stack. Read the per-rule flag; the
        # top-level key says so rather than making one claim for both.
        "alert_evaluation": ALERT_EVALUATION_SCOPE,
        "alert_routing": ALERT_ROUTING_STATUS,
        "alerts": [
            {
                "id": "policy_audit_gap",
                "condition": (
                    "a policy-gated route answered 2xx while recording no policy "
                    "decision and no audit event"
                ),
                "declared_condition": (
                    "preview/query count exceeds policy decision or audit event count"
                ),
                "not_covered": (
                    "evidence rows removed out of band after the request; this counts "
                    "at request time, on the governed surface the refusal contract declares"
                ),
                "severity": "critical",
                "evaluated": True,
                "evaluation": "measured_in_process",
                **governed_evidence_gap_report(),
            },
            {
                "id": "central_workflow_backlog",
                "condition": "required workflow queued or in_progress beyond stale threshold",
                "severity": "warning",
                "evaluated": False,
                "evaluation": ALERT_EVALUATION_STATUS,
                "not_evaluated_because": (
                    "the condition is about GitHub Actions run state, which this service "
                    "does not observe"
                ),
            },
        ],
    }


def prometheus_metrics_text() -> str:
    manifest = build_observability_manifest()
    metrics = manifest["metrics"]
    lines = [
        "# HELP sdp_catalog_datasets_total Number of catalog datasets currently registered.",
        "# TYPE sdp_catalog_datasets_total gauge",
        f"sdp_catalog_datasets_total {metrics['catalog_datasets_total']}",
        "# HELP sdp_audit_events_observed_total Number of in-process audit events visible to the API.",
        "# TYPE sdp_audit_events_observed_total gauge",
        f"sdp_audit_events_observed_total {metrics['audit_events_observed_total']}",
        "# HELP sdp_policy_decisions_observed_total Number of policy decisions visible to the API.",
        "# TYPE sdp_policy_decisions_observed_total gauge",
        f"sdp_policy_decisions_observed_total {metrics['policy_decisions_observed_total']}",
        "# HELP sdp_enterprise_controls_implemented Number of implemented enterprise controls.",
        "# TYPE sdp_enterprise_controls_implemented gauge",
        f"sdp_enterprise_controls_implemented {metrics['enterprise_controls_implemented']}",
        "# HELP sdp_enterprise_controls_planned Number of planned enterprise controls.",
        "# TYPE sdp_enterprise_controls_planned gauge",
        f"sdp_enterprise_controls_planned {metrics['enterprise_controls_planned']}",
        "# HELP sdp_request_observations_total Request observations held in the local bounded ring buffer.",
        "# TYPE sdp_request_observations_total gauge",
        f"sdp_request_observations_total {metrics['request_observations_total']}",
        "# HELP sdp_observability_export_errors_total Number of request observation export errors.",
        "# TYPE sdp_observability_export_errors_total gauge",
        f"sdp_observability_export_errors_total {metrics['observability_export_errors_total']}",
        "# HELP sdp_governed_requests_without_evidence_total Policy-gated 2xx responses that recorded no policy decision and no audit event.",
        "# TYPE sdp_governed_requests_without_evidence_total gauge",
        f"sdp_governed_requests_without_evidence_total {metrics['governed_requests_without_evidence_total']}",
        "",
    ]
    return "\n".join(lines)
