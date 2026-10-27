from __future__ import annotations

import math
import re
from urllib.parse import unquote
from typing import Any
from datetime import datetime, timezone
from sdp_core.demo_seed import classify_source_type

from .authz import can_access_tenant
from .catalog import get_dataset, ingest_event
from .domain import QueryDraftRequest
from .policy import evaluate
from .domain import QueryExecutionRequest
from .domain import QueryExecutionResponse


# Statement-initiating or write-capable keywords. `into`, `create` and `copy`
# matter even though the guard already demands a leading `select `: PostgreSQL
# reads `SELECT ... INTO <name>` as CREATE TABLE AS, so a write can hide inside
# a statement that opens like the read the guard is looking for.
_FORBIDDEN_KEYWORDS = {
    "alter",
    "call",
    "copy",
    "create",
    "delete",
    "drop",
    "exec",
    "execute",
    "grant",
    "insert",
    "into",
    "lock",
    "merge",
    "prepare",
    "revoke",
    "truncate",
    "union",
    "update",
    "vacuum",
}

# A dollar-quoted string ($$text$$ or $tag$text$tag$) is a PostgreSQL string
# literal that contains neither quote character, so it smuggles an argument past
# a guard that only looks for ' and ".
_DOLLAR_QUOTE = re.compile(r"\$[A-Za-z_]*\$")

# Keywords that end a table list. Anything else following a table identifier is
# an alias (with or without AS) and is not itself a table.
_TABLE_CLAUSE_TERMINATORS = frozenset(
    {
        "cross",
        "except",
        "fetch",
        "from",
        "full",
        "group",
        "having",
        "inner",
        "intersect",
        "into",
        "join",
        "lateral",
        "left",
        "limit",
        "natural",
        "offset",
        "on",
        "order",
        "right",
        "select",
        "union",
        "using",
        "where",
        "window",
    }
)

# PostgreSQL's identifier continuation set is ``[A-Za-z\200-\377_0-9$]`` - it
# includes ``$`` and every byte at or above 0x80. The old token
# ``[A-Za-z_][\w.]*`` stopped at both, so it split one identifier into two and
# then discarded the second as an alias. Measured against an allow-list of
# ``customer``::
#
#     SELECT count(*) FROM customer$pii_raw LIMIT 1
#       warnings []            parsed ['customer']       <- certified clean
#     SELECT count(*) FROM customer×pii_raw LIMIT 1
#       warnings []            parsed ['customer']       <- certified clean
#     SELECT count(*) FROM secret$customer
#       warnings ['unauthorized_table_reference']        <- the prefix decides
#
# The engine resolves the single table ``customer$pii_raw``, so the allow-list
# proved a claim about a table name that is not the one the query names - the
# same unsoundness class as the comma-FROM bypass this repo rated critical and
# closed. Widening the token makes the reference parse whole and be compared,
# which is the fail-closed direction: a name the allow-list cannot prove is
# refused.
#
# Note on evidence: the PostgreSQL half is **measured**, not inferred. An
# independent verification of this finding stood up a throwaway UTF-8 cluster
# and ran it::
#
#     CREATE TABLE customer(a int);
#     CREATE TABLE customer$pii_raw(secret text);
#     INSERT INTO customer$pii_raw VALUES ('ssn-123-45-6789');
#     SELECT count(*), max(secret) FROM customer$pii_raw  -> 1 | ssn-123-45-6789
#     SELECT count(*) FROM customer                       -> 0
#
# with ``pg_tables`` listing ``customer``, ``customer$pii_raw`` and
# ``customer×pii_raw`` as three distinct tables, and the non-ASCII form
# behaving identically. So the unquoted reference this validator certified as
# ``customer`` really does resolve to a different table holding different rows.
# Nothing executes in *this* repository - ``execute_query`` is a mock engine -
# which is why the gate's own verdict is what the tests above measure.
_TABLE_LIST_TOKEN = re.compile(r"[(),]|[A-Za-z_\u0080-\uffff][\w.$\u0080-\uffff]*")

# Keywords that qualify the table item following them rather than being it.
# ``FROM ONLY customer`` and ``FROM a, LATERAL (...)`` both name a relation
# after the keyword; reading the keyword as the relation hid the real one from
# the allow-list entirely (``FROM ONLY customer`` was read as the table
# ``ONLY``, so ``customer`` was never checked - it failed closed only because
# no catalog relation is named ``only``).
_TABLE_ITEM_PREFIXES = frozenset({"lateral", "only"})

# A read-only certification cannot be given to a function it does not know.
# The literal guard already stops an argument-bearing call
# (``pg_read_file($$/etc/passwd$$)`` -> ``literal_values_not_allowed``), which
# left zero-argument and integer-argument calls in the safe lane. Measured, all
# with an allow-listed table and zero warnings before this gate::
#
#     SELECT pg_terminate_backend(12345) FROM customer   -> []
#     SELECT lo_unlink(1) FROM customer                  -> []
#     SELECT pg_sleep(100000) FROM customer              -> []
#     SELECT pg_reload_conf() FROM customer              -> []
#
# docs/prd-trd.md states BRW-005 ("read-only SELECT only ... block DDL/DML and
# unsafe functions") as P0 and NFR-SEC-007 repeats it, so this is a declared
# requirement rather than an extra. A deny-list is unbounded and therefore
# unsound; an allow-list is the only shape that can certify. This set is what
# the drafter itself emits (``count``) plus the standard read-only aggregates -
# measured from ``draft_sql`` output across every seeded dataset and column.
# Widening it is a deliberate act, not a side effect.
#
# Nothing executes here, so the side effects of the examples above are
# PostgreSQL's documented function semantics, not observed behaviour. The defect
# is the false certification either way.
_ALLOWED_FUNCTIONS = frozenset({"count", "sum", "avg", "min", "max"})

# ``name(`` with optional whitespace. A bare ``(`` is not a call, so a
# parenthesised expression or a subquery is untouched.
#
# The name is captured **whole, qualification included**. Capturing only the
# identifier next to the ``(`` read ``evil.count(*)`` as ``count`` - an
# allow-list member - and the statement drew no warning at all. In PostgreSQL
# the qualification selects which implementation runs, so a name admitted
# without its owner certifies something the allow-list never reviewed, and an
# allow-list read by its tail is bypassed by any prefix. ``_ALLOWED_FUNCTIONS``
# holds no dotted names, so a qualified call is unauthorised by construction
# rather than by a second rule that could drift from the first.
#
# The dot tolerates surrounding whitespace because PostgreSQL does:
# ``pg_catalog . count(*)`` is the same call, and binding the dot tightly leaves
# the scan to match the bare ``count(`` tail instead - admitting it. #32 states
# the qualification rule; its own pattern binds the dot tightly and so would
# still admit the spaced spelling.
#
# A lookbehind guarding against a tail matching alone was in the first version
# of this and is not here, because removing it reddened nothing: Python's scan
# is leftmost, so ``evil.count(`` matches at ``evil`` and the tail is never
# reached on its own. It is not kept as insurance - a line that changes no
# verdict should not ship with a comment implying it does.
_FUNCTION_CALL = re.compile(
    r"([A-Za-z_][A-Za-z_0-9]*(?:\s*\.\s*[A-Za-z_][A-Za-z_0-9]*)*)\s*\("
)


