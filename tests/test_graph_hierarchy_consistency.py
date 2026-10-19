"""A published concept cannot be broader than itself (ONT-007's consistency item).

``broader``/``narrower`` assert subsumption, and nothing looked at what the
stored hierarchy already said. Measured at HEAD before this gate, each one
authorized request against the shipped seed::

    POST /graph/edges broader 고객 -> 주문                       -> 200
    POST /graph/edges broader 주문 -> 고객                       -> 200
    POST /graph/edges broader 고객 -> 고객                       -> 200   (self-loop)
    POST /ontology/concepts {"concept": "순환상위", "broader": "고객"}  -> 200
    POST /ontology/concepts {"concept": "고객", "broader": "순환상위"}  -> 200

so the published glossary could assert that each of two distinct terms is a kind
of the other. No read surface crashed on it - traversal is depth-bounded, and
``/ontology/term/{term}/graph``, ``/ontology/concept/{term}``,
``/ontology/search`` and ``/graph/query`` all answered 200 with the cycle in
place - so the damage was silent and semantic: ONT-003's "broader/narrower 조회"
returns a hierarchy with no top, and in any OWL reading of SKOS the two concepts
collapse into one.

Direction is the whole subtlety. ``narrower: 고객 -> 활성 고객`` and
``broader: 활성 고객 -> 고객`` are the *same* assertion written from both ends,
and the shipped vocabulary states exactly that for two of its five subsumptions;
reading them as two opposed assertions would make the seed itself cyclic. So the
direction is normalized once, in ``graph_store.subsumption_pair``, and the seed's
7 hierarchy edges carry 5 distinct ``(child, parent)`` assertions.

Two halves again, but **not** for the reason the class-separation rule has two,
and the difference is measured. That gate reads node *kinds*, so an edge written
while an endpoint is not a node yet escapes it; this gate reads *edges*, and sees
both spellings of every stored subsumption, so no single write through
``upsert_edge`` closes a cycle unseen - the ordering that defeats the other gate
is refused by this one (measured below: 409). The report is for edges the gate
never saw: a hierarchy written before the gate existed, a future bulk path that
appends without going through ``upsert_edge``, and - on the Postgres backend only
- two concurrent writers each adding one edge, because there the reachability
walk runs outside the write transaction. It publishes ``cyclic_group_count``,
the number ONT-007 wants a release gate to read. It is published under its own engine declaration
(``consistency_engine: builtin_graph_checks``, ``reasoner_executed: false``) and
deliberately *not* added to the SHACL shape catalog: acyclicity is a property of
the graph rather than of a node or an edge, so calling it a shape would make
``shacl_compatible`` cover a constraint that is not shape-shaped. It is named
``cyclic_group_count`` and not "unsatisfiable classes" because a cycle makes concepts
mutually subsuming, and unsatisfiability needs a disjointness axiom this
repository does not have.

Reverse-verified:

* removing ``assert_hierarchy_stays_acyclic`` from
  ``InMemoryGraphStore.upsert_edge`` returns the cycle writes to 200;
* removing ``_assert_declared_hierarchy_stays_acyclic`` from
  ``validate_concept_registration`` makes the concept path answer 500 from the
  unguarded mirror write instead of 409;
* and a found defect, which is why the two hierarchy rules are asked *above* the
  already-published branch rather than below it: with them below, the identical
  request for one of the five **seeded** concepts answered 500 where it answers
  409 for an unpublished one, because that branch returns early on the ground
  that the stored record was already validated - true for ``definition``, false
  for the hierarchy fields, which the route mirrors into the graph from the
  submission.
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
    HierarchyCycleConflict,
    InMemoryGraphStore,
    subsumption_pair,
)
from sdp.seed import seed_store


client = TestClient(app, raise_server_exceptions=False)

ADMIN = {"actor": "admin"}
SEEDED_CONCEPT = "고객"
SEEDED_CHILD = "활성 고객"


@contextmanager
def _private_seeded_store() -> Iterator[InMemoryGraphStore]:
    """A freshly seeded store, swapped in for the body and restored after.

    Duplicated from ``tests/test_graph_hierarchy_class_separation.py``, whose
    copy carries the reasoning: the autouse fixture does not restore the
    graph-store singleton, so a test that asserts a count takes its own
    baseline - and a test that left a cycle in the shared store would make every
    later assertion that the shipped hierarchy is acyclic depend on file order.
    """
    previous = graph_store.get_store()
    fresh = InMemoryGraphStore()
    seed_store(fresh)
    graph_store.set_store(fresh)
    try:
        yield fresh
    finally:
        graph_store.set_store(previous)


def _edge(edge_type: str, source_id: str, target_id: str):
    """Ask ``POST /graph/edges`` for one edge as an authorized writer."""
    return client.post(
        "/graph/edges",
        json={**ADMIN, "edge_type": edge_type, "source_id": source_id, "target_id": target_id},
    )


def _consistency() -> dict:
    """The published hierarchy-consistency report."""
    return client.get("/enterprise/shacl-validation").json()["hierarchy_consistency"]


# ------------------------------------------------------- direction, not order --


def test_the_two_spellings_of_one_assertion_are_one_pair() -> None:
    """Reading them as opposed assertions would make the shipped seed cyclic."""
    assert subsumption_pair("broader", "아이", "어른") == ("아이", "어른")
    assert subsumption_pair("narrower", "어른", "아이") == ("아이", "어른")
    # Only subsumption has a direction to normalize.
    assert subsumption_pair("related", "아이", "어른") is None
    assert subsumption_pair("mapping", "아이", "어른") is None


def test_the_seed_states_two_of_its_subsumptions_from_both_ends() -> None:
    """The measurement the deduplication rests on, re-derived not remembered."""
    with _private_seeded_store():
        report = _consistency()
    # 7 hierarchy edges, 5 distinct (child, parent) assertions.
    assert report["subsumption_pair_count"] == 5
    assert report["conforms"] is True
    assert report["cyclic_group_count"] == 0


# ---------------------------------------------------------- the gate, writing --


@pytest.mark.parametrize(
    "edge_type, source_id, target_id",
    [
        ("broader", "주문", SEEDED_CONCEPT),
        ("narrower", SEEDED_CONCEPT, "주문"),
    ],
)
def test_the_edge_that_closes_a_two_concept_cycle_is_refused(
    edge_type: str, source_id: str, target_id: str
) -> None:
    """Both spellings of the closing edge, after one legitimate edge."""
    assert _edge("broader", SEEDED_CONCEPT, "주문").status_code == 200
    response = _edge(edge_type, source_id, target_id)
    assert response.status_code == 409
    assert "broader than itself" in response.json()["detail"]


def test_a_self_loop_is_the_same_rule() -> None:
    """A concept strictly broader than itself, which is the degenerate cycle."""
    response = _edge("broader", SEEDED_CONCEPT, SEEDED_CONCEPT)
    assert response.status_code == 409
    assert "a kind of itself" in response.json()["detail"]


def test_a_longer_cycle_is_refused_too() -> None:
    """The walk is transitive, not a check of the immediate parent."""
    store = InMemoryGraphStore()
    for node in ("사슬하나", "사슬둘", "사슬셋"):
        store.upsert_node(node, "concept")
    store.upsert_edge("broader", "사슬하나", "사슬둘")
    store.upsert_edge("broader", "사슬둘", "사슬셋")
    with pytest.raises(HierarchyCycleConflict):
        store.upsert_edge("broader", "사슬셋", "사슬하나")
    assert [edge.target_id for edge in store.edges_for("사슬셋", "broader")] == []


def test_the_rule_refuses_nothing_legitimate() -> None:
    """A re-statement, a second parent, and an endpoint that is not a node yet."""
    # Re-stating a seeded subsumption from either end is not a cycle.
    assert _edge("narrower", SEEDED_CONCEPT, SEEDED_CHILD).status_code == 200
    assert _edge("broader", SEEDED_CHILD, SEEDED_CONCEPT).status_code == 200
    # Multiple parents are legal in SKOS, and the seed uses them.
    assert _edge("broader", "이탈 고객", "이탈").status_code == 200
    # An unknown endpoint has no parents, so it can close nothing.
    assert _edge("broader", SEEDED_CONCEPT, "아직없는상위개념").status_code == 200


def _store_with_a_planted_cycle() -> InMemoryGraphStore:
    """A store holding 순환하나 <= 순환둘 <= 순환하나, appended past the gate.

    What "an edge the gate never saw" means concretely - a hierarchy written
    before the gate existed, or a bulk path that does not go through
    ``upsert_edge``.
    """
    store = InMemoryGraphStore()
    for node in ("순환하나", "순환둘", "새로운하위"):
        store.upsert_node(node, "concept")
    store._edges.append(graph_store.GraphEdge("broader", "순환하나", "순환둘", {}))
    store._edges.append(graph_store.GraphEdge("broader", "순환둘", "순환하나", {}))
    return store


def test_an_already_cyclic_store_still_refuses_rather_than_hangs() -> None:
    """A re-statement of one edge of the planted cycle is refused on the first hop."""
    store = _store_with_a_planted_cycle()
    with pytest.raises(HierarchyCycleConflict):
        store.upsert_edge("broader", "순환하나", "순환둘")


class _BoundedReadStore(InMemoryGraphStore):
    """A store that refuses to answer more than ``read_budget`` ancestor reads.

    Why a budget rather than just calling ``upsert_edge``: without the ``visited``
    guard the walk does not raise, it *never returns*, and a test that hangs is
    not a test that fails - pytest waits forever and a CI run is killed with no
    verdict. Adversarial review pointed this out about the first version of the
    test below, which asserted the return value and would have hung. Counting the
    store reads turns the non-termination into an ordinary assertion failure.
    """

    read_budget = 64

    def __init__(self) -> None:
        """Start with an empty read counter."""
        super().__init__()
        self.ancestor_reads = 0

    def subsumption_parents(self, node_id: str) -> list[str]:
        """Count this read, then answer it, failing past the budget."""
        self.ancestor_reads += 1
        if self.ancestor_reads > self.read_budget:
            raise AssertionError(
                "the acyclicity walk read more than "
                f"{self.read_budget} ancestors on a 3-node graph: it is not "
                "terminating (the `visited` guard is what bounds it)"
            )
        return super().subsumption_parents(node_id)


def test_a_write_whose_parent_sits_inside_a_planted_cycle_terminates() -> None:
    """This is the case ``visited`` exists for, and the first attempt to
    reverse-verify it chose a parent with no parents at all, so the walk ended
    before it reached the cycle and the guard looked unnecessary.

    Reverse-verified with the right case: with ``visited`` removed this write
    does not return at all (killed at a 15s timeout). The budget is what makes
    that a failure here instead of a hang.
    """
    store = _BoundedReadStore()
    for node in ("순환하나", "순환둘", "새로운하위"):
        store.upsert_node(node, "concept")
    store._edges.append(graph_store.GraphEdge("broader", "순환하나", "순환둘", {}))
    store._edges.append(graph_store.GraphEdge("broader", "순환둘", "순환하나", {}))
    edge = store.upsert_edge("broader", "새로운하위", "순환하나")
    assert (edge.source_id, edge.target_id) == ("새로운하위", "순환하나")
    # Three nodes, so a terminating walk reads a handful of times, not 64.
    assert store.ancestor_reads <= 8


# ----------------------------------------------------- the gate, publishing --


def test_a_concept_cannot_be_published_under_its_own_descendant() -> None:
    """Measured at 200 before this gate, on the concept path."""
    assert (
        client.post(
            "/ontology/concepts",
            json={**ADMIN, "concept": "순환상위", "definition": "정의", "broader": SEEDED_CONCEPT},
        ).status_code
        == 200
    )
    before = set(ontology.list_concepts())
    response = client.post(
        "/ontology/concepts",
        json={**ADMIN, "concept": SEEDED_CONCEPT, "definition": "정의", "broader": "순환상위"},
    )
    assert response.status_code == 409
    assert "broader than itself" in response.json()["detail"]
    assert set(ontology.list_concepts()) == before


def test_an_already_published_concept_is_gated_on_the_same_rule() -> None:
    """The found defect: this answered 500 while the unpublished case answered 409.

    ``validate_concept_registration`` returns early for an already-published
    concept because the registrar discards the submission - but the route
    mirrors the submitted hierarchy fields into the graph store, so they are not
    discarded, and the refusal surfaced from the unguarded mirror write.
    """
    assert SEEDED_CONCEPT in ontology.list_concepts()
    assert (
        client.post(
            "/graph/nodes", json={**ADMIN, "node_id": "하위개념하나", "kind": "concept"}
        ).status_code
        == 200
    )
    assert _edge("narrower", SEEDED_CONCEPT, "하위개념하나").status_code == 200
    response = client.post(
        "/ontology/concepts",
        json={**ADMIN, "concept": SEEDED_CONCEPT, "definition": "정의", "broader": "하위개념하나"},
    )
    assert response.status_code == 409
    assert "broader than itself" in response.json()["detail"]


def test_an_already_published_concept_still_accepts_legitimate_fields() -> None:
    """The early-return path is narrowed, not closed: only the mirrored
    hierarchy fields are gated, and a re-submission that changes nothing still
    answers 200."""
    assert (
        client.post(
            "/ontology/concepts",
            json={**ADMIN, "concept": SEEDED_CONCEPT, "definition": "정의", "related": ["주문"]},
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/ontology/concepts",
            json={
                **ADMIN,
                "concept": SEEDED_CHILD,
                "definition": "정의",
                "broader": SEEDED_CONCEPT,
            },
        ).status_code
        == 200
    )


# ------------------------------------------------------------- the 검증 half --


def test_the_report_is_honest_about_what_ran() -> None:
    """"consistency check" alone reads as a reasoner having run."""
    report = _consistency()
    assert report["consistency_engine"] == "builtin_graph_checks"
    assert report["reasoner_executed"] is False
    assert report["checked_conditions"] == ["acyclic_subsumption"]
    assert "reasoner" in report["conformance_scope"]
    assert "S27" in report["conformance_scope"]


def test_acyclicity_is_not_published_as_a_shacl_shape() -> None:
    """It is a graph property, so calling it a shape would make
    ``shacl_compatible`` cover a constraint that is not shape-shaped."""
    assert "ConceptHierarchyAcyclicShape" not in {
        shape["id"] for shape in sv._SHACL_COMPATIBLE_SHAPES
    }
    assert sv._shacl_compatible() is True
    body = client.get("/enterprise/shacl-validation").json()
    assert body["shape_count"] == len(sv._SHACL_COMPATIBLE_SHAPES)
    # Its own block, beside the shape reports rather than inside them.
    assert "hierarchy_consistency" in body
    assert "evaluated_shapes" not in body["hierarchy_consistency"]


def test_the_ordering_that_defeats_the_other_gate_does_not_defeat_this_one() -> None:
    """Written as "the report catches what the gate cannot" and then measured.

    An edge to an endpoint that is not a node yet is exactly what escapes the
    class-separation gate, because that one reads kinds. This gate reads edges,
    so the closing write is refused and the hierarchy stays acyclic - which is
    why the report's purpose is stated as "edges the gate never saw" rather than
    borrowing the other rule's ordering hole.
    """
    with _private_seeded_store():
        # 고객 <= 선행간선, written while 선행간선 does not exist as a node.
        assert _edge("broader", SEEDED_CONCEPT, "선행간선").status_code == 200
        # ...and the closing edge, through the other spelling, from the end the
        # gate walks away from.
        assert _edge("narrower", SEEDED_CONCEPT, "선행간선").status_code == 409
        report = _consistency()
    assert report["conforms"] is True


def test_a_cycle_the_gate_never_saw_is_reported_with_its_members() -> None:
    """What a release gate reads: the count, and which concepts are in it.

    Appended straight to the store, which is what "an edge the gate never saw"
    means concretely - a hierarchy written before the gate existed, or a future
    bulk path that does not go through ``upsert_edge``.
    """
    with _private_seeded_store() as store:
        store._edges.append(graph_store.GraphEdge("broader", SEEDED_CONCEPT, "순환짝", {}))
        store._edges.append(graph_store.GraphEdge("broader", "순환짝", SEEDED_CONCEPT, {}))
        store.upsert_node("순환짝", "concept")
        report = _consistency()
    assert report["conforms"] is False
    assert report["cyclic_group_count"] == 1
    assert report["concepts_in_a_cycle"] == sorted([SEEDED_CONCEPT, "순환짝"])
    assert report["cyclic_groups"] == [sorted([SEEDED_CONCEPT, "순환짝"])]


def test_one_group_is_reported_however_many_cycles_run_through_it() -> None:
    """Three mutually-subsuming concepts are one group, and the published name
    says group rather than cycle.

    The first version of this report canonicalized a cycle by its member set and
    called the count ``cycle_count``, which under-reported: the six subsumptions
    below hold five simple cycles over three concepts, and counting simple cycles
    is exponential by nature. One strongly-connected component is the honest
    linear answer, and it is what a release gate needs.
    """
    report = sv.hierarchy_consistency([("가", "나"), ("나", "다"), ("다", "가")])
    assert report["cyclic_group_count"] == 1
    assert report["cyclic_groups"] == [["가", "나", "다"]]
    assert report["conforms"] is False
    both_ways = sv.hierarchy_consistency(
        [("x1", "x2"), ("x2", "x3"), ("x3", "x1"), ("x1", "x3"), ("x3", "x2"), ("x2", "x1")]
    )
    assert both_ways["cyclic_group_count"] == 1
    assert both_ways["cyclic_groups"] == [["x1", "x2", "x3"]]
    # Two disjoint groups stay two, and a tail hanging off one is not a member.
    disjoint = sv.hierarchy_consistency(
        [("c1", "c2"), ("c2", "c1"), ("d1", "d2"), ("d2", "d1"), ("tail", "c1")]
    )
    assert disjoint["cyclic_group_count"] == 2
    assert disjoint["cyclic_groups"] == [["c1", "c2"], ["d1", "d2"]]
    assert "tail" not in disjoint["concepts_in_a_cycle"]


def test_a_submission_that_is_cyclic_within_itself_is_refused_before_any_write() -> None:
    """Confirmed by adversarial review on the first version of this change.

    ``broader: P`` and ``narrower: [P]`` in one request assert that each of two
    terms is a kind of the other. Each declared relation alone closes no cycle
    against stored state, so the pre-write validator passed and the store's gate
    refused the *second* edge from inside the route's unguarded mirror write.
    Measured then: **500**, with the vocabulary record published asserting the
    contradiction, the graph node written, the first edge written, every read
    surface serving it 200, the concept in the SKOS export, and
    ``hierarchy_consistency`` still reporting conforms - the closing edge never
    landed, so the report could not see it. A later ``seed_store`` on a fresh
    store then raised on that stored record.
    """
    before_concepts = set(ontology.list_concepts())
    response = client.post(
        "/ontology/concepts",
        json={
            **ADMIN,
            "concept": "자기모순개념",
            "definition": "정의",
            "broader": "상대개념하나",
            "narrower": ["상대개념하나"],
        },
    )
    assert response.status_code == 409
    assert "broader than itself" in response.json()["detail"]
    # Nothing written, in either store.
    assert set(ontology.list_concepts()) == before_concepts
    assert (
        client.get("/graph/nodes/자기모순개념", params={"user": "admin"}).status_code == 404
    )
    store = graph_store.get_store()
    assert [
        edge
        for edge in store._edges
        if "자기모순개념" in (edge.source_id, edge.target_id)
    ] == []
    # ...and the vocabulary can still be replayed into a fresh store.
    seed_store(InMemoryGraphStore())


def test_the_longer_self_contradiction_is_refused_too() -> None:
    """Not just the broader/narrower overlap: a declared parent and a declared
    child joined by the *stored* hierarchy also close a cycle, and the pending
    pairs are what let the second check see the first."""
    assert _edge("broader", "중간개념하나", "중간개념둘").status_code == 200
    response = client.post(
        "/ontology/concepts",
        json={
            **ADMIN,
            "concept": "사이개념",
            "definition": "정의",
            "broader": "중간개념하나",
            "narrower": ["중간개념둘"],
        },
    )
    assert response.status_code == 409
    assert "사이개념" not in ontology.list_concepts()


def test_the_report_is_linear_rather_than_exponential() -> None:
    """A cost regression guard, because the first version was exponential.

    It enumerated every simple upward path, so a legal SKOS poly-hierarchy - 67
    concepts, 88 subsumptions, every write an authorized 200 - took **45.6
    seconds**, and this report is served to an unauthenticated caller by
    ``GET /enterprise/shacl-validation`` and twice by
    ``GET /enterprise/steward-review``. An ordinary writer could make those
    endpoints unresponsive without writing a single cycle. The replacement is
    Tarjan's SCC algorithm, which is linear; the same graph now measures ~0.001s.

    The assertion is deliberately loose (a second for a graph 30x larger than
    the one that took 45s) so it fails on a reintroduced blow-up rather than on
    a slow machine.
    """
    import time

    pairs: list[tuple[str, str]] = []
    for level in range(600):
        pairs.append((f"n{level}", f"a{level}"))
        pairs.append((f"n{level}", f"b{level}"))
        pairs.append((f"a{level}", f"n{level + 1}"))
        pairs.append((f"b{level}", f"n{level + 1}"))
    started = time.monotonic()
    report = sv.hierarchy_consistency(pairs)
    elapsed = time.monotonic() - started
    assert report["conforms"] is True
    assert report["subsumption_pair_count"] == len(pairs)
    assert elapsed < 1.0, f"the acyclicity report took {elapsed:.3f}s on {len(pairs)} pairs"


def test_the_classifier_is_pure_and_deduplicates_its_pairs() -> None:
    """So ``semantic_validation`` stays free of the store it validates."""
    report = sv.hierarchy_consistency(
        [("활성 고객", "고객"), ("활성 고객", "고객"), ("이탈 고객", "고객")]
    )
    assert report["subsumption_pair_count"] == 2
    assert report["conforms"] is True
    empty = sv.hierarchy_consistency([])
    assert empty["subsumption_pair_count"] == 0
    assert empty["cyclic_group_count"] == 0
    assert empty["conforms"] is True
