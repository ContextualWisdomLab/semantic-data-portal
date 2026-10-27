"""Derive ``src/sdp/api_response_contract.py`` by executing every GET.

``api_response_contract``'s own docstring says its schemas are "derived by
executing the routes, not written by hand", because a hand-written response
schema is the drift this product exists to refuse. Both that module and
``tests/test_api_response_contract.py`` told the reader to regenerate with "the
script recorded in that test's docstring" - and **that script existed nowhere**:
not in the repository, and the test said so in as many words ("the generator,
which lives outside the repository"). So the rule could not be followed, and
the module had since been hand-edited: regenerating it at ``a2f50c2`` changed
exactly two regions, both of them mis-indented insertions from ``8cda569``
(``probe_semantics``) and ``41dffb1`` (the alert counters). The indentation is
what gave them away.

This file is that script, in the repository, and
``tests/test_api_response_contract.py`` asserts that running it reproduces the
committed module byte for byte - so a hand edit now fails a test instead of
being invisible.

Run it from the repository root::

    PYTHONPATH=src python3 scripts/generate_response_contract.py

Derivation rules (the module's docstring publishes these to readers; this is
where they are implemented):

* GETs only. No request body is ever sent, so a POST or PATCH is never reached
  - a tooling boundary, recorded in ``UNPUBLISHED_RESPONSES`` rather than left
  as a silent gap.
* three probes per operation - anonymous, ``?user=admin``, ``?actor=admin`` -
  and the first to answer 200 is the one described.
* nothing is ``required``: a field may be absent depending on state.
* every number publishes ``number``, never ``integer``, so the superset stays
  true where a field is an int in one state and a float in another.
* ``null`` and an empty array's items publish ``{}`` ("any") rather than a
  claim about a type that was not observed.
* nesting to depth 5; deeper publishes ``type: object`` with no properties.
* an object whose **keys are data** publishes ``additionalProperties`` instead
  of ``properties``. Measured by probing a second catalog state: ``counts`` on
  ``/catalog/facets`` was published as five properties named after the seed's
  Korean domain values, so a generated client got a five-field struct for a map
  and any catalog but the demo seed broke it.
"""

from __future__ import annotations

import json
import pprint
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
TARGET = REPO_ROOT / "src" / "sdp" / "api_response_contract.py"

# Path parameters and required query parameters. Imported by
# ``tests/test_api_response_contract.py`` rather than copied into it: the test
# drives the same operations, and two copies of this table are two things to
# keep in step.
# A fixed first value per placeholder, for callers that need one concrete URL.
# Everything else is derived - see ``path_values``.
PATH_SUBSTITUTIONS = {
    "{dataset_id}": "crm-customer-master",
    "{node_id}": "crm-customer-master",
    "{connector_id}": "sql_connector",
    "{concept}": "고객",
    "{term}": "고객",
}


def path_values() -> dict[str, tuple[str, ...]]:
    """Every value each path placeholder is probed with, derived from the app.

    Several values per placeholder, **unioned**. One value per placeholder is
    how the probe route came to publish one of five shapes: its rows depend on
    the connector and the dataset, and a schema derived from ``sql_connector``
    and ``crm-customer-master`` alone omitted eleven keys the other pairs
    return.

    The connector ids and dataset ids are read from the product rather than
    listed here. A hand-written list already went stale once in this file's
    short life - it guessed ``api_connector`` and ``file_connector`` where the
    product has ``rest_connector`` and ``file_lake_connector``, so one
    connector was never probed and the contract test caught it. The test reads
    the same two sources, so both sides agree by construction.
    """
    from sdp.catalog import list_datasets
    from sdp.connectors import _SOURCE_CONNECTORS

    dataset_ids = tuple(dataset.id for dataset in list_datasets())
    first = dataset_ids[0] if dataset_ids else PATH_SUBSTITUTIONS["{dataset_id}"]
    column = next(
        (
            f"{dataset.id}:{dataset.schema[0].name}"
            for dataset in list_datasets()
            if dataset.schema
        ),
        first,
    )
    return {
        "{dataset_id}": dataset_ids or (first,),
        # A column node as well as a dataset node: the two carry different keys
        # and the route's shape follows the id it is given.
        "{node_id}": (first, column),
        "{connector_id}": tuple(sorted(_SOURCE_CONNECTORS)),
        "{concept}": ("고객",),
        "{term}": ("고객",),
    }
