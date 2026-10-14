"""The published request-body schema must be the contract the handler enforces.

Fifteen of the twenty routes with a body took ``payload: dict[str, Any]``, so
``GET /openapi.json`` described them as ``{"type": "object",
"additionalProperties": true}`` - a generated client saw ``object`` and not one
field name, including for ``POST /catalog/datasets`` (onboarding) and
``POST /browse/query`` (the governed query).

For four of them the contract already existed as a pydantic model; the dict
parameter is there only to turn a ``ValidationError`` into this repository's
``400 {"error": "invalid_request", "fields": [...]}`` shape rather than
FastAPI's 422. So the document was simply not saying what was already enforced.

The guard is **not** "a schema is published". It is that the model named for
each route is the model the handler actually constructs, checked by walking the
AST of ``sdp.api`` - otherwise the document would be free to advertise a schema
nobody validates against, which is a more useful-looking lie than
``additionalProperties: true``.
"""

from __future__ import annotations

import ast
import pathlib

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from sdp.api import app
from sdp.api_request_contract import REQUEST_BODY_MODELS


client = TestClient(app)
API_SOURCE = pathlib.Path(__file__).resolve().parents[1] / "src" / "sdp" / "api.py"
ROUTE_DECORATOR_METHODS = {"get", "post", "patch", "put", "delete"}


def _models_constructed_per_route() -> dict[tuple[str, str], set[str]]:
    """Per route, the contract-model names its handler constructs.

    Transitive through other route handlers, so the versioned alias
    ``POST /api/v1/browse/query`` - which just calls ``browse_query`` - resolves
    to the same model rather than looking unvalidated.
    """
    tree = ast.parse(API_SOURCE.read_text())
    functions: dict[str, ast.AST] = {}
    routes: list[tuple[str, list[tuple[str, str]]]] = []
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        functions[node.name] = node
        decorated = [
            (deco.func.attr.upper(), deco.args[0].value)
            for deco in node.decorator_list
            if isinstance(deco, ast.Call)
            and isinstance(deco.func, ast.Attribute)
            and deco.func.attr in ROUTE_DECORATOR_METHODS
            and getattr(deco.func.value, "id", "") == "app"
            and deco.args
        ]
        if decorated:
            routes.append((node.name, decorated))

    known = {model.__name__ for model in REQUEST_BODY_MODELS.values()}

    def called_functions(node: ast.AST) -> set[str]:
        names = {
            getattr(sub.func, "id", None)
            for sub in ast.walk(node)
            if isinstance(sub, ast.Call)
        }
        return {name for name in names if name in functions}

    def constructed(name: str, seen: set[str] | None = None) -> set[str]:
        seen = seen or set()
        if name in seen:
            return set()
        seen.add(name)
        node = functions[name]
        found = {
            getattr(sub.func, "id", None)
            for sub in ast.walk(node)
            if isinstance(sub, ast.Call) and getattr(sub.func, "id", None) in known
        }
        for callee in called_functions(node):
            found |= constructed(callee, seen)
        return {name for name in found if name}

    return {key: constructed(fn) for fn, decorated in routes for key in decorated}


CONSTRUCTED = _models_constructed_per_route()


@pytest.mark.parametrize(
    "method,path", sorted(REQUEST_BODY_MODELS), ids=lambda value: str(value)
)
def test_the_published_model_is_the_one_the_handler_validates_with(
    method: str, path: str
) -> None:
    model = REQUEST_BODY_MODELS[(method, path)]
    constructed = CONSTRUCTED.get((method, path), set())
    assert model.__name__ in constructed, (
        f"{method} {path} publishes {model.__name__} but its handler constructs "
        f"{sorted(constructed) or 'no contract model'}"
    )


