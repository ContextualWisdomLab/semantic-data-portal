"""The draft now names the relation the catalog declares, and the gate agrees.

``tests/test_draft_source_kind.py`` pinned the state this repairs: the drafted
``FROM`` came from the last path segment of ``source_system``, a *connection*
locator, so no draft named a relation that exists. The catalog knew the answer
all along - two of the five seed datasets declare a ``postgresql.table``
distribution whose endpoint ends in the relation::

    crm-customer-master  postgresql://analytics.dw/customer -> FROM customer
      declared: https://example.internal/api/table/crm_customer_master
    sales-order          postgresql://analytics.dw/sales    -> FROM sales
      declared: https://example.internal/api/table/sales_order

The other three declare ``parquet``, ``sparql.graph`` and ``rest.json``: they
have no relation at all, so they keep the locator-derived name and keep saying
so. That is why ``executable_against_source`` becomes true for exactly two
datasets rather than for all five.

The second half matters as much as the first. ``validate_sql_query``'s
source-table allow-list was built from the *same* guess, so the product
refused the catalog's own relation and accepted the one it had invented::

    validate("... FROM crm_customer_master ...") -> ['unauthorized_table_reference']
    validate("... FROM customer ...")            -> []

A buyer who corrected the table name by hand was refused by the governance
gate; one who did not was refused by their warehouse. Resolving the relation in
one place and letting both readers use it is what closes that, and it is why
the allow-list is not given its own lookup.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sdp.api import app  # noqa: E402
from sdp.catalog import get_dataset, list_datasets  # noqa: E402
from sdp.orchestrator import (  # noqa: E402
    DRAFT_SQL_DIALECT,
    source_relation_name,
    declares_relational_distribution,
    validate_sql_query,
)

client = TestClient(app)

# Measured at bf5f8cc. Asserted rather than assumed: a reseed that adds or drops
# a declared relation fails here instead of silently changing what the product
# claims is executable.
DECLARED = {
    "crm-customer-master": "crm_customer_master",
    "sales-order": "sales_order",
}
UNDECLARED = ["crm-event", "semantic-glossary", "marketing-campaign"]


def _draft(dataset_id: str) -> dict:
    """One draft for this dataset."""
    response = client.post(
        "/llm/draft-query",
        json={
            "dataset_id": dataset_id,
            "question": "월별 추이를 보여줘",
            "user": "admin",
            "purpose": "analytics",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


class _DistributionDouble:
    """One declared distribution, carrying just the two fields read."""

    def __init__(self, declared_format: str, endpoint: str) -> None:
        self.format = declared_format
        self.endpoint = endpoint


class _DatasetDouble:
    """A dataset carrying only the declaration under test."""

    def __init__(self, distributions: list[_DistributionDouble]) -> None:
        self.distributions = distributions


def _dataset_double(declared_format: str, relation: str) -> _DatasetDouble:
    """A dataset whose single distribution declares this format and relation.

    Synthetic on purpose: the seed catalogue cannot express a non-emittable
    name or a non-PostgreSQL table, and both rules were measured to be
    untested against it - one by a Hypothesis counterexample, the other by a
    mutation that stayed green.
    """
    return _DatasetDouble(
        [
            _DistributionDouble(
                declared_format, f"https://example.internal/api/table/{relation}"
            )
        ]
    )


def test_the_seed_still_declares_two_relations_and_three_non_relations() -> None:
    """The premise, measured from the catalog rather than restated."""
    resolved = {
        dataset.id: source_relation_name(dataset) for dataset in list_datasets()
    }
    assert {k: v for k, v in resolved.items() if v} == DECLARED, resolved
    assert sorted(k for k, v in resolved.items() if v is None) == sorted(UNDECLARED)


def test_the_relation_is_only_taken_from_the_drafted_dialect() -> None:
    """A relation in some other dialect is not a relation this draft can name.

    The draft emits ``DRAFT_SQL_DIALECT`` SQL, so only a distribution of that
    dialect can be claimed executable. The suffix is derived from the same
    constant the response publishes as ``dialect``, so the two cannot disagree.
    """
    dataset = get_dataset("crm-customer-master")
    declared = [
        dist for dist in dataset.distributions if str(dist.format).endswith(".table")
    ]
    assert declared, [str(d.format) for d in dataset.distributions]
    assert all(
        str(dist.format) == f"{DRAFT_SQL_DIALECT}.table" for dist in declared
    ), [str(d.format) for d in declared]
    assert _draft("crm-customer-master")["dialect"] == DRAFT_SQL_DIALECT


@pytest.mark.parametrize("dataset_id,relation", sorted(DECLARED.items()))
def test_a_declared_relation_is_what_the_draft_names(
    dataset_id: str, relation: str
) -> None:
    """The defect, from the buyer's side: the statement names a real table."""
    body = _draft(dataset_id)
    assert f"FROM {relation}" in body["query"], body["query"]
    assert body["source_table"] == relation, body.get("source_table")


