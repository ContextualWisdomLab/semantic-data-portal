"""ONT-002's edge half: a data asset cannot be placed in the business-class hierarchy.

The acceptance criterion is "table/dataset이 business class의 subclass가 되지
않도록 SHACL/OWL 검증". The kinds were modelled - concept, dataset and column are
distinct, and a dataset relates to a concept through a ``mapping`` edge rather
than by subclassing - and ``assert_node_kind_is_stable`` closed the half where an
id was *reclassified*. Nothing checked the edges. Measured at HEAD before this
change, each with one authorized request against the shipped seed::

    POST /graph/edges    broader  crm-customer-master -> 고객   -> 200
    POST /graph/edges    broader  고객 -> crm-customer-master   -> 200
    POST /graph/edges    narrower crm-customer-master -> 고객   -> 200
    POST /ontology/concepts {"concept": "테스트개념하나", "definition": "정의",
                             "broader": "crm-customer-master"}
                                                                -> 200
    POST /ontology/concepts {... "narrower":
                             ["crm-customer-master:customer_id"]} -> 200

so both publication paths merged the two class systems into one hierarchy, and
both endpoints' ``kind`` - every fact needed to refuse it - was already stored
and unread.

Two halves, because neither is sufficient:

* The **gate** refuses the write (409: the request is well-formed, the conflict
  is with the stored kinds). It can only read the kinds known at write time, and
  an edge whose endpoints are both unknown must be permitted - the seed itself
  declares ``narrower: 매출 -> 매출 성장`` for a concept the vocabulary never
  defines, and ``upsert_concept`` writes a concept's hierarchy edges before its
  targets are registered, so refusing an unknown endpoint would refuse the
  product's own load order. Measured on the seed: 27 of 78 edges name a node
  that does not exist, 2 of them hierarchy edges.
* The **report** (``ConceptHierarchyShape``) evaluates what the graph now holds,
  which is the 검증 the criterion words and which catches what the gate cannot:
  measured, an edge written to an unknown target that is *then* created as a
  dataset passes the gate twice (200, 200) and turns the report's ``conforms``
  false with ``hierarchy_pass_rate`` 0.875.

Reverse-verified, each direction separately:

* removing the ``assert_hierarchy_respects_class_separation`` call from
  ``InMemoryGraphStore.upsert_edge`` returns ``POST /graph/edges`` to 200 and
  fails the gate tests here;
* removing ``_assert_hierarchy_targets_respect_class_separation`` from
  ``validate_concept_registration``, with the store's gate left in place,
  answers **500** - the route's mirror write is inside neither ``try`` block -
  having already published the vocabulary record and the graph node, which is
  why the check belongs in the pre-write validator and not only in the store;
* dropping ``ConceptHierarchyShape`` from ``_EVALUATED_SHAPE_IDS`` makes
  ``shacl_compatible`` false, which is what the derived claim is for;
* and treating an unknown endpoint as a violation rather than a warning makes
  ``seed_store`` on a fresh store raise outright
  (``'narrower' ... target '활성 고객'``), so the permission for an unknown
  endpoint is load-bearing rather than a preference.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from sdp import graph_store, ontology
from sdp import semantic_validation as sv
from sdp.api import app
from sdp.graph_store import (
    CONCEPT_NODE_KIND,
    HIERARCHY_EDGE_TYPES,
    HierarchyClassSeparationConflict,
    InMemoryGraphStore,
)
from sdp.seed import seed_store


client = TestClient(app, raise_server_exceptions=False)


@contextmanager
def _private_seeded_store() -> Iterator[InMemoryGraphStore]:
    """A freshly seeded store, swapped in for the body and restored after.

    ``tests/conftest.py``'s autouse fixture deliberately does not restore the
    graph-store singleton - there is no snapshot API - and this repository's
    standing rule is therefore that a test depending on graph counts takes its
    own baseline. Two reasons here, and the second is the stronger one:

    * the counts below are about the **shipped seed**, not about whatever edges
      an earlier test in this file legitimately added;
    * a test that left a class-separation *violation* in the shared store would
      make every later assertion that the shipped graph conforms depend on file
      order, which is the failure mode this repository has already been bitten
      by once.

    Seeding a fresh store also exercises the gate against the product's own load
    order: ``seed_store`` writes the concepts first, so a concept's hierarchy
    targets are written before the targets exist.
    """
    previous = graph_store.get_store()
    fresh = InMemoryGraphStore()
    seed_store(fresh)
    graph_store.set_store(fresh)
    try:
        yield fresh
    finally:
        graph_store.set_store(previous)

ADMIN = {"actor": "admin"}
SEEDED_DATASET = "crm-customer-master"
SEEDED_COLUMN = "crm-customer-master:customer_id"
SEEDED_CONCEPT = "고객"
OTHER_SEEDED_CONCEPT = "주문"


def _edge(edge_type: str, source_id: str, target_id: str):
    """Ask ``POST /graph/edges`` for one edge as an authorized writer."""
    return client.post(
        "/graph/edges",
        json={**ADMIN, "edge_type": edge_type, "source_id": source_id, "target_id": target_id},
    )


def _hierarchy_report() -> dict:
    """The published ConceptHierarchyShape report."""
    return client.get("/enterprise/shacl-validation").json()["hierarchy_class_separation"]


# ------------------------------------------------- the gate, the direct path --


@pytest.mark.parametrize(
    "edge_type, source_id, target_id",
    [
        ("broader", SEEDED_DATASET, SEEDED_CONCEPT),
        ("broader", SEEDED_CONCEPT, SEEDED_DATASET),
        ("narrower", SEEDED_DATASET, SEEDED_CONCEPT),
        ("narrower", SEEDED_CONCEPT, SEEDED_DATASET),
        ("broader", SEEDED_COLUMN, SEEDED_CONCEPT),
        ("narrower", SEEDED_CONCEPT, SEEDED_COLUMN),
    ],
)
def test_a_hierarchy_edge_across_the_class_boundary_is_refused(
    edge_type: str, source_id: str, target_id: str
) -> None:
    """Both relations, both directions, both asset kinds. Each answered 200."""
    response = _edge(edge_type, source_id, target_id)
    assert response.status_code == 409
    detail = response.json()["detail"]
    assert edge_type in detail
    # The refusal names the modelled alternative rather than only refusing.
    assert "mapping" in detail


@pytest.mark.parametrize(
    "edge_type, source_id, target_id",
    [
        # ``mapping`` is how a dataset and a concept are modelled as linked, and
        # ``related`` is associative in SKOS rather than subsumption: neither
        # asserts a class hierarchy, so neither is gated.
        ("mapping", SEEDED_DATASET, SEEDED_CONCEPT),
        ("related", SEEDED_DATASET, SEEDED_CONCEPT),
        ("has_column", SEEDED_DATASET, SEEDED_COLUMN),
        # Legitimate SKOS subsumption.
        ("broader", SEEDED_CONCEPT, OTHER_SEEDED_CONCEPT),
        ("narrower", SEEDED_CONCEPT, OTHER_SEEDED_CONCEPT),
    ],
)
def test_the_rule_refuses_nothing_legitimate(
    edge_type: str, source_id: str, target_id: str
) -> None:
    """The narrow rule: exactly the subsumption claim across the boundary."""
    assert _edge(edge_type, source_id, target_id).status_code == 200


def test_an_unknown_endpoint_is_permitted_because_the_seed_needs_it() -> None:
    """The seed declares hierarchy targets it never defines; refusing them would
    refuse the product's own load order (and ``upsert_concept`` writes a
    concept's edges before its targets exist)."""
    assert _edge("broader", SEEDED_CONCEPT, "아직존재하지않는개념").status_code == 200
    assert _edge("broader", "아직없는출발점", "아직없는도착점").status_code == 200