@pytest.mark.parametrize(
    "method,path", sorted(REQUEST_BODY_MODELS), ids=lambda value: str(value)
)
def test_each_route_publishes_its_model_as_a_resolvable_ref(
    method: str, path: str
) -> None:
    from sdp.api_request_contract import (
        REQUEST_BODY_EXTRA_PROPERTIES,
        _body_component_name,
    )

    spec = client.get("/openapi.json").json()
    operation = spec["paths"][path][method.lower()]
    schema = operation["requestBody"]["content"]["application/json"]["schema"]
    model = REQUEST_BODY_MODELS[(method, path)]
    extras = REQUEST_BODY_EXTRA_PROPERTIES.get((method, path), {})
    # A route whose handler reads body keys outside its model publishes a
    # ``<Model>Body`` variant carrying them; the model's own component is left
    # untouched. Publishing the bare model shipped a schema that produced a 403.
    component = _body_component_name(model, extras)
    # A bare ``$ref`` with no siblings: a ``$ref`` beside other keys is ignored
    # by OpenAPI 3.0 tooling, which is what merging via ``openapi_extra``
    # produced - a document that looked typed and was not.
    assert schema == {"$ref": f"#/components/schemas/{component}"}, schema
    assert component in spec["components"]["schemas"]
    assert model.__name__ in spec["components"]["schemas"], (
        "the model's own component must survive for anything already referencing it"
    )


def test_no_published_reference_dangles() -> None:
    """Nested models must be lifted out of ``$defs`` into components.

    ``model_json_schema`` points at nested models with ``#/$defs/Name``; the
    document keeps them under ``#/components/schemas``. A dangling ``$ref`` is
    worse for a client generator than no schema at all.
    """
    import json
    import re

    spec = client.get("/openapi.json").json()
    declared = set(spec.get("components", {}).get("schemas", {}))
    referenced = set(
        re.findall(r'"\$ref": "#/components/schemas/([^"]+)"', json.dumps(spec))
    )
    assert not referenced - declared, sorted(referenced - declared)
    # The nested contracts really are reached, so the lifting is exercised.
    assert {"ColumnMetadata", "BusinessMapping", "DatasetDistribution"} <= declared


def test_publishing_the_schema_did_not_move_validation_to_pydantic() -> None:
    """The 400 shape is the contract clients already have.

    Typing the route parameter would have handed validation to FastAPI and
    turned this into a 422. The document now names the model while the handler
    keeps converting the ``ValidationError`` itself.
    """
    refused = client.post("/catalog/datasets", json={"actor": "admin"})
    assert refused.status_code == 400, refused.text
    detail = refused.json()["detail"]
    assert detail["error"] == "invalid_request"
    assert any(field["field"] == "title" for field in detail["fields"]), detail


def test_the_runtime_body_parameter_is_still_a_mapping() -> None:
    """Pins the thing that makes the 400 above possible."""
    route = next(
        candidate
        for candidate in app.routes
        if isinstance(candidate, APIRoute)
        and candidate.path == "/catalog/datasets"
        and "POST" in candidate.methods
    )
    annotation = route.dependant.body_params[0].field_info.annotation
    assert "dict" in str(annotation), annotation


def test_the_untyped_bodies_that_remain_are_the_ones_with_no_model() -> None:
    """The scope boundary, measured rather than asserted in prose.

    Ten routes still publish ``additionalProperties: true``. Every one of them
    reads loose keys from the dict and constructs no contract model, so there is
    nothing to publish that could not drift from what the handler reads.
    """
    spec = client.get("/openapi.json").json()
    untyped = []
    for path, methods in spec["paths"].items():
        for method, operation in methods.items():
            body = operation.get("requestBody")
            if not body:
                continue
            schema = body["content"]["application/json"]["schema"]
            if "$ref" not in schema:
                untyped.append((method.upper(), path))

    for key in untyped:
        assert key not in REQUEST_BODY_MODELS, f"{key} has a model but publishes none"
        assert not CONSTRUCTED.get(key), (
            f"{key} constructs {sorted(CONSTRUCTED[key])} but publishes no schema"
        )


