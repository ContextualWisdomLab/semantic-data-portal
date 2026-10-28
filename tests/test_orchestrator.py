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
    audit_events = list(evidence._AUDIT_EVENT_LOG)
    try:
        yield
    finally:
        catalog._DATA.clear()
        catalog._DATA.update(data)
        catalog._AUDIT_LOG.clear()
        catalog._AUDIT_LOG.extend(audit)
        evidence._POLICY_DECISION_LOG.clear()
        evidence._POLICY_DECISION_LOG.extend(decisions)
        evidence._AUDIT_EVENT_LOG.clear()
        evidence._AUDIT_EVENT_LOG.extend(audit_events)


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


@pytest.mark.parametrize(
    "sql,expected",
    [
        # A comma-separated FROM list is a join: every element must be allow-listed,
        # not just the identifier that happens to follow the FROM keyword.
        ("SELECT customer_id FROM customer, secret_table", "unauthorized_table_reference"),
        ("SELECT customer_id FROM customer AS c, warehouse.secret AS s", "unauthorized_table_reference"),
        ("SELECT customer_id FROM customer c, secret_table s WHERE c.id = s.id", "unauthorized_table_reference"),
        # `SELECT ... INTO <name>` is CREATE TABLE AS in PostgreSQL - a write that
        # begins with the SELECT the guard is looking for.
        ("SELECT * INTO exfil_table FROM customer", "forbidden_keyword_detected"),
        ("SELECT customer_id INTO exfil FROM customer", "forbidden_keyword_detected"),
        # Dollar-quoted strings are string literals that contain neither quote
        # character, so they smuggle arguments past the literal guard.
        ("SELECT pg_read_file($$/etc/passwd$$) FROM customer", "literal_values_not_allowed"),
        ("SELECT lo_import($tag$/etc/passwd$tag$) FROM customer", "literal_values_not_allowed"),
    ],
)
def test_validate_sql_query_closes_guard_bypasses(sql: str, expected: str) -> None:
    """Each of these passed the guard with zero warnings before this contract."""
    assert expected in orch.validate_sql_query(sql, source_system=_SRC)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT customer_id FROM customer",
        "SELECT c.customer_id FROM customer AS c",
        "SELECT c.customer_id FROM customer c",
        "SELECT customer_id FROM customer JOIN customer ON 1=1",
    ],
)
def test_validate_sql_query_keeps_accepting_allowlisted_shapes(sql: str) -> None:
    """Closing the bypasses must not reject the shapes the drafter emits.

    ``SELECT customer_id FROM analytics.customer`` used to be in this list as an
    accepted control. That acceptance *was* the qualified-table hole: the check
    compared only the leaf, so any qualifier passed. The drafter never emits a
    qualified name, so the bare form is the whole contract.
    """
    assert orch.validate_sql_query(sql, source_system=_SRC) == []


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
            query="SELECT customer_id FROM crm_customer_master",
            user="admin",
            purpose="analysis",
            dry_run=True,
        )
    )
    assert resp.status == "SUCCEEDED"
    assert resp.row_count == 0
    # The property this test is named for. It asserted the count and never the
    # rows, so it passed against a response that reported zero and delivered
    # one: `row_count=0, len(rows)=1, rows=[{"result": 0}]`.
    assert resp.rows == [], (
        f"a dry run delivered {len(resp.rows)} row(s) while reporting "
        f"row_count={resp.row_count}: {resp.rows}"
    )


def test_a_dry_run_group_by_does_not_fabricate_a_measurement() -> None:
    """The group-by path invented a non-zero figure dated today.

    Measured before the repair, with ``dry_run=True``::

        row_count=0  len(rows)=1  columns=['week', 'active_count']
        rows=[{'week': '2026-10-26', 'active_count': 1}]

    and the audit event for the same call recorded ``{"dry_run": true,
    "row_count": 0}``. So the response contradicted itself and the compliance
    ledger asserted that no rows were delivered while one was. ``active_count:
    1`` is the part that matters: a reader cannot tell a fabricated row from a
    measured one, and this product's standing rule is that an unlabelled
    estimate on the ledger is a fabricated measurement.

    ``columns`` is deliberately still published on a dry run - the declared
    result shape is what a dry run is for - and only the data is empty.
    """
    resp = orch.execute_query(
        QueryExecutionRequest(
            dataset_ids=[_CRM],
            query=(
                "SELECT signup_at, count(*) AS active_customer_count "
                "FROM crm_customer_master GROUP BY signup_at LIMIT 1000"
            ),
            user="admin",
            purpose="analysis",
            dry_run=True,
        )
    )
    assert resp.status == "SUCCEEDED"
    assert resp.row_count == 0
    assert resp.rows == [], (
        f"a dry run fabricated a data row: {resp.rows}"
    )
    assert resp.columns, "the declared result shape is what a dry run reports"


