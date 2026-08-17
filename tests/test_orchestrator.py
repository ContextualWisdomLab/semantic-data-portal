"""SQL-safety + query-draft guard tests for the orchestrator.

``validate_sql_query`` is the SELECT-only / single-statement / no-comment /
no-literal / no-boolean / no-forbidden-keyword / source-table-allowlist guard
(the Atheris fuzz target). ``draft_sql`` / ``execute_query`` are the policy- and
schema-gated query paths. These pin the reject branches directly so a refactor
cannot silently loosen the injection guards. Each call records policy/audit
evidence, so the in-memory stores are snapshot/restored.
"""

from __future__ import annotations

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sdp import catalog, evidence, orchestrator as orch  # noqa: E402
from sdp.domain import QueryDraftRequest, QueryExecutionRequest  # noqa: E402

_CRM = "crm-customer-master"
_SRC = "postgresql://analytics.dw/customer"  # -> table name "customer"


@pytest.fixture(autouse=True)
def _isolate_state():
    data = {k: v.model_copy(deep=True) for k, v in catalog._DATA.items()}
    audit = list(catalog._AUDIT_LOG)
    decisions = list(evidence._POLICY_DECISION_LOG)
    try:
        yield
    finally:
        catalog._DATA.clear()
        catalog._DATA.update(data)
        catalog._AUDIT_LOG.clear()
        catalog._AUDIT_LOG.extend(audit)
        evidence._POLICY_DECISION_LOG.clear()
        evidence._POLICY_DECISION_LOG.extend(decisions)


# --- validate_sql_query (the injection guard / fuzz target) --------------


def test_validate_sql_query_accepts_clean_single_select() -> None:
    assert orch.validate_sql_query("SELECT customer_id FROM customer", source_system=_SRC) == []


def test_validate_sql_query_accepts_projection_commas_in_derived_table() -> None:
    """Projection commas inside a derived table are not relation separators."""

    warnings = orch.validate_sql_query(
        "SELECT count(*) AS c FROM (SELECT customer_id, signup_at FROM customer) t",
        source_system=_SRC,
    )

    assert "unauthorized_table_reference" not in warnings


def test_split_top_level_commas_preserves_nested_relations() -> None:
    """The relation scanner splits only commas outside parenthesized regions."""

    assert orch._split_top_level_commas(
        "customer, (SELECT customer_id, signup_at FROM customer) nested"
    ) == [
        "customer",
        " (SELECT customer_id, signup_at FROM customer) nested",
    ]


def test_validate_sql_query_flags_table_smuggled_past_nested_where() -> None:
    """A derived table's own WHERE must not truncate the outer relation list.

    Regression for a clause-boundary scan that wasn't parenthesis-depth-aware:
    the nested ``WHERE`` inside the derived table used to end the *outer*
    FROM-clause scan before the comma-joined ``customer`` after it was ever
    seen, letting an unauthorized table slip past the allowlist.
    """

    warnings = orch.validate_sql_query(
        "SELECT * FROM (SELECT customer_id FROM customer WHERE customer_id > 0) t, other_table",
        source_system=_SRC,
    )

    assert "unauthorized_table_reference" in warnings