def test_the_shipped_seed_declares_hierarchy_targets_that_are_not_nodes() -> None:
    """The measurement the permission above rests on, re-derived not remembered."""
    with _private_seeded_store() as store:
        nodes = store._nodes
        dangling = [
            edge
            for edge in store._edges
            if edge.edge_type in HIERARCHY_EDGE_TYPES
            and (edge.source_id not in nodes or edge.target_id not in nodes)
        ]
    assert len(dangling) == 2, (
        "the permission for an unknown endpoint has lost its reason"
    )


# --------------------------------------------------- the gate, in the store --


def test_the_store_refuses_the_boundary_crossing_edge() -> None:
    """On a fresh store, so the refusal is the store's and not the route's."""
    store = InMemoryGraphStore()
    store.upsert_node("고객데이터셋", "dataset", label="고객 데이터셋")
    store.upsert_node("고객개념", CONCEPT_NODE_KIND, label="고객 개념")
    with pytest.raises(HierarchyClassSeparationConflict):
        store.upsert_edge("broader", "고객데이터셋", "고객개념")
    with pytest.raises(HierarchyClassSeparationConflict):
        store.upsert_edge("narrower", "고객개념", "고객데이터셋")
    # Nothing was appended by either refusal.
    assert [edge for edge in store._edges if edge.edge_type in HIERARCHY_EDGE_TYPES] == []


