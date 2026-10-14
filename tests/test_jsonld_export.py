"""The DCAT export declared ``@context`` and was not consumable as JSON-LD.

Three defects in one payload, measured before the repair::

    GET /catalog/datasets/crm-customer-master/jsonld
      "@context": "https://www.w3.org/TR/vocab-dcat-3/"   <- the HTML spec page
      "@type":    "Dataset"                               <- unmapped term
      "id":       "https://.../datasets/crm-customer-master"
      "@id" present: False

* ``id`` is an ordinary term, not the ``@id`` keyword, so a processor read no
  subject IRI for the dataset at all.
* ``@context`` pointed at the DCAT *specification page*. A processor
  dereferencing it receives HTML, not a context document.
* With no term definitions, every one of ``title``, ``description``, ``license``,
  ``status``, ``domain``, ``owner``, ``steward``, ``distribution``, ``mappings``
  and the three score fields was unmapped - and a JSON-LD processor **drops**
  unmapped terms. The export would have produced a single typeless node with no
  properties.

The context is now inline, so the document is self-describing and needs no
network fetch, and portal-specific fields carry the portal's own vocabulary IRI
rather than being asserted as DCAT terms they are not.

On tooling: the strongest checks here expand the document with a real JSON-LD
processor (``pyld``), and ``pyld`` is **not a declared dependency** of this
repository - it pulls in ``lxml``, a C extension, and CI installs from
hash-pinned requirements. Those checks therefore ``importorskip`` and will skip
in CI. The gate that always runs is the dependency-free recursive term check,
and it is the one that actually catches this defect class: reverse-verified by
reverting the nested context entries, it reports 46 unmapped nested terms where
the old top-level-only version reported 0. ``test_no_published_node_expands_to_nothing``
passed even in that reverted state, because the distribution node carries its
own ``@id``/``@type``, so it is a complement to the term check rather than a
substitute for it.
"""

from __future__ import annotations

import pytest

from fastapi.testclient import TestClient

from sdp import catalog
from sdp.api import JSONLD_CONTEXT, JSONLD_KEYWORDS, app


client = TestClient(app)

# Prefix definitions map to absolute IRIs; term definitions map to prefixed
# names, or to an **expanded term definition** - a dict carrying ``@id`` and
# often ``@type``, which is how a term gets a datatype (``xsd:dateTime``) or is
# declared to be a node reference rather than a string literal (``@type: @id``).
# This set used to call ``.startswith`` on every value and crashed the moment
# the context gained its first expanded definition.
def _term_iri(value: object) -> str:
    """The IRI a context entry maps to, for either definition form."""
    if isinstance(value, dict):
        return str(value.get("@id", ""))
    return str(value)


PREFIXES = {
    name
    for name, value in JSONLD_CONTEXT.items()
    if not isinstance(value, dict) and _term_iri(value).startswith("http")
}


