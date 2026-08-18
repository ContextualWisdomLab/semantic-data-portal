"""Regression contracts for fail-closed SQL function admission."""

from types import SimpleNamespace

import pytest

from sdp.domain import QueryExecutionRequest, QueryExecutionResponse
from sdp import orchestrator
from sdp.orchestrator import validate_sql_query


def _execute_query(monkeypatch, query: str) -> QueryExecutionResponse:
    """Run execute_query against a published CRM dataset with policy allow."""

    dataset = SimpleNamespace(id="dataset_one", source_system="crm")
    decision = SimpleNamespace(effect="allow", decision_id="decision_one", reason="ok")
    monkeypatch.setattr(orchestrator, "get_dataset", lambda _dataset_id: dataset)
    monkeypatch.setattr(orchestrator, "evaluate", lambda **_kwargs: decision)
    monkeypatch.setattr(orchestrator, "ingest_event", lambda **_kwargs: None)
    return orchestrator.execute_query(
        QueryExecutionRequest(
            language="SQL",
            user="analyst_one",
            purpose="analysis",
            dataset_ids=["dataset_one"],
            query=query,
            dry_run=False,
        )
    )


@pytest.mark.parametrize(
    "query",
    [
        "SELECT nextval(16385) FROM crm",
        "SELECT setval(16385, 1) FROM crm",
        "SELECT lo_creat(0) FROM crm",
        "SELECT lo_get(16386) FROM crm",
        "SELECT lo_lseek(16386, 0) FROM crm",
        "SELECT pg_advisory_lock(1) FROM crm",
        "SELECT pg_catalog.pg_advisory_lock(1) FROM crm",
        "SELECT unreviewed_extension_function(1) FROM crm",
    ],
)
def test_readonly_gate_rejects_unreviewed_function_calls(query: str) -> None:
    """Any function outside the reviewed read-only allowlist must fail closed."""
    warnings = validate_sql_query(query, source_system="crm")
    assert "unsafe_function_call" in warnings


@pytest.mark.parametrize(
    "query",
    [
        "SELECT count(*) FROM crm",
        "SELECT sum(amount) FROM crm",
        "SELECT avg(amount) FROM crm",
        "SELECT min(amount) FROM crm",
        "SELECT max(amount) FROM crm",
    ],
)
def test_readonly_gate_accepts_reviewed_aggregate_functions(query: str) -> None:
    """Reviewed aggregate functions remain available for ordinary analytics."""
    assert validate_sql_query(query, source_system="crm") == []


@pytest.mark.parametrize(
    "query",
    [
        "SELECT left_value + right_value FROM crm",
        "SELECT left_value::custom_type FROM crm",
        "SELECT (SELECT count(*) FROM crm) FROM crm",
        "SELECT count(*) OVER () FROM crm",
        "SELECT ARRAY[left_value] FROM crm",
        "SELECT crm.",
        "SELECT count FROM crm",
        "SELECT count() FROM crm",
        "SELECT count(* FROM crm",
        "SELECT id AS 1 FROM crm",
        "SELECT id, FROM crm",
        "SELECT id, 1 FROM crm",
        "SELECT id FROM crm AS",
        "SELECT id FROM crm GROUP",
        "SELECT id FROM crm GROUP BY",
        "SELECT id FROM crm GROUP BY id, 1",
        "SELECT id FROM crm ORDER",
        "SELECT id FROM crm ORDER BY",
        "SELECT id FROM crm LIMIT",
        "SELECT id FROM crm LIMIT all",
        "SELECT id FROM crm LIMIT 0",
        "SELECT id FROM crm LIMIT 2001",
    ],
)
def test_readonly_gate_rejects_non_allowlisted_select_expressions(
    monkeypatch, query: str
) -> None:
    """Operators, casts, subqueries, windows, and arrays must fail closed."""
    warnings = validate_sql_query(query, source_system="crm")
    assert "unsafe_select_expression" in warnings

    response = _execute_query(monkeypatch, query)
    assert response.status == "REJECTED"
    assert response.execution["source"] == "query_safety"
    assert "unsafe_select_expression" in response.warnings
    assert response.rows == []
    assert response.columns == []


@pytest.mark.parametrize(
    "query",
    [
        "SELECT id FROM crm ORDER BY id::unreviewed_type",
        "SELECT id FROM (SELECT id FROM crm) AS derived_rows",
        "SELECT id FROM crm WHERE id IN (SELECT id FROM crm)",
    ],
)
def test_readonly_gate_rejects_unsafe_syntax_outside_projection(
    monkeypatch, query: str
) -> None:
    """Casts, derived tables, and nested queries must fail closed in every clause."""
    warnings = validate_sql_query(query, source_system="crm")
    assert "unsafe_select_expression" in warnings

    response = _execute_query(monkeypatch, query)
    assert response.status == "REJECTED"
    assert response.execution["source"] == "query_safety"
    assert "unsafe_select_expression" in response.warnings
    assert response.rows == []
    assert response.columns == []


def test_readonly_gate_accepts_complete_reviewed_analytics_grammar() -> None:
    """The bounded group, sort, and row-limit surface remains buyer-usable."""
    query = (
        "SELECT customer_id, count(DISTINCT order_id) AS order_count "
        "FROM crm GROUP BY customer_id ORDER BY customer_id DESC LIMIT 25"
    )
    assert validate_sql_query(query, source_system="crm") == []


def test_readonly_gate_accepts_qualified_and_multi_column_sorting() -> None:
    """Qualified identifiers and per-column sort directions remain supported."""
    query = "SELECT crm.customer_id FROM crm ORDER BY customer_id ASC, order_id DESC"
    assert validate_sql_query(query, source_system="crm") == []


def test_readonly_gate_accepts_group_and_sort_lists_without_directions() -> None:
    """Grouping and sorting can contain more than one ordinary identifier."""
    query = "SELECT customer_id FROM crm GROUP BY customer_id, order_id ORDER BY customer_id, order_id"
    assert validate_sql_query(query, source_system="crm") == []


def test_execute_query_rejects_unsafe_sql_at_execution_boundary(monkeypatch) -> None:
    """Unsafe syntax must never pass the production execution boundary."""
    response = _execute_query(
        monkeypatch,
        "SELECT id FROM crm ORDER BY id::unreviewed_type",
    )

    assert response.status == "REJECTED"
    assert response.execution["source"] == "query_safety"
    assert "unsafe_select_expression" in response.warnings
    assert response.rows == []
    assert response.columns == []