REQUIRED_QUERY = {
    "/catalog/search": {"q": "고객"},
    "/ontology/search": {"q": "고객"},
    "/catalog/datasets/{dataset_id}/schema-diff": {
        "from_version": "1.0.0",
        "to_version": "1.0.0",
    },
    "/enterprise/connectors/{connector_id}/probe": {"dataset_id": "crm-customer-master"},
    # The ledger is newest-first and the default page is 100 rows, and the
    # probe sequence itself files far more than 100 decisions before this path
    # is read. So the rows carrying the *refusal* branches' obligations keys -
    # ``refusal_cause``, ``known_actions``, ``unmapped_published_action``,
    # ``actor_tenant_id``, ``redact`` - were off the end of the page, and
    # ``obligations`` was published as a closed four-key struct for a node the
    # product fills from nine. 500 is the route's own ceiling.
    #
    # This one line is the whole repair. A helper that deliberately drove those
    # branches was written first and removed: regenerating with and without it
    # produced byte-identical output, because the ordinary probing already
    # triggers every one of them - they were observed, just not on page one.
    # A mutation that deleted the helper came back green, which is what said so.
    "/policy/decisions": {"limit": "500"},
}
PROBES: tuple[dict[str, str], ...] = ({}, {"user": "admin"}, {"actor": "admin"})

MAX_DEPTH = 5
PFORMAT_WIDTH = 88
CONTINUATION_PAD = 8

# The second catalog state the map rule is measured against. A new domain is
# what makes a data-keyed object's keys move; the id is deliberately unlike any
# seed id so a leftover cannot be mistaken for seed data.
PROBE_DATASET_ID = "generator-probe-dataset"
PROBE_DOMAIN = "제너레이터프로브"
PROBE_SEED_DATASET = "crm-customer-master"
# The nullability probe's dataset: in no buyer-demo domain. The id is unlike
# any seed id so a leftover cannot be mistaken for seed data.
NON_DEMO_DATASET_ID = "generator-probe-outside-demo"
# Fields the onboarding route derives rather than accepts.
PROBE_EXCLUDED_FIELDS = frozenset(
    {"created_at", "updated_at", "version", "schema_version", "status"}
)


def probe_dataset_body(seed: dict[str, Any]) -> dict[str, Any]:
    """An onboarding body built from a seed dataset, in a new domain.

    Derived from a real dataset rather than hand-written: the create route
    requires twenty-four fields, a literal would go stale the moment the model
    gains one, and a body that fails validation leaves the map rule silently
    unmeasured - which is how ``/catalog/facets`` kept publishing the seed's
    domain values as field names.
    """
    return {
        **{k: v for k, v in seed.items() if k not in PROBE_EXCLUDED_FIELDS},
        "id": PROBE_DATASET_ID,
        "title": "generator probe",
        "domain": PROBE_DOMAIN,
        "owner": "generator-probe",
        "actor": "admin",
    }


def fill_path(path: str) -> str:
    """The concrete URL for a documented path template."""
    filled = path
    for placeholder, value in PATH_SUBSTITUTIONS.items():
        filled = filled.replace(placeholder, value)
    return filled


def fetch(client: Any, path: str) -> Any:
    """The first probe that reaches 200, or the last response if none does."""
    base = dict(REQUIRED_QUERY.get(path, {}))
    last = None
    for params in PROBES:
        response = client.get(fill_path(path), params={**base, **params})
        last = response
        if response.status_code == 200:
            return response
    return last


def path_variants(path: str) -> list[str]:
    """Every concrete URL this template expands to, over ``PATH_VALUES``."""
    urls = [path]
    for placeholder, values in path_values().items():
        if placeholder not in path:
            continue
        urls = [url.replace(placeholder, value) for url in urls for value in values]
    return urls


def fetch_all(client: Any, path: str) -> list[Any]:
    """Every 200 JSON payload this template yields, across its variants.

    A route whose shape depends on a path segment needs every segment probed;
    deriving from one of several shapes is the drift the response contract
    exists to refuse. The query parameters that name a dataset are varied with
    the path for the same reason.
    """
    base = dict(REQUIRED_QUERY.get(path, {}))
    queries = [base]
    if "dataset_id" in base:
        queries = [
            {**base, "dataset_id": value}
            for value in path_values()["{dataset_id}"]
        ]
    payloads = []
    for url in path_variants(path):
        for query in queries:
            for params in PROBES:
                response = client.get(url, params={**query, **params})
                if response.status_code != 200:
                    continue
                if not response.headers.get("content-type", "").startswith(
                    "application/json"
                ):
                    continue
                payloads.append(response.json())
                break
    return payloads