def test_the_ledger_and_the_response_agree_and_the_rows_carry_provenance() -> None:
    """Two separate properties, because the first version of this conflated them.

    It asserted ``recorded == row_count == len(rows)`` for both values of
    ``dry_run``, which is false on a live run **and should be**: ``row_count``
    there is a labelled estimate (2000, from the catalog profile) while ``rows``
    is one fixed illustrative row. Demanding equality would demand that the mock
    fabricate 2000 rows, which is strictly worse than publishing one labelled
    sample. That over-reach is the same mistake as asserting a value domain the
    code never claimed, and writing it down is how it was caught.

    What is actually required:

    * the ledger's ``row_count`` describes the response's, always;
    * on a dry run all three agree at zero, because nothing was returned;
    * ``rows`` carries its own provenance, like every other figure in that
      response - it was the only one that did not, while the comment above it
      claimed each one did.

    One more thing this test got wrong before it got it right: it read the
    newest audit event as ``events[-1]``. ``catalog.list_audit_events`` returns
    newest **first**, so that was the oldest row, and on the loop's second pass
    it was a previous call's event - presenting as the product recording
    ``row_count: 0`` for a 2000-row response. Checking the ordering instead of
    assuming it is the difference between a defect and a misread.
    """
    from sdp import catalog

    for dry_run in (True, False):
        for query in (
            "SELECT customer_id FROM crm_customer_master",
            "SELECT signup_at, count(*) AS n FROM crm_customer_master "
            "GROUP BY signup_at",
        ):
            before = len(catalog.list_audit_events(limit=500))
            resp = orch.execute_query(
                QueryExecutionRequest(
                    dataset_ids=[_CRM],
                    query=query,
                    user="admin",
                    purpose="analysis",
                    dry_run=dry_run,
                )
            )
            events = catalog.list_audit_events(limit=500)
            assert len(events) > before, "the execution recorded no audit event"
            # Newest **first**. Reading ``events[-1]`` gave the oldest row, and
            # on the second iteration of this loop that was a previous call's
            # event - which looked exactly like the product recording 0 for a
            # 2000-row response until the ordering was checked rather than
            # assumed.
            recorded = events[0].details.get("row_count")
            assert recorded == resp.row_count, (
                f"dry_run={dry_run} {query!r}: the ledger recorded "
                f"row_count={recorded} and the response reported {resp.row_count}"
            )
            rows_source = resp.execution.get("rows_source")
            if dry_run:
                assert resp.row_count == len(resp.rows) == 0, (
                    f"{query!r}: a dry run reported {resp.row_count} and "
                    f"delivered {len(resp.rows)}"
                )
                assert rows_source == "withheld_dry_run", rows_source
            else:
                assert rows_source == "fixed_mock_sample", (
                    "the row sample is the one figure in this response with no "
                    f"provenance: {resp.execution}"
                )


@pytest.mark.parametrize(
    "sql",
    [
        # The allow-list compared only the last dot-separated component, so any
        # qualification whose leaf matches passed with zero warnings.
        "SELECT count(*) FROM pg_catalog.customer",
        "SELECT count(*) FROM otherdb.otherschema.customer",
        "SELECT count(*) FROM information_schema.customer",
        "SELECT count(*) FROM customer JOIN finance.customer x ON 1=1",
    ],
)
def test_validate_sql_query_rejects_a_qualified_table_whose_leaf_matches(sql: str) -> None:
    """``FROM pg_catalog.customer`` is not ``FROM customer``. The drafter only ever
    emits the bare table name (``_source_table_name``), so a qualified reference is
    one the allow-list cannot prove and must be refused."""
    assert "unauthorized_table_reference" in orch.validate_sql_query(sql, source_system=_SRC)


