"""ONT-005: a concept is validated against ConceptShape before it is published.

ONT-005's acceptance criterion is "reasoner + SHACL + reviewer 승인 후 병합".
Reviewer approval was the whole gate: ``review_patch`` went from an approve
decision straight to ``register_concept``, whose checks are a non-empty name, a
length bound, alias conflict and the vocabulary cap. Nothing looked at the
concept being published, ``semantic_validation`` had no concept-targeting shape
at all, and the shape catalog it publishes was never applied to a concept.

Measured before this gate, over HTTP::

    POST /ontology/concepts {"actor": "admin", "concept": "정의누락개념"}
        -> 200,  stored definition = ''
    GET  /ontology/search?q=정의누락개념   -> count 1, definition = ''
    GET  /ontology/concept/정의누락개념    -> definition = ''

So the shared glossary every read surface consults could hold a concept with no
definition, published through an authorized route. A glossary whose terms have
no definitions is not a glossary.

What this does **not** close: there is still no reasoner (ONT-007), so ONT-005
remains partial. The engine is ``builtin_shape_checks`` and
``shacl_engine_executed`` stays false - the shapes are SHACL-expressible and
enforced by equivalent in-process checks, which is the strongest honest claim
this repository can make without an RDF stack (pyshacl and rdflib are not
dependencies, and CI installs from hash-pinned requirements).

Reverse-verified: dropping the ``report["conforms"]`` check from
``validate_concept_registration`` fails three of these tests (the two
publication paths and the shared-validator one), and raising the hierarchy
constraint from warning to violation fails ``test_the_shipped_vocabulary_conforms``
with all five seeded concepts non-conforming - 고객, 매출, 이탈, 이탈 고객,
활성 고객 - which is the measurement behind calling it a warning.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from sdp import ontology, semantic_validation as sv
from sdp.api import app
from sdp.domain import OntologyPatch


client = TestClient(app, raise_server_exceptions=False)


def _conformance() -> dict:
    return sv.concept_vocabulary_conformance(
        ontology.concept_vocabulary_snapshot(),
        resolve_concept=ontology.canonical_concept_or_none,
    )


# ------------------------------------------------------------- the shape ----


def test_the_shape_catalog_publishes_a_concept_shape() -> None:
    shape = sv._shape("ConceptShape")
    assert shape["target"] == "Concept"
    assert shape["required_properties"] == ["definition"]
    assert shape["recommended_properties"] == ["aliases"]
    assert shape["resolvable_hierarchy_targets"] == ["broader", "narrower", "related"]


def test_the_shape_is_evaluated_so_the_compatibility_claim_stays_true() -> None:
    """``shacl_compatible`` is derived from the evaluated set, not asserted.

    Publishing a shape without evaluating it has to make the claim false; that
    is why the set exists.
    """
    assert "ConceptShape" in sv._EVALUATED_SHAPE_IDS
    assert sv._shacl_compatible() is True


def test_each_report_names_only_the_shapes_it_applied() -> None:
    """``shapes`` publishes the whole catalog, which is now five shapes.

    A dataset report that published the catalog alone would read as having
    validated a dataset against ConceptShape - the exact misreading this
    module's history is about.
    """
    dataset = client.get(
        "/catalog/datasets/crm-customer-master/semantic-validation",
        params={"user": "admin"},
    ).json()
    # A literal on purpose: it is the tripwire that brings whoever adds a
    # shape to this test to say which reports apply it. ConceptHierarchyShape
    # (ONT-002) was the fifth, and it applies to neither report below - it
    # targets an edge, not a dataset and not a concept record.
    assert len(dataset["shapes"]) == 5
    assert dataset["evaluated_shapes"] == [
        "DatasetShape",
        "BusinessMappingShape",
        "DistributionShape",
    ]
    assert "ConceptShape" not in dataset["evaluated_shapes"]

    report = ontology.concept_shape_report(
        "보고확인개념", ontology.concept_record(definition="d")
    )
    assert report["evaluated_shapes"] == ["ConceptShape"]


# -------------------------------------------------------------- the gate ----


def test_a_concept_with_no_definition_is_refused_at_both_publication_paths() -> None:
    """The measured defect, closed at the shared validator rather than per route."""
    direct = client.post(
        "/ontology/concepts", json={"actor": "admin", "concept": "정의누락개념"}
    )
    assert direct.status_code == 400, direct.text
    assert "definition" in direct.json()["detail"]
    assert "정의누락개념" not in ontology.list_concepts()

    # The library path, which is what an approval reaches.
    with pytest.raises(ValueError, match="definition"):
        ontology.register_concept(
            "정의없는개념", change_source="concept_upsert", definition="   "
        )
    assert "정의없는개념" not in ontology.list_concepts()


@pytest.mark.parametrize(
    "suggestion", ["", "   ", "\u200b", "\ufeff", "\x00"],
    ids=["empty", "spaces", "U+200B", "U+FEFF", "NUL"],
)
def test_the_queue_cannot_hold_a_proposal_that_can_never_be_approved(
    suggestion: str,
) -> None:
    """Intake and the publication gate must use one predicate for one field.

    ``POST /ontology/patches`` tested ``suggestion.strip()`` while the gate
    tested visibility, and ``suggestion`` *is* the definition. Measured, a
    suggestion of U+200B, U+FEFF, U+00AD or NUL was accepted into the shared
    steward queue with 200 and could then **never** be approved: every approval
    answered 400 and the patch stayed ``proposed`` forever, so a reviewer's only
    remedy was to reject a proposal the product itself had accepted. Any
    authorized analyst could fill a bounded shared queue with them.
    """
    with pytest.raises(ValueError, match="must contain"):
        ontology.propose_patch("승인불가개념", suggestion, requestor="analyst")
    assert not [
        item for item in ontology.list_patches() if item["concept"] == "승인불가개념"
    ]

    response = client.post(
        "/ontology/patches",
        json={"actor": "analyst", "concept": "승인불가개념", "suggestion": suggestion},
    )
    assert response.status_code == 400, response.text


def test_the_approval_gate_is_still_a_backstop_behind_intake() -> None:
    """Defence in depth: intake refusing is not the same as approval checking.

    Intake now refuses an unconforming suggestion, so a stored patch that fails
    the shape cannot be produced through the API any more. The approval-path
    gate still has to hold, because it is what guarantees the publication
    itself - so the patch is placed in the queue directly here, which is the
    only way left to exercise the backstop.

    ``register_concept`` runs **before** the status write, so a refusal leaves
    the patch proposed rather than marked approved with nothing published - 승인
    recorded, 노출 missing, the exact break that path exists to close.
    """
    smuggled = OntologyPatch(
        id="backstop-patch",
        concept="밀수된개념",
        suggestion="",
        requestor="analyst",
        confidence=0.5,
    )
    ontology._ONTOLOGY_PATCHES.append(smuggled)

    with pytest.raises(ValueError, match="definition"):
        ontology.review_patch("backstop-patch", "approve", reviewer="admin")

    stored = next(
        item for item in ontology.list_patches() if item["id"] == "backstop-patch"
    )
    assert stored["status"] == "proposed"
    assert stored["reviewed_by"] is None
    assert "밀수된개념" not in ontology.list_concepts()


def test_the_shared_validator_itself_refuses() -> None:
    """The gate is in ``validate_concept_registration``, not in each route.

    Renamed from ``test_the_gate_cannot_be_bypassed_by_a_future_caller``,
    because that is not what this asserts. An adversarial review added a third
    caller that writes the vocabulary directly - sixteen lines - and measured
    the whole suite green, this test included. "Cannot be bypassed" is a
    property of the shape of the code, and it is now checked as one in
    ``tests/test_concept_write_chokepoint.py``, which fails on exactly that
    mutation. This test checks the narrower thing its name now claims: calling
    the validator refuses.
    """
    with pytest.raises(ValueError, match="ConceptShape"):
        ontology.validate_concept_registration("우회시도개념", definition="")


def test_a_conforming_publication_still_succeeds_and_publishes_its_report() -> None:
    response = client.post(
        "/ontology/concepts",
        json={
            "actor": "admin",
            "concept": "정의있는개념",
            "definition": "정의가 있는 개념",
            "aliases": ["defined-concept"],
        },
    )
    assert response.status_code == 200, response.text
    report = response.json()["concept_validation"]
    assert report["conforms"] is True
    assert report["violations"] == []
    assert report["shacl_engine_executed"] is False
    assert report["validation_engine"] == "builtin_shape_checks"


def test_an_approval_publishes_its_report_too() -> None:
    proposed = client.post(
        "/ontology/patches",
        json={"actor": "analyst", "concept": "승인보고개념", "suggestion": "승인된 정의"},
    )
    patch_id = proposed.json()["id"]
    reviewed = client.post(
        f"/ontology/patches/{patch_id}/review",
        json={"actor": "admin", "decision": "approve"},
    )
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["concept_validation"]["conforms"] is True


def test_an_already_published_concept_reports_the_stored_record() -> None:
    """Not the submission, which published nothing."""
    ontology.register_concept(
        "재게시개념", change_source="concept_upsert", definition="처음 정의"
    )
    again = ontology.register_concept(
        "재게시개념", change_source="concept_upsert", definition="다른 정의"
    )
    assert again["already_published"] is True
    assert again["definition"] == "처음 정의"
    assert again["concept_validation"]["conforms"] is True


# --------------------------------------------- what "present" has to mean ---

# Characters a reader cannot see, by Unicode category. The first version of this
# gate used ``str.strip()``, which removes only characters ``str.isspace()``
# accepts - and the format category is not whitespace, so every one of these
# passed it. Each is a real codepoint a client can send in JSON.
INVISIBLE = [
    ("zero-width space U+200B", "\u200b"),
    ("zero-width non-joiner U+200C", "\u200c"),
    ("soft hyphen U+00AD", "\u00ad"),
    ("left-to-right mark U+200E", "\u200e"),
    ("word joiner U+2060", "\u2060"),
    ("byte-order mark U+FEFF", "\ufeff"),
    ("NUL", "\x00"),
]


@pytest.mark.parametrize("label,character", INVISIBLE, ids=[row[0] for row in INVISIBLE])
def test_a_definition_of_only_invisible_characters_is_not_present(
    label: str, character: str
) -> None:
    """Measured: each of these passed the gate and was served as a definition.

    ``POST /ontology/concepts {"concept": "x", "definition": "\u200b"}``
    answered 200 and ``/ontology/search`` returned that concept with a
    definition that renders as blank - the same defect the gate exists to close,
    reached through a character class ``str.strip()`` does not touch. The rule
    is deliberately stricter than ``sh:minCount 1``, which an invisible literal
    satisfies, and the shape publishes the rule it enforces.
    """
    del label
    response = client.post(
        "/ontology/concepts",
        json={"actor": "admin", "concept": "투명정의개념", "definition": character},
    )
    assert response.status_code == 400, response.text
    assert "투명정의개념" not in ontology.list_concepts()


@pytest.mark.parametrize("label,character", INVISIBLE, ids=[row[0] for row in INVISIBLE])
def test_a_concept_named_with_only_invisible_characters_is_refused(
    label: str, character: str
) -> None:
    """The same rule, applied to the name.

    Measured before this: three concepts named U+200B, U+FEFF and NUL were
    published through ``POST /ontology/concepts`` with 200, because the only
    check was a non-empty ``.strip()``. A concept whose name no reader can see
    cannot be resolved, searched for or cited, and it occupies a slot in a
    bounded vocabulary.
    """
    del label
    response = client.post(
        "/ontology/concepts",
        json={"actor": "admin", "concept": character, "definition": "정의"},
    )
    assert response.status_code == 400, response.text
    assert sv.PRESENCE_BASIS[:20] in response.json()["detail"]
    assert all(sv.has_visible_character(name) for name in ontology.list_concepts())


def test_the_published_presence_rule_is_the_enforced_one() -> None:
    """The shape declares the predicate, so the two cannot drift.

    ``required_properties`` with no stated rule for "present" is how the first
    version of this gate came to accept an invisible definition while publishing
    a constraint a reader would have read as excluding it.
    """
    assert sv._shape("ConceptShape")["required_property_basis"] == sv.PRESENCE_BASIS
    assert "Cf" in sv.PRESENCE_BASIS

    # The predicate itself, in both directions.
    assert sv.has_visible_character("정의") is True
    assert sv.has_visible_character("x") is True
    assert sv.has_visible_character(" \t\n") is False
    assert sv.has_visible_character("\u00a0\u3000") is False
    assert sv.has_visible_character("") is False
    assert sv.has_visible_character(None) is False
    # A visible character among invisible ones is still present.
    assert sv.has_visible_character("\u200b정의\ufeff") is True


def test_a_visible_definition_with_invisible_padding_is_accepted() -> None:
    """The rule is "has a visible character", not "has no invisible ones"."""
    response = client.post(
        "/ontology/concepts",
        json={
            "actor": "admin",
            "concept": "패딩정의개념",
            "definition": "\u200b 실제 정의 \ufeff",
            "aliases": ["padded"],
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["concept_validation"]["conforms"] is True


# ------------------------------------------- the constraint that cannot gate -


def test_the_shipped_vocabulary_conforms() -> None:
    """A constraint that refuses the product's own seed cannot gate publication."""
    conformance = _conformance()
    assert conformance["concept_count"] == len(ontology.list_concepts())
    assert conformance["non_conforming_concepts"] == []
    assert conformance["concept_pass_rate"] == 1.0


