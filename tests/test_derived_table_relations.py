"""A derived table over the authorised relation must not be refused.

The allow-list reads the FROM clause with a token scan that does not see
parentheses, so a derived table's inner ``SELECT`` arrived where a table name
was expected. That is the scanner's "I cannot read this list" branch, which
refuses - correctly, as a default. The consequence was never measured: six
ordinary single-source shapes are refused, and the reason given is
``unauthorized_table_reference`` on a statement whose only table **is** the
authorised one. An analyst writing

    SELECT count(*) FROM (SELECT customer_id FROM customer) t

is told the query touches a table it is not allowed to touch. The refusal does
not name a real cause, and there is no spelling of the same question that gets
through.

The corpus here is taken from ContextualWisdomLab/semantic-data-portal#35,
which adds a parenthesis-aware scanner on top of ``main`` and asserts both
directions. Measured against this branch before the repair: **0 of its 19
hostile shapes slipped through** - the allow-list is sound - and **6 of its 8
legitimate shapes were refused**. So this is an availability defect with a
misleading reason, not a bypass, and the hostile half is kept here as the
regression net that makes the availability repair safe.

One of those hostile shapes is a trap worth naming: ``FROM (SELECT * FROM crm
WHERE x > 0 t, customer`` has unbalanced parentheses, and it is currently
refused *because* the scanner cannot see parentheses at all. Teaching it to see
them removes that accident, so the balance check has to arrive in the same
change or the repair opens a hole while closing a gap.
"""

from __future__ import annotations

import pytest

from sdp import orchestrator as orch

# The allow-listed relation for each locator below.
_CRM = "s3://analytics/events/crm"          # -> crm
_CUSTOMER = "postgresql://analytics.dw/customer"  # -> customer


LEGITIMATE = [
    "SELECT customer_id FROM customer",
    "SELECT count(*) AS c FROM (SELECT customer_id, signup_at FROM customer) t",
    "SELECT * FROM (SELECT customer_id FROM customer WHERE customer_id > 0) t",
    "SELECT * FROM (customer JOIN customer ON customer.id = customer.id) j",
    "SELECT * FROM customer, (SELECT customer_id FROM customer WHERE customer_id > 0) t",
    "SELECT * FROM customer LEFT JOIN (SELECT customer_id FROM customer) t ON customer.id = t.customer_id",
    "SELECT * FROM customer, LATERAL (SELECT customer_id FROM customer) s",
    "SELECT * FROM ONLY customer",
    # Parentheses *inside* the region. Matching the first ``)`` rather than the
    # one at the same depth cuts the region short, and the relation after the
    # cut is lost - so these shapes are what make the depth count load-bearing.
    # Added after a mutation that broke the depth count reddened nothing: the
    # corpus was thin, which is a defect in the guard, not permission to drop
    # the code.
    "SELECT * FROM (SELECT count(*) AS c FROM customer) t",
    "SELECT * FROM (SELECT max(signup_at) FROM customer) t",
    "SELECT * FROM (SELECT customer_id FROM customer WHERE customer_id IN (1, 2)) t",
]

HOSTILE = [
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
    "SELECT * FROM (SELECT customer_id FROM crm WHERE customer_id > 0) t, customer",
    "SELECT count(*) FROM crm, customer",
    "SELECT * FROM (SELECT count(*) FROM secrets) t",
    "SELECT * FROM (SELECT count(*) FROM crm) t, customer",
]

UNBALANCED = [
    "SELECT * FROM (SELECT * FROM crm WHERE x > 0 t, customer",
    "SELECT * FROM crm)",
    "SELECT * FROM (SELECT customer_id FROM crm",
]


@pytest.mark.parametrize("sql", LEGITIMATE)
def test_a_single_source_query_is_not_refused_for_its_shape(sql: str) -> None:
    """Every table named is the authorised one, so there is nothing to refuse."""
    assert orch.validate_sql_query(sql, source_system=_CUSTOMER) == []


@pytest.mark.parametrize("sql", HOSTILE)
def test_a_second_relation_is_still_refused_however_it_is_nested(sql: str) -> None:
    """The regression net: the repair must not buy availability with a bypass."""
    warnings = orch.validate_sql_query(sql, source_system=_CRM)
    assert "unauthorized_table_reference" in warnings, warnings


@pytest.mark.parametrize("sql", UNBALANCED)
def test_an_unbalanced_parenthesis_is_refused_rather_than_guessed(sql: str) -> None:
    """Fail closed where the statement cannot be read.

    Before the repair these were refused by accident - the scanner could not
    see parentheses, so the inner ``SELECT`` landed where a table was expected
    and the list was declared unreadable. Once it can see them, the imbalance
    has to be checked on purpose.
    """
    assert orch._referenced_source_tables(sql) is None, orch._referenced_source_tables(sql)
    assert "unauthorized_table_reference" in orch.validate_sql_query(sql, source_system=_CRM)


def test_every_relation_in_a_parenthesised_join_reaches_the_allow_list() -> None:
    """Both sides, not just the one the scan happens to reach first.

    #35 pins this list exactly, and it is the property the hostile cases above
    depend on: a relation the scanner never records is a relation the allow-list
    never checks.
    """
    assert orch._referenced_source_tables(
        "select * from crm, (customer JOIN secrets ON crm.id = customer.id) j"
    ) == ["crm", "customer", "secrets"]


def test_a_derived_table_contributes_its_inner_relations_not_its_alias() -> None:
    """The alias is not a relation, and the inner table is."""
    assert orch._referenced_source_tables(
        "select count(*) as c from (select customer_id from customer) t"
    ) == ["customer"]
    assert orch._referenced_source_tables("select * from only customer") == ["customer"]


def test_the_refusal_names_a_cause_that_is_true() -> None:
    """The measured symptom, stated as a contract.

    ``unauthorized_table_reference`` on a statement whose only table is the
    authorised one is a false statement about the query, not a stricter policy.
    """
    sql = "SELECT count(*) FROM (SELECT customer_id FROM customer) t"
    warnings = orch.validate_sql_query(sql, source_system=_CUSTOMER)
    assert "unauthorized_table_reference" not in warnings, (
        "the only relation in this statement is the authorised one, so this "
        f"reason is false: {warnings}"
    )
