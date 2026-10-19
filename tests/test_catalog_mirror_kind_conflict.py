"""A catalog write whose graph mirror would reclassify a node is refused, not half-applied.

``seed_dataset`` mirrors a dataset as a ``dataset`` node and each declared column
as ``{dataset_id}:{column}``, a ``column`` node, and
``assert_node_kind_is_stable`` refuses either write if that id already exists as
something else. Both catalog routes mirrored **after** writing the catalog row,
so the refusal arrived too late. Found by adversarial review of the hierarchy
commits, while enumerating every path that can change a node's kind; both paths
date from the commit that introduced the kind rule itself, not from the
hierarchy work.

Measured before this change, each one authorized request::

    POST /catalog/datasets {"id": "고객", ...}          (고객 is a seeded concept)
        -> 500
           catalog row created:            True
           GET /catalog/datasets/고객:      200
           graph node kind:                concept  (no dataset node, ever)
           a later seed_store(fresh store): ValueError

    PATCH /catalog/datasets/{id} declaring a column whose node id a concept holds
        -> 400 {"error": "invalid_request", "reason": "request body is not valid"}
           catalog title:  '충돌검사셋 제목' -> '바뀐 제목'      (applied)
           catalog schema: []              -> ['컬럼']        (applied)

The first one is the worse of the two: one request leaves the process unable to
seed a graph store ever again, because ``seed_store`` loops over every catalog
row and raises on that one. The second tells the caller their body was invalid
while the catalog kept both changes.

Both now answer **409** - the status the structurally identical conflict already
answers on ``POST /graph/nodes`` and ``POST /ontology/concepts`` - and write
nothing. The check is asked before the catalog row is touched, and lives next to
``seed_dataset`` so it enumerates the same node ids that function writes.

Reverse-verified: removing the ``assert_dataset_mirror_kinds_are_available`` call
from the create route restores the 500 with the row created and breaks
``seed_store``; removing it from the patch route restores the 400 with the
mutation applied.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from sdp import catalog, graph_store
from sdp.api import app
from sdp.graph_store import InMemoryGraphStore, NodeKindConflict
from sdp.seed import assert_dataset_mirror_kinds_are_available, seed_store


client = TestClient(app, raise_server_exceptions=False)

ADMIN = {"actor": "admin"}
SEEDED_CONCEPT = "고객"


def _payload(dataset_id: str, columns: tuple[str, ...] = ()) -> dict:
    """A create payload the request model accepts."""
    return {
        **ADMIN,
        "id": dataset_id,
        "title": f"{dataset_id} 제목",
        "description": "kind 충돌 검사용 데이터셋",
        "owner": "data-platform",
        "steward": "qa",
        "domain": "테스트",
        "source_system": "postgresql://analytics.dw/t",
        "sensitivity": "low",
        "update_frequency": "daily",
        "quality_score": 0.9,
        "freshness_score": 0.9,
        "tags": ["테스트"],
        "terms": ["테스트"],
        "related_datasets": [],
        "schema": [
            {
                "name": column,
                "datatype": "string",
                "nullable_ratio": 0.0,
                "distinct_ratio": 0.5,
                "pii": False,
            }
            for column in columns
        ],
        "distributions": [
            {
                "id": f"dist-{dataset_id}",
                "format": "postgresql.table",
                "endpoint": "https://example.internal/api/table/t",
            }
        ],
        "mappings": [],
    }


# ------------------------------------------------------------- the create path --


def test_a_dataset_id_a_concept_node_holds_is_refused_with_nothing_written() -> None:
    """Measured at 500 with the row created and seeding permanently broken."""
    response = client.post("/catalog/datasets", json=_payload(SEEDED_CONCEPT))
    assert response.status_code == 409
    assert "kind" in response.json()["detail"]
    assert SEEDED_CONCEPT not in catalog._DATA
    assert (
        client.get(f"/catalog/datasets/{SEEDED_CONCEPT}", params={"user": "admin"}).status_code
        == 404
    )
    # The node the caller tried to take over is untouched...
    node = graph_store.get_store().get_node(SEEDED_CONCEPT)
    assert node is not None and node.kind == "concept"
    # ...and the process can still seed a fresh store, which is what the 500 path
    # broke for good.
    seed_store(InMemoryGraphStore())


def test_a_declared_column_whose_node_id_a_concept_holds_is_refused_too() -> None:
    """The column half of the same rule, on the create path."""
    assert (
        client.post(
            "/ontology/concepts",
            json={**ADMIN, "concept": "컬럼충돌데이터셋:이름컬럼", "definition": "정의"},
        ).status_code
        == 200
    )
    response = client.post(
        "/catalog/datasets", json=_payload("컬럼충돌데이터셋", ("이름컬럼",))
    )
    assert response.status_code == 409
    assert "컬럼충돌데이터셋:이름컬럼" in response.json()["detail"]
    assert "컬럼충돌데이터셋" not in catalog._DATA


def test_an_ordinary_create_still_succeeds() -> None:
    """The rule refuses exactly the reclassification and nothing legitimate."""
    assert (
        client.post("/catalog/datasets", json=_payload("정상데이터셋", ("정상컬럼",))).status_code
        == 200
    )
    node = graph_store.get_store().get_node("정상데이터셋")
    assert node is not None and node.kind == "dataset"
    column = graph_store.get_store().get_node("정상데이터셋:정상컬럼")
    assert column is not None and column.kind == "column"


# -------------------------------------------------------------- the patch path --


def test_a_patch_whose_column_collides_is_refused_before_the_mutation() -> None:
    """Measured at 400 "request body is not valid" *after* the catalog applied
    both the title and the schema change."""
    assert client.post("/catalog/datasets", json=_payload("패치충돌셋")).status_code == 200
    assert (
        client.post(
            "/ontology/concepts",
            json={**ADMIN, "concept": "패치충돌셋:충돌컬럼", "definition": "정의"},
        ).status_code
        == 200
    )
    before_title = catalog._DATA["패치충돌셋"].title
    response = client.patch(
        "/catalog/datasets/패치충돌셋",
        json={
            **ADMIN,
            "title": "바뀐 제목",
            "schema": [
                {
                    "name": "충돌컬럼",
                    "datatype": "string",
                    "nullable_ratio": 0.0,
                    "distinct_ratio": 0.5,
                    "pii": False,
                }
            ],
        },
    )
    assert response.status_code == 409
    assert "패치충돌셋:충돌컬럼" in response.json()["detail"]
    # Neither half of the patch was applied.
    assert catalog._DATA["패치충돌셋"].title == before_title
    assert [column.name for column in catalog._DATA["패치충돌셋"].schema] == []


def test_a_malformed_patch_body_is_still_400_not_409() -> None:
    """The new arm is ordered before the blanket one, so it must not swallow a
    body-validation failure - which is a ``pydantic.ValidationError``, not a
    ``ValueError`` here."""
    assert client.post("/catalog/datasets", json=_payload("본문검사셋")).status_code == 200
    response = client.patch(
        "/catalog/datasets/본문검사셋",
        json={**ADMIN, "quality_score": "숫자가 아님"},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "invalid_request"


def test_an_ordinary_patch_still_succeeds() -> None:
    """Including one that declares a column, which is the mirrored write."""
    assert client.post("/catalog/datasets", json=_payload("정상패치셋")).status_code == 200
    response = client.patch(
        "/catalog/datasets/정상패치셋",
        json={
            **ADMIN,
            "title": "새 제목",
            "schema": [
                {
                    "name": "새컬럼",
                    "datatype": "string",
                    "nullable_ratio": 0.0,
                    "distinct_ratio": 0.5,
                    "pii": False,
                }
            ],
        },
    )
    assert response.status_code == 200
    assert catalog._DATA["정상패치셋"].title == "새 제목"
    column = graph_store.get_store().get_node("정상패치셋:새컬럼")
    assert column is not None and column.kind == "column"


# ------------------------------------------------------------------- the check --


def test_the_check_enumerates_the_same_node_ids_the_mirror_writes() -> None:
    """A private store, so this is about the rule rather than about the routes."""
    store = InMemoryGraphStore()
    store.upsert_node("예약된개념", "concept")
    store.upsert_node("예약된데이터셋:예약된컬럼", "concept")
    with pytest.raises(NodeKindConflict, match="kind"):
        assert_dataset_mirror_kinds_are_available("예약된개념", (), store=store)
    with pytest.raises(NodeKindConflict, match="kind"):
        assert_dataset_mirror_kinds_are_available(
            "예약된데이터셋", ("예약된컬럼",), store=store
        )
    # A ``ValueError`` subclass, so every handler that already caught one still
    # does - and precise enough that a route can tell it from a malformed body.
    assert issubclass(NodeKindConflict, ValueError)
    # Nothing refused where nothing collides.
    assert_dataset_mirror_kinds_are_available("새데이터셋", ("새컬럼",), store=store)


def test_the_refusal_is_audited_with_its_own_reason() -> None:
    """The governance invariant is a decision **and** an audit row for every
    catalog mutation, including a refused one - and the row must not carry the
    allow-reason of the decision that permitted it."""
    before = len(catalog.list_audit_events())
    response = client.post("/catalog/datasets", json=_payload(SEEDED_CONCEPT))
    assert response.status_code == 409
    rows = catalog.list_audit_events()
    assert len(rows) == before + 1
    recorded = rows[-1]
    assert recorded.result == "denied"
    # The row carries the integrity reason, not the allow-reason of the decision
    # that permitted the mutation - which would read as the opposite of what
    # happened.
    assert "kind" in recorded.reason
