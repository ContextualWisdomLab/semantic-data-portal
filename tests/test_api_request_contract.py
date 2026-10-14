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
    spec = client.get("/openapi.json").json()
    operation = spec["paths"][path][method.lower()]
    schema = operation["requestBody"]["content"]["application/json"]["schema"]
    model = REQUEST_BODY_MODELS[(method, path)]
    # A bare ``$ref`` with no siblings: a ``$ref`` beside other keys is ignored
    # by OpenAPI 3.0 tooling, which is what merging via ``openapi_extra``
    # produced - a document that looked typed and was not.
    assert schema == {"$ref": f"#/components/schemas/{model.__name__}"}, schema
    assert model.__name__ in spec["components"]["schemas"]


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
