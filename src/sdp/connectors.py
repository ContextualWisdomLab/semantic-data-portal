from __future__ import annotations

from typing import Any

from sdp_core import SourceConnector, connector_registry_manifest

from .catalog import get_dataset
from .credentials import connector_secret_status


_IMPLEMENTED_PROOF = {
    "audit_event": ["/audit/events"],
    "credential_vault": ["/enterprise/connectors/{connector_id}/probe", "SDP_CONNECTOR_SECRET_REF_PREFIX"],
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

_PREVIEW_UNAVAILABLE = "source_preview_backend_not_configured"


def _preview_unavailable() -> list[dict[str, Any]]:
    """Reject source preview when no provider-backed data-plane adapter exists."""
    raise RuntimeError(_PREVIEW_UNAVAILABLE)


class DemoSQLConnector(SourceConnector):
    """Catalog-only SQL source adapter retained for compatibility until execution ships."""

    connector_id = "sql_connector"
    source_type = "warehouse_or_rdbms"

    def inspect_schema(self, dataset_id: str) -> dict[str, Any]:
        """Return persisted catalog schema without claiming a live SQL connection."""
        dataset = get_dataset(dataset_id)
        if not dataset:
            raise KeyError(dataset_id)
        if not dataset.source_system.startswith("postgresql://"):
            raise ValueError("dataset is not backed by the SQL connector contract")
        return {
            "dataset_id": dataset.id,
            "source_system": dataset.source_system,
            "columns": [column.model_dump() for column in dataset.schema],
        }

    def preview(self, dataset_id: str, *, limit: int, offset: int) -> list[dict[str, Any]]:
        """Fail closed until a PostgreSQL preview executor is configured."""
        del dataset_id, limit, offset
        return _preview_unavailable()


class DemoRDFConnector(SourceConnector):
    """Catalog-only RDF source adapter retained until a SPARQL client is implemented."""

    connector_id = "rdf_connector"
    source_type = "semantic_store"

    def inspect_schema(self, dataset_id: str) -> dict[str, Any]:
        """Return persisted RDF catalog metadata without issuing a SPARQL request."""
        dataset = get_dataset(dataset_id)
        if not dataset:
            raise KeyError(dataset_id)
        if not dataset.source_system.startswith("sparql://"):
            raise ValueError("dataset is not backed by the RDF connector contract")
        return {
            "dataset_id": dataset.id,
            "source_system": dataset.source_system,
            "named_graph": dataset.source_system.removeprefix("sparql://"),
            "columns": [column.model_dump() for column in dataset.schema],
        }

    def preview(self, dataset_id: str, *, limit: int, offset: int) -> list[dict[str, Any]]:
        """Fail closed until a SPARQL preview executor is configured."""
        del dataset_id, limit, offset
        return _preview_unavailable()


class DemoFileLakeConnector(SourceConnector):
    """Catalog-only lake source adapter retained until object-store reads are implemented."""

    connector_id = "file_lake_connector"
    source_type = "object_storage_or_lakehouse"

    def inspect_schema(self, dataset_id: str) -> dict[str, Any]:
        """Return catalog metadata for an S3-backed dataset without fetching objects."""
        dataset = get_dataset(dataset_id)
        if not dataset:
            raise KeyError(dataset_id)
        if not dataset.source_system.startswith("s3://"):
            raise ValueError("dataset is not backed by the file-lake connector contract")
        return {
            "dataset_id": dataset.id,
            "source_system": dataset.source_system,
            "manifest_path": f"{dataset.source_system.rstrip('/')}/_manifest.json",
            "columns": [column.model_dump() for column in dataset.schema],
        }

    def preview(self, dataset_id: str, *, limit: int, offset: int) -> list[dict[str, Any]]:
        """Fail closed until an object-store preview executor is configured."""
        del dataset_id, limit, offset
        return _preview_unavailable()


class DemoRESTConnector(SourceConnector):
    """Catalog-only REST source adapter retained until governed HTTP reads are implemented."""

    connector_id = "rest_connector"
    source_type = "governed_api"

    def inspect_schema(self, dataset_id: str) -> dict[str, Any]:
        """Return catalog metadata for an HTTP source without making a network request."""
        dataset = get_dataset(dataset_id)
        if not dataset:
            raise KeyError(dataset_id)
        if not dataset.source_system.startswith(("https://", "http://")):
            raise ValueError("dataset is not backed by the REST connector contract")
        return {
            "dataset_id": dataset.id,
            "source_system": dataset.source_system,
            "auth_mode": "service_account_reference",
            "columns": [column.model_dump() for column in dataset.schema],
        }

    def preview(self, dataset_id: str, *, limit: int, offset: int) -> list[dict[str, Any]]:
        """Fail closed until a governed HTTP preview executor is configured."""
        del dataset_id, limit, offset
        return _preview_unavailable()


_SOURCE_CONNECTORS: dict[str, SourceConnector] = {
    "sql_connector": DemoSQLConnector(),
    "rdf_connector": DemoRDFConnector(),
    "file_lake_connector": DemoFileLakeConnector(),
    "rest_connector": DemoRESTConnector(),
}


def get_source_connector(connector_id: str) -> SourceConnector:
    """Return a registered source contract or reject an unknown connector id."""
    connector = _SOURCE_CONNECTORS.get(connector_id)
    if not connector:
        raise ValueError(f"unsupported connector id: {connector_id}")
    return connector


def connector_probe(connector_id: str, dataset_id: str) -> dict[str, Any]:
    """Report connector control evidence without claiming unavailable data-plane reads."""
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
        adapter_status = "metadata_only"

    control_evidence = []
    satisfied_controls = 0
    for control in connector.required_controls:
        proof_endpoints = _IMPLEMENTED_PROOF.get(control, [])
        implemented = bool(proof_endpoints)
        satisfied = implemented
        evidence_payload: dict[str, Any] = {
            "control": control,
            "status": "implemented" if implemented else "planned",
            "proof_endpoints": proof_endpoints,
        }
        if control == "credential_vault":
            vault = connector_secret_status(connector_id, dataset_id)
            evidence_payload.update(vault.public_dict())
            satisfied = implemented and vault.secret_present
        satisfied_controls += int(satisfied)
        control_evidence.append(evidence_payload)

    controls_ready = satisfied_controls == len(connector.required_controls)
    return {
        "connector_id": connector.id,
        "dataset_id": dataset.id,
        "source_type": connector.source_type,
        "source_system": dataset.source_system,
        "status": "metadata_only" if source_adapter and controls_ready else "contract_only",
        "contract_methods": ["inspect_schema"],
        "adapter_status": adapter_status,
        "data_plane_preview_available": False,
        "data_contract": {
            "schema_fields": len(inspected_schema["columns"]) if inspected_schema else len(dataset.schema),
            "sensitivity": dataset.sensitivity,
            "quality_score": dataset.quality_score,
            "freshness_score": dataset.freshness_score,
        },
        "control_evidence": control_evidence,
        "proof": connector.proof,
    }