def _export(dataset_id: str) -> dict:
    response = client.get(
        f"/catalog/datasets/{dataset_id}/jsonld", params={"user": "admin"}
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_every_published_term_is_mapped_by_the_context() -> None:
    """A term a processor would drop is a term the export does not really publish.

    Enumerated over every seeded dataset, so a field added to the payload without
    a context entry fails here rather than silently vanishing for consumers.
    """
    unmapped = []
    for dataset in catalog.list_datasets(None):
        unmapped.extend(
            (dataset.id, path) for path in _unmapped_terms(_export(dataset.id))
        )
    assert not unmapped, (
        "these terms have no context mapping, so a JSON-LD processor drops them: "
        f"{unmapped}"
    )


def _unmapped_terms(node: object, path: str = "") -> list[str]:
    """Every term with no context mapping, at any depth.

    This check used to be ``for term in body`` - the **top level only**. It
    reported 0 unmapped terms while the same rule applied recursively reported
    51, because ``distribution`` and ``mappings`` carry nested objects and none
    of their properties were mapped. Confirmed with pyld 3.3.0 against the live
    response: ``dcat:distribution`` expanded to ``[{}]`` (an empty blank node -
    no access URL, no format, no identifier) and a business mapping kept only
    ``status`` and ``steward``, dropping ``concept``, ``source`` and
    ``approved_at``.

    A rule applied to one level of a nested document is the same defect class as
    a check applied to one route of a family: it passes while the thing it is
    supposed to prevent is happening one level down.
    """
    if isinstance(node, list):
        found = []
        for item in node:
            found.extend(_unmapped_terms(item, f"{path}[]"))
        return found
    if not isinstance(node, dict):
        return []
    found = []
    for term, value in node.items():
        here = f"{path}.{term}" if path else term
        # A term already written as a prefixed IRI (``dcterms:identifier``) is
        # resolved through the prefix, so it is mapped by construction.
        prefixed = ":" in term and term.split(":", 1)[0] in JSONLD_CONTEXT
        if term not in JSONLD_KEYWORDS and term not in JSONLD_CONTEXT and not prefixed:
            found.append(here)
        found.extend(_unmapped_terms(value, here))
    return found


def test_no_published_node_expands_to_nothing() -> None:
    """The property the recursive term check is a proxy for.

    A node that survives expansion but carries no triples is indistinguishable,
    to a consumer, from a node that was never published. The distribution was
    exactly that: present as an object of ``dcat:distribution`` and empty.
    """
    pyld = pytest.importorskip("pyld.jsonld", reason="pyld is a dev-only dependency")
    for dataset in catalog.list_datasets(None):
        expanded = pyld.expand(_export(dataset.id))
        assert expanded, dataset.id
        for subject in expanded:
            for predicate, objects in subject.items():
                if predicate.startswith("@"):
                    continue
                for obj in objects:
                    if not isinstance(obj, dict) or "@value" in obj or "@id" in obj:
                        continue
                    assert obj, (
                        f"{dataset.id}: {predicate} expands to an empty node, so a "
                        "consumer sees the property published and finds nothing in it"
                    )


def test_a_distribution_is_a_real_dcat_node_with_an_access_url() -> None:
    """What a DCAT consumer actually needs from a distribution."""
    pyld = pytest.importorskip("pyld.jsonld", reason="pyld is a dev-only dependency")
    expanded = pyld.expand(_export("crm-customer-master"))[0]
    distributions = expanded["http://www.w3.org/ns/dcat#distribution"]
    assert distributions
    for distribution in distributions:
        assert distribution["@id"].startswith(
            "https://semantic-data-portal.local/datasets/crm-customer-master/distributions/"
        ), distribution
        assert "http://www.w3.org/ns/dcat#Distribution" in distribution["@type"]
        access = distribution["http://www.w3.org/ns/dcat#accessURL"]
        # Typed @id, so the endpoint is a node reference and not a bare string.
        assert access[0].get("@id"), access
        assert distribution["http://purl.org/dc/terms/format"][0]["@value"]
        assert distribution["http://purl.org/dc/terms/identifier"][0]["@value"]


def test_a_business_mapping_keeps_the_concept_it_approved() -> None:
    """An approval record with no subject cannot be audited."""
    pyld = pytest.importorskip("pyld.jsonld", reason="pyld is a dev-only dependency")
    expanded = pyld.expand(_export("crm-customer-master"))[0]
    mappings = expanded["https://semantic-data-portal.local/ns#businessMapping"]
    assert mappings
    for mapping in mappings:
        assert mapping["https://semantic-data-portal.local/ns#concept"][0]["@value"]
        assert mapping["https://semantic-data-portal.local/ns#approvedAt"][0]["@value"]
        assert mapping["http://purl.org/dc/terms/source"][0]["@value"]


def test_the_node_carries_an_id_keyword_not_an_id_term() -> None:
    body = _export("crm-customer-master")
    assert body["@id"] == "https://semantic-data-portal.local/datasets/crm-customer-master"
    assert "id" not in body, (
        "`id` is an ordinary term; a processor would not read it as the subject IRI"
    )


def test_the_type_is_a_mapped_prefixed_name() -> None:
    body = _export("crm-customer-master")
    assert body["@type"] == "dcat:Dataset"
    prefix = body["@type"].split(":", 1)[0]
    assert prefix in PREFIXES, f"@type uses prefix {prefix!r} that the context does not define"


def test_the_context_is_inline_and_every_prefixed_name_resolves() -> None:
    """Self-describing: no network fetch, and no dangling prefix."""
    body = _export("crm-customer-master")
    context = body["@context"]
    assert isinstance(context, dict), (
        "a remote @context string made the document depend on fetching a page that "
        "is not a context document"
    )

    dangling = []
    for term, value in context.items():
        if term in PREFIXES:
            assert _term_iri(value).startswith("http"), f"prefix {term} must map to an IRI"
            continue
        # An expanded term definition keeps its IRI under ``@id``; its optional
        # ``@type`` is checked below so a datatype prefix cannot dangle either.
        iri = _term_iri(value)
        assert iri, f"term {term} has no @id: {value!r}"
        assert ":" in iri, f"term {term} must map to a prefixed name or IRI, got {iri!r}"
        for candidate in (iri, *( [str(value["@type"])] if isinstance(value, dict) and "@type" in value else [] )):
            if candidate.startswith("@"):
                continue  # the @id keyword as a datatype: a node reference
            prefix = candidate.split(":", 1)[0]
            if prefix not in PREFIXES and not candidate.startswith("http"):
                dangling.append((term, candidate))
    assert not dangling, f"these mappings use an undefined prefix: {dangling}"


def test_portal_specific_fields_are_not_asserted_as_dcat_terms() -> None:
    """Over-claiming a vocabulary is its own kind of dishonest metadata."""
    context = _export("crm-customer-master")["@context"]
    for term in (
        "status",
        "domain",
        "owner",
        "steward",
        "completeness_score",
        "metadata_completeness",
        "metadata_recommendation_score",
        "mappings",
    ):
        assert context[term].startswith("sdp:"), (
            f"{term} is portal-specific and must not claim a DCAT/DCTERMS IRI"
        )

    # The genuinely standard ones do use the standard vocabularies.
    assert context["title"] == "dcterms:title"
    assert context["description"] == "dcterms:description"
    assert context["license"] == "dcterms:license"
    assert context["distribution"] == "dcat:distribution"


def test_the_export_is_still_tenant_scoped() -> None:
    """The shape change must not have reopened the route."""
    base = catalog._DATA["crm-customer-master"]
    catalog._DATA["jsonld-foreign-ds"] = base.model_copy(
        update={"id": "jsonld-foreign-ds", "tenant_id": "unreachable-tenant"}
    )
    refused = client.get(
        "/catalog/datasets/jsonld-foreign-ds/jsonld", params={"user": "analyst"}
    )
    assert refused.status_code == 404, refused.text
    assert client.get("/catalog/datasets/crm-customer-master/jsonld").status_code == 403
