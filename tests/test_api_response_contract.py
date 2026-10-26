"""The published 200 schemas must match what the handlers actually return.

``GET /openapi.json`` documented a usable 200 schema on **0 of 60** operations.
Measured at HEAD before ``sdp.api_response_contract``, classifying every
operation's 200 schema::

    54  {"type": "object", "additionalProperties": true}   (a bare ``dict``)
     4  a bare array
     1  {} (empty schema)
     1  a bare type
    --
     0  anything a client could generate a typed model from

Every handler is annotated ``-> dict[str, Any]``, which is true and useless to a
consumer: a buyer generating a client got ``Dict[str, Any]`` for the catalog,
the evidence pack and every governed read.

The schemas are **derived by executing the routes**, because a hand-written
response schema is the exact drift this product exists to refuse - a published
claim that disagrees with the code producing it. This file is the mechanism that
keeps them honest: it fetches every documented operation and validates the live
response against what is published. Regenerate the module with::

    PYTHONPATH=src python3 <<'EOF'
    # see scratchpad/gen_response_contract.py - executes each GET under the
    # anonymous, ?user=admin and ?actor=admin probes, unions the observed
    # shapes, and rewrites src/sdp/api_response_contract.py
    EOF

Reverse-verified: narrowing one published property's type (``number`` ->
``string``) fails ``test_every_published_schema_matches_the_live_response``, and
deleting a route's entry fails ``test_every_json_get_operation_is_covered``.
"""

from __future__ import annotations

from pathlib import Path
import sys

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sdp.api import app  # noqa: E402
from sdp.api_response_contract import (  # noqa: E402
    METRICS_CONTENT_TYPE,
    RESPONSE_SCHEMAS,
    UNPUBLISHED_RESPONSES,
)

client = TestClient(app)

# Path parameters and required query parameters, matching the generator. Kept
# here too so this file can drive every operation without importing the
# generator, which lives outside the repository.
PATH_SUBSTITUTIONS = {
    "{dataset_id}": "crm-customer-master",
    "{node_id}": "crm-customer-master",
    "{connector_id}": "sql_connector",
    "{concept}": "고객",
    "{term}": "고객",
}
REQUIRED_QUERY = {
    "/catalog/search": {"q": "고객"},
    "/ontology/search": {"q": "고객"},
    "/catalog/datasets/{dataset_id}/schema-diff": {
        "from_version": "1.0.0",
        "to_version": "1.0.0",
    },
    "/enterprise/connectors/{connector_id}/probe": {"dataset_id": "crm-customer-master"},
}


def _url(path: str) -> str:
    filled = path
    for placeholder, value in PATH_SUBSTITUTIONS.items():
        filled = filled.replace(placeholder, value)
    return filled


def _fetch(path: str):
    """The first probe that reaches 200, as the generator did."""
    base = dict(REQUIRED_QUERY.get(path, {}))
    last = None
    for params in ({}, {"user": "admin"}, {"actor": "admin"}):
        response = client.get(_url(path), params={**base, **params})
        last = response
        if response.status_code == 200:
            return response
    return last


# No jsonschema dependency in this repository, and the derived schemas use four
# constructs, so the validator is twenty lines rather than a new pin. It is
# deliberately a *superset* check in one direction only: a key present in the
# response but absent from the schema is a failure (the schema under-declares),
# and a key in the schema but absent from the response is allowed (nothing is
# published as required - see the module docstring).
def _violations(value: object, schema: dict, path: str = "$") -> list[str]:
    """Where the live value disagrees with the published schema."""
    if not schema:  # {} means "any", claimed deliberately
        return []
    expected = schema.get("type")
    if expected == "object":
        if not isinstance(value, dict):
            return [f"{path}: published object, got {type(value).__name__}"]
        properties = schema.get("properties")
        if properties is None:
            return []  # "an object", no claim about keys
        found = []
        for key, item in value.items():
            if key not in properties:
                found.append(f"{path}.{key}: present in the response, not published")
                continue
            found.extend(_violations(item, properties[key], f"{path}.{key}"))
        return found
    if expected == "array":
        if not isinstance(value, list):
            return [f"{path}: published array, got {type(value).__name__}"]
        items = schema.get("items") or {}
        found = []
        for index, item in enumerate(value):
            found.extend(_violations(item, items, f"{path}[{index}]"))
        return found
    if expected == "boolean":
        return [] if isinstance(value, bool) else [f"{path}: published boolean, got {value!r}"]
    if expected == "number":
        ok = isinstance(value, (int, float)) and not isinstance(value, bool)
        return [] if ok else [f"{path}: published number, got {value!r}"]
    if expected == "string":
        return [] if isinstance(value, str) else [f"{path}: published string, got {value!r}"]
    return []


