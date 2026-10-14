"""ONT-004: the ontology has a version, a change log, and a reviewer record.

Before this, the concept vocabulary was a module-level Python dict with no
release identity. Three published claims were wrong at once:

* ``ONT-004`` ("OWL/RDFS 기반 도메인 ontology를 버전관리해야 한다", ACCEPT
  "ontology version, change log, reviewer 기록") was recorded
  ``not_implemented`` - correctly, there was nothing;
* the ``rdf_connector`` control ``ontology_version_pin`` was simultaneously
  reported ``status: implemented`` / ``verification: proof_route_served`` with
  proof endpoints ``/ontology/search`` and ``/ontology/resolve``, and measured,
  neither response contained the string "version" anywhere;
* the only reviewer identity anywhere was ``OntologyPatch.reviewed_by``, which
  exists on the patch path only. ``POST /ontology/concepts`` published into the
  shared vocabulary with no review record, and its one audit row says
  ``result: "authorized"`` and is written **before** the mutation - measured, an
  alias-hijack POST answered 400, published nothing, and left that identical
  "authorized" row.

Reverse-verified: removing the ``already_published`` guard from the recording
call makes ``test_republishing_an_existing_concept_records_no_change`` fail;
recording the change before the vocabulary write instead of after makes
``test_the_entrys_digest_is_the_content_the_revision_names`` fail; dropping the
``REVIEWED_SOURCES`` check makes
``test_a_source_with_no_review_cannot_name_a_reviewer`` fail.
"""

from __future__ import annotations

import threading

import pytest
from fastapi.testclient import TestClient

from sdp import ontology, ontology_version
from sdp.api import app


client = TestClient(app, raise_server_exceptions=False)


def _identity() -> dict:
    return ontology.ontology_version_identity()


# --------------------------------------------------------------- identity ---


def test_the_shipped_vocabulary_is_a_nameable_revision() -> None:
    """The baseline is revision 1, not 0: a reader must be able to name it."""
    identity = _identity()
    assert identity["ontology_revision"] == ontology_version.BASELINE_REVISION == 1
    assert identity["baseline_revision"] == 1
    assert identity["concept_count"] == len(ontology.list_concepts())


def test_the_revision_declares_that_it_does_not_survive_a_restart() -> None:
    """Otherwise ``revision 7`` reads as a release number, which it is not.

    The vocabulary is in-memory state lost on restart, so the revision is
    process-local. The digest is the part that identifies content across
    processes, and the pair is published with the limitation named.
    """
    identity = _identity()
    assert identity["revision_is_durable"] is False
    assert identity["revision_scope"] == "process_lifetime"
    assert identity["digest_algorithm"] == "sha256"
    assert len(identity["content_digest"]) == 64


def test_the_digest_is_independent_of_dict_ordering() -> None:
    """Two deployments holding the same concepts must agree on the digest."""
    live = ontology.concept_vocabulary_snapshot()
    reversed_order = dict(reversed(list(live.items())))
    assert ontology_version.vocabulary_content_digest(
        live
    ) == ontology_version.vocabulary_content_digest(reversed_order)


def test_the_digest_is_a_semantic_identity_not_a_serialization_checksum() -> None:
    """Reordering a concept's aliases is not a version change.

    ``skos:altLabel``, ``skos:narrower`` and ``skos:related`` are unordered in
    meaning, and the alias index treats one concept's aliases as a set. Digesting
    the raw lists made two deployments holding the same vocabulary report
    different versions - and a client pinning the digest would be refused over a
    difference with no meaning. Adding or removing a member still moves it.
    """
    live = ontology.concept_vocabulary_snapshot()
    digest = ontology_version.vocabulary_content_digest(live)

    for field in ontology_version._UNORDERED_RECORD_FIELDS:
        shuffled = {concept: dict(record) for concept, record in live.items()}
        moved = False
        for record in shuffled.values():
            if isinstance(record.get(field), list) and len(record[field]) > 1:
                record[field] = list(reversed(record[field]))
                moved = True
        if not moved:
            continue
        assert (
            ontology_version.vocabulary_content_digest(shuffled) == digest
        ), f"reordering {field} changed the version"

    added = {concept: dict(record) for concept, record in live.items()}
    added["고객"]["aliases"] = list(added["고객"]["aliases"]) + ["추가된별칭"]
    assert ontology_version.vocabulary_content_digest(added) != digest

    edited = {concept: dict(record) for concept, record in live.items()}
    edited["고객"]["definition"] = "다른 정의"
    assert ontology_version.vocabulary_content_digest(edited) != digest


