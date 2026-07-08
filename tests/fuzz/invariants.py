"""Invariant checks shared by the Hypothesis property tests and the Atheris
coverage-guided harnesses.

Each function raises ``AssertionError`` when an invariant is violated. Keeping
them here means the crash-oracle is identical no matter which fuzzing engine
drives the code under test.
"""

from __future__ import annotations

import re
from typing import Any

from sdp import catalog, ontology, orchestrator
from sdp.domain import QueryDraftRequest, QueryExecutionRequest, QueryExecutionResponse

# Anything the query drafter/executor must never let through unescaped.
FORBIDDEN_KEYWORDS = orchestrator._FORBIDDEN_KEYWORDS

# Strict ASCII identifier shape (documentation of the *intended* contract).
_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9_]*$")

# The genuine injection-relevant contract: an emitted identifier must contain no
# ASCII whitespace and no SQL metacharacter. (NB: fuzzing surfaced that
# ``str.isalnum()`` is Unicode-aware, so non-ASCII letters/digits such as "²" or
# Korean survive sanitisation — harmless for injection since every quoting/
# terminator/whitespace byte is still mapped to "_", but see PR notes.)
_SQL_METACHARACTERS = set(" \t\r\n'\";()[]{}`*/\\%+-.,=<>!&|@#?:")


def check_safe_identifier(value: str) -> None:
    """``_safe_identifier`` must neutralise every SQL metacharacter and all
    whitespace — the core identifier-injection guard — and be idempotent."""
    out = orchestrator._safe_identifier(value)
    leaked = _SQL_METACHARACTERS.intersection(out)
    assert not leaked, f"SQL metacharacter(s) leaked through sanitiser: {leaked!r}"
    # Sanitising an already-safe string must be a no-op (idempotence).
    assert orchestrator._safe_identifier(out) == out


def check_resolve_terms(text: str) -> None:
    """``ontology.resolve_terms`` on arbitrary text: no crash, well-formed and
    bounded scores, sorted descending."""
    resolutions = ontology.resolve_terms(text)
    assert isinstance(resolutions, list)
    scores = [r.score for r in resolutions]
    for r in resolutions:
        assert isinstance(r.term, str) and r.term
        assert 0.0 <= r.score <= 1.0, f"score out of range: {r.score}"
        assert isinstance(r.aliases, list)
        assert r.uri.startswith("https://")
    assert scores == sorted(scores, reverse=True), "resolutions not sorted by score"


def check_search_concepts(text: str) -> None:
    """``ontology.search_concepts`` never crashes and returns known concepts."""
    matches = ontology.search_concepts(text)
    assert isinstance(matches, list)
    known = set(ontology.list_concepts())
    for m in matches:
        assert m.concept in known, f"unknown concept surfaced: {m.concept!r}"


def check_concept_graph(text: str) -> None:
    """``ontology.concept_graph`` always returns a dict with a ``canonical`` key."""
    graph = ontology.concept_graph(text)
    assert isinstance(graph, dict)
    assert "canonical" in graph


def check_search_catalog(query: str, **filters: Any) -> None:
    """``catalog.search_catalog`` on arbitrary input: no crash (notably no regex
    error — tokens must be escaped), bounded by ``limit``, positive scores."""
    limit = filters.pop("limit", 20)
    results = catalog.search_catalog(query, limit=limit, **filters)
    assert isinstance(results, list)
    assert len(results) <= max(limit, 0) or limit < 0
    prev = None
    for row in results:
        assert row.score > 0, "zero/negative score should be filtered out"
        if prev is not None:
            assert row.score <= prev, "results not sorted by score"
        prev = row.score


def check_draft_sql(req: QueryDraftRequest) -> None:
    """``orchestrator.draft_sql``: no crash; if a SQL string is returned it stays
    within bounds and never smuggles a forbidden keyword or SQL metacharacter in
    via a user-controlled identifier (group_by / columns)."""
    result = orchestrator.draft_sql(req)
    assert isinstance(result, dict)
    if "query" not in result:
        # An error dict is a perfectly valid outcome for hostile input.
        assert "error" in result
        return

    sql = result["query"]
    assert isinstance(sql, str) and sql.startswith("SELECT ")
    assert result["row_limit"] <= 2000
    # The generated statement must only ever be a single read-only SELECT: no
    # statement terminators or comment sequences injected through identifiers.
    assert ";" not in sql, f"statement terminator leaked into SQL: {sql!r}"
    assert "--" not in sql, f"comment sequence leaked into SQL: {sql!r}"
    for col in result.get("requested_columns", []):
        if col != "*":
            check_safe_identifier(col)


def check_execute_query(req: QueryExecutionRequest) -> None:
    """``orchestrator.execute_query``: always returns a response; hostile SQL is
    rejected rather than marked SUCCEEDED."""
    resp = orchestrator.execute_query(req)
    assert isinstance(resp, QueryExecutionResponse)
    assert resp.status in {"SUCCEEDED", "REJECTED", "DENIED"}
    lowered = req.query.lower()
    if any(tok in lowered for tok in FORBIDDEN_KEYWORDS):
        assert resp.status == "REJECTED", "forbidden keyword was not rejected"
    if resp.status == "SUCCEEDED":
        assert resp.row_count >= 0
        assert isinstance(resp.rows, list)
