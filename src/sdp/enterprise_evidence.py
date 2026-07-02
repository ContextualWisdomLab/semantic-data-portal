from __future__ import annotations

from typing import Any

from sdp_core import (
    MappingStatus,
    buyer_demo_activation_plan,
    enterprise_controls_manifest,
    enterprise_kpi_framework,
    enterprise_readiness_manifest,
)

from .catalog import list_audit_events, list_datasets, validate_metadata
from .evidence import list_policy_decisions


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
    datasets = list_datasets()
    audit_events = list_audit_events(limit=500)
    policy_decisions = list_policy_decisions(limit=500)

    return {
        "product": readiness.product,
        "valuation_target_krw": readiness.valuation_target_krw,
        "demo_domain": demo_plan.priority_domain,
        "dataset_count": len(datasets),
        "demo_seed_datasets": [dataset.id for dataset in demo_plan.demo_datasets],
        "metadata_validation_pass_rate": _metadata_validation_pass_rate(),
        "ontology_mapping_coverage": _ontology_mapping_coverage(),
        "policy_decision_count": len(policy_decisions),
        "audit_event_count": len(audit_events),
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
            "/enterprise/connectors/sql_connector/probe?dataset_id=crm-customer-master",
            "/policy/decisions",
            "/audit/events",
            "/metrics",
        ],
        "saleability_gates": {
            "metadata_validation_pass_rate": "pass" if _metadata_validation_pass_rate() >= 0.95 else "gap",
            "ontology_mapping_coverage": "pass" if _ontology_mapping_coverage() >= 0.7 else "gap",
            "policy_decisions_inspectable": "pass" if policy_decisions else "needs_activity",
            "audit_events_inspectable": "pass" if audit_events else "needs_activity",
            "enterprise_controls_visible": "pass" if controls.implemented_controls >= 2 else "gap",
        },
    }
