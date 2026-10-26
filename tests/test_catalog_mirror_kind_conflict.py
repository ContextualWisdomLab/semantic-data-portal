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
from sdp.seed import assert_dataset_mirror_kinds_are_available, seed_dataset, seed_store


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


def test_the_check_asks_about_every_node_the_mirror_actually_writes() -> None:
    """Completeness, which the test above only claims in its name.

    That one proves the two known id shapes are refused; it would go on passing
    if ``seed_dataset`` grew a third kind of node write and the guard stopped
    covering it - and a node write the guard does not know about is exactly the
    defect this whole control exists to prevent, rediscovered four times in two
    rounds of review. So: mirror a dataset carrying columns, terms, mappings,
    lineage on both sides and a related dataset into a private store, and
    require the set of node ids the guard asks about to be the set the mirror
    created. Edges are not node writes - ``upsert_edge`` appends without
    creating its endpoints - so a term or lineage counterpart is deliberately
    not in either set.
    """
    dataset_id = "열거검사셋"
    payload = _payload(dataset_id, ("첫컬럼", "둘째컬럼"))
    payload["terms"] = ["어떤용어"]
    payload["lineage_inputs"] = ["상류셋"]
    payload["lineage_outputs"] = ["하류셋"]
    payload["related_datasets"] = ["옆집셋"]
    assert client.post("/catalog/datasets", json=payload).status_code == 200
    dataset = catalog.get_dataset(dataset_id)
    assert dataset is not None

    mirror_store = InMemoryGraphStore()
    seed_dataset(dataset, store=mirror_store)
    # ``_nodes`` directly: the store publishes counts (``stats``) but no node
    # enumeration, and adding a product API for a test is out of scope - the
    # same reason ``catalog._DATA`` is read directly elsewhere in this file.
    written = set(mirror_store._nodes)

    class _RecordingStore(InMemoryGraphStore):
        """Records which node ids the guard asks about."""

        def __init__(self) -> None:
            super().__init__()
            self.asked: list[str] = []

        def assert_node_kind_is_stable(self, node_id: str, kind: str) -> None:
            """Record the question instead of answering it."""
            self.asked.append(node_id)

    recorder = _RecordingStore()
    assert_dataset_mirror_kinds_are_available(
        dataset_id, [column.name for column in dataset.schema or []], store=recorder
    )
    assert set(recorder.asked) == written
    assert written == {dataset_id, f"{dataset_id}:첫컬럼", f"{dataset_id}:둘째컬럼"}


def test_the_refusal_is_audited_with_its_own_reason() -> None:
    """The governance invariant is a decision **and** an audit row for every
    catalog mutation, including a refused one - and the row must not carry the
    allow-reason of the decision that permitted it."""
    before = len(catalog.list_audit_events())
    response = client.post("/catalog/datasets", json=_payload(SEEDED_CONCEPT))
    assert response.status_code == 409
    rows = catalog.list_audit_events()
    assert len(rows) == before + 1
    # ``list_audit_events`` sorts **newest first** and returns one page, so the
    # new row is ``rows[0]``. Read as ``rows[-1]`` this assertion passed only
    # because the restored baseline happens to leave the log empty, making the
    # page one row long; it would have gone on passing against the oldest row of
    # the page the moment it was not.
    recorded = rows[0]
    assert recorded.resource == SEEDED_CONCEPT
    assert recorded.result == "denied"
    # The row carries the integrity reason, not the allow-reason of the decision
    # that permitted the mutation - which would read as the opposite of what
    # happened.
    assert "kind" in recorded.reason


# --------------------------------------- the id the catalog assigns itself --