def _safe_identifier(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in value)


def _is_emittable_identifier(value: str) -> bool:
    """Whether this name can be emitted unquoted and mean the same thing.

    ``_safe_identifier`` replaces every non-alphanumeric character with ``_``,
    which is right for deriving a *table* name from a source locator and wrong
    for a *declared column*: the draft then names a column the dataset does not
    declare, while the same response reports the original under
    ``requested_columns`` and asserts it used only catalog-validated columns.
    Measured with a declared column ``order amount``::

        query             SELECT order_amount, count(*) ... FROM customer
        requested_columns ['order amount']
        assumptions       ['카탈로그에서 검증된 테이블/컬럼만 사용', ...]

    (That assumption no longer ships - see ``draft_sql``, which now states which
    half is catalog-backed - but it is what the response said when this was
    measured, and it is the reason the mismatch was invisible.)

    The statement passed ``validate_sql_query`` and ``/browse/query`` answered
    200, so nothing in the product flagged it; the buyer finds out when the
    warehouse answers ``column "order_amount" does not exist``. The mapping is
    also not injective - ``order amount`` and ``order_amount`` collapse to the
    same emitted identifier - so a draft could silently aggregate a different
    column than the one asked for.

    Emitting a quoted identifier is not available: ``validate_sql_query``
    refuses any statement containing a double quote
    (``literal_values_not_allowed``), so a quoted name could never execute
    through this product's own gate. Refusing with a reason is therefore the
    honest answer, and it is also the one that surfaces the limitation at the
    moment the caller can act on it.
    """
    return bool(value) and value == _safe_identifier(value)


def _safe_request_id() -> str:
    return "req-" + str(datetime.now(timezone.utc).timestamp()).replace(".", "")


def _source_table_name(source_system: str) -> str:
    return _safe_identifier(source_system.rstrip("/").rsplit("/", 1)[-1])


# The dialect every draft is emitted in. Published as the response's
# ``dialect`` and used to decide which declared distribution can be claimed
# executable, so the two cannot disagree: a relation in another dialect is not
# a relation this statement can name.
DRAFT_SQL_DIALECT = "postgresql"


def source_relation_name(dataset: Any) -> str | None:
    """The relation this dataset declares, or ``None`` when it declares none.

    ``_source_table_name`` reads the last path segment of ``source_system``,
    which is a *connection* locator: for a libpq URI that segment is the
    **database** name, and for an object prefix, a named graph or a REST path it
    is not a relation at all. Measured over the seed catalogue, no draft named a
    relation that exists, while the catalog held the answer the whole time::

        crm-customer-master  postgresql://analytics.dw/customer -> FROM customer
          declared: https://example.internal/api/table/crm_customer_master
        sales-order          postgresql://analytics.dw/sales    -> FROM sales
          declared: https://example.internal/api/table/sales_order

    ``validate_sql_query``'s source-table allow-list was built from the same
    guess, so the product refused the catalog's own relation and accepted the
    one it had invented. Both readers take the answer from here instead, which
    is why the allow-list is not given a lookup of its own.

    ``None`` is the honest answer for the three seed datasets that declare
    ``parquet``, ``sparql.graph`` and ``rest.json``: they have no relation, and
    the caller keeps the locator-derived name and keeps saying so.

    It is also the answer for a declared name that cannot be emitted as a table
    reference, which the fuzz seam surfaced. ``_safe_identifier`` happily
    returns ``"0"``, and a leading digit is not an identifier: the emitted
    ``FROM 0`` is not a table reference at all, and ``FROM 0abc`` is parsed as
    the table ``abc`` - a *different* name than the one written. Either way the
    draft's own allow-list check refuses it as
    ``unauthorized_table_reference``, which is a security-shaped reason for a
    naming problem. Returning ``None`` instead keeps the locator name and the
    "derived, not declared" caveat, which is both true and diagnosable.

    **The declared name is never rewritten.** It used to be pushed through
    ``_safe_identifier`` first, and the draft then published the *rewritten*
    name while claiming, in its ``assumptions`` and its ``execution_caveat``,
    that it "is the relation declared in the catalog's postgresql.table
    distribution". Measured on synthetic declarations::

        declared analytics.sales_order  ->  FROM analytics_sales_order
        declared "sales order"          ->  FROM sales_20order

    The second is the URL escape ``%20`` surviving into the name after ``%``
    became ``_``. Both were published with ``executable_against_source: true``
    and an empty ``emitted_identifiers`` - no disclosure at all - while the
    column path discloses the very same kind of rewrite in
    ``emitted_identifiers`` plus a caveat. Same rewrite, opposite honesty, in
    one response. And a rewritten relation name is the defect this function was
    written to fix: a name that is not the one the catalog declared.

    So the segment is URL-decoded and accepted **as written** when it is a
    usable reference - one to three dot-separated parts, each a plain SQL
    identifier - and declined otherwise. A qualified name is emittable because
    the allow-list compares references raw, so ``FROM analytics.sales_order``
    against the declared ``analytics.sales_order`` matches; nothing is quoted,
    and no part can carry a metacharacter.
    """
    for distribution in getattr(dataset, "distributions", ()) or ():
        if str(distribution.format) != f"{DRAFT_SQL_DIALECT}.table":
            continue
        segment = unquote(str(distribution.endpoint).rstrip("/").rsplit("/", 1)[-1])
        if not segment:
            continue
        if _is_emittable_relation(segment) and _reads_back_as_one_table(segment):
            return segment
    return None


# One to three dot-separated plain identifiers: table, schema.table,
# database.schema.table. Deliberately not a sanitiser - a declaration that does
# not match is declined, not rewritten.
_RELATION_PART = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_MAX_RELATION_PARTS = 3


def _is_emittable_relation(name: str) -> bool:
    """Whether this declared name can be emitted into SQL exactly as written."""
    parts = name.split(".")
    if not 1 <= len(parts) <= _MAX_RELATION_PARTS:
        return False
    return all(_RELATION_PART.match(part) for part in parts)


def declares_relational_distribution(dataset: Any) -> bool:
    """Whether the dataset declares a relation at all, emittable or not.

    ``source_relation_name`` returning ``None`` has two different causes and
    the draft's caveat used to state only one of them: "this dataset declares
    no postgresql.table distribution, so the catalog has no relation name to
    give". That is true for the three seed datasets declaring ``parquet``,
    ``sparql.graph`` and ``rest.json``. It is **false** for a dataset that
    declares a relation whose name cannot be emitted as written - the catalog
    does have a name, and the reason the draft is not using it is the name
    itself. Telling an operator "you declared nothing" when they declared
    ``sales order`` sends them to the wrong place.
    """
    return any(
        str(distribution.format) == f"{DRAFT_SQL_DIALECT}.table"
        and unquote(str(distribution.endpoint).rstrip("/").rsplit("/", 1)[-1])
        for distribution in getattr(dataset, "distributions", ()) or ()
    )


