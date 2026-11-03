"""A clean dataset's draft was refused as a governance violation over a name.

Measured at ``dba2403`` on two probe datasets that differ only in the last path
segment of ``source_system``::

    s3://analytics/events/2024    GET /validate -> is_valid=true missing=[]
                                  POST /policy/decision -> effect=allow
                                  POST /llm/draft-query -> 400
                                    draft_rejected_by_validator
                                    "... SQL 안전성 게이트를 통과하지 못했습니다:
                                     unauthorized_table_reference"
    s3://analytics/events/orders  POST /llm/draft-query -> 200
                                    SELECT count(*) ... FROM orders ...

Nothing was unauthorized. The dataset is the caller's own tenant, published, and
``POST /policy/decision`` answers ``allow`` for the same subject, resource and
action; the only table the statement names is the one the product itself derived
from the dataset's own ``source_system``. The mechanism::

    _source_table_name('s3://analytics/events/2024')      -> '2024'
    _reads_back_as_one_table('2024')                      -> False
    _referenced_source_tables('select 1 from 2024')       -> None
    validate_sql_query(...)  -> ['unauthorized_table_reference']

A leading digit is not a SQL identifier, so the allow-list's parser finds no
table reference at all and the validator reports the one warning it has for "no
authorized table was named". The refusal therefore stated a false cause, and an
unactionable one: it named neither the derived table, nor the locator it came
from, nor the remedy (declare a ``postgresql.table`` distribution whose name is
an identifier). Date-partitioned lake prefixes are the ordinary shape of this.

This is the second instance of one class. The first - a source table that *is* an
identifier but collides with a SQL clause keyword (``FROM order``) - was repaired
by refusing with a true cause, ``unquotable_source_table``, and is pinned by
``tests/test_orchestrator.py::test_a_clause_keyword_source_table_refuses_instead_of_drafting``.
That repair enumerated the 24 clause keywords; this one asks the production
parser whether the emitted name reads back, which covers both and anything else
that is not an identifier.
"""

from __future__ import annotations

from typing import Any

import pytest

from fastapi.testclient import TestClient

from sdp import orchestrator
from sdp.api import app


client = TestClient(app)

# Last path segments that are not SQL identifiers, with the derived table name
# each produces. All five are shapes a data lake really uses.
NON_IDENTIFIER_TAILS = (
    ("2024", "2024"),
    ("2024_q1", "2024_q1"),
    ("3rd-party", "3rd_party"),
    ("2026-10", "2026_10"),
    ("1h", "1h"),
)


def _publish(dataset_id: str, source_system: str) -> None:
    """Register and publish one probe dataset with no declared relation."""
    body: dict[str, Any] = {
        "id": dataset_id,
        "tenant_id": "demo",
        "title": f"프로브 {dataset_id}",
        "description": "파생 테이블 이름 측정을 위한 프로브 데이터셋",
        "owner": "data-admin",
        "steward": "data-admin",
        "domain": "고객",
        "source_system": source_system,
        "sensitivity": "low",
        "update_frequency": "daily",
        "quality_score": 0.9,
        "freshness_score": 0.9,
        "schema": [
            {"name": "customer_id", "datatype": "string", "nullable_ratio": 0.0, "distinct_ratio": 1.0},
            {"name": "event_timestamp", "datatype": "timestamp", "nullable_ratio": 0.0, "distinct_ratio": 0.9},
        ],
        # ``format: csv`` on purpose: a ``postgresql.table`` distribution is the
        # remedy the refusal must name, so the probe must not already have one.
        "distributions": [
            {
                "id": f"{dataset_id}-csv",
                "format": "csv",
                "endpoint": "https://files.example.internal/probe.csv",
            }
        ],
        "actor": "data-admin",
        "reason": "probe",
    }
    created = client.post("/catalog/datasets", json=body)
    assert created.status_code == 200, created.text
    published = client.post(
        f"/catalog/datasets/{dataset_id}/publish", json={"actor": "data-admin", "reason": "probe"}
    )
    assert published.status_code == 200, published.text


def _draft(dataset_id: str):
    return client.post(
        "/llm/draft-query",
        json={
            "user": "analyst",
            "dataset_id": dataset_id,
            "question": "최근 고객 수",
            "purpose": "analysis",
        },
    )


