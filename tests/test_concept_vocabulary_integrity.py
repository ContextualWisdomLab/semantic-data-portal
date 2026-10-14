"""The published concept vocabulary must not be hijackable or evictable.

Three defects, all introduced by the change that closed the 제안 -> 승인 -> 노출
loop by writing registrations into the module vocabulary. Each is measured here
with the numbers that were observed first.

**Alias hijack.** The alias index was last-writer-wins and nothing checked
ownership, so one authorized upsert naming a seeded concept as its *alias* took
that concept over. Every read surface (resolve, search, concept lookup) resolves
through the index, so the seeded concept's identity moved::

    POST /ontology/concepts {"concept": "침입개념", "aliases": ["고객"]} -> 200
    canonicalize("고객")  before -> "고객"
    canonicalize("고객")  after  -> "침입개념"

**Eviction destroyed the shipped vocabulary.** The cap evicted
``next(iter(_CONCEPT_DEFINITIONS))``, and the dict is insertion-ordered with the
seed inserted first, so the oldest entry was always a seeded concept. Filling to
the cap of 500 destroyed 3 of the 5 seeded concepts ("고객", "활성 고객", "이탈")
and left 2.

**An invalid concept answered 500 and left a partial write.** The route wrote the
graph node first and registered the vocabulary second, so a ``ValueError`` from
registration escaped unmapped *after* the graph node existed::

    POST /ontology/concepts {"concept": "   "} -> ValueError out of the endpoint
"""

from __future__ import annotations

from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from sdp import ontology
from sdp.api import app
from sdp.graph_store import get_store


client = TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _isolate_vocabulary():
    """register_concept mutates module state shared by every read surface."""
    definitions = deepcopy(ontology._CONCEPT_DEFINITIONS)
    aliases = dict(ontology._ALIAS_TO_CANONICAL)
    patches = [patch.model_copy(deep=True) for patch in ontology._ONTOLOGY_PATCHES]
    try:
        yield
    finally:
        ontology._CONCEPT_DEFINITIONS.clear()
        ontology._CONCEPT_DEFINITIONS.update(definitions)
        ontology._ALIAS_TO_CANONICAL.clear()
        ontology._ALIAS_TO_CANONICAL.update(aliases)
        ontology._ONTOLOGY_PATCHES[:] = patches


def test_an_alias_cannot_take_over_a_concept_that_already_exists() -> None:
    seeded = sorted(ontology.SEEDED_CONCEPTS)
    assert "고객" in seeded, seeded
    before = ontology._canonicalize_concept("고객")

    hijack = client.post(
        "/ontology/concepts",
        json={"actor": "admin", "concept": "침입개념", "definition": "intruder", "aliases": ["고객"]},
    )
    assert hijack.status_code == 400, hijack.text
    assert "고객" in hijack.text and "already belongs to" in hijack.text

    assert ontology._canonicalize_concept("고객") == before == "고객"
    assert "침입개념" not in ontology._CONCEPT_DEFINITIONS


def test_an_alias_cannot_be_stolen_from_another_registered_concept() -> None:
    """Not only seeded concepts: ownership holds for anything already published."""
    first = client.post(
        "/ontology/concepts",
        json={"actor": "admin", "concept": "최초개념", "definition": "d", "aliases": ["공용별칭"]},
    )
    assert first.status_code == 200, first.text
    assert ontology._canonicalize_concept("공용별칭") == "최초개념"

    second = client.post(
        "/ontology/concepts",
        json={"actor": "admin", "concept": "나중개념", "definition": "d", "aliases": ["공용별칭"]},
    )
    assert second.status_code == 400, second.text
    assert ontology._canonicalize_concept("공용별칭") == "최초개념"


def test_a_concept_keeps_its_own_name_as_an_alias_without_conflicting() -> None:
    """The self-reference and a repeat of the same term must not read as a clash."""
    created = client.post(
        "/ontology/concepts",
        json={
            "actor": "admin",
            "concept": "자기참조개념",
            "definition": "d",
            "aliases": ["자기참조개념", "별칭하나"],
            "multilingual": ["별칭하나"],
        },
    )
    assert created.status_code == 200, created.text
    assert ontology._canonicalize_concept("별칭하나") == "자기참조개념"


