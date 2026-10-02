"""Regression tests for the independent query-execution crash oracle."""

from __future__ import annotations

import pytest

from sdp import orchestrator
from sdp.domain import QueryExecutionRequest
from tests.fuzz import invariants


# Explicit expected corpus: do not derive the test cases from a regex/helper
# whose regression the oracle is meant to catch.
_KEYWORDS = ("drop", "delete", "truncate", "alter", "insert", "update", "merge", "exec", "union")
_BOUNDARIES = [
    ("", "", True),
    ("1", "", True),
    ("9", "", True),
    ("한", "", True),
    ("", "한", True),
    ("é", "", True),
    ("", "é", True),
    ("²", "", True),
    ("", "²", True),
    ("١", "", True),
    ("", "١", True),
    (".", "", True),
    ("", ".", True),
    ("a", "", False),
    ("A", "", False),
    ("_", "", False),
    ("", "a", False),
    ("", "A", False),
    ("", "_", False),
    ("", "1", False),
    ("1", "1", False),
    # Python IGNORECASE treats these Unicode letters as part of [a-z].
    ("ſ", "", False),
    ("", "ſ", False),
    ("K", "", False),
    ("", "K", False),
    ("ı", "", False),
    ("", "ı", False),
    ("İ", "", True),  # lower() expands to i + combining dot before the token
    ("", "İ", False),
]


@pytest.mark.parametrize("fragment", ["1union", "한union", "union한", "²union", "union²"])
def test_execute_oracle_catches_boundary_false_success(monkeypatch, fragment):
    req = QueryExecutionRequest(
        dataset_ids=["crm-customer-master"],
        query=f"SELECT {fragment} FROM customer",
        user="admin",
        purpose="analysis",
    )
    real = orchestrator.execute_query(req)
    assert real.status == "REJECTED"
    assert [warning.partition(":")[0] for warning in real.warnings] == ["forbidden_keyword_detected"]
    false_success = real.model_copy(update={"status": "SUCCEEDED"})
    monkeypatch.setattr(orchestrator, "execute_query", lambda request: false_success)

    # The oracle must independently catch a regressed executor, not ask the
    # production keyword helper to validate its own result.
    def forbidden_helper_must_not_run(text):
        pytest.fail("oracle called the production keyword helper")

    monkeypatch.setattr(orchestrator, "_has_forbidden_keyword", forbidden_helper_must_not_run)
    with pytest.raises(AssertionError, match="forbidden keyword was not rejected"):
        invariants.check_execute_query(req)


def test_execute_oracle_preserves_updated_at():
    req = QueryExecutionRequest(
        dataset_ids=["crm-customer-master"],
        query="SELECT updated_at FROM customer",
        user="admin",
        purpose="analysis",
    )
    assert orchestrator.validate_sql_query(req.query, source_system="customer") == []
    assert orchestrator.execute_query(req).status == "SUCCEEDED"
    invariants.check_execute_query(req)


@pytest.mark.parametrize("keyword", _KEYWORDS)
@pytest.mark.parametrize("uppercase", [False, True], ids=["lower", "upper"])
@pytest.mark.parametrize("prefix,suffix,rejected", _BOUNDARIES)
def test_execute_oracle_matches_runtime_boundaries(monkeypatch, keyword, uppercase, prefix, suffix, rejected):
    assert set(_KEYWORDS) == orchestrator._FORBIDDEN_KEYWORDS
    token = keyword.upper() if uppercase else keyword
    req = QueryExecutionRequest(
        dataset_ids=["crm-customer-master"],
        query=f"SELECT {prefix}{token}{suffix} FROM customer",
        user="admin",
        purpose="analysis",
    )
    warnings = orchestrator.validate_sql_query(req.query, source_system="customer")
    real = orchestrator.execute_query(req)
    if rejected:
        assert [warning.partition(":")[0] for warning in warnings] == ["forbidden_keyword_detected"]
        assert real.status == "REJECTED"
        assert [warning.partition(":")[0] for warning in real.warnings] == ["forbidden_keyword_detected"]
    else:
        assert warnings == []
        assert real.status == "SUCCEEDED"
        assert real.policy_decision_id  # reached the real allow-policy path
    invariants.check_execute_query(req)

    # Force an incorrect success only after validating the real runtime path.
    # Block helper delegation so the oracle remains an independent assertion.
    false_success = real.model_copy(update={"status": "SUCCEEDED"})
    monkeypatch.setattr(orchestrator, "execute_query", lambda request: false_success)

    def forbidden_helper_must_not_run(text):
        pytest.fail("oracle called the production keyword helper")

    monkeypatch.setattr(orchestrator, "_has_forbidden_keyword", forbidden_helper_must_not_run)
    if rejected:
        with pytest.raises(AssertionError, match="forbidden keyword was not rejected"):
            invariants.check_execute_query(req)
    else:
        invariants.check_execute_query(req)
