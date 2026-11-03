"""The draft says where its table name came from, because it is not a relation.

``POST /llm/draft-query`` asserted ``카탈로그에서 검증된 테이블/컬럼만 사용``.
The columns are catalog-declared; the **table** was not. ``table_name`` comes
from the last path segment of ``source_system``, a *connection* locator.
Measured at ``9cf278e`` over the whole seed catalogue::

    crm-customer-master  postgresql://analytics.dw/customer   -> FROM customer
      the catalog's own relation, from its postgresql.table distribution:
      https://example.internal/api/table/crm_customer_master
    crm-event            s3://analytics/events/crm            -> FROM crm
    sales-order          postgresql://analytics.dw/sales      -> FROM sales
    semantic-glossary    sparql://semantic.graph/customer-intelligence
                                              -> FROM customer_intelligence
    marketing-campaign   https://api.example.internal/marketing/campaigns
                                              -> FROM campaigns

For a libpq URI that segment is the **database** name; for the other three the
source is not relational at all and the segment is an object prefix, a named
graph and a REST path. So **no** draft named a relation that exists, and a buyer
who pasted one into their warehouse got ``relation "customer" does not exist``.

Two designs were tried. Refusing to draft for a non-relational source was
written first and reverted: eleven tests in four files enumerate every dataset
and expect a draft, including ``test_latency_budget_measurement.py``, which uses
this route as traffic infrastructure for latency sampling. Removing a surface
other measurements stand on is a bigger change than the defect, and the defect
is the **false claim**, not the draft's existence. So the response labels itself
at the point of delivery - the same choice made for ``/graph/stats``'s
instance-wide counts and for the mock executor's provenance fields.

``executable_against_source`` was ``False`` for **every** dataset when this
file was written, including the two SQL ones, because that was true of every
dataset then. **That repair has since landed** - the drafter resolves the
relation from the catalog's declared ``postgresql.table`` distribution and
``validate_sql_query``'s allow-list is built from the same resolution - so
``crm-customer-master`` and ``sales-order`` now name a real relation and say
they are executable. ``tests/test_draft_names_the_declared_relation.py`` owns
that half.

What is left here is the half that is still true, and it is not a leftover: the
other three datasets declare ``parquet``, ``sparql.graph`` and ``rest.json``,
have no relation to name, and must keep saying so. Flipping all five would have
been the same over-claim in a new place. The file's docstring predicted this
change and the expectations moved with it rather than being deleted.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sdp.api import app  # noqa: E402
from sdp.catalog import get_dataset, list_datasets  # noqa: E402
from sdp.orchestrator import _source_table_name  # noqa: E402
from sdp_core.demo_seed import classify_source_type  # noqa: E402


client = TestClient(app)

# Measured at 9cf278e. Asserted rather than assumed, so a reseed that changes a
# source kind fails here instead of silently widening the claim.
EXPECTED_KINDS = {
    "crm-customer-master": "sql",
    "crm-event": "file_lake",
    "sales-order": "sql",
    "semantic-glossary": "rdf",
    "marketing-campaign": "api",
}


# The three datasets that declare no relation. Derived from ``EXPECTED_KINDS``
# rather than listed again: a source kind other than ``sql`` cannot have a
# ``postgresql.table`` distribution, and the relational pair's own expectations
# live in ``tests/test_draft_names_the_declared_relation.py``.
NON_RELATIONAL = {
    dataset_id: kind for dataset_id, kind in EXPECTED_KINDS.items() if kind != "sql"
}


def _draft(dataset_id: str) -> dict:
    """One draft, with the fields this route requires."""
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


def test_the_seed_catalogue_still_mixes_relational_and_non_relational() -> None:
    """The premise: three of five sources are not relational at all."""
    measured = {
        dataset.id: classify_source_type(dataset.source_system)
        for dataset in list_datasets()
        if dataset.id in EXPECTED_KINDS
    }
    assert measured == EXPECTED_KINDS, measured
    assert sum(1 for kind in measured.values() if kind != "sql") == 3, measured


@pytest.mark.parametrize("dataset_id", sorted(EXPECTED_KINDS))
def test_every_draft_publishes_its_source_kind(dataset_id: str) -> None:
    """A reader cannot judge the SQL without knowing what it is aimed at."""
    body = _draft(dataset_id)
    assert body["source_kind"] == EXPECTED_KINDS[dataset_id], body["source_kind"]


@pytest.mark.parametrize("dataset_id", sorted(NON_RELATIONAL))
def test_a_source_with_no_relation_does_not_claim_to_be_executable(
    dataset_id: str,
) -> None:
    """An object prefix, a named graph and a REST path are not relations.

    The relational two are covered by
    ``tests/test_draft_names_the_declared_relation.py``; these three have
    nothing for the catalog to declare, so the response has to be the place that
    says the name was derived.
    """
    body = _draft(dataset_id)
    assert body["executable_against_source"] is False, body

    # Two separate properties, because the caveat has to do two jobs and a bare
    # ``"relation" in caveat`` is satisfied by either sentence on its own.
    caveat = body["execution_caveat"]
    assert EXPECTED_KINDS[dataset_id] in caveat, caveat
    assert "locator" in caveat, f"the caveat does not say where the name came from: {caveat}"
    assert "distribution" in caveat, (
        f"the caveat does not say what the catalog would have to declare: {caveat}"
    )


@pytest.mark.parametrize("dataset_id", sorted(EXPECTED_KINDS))
def test_no_draft_claims_the_catalog_verified_its_table(dataset_id: str) -> None:
    """The sentence that was false for all five is gone, for all five.

    "검증된" is a claim about *validation* the catalog never performed, and it
    stays absent whether or not the dataset declares a relation - a declared
    relation is a declaration, not a verification that it exists on the target
    system. The columns half is catalog-backed for every dataset and is asserted
    with it, so a reader can tell which half is which.
    """
    assumptions = " ".join(_draft(dataset_id)["assumptions"])
    assert "검증된 테이블" not in assumptions, (
        f"the table-verification claim survives: {assumptions}"
    )
    assert "컬럼은 카탈로그 선언에서" in assumptions, assumptions


@pytest.mark.parametrize("dataset_id", sorted(NON_RELATIONAL))
def test_an_undeclared_table_name_says_where_it_came_from(dataset_id: str) -> None:
    """The three with no declared relation name their derivation in the open."""
    assumptions = " ".join(_draft(dataset_id)["assumptions"])
    assert "source_system" in assumptions, assumptions


@pytest.mark.parametrize("dataset_id", sorted(NON_RELATIONAL))
def test_an_undeclared_table_name_is_the_locator_segment(
    dataset_id: str,
) -> None:
    """The measurement behind the caveat, for the datasets it still describes.

    These three declare no relation, so there is nothing else the name could
    come from. If one of them gains a ``postgresql.table`` distribution, this
    fails and is the right place to notice - ``NON_RELATIONAL`` and the
    executability expectation would both move in the same breath.
    """
    dataset = get_dataset(dataset_id)
    body = _draft(dataset_id)
    emitted = _source_table_name(dataset.source_system)
    assert f"FROM {emitted}" in body["query"], body["query"]

    declared_relations = [
        str(dist.endpoint).rstrip("/").rsplit("/", 1)[-1]
        for dist in dataset.distributions
        if str(dist.format).endswith(".table")
    ]
    if declared_relations:
        assert False, (
            f"{dataset_id} now declares a relation ({declared_relations}); it "
            "belongs with the relational datasets, not here"
        )


def test_the_summary_surface_reports_the_shared_classification() -> None:
    """``buyer_demo_dataset_summaries`` classified the source inline.

    It now calls the extracted rule, so the kind a buyer reads in the demo plan
    and the kind the draft publishes are the same answer. This half only pins
    the summary side; the drafter side is two tests below, because agreement
    alone cannot tell a shared derivation from a copy that happens to match.
    """
    from sdp_core.demo_seed import buyer_demo_dataset_summaries

    for summary in buyer_demo_dataset_summaries():
        dataset = get_dataset(summary.id)
        assert summary.source_type == classify_source_type(dataset.source_system), (
            f"{summary.id}: summary says {summary.source_type}, the shared "
            f"classifier says {classify_source_type(dataset.source_system)}"
        )


def test_the_drafter_holds_the_shared_rule_not_its_own() -> None:
    """Structural: the drafter's name resolves to the extracted function.

    A copy pasted into ``orchestrator.py`` under this name reddens here.
    """
    from sdp import orchestrator
    from sdp_core import demo_seed

    assert orchestrator.classify_source_type is demo_seed.classify_source_type


def test_the_published_kind_is_the_shared_rules_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Behavioural: the response follows that function, so it is not recomputed.

    The structural check above cannot see a copy under a *different* name with
    the import left unused. Replacing the drafter's binding and watching the
    response move does: a drafter deriving its own kind would ignore this.
    """
    monkeypatch.setattr(
        "sdp.orchestrator.classify_source_type", lambda _source: "sentinel_kind"
    )
    body = _draft("crm-customer-master")
    assert body["source_kind"] == "sentinel_kind", body["source_kind"]
    assert "sentinel_kind" in body["execution_caveat"], body["execution_caveat"]