def test_the_revision_declares_that_its_arithmetic_is_not_content_distance() -> None:
    """A publish and an eviction move the number by two and the content nowhere.

    So a reader must not subtract revisions to measure how far a vocabulary
    moved. The identity is the digest; the revision orders the log.
    """
    identity = _identity()
    assert "content_digest" in identity["revision_comparison_note"]
    assert "recorded changes" in identity["revision_comparison_note"]


def test_the_change_log_declares_that_an_actor_name_is_a_claim() -> None:
    """``actor_id`` comes from the request body.

    The policy engine checks it against the subject table, so it is an
    *authorized* identity; this product has no end-user authentication on the
    write path. A reader must not take a name in the ledger for a proven one.
    """
    log = ontology.vocabulary_change_log(limit=1)
    assert log["actor_identity_basis"] == "authorized_subject_claim"


def test_the_digest_changes_when_the_vocabulary_changes() -> None:
    """A content identity that does not move with the content is decorative."""
    before = _identity()["content_digest"]
    ontology.register_concept(
        "버전확인개념", change_source="concept_upsert", definition="d", actor_id="admin"
    )
    assert _identity()["content_digest"] != before


def test_a_vocabulary_mutated_outside_the_versioned_path_is_reported() -> None:
    """The self-check that makes the digest worth publishing.

    The digest is recomputed from live content rather than cached, so the
    recorded digest and the live one can be compared. They differ exactly when
    something changed the vocabulary without recording a revision, and that is
    a defect this surface reports rather than hides.
    """
    assert _identity()["digest_matches_recorded_revision"] is True
    ontology._CONCEPT_DEFINITIONS["밀수개념"] = {
        "aliases": [],
        "broader": None,
        "narrower": [],
        "related": [],
        "definition": "",
        "multilingual": [],
    }
    identity = _identity()
    assert identity["digest_matches_recorded_revision"] is False
    assert identity["content_digest"] != identity["recorded_content_digest"]


# ------------------------------------------------------------ change log ----


def test_publishing_a_concept_advances_the_revision_and_logs_it() -> None:
    before = _identity()["ontology_revision"]
    ontology.register_concept(
        "기록확인개념", change_source="concept_upsert", definition="d", actor_id="admin"
    )
    identity = _identity()
    assert identity["ontology_revision"] == before + 1
    newest = ontology.vocabulary_change_log(limit=1)["changes"][0]
    assert newest["change_revision"] == before + 1
    assert newest["change_kind"] == "concept_published"
    assert newest["change_source"] == "concept_upsert"
    assert newest["concept_name"] == "기록확인개념"
    assert newest["actor_id"] == "admin"


def test_republishing_an_existing_concept_records_no_change() -> None:
    """A no-op must not create history.

    ``register_concept`` on an already-published concept changes nothing - it
    discards the whole submitted payload and returns the stored record - so
    advancing the revision for it would publish a change that did not happen.
    This is the same guard the empty-``PATCH`` and already-deprecated paths in
    ``catalog`` carry.
    """
    ontology.register_concept(
        "중복확인개념", change_source="concept_upsert", definition="first", actor_id="admin"
    )
    after_first = _identity()
    again = ontology.register_concept(
        "중복확인개념", change_source="concept_upsert", definition="second", actor_id="admin"
    )
    assert again["already_published"] is True
    assert _identity()["ontology_revision"] == after_first["ontology_revision"]
    assert _identity()["change_log_entry_count"] == after_first["change_log_entry_count"]


