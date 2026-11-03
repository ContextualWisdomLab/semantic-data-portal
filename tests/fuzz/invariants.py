"""Invariant checks shared by the Hypothesis property tests and the Atheris
coverage-guided harnesses.

Each function raises ``AssertionError`` when an invariant is violated. Keeping
them here means the crash-oracle is identical no matter which fuzzing engine
drives the code under test.
"""

from __future__ import annotations

import re

from typing import Any

from sdp import catalog, evidence, observability, ontology, orchestrator
from sdp.domain import QueryDraftRequest, QueryExecutionRequest, QueryExecutionResponse

# Anything the query drafter/executor must never let through unescaped.
FORBIDDEN_KEYWORDS = orchestrator._FORBIDDEN_KEYWORDS

# The genuine injection-relevant contract: an emitted identifier must contain no
# ASCII whitespace and no SQL metacharacter. (NB: fuzzing surfaced that
# ``str.isalnum()`` is Unicode-aware, so non-ASCII letters/digits such as "²" or
# Korean survive sanitisation — harmless for injection since every quoting/
# terminator/whitespace byte is still mapped to "_", but see PR notes.)
_SQL_METACHARACTERS = set(" \t\r\n'\";()[]{}`*/\\%+-.,=<>!&|@#?:")


def forbidden_keyword_present(text: str) -> bool:
    r"""Whether ``text`` carries a forbidden keyword as a token.

    Re-derived here rather than calling ``orchestrator._matched_forbidden_keyword``
    on purpose: an oracle that calls the implementation it judges compares a
    regex with itself and cannot fail. The boundary is asymmetric - a digit or a
    non-ASCII character before a keyword is a boundary a SQL lexer honours
    (``1union`` is ``1 union``), an ASCII identifier character after it is not
    (``updated_at`` is a name). ``\b`` is the wrong predicate for both sides and
    was what stood here, which made this lane weaker than production and so
    blind to the class production had dropped.
    """
    lowered = text.lower()
    return any(
        re.search(rf"(?<![a-z_]){re.escape(token)}(?![a-z0-9_])", lowered)
        for token in FORBIDDEN_KEYWORDS
    )


def reset_in_memory_state() -> None:
    """Clear the in-memory append-only stores between fuzz iterations.

    ``execute_query`` and ``draft_sql`` record a policy decision plus an audit
    event on every call. Across a bounded-time coverage-guided run that is
    hundreds of thousands of iterations, so the unbounded ``list`` accumulators
    (``catalog._AUDIT_LOG``, ``evidence._POLICY_DECISION_LOG``) grew the process
    past libFuzzer's rss limit and aborted the run with an ``oom-*`` exit — a
    fuzz-harness state-accumulation artifact, not a logic bug in the code under
    test. The pytest suite avoids this with an autouse isolation fixture; the
    fuzz harnesses have none, so reset here. Only append-only growth is cleared;
    the seeded catalog datasets (``catalog._DATA``) are left intact so the code
    under test still has data to operate on.
    """
    catalog._AUDIT_LOG.clear()
    catalog._SCHEMA_HISTORY.clear()
    evidence._POLICY_DECISION_LOG.clear()
    observability.reset_request_observability()


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
    reset_in_memory_state()  # bound append-only evidence growth across iterations
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


# A character the table-list tokeniser keeps inside one token *and*
# ``_safe_identifier`` rewrites to "_". Both properties together are what let a
# reference collide with an authorised name that already contains "_" - and
# every relation in this catalogue contains one. ASCII "." and "$"; above
# U+007F, any non-alphanumeric character, of which these three are real "."
# confusables a warehouse would read as separators.
COLLIDING_SEPARATORS = (".", "$", "\u00b7", "\u2024", "\uff0e")


def near_miss_reference(name: str, separator: str, seam: int) -> str | None:
    """Rewrite one ``_`` of ``name`` into a character that normalises back to it.

    Returns ``None`` when ``name`` has no underscore to rewrite, so a caller
    that cannot build a near miss can say so rather than quietly testing the
    authorised name against itself.

    This lives with the oracle rather than in either engine because it is what
    *defines* the region the allow-list was weakest in: both the Hypothesis
    strategy and the Atheris harness have to reach it by construction, and a
    second copy of the separator set is one more thing that can drift.
    """
    seams = [index for index, character in enumerate(name) if character == "_"]
    if not seams:
        return None
    index = seams[seam % len(seams)]
    return name[:index] + separator + name[index + 1 :]