def test_a_create_without_an_id_checks_the_id_the_catalog_will_assign() -> None:
    """The hole the first version of this guard left wide open.

    ``POST /catalog/datasets`` may omit ``id``; the catalog then assigns the
    first free ``dataset-NNN``. The guard was called from the route against
    ``request.id`` - ``None`` for exactly those requests - so it asked whether a
    node named ``None`` existed, got no, and the 500 with the row created and
    ``seed_store`` permanently broken came back for every request that let the
    catalog name the dataset. It is now the registrar's ``before_commit`` hook,
    which runs after the id is resolved and before the first write.

    The graph store singleton is deliberately outside ``conftest``'s restore
    fixture (it has no snapshot API), so this test both cleans up after itself
    and refuses to depend on what ran before it - it was written doing neither
    and failed both ways. Leaving the parked concept behind made three tests in
    ``test_change_reason_evidence`` answer this 409 while this file passed on
    its own; assuming the id was free in the graph made the test itself fail in
    reverse and one shuffled file order, because an earlier no-id registration
    had left a ``dataset`` node there and parking a concept on it is exactly
    what the rule under test refuses. Whatever sits at that id is an orphan -
    ``catalog._DATA`` is restored per test, so no catalog row claims it - so it
    is removed first and the id is left empty afterwards.
    """
    generated = catalog._next_generated_dataset_id()
    graph_store.get_store().delete_node(generated)
    assert (
        client.post(
            "/ontology/concepts",
            json={**ADMIN, "concept": generated, "definition": "정의"},
        ).status_code
        == 200
    )
    try:
        payload = _payload("무시되는값")
        del payload["id"]
        response = client.post("/catalog/datasets", json=payload)
        assert response.status_code == 409
        assert generated in response.json()["detail"]
        assert generated not in catalog._DATA
        # The id is still free.
        assert catalog._next_generated_dataset_id() == generated
        seed_store(InMemoryGraphStore())
    finally:
        graph_store.get_store().delete_node(generated)
    # With the id free again the very request the guard refused succeeds and
    # takes it - which is both the cleanup check and the proof that the guard
    # refuses the collision rather than no-id registration itself.
    payload = _payload("무시되는값")
    del payload["id"]
    assert client.post("/catalog/datasets", json=payload).status_code == 200
    assert catalog.get_dataset(generated) is not None
    graph_store.get_store().delete_node(generated)


def test_a_duplicate_dataset_id_is_a_conflict_not_a_crash() -> None:
    """``_register_dataset_locked`` raised a bare ``ValueError`` no route caught,
    so registering an id the catalog already holds answered **500** (measured).
    It is the same refusal as the kind conflict - the id is taken - and now the
    same status."""
    assert client.post("/catalog/datasets", json=_payload("중복아이디셋")).status_code == 200
    response = client.post("/catalog/datasets", json=_payload("중복아이디셋"))
    assert response.status_code == 409
    assert "exists" in response.json()["detail"]
    assert isinstance(catalog.DatasetAlreadyExists("x"), ValueError)


# ------------------------------- the two status verbs, which carry no schema --


def _drift_the_dataset_node_into_a_concept(dataset_id: str) -> None:
    """Put the store in the state the four mutations have to survive.

    The catalog holds the row; the graph holds a ``concept`` at that id, so the
    next mirror would have to reclassify it. Written through the store rather
    than over HTTP because no route deletes a node - but the state is reachable:
    before ``_owns_column_node``, pointing a ``has_column`` edge at another
    dataset's node and then patching that dataset's schema **deleted the target
    node**, and ``POST /ontology/concepts`` could then take the freed id. That
    chain is pinned by
    ``test_reconciliation_drops_a_foreign_has_column_edge_without_its_node``.
    """
    store = graph_store.get_store()
    store.delete_node(dataset_id)
    store.upsert_node(dataset_id, "concept", label=dataset_id)


def test_a_patch_that_declares_no_schema_is_checked_too() -> None:
    """The check was gated on ``request.schema is not None``, so a title-only
    patch skipped it - and the dataset's *own* node is rewritten by every
    mirror. Measured: 400 "request body is not valid" with the new title kept."""
    assert client.post("/catalog/datasets", json=_payload("제목만패치셋")).status_code == 200
    _drift_the_dataset_node_into_a_concept("제목만패치셋")
    response = client.patch(
        "/catalog/datasets/제목만패치셋", json={**ADMIN, "title": "바뀐 제목"}
    )
    assert response.status_code == 409
    assert catalog.get_dataset("제목만패치셋").title == "제목만패치셋 제목"