def test_the_custom_generator_does_not_drop_app_level_openapi_settings() -> None:
    """It must delegate to FastAPI's generator, not re-implement the call.

    ``FastAPI.openapi()`` forwards fourteen arguments to ``get_openapi``,
    including ``summary``, ``terms_of_service``, ``contact``, ``license_info``,
    ``servers``, ``webhooks``, ``tags`` and
    ``separate_input_output_schemas``. The first version of
    ``document_request_bodies`` re-implemented that call with five of them.
    Every omitted setting is empty on this app today, and
    ``separate_input_output_schemas`` happens to share its default, so the
    document was byte-identical and nothing failed - the defect was latent. A
    deployment that set ``servers`` or ``contact`` for a buyer would have found
    them silently missing from the published document.
    """
    original_servers = app.servers
    original_contact = app.contact
    original_schema = app.openapi_schema
    try:
        app.servers = [{"url": "https://portal.example", "description": "pilot"}]
        app.contact = {"name": "data governance", "email": "governance@example"}
        app.openapi_schema = None
        spec = app.openapi()
        assert spec["servers"] == app.servers, spec.get("servers")
        assert spec["info"]["contact"] == app.contact, spec["info"].get("contact")
        # and the request-body contract is still applied on top
        schema = spec["paths"]["/catalog/datasets"]["post"]["requestBody"]["content"][
            "application/json"
        ]["schema"]
        assert schema == {"$ref": "#/components/schemas/DatasetCreateRequestBody"}
    finally:
        app.servers = original_servers
        app.contact = original_contact
        app.openapi_schema = original_schema


# --------------------------------------------------------------------------- #
# The check that would have caught the first version of this module.
#
# Publishing the model alone made the document typed and WRONG: a client built
# from the published ``DatasetCreateRequest`` schema sends exactly its nineteen
# fields, and ``actor`` is not one of them. Measured:
#
#     POST /catalog/datasets  <only the published fields>   -> 403
#                             "create 작업은 admin 권한만 가능"
#     POST /catalog/datasets  <same body + "actor": "admin"> -> 200
#
# A schema that cannot be used to make the call it describes is the
# "more useful-looking lie" this module's own docstring warns about. Asserting
# that a schema is present was not enough; what matters is whether it is
# sufficient.
# --------------------------------------------------------------------------- #

# Helper name -> (index of the argument naming the body key, published type).
BODY_KEY_HELPERS = {"_payload_str": (1, "string"), "_pagination_int": (1, "integer")}


def _body_keys_read(handler: str) -> tuple[set[str], set[str]]:
    """Body keys a handler reads, and the reads this scan cannot resolve.

    Fail-closed: a read whose key is not a literal, or a call that hands the
    body to something this scan cannot follow, lands in the second set. A route
    with unresolved reads is not allowed to publish a schema, because an
    incomplete schema is what broke the create call.
    """
    tree = ast.parse(API_SOURCE.read_text())
    functions = {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }

    def body_param(node: ast.AST) -> str | None:
        for argument in node.args.args:
            if argument.annotation is not None and "dict" in ast.unparse(argument.annotation):
                return argument.arg
        return None

    def scan(node: ast.AST, param: str, seen: set[str]) -> tuple[set[str], set[str]]:
        found: set[str] = set()
        unresolved: set[str] = set()
        for sub in ast.walk(node):
            if isinstance(sub, ast.Subscript) and getattr(sub.value, "id", None) == param:
                if isinstance(sub.slice, ast.Constant):
                    found.add(sub.slice.value)
                else:
                    unresolved.add(ast.unparse(sub))
            if isinstance(sub, ast.Compare):
                for comparator in sub.comparators:
                    if getattr(comparator, "id", None) == param and isinstance(
                        sub.left, ast.Constant
                    ):
                        found.add(sub.left.value)
            if not isinstance(sub, ast.Call):
                continue
            if (
                getattr(sub.func, "attr", None) == "get"
                and getattr(sub.func.value, "id", None) == param
            ):
                if sub.args and isinstance(sub.args[0], ast.Constant):
                    found.add(sub.args[0].value)
                else:
                    unresolved.add(ast.unparse(sub))
                continue
            name = getattr(sub.func, "id", None)
            if not name or not any(getattr(a, "id", None) == param for a in sub.args):
                continue
            if name in BODY_KEY_HELPERS:
                index, _kind = BODY_KEY_HELPERS[name]
                if len(sub.args) > index and isinstance(sub.args[index], ast.Constant):
                    found.add(sub.args[index].value)
                else:
                    unresolved.add(ast.unparse(sub))
            elif name in functions:
                if name not in seen:
                    seen.add(name)
                    nested_found, nested_unresolved = scan(
                        functions[name], body_param(functions[name]) or param, seen
                    )
                    found |= nested_found
                    unresolved |= nested_unresolved
            else:
                unresolved.add(f"{name}(<body>)")
        return found, unresolved

    node = functions[handler]
    param = body_param(node)
    if param is None:
        return set(), set()
    found, unresolved = scan(node, param, set())
    # ``_payload_str``'s own ``payload.get(field, default)`` is dynamic by
    # design; each call site supplies the literal, which is captured above.
    unresolved = {item for item in unresolved if item != "payload.get(field, default)"}
    return {key for key in found if isinstance(key, str)}, unresolved


