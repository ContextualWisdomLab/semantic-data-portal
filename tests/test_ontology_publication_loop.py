"""제안 → 승인 → 노출: the documented loop stopped at 승인.

There were two disconnected concept stores. ``POST /ontology/concepts`` wrote to
the graph store, while ``/ontology/search``, ``/ontology/resolve``,
``/ontology/concept/{term}`` and ``GET /ontology/concepts`` all read the
module-level vocabulary. Measured before the repair, after a **successful**
upsert::

    POST /ontology/concepts        -> 200
    GET  /graph/nodes/<term>       -> 200      (the node really was written)
    GET  /ontology/search?q=<term> -> count=0
    POST /ontology/resolve         -> resolved=[]
    GET  /ontology/concepts        -> does not contain it

And approving a patch did not call that write path at all, so no documented
route loaded an approved term into the read surface::

    POST /ontology/patches               -> 200
    POST /ontology/patches/<id>/review   -> 200  status=approved
    GET  /ontology/search?q=<term>       -> count=0   (unchanged)

Note on a false positive in the first pass of this investigation: probing with
``term in response.text`` reported the term as present on ``/ontology/search``,
because that route echoes the query string back in its ``query`` field. The
matches list was empty. The assertions here read ``matches``/``resolved``, never
the raw body.

Durability limit, stated because it is real: the vocabulary is process-lifetime
module state, so a published concept is lost on restart - exactly as the
in-memory evidence store and graph defaults are. Durable publication needs a
store-backed read path, which would mean extending the abstract ``GraphStore``
surface and its Postgres implementation; that is deliberately not attempted here
rather than shipped untested.
"""

from __future__ import annotations

from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from sdp import ontology
from sdp.api import app


client = TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _isolate_vocabulary():
    """register_concept mutates module state; a leak would reach every later test."""
    definitions = deepcopy(ontology._CONCEPT_DEFINITIONS)
    aliases = dict(ontology._ALIAS_TO_CANONICAL)
    patches = [patch.model_copy(deep=True) for patch in ontology._ONTOLOGY_PATCHES]
    yield
    ontology._CONCEPT_DEFINITIONS.clear()
    ontology._CONCEPT_DEFINITIONS.update(definitions)
    ontology._ALIAS_TO_CANONICAL.clear()
    ontology._ALIAS_TO_CANONICAL.update(aliases)
    ontology._ONTOLOGY_PATCHES[:] = patches


def _search(term: str) -> list[str]:
    body = client.get("/ontology/search", params={"q": term}).json()
    return [match["concept"] for match in body["matches"]]


def _resolved(text: str) -> list[str]:
    body = client.post("/ontology/resolve", json={"text": text}).json()
    return [item["term"] for item in body["resolved"]]


def test_approving_a_patch_publishes_the_term_to_every_read_surface() -> None:
    term = "승인노출검증용어"
    assert _search(term) == []

    proposed = client.post(
        "/ontology/patches",
        json={"actor": "analyst", "concept": term, "suggestion": "검증용 정의입니다"},
    )
    assert proposed.status_code == 200, proposed.text
    patch_id = proposed.json()["id"]
    assert _search(term) == [], "a proposal alone must not publish anything"

    reviewed = client.post(
        f"/ontology/patches/{patch_id}/review",
        json={"actor": "admin", "decision": "approve", "comment": "ok"},
    )
    assert reviewed.status_code == 200, reviewed.text
    body = reviewed.json()
    assert body["status"] == "approved"
    # The response says what was published rather than leaving the caller to look.
    assert body["published_concept"] == term
    assert body["concept_already_published"] is False

    assert _search(term) == [term]
    assert term in client.get("/ontology/concepts").json()["concepts"]
    assert _resolved(f"{term} 관련 질문") == [term]
    detail = client.get(f"/ontology/concept/{term}").json()
    assert detail["graph"].get("not_found") is None
    assert detail["graph"]["definition"] == "검증용 정의입니다"


def test_rejecting_a_patch_publishes_nothing() -> None:
    term = "거부된용어"
    patch_id = client.post(
        "/ontology/patches",
        json={"actor": "analyst", "concept": term, "suggestion": "정의"},
    ).json()["id"]
    reviewed = client.post(
        f"/ontology/patches/{patch_id}/review",
        json={"actor": "admin", "decision": "reject", "comment": "no"},
    ).json()
    assert reviewed["status"] == "rejected"
    assert "published_concept" not in reviewed
    assert _search(term) == []
    assert term not in client.get("/ontology/concepts").json()["concepts"]


def test_a_concept_upsert_reaches_the_read_surfaces_and_the_graph() -> None:
    term = "직접등록검증용어"
    created = client.post(
        "/ontology/concepts",
        json={"actor": "admin", "concept": term, "definition": "직접 정의", "aliases": ["directalias"]},
    )
    assert created.status_code == 200, created.text
    assert created.json()["published_concept"] == term

    assert _search(term) == [term]
    assert _search("directalias") == [term], "an alias must canonicalize to the concept"
    assert term in client.get("/ontology/concepts").json()["concepts"]
    # The graph node and its embedding are still written - both stores, not one.
    assert client.get(f"/graph/nodes/{term}", params={"actor": "admin"}).status_code == 200


def test_approval_does_not_overwrite_an_already_published_definition() -> None:
    """An approval must not silently rewrite a shipped definition."""
    existing = "고객"
    original = deepcopy(ontology._CONCEPT_DEFINITIONS[existing])

    patch_id = client.post(
        "/ontology/patches",
        json={"actor": "analyst", "concept": existing, "suggestion": "완전히 다른 정의"},
    ).json()["id"]
    body = client.post(
        f"/ontology/patches/{patch_id}/review",
        json={"actor": "admin", "decision": "approve", "comment": "ok"},
    ).json()

    assert body["status"] == "approved"
    assert body["concept_already_published"] is True
    assert ontology._CONCEPT_DEFINITIONS[existing] == original, (
        "an approval rewrote a shipped definition"
    )


def test_the_published_vocabulary_is_bounded() -> None:
    """Process-lifetime state must not grow without limit."""
    for index in range(ontology.MAX_REGISTERED_CONCEPTS + 10):
        ontology.register_concept(
            f"bounded_concept_{index}", change_source="concept_upsert", definition="d"
        )
    assert len(ontology._CONCEPT_DEFINITIONS) <= ontology.MAX_REGISTERED_CONCEPTS


def test_an_empty_concept_is_refused() -> None:
    with pytest.raises(ValueError):
        ontology.register_concept("   ", change_source="concept_upsert")