def test_filling_the_vocabulary_never_evicts_a_seeded_concept() -> None:
    seeded = sorted(ontology.SEEDED_CONCEPTS)
    room = ontology.MAX_REGISTERED_CONCEPTS - len(ontology._CONCEPT_DEFINITIONS)
    for index in range(room + 3):
        ontology.register_concept(f"filler-{index}", definition="f")

    survived = sorted(c for c in seeded if c in ontology._CONCEPT_DEFINITIONS)
    assert survived == seeded, f"eviction destroyed {sorted(set(seeded) - set(survived))}"
    assert len(ontology._CONCEPT_DEFINITIONS) <= ontology.MAX_REGISTERED_CONCEPTS
    # The evicted entries' aliases go with them rather than pointing at a
    # concept the vocabulary no longer holds.
    for term, owner in ontology._ALIAS_TO_CANONICAL.items():
        assert owner in ontology._CONCEPT_DEFINITIONS, f"{term!r} -> missing {owner!r}"


def test_a_full_vocabulary_of_seeded_concepts_is_reported_not_overwritten() -> None:
    """When there is nothing caller-added to evict, the cap is reported."""
    ontology._CONCEPT_DEFINITIONS.clear()
    ontology._CONCEPT_DEFINITIONS.update(
        {concept: {"aliases": [], "multilingual": []} for concept in ontology.SEEDED_CONCEPTS}
    )
    original = dict(ontology._CONCEPT_DEFINITIONS)
    try:
        ontology.MAX_REGISTERED_CONCEPTS = len(ontology.SEEDED_CONCEPTS)
        with pytest.raises(ValueError) as refused:
            ontology.register_concept("한계초과개념", definition="d")
        assert "never evicted" in str(refused.value)
        assert dict(ontology._CONCEPT_DEFINITIONS) == original
    finally:
        ontology.MAX_REGISTERED_CONCEPTS = 500


@pytest.mark.parametrize(
    "concept",
    ["   ", "", "x" * (ontology.MAX_ONTOLOGY_PATCH_FIELD + 1)],
    ids=["whitespace", "empty", "over-long"],
)
def test_an_invalid_concept_is_refused_without_a_server_error(concept: str) -> None:
    response = client.post(
        "/ontology/concepts", json={"actor": "admin", "concept": concept, "definition": "d"}
    )
    assert response.status_code in (400, 422), response.text
    assert response.status_code != 500


def test_an_invalid_concept_leaves_no_graph_node_behind() -> None:
    """Validation runs before the first of the route's two writes.

    The graph node was written first, so an invalid concept left the node in the
    store while the request failed - a partial governed write with a 500.
    """
    store = get_store()
    before = store.stats()
    for invalid in ("   ", "y" * (ontology.MAX_ONTOLOGY_PATCH_FIELD + 1)):
        refused = client.post(
            "/ontology/concepts", json={"actor": "admin", "concept": invalid, "definition": "d"}
        )
        assert refused.status_code == 400, refused.text
        assert store.get_node(invalid) is None, f"{invalid!r} was written to the graph store"
        assert store.get_node(invalid.strip()) is None
    assert store.stats() == before, "a refused upsert changed the graph store"


def test_an_approved_patch_that_cannot_publish_stays_proposed() -> None:
    """승인 must not be recorded without 노출.

    ``review_patch`` set the status first and published second, so a refusal from
    the registrar left the patch marked ``approved`` with nothing published and
    the caller holding an error - the exact break between 승인 and 노출 that the
    publication path exists to close.
    """
    proposed = client.post(
        "/ontology/patches",
        json={"actor": "analyst", "concept": "출판실패개념", "suggestion": "정의"},
    )
    assert proposed.status_code == 200, proposed.text
    patch_id = proposed.json()["id"]

    try:
        ontology.MAX_REGISTERED_CONCEPTS = len(ontology._CONCEPT_DEFINITIONS)
        ontology._CONCEPT_DEFINITIONS.clear()
        ontology._CONCEPT_DEFINITIONS.update(
            {concept: {"aliases": [], "multilingual": []} for concept in ontology.SEEDED_CONCEPTS}
        )
        ontology.MAX_REGISTERED_CONCEPTS = len(ontology.SEEDED_CONCEPTS)

        refused = client.post(
            f"/ontology/patches/{patch_id}/review",
            json={"actor": "admin", "decision": "approve"},
        )
        assert refused.status_code in (400, 409), refused.text
    finally:
        ontology.MAX_REGISTERED_CONCEPTS = 500

    still = [patch for patch in ontology._ONTOLOGY_PATCHES if patch.id == patch_id]
    assert still and still[0].status == "proposed", still
