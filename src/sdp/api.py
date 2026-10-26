from __future__ import annotations

import logging
from datetime import datetime, timezone
from time import monotonic
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from sdp_core import (
    buyer_demo_activation_plan,
    enterprise_controls_manifest,
    enterprise_kpi_framework,
    enterprise_production_readiness_manifest,
    enterprise_rbac_matrix,
    enterprise_readiness_manifest,
)

from . import authz, browse, catalog, connectors, ontology, ontology_version, orchestrator
from .config import get_app_config
from .console import render_enterprise_console
from .graph_models import (
    GraphEdgeRequest,
    GraphNodeRequest,
    GraphTraversalRequest,
    OntologyConceptRequest,
    SemanticSearchRequest,
)
from .graph_store import GraphIntegrityConflict, NodeKindConflict, get_store
from .seed import assert_dataset_mirror_kinds_are_available, seed_dataset, seed_store
from .catalog import (
    deprecate_dataset,
    get_dataset,
    get_dataset_audit_events,
    get_dataset_profile,
    get_dataset_lineage,
    get_join_candidates,
    get_dataset_schema_diff,
    get_dataset_schema_history,
    list_dataset_schema_versions,
    get_related_datasets,
    list_audit_events,
    list_datasets,
    list_facet_counts,
    patch_dataset,
    publish_dataset,
    register_dataset,
    validate_metadata,
)
from .domain import (
    DatasetCreateRequest,
    DatasetPatchRequest,
    QueryDraftRequest,
    QueryExecutionRequest,
)
from .enterprise_evidence import build_enterprise_evidence_pack
from .evidence import collect_request_evidence_ids, list_policy_decisions
from .latency_budgets import latency_budget_report
from .observability import (
    build_observability_manifest,
    build_request_observation,
    prometheus_metrics_text,
    record_request_observation_async,
    request_id_from_headers,
    request_id_header,
)
from .api_error_contract import document_refusals
from .api_request_contract import document_request_bodies
from .api_response_contract import document_responses
from .authz import can_access_tenant, resolve_actor_context
from .policy import (
    accessible_tenant_ids,
    can_see_graph_node,
    evaluate,
    evaluate_dataset_scope_refusal,
    filter_graph_search_results,
    filter_graph_traversal,
    scope_concept_graph,
    graph_node_target_tenant,
)
from .semantic_validation import enterprise_shacl_validation_summary, validate_dataset_semantics
from .steward_review import build_steward_review_summary


_logger = logging.getLogger(__name__)


app = FastAPI(
    title="Semantic Data Portal",
    description="온톨로지 기반 그래프 데이터 카탈로그 및 시맨틱 검색 서비스",
    version="0.3.0",
)

# CORS allowlist comes from config (KV table `config_entries` when a database is
# reachable, otherwise bundled safe defaults). Tightened from the previous "*".
_config = get_app_config()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_config.cors_allow_origins,
    allow_methods=_config.cors_allow_methods,
    allow_headers=_config.cors_allow_headers,
)


@app.on_event("startup")
def _bootstrap_graph_engine() -> None:
    """Seed the active graph store on startup (idempotent)."""

    try:
        seed_store()
    except Exception:  # pragma: no cover - seeding must never block startup
        pass


# Seed at import time as well: the test client and embedded/submodule callers
# may hit endpoints without triggering ASGI startup events. Seeding is
# idempotent so running it here and on startup is safe.
try:
    seed_store()
except Exception:  # pragma: no cover
    pass


@app.middleware("http")
async def record_request_observability(request: Request, call_next):
    started = monotonic()
    request_id = request_id_from_headers(request.headers)
    response: Response | None = None

    # The log line's ``evidence_ids`` is the key that ties it to
    # ``/policy/decisions`` and ``/audit/events``. It was read from the
    # caller-supplied ``X-SDP-Evidence-Ids`` header, so the caller the line is
    # about chose its own correlation key and the id the server recorded never
    # appeared - measured, a governed preview exported two forged ids while its
    # real decision was absent from the log. Collected from the two evidence
    # chokepoints instead; the list the handler appends to is the one read here,
    # which is why a ``ContextVar`` holding a mutable object works across the
    # threadpool copy FastAPI makes for ``def`` handlers.
    with collect_request_evidence_ids() as collected:
        try:
            response = await call_next(request)
            return response
        finally:
            latency_ms = (monotonic() - started) * 1000
            status_code = response.status_code if response is not None else 500
            observation = build_request_observation(
                method=request.method,
                route=request.url.path,
                status_code=status_code,
                latency_ms=latency_ms,
                headers=request.headers,
                request_id=request_id,
                evidence_ids=collected.ids,
                withheld_evidence_id_count=collected.withheld,
            )
            if response is not None:
                response.headers[request_id_header()] = request_id
            # The sink write is blocking, so it is awaited off the event loop;
            # see record_request_observation_async. Setting the header first
            # keeps the response untouched by the export path.
            await record_request_observation_async(observation)


def _change_reason(payload: dict[str, Any] | None) -> str | None:
    """A caller-supplied reason for a catalog change, or ``None``.

    CAT-005's acceptance criterion names the reason alongside the diff, the
    actor and the timestamp, and only ``deprecate`` accepted one: a ``reason``
    sent to ``POST /catalog/datasets`` or ``PATCH /catalog/datasets/{id}``
    answered 200 and was dropped, because the request models declare no such
    field and pydantic ignores an extra one.

    Read from the raw payload rather than added to those models on purpose: a
    change reason is metadata *about* the change, not dataset state, and the
    models' fields are a strict subset of ``Dataset``'s - an invariant
    ``tests/test_catalog_field_forwarding.py`` asserts and a ``reason`` field
    would break.

    Bounded and normalised here rather than at four call sites. A blank or
    whitespace-only string is ``None``: "the caller sent an empty reason" and
    "the caller sent none" are the same fact, and recording the first as a
    reason would put an empty string where a ledger reader expects prose.
    """
    if not payload:
        return None
    reason = payload.get("reason")
    if not isinstance(reason, str):
        return None
    reason = reason.strip()
    if not reason:
        return None
    return reason[:MAX_CHANGE_REASON_CHARS]


def _audit_refused_catalog_mutation(
    *, event_type: str, actor: str, dataset_id: str, decision: Any, reason: str = ""
) -> None:
    """Record the audit half of a *refused* catalog mutation.

    ``CLAUDE.md`` states the governance invariant for this product: a policy
    evaluation **and** an evidence record accompany every catalog mutation and
    every browse/query path. The browse paths honoured both halves on a denial
    (``browse.py`` calls ``ingest_event(decision="denied", ...)``); the four
    catalog mutations evaluated policy and then raised, so a refused attempt
    left a decision and no audit row. Measured on each verb as an
    unauthorized actor:

        PATCH  /catalog/datasets/{id}            -> 403  decisions +1  audits +0
        POST   /catalog/datasets/{id}/publish    -> 403  decisions +1  audits +0
        POST   /catalog/datasets/{id}/deprecate  -> 403  decisions +1  audits +0
        POST   /catalog/datasets                 -> 403  decisions +1  audits +0

    An auditor looking for refused attempts on a catalog mutation - which is
    exactly what an auditor looks for - found nothing in ``/audit/events`` or
    ``/catalog/datasets/{id}/audit``. The ontology and graph writes were already
    covered, because they share ``_authorize_graph_write``, which audits; these
    four authorize inline. The row carries the same ``action`` as the allow-path
    row so a filter by action returns both outcomes, with ``result`` telling
    them apart.

    The real reason is recorded even where the response withholds it: an
    out-of-scope dataset answers 404 with a generic detail so the status and the
    body cannot be an existence oracle, while the ledger - which the refused
    caller cannot read - keeps the reason the engine gave. That is the same
    split ``browse`` already makes.
    """
    catalog.ingest_event(
        event_type=event_type,
        actor=actor,
        dataset_id=dataset_id,
        decision="denied",
        # ``reason`` overrides the decision's own only where the refusal is not
        # the decision's: a mutation the policy *allowed* and an integrity rule
        # then refused (a node-kind conflict, 409) would otherwise be recorded
        # under the allow-reason, which reads as the opposite of what happened.
        # The governance invariant is a decision **and** an audit row for every
        # catalog mutation, including a refused one, so these are audited rather
        # than silently 409'd - the same choice the concept-upsert route makes
        # for the structurally identical conflict.
        reason=reason or decision.reason,
        decision_id=decision.decision_id,
        details={"purpose": "catalog", "policy_decision_id": decision.decision_id},
    )


# A reason is prose for a human auditor, and the payload is caller-supplied, so
# it is bounded like every other caller-supplied string this product retains.
MAX_CHANGE_REASON_CHARS = 512


def _actor(payload: dict[str, Any] | None) -> str:
    if not payload:
        return "anonymous"
    return str(payload.get("actor", "anonymous"))


def _require_actor(payload: dict[str, Any]) -> str:
    return _actor(payload)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "at": datetime.now(timezone.utc).isoformat()}


@app.get("/metrics")
def metrics() -> Response:
    return Response(content=prometheus_metrics_text(), media_type="text/plain; version=0.0.4")


@app.get("/enterprise/readiness")
def enterprise_readiness() -> dict[str, Any]:
    return enterprise_readiness_manifest().model_dump()


@app.get("/enterprise/demo-plan")
def enterprise_demo_plan(
    domain: str = Query(default="customer intelligence", min_length=1),
    connector: list[str] | None = Query(default=None),
) -> dict[str, Any]:
    # A domain with no fixture is NOT an error: the activation plan is a generic
    # template - workflow, activation days, data requirements and handoff
    # artifacts - and the fixture only supplies domain-specific datasets and
    # analyst questions when the lab has built one. An earlier attempt to refuse
    # an unfixtured domain here was wrong and broke
    # test_enterprise_demo_plan_supports_buyer_activation_path, which sends
    # "insurance claims" deliberately and expects a full plan back.
    try:
        return buyer_demo_activation_plan(priority_domain=domain, connector_ids=connector).model_dump()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/enterprise/kpis")
def enterprise_kpis() -> dict[str, Any]:
    return enterprise_kpi_framework().model_dump()


@app.get("/enterprise/controls")
def enterprise_controls() -> dict[str, Any]:
    return enterprise_controls_manifest().model_dump()


@app.get("/enterprise/rbac-matrix")
def enterprise_rbac() -> dict[str, Any]:
    # The per-role matrix plus the seeded subject->role bundling. Without the
    # bundling a reader of the `security` row (platform_evidence_only) cannot tell
    # that the `security` subject also holds `platform-admin` and therefore
    # crosses every tenant.
    return {
        **enterprise_rbac_matrix().model_dump(),
        "seeded_subject_bindings": authz.seeded_subject_bindings(),
    }


@app.get("/enterprise/observability")
def enterprise_observability() -> dict[str, Any]:
    return build_observability_manifest()


@app.get("/enterprise/latency-budgets")
def enterprise_latency_budgets() -> dict[str, Any]:
    return latency_budget_report()


@app.get("/enterprise/production-readiness")
def enterprise_production_readiness() -> dict[str, Any]:
    return enterprise_production_readiness_manifest().model_dump()


@app.get("/enterprise/evidence-pack")
def enterprise_evidence_pack() -> dict[str, Any]:
    return build_enterprise_evidence_pack()


@app.get("/enterprise/shacl-validation")
def enterprise_shacl_validation(user: str = Query(default="anonymous")) -> dict[str, Any]:
    # The aggregate stays open - it carries no dataset identity. The per-dataset
    # report array does, so it is scoped to the caller like the rest of the
    # discovery surface. An unresolvable actor sees the aggregate and no reports.
    return enterprise_shacl_validation_summary(accessible_tenant_ids(user))


@app.get("/enterprise/steward-review")
def enterprise_steward_review(user: str = Query(default="anonymous")) -> dict[str, Any]:
    # Same split as /enterprise/shacl-validation: platform-wide counts and
    # readiness, caller-scoped per-dataset identity.
    return build_steward_review_summary(accessible_tenant_ids(user))


@app.get("/enterprise/console", response_class=HTMLResponse)
def enterprise_console() -> str:
    return render_enterprise_console()