def _json_get_operations() -> list[str]:
    """Every GET operation that answers 200 with JSON, derived from the app."""
    paths = []
    for route in app.routes:
        if not isinstance(route, APIRoute) or "GET" not in route.methods:
            continue
        response = _fetch(route.path)
        if response is None or response.status_code != 200:
            continue
        if "json" not in response.headers.get("content-type", ""):
            continue
        paths.append(route.path)
    return sorted(set(paths))


@pytest.mark.parametrize("path", sorted(path for _method, path in RESPONSE_SCHEMAS))
def test_every_published_schema_matches_the_live_response(path: str) -> None:
    """The property that makes a derived schema trustworthy."""
    response = _fetch(path)
    assert response is not None and response.status_code == 200, (
        f"{path} no longer answers 200: {response.status_code if response else 'none'}"
    )
    violations = _violations(response.json(), RESPONSE_SCHEMAS[("GET", path)])
    assert not violations, f"{path} published schema disagrees with the response: {violations}"


def test_every_json_get_operation_is_covered() -> None:
    """Enumerated from the route table, so a new route cannot slip through.

    A GET that answers 200 with JSON and has no published schema is the gap this
    module closes; it must be either published or explicitly declared
    unpublished with a reason.
    """
    published = {path for _method, path in RESPONSE_SCHEMAS}
    declared = {path for method, path in UNPUBLISHED_RESPONSES if method == "GET"}
    missing = [path for path in _json_get_operations() if path not in published | declared]
    assert not missing, f"these JSON GET operations publish no 200 schema: {missing}"


def test_the_unpublished_set_is_accurate() -> None:
    """A declared gap must be a real gap.

    Listing an operation as unpublished when it is in fact published - or naming
    a route that no longer exists - would make the declaration the thing that is
    lying.
    """
    routes = {
        (method, route.path)
        for route in app.routes
        if isinstance(route, APIRoute)
        for method in route.methods
    }
    for key, reason in UNPUBLISHED_RESPONSES.items():
        assert key in routes, f"{key} is declared unpublished and is not a route"
        assert key not in RESPONSE_SCHEMAS, f"{key} is both published and declared unpublished"
        assert reason, key

    # Every operation is either published or declared, with nothing left over.
    assert routes == set(RESPONSE_SCHEMAS) | set(UNPUBLISHED_RESPONSES), sorted(
        routes - (set(RESPONSE_SCHEMAS) | set(UNPUBLISHED_RESPONSES))
    )


def test_the_document_now_publishes_a_usable_schema() -> None:
    """The headline measurement, asserted rather than claimed.

    Was 0 of 60: 54 bare ``{"type": "object", "additionalProperties": true}``,
    4 bare arrays, 1 empty schema, 1 bare type.
    """
    spec = app.openapi()
    usable = 0
    for item in spec["paths"].values():
        for operation in item.values():
            content = (operation.get("responses", {}).get("200", {})).get("content", {})
            schema = (content.get("application/json") or {}).get("schema") or {}
            if schema.get("properties") or (schema.get("items") or {}).get("properties"):
                usable += 1
    assert usable == len(RESPONSE_SCHEMAS), usable
    assert usable >= 38, usable


def test_metrics_is_not_documented_as_json() -> None:
    """A generated client would have tried to JSON-parse Prometheus text.

    Measured before: documented ``application/json`` with an empty schema, while
    the endpoint serves ``text/plain; version=0.0.4; charset=utf-8``.
    """
    spec = app.openapi()
    content = spec["paths"]["/metrics"]["get"]["responses"]["200"]["content"]
    assert "application/json" not in content, content
    assert METRICS_CONTENT_TYPE in content, content
    assert client.get("/metrics").headers["content-type"] == METRICS_CONTENT_TYPE


