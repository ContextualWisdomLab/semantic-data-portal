from __future__ import annotations

from typing import Any

from sdp_core import connector_registry_manifest

from .catalog import get_dataset


_IMPLEMENTED_PROOF = {
    "audit_event": ["/audit/events"],
    "lineage_capture": ["/catalog/datasets/{dataset_id}/lineage"],
    "ontology_version_pin": ["/ontology/search", "/ontology/resolve"],
    "pii_masking": ["/browse/{dataset_id}/preview"],
    "policy_before_query": ["/browse/query", "/policy/decision"],
    "purpose_binding": ["/policy/decision"],
    "row_limit": ["/browse/query", "/llm/draft-query"],
    "sample_budget": ["/browse/{dataset_id}/preview"],
    "timeout_ms": ["/browse/query", "/llm/draft-query"],
}


def connector_probe(connector_id: str, dataset_id: str) -> dict[str, Any]:
    connectors = {connector.id: connector for connector in connector_registry_manifest()}
    connector = connectors.get(connector_id)
    if not connector:
        raise ValueError(f"unsupported connector id: {connector_id}")

    dataset = get_dataset(dataset_id)
    if not dataset:
        raise KeyError(dataset_id)

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

    ready_for_demo = implemented_controls == len(connector.required_controls)
    return {
        "connector_id": connector.id,
        "dataset_id": dataset.id,
        "source_type": connector.source_type,
        "source_system": dataset.source_system,
        "status": "ready_for_demo" if ready_for_demo else "contract_only",
        "contract_methods": ["inspect_schema", "preview"],
        "data_contract": {
            "schema_fields": len(dataset.schema),
            "sensitivity": dataset.sensitivity,
            "quality_score": dataset.quality_score,
            "freshness_score": dataset.freshness_score,
        },
        "control_evidence": control_evidence,
        "proof": connector.proof,
    }