def test_the_conflict_is_a_value_error_so_no_existing_handler_stops_refusing() -> None:
    """The same reason ``ConceptKindConflict`` is one."""
    assert issubclass(HierarchyClassSeparationConflict, ValueError)


def test_the_refusal_rule_is_one_pure_function_both_backends_call() -> None:
    """So the two backends cannot drift in what they refuse or in what they say."""
    refusal = graph_store.hierarchy_class_separation_refusal(
        "broader", "데이터셋하나", "개념하나", source_kind="dataset", target_kind="concept"
    )
    assert refusal is not None and "dataset" in refusal
    assert (
        graph_store.hierarchy_class_separation_refusal(
            "broader", "개념하나", "개념둘", source_kind="concept", target_kind="concept"
        )
        is None
    )
    assert (
        graph_store.hierarchy_class_separation_refusal(
            "broader", "개념하나", "미지", source_kind="concept", target_kind=None
        )
        is None
    )
    # A non-hierarchy relation never reaches the rule, and the rule itself does
    # not decide that - the callers gate on HIERARCHY_EDGE_TYPES - so this
    # asserts the set, which is what they read.
    assert HIERARCHY_EDGE_TYPES == ("broader", "narrower")
    assert "related" not in HIERARCHY_EDGE_TYPES
    assert "mapping" not in HIERARCHY_EDGE_TYPES


# ------------------------------------------- the gate, the publication path --


@pytest.mark.parametrize(
    "payload",
    [
        {"concept": "경계검사하나", "definition": "정의", "broader": SEEDED_DATASET},
        {"concept": "경계검사둘", "definition": "정의", "narrower": [SEEDED_COLUMN]},
    ],
)
def test_a_concept_cannot_declare_a_data_asset_as_its_parent_or_child(payload: dict) -> None:
    """The route answered 200 and the graph then held the subsumption edge."""
    response = client.post("/ontology/concepts", json={**ADMIN, **payload})
    assert response.status_code == 409
    assert "mapping" in response.json()["detail"]


def test_the_refused_publication_leaves_neither_store_written() -> None:
    """Why the check is in the pre-write validator and not only in the store.

    ``upsert_concept`` writes the concept node and the vocabulary record before
    its hierarchy edges, and the route's mirror write is inside neither ``try``
    block. Measured with this file's reverse-verification: the store's gate
    alone answers **500** with the vocabulary record published and the graph node
    served.
    """
    before = set(ontology.list_concepts())
    response = client.post(
        "/ontology/concepts",
        json={**ADMIN, "concept": "부분쓰기검사", "definition": "정의", "broader": SEEDED_DATASET},
    )
    assert response.status_code == 409
    assert set(ontology.list_concepts()) == before
    assert "부분쓰기검사" not in ontology.list_concepts()
    assert (
        client.get("/graph/nodes/부분쓰기검사", params={"user": "admin"}).status_code == 404
    )