def test_publish_refuses_the_conflict_instead_of_applying_it() -> None:
    """``seed_dataset`` is called by all four mutations and only two of them
    asked this question. Measured: **400** with ``status`` already ``published``
    and an audit row reading ``result='success'`` for a request the caller saw
    fail."""
    assert client.post("/catalog/datasets", json=_payload("발행충돌셋")).status_code == 200
    _drift_the_dataset_node_into_a_concept("발행충돌셋")
    before = catalog.get_dataset("발행충돌셋")
    before_status, before_updated = before.status, before.updated_at
    response = client.post("/catalog/datasets/발행충돌셋/publish", json=ADMIN)
    assert response.status_code == 409
    after = catalog.get_dataset("발행충돌셋")
    assert after.status == before_status == "registered"
    assert after.updated_at == before_updated
    rows = catalog.list_audit_events(resource="발행충돌셋")
    assert rows[0].action == "dataset.publish"
    assert rows[0].result == "denied"
    assert "kind" in rows[0].reason


def test_deprecate_refuses_the_conflict_instead_of_applying_it() -> None:
    """The same hole on the fourth verb, which answered **500** - its route has
    no ``ValueError`` arm at all - with the status change already applied."""
    assert client.post("/catalog/datasets", json=_payload("폐기충돌셋")).status_code == 200
    _drift_the_dataset_node_into_a_concept("폐기충돌셋")
    before = catalog.get_dataset("폐기충돌셋")
    before_status, before_updated = before.status, before.updated_at
    response = client.post("/catalog/datasets/폐기충돌셋/deprecate", json=ADMIN)
    assert response.status_code == 409
    after = catalog.get_dataset("폐기충돌셋")
    assert after.status == before_status == "registered"
    assert after.updated_at == before_updated
    rows = catalog.list_audit_events(resource="폐기충돌셋")
    assert rows[0].action == "dataset.deprecate"
    assert rows[0].result == "denied"


def test_an_absent_dataset_is_still_404_on_both_status_verbs() -> None:
    """The pre-check must not turn "no such dataset" into something else: it
    returns without asking when the row is absent, leaving the mutation to raise
    ``KeyError``."""
    for verb in ("publish", "deprecate"):
        response = client.post(f"/catalog/datasets/없는데이터셋/{verb}", json=ADMIN)
        assert response.status_code == 404, verb


# ---------------------- reconciliation destroys only its own column nodes --


def test_reconciliation_drops_a_foreign_has_column_edge_without_its_node() -> None:
    """``_reconcile_removed`` deleted **any** undeclared ``has_column`` target.

    ``POST /graph/edges`` accepts a ``has_column`` edge to any node, and the
    reconciliation pass that runs on every mirror removed the edge *and the node
    it pointed at*. Measured: pointing one at the seeded ``고객`` concept and
    then patching the dataset's schema deleted ``고객`` itself - with every edge
    touching it - so the ontology routes that resolve that term answered as if
    the concept had never been defined, and the state the four catalog
    mutations now have to refuse became reachable from two authorized requests.

    The edge is still removed: it is this dataset's edge. Only the node another
    writer owns survives.
    """
    assert client.post("/catalog/datasets", json=_payload("회수검사셋")).status_code == 200
    assert (
        client.post(
            "/ontology/concepts",
            json={**ADMIN, "concept": "남의개념노드", "definition": "정의"},
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/graph/edges",
            json={
                **ADMIN,
                "edge_type": "has_column",
                "source_id": "회수검사셋",
                "target_id": "남의개념노드",
            },
        ).status_code
        == 200
    )
    assert (
        client.patch(
            "/catalog/datasets/회수검사셋",
            json={**_payload("회수검사셋", ("자기컬럼",)), "id": None},
        ).status_code
        == 200
    )
    store = graph_store.get_store()
    survivor = store.get_node("남의개념노드")
    assert survivor is not None and survivor.kind == "concept"
    targets = {edge.target_id for edge in store.edges_for("회수검사셋", "has_column")}
    assert "남의개념노드" not in targets
    assert targets == {"회수검사셋:자기컬럼"}
    # The dataset's own column node is still collected when it is undeclared.
    assert (
        client.patch(
            "/catalog/datasets/회수검사셋",
            json={**_payload("회수검사셋"), "id": None},
        ).status_code
        == 200
    )
    assert store.get_node("회수검사셋:자기컬럼") is None