@pytest.mark.parametrize("dataset_id,relation", sorted(DECLARED.items()))
def test_the_gate_accepts_the_declared_relation_and_refuses_the_locator(
    dataset_id: str, relation: str
) -> None:
    """The self-contradiction, inverted and pinned in both directions.

    Accepting the real relation is half of it; refusing the invented one is the
    other half. If only the first were asserted, an allow-list widened to admit
    both would pass while still certifying a statement that cannot run.
    """
    dataset = get_dataset(dataset_id)
    locator_segment = dataset.source_system.rstrip("/").rsplit("/", 1)[-1]
    assert locator_segment != relation, (locator_segment, relation)

    declared = source_relation_name(dataset)
    real = validate_sql_query(
        f"select count(*) from {relation} limit 1",
        source_system=dataset.source_system,
        declared_relation=declared,
    )
    invented = validate_sql_query(
        f"select count(*) from {locator_segment} limit 1",
        source_system=dataset.source_system,
        declared_relation=declared,
    )
    assert real == [], real
    assert "unauthorized_table_reference" in invented, invented


@pytest.mark.parametrize("dataset_id,relation", sorted(DECLARED.items()))
def test_a_relational_draft_now_says_it_is_executable(
    dataset_id: str, relation: str
) -> None:
    """``executable_against_source`` was false for all five; now it is honest."""
    body = _draft(dataset_id)
    assert body["executable_against_source"] is True, body
    assert body["source_kind"] == "sql", body["source_kind"]
    assert relation in body["execution_caveat"], body["execution_caveat"]


@pytest.mark.parametrize("dataset_id", UNDECLARED)
def test_a_dataset_with_no_declared_relation_still_says_so(dataset_id: str) -> None:
    """The three non-relational sources are unchanged, and that is the point.

    Flipping every dataset to executable would be the same over-claim in a new
    place: an object prefix, a named graph and a REST path are not relations.
    """
    body = _draft(dataset_id)
    assert body["executable_against_source"] is False, body
    assert body["source_kind"] != "sql", body["source_kind"]
    assert "locator" in body["execution_caveat"], body["execution_caveat"]


@pytest.mark.parametrize(
    "declared, expected",
    [
        ("crm_customer_master", "crm_customer_master"),
        ("_private_table", "_private_table"),
        # Sanitised, not rejected: ``$`` is a legal continuation character in
        # PostgreSQL and in this module's token, but it is not a plain
        # identifier, so it is declined rather than rewritten.
        #
        # This case used to assert ``("table$x", "table_x")`` - the rewrite,
        # "asserted as measured". Recording a rewrite as expected was the
        # mistake: the draft published the rewritten name while claiming in its
        # assumptions and caveat that it *is* the relation the catalog declared,
        # with nothing in ``emitted_identifiers``. A name that is not the
        # declared one is the defect this resolver exists to fix, so measuring
        # the rewrite and writing it down is not the same as accepting it.
        ("table$x", None),
        # The URL escape, which is how a space actually arrives. Undecoded,
        # ``%`` became ``_`` and the draft emitted ``sales_20order`` - a
        # fragment of the encoding, published as the declared relation.
        ("sales%20order", None),
        ("sales order", None),
        # Quoting and termination characters, declined rather than scrubbed.
        ("orders;drop", None),
        ("orders'x", None),
        ('orders"x', None),
        ("orders-2024", None),
        # Too many parts to be a relation reference.
        ("a.b.c.d", None),
        # Empty parts are not identifiers.
        (".orders", None),
        ("orders.", None),
        ("a..b", None),
        # A leading digit is not an identifier. ``_safe_identifier`` returns
        # these unchanged, so a declaration carrying one used to be emitted and
        # then refused by the draft's own allow-list as
        # ``unauthorized_table_reference`` - a security-shaped reason for a
        # naming problem. Hypothesis found ``"0"`` in the fuzz seam.
        ("0", None),
        # Worse: the parser reads ``FROM 0abc`` as the table ``abc``, so the
        # emitted name and the authorized name are different strings.
        ("0abc", None),
        # A clause keyword ends the table list, so nothing is read as a table.
        ("select", None),
    ],
)
def test_a_declaration_that_cannot_be_emitted_is_declined(
    declared: str, expected: str | None
) -> None:
    """Resolution declines a name the emitted SQL would not carry as written.

    Driven through a synthetic dataset rather than the seed, because the seed
    cannot express this case - which is exactly why it took a fuzz run to find.
    """
    resolved = source_relation_name(
        _dataset_double(f"{DRAFT_SQL_DIALECT}.table", declared)
    )
    assert resolved == expected, resolved