def test_validate_sql_query_flags_coderabbit_nested_where_outer_relation() -> None:
    """Exact current-head PoC: nested WHERE must not hide the outer comma join.

    ``SELECT * FROM (SELECT customer_id FROM crm WHERE customer_id > 0) t, customer``
    with allowlisted ``crm`` must still see the trailing ``customer``.
    """

    warnings = orch.validate_sql_query(
        "SELECT * FROM (SELECT customer_id FROM crm WHERE customer_id > 0) t, customer",
        source_system="s3://analytics/events/crm",
    )

    assert "unauthorized_table_reference" in warnings
    assert set(orch._from_clause_tables(
        "SELECT * FROM (SELECT customer_id FROM crm WHERE customer_id > 0) t, customer"
    )) >= {"crm", "customer"}


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM crm, (customer JOIN secrets ON crm.id = customer.id) j",
        "SELECT * FROM crm LEFT JOIN (customer JOIN secrets ON customer.id = secrets.id) j ON crm.id = j.id",
        "SELECT * FROM ((customer JOIN secrets ON customer.id = secrets.id)) j",
        "SELECT * FROM crm, LATERAL (SELECT * FROM customer) s",
        "SELECT * FROM crm LEFT OUTER JOIN customer ON crm.id = customer.id",
        "SELECT * FROM crm RIGHT OUTER JOIN customer ON crm.id = customer.id",
        "SELECT * FROM crm FULL OUTER JOIN customer ON crm.id = customer.id",
        "SELECT * FROM crm CROSS JOIN customer",
        "SELECT * FROM crm NATURAL JOIN customer",
        "SELECT * FROM crm, customer",
        "SELECT * FROM (SELECT * FROM customer) t",
        "SELECT * FROM (SELECT * FROM crm JOIN extra ON crm.id = extra.id WHERE x > 0) t, customer",
        "SELECT * FROM other_table, (SELECT customer_id FROM crm WHERE customer_id > 0) t",
        "SELECT * FROM (SELECT a FROM customer) leak1, (SELECT b FROM secrets) leak2, crm",
        "SELECT * FROM crm WHERE EXISTS (SELECT * FROM customer)",
        "SELECT * FROM analytics.customer",
        "SELECT * FROM (SELECT * FROM crm WHERE x > 0 t, customer",
    ],
)
def test_validate_sql_query_rejects_adversarial_unauthorized_relations(sql: str) -> None:
    """Nested / CTE-adjacent / parenthesized / OUTER / comma smuggles fail closed."""

    warnings = orch.validate_sql_query(sql, source_system="s3://analytics/events/crm")

    assert "unauthorized_table_reference" in warnings


@pytest.mark.parametrize(
    "sql,expected",
    [
        ("WITH x AS (SELECT * FROM customer) SELECT * FROM crm", "only_select_allowed"),
        ("WITH x AS (SELECT * FROM crm) SELECT * FROM crm", "only_select_allowed"),
    ],
)
def test_validate_sql_query_rejects_cte_wrapper(sql: str, expected: str) -> None:
    """CTEs are not SELECT-leading and must stay rejected even when tables match."""

    warnings = orch.validate_sql_query(sql, source_system="s3://analytics/events/crm")

    assert expected in warnings


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT customer_id FROM customer",
        "SELECT count(*) AS c FROM (SELECT customer_id, signup_at FROM customer) t",
        "SELECT * FROM (SELECT customer_id FROM customer WHERE customer_id > 0) t",
        "SELECT * FROM (customer JOIN customer ON customer.id = customer.id) j",
        "SELECT * FROM customer, (SELECT customer_id FROM customer WHERE customer_id > 0) t",
        "SELECT * FROM customer LEFT JOIN (SELECT customer_id FROM customer) t ON customer.id = t.customer_id",
        "SELECT * FROM customer, LATERAL (SELECT customer_id FROM customer) s",
        "SELECT * FROM ONLY customer",
    ],
)
def test_validate_sql_query_preserves_allowlisted_shapes(sql: str) -> None:
    """Legitimate single-source SQL, including derived tables and paren joins, stays allowed."""

    assert orch.validate_sql_query(sql, source_system=_SRC) == []


def test_parentheses_balanced_and_outer_group_split() -> None:
    """Paren helpers fail closed on unclosed groups and unwrap one layer."""

    assert orch._parentheses_balanced("SELECT * FROM (SELECT a FROM crm) t")
    assert not orch._parentheses_balanced("SELECT * FROM (SELECT a FROM crm")
    assert not orch._parentheses_balanced("SELECT * FROM crm)")
    assert orch._split_outer_paren_group("(customer JOIN secrets ON x = y) j") == (
        "customer JOIN secrets ON x = y",
        " j",
    )
    assert orch._split_outer_paren_group("(SELECT a FROM crm") is None
    assert orch._split_outer_paren_group("customer") is None