def test_the_entrys_digest_is_the_content_the_revision_names() -> None:
    """Recorded after the writes, so the digest is the published content.

    Recorded before them, the entry would claim a digest the vocabulary does
    not have, and a mutation that then failed would leave a revision describing
    content that was never published.
    """
    ontology.register_concept(
        "digest확인개념", change_source="concept_upsert", definition="d", actor_id="admin"
    )
    newest = ontology.vocabulary_change_log(limit=1)["changes"][0]
    assert newest["content_digest"] == _identity()["content_digest"]


def test_the_change_log_is_newest_first() -> None:
    for index in range(3):
        ontology.register_concept(
            f"순서개념-{index}", change_source="concept_upsert", actor_id="admin"
        )
    revisions = [
        entry["change_revision"] for entry in ontology.vocabulary_change_log(limit=3)["changes"]
    ]
    assert revisions == sorted(revisions, reverse=True)


def test_the_change_log_is_bounded_and_declares_what_it_dropped() -> None:
    """Process-lifetime state is bounded here like every other store.

    A short log that does not say it is short reads as the whole history.
    """
    capacity = ontology_version.MAX_ONTOLOGY_CHANGE_LOG_ENTRIES
    assert _identity()["change_log_is_truncated"] is False
    for index in range(capacity + 5):
        ontology.register_concept(
            f"상한개념-{index}", change_source="concept_upsert", actor_id="admin"
        )
    identity = _identity()
    assert identity["change_log_entry_count"] == capacity
    assert identity["change_log_is_truncated"] is True
    assert identity["withheld_change_count"] > 0


def test_an_eviction_is_recorded_as_its_own_revision() -> None:
    """The deletion nobody asked for, which used to leave no trace at all.

    At the vocabulary cap a published term leaves the ontology as a side effect
    of an unrelated caller's successful registration. The only evidence was its
    absence: no audit row, no caller, nothing in any ledger. It is now one
    revision of its own, ordered before the publication that forced it.
    """
    while len(ontology._CONCEPT_DEFINITIONS) < ontology.MAX_REGISTERED_CONCEPTS:
        ontology.register_concept(
            f"퇴출채움-{len(ontology._CONCEPT_DEFINITIONS)}",
            change_source="concept_upsert",
            actor_id="admin",
        )
    before = _identity()["ontology_revision"]
    ontology.register_concept(
        "퇴출유발개념", change_source="concept_upsert", actor_id="admin"
    )
    identity = _identity()
    assert identity["ontology_revision"] == before + 2
    page = ontology.vocabulary_change_log(limit=2)["changes"]
    publication, eviction = page[0], page[1]
    assert publication["change_kind"] == "concept_published"
    assert eviction["change_kind"] == "concept_evicted"
    assert eviction["change_source"] == "cap_eviction"
    assert eviction["change_revision"] + 1 == publication["change_revision"]
    assert eviction["reviewer_id"] is None
    assert eviction["review_basis"] == "capacity_policy"
    # Not someone who asked for a deletion.
    assert eviction["actor_role"] == "eviction_trigger"


# ------------------------------------------------------- reviewer record ----


def test_a_direct_upsert_names_no_reviewer_and_says_why() -> None:
    """Nobody reviewed it, so no steward is named.

    ``catalog.deprecate_dataset`` used to default ``reason`` to ``"deprecated"``
    and so reported a reason the caller never gave; the same rule applies to a
    reviewer. ``review_basis`` says in words that this path carries no review,
    rather than leaving a null reviewer to read as an omission.
    """
    response = client.post(
        "/ontology/concepts",
        json={"actor": "admin", "concept": "직접등록개념", "definition": "d"},
    )
    assert response.status_code == 200
    newest = ontology.vocabulary_change_log(limit=1)["changes"][0]
    assert newest["concept_name"] == "직접등록개념"
    assert newest["actor_id"] == "admin"
    assert newest["actor_role"] == "publisher"
    assert newest["reviewer_id"] is None
    assert newest["review_basis"] == "direct_admin_upsert"


