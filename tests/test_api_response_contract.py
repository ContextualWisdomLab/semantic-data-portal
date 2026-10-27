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

    PYTHONPATH=src python3 scripts/generate_response_contract.py

That command used to point at a heredoc referring to
``scratchpad/gen_response_contract.py``, and **no such file existed** - this
docstring even described the generator as living "outside the repository", and
the probe configuration was duplicated here with a comment saying so. A rule
nobody can run is not a rule: the module had been hand-edited, and regenerating
it changed exactly two mis-indented regions. The generator is now in the
repository, this file imports its probe configuration instead of copying it, and
``test_regenerating_reproduces_the_committed_module`` holds the committed module
to the generator's output.

Reverse-verified: narrowing one published property's type (``number`` ->
``string``) fails ``test_every_published_schema_matches_the_live_response``,
deleting a route's entry fails ``test_every_json_get_operation_is_covered``, and
hand-editing the module fails the idempotence check. Each generator rule is
defended by the guard that exists for it, checked by mutating the generator and
*regenerating*: dropping the data-keyed-map rule fails
``test_a_new_domain_does_not_break_the_published_facets_schema``, probing one
connector instead of every one fails
``test_the_probe_schema_covers_every_connector_not_only_the_one_probed``, and
confusing "observed null" with "nothing observed" fails the live-response check.
"""

from __future__ import annotations

from pathlib import Path
import re
import sys

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
# The repository root too, for ``scripts.generate_response_contract``. It used
# to rely on the root being on the path by virtue of being the working
# directory, which it is under ``python -m pytest`` from the root - and only
# then. Collected from anywhere else the module raised
# ``ModuleNotFoundError: No module named 'scripts'``, so the contract tests
# depended on how they were invoked rather than on the tree.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sdp.api import app  # noqa: E402
from sdp.api_response_contract import (  # noqa: E402
    METRICS_CONTENT_TYPE,
    RESPONSE_SCHEMAS,
    UNPUBLISHED_RESPONSES,
)

client = TestClient(app)

# The probe configuration is **imported** from the generator, not copied. It
# used to be duplicated here with the comment "kept here too so this file can
# drive every operation without importing the generator, which lives outside the
# repository" - and that was the defect: the generator existed nowhere, so the
# module's "derived, never hand-written" rule could not be followed and the file
# had since been hand-edited (two mis-indented regions gave it away). The script
# is now at ``scripts/generate_response_contract.py`` and this file holds it to
# its output.
from scripts import generate_response_contract as generator  # noqa: E402
from scripts.generate_response_contract import (  # noqa: E402
    PATH_SUBSTITUTIONS,
    PROBES,
    REQUIRED_QUERY,
    fill_path as _url,
    generate as _regenerate,
)

GENERATOR = Path(__file__).resolve().parents[1] / "scripts" / "generate_response_contract.py"


def _fetch(path: str):
    """The first probe that reaches 200, as the generator does."""
    base = dict(REQUIRED_QUERY.get(path, {}))
    last = None
    for params in PROBES:
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
        if "additionalProperties" in schema:
            # A data-keyed map: every key's value is described by one schema.
            # The construct exists because five nodes are keyed by data - the
            # authoritative list is in ``api_response_contract``'s docstring and
            # ``test_the_data_keyed_nodes_are_the_ones_the_prose_names`` below
            # holds the two together. Publishing the seed's observed keys as a
            # field list handed a client a struct where the product returns a
            # map.
            values = schema["additionalProperties"]
            found = []
            for key, item in value.items():
                found.extend(_violations(item, values, f"{path}.{key}"))
            return found
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


def test_the_generator_the_docstrings_name_exists() -> None:
    """Both docstrings told the reader to run a script that was nowhere.

    ``api_response_contract`` said "derived by executing the routes, not written
    by hand... Regenerate with the script recorded in that test's docstring",
    and this file's docstring pointed at a heredoc in a scratchpad. Neither the
    repository nor that scratchpad held it, so the rule was unfollowable and the
    module was hand-edited instead.
    """
    assert GENERATOR.is_file(), GENERATOR
    source = GENERATOR.read_text()
    assert "PYTHONPATH=src python3 scripts/generate_response_contract.py" in source


@pytest.mark.parametrize("module", ["src/sdp/api_response_contract.py"])
def test_regenerating_reproduces_the_committed_module(module: str) -> None:
    """The property that makes "derived, not hand-written" checkable.

    Running the generator must reproduce the committed file byte for byte, so a
    hand edit fails here instead of being invisible. Regenerating at ``a2f50c2``
    changed exactly two regions, both mis-indented insertions from ``8cda569``
    and ``41dffb1``.
    """
    committed = (Path(__file__).resolve().parents[1] / module).read_text()
    assert _regenerate() == committed, (
        "the committed response contract is not what the generator produces - "
        "run: PYTHONPATH=src python3 scripts/generate_response_contract.py"
    )


def test_a_new_domain_does_not_break_the_published_facets_schema() -> None:
    """The map rule, from the buyer's side rather than the generator's.

    ``counts`` was published as five properties named after the seed's Korean
    domain values, so a client generated from the document got a five-field
    struct for a map and any catalog but the demo seed broke it. Onboarding one
    dataset in a new domain is enough to show it.
    """
    from sdp.catalog import get_dataset
    import json as _json

    seed = _json.loads(get_dataset("crm-customer-master").model_dump_json())
    body = {
        **{
            key: item
            for key, item in seed.items()
            if key
            not in {"created_at", "updated_at", "version", "schema_version", "status"}
        },
        "id": "facets-map-probe",
        "title": "facets map probe",
        "domain": "지표프로브",
        "owner": "facets-map-probe",
        "actor": "admin",
    }
    created = client.post("/catalog/datasets", json=body)
    assert created.status_code == 200, created.text

    response = client.get("/catalog/facets", params={"user": "admin"})
    assert response.status_code == 200, response.text
    assert "지표프로브" in response.json()["counts"], response.json()
    published = RESPONSE_SCHEMAS[("GET", "/catalog/facets")]
    assert _violations(response.json(), published) == [], _violations(
        response.json(), published
    )


# ---------------------------------------------------------------------------
# ``union`` is the generator's whole merge rule, and it drew a careful
# distinction in its docstring - ``None`` is "nothing observed yet", ``{}`` is
# "observed, and any type fits" - then violated it one paragraph later:
#
#     properties[key] = union(properties.get(key, {}), item)
#
# ``.get(key, {})`` says "observed, any type fits" about a key the left
# observation never carried, and ``union({}, typed)`` collapses to ``{}``. So
# every field a *second* probe introduced lost its measured type and was
# published as untyped. The default has to be ``NOTHING_OBSERVED``.
# ---------------------------------------------------------------------------


def _object(**properties: dict) -> dict:
    """One observed object schema, spelled the way ``derive`` spells it."""
    return {"type": "object", "properties": dict(properties)}


def test_a_field_only_the_second_observation_carries_keeps_its_type() -> None:
    """The defect. ``b`` was published untyped despite being measured once."""
    merged = generator.union(
        _object(a={"type": "string"}),
        _object(a={"type": "string"}, b={"type": "integer"}),
    )
    assert merged["properties"]["b"] == {"type": "integer"}, merged["properties"]


def test_a_field_only_the_first_observation_carries_keeps_its_type() -> None:
    """The mirror case, which already worked - asserted so a fix cannot trade one for the other."""
    merged = generator.union(
        _object(a={"type": "string"}, b={"type": "integer"}),
        _object(a={"type": "string"}),
    )
    assert merged["properties"]["b"] == {"type": "integer"}, merged["properties"]


def test_a_field_observed_as_null_still_collapses_to_any() -> None:
    """The distinction must survive the fix: observed-and-untypable is not unobserved.

    This is the case the generator was built for - ``steward`` is ``None`` on
    one dataset and a string on another - so a repair that made ``{}`` yield to
    a type would republish the claim that broke the live-match test.
    """
    merged = generator.union(
        _object(steward={}),
        _object(steward={"type": "string"}),
    )
    assert merged["properties"]["steward"] == {}, merged["properties"]


def test_two_conflicting_types_still_collapse_to_any() -> None:
    """Picking one would publish a claim the other probe contradicted."""
    merged = generator.union(
        _object(value={"type": "string"}),
        _object(value={"type": "integer"}),
    )
    assert merged["properties"]["value"] == {}, merged["properties"]


def test_the_sentinel_for_nothing_observed_is_not_the_empty_schema() -> None:
    """The premise the two cases above rest on, asserted rather than assumed."""
    assert generator.NOTHING_OBSERVED is None
    assert generator.union(generator.NOTHING_OBSERVED, {"type": "integer"}) == {"type": "integer"}
    assert generator.union({}, {"type": "integer"}) == {}


def test_nesting_does_not_lose_a_second_observation_either() -> None:
    """The same default is used recursively, so the fix has to hold at depth."""
    merged = generator.union(
        {"type": "object", "properties": {"outer": _object(a={"type": "string"})}},
        {"type": "object", "properties": {"outer": _object(a={"type": "string"}, b={"type": "boolean"})}},
    )
    assert merged["properties"]["outer"]["properties"]["b"] == {"type": "boolean"}


def _data_keyed_nodes() -> set[str]:
    """Every published node whose keys are data, read off the schemas."""
    found: set[str] = set()

    def walk(node: object, path: str) -> None:
        if not isinstance(node, dict):
            return
        if node.get("type") == "object" and "additionalProperties" in node:
            found.add(path)
        for name, child in (node.get("properties") or {}).items():
            walk(child, f"{path}.{name}")
        if "items" in node:
            walk(node["items"], f"{path}[]")

    for (_method, path), schema in RESPONSE_SCHEMAS.items():
        walk(schema, path)
    return found


def test_the_data_keyed_nodes_are_the_ones_the_prose_names() -> None:
    """The module docstring lists them; a list nobody checks goes stale.

    It did. It said four, named ``/policy/decisions[].obligations`` - which was
    published as a closed four-key struct, so the rule had never fired on it -
    and omitted ``/catalog/datasets/{dataset_id}/audit[].details`` altogether.
    Wrong in both directions at once, with the count wrong to match.
    """
    import sdp.api_response_contract as module

    prose = module.__doc__ or ""
    measured = _data_keyed_nodes()
    assert len(measured) == 5, sorted(measured)

    # The *enumeration*, not the whole docstring. Matching anywhere in the
    # prose was too loose: removing a node from the list left it mentioned in
    # the paragraph below that explains the list, and the mutation came back
    # green. The sentence runs from "keyed by data" to the first full stop that
    # ends it, which is where the nodes are enumerated.
    marker = "nodes are keyed by data"
    assert marker in prose, prose[:200]
    enumeration = prose.split(marker, 1)[1].split("The generator tells", 1)[0]
    listed = set(re.findall(r"``([^`]+)``", enumeration))
    missing = sorted(node for node in measured if node not in listed)
    assert not missing, (
        "these data-keyed nodes are not in the docstring's list, so a client "
        f"reading it would generate a struct for a map: {missing}"
    )
    extra = sorted(name for name in listed if name not in measured)
    assert not extra, (
        f"the docstring lists nodes that are not published as maps: {extra}"
    )
    assert "**Five**" in prose or f"**{len(measured)}**" in prose, prose[:200]


def test_the_obligations_node_is_a_map_because_its_keys_vary() -> None:
    """A node the product fills from nine keys must not publish four of them.

    What achieves it is the ledger page size in ``REQUIRED_QUERY``: the probe
    sequence files more than a hundred decisions before this path is read, so
    the refusal branches' rows were off the end of the default page. Dropping
    that one query parameter republishes the four-key struct, which is the
    mutation this assertion answers.

    A helper that deliberately drove those branches was written first and then
    removed - regenerating with and without it gave byte-identical output. This
    docstring claimed the helper was what held the property up; it was not, and
    the mutation that deleted it came back green rather than red.
    """
    obligations = RESPONSE_SCHEMAS[("GET", "/policy/decisions")]["items"]["properties"][
        "obligations"
    ]
    assert "additionalProperties" in obligations, obligations
    assert "properties" not in obligations, obligations


# ---------------------------------------------------------------------------
# ``union``'s sentinel confusion had three sites, not one. ``None`` is "nothing
# observed yet" and ``{}`` is "observed, and any type fits", and three defaults
# spelled the first as the second:
#
#   properties[key] = union(properties.get(key, {}), item)          <- fixed earlier
#   merged["items"] = union(left.get("items") or {}, ...)           <- here
#   union(left.get("additionalProperties") or {}, ...)              <- here
#
# Each let one observation that saw nothing erase a type another had measured.
# ---------------------------------------------------------------------------


def test_an_empty_array_observes_nothing_about_its_elements() -> None:
    """``derive([])`` must not claim "any element type fits"."""
    assert generator.derive([]) == {"type": "array"}
    assert "items" not in generator.derive([])


def test_an_empty_array_does_not_erase_a_measured_element_type() -> None:
    """The defect: one empty ``lineage_inputs`` erased the ``string``."""
    empty = generator.derive([])
    typed = generator.derive(["a"])
    assert generator.union(empty, typed) == {"type": "array", "items": {"type": "string"}}
    assert generator.union(typed, empty) == {"type": "array", "items": {"type": "string"}}


def test_two_empty_arrays_still_claim_nothing() -> None:
    """The other direction: nothing observed must not become "any"."""
    assert generator.union(generator.derive([]), generator.derive([])) == {"type": "array"}


def test_an_array_observed_as_two_types_still_collapses_to_any() -> None:
    """The guard against over-correcting, as for ``properties``."""
    merged = generator.union(generator.derive(["a"]), generator.derive([1]))
    assert merged == {"type": "array", "items": {}}, merged


def test_a_struct_observation_describes_a_maps_values() -> None:
    """A map unioned with a struct keeps the value type the struct carried.

    ``.get("additionalProperties") or {}`` read a struct observation as "any",
    so one such observation erased ``counts``' and
    ``dataset_status_counts``' ``number``.
    """
    as_map = {"type": "object", "additionalProperties": {"type": "number"}}
    as_struct = {"type": "object", "properties": {"고객": {"type": "number"}}}
    assert generator.union(as_map, as_struct) == as_map
    assert generator.union(as_struct, as_map) == as_map


def test_a_struct_of_mixed_types_widens_the_maps_values() -> None:
    """And it must widen honestly when the struct's values disagree."""
    as_map = {"type": "object", "additionalProperties": {"type": "number"}}
    mixed = {"type": "object", "properties": {"a": {"type": "number"}, "b": {"type": "string"}}}
    merged = generator.union(as_map, mixed)
    assert merged == {"type": "object", "additionalProperties": {}}, merged


