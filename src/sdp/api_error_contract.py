"""The refusals each route can return, published in the OpenAPI document.

The product's distinguishing behaviour is its *refusals*: a governed read is
refused 403 for a role, sensitivity or purpose, 404 when the dataset is outside
the caller's tenant scope or absent, 400 for a malformed request, 409 when a
bounded resource is full, when a request pins an ontology version other than the
one being served, or when a write would change an existing graph node's kind.
None of it reached the machine-readable contract.
Measured against ``GET /openapi.json`` before this module existed:

    routes with a typed request body               5 of 20
    operations with a ``$ref`` 200 response schema 0 of 60
    operations documenting ANY error status        0 of 60

So a buyer generating a client from the spec got no refusal in the type system
at all - every governed route looked like it either returns 200 or raises 422.
The error contract is stated in ``README.md`` and ``CLAUDE.md``
(``KeyError`` -> 404, ``ValueError`` -> 400, ``PermissionError`` -> 403) and
enforced by the suite; it just was not published.

The table below is the contract. It is applied to the routes after
registration rather than as a ``responses=`` argument on 42 decorators, so the
contract is readable in one place and cannot drift between routes that share a
family. ``tests/test_api_error_contract.py`` compares it against the statuses
the source can actually raise, derived by walking the AST of ``sdp.api``, so a
route that gains a refusal without declaring it fails the suite.

Only statuses a route can really return are listed. Documenting a refusal a
route cannot produce would be the same kind of false claim as the mislabelled
measurement provenance repaired elsewhere in this series - an answer that is
wrong rather than a question left open.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.routing import APIRoute

# ``HTTPException(detail=...)`` is a string on most paths here and a structured
# object on a few (for example the unknown-status-filter refusal, which returns
# the requested value and the known set). Both are declared rather than only the
# common one.
ERROR_RESPONSE_SCHEMA: dict[str, Any] = {
    "title": "RefusalDetail",
    "type": "object",
    "properties": {
        "detail": {
            "title": "Detail",
            "description": (
                "거부 사유. 대부분의 경로는 문자열이고, 일부 경로는 구조화된 "
                "객체를 반환한다 (예: 알 수 없는 status 필터는 requested와 "
                "known_statuses를 함께 반환)."
            ),
            "anyOf": [{"type": "string"}, {"type": "object"}, {"type": "array"}],
        }
    },
    "required": ["detail"],
}

REFUSAL_DESCRIPTIONS: dict[int, str] = {
    400: (
        "잘못된 요청. 요청 본문/파라미터가 계약을 위반했거나, 금지된 SQL 키워드 "
        "또는 허용되지 않은 식별자가 포함되어 정책 평가 전에 거부되었다."
    ),
    403: (
        "정책 거부. 역할(RBAC), 민감도, 목적(purpose) 중 하나가 허용되지 않았다. "
        "호출자가 데이터셋의 테넌트에는 접근할 수 있는 경우에만 403이며, 거부는 "
        "정책 결정과 감사 이벤트로 함께 기록된다."
    ),
    404: (
        "찾을 수 없음. 리소스가 존재하지 않거나 호출자의 테넌트 범위 밖이다. "
        "두 경우의 응답은 상태 코드와 본문이 동일하다 — 데이터셋 id는 열거 "
        "가능하므로 구별 가능한 응답 자체가 존재 oracle이 된다. 실제 사유는 "
        "호출자가 읽을 수 없는 증빙 원장에만 남는다."
    ),
    409: (
        "충돌. 다섯 가지 경우다 — (1) 요청이 고정한 "
        "온톨로지 content digest가 현재 어휘의 digest와 다르다, (2) 이미 다른 "
        "kind로 존재하는 node id에 쓰려 했다 — node의 kind는 바뀌지 않는다 "
        "(kind마다 담는 거버닝 속성이 다르고, 덮어쓰면 그 속성이 파괴된다. "
        "어휘 쪽 사전 검사도 같은 사유다), (3) 등록하려는 dataset id를 카탈로그가 "
        "이미 들고 있다, (4) broader/narrower의 끝점이 개념과 데이터 자산의 "
        "class 경계를 넘는다 (ONT-002), (5) broader/narrower가 포섭 순환을 "
        "닫거나 자기 자신을 포섭한다 (ONT-007). "
        "(1)에서 형식이 잘못된 digest는 409가 아니라 400이다 — 오타를 \"서버가 "
        "다른 어휘를 들고 있다\"로 보고하면 클라이언트가 잘못된 조치를 하게 된다."
    ),
}

# Statuses a literal-scanning reader cannot see, declared explicitly.
#
# ``POST /llm/draft-query`` resolves its status through
# ``_DRAFT_QUERY_ERROR_STATUS.get(error, 400)``, so 403 and 404 never appear as
# literals in the route body. The contract test knows to expect these from here
# rather than from the AST.
DYNAMIC_REFUSALS: dict[tuple[str, str], tuple[int, ...]] = {
    ("POST", "/llm/draft-query"): (403, 404),
}

ROUTE_REFUSALS: dict[tuple[str, str], tuple[int, ...]] = {
    ("POST", "/api/v1/browse/query"): (400, 403),
    ("GET", "/audit/events"): (403,),
    ("POST", "/browse/query"): (400, 403),
    ("POST", "/browse/{dataset_id}/preview"): (400, 403, 404),
    ("GET", "/browse/{dataset_id}/schema"): (403, 404),
    ("GET", "/catalog/datasets"): (403,),
    ("POST", "/catalog/datasets"): (400, 403, 409),
    ("GET", "/catalog/datasets/{dataset_id}"): (403, 404),
    ("PATCH", "/catalog/datasets/{dataset_id}"): (400, 403, 404, 409),
    ("GET", "/catalog/datasets/{dataset_id}/audit"): (403, 404),
    ("POST", "/catalog/datasets/{dataset_id}/deprecate"): (400, 403, 404, 409),
    ("GET", "/catalog/datasets/{dataset_id}/join-candidates"): (403, 404),
    ("GET", "/catalog/datasets/{dataset_id}/jsonld"): (403, 404),
    ("GET", "/catalog/datasets/{dataset_id}/lineage"): (403, 404),
    ("GET", "/catalog/datasets/{dataset_id}/profile"): (403, 404),
    ("POST", "/catalog/datasets/{dataset_id}/publish"): (400, 403, 404, 409),
    ("GET", "/catalog/datasets/{dataset_id}/related"): (403, 404),
    ("GET", "/catalog/datasets/{dataset_id}/schema-diff"): (400, 403, 404),
    ("GET", "/catalog/datasets/{dataset_id}/schema-history"): (403, 404),
    ("GET", "/catalog/datasets/{dataset_id}/schema-versions"): (403, 404),
    ("GET", "/catalog/datasets/{dataset_id}/semantic-validation"): (403, 404),
    ("GET", "/catalog/datasets/{dataset_id}/validate"): (403, 404),
    ("GET", "/catalog/facets"): (400, 403),
    ("GET", "/catalog/search"): (403,),
    ("POST", "/enterprise/auth/oidc-preview"): (400,),
    ("POST", "/enterprise/auth/oidc-verify"): (400,),
    ("GET", "/enterprise/connectors/{connector_id}/probe"): (400, 403, 404),
    ("GET", "/enterprise/demo-plan"): (400,),
    ("POST", "/graph/edges"): (400, 403, 409),
    ("POST", "/graph/nodes"): (403, 409),
    ("GET", "/graph/nodes/{node_id}"): (403, 404),
    # ``/graph/stats`` refuses an anonymous caller like every other graph read.
    # It answered 200 to one, with no policy decision recorded, until the gate
    # its three siblings already used was applied.
    ("GET", "/graph/stats"): (403,),
    ("POST", "/graph/query"): (400, 403, 404),
    ("POST", "/llm/draft-query"): (400, 403, 404),
    ("POST", "/llm/search"): (400, 403),
    ("GET", "/ontology/change-log"): (403,),
    ("POST", "/ontology/concepts"): (400, 403, 409),
    ("GET", "/ontology/patches"): (400, 403),
    ("POST", "/ontology/patches"): (400, 403),
    ("POST", "/ontology/patches/{patch_id}/review"): (400, 403, 404, 409),
    ("POST", "/ontology/resolve"): (400, 409),
    ("GET", "/ontology/search"): (400, 409),
    ("POST", "/policy/decision"): (403, 404),
    ("GET", "/policy/decisions"): (403,),
    ("POST", "/search/semantic"): (403,),
}


def refusal_responses(statuses: tuple[int, ...]) -> dict[int, dict[str, Any]]:
    """Build the OpenAPI ``responses`` fragment for one route's refusals."""
    return {
        status: {
            "description": REFUSAL_DESCRIPTIONS[status],
            "content": {"application/json": {"schema": ERROR_RESPONSE_SCHEMA}},
        }
        for status in statuses
    }