def test_an_approved_patch_records_both_the_proposer_and_the_reviewer() -> None:
    """The 제안 -> 승인 workflow, with both halves attributable."""
    proposed = client.post(
        "/ontology/patches",
        json={"actor": "analyst", "concept": "검토기록개념", "suggestion": "정의 제안"},
    )
    assert proposed.status_code == 200
    patch_id = proposed.json()["id"]
    reviewed = client.post(
        f"/ontology/patches/{patch_id}/review",
        json={"actor": "admin", "decision": "approve", "comment": "승인합니다"},
    )
    assert reviewed.status_code == 200
    newest = ontology.vocabulary_change_log(limit=1)["changes"][0]
    assert newest["concept_name"] == "검토기록개념"
    assert newest["change_source"] == "patch_approval"
    assert newest["actor_id"] == "analyst"
    # Not the publisher: the actor proposed it, the reviewer authorized it.
    assert newest["actor_role"] == "proposer"
    assert newest["reviewer_id"] == "admin"
    assert newest["review_basis"] == "patch_review"


def test_the_actor_column_says_which_role_the_actor_held() -> None:
    """``actor_id`` does not mean the same thing on every source.

    On a direct upsert the actor published the concept; on an approved patch the
    actor *proposed* it and the person who authorized publication is in
    ``reviewer_id``. A reader scanning one column for "who put this in the
    ontology" would answer that wrongly for every approval, so each entry names
    its actor's role and the open version surface publishes the whole mapping.
    """
    assert ontology_version.ACTOR_ROLES == {
        "seed": None,
        "concept_upsert": "publisher",
        "patch_approval": "proposer",
        "cap_eviction": "eviction_trigger",
    }
    # Every source the recorder accepts has a declared role, derived from the
    # source vocabulary rather than listed twice.
    assert set(ontology_version.ACTOR_ROLES) == set(ontology_version.CHANGE_SOURCES)
    assert _identity()["actor_roles_by_change_source"] == ontology_version.ACTOR_ROLES


def test_a_concept_can_outlive_its_patch_but_not_its_change_entry() -> None:
    """Why the change log is net-new state and not a re-read of the patch queue.

    The patch queue is FIFO-evicted, so the reviewed patch that published a
    concept can be gone while the concept is still served - the reviewer record
    disappears from under a live term. The change log is bounded too, but it is
    bounded separately and declares its truncation, so the approval is not lost
    the moment 500 further proposals arrive.
    """
    proposed = client.post(
        "/ontology/patches",
        json={"actor": "analyst", "concept": "장수개념", "suggestion": "정의"},
    )
    patch_id = proposed.json()["id"]
    client.post(
        f"/ontology/patches/{patch_id}/review",
        json={"actor": "admin", "decision": "approve"},
    )
    for index in range(ontology.MAX_ONTOLOGY_PATCHES + 1):
        ontology.propose_patch(f"밀어내기-{index}", "s", requestor="analyst")
    assert not [
        patch for patch in ontology.list_patches() if patch["id"] == patch_id
    ], "the reviewed patch survived, so this test no longer measures what it claims"
    assert "장수개념" in ontology.list_concepts()
    entries = ontology.vocabulary_change_log(limit=500)["changes"]
    assert any(
        entry["concept_name"] == "장수개념" and entry["reviewer_id"] == "admin"
        for entry in entries
    )


def test_a_source_with_no_review_cannot_name_a_reviewer() -> None:
    """Refused, not dropped: the caller is told rather than silently corrected."""
    with pytest.raises(ValueError, match="carries no review"):
        ontology_version.record_vocabulary_change(
            change_kind="concept_published",
            change_source="concept_upsert",
            concept_name="위조검토개념",
            vocabulary=ontology.concept_vocabulary_snapshot(),
            actor_id="admin",
            reviewer_id="없는심사자",
        )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"change_kind": "concept_invented", "change_source": "concept_upsert"},
        {"change_kind": "concept_published", "change_source": "nowhere"},
        {"change_kind": "baseline", "change_source": "seed"},
    ],
    ids=["unknown-kind", "unknown-source", "baseline-is-not-callable-here"],
)
def test_the_change_vocabulary_is_closed(kwargs: dict) -> None:
    """An unknown kind or source would record a change nobody can interpret."""
    with pytest.raises(ValueError):
        ontology_version.record_vocabulary_change(
            concept_name="어휘검사개념",
            vocabulary=ontology.concept_vocabulary_snapshot(),
            **kwargs,
        )


