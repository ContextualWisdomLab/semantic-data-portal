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

# Body keys a handler reads **outside** its model. Publishing the model alone
# made the document typed and wrong: a client built from the published
# ``DatasetCreateRequest`` schema sends exactly its nineteen fields, and
# ``actor`` is not one of them. Measured:
#
#     POST /catalog/datasets  <only the published fields>  -> 403
#                             "create 작업은 admin 권한만 가능"
#     POST /catalog/datasets  <same body + "actor": "admin"> -> 200
#
# So the first version of this module shipped a schema that cannot be used to
# make the call it describes - the "more useful-looking lie" its own docstring
# warns about. ``actor`` is marked required because the call is refused without
# it, even though the model's validation does not require it: a generator that
# treats it as optional produces a client that always gets 403.
#
# ``tests/test_api_request_contract.py`` derives these keys from the AST of
# ``sdp.api`` and fails if a handler reads a body key this table does not
# publish, so the next one cannot be forgotten.
REQUEST_BODY_EXTRA_PROPERTIES: dict[tuple[str, str], dict[str, Any]] = {
    ("POST", "/catalog/datasets"): {
        "actor": {
            "type": "string",
            "description": (
                "인가 주체. 모델 밖에서 읽히며, 없으면 anonymous로 취급되어 "
                "403으로 거부됩니다 — 생성 호출에는 사실상 필수입니다."
            ),
        }
    },
    ("PATCH", "/catalog/datasets/{dataset_id}"): {
        "actor": {
            "type": "string",
            "description": (
                "인가 주체. 모델 밖에서 읽히며, 없으면 anonymous로 취급되어 "
                "403으로 거부됩니다 — 변경 호출에는 사실상 필수입니다."
            ),
        }
    },
}

_REF_TEMPLATE = "#/components/schemas/{model}"
_BODY_COMPONENT_SUFFIX = "Body"


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


def _body_component_name(model: type[BaseModel], extras: dict[str, Any]) -> str:
    """The component a route publishes: the model, or a model+extras variant."""
    if not extras:
        return model.__name__
    return f"{model.__name__}{_BODY_COMPONENT_SUFFIX}"


def _composed_body_schema(
    model: type[BaseModel], extras: dict[str, Any], components: dict[str, Any]
) -> dict[str, Any]:
    """The model's schema with the handler's extra body keys merged in.

    A separate component rather than ``allOf``: a client generator handles one
    flat object schema reliably, and ``allOf`` with a sibling property object is
    where generators differ most. The model's own component is left untouched so
    anything already referencing it is unaffected.
    """
    base = dict(components[model.__name__])
    properties = dict(base.get("properties", {}))
    properties.update(extras)
    base["properties"] = properties
    base["required"] = sorted({*base.get("required", []), *extras})
    base["title"] = _body_component_name(model, extras)
    return base


def _published_body(component: str) -> dict[str, Any]:
    """The ``requestBody`` object naming a component schema."""
    return {
        "required": True,
        "content": {
            "application/json": {"schema": {"$ref": f"#/components/schemas/{component}"}}
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

    # FastAPI's own generator, captured before it is replaced. Calling it is not
    # the same as calling ``get_openapi`` with a few hand-picked arguments: the
    # real method forwards fourteen, including ``summary``,
    # ``terms_of_service``, ``contact``, ``license_info``, ``servers``,
    # ``webhooks``, ``tags`` and ``separate_input_output_schemas``. The first
    # version of this function re-implemented the call with five of them. Every
    # omitted setting is empty on this app today and
    # ``separate_input_output_schemas`` happens to share its default, so the
    # document was identical - but the moment a deployment sets ``servers`` or
    # ``contact`` for a buyer, they would have vanished from the document with
    # nothing failing. Delegating keeps this function responsible for one thing.
    generate = app.openapi

    def openapi() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema
        # ``generate()`` fills ``app.openapi_schema`` and returns that same dict,
        # so the mutations below land on the cached document in place.
        schema = generate()
        components = schema.setdefault("components", {}).setdefault("schemas", {})
        for route in app.routes:
            if not isinstance(route, APIRoute):
                continue
            for method in route.methods:
                model = REQUEST_BODY_MODELS.get((method, route.path))
                if model is None:
                    continue
                components.update(_model_component_schemas(model))
                extras = REQUEST_BODY_EXTRA_PROPERTIES.get((method, route.path), {})
                component = _body_component_name(model, extras)
                if extras:
                    components[component] = _composed_body_schema(
                        model, extras, components
                    )
                operation = schema["paths"][route.path][method.lower()]
                operation["requestBody"] = _published_body(component)
        app.openapi_schema = schema
        return schema

    app.openapi = openapi  # type: ignore[method-assign]
    return openapi
