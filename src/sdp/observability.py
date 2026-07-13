from __future__ import annotations

import json
import os
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request as UrlRequest, urlopen
from urllib.request import url2pathname
from uuid import uuid4

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


def _file_sink_path(sink_url: str, parsed: Any) -> Path:
    if parsed.netloc and not parsed.path:
        return Path(url2pathname(parsed.netloc))

    raw_path = url2pathname(parsed.path or sink_url)
    if os.name == "nt" and len(raw_path) >= 3 and raw_path[0] in {"\\", "/"} and raw_path[2] == ":":
        raw_path = raw_path[1:]
    if parsed.netloc:
        raw_path = f"//{parsed.netloc}{raw_path}"
    return Path(raw_path)


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
    evidence_ids = [item.strip() for item in evidence_header.split(",") if item.strip()] if evidence_header else []
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "request_id": request_id,
        "tenant_id": _header_value(headers, "X-SDP-Tenant", "unknown"),
        "actor": _header_value(headers, "X-SDP-Actor", "anonymous"),
        "route": route,
        "method": method,
        "status_code": status_code,
        "latency_ms": round(latency_ms, 3),
        "evidence_ids": evidence_ids,
    }


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
    scheme = parsed.scheme or "file"
    if scheme == "file":
        target = str(_file_sink_path(sink_url, parsed))
    elif scheme in {"http", "https"}:
        target = parsed.netloc
    else:
        target = sink_url

    return {
        "configured": True,
        "scheme": scheme,
        "target": target,
        "alert_webhook_configured": bool(alert_webhook_url),
    }


def _export_to_sink(observation: dict[str, Any]) -> None:
    sink_url = os.getenv("SDP_LOG_SINK_URL", "").strip()
    if not sink_url:
        return

    parsed = urlparse(sink_url)
    scheme = parsed.scheme or "file"
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
    _REQUEST_OBSERVATIONS.append(dict(observation))
    if not export:
        return
    try:
        _export_to_sink(observation)
    except Exception as exc:  # pragma: no cover - defensive around external sinks
        record_observability_export_error(str(exc))


def list_request_observations(limit: int = 100) -> list[dict[str, Any]]:
    return list(_REQUEST_OBSERVATIONS)[-limit:]


def list_observability_export_errors(limit: int = 50) -> list[dict[str, Any]]:
    return list(_EXPORT_ERRORS)[-limit:]


def reset_request_observability() -> None:
    _REQUEST_OBSERVATIONS.clear()
    _EXPORT_ERRORS.clear()


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
        },
        "metrics": {
            "catalog_datasets_total": len(datasets),
            "audit_events_observed_total": len(audit_events),
            "policy_decisions_observed_total": len(policy_decisions),
            "enterprise_controls_implemented": controls.implemented_controls,
            "enterprise_controls_planned": controls.planned_controls,
            "enterprise_controls_external": controls.external_controls,
            "request_observations_total": len(request_observations),
            "observability_export_errors_total": len(export_errors),
        },
        "recent_requests": request_observations[-10:],
        "export_errors": export_errors[-5:],
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
        "# HELP sdp_request_observations_total Number of request observations in the local ring buffer.",
        "# TYPE sdp_request_observations_total gauge",
        f"sdp_request_observations_total {metrics['request_observations_total']}",
        "# HELP sdp_observability_export_errors_total Number of request observation export errors.",
        "# TYPE sdp_observability_export_errors_total gauge",
        f"sdp_observability_export_errors_total {metrics['observability_export_errors_total']}",
        "",
    ]
    return "\n".join(lines)
