from __future__ import annotations

import json
from typing import Any

from sdp_core import buyer_demo_activation_plan, enterprise_kpi_framework, enterprise_readiness_manifest

from .connectors import connector_probe


def smoke_summary() -> dict[str, Any]:
    readiness = enterprise_readiness_manifest()
    demo_plan = buyer_demo_activation_plan()
    kpis = enterprise_kpi_framework()
    probe = connector_probe("sql_connector", "crm-customer-master")

    return {
        "product": readiness.product,
        "valuation_target_krw": readiness.valuation_target_krw,
        "demo_activation_days": demo_plan.activation_days,
        "primary_kpis": len(kpis.primary_kpis),
        "guardrail_kpis": len(kpis.guardrail_kpis),
        "demo_seed_datasets": len(demo_plan.demo_datasets),
        "connector_probe_status": probe["status"],
        "connector_probe_dataset": probe["dataset_id"],
        "connector_probe_domain": (probe["demo_context"] or {}).get("domain_id"),
        "ready": (
            readiness.valuation_target_krw == 2_000_000_000
            and demo_plan.activation_days <= 10
            and len(demo_plan.demo_datasets) >= 3
            and len(kpis.primary_kpis) >= 3
            and probe["demo_context"] is not None
            and probe["status"] == "ready_for_demo"
        ),
    }


def main() -> int:
    summary = smoke_summary()
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