def _reads_back_as_one_table(name: str) -> bool:
    """Whether an emitted ``FROM <name>`` is read back as exactly this table.

    Asked of the production parser rather than re-deriving PostgreSQL's
    identifier rules here: ``_referenced_source_tables`` is what the allow-list
    consults, so agreeing with it is the property that matters.
    """
    return _referenced_source_tables(f"select 1 from {name}") == [name]


def _matching_paren(tokens: list[str], open_index: int) -> int | None:
    """Index of the ``)`` closing the ``(`` at ``open_index``, or ``None``."""
    depth = 0
    for index in range(open_index, len(tokens)):
        if tokens[index] == "(":
            depth += 1
        elif tokens[index] == ")":
            depth -= 1
            if depth == 0:
                return index
    return None


def _read_table_items(
    tokens: list[str], index: int, tables: list[str]
) -> tuple[int, bool]:
    """Read one comma-separated table-item list, appending the relations named.

    Returns where reading stopped and whether the list was readable. An item
    may be parenthesised, and the contents are handed to
    ``_collect_region_relations`` rather than refused: a derived table
    ``(SELECT ...) t`` and a parenthesised join ``(a JOIN b ON ...) j`` both
    name relations, and skipping the region would hide them from the allow-list.
    Reading resumes *after* the closing parenthesis, which is what lets a
    trailing ``, customer`` still be seen - a flat scan that stopped at the
    region's own ``SELECT`` never came back for it, and that is the shape #35
    records as a nested ``WHERE`` truncating the outer relation list.
    """
    expect_table = True
    while index < len(tokens):
        token = tokens[index]
        lowered = token.lower()
        if token == ",":
            index += 1
            if expect_table:
                return index, False
            expect_table = True
            continue
        if token == ")":
            break
        if token == "(" and expect_table:
            close = _matching_paren(tokens, index)
            if close is None:
                return index, False
            if not _collect_region_relations(tokens[index + 1 : close], tables):
                return index, False
            index = close + 1
            expect_table = False
            continue
        if lowered in _TABLE_ITEM_PREFIXES and expect_table:
            index += 1
            continue
        if lowered in _TABLE_CLAUSE_TERMINATORS or token == "(":
            break
        index += 1
        if expect_table:
            tables.append(token)
            expect_table = False
    return index, not expect_table


def _collect_region_relations(region: list[str], tables: list[str]) -> bool:
    """Append the relations named inside one parenthesised table item.

    The two shapes differ in where their first relation sits. A derived table
    opens with ``SELECT``, so its relations come from its own FROM/JOIN
    clauses. A parenthesised join opens with the relation itself, so the region
    *is* a table-item list and its remainder still has to be walked for the
    further JOIN clauses after it - ``((a JOIN b)) j`` nests both facts.
    """
    if not region:
        return False
    leading_items = region[0].lower() != "select"
    collected = _collect_relations(region, leading_items=leading_items)
    if collected is None:
        return False
    tables.extend(collected)
    return True


def _collect_relations(
    tokens: list[str], *, leading_items: bool = False
) -> list[str] | None:
    """Every relation named by the FROM/JOIN clauses in ``tokens``.

    ``leading_items`` reads a table-item list before the first keyword, which is
    what a parenthesised join's contents are.
    """
    tables: list[str] = []
    index = 0
    if leading_items:
        index, readable = _read_table_items(tokens, index, tables)
        if not readable:
            return None
    while index < len(tokens):
        keyword = tokens[index].lower()
        index += 1
        if keyword not in {"from", "join"}:
            continue
        index, readable = _read_table_items(tokens, index, tables)
        if not readable:
            return None
    return tables


def _referenced_source_tables(sql: str) -> list[str] | None:
    """List every table identifier that a FROM or JOIN clause references.

    One FROM clause may name several tables in a comma-separated list, each
    optionally aliased, so reading only the identifier that follows the keyword
    leaves every table after the first comma invisible to the allow-list check.
    Returns ``None`` when a clause cannot be read as a table list, so the caller
    refuses the query instead of guessing what it touches.

    Parenthesised table items are read rather than refused. They used to be
    refused because parentheses were not tokens at all: a derived table's inner
    ``SELECT`` landed where a table name was expected, which is the
    unreadable-list branch. Six ordinary single-source shapes were refused that
    way - ``SELECT count(*) FROM (SELECT customer_id FROM customer) t`` among
    them - and the caller's reason, ``unauthorized_table_reference``, was false:
    the only relation named was the authorised one, and no spelling of the
    question got through.

    Unbalanced parentheses are refused outright. That used to happen by
    accident for an unclosed ``(``, and not at all for a stray ``)``:
    ``select * from crm)`` read back as the authorised table and passed. A
    statement whose shape cannot be read is one this function cannot speak for.
    """
    if sql.count("(") != sql.count(")"):
        return None
    return _collect_relations(_TABLE_LIST_TOKEN.findall(sql))


def _matched_forbidden_keyword(text: str) -> str | None:
    r"""Return the first forbidden keyword appearing in ``text`` as a whole word.

    Every gate that consults ``_FORBIDDEN_KEYWORDS`` goes through here, because
    they did not agree before: ``validate_sql_query`` matched on word boundaries
    while ``draft_sql`` and ``execute_query`` matched on bare substrings. The
    canonical validator therefore returned no warning for
    ``select created_at from customer`` while ``/browse/query`` rejected the
    identical SQL as hostile.

    Substring matching refuses ordinary identifiers: ``create`` is inside
    ``created_at``, ``update`` inside ``updated_at``, ``delete`` inside
    ``deleted_flag``, and the same holds for ``merged_at``, ``locked_at``,
    ``granted_scope``, ``execution_count``, ``dropoff_rate`` and ``intopic`` -
    nine shapes an ordinary warehouse column carries. Word boundaries still
    catch the real cases (``drop table``, ``select ... into exfil``), which is
    what the keyword list exists for.

    The boundary is deliberately asymmetric, and ``\b`` is not it. ``\b`` sits
    between a word character and a non-word character, and Python's ``\w`` is
    Unicode-aware, so a digit or a non-ASCII letter immediately *before* a
    keyword is not a boundary to it: ``\bunion\b`` does not match ``1union``,
    which MySQL reads as ``1 union``. Folding three predicates onto this one
    therefore lost a class the two substring gates had caught - a survivor has
    to be at least as strict as each predicate it replaces, and this one was
    not. So the prefix side refuses anything that is not an ASCII identifier
    character, while the suffix side still accepts one, because that is what
    separates a split token from an ordinary column: ``1union`` is a keyword,
    ``updated_at`` is a name. #107 reached the same predicate independently.

    The list is iterated in sorted order so the keyword reported back to the
    caller is deterministic rather than set-iteration dependent.
    """
    lowered = text.lower()
    for token in sorted(_FORBIDDEN_KEYWORDS):
        if re.search(rf"(?<![a-z_]){re.escape(token)}(?![a-z0-9_])", lowered):
            return token
    return None