@pytest.mark.parametrize("tail,derived", NON_IDENTIFIER_TAILS)
def test_the_refusal_does_not_call_a_naming_problem_an_authorization_one(
    tail: str, derived: str
) -> None:
    """The cause has to be true before it can be actionable."""
    dataset_id = f"name-probe-{derived}"
    _publish(dataset_id, f"s3://analytics/events/{tail}")

    # The premises the buyer can check, and did: nothing here is unauthorized.
    validated = client.get(f"/catalog/datasets/{dataset_id}/validate?user=data-admin").json()
    assert validated["is_valid"] is True, validated
    allowed = client.post(
        "/policy/decision",
        json={
            "user": "data-admin",
            "subject": "analyst",
            "resource": dataset_id,
            "action": "query",
            "purpose": "analysis",
        },
    ).json()
    assert allowed["effect"] == "allow", allowed

    response = _draft(dataset_id)
    assert response.status_code == 400, response.text
    detail = response.json()["detail"]
    assert "unauthorized" not in detail["error"], detail
    assert "unauthorized" not in detail["reason"], detail
    assert detail.get("warnings", []) == [] or "unauthorized_table_reference" not in detail.get(
        "warnings", []
    ), detail


@pytest.mark.parametrize("tail,derived", NON_IDENTIFIER_TAILS)
def test_the_refusal_names_the_derived_name_the_locator_and_the_remedy(
    tail: str, derived: str
) -> None:
    """Actionable means the buyer can act without reading the source."""
    dataset_id = f"name-probe-{derived}"
    _publish(dataset_id, f"s3://analytics/events/{tail}")
    detail = _draft(dataset_id).json()["detail"]
    reason = detail["reason"]

    assert derived in reason, (derived, reason)
    assert tail in reason, (tail, reason)
    assert orchestrator.DRAFT_SQL_DIALECT in reason, reason
    assert "table" in reason, reason


def test_the_refusal_names_the_locator_without_its_credential() -> None:
    """The message quotes ``source_system``, which is the one field every read
    surface withholds because it carries the connection credential."""
    secret = "SUPERSEKRET123"
    dataset_id = "name-probe-credential"
    _publish(dataset_id, f"postgresql://dsnuser:{secret}@analytics.dw:5432/2024")
    response = _draft(dataset_id)
    assert response.status_code == 400, response.text
    assert secret not in response.text, "the refusal echoed the DSN credential"
    assert "analytics.dw:5432/2024" in response.json()["detail"]["reason"], response.text


def test_an_identifier_shaped_tail_still_drafts() -> None:
    """The control: the repair refuses a name, not a dataset shape."""
    _publish("name-probe-ok", "s3://analytics/events/orders")
    response = _draft("name-probe-ok")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["source_table"] == "orders", body
    assert " FROM orders " in body["query"], body["query"]


def test_declaring_the_relation_is_a_remedy_that_works() -> None:
    """The refusal points at a distribution, so that distribution must fix it.

    A refusal naming a remedy that does not work is the same defect one layer
    out, and this is the assertion that keeps the message honest.
    """
    dataset_id = "name-probe-remedy"
    _publish(dataset_id, "s3://analytics/events/2024")
    assert _draft(dataset_id).status_code == 400

    patched = client.patch(
        f"/catalog/datasets/{dataset_id}",
        json={
            "actor": "data-admin",
            "reason": "relation 선언",
            "distributions": [
                {
                    "id": f"{dataset_id}-table",
                    "format": f"{orchestrator.DRAFT_SQL_DIALECT}.table",
                    "endpoint": "https://warehouse.example.internal/api/table/events_2024",
                }
            ],
        },
    )
    assert patched.status_code == 200, patched.text

    drafted = _draft(dataset_id)
    assert drafted.status_code == 200, drafted.text
    assert drafted.json()["source_table"] == "events_2024", drafted.json()


def test_the_predicate_is_the_parser_not_a_second_identifier_rule() -> None:
    """Whether the name reads back is asked of the allow-list's own parser.

    A re-derived identifier rule here would be a second opinion that can drift
    from the one the gate enforces, which is how the false refusal arose: the
    drafter believed it had emitted a table and the parser disagreed.
    """
    for _tail, derived in NON_IDENTIFIER_TAILS:
        assert orchestrator._reads_back_as_one_table(derived) is False, derived
        # Not "the parser finds nothing": for ``2024_q1`` it finds ``_q1``, a
        # *different* table than the one written, because the tokeniser starts a
        # token at the first identifier character. Asserting ``None`` here was
        # wrong about three of the five shapes, which is the reason the predicate
        # is "reads back as this table" and not "parses to something".
        read_back = orchestrator._referenced_source_tables(f"select 1 from {derived}")
        assert read_back != [derived], (derived, read_back)
    assert orchestrator._reads_back_as_one_table("orders") is True
    assert orchestrator._referenced_source_tables("select 1 from 2024_q1") == ["_q1"]
