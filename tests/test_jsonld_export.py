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
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from sdp import catalog
from sdp.api import JSONLD_CONTEXT, JSONLD_KEYWORDS, app


client = TestClient(app)

# Prefix definitions map to absolute IRIs; term definitions map to prefixed names.
PREFIXES = {name for name, value in JSONLD_CONTEXT.items() if value.startswith("http")}


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
    unmapped: list[tuple[str, str]] = []
    for dataset in catalog.list_datasets(None):
        body = _export(dataset.id)
        for term in body:
            if term in JSONLD_KEYWORDS or term in JSONLD_CONTEXT:
                continue
            unmapped.append((dataset.id, term))
    assert not unmapped, (
        "these terms have no context mapping, so a JSON-LD processor drops them: "
        f"{unmapped}"
    )


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
            assert value.startswith("http"), f"prefix {term} must map to an IRI"
            continue
        assert ":" in value, f"term {term} must map to a prefixed name or IRI, got {value!r}"
        prefix = value.split(":", 1)[0]
        if prefix not in PREFIXES and not value.startswith("http"):
            dangling.append((term, value))
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
