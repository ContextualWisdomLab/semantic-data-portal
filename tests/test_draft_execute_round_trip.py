"""The documented two-step workflow: draft a query, then execute it.

The repository shipped a drafter (``POST /llm/draft-query``) and an executor
(``POST /browse/query``) and no test that fed one into the other, so the pair was
broken for every dataset while the suite stayed green. Measured before the
repair:

    POST /llm/draft-query  (crm-customer-master) -> 200
      SELECT count(*) AS active_customer_count FROM customer
      WHERE created_at >= current_date - interval '90 day'  LIMIT 1000
    validate_sql_query(that SQL)                 -> ['literal_values_not_allowed']
    POST /browse/query     (that SQL)            -> 400 REJECTED

Two independent defects in one predicate:

* ``interval '90 day'`` is a single-quoted literal, and this module's own
  validator refuses any statement containing a quote. Every draft was therefore
  unexecutable - the workflow had no path through it.
* ``created_at`` was hard-coded. Not one seeded dataset declares that column:
  ``crm-customer-master`` has ``signup_at``, ``crm-event`` has
  ``event_timestamp``, and ``sales-order``, ``semantic-glossary`` and
  ``marketing-campaign`` declare no temporal column at all. So the predicate
  filtered on a phantom column while the same response claimed to use
  "카탈로그에서 검증된 테이블/컬럼만" - a claim since removed from the response,
  because the table half of it was false for every dataset too
  (``tests/test_draft_source_kind.py``).

The datasets are enumerated from the catalog rather than listed, so a seed whose
schema shape differs is covered without anyone remembering to add it.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from sdp import catalog
from sdp.api import app
from sdp.orchestrator import (
    _temporal_column,
    source_relation_name,
    validate_sql_query,
)


client = TestClient(app)


def _draftable_datasets() -> list:
    """Published datasets with a schema - the drafter's own preconditions."""
    return [
        dataset
        for dataset in catalog.list_datasets(None)
        if dataset.status == "published" and dataset.schema
    ]


def test_every_drafted_query_passes_the_validator_and_executes() -> None:
    """A draft the executor refuses is not a draft."""
    datasets = _draftable_datasets()
    assert datasets, "the seed must contain at least one draftable dataset"

    failures = []
    for dataset in datasets:
        drafted = client.post(
            "/llm/draft-query",
            json={
                "user": "admin",
                "dataset_id": dataset.id,
                "question": "월별 추이를 보여줘",
                "purpose": "analysis",
            },
        )
        assert drafted.status_code == 200, drafted.text
        body = drafted.json()
        assert "query" in body, f"{dataset.id}: {body}"
        sql = body["query"]

        # Validated the way the product validates it. The drafter now names
        # the relation the catalog declares, and the allow-list is built from
        # the same resolution - calling this without the declared relation
        # exercises the fuzz harness's fallback, not the governed path, and
        # would refuse the statement the product itself accepts.
        warnings = validate_sql_query(
            sql,
            source_system=dataset.source_system,
            declared_relation=source_relation_name(dataset),
        )
        if warnings:
            failures.append((dataset.id, "validator", warnings, sql))
            continue

        executed = client.post(
            "/browse/query",
            json={
                "user": "admin",
                "dataset_ids": [dataset.id],
                "language": "SQL",
                "query": sql,
                "purpose": "analysis",
            },
        )
        if executed.status_code != 200:
            detail = executed.json().get("detail", executed.json())
            failures.append((dataset.id, "executor", detail.get("warnings"), sql))

    assert not failures, "drafted SQL was refused downstream:\n" + "\n".join(
        f"  {dataset_id} rejected by {stage}: {reported}\n    {sql}"
        for dataset_id, stage, reported, sql in failures
    )


def test_the_window_predicate_names_a_column_the_dataset_declares() -> None:
    """Filtering on a column the dataset does not have is not a valid draft."""
    for dataset in _draftable_datasets():
        declared = {column.name for column in dataset.schema}
        body = client.post(
            "/llm/draft-query",
            json={
                "user": "admin",
                "dataset_id": dataset.id,
                "question": "월별 추이를 보여줘",
                "purpose": "analysis",
            },
        ).json()

        expected_column = _temporal_column(dataset)
        assert body["date_window_column"] == expected_column, dataset.id
        assert body["date_window_applied"] is (expected_column is not None), dataset.id

        if expected_column is None:
            # No temporal column: no predicate, and the response says so rather
            # than letting the caller assume its date_window_days was honored.
            assert "WHERE" not in body["query"], f"{dataset.id}: {body['query']}"
            assert body["date_window_days"] == 0
            assert any("기간 필터를 적용하지 않았습니다" in line for line in body["assumptions"])
        else:
            assert expected_column in declared
            assert f"WHERE {expected_column} >=" in body["query"], body["query"]
            assert "created_at" not in body["query"] or "created_at" in declared
            assert any(expected_column in line for line in body["assumptions"])


def test_no_drafted_query_contains_a_quoted_literal() -> None:
    """The guard that made every draft unexecutable, pinned directly.

    ``literal_values_not_allowed`` is a real injection guard and must stay. The
    drafter is what had to change, so this asserts the emitted statement never
    needs the guard relaxed.
    """
    for dataset in _draftable_datasets():
        for window in (1, 90, 365):
            sql = client.post(
                "/llm/draft-query",
                json={
                    "user": "admin",
                    "dataset_id": dataset.id,
                    "question": "추이",
                    "purpose": "analysis",
                    "date_window_days": window,
                },
            ).json()["query"]
            assert "'" not in sql, f"{dataset.id} window={window}: {sql}"
            assert '"' not in sql, f"{dataset.id} window={window}: {sql}"
            assert "  " not in sql, f"double space in emitted SQL: {sql!r}"


def test_a_group_by_draft_also_round_trips() -> None:
    """The grouped branch assembles a different statement, so it is exercised too."""
    dataset = next(
        dataset
        for dataset in _draftable_datasets()
        if _temporal_column(dataset) is not None
    )
    group_column = _temporal_column(dataset)
    body = client.post(
        "/llm/draft-query",
        json={
            "user": "admin",
            "dataset_id": dataset.id,
            "question": "월별 추이",
            "purpose": "analysis",
            "group_by": group_column,
        },
    ).json()
    sql = body["query"]
    assert f"GROUP BY {group_column}" in sql, sql
    assert (
        validate_sql_query(
            sql,
            source_system=dataset.source_system,
            declared_relation=source_relation_name(dataset),
        )
        == []
    )

    executed = client.post(
        "/browse/query",
        json={
            "user": "admin",
            "dataset_ids": [dataset.id],
            "language": "SQL",
            "query": sql,
            "purpose": "analysis",
        },
    )
    assert executed.status_code == 200, executed.text
