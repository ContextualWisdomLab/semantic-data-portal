"""Two vocabulary writes said they published while publishing nothing.

An approval must not rewrite a shipped definition - the registrar returns the
stored record on purpose - and the audit ledger already says which happened
(``approved_without_publication``, ``upserted_without_publication``). The
**responses** did not. Measured at ``46e9156``::

    POST /ontology/patches {concept: 고객, suggestion: 개정 정의}      -> 200
    POST /ontology/patches/{id}/review {decision: approve}            -> 200
      status 'approved' · published_concept '고객' · concept_already_published True
      revision 1 -> 1 · content_digest unchanged
      audit result: 'approved_without_publication'

    POST /ontology/concepts {concept: 고객, definition: 다시 쓴 정의}   -> 200
      status 'upserted' · published_concept '고객' · already_published True
      revision 2 -> 2 · content_digest unchanged

So one request produced ``published_concept: 고객`` with nothing published, and
the honest label existed only in the ledger a curator does not read.

The same two routes also published **no version identity at all** and accepted
the documented pin token silently::

    POST /ontology/concepts {..., ontology_content_digest: 'deadbeef'*8} -> 200
      response keys: concept, concept_already_published, concept_validation,
                     published_concept, status          (no version, no digest)

``GET /ontology/search`` and ``POST /ontology/resolve`` enforce that same token
with 409 on a mismatch and 400 on a malformed one, and stamp the version they
answered from. A caller pinning "I believe the vocabulary is at digest X" before
writing got neither the enforcement nor the stamp.
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from sdp import ontology
from sdp.api import app


client = TestClient(app)

PUBLISHED_CONCEPT = "고객"


def _version() -> tuple[int, str]:
    body = client.get("/ontology/version").json()
    return body["ontology_revision"], body["content_digest"]


def _approve(concept: str, suggestion: str = "개정된 정의 문장입니다") -> dict[str, Any]:
    proposed = client.post(
        "/ontology/patches",
        json={"actor": "analyst", "concept": concept, "suggestion": suggestion},
    )
    assert proposed.status_code == 200, proposed.text
    reviewed = client.post(
        f"/ontology/patches/{proposed.json()['id']}/review",
        json={"actor": "admin", "decision": "approve", "comment": "승인"},
    )
    assert reviewed.status_code == 200, reviewed.text
    return reviewed.json()


def _upsert(concept: str, definition: str, **extra: Any) -> Any:
    body = {"actor": "admin", "concept": concept, "definition": definition}
    body.update(extra)
    return client.post("/ontology/concepts", json=body)


def test_the_two_labels_say_what_they_mean() -> None:
    """The strings are a published contract, so they are pinned as strings.

    Every other assertion in this file compares a response against these two
    constants, which makes it blind to the constants being **swapped**: a
    mutation that exchanged the two values left the whole file green, because
    both sides of every comparison moved together. A consumer switches on the
    literal, so the literal is what has to be right.
    """
    assert ontology.PUBLICATION_PUBLISHED == "published"
    assert ontology.PUBLICATION_EXISTING_KEPT == "existing_definition_kept"
    assert not ontology.PUBLICATION_EXISTING_KEPT.startswith("publish"), (
        "the label for a write that published nothing reads as a publication: "
        f"{ontology.PUBLICATION_EXISTING_KEPT!r}"
    )


def test_an_approval_that_publishes_nothing_does_not_claim_a_publication() -> None:
    """The response has to agree with the ledger it writes beside itself."""
    before = _version()
    body = _approve(PUBLISHED_CONCEPT)
    after = _version()

    assert after == before, ("the premise failed: the vocabulary changed", before, after)
    assert body["concept_already_published"] is True, body
    assert body["publication_status"] == ontology.PUBLICATION_EXISTING_KEPT, body
    assert body["published_concept"] is None, (
        "the response names a published concept while the vocabulary is unchanged: "
        f"{body['published_concept']!r}"
    )
    # The review itself still happened, and says so.
    assert body["status"] == "approved", body
    assert body["concept"] == PUBLISHED_CONCEPT, body


def test_an_approval_that_publishes_says_so() -> None:
    """The converse, or the label means nothing."""
    before = _version()
    body = _approve("승인 신규 개념", "승인으로 처음 게시되는 정의")
    after = _version()
    assert after != before, (before, after)
    assert body["concept_already_published"] is False, body
    assert body["publication_status"] == ontology.PUBLICATION_PUBLISHED, body
    assert body["published_concept"] == "승인 신규 개념", body


def test_an_upsert_of_an_existing_concept_does_not_claim_a_publication() -> None:
    """The sibling write had the same defect."""
    before = _version()
    response = _upsert(PUBLISHED_CONCEPT, "다시 쓴 정의입니다")
    assert response.status_code == 200, response.text
    body = response.json()
    assert _version() == before
    assert body["concept_already_published"] is True, body
    assert body["publication_status"] == ontology.PUBLICATION_EXISTING_KEPT, body
    assert body["published_concept"] is None, body


def test_an_upsert_of_a_new_concept_says_it_published() -> None:
    before = _version()
    response = _upsert("업서트 신규 개념", "처음 게시되는 정의입니다")
    assert response.status_code == 200, response.text
    body = response.json()
    assert _version() != before
    assert body["publication_status"] == ontology.PUBLICATION_PUBLISHED, body
    assert body["published_concept"] == "업서트 신규 개념", body


def test_both_writes_stamp_the_version_they_wrote_against() -> None:
    """The read routes stamp it; a writer needs it more, not less."""
    upserted = _upsert("스탬프 개념", "스탬프 확인용 정의").json()
    assert upserted["ontology_version"]["content_digest"], upserted
    assert upserted["ontology_version"]["ontology_revision"] >= 1, upserted

    reviewed = _approve("스탬프 승인 개념", "스탬프 확인용 승인 정의")
    assert reviewed["ontology_version"]["content_digest"], reviewed


def test_a_pin_naming_another_vocabulary_refuses_the_write() -> None:
    """409, the same answer the read routes give, instead of a silent 200."""
    stale = "0" * 64
    refused = _upsert("핀 개념", "핀 거부 확인용", ontology_content_digest=stale)
    assert refused.status_code == 409, refused.text
    assert ontology.published_concept_definition("핀 개념") is None, "the write was applied anyway"

    proposed = client.post(
        "/ontology/patches",
        json={"actor": "analyst", "concept": "핀 승인 개념", "suggestion": "핀 거부 확인용 제안"},
    )
    reviewed = client.post(
        f"/ontology/patches/{proposed.json()['id']}/review",
        json={
            "actor": "admin",
            "decision": "approve",
            "comment": "승인",
            "ontology_content_digest": stale,
        },
    )
    assert reviewed.status_code == 409, reviewed.text
    assert ontology.published_concept_definition("핀 승인 개념") is None


def test_a_malformed_pin_is_a_bad_request_not_a_conflict() -> None:
    """The two refusals mean different things, as the read routes already say."""
    refused = _upsert("형식 개념", "형식 확인용", ontology_content_digest="not-a-digest")
    assert refused.status_code == 400, refused.text


def test_a_matching_pin_lets_the_write_through() -> None:
    """A pin is a precondition, not a prohibition."""
    _revision, digest = _version()
    accepted = _upsert("일치 핀 개념", "일치하는 핀으로 쓰기", ontology_content_digest=digest)
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["publication_status"] == ontology.PUBLICATION_PUBLISHED


def test_the_ledger_keeps_its_own_verbs() -> None:
    """The audit rows were already honest; this repair must not disturb them."""
    _approve(PUBLISHED_CONCEPT)
    events = client.get("/audit/events?user=admin&limit=10").json()
    results = [event["result"] for event in events]
    assert "approved_without_publication" in results, results
    _upsert(PUBLISHED_CONCEPT, "또 다른 정의")
    events = client.get("/audit/events?user=admin&limit=10").json()
    assert "upserted_without_publication" in [event["result"] for event in events]
