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


def test_draft_sql_joins_integer_date_window_without_string_literals() -> None:
    """Date windows are integer tokens, not interpolated SQL string literals."""
    result = _draft(date_window_days=7, row_limit=25)
    assert result["query"] == (
        "SELECT count(*) AS active_customer_count FROM customer "
        "WHERE created_at >= current_date - 7 LIMIT 25"
    )


def test_draft_sql_joins_reviewed_column_and_group_tokens() -> None:
    """Explicit columns and group-by stay reviewed identifiers in the draft."""
    grouped = _draft(columns=["customer_id"], group_by="signup_at", date_window_days=14)
    assert grouped["query"] == (
        "SELECT signup_at, count(*) AS active_customer_count FROM customer "
        "WHERE created_at >= current_date - 14 GROUP BY signup_at LIMIT 1000"
    )
    explicit = _draft(columns=["customer_id"], date_window_days=3, row_limit=10)
    assert explicit["query"] == (
        "SELECT customer_id, count(*) AS active_customer_count FROM customer "
        "WHERE created_at >= current_date - 3 LIMIT 10"
    )


def test_draft_sql_rejects_source_table_that_is_not_an_identifier() -> None:
    catalog._DATA["empty-source"] = catalog._DATA[_CRM].model_copy(
        update={"id": "empty-source", "source_system": "/"}
    )
    assert _draft(dataset_id="empty-source")["error"] == "invalid_source_table"


def test_draft_sql_fails_closed_when_renderer_rejects(monkeypatch) -> None:
    def reject(**_kwargs):
        raise ValueError("reviewed SQL slot rejected")

    monkeypatch.setattr(orch, "_render_reviewed_draft_sql", reject)
    assert _draft()["error"] == "invalid_sql_identifier"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"table_name": "customer;drop", "date_window_days": 7, "max_rows": 10, "select_columns": ["*"], "group_by": None},
        {"table_name": "customer", "date_window_days": True, "max_rows": 10, "select_columns": ["*"], "group_by": None},
        {"table_name": "customer", "date_window_days": 0, "max_rows": 10, "select_columns": ["*"], "group_by": None},
        {"table_name": "customer", "date_window_days": 7, "max_rows": 0, "select_columns": ["*"], "group_by": None},
        {"table_name": "customer", "date_window_days": 7, "max_rows": 10, "select_columns": ["id;drop"], "group_by": None},
        {"table_name": "customer", "date_window_days": 7, "max_rows": 10, "select_columns": ["*"], "group_by": "id;drop"},
    ],
)
def test_render_reviewed_draft_sql_rejects_unreviewed_slots(kwargs) -> None:
    with pytest.raises(ValueError, match="reviewed"):
        orch._render_reviewed_draft_sql(**kwargs)


def test_drafted_sql_is_rejected_by_execute_query_not_sent_to_a_driver() -> None:
    """A token-joined draft is review text; execute_query still fail-closes."""

    drafted = _draft(date_window_days=7, row_limit=25)["query"]
    assert "'" not in drafted
    assert '"' not in drafted
    resp = orch.execute_query(
        QueryExecutionRequest(
            dataset_ids=[_CRM],
            query=drafted,
            user="admin",
            purpose="analysis",
            dry_run=False,
        )
    )
    assert resp.status == "REJECTED"
    assert "unsafe_select_expression" in resp.warnings
    assert resp.execution == {"elapsedMs": 0, "source": "query_safety", "bytesScanned": 0}
    assert resp.rows == []
    assert resp.columns == []


# --- execute_query dry-run path ------------------------------------------


def test_execute_query_dry_run_validates_with_zero_rows() -> None:
    resp = orch.execute_query(
        QueryExecutionRequest(
            dataset_ids=[_CRM],
            query="SELECT customer_id FROM customer",
            user="admin",
            purpose="analysis",
            dry_run=True,
        )
    )
    assert resp.status == "VALIDATED"
    assert resp.query_id == ""
    assert resp.row_count == 0
    assert resp.rows == []
    assert resp.columns == []
    assert resp.execution == {
        "elapsedMs": 0,
        "source": "validation",
        "bytesScanned": 0,
    }