@app.post("/enterprise/auth/oidc-preview")
def enterprise_oidc_preview(payload: dict[str, Any]) -> dict[str, Any]:
    claims = payload.get("claims", payload)
    if not isinstance(claims, dict):
        raise HTTPException(status_code=400, detail="claims must be an object")

    role_map = payload.get("role_map")
    if role_map is not None and not isinstance(role_map, dict):
        raise HTTPException(status_code=400, detail="role_map must be an object")

    # Who is asking. The same predicate gates the ledger write below, so this
    # route has one notion of "an authenticated operator" rather than two.
    actor_id = _actor(payload)
    operator = actor_id != "anonymous" and bool(resolve_actor_context(actor_id).roles)

    # The configured role map is operator configuration, and this route turned it
    # into an oracle. Measured with
    # SDP_OIDC_GROUP_ROLE_MAP={"acme-finance": {"admins": ["platform-admin"]}},
    # no credential of any kind:
    #
    #   POST /enterprise/auth/oidc-preview
    #     {"claims": {"sub": "attacker@evil.example", "tenant_id": "acme-finance",
    #                 "groups": ["admins"], "exp": <future>}}
    #   -> 200 {"actor_context": {"roles": ["platform-admin"], ...},
    #           "group_role_bindings": [{"group_name": "admins",
    #                                    "tenant_scope": "acme-finance",
    #                                    "granted_roles": ["platform-admin"]}]}
    #
    # An unmapped group comes back with an empty scope and no roles, so the two
    # are distinguishable and an outsider can enumerate the whole group -> role
    # map, and the valid tenant scopes, one guessed group name at a time.
    #
    # A caller previewing against a role map **they supplied in the request**
    # learns nothing they did not already know, and that is the route's stated
    # purpose - validating a claim shape against a candidate map. So that path
    # stays open. Nor is the shipped default a secret: it is a constant in
    # ``authz.py``, public and in the repository, and it is what makes the demo
    # preview work with no configuration. What must not be readable without an
    # actor is the **deployment's own** map from SDP_OIDC_GROUP_ROLE_MAP, which
    # is the real group-to-role policy. The response says which map produced the
    # mapping instead of leaving it to be inferred.
    effective_role_map = role_map
    if role_map is not None:
        role_map_source = "request"
    elif not authz.oidc_role_map_is_operator_configured():
        role_map_source = "shipped_default"
    elif operator:
        role_map_source = "operator_configured"
    else:
        effective_role_map = {}
        role_map_source = "withheld_operator_configured_map_requires_an_actor"

    try:
        context = authz.resolve_oidc_actor_context(claims, role_map=effective_role_map)
        group_bindings = authz.oidc_group_role_bindings(claims, role_map=effective_role_map)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    declared_group_count = authz.claim_value_count(claims.get("groups"))
    withheld_group_count = max(0, declared_group_count - len(group_bindings))

    ignored_role_claims = authz.oidc_role_claims(claims)
    # An unauthenticated caller must not be able to write to the evidence
    # ledger at all. This route is open (previewing a claim shape discloses
    # nothing) and it was recording an audit event on every call, filed under
    # the tenant the *unverified claims* named. Two consequences, both measured:
    # an outsider could plant a row in any tenant's ledger claiming
    # platform-admin had been granted, and 300 unauthenticated requests put 300
    # rows into the persisted store, which has no cap.
    #
    # The preview still computes and still returns its mapping. The ledger write
    # now needs an authenticated actor, and even then the row is marked
    # unverified: this route does not check a signature, so its tenant is a
    # claim rather than a fact.
    audit_event = None
    if operator:
        audit_event = authz.record_oidc_mapping_audit_event(
            context,
            group_bindings,
            mapping_mode="claim_mapping_preview",
            ignored_role_claims=ignored_role_claims,
            tenant_verified=False,
        )

    return {
        "mode": "claim_mapping_preview",
        "token_verification": "external_signature_required_claim_shape_validated",
        # Stated rather than left to inference: an open preview records nothing.
        "audit_recorded": audit_event is not None,
        "audit_note": (
            "미인증 preview는 증빙 원장에 기록되지 않습니다 (actor를 보내면 "
            "기록되며, 이 라우트는 서명을 검증하지 않으므로 tenant는 claim으로 "
            "표시됩니다)."
        ),
        "actor_context": context.model_dump(),
        # Shaped exactly like a resolved ``ActorContext``, so say plainly that it
        # is not one. No signature was checked here; the subject, tenant and
        # roles are what a token carrying these claims *would* map to.
        "actor_context_verified": False,
        # Which role map produced the mapping above.
        "role_map_source": role_map_source,
        # The caller's own group claim, bounded and echoed back. Unbounded, this
        # was an amplifier: a 2 MB group name produced a 4 MB response, and
        # 100,000 groups produced 7.58 MB, on a route needing no credential.
        "groups": [binding["group_name"] for binding in group_bindings],
        "group_role_bindings": group_bindings,
        "declared_group_count": declared_group_count,
        "withheld_group_count": withheld_group_count,
        "ignored_role_claims": ignored_role_claims,
        "audit_event_id": audit_event.id if audit_event else None,
    }


# The trust anchors a token is verified against are operator configuration, not
# request input. A caller that could name its own issuer, audience, signing keys
# or role map would be verifying its own signature and could mint any tenant and
# role it liked, so these fields are refused outright rather than ignored.
_OIDC_VERIFY_OPERATOR_ONLY_FIELDS = ("issuer", "audience", "jwks", "role_map")


@app.post("/enterprise/auth/oidc-verify")
def enterprise_oidc_verify(payload: dict[str, Any]) -> dict[str, Any]:
    token = payload.get("token")
    if not isinstance(token, str) or not token:
        raise HTTPException(status_code=400, detail="token is required")

    supplied_operator_fields = [
        field for field in _OIDC_VERIFY_OPERATOR_ONLY_FIELDS if field in payload
    ]
    if supplied_operator_fields:
        raise HTTPException(
            status_code=400,
            detail=(
                "issuer, audience, jwks and role_map are operator configuration "
                "(SDP_OIDC_ISSUER, SDP_OIDC_AUDIENCE, SDP_OIDC_JWKS or "
                "SDP_OIDC_JWKS_URL, SDP_OIDC_GROUP_ROLE_MAP) and are not accepted "
                "in the request body: " + ", ".join(supplied_operator_fields)
            ),
        )

    try:
        context, claims = authz.verify_oidc_jwks_token(token)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    group_bindings = authz.oidc_group_role_bindings(claims)
    ignored_role_claims = authz.oidc_role_claims(claims)
    # The group claim is capped (``authz.MAX_CLAIM_VALUES``), and on this path the
    # cap can change an authorization outcome: groups past the cap grant no
    # roles. That direction is fail-closed - it withholds roles rather than
    # granting them - but an operator debugging a missing role must be able to
    # see that it happened, so the truncation is declared here as it is on the
    # preview rather than being silent.
    declared_group_count = authz.claim_value_count(claims.get("groups"))
    withheld_group_count = max(0, declared_group_count - len(group_bindings))
    audit_event = authz.record_oidc_mapping_audit_event(
        context,
        group_bindings,
        # This path checked the signature against operator-configured trust
        # anchors, so the token's tenant is a verified fact and the row belongs
        # in that tenant's ledger.
        tenant_verified=True,
        mapping_mode="jwks_signature_verification",
        ignored_role_claims=ignored_role_claims,
    )

    return {
        "mode": "jwks_signature_verification",
        "token_verification": "jwks_signature_verified",
        "actor_context": context.model_dump(),
        "issuer": claims.get("iss"),
        "audience": claims.get("aud"),
        "groups": [binding["group_name"] for binding in group_bindings],
        "group_role_bindings": group_bindings,
        "declared_group_count": declared_group_count,
        "withheld_group_count": withheld_group_count,
        "ignored_role_claims": ignored_role_claims,
        "audit_event_id": audit_event.id,
    }


