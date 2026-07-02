from __future__ import annotations

from typing import Any

from sdp_core import enterprise_controls_manifest

from .catalog import list_audit_events, list_datasets
from .evidence import list_policy_decisions


def build_observability_manifest() -> dict[str, Any]:
    datasets = list_datasets()
    audit_events = list_audit_events(limit=500)
    policy_decisions = list_policy_decisions(limit=500)
    controls = enterprise_controls_manifest()

    return {
        "service": "semantic-data-portal",
        "health_endpoint": "/health",
        "metrics_endpoint": "/metrics",
        "structured_logs": {
            "status": "planned",
            "fields": ["request_id", "actor", "tenant_id", "action", "resource", "decision_id", "result"],
        },
        "metrics": {
            "catalog_datasets_total": len(datasets),
            "audit_events_observed_total": len(audit_events),
            "policy_decisions_observed_total": len(policy_decisions),
            "enterprise_controls_implemented": controls.implemented_controls,
            "enterprise_controls_planned": controls.planned_controls,
            "enterprise_controls_external": controls.external_controls,
        },
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
        "",
    ]
    return "\n".join(lines)
