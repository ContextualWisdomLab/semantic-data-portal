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
#
# That claim was wider than the check for a while: the derivation is
# parametrized over ``REQUEST_BODY_MODELS``, so the **ten routes with no model**
# were never in it. They published ``additionalProperties: true`` and not one
# field name, while their handlers read named keys - five of them the
# authorization subject, so a body built from the document was refused before it
# reached the handler. ``tests/test_untyped_request_bodies_are_documented.py`` is
# the other half, over the untyped routes derived from the live document, and
# the entries below now cover both kinds.
#
# The subject's key name is not uniform and that is precisely what a document is
# for: every GET takes ``?user=``, five of these routes take body ``actor`` and
# three take body ``user``. No client can derive that from the path.
REQUEST_BODY_EXTRA_PROPERTIES: dict[tuple[str, str], dict[str, Any]] = {
    ("POST", "/catalog/datasets"): {
        "reason": {
            "type": "string",
            "maxLength": 512,
            "description": (
                "이 변경의 사유. 모델 밖에서 읽혀 감사 행의 "
                "`details.change_reason`으로 기록됩니다(CAT-005의 수락 기준). "
                "모델 필드가 아닌 이유는 변경에 **대한** 메타데이터이고 데이터셋 "
                "상태가 아니기 때문입니다 — 요청 모델의 필드는 `Dataset` 필드의 "
                "부분집합이어야 합니다. 생략하거나 공백만 보내면 `None`으로 "
                "기록됩니다(둘은 같은 사실입니다)."
            ),
        },
        "actor": {
            "type": "string",
            "description": (
                "인가 주체. 모델 밖에서 읽히며, 없으면 anonymous로 취급되어 "
                "403으로 거부됩니다 — 생성 호출에는 사실상 필수입니다."
            ),
        }
    },
    ("PATCH", "/catalog/datasets/{dataset_id}"): {
        "reason": {
            "type": "string",
            "maxLength": 512,
            "description": (
                "이 변경의 사유. 모델 밖에서 읽혀 감사 행의 "
                "`details.change_reason`으로 기록됩니다(CAT-005의 수락 기준). "
                "모델 필드가 아닌 이유는 변경에 **대한** 메타데이터이고 데이터셋 "
                "상태가 아니기 때문입니다 — 요청 모델의 필드는 `Dataset` 필드의 "
                "부분집합이어야 합니다. 생략하거나 공백만 보내면 `None`으로 "
                "기록됩니다(둘은 같은 사실입니다)."
            ),
        },
        "actor": {
            "type": "string",
            "description": (
                "인가 주체. 모델 밖에서 읽히며, 없으면 anonymous로 취급되어 "
                "403으로 거부됩니다 — 변경 호출에는 사실상 필수입니다."
            ),
        }
    },

    ("POST", "/catalog/datasets/{dataset_id}/publish"): {
        "actor": {
            "type": "string",
            "description": (
                "인가 주체. 없으면 anonymous로 취급되어 거부됩니다. GET 라우트는 같은 주체를 쿼리 "
                "`?user=`로 받지만 이 라우트는 **본문의 `actor`**로 받습니다 — 이름이 라우트마다 다르므로 "
                "문서가 말해야 합니다."
            ),
        },
        "reason": {
            "type": "string",
            "description": (
                "이 변경의 사유. 감사 행의 `details.change_reason`으로 기록됩니다. 생략하거나 공백만 "
                "보내면 `None`으로 기록됩니다."
            ),
            "maxLength": 512,
        },
    },
    ("POST", "/catalog/datasets/{dataset_id}/deprecate"): {
        "actor": {
            "type": "string",
            "description": (
                "인가 주체. 없으면 anonymous로 취급되어 거부됩니다. GET 라우트는 같은 주체를 쿼리 "
                "`?user=`로 받지만 이 라우트는 **본문의 `actor`**로 받습니다 — 이름이 라우트마다 다르므로 "
                "문서가 말해야 합니다."
            ),
        },
        "reason": {
            "type": "string",
            "description": (
                "이 변경의 사유. 감사 행의 `details.change_reason`으로 기록됩니다. 생략하거나 공백만 "
                "보내면 `None`으로 기록됩니다."
            ),
            "maxLength": 512,
        },
    },
    ("POST", "/enterprise/auth/oidc-preview"): {
        "actor": {
            "type": "string",
            "description": (
                "인가 주체. 없으면 anonymous로 취급되어 거부됩니다. GET 라우트는 같은 주체를 쿼리 "
                "`?user=`로 받지만 이 라우트는 **본문의 `actor`**로 받습니다 — 이름이 라우트마다 다르므로 "
                "문서가 말해야 합니다."
            ),
        },
        "claims": {
            "type": "object",
            "additionalProperties": True,
            "description": (
                "미리보기할 OIDC 클레임 집합. 서명 검증은 하지 않으며 역할·테넌트 매핑 결과만 돌려주는 읽기 전용 "
                "미리보기입니다 — 검증은 `/enterprise/auth/oidc-verify`입니다."
            ),
        },
        "role_map": {
            "type": "object",
            "additionalProperties": True,
            "description": (
                "이 미리보기에만 적용할 group→role 매핑. 생략하면 운영자가 설정한 "
                "매핑(`SDP_OIDC_GROUP_ROLE_MAP`)이 쓰이고, 저장되지 않습니다."
            ),
        },
    },
    ("POST", "/ontology/patches"): {
        "actor": {
            "type": "string",
            "description": (
                "인가 주체. 없으면 anonymous로 취급되어 거부됩니다. GET 라우트는 같은 주체를 쿼리 "
                "`?user=`로 받지만 이 라우트는 **본문의 `actor`**로 받습니다 — 이름이 라우트마다 다르므로 "
                "문서가 말해야 합니다."
            ),
        },
        "concept": {
            "type": "string",
            "description": (
                "패치가 다루는 용어(canonical concept 또는 alias). `suggestion`과 함께 "
                "필수이며, 둘 중 하나가 없으면 400입니다."
            ),
        },
        "suggestion": {
            "type": "string",
            "description": (
                "제안 내용. `concept`과 함께 필수이며, 둘 중 하나가 없으면 400입니다."
            ),
        },
    },
    ("POST", "/ontology/patches/{patch_id}/review"): {
        "actor": {
            "type": "string",
            "description": (
                "인가 주체. 없으면 anonymous로 취급되어 거부됩니다. GET 라우트는 같은 주체를 쿼리 "
                "`?user=`로 받지만 이 라우트는 **본문의 `actor`**로 받습니다 — 이름이 라우트마다 다르므로 "
                "문서가 말해야 합니다."
            ),
        },
        "decision": {
            "type": "string",
            "description": (
                "심사 결과. 허용 값은 `approve`와 `reject`이고, 다른 값은 400입니다."
            ),
        },
        "comment": {
            "type": "string",
            "description": (
                "심사 코멘트. 감사 행에 함께 기록됩니다."
            ),
            "maxLength": 512,
        },
        "reviewer": {
            "type": "string",
            "description": (
                "**보내지 마십시오.** 심사자는 인가된 주체(`actor`)에서 파생되므로, 이 필드가 있으면 400으로 "
                "거부됩니다 — 패치를 보지 않은 steward의 이름이 기록되는 것을 막기 위해 조용히 무시하지 않고 "
                "거부합니다."
            ),
        },
    },
    ("POST", "/browse/{dataset_id}/preview"): {
        "user": {
            "type": "string",
            "description": (
                "인가 주체. 이 라우트는 **본문의 `user`**로 받습니다(형제 라우트 다섯은 본문 `actor`, "
                "GET 라우트는 쿼리 `?user=`) — 이름이 라우트마다 다르므로 문서가 말해야 합니다."
            ),
        },
        "purpose": {
            "type": "string",
            "description": (
                "거버넌스 목적. 정책 평가의 입력이며 목적에 따라 masking·집계 제한이 달라집니다. 생략하면 라우트의 "
                "기본 목적으로 평가됩니다."
            ),
        },
        "limit": {
            "type": "integer",
            "description": (
                "돌려줄 행 수의 상한. 정책이 더 낮은 상한을 요구하면 그쪽이 적용됩니다."
            ),
        },
        "offset": {
            "type": "integer",
            "description": (
                "건너뛸 행 수. 페이지네이션용이며 기본값은 0입니다."
            ),
        },
    },
    ("POST", "/enterprise/auth/oidc-verify"): {
        "token": {
            "type": "string",
            "description": (
                "검증할 OIDC JWT. 설정된 issuer·audience·JWKS로 서명과 클레임을 검증합니다 — 서명을 "
                "보지 않는 미리보기는 `/enterprise/auth/oidc-preview`입니다."
            ),
        },
    },
    ("POST", "/llm/search"): {
        "user": {
            "type": "string",
            "description": (
                "인가 주체. 이 라우트는 **본문의 `user`**로 받습니다(형제 라우트 다섯은 본문 `actor`, "
                "GET 라우트는 쿼리 `?user=`) — 이름이 라우트마다 다르므로 문서가 말해야 합니다."
            ),
        },
        "purpose": {
            "type": "string",
            "description": (
                "거버넌스 목적. 정책 평가의 입력이며 목적에 따라 masking·집계 제한이 달라집니다. 생략하면 라우트의 "
                "기본 목적으로 평가됩니다."
            ),
        },
        "question": {
            "type": "string",
            "description": (
                "자연어 질의. 용어 해석을 거쳐 카탈로그 검색으로 이어집니다."
            ),
        },
    },
    ("POST", "/ontology/resolve"): {
        "text": {
            "type": "string",
            "description": (
                "해석할 자연어 텍스트. 용어가 canonical concept으로 매핑됩니다."
            ),
        },
        "ontology_content_digest": {
            "type": "string",
            "description": (
                "읽을 어휘 버전을 고정하는 content digest(64자 16진수). 생략하면 현재 버전으로 해석합니다. "
                "키 이름은 `sdp.ontology_version.PIN_PARAMETER`가 정의하며, 이 표의 값과 "
                "같아야 한다는 것을 테스트가 단언합니다."
            ),
        },
    },
    ("POST", "/policy/decision"): {
        "user": {
            "type": "string",
            "description": (
                "인가 주체. 이 라우트는 **본문의 `user`**로 받습니다(형제 라우트 다섯은 본문 `actor`, "
                "GET 라우트는 쿼리 `?user=`) — 이름이 라우트마다 다르므로 문서가 말해야 합니다."
            ),
        },
        "subject": {
            "type": "string",
            "description": (
                "평가할 주체. 생략하면 `user`가 쓰입니다. 다른 주체를 넣어 평가해 볼 수 있지만, 그 결과는 호출자의 "
                "권한을 바꾸지 않습니다."
            ),
        },
        "resource": {
            "type": "string",
            "description": (
                "평가할 자원(dataset id 또는 `catalog` 같은 논리 자원)."
            ),
        },
        "action": {
            "type": "string",
            "description": (
                "평가할 동작(`search`·`read`·`create`·`publish` 등)."
            ),
        },
        "purpose": {
            "type": "string",
            "description": (
                "거버넌스 목적. 정책 평가의 입력이며 목적에 따라 masking·집계 제한이 달라집니다. 생략하면 라우트의 "
                "기본 목적으로 평가됩니다."
            ),
        },
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


def _documented_untyped_schema(
    schema: dict[str, Any], extras: dict[str, Any]
) -> dict[str, Any]:
    """Merge the handler's body keys into an untyped route's inline schema.

    Ten routes have no contract model, so there is nothing to ``$ref`` and the
    document published ``{"type": "object", "additionalProperties": true}`` -
    valid for any body and sufficient for none. Five of them read the
    authorization subject out of that dict, so a body built from the document
    was refused before it reached the handler.

    The schema stays **open**: a route with no model validates nothing, so
    closing it in the document would describe a strictness the handler does not
    enforce - the same lie in the other direction. Openness is also not always
    the literal ``true`` here; a ``dict[str, str]`` parameter publishes
    ``additionalProperties: {"type": "string"}``, and that value type is left
    exactly as FastAPI generated it.

    ``anyOf`` is handled rather than flattened: a body typed ``dict | None`` is
    published as an object-or-null union, and the keys belong on the object
    member. Replacing the union with a bare object would document the optional
    body as required.
    """
    members = schema.get("anyOf")
    if members is None:
        return _documented_object_member(schema, extras)
    return {
        **schema,
        "anyOf": [
            _documented_object_member(member, extras)
            if member.get("type") == "object"
            else member
            for member in members
        ],
    }


def _documented_object_member(
    member: dict[str, Any], extras: dict[str, Any]
) -> dict[str, Any]:
    """One object schema with the extra properties merged into it."""
    properties = {**member.get("properties", {}), **extras}
    return {**member, "properties": properties}


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
                extras = REQUEST_BODY_EXTRA_PROPERTIES.get((method, route.path), {})
                model = REQUEST_BODY_MODELS.get((method, route.path))
                if model is None:
                    # No contract model: document the keys on the route's own
                    # inline schema instead of skipping the route entirely,
                    # which is what left ten routes publishing field names for
                    # none of the keys their handlers read.
                    operation = schema["paths"].get(route.path, {}).get(method.lower())
                    if not extras or operation is None:
                        continue
                    body = operation.get("requestBody")
                    if body is None:
                        continue
                    content = body["content"]["application/json"]
                    content["schema"] = _documented_untyped_schema(
                        content["schema"], extras
                    )
                    continue
                components.update(_model_component_schemas(model))
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