# --------------------------------------------------------------------------- #
# Soundness of the certification, not just of the parse.
#
# ``validate_sql_query`` is the documented boundary a real engine would sit
# behind, so a statement it certifies with zero warnings is a claim about what
# the engine will do. Two ways that claim was false, both measured against an
# allow-list of ``customer``:
#
#   SELECT count(*) FROM customer$pii_raw LIMIT 1   -> [] , parsed ['customer']
#   SELECT count(*) FROM customer×pii_raw LIMIT 1   -> [] , parsed ['customer']
#   SELECT pg_terminate_backend(12345) FROM customer -> []
#   SELECT lo_unlink(1) FROM customer                -> []
#   SELECT pg_sleep(100000) FROM customer            -> []
#   SELECT pg_reload_conf() FROM customer            -> []
#
# PostgreSQL's identifier continuation set is ``[A-Za-z\200-\377_0-9$]``, so the
# first two name a single table that is not the allow-listed one; the parser
# split it and discarded the remainder as an alias. The last four are the gap
# the literal guard left: it catches an argument-bearing call through the string
# rule, which leaves zero-argument and integer-argument calls in the safe lane.
#
# Nothing executes here - ``execute_query`` is a mock engine - so what those
# functions do, and that ``$`` continues an identifier, is PostgreSQL's
# documented behaviour rather than an observation. The false certification is
# the defect either way, and it is what is measured above.
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT count(*) FROM customer$pii_raw LIMIT 1",
        "SELECT count(*) FROM customer×pii_raw LIMIT 1",
        "SELECT count(*) FROM customer$ LIMIT 1",
        "SELECT count(*) FROM ¢ustomer LIMIT 1",
        "SELECT count(*) FROM customer, customer$pii_raw",
    ],
)
def test_an_identifier_continuation_character_cannot_shorten_a_table_name(sql: str) -> None:
    assert "unauthorized_table_reference" in orch.validate_sql_query(sql, source_system=_SRC)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT count(*) FROM customer",
        "SELECT count(*) FROM customer AS c",
        "SELECT c.customer_id FROM customer c",
        "SELECT customer_id FROM customer JOIN customer ON 1=1",
    ],
)
def test_widening_the_token_did_not_refuse_a_legitimate_reference(sql: str) -> None:
    """The fail-closed direction must not have closed on the allow-listed name."""
    assert "unauthorized_table_reference" not in orch.validate_sql_query(sql, source_system=_SRC)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT pg_terminate_backend(12345) FROM customer",
        "SELECT lo_unlink(1) FROM customer",
        "SELECT pg_sleep(100000) FROM customer",
        "SELECT pg_reload_conf() FROM customer",
        "SELECT pg_read_file(customer_email) FROM customer",
        "SELECT current_setting(customer_id) FROM customer",
        "SELECT COUNT(*), pg_sleep(1) FROM customer",
    ],
)
def test_a_function_outside_the_allowlist_is_refused(sql: str) -> None:
    assert "unauthorized_function_call" in orch.validate_sql_query(sql, source_system=_SRC)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT count(*) FROM customer",
        "SELECT COUNT(*) FROM customer",
        "SELECT sum(customer_id) FROM customer",
        "SELECT avg(customer_id) FROM customer",
        "SELECT min(customer_id), max(customer_id) FROM customer",
        # A parenthesised expression and an IN list are not function calls.
        "SELECT count(*) FROM customer WHERE customer_id IN (1, 2)",
        "SELECT count(*) FROM customer WHERE (customer_id) > 1",
    ],
)
def test_the_allowlist_admits_what_the_product_itself_emits(sql: str) -> None:
    assert "unauthorized_function_call" not in orch.validate_sql_query(sql, source_system=_SRC)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT pg_catalog.count(*) FROM customer",
        "SELECT evil.count(*) FROM customer",
        "SELECT public.sum(customer_id) FROM customer",
        "SELECT attacker_schema.max(customer_id) FROM customer",
        "SELECT other.schema.avg(customer_id) FROM customer",
        "SELECT pg_catalog . count(*) FROM customer",
    ],
)
def test_a_qualified_call_is_refused_even_when_its_last_part_is_allowlisted(sql: str) -> None:
    """The allow-list holds names, so a qualified call must not be read by its tail.

    ``_FUNCTION_CALL`` captured only the identifier immediately before the
    ``(``, so ``evil.count(*)`` presented as ``count`` - a member of the
    allow-list - and the statement drew **no warning at all**. The name is not
    the function: in PostgreSQL the schema qualification selects which
    implementation runs, and ``search_path`` is not the only way to reach a
    different one. Admitting a name while ignoring who owns it certifies
    something the allow-list never reviewed.

    The sibling cases matter as much as the first: an allow-list read by its
    tail is bypassed by *any* prefix, so a schema an attacker can create in is
    enough. The unqualified members stay admitted below, which is what makes
    this a boundary rather than a tightening.

    ContextualWisdomLab/semantic-data-portal#32 states this rule explicitly -
    "schema-qualified function calls are rejected even when their final
    identifier resembles an allowlisted function, because qualification can
    select a different implementation" - and this branch did not hold it. The
    27 other cases in that PR's corpus were already refused here; these four
    were not.
    """
    assert "unauthorized_function_call" in orch.validate_sql_query(sql, source_system=_SRC)