def validate_sql_query(
    sql: str, *, source_system: str, declared_relation: str | None = None
) -> list[str]:
    stripped = sql.strip()
    lowered = stripped.lower()
    warnings: list[str] = []

    if not lowered.startswith("select "):
        warnings.append("only_select_allowed")
    if ";" in stripped:
        warnings.append("single_statement_required")
    if "--" in stripped or "/*" in stripped or "*/" in stripped:
        warnings.append("sql_comments_not_allowed")
    if "'" in stripped or '"' in stripped or _DOLLAR_QUOTE.search(stripped):
        warnings.append("literal_values_not_allowed")
    if re.search(r"\b(and|or)\b", lowered):
        warnings.append("boolean_operator_not_allowed")

    if _matched_forbidden_keyword(lowered) is not None:
        warnings.append("forbidden_keyword_detected")

    called = {
        name.lower()
        for name in _FUNCTION_CALL.findall(stripped)
        # A clause keyword followed by "(" is not a function call: ``in (``,
        # ``exists (`` and the set operators all take a parenthesised operand.
        if name.lower() not in _TABLE_CLAUSE_TERMINATORS
        and name.lower() not in {"in", "exists", "not", "and", "or", "all", "any", "values"}
    }
    unauthorized = sorted(called - _ALLOWED_FUNCTIONS)
    if unauthorized:
        warnings.append("unauthorized_function_call")

    referenced = _referenced_source_tables(stripped)
    if referenced is None:
        # An unreadable table list is refused rather than treated as empty: the
        # query does touch tables, we just cannot prove which ones are allowed.
        warnings.append("unauthorized_table_reference")
        return warnings
    if not referenced:
        warnings.append("missing_source_table")
        return warnings

    # ``declared_relation`` is what the catalog says the relation is, resolved
    # once by ``source_relation_name`` and passed in by every caller that has a
    # dataset. The ``source_system`` fallback is a live path, not dead code:
    # ``fuzz/fuzz_query_safety.py`` and its Hypothesis mirror call this with a
    # bare locator and no dataset to resolve against.
    expected = (declared_relation or _source_table_name(source_system)).lower()
    # Compare the WHOLE reference, RAW. Taking only the last dot-separated
    # component made any qualification whose leaf matched pass the allow-list:
    # pg_catalog.customer, otherdb.otherschema.customer and
    # information_schema.customer all reduce to "customer". The drafter emits the
    # declared name verbatim, so a qualified reference is one the allow-list
    # cannot prove.
    #
    # It used to normalise each reference through _safe_identifier first, on the
    # argument that "the dot becomes _, so a qualified name can never collide
    # with the bare one". That holds only where normalisation *adds* a character
    # the expected name lacks (pg_catalog.customer -> pg_catalog_customer, which
    # is not "customer"). Where the declared name already contains the character
    # normalisation produces - and every relation in this catalogue contains an
    # underscore - the mapping manufactures matches instead of preventing them.
    # Against declared crm_customer_master, nine references naming nine
    # different relations were certified clean: crm.customer_master,
    # crm$customer_master, crm_customer.master, crm.customer.master and the
    # non-ASCII "." confusables the token regex keeps (U+00B7, U+2024, U+FF0E).
    # _TABLE_LIST_TOKEN is [A-Za-z_\u0080-\uffff][\w.$\u0080-\uffff]*, so those
    # characters stay inside one token and reach the comparison.
    #
    # The reference is untrusted text; the declared relation arrives from
    # source_relation_name, already sanitised and already checked to read back as
    # one table. Rewriting the untrusted side to match the trusted one is
    # backwards. Raw comparison is strictly tighter and still accepts the
    # drafter's own output, which emits the declared name unchanged.
    referenced_tables = {table.lower() for table in referenced}
    if referenced_tables != {expected}:
        warnings.append("unauthorized_table_reference")

    return warnings


# Declared datatypes that carry a point in time. The drafter's date window is
# only meaningful against one of these.
_TEMPORAL_DATATYPES = frozenset({"date", "datetime", "time", "timestamp", "timestamptz"})


def _temporal_column(dataset: Any) -> str | None:
    """Return the dataset's first declared temporal column, or ``None``.

    The drafter hard-coded ``created_at`` into its window predicate while
    claiming, in the same response, to use "카탈로그에서 검증된 테이블/컬럼만"
    (a claim since removed from ``draft_sql``'s ``assumptions``).
    Three of the five seeded datasets declare no temporal column at all and not
    one of them declares ``created_at``: ``crm-customer-master`` has
    ``signup_at``, ``crm-event`` has ``event_timestamp``, and ``sales-order``,
    ``semantic-glossary`` and ``marketing-campaign`` have none. Every draft
    therefore filtered on a column its own dataset does not have.
    """
    for column in dataset.schema:
        if str(column.datatype).lower() in _TEMPORAL_DATATYPES:
            return column.name
    return None


def _audit_draft(
    req: QueryDraftRequest, *, decision_id: str, result: str, reason: str
) -> None:
    """Record one audit event for a query-draft attempt.

    ``draft_sql`` recorded a policy decision and **no audit event** - not on
    denial and not on success. The repository's stated invariant is that the
    browse/query paths evaluate policy *and* record evidence, and an auditor
    reading the audit feed saw no trace that a governed SQL draft had been
    requested at all. Measured before this change: `decisions +1  audits +0`.
    """
    ingest_event(
        event_type="llm.draft_query",
        actor=req.user,
        dataset_id=req.dataset_id,
        decision=result,
        decision_id=decision_id,
        reason=reason,
        details={"purpose": req.purpose, "policy_decision_id": decision_id},
    )


