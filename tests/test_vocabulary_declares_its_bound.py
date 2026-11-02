"""The concept vocabulary is bounded, and the counts it feeds say so.

``_CONCEPT_DEFINITIONS`` is capped at ``MAX_REGISTERED_CONCEPTS`` and
``_evict_one_registered_concept`` drops a published term to make room for a new
one. Measured before this contract: 714 accepted registrations left the
vocabulary at exactly 500, ``GET /ontology/version`` published
``concept_count: 500`` with no capacity, no withheld count and no truncation
flag, and the same payload DID publish ``change_log_capacity``,
``withheld_change_count`` and ``change_log_is_truncated`` for a different
container three keys away - so a reader who saw truncation disclosed there
would reasonably take ``concept_count`` for a complete figure.

The count also reaches ``GET /enterprise/evidence-pack``, where it is the
denominator of ``ontology_mapping_coverage`` and therefore of the
``saleability_gates.ontology_mapping_coverage`` verdict. The denominator is the
LIVE glossary, which is correct as that metric defines itself - an evicted term
is not in the glossary - so what was wrong is not the ratio but that nothing
let a reader tell a complete 500-term glossary from what is left of one.

The flag is derived from the counted eviction, never from ``len == capacity``.
That distinction is the whole point of the boundary test below: at exactly the
cap nothing has been evicted yet, and a flag derived from container shape would
publish a loss that did not happen - the artifact for which a previous draft in
this repository was withdrawn.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from sdp import ontology
from sdp.api import app


client = TestClient(app)


def _register(name: str) -> int:
    """Register one concept as the admin actor and return the status code."""
    return client.post(
        "/ontology/concepts",
        json={"concept": name, "definition": f"definition for {name}", "actor": "admin"},
    ).status_code


def _fill_to_the_cap() -> int:
    """Register concepts until the vocabulary is exactly full; return the count."""
    issued = 0
    while len(ontology._CONCEPT_DEFINITIONS) < ontology.MAX_REGISTERED_CONCEPTS:
        issued += 1
        assert _register(f"boundary_{issued:05d}") == 200
    return issued


def test_an_exactly_full_vocabulary_declares_no_loss() -> None:
    """At the cap, nothing has been evicted, so nothing may be reported as lost.

    This is the half a flag derived from ``len(vocabulary) == capacity`` gets
    wrong, and it gets it wrong in the direction this repository has already
    paid for once: it publishes a lower bound beside a withheld count of zero.
    """
    _fill_to_the_cap()
    body = client.get("/ontology/version").json()
    assert body["concept_count"] == ontology.MAX_REGISTERED_CONCEPTS
    assert body["concept_capacity"] == ontology.MAX_REGISTERED_CONCEPTS
    assert body["withheld_concept_count"] == 0
    assert body["concept_vocabulary_is_truncated"] is False


def test_the_vocabulary_publishes_the_exact_number_of_concepts_it_evicted() -> None:
    """One eviction per accepted registration past the cap, counted exactly."""
    _fill_to_the_cap()
    for index in range(7):
        assert _register(f"past_the_cap_{index:05d}") == 200

    body = client.get("/ontology/version").json()
    assert body["concept_count"] == ontology.MAX_REGISTERED_CONCEPTS
    assert body["withheld_concept_count"] == 7
    assert body["concept_vocabulary_is_truncated"] is True
    assert ontology.vocabulary_withheld_count() == 7


def test_reading_the_withheld_count_does_not_change_it() -> None:
    """The count is readable, not consumable.

    A monotonic total implemented with ``itertools.count`` has no
    read-without-advance - ``next()`` both returns and consumes - so every read
    of the published payload raised the loss by one on data that had not
    changed. Measured on that design: five reads of an unchanged saturated ring
    published 149, 150, 151, 152, 153.
    """
    _fill_to_the_cap()
    for index in range(3):
        assert _register(f"stable_{index:05d}") == 200

    reads = [ontology.vocabulary_withheld_count() for _ in range(5)]
    assert reads == [3, 3, 3, 3, 3], reads


def test_the_evidence_pack_denominator_says_what_set_it_was_computed_over() -> None:
    """The glossary coverage denominator carries the vocabulary's bound.

    ``ontology_mapping_coverage`` gates ``sdp.demo_smoke``'s ``ready`` flag and
    a saleability verdict at ``>= 0.7``. Its denominator is the live glossary,
    so a buyer reading the ratio needs to know the glossary is capped.
    """
    _fill_to_the_cap()
    for index in range(4):
        assert _register(f"pack_{index:05d}") == 200

    pack = client.get("/enterprise/evidence-pack").json()
    assert pack["glossary_concept_count"] == ontology.MAX_REGISTERED_CONCEPTS
    assert pack["glossary_concept_capacity"] == ontology.MAX_REGISTERED_CONCEPTS
    assert pack["withheld_glossary_concept_count"] == 4
    assert pack["glossary_is_truncated"] is True


def test_an_untruncated_glossary_says_nothing_was_withheld() -> None:
    """The seeded vocabulary is far below the cap, so the pack declares no loss."""
    pack = client.get("/enterprise/evidence-pack").json()
    assert pack["glossary_concept_count"] < ontology.MAX_REGISTERED_CONCEPTS
    assert pack["withheld_glossary_concept_count"] == 0
    assert pack["glossary_is_truncated"] is False