def test_the_seeds_undefined_hierarchy_targets_are_reported_as_warnings() -> None:
    """Measured: 10 of the 19 hierarchy edges name a target nothing defines.

    Raised to a violation this would make five shipped concepts non-conforming,
    so it is declared at warning severity and reported - the same strength the
    "at least one searchable business term is recommended" rule already has.
    """
    conformance = _conformance()
    assert conformance["concept_warning_count"] == 10

    customer = ontology.concept_shape_report(
        "고객", ontology.concept_vocabulary_snapshot()["고객"]
    )
    assert customer["conforms"] is True
    warnings = [
        item for item in customer["violations"] if item["severity"] == "warning"
    ]
    assert warnings, customer
    assert all(item["severity"] == "warning" for item in warnings)
    assert any("구매" in item["message"] for item in warnings)


def test_an_alias_only_hierarchy_target_is_not_a_warning() -> None:
    """활성 고객 ``related`` 휴면 고객 resolves to 이탈 고객 through the alias index."""
    report = ontology.concept_shape_report(
        "활성 고객", ontology.concept_vocabulary_snapshot()["활성 고객"]
    )
    assert not any("휴면 고객" in item["message"] for item in report["violations"]), report


def test_a_missing_alias_list_is_a_warning_not_a_refusal() -> None:
    """``aliases`` is recommended: a concept with one name is still a concept."""
    report = ontology.concept_shape_report(
        "별칭없는개념", ontology.concept_record(definition="정의만 있는 개념")
    )
    assert report["conforms"] is True
    assert [item["path"] for item in report["violations"]] == ["aliases"]
    assert report["violations"][0]["severity"] == "warning"


