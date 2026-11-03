"""The facet route enforced a vocabulary that appeared in no published document.

Measured at ``dba2403`` as ``user=data-admin``::

    GET /catalog/facets?field=domain -> 200 {"field": "domain", "counts": {...}}
    GET /catalog/facets?field=tags   -> 400 {"detail": "unsupported facet field"}
    GET /catalog/facets?field=terms  -> 400 {"detail": "unsupported facet field"}

    README.md                    grep -in "facet" -> zero hits (route absent)
    GET /openapi.json            {"name": "field", "schema": {"type": "string",
                                  "default": "domain"}}  - no enum, no description
    docs/implementation-compliance.md:22,25  names the route, not its field values

So the only way to learn a valid value was to read ``src/sdp/catalog.py:650``. The
repository ships the opposite pattern on a sibling refusal and advertises it -
``GET /ontology/patches?status=`` answers 400 with ``requested`` and
``known_statuses`` - and closed this very defect class on ``POST
/policy/decision``'s ``action`` four hours earlier by publishing the engine's own
enumeration.

The two values a buyer tries first are the two the product's own PRD publishes as
facet dimensions: ``docs/prd-trd.md`` marks ``businessTerms`` as "keyword + facet"
and CAT-001 names ``tags`` as a search/facet dimension. Both were refused, and
``list_facet_counts`` has had a list-valued branch all along that **no**
allow-listed field could reach: measured, all six were scalars, so the only thing
exercising that branch was a test fabricating ``domain: ["retail", "wholesale"]``,
which the ``Dataset.domain: str`` contract forbids. The capability existed for
exactly the dimensions the route refused.
"""

from __future__ import annotations

import pathlib
import re

from typing import Any

import pytest

from fastapi.testclient import TestClient

from sdp import catalog
from sdp.api import app


client = TestClient(app)

# The dimensions the PRD publishes as facets, which were refused.
PRD_PUBLISHED_FACETS = ("tags", "terms")


def test_every_enforced_field_answers_and_the_set_is_derived() -> None:
    """Driven from the constant, so the two cannot drift apart."""
    assert catalog.FACET_FIELDS, "the enforced set is empty"
    for field in sorted(catalog.FACET_FIELDS):
        response = client.get(f"/catalog/facets?field={field}&user=data-admin")
        assert response.status_code == 200, (field, response.text)
        body = response.json()
        assert body["field"] == field
        assert isinstance(body["counts"], dict), body


def test_the_refusal_names_the_rejected_value_and_the_supported_set() -> None:
    """The shape ``?status=`` already uses, on the route that withheld it."""
    response = client.get("/catalog/facets?field=not_a_field&user=data-admin")
    assert response.status_code == 400, response.text
    detail = response.json()["detail"]
    assert isinstance(detail, dict), detail
    assert detail["requested"] == "not_a_field", detail
    assert detail["known_fields"] == sorted(catalog.FACET_FIELDS), detail
    assert detail["error"], detail


@pytest.mark.parametrize("field", PRD_PUBLISHED_FACETS)
def test_the_dimensions_the_prd_publishes_as_facets_are_countable(field: str) -> None:
    """And counted per value, which is the list branch nothing could reach."""
    assert field in catalog.FACET_FIELDS, field
    response = client.get(f"/catalog/facets?field={field}&user=data-admin")
    assert response.status_code == 200, response.text
    counts = response.json()["counts"]
    assert counts, f"{field} counted nothing on the seeded catalogue: {counts}"
    # A list-valued dimension sums to more than the dataset count when datasets
    # carry several values, and every key is one value rather than one list.
    for key in counts:
        assert not key.startswith("["), f"a whole list became one facet key: {key!r}"


def test_the_published_parameter_description_carries_the_vocabulary() -> None:
    """OpenAPI is where a buyer looks before reading the source."""
    document = client.get("/openapi.json").json()
    parameters = document["paths"]["/catalog/facets"]["get"]["parameters"]
    field = next(item for item in parameters if item["name"] == "field")
    described = field.get("description") or ""
    for value in sorted(catalog.FACET_FIELDS):
        assert value in described, (value, described)
    assert field["schema"].get("default") in catalog.FACET_FIELDS, field["schema"]


def test_the_readme_publishes_the_route_and_its_vocabulary() -> None:
    """The route was absent from README entirely."""
    readme = pathlib.Path(__file__).resolve().parents[1] / "README.md"
    text = readme.read_text(encoding="utf-8")
    assert "/catalog/facets" in text, "the route is still absent from README"
    line = next(line for line in text.splitlines() if "/catalog/facets" in line)
    window = text[text.index(line) : text.index(line) + 600]
    for value in sorted(catalog.FACET_FIELDS):
        assert value in window, (value, window[:300])


def test_the_enforced_vocabulary_lives_in_exactly_one_place() -> None:
    """Structural: a second literal is how the published set goes stale."""
    import inspect

    enforcement = inspect.getsource(catalog.list_facet_counts)
    code = "\n".join(
        line for line in enforcement.splitlines() if not line.lstrip().startswith("#")
    )
    assert "FACET_FIELDS" in code, code
    # The enforcement site must not carry a set literal of its own. Asserting
    # "at most one literal in the module" was the first version and it passed a
    # reintroduced literal, because the constant is written as a multi-line
    # ``frozenset`` and so matched no brace pattern - the duplicate was then the
    # only match and "at most one" held. Only the behavioural guards caught that
    # mutation, and they caught it because the duplicate happened to differ.
    literals = re.findall(r'\{\s*"[a-z_]+"\s*,', code)
    assert not literals, (
        f"the facet vocabulary is written out again at the enforcement site: {literals}"
    )
    api_source = pathlib.Path(
        pathlib.Path(catalog.__file__).parent / "api.py"
    ).read_text(encoding="utf-8")
    assert "FACET_FIELDS" in api_source, "the route re-derives the set instead of reading it"
