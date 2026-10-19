"""A graph node's kind cannot be changed, because changing it destroyed the node.

``upsert_node`` built a fresh ``GraphNode`` and stored it over whatever was
there, so a write under an id another kind already held replaced it outright.
Measured on the seed, with one authorized request::

    GET  /graph/nodes/crm-customer-master   kind=dataset
        label='고객 마스터'
        properties={domain, owner, steward, tags, terms,
                    sensitivity: 'medium', status: 'published'}

    POST /ontology/concepts {"actor": "admin",
                             "concept": "crm-customer-master",
                             "definition": "...", "broader": "고객"}
        -> 200

    GET  /graph/nodes/crm-customer-master   kind=concept
        label='crm-customer-master'
        properties={definition, aliases, multilingual}

So an ontology write silently erased a dataset's classification - ``sensitivity``,
``owner``, ``steward``, ``status`` - which is exactly the metadata the tenant
boundary and the masking obligations reason about, and which ``/search/semantic``
and ``/graph/query`` serve. The tenant half of this boundary was closed earlier
(``_authorize_graph_write`` resolves the target tenant, so a foreign admin cannot
write a node it cannot read); this is the kind half, and it was open to any
authorized writer.

The rule is deliberately **not** a kind allow-list. ``kind`` stays free-form, so
a caller may still introduce a new kind and the injection-regression tests that
pass a hostile string as a kind keep working. What is refused is *reclassifying*
an id that already exists as something else - which refuses the destruction and
nothing legitimate, because a same-kind upsert is how the catalog mirror, the
seed and concept re-registration all work.

Reverse-verified: removing the ``assert_node_kind_is_stable`` call from
``InMemoryGraphStore.upsert_node`` fails every test here that asserts a refusal,
and the dataset node's properties come back as the concept's three keys.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from sdp import ontology
from sdp.api import app
from sdp.graph_store import InMemoryGraphStore


client = TestClient(app, raise_server_exceptions=False)

SEEDED_DATASET = "crm-customer-master"


def _node(node_id: str) -> dict:
    body = client.get(f"/graph/nodes/{node_id}", params={"user": "admin"}).json()
    return body.get("node", body)


# ------------------------------------------------------ the store invariant --


def test_the_store_refuses_a_kind_change() -> None:
    store = InMemoryGraphStore()
    store.upsert_node("보존대상", "dataset", label="원래 라벨", properties={"sensitivity": "high"})
    with pytest.raises(ValueError, match="kind"):
        store.upsert_node("보존대상", "concept", label="덮어쓴 라벨")
    kept = store.get_node("보존대상")
    assert kept is not None
    assert kept.kind == "dataset"
    assert kept.label == "원래 라벨"
    assert kept.properties == {"sensitivity": "high"}


def test_the_store_still_accepts_a_same_kind_update() -> None:
    """A same-kind upsert is how the catalog mirror and the seed both work."""
    store = InMemoryGraphStore()
    store.upsert_node("갱신대상", "dataset", label="처음", properties={"status": "draft"})
    store.upsert_node("갱신대상", "dataset", label="나중", properties={"status": "published"})
    updated = store.get_node("갱신대상")
    assert updated is not None
    assert updated.label == "나중"
    assert updated.properties == {"status": "published"}


def test_a_new_node_may_carry_any_kind() -> None:
    """Not a kind allow-list: free-form kinds still work for a new id.

    The graph security suite passes a SQL-injection string as a ``kind`` to
    check it is bound as a parameter; an enum would have broken that test and
    the invariant it protects.
    """
    store = InMemoryGraphStore()
    for kind in ("dataset", "column", "concept", "service", "'; DROP TABLE x; --"):
        node = store.upsert_node(f"종류-{kind[:6]}", kind)
        assert node.kind == kind


def test_the_invariant_lives_on_the_store_base_so_both_backends_carry_it() -> None:
    """The in-memory and Postgres stores would otherwise drift.

    The Postgres implementation reads the stored kind **inside** its write
    transaction with ``FOR UPDATE`` rather than calling the shared helper, which
    would open its own connection and leave a window between the check and the
    upsert. The helper is on the base so the rule has one statement of itself.
    """
    from sdp import graph_store as module

    assert hasattr(module.GraphStore, "assert_node_kind_is_stable")
    source = module.__file__
    with open(source, encoding="utf-8") as handle:
        text = handle.read()
    assert "assert_node_kind_is_stable(node_id, kind)" in text
    assert "FOR UPDATE" in text


# ------------------------------------------------------------ the routes ----


def test_a_concept_named_after_an_existing_dataset_is_refused() -> None:
    """The measured destruction, through the route that caused it."""
    before = _node(SEEDED_DATASET)
    assert before["kind"] == "dataset"
    assert before["properties"]["sensitivity"] == "medium"

    response = client.post(
        "/ontology/concepts",
        json={"actor": "admin", "concept": SEEDED_DATASET, "definition": "정의", "broader": "고객"},
    )
    assert response.status_code == 409, response.text
    assert "kind" in response.json()["detail"]

    after = _node(SEEDED_DATASET)
    assert after["kind"] == "dataset"
    assert after["label"] == before["label"]
    assert after["properties"] == before["properties"]


def test_a_refused_concept_upsert_leaves_no_trace_in_the_vocabulary() -> None:
    """The store write runs before the vocabulary write, so a refusal is clean.

    Were the order reversed, the concept would be published to every read
    surface while the graph refused it - the two stores disagreeing permanently,
    which is the defect ``register_concept`` was wired into this route to close.
    """
    before_revision = ontology.ontology_version_identity()["ontology_revision"]
    response = client.post(
        "/ontology/concepts",
        json={"actor": "admin", "concept": SEEDED_DATASET, "definition": "정의"},
    )
    assert response.status_code == 409
    assert SEEDED_DATASET not in ontology.list_concepts()
    assert (
        ontology.ontology_version_identity()["ontology_revision"] == before_revision
    )
    assert not [
        entry
        for entry in ontology.vocabulary_change_log(limit=50)["changes"]
        if entry["concept_name"] == SEEDED_DATASET
    ]


def test_the_graph_node_route_refuses_a_kind_change_too() -> None:
    """Not only the ontology route: the same id, reached directly."""
    response = client.post(
        "/graph/nodes",
        json={"actor": "admin", "node_id": SEEDED_DATASET, "kind": "concept", "label": "덮어쓰기"},
    )
    assert response.status_code == 409, response.text
    assert _node(SEEDED_DATASET)["kind"] == "dataset"


def test_the_graph_node_route_still_accepts_a_same_kind_write() -> None:
    response = client.post(
        "/graph/nodes",
        json={
            "actor": "admin",
            "node_id": SEEDED_DATASET,
            "kind": "dataset",
            "label": "같은 kind 갱신",
        },
    )
    assert response.status_code == 200, response.text
    assert _node(SEEDED_DATASET)["label"] == "같은 kind 갱신"


def test_a_column_node_cannot_be_reclassified_either() -> None:
    """Column nodes carry the ``pii`` flag the masking obligations read."""
    column_id = f"{SEEDED_DATASET}:customer_email"
    before = _node(column_id)
    assert before["kind"] == "column"
    response = client.post(
        "/graph/nodes",
        json={"actor": "admin", "node_id": column_id, "kind": "concept", "label": "x"},
    )
    assert response.status_code == 409, response.text
    after = _node(column_id)
    assert after["kind"] == "column"
    assert after["properties"] == before["properties"]


def test_an_ordinary_concept_registration_is_unaffected() -> None:
    """The rule must not cost a legitimate publication."""
    response = client.post(
        "/ontology/concepts",
        json={"actor": "admin", "concept": "충돌없는개념", "definition": "정의", "aliases": ["no-clash"]},
    )
    assert response.status_code == 200, response.text
    assert "충돌없는개념" in ontology.list_concepts()
    assert _node("충돌없는개념")["kind"] == "concept"


def test_the_patch_approval_path_refuses_the_same_conflict() -> None:
    """The check could not live in the store: that path never writes one.

    ``review_patch`` -> ``register_concept`` touches the vocabulary only, so a
    guard inside ``GraphStore.upsert_node`` covered the routes that write a node
    and missed this one entirely. Measured: approving a patch named
    ``crm-customer-master`` answered **200** and put a dataset id into the
    vocabulary and into the open SKOS export. The check now lives in the shared
    pre-write validator, which is the same chokepoint the ConceptShape gate uses
    and the only one both publication paths pass through.
    """
    proposed = client.post(
        "/ontology/patches",
        json={"actor": "analyst", "concept": SEEDED_DATASET, "suggestion": "데이터셋 id를 이름으로"},
    )
    assert proposed.status_code == 200, proposed.text
    patch_id = proposed.json()["id"]

    reviewed = client.post(
        f"/ontology/patches/{patch_id}/review",
        json={"actor": "admin", "decision": "approve"},
    )
    assert reviewed.status_code == 409, reviewed.text
    assert SEEDED_DATASET not in ontology.list_concepts()
    assert SEEDED_DATASET not in repr(
        client.get("/ontology/vocabulary/jsonld").json()
    )
    stored = next(item for item in ontology.list_patches() if item["id"] == patch_id)
    assert stored["status"] == "proposed"
    assert _node(SEEDED_DATASET)["kind"] == "dataset"


def test_both_publication_paths_answer_the_same_status() -> None:
    """One conflict, one status.

    The approval route maps every ``ValueError`` to 400, so this conflict
    reached a client as 400 there and 409 on the upsert route. ``ConceptKindConflict``
    is a ``ValueError`` subclass - so every existing handler still catches it -
    which lets both routes answer 409 without loosening anything.
    """
    assert issubclass(ontology.ConceptKindConflict, ValueError)

    upsert = client.post(
        "/ontology/concepts",
        json={"actor": "admin", "concept": SEEDED_DATASET, "definition": "정의"},
    )
    proposed = client.post(
        "/ontology/patches",
        json={"actor": "analyst", "concept": SEEDED_DATASET, "suggestion": "정의"},
    )
    review = client.post(
        f"/ontology/patches/{proposed.json()['id']}/review",
        json={"actor": "admin", "decision": "approve"},
    )
    assert upsert.status_code == review.status_code == 409


def test_a_refused_publication_is_audited_with_its_real_outcome() -> None:
    """An auditor looking for refused governed writes found an ALLOW and nothing else.

    Measured: a refused approval wrote one policy decision with
    ``effect: allow`` and **zero** audit rows, and a refused upsert wrote a row
    reading ``authorized`` - written before the mutation, so it cannot attest
    that the publication happened. Both now write their real outcome.
    """
    from sdp import evidence

    before = len(evidence._AUDIT_EVENT_LOG)
    refused = client.post(
        "/ontology/concepts",
        json={"actor": "admin", "concept": SEEDED_DATASET, "definition": "정의"},
    )
    assert refused.status_code == 409
    outcomes = [
        row.result for row in evidence._AUDIT_EVENT_LOG[before:]
    ]
    assert outcomes == ["refused"], outcomes

    before_review = len(evidence._AUDIT_EVENT_LOG)
    proposed = client.post(
        "/ontology/patches",
        json={"actor": "analyst", "concept": SEEDED_DATASET, "suggestion": "정의"},
    )
    client.post(
        f"/ontology/patches/{proposed.json()['id']}/review",
        json={"actor": "admin", "decision": "approve"},
    )
    review_outcomes = [
        row.result for row in evidence._AUDIT_EVENT_LOG[before_review:]
    ]
    assert "refused" in review_outcomes, review_outcomes


def test_an_approval_that_published_nothing_says_so_in_the_ledger() -> None:
    """``approved`` alone reads as a publication.

    An approval of a patch whose concept already exists writes the status but
    publishes nothing - the registrar returns the stored record, so an approval
    cannot rewrite a shipped definition. Measured: that answered 200 with
    ``status: approved`` while the vocabulary was untouched.
    """
    from sdp import evidence

    proposed = client.post(
        "/ontology/patches",
        json={"actor": "analyst", "concept": "고객", "suggestion": "공개되지 않는 정의"},
    )
    before = len(evidence._AUDIT_EVENT_LOG)
    reviewed = client.post(
        f"/ontology/patches/{proposed.json()['id']}/review",
        json={"actor": "admin", "decision": "approve"},
    )
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["concept_already_published"] is True
    outcomes = [row.result for row in evidence._AUDIT_EVENT_LOG[before:]]
    assert outcomes == ["approved_without_publication"], outcomes


def test_a_refused_upsert_leaves_no_graph_node_behind() -> None:
    """The store write now mirrors a committed publication, not precedes it.

    The order was store-first, and the store write is unconditional, so a
    refusal from ``register_concept`` (a full vocabulary, or the alias conflict
    it re-checks inside the lock) answered 409 with the graph node already
    written - the two stores left disagreeing by the very refusal meant to
    prevent a write.
    """
    refused = client.post(
        "/ontology/concepts",
        json={
            "actor": "admin",
            "concept": "별칭충돌개념",
            "definition": "정의",
            # ``고객`` is a seeded concept's canonical name, so claiming it as an
            # alias is refused by ``_assert_no_alias_conflict``.
            "aliases": ["고객"],
        },
    )
    assert refused.status_code == 400, refused.text
    assert client.get(
        "/graph/nodes/별칭충돌개념", params={"user": "admin"}
    ).status_code == 404
    assert "별칭충돌개념" not in ontology.list_concepts()


def test_the_published_refusal_contract_names_the_conflict() -> None:
    """A 409 the document does not mention is a refusal a client cannot handle."""
    from sdp.api_error_contract import REFUSAL_DESCRIPTIONS, ROUTE_REFUSALS

    assert 409 in ROUTE_REFUSALS[("POST", "/graph/nodes")]
    assert 409 in ROUTE_REFUSALS[("POST", "/ontology/concepts")]
    assert 409 in ROUTE_REFUSALS[("POST", "/ontology/patches/{patch_id}/review")]
    assert "kind" in REFUSAL_DESCRIPTIONS[409]