def derive(value: Any, depth: int = 1) -> dict[str, Any]:
    """The schema one observed value supports, claiming nothing more."""
    if value is None:
        return {}
    if isinstance(value, bool):
        return {"type": "boolean"}
    if isinstance(value, (int, float)):
        return {"type": "number"}
    if isinstance(value, str):
        return {"type": "string"}
    if isinstance(value, list):
        if not value:
            # No ``items`` at all: an empty array observes **nothing** about its
            # elements. Returning ``{"items": {}}`` said "observed, and any type
            # fits", and ``union`` then let that swallow a real element type -
            # one empty ``lineage_inputs`` in any probed payload erased the
            # ``string`` the others showed. Same confusion as the properties
            # default, one level down.
            return {"type": "array"}
        items = NOTHING_OBSERVED
        for element in value:
            items = union(items, derive(element, depth + 1))
        return {"type": "array", "items": union(items, items)}
    if isinstance(value, dict):
        if depth >= MAX_DEPTH:
            return {"type": "object"}
        return {
            "type": "object",
            "properties": {
                key: derive(item, depth + 1) for key, item in value.items()
            },
        }
    return {}


NOTHING_OBSERVED: dict[str, Any] | None = None


def _map_value_schema(node: dict[str, Any]) -> dict[str, Any] | None:
    """What this object observation says about a map's values.

    A node already published as a map says it directly. A node observed as a
    struct says the union of its property schemas - every value it carried is a
    value of the map. A node with neither has observed nothing, which is
    ``NOTHING_OBSERVED`` rather than ``{}``: the distinction this module's
    ``union`` rests on, and the one all three of its defaults got wrong.
    """
    if "additionalProperties" in node:
        return node["additionalProperties"]
    merged: dict[str, Any] | None = NOTHING_OBSERVED
    for item in (node.get("properties") or {}).values():
        merged = union(merged, item)
    return merged


def union(left: dict[str, Any] | None, right: dict[str, Any] | None) -> dict[str, Any]:
    """Both observations in one schema, collapsing a conflict to "any".

    Two different observed types collapse to ``{}`` rather than one being
    picked, because picking would publish a claim one probe contradicted.

    ``None`` means *nothing observed yet* and ``{}`` means *observed, and any
    type fits* - a value seen as ``null``, or two conflicting types. Spelling
    both as ``{}`` is what broke the first version of this generator: a field
    seen as ``null`` in one dataset and as a string in another published
    ``string``, so the live response ``steward: None`` failed the contract test
    the generator exists to satisfy.
    """
    if left is None:
        return {} if right is None else right
    if right is None:
        return left
    if not left or not right:
        return {}
    if left.get("type") != right.get("type"):
        return {}
    merged = dict(left)
    if left.get("type") == "object":
        if "additionalProperties" in left or "additionalProperties" in right:
            # The third site of the same defect. ``.get(...) or {}`` said
            # "observed, any type fits" about a side that carries no
            # ``additionalProperties`` at all - and a struct observation does
            # describe a map's values: they are the union of its property
            # schemas. Reading it as "any" let one struct observation erase
            # ``counts``' and ``dataset_status_counts``' ``number``.
            values = union(_map_value_schema(left), _map_value_schema(right))
            return {"type": "object", "additionalProperties": values}
        if "properties" not in left or "properties" not in right:
            merged.pop("properties", None)
            return merged
        properties = dict(left["properties"])
        for key, item in right["properties"].items():
            # ``NOTHING_OBSERVED``, not ``{}``. The distinction above is the
            # whole point of the sentinel, and this line used to supply ``{}``
            # as the default - which says "observed, and any type fits" about a
            # key the left observation never carried. ``union({}, typed)``
            # collapses to ``{}``, so every field a *second* probe introduced
            # lost its measured type and was published untyped. Measured:
            # union({"a": string}, {"a": string, "b": integer}) put ``b`` at
            # ``{}``. The same default is used recursively, so nested objects
            # lost theirs too.
            properties[key] = union(properties.get(key, NOTHING_OBSERVED), item)
        merged["properties"] = properties
    elif left.get("type") == "array":
        # ``NOTHING_OBSERVED`` as the default, not ``{}`` - an absent ``items``
        # means no element was ever seen, and must yield to a side that saw one.
        items = union(
            left.get("items", NOTHING_OBSERVED), right.get("items", NOTHING_OBSERVED)
        )
        if items or "items" in left or "items" in right:
            merged["items"] = items
        else:
            merged.pop("items", None)
    return merged