def test_the_counted_maps_still_publish_their_value_type() -> None:
    """End to end, on the committed contract rather than on synthetic input."""
    facets = RESPONSE_SCHEMAS[("GET", "/catalog/facets")]["properties"]["counts"]
    assert facets == {"type": "object", "additionalProperties": {"type": "number"}}, facets


def test_demo_context_is_published_as_nullable() -> None:
    """The third probe state's whole purpose.

    ``buyer_demo_context_for_dataset`` returns ``None`` for any dataset in no
    buyer-demo domain, and every *seed* dataset is in one - so the connector
    probe's ``demo_context`` was only ever observed as an object and published
    as a non-nullable one. A client generated from the document broke on the
    first dataset outside those domains.
    """
    probe = RESPONSE_SCHEMAS[("GET", "/enterprise/connectors/{connector_id}/probe")]
    assert probe["properties"]["demo_context"] == {}, probe["properties"]["demo_context"]


def test_the_nullability_probe_runs_after_the_map_rule() -> None:
    """Order is the property here, and it is the one two attempts got wrong.

    Unioning the second (new-domain) state into the types, and onboarding the
    non-demo dataset before the first observation, each destroy the map rule:
    it compares the schema's key set against the second state's, and once those
    keys are in the schema nothing differs. Measured both times - ``details``
    reverted from a map to a closed struct. The third state is applied after
    the rule has fired, which cannot do that.
    """
    source = GENERATOR.read_text()
    map_rule = source.index("as_map_where_keys_are_data(schema, other)")
    third = source.index("for payload in third_state.get(path, []):")
    assert map_rule < third, (
        "the nullability state is unioned before the map rule has fired, which "
        "destroys it"
    )
    # And the map rule's own result is still there to prove it did fire.
    details = RESPONSE_SCHEMAS[("GET", "/audit/events")]["items"]["properties"]["details"]
    assert "additionalProperties" in details, details