def test_the_record_the_gate_checks_is_the_record_that_is_stored() -> None:
    """One builder, so the validated and the stored record cannot drift.

    A validator checking a record assembled a second way is a validator that can
    pass while the stored record fails.
    """
    ontology.register_concept(
        "동일레코드개념",
        change_source="concept_upsert",
        definition="정의",
        aliases=["same-record"],
        broader="고객",
        narrower=["하위"],
        related=["연관"],
    )
    stored = ontology.concept_vocabulary_snapshot()["동일레코드개념"]
    rebuilt = ontology.concept_record(
        definition="정의",
        aliases=["same-record"],
        broader="고객",
        narrower=["하위"],
        related=["연관"],
    )
    assert stored == rebuilt


# ------------------------- what the gate must NOT refuse, and must bound ----


def test_updating_an_existing_concepts_graph_edges_needs_no_definition() -> None:
    """The regression this gate introduced, and the reason it was wrong.

    An already-published concept's record is not replaced - the registrar
    returns the stored record and discards the submission, so an approval cannot
    silently rewrite a shipped definition. The submitted ``definition`` is
    therefore not what will exist, and requiring it refused a request that
    changes nothing in the vocabulary. Measured as a regression: this call went
    200 -> 400, and this route is the only way to update the graph-store concept
    record, its broader/narrower/related edges and its embedding. The caller's
    only way through was to re-send a definition the vocabulary throws away -
    which the graph store then stored, so one 200 body carried a graph
    definition the vocabulary never accepted.
    """
    # A concept of this test's own, not a seeded one: the graph store singleton
    # is deliberately outside conftest's restore (see its docstring), so
    # mutating a seeded concept's graph record leaks into later tests - which is
    # exactly how the divergence below was found, by a retained test failing in
    # reversed file order.
    first = client.post(
        "/ontology/concepts",
        json={
            "actor": "admin",
            "concept": "재게시대상개념",
            "definition": "처음 게시한 정의",
            "aliases": ["first-alias"],
        },
    )
    assert first.status_code == 200, first.text
    stored_before = ontology.concept_vocabulary_snapshot()["재게시대상개념"]["definition"]

    response = client.post(
        "/ontology/concepts",
        json={
            "actor": "admin",
            "concept": "재게시대상개념",
            "related": ["신규연관개념"],
            "aliases": ["buyer-side"],
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["concept_already_published"] is True
    assert body["concept_validation"]["evaluated_record"] == "published_vocabulary"
    assert (
        ontology.concept_vocabulary_snapshot()["재게시대상개념"]["definition"]
        == stored_before
    )


def test_the_graph_mirror_keeps_the_vocabularys_definition() -> None:
    """The two stores must not disagree about a concept's definition.

    The registrar keeps the stored definition and discards a re-submission, but
    the route handed the raw submission to the graph store - so a re-upsert that
    simply omitted ``definition`` left the graph store holding ``''`` while the
    vocabulary held the real text, and ``GET /ontology/term/{term}/graph``,
    which reads the store, served the empty one. Measured on the seeded concept
    고객; a retained test (``test_the_shared_vocabulary_itself_stays_open``)
    caught it in reversed file order.
    """
    published = client.post(
        "/ontology/concepts",
        json={
            "actor": "admin",
            "concept": "거울개념",
            "definition": "거울이 지켜야 하는 정의",
            "aliases": ["mirror-first"],
        },
    )
    assert published.status_code == 200, published.text

    reupsert = client.post(
        "/ontology/concepts",
        json={"actor": "admin", "concept": "거울개념", "aliases": ["mirror-second"]},
    )
    assert reupsert.status_code == 200, reupsert.text

    graph = client.get("/ontology/term/거울개념/graph").json()
    assert graph["definition"] == "거울이 지켜야 하는 정의"
    assert (
        ontology.concept_vocabulary_snapshot()["거울개념"]["definition"]
        == graph["definition"]
    )
    # The caller's own fields still reach the mirror; only the definition is
    # taken from the vocabulary.
    assert "mirror-second" in graph["aliases"]


def test_the_authoritative_definition_resolves_through_the_alias_index() -> None:
    """A caller naming an alias must not look like a new concept."""
    assert ontology.published_concept_definition("customer") == (
        ontology.concept_vocabulary_snapshot()["고객"]["definition"]
    )
    assert ontology.published_concept_definition("존재하지않는개념") is None


def test_the_report_names_the_record_its_verdict_is_about() -> None:
    """``evaluated_record`` is to the subject what ``evaluated_shapes`` is to the
    constraints.

    On a re-publication the submitted payload is discarded, so a report that did
    not say which record it read let a 200 response carry ``conforms: true``
    about content the caller never sent.
    """
    fresh = client.post(
        "/ontology/concepts",
        json={"actor": "admin", "concept": "주체표기개념", "definition": "정의", "aliases": ["subject"]},
    )
    assert fresh.status_code == 200, fresh.text
    assert fresh.json()["concept_validation"]["evaluated_record"] == "published_vocabulary"

    report = ontology.concept_shape_report(
        "임의개념", ontology.concept_record(definition="정의")
    )
    assert report["evaluated_record"] == "submitted"


@pytest.mark.parametrize(
    "length,expected", [(2000, 200), (2001, 400), (200_000, 400)],
    ids=["at-the-bound", "one-over", "far-over"],
)
def test_the_required_definition_is_bounded(length: int, expected: int) -> None:
    """A field made mandatory on the one path that did not bound it.

    Measured: a 2,000,000-character definition was accepted and stored in full,
    in a 500-slot process-lifetime vocabulary. The concept *name* is bounded at
    the same constant three lines from the gate, and the patch path refuses a
    2001-character suggestion at intake, so the two publication paths disagreed
    about the same field.
    """
    response = client.post(
        "/ontology/concepts",
        json={
            "actor": "admin",
            "concept": f"길이개념-{length}",
            "definition": "가" * length,
            "aliases": [f"len-{length}"],
        },
    )
    assert response.status_code == expected, response.text
    if expected == 400:
        assert "longer than" in response.json()["detail"]


def test_the_published_bound_is_the_enforced_bound() -> None:
    """One constant, so the shape and the two paths cannot disagree."""
    assert sv._shape("ConceptShape")["max_property_length"] == sv.MAX_PUBLISHED_FIELD_LENGTH
    assert ontology.MAX_ONTOLOGY_PATCH_FIELD == sv.MAX_PUBLISHED_FIELD_LENGTH


def test_the_vocabulary_snapshot_is_a_real_copy() -> None:
    """``dict(record)`` handed out the live lists under a read-only docstring.

    Measured through this accessor alone, with no private access: appending to
    the returned ``narrower`` list installed an unresolvable hierarchy target
    into the published vocabulary, and an alias appended the same way takes a
    term ``_assert_no_alias_conflict`` refuses. A "copy" that aliases its source
    is worse than no copy, because callers trust the docstring.
    """
    snapshot = ontology.concept_vocabulary_snapshot()
    snapshot["매출"]["narrower"].append("밀수된하위")
    snapshot["고객"]["aliases"].append("매출")
    snapshot["이탈"]["definition"] = "덮어쓴 정의"
    live = ontology.concept_vocabulary_snapshot()
    assert "밀수된하위" not in live["매출"]["narrower"]
    assert "매출" not in live["고객"]["aliases"]
    assert live["이탈"]["definition"] != "덮어쓴 정의"
    assert (
        ontology.ontology_version_identity()["digest_matches_recorded_revision"] is True
    )


@pytest.mark.parametrize("value", [5, None, ["x"], {"a": 1}], ids=lambda v: type(v).__name__)
def test_a_non_string_definition_is_refused_with_value_error(value: object) -> None:
    """``definition.strip()`` raised AttributeError, which the routes do not map.

    A function documented to signal refusal with ValueError handed an in-process
    caller an unmapped exception type. Refused rather than coerced: ``str(5)``
    would publish "5" as a definition, which is a fabrication, not a repair.
    """
    with pytest.raises(ValueError, match="must be a string"):
        ontology.validate_concept_registration("타입검사개념", definition=value)


# ----------------------------------------------- the platform-wide surface --


def test_the_enterprise_surface_publishes_vocabulary_conformance() -> None:
    """So the shape's effect is measurable, not only visible at a publication."""
    body = client.get("/enterprise/shacl-validation").json()
    assert body["shape_count"] == 5
    assert body["evaluated_shapes"] == [
        "DatasetShape",
        "BusinessMappingShape",
        "DistributionShape",
    ]
    concept = body["concept_conformance"]
    assert concept["evaluated_shapes"] == ["ConceptShape"]
    # The scope the number covers, declared: a kind="concept" node written
    # straight to the graph store is not in the vocabulary and is not counted -
    # measured, such a node with definition "" is served by /graph/nodes while
    # this pass rate stays 1.0.
    assert concept["conformance_scope"] == sv.CONCEPT_CONFORMANCE_SCOPE
    assert "POST /graph/nodes" in concept["conformance_scope"]
    assert concept["concept_count"] == len(ontology.list_concepts())
    assert concept["concept_pass_rate"] == 1.0
    assert concept["concept_warning_count"] == 10


def test_a_non_conforming_concept_would_show_in_the_platform_number() -> None:
    """Otherwise the pass rate is unfalsifiable by construction.

    The gate makes a non-conforming concept unreachable through any route, so
    the vocabulary is written directly here - which is also what
    ``digest_matches_recorded_revision`` is for: this is a vocabulary mutated
    outside the publication path.
    """
    ontology._CONCEPT_DEFINITIONS["규칙위반개념"] = ontology.concept_record(
        definition="", aliases=["violating"]
    )
    conformance = _conformance()
    assert conformance["non_conforming_concepts"] == ["규칙위반개념"]
    assert conformance["concept_pass_rate"] < 1.0
    assert ontology.ontology_version_identity()["digest_matches_recorded_revision"] is False