def observed_keys(value: Any) -> set[str] | None:
    """Every key this node was observed to carry, or ``None`` if it is not one.

    An array's elements are **unioned**, the same way ``derive`` unions their
    types. Comparing against only the first element - which the first version of
    this rule did - reports a heterogeneous array as data-keyed: the unioned
    schema legitimately carries more keys than element zero, and
    ``/enterprise/observability``'s alerts, the SHACL shape list and the JSON-LD
    ``@graph`` were all collapsed into untyped maps by that mistake.
    """
    if isinstance(value, dict):
        return set(value)
    if isinstance(value, list):
        keys: set[str] = set()
        for element in value:
            if not isinstance(element, dict):
                return None
            keys |= set(element)
        return keys if value else None
    return None


def element_values(value: Any) -> list[Any]:
    """The values whose types a data-keyed node's ``additionalProperties`` covers."""
    if isinstance(value, dict):
        return list(value.values())
    if isinstance(value, list):
        found = []
        for element in value:
            if isinstance(element, dict):
                found.extend(element.values())
        return found
    return []


def as_map_where_keys_are_data(
    schema: dict[str, Any], other: Any, depth: int = 1
) -> dict[str, Any]:
    """Publish ``additionalProperties`` where the observed keys moved.

    ``other`` is the same node observed in a second catalog state. A key set
    that differs between states is data, not a field list, and publishing it as
    ``properties`` hands a client a struct where the product returns a map.
    Recurses so a data-keyed object nested inside a field is found too.

    A field that is simply *absent* in one state does not qualify: the key sets
    would differ while the node is still a struct, so only a key the other state
    has and this one does not counts. That asymmetry is deliberate - nothing is
    published as ``required``, so a conditionally present field is expected.
    """
    if schema.get("type") == "array":
        return {
            **schema,
            "items": as_map_where_keys_are_data(
                schema.get("items") or {}, other, depth + 1
            ),
        }
    if schema.get("type") != "object" or "properties" not in schema:
        return schema
    seen = observed_keys(other)
    if seen is not None and seen - set(schema["properties"]):
        values = NOTHING_OBSERVED
        for item in schema["properties"].values():
            values = union(values, item)
        for item in element_values(other):
            values = union(values, derive(item, depth + 1))
        return {"type": "object", "additionalProperties": union(values, values)}
    properties = {
        key: as_map_where_keys_are_data(item, _child(other, key), depth + 1)
        for key, item in schema["properties"].items()
    }
    return {**schema, "properties": properties}


def _child(other: Any, key: str) -> Any:
    """This key's value in the second state: one node, or every element's."""
    if isinstance(other, dict):
        return other.get(key)
    if isinstance(other, list):
        found = [
            element[key]
            for element in other
            if isinstance(element, dict) and key in element
        ]
        if not found:
            return None
        if all(isinstance(item, dict) for item in found):
            merged: dict[str, Any] = {}
            for item in found:
                merged.update(item)
            return merged
        flattened = []
        for item in found:
            if isinstance(item, list):
                flattened.extend(item)
            else:
                return found[0]
        return flattened
    return None


def json_get_operations(app: Any) -> list[str]:
    """Every documented GET path, in the app's own route order."""
    from fastapi.routing import APIRoute

    paths = []
    for route in app.routes:
        if isinstance(route, APIRoute) and "GET" in route.methods:
            if route.path not in paths:
                paths.append(route.path)
    return paths


def render_block(name: str, annotation: str, entries: dict[Any, Any]) -> str:
    """One generated assignment, in the module's existing shape."""
    lines = [f"{name}: {annotation} = {{"]
    for (method, route), value in entries.items():
        body = pprint.pformat(value, width=PFORMAT_WIDTH, sort_dicts=False)
        body = body.replace("\n", "\n" + " " * CONTINUATION_PAD)
        lines.append(f'    ("{method}", "{route}"): {body},')
    lines.append("}")
    return "\n".join(lines) + "\n"