@app.get("/enterprise/connectors/{connector_id}/probe")
def enterprise_connector_probe(
    connector_id: str,
    dataset_id: str = Query(..., min_length=1),
    user: str = Query(default="anonymous"),
    purpose: str = Query(default="analysis"),
) -> dict[str, Any]:
    # The probe describes one named dataset - its source system, schema-field
    # count and sensitivity - so it is gated and audited like the other governed
    # per-dataset reads rather than served as an actor-less manifest.
    # The dataset arrives in a QUERY parameter here. The earlier sweep enumerated
    # routes naming a dataset in the path, then in the request body, and never
    # checked this third mechanism - so this route answered 403 "tenant boundary
    # denied" for a foreign dataset and 404 "dataset not found" for an absent
    # one. Resolving it in the caller's scope makes both answers the same, before
    # the policy evaluation below can produce a distinguishing reason.
    if catalog.dataset_in_scope(dataset_id, accessible_tenant_ids(user)) is None:
        raise HTTPException(status_code=404, detail="dataset not found")
    decision = evaluate(subject=user, resource=dataset_id, action="schema", purpose=purpose)
    if decision.effect != "allow":
        catalog.ingest_event(
            event_type="enterprise.connector_probe",
            actor=user,
            dataset_id=dataset_id,
            decision="denied",
            reason=decision.reason,
            decision_id=decision.decision_id,
            details={"connector_id": connector_id, "policy_decision_id": decision.decision_id},
        )
        raise HTTPException(status_code=403, detail=decision.reason)
    try:
        probe = connectors.connector_probe(connector_id, dataset_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except KeyError:
        raise HTTPException(status_code=404, detail="dataset not found")
    catalog.ingest_event(
        event_type="enterprise.connector_probe",
        actor=user,
        dataset_id=dataset_id,
        decision="allowed",
        reason=decision.reason,
        decision_id=decision.decision_id,
        details={"connector_id": connector_id, "policy_decision_id": decision.decision_id},
    )
    return {**probe, "policy_decision_id": decision.decision_id}


@app.get("/healthz")
def healthz(response: Response) -> dict[str, Any]:
    """Readiness probe verifying graph-engine backend availability.

    Returns 200 when the active store is ready (in-memory always ready; the
    Postgres backend requires AGE + pgvector reachable), 503 otherwise.
    """

    try:
        store = get_store()
        readiness = store.readiness()
        stats = store.stats() if readiness.get("ready") else {}
    except Exception:  # details belong in server logs, never this public endpoint
        _logger.exception("graph health probe failed")
        readiness = {
            "ready": False,
            "backend": "unavailable",
            "error": "backend unreachable",
        }
        stats = {}
    payload = {
        "status": "ready" if readiness.get("ready") else "unavailable",
        "config_source": _config.source,
        "store": readiness,
        "stats": stats,
        "at": datetime.now(timezone.utc).isoformat(),
    }
    if not readiness.get("ready"):
        response.status_code = 503
    return payload


def _authorize_catalog_discovery(user: str) -> list[str] | None:
    """Authorize a catalog discovery read and resolve its tenant scope.

    Discovery used to take no actor at all, so an unauthenticated caller received
    every tenant's dataset inventory - ids, titles, owners, status - and the owner
    facet aggregated across tenants, while the governed path refused the same
    dataset. ``src/sdp_core/kpis.py`` publishes the guardrail that contradicts:
    "No unauthorized dataset existence disclosure."
    """
    decision = evaluate(subject=user, resource="catalog", action="search", purpose="discovery")
    if decision.effect != "allow":
        raise HTTPException(status_code=403, detail=decision.reason)
    return accessible_tenant_ids(user)


@app.get("/catalog/search")
def catalog_search(
    # Each token is matched against every dataset, so an unbounded query is
    # unbounded work: 1005 datasets took 0.03s at 10 tokens and 5.10s at 2000.
    q: str = Query(..., min_length=1, max_length=2000),
    user: str = Query(default="anonymous"),
    tags: list[str] | None = Query(default=None),
    domain: list[str] | None = Query(default=None),
    owner: list[str] | None = Query(default=None),
    sensitivity: list[str] | None = Query(default=None),
    status: list[str] | None = Query(default=None),
    license: list[str] | None = Query(default=None),
    min_quality: float | None = Query(default=None, ge=0, le=1),
    min_freshness: float | None = Query(default=None, ge=0, le=1),
    limit: int = Query(default=20, ge=1, le=100),
    include_inactive: bool = Query(default=False),
) -> dict[str, Any]:
    tenant_ids = _authorize_catalog_discovery(user)
    results = catalog.search_catalog(
        q,
        tenant_ids=tenant_ids,
        tags=tags,
        domain=domain,
        owner=owner,
        sensitivity=sensitivity,
        status=status,
        license=license,
        min_quality=min_quality,
        min_freshness=min_freshness,
        include_inactive=include_inactive,
        limit=limit,
    )

    filtered = [
        {
            "id": row.dataset.id,
            "title": row.dataset.title,
            "tags": row.dataset.tags,
            "owner": row.dataset.owner,
            "steward": row.dataset.steward,
            "domain": row.dataset.domain,
            "quality": row.dataset.quality_score,
            "freshness": row.dataset.freshness_score,
            "search_score": row.score,
            "metadata_completeness": row.dataset.metadata_completeness,
            "completeness_score": row.dataset.completeness_score,
            "status": row.dataset.status,
            "version": row.dataset.version,
            "schema_version": row.dataset.schema_version,
            "metadata_recommendation_score": row.dataset.metadata_recommendation_score,
            "completeness_badge": catalog.completeness_badge(row.dataset)
        }
        for row in results
    ]

    return {
        "query": q,
        "count": len(filtered),
        "items": filtered,
    }


@app.get("/catalog/facets")
def catalog_facets(
    q: str | None = Query(default=None, max_length=2000),
    field: str = Query(default="domain"),
    user: str = Query(default="anonymous"),
) -> dict[str, Any]:
    tenant_ids = _authorize_catalog_discovery(user)
    try:
        counts = list_facet_counts(field, query=q, tenant_ids=tenant_ids)
    except ValueError:
        raise HTTPException(status_code=400, detail="unsupported facet field")
    return {"field": field, "counts": counts}


@app.get("/catalog/datasets")
def list_datasets_endpoint(user: str = Query(default="anonymous")) -> list[dict[str, Any]]:
    tenant_ids = _authorize_catalog_discovery(user)
    return [catalog.discovery_view(dataset) for dataset in list_datasets(tenant_ids)]


def _record_unscoped_dataset_refusal(dataset_id: str, user: str) -> None:
    """Leave the evidence a catalog-family scope refusal owes the ledger.

    Closing the existence oracle made the *response* for a foreign dataset
    identical to the one for an absent dataset, which is the point. It must not
    make the two identical in the **ledger** as well, and it did. Measured on a
    ``/catalog/datasets/{id}/...`` read of a dataset in another tenant:

        decisions +1   effect=allow  resource='catalog'  (discovery passed)
        audits     +0

    So the refusal left no deny decision naming the dataset and no audit event
    at all, while ``/browse`` - refusing the same caller for the same cause -
    wrote both halves with ``reason='tenant boundary denied'``. An auditor
    reading the ledger could not see that anyone had reached for the dataset.
    This gap was recorded honestly as open in an earlier commit in this series
    rather than claimed closed; this is the close.

    Which of the two surfaces carries which fact is the whole design here, and
    getting it wrong reopens the oracle through the ledger instead of the
    response. The first attempt at this repair put ``refusal_cause`` and the
    owning tenant id into the audit row and filed a foreign-dataset refusal
    under the *owning* tenant. The prober can read its own tenant's audit
    events, so that made the row itself the oracle: present and saying
    ``absent_dataset`` when the id is free, missing when the id belongs to
    somebody else.

    So:

    * the **policy decision** holds the truth. It is evaluated against the
      dataset id, so a foreign dataset yields the engine's own ``tenant
      boundary denied``, and ``_effective_tenant_id`` files it under the
      dataset's owning tenant - where that tenant's auditor sees attempts on its
      assets and the prober cannot reach it.
    * the **audit event** is uniform and filed to the actor's own tenant:
      identical reason and details whether the id is foreign or free, so reading
      it back discloses nothing the caller did not already know.
    """
    decision = evaluate_dataset_scope_refusal(user, dataset_id)
    catalog.ingest_event(
        event_type="catalog.dataset_read",
        actor=user,
        dataset_id=dataset_id,
        decision="denied",
        reason="dataset not found",
        decision_id=decision.decision_id,
        details={
            "policy_decision_id": decision.decision_id,
            "tenant_id": resolve_actor_context(user).tenant_id or None,
        },
    )


def _scoped_dataset_and_tenants(dataset_id: str, user: str) -> tuple[Any, list[str] | None]:
    """Resolve a dataset and the reader's tenant scope, or 404.

    Used directly by the routes that need the scope itself; the rest go through
    :func:`_require_scoped_dataset`.
    """
    tenant_ids = _authorize_catalog_discovery(user)
    dataset = catalog.dataset_in_scope(dataset_id, tenant_ids)
    if not dataset:
        _record_unscoped_dataset_refusal(dataset_id, user)
        raise HTTPException(status_code=404, detail="dataset not found")
    return dataset, tenant_ids


def _require_scoped_dataset(dataset_id: str, user: str) -> Any:
    """Resolve a dataset for a per-dataset catalog read, or 404.

    Applied uniformly to every ``/catalog/datasets/{dataset_id}/...`` route: a
    dataset outside the reader's tenant scope must be indistinguishable from one
    that does not exist. Three per-route fixes were each bypassed by a sibling -
    ``/jsonld`` kept returning a hidden dataset's title, owner and description,
    ``/lineage`` its upstream and downstream ids, and ``/related``, ``/validate``,
    ``/semantic-validation`` and ``/schema-versions`` answered 200, which is an
    existence oracle on its own. ``tests/test_catalog_tenant_scope.py`` enumerates
    the routes from ``app.routes`` so the next sibling is covered automatically.
    """
    return _scoped_dataset_and_tenants(dataset_id, user)[0]


@app.get("/catalog/datasets/{dataset_id}")
def dataset_detail(
    dataset_id: str, user: str = Query(default="anonymous")
) -> dict[str, Any]:
    # 404, not 403: the defect being fixed here is existence disclosure, so a
    # dataset outside the reader's tenant scope must be indistinguishable from
    # one that does not exist.
    #
    # This route re-implemented the gate inline instead of calling the shared
    # helper, which is why it did not pick up the refusal-evidence repair with
    # its siblings. It now goes through the same helper they do.
    dataset = _require_scoped_dataset(dataset_id, user)
    return catalog.discovery_view(dataset)


# Inline JSON-LD context for the DCAT export.
#
# The export declared `@context` and `@type` but was not consumable as JSON-LD:
#
#   * the node identifier was `id`, which is an ordinary term rather than the
#     `@id` keyword, so a processor read no subject IRI for the dataset;
#   * `@context` pointed at https://www.w3.org/TR/vocab-dcat-3/ - the HTML
#     specification page, not a context document - so a processor fetching it
#     received HTML;
#   * `@type` was the bare string "Dataset", and `title`, `description`,
#     `owner`, `steward`, `domain` and the score fields had no mapping at all,
#     so a processor would have *dropped every one of them* as unmapped terms.
#
# The context is inline so the document is self-describing and needs no network
# fetch. Portal-specific fields get the portal's own vocabulary IRI rather than
# being asserted as DCAT terms they are not.
#
# Adding the context fixed only the **top level**. Every property inside
# `distribution` and `mappings` stayed unmapped, so a conforming processor
# dropped them. Measured with pyld 3.3.0 on the live response:
#
#     raw  distribution -> [{"id": "dist-crm-customer",
#                            "format": "postgresql.table",
#                            "endpoint": "https://example.internal/..."}]
#     expanded          -> [{}]                  # an empty blank node
#
#     raw  mappings[0]  -> {"concept": "고객", "status": ..., "source": ...,
#                           "steward": ..., "approved_at": ...}
#     expanded keys     -> ['sdp#status', 'sdp#steward']   # concept dropped
#
# In N-Quads the distribution appears only as an object with **zero** outgoing
# triples: no access URL, no format, no identifier - which is the entire point
# of a DCAT distribution. An approval record with its `concept` dropped cannot
# say which business concept was approved. Across the five seeded datasets:
# 5/5 distributions expanded to `{}` and 51 nested term occurrences had no
# mapping. `docs`/`readiness` cite this endpoint as the proof artifact for the
# `rdf_connector` capability, so the auditor verifying that claim is exactly who
# loads the export into an RDF tool and finds nothing there.
#
# `endpoint` is typed `@id` so it expands to a node reference rather than a
# string literal, and `approved_at` is typed `xsd:dateTime` so a consumer can
# order approvals. `dist_id` is the distribution's own `@id`; the nested `id`
# term is gone, because `id` is an ordinary term and never the `@id` keyword -
# the same mistake the top level had.
JSONLD_CONTEXT: dict[str, Any] = {
    "dcat": "http://www.w3.org/ns/dcat#",
    "dcterms": "http://purl.org/dc/terms/",
    "sdp": "https://semantic-data-portal.local/ns#",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
    "title": "dcterms:title",
    "description": "dcterms:description",
    "license": "dcterms:license",
    "distribution": "dcat:distribution",
    "status": "sdp:status",
    "domain": "sdp:domain",
    "owner": "sdp:owner",
    "steward": "sdp:steward",
    "completeness_score": "sdp:completenessScore",
    "metadata_completeness": "sdp:metadataCompleteness",
    "metadata_recommendation_score": "sdp:metadataRecommendationScore",
    "mappings": "sdp:businessMapping",
    # nested: dcat:Distribution
    "format": "dcterms:format",
    "endpoint": {"@id": "dcat:accessURL", "@type": "@id"},
    # nested: sdp:businessMapping
    "concept": "sdp:concept",
    "source": "dcterms:source",
    "approved_at": {"@id": "sdp:approvedAt", "@type": "xsd:dateTime"},
}

JSONLD_KEYWORDS = frozenset({"@context", "@id", "@type"})


def _jsonld_distribution(dataset: Any, distribution: Any) -> dict[str, Any]:
    """Render one distribution as a real DCAT node rather than a bare dict.

    The raw ``model_dump`` carried ``id``, which is an ordinary term and not the
    ``@id`` keyword, so the distribution expanded to an anonymous blank node
    with no identity. It now gets a subject IRI derived from the dataset and the
    distribution id, and an explicit ``@type``, so a consumer can refer to it.
    The original identifier is kept as ``dcterms:identifier`` rather than
    silently dropped.
    """
    payload = distribution.model_dump()
    distribution_id = payload.pop("id", None)
    node: dict[str, Any] = {"@type": "dcat:Distribution"}
    if distribution_id:
        node["@id"] = (
            "https://semantic-data-portal.local/datasets/"
            f"{dataset.id}/distributions/{distribution_id}"
        )
        node["dcterms:identifier"] = distribution_id
    node.update(payload)
    return node


@app.get("/catalog/datasets/{dataset_id}/jsonld")
def dataset_jsonld(
    dataset_id: str,
    user: str = Query(default="anonymous"),
) -> dict[str, Any]:
    _require_scoped_dataset(dataset_id, user)
    dataset = get_dataset(dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="dataset not found")
    return {
        "@context": JSONLD_CONTEXT,
        "@type": "dcat:Dataset",
        "@id": f"https://semantic-data-portal.local/datasets/{dataset.id}",
        "title": dataset.title,
        "description": dataset.description,
        "license": dataset.license,
        "status": dataset.status,
        "completeness_score": dataset.completeness_score,
        "metadata_completeness": dataset.metadata_completeness,
        "metadata_recommendation_score": dataset.metadata_recommendation_score,
        "domain": dataset.domain,
        "owner": dataset.owner,
        "steward": dataset.steward,
        "distribution": [_jsonld_distribution(dataset, d) for d in dataset.distributions],
        "mappings": [m.model_dump() for m in dataset.mappings],
    }


@app.get("/catalog/datasets/{dataset_id}/semantic-validation")
def catalog_dataset_semantic_validation(
    dataset_id: str,
    user: str = Query(default="anonymous"),
) -> dict[str, Any]:
    _require_scoped_dataset(dataset_id, user)
    try:
        return validate_dataset_semantics(dataset_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="dataset not found")


@app.get("/catalog/datasets/{dataset_id}/schema-history")
def catalog_dataset_schema_history(
    dataset_id: str,
    user: str = Query(default="anonymous"),
) -> dict[str, Any]:
    _require_scoped_dataset(dataset_id, user)
    try:
        return get_dataset_schema_history(dataset_id)
    except KeyError as exc:
        # A dataset with no snapshot yet is a 404, per the repository's documented
        # mapping; it was escaping as an uncaught KeyError, i.e. a 500.
        raise HTTPException(status_code=404, detail=str(exc))


@app.get("/catalog/datasets/{dataset_id}/schema-versions")
def catalog_dataset_schema_versions(
    dataset_id: str,
    user: str = Query(default="anonymous"),
) -> dict[str, Any]:
    _require_scoped_dataset(dataset_id, user)
    return {"dataset_id": dataset_id, "versions": list_dataset_schema_versions(dataset_id)}


@app.get("/catalog/datasets/{dataset_id}/join-candidates")
def catalog_dataset_join_candidates(
    dataset_id: str,
    limit: int = Query(default=10, ge=1, le=100),
    user: str = Query(default="anonymous"),
) -> dict[str, Any]:
    _, tenant_ids = _scoped_dataset_and_tenants(dataset_id, user)
    return {
        "dataset_id": dataset_id,
        "join_candidates": get_join_candidates(dataset_id, limit=limit, tenant_ids=tenant_ids),
    }


@app.get("/catalog/datasets/{dataset_id}/profile")
def catalog_dataset_profile(
    dataset_id: str,
    user: str = Query(default="anonymous"),
    purpose: str = Query(default="analysis"),
) -> dict[str, Any]:
    # Scope first, and as a 404: under this prefix a dataset outside the reader's
    # tenant must be indistinguishable from a missing one.
    _require_scoped_dataset(dataset_id, user)
    try:
        return browse.dataset_profile(dataset_id, user=user, purpose=purpose)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


@app.get("/catalog/datasets/{dataset_id}/schema-diff")
def catalog_dataset_schema_diff(
    dataset_id: str,
    from_version: str = Query(...),
    to_version: str = Query(...),
    user: str = Query(default="anonymous"),
) -> dict[str, Any]:
    _require_scoped_dataset(dataset_id, user)
    try:
        return {"dataset_id": dataset_id, "diff": get_dataset_schema_diff(dataset_id, from_version, to_version)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/catalog/datasets/{dataset_id}/validate")
def validate(
    dataset_id: str,
    user: str = Query(default="anonymous"),
) -> dict[str, Any]:
    _require_scoped_dataset(dataset_id, user)
    dataset = get_dataset(dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="dataset not found")
    return validate_metadata(dataset)


@app.get("/catalog/datasets/{dataset_id}/lineage")
def dataset_lineage(
    dataset_id: str,
    user: str = Query(default="anonymous"),
) -> dict[str, Any]:
    _require_scoped_dataset(dataset_id, user)
    try:
        return get_dataset_lineage(dataset_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.get("/catalog/datasets/{dataset_id}/related")
def dataset_related(
    dataset_id: str,
    user: str = Query(default="anonymous"),
) -> dict[str, Any]:
    _require_scoped_dataset(dataset_id, user)
    try:
        return {"dataset_id": dataset_id, "related_datasets": get_related_datasets(dataset_id)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.get("/catalog/datasets/{dataset_id}/audit")
def dataset_audit_events(
    dataset_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    user: str = Query(default="anonymous"),
) -> list[dict[str, Any]]:
    # The same ledger behind a per-dataset path, so it carries the same gate plus
    # the dataset's own tenant check.
    _, tenant_ids = _authorize_evidence_read(user)
    # 404, matching every other /catalog/datasets/{id}/... route: a 403 here would
    # distinguish "exists but denied" from "does not exist" and reopen the
    # existence oracle the detail route was fixed to close.
    dataset = catalog.get_dataset(dataset_id)
    # A dataset that does not exist returned `200 []`, while every sibling route
    # under this prefix returns 404 - so an integrator could not tell an empty
    # ledger from a typo in the id. Out-of-scope and absent answer alike, which
    # is what keeps the existence oracle closed.
    if dataset is None or not can_access_tenant(user, dataset.tenant_id):
        raise HTTPException(status_code=404, detail="dataset not found")
    return [
        event.model_dump()
        for event in get_dataset_audit_events(dataset_id, limit=limit, tenant_ids=tenant_ids)
    ]


def _assert_mirror_kinds_for_existing_dataset(dataset_id: str) -> None:
    """Refuse a status change whose graph mirror would reclassify a node.

    ``publish`` and ``deprecate`` carry no schema, so the column names come
    from the stored row - exactly what ``seed_dataset`` will mirror. An absent
    dataset is left to the mutation itself, which raises ``KeyError`` and
    answers 404; this guard only refuses a conflict it can see.
    """
    dataset = catalog.get_dataset(dataset_id)
    if dataset is None:
        return
    assert_dataset_mirror_kinds_are_available(
        dataset_id, [column.name for column in dataset.schema or []]
    )


@app.post("/catalog/datasets")
def create_dataset(payload: dict[str, Any]) -> dict[str, Any]:
    actor_id = _actor(payload)
    try:
        request = DatasetCreateRequest(**payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=_invalid_request_detail(exc))

    decision = evaluate(
        subject=actor_id,
        resource=request.id or "new",
        action="create",
        purpose="catalog",
        target_tenant_id=request.tenant_id,
    )
    if decision.effect != "allow":
        _audit_refused_catalog_mutation(
            event_type="dataset.register",
            actor=actor_id,
            dataset_id=request.id or "new",
            decision=decision,
        )
        raise HTTPException(status_code=403, detail=decision.reason)

    # The catalog write and its graph mirror are one critical section. They were
    # two unsynchronised steps, so two concurrent schema patches could apply to
    # the catalog in one order and to the graph in the opposite order: measured
    # at 11 of 30 trials, the graph kept a ``pii: true`` column the catalog does
    # not declare, ``/search/semantic`` returned it as the top hit, and
    # ``/browse/{id}/schema`` could not mask it because for the catalog that
    # column does not exist. The lock is reentrant, so the mutation inside may
    # take it again.
    #
    # The mirror itself goes through the same upsert path the startup bootstrap
    # uses. That path ran only at startup, so an onboarded dataset was invisible
    # to graph traversal and semantic search - two capabilities README names -
    # and a status change left a stale node.
    # Before the catalog row, because the mirror below cannot be undone from
    # inside this lock: an id (or a column id) that already exists as another
    # kind of graph node made this route answer 500 with the row created and
    # every later ``seed_store`` raising. See
    # ``assert_dataset_mirror_kinds_are_available``.
    #
    # Passed as ``register_dataset``'s ``before_commit`` hook rather than called
    # here, because a ``POST`` that omits ``id`` has none to check yet: the id is
    # assigned inside the registrar. Checked out here against ``request.id`` -
    # ``None`` for that request - the guard tested a node named ``None``, passed,
    # and the measured 500 with a row created and ``seed_store`` broken came
    # back for every request that let the catalog name the dataset. The hook
    # runs after the id is resolved and before the first write, so a refusal
    # still leaves nothing written.
    try:
        with catalog.catalog_mutation_lock():
            dataset = register_dataset(
                request,
                actor=actor_id,
                decision_id=decision.decision_id,
                # CAT-005's acceptance criterion names a change reason. Read from
                # the raw payload because it is metadata about the change, not
                # dataset state: the request models' fields are a strict subset of
                # ``Dataset``'s, and a ``reason`` field would break that.
                change_reason=_change_reason(payload),
                before_commit=assert_dataset_mirror_kinds_are_available,
            )
            seed_dataset(dataset)
    except (NodeKindConflict, catalog.DatasetAlreadyExists) as conflict:
        # Two refusals, one status: the id this registration wants is already
        # taken - by another kind of graph node, or by a dataset. A duplicate id
        # answered **500** before this arm, because ``_register_dataset_locked``
        # raised a bare ``ValueError`` no route caught.
        _audit_refused_catalog_mutation(
            event_type="dataset.register",
            actor=actor_id,
            dataset_id=request.id or "new",
            decision=decision,
            reason=str(conflict),
        )
        raise HTTPException(status_code=409, detail=str(conflict)) from conflict
    return {"status": "created", "dataset": catalog.mutation_response_view(dataset)}


@app.post("/catalog/datasets/{dataset_id}/publish")
def publish_catalog_dataset(dataset_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    actor_id = _actor(payload)
    decision = evaluate(subject=actor_id, resource=dataset_id, action="publish", purpose="catalog")
    if decision.effect != "allow":
        _audit_refused_catalog_mutation(
            event_type="dataset.publish",
            actor=actor_id,
            dataset_id=dataset_id,
            decision=decision,
        )
        # Foreign and absent both answered 403 here, but with different reasons -
        # "tenant boundary denied" versus "존재하지 않는 데이터셋입니다." - so the
        # reason string carried the oracle even though the status matched. A
        # caller that cannot reach the dataset's tenant gets one answer; an
        # in-scope refusal (role, sensitivity, purpose) keeps its reason.
        if catalog.dataset_in_scope(dataset_id, accessible_tenant_ids(actor_id)) is None:
            raise HTTPException(status_code=404, detail="dataset not found")
        raise HTTPException(status_code=403, detail=decision.reason)

    try:
        # Before the status change, for the reason the create route gives.
        # ``seed_dataset`` is called by all four mutations, and only two of them
        # asked this question: publish answered **400** and deprecate **500**
        # with the status and version already applied and an audit row claiming
        # ``result='success'`` for a request the caller saw fail (measured).
        _assert_mirror_kinds_for_existing_dataset(dataset_id)
        # Mutation and mirror in one critical section; see the create route.
        with catalog.catalog_mutation_lock():
            dataset = publish_dataset(
                dataset_id,
                actor=actor_id,
                decision_id=decision.decision_id,
                change_reason=_change_reason(payload),
            )
            seed_dataset(dataset)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except NodeKindConflict as conflict:
        # Before the ``ValueError`` arm: ``NodeKindConflict`` is one, and this
        # refusal is a conflict, not a malformed publish.
        _audit_refused_catalog_mutation(
            event_type="dataset.publish",
            actor=actor_id,
            dataset_id=dataset_id,
            decision=decision,
            reason=str(conflict),
        )
        raise HTTPException(status_code=409, detail=str(conflict)) from conflict
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"status": "published", "dataset": catalog.mutation_response_view(dataset)}


@app.patch("/catalog/datasets/{dataset_id}")
def patch_catalog_dataset(dataset_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    actor_id = _actor(payload)
    decision = evaluate(subject=actor_id, resource=dataset_id, action="patch", purpose="catalog")
    if decision.effect != "allow":
        _audit_refused_catalog_mutation(
            event_type="dataset.patch",
            actor=actor_id,
            dataset_id=dataset_id,
            decision=decision,
        )
        # Foreign and absent both answered 403 here, but with different reasons -
        # "tenant boundary denied" versus "존재하지 않는 데이터셋입니다." - so the
        # reason string carried the oracle even though the status matched. A
        # caller that cannot reach the dataset's tenant gets one answer; an
        # in-scope refusal (role, sensitivity, purpose) keeps its reason.
        if catalog.dataset_in_scope(dataset_id, accessible_tenant_ids(actor_id)) is None:
            raise HTTPException(status_code=404, detail="dataset not found")
        raise HTTPException(status_code=403, detail=decision.reason)

    try:
        request = DatasetPatchRequest(**payload)
        # Before the mutation, for the reason the create route gives: a declared
        # column whose node id a concept already holds made this route answer
        # **400 "request body is not valid"** *after* the catalog had applied
        # both the title and the schema change, so the caller was told the
        # request was rejected while it was kept. A conflict is now 409 and
        # nothing is written.
        # Unconditional, not ``if request.schema is not None``: the dataset's
        # *own* node is rewritten by every mirror, so a patch declaring no
        # schema at all still had to reclassify a colliding node - and answered
        # 400 with the title change kept (measured). The columns are only the
        # second half of what the mirror writes.
        assert_dataset_mirror_kinds_are_available(
            dataset_id,
            [column.name for column in request.schema] if request.schema is not None else [],
        )
        # Mutation and mirror in one critical section; see the create route.
        with catalog.catalog_mutation_lock():
            dataset = patch_dataset(
                dataset_id,
                request,
                actor=actor_id,
                decision_id=decision.decision_id,
                change_reason=_change_reason(payload),
            )
            seed_dataset(dataset)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except NodeKindConflict as conflict:
        # Before the blanket arm, so a kind conflict is not reported as a
        # malformed body - and catching the *precise* type rather than
        # ``ValueError``, because ``pydantic.ValidationError`` is a ``ValueError``
        # too: with a bare ``ValueError`` arm here a non-numeric
        # ``quality_score`` answered 409 instead of 400 (measured).
        _audit_refused_catalog_mutation(
            event_type="dataset.patch",
            actor=actor_id,
            dataset_id=dataset_id,
            decision=decision,
            reason=str(conflict),
        )
        raise HTTPException(status_code=409, detail=str(conflict)) from conflict
    except Exception as exc:
        raise HTTPException(status_code=400, detail=_invalid_request_detail(exc))
    return {"status": "updated", "dataset": catalog.mutation_response_view(dataset)}


@app.post("/catalog/datasets/{dataset_id}/deprecate")
def deprecate_catalog_dataset(dataset_id: str, payload: dict[str, str] | None = None) -> dict[str, Any]:
    actor_id = _actor(payload)
    decision = evaluate(subject=actor_id, resource=dataset_id, action="deprecate", purpose="catalog")
    if decision.effect != "allow":
        _audit_refused_catalog_mutation(
            event_type="dataset.deprecate",
            actor=actor_id,
            dataset_id=dataset_id,
            decision=decision,
        )
        # Foreign and absent both answered 403 here, but with different reasons -
        # "tenant boundary denied" versus "존재하지 않는 데이터셋입니다." - so the
        # reason string carried the oracle even though the status matched. A
        # caller that cannot reach the dataset's tenant gets one answer; an
        # in-scope refusal (role, sensitivity, purpose) keeps its reason.
        if catalog.dataset_in_scope(dataset_id, accessible_tenant_ids(actor_id)) is None:
            raise HTTPException(status_code=404, detail="dataset not found")
        raise HTTPException(status_code=403, detail=decision.reason)

    payload = payload or {}
    try:
        # Before the status change; see the publish route.
        _assert_mirror_kinds_for_existing_dataset(dataset_id)
        # Mutation and mirror in one critical section; see the create route.
        with catalog.catalog_mutation_lock():
            dataset = deprecate_dataset(
                dataset_id,
                actor=actor_id,
                # ``payload.get("reason", "deprecated")`` before this, which
                # turned "the caller gave no reason" into the literal reason
                # "deprecated" - a reason the caller never gave, recorded as
                # though they had. The other three verbs report ``None``, and a
                # fabricated default is the one answer this surface must not
                # give.
                reason=_change_reason(payload),
                decision_id=decision.decision_id,
            )
            seed_dataset(dataset)
        return {"status": "deprecated", "dataset": catalog.mutation_response_view(dataset)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except NodeKindConflict as conflict:
        _audit_refused_catalog_mutation(
            event_type="dataset.deprecate",
            actor=actor_id,
            dataset_id=dataset_id,
            decision=decision,
            reason=str(conflict),
        )
        raise HTTPException(status_code=409, detail=str(conflict)) from conflict


def _authorize_evidence_read(user: str) -> tuple[Any, list[str] | None]:
    """Authorize an evidence-ledger read and resolve the tenants it may cover.

    The ledger is the product's auditability claim, so a read is gated like any
    other governed read and then scoped: ``policy.accessible_tenant_ids`` returns
    ``None`` only for the explicit platform-admin crossing. Without the scope the
    tenant stamp on every row would be decorative - one unauthenticated call used
    to return every tenant's rows.
    """
    decision = evaluate(subject=user, resource="evidence", action="search", purpose="audit")
    if decision.effect != "allow":
        raise HTTPException(status_code=403, detail=decision.reason)
    return decision, accessible_tenant_ids(user)


@app.get("/audit/events")
def list_events(
    limit: int = Query(default=100, ge=1, le=500),
    resource: str | None = Query(default=None),
    user: str = Query(default="anonymous"),
) -> list[dict[str, Any]]:
    _, tenant_ids = _authorize_evidence_read(user)
    return [
        event.model_dump()
        for event in list_audit_events(limit=limit, resource=resource, tenant_ids=tenant_ids)
    ]


# Resources this application evaluates policy against that are not datasets.
# `POST /policy/decision` takes the resource from the caller, so anything outside
# this set and not an in-scope dataset is treated as a probe rather than a
# question, and gets one refusal regardless of whether the id happens to exist.
NON_DATASET_POLICY_RESOURCES = frozenset({"catalog", "evidence", "graph"})


@app.post("/policy/decision")
def policy_decision(payload: dict[str, str]) -> dict[str, Any]:
    """Evaluate one policy question for an authorized caller.

    This route was open, and it answered more than the routes this series spent
    four commits closing. Measured with **no authentication at all**:

        {"resource": "zeta-secret",      ...} -> reason "tenant boundary denied"
                                                 obligations.tenant_id "zeta-bank"
        {"resource": "no-such-dataset",  ...} -> reason "존재하지 않는 데이터셋입니다."
                                                 obligations.tenant_id "unresolved"

    So an unauthenticated caller could enumerate dataset ids, learn which exist
    from the differing reason, **and read the owning tenant out of the
    obligations**. Closing the catalog, browse, llm and graph families left this
    as an open side channel exposing the same facts plus tenant ownership,
    because the sweep enumerated routes that *resolve* a dataset and this one
    merely answers questions *about* one.

    It also wrote to the ledger. ``evaluate()`` records every decision, so 50
    unauthenticated calls produced 50 rows in the evidence log an auditor reads -
    while the sibling ``GET /policy/decisions`` already refused an actor-less
    *read* with 403. You could not read the ledger without an actor but could
    write to it without one.

    Both halves close the same way: the same gate as the sibling read, plus the
    tenant scope every other dataset-resolving route now applies. ``subject``
    stays caller-supplied because a governance "what would policy say for this
    subject" is this route's purpose; it defaults to the caller.
    """
    caller = payload.get("user") or payload.get("subject") or "anonymous"
    # Same gate as GET /policy/decisions.
    _, tenant_ids = _authorize_evidence_read(caller)

    resource = payload.get("resource", "")
    # One answer for "not yours" and "not a dataset". Scoping only the datasets
    # that exist left the oracle intact for an authorized caller: a foreign
    # dataset answered 404 while a nonexistent id answered 200 with the engine's
    # "존재하지 않는 데이터셋입니다.", so the pair still revealed which ids are
    # real. The app's own non-dataset resources are named, so anything else that
    # is not an in-scope dataset gets the single refusal.
    if (
        resource
        and resource not in NON_DATASET_POLICY_RESOURCES
        and not resource.startswith("ontology/")
        and catalog.dataset_in_scope(resource, tenant_ids) is None
    ):
        raise HTTPException(status_code=404, detail="dataset not found")

    # The answer is hypothetical - that is this route's purpose - and the row it
    # records was indistinguishable from a real refused access attempt by the
    # named subject, with no record of who asked. See ``policy.evaluate``'s
    # ``provenance`` parameter for the measurement.
    subject = payload.get("subject", caller)
    decision = evaluate(
        subject=subject,
        resource=resource,
        action=payload.get("action", "preview"),
        purpose=payload.get("purpose", "analysis"),
        provenance={
            "evaluation_mode": "hypothetical",
            # Who actually asked, which the row lost entirely when ``subject``
            # named someone else.
            "asked_by": caller,
            "subject_is_caller": subject == caller,
        },
    )
    return decision.model_dump()


@app.get("/policy/decisions")
def policy_decisions(
    limit: int = Query(default=100, ge=1, le=500),
    resource: str | None = Query(default=None),
    user: str = Query(default="anonymous"),
) -> list[dict[str, Any]]:
    _, tenant_ids = _authorize_evidence_read(user)
    return [
        decision.model_dump()
        for decision in list_policy_decisions(resource=resource, limit=limit, tenant_ids=tenant_ids)
    ]


def _ontology_version_stamp(pinned: str | None) -> dict[str, Any]:
    """The version this answer came from, refusing a pin that names another one.

    ``ontology_version_pin`` was published as an ``implemented`` connector
    control whose proof endpoints are this route and ``/ontology/search`` -
    measured, neither response contained the string "version" anywhere, so the
    control's own proof routes evidenced nothing about it while ``ONT-004`` was
    recorded ``not_implemented`` for exactly that reason.

    Both refusals are distinct because they mean different things. A malformed
    digest is a bad request (400); a well-formed digest naming a different
    vocabulary is a conflict (409). Collapsing them would tell a client with a
    typo that the server holds a different vocabulary, and a client holding a
    genuinely older vocabulary that its request was malformed.
    """
    try:
        verdict = ontology_version.version_pin_verdict(
            pinned, ontology.concept_vocabulary_snapshot()
        )
    except ValueError as malformed:
        raise HTTPException(status_code=400, detail=str(malformed)) from malformed
    if not verdict["pin_matches"]:
        raise HTTPException(
            status_code=409,
            detail=(
                f"고정한 온톨로지 버전이 현재 버전과 다릅니다 "
                f"(requested={verdict['requested_content_digest']}, "
                f"live={verdict['live_content_digest']})"
            ),
        )
    stamp = ontology.ontology_version_identity()
    return {
        "ontology_revision": stamp["ontology_revision"],
        "content_digest": stamp["content_digest"],
        "digest_algorithm": stamp["digest_algorithm"],
        "revision_is_durable": stamp["revision_is_durable"],
        "pin_basis": verdict["pin_basis"],
        "revision_is_pinnable": verdict["revision_is_pinnable"],
        "pin_requested": verdict["pin_requested"],
    }


@app.post("/ontology/resolve")
def resolve_terms(payload: dict[str, str]) -> dict[str, Any]:
    text = payload.get("text", "")
    if not text:
        raise HTTPException(status_code=400, detail="question text required")
    # Stamped **and** pinnable: a caller may send the vocabulary digest it
    # compiled against and be refused rather than silently resolved against a
    # different vocabulary.
    version = _ontology_version_stamp(payload.get(ontology_version.PIN_PARAMETER))
    resolutions = ontology.resolve_terms(text)
    return {
        "query": text,
        "resolved": [
            {
                "term": item.term,
                "score": item.score,
                "uri": item.uri,
                "aliases": item.aliases,
                # A term IRI for a concept the glossary does not define looks
                # exactly like one it does. See ``ontology.Resolution``.
                "defined_in_vocabulary": item.defined_in_vocabulary,
            }
            for item in resolutions
        ],
        "undefined_resolution_count": sum(
            1 for item in resolutions if not item.defined_in_vocabulary
        ),
        "ontology_version": version,
    }


@app.get("/ontology/concept/{concept}")
def concept_detail(
    concept: str, user: str = Query(default="anonymous")
) -> dict[str, Any]:
    """Describe one concept, with its dataset mapping scoped to the caller.

    ``concept_assets`` was given a tenant scope and wired into ``/llm/search``.
    This is its other caller and it was left unscoped, so the same payload the
    other route withholds was served here to **no actor at all**: measured,
    ``dataset_ids`` listed every tenant's datasets with
    ``withheld_dataset_count: 0``, while ``/llm/search`` withheld two for the
    same caller. Scoping the helper fixed one of its two callers.
    """
    return ontology.concept_assets(concept, accessible_tenant_ids(user))


@app.get("/ontology/concepts")
def ontology_concepts() -> dict[str, Any]:
    return {"count": len(ontology.list_concepts()), "concepts": ontology.list_concepts()}


@app.get("/ontology/version")
def ontology_version_identity_route() -> dict[str, Any]:
    """The live ontology version. Open, and carries no actor identity.

    Open for the same reason ``GET /ontology/concepts`` is: the vocabulary is
    shared, not tenant-scoped, and a client that cannot read the version it is
    resolving against cannot pin it. Identity - who published or reviewed each
    change - is not here; it is in the change log, which is a governed read.
    """
    return ontology.ontology_version_identity()


@app.get("/ontology/change-log")
def ontology_change_log(
    user: str = Query(default="anonymous"),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, Any]:
    """The ontology change log: what changed, who published it, who reviewed it.

    Governed, not open. Every entry is field-for-field an access record -
    ``{actor_id, reviewer_id, change_kind, recorded_at}`` - and both existing
    read surfaces for that shape, ``/audit/events`` and ``/policy/decisions``,
    are gated. The counts are published openly on ``/ontology/version``; the
    identity is not.

    (``GET /ontology/patches`` served ``requestor``, ``reviewed_by``,
    ``reviewed_at`` and ``review_comment`` to an anonymous caller when this
    route was added, and that disagreement was recorded here rather than used as
    precedent for a second open identity surface. It is closed: that route now
    runs this same gate, and ``/enterprise/steward-review`` withholds the
    proposer rather than republishing it.)
    """
    # The same gate as ``/audit/events`` and ``/policy/decisions``, through the
    # same helper, because this is the same kind of record. Its tenant list is
    # deliberately not applied: the concept vocabulary is shared rather than
    # tenant-owned (``GET /ontology/concepts`` is open to anyone), so there is
    # no tenant predicate to scope a vocabulary change by, and inventing one
    # would hide a shared change from a reader entitled to it. The scope that
    # does apply is authorization, and an unauthorized caller is refused.
    decision, _ = _authorize_evidence_read(user)
    return {
        **ontology.vocabulary_change_log(limit=limit),
        "scope_note": (
            "온톨로지 어휘는 테넌트 소유가 아니라 공유 자원이므로 이 원장에는 "
            "테넌트 범위가 적용되지 않는다. 적용되는 범위는 권한 뿐이다."
        ),
        "policy_decision_id": decision.decision_id,
    }


@app.get("/ontology/vocabulary/jsonld")
def ontology_vocabulary_jsonld() -> dict[str, Any]:
    """The vocabulary as versioned SKOS/RDFS JSON-LD.

    ONT-004's subject is an "OWL/RDFS 기반" ontology and there was no RDF
    artifact at all: the DCAT export covers datasets, and its
    ``mappings[].concept`` is a plain literal, so no triple anywhere named a
    concept. This is the artifact the revision versions.

    Open, and it **derives** no dataset identity. ``ontology._INDEX`` is built
    with no tenant predicate, and serving it is exactly how ``concept_assets``
    leaked every tenant's dataset ids to a caller its own policy decision
    denied; the concept-to-dataset mapping stays on the governed
    ``GET /ontology/concept/{term}``. The document says so in
    ``sdp:datasetMappingIsVersioned false``.

    That guarantee is about derivation and is narrower than "no dataset id can
    appear in this document". A concept named after a dataset that **exists** is
    refused 409 by the graph store, which will not change a node's kind - that
    is what used to destroy the dataset's label and governed properties. A
    dataset-id-shaped name that collides with nothing is still accepted, because
    ``kind`` is free-form and no class check guards concept registration
    (ONT-002's recorded gap), and it reaches the document as a label and an
    ``@id`` like any other - carrying no mapping, distribution or dataset
    structure with it. Both halves are pinned by
    ``test_the_export_never_derives_dataset_identity``.
    """
    return ontology.vocabulary_jsonld()


@app.get("/ontology/search")
def ontology_search(
    q: str = Query(..., min_length=1),
    ontology_content_digest: str | None = Query(default=None),
) -> dict[str, Any]:
    """Search the vocabulary, stamped with the version that answered.

    See :func:`_ontology_version_stamp` for why the pin is matched on the
    content digest and never on the revision.
    """
    version = _ontology_version_stamp(ontology_content_digest)
    matches = ontology.search_concepts(q)
    return {
        "query": q,
        "count": len(matches),
        "matches": [item.__dict__ for item in matches],
        "ontology_version": version,
    }


@app.get("/ontology/patches")
def ontology_patches(
    status: str | None = Query(default=None),
    user: str = Query(default="anonymous"),
) -> dict[str, Any]:
    """The steward review queue. Governed, because every row names actors.

    This route ran **no** authorization at all. Measured, with no actor supplied
    and with two unknown ones::

        GET /ontology/patches                  200  requestor=analyst
                                                    reviewed_by=admin
                                                    reviewed_at=2026-...
                                                    review_comment='스튜어드 승인 사유'
        GET /ontology/patches?user=anonymous   200  (the same four fields)
        GET /ontology/patches?user=nobody      200  (the same four fields)

    at the same moment as, for the same identities::

        GET /ontology/change-log               403
        GET /audit/events                      403
        GET /policy/decisions                  403

    So the platform published who proposed a vocabulary change, who signed it off
    and the reviewer's own comment to an unauthenticated caller, while refusing
    the same facts on the three surfaces built to carry them. ONT-004 gated the
    change log on the argument that ``{actor_id, reviewer_id, recorded_at}`` *is*
    an access record; this route serves that record plus the review comment, so
    the argument applies unchanged and the two surfaces no longer disagree.

    The gate is ``_authorize_evidence_read`` - the same helper, not a parallel
    rule - and its tenant list is deliberately not applied, for the reason the
    change log states: the concept vocabulary is shared rather than tenant-owned,
    so there is no tenant predicate to scope a proposal by. The scope that does
    apply is authorization.

    Authorization runs **before** the status-filter validation, matching
    ``ontology_patch_review``: an unauthorized caller must not learn the payload
    rules. ``?status=nope`` therefore answers 403 without an actor and 400 with
    one, and both are declared in ``api_error_contract``.

    The companion half is ``steward_review.build_steward_review_summary``, which
    republished ``requestor`` on the open ``/enterprise/steward-review``. Gating
    only this route would have been theatre: the identity was reachable either
    way. That surface now withholds the field and declares the withholding.
    """
    # The gate first, then the payload rules. A refusal here writes exactly one
    # decision row, which is the same shape every other governed read produces -
    # and no GET on this app answers 200 while writing a ledger row, so the
    # alternative (evaluate, then serve a redacted 200) would have made this the
    # only read in the product that bills the ledger for an anonymous success.
    decision, _ = _authorize_evidence_read(user)
    # An unknown or wrongly-cased filter matched nothing and returned
    # `count: 0`, so `?status=PROPOSED` and `?status=not-a-status` both reported
    # an empty steward queue - indistinguishable from a genuinely empty one. A
    # reviewer reading that concludes there is nothing to review.
    if status is not None and status not in ontology.PATCH_STATUSES:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "unknown_status_filter",
                "requested": status,
                "known_statuses": sorted(ontology.PATCH_STATUSES),
            },
        )
    patches = ontology.list_patches(status=status)
    return {
        "count": len(patches),
        "patches": patches,
        "scope_note": (
            "제안 큐의 각 행은 제안자/승인자 신원을 담으므로 이 읽기는 "
            "거버닝 읽기다. 온톨로지 어휘는 테넌트 소유가 아니라 공유 자원이므로 "
            "테넌트 범위는 적용되지 않고, 적용되는 범위는 권한 뿐이다."
        ),
        "policy_decision_id": decision.decision_id,
    }


@app.post("/ontology/patches")
def ontology_patch_create(payload: dict[str, str]) -> dict[str, Any]:
    concept = payload.get("concept", "").strip()
    suggestion = payload.get("suggestion", "").strip()
    if not concept or not suggestion:
        raise HTTPException(status_code=400, detail="concept and suggestion are required")
    # A proposal writes to a shared, process-lifetime queue, so it is a governed
    # write rather than an open endpoint: it ran no policy evaluation at all.
    actor_id = _actor(payload)
    decision = evaluate(
        subject=actor_id, resource="ontology/patches", action="search", purpose="ontology"
    )
    if decision.effect != "allow":
        _audit_governed_write(
            event_type="ontology.patch_propose",
            actor=actor_id,
            resource="ontology/patches",
            decision=decision,
            result="denied",
        )
        raise HTTPException(status_code=403, detail=decision.reason)
    # The audit row is written **after** the proposal, carrying what actually
    # happened. It used to be written before, saying ``allowed``, while
    # ``propose_patch`` can still refuse (field bounds, a full queue) and answer
    # 400 - so the ledger claimed an accepted proposal that does not exist.
    # Authorization alone is audited above, on denial; an authorized attempt
    # leaves exactly one row, and that row states its outcome.
    try:
        proposed = ontology.propose_patch(
            concept=concept,
            suggestion=suggestion,
            requestor=actor_id,
        )
    except ValueError as exc:
        _audit_governed_write(
            event_type="ontology.patch_propose",
            actor=actor_id,
            resource="ontology/patches",
            decision=decision,
            result="rejected",
        )
        raise HTTPException(status_code=400, detail=str(exc))
    _audit_governed_write(
        event_type="ontology.patch_propose",
        actor=actor_id,
        resource="ontology/patches",
        decision=decision,
        result="proposed",
    )
    return proposed


@app.post("/ontology/patches/{patch_id}/review")
def ontology_patch_review(patch_id: str, payload: dict[str, str]) -> dict[str, Any]:
    # A steward sign-off is a governance mutation, so it carries the same admin
    # authorization as POST /ontology/concepts rather than none at all.
    actor_id = _actor(payload)
    # Authorization first: an unauthorized caller must not learn the payload rules.
    # ``audit_allow=False`` because this route writes its own outcome row below,
    # carrying the review's real result; both rows produced a double-counted
    # review (decisions +2, audits +2 for one approval). The decision returned
    # here is reused rather than a second one being evaluated.
    decision = _authorize_graph_write(
        actor_id,
        f"ontology/patches/{patch_id}",
        event_type="ontology.patch_review",
        audit_allow=False,
    )
    if "reviewer" in payload:
        # The reviewer is the authorized actor. A caller-chosen name would produce
        # a record naming a steward who never saw the patch, so the field is
        # refused outright rather than silently ignored.
        raise HTTPException(
            status_code=400,
            detail="reviewer is derived from the authorized actor and must not be sent in the request body",
        )
    try:
        reviewed = ontology.review_patch(
            patch_id=patch_id,
            decision=payload.get("decision", ""),
            reviewer=actor_id,
            comment=payload.get("comment", ""),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ontology.ConceptKindConflict as conflict:
        # The same conflict the upsert route answers 409 for; it reached here as
        # a plain 400 until the publication paths were made to agree.
        catalog.ingest_event(
            event_type="ontology.patch_review",
            actor=actor_id,
            dataset_id=f"ontology/patches/{patch_id}",
            decision="refused",
            reason=str(conflict),
            decision_id=decision.decision_id,
            details={
                "policy_decision_id": decision.decision_id,
                "tenant_id": decision.obligations.get("tenant_id"),
            },
        )
        raise HTTPException(status_code=409, detail=str(conflict)) from conflict
    except ValueError as exc:
        # The refusal is audited with its real outcome. Without this the ledger
        # held one policy decision reading ``allow`` and **zero** audit rows for
        # a refused approval - measured - so an auditor saw an admin permitted
        # to publish and no record that the publication was refused.
        catalog.ingest_event(
            event_type="ontology.patch_review",
            actor=actor_id,
            dataset_id=f"ontology/patches/{patch_id}",
            decision="refused",
            reason=str(exc),
            decision_id=decision.decision_id,
            details={
                "policy_decision_id": decision.decision_id,
                "tenant_id": decision.obligations.get("tenant_id"),
            },
        )
        raise HTTPException(status_code=400, detail=str(exc))
    catalog.ingest_event(
        event_type="ontology.patch_review",
        actor=actor_id,
        dataset_id=f"ontology/patches/{patch_id}",
        # An approval of a patch whose concept is already published writes the
        # status but publishes nothing - the registrar returns the stored record
        # so an approval cannot rewrite a shipped definition. Recorded as
        # ``approved`` alone that reads as a publication, so the outcome says
        # which it was.
        decision=(
            "approved_without_publication"
            if reviewed.get("concept_already_published") is True
            else reviewed.get("status", "reviewed")
        ),
        reason=payload.get("comment", ""),
        decision_id=decision.decision_id,
        details={
            "concept": reviewed.get("concept"),
            "policy_decision_id": decision.decision_id,
            "tenant_id": decision.obligations.get("tenant_id"),
        },
    )
    return {**reviewed, "policy_decision_id": decision.decision_id}


@app.get("/ontology/term/{term}/graph")
def ontology_term_graph(
    term: str, user: str = Query(default="anonymous")
) -> dict[str, Any]:
    """Describe one concept's graph, with its dataset mapping scoped to the caller.

    This took **no actor at all** and served every tenant's dataset ids, while
    its two siblings serving the same fact withheld them. See
    ``policy.scope_concept_graph`` for the measurement; the concept vocabulary
    itself is shared and stays open, it is dataset identity that is scoped.
    """
    # Backed by the persistent graph store now; falls back to the legacy
    # in-memory ontology module when the concept is not in the store.
    graph = get_store().concept_graph(term)
    if graph.get("not_found"):
        # The legacy payload carries no ``dataset_ids``; scope it anyway so a
        # future field added there cannot bypass the boundary.
        return scope_concept_graph(user, ontology.concept_graph(term))
    return scope_concept_graph(user, graph)


# --- Graph ingestion (nodes / edges / concepts) ------------------------------


def _audit_governed_write(
    *, event_type: str, actor: str, resource: str, decision: Any, result: str
) -> None:
    """Record the audit half of a governed write.

    The graph and ontology mutation routes evaluated policy and recorded the
    decision, but **no audit event** - on denial or on success. Measured:
    ``POST /ontology/concepts`` and ``POST /graph/edges`` each produced
    ``decisions +1  audits +0``, so a concept or edge overwrite was
    unattributable in the ledger an auditor reads, while the structurally
    identical catalog mutations wrote both halves. The repository's stated
    invariant is policy evaluation *and* evidence recording.

    ``details['tenant_id']`` is copied from the decision. The evidence stores
    read an audit row's tenant from that key and fall back to the literal
    ``'unresolved'``; these rows carried no tenant at all (measured:
    ``tenant=None`` on every ``ontology.patch_review`` row), so a tenant-scoped
    auditor could not see its own governance writes while the decision half of
    the very same event was correctly scoped. The two halves now agree.
    """
    catalog.ingest_event(
        event_type=event_type,
        actor=actor,
        dataset_id=resource,
        decision=result,
        decision_id=decision.decision_id,
        reason=decision.reason,
        details={
            "policy_decision_id": decision.decision_id,
            "resource": resource,
            "tenant_id": decision.obligations.get("tenant_id"),
        },
    )


def _authorize_graph_write(
    actor: str,
    resource: str,
    *,
    event_type: str = "graph.write",
    audit_allow: bool = True,
    also_touches: tuple[str, ...] = (),
) -> Any:
    """Graph/ontology writes require an authorized (admin) subject.

    Uses the same policy engine as the catalog mutation endpoints: the ``create``
    action is allowed only for an admin subject, so unauthenticated/anonymous
    writers are refused with 403. A denial is always audited here, so a new
    governed write cannot forget the evidence half of a refusal.

    The allow row says ``"authorized"``, not ``"allowed"``. It is written before
    the mutation runs and therefore cannot attest that the write happened: a
    request can be authorized here and then refused by validation (400) or by a
    full vocabulary (409), and a row reading ``allowed`` claims a completed
    governed write that never occurred.

    ``audit_allow=False`` is for a route that writes its own outcome row. With
    both, one review produced ``decisions +2  audits +2`` - two rows with the
    same ``action`` and *different* ``decision_id`` values, one saying
    ``allowed`` and one saying ``approved``, with nothing linking them, so an
    auditor counting reviews counted each one twice.
    """

    # The owning tenant of the node being written. ``create`` is the one policy
    # branch that cannot resolve this from the catalog - the asset may not exist
    # yet - so it takes the target from the caller, and this function never
    # supplied it. The result was a tenant boundary that held on reads and
    # failed open on writes; see ``policy.graph_node_target_tenant``.
    decision = evaluate(
        subject=actor,
        resource=resource,
        action="create",
        purpose="graph",
        target_tenant_id=graph_node_target_tenant(resource),
    )
    # An edge touches two nodes. Checking only its source let an authorized
    # writer attach an edge to a foreign tenant's node, which the read side then
    # withholds - so the edge would exist, unreadable by the tenant whose graph
    # it altered. Every endpoint is checked, with the same refusal and the same
    # audit row.
    if decision.effect == "allow":
        for touched in also_touches:
            if not can_see_graph_node(actor, touched):
                decision = evaluate(
                    subject=actor,
                    resource=touched,
                    action="create",
                    purpose="graph",
                    target_tenant_id=graph_node_target_tenant(touched),
                )
                break
    if decision.effect != "allow":
        _audit_governed_write(
            event_type=event_type,
            actor=actor,
            resource=resource,
            decision=decision,
            result="denied",
        )
        raise HTTPException(status_code=403, detail=decision.reason)
    if audit_allow:
        _audit_governed_write(
            event_type=event_type,
            actor=actor,
            resource=resource,
            decision=decision,
            result="authorized",
        )
    return decision


def _authorize_graph_read(actor: str, resource: str) -> None:
    """Graph traversal / semantic search require an authenticated reader.

    Uses the catalog discovery policy branch (``search``): allowed for any reader
    role, denied for anonymous/unauthenticated subjects. That branch returns before
    the policy engine's tenant check, so it establishes authentication only - the
    tenant boundary is enforced per node by ``policy.can_see_graph_node`` on
    everything these routes release.
    """

    decision = evaluate(subject=actor, resource=resource, action="search", purpose="graph")
    if decision.effect != "allow":
        raise HTTPException(status_code=403, detail=decision.reason)


def _authorize_graph_node_read(actor: str, node_id: str) -> None:
    """Require an authorized reader who may also see this particular node.

    404, not 403, when the node belongs to a dataset outside the caller's tenant.
    This route answered 403 for a foreign node and 404 for one that does not
    exist, which is the same existence oracle the browse, catalog and llm
    families were repaired to close - and it became reachable for onboarded
    datasets the moment catalog mutations started mirroring into the graph, so it
    is closed in the same change rather than left for a later sweep. Node ids are
    derived from dataset ids (``<dataset_id>`` and ``<dataset_id>:<column>``), so
    they are exactly as enumerable.
    """
    _authorize_graph_read(actor, node_id)
    if not can_see_graph_node(actor, node_id):
        raise HTTPException(status_code=404, detail="node not found")


def _audit_refused_concept_upsert(
    actor: str, concept: str, decision: Any, reason: str
) -> None:
    """Record that an authorized concept publication was refused.

    The generic gate writes ``authorized`` before the mutation, so a refusal
    left the ledger holding one row that reads as a permitted publication and
    nothing saying it did not happen - measured on both refusal paths. An
    auditor looking for refused attempts on a governed write is exactly who
    found nothing, which is the same defect the catalog mutation routes were
    fixed for.
    """
    catalog.ingest_event(
        event_type="ontology.concept_upsert",
        actor=actor,
        dataset_id=concept,
        decision="refused",
        reason=reason,
        decision_id=decision.decision_id,
        details={
            "policy_decision_id": decision.decision_id,
            "tenant_id": decision.obligations.get("tenant_id"),
        },
    )


@app.post("/ontology/concepts")
def ingest_concept(payload: OntologyConceptRequest) -> dict[str, Any]:
    # ``audit_allow=False`` because this route writes its own outcome row below.
    # The generic gate's row says ``authorized`` and is written before the
    # mutation, so on a refusal the ledger held one row reading "authorized" and
    # nothing saying the publication did not happen - measured. Same shape as
    # ``POST /ontology/patches``.
    decision = _authorize_graph_write(
        payload.actor,
        payload.concept,
        event_type="ontology.concept_upsert",
        audit_allow=False,
    )
    aliases = list(payload.aliases or [])
    multilingual = list(getattr(payload, "multilingual", None) or [])
    # Validate before the first of the two writes. This route wrote the graph
    # node first and registered the vocabulary second, so an invalid concept
    # left the graph node behind and answered 500 with the ``ValueError``
    # escaping unmapped (measured with ``{"concept": "   "}``). Validation is
    # also where an alias that would hijack another concept is refused.
    try:
        # ``definition`` and the hierarchy fields are passed so the ConceptShape
        # gate runs here, where a violation maps to 400. Validated a second time
        # inside ``register_concept``; the duplication is the existing pattern
        # and is what makes the gate unbypassable by a future caller.
        ontology.validate_concept_registration(
            payload.concept,
            definition=payload.definition or "",
            aliases=aliases,
            multilingual=multilingual,
            broader=getattr(payload, "broader", None),
            narrower=list(getattr(payload, "narrower", None) or []),
            related=list(getattr(payload, "related", None) or []),
        )
    except (ontology.ConceptKindConflict, GraphIntegrityConflict) as conflict:
        # 409, not 400: the request is well-formed and the conflict is with
        # state. Caught before the ValueError arm because it is a subclass.
        # Every conflict here is "what the store already holds forbids what you
        # asked" - the concept's own name (ConceptKindConflict), a declared
        # ``broader``/``narrower`` target that is a data asset (ONT-002), or one
        # that would make the concept broader than itself - so they answer the
        # same status and are audited the same way, and a further integrity rule
        # joins them without a third arm to remember.
        _audit_refused_concept_upsert(payload.actor, payload.concept, decision, str(conflict))
        raise HTTPException(status_code=409, detail=str(conflict)) from conflict
    except ValueError as invalid:
        _audit_refused_concept_upsert(payload.actor, payload.concept, decision, str(invalid))
        raise HTTPException(status_code=400, detail=str(invalid)) from invalid

    # The vocabulary is written **first** and the graph store mirrors it. The
    # order used to be the other way round, and the store write is
    # unconditional, so a refusal from ``register_concept`` (a full vocabulary,
    # or the alias conflict it re-checks inside the lock) answered 409 with the
    # graph node already written - the two stores left disagreeing by the very
    # refusal that was supposed to prevent a write. Validation, including the
    # kind check that used to live in the store, now happens above, before
    # either write.
    try:
        registration = ontology.register_concept(
            payload.concept,
            # A direct upsert, with nobody reviewing it: the change log records
            # ``reviewer_id: null`` and ``review_basis:
            # "direct_admin_upsert"`` rather than naming a steward who never
            # saw this concept.
            change_source="concept_upsert",
            actor_id=payload.actor,
            definition=payload.definition or "",
            aliases=aliases,
            multilingual=multilingual,
            broader=getattr(payload, "broader", None),
            narrower=list(getattr(payload, "narrower", None) or []),
            related=list(getattr(payload, "related", None) or []),
        )
    except ValueError as refused:
        # Reachable without an invalid payload: the vocabulary cap can be full of
        # seeded concepts, which are never evicted.
        _audit_refused_concept_upsert(payload.actor, payload.concept, decision, str(refused))
        raise HTTPException(status_code=409, detail=str(refused)) from refused

    # The graph store mirrors the record the vocabulary published. The
    # definition comes from the vocabulary, not the submission: the registrar
    # keeps the stored one and discards a re-submission, so handing the store
    # the raw payload left the two disagreeing - measured, a re-upsert that
    # omitted ``definition`` left ``GET /ontology/term/{term}/graph``, which
    # reads the store, serving 고객 with ``definition: ''``.
    store_payload = payload.model_dump(exclude={"actor"})
    store_payload["definition"] = registration.get("definition", "")
    record = get_store().upsert_concept(store_payload)

    catalog.ingest_event(
        event_type="ontology.concept_upsert",
        actor=payload.actor,
        dataset_id=payload.concept,
        decision=(
            "upserted"
            if not registration["already_published"]
            else "upserted_without_publication"
        ),
        reason="",
        decision_id=decision.decision_id,
        details={
            "policy_decision_id": decision.decision_id,
            "tenant_id": decision.obligations.get("tenant_id"),
            "concept_already_published": registration["already_published"],
        },
    )
    return {
        "status": "upserted",
        "concept": record,
        "published_concept": registration["concept"],
        "concept_already_published": registration["already_published"],
        "concept_validation": registration["concept_validation"],
    }


@app.post("/graph/nodes")
def ingest_graph_node(payload: GraphNodeRequest) -> dict[str, Any]:
    """Upsert one graph node. A node's kind cannot be changed.

    The tenant half of this boundary was closed earlier - ``_authorize_graph_write``
    resolves the target tenant, so a foreign admin cannot write a node it cannot
    read. The kind half was open: an upsert replaced the stored node outright, so
    a write under an id another kind already held destroyed its label and every
    governed property. See ``GraphStore.assert_node_kind_is_stable``.
    """
    _authorize_graph_write(payload.actor, payload.node_id, event_type="graph.node_upsert")
    try:
        node = get_store().upsert_node(
            payload.node_id,
            payload.kind,
            label=payload.label,
            properties=payload.properties,
            text=payload.text,
        )
    except ValueError as conflict:
        raise HTTPException(status_code=409, detail=str(conflict)) from conflict
    return {"status": "upserted", "node": node.as_dict()}


@app.post("/graph/edges")
def ingest_graph_edge(payload: GraphEdgeRequest) -> dict[str, Any]:
    _authorize_graph_write(
        payload.actor,
        payload.source_id,
        event_type="graph.edge_upsert",
        also_touches=(payload.target_id,),
    )
    try:
        edge = get_store().upsert_edge(
            payload.edge_type,
            payload.source_id,
            payload.target_id,
            properties=payload.properties,
        )
    except GraphIntegrityConflict as conflict:
        # 409, not 400: the request is well-formed and the conflict is with
        # stored state - the named nodes' kinds, or the subsumption relation the
        # stored hierarchy already asserts - which is the same reading that
        # makes a reclassification 409 on ``POST /graph/nodes``. Caught before
        # the ValueError arm because it is a subclass, and the two publication
        # paths for a hierarchy edge therefore answer one status for one rule.
        #
        # No second evidence row: ``_authorize_graph_write`` above has already
        # evaluated the policy and recorded the decision (the *authorization* was
        # granted - this refusal is an integrity refusal, not an authorization
        # one), and the structurally identical kind conflict on
        # ``POST /graph/nodes`` writes no refusal audit either. Deliberate, so
        # the two 409s on this surface do not differ in what they leave behind.
        raise HTTPException(status_code=409, detail=str(conflict)) from conflict
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"status": "upserted", "edge": edge.as_dict()}


@app.get("/graph/nodes/{node_id}")
def get_graph_node(
    node_id: str,
    actor: str = Query(default="anonymous"),
    user: str | None = Query(default=None),
) -> dict[str, Any]:
    # This was the only route in the catalog/browse/ontology/graph surface
    # spelling the caller `actor` as a *query* parameter; 21 others spell it
    # `user`. An integrator using the common spelling got the anonymous default
    # and an unactionable refusal. Both are accepted, `user` wins when supplied,
    # and `actor` stays valid so existing callers keep working.
    _authorize_graph_node_read(user or actor, node_id)
    node = get_store().get_node(node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="node not found")
    return node.as_dict()


# --- Graph traversal + semantic retrieval ------------------------------------


@app.post("/graph/query")
def graph_query(payload: GraphTraversalRequest) -> dict[str, Any]:
    _authorize_graph_node_read(payload.actor, payload.start_id)
    try:
        traversal = get_store().traverse(
            payload.start_id,
            edge_types=payload.edge_types,
            direction=payload.direction,
            max_depth=payload.max_depth,
        )
    except KeyError:
        # str(exc) echoed the requested id - 'node not found: <id>' - while a
        # node withheld for tenant scope answered the bare 'node not found'. Both
        # were 404 and the bodies still distinguished them, so the collapse was
        # cosmetic. One message for both.
        raise HTTPException(status_code=404, detail="node not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return filter_graph_traversal(payload.actor, traversal)


@app.post("/search/semantic")
def semantic_search(payload: SemanticSearchRequest) -> dict[str, Any]:
    _authorize_graph_read(payload.actor, "graph")
    results = get_store().semantic_search(
        payload.query, kind=payload.kind, limit=payload.limit
    )
    visible, withheld = filter_graph_search_results(payload.actor, results)
    return {
        "query": payload.query,
        "count": len(visible),
        "results": visible,
        "withheld_result_count": withheld,
    }


@app.get("/graph/stats")
def graph_stats() -> dict[str, Any]:
    store = get_store()
    return {"backend": store.readiness().get("backend"), "stats": store.stats()}


@app.get("/browse/{dataset_id}/schema")
def browse_schema(dataset_id: str, user: str = Query(default="anonymous"), purpose: str = Query(default="analysis")) -> dict[str, Any]:
    try:
        return browse.schema(dataset_id, user=user, purpose=purpose)
    except KeyError:
        raise HTTPException(status_code=404, detail="dataset not found")
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


def _invalid_request_detail(exc: Exception) -> dict[str, Any]:
    """Project a request-model failure into a field-named client error.

    Four routes constructed a pydantic model inside ``try`` and put ``str(exc)``
    into the 400 body, which embeds internals a client has no business seeing and
    cannot act on. Measured:

        POST /browse/query     {"dataset_ids": []}  -> 400 body contained
          "1 validation error for QueryExecutionRequest", "type=too_short",
          "https://errors.pydantic.dev/2.13/v/too_short"
        POST /catalog/datasets {"actor":"admin","id":"x"} -> "DatasetCreateRequest"
        POST /llm/draft-query  {"user":"admin"}           -> "QueryDraftRequest"

    So the body leaked the internal model class name, the validator code and the
    pydantic version, while still not stating plainly which field was wrong. The
    field path and the human-readable reason are kept; the rest is dropped.
    """
    errors = getattr(exc, "errors", None)
    if not callable(errors):
        # Not a validation failure (e.g. a non-object body). Say so without
        # echoing the exception text.
        return {"error": "invalid_request", "reason": "request body is not valid"}
    fields = []
    for error in errors():
        location = ".".join(str(part) for part in error.get("loc", ()) if part != "body")
        fields.append({"field": location or "<body>", "reason": error.get("msg", "invalid")})
    return {"error": "invalid_request", "fields": fields}


def _payload_str(payload: dict[str, Any], field: str, default: str) -> str:
    """Coerce one string field, refusing a non-string JSON value as a 400.

    ``/browse/{dataset_id}/preview`` is the only route whose body is annotated
    ``dict[str, Any]`` - it has to be, because ``limit``/``offset`` are integers -
    and it read ``user``/``purpose`` straight out of that dict. A non-string value
    flowed into the policy and masking code and raised there, so every one of
    these produced a 500:

        {"user": 123} {"user": null} {"user": ["a"]} {"user": {"x": 1}} {"user": true}

    Sibling routes annotated ``dict[str, str]`` are validated by FastAPI and
    already answered 422; a sweep of every raw-payload POST route found no other
    5xx, so the coercion is applied here rather than everywhere.
    """
    value = payload.get(field, default)
    if value is None:
        return default
    if not isinstance(value, str):
        raise HTTPException(status_code=400, detail=f"{field} must be a string")
    return value


def _pagination_int(payload: dict[str, Any], field: str, default: int) -> int:
    """Coerce one pagination field, refusing a non-numeric JSON value as a 400.

    ``int()`` raises ``TypeError`` for a list, dict or ``None``, which is not in
    the route's ``except`` list, so those bodies produced a 500.
    """
    value = payload.get(field, default)
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise HTTPException(status_code=400, detail=f"{field} must be an integer")
    try:
        return int(value)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail=f"{field} must be an integer")


@app.post("/browse/{dataset_id}/preview")
def browse_preview(dataset_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        if "user" not in payload:
            raise HTTPException(status_code=400, detail="user is required")
        # int() on a JSON array, object or null raises TypeError, which the
        # handlers below do not catch - a 500 for what is plainly a bad request.
        limit = _pagination_int(payload, "limit", 100)
        offset = _pagination_int(payload, "offset", 0)
        return browse.preview(
            dataset_id=dataset_id,
            user=_payload_str(payload, "user", "anonymous"),
            purpose=_payload_str(payload, "purpose", "analysis"),
            limit=min(limit, 100),
            offset=max(offset, 0),
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="dataset not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


@app.post("/llm/search")
def llm_search(payload: dict[str, str]) -> dict[str, Any]:
    query = payload.get("question", "")
    if not query:
        raise HTTPException(status_code=400, detail="question is required")

    user = payload.get("user", "anonymous")
    purpose = payload.get("purpose", "analysis")
    resolved = ontology.resolve_terms(query)
    if not resolved:
        return {
            "question": query,
            "error": "No resolvable ontology term.",
            "user": user,
            "purpose": purpose,
        }
    top = resolved[0]
    decision = evaluate(subject=user, resource="catalog", action="discover", purpose=purpose)
    if decision.effect != "allow":
        # The route evaluated policy, got `deny`, and served the payload anyway
        # with the denial embedded as decoration: a denied anonymous caller
        # received `recommendations.dataset_ids` for every tenant, because the
        # ontology index is built with no tenant predicate. A decision that does
        # not decide anything is not policy-before-data-access.
        raise HTTPException(
            status_code=403,
            detail={
                "policy_scope": "catalog_discovery",
                "policy_decision_id": decision.decision_id,
                "reason": decision.reason,
            },
        )
    return {
        "question": query,
        "mapped_term": top.term,
        "user": user,
        "purpose": purpose,
        "policy_scope": "catalog_discovery",
        "policy": decision.model_dump(),
        "recommendations": ontology.concept_assets(top.term, accessible_tenant_ids(user)),
    }


# Draft-query failure codes mapped to the status an integrator can act on. The
# route answered **200 for every failure**, including authorization denial and an
# unknown dataset, with the cause buried in an `error` key - so a client checking
# `response.ok` read a denial as success.
_DRAFT_QUERY_ERROR_STATUS = {
    "dataset_not_found": 404,
    "policy_denied": 403,
}


@app.post("/llm/draft-query")
def draft_query(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        request = QueryDraftRequest(**payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=_invalid_request_detail(exc))

    drafted = orchestrator.draft_sql(request)
    error = drafted.get("error")
    if error:
        # 400 is the default: every remaining code (invalid_date_window,
        # missing_schema, invalid_columns, invalid_group_by, invalid_row_limit,
        # invalid_timeout) is a malformed request.
        raise HTTPException(
            status_code=_DRAFT_QUERY_ERROR_STATUS.get(error, 400), detail=drafted
        )
    return drafted


@app.post("/browse/query")
def browse_query(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        request = QueryExecutionRequest(**payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=_invalid_request_detail(exc))

    result = orchestrator.execute_query(request)
    if result.status == "REJECTED":
        raise HTTPException(status_code=400, detail={"status": result.status, "warnings": result.warnings})
    if result.status == "DENIED":
        raise HTTPException(status_code=403, detail={"status": result.status, "warnings": result.warnings})

    return result.model_dump()


@app.post("/api/v1/browse/query")
def browse_query_v1(payload: dict[str, Any]) -> dict[str, Any]:
    return browse_query(payload)


# --- Published refusal contract ---------------------------------------------
#
# Attached after every route is registered, from the single table in
# ``sdp.api_error_contract``. Before this, ``GET /openapi.json`` documented an
# error status on **0 of 60** operations, so a buyer generating a client saw
# none of the product's governed refusals in the type system - while the error
# contract itself (KeyError -> 404, ValueError -> 400, PermissionError -> 403)
# was stated in README.md and enforced by the suite.
#
# One table rather than a ``responses=`` argument on 42 decorators, so the
# contract is readable in one place and cannot drift between routes of the same
# family. ``tests/test_api_error_contract.py`` checks it against the statuses
# the source can actually raise, in both directions.
DOCUMENTED_REFUSALS = document_refusals(app)
# Publish the request-body contracts these routes already validate against. The
# runtime parameter stays ``dict[str, Any]`` and the 400 shape is unchanged; see
# ``sdp.api_request_contract`` for why the document was lying about them.
document_request_bodies(app)
# Publish the 200 bodies. Third of the three published contracts, and the last
# place the document said ``Dict[str, Any]`` where the handler returns a known
# shape: a usable 200 schema appeared on **0 of 60** operations. The schemas are
# derived by executing the routes and re-checked against live responses by
# ``tests/test_api_response_contract.py``; nothing about the runtime changes.
# Order matters - ``document_responses`` wraps whatever ``app.openapi`` is now,
# so it must come after the request-body wrapper, not before.
document_responses(app)