def test_the_allowlist_is_an_allowlist_not_a_denylist() -> None:
    """A deny-list cannot certify, because the set of unsafe names is unbounded.

    docs/prd-trd.md states BRW-005 ("read-only SELECT only ... block DDL/DML and
    unsafe functions") as P0, so this is a declared requirement. An allow-list
    is the only shape that can satisfy it; this test pins the shape so a future
    change cannot invert it and keep the name.
    """
    assert orch._ALLOWED_FUNCTIONS == frozenset({"count", "sum", "avg", "min", "max"})
    invented = "SELECT definitely_not_a_real_function(1) FROM customer"
    assert "unauthorized_function_call" in orch.validate_sql_query(invented, source_system=_SRC)


# --------------------------------------------------------------------------- #
# The drafter must not emit SQL its own validator rejects.
# --------------------------------------------------------------------------- #


def _publish(dataset_id: str, table: str, columns: list[str]) -> None:
    from fastapi.testclient import TestClient

    from sdp.api import app

    client = TestClient(app, raise_server_exceptions=False)
    payload = {
        "actor": "admin",
        "id": dataset_id,
        "tenant_id": "demo",
        "title": "T",
        "description": "d",
        "owner": "a",
        "steward": "a",
        "domain": "s",
        "source_system": f"postgresql://a.dw/{table}",
        "sensitivity": "low",
        "update_frequency": "daily",
        "quality_score": 0.9,
        "freshness_score": 0.9,
        "schema": [
            {
                "name": name,
                "datatype": "string",
                "nullable_ratio": 0.0,
                "distinct_ratio": 1.0,
            }
            for name in columns
        ],
        "distributions": [{"id": "d1", "format": "table", "endpoint": "https://x/y"}],
        "profile": {},
    }
    assert client.post("/catalog/datasets", json=payload).status_code == 200, dataset_id
    client.post(f"/catalog/datasets/{dataset_id}/publish", json={"actor": "admin"})
    return client


@pytest.mark.parametrize("table", sorted(orch._TABLE_CLAUSE_TERMINATORS))
def test_a_clause_keyword_source_table_refuses_instead_of_drafting(table: str) -> None:
    """All 24 of them, because ``order`` is the one that would be reported.

    Measured before: the drafter returned 200 with
    ``'... FROM order WHERE order_ts >= current_date - 90 LIMIT 1000'`` and the
    very next call in the documented draft-then-execute workflow answered 400
    ``unauthorized_table_reference`` - the product accusing its own output of a
    governance violation, with no way to proceed. ``FROM order`` is also unquoted
    reserved-word SQL that PostgreSQL would refuse.
    """
    client = _publish(f"clause-{table}", table, ["some_column"])
    response = client.post(
        "/llm/draft-query",
        json={"user": "admin", "purpose": "analysis", "dataset_id": f"clause-{table}", "question": "q"},
    )
    assert response.status_code == 400, response.text
    detail = response.json()["detail"]
    assert detail["error"] in {"unquotable_source_table", "draft_rejected_by_validator"}, detail
    assert table in detail["reason"], detail