def check_validate_sql_query(
    query: str, source_system: str, declared_relation: str | None
) -> None:
    """``validate_sql_query`` over arbitrary text, with and without a relation.

    ``declared_relation`` became a live input when the drafter and the allow-list
    stopped guessing the relation from the connection locator and started taking
    it from the catalog's declared ``postgresql.table`` distribution. The
    parameter is catalog-derived rather than caller-supplied, but it reaches the
    same comparison, so the fuzz seam covers it: an engine that only ever drove
    the locator path would stop exercising what production now does.

    The last assertion is the repair itself as an invariant: a statement naming
    exactly the declared relation is never refused as *unauthorized*. It may
    still be refused for other reasons (a keyword collision, a literal), which
    is why only that one warning is excluded.
    """
    warnings = orchestrator.validate_sql_query(
        query, source_system=source_system, declared_relation=declared_relation
    )
    assert isinstance(warnings, list)
    assert all(isinstance(item, str) for item in warnings)
    assert len(warnings) == len(set(warnings)), f"duplicated warning: {warnings}"
    if not query.strip().lower().startswith("select "):
        assert "only_select_allowed" in warnings
    if ";" in query:
        assert "single_statement_required" in warnings

    if declared_relation:
        relation = orchestrator._safe_identifier(declared_relation)
        # Whether the emitted name reads back as itself is asked of the
        # production parser, not re-derived here. The first version of this
        # invariant used "non-empty and not a clause keyword" and Hypothesis
        # refuted it with ``"0"``: a leading digit is not an identifier, so
        # ``FROM 0`` is not a table reference and ``FROM 0abc`` parses as the
        # table ``abc``. That counterexample is why ``source_relation_name``
        # now declines such a name instead of emitting it.
        if orchestrator._reads_back_as_one_table(relation):
            authorized = orchestrator.validate_sql_query(
                f"select count(*) from {relation} limit 1",
                source_system=source_system,
                declared_relation=relation,
            )
            assert "unauthorized_table_reference" not in authorized, (
                f"the declared relation {relation!r} was refused as unauthorized: "
                f"{authorized}"
            )

    # The converse, and the stronger half: anything the query references that is
    # not character-for-character the authorised name must be refused. The
    # allow-list used to normalise each reference through ``_safe_identifier``
    # before comparing, which manufactured matches wherever the authorised name
    # already contained the character normalisation produces - so against
    # declared ``crm_customer_master``, the references ``crm.customer_master``,
    # ``crm$customer_master``, ``crm_customer.master`` and the non-ASCII "."
    # confusables were all certified clean. Expressing the allow-list as a
    # property rather than a list of examples is what makes that a crash for
    # both engines; ``expected`` is computed exactly as production computes it,
    # including the fact that a supplied ``declared_relation`` is *not*
    # re-sanitised.
    authorized_name = (
        declared_relation
        if declared_relation
        else orchestrator._source_table_name(source_system)
    ).lower()
    references = orchestrator._referenced_source_tables(query)
    if references and any(table.lower() != authorized_name for table in references):
        assert "unauthorized_table_reference" in warnings, (
            f"{references!r} is not {authorized_name!r}, yet the allow-list did "
            f"not refuse it: {warnings}"
        )


def check_execute_query(req: QueryExecutionRequest) -> None:
    """``orchestrator.execute_query``: always returns a response; hostile SQL is
    rejected rather than marked SUCCEEDED."""
    reset_in_memory_state()  # bound append-only evidence growth across iterations
    resp = orchestrator.execute_query(req)
    assert isinstance(resp, QueryExecutionResponse)
    assert resp.status in {"SUCCEEDED", "REJECTED", "DENIED"}
    lowered = req.query.lower()
    # Word boundaries, independently re-implemented here rather than calling the
    # production matcher, so this stays a real check and not a tautology. The
    # previous substring predicate pinned the defect it was meant to guard: it
    # demanded that `select created_at from customer` be REJECTED, because
    # "create" is a substring of "created_at".
    if forbidden_keyword_present(lowered):
        assert resp.status == "REJECTED", "forbidden keyword was not rejected"
    if resp.status == "SUCCEEDED":
        assert resp.row_count >= 0
        assert isinstance(resp.rows, list)