@pytest.mark.parametrize(
    "declared_format,expected",
    [
        (f"{DRAFT_SQL_DIALECT}.table", "some_relation"),
        # A relation in another dialect is not a relation *this* statement can
        # name: the draft is emitted as DRAFT_SQL_DIALECT SQL and claiming it
        # executable against a MySQL or Snowflake table would be a new
        # over-claim. The seed declares no such distribution, so widening the
        # match to any format containing "table" was behaviourally inert on it
        # and passed every other test in this file - which is why this case is
        # driven synthetically.
        ("mysql.table", None),
        ("snowflake.table", None),
        ("delta.table", None),
        # Not a relation at all - the three the seed actually has.
        ("parquet", None),
        ("sparql.graph", None),
        ("rest.json", None),
        # Near-misses that must not be read as the relational format.
        (f"{DRAFT_SQL_DIALECT}.table.backup", None),
        (f"not_{DRAFT_SQL_DIALECT}.table", None),
    ],
)
def test_only_the_drafted_dialects_table_is_read_as_a_relation(
    declared_format: str, expected: str | None
) -> None:
    """The dialect rule itself, independent of what the seed happens to carry."""
    resolved = source_relation_name(_dataset_double(declared_format, "some_relation"))
    assert resolved == expected, resolved


def test_the_validator_falls_back_to_the_locator_with_no_declared_relation() -> None:
    """The fuzz harness calls it with a bare ``source_system`` and no dataset.

    ``fuzz/fuzz_query_safety.py`` and its Hypothesis mirror pass only
    ``source_system``, so the fallback is a live path, not dead code - and the
    argument stays optional for that reason.
    """
    warnings = validate_sql_query(
        "select count(*) from customer limit 1",
        source_system="postgresql://analytics.dw/customer",
    )
    assert warnings == [], warnings
    refused = validate_sql_query(
        "select count(*) from crm_customer_master limit 1",
        source_system="postgresql://analytics.dw/customer",
    )
    assert "unauthorized_table_reference" in refused, refused


def test_one_resolver_serves_the_draft_and_the_gate() -> None:
    """Behavioural: both readers follow the same function, so neither drifts.

    Replacing the resolver's binding in the orchestrator moves the drafted
    statement *and* what the gate authorizes. Two copies would move one.
    """
    from sdp import orchestrator

    original = orchestrator.source_relation_name
    try:
        orchestrator.source_relation_name = lambda _dataset: "sentinel_relation"
        body = _draft("crm-customer-master")
        assert "FROM sentinel_relation" in body["query"], body["query"]
        # The self-check runs inside the same request and did not reject it, so
        # the gate authorized the same name the draft emitted.
        assert "warnings" not in body, body.get("warnings")
    finally:
        orchestrator.source_relation_name = original


# ---------------------------------------------------------------------------
# A qualified declaration is emittable, and nothing is rewritten on the way.
#
# The allow-list compares references raw (see
# ``tests/test_table_allow_list_compares_raw.py``), so ``FROM
# analytics.sales_order`` against the declared ``analytics.sales_order``
# matches. That is what makes emitting the declared name verbatim possible
# rather than having to choose between a rewrite and a refusal.
# ---------------------------------------------------------------------------

QUALIFIED = "analytics.sales_order"


@pytest.mark.parametrize(
    "declared",
    [
        "orders",
        QUALIFIED,
        "warehouse.analytics.sales_order",
        "_private_orders",
        "Orders2024",
    ],
    ids=["bare", "schema_qualified", "three_part", "leading_underscore", "mixed_case"],
)
def test_an_emittable_declaration_is_returned_exactly_as_written(declared: str) -> None:
    """No rewriting: resolution either returns the declared string or ``None``."""
    resolved = source_relation_name(
        _dataset_double(f"{DRAFT_SQL_DIALECT}.table", declared)
    )
    assert resolved == declared, resolved


def test_the_gate_accepts_a_qualified_declaration_naming_itself() -> None:
    """Emitting a qualified name is only honest if the allow-list takes it."""
    assert validate_sql_query(
        f"select count(*) from {QUALIFIED} limit 1",
        source_system="postgresql://analytics.dw/orders",
        declared_relation=QUALIFIED,
    ) == []


def test_the_gate_still_refuses_a_different_qualification() -> None:
    """Accepting the declared qualified name must not accept any qualified name."""
    warnings = validate_sql_query(
        f"select count(*) from other.{QUALIFIED.split('.')[1]} limit 1",
        source_system="postgresql://analytics.dw/orders",
        declared_relation=QUALIFIED,
    )
    assert "unauthorized_table_reference" in warnings, warnings


