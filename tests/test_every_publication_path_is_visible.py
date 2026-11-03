"""One of the two publication paths left the graph blind, and both misdated themselves.

**1. A steward-approved concept reached the vocabulary and the JSON-LD export but
wrote no graph node.** ``POST /ontology/concepts`` registers *and* mirrors
(``get_store().upsert_concept``); ``review_patch`` calls ``register_concept``
alone. Measured at ``2540775``, with the direct path in the same process as a
control::

    path A  POST /ontology/concepts "직접 업서트 개념"
      /ontology/concepts lists it        True
      GET /graph/nodes/<name>            200
      /graph/stats                       nodes 26 -> 27, concepts 5 -> 6

    path B  POST /ontology/patches + review approve "승인 경로 개념"
      /ontology/concepts lists it        True
      /ontology/vocabulary/jsonld        True
      GET /graph/nodes/<name>            404
      /graph/stats                       unchanged

So the **governed** path - the one with a proposer, a reviewer and a change-log
entry - produces a concept that ``/graph/nodes/{id}``, ``/graph/query``,
``POST /search/semantic`` and ``/graph/stats`` cannot see, while the
ungoverned direct upsert produces one they can.

**2. Both write routes published the version they replaced.** Their comments say
"the version this write produced" and the served OpenAPI says the response
"carries the version this write produced"; ``_ontology_version_stamp`` is called
*before* the write, which is right for the pin check and wrong for the stamp::

    /ontology/version before   revision 3  digest 07cac5a3…
    write response             revision 3  digest 07cac5a3…      <- the old one
    /ontology/version after    revision 4  digest 04193fcb…

    replaying the returned digest as ``ontology_content_digest``  -> 409

A caller who pins the digest it was just handed is refused by the very write
that handed it over. The pin check must stay before the write; only the stamp
moves after it.
"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from sdp.api import app


client = TestClient(app)

ADMIN = {"actor": "admin"}


def _stats() -> dict:
    return client.get("/graph/stats?user=admin").json()["stats"]


def _publish_directly(concept: str) -> dict:
    response = client.post(
        "/ontology/concepts",
        json={**ADMIN, "concept": concept, "definition": f"{concept}의 정의입니다"},
    )
    assert response.status_code == 200, response.text[:300]
    return response.json()


def _publish_through_review(concept: str) -> dict:
    proposed = client.post(
        "/ontology/patches",
        json={**ADMIN, "concept": concept, "suggestion": f"{concept}의 정의입니다"},
    )
    assert proposed.status_code == 200, proposed.text[:300]
    reviewed = client.post(
        f"/ontology/patches/{proposed.json()['id']}/review",
        json={**ADMIN, "decision": "approve", "comment": "승인합니다"},
    )
    assert reviewed.status_code == 200, reviewed.text[:300]
    return reviewed.json()


def test_both_publication_paths_leave_a_graph_node() -> None:
    """Derived over both paths, so a third one added later must satisfy it too."""
    for concept, publish in (
        ("직접 경로 개념", _publish_directly),
        ("승인 경로 개념", _publish_through_review),
    ):
        before = _stats()
        published = publish(concept)
        assert published.get("publication_status") == "published", published
        node = client.get(f"/graph/nodes/{concept}?user=admin")
        assert node.status_code == 200, (concept, node.status_code, node.text[:200])
        assert node.json()["kind"] == "concept", node.json()
        after = _stats()
        assert after["concepts"] == before["concepts"] + 1, (concept, before, after)
        assert after["nodes"] == before["nodes"] + 1, (concept, before, after)


def test_an_approved_concept_is_reachable_by_traversal_and_search() -> None:
    """The surfaces the invisible concept was missing from."""
    concept = "승인 탐색 개념"
    _publish_through_review(concept)

    traversal = client.post(
        "/graph/query", json={**ADMIN, "start_id": concept, "max_depth": 1}
    )
    assert traversal.status_code == 200, traversal.text[:200]

    search = client.post(
        "/search/semantic", json={**ADMIN, "query": concept, "limit": 20}
    )
    assert search.status_code == 200, search.text[:200]
    found = [hit["node_id"] for hit in search.json()["results"]]
    assert concept in found, found


def test_the_mirrored_node_carries_the_definition_the_vocabulary_holds() -> None:
    """A node written with an empty definition is a mirror of nothing.

    The direct route's own comment records this defect on its side - "a re-upsert
    that omitted ``definition`` left ``GET /ontology/term/{term}/graph`` …
    serving 고객 with ``definition: ''``" - and the mutation that blanked the new
    mirror's definition came back **green** until this test existed. So the
    assertion is the registrar's stored definition, not merely a non-empty one:
    the registrar keeps a shipped definition and discards a re-submission, and
    the node must agree with whichever it kept.
    """
    concept = "승인 정의 개념"
    _publish_through_review(concept)

    stored = client.get(f"/ontology/concept/{concept}?user=admin").json()
    node = client.get(f"/graph/nodes/{concept}?user=admin").json()
    graph_definition = node["properties"]["definition"]
    assert graph_definition, node
    assert graph_definition == stored["graph"]["definition"], (graph_definition, stored["graph"])

    # And a second approval that keeps the shipped definition must not blank it.
    again = client.post(
        "/ontology/patches",
        json={**ADMIN, "concept": concept, "suggestion": "다시 쓴 정의입니다"},
    )
    assert again.status_code == 200, again.text[:200]
    reviewed = client.post(
        f"/ontology/patches/{again.json()['id']}/review",
        json={**ADMIN, "decision": "approve", "comment": "두 번째 승인"},
    )
    assert reviewed.status_code == 200, reviewed.text[:200]
    after = client.get(f"/graph/nodes/{concept}?user=admin").json()
    assert after["properties"]["definition"] == graph_definition, (
        after["properties"]["definition"],
        graph_definition,
    )


def test_the_approved_concept_still_reaches_the_vocabulary_and_the_export() -> None:
    """The halves that already worked must not regress."""
    concept = "승인 내보내기 개념"
    _publish_through_review(concept)
    assert concept in client.get("/ontology/concepts").json()["concepts"]
    export = json.dumps(client.get("/ontology/vocabulary/jsonld").json(), ensure_ascii=False)
    assert concept in export


def test_a_write_publishes_the_version_it_produced() -> None:
    """The stamp must name the vocabulary the caller can now pin."""
    for concept, publish in (
        ("버전 직접 개념", _publish_directly),
        ("버전 승인 개념", _publish_through_review),
    ):
        before = client.get("/ontology/version").json()
        published = publish(concept)
        after = client.get("/ontology/version").json()
        stamp = published["ontology_version"]

        assert after["content_digest"] != before["content_digest"], (concept, before, after)
        assert stamp["content_digest"] == after["content_digest"], (concept, stamp, after)
        assert stamp["ontology_revision"] == after["ontology_revision"], (concept, stamp, after)


def test_the_digest_a_write_returns_can_be_pinned_immediately() -> None:
    """The sharp end: the caller pins what it was just handed."""
    first = _publish_directly("핀 재생 개념")
    digest = first["ontology_version"]["content_digest"]
    replay = client.post(
        "/ontology/concepts",
        json={
            **ADMIN,
            "concept": "핀 재생 확인 개념",
            "definition": "돌려받은 digest를 그대로 pin으로 보냅니다",
            "ontology_content_digest": digest,
        },
    )
    assert replay.status_code == 200, (replay.status_code, replay.text[:300])


def test_a_stale_pin_is_still_refused_before_anything_is_written() -> None:
    """Moving the stamp must not move the check."""
    before = client.get("/ontology/version").json()
    stale = "0" * 64
    refused = client.post(
        "/ontology/concepts",
        json={
            **ADMIN,
            "concept": "거부되어야 하는 개념",
            "definition": "낡은 pin으로 보낸 쓰기입니다",
            "ontology_content_digest": stale,
        },
    )
    assert refused.status_code == 409, (refused.status_code, refused.text[:200])
    assert client.get("/ontology/version").json() == before
    assert "거부되어야 하는 개념" not in client.get("/ontology/concepts").json()["concepts"]
    assert client.get("/graph/nodes/거부되어야 하는 개념?user=admin").status_code == 404
