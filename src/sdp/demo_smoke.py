from __future__ import annotations

import json
from typing import Any

from sdp_core import (
    buyer_demo_activation_plan,
    enterprise_controls_manifest,
    enterprise_kpi_framework,
    enterprise_readiness_manifest,
)

from .connectors import connector_probe
from .enterprise_evidence import build_enterprise_evidence_pack


def smoke_summary() -> dict[str, Any]:
    readiness = enterprise_readiness_manifest()
    demo_plan = buyer_demo_activation_plan()
    controls = enterprise_controls_manifest()
    evidence = build_enterprise_evidence_pack()
    kpis = enterprise_kpi_framework()
    sql_probe = connector_probe("sql_connector", "crm-customer-master")
    rdf_probe = connector_probe("rdf_connector", "semantic-glossary")
    file_probe = connector_probe("file_lake_connector", "crm-event")
    rest_probe = connector_probe("rest_connector", "marketing-campaign")

    return {
        "product": readiness.product,
        "valuation_target_krw": readiness.valuation_target_krw,
        "demo_activation_days": demo_plan.activation_days,
        "primary_kpis": len(kpis.primary_kpis),
        "guardrail_kpis": len(kpis.guardrail_kpis),
        "demo_seed_datasets": len(demo_plan.demo_datasets),
        "metadata_validation_pass_rate": evidence["metadata_validation_pass_rate"],
        "ontology_mapping_coverage": evidence["ontology_mapping_coverage"],
        "enterprise_controls": len(controls.controls),
        "implemented_enterprise_controls": controls.implemented_controls,
        "connector_probe_status": sql_probe["status"],
        "connector_probe_dataset": sql_probe["dataset_id"],
        "connector_probe_domain": (sql_probe["demo_context"] or {}).get("domain_id"),
        "rdf_connector_probe_status": rdf_probe["status"],
        "rdf_connector_probe_dataset": rdf_probe["dataset_id"],
        "file_lake_connector_probe_status": file_probe["status"],
        "file_lake_connector_probe_dataset": file_probe["dataset_id"],
        "rest_connector_probe_status": rest_probe["status"],
        "rest_connector_adapter_status": rest_probe["adapter_status"],
        "ready": (
            readiness.valuation_target_krw == 2_000_000_000
            and demo_plan.activation_days <= 10
            and len(demo_plan.demo_datasets) >= 3
            and evidence["metadata_validation_pass_rate"] >= 0.95
            and evidence["ontology_mapping_coverage"] >= 0.7
            and len(kpis.primary_kpis) >= 3
            and controls.implemented_controls >= 2
            and sql_probe["demo_context"] is not None
            and sql_probe["status"] == "ready_for_demo"
            and rdf_probe["status"] == "ready_for_demo"
            and file_probe["status"] == "ready_for_demo"
            and rest_probe["adapter_status"] == "implemented"
        ),
    }


def main() -> int:
    summary = smoke_summary()
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