def non_demo_dataset_body() -> dict[str, Any]:
    """An onboarding body for a dataset belonging to no buyer-demo domain.

    Built from a seed dataset, keeping its domain so no key set moves. The only
    property that matters is that this id is in none of
    ``buyer_demo_domains()``'s ``dataset_ids``, which is what makes
    ``demo_context`` observable as ``null``.
    """
    from sdp.catalog import get_dataset

    seed = json.loads(get_dataset(PROBE_SEED_DATASET).model_dump_json())
    body = {
        key: value for key, value in seed.items() if key not in PROBE_EXCLUDED_FIELDS
    }
    body["id"] = NON_DEMO_DATASET_ID
    body["title"] = "generator nullability probe"
    body["actor"] = "admin"
    return body


def generate() -> str:
    """The regenerated module text, with the hand-written prose preserved."""
    sys.path.insert(0, str(REPO_ROOT / "src"))
    from fastapi.testclient import TestClient

    from sdp.api import app
    from sdp.api_response_contract import UNPUBLISHED_RESPONSES
    from sdp.catalog import get_dataset

    client = TestClient(app)
    paths = json_get_operations(app)

    first_state: dict[str, list[Any]] = {}
    for path in paths:
        payloads = fetch_all(client, path)
        if payloads:
            first_state[path] = payloads

    # The second catalog state, for the map rule only. Its observations never
    # enter the published types - they decide whether a node's keys are data.
    seed = json.loads(get_dataset(PROBE_SEED_DATASET).model_dump_json())
    created = client.post("/catalog/datasets", json=probe_dataset_body(seed))
    if created.status_code not in {200, 201}:
        raise SystemExit(
            "the map-rule probe could not onboard a dataset "
            f"({created.status_code}): {created.text[:300]}\n"
            "Without a second catalog state a data-keyed object cannot be told "
            "from a field list, so the contract would be regenerated with the "
            "defect this rule exists to catch."
        )
    second_state: dict[str, list[Any]] = {}
    for path in paths:
        payloads = fetch_all(client, path)
        if payloads:
            second_state[path] = payloads

    # The third state: one dataset in no buyer-demo domain, for nullability.
    outside = client.post("/catalog/datasets", json=non_demo_dataset_body())
    if outside.status_code not in {200, 201}:
        raise SystemExit(
            "the nullability probe could not onboard a dataset outside the "
            f"buyer-demo domains ({outside.status_code}): {outside.text[:300]}"
        )
    third_state: dict[str, list[Any]] = {}
    for path in paths:
        payloads = fetch_all(client, path)
        if payloads:
            third_state[path] = payloads

    schemas: dict[tuple[str, str], dict[str, Any]] = {}
    # Sorted, so the committed file's order is a property of the generator and
    # not of the app's route registration order.
    for path in sorted(first_state):
        if ("GET", path) in UNPUBLISHED_RESPONSES:
            continue
        schema = NOTHING_OBSERVED
        for payload in first_state[path]:
            schema = union(schema, derive(payload))
        schema = union(schema, schema)
        for other in second_state.get(path, []):
            schema = as_map_where_keys_are_data(schema, other)
        # Types only, and strictly **after** the map rule. Every seed dataset
        # belongs to a buyer-demo domain, so ``demo_context`` on the connector
        # probe was only ever observed as an object - the product returns
        # ``null`` for any dataset outside those domains, and the contract
        # published a non-nullable object a client breaks on.
        #
        # Two earlier attempts are recorded because both were wrong: unioning
        # the second state into the types, and onboarding this dataset before
        # the first observation. Each destroys the map rule, which compares the
        # schema's key set against the second state's - once those keys are in
        # the schema there is nothing left to differ, and ``details`` reverted
        # from a map to a closed struct. Applying a third state after the rule
        # has already fired cannot do that.
        for payload in third_state.get(path, []):
            schema = union(schema, derive(payload))
        schemas[("GET", path)] = schema

    text = TARGET.read_text()
    start = text.index("RESPONSE_SCHEMAS: dict[tuple[str, str], dict[str, Any]] = {\n")
    end = text.index("\n}\n", start) + len("\n}\n")
    block = render_block(
        "RESPONSE_SCHEMAS", "dict[tuple[str, str], dict[str, Any]]", schemas
    )
    return text[:start] + block + text[end:]


def main() -> int:
    """Rewrite the module and report whether it changed."""
    regenerated = generate()
    if TARGET.read_text() == regenerated:
        print(f"{TARGET.relative_to(REPO_ROOT)} is already up to date")
        return 0
    TARGET.write_text(regenerated)
    print(f"rewrote {TARGET.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