def test_publishing_responses_did_not_drop_the_other_two_contracts() -> None:
    """Three wrappers now compose over one cached document.

    ``document_responses`` wraps whatever ``app.openapi`` was, so it must call
    that wrapper rather than FastAPI's generator - otherwise the refusal and
    request-body contracts vanish. Both are asserted here as well as in their
    own files, because this is the change that could silently remove them.
    """
    spec = app.openapi()
    refusals = spec["paths"]["/catalog/datasets/{dataset_id}"]["get"]["responses"]
    assert "404" in refusals, sorted(refusals)
    body = spec["paths"]["/catalog/datasets"]["post"].get("requestBody")
    assert body, "the published request body is gone"
    schema = body["content"]["application/json"]["schema"]
    assert "$ref" in schema, schema


def test_no_published_schema_marks_anything_required() -> None:
    """A field may be absent depending on state.

    Marking a key required because one probe returned it would publish a
    constraint the handler does not honour - ``gap_reason``,
    ``invalid_configuration`` and the ``withheld_*`` counters all appear only in
    some states.
    """
    def walk(schema: dict, where: str) -> list[str]:
        found = []
        if "required" in schema:
            found.append(where)
        for key, value in (schema.get("properties") or {}).items():
            found.extend(walk(value, f"{where}.{key}"))
        if schema.get("items"):
            found.extend(walk(schema["items"], f"{where}[]"))
        return found

    offenders = []
    for (_method, path), schema in RESPONSE_SCHEMAS.items():
        offenders.extend(walk(schema, path))
    assert not offenders, offenders


def test_no_published_schema_claims_integer_or_null() -> None:
    """Two type claims the derivation deliberately refuses to make."""
    def walk(schema: dict, where: str) -> list[str]:
        found = []
        if schema.get("type") in {"integer", "null"}:
            found.append(f"{where}: {schema['type']}")
        for key, value in (schema.get("properties") or {}).items():
            found.extend(walk(value, f"{where}.{key}"))
        if schema.get("items"):
            found.extend(walk(schema["items"], f"{where}[]"))
        return found

    offenders = []
    for (_method, path), schema in RESPONSE_SCHEMAS.items():
        offenders.extend(walk(schema, path))
    assert not offenders, offenders


def test_the_probe_schema_covers_every_connector_not_only_the_one_probed() -> None:
    """A route whose shape depends on a path segment needs every segment probed.

    ``_fetch`` substitutes one connector id, so the published schema for
    ``/enterprise/connectors/{connector_id}/probe`` was derived from one
    connector's control rows and the parametrized check above validates it
    against that same one. Measured before this test, over every
    connector/dataset pair that answers 200: the live rows carry eleven keys the
    schema did not publish - ``gap_reason``, the ontology pin's four
    observation fields, the credential vault's four, and
    ``runtime_check_owner`` - because no probed pair has a runtime-verified
    control. A published response schema derived from one of five shapes is the
    drift this module exists to refuse, in the module's own words.
    """
    from sdp.catalog import list_datasets
    from sdp.connectors import _SOURCE_CONNECTORS

    schema = RESPONSE_SCHEMAS[("GET", "/enterprise/connectors/{connector_id}/probe")]
    answered = []
    for connector_id in sorted(_SOURCE_CONNECTORS):
        for dataset in list_datasets():
            response = client.get(
                f"/enterprise/connectors/{connector_id}/probe",
                params={"dataset_id": dataset.id, "user": "admin"},
            )
            if response.status_code != 200:
                continue
            answered.append(f"{connector_id}/{dataset.id}")
            violations = _violations(response.json(), schema)
            assert not violations, (
                f"{connector_id}/{dataset.id} publishes keys the schema does "
                f"not: {violations}"
            )

    assert len(answered) >= 4, (
        "fewer pairs answered 200 than the seed catalogue provides, so this "
        f"validated almost nothing: {answered}"
    )