def test_a_rewritten_column_is_reported_rather_than_contradicted() -> None:
    """The response asserted it used only catalog-validated columns.

    Measured with a declared column ``order amount``: the query named
    ``order_amount`` while ``requested_columns`` reported ``order amount``, so a
    buyer learned otherwise from the warehouse. The rewrite is kept - a quoted
    identifier could never pass this product's own gate, which refuses any
    statement containing a double quote - and is now stated.
    """
    client = _publish("rewrite-space", "spacey", ["order amount"])
    body = client.post(
        "/llm/draft-query",
        json={
            "user": "admin",
            "purpose": "analysis",
            "dataset_id": "rewrite-space",
            "question": "q",
            "group_by": "order amount",
        },
    ).json()
    assert "order_amount" in body["query"]
    assert body["emitted_identifiers"] == {"order amount": "order_amount"}
    assert any("변환" in assumption for assumption in body["assumptions"]), body["assumptions"]


def test_an_ambiguous_rewrite_is_refused_rather_than_guessed() -> None:
    """The mapping is not injective, so the draft could aggregate the wrong column."""
    client = _publish("rewrite-collide", "collide", ["order amount", "order_amount"])
    response = client.post(
        "/llm/draft-query",
        json={
            "user": "admin",
            "purpose": "analysis",
            "dataset_id": "rewrite-collide",
            "question": "q",
            "group_by": "order amount",
        },
    )
    assert response.status_code == 400, response.text
    assert response.json()["detail"]["error"] == "ambiguous_identifier"


def test_the_drafter_self_check_is_a_live_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    """Not dead code: the backstop fires when validation would reject a draft.

    Two causes of "the drafter emits SQL its own validator rejects" have been
    found and fixed one at a time - the ``interval '<n> day'`` literal, and a
    source table colliding with a clause keyword. This check is what catches the
    third without waiting for a report, so it is exercised by making validation
    reject what the drafter emits.
    """
    client = _publish("selfcheck-ds", "selfcheck_table", ["some_column"])
    ok = client.post(
        "/llm/draft-query",
        json={"user": "admin", "purpose": "analysis", "dataset_id": "selfcheck-ds", "question": "q"},
    )
    assert ok.status_code == 200, ok.text

    # ``count`` is what every draft emits; removing it from the allow-list makes
    # the drafter's own output fail validation.
    monkeypatch.setattr(orch, "_ALLOWED_FUNCTIONS", frozenset({"sum"}))
    refused = client.post(
        "/llm/draft-query",
        json={"user": "admin", "purpose": "analysis", "dataset_id": "selfcheck-ds", "question": "q"},
    )
    assert refused.status_code == 400, refused.text
    detail = refused.json()["detail"]
    assert detail["error"] == "draft_rejected_by_validator", detail
    assert "unauthorized_function_call" in detail["warnings"], detail


def test_every_seeded_dataset_drafts_a_statement_its_validator_accepts() -> None:
    """The documented workflow, end to end, for every dataset the demo ships.

    This is the property both of those defects broke, and it is cheap to assert
    over the whole seed rather than one dataset.
    """
    from fastapi.testclient import TestClient

    from sdp import catalog
    from sdp.api import app

    client = TestClient(app, raise_server_exceptions=False)
    for dataset in catalog.list_datasets():
        if dataset.status != "published" or not dataset.schema:
            continue
        draft = client.post(
            "/llm/draft-query",
            json={
                "user": "admin",
                "purpose": "analysis",
                "dataset_id": dataset.id,
                "question": "q",
            },
        )
        assert draft.status_code == 200, (dataset.id, draft.text)
        executed = client.post(
            "/browse/query",
            json={
                "user": "admin",
                "purpose": "analysis",
                "dataset_ids": [dataset.id],
                "query": draft.json()["query"],
                "language": "sql",
            },
        )
        assert executed.status_code == 200, (dataset.id, draft.json()["query"], executed.text)