def test_there_is_no_update_event_because_there_is_no_update_operation() -> None:
    """The absence is declared rather than left as a silent omission.

    A re-publication of an existing concept is a no-op, not an edit, so nothing
    anywhere can change a published concept's definition. A change log
    publishing an ``updated`` kind would imply an operation the product does
    not have.
    """
    assert ontology_version.CHANGE_KINDS == (
        "baseline",
        "concept_published",
        "concept_evicted",
    )
    assert "concept_updated" not in _identity()["known_change_kinds"]


# ----------------------------------------------------------- concurrency ----


class _PausingVocabulary(dict):
    """A vocabulary that suspends the first reader between its read and its write.

    The critical section in ``_register_concept_locked`` - the existence read,
    then the store write nineteen lines later - contains no I/O and no
    GIL-releasing call, so under CPython the window does not open on its own:
    400 trials with a thread barrier and a 1e-9 switch interval produced zero
    interleavings. A test that cannot open the window cannot show the lock doing
    anything, so the suspension is forced *inside the read itself* rather than
    hoped for. ``get`` is the method the existence check uses.
    """

    def __init__(self, source: dict, *, pause_for: str) -> None:
        super().__init__(source)
        self._pause_for = pause_for
        self.reader_is_parked = threading.Event()
        self._release_reader = threading.Event()
        self._already_paused = False

    def get(self, key, default=None):  # type: ignore[override]
        result = super().get(key, default)
        if key == self._pause_for and not self._already_paused:
            self._already_paused = True
            self.reader_is_parked.set()
            self._release_reader.wait(timeout=5)
        return result

    def release_reader(self) -> None:
        self._release_reader.set()


def test_two_concurrent_publications_of_one_concept_produce_one_revision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The read-modify-write window the lock closes.

    ``register_concept`` reads the vocabulary to decide new-versus-no-op and
    writes well after. Unsynchronised, two concurrent registrations of one
    concept both read ``None``, both answer ``already_published: False``, and
    both record a revision - two acknowledged publications and two revisions for
    one dict entry. With the lock the second writer cannot enter until the first
    has finished, so it sees the concept and reports it already published.

    Reverse-verified: replacing ``with ontology_version.vocabulary_change_lock()``
    in ``register_concept`` with ``if True`` makes this fail with two
    ``already_published: False`` rows and the revision advancing by two.
    """
    paused = _PausingVocabulary(ontology._CONCEPT_DEFINITIONS, pause_for="경쟁개념")
    monkeypatch.setattr(ontology, "_CONCEPT_DEFINITIONS", paused)

    results: list[dict] = []
    errors: list[BaseException] = []

    def publish() -> None:
        try:
            results.append(
                ontology.register_concept(
                    "경쟁개념", change_source="concept_upsert", actor_id="admin"
                )
            )
        except BaseException as exc:  # pragma: no cover - reported, not swallowed
            errors.append(exc)

    before = ontology_version.ontology_version_identity(paused)["ontology_revision"]
    first = threading.Thread(target=publish, name="first-writer")
    first.start()
    # The first writer is now parked *inside* its existence read, before its
    # write. Without the lock the second writer would walk straight past it.
    assert paused.reader_is_parked.wait(timeout=5), "the read was never reached"
    second = threading.Thread(target=publish, name="second-writer")
    second.start()
    # Give the second writer time to overtake if nothing is holding it back,
    # then let the first one finish.
    second.join(timeout=0.5)
    paused.release_reader()
    first.join(timeout=10)
    second.join(timeout=10)

    assert not errors, errors
    assert len(results) == 2, results
    assert sum(1 for row in results if row["already_published"] is False) == 1, results
    assert sum(1 for row in results if row["already_published"] is True) == 1, results
    identity = ontology_version.ontology_version_identity(paused)
    assert identity["ontology_revision"] == before + 1
    entries = [
        entry
        for entry in ontology_version.vocabulary_change_log(limit=10)["changes"]
        if entry["concept_name"] == "경쟁개념"
    ]
    assert len(entries) == 1, entries
