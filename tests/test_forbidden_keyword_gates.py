"""The three gates that read the forbidden-keyword list must read it alike.

`validate_sql_query` matched keywords on word boundaries while `draft_sql` and
`execute_query` matched bare substrings, so the canonical validator and the two
routes disagreed on the same input: `select created_at from customer` drew no
warning from `validate_sql_query` and was rejected as hostile by
`/browse/query`.

The gates are checked here by enumerating the readers of the keyword list from
the module source, not by testing each one by hand. Testing them by hand is
precisely how the disagreement survived a fix to one of them.
"""

from __future__ import annotations

import ast
import pathlib

from fastapi.testclient import TestClient

from sdp import orchestrator
from sdp.api import app
from sdp_core import QueryDraftRequest, QueryExecutionRequest


client = TestClient(app)

# Ordinary warehouse identifiers that contain a forbidden keyword as a substring.
INNOCUOUS_IDENTIFIERS = (
    ("created_at", "create"),
    ("updated_at", "update"),
    ("deleted_flag", "delete"),
    ("merged_at", "merge"),
    ("locked_at", "lock"),
    ("granted_scope", "grant"),
    ("execution_count", "exec"),
    ("dropoff_rate", "drop"),
    ("intopic", "into"),
)


def test_the_keyword_list_has_exactly_one_reader() -> None:
    """One list, one matcher.

    Three readers drifted apart because each owned its own matching expression.
    This asserts structurally that only the matcher reads the list, so a fourth
    gate cannot quietly reintroduce substring semantics.
    """
    source = pathlib.Path(orchestrator.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)

    # Every function whose body loads the name, found by walking the AST rather
    # than grepping, so prose that merely mentions the list does not count.
    readers: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for inner in ast.walk(node):
            if isinstance(inner, ast.Name) and inner.id == "_FORBIDDEN_KEYWORDS":
                readers.add(node.name)

    assert readers == {"_matched_forbidden_keyword"}, (
        f"the keyword list has readers other than the shared matcher: {sorted(readers)}. "
        "Route the new one through _matched_forbidden_keyword instead of matching "
        "the list again - three call sites drifted apart exactly this way."
    )


def test_the_matcher_accepts_identifiers_and_still_catches_keywords() -> None:
    """Word boundaries, not substrings."""
    for identifier, swallowed_keyword in INNOCUOUS_IDENTIFIERS:
        assert swallowed_keyword in identifier, "fixture no longer demonstrates the overlap"
        assert orchestrator._matched_forbidden_keyword(identifier) is None, identifier
        # The bare keyword is still caught.
        assert orchestrator._matched_forbidden_keyword(swallowed_keyword) == swallowed_keyword

    assert orchestrator._matched_forbidden_keyword("select customer_id from customer") is None
    assert orchestrator._matched_forbidden_keyword("drop table customer") == "drop"
    assert orchestrator._matched_forbidden_keyword("select * into exfil from customer") == "into"


def test_every_gate_returns_the_same_verdict_on_the_same_sql() -> None:
    """The validator and the executor must not disagree about one SQL string."""
    source_system = "postgresql://analytics.dw/customer"

    def validator_flags(sql: str) -> bool:
        warnings = orchestrator.validate_sql_query(sql, source_system=source_system)
        return "forbidden_keyword_detected" in warnings

    def executor_flags(sql: str) -> bool:
        response = orchestrator.execute_query(
            QueryExecutionRequest(
                language="SQL",
                user="analyst",
                purpose="analysis",
                dataset_ids=["crm-customer-master"],
                query=sql,
            )
        )
        return "forbidden_keyword_detected" in response.warnings

    accepted = "select customer_id from customer"
    identifier_shaped = "select created_at from customer"
    hostile = "select customer_id from customer drop"

    for sql in (accepted, identifier_shaped, hostile):
        assert validator_flags(sql) == executor_flags(sql), (
            f"validator and executor disagree about {sql!r}: "
            f"validator={validator_flags(sql)} executor={executor_flags(sql)}"
        )

    assert validator_flags(accepted) is False
    assert validator_flags(identifier_shaped) is False
    assert validator_flags(hostile) is True


def test_browse_query_accepts_a_query_whose_column_merely_contains_a_keyword() -> None:
    """End to end: the only difference between these two calls is a column name."""
    def post(sql: str):
        return client.post(
            "/browse/query",
            json={
                "user": "analyst",
                "dataset_ids": ["crm-customer-master"],
                "language": "SQL",
                "query": sql,
                "purpose": "analysis",
            },
        )

    control = post("select customer_id from crm_customer_master")
    assert control.status_code == 200, control.text

    measured = post("select created_at from crm_customer_master")
    assert measured.status_code == 200, measured.text
    assert "forbidden_keyword_detected" not in measured.json()["warnings"]

    hostile = post("select customer_id from crm_customer_master drop")
    assert hostile.status_code == 400
    assert "forbidden_keyword_detected" in hostile.json()["detail"]["warnings"]


def test_draft_query_accepts_a_question_naming_such_a_column_and_names_the_keyword() -> None:
    """The NL drafter shared the defect, and its refusal named no keyword."""
    def draft(question: str):
        return client.post(
            "/llm/draft-query",
            json={
                "user": "analyst",
                "dataset_id": "crm-customer-master",
                "question": question,
                "purpose": "analysis",
            },
        )

    allowed = draft("월별 가입 추이를 created_at 기준으로 보여줘")
    assert allowed.status_code == 200, allowed.text
    assert "error" not in allowed.json(), allowed.text

    refused = draft("고객 테이블을 drop 해줘")
    # 403, not 200: this route used to answer 200 for every failure, and my own
    # assertion here pinned that shape. The body moved under `detail` with the
    # status.
    assert refused.status_code == 403, refused.text
    body = refused.json()["detail"]
    assert body["error"] == "policy_denied"
    # The refusal says which word was refused, so a spurious one is diagnosable.
    assert body["reason"].endswith(": drop"), body["reason"]


def test_draft_sql_direct_call_shares_the_same_verdict() -> None:
    """The module-level drafter, not only the route."""
    def drafted(question: str) -> dict:
        return orchestrator.draft_sql(
            QueryDraftRequest(
                question=question,
                user="analyst",
                purpose="analysis",
                dataset_id="crm-customer-master",
            )
        )

    assert "error" not in drafted("deleted_flag 가 null 인 고객 수")
    assert drafted("drop 고객")["error"] == "policy_denied"