def test_the_publication_path_still_accepts_a_concept_hierarchy() -> None:
    """``related`` to a dataset asserts no hierarchy, and a concept parent is the
    whole point of the relation."""
    assert (
        client.post(
            "/ontology/concepts",
            json={**ADMIN, "concept": "허용검사하나", "definition": "정의", "broader": SEEDED_CONCEPT},
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/ontology/concepts",
            json={
                **ADMIN,
                "concept": "허용검사둘",
                "definition": "정의",
                "related": [SEEDED_DATASET],
            },
        ).status_code
        == 200
    )
    # A target that is not a node yet: the seed's own shape.
    assert (
        client.post(
            "/ontology/concepts",
            json={**ADMIN, "concept": "허용검사셋", "definition": "정의", "broader": "아직없는상위개념"},
        ).status_code
        == 200
    )


def test_the_refusal_is_409_on_both_paths_and_the_contract_says_so() -> None:
    """One status for one rule, and the published error contract carries it."""
    from sdp.api_error_contract import ROUTE_REFUSALS

    assert 409 in ROUTE_REFUSALS[("POST", "/graph/edges")]
    assert 409 in ROUTE_REFUSALS[("POST", "/ontology/concepts")]


# ------------------------------------------------------------- the 검증 half --


def test_the_shape_is_published_and_evaluated() -> None:
    """A shape in the catalog that nothing evaluates makes the derived claim
    false - the discipline ``_shacl_compatible`` already encodes."""
    shape = sv._shape("ConceptHierarchyShape")
    assert shape["hierarchy_relations"] == list(HIERARCHY_EDGE_TYPES)
    assert shape["required_endpoint_kind"] == CONCEPT_NODE_KIND
    assert shape["unknown_endpoint_severity"] == "warning"
    assert "ConceptHierarchyShape" in sv._EVALUATED_SHAPE_IDS
    assert sv._shacl_compatible() is True


def test_the_published_catalog_carries_the_shape_and_its_count_is_derived() -> None:
    """Both publication paths, because a reader of either takes the catalog it
    publishes for the constraints that produced ``conforms``.

    ``shape_count`` is asserted against the catalog's length rather than a
    literal, so the published number cannot drift from what is published.
    """
    summary = client.get("/enterprise/shacl-validation").json()
    assert summary["shape_count"] == len(sv._SHACL_COMPATIBLE_SHAPES)
    # The aggregate publishes the count; the per-dataset report publishes the
    # catalog itself (the aggregate's ``reports`` array is tenant-scoped and is
    # empty for an unauthenticated caller - measured, withheld 5 of 5).
    assert summary["reports"] == []
    published = client.get(
        "/catalog/datasets/crm-customer-master/semantic-validation",
        params={"user": "admin"},
    ).json()
    assert "ConceptHierarchyShape" in {shape["id"] for shape in published["shapes"]}
    # ...and is *not* claimed as evaluated by a dataset report: it targets an
    # edge, the same separation ``ConceptShape`` already has from this list.
    assert "ConceptHierarchyShape" not in published["evaluated_shapes"]


def test_the_shipped_graph_conforms_and_its_warnings_are_counted_separately() -> None:
    """The measurement that lets this constraint be a violation at all: no
    shipped hierarchy edge crosses the boundary, and the 2 that name a missing
    target are the warning case."""
    with _private_seeded_store():
        report = _hierarchy_report()
    assert report["evaluated_shapes"] == ["ConceptHierarchyShape"]
    assert report["conforms"] is True
    assert report["hierarchy_edge_count"] == 7
    assert report["conforming_edge_count"] == 7
    assert report["hierarchy_pass_rate"] == 1.0
    assert report["unknown_endpoint_count"] == 2
    assert [item["severity"] for item in report["violations"]] == ["warning", "warning"]
    assert report["conformance_scope"] == sv.HIERARCHY_CLASS_SEPARATION_SCOPE