def document_refusals(app: FastAPI) -> dict[tuple[str, str], tuple[int, ...]]:
    """Attach the refusal contract to every route that declares one.

    Returns the routes that were annotated, so a caller (and the contract test)
    can see that no table entry named a path the app does not serve - a stale
    entry would otherwise sit in the table documenting nothing.
    """
    applied: dict[tuple[str, str], tuple[int, ...]] = {}
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        for method in route.methods:
            statuses = ROUTE_REFUSALS.get((method, route.path))
            if not statuses:
                continue
            route.responses = {**route.responses, **refusal_responses(statuses)}
            applied[(method, route.path)] = statuses
    # Regenerating is required: FastAPI caches the document on first request.
    app.openapi_schema = None
    return applied


def policy_gated_route_methods() -> frozenset[tuple[str, str]]:
    """The ``(method, path)`` pairs this contract says evaluate policy.

    A route that can answer **403** is a route that asked ``policy.evaluate``
    and was refused, so the published refusal contract already names the
    governed surface. Derived from it rather than listed again, because two
    lists of the same thing drift: declaring a new governed route's 403 here is
    what puts it under the policy/audit self-check, and forgetting the
    declaration is already a contract-test failure.

    The **method is part of the answer**, and dropping it was a live defect in
    the first version of this function: it returned bare paths, the middleware
    compared bare paths, and one path serves both a governed and an open
    method. ``POST /ontology/concepts`` declares 403, so ``/ontology/concepts``
    entered the governed set and took ``GET /ontology/concepts`` with it - a
    deliberately open, actor-less vocabulary read that evaluates no policy and
    records nothing. One anonymous ``GET`` then scored as a governed 2xx with no
    evidence and made the *critical* ``policy_audit_gap`` rule publish
    ``firing: true`` on the first ordinary request (measured). The published
    "measured 0, a regression detector rather than a standing complaint" was
    taken over 403-capable **GET** templates only, so the measurement and the
    membership test disagreed about what "governed" meant and the measurement
    was the one that looked right.

    Both maps are read, because a 403 declared in either one is a 403 the route
    can answer.
    """
    gated: set[tuple[str, str]] = set()
    for refusals in (ROUTE_REFUSALS, DYNAMIC_REFUSALS):
        for (method, path), codes in refusals.items():
            if 403 in codes:
                gated.add((method, path))
    return frozenset(gated)
