"""The published contract must name every refusal the code can actually return.

Measured against ``GET /openapi.json`` before ``sdp.api_error_contract`` existed:

    routes with a typed request body                5 of 20
    operations with a ``$ref`` 200 response schema  0 of 60
    operations documenting ANY error status         0 of 60

The product's distinguishing behaviour is its refusals - 403 for role,
sensitivity or purpose; 404 for out-of-scope *and* absent, deliberately
indistinguishable; 400 for a malformed request; 409 for a full bounded resource
- and a buyer generating a client saw none of them.

The guard here is not "the table is non-empty". It is that the table and the
code agree, in both directions, with the statuses the code can return derived by
walking the AST of ``sdp.api`` rather than listed by hand. A route that gains a
refusal without declaring it fails; a table entry naming a path the app does not
serve fails; a documented status the route cannot return fails, because
documenting an impossible refusal is a false claim rather than a cautious one.
"""

from __future__ import annotations

import ast
import pathlib

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from sdp.api import app
from sdp.api_error_contract import (
    DYNAMIC_REFUSALS,
    ERROR_RESPONSE_SCHEMA,
    REFUSAL_DESCRIPTIONS,
    ROUTE_REFUSALS,
)


client = TestClient(app)
ROUTE_DECORATOR_METHODS = {"get", "post", "patch", "put", "delete"}
API_SOURCE = pathlib.Path(__file__).resolve().parents[1] / "src" / "sdp" / "api.py"


def _literal_statuses(node: ast.AST) -> set[int]:
    """Every ``HTTPException`` status-code literal in this function body."""
    found: set[int] = set()
    for sub in ast.walk(node):
        if not isinstance(sub, ast.Call):
            continue
        label = getattr(sub.func, "id", None) or getattr(sub.func, "attr", None)
        if label != "HTTPException":
            continue
        for keyword in sub.keywords:
            if keyword.arg == "status_code" and isinstance(keyword.value, ast.Constant):
                found.add(keyword.value.value)
        for arg in sub.args:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, int):
                found.add(arg.value)
    return found


def _raiseable_statuses() -> dict[tuple[str, str], set[int]]:
    """Per route, every status its body or anything it calls can raise.

    Transitive through module-level functions, which is what makes the shared
    gates (``_require_scoped_dataset``, ``_authorize_graph_write``, ...) and
    route-to-route delegation (``/api/v1/browse/query`` -> ``browse_query``)
    count toward the route that uses them.
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

    def called(node: ast.AST) -> set[str]:
        names = {
            getattr(sub.func, "id", None)
            for sub in ast.walk(node)
            if isinstance(sub, ast.Call)
        }
        return {name for name in names if name in functions}

    def transitive(name: str, seen: set[str] | None = None) -> set[int]:
        seen = seen or set()
        if name in seen:
            return set()
        seen.add(name)
        statuses = _literal_statuses(functions[name])
        for callee in called(functions[name]):
            statuses |= transitive(callee, seen)
        return statuses

    derived: dict[tuple[str, str], set[int]] = {}
    for name, decorated in routes:
        statuses = transitive(name)
        for method, path in decorated:
            derived[(method, path)] = statuses | set(
                DYNAMIC_REFUSALS.get((method, path), ())
            )
    return derived


RAISEABLE = _raiseable_statuses()


def test_every_refusal_the_code_can_raise_is_published() -> None:
    """The direction that matters for a buyer: nothing undocumented."""
    undocumented = {}
    for key, statuses in sorted(RAISEABLE.items()):
        if not statuses:
            continue
        declared = set(ROUTE_REFUSALS.get(key, ()))
        missing = statuses - declared
        if missing:
            undocumented[key] = sorted(missing)
    assert not undocumented, (
        "these routes can refuse with statuses the OpenAPI document does not "
        f"mention: {undocumented}"
    )


def test_no_published_refusal_is_one_the_route_cannot_return() -> None:
    """The other direction: no false claim in the contract."""
    impossible = {}
    for key, declared in sorted(ROUTE_REFUSALS.items()):
        statuses = RAISEABLE.get(key)
        if statuses is None:
            continue
        extra = set(declared) - statuses
        if extra:
            impossible[key] = sorted(extra)
    assert not impossible, (
        f"these documented refusals cannot actually occur: {impossible}"
    )


def test_the_table_names_no_route_the_app_does_not_serve() -> None:
    served = {
        (method, route.path)
        for route in app.routes
        if isinstance(route, APIRoute)
        for method in route.methods
    }
    stale = sorted(key for key in ROUTE_REFUSALS if key not in served)
    assert not stale, f"table entries documenting nothing: {stale}"


def test_each_declared_status_has_a_description() -> None:
    used = {status for statuses in ROUTE_REFUSALS.values() for status in statuses}
    assert used <= set(REFUSAL_DESCRIPTIONS), sorted(used - set(REFUSAL_DESCRIPTIONS))


@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/catalog/datasets/{dataset_id}"),
        ("post", "/browse/query"),
        ("post", "/ontology/concepts"),
        ("post", "/llm/draft-query"),
    ],
)
def test_the_openapi_document_actually_carries_the_refusals(method: str, path: str) -> None:
    """Attaching the contract after registration must reach the document."""
    spec = client.get("/openapi.json").json()
    operation = spec["paths"][path][method]
    declared = ROUTE_REFUSALS[(method.upper(), path)]
    for status in declared:
        assert str(status) in operation["responses"], (
            f"{method.upper()} {path} does not publish {status}: "
            f"{sorted(operation['responses'])}"
        )
        documented = operation["responses"][str(status)]
        assert documented["description"] == REFUSAL_DESCRIPTIONS[status]
        schema = documented["content"]["application/json"]["schema"]
        assert schema == ERROR_RESPONSE_SCHEMA


def test_the_refusal_schema_admits_both_detail_shapes() -> None:
    """``detail`` is a string on most paths and structured on a few.

    Declaring only the common shape would make the spec wrong for the routes
    that return the requested value and the known set (the unknown-status-filter
    refusal), which is how a generated client ends up unable to parse a real
    response.
    """
    types = {
        option["type"] for option in ERROR_RESPONSE_SCHEMA["properties"]["detail"]["anyOf"]
    }
    assert {"string", "object"} <= types, types

    string_detail = client.get(
        "/catalog/datasets/__absent__", params={"user": "analyst"}
    )
    assert string_detail.status_code == 404
    assert isinstance(string_detail.json()["detail"], str)

    structured_detail = client.get("/ontology/patches", params={"status": "nope"})
    assert structured_detail.status_code == 400
    assert isinstance(structured_detail.json()["detail"], dict)