def draft_sql(req: QueryDraftRequest) -> dict:
    if req.date_window_days < 1 or req.date_window_days > 365:
        return {"error": "invalid_date_window", "reason": "date_window_days must be between 1 and 365"}

    dataset = get_dataset(req.dataset_id)
    # Scope before anything else is said about the dataset. This route reported
    # `dataset_not_found` for a dataset that does not exist and `policy_denied`
    # for one in another tenant, so an outside caller could tell which ids exist
    # by reading the error code - the same oracle the browse and catalog families
    # were repaired to close.
    if dataset is None or not can_access_tenant(req.user, dataset.tenant_id):
        if dataset is not None:
            # Record the real reason before answering with the indistinguishable
            # one, so the refusal is still evidence.
            denial = evaluate(
                subject=req.user,
                resource=req.dataset_id,
                action="query",
                purpose=req.purpose,
            )
            _audit_draft(req, decision_id=denial.decision_id, result="denied", reason=denial.reason)
        return {"error": "dataset_not_found"}
    if dataset.status != "published":
        return {"error": "policy_denied", "reason": "dataset is not published"}
    if not dataset.schema:
        return {"error": "missing_schema", "reason": "dataset schema must be present to draft query"}

    decision = evaluate(subject=req.user, resource=req.dataset_id, action="query", purpose=req.purpose)
    if decision.effect != "allow":
        _audit_draft(req, decision_id=decision.decision_id, result="denied", reason=decision.reason)
        return {"error": "policy_denied", "reason": decision.reason}

    question = req.question.strip().lower()
    # The reason names the offending keyword: the previous message said only
    # that "a" keyword was present, so an integrator whose question mentioned
    # created_at had no way to tell which word was refused - or that the refusal
    # was spurious.
    forbidden_in_question = _matched_forbidden_keyword(question)
    if forbidden_in_question is not None:
        return {
            "error": "policy_denied",
            "reason": f"허용되지 않은 키워드가 질의에 포함되었습니다: {forbidden_in_question}",
        }

    allowed_columns = {column.name for column in dataset.schema if column.datatype}
    if req.columns:
        unknown = sorted(set(req.columns) - allowed_columns)
        if unknown:
            return {
                "error": "invalid_columns",
                "reason": f"요청한 컬럼이 데이터셋에 없습니다: {', '.join(unknown)}",
            }

    requested_columns = req.columns or ["*"]
    if req.group_by and req.group_by not in allowed_columns:
        return {"error": "invalid_group_by", "reason": "요청한 그룹화 컬럼이 데이터셋에 없습니다."}

    # ``_safe_identifier`` rewrites a declared column that cannot be emitted
    # unquoted, and that rewrite is kept: a quoted identifier could never
    # execute through this product's own gate, which refuses any statement
    # containing a double quote (``literal_values_not_allowed``), and
    # ``test_draft_query_sanitizes_group_by_identifier`` pins the rewrite
    # deliberately so a hyphen cannot reach the SQL.
    #
    # Two things about it were wrong. The response **contradicted itself**:
    # measured with a declared column ``order amount``, the query named
    # ``order_amount`` while ``requested_columns`` reported ``order amount`` and
    # the assumptions asserted only catalog-validated columns were used, so a
    # buyer learned otherwise from the warehouse ("column order_amount does not
    # exist"). And the mapping is **not injective** - ``order amount`` and
    # ``order_amount``, or ``a-b`` and ``a_b``, collapse to one identifier - so
    # a draft could silently aggregate a different column than the one asked
    # for. The rewrite is now reported, and an ambiguous one is refused rather
    # than guessed.
    rewritten = {
        name: _safe_identifier(name)
        for name in list(requested_columns) + ([req.group_by] if req.group_by else [])
        if name != "*" and name != _safe_identifier(name)
    }
    emitted_by_declared = {
        column.name: _safe_identifier(column.name) for column in dataset.schema
    }
    collisions = sorted(
        {
            emitted
            for name, emitted in rewritten.items()
            for other, other_emitted in emitted_by_declared.items()
            if other != name and other_emitted == emitted
        }
    )
    if collisions:
        return {
            "error": "ambiguous_identifier",
            "reason": (
                "컬럼명을 SQL 식별자로 변환하면 다른 선언 컬럼과 같아져, 어느 컬럼을 "
                "집계할지 확정할 수 없습니다: " + ", ".join(collisions)
            ),
        }

    # `interval '<n> day'` is a single-quoted literal, and this module's own
    # validate_sql_query refuses any statement containing a quote
    # (literal_values_not_allowed). Every draft this route produced was therefore
    # rejected by /browse/query, so the documented draft-then-execute workflow had
    # no path through it for any dataset. PostgreSQL date arithmetic expresses the
    # same window with no literal, and date_window_days is already validated as an
    # integer in 1..365 above, so nothing caller-controlled reaches the SQL as text.
    window_column = _temporal_column(dataset)
    if window_column is None:
        # No temporal column: emit no predicate rather than invent one. The
        # response says the window was not applied, because a caller that passed
        # date_window_days would otherwise assume it was.
        where_clause = ""
    else:
        where_clause = (
            f"WHERE {_safe_identifier(window_column)} >= current_date - {req.date_window_days}"
        )
    # The source's kind is published, not used to withhold the draft. An
    # earlier version of this comment claimed "relational SQL is drafted only
    # for a relational source", which is false of the code directly below it:
    # measured, this function still emits PostgreSQL for all five seed datasets,
    # three of which classify as ``file_lake``, ``rdf`` and ``api``. What
    # changed is that the response now carries ``source_kind`` and
    # ``executable_against_source: false`` for those three instead of asserting
    # the catalog had verified the table. The repair was disclosure, not
    # refusal, and the comment should say which.
    #
    # Measured over the seed catalogue, this function emitted PostgreSQL for all five datasets and
    # three of them are not relational at all - the "table" was an S3 prefix
    # (``s3://analytics/events/crm`` -> ``FROM crm``), a SPARQL named graph
    # (``sparql://semantic.graph/customer-intelligence`` ->
    # ``FROM customer_intelligence``) and a REST endpoint path
    # (``https://api.example.internal/marketing/campaigns`` ->
    # ``FROM campaigns``) - while the response asserted
    # ``카탈로그에서 검증된 테이블/컬럼만 사용``. A buyer was handed relational
    # SQL for a graph store and told the catalog had verified the table.
    #
    # The classifier is ``sdp_core.demo_seed.classify_source_type``, which
    # already existed inline for ``buyer_demo_dataset_summaries`` and is now
    # shared rather than copied.
    source_kind = classify_source_type(dataset.source_system)
    declared_relation = source_relation_name(dataset)
    table_name = declared_relation or _source_table_name(dataset.source_system)
    # ``_referenced_source_tables`` treats a clause keyword as the end of the
    # table list, so a source table named ``order`` - one of the most ordinary
    # names in a sales warehouse - broke out of the list with ``expect_table``
    # still true and returned ``None``, which the validator turns into
    # ``unauthorized_table_reference``. Measured end to end::
    #
    #     POST /llm/draft-query -> 200
    #       'SELECT count(*) AS active_customer_count FROM order
    #        WHERE order_ts >= current_date - 90 LIMIT 1000'
    #     POST /browse/query    -> 400
    #       {'status': 'REJECTED', 'warnings': ['unauthorized_table_reference']}
    #
    # The product accused its own output of a governance violation with no way
    # to proceed, and ``FROM order`` is unquoted reserved-word SQL that
    # PostgreSQL would refuse anyway. All 24 members of
    # ``_TABLE_CLAUSE_TERMINATORS`` fail this way.
    if table_name.lower() in _TABLE_CLAUSE_TERMINATORS:
        return {
            "error": "unquotable_source_table",
            "reason": (
                "source table 이름이 SQL 절 키워드와 충돌해 이 게이트를 통과하는 "
                "질의를 만들 수 없습니다. 인용 식별자는 "
                "literal_values_not_allowed로 거부됩니다: "
                f"{table_name}"
            ),
        }

    row_limit = min(req.row_limit, 2000)
    if row_limit <= 0:
        return {"error": "invalid_row_limit", "reason": "row_limit must be a positive integer"}

    timeout_ms = req.timeout_ms
    if timeout_ms < 500 or timeout_ms > 120000:
        return {"error": "invalid_timeout", "reason": "timeout_ms must be between 500 and 120000"}

    if req.group_by:
        group_identifier = _safe_identifier(req.group_by)
        group_clause = f"GROUP BY {group_identifier}"
        select_fields = f"{group_identifier}, count(*) AS active_customer_count"
    else:
        group_clause = ""
        if "*" in requested_columns:
            select_fields = "count(*) AS active_customer_count"
        else:
            select_fields = ", ".join(_safe_identifier(column) for column in requested_columns)
            select_fields = f"{select_fields}, count(*) AS active_customer_count"

    max_rows = min(row_limit, 2000)
    if "*" in requested_columns and len(requested_columns) > 1:
        requested_columns = ["*"]

    estimated_cost = max(1, len(requested_columns) * row_limit // 200 + 1)
    # Join only the clauses that exist: an empty WHERE or GROUP BY would otherwise
    # leave a double space in the emitted statement.
    sql = " ".join(
        part
        for part in (
            f"SELECT {select_fields}",
            f"FROM {table_name}",
            where_clause,
            group_clause,
            f"LIMIT {max_rows}",
        )
        if part
    )

    # The last word belongs to the validator that will judge this statement.
    # The documented workflow is draft-then-execute, so a draft the very next
    # call rejects is worse than a refusal: the buyer sees the product accuse
    # its own output of a governance violation. Two causes have already been
    # found and fixed one at a time (the ``interval '<n> day'`` literal, and a
    # source table colliding with a clause keyword); this check is what catches
    # the third without waiting for a report.
    self_check = validate_sql_query(
        sql,
        source_system=dataset.source_system,
        declared_relation=declared_relation,
    )
    # Published rather than inferred, and now true in both directions: a dataset
    # that declares a relation gets a statement naming it, and one that declares
    # none says the name came from the locator. Claiming all five executable
    # would be the same over-claim in a new place - an object prefix, a named
    # graph and a REST path are not relations.
    executable_against_source = declared_relation is not None
    if declared_relation is not None:
        execution_caveat = (
            f"source_kind={source_kind}. 테이블 이름 {declared_relation}은(는) "
            f"카탈로그의 {DRAFT_SQL_DIALECT}.table distribution에 선언된 relation "
            "입니다. 권한·스키마 경로는 대상 시스템 쪽 설정을 따릅니다."
        )
    elif declares_relational_distribution(dataset):
        # The declaration exists; its *name* is the problem. Saying "you
        # declared nothing" here would send an operator who declared
        # ``sales order`` to look for a missing distribution.
        execution_caveat = (
            f"source_kind={source_kind}. 이 draft의 테이블 이름은 연결 locator에서 "
            "파생된 것이므로 대상 시스템의 relation 이름과 다를 수 있습니다. 이 "
            f"데이터셋은 {DRAFT_SQL_DIALECT}.table distribution을 선언했지만, 선언된 "
            "이름이 SQL 식별자(또는 점으로 구분된 식별자 1~3개)가 아니어서 적힌 대로 "
            "emit할 수 없습니다. 이름을 고쳐 쓰지 않고 거절합니다 — 고쳐 쓰면 카탈로그가 "
            "선언하지 않은 relation을 선언된 것처럼 공표하게 됩니다."
        )
    else:
        execution_caveat = (
            f"source_kind={source_kind}. 이 draft의 테이블 이름은 연결 locator에서 "
            "파생된 것이므로 대상 시스템의 relation 이름과 다를 수 있습니다. 이 "
            f"데이터셋은 {DRAFT_SQL_DIALECT}.table distribution을 선언하지 않았으므로 "
            "카탈로그가 알려 줄 relation 이름이 없습니다."
        )
    if self_check:
        return {
            "error": "draft_rejected_by_validator",
            "reason": (
                "생성된 질의가 이 제품의 SQL 안전성 게이트를 통과하지 못했습니다: "
                f"{', '.join(self_check)}"
            ),
            "warnings": self_check,
        }

    # ``카탈로그에서 검증된 테이블/컬럼만 사용`` was false for every dataset,
    # for two different reasons, so it is replaced by what is true.
    #
    # The columns are catalog-declared; the **table** is not. ``table_name``
    # comes from the last path segment of ``source_system``, which is a
    # *connection* locator. Measured over the seed catalogue::
    #
    #   crm-customer-master  postgresql://analytics.dw/customer  -> FROM customer
    #     catalog's own relation, from its postgresql.table distribution:
    #     .../api/table/crm_customer_master
    #   crm-event            s3://analytics/events/crm           -> FROM crm
    #   semantic-glossary    sparql://semantic.graph/customer-intelligence
    #                                              -> FROM customer_intelligence
    #   marketing-campaign   https://api.../marketing/campaigns  -> FROM campaigns
    #
    # For a libpq URI that segment is the **database** name, not a relation; for
    # the other three the source is not relational at all and the segment is an
    # object prefix, a named graph and a REST path. So no draft currently names
    # a relation that exists, and a buyer who pasted one into their warehouse
    # got ``relation "customer" does not exist``.
    #
    # Resolving the relation from the catalog's declared ``postgresql.table``
    # distribution - and building ``validate_sql_query``'s allow-list from that
    # same derivation, which today shares this guess and therefore refuses the
    # catalog's own relation - is the separate repair recorded in the gap
    # baseline. Until it lands the response says so rather than claiming
    # otherwise.
    assumptions = [
        "컬럼은 카탈로그 선언에서 가져왔습니다",
        (
            f"테이블 이름 {table_name}은(는) 카탈로그의 "
            f"{DRAFT_SQL_DIALECT}.table distribution에 선언된 relation입니다"
            if declared_relation is not None
            # Still true for a dataset that declares no relation, and it has to
            # stay said: the same sentence was published for every dataset while
            # being false for none of them in this direction and true for none in
            # the other.
            else f"테이블 이름은 source_system({source_kind}) 경로의 마지막 "
            "조각에서 파생했습니다 — 카탈로그가 선언한 relation 이름이 아닙니다"
        ),
        "read-only SELECT만 허용",
        "목적별 정책으로 PII 필드는 masking 또는 집계 제한",
    ]
    if rewritten:
        # Stated, because the emitted SQL names an identifier the dataset does
        # not declare and the response otherwise asserted the opposite.
        assumptions.append(
            "SQL 식별자로 쓸 수 없는 컬럼명을 변환했습니다("
            + ", ".join(f"{name} -> {emitted}" for name, emitted in sorted(rewritten.items()))
            + "). 대상 엔진의 실제 컬럼명과 다를 수 있습니다."
        )
    if req.group_by in {"signup_at", "event_timestamp", "created_at"}:
        assumptions.append("날짜 집계는 기간 기반 집계로만 제한")

    masked_pii = [col.name for col in dataset.schema if col.pii]
    if masked_pii and req.purpose == "analysis":
        assumptions.append(f"PII 컬럼({', '.join(masked_pii)})은 별도 집계/마스킹 필요")

    row_filter = decision.obligations.get("row_filter")
    if row_filter:
        assumptions.append(f"행 레벨 필터 적용: {', '.join(row_filter)}")

    if not req.group_by:
        assumptions.append("기본 집계는 건수 카운트 기반으로 반환")

    if window_column is None:
        assumptions.append(
            f"이 데이터셋에는 시간 컬럼이 없어 {req.date_window_days}일 기간 필터를 적용하지 않았습니다"
        )
    else:
        assumptions.append(
            f"기간 필터는 {window_column} 기준 최근 {req.date_window_days}일"
        )

    _audit_draft(req, decision_id=decision.decision_id, result="allowed", reason="ok")
    return {
        "dataset_id": req.dataset_id,
        "query": sql,
        "policy_decision_id": decision.decision_id,
        "assumptions": assumptions,
        "policy_decision": decision.model_dump(),
        "preview_required": req.purpose == "analysis",
        "dialect": DRAFT_SQL_DIALECT,
        "source_kind": source_kind,
        "executable_against_source": executable_against_source,
        "execution_caveat": execution_caveat,
        "row_limit": max_rows,
        "requested_columns": requested_columns,
        # What the emitted SQL actually names, where it differs from the
        # declared name. ``requested_columns`` reports the declared names and
        # alone it contradicted the statement beside it.
        "emitted_identifiers": dict(sorted(rewritten.items())),
        # The relation the statement targets, so a reader does not have to parse
        # the SQL to find out - and so the claim beside it
        # (``executable_against_source``) is about something visible.
        "source_table": table_name,
        "timeout_ms": timeout_ms,
        "estimated_cost": estimated_cost,
        "date_window_days": req.date_window_days if window_column else 0,
        "date_window_column": window_column,
        "date_window_applied": window_column is not None,
    }


MOCK_ROW_COUNT_CAP = 2000
MOCK_ROW_COUNT_WITHOUT_PROFILE = 1000


def _row_count_estimate(dataset: Any, *, dry_run: bool) -> tuple[int, str]:
    """Return the mock row count **and the name of where it came from**.

    One label, ``catalog_profile_estimate``, was used for three different
    provenances, so the compliance ledger asserted a provenance the figure did
    not have. Measured before this change:

        crm-customer-master  profile.row_count = 1200000
          -> row_count 2000,  row_count_source "catalog_profile_estimate"
        a dataset with profile = {}
          -> row_count 1000,  row_count_source "catalog_profile_estimate"

    The first is the cap, not the estimate - off by a factor of 600 from the
    figure whose provenance it claims. The second is a hardcoded literal; there
    is no estimate at all. The comment three lines above the defect already said
    an unlabelled estimate in the ledger is a fabricated measurement; a
    mislabelled one is worse, because it answers the question wrongly instead of
    leaving it open.
    """
    if dry_run:
        return 0, "dry_run_zero"
    profiled = dataset.profile.get("row_count")
    if profiled is None:
        return MOCK_ROW_COUNT_WITHOUT_PROFILE, "fixed_default_no_catalog_profile"
    # ``profile`` is a free-form ``Dict[str, Any]`` on both POST /catalog/datasets
    # and PATCH, so ``row_count`` arrives as whatever the caller sent. Comparing
    # it to an int raised ``TypeError``, which no handler catches, so the whole
    # governed query route was permanently dead for that dataset. Measured with
    # ``profile: {"row_count": "1200000"}`` - a JSON string, which is what a
    # metadata harvester emitting counts as text produces:
    #
    #     POST /catalog/datasets           -> 200
    #     POST /catalog/.../publish        -> 200
    #     POST /browse/query               -> 500 Internal Server Error
    #     ledger delta: decisions +1  audits +0
    #
    # The 500 is the lesser half. The crash lands between the policy decision
    # and the audit write, so it produced a policy decision with no matching
    # audit event - the one pairing CLAUDE.md names non-negotiable. A client also
    # gets no error code it can act on, against this repo's KeyError -> 404 /
    # ValueError -> 400 / PermissionError -> 403 contract.
    #
    # A non-numeric row count is not an estimate, so it is not labelled as one:
    # the honest answer is the no-profile default with a source that says the
    # profile value was unusable. ``bool`` is excluded deliberately - ``True``
    # is an ``int`` in Python and a row count of ``True`` is not a measurement.
    # ``bool`` is excluded deliberately - ``True`` is an ``int`` in Python and a
    # row count of ``True`` is not a measurement. The int and float branches are
    # separate because folding them raised on the values that cannot be
    # converted: my first version used ``float(profiled) != int(profiled)``,
    # which raises ``ValueError`` on ``NaN`` and ``OverflowError`` on
    # ``Infinity`` - both of which Python's ``json`` accepts as literals, so
    # that would have been a second uncaught 500 in the same function - and
    # which also misclassified ``10**30`` as unusable, because ``float(10**30)``
    # is not exactly ``10**30``.
    if isinstance(profiled, bool):
        return MOCK_ROW_COUNT_WITHOUT_PROFILE, "unusable_catalog_profile_row_count"
    if isinstance(profiled, int):
        count = profiled
    elif isinstance(profiled, float):
        # ``1200.0`` is a legitimate JSON spelling of 1200 and is accepted;
        # ``1200.5`` would have to be silently truncated, and silently changing
        # a number while labelling it ``catalog_profile_estimate`` is the
        # mislabelling this function's docstring was written about.
        if not math.isfinite(profiled) or not profiled.is_integer():
            return MOCK_ROW_COUNT_WITHOUT_PROFILE, "unusable_catalog_profile_row_count"
        count = int(profiled)
    else:
        return MOCK_ROW_COUNT_WITHOUT_PROFILE, "unusable_catalog_profile_row_count"
    if count < 0:
        # A negative count is not a count.
        return MOCK_ROW_COUNT_WITHOUT_PROFILE, "unusable_catalog_profile_row_count"
    if count > MOCK_ROW_COUNT_CAP:
        return MOCK_ROW_COUNT_CAP, "mock_row_cap_below_catalog_profile_estimate"
    return count, "catalog_profile_estimate"


def execute_query(req: QueryExecutionRequest) -> QueryExecutionResponse:
    request_id = _safe_request_id()

    def response(
        *,
        dataset_id: str,
        query_id: str = "",
        policy_decision_id: str = "",
        status: str,
        row_count: int = 0,
        columns: list[str] | None = None,
        rows: list[dict[str, str | int | float | bool | None]] | None = None,
        execution: dict[str, object] | None = None,
        warnings: list[str] | None = None,
    ) -> QueryExecutionResponse:
        return QueryExecutionResponse(
            request_id=request_id,
            dataset_id=dataset_id,
            query_id=query_id,
            policy_decision_id=policy_decision_id,
            status=status,
            row_count=row_count,
            columns=columns or [],
            rows=rows or [],
            execution=execution or {"elapsedMs": 0, "source": "validation", "bytesScanned": 0},
            warnings=warnings or [],
        )

    def audit(
        *,
        dataset_id: str,
        result: str,
        reason: str,
        decision_id: str | None = None,
        details: dict[str, object] | None = None,
    ) -> None:
        audit_details = {"purpose": req.purpose, "request_id": request_id, "dry_run": req.dry_run}
        # An audit row with no decision_id read as "policy was skipped". These
        # branches refuse malformed input before a decision exists, so the stage
        # is stated instead of left to be inferred from a null field. A reader of
        # the ledger can now tell "policy not reached" from "policy not applied".
        audit_details["policy_stage"] = (
            "evaluated" if decision_id else "pre_policy_validation"
        )
        if details:
            audit_details.update(details)
        ingest_event(
            event_type="browse.query",
            actor=req.user,
            dataset_id=dataset_id,
            decision=result,
            decision_id=decision_id,
            reason=reason,
            details=audit_details,
        )

    if not req.dataset_ids:
        # The contract requires one, but a programmatically built request can
        # still arrive empty; answer, never index into nothing.
        return response(dataset_id="", status="REJECTED", warnings=["dataset_ids_required"])

    dataset_id = req.dataset_ids[0]
    if req.language.strip().upper() != "SQL":
        audit(dataset_id=dataset_id, result="rejected", reason="unsupported_language")
        return response(
            dataset_id=dataset_id,
            status="REJECTED",
            warnings=["unsupported_language"],
        )

    lowered = req.query.lower()
    if _matched_forbidden_keyword(lowered) is not None:
        audit(dataset_id=dataset_id, result="rejected", reason="forbidden_keyword_detected")
        return response(
            dataset_id=dataset_id,
            status="REJECTED",
            warnings=["forbidden_keyword_detected"],
        )

    if len(req.dataset_ids) > 1:
        audit(dataset_id=dataset_id, result="rejected", reason="cross_source_join_not_supported")
        return response(
            dataset_id=dataset_id,
            status="REJECTED",
            warnings=["cross_source_join_not_supported"],
        )

    dataset = get_dataset(dataset_id)
    # This route names its dataset in the request *body*, which is why the
    # path-shaped enumeration that repaired /browse/{id}/... and
    # /catalog/datasets/{id}/... did not reach it: it answered 403 DENIED
    # "tenant boundary denied" for a dataset in another tenant and 400 REJECTED
    # "dataset_not_found" for one that does not exist, so the error code still
    # told an outsider which ids exist. One answer for both, with the real reason
    # recorded first.
    if dataset is not None and not can_access_tenant(req.user, dataset.tenant_id):
        denial = evaluate(
            subject=req.user, resource=dataset_id, action="query", purpose=req.purpose
        )
        audit(
            dataset_id=dataset_id,
            result="denied",
            reason=denial.reason,
            decision_id=denial.decision_id,
            details={"policy_decision_id": denial.decision_id},
        )
        return response(
            dataset_id=dataset_id,
            status="REJECTED",
            warnings=["dataset_not_found"],
        )
    if not dataset:
        audit(dataset_id=dataset_id, result="rejected", reason="dataset_not_found")
        return response(
            dataset_id=dataset_id,
            status="REJECTED",
            warnings=["dataset_not_found"],
        )

    decision = evaluate(subject=req.user, resource=dataset_id, action="query", purpose=req.purpose)
    if decision.effect != "allow":
        audit(
            dataset_id=dataset.id,
            result="denied",
            reason=decision.reason,
            decision_id=decision.decision_id,
            details={"policy_decision_id": decision.decision_id},
        )
        return response(
            dataset_id=dataset.id,
            policy_decision_id=decision.decision_id,
            status="DENIED",
            execution={"elapsedMs": 0, "source": "policy", "bytesScanned": 0},
            warnings=[decision.reason],
        )

    validation_warnings = validate_sql_query(
        req.query,
        source_system=dataset.source_system,
        declared_relation=source_relation_name(dataset),
    )
    if validation_warnings:
        audit(
            dataset_id=dataset.id,
            result="rejected",
            reason="query_safety_validation_failed",
            decision_id=decision.decision_id,
            details={
                "policy_decision_id": decision.decision_id,
                "warnings": validation_warnings,
            },
        )
        return response(
            dataset_id=dataset.id,
            policy_decision_id=decision.decision_id,
            status="REJECTED",
            execution={"elapsedMs": 0, "source": "query_safety", "bytesScanned": 0},
            warnings=validation_warnings,
        )

    row_count, row_count_source = _row_count_estimate(dataset, dry_run=req.dry_run)

    now = datetime.now(timezone.utc).isoformat()
    query_id = f"qry-{now.replace(':', '')}"
    columns = ["week", "active_count"] if "group by" in lowered else ["result"]
    # ``rows`` has to agree with ``row_count``, which is computed above and is
    # ``0`` on a dry run. It did not consult ``dry_run`` at all, so a dry run
    # reported zero and delivered one row - and on the group-by branch that row
    # carried a fabricated non-zero figure dated today::
    #
    #     dry_run=True  row_count=0  len(rows)=1
    #     rows=[{'week': '2026-10-26', 'active_count': 1}]
    #     audit: {"dry_run": true, "row_count": 0, ...}
    #
    # So one response contradicted itself and the compliance ledger asserted
    # that nothing was delivered while the caller held a row. ``columns`` stays
    # published: the declared result shape is what a dry run is for, and only
    # the data is withheld.
    rows: list[dict[str, str | int | float | bool | None]] = []
    if not req.dry_run:
        rows = (
            [{"week": now[:10], "active_count": 1}]
            if "group by" in lowered
            else [{"result": row_count}]
        )
    # No query is executed here, so every figure below is labelled with where it
    # came from. `elapsedMs` and `bytesScanned` are fixed constants and
    # `row_count` is the catalog's own profile estimate, not a measurement.
    execution = {
        "elapsedMs": 100,
        "source": "mock-trino",
        "bytesScanned": 1024,
        "measurement_status": "mock_execution_no_real_data",
        "elapsed_ms_source": "fixed_mock_constant",
        "bytes_scanned_source": "fixed_mock_constant",
        # The response under-labelled relative to the ledger: it named the
        # provenance of the two constants and said nothing about the row count,
        # which is the only figure a reader is likely to act on.
        "row_count_source": row_count_source,
        # ``rows`` was the one figure in this response with no provenance,
        # while the comment above claims every figure carries one. It is not
        # the result set and it is not a sample of one: on a dry run nothing
        # is returned, and otherwise it is a fixed illustrative row whose
        # length has no relation to ``row_count`` - which is why a test
        # asserting ``row_count == len(rows)`` on a live run would be
        # demanding that the mock fabricate 2000 rows.
        "rows_source": "withheld_dry_run" if req.dry_run else "fixed_mock_sample",
    }
    audit(
        dataset_id=dataset.id,
        result="allowed",
        reason="ok",
        decision_id=decision.decision_id,
        details={
            "policy_decision_id": decision.decision_id,
            "query_id": query_id,
            "row_count": row_count,
            "bytes_scanned": execution["bytesScanned"],
            # The HTTP response carried `mock_execution_no_real_data` while the
            # audit row carried nothing, so the compliance ledger recorded
            # "2000 rows, 1024 bytes scanned" as if it had been measured. The
            # ledger is the surface a buyer's compliance team reads; an unlabelled
            # estimate there is a fabricated measurement.
            "measurement_status": "mock_execution_no_real_data",
            "row_count_source": row_count_source,
            "bytes_scanned_source": "fixed_mock_constant",
        },
    )
    return response(
        dataset_id=dataset.id,
        query_id=query_id,
        policy_decision_id=decision.decision_id,
        status="SUCCEEDED",
        row_count=row_count,
        columns=columns,
        rows=rows,
        execution=execution,
        warnings=["mock_execution_no_real_data"],
    )
