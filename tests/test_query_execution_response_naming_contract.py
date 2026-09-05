from __future__ import annotations

from sdp_core.contracts import QueryExecutionResponse


_RESPONSE_BASE = {
    "request_id": "req-1",
    "dataset_id": "crm-customer-master",
    "query_id": "qry-1",
    "policy_decision_id": "decision-1",
    "row_count": 1,
    "columns": ["result"],
    "rows": [{"result": 1}],
}


def test_query_execution_response_owns_semantic_fields() -> None:
    response = QueryExecutionResponse(
        **_RESPONSE_BASE,
        query_status="SUCCEEDED",
        execution_metadata={"elapsedMs": 100, "source": "mock-trino"},
        query_warnings=["mock_execution_no_real_data"],
    )

    assert {"query_status", "execution_metadata", "query_warnings"} <= set(
        QueryExecutionResponse.model_fields
    )
    assert {"status", "execution", "warnings"}.isdisjoint(QueryExecutionResponse.model_fields)
    assert response.query_status == "SUCCEEDED"
    assert response.execution_metadata["source"] == "mock-trino"
    assert response.query_warnings == ["mock_execution_no_real_data"]


def test_query_execution_response_preserves_legacy_wire_contract() -> None:
    response = QueryExecutionResponse(
        **_RESPONSE_BASE,
        status="SUCCEEDED",
        execution={"elapsedMs": 100, "source": "mock-trino"},
        warnings=["mock_execution_no_real_data"],
    )

    assert response.status == response.query_status
    assert response.execution == response.execution_metadata
    assert response.warnings == response.query_warnings

    wire_payload = response.model_dump(mode="json", by_alias=True)
    assert wire_payload["status"] == "SUCCEEDED"
    assert wire_payload["execution"]["source"] == "mock-trino"
    assert wire_payload["warnings"] == ["mock_execution_no_real_data"]
    assert "query_status" not in wire_payload
    assert "execution_metadata" not in wire_payload
    assert "query_warnings" not in wire_payload
