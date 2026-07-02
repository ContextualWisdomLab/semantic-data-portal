from __future__ import annotations

from typing import Any

from sdp_core import SourceConnector, buyer_demo_context_for_dataset, connector_registry_manifest

from .catalog import get_dataset


_IMPLEMENTED_PROOF = {
    "audit_event": ["/audit/events"],
    "lineage_capture": ["/catalog/datasets/{dataset_id}/lineage"],
    "ontology_version_pin": ["/ontology/search", "/ontology/resolve"],
    "pii_masking": ["/browse/{dataset_id}/preview"],
    "pii_profile": ["/catalog/datasets/{dataset_id}/profile"],
    "policy_before_query": ["/browse/query", "/policy/decision", "/policy/decisions"],
    "purpose_binding": ["/policy/decision", "/policy/decisions"],
    "row_limit": ["/browse/query", "/llm/draft-query"],
    "sample_budget": ["/browse/{dataset_id}/preview"],
    "timeout_ms": ["/browse/query", "/llm/draft-query"],
}


class DemoSQLConnector(SourceConnector):
    connector_id = "sql_connector"
    source_type = "warehouse_or_rdbms"

    def inspect_schema(self, dataset_id: str) -> dict[str, Any]:
        dataset = get_dataset(dataset_id)
        if not dataset:
            raise KeyError(dataset_id)
        if not dataset.source_system.startswith("postgresql://"):
            raise ValueError("dataset is not backed by the demo SQL connector")
        return {
            "dataset_id": dataset.id,
            "source_system": dataset.source_system,
            "columns": [column.model_dump() for column in dataset.schema],
        }

    def preview(self, dataset_id: str, *, limit: int, offset: int) -> list[dict[str, Any]]:
        from .browse import preview

        result = preview(dataset_id, user="analyst", purpose="analysis", limit=limit, offset=offset)
        return result["rows"]


class DemoRDFConnector(SourceConnector):
    connector_id = "rdf_connector"
    source_type = "semantic_store"

    def inspect_schema(self, dataset_id: str) -> dict[str, Any]:
        dataset = get_dataset(dataset_id)
        if not dataset:
            raise KeyError(dataset_id)
        if not dataset.source_system.startswith("sparql://"):
            raise ValueError("dataset is not backed by the demo RDF connector")
        return {
            "dataset_id": dataset.id,
            "source_system": dataset.source_system,
            "named_graph": dataset.source_system.removeprefix("sparql://"),
            "columns": [column.model_dump() for column in dataset.schema],
        }

    def preview(self, dataset_id: str, *, limit: int, offset: int) -> list[dict[str, Any]]:
        from .catalog import ingest_event
        from .policy import evaluate

        dataset = get_dataset(dataset_id)
        if not dataset:
            raise KeyError(dataset_id)
        if not dataset.source_system.startswith("sparql://"):
            raise ValueError("dataset is not backed by the demo RDF connector")

        decision = evaluate(subject="analyst", resource=dataset_id, action="preview", purpose="analysis")
        if decision.effect != "allow":
            ingest_event(
                event_type="connector.rdf.preview",
                actor="analyst",
                dataset_id=dataset_id,
                decision="denied",
                decision_id=decision.decision_id,
                reason=decision.reason,
                details={"policy_decision_id": decision.decision_id},
            )
            raise PermissionError(decision.reason)

        rows = [
            {
                "concept_uri": "https://semantic-data-portal.local/concepts/customer",
                "preferred_label": "고객",
                "broader_concept": "https://semantic-data-portal.local/concepts/party",
            },
            {
                "concept_uri": "https://semantic-data-portal.local/concepts/active-customer",
                "preferred_label": "활성 고객",
                "broader_concept": "https://semantic-data-portal.local/concepts/customer",
            },
            {
                "concept_uri": "https://semantic-data-portal.local/concepts/churn",
                "preferred_label": "이탈",
                "broader_concept": "https://semantic-data-portal.local/concepts/customer",
            },
        ]
        selected = rows[offset : offset + limit]
        ingest_event(
            event_type="connector.rdf.preview",
            actor="analyst",
            dataset_id=dataset_id,
            decision="allowed",
            decision_id=decision.decision_id,
            reason="ok",
            details={
                "policy_decision_id": decision.decision_id,
                "requested_offset": offset,
                "requested_limit": limit,
                "returned_rows": len(selected),
                "named_graph": dataset.source_system.removeprefix("sparql://"),
            },
        )
        return selected


class DemoFileLakeConnector(SourceConnector):
    connector_id = "file_lake_connector"
    source_type = "object_storage_or_lakehouse"

    def inspect_schema(self, dataset_id: str) -> dict[str, Any]:
        dataset = get_dataset(dataset_id)
        if not dataset:
            raise KeyError(dataset_id)
        if not dataset.source_system.startswith("s3://"):
            raise ValueError("dataset is not backed by the demo file lake connector")
        return {
            "dataset_id": dataset.id,
            "source_system": dataset.source_system,
            "manifest_path": f"{dataset.source_system.rstrip('/')}/_manifest.json",
            "columns": [column.model_dump() for column in dataset.schema],
        }

    def preview(self, dataset_id: str, *, limit: int, offset: int) -> list[dict[str, Any]]:
        from .catalog import ingest_event
        from .policy import evaluate

        dataset = get_dataset(dataset_id)
        if not dataset:
            raise KeyError(dataset_id)
        if not dataset.source_system.startswith("s3://"):
            raise ValueError("dataset is not backed by the demo file lake connector")

        decision = evaluate(subject="analyst", resource=dataset_id, action="preview", purpose="analysis")
        if decision.effect != "allow":
            ingest_event(
                event_type="connector.file_lake.preview",
                actor="analyst",
                dataset_id=dataset_id,
                decision="denied",
                decision_id=decision.decision_id,
                reason=decision.reason,
                details={"policy_decision_id": decision.decision_id},
            )
            raise PermissionError(decision.reason)

        rows = [
            {
                "event_id": "evt-1001",
                "customer_id": "C-1001",
                "event_timestamp": "2026-06-20T12:10:00Z",
                "device_id": "dev-88",
            },
            {
                "event_id": "evt-1002",
                "customer_id": "C-1002",
                "event_timestamp": "2026-06-21T09:11:00Z",
                "device_id": "dev-01",
            },
        ]
        selected = rows[offset : offset + limit]
        ingest_event(
            event_type="connector.file_lake.preview",
            actor="analyst",
            dataset_id=dataset_id,
            decision="allowed",
            decision_id=decision.decision_id,
            reason="ok",
            details={
                "policy_decision_id": decision.decision_id,
                "requested_offset": offset,
                "requested_limit": limit,
                "returned_rows": len(selected),
                "sample_budget": limit,
                "manifest_path": f"{dataset.source_system.rstrip('/')}/_manifest.json",
            },
        )
        return selected


