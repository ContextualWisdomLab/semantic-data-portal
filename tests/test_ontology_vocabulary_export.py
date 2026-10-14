"""The versioned SKOS/RDFS vocabulary export, and the version pin on resolution.

ONT-004's subject is an "OWL/RDFS 기반 도메인 ontology" and there was no RDF
artifact at all: the DCAT export covers datasets, and its
``mappings[].concept`` is a plain literal, so no triple anywhere named a
concept. A revision number on a Python dict is not a versioned ontology; this
is the artifact the revision names.

The pin half closes a contradiction between two published claims. The
``rdf_connector`` control ``ontology_version_pin`` reported ``implemented`` with
``verification: proof_route_served`` and proof endpoints ``/ontology/search``
and ``/ontology/resolve`` - measured, neither response contained the string
"version" anywhere - while ``ONT-004`` was recorded ``not_implemented`` for
exactly that reason.

``pyld`` is importable in this environment but is declared in no requirements
file, so the expansion tests below ``importorskip`` it exactly as
``tests/test_jsonld_export.py`` does. The always-running gate is the
dependency-free recursive term check, which that file applies to the dataset
export and which is applied here to the vocabulary export - the dataset version
enumerates datasets and would never have covered this route.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from sdp import ontology, ontology_version
from sdp.api import app


client = TestClient(app, raise_server_exceptions=False)

JSONLD_KEYWORDS = frozenset({"@context", "@id", "@type", "@graph"})


def _export() -> dict:
    response = client.get("/ontology/vocabulary/jsonld")
    assert response.status_code == 200, response.text
    return response.json()


def _nodes(document: dict) -> list[dict]:
    return document["@graph"]


def _scheme(document: dict) -> dict:
    return next(
        node for node in _nodes(document) if node["@type"] == "skos:ConceptScheme"
    )


def _concepts(document: dict) -> list[dict]:
    return [node for node in _nodes(document) if node["@type"] == "skos:Concept"]


# ------------------------------------------------------- the RDF artifact ---


def test_every_concept_is_a_skos_concept_in_one_scheme() -> None:
    document = _export()
    concepts = _concepts(document)
    assert {node["prefLabel"] for node in concepts} == set(ontology.list_concepts())
    scheme = _scheme(document)
    for node in concepts:
        assert node["inScheme"] == scheme["@id"]


def test_the_scheme_carries_the_version_it_serialized() -> None:
    """``owl:versionInfo`` carries the digest as well as the revision.

    The revision alone cannot identify the content across a restart, so the
    document would claim a version that means nothing to a consumer comparing
    two exports.
    """
    identity = ontology.ontology_version_identity()
    scheme = _scheme(_export())
    assert scheme["ontologyRevision"] == identity["ontology_revision"]
    assert scheme["contentDigest"] == identity["content_digest"]
    assert str(identity["ontology_revision"]) in scheme["versionInfo"]
    assert identity["content_digest"] in scheme["versionInfo"]
    assert scheme["revisionIsDurable"] is False


def test_no_published_term_is_unmapped_by_the_context() -> None:
    """The dependency-free gate, applied recursively.

    An unmapped term is dropped silently by an RDF processor, which is how the
    DCAT export came to publish distributions that expanded to ``[{}]``. The
    equivalent check for datasets enumerates datasets and would never reach
    this route, so the rule is applied here too rather than assumed.
    """
    document = _export()
    context = document["@context"]

    def unmapped(node: object, path: str = "") -> list[str]:
        if isinstance(node, list):
            found: list[str] = []
            for item in node:
                found.extend(unmapped(item, f"{path}[]"))
            return found
        if not isinstance(node, dict):
            return []
        found = []
        for term, value in node.items():
            here = f"{path}.{term}" if path else term
            prefixed = ":" in term and term.split(":", 1)[0] in context
            if term not in JSONLD_KEYWORDS and term not in context and not prefixed:
                found.append(here)
            found.extend(unmapped(value, here))
        return found

    assert unmapped({k: v for k, v in document.items() if k != "@context"}) == []


def test_the_document_expands_to_real_triples() -> None:
    """The property the term check is a proxy for."""
    jsonld = pytest.importorskip("pyld.jsonld", reason="pyld is a dev-only dependency")
    document = _export()
    expanded = jsonld.expand(document)
    assert len(expanded) == len(_nodes(document))
    for node in expanded:
        assert node["@id"].startswith("http")
        # A node that survives expansion carrying no triples is, to a consumer,
        # indistinguishable from one that was never published.
        assert [key for key in node if key != "@id"], node


def test_a_prefix_label_is_not_also_its_own_alternate_label() -> None:
    """``_to_concept_payload`` prepends the canonical name into ``aliases``.

    Serializing from that shape would emit the ``skos:prefLabel`` as its own
    ``skos:altLabel``. The export reads the raw record instead, and drops any
    alternate label equal to the concept name.
    """
    for node in _concepts(_export()):
        assert node["prefLabel"] not in node.get("altLabel", [])


def test_alternate_labels_are_deduplicated() -> None:
    """``aliases`` and ``multilingual`` overlap - 고객 declares customer in both."""
    for node in _concepts(_export()):
        labels = node.get("altLabel", [])
        assert len(labels) == len(set(labels)), node["prefLabel"]


# ------------------------------------------------- the declared gaps --------


def test_a_hierarchy_target_that_resolves_to_nothing_is_declared_not_minted() -> None:
    """Measured on the shipped vocabulary: 10 of 19 edges name an undefined term.

    Minting ``skos:broader`` to an IRI for a concept that does not exist would
    publish subjects with no definition, no label and no scheme - a vocabulary
    claiming to define terms it never defines. They are published as a declared
    gap with a count instead, which is also the first time the defect is visible
    to a reader.
    """
    document = _export()
    scheme = _scheme(document)
    declared = scheme["undefinedHierarchyTarget"]
    assert scheme["undefinedHierarchyTargetCount"] == len(declared)
    assert len(declared) == 10

    minted = {node["@id"] for node in _concepts(document)}
    for relation in ("broader", "narrower", "related"):
        for node in _concepts(document):
            for target in node.get(relation, []):
                assert target in minted, (node["prefLabel"], relation, target)


def test_an_alias_only_target_points_at_the_concept_it_aliases() -> None:
    """활성 고객 ``related`` 휴면 고객, which is an alias of 이탈 고객.

    Resolved through the alias index rather than dropped as undefined, so the
    triple names the real concept. Declared as well, because a reader comparing
    the document with the source record would otherwise see a target that moved.
    """
    scheme = _scheme(_export())
    resolved = scheme["aliasResolvedHierarchyTarget"]
    assert any("휴면 고객" in entry and "이탈 고객" in entry for entry in resolved)
    active = next(
        node for node in _concepts(_export()) if node["prefLabel"] == "활성 고객"
    )
    assert ontology_version.concept_iri("이탈 고객") in active["related"]
    assert ontology_version.concept_iri("휴면 고객") not in active["related"]


def test_the_export_never_derives_dataset_identity() -> None:
    """``ontology._INDEX`` has no tenant predicate, and this route is open.

    Serving that index is exactly how ``concept_assets`` leaked every tenant's
    dataset ids to a caller its own policy decision denied, so the export reads
    the vocabulary and nothing else, and the document says the mapping is not
    versioned here rather than leaving a reader to assume it is covered.

    The guarantee is about what the export *derives*, and it is narrower than
    "no dataset id can ever appear in this document". Nothing stops an
    authorized writer naming a concept after a dataset - measured,
    ``POST /ontology/concepts {"concept": "crm-customer-master", "broader":
    "고객"}`` answers 200, because ``kind`` is free-form and no class check
    guards concept registration. That is ONT-002's recorded gap, not something
    this export introduces or can close; the second half of this test pins the
    distinction so the first half is not read as a stronger promise than it is.
    The route's own docstring states the same limit, because that is what a
    reader sees as the OpenAPI description - it said a flat "no dataset ids"
    until an adversarial review pointed out that the guarantee is about
    derivation.
    """
    from sdp.catalog import list_datasets

    document = _export()
    blob = repr(document)
    dataset_ids = [dataset.id for dataset in list_datasets()]
    for dataset_id in dataset_ids:
        assert dataset_id not in blob, dataset_id
    assert _scheme(document)["datasetMappingIsVersioned"] is False

    # A writer-chosen concept name reaches the document as a label, and still
    # brings no mapping, no distribution and no dataset structure with it.
    hijack = client.post(
        "/ontology/concepts",
        json={"actor": "admin", "concept": dataset_ids[0], "definition": "d"},
    )
    assert hijack.status_code == 200, hijack.text
    after = _export()
    node = next(
        item for item in _concepts(after) if item["prefLabel"] == dataset_ids[0]
    )
    assert set(node) <= {
        "@id",
        "@type",
        "inScheme",
        "prefLabel",
        "label",
        "definition",
        "altLabel",
        "broader",
        "narrower",
        "related",
    }, node
    assert _scheme(after)["datasetMappingIsVersioned"] is False


def test_a_published_concept_appears_in_the_next_export() -> None:
    before = {node["prefLabel"] for node in _concepts(_export())}
    ontology.register_concept(
        "수출확인개념", change_source="concept_upsert", definition="d", actor_id="admin"
    )
    after = _export()
    assert "수출확인개념" in {node["prefLabel"] for node in _concepts(after)}
    assert "수출확인개념" not in before
    assert _scheme(after)["contentDigest"] == ontology.ontology_version_identity()[
        "content_digest"
    ]


# ------------------------------------------------------- the concept IRI ----


def test_the_concept_iri_is_injective() -> None:
    """``concept.replace(" ", "-")`` was not.

    Measured: ``활성 고객`` and a separately registrable ``활성-고객`` minted the
    identical IRI. In a resolution response that is a confusing identifier; in
    an RDF document two distinct concepts collapse into one subject and their
    labels, definitions and hierarchies merge.
    """
    colliding = ("활성 고객", "활성-고객", "a b", "a-b", "a%20b", "a/b", "a%2Fb")
    minted = [ontology_version.concept_iri(name) for name in colliding]
    assert len(set(minted)) == len(colliding), minted


def test_the_iri_keeps_unicode_readable() -> None:
    """``urllib.parse.quote`` would percent-encode 고객 into 24 characters.

    An IRI may carry Unicode, and the export is something a buyer reads.
    """
    assert ontology_version.concept_iri("고객").endswith("/고객")


def test_resolution_and_the_export_name_the_same_concept() -> None:
    """One definition of the concept IRI, not two that can drift apart.

    And the distinction this test found: resolution answers with term IRIs for
    dataset-declared terms the glossary never defines (캠페인, 전환,
    비즈니스 용어 on the seed), identically shaped to a defined concept's IRI.
    Each row now says which it is, so the two sets are checked separately
    instead of the mismatch being hidden.
    """
    resolved = client.post("/ontology/resolve", json={"text": "고객 이탈"})
    assert resolved.status_code == 200
    rows = resolved.json()["resolved"]
    exported = {node["@id"] for node in _concepts(_export())}
    defined = {row["uri"] for row in rows if row["defined_in_vocabulary"]}
    undefined = {row["uri"] for row in rows if not row["defined_in_vocabulary"]}
    assert defined, "nothing defined resolved, so this test proves nothing"
    assert defined <= exported, defined - exported
    assert not (undefined & exported), undefined & exported
    assert resolved.json()["undefined_resolution_count"] == len(undefined)


def test_an_undefined_resolution_is_declared_rather_than_withheld() -> None:
    """It is still a real pointer to a dataset, so it is returned, not dropped."""
    rows = client.post("/ontology/resolve", json={"text": "캠페인 전환"}).json()[
        "resolved"
    ]
    undefined = [row for row in rows if not row["defined_in_vocabulary"]]
    assert undefined, rows
    for row in undefined:
        assert row["term"] not in ontology.list_concepts()


# ------------------------------------------------------- the version pin ----


def test_both_proof_routes_stamp_the_version_they_answered_from() -> None:
    identity = ontology.ontology_version_identity()
    search = client.get("/ontology/search", params={"q": "고객"})
    resolve = client.post("/ontology/resolve", json={"text": "고객"})
    for response in (search, resolve):
        assert response.status_code == 200, response.text
        stamp = response.json()["ontology_version"]
        assert stamp["ontology_revision"] == identity["ontology_revision"]
        assert stamp["content_digest"] == identity["content_digest"]
        assert stamp["revision_is_durable"] is False
        assert stamp["pin_requested"] is False


def test_a_matching_pin_is_served() -> None:
    digest = ontology.ontology_version_identity()["content_digest"]
    search = client.get(
        "/ontology/search", params={"q": "고객", "ontology_content_digest": digest}
    )
    assert search.status_code == 200
    assert search.json()["ontology_version"]["pin_requested"] is True
    resolve = client.post(
        "/ontology/resolve",
        json={"text": "고객", "ontology_content_digest": digest},
    )
    assert resolve.status_code == 200
    assert resolve.json()["ontology_version"]["pin_requested"] is True


def test_a_pin_naming_another_version_is_refused_with_409() -> None:
    """Refused rather than silently answered from a different vocabulary."""
    stale = "0" * 64
    search = client.get(
        "/ontology/search", params={"q": "고객", "ontology_content_digest": stale}
    )
    assert search.status_code == 409
    assert stale in search.json()["detail"]
    resolve = client.post(
        "/ontology/resolve", json={"text": "고객", "ontology_content_digest": stale}
    )
    assert resolve.status_code == 409


def test_a_pin_stops_matching_when_the_vocabulary_changes() -> None:
    """The whole point: a client learns the vocabulary moved under it."""
    digest = ontology.ontology_version_identity()["content_digest"]
    assert (
        client.get(
            "/ontology/search", params={"q": "고객", "ontology_content_digest": digest}
        ).status_code
        == 200
    )
    ontology.register_concept(
        "핀무효화개념",
        change_source="concept_upsert",
        definition="핀 무효화 확인용",
        actor_id="admin",
    )
    assert (
        client.get(
            "/ontology/search", params={"q": "고객", "ontology_content_digest": digest}
        ).status_code
        == 409
    )


@pytest.mark.parametrize(
    "malformed", ["", "abc", "g" * 64, "0" * 63, "0" * 65], ids=lambda value: f"len{len(value)}"
)
def test_a_malformed_pin_is_400_not_409(malformed: str) -> None:
    """A typo must not be reported as "the server holds a different vocabulary".

    The two refusals mean different things and lead a client to different
    actions, so they do not share a status.
    """
    response = client.get(
        "/ontology/search", params={"q": "고객", "ontology_content_digest": malformed}
    )
    assert response.status_code == 400, response.text


def test_the_revision_is_not_pinnable_and_says_so() -> None:
    """A pin on a process-local number would silently stop pinning on restart."""
    stamp = client.get("/ontology/search", params={"q": "고객"}).json()[
        "ontology_version"
    ]
    assert stamp["revision_is_pinnable"] is False
    assert stamp["pin_basis"] == "content_digest_only"


def test_the_connector_control_is_now_verified_by_a_runtime_probe() -> None:
    """The claim that used to rest on the proof route merely existing."""
    probe = client.get(
        "/enterprise/connectors/rdf_connector/probe",
        params={"dataset_id": "semantic-glossary", "user": "admin"},
    )
    assert probe.status_code == 200
    row = next(
        item
        for item in probe.json()["control_evidence"]
        if item["control"] == "ontology_version_pin"
    )
    assert row["status"] == "implemented"
    assert row["verification"] == "runtime_probe_verified"
    assert row["accepts_the_live_digest"] is True
    assert row["refuses_a_different_digest"] is True
    assert row["rejects_a_malformed_digest"] is True
    assert "/ontology/version" in row["proof_endpoints"]