def test_the_report_catches_the_ordering_the_gate_cannot() -> None:
    """An edge to an unknown target, whose target is then created as a dataset.

    Both writes pass - the gate reads the kinds known at write time, and a first
    create is not a reclassification - so without this report ONT-002's
    constraint would have a hole no surface reported.
    """
    with _private_seeded_store():
        assert _edge("broader", SEEDED_CONCEPT, "나중에데이터셋").status_code == 200
        assert (
            client.post(
                "/graph/nodes",
                json={**ADMIN, "node_id": "나중에데이터셋", "kind": "dataset"},
            ).status_code
            == 200
        )
        report = _hierarchy_report()
    assert report["conforms"] is False
    violations = [item for item in report["violations"] if item["severity"] == "violation"]
    assert len(violations) == 1
    assert "나중에데이터셋" in violations[0]["message"]
    assert "dataset" in violations[0]["message"]
    assert report["hierarchy_pass_rate"] < 1.0


def test_the_classifier_is_pure_and_reads_its_kinds_from_its_argument() -> None:
    """So ``semantic_validation`` stays free of the store it validates - the same
    split as ``validate_concept_semantics`` and its injected resolver."""
    report = sv.hierarchy_class_separation(
        [
            {
                "edge_type": "broader",
                "source_id": "데이터셋",
                "target_id": "개념",
                "source_kind": "dataset",
                "target_kind": "concept",
            },
            {
                "edge_type": "narrower",
                "source_id": "개념",
                "target_id": "없는것",
                "source_kind": "concept",
                "target_kind": None,
            },
            {
                "edge_type": "broader",
                "source_id": "개념하나",
                "target_id": "개념둘",
                "source_kind": "concept",
                "target_kind": "concept",
            },
        ]
    )
    assert report["hierarchy_edge_count"] == 3
    assert report["conforming_edge_count"] == 2
    assert report["unknown_endpoint_count"] == 1
    assert report["conforms"] is False
    assert report["hierarchy_pass_rate"] == 0.667


def test_the_empty_graph_reports_a_zero_rate_rather_than_dividing_by_zero() -> None:
    """The same guard the dataset and concept pass rates use."""
    report = sv.hierarchy_class_separation([])
    assert report["hierarchy_edge_count"] == 0
    assert report["hierarchy_pass_rate"] == 0.0
    assert report["conforms"] is True


def test_the_report_declares_what_it_does_not_cover() -> None:
    """A measured blind spot, published rather than left for a reader to assume
    away: a ``kind="concept"`` node written straight through POST /graph/nodes is
    not in the vocabulary, so a hierarchy edge between it and a node that later
    becomes a dataset is counted by nothing.
    """
    scope = sv.HIERARCHY_CLASS_SEPARATION_SCOPE
    assert "_CONCEPT_DEFINITIONS" in scope
    assert "POST /graph/nodes" in scope
    with _private_seeded_store():
        before = _hierarchy_report()["hierarchy_edge_count"]
        assert (
            client.post(
                "/graph/nodes",
                json={**ADMIN, "node_id": "어휘밖개념노드", "kind": CONCEPT_NODE_KIND},
            ).status_code
            == 200
        )
        assert "어휘밖개념노드" not in ontology.list_concepts()
        assert _edge("broader", "어휘밖개념노드", "나중데이터셋2").status_code == 200
        assert (
            client.post(
                "/graph/nodes", json={**ADMIN, "node_id": "나중데이터셋2", "kind": "dataset"}
            ).status_code
            == 200
        )
        after = _hierarchy_report()
    assert after["hierarchy_edge_count"] == before
    assert not any("나중데이터셋2" in item["message"] for item in after["violations"])
