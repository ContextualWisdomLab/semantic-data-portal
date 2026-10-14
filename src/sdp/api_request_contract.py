"""Publish the request-body contracts these routes already validate against.

Fifteen of the twenty routes with a request body take ``payload: dict[str, Any]``,
so ``GET /openapi.json`` described them as ``{"type": "object",
"additionalProperties": true}`` - a generated client got ``object`` and not one
field name. Among them are the two calls a buyer uses first: ``POST
/catalog/datasets`` (onboarding a dataset) and ``POST /browse/query`` (the
governed query).

For four of those routes the contract **already exists as a pydantic model**;
the route takes a dict only so it can turn a ``ValidationError`` into this
repository's ``400 {"error": "invalid_request", "fields": [...]}`` shape instead
of FastAPI's native 422. Measured at the route:

    POST /catalog/datasets {"actor": "admin"}
      -> 400 {"detail": {"error": "invalid_request",
                         "fields": [{"field": "title", "reason": "Field required"}, ...]}}

So the model is the contract and the document simply did not say so. Publishing
it here is not a workaround for an untyped route - it is the document telling the
truth about a contract that is already enforced. Nothing about the runtime
changes: the parameter stays ``dict[str, Any]``, the 400 shape stays, and
``tests/test_api_request_contract.py`` verifies by AST that the model named for
each route is the model that route actually constructs, so the document cannot
claim a schema the handler does not use.

Deliberately out of scope, and measured rather than assumed: the other ten
raw-dict routes read loose keys (``payload.get("concept")`` and friends) and have
no model. Authoring a schema for them would be a claim that can drift from the
reads, and giving them real models would move validation to pydantic and change
the published 400 into a 422 - a contract change for existing clients, not a
documentation fix.
"""

from __future__ import annotations

from typing import Any, Callable

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from fastapi.routing import APIRoute
from pydantic import BaseModel

from sdp_core import (
    DatasetCreateRequest,
    DatasetPatchRequest,
    QueryDraftRequest,
    QueryExecutionRequest,
)

# (method, path) -> the model the handler constructs from the body.
REQUEST_BODY_MODELS: dict[tuple[str, str], type[BaseModel]] = {
    ("POST", "/catalog/datasets"): DatasetCreateRequest,
    ("PATCH", "/catalog/datasets/{dataset_id}"): DatasetPatchRequest,
    ("POST", "/llm/draft-query"): QueryDraftRequest,
    ("POST", "/browse/query"): QueryExecutionRequest,
    # The versioned alias delegates to ``browse_query`` with the same body.
    ("POST", "/api/v1/browse/query"): QueryExecutionRequest,
}

_REF_TEMPLATE = "#/components/schemas/{model}"


def _model_component_schemas(model: type[BaseModel]) -> dict[str, Any]:
    """Return this model's schema plus every nested model it references.

    ``model_json_schema`` puts nested models under ``$defs`` and points at them
    with ``#/$defs/Name``. The OpenAPI document keeps components under
    ``#/components/schemas``, so the definitions are lifted out and the
    references rewritten - otherwise the published ``$ref`` dangles, which is
    worse for a client generator than no schema at all.
    """
    schema = model.model_json_schema(ref_template=_REF_TEMPLATE)
    definitions = schema.pop("$defs", {})
    components = {model.__name__: schema}
    for name, definition in definitions.items():
        definition.pop("$defs", None)
        components[name] = definition
    return components


def _published_body(model: type[BaseModel]) -> dict[str, Any]:
    """The ``requestBody`` object naming this model's component schema."""
    return {
        "required": True,
        "content": {
            "application/json": {"schema": {"$ref": _REF_TEMPLATE.format(model=model.__name__)}}
        },
    }


def document_request_bodies(app: FastAPI) -> Callable[[], dict[str, Any]]:
    """Install an ``openapi()`` that publishes the known request-body contracts.

    A custom generator rather than per-route ``openapi_extra``: FastAPI merges
    ``openapi_extra`` into the generated operation, so the model ``$ref`` ended
    up beside the leftover ``additionalProperties: true`` and ``title:
    Payload`` from the dict parameter. A ``$ref`` with siblings is ignored by
    OpenAPI 3.0 tooling, so the merge produced a document that looked typed and
    was not. Replacing the body outright is unambiguous.
    """

    def openapi() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(
            title=app.title,
            version=app.version,
            openapi_version=app.openapi_version,
            description=app.description,
            routes=app.routes,
        )
        components = schema.setdefault("components", {}).setdefault("schemas", {})
        for route in app.routes:
            if not isinstance(route, APIRoute):
                continue
            for method in route.methods:
                model = REQUEST_BODY_MODELS.get((method, route.path))
                if model is None:
                    continue
                components.update(_model_component_schemas(model))
                operation = schema["paths"][route.path][method.lower()]
                operation["requestBody"] = _published_body(model)
        app.openapi_schema = schema
        return schema

    app.openapi = openapi  # type: ignore[method-assign]
    return openapi
