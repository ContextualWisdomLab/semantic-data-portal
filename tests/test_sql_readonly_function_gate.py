"""Regression contracts for fail-closed SQL function admission."""

import pytest

from sdp.orchestrator import validate_sql_query


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
    ],
)
def test_readonly_gate_rejects_non_allowlisted_select_expressions(query: str) -> None:
    """Operators, casts, subqueries, windows, and arrays must fail closed."""
    warnings = validate_sql_query(query, source_system="crm")
    assert "unsafe_select_expression" in warnings