@pytest.mark.parametrize(
    "declared",
    ["table$x", "sales%20order", "orders;drop", "orders'x", "0abc", "a.b.c.d"],
)
def test_a_declined_declaration_is_never_published_as_the_declared_relation(
    declared: str,
) -> None:
    """The honesty property, stated over the resolver rather than one example.

    Whatever the draft ends up naming, it must not be a *rewrite* of the
    declared name presented as the declared name. Resolution returning ``None``
    is what routes the caller to the locator-derived name and the
    "derived, not declared" caveat.
    """
    resolved = source_relation_name(
        _dataset_double(f"{DRAFT_SQL_DIALECT}.table", declared)
    )
    assert resolved is None, (
        f"{declared!r} resolved to {resolved!r}, which the draft would publish "
        "as the relation the catalog declares"
    )


def test_an_escape_that_decodes_to_an_identifier_resolves_to_the_decoded_name() -> None:
    """The URL decode has to change an outcome, or it is not being tested.

    ``sales%20order`` is declined with or without decoding - ``%`` is not in
    the identifier pattern either way - so listing it among the declined cases
    proves nothing about the decode. Removing ``unquote`` left every assertion
    in this file green. ``%5F`` is the case that separates them: the declared
    relation *is* ``sales_order``, and only a decoding resolver can say so.
    """
    resolved = source_relation_name(
        _dataset_double(f"{DRAFT_SQL_DIALECT}.table", "sales%5Forder")
    )
    assert resolved == "sales_order", resolved


def _onboard_published(dataset_id: str, declared_format: str, relation: str) -> None:
    """Create and publish a dataset declaring exactly this distribution."""
    created = client.post(
        "/catalog/datasets",
        json={
            "id": dataset_id,
            "title": "caveat fixture",
            "description": "a declaration whose name cannot be emitted",
            "owner": "owner-team",
            "steward": "steward-team",
            "domain": "고객",
            "tenant_id": "demo",
            "source_system": "postgresql://analytics.dw/orders",
            "sensitivity": "low",
            "update_frequency": "daily",
            "quality_score": 0.9,
            "freshness_score": 0.9,
            "schema": [
                {
                    "name": "order_id",
                    "datatype": "string",
                    "description": "order identifier",
                    "pii": False,
                    "nullable_ratio": 0.0,
                    "distinct_ratio": 1.0,
                    "classification": [],
                }
            ],
            "distributions": [
                {
                    "id": "declared_table",
                    "format": declared_format,
                    "endpoint": f"https://example.internal/api/table/{relation}",
                }
            ],
            "actor": "admin",
        },
    )
    assert created.status_code == 200, created.text
    published = client.post(
        f"/catalog/datasets/{dataset_id}/publish", json={"actor": "admin"}
    )
    assert published.status_code == 200, published.text


def test_the_caveat_distinguishes_no_declaration_from_an_unusable_one() -> None:
    """``None`` has two causes and the caveat used to state only one.

    "this dataset declares no postgresql.table distribution, so the catalog has
    no relation name to give" is true of the three seed datasets that declare
    ``parquet``, ``sparql.graph`` and ``rest.json``. It is false of a dataset
    that declares ``sales order`` - the catalog *does* have a name, and the
    reason it is not used is the name. Repairing the rewrite without repairing
    this would trade one false claim for another.

    The first version of this test asserted ``declares_relational_distribution``
    and ``source_relation_name`` and called itself a caveat test. Replacing the
    caveat branch's condition with ``False`` left it green: it checked the
    helper, not the sentence the helper exists to choose. So the sentence is
    read here, out of the drafted response.
    """
    unusable = _dataset_double(f"{DRAFT_SQL_DIALECT}.table", "sales%20order")
    absent = _dataset_double("parquet", "whatever")
    assert source_relation_name(unusable) is None
    assert source_relation_name(absent) is None
    assert declares_relational_distribution(unusable) is True
    assert declares_relational_distribution(absent) is False

    _onboard_published("caveat-unusable-name", f"{DRAFT_SQL_DIALECT}.table", "sales%20order")
    caveat = _draft("caveat-unusable-name")["execution_caveat"]
    assert "선언했지만" in caveat, caveat
    assert "선언하지 않았으므로" not in caveat, (
        "the caveat tells an operator who declared a relation that they "
        f"declared none: {caveat}"
    )

    for undeclared in UNDECLARED:
        other = _draft(undeclared)["execution_caveat"]
        assert "선언하지 않았으므로" in other, (undeclared, other)
        assert "선언했지만" not in other, (undeclared, other)


def test_the_resolver_has_no_sanitiser_on_its_path() -> None:
    """Structural, because the behavioural guards above cannot see a near-miss.

    A sanitiser reintroduced here would pass every case that happens to be
    idempotent under it and fail only the ones this file lists. The rule is
    that the declared segment reaches the return unmodified except for URL
    decoding, so ``_safe_identifier`` must not appear in this function.
    """
    import inspect

    source = inspect.getsource(source_relation_name)
    body = source.split('"""', 2)[-1]
    assert "_safe_identifier" not in body, body