def test_collect_relations_from_parenthesized_join() -> None:
    """Parenthesized joined tables contribute both sides to the allowlist set."""

    tables: list[str] = []
    orch._collect_relations_from_region(
        "crm, (customer JOIN secrets ON crm.id = customer.id) j",
        tables,
    )

    assert tables == ["crm", "customer", "secrets"]


@pytest.mark.parametrize(
    "sql,expected",
    [
        ("UPDATE customer SET x=1", "only_select_allowed"),
        ("SELECT customer_id FROM customer; SELECT 1", "single_statement_required"),
        ("SELECT customer_id FROM customer -- sneaky", "sql_comments_not_allowed"),
        ("SELECT customer_id FROM customer /* c */", "sql_comments_not_allowed"),
        ("SELECT 'x' FROM customer", "literal_values_not_allowed"),
        ("SELECT customer_id FROM customer WHERE a AND b", "boolean_operator_not_allowed"),
        ("SELECT drop FROM customer", "forbidden_keyword_detected"),
        ("SELECT 1", "missing_source_table"),
        ("SELECT customer_id FROM other_table", "unauthorized_table_reference"),
    ],
)
def test_validate_sql_query_flags_unsafe_input(sql: str, expected: str) -> None:
    assert expected in orch.validate_sql_query(sql, source_system=_SRC)


# --- draft_sql guard branches --------------------------------------------


def _draft(**over):
    base = dict(question="active customers", user="admin", purpose="analysis", dataset_id=_CRM)
    base.update(over)
    return orch.draft_sql(QueryDraftRequest(**base))


def test_draft_sql_rejects_unpublished_dataset() -> None:
    catalog._DATA["draft-ds"] = catalog._DATA[_CRM].model_copy(update={"id": "draft-ds", "status": "draft"})
    assert _draft(dataset_id="draft-ds")["error"] == "policy_denied"


def test_draft_sql_rejects_missing_schema() -> None:
    catalog._DATA["noschema-ds"] = catalog._DATA[_CRM].model_copy(update={"id": "noschema-ds", "schema": []})
    assert _draft(dataset_id="noschema-ds")["error"] == "missing_schema"


def test_draft_sql_rejects_forbidden_keyword_in_question() -> None:
    assert _draft(question="please drop the table")["error"] == "policy_denied"


def test_draft_sql_rejects_unknown_columns() -> None:
    assert _draft(columns=["ghost_column"])["error"] == "invalid_columns"


def test_draft_sql_explicit_columns_and_pii() -> None:
    """Explicit (non-'*') columns build a column SELECT; PII-in-analysis adds the
    masking assumption."""
    result = _draft(columns=["customer_id"])  # no group_by -> the explicit-column SELECT branch
    assert "query" in result and result["requested_columns"] == ["customer_id"]
    assert "customer_id" in result["query"]
    # customer_email is PII and purpose is analysis -> the PII masking assumption is added.
    assert any("PII" in a for a in result["assumptions"])


def test_draft_sql_date_group_by_adds_date_assumption() -> None:
    """A date-like group key adds the period-aggregation assumption (group-by branch)."""
    result = _draft(group_by="signup_at")
    assert "query" in result
    assert any("날짜" in a for a in result["assumptions"])


def test_draft_sql_default_builds_count_query() -> None:
    """With no columns and no group-by, the draft is a bounded count(*) SELECT."""
    result = _draft()  # defaults: requested_columns == ['*']
    assert result["requested_columns"] == ["*"]
    assert "count(*)" in result["query"] and result["query"].startswith("SELECT ")


# --- execute_query dry-run path ------------------------------------------


def test_execute_query_dry_run_succeeds_with_zero_rows() -> None:
    resp = orch.execute_query(
        QueryExecutionRequest(
            dataset_ids=[_CRM],
            query="SELECT customer_id FROM customer",
            user="admin",
            purpose="analysis",
            dry_run=True,
        )
    )
    assert resp.status == "SUCCEEDED"
    assert resp.row_count == 0