def _handler_name(method: str, path: str) -> str:
    tree = ast.parse(API_SOURCE.read_text())
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for deco in node.decorator_list:
            if (
                isinstance(deco, ast.Call)
                and isinstance(deco.func, ast.Attribute)
                and deco.func.attr == method.lower()
                and getattr(deco.func.value, "id", "") == "app"
                and deco.args
                and deco.args[0].value == path
            ):
                return node.name
    raise AssertionError(f"no handler for {method} {path}")


@pytest.mark.parametrize(
    "method,path", sorted(REQUEST_BODY_MODELS), ids=lambda value: str(value)
)
def test_the_published_schema_covers_every_body_key_the_handler_reads(
    method: str, path: str
) -> None:
    """A key read outside the model must still be published."""
    from sdp.api_request_contract import REQUEST_BODY_EXTRA_PROPERTIES

    read, unresolved = _body_keys_read(_handler_name(method, path))
    assert not unresolved, (
        f"{method} {path} has body reads this scan cannot resolve, so its "
        f"published schema may be incomplete: {sorted(unresolved)}"
    )

    model = REQUEST_BODY_MODELS[(method, path)]
    published = set(model.model_fields) | set(
        REQUEST_BODY_EXTRA_PROPERTIES.get((method, path), {})
    )
    missing = read - published
    assert not missing, (
        f"{method} {path} reads {sorted(missing)} from the body and publishes "
        "neither in its model nor in REQUEST_BODY_EXTRA_PROPERTIES, so a client "
        "generated from the document cannot make the call"
    )


def test_a_body_built_from_the_published_schema_is_accepted() -> None:
    """The round trip, on the call a buyer makes first.

    Not "is a schema published" but "is the published schema enough". The two
    measured outcomes below are the regression: before the repair the first one
    was a 403.
    """
    spec = client.get("/openapi.json").json()
    component = spec["paths"]["/catalog/datasets"]["post"]["requestBody"]["content"][
        "application/json"
    ]["schema"]["$ref"].rsplit("/", 1)[-1]
    published = spec["components"]["schemas"][component]

    assert "actor" in published["properties"], sorted(published["properties"])
    assert "actor" in published["required"], published["required"]

    body = {
        "id": "published-schema-roundtrip",
        "title": "제목",
        "description": "설명",
        "domain": "customer_intelligence",
        "owner": "owner",
        "steward": "steward",
        "tags": ["tag_one"],
        "terms": ["고객"],
        "sensitivity": "internal",
        "source_system": "source_system",
        "update_frequency": "daily",
        "quality_score": 0.9,
        "freshness_score": 0.9,
        "schema": [
            {
                "name": "column_one",
                "datatype": "string",
                "nullable_ratio": 0.0,
                "distinct_ratio": 1.0,
                "quality_issues": [],
                "pii": False,
            }
        ],
        "distributions": [],
        "mappings": [],
        "related_datasets": [],
        "profile": {},
        "actor": "admin",
    }
    # Every key sent is one the document publishes.
    assert set(body) <= set(published["properties"]), (
        sorted(set(body) - set(published["properties"]))
    )
    created = client.post("/catalog/datasets", json=body)
    assert created.status_code == 200, created.text

    # And the field whose omission caused the 403 really is the cause.
    without_actor = {key: value for key, value in body.items() if key != "actor"}
    without_actor["id"] = "published-schema-roundtrip-no-actor"
    refused = client.post("/catalog/datasets", json=without_actor)
    assert refused.status_code == 403, refused.text
