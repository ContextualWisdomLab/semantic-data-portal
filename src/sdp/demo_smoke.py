from __future__ import annotations

import json
from typing import Any

from sdp_core import (
    buyer_demo_activation_plan,
    enterprise_controls_manifest,
    enterprise_kpi_framework,
    enterprise_production_readiness_manifest,
    enterprise_readiness_manifest,
)

from .connectors import connector_probe
from .enterprise_evidence import build_enterprise_evidence_pack
from .semantic_validation import enterprise_shacl_validation_summary
from .steward_review import build_steward_review_summary


def http_walkthrough() -> dict[str, Any]:
    """Drive the documented buyer journey over HTTP and report what happened.

    Everything else in this module calls Python functions directly, so the
    ``ready`` gate never touched a route. It therefore certified the platform as
    ready while the HTTP surface was broken in ways a buyer hits immediately: the
    operator console reported "evidence load failed" to every viewer, the
    documented draft-then-execute pair rejected every draft it produced, and
    ``POST /browse/query`` answered 500 when ``dataset_ids`` was omitted. A
    readiness gate that does not exercise the surface the buyer uses is not
    evidence about that surface.

    The walkthrough is kept additive: the direct-call checks above are unchanged,
    and the gate now also requires that these routes actually work.
    """
    # Imported here, not at module scope: this is the only part of the smoke that
    # needs the app object, and importing it at module load would make every
    # direct-call consumer of smoke_summary pay for building the route table.
    from fastapi.testclient import TestClient

    from .api import app

    client = TestClient(app, raise_server_exceptions=False)
    steps: list[dict[str, Any]] = []

    def record(step: str, response: Any, *, expect: int = 200) -> Any:
        ok = response.status_code == expect
        steps.append(
            {
                "step": step,
                "status_code": response.status_code,
                "expected": expect,
                "ok": ok,
            }
        )
        if not ok:
            return None
        try:
            return response.json()
        except ValueError:
            return response.text

    actor = "admin"
    dataset_id = "crm-customer-master"

    record("health", client.get("/healthz"))
    record("console", client.get("/enterprise/console"))
    record(
        "catalog_search",
        client.get("/catalog/search", params={"q": "고객", "user": actor}),
    )
    record(
        "dataset_detail",
        client.get(f"/catalog/datasets/{dataset_id}", params={"user": actor}),
    )
    record(
        "governed_schema",
        client.get(f"/browse/{dataset_id}/schema", params={"user": actor, "purpose": "analysis"}),
    )
    record(
        "governed_preview",
        client.post(
            f"/browse/{dataset_id}/preview",
            json={"user": actor, "purpose": "analysis", "limit": 5, "offset": 0},
        ),
    )
    record(
        "connector_probe",
        client.get(
            "/enterprise/connectors/sql_connector/probe",
            params={"dataset_id": dataset_id, "user": actor},
        ),
    )
    # The pair that had no path through it: a draft must be executable.
    drafted = record(
        "draft_query",
        client.post(
            "/llm/draft-query",
            json={
                "user": actor,
                "dataset_id": dataset_id,
                "question": "월별 추이를 보여줘",
                "purpose": "analysis",
            },
        ),
    )
    drafted_sql = (drafted or {}).get("query") if isinstance(drafted, dict) else None
    if drafted_sql:
        record(
            "execute_drafted_query",
            client.post(
                "/browse/query",
                json={
                    "user": actor,
                    "dataset_ids": [dataset_id],
                    "language": "SQL",
                    "query": drafted_sql,
                    "purpose": "analysis",
                },
            ),
        )
    else:
        steps.append(
            {"step": "execute_drafted_query", "status_code": None, "expected": 200, "ok": False}
        )
    record("audit_feed", client.get("/audit/events", params={"user": actor, "limit": 5}))
    record("policy_decisions", client.get("/policy/decisions", params={"user": actor, "limit": 5}))
    # A malformed body must be a client error, never a 500.
    record(
        "malformed_query_is_a_client_error",
        client.post(
            "/browse/query",
            json={"user": actor, "language": "SQL", "query": "select 1", "purpose": "analysis"},
        ),
        expect=400,
    )

    failed = [step["step"] for step in steps if not step["ok"]]
    server_errors = [
        step["step"]
        for step in steps
        if isinstance(step["status_code"], int) and step["status_code"] >= 500
    ]
    return {
        "steps": steps,
        "step_count": len(steps),
        "failed_steps": failed,
        "server_error_steps": server_errors,
        "all_steps_passed": not failed,
    }


def smoke_summary() -> dict[str, Any]:
    readiness = enterprise_readiness_manifest()
    demo_plan = buyer_demo_activation_plan()
    controls = enterprise_controls_manifest()
    evidence = build_enterprise_evidence_pack()
    shacl_validation = enterprise_shacl_validation_summary()
    steward_review = build_steward_review_summary()
    kpis = enterprise_kpi_framework()
    production = enterprise_production_readiness_manifest()
    sql_probe = connector_probe("sql_connector", "crm-customer-master")
    rdf_probe = connector_probe("rdf_connector", "semantic-glossary")
    file_probe = connector_probe("file_lake_connector", "crm-event")
    rest_probe = connector_probe("rest_connector", "marketing-campaign")
    walkthrough = http_walkthrough()

    return {
        "product": readiness.product,
        "valuation_target_krw": readiness.valuation_target_krw,
        "demo_activation_days": demo_plan.activation_days,
        "primary_kpis": len(kpis.primary_kpis),
        "guardrail_kpis": len(kpis.guardrail_kpis),
        "demo_seed_datasets": len(demo_plan.demo_datasets),
        "metadata_validation_pass_rate": evidence["metadata_validation_pass_rate"],
        "shacl_validation_pass_rate": shacl_validation["validation_pass_rate"],
        "steward_review_queue_count": steward_review["review_queue_count"],
        "steward_buyer_handoff_ready": steward_review["buyer_handoff_ready"],
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
        "production_current_stage": production.current_stage,
        "production_demo_release_ready": production.demo_release_ready,
        "production_paid_pilot_ready": production.paid_pilot_ready,
        "production_paid_pilot_blockers": len(production.paid_pilot_blockers),
        "http_walkthrough_steps": walkthrough["step_count"],
        "http_walkthrough_failed_steps": walkthrough["failed_steps"],
        "http_walkthrough_server_errors": walkthrough["server_error_steps"],
        "http_walkthrough_passed": walkthrough["all_steps_passed"],
        "ready": (
            readiness.valuation_target_krw == 2_000_000_000
            and demo_plan.activation_days <= 10
            and len(demo_plan.demo_datasets) >= 3
            and evidence["metadata_validation_pass_rate"] >= 0.95
            and shacl_validation["validation_pass_rate"] >= 0.95
            and steward_review["buyer_handoff_ready"]
            and evidence["ontology_mapping_coverage"] >= 0.7
            and len(kpis.primary_kpis) >= 3
            and controls.implemented_controls >= 2
            and sql_probe["demo_context"] is not None
            and sql_probe["status"] == "ready_for_demo"
            and rdf_probe["status"] == "ready_for_demo"
            and file_probe["status"] == "ready_for_demo"
            and rest_probe["adapter_status"] == "implemented"
            # The documented buyer journey must actually work over HTTP, not only
            # as direct function calls.
            and walkthrough["all_steps_passed"]
        ),
    }


def main() -> int:
    summary = smoke_summary()
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["ready"] else 1


if __name__ == "__main__":  # pragma: no cover - CLI entry, exercised only on direct execution
    raise SystemExit(main())
