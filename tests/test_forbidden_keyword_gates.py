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


# Keyword tokens that a SQL lexer splits off but ``\b`` does not.
# ``\b`` sits between a word character and a non-word character, and Python's
# ``\w`` is Unicode-aware, so a digit or a non-ASCII letter immediately before a
# keyword is *not* a boundary: ``\bunion\b`` does not match ``1union`` or
# ``\ud55cunion``. Real engines do split there - MySQL reads ``SELECT 1union`` as
# ``1 union`` - so the token is live while the guard is blind.
#
# This is a regression the unified matcher introduced. The two gates it replaced
# (``draft_sql`` and ``audit``) matched bare substrings, which caught every shape
# below; folding them onto ``validate_sql_query``'s word-boundary predicate fixed
# their false refusals and inherited its blind spot in the same move. Replacing
# three predicates with one is only safe if the survivor is at least as strict as
# each; it was not. ContextualWisdomLab/semantic-data-portal#107 found this
# boundary independently and chose the asymmetric predicate adopted here.
LEXER_SPLIT_PREFIXES = ("1", "9", "0x1", "\ud55c", "\u00e9", "\u00b2")


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


def test_the_matcher_sees_the_boundary_a_digit_or_non_ascii_prefix_hides() -> None:
    r"""A keyword a lexer splits off must still be a keyword to the guard.

    The accepted side of this contract is the point of the asymmetry: a keyword
    *followed* by an ASCII identifier character stays accepted, because that is
    an identifier (``updated_at``), while a keyword *preceded* by a digit or a
    non-ASCII character is refused, because that is a token boundary the engine
    honours and the previous predicate did not.
    """
    for prefix in LEXER_SPLIT_PREFIXES:
        for keyword in ("union", "drop", "into"):
            probe = f"{prefix}{keyword}"
            assert orchestrator._matched_forbidden_keyword(probe) == keyword, probe

    # The asymmetry, held in both directions on one keyword.
    assert orchestrator._matched_forbidden_keyword("1update") == "update"
    assert orchestrator._matched_forbidden_keyword("update1") is None
    assert orchestrator._matched_forbidden_keyword("updated") is None
    assert orchestrator._matched_forbidden_keyword("my_update") is None

    # And the identifiers above stay accepted, so the fix is not "refuse more".
    for identifier, _ in INNOCUOUS_IDENTIFIERS:
        assert orchestrator._matched_forbidden_keyword(identifier) is None, identifier


def test_browse_query_refuses_a_union_the_lexer_splits_off_a_number() -> None:
    """End to end, on the shape that passed every gate with no warning at all.

    ``limit 1union all`` drew an empty warning list from ``validate_sql_query``
    before this: not a different refusal, no refusal.
    """
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

    spaced = post("select customer_id from crm_customer_master limit 1 union all")
    assert spaced.status_code == 400, spaced.text
    assert "forbidden_keyword_detected" in spaced.json()["detail"]["warnings"]

    # The same statement with the one space removed.
    joined = post("select customer_id from crm_customer_master limit 1union all")
    assert joined.status_code == 400, joined.text
    assert "forbidden_keyword_detected" in joined.json()["detail"]["warnings"]


def test_the_property_lane_presses_the_same_boundary_as_production() -> None:
    """The shared crash oracle must not be the weaker predicate.

    ``tests/fuzz/invariants.py`` encodes the keyword contract independently so a
    production regression is a property failure rather than a silent agreement.
    An oracle weaker than production never fails falsely - and never presses the
    class it dropped either, which is the whole reason the property lane exists.
    The predicate is re-derived there rather than imported, so this compares two
    implementations instead of a regex with itself.
    """
    from tests.fuzz import invariants

    corpus = [f"{prefix}{keyword}" for prefix in LEXER_SPLIT_PREFIXES for keyword in ("union", "drop")]
    corpus += [identifier for identifier, _ in INNOCUOUS_IDENTIFIERS]
    corpus += ["select customer_id from customer", "drop table customer", "update1", "my_update"]

    for probe in corpus:
        production = orchestrator._matched_forbidden_keyword(probe) is not None
        oracle = invariants.forbidden_keyword_present(probe)
        assert production == oracle, (
            f"production and the fuzz oracle disagree about {probe!r}: "
            f"production={production} oracle={oracle}"
        )
