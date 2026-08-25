from __future__ import annotations

from typing import Any

from sdp_core import (
    MappingStatus,
    buyer_demo_activation_plan,
    enterprise_controls_manifest,
    enterprise_kpi_framework,
    enterprise_production_readiness_manifest,
    enterprise_readiness_manifest,
)

from .catalog import list_audit_events, list_datasets, validate_metadata
from .evidence import list_policy_decisions
from .semantic_validation import enterprise_shacl_validation_summary
from .steward_review import build_steward_review_summary

GRC_REDACTED_VALUE = "[grc-redacted]"
GRC_OBLIGATION_KEY = "grc_redaction_obligated_columns"
_AUDIT_TAIL_LIMIT = 50


def redact_grc_obligated_payload(payload: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Redact GRC-obligated columns from an export payload.

    The catalog plane returns original PII to authorized stewards (PR #80);
    response minimization therefore happens here — immediately before any
    evidence export leaves the portal. A payload declares its obligations via
    ``grc_redaction_obligated_columns`` (top level or inside ``details``).
    Every obligated column found as a payload key is replaced with
    :data:`GRC_REDACTED_VALUE`; non-obligated fields pass through untouched.

    Args:
        payload: Export record such as an audit-event dict.

    Returns:
        Tuple of ``(redacted_copy, applied_columns)`` where ``applied_columns``
        lists the obligated columns that were actually present and redacted.
    """
    obligated = list(payload.get(GRC_OBLIGATION_KEY) or [])
    details = payload.get("details")
    if isinstance(details, dict):
        obligated = obligated or list(details.get(GRC_OBLIGATION_KEY) or [])

    redacted = _deep_redact(dict(payload), set(obligated))
    applied = sorted(column for column in obligated if column in _iter_keys(redacted))
    return redacted, applied


def _iter_keys(node: Any) -> set[str]:
    keys: set[str] = set()
    if isinstance(node, dict):
        for key, value in node.items():
            keys.add(key)
            keys |= _iter_keys(value)
    elif isinstance(node, list):
        for item in node:
            keys |= _iter_keys(item)
    return keys


def _deep_redact(node: Any, obligated: set[str], in_details: bool = False) -> Any:
    if not obligated:
        return node
    if isinstance(node, dict):
        redacted: dict[Any, Any] = {}
        for key, value in node.items():
            if key in obligated and not isinstance(value, (dict, list)):
                redacted[key] = GRC_REDACTED_VALUE
            else:
                redacted[key] = _deep_redact(value, obligated, in_details or key == "details")
        return redacted
    if isinstance(node, list):
        return [_deep_redact(item, obligated, in_details) for item in node]
    return node


def _ratio(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return round(numerator / denominator, 3)


def _metadata_validation_pass_rate() -> float:
    datasets = list_datasets()
    valid = sum(1 for dataset in datasets if validate_metadata(dataset)["is_valid"])
    return _ratio(valid, len(datasets))


def _ontology_mapping_coverage() -> float:
    mappings = [mapping for dataset in list_datasets() for mapping in dataset.mappings]
    approved = sum(1 for mapping in mappings if mapping.status == MappingStatus.APPROVED)
    return _ratio(approved, len(mappings))


def build_enterprise_evidence_pack() -> dict[str, Any]:
    readiness = enterprise_readiness_manifest()
    demo_plan = buyer_demo_activation_plan()
    controls = enterprise_controls_manifest()
    kpis = enterprise_kpi_framework()
    production = enterprise_production_readiness_manifest()
    shacl_validation = enterprise_shacl_validation_summary()
    steward_review = build_steward_review_summary()
    datasets = list_datasets()
    audit_events = list_audit_events(limit=500)
    policy_decisions = list_policy_decisions(limit=500)

    audit_tail: list[dict[str, Any]] = []
    declared_event_count = 0
    redacted_event_count = 0
    redacted_column_count = 0
    for event in sorted(audit_events, key=lambda row: row.created_at, reverse=True)[:_AUDIT_TAIL_LIMIT]:
        event_payload, applied_columns = redact_grc_obligated_payload(event.model_dump(mode="json"))
        if event_payload.get("details", {}).get(GRC_OBLIGATION_KEY):
            declared_event_count += 1
        if applied_columns:
            redacted_event_count += 1
            redacted_column_count += len(applied_columns)
        audit_tail.append(event_payload)

    return {
        "product": readiness.product,
        "valuation_target_krw": readiness.valuation_target_krw,
        "demo_domain": demo_plan.priority_domain,
        "dataset_count": len(datasets),
        "demo_seed_datasets": [dataset.id for dataset in demo_plan.demo_datasets],
        "metadata_validation_pass_rate": _metadata_validation_pass_rate(),
        "shacl_validation_pass_rate": shacl_validation["validation_pass_rate"],
        "steward_review_queue_count": steward_review["review_queue_count"],
        "steward_buyer_handoff_ready": steward_review["buyer_handoff_ready"],
        "ontology_mapping_coverage": _ontology_mapping_coverage(),
        "policy_decision_count": len(policy_decisions),
        "audit_event_count": len(audit_events),
        "grc_redaction": {
            "obligation_key": GRC_OBLIGATION_KEY,
            "redacted_value": GRC_REDACTED_VALUE,
            "audit_tail_limit": _AUDIT_TAIL_LIMIT,
            "obligation_declared_event_count": declared_event_count,
            "redacted_event_count": redacted_event_count,
            "redacted_column_count": redacted_column_count,
        },
        "grc_audit_tail": audit_tail,
        "production_demo_release_ready": production.demo_release_ready,
        "production_paid_pilot_ready": production.paid_pilot_ready,
        "production_paid_pilot_blockers": len(production.paid_pilot_blockers),
        "implemented_enterprise_controls": controls.implemented_controls,
        "planned_enterprise_controls": controls.planned_controls,
        "primary_kpis": [kpi.id for kpi in kpis.primary_kpis],
        "guardrail_kpis": [kpi.id for kpi in kpis.guardrail_kpis],
        "proof_endpoints": [
            "/enterprise/readiness",
            "/enterprise/demo-plan",
            "/enterprise/kpis",
            "/enterprise/controls",
            "/enterprise/rbac-matrix",
            "/enterprise/observability",
            "/enterprise/production-readiness",
            "/enterprise/shacl-validation",
            "/enterprise/steward-review",
            "/enterprise/connectors/sql_connector/probe?dataset_id=crm-customer-master",
            "/policy/decisions",
            "/audit/events",
            "/metrics",
        ],
        "saleability_gates": {
            "metadata_validation_pass_rate": "pass" if _metadata_validation_pass_rate() >= 0.95 else "gap",
            "shacl_validation_pass_rate": "pass" if shacl_validation["validation_pass_rate"] >= 0.95 else "gap",
            "steward_review_queue": "pass" if steward_review["buyer_handoff_ready"] else "needs_review",
            "ontology_mapping_coverage": "pass" if _ontology_mapping_coverage() >= 0.7 else "gap",
            "policy_decisions_inspectable": "pass" if policy_decisions else "needs_activity",
            "audit_events_inspectable": "pass" if audit_events else "needs_activity",
            "enterprise_controls_visible": "pass" if controls.implemented_controls >= 2 else "gap",
            "production_demo_release": "pass" if production.demo_release_ready else "gap",
            "production_paid_pilot": "pass" if production.paid_pilot_ready else "needs_integration",
        },
    }