class DemoRESTConnector(SourceConnector):
    connector_id = "rest_connector"
    source_type = "governed_api"

    def inspect_schema(self, dataset_id: str) -> dict[str, Any]:
        dataset = get_dataset(dataset_id)
        if not dataset:
            raise KeyError(dataset_id)
        if not dataset.source_system.startswith(("https://", "http://")):
            raise ValueError("dataset is not backed by the demo REST connector")
        return {
            "dataset_id": dataset.id,
            "source_system": dataset.source_system,
            "auth_mode": "service_account_reference",
            "columns": [column.model_dump() for column in dataset.schema],
        }

    def preview(self, dataset_id: str, *, limit: int, offset: int) -> list[dict[str, Any]]:
        from .catalog import ingest_event
        from .policy import evaluate

        dataset = get_dataset(dataset_id)
        if not dataset:
            raise KeyError(dataset_id)
        if not dataset.source_system.startswith(("https://", "http://")):
            raise ValueError("dataset is not backed by the demo REST connector")

        decision = evaluate(subject="analyst", resource=dataset_id, action="preview", purpose="analysis")
        if decision.effect != "allow":
            ingest_event(
                event_type="connector.rest.preview",
                actor="analyst",
                dataset_id=dataset_id,
                decision="denied",
                decision_id=decision.decision_id,
                reason=decision.reason,
                details={"policy_decision_id": decision.decision_id},
            )
            raise PermissionError(decision.reason)

        rows = [
            {"campaign_id": "cmp-1001", "target_segment": "active_customers", "channel": "email"},
            {"campaign_id": "cmp-1002", "target_segment": "churn_risk", "channel": "push"},
        ]
        selected = rows[offset : offset + limit]
        ingest_event(
            event_type="connector.rest.preview",
            actor="analyst",
            dataset_id=dataset_id,
            decision="allowed",
            decision_id=decision.decision_id,
            reason="ok",
            details={
                "policy_decision_id": decision.decision_id,
                "requested_offset": offset,
                "requested_limit": limit,
                "returned_rows": len(selected),
                "auth_mode": "service_account_reference",
            },
        )
        return selected


_SOURCE_CONNECTORS: dict[str, SourceConnector] = {
    "sql_connector": DemoSQLConnector(),
    "rdf_connector": DemoRDFConnector(),
    "file_lake_connector": DemoFileLakeConnector(),
    "rest_connector": DemoRESTConnector(),
}


def get_source_connector(connector_id: str) -> SourceConnector:
    connector = _SOURCE_CONNECTORS.get(connector_id)
    if not connector:
        raise ValueError(f"unsupported connector id: {connector_id}")
    return connector


def connector_probe(connector_id: str, dataset_id: str) -> dict[str, Any]:
    connectors = {connector.id: connector for connector in connector_registry_manifest()}
    connector = connectors.get(connector_id)
    if not connector:
        raise ValueError(f"unsupported connector id: {connector_id}")

    dataset = get_dataset(dataset_id)
    if not dataset:
        raise KeyError(dataset_id)

    source_adapter = _SOURCE_CONNECTORS.get(connector_id)
    inspected_schema = None
    adapter_status = "planned"
    if source_adapter:
        inspected_schema = source_adapter.inspect_schema(dataset_id)
        adapter_status = "implemented"

    control_evidence = []
    implemented_controls = 0
    for control in connector.required_controls:
        proof_endpoints = _IMPLEMENTED_PROOF.get(control, [])
        implemented = bool(proof_endpoints)
        implemented_controls += int(implemented)
        control_evidence.append(
            {
                "control": control,
                "status": "implemented" if implemented else "planned",
                "proof_endpoints": proof_endpoints,
            }
        )

    ready_for_demo = adapter_status == "implemented" and implemented_controls == len(connector.required_controls)
    return {
        "connector_id": connector.id,
        "dataset_id": dataset.id,
        "source_type": connector.source_type,
        "source_system": dataset.source_system,
        "status": "ready_for_demo" if ready_for_demo else "contract_only",
        "contract_methods": ["inspect_schema", "preview"],
        "adapter_status": adapter_status,
        "data_contract": {
            "schema_fields": len(inspected_schema["columns"]) if inspected_schema else len(dataset.schema),
            "sensitivity": dataset.sensitivity,
            "quality_score": dataset.quality_score,
            "freshness_score": dataset.freshness_score,
        },
        "demo_context": buyer_demo_context_for_dataset(dataset.id),
        "control_evidence": control_evidence,
        "proof": connector.proof,
    }
