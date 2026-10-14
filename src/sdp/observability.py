from __future__ import annotations

import json
import os
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request as UrlRequest, urlopen
from urllib.request import url2pathname
from uuid import uuid4

from anyio import to_thread

from sdp_core import enterprise_controls_manifest

from .catalog import list_audit_events, list_datasets
from .evidence import list_policy_decisions


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
) -> dict[str, Any]:
    evidence_header = _header_value(headers, "X-SDP-Evidence-Ids", "")
    evidence_ids = (
        [item.strip() for item in evidence_header.split(",") if item.strip()]
        if evidence_header
        else []
    )
    withheld_evidence_ids = max(0, len(evidence_ids) - MAX_OBSERVATION_EVIDENCE_IDS)
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
    elif scheme not in {"http", "https"}:
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
        request = UrlRequest(
            sink_url,
            data=payload.encode("utf-8"),
            headers={"Content-Type": "application/json"},
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
_SINK_BREAKER: dict[str, Any] = {
    "consecutive_failures": 0,
    "open_until": 0.0,
    "skipped_exports": 0,
}


def sink_breaker_state() -> dict[str, Any]:
    """Report the export breaker, so an outage is visible rather than silent."""
    return {
        "open": _SINK_BREAKER["open_until"] > time.monotonic(),
        "consecutive_failures": _SINK_BREAKER["consecutive_failures"],
        "skipped_exports": _SINK_BREAKER["skipped_exports"],
        "failure_threshold": SINK_FAILURE_THRESHOLD,
        "cooldown_seconds": SINK_COOLDOWN_SECONDS,
    }


def reset_sink_breaker() -> None:
    """Clear the breaker (used by tests and by reset_request_observability)."""
    _SINK_BREAKER["consecutive_failures"] = 0
    _SINK_BREAKER["open_until"] = 0.0
    _SINK_BREAKER["skipped_exports"] = 0


def _sink_breaker_is_open() -> bool:
    return _SINK_BREAKER["open_until"] > time.monotonic()


def _record_sink_failure(message: str) -> None:
    """Count one export failure and open the breaker once the run is long enough."""
    _SINK_BREAKER["consecutive_failures"] += 1
    if _SINK_BREAKER["consecutive_failures"] >= SINK_FAILURE_THRESHOLD:
        _SINK_BREAKER["open_until"] = time.monotonic() + SINK_COOLDOWN_SECONDS
    record_observability_export_error(message)


def _record_sink_success() -> None:
    _SINK_BREAKER["consecutive_failures"] = 0
    _SINK_BREAKER["open_until"] = 0.0



def _export_buffered_observation(observation: dict[str, Any]) -> None:
    """Export one already-buffered observation, recording a sink failure.

    While the breaker is open the sink is not attempted at all, so a dead sink
    costs nothing per request instead of a timeout and a threadpool slot.
    """
    if _sink_breaker_is_open():
        _SINK_BREAKER["skipped_exports"] += 1
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
    reset_sink_breaker()


def build_observability_manifest() -> dict[str, Any]:
    datasets = list_datasets()
    audit_events = list_audit_events(limit=500)
    policy_decisions = list_policy_decisions(limit=500)
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
            "body_logging": "disabled",
            "sink_breaker": sink_breaker_state(),
        },
        "metrics": {
            "catalog_datasets_total": len(datasets),
            "audit_events_observed_total": len(audit_events),
            "policy_decisions_observed_total": len(policy_decisions),
            "enterprise_controls_implemented": controls.implemented_controls,
            "enterprise_controls_planned": controls.planned_controls,
            "enterprise_controls_external": controls.external_controls,
            # Real buffer occupancy, not the size of the page rendered below.
            "request_observations_total": count_request_observations(),
            "observability_export_errors_total": count_observability_export_errors(),
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
        "alerts": [
            {
                "id": "policy_audit_gap",
                "condition": "preview/query count exceeds policy decision or audit event count",
                "severity": "critical",
            },
            {
                "id": "central_workflow_backlog",
                "condition": "required workflow queued or in_progress beyond stale threshold",
                "severity": "warning",
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
        "",
    ]
    return "\n".join(lines)
