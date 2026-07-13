from __future__ import annotations

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

from . import authz, browse, catalog, connectors, ontology, orchestrator
from .config import get_app_config
from .console import render_enterprise_console
from .graph_models import (
    GraphEdgeRequest,
    GraphNodeRequest,
    GraphTraversalRequest,
    OntologyConceptRequest,
    SemanticSearchRequest,
)
from .graph_store import get_store
from .seed import seed_store
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
    search_catalog,
    validate_metadata,
)
from .domain import (
    DatasetCreateRequest,
    DatasetPatchRequest,
    QueryDraftRequest,
    QueryExecutionRequest,
)
from .enterprise_evidence import build_enterprise_evidence_pack
from .evidence import list_policy_decisions
from .observability import (
    build_observability_manifest,
    build_request_observation,
    prometheus_metrics_text,
    record_request_observation,
    request_id_from_headers,
    request_id_header,
)
from .policy import evaluate
from .semantic_validation import enterprise_shacl_validation_summary, validate_dataset_semantics
from .steward_review import build_steward_review_summary


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
        )
        record_request_observation(observation)
        if response is not None:
            response.headers[request_id_header()] = request_id


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
    return enterprise_rbac_matrix().model_dump()


@app.get("/enterprise/observability")
def enterprise_observability() -> dict[str, Any]:
    return build_observability_manifest()


@app.get("/enterprise/production-readiness")
def enterprise_production_readiness() -> dict[str, Any]:
    return enterprise_production_readiness_manifest().model_dump()


@app.get("/enterprise/evidence-pack")
def enterprise_evidence_pack() -> dict[str, Any]:
    return build_enterprise_evidence_pack()


@app.get("/enterprise/shacl-validation")
def enterprise_shacl_validation() -> dict[str, Any]:
    return enterprise_shacl_validation_summary()


@app.get("/enterprise/steward-review")
def enterprise_steward_review() -> dict[str, Any]:
    return build_steward_review_summary()


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

    try:
        context = authz.resolve_oidc_actor_context(claims, role_map=role_map)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {
        "mode": "claim_mapping_preview",
        "token_verification": "external_signature_required_claim_shape_validated",
        "actor_context": context.model_dump(),
        "groups": claims.get("groups", []),
        "ignored_role_claims": authz.oidc_role_claims(claims),
    }


@app.post("/enterprise/auth/oidc-verify")
def enterprise_oidc_verify(payload: dict[str, Any]) -> dict[str, Any]:
    token = payload.get("token")
    if not isinstance(token, str) or not token:
        raise HTTPException(status_code=400, detail="token is required")

    jwks = payload.get("jwks")
    if jwks is not None and not isinstance(jwks, dict):
        raise HTTPException(status_code=400, detail="jwks must be an object")

    role_map = payload.get("role_map")
    if role_map is not None and not isinstance(role_map, dict):
        raise HTTPException(status_code=400, detail="role_map must be an object")

    try:
        context, claims = authz.verify_oidc_jwks_token(
            token,
            issuer=payload.get("issuer"),
            audience=payload.get("audience"),
            jwks=jwks,
            role_map=role_map,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {
        "mode": "jwks_signature_verification",
        "token_verification": "jwks_signature_verified",
        "actor_context": context.model_dump(),
        "issuer": claims.get("iss"),
        "audience": claims.get("aud"),
        "groups": claims.get("groups", []),
        "ignored_role_claims": authz.oidc_role_claims(claims),
    }


@app.get("/enterprise/connectors/{connector_id}/probe")
def enterprise_connector_probe(
    connector_id: str,
    dataset_id: str = Query(..., min_length=1),
) -> dict[str, Any]:
    try:
        return connectors.connector_probe(connector_id, dataset_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except KeyError:
        raise HTTPException(status_code=404, detail="dataset not found")


@app.get("/healthz")
def healthz(response: Response) -> dict[str, Any]:
    """Readiness probe verifying graph-engine backend availability.

    Returns 200 when the active store is ready (in-memory always ready; the
    Postgres backend requires AGE + pgvector reachable), 503 otherwise.
    """

    store = get_store()
    readiness = store.readiness()
    payload = {
        "status": "ready" if readiness.get("ready") else "unavailable",
        "config_source": _config.source,
        "store": readiness,
        "stats": store.stats(),
        "at": datetime.utcnow().isoformat() + "Z",
    }
    if not readiness.get("ready"):
        response.status_code = 503
    return payload


@app.get("/catalog/search")
def catalog_search(
    q: str = Query(..., min_length=1),
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
    results = catalog.search_catalog(
        q,
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
            "completeness_badge": "good" if row.dataset.metadata_recommendation_score >= 0.8 else "partial"
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
    q: str | None = Query(default=None),
    field: str = Query(default="domain"),
) -> dict[str, Any]:
    try:
        counts = list_facet_counts(field, query=q)
    except ValueError:
        raise HTTPException(status_code=400, detail="unsupported facet field")
    return {"field": field, "counts": counts}


@app.get("/catalog/datasets")
def list_datasets_endpoint() -> list[dict[str, Any]]:
    return [
        {
            **dataset.model_dump(),
            "metadata_recommendation_score": dataset.metadata_recommendation_score,
            "completeness_badge": "good" if dataset.metadata_recommendation_score >= 0.8 else "partial",
        }
        for dataset in list_datasets()
    ]


@app.get("/catalog/datasets/{dataset_id}")
def dataset_detail(dataset_id: str) -> dict[str, Any]:
    dataset = get_dataset(dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="dataset not found")
    return {
        **dataset.model_dump(),
        "metadata_recommendation_score": dataset.metadata_recommendation_score,
        "completeness_badge": "good" if dataset.metadata_recommendation_score >= 0.8 else "partial",
    }


@app.get("/catalog/datasets/{dataset_id}/jsonld")
def dataset_jsonld(dataset_id: str) -> dict[str, Any]:
    dataset = get_dataset(dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="dataset not found")
    return {
        "@context": "https://www.w3.org/TR/vocab-dcat-3/",
        "@type": "Dataset",
        "id": f"https://semantic-data-portal.local/datasets/{dataset.id}",
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
        "distribution": [d.model_dump() for d in dataset.distributions],
        "mappings": [m.model_dump() for m in dataset.mappings],
    }


@app.get("/catalog/datasets/{dataset_id}/semantic-validation")
def catalog_dataset_semantic_validation(dataset_id: str) -> dict[str, Any]:
    try:
        return validate_dataset_semantics(dataset_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="dataset not found")


@app.get("/catalog/datasets/{dataset_id}/schema-history")
def catalog_dataset_schema_history(dataset_id: str) -> dict[str, Any]:
    return get_dataset_schema_history(dataset_id)


@app.get("/catalog/datasets/{dataset_id}/schema-versions")
def catalog_dataset_schema_versions(dataset_id: str) -> dict[str, Any]:
    return {"dataset_id": dataset_id, "versions": list_dataset_schema_versions(dataset_id)}


@app.get("/catalog/datasets/{dataset_id}/join-candidates")
def catalog_dataset_join_candidates(dataset_id: str, limit: int = Query(default=10, ge=1, le=100)) -> dict[str, Any]:
    return {
        "dataset_id": dataset_id,
        "join_candidates": get_join_candidates(dataset_id, limit=limit),
    }


@app.get("/catalog/datasets/{dataset_id}/profile")
def catalog_dataset_profile(dataset_id: str) -> dict[str, Any]:
    try:
        return get_dataset_profile(dataset_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.get("/catalog/datasets/{dataset_id}/schema-diff")
def catalog_dataset_schema_diff(
    dataset_id: str,
    from_version: str = Query(...),
    to_version: str = Query(...),
) -> dict[str, Any]:
    try:
        return {"dataset_id": dataset_id, "diff": get_dataset_schema_diff(dataset_id, from_version, to_version)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/catalog/datasets/{dataset_id}/validate")
def validate(dataset_id: str) -> dict[str, Any]:
    dataset = get_dataset(dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="dataset not found")
    return validate_metadata(dataset)


@app.get("/catalog/datasets/{dataset_id}/lineage")
def dataset_lineage(dataset_id: str) -> dict[str, Any]:
    try:
        return get_dataset_lineage(dataset_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.get("/catalog/datasets/{dataset_id}/related")
def dataset_related(dataset_id: str) -> dict[str, Any]:
    try:
        return {"dataset_id": dataset_id, "related_datasets": get_related_datasets(dataset_id)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.get("/catalog/datasets/{dataset_id}/audit")
def dataset_audit_events(dataset_id: str, limit: int = Query(default=50, ge=1, le=200)) -> list[dict[str, Any]]:
    return [event.model_dump() for event in get_dataset_audit_events(dataset_id, limit=limit)]


@app.post("/catalog/datasets")
def create_dataset(payload: dict[str, Any]) -> dict[str, Any]:
    actor_id = _actor(payload)
    try:
        request = DatasetCreateRequest(**payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"invalid payload: {exc}")

    decision = evaluate(subject=actor_id, resource=request.id or "new", action="create", purpose="catalog")
    if decision.effect != "allow":
        raise HTTPException(status_code=403, detail=decision.reason)

    dataset = register_dataset(request, actor=actor_id, decision_id=decision.decision_id)
    return {"status": "created", "dataset": dataset.model_dump()}


@app.post("/catalog/datasets/{dataset_id}/publish")
def publish_catalog_dataset(dataset_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    actor_id = _actor(payload)
    decision = evaluate(subject=actor_id, resource=dataset_id, action="publish", purpose="catalog")
    if decision.effect != "allow":
        raise HTTPException(status_code=403, detail=decision.reason)

    try:
        dataset = publish_dataset(dataset_id, actor=actor_id, decision_id=decision.decision_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"status": "published", "dataset": dataset.model_dump()}


@app.patch("/catalog/datasets/{dataset_id}")
def patch_catalog_dataset(dataset_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    actor_id = _actor(payload)
    decision = evaluate(subject=actor_id, resource=dataset_id, action="patch", purpose="catalog")
    if decision.effect != "allow":
        raise HTTPException(status_code=403, detail=decision.reason)

    try:
        request = DatasetPatchRequest(**payload)
        dataset = patch_dataset(dataset_id, request, actor=actor_id, decision_id=decision.decision_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"status": "updated", "dataset": dataset.model_dump()}


@app.post("/catalog/datasets/{dataset_id}/deprecate")
def deprecate_catalog_dataset(dataset_id: str, payload: dict[str, str] | None = None) -> dict[str, Any]:
    actor_id = _actor(payload)
    decision = evaluate(subject=actor_id, resource=dataset_id, action="deprecate", purpose="catalog")
    if decision.effect != "allow":
        raise HTTPException(status_code=403, detail=decision.reason)

    payload = payload or {}
    try:
        dataset = deprecate_dataset(
            dataset_id,
            actor=actor_id,
            reason=payload.get("reason", "deprecated"),
            decision_id=decision.decision_id,
        )
        return {"status": "deprecated", "dataset": dataset.model_dump()}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.get("/audit/events")
def list_events(
    limit: int = Query(default=100, ge=1, le=500),
    resource: str | None = Query(default=None),
) -> list[dict[str, Any]]:
    return [event.model_dump() for event in list_audit_events(limit=limit, resource=resource)]


@app.post("/policy/decision")
def policy_decision(payload: dict[str, str]) -> dict[str, Any]:
    decision = evaluate(
        subject=payload.get("subject", "anonymous"),
        resource=payload.get("resource", ""),
        action=payload.get("action", "preview"),
        purpose=payload.get("purpose", "analysis"),
    )
    return decision.model_dump()


@app.get("/policy/decisions")
def policy_decisions(
    limit: int = Query(default=100, ge=1, le=500),
    resource: str | None = Query(default=None),
) -> list[dict[str, Any]]:
    return [decision.model_dump() for decision in list_policy_decisions(resource=resource, limit=limit)]


@app.post("/ontology/resolve")
def resolve_terms(payload: dict[str, str]) -> dict[str, Any]:
    text = payload.get("text", "")
    if not text:
        raise HTTPException(status_code=400, detail="question text required")
    resolutions = ontology.resolve_terms(text)
    return {
        "query": text,
        "resolved": [
            {"term": item.term, "score": item.score, "uri": item.uri, "aliases": item.aliases}
            for item in resolutions
        ],
    }


@app.get("/ontology/concept/{concept}")
def concept_detail(concept: str) -> dict[str, Any]:
    return ontology.concept_assets(concept)


@app.get("/ontology/concepts")
def ontology_concepts() -> dict[str, Any]:
    return {"count": len(ontology.list_concepts()), "concepts": ontology.list_concepts()}


@app.get("/ontology/search")
def ontology_search(q: str = Query(..., min_length=1)) -> dict[str, Any]:
    matches = ontology.search_concepts(q)
    return {
        "query": q,
        "count": len(matches),
        "matches": [item.__dict__ for item in matches],
    }


@app.get("/ontology/patches")
def ontology_patches(status: str | None = Query(default=None)) -> dict[str, Any]:
    patches = ontology.list_patches(status=status)
    return {"count": len(patches), "patches": patches}


@app.post("/ontology/patches")
def ontology_patch_create(payload: dict[str, str]) -> dict[str, Any]:
    concept = payload.get("concept", "").strip()
    suggestion = payload.get("suggestion", "").strip()
    if not concept or not suggestion:
        raise HTTPException(status_code=400, detail="concept and suggestion are required")
    return ontology.propose_patch(
        concept=concept,
        suggestion=suggestion,
        requestor=payload.get("requestor", "anonymous"),
    )


@app.post("/ontology/patches/{patch_id}/review")
def ontology_patch_review(patch_id: str, payload: dict[str, str]) -> dict[str, Any]:
    try:
        return ontology.review_patch(
            patch_id=patch_id,
            decision=payload.get("decision", ""),
            reviewer=payload.get("reviewer", "anonymous"),
            comment=payload.get("comment", ""),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/ontology/term/{term}/graph")
def ontology_term_graph(term: str) -> dict[str, Any]:
    # Backed by the persistent graph store now; falls back to the legacy
    # in-memory ontology module when the concept is not in the store.
    graph = get_store().concept_graph(term)
    if graph.get("not_found"):
        return ontology.concept_graph(term)
    return graph


# --- Graph ingestion (nodes / edges / concepts) ------------------------------


def _authorize_graph_write(actor: str, resource: str) -> None:
    """Graph/ontology writes require an authorized (admin) subject.

    Uses the same policy engine as the catalog mutation endpoints: the ``create``
    action is allowed only for an admin subject, so unauthenticated/anonymous
    writers are refused with 403.
    """

    decision = evaluate(subject=actor, resource=resource, action="create", purpose="graph")
    if decision.effect != "allow":
        raise HTTPException(status_code=403, detail=decision.reason)


def _authorize_graph_read(actor: str, resource: str) -> None:
    """Graph traversal / semantic search require an authenticated reader.

    Uses the catalog discovery policy branch (``search``): allowed for any reader
    role, denied for anonymous/unauthenticated subjects.
    """

    decision = evaluate(subject=actor, resource=resource, action="search", purpose="graph")
    if decision.effect != "allow":
        raise HTTPException(status_code=403, detail=decision.reason)


@app.post("/ontology/concepts")
def ingest_concept(payload: OntologyConceptRequest) -> dict[str, Any]:
    _authorize_graph_write(payload.actor, payload.concept)
    record = get_store().upsert_concept(payload.model_dump(exclude={"actor"}))
    return {"status": "upserted", "concept": record}


@app.post("/graph/nodes")
def ingest_graph_node(payload: GraphNodeRequest) -> dict[str, Any]:
    _authorize_graph_write(payload.actor, payload.node_id)
    node = get_store().upsert_node(
        payload.node_id,
        payload.kind,
        label=payload.label,
        properties=payload.properties,
        text=payload.text,
    )
    return {"status": "upserted", "node": node.as_dict()}


@app.post("/graph/edges")
def ingest_graph_edge(payload: GraphEdgeRequest) -> dict[str, Any]:
    _authorize_graph_write(payload.actor, payload.source_id)
    try:
        edge = get_store().upsert_edge(
            payload.edge_type,
            payload.source_id,
            payload.target_id,
            properties=payload.properties,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"status": "upserted", "edge": edge.as_dict()}


@app.get("/graph/nodes/{node_id}")
def get_graph_node(node_id: str) -> dict[str, Any]:
    node = get_store().get_node(node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="node not found")
    return node.as_dict()


# --- Graph traversal + semantic retrieval ------------------------------------


@app.post("/graph/query")
def graph_query(payload: GraphTraversalRequest) -> dict[str, Any]:
    _authorize_graph_read(payload.actor, payload.start_id)
    try:
        return get_store().traverse(
            payload.start_id,
            edge_types=payload.edge_types,
            direction=payload.direction,
            max_depth=payload.max_depth,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/search/semantic")
def semantic_search(payload: SemanticSearchRequest) -> dict[str, Any]:
    _authorize_graph_read(payload.actor, "graph")
    results = get_store().semantic_search(
        payload.query, kind=payload.kind, limit=payload.limit
    )
    return {"query": payload.query, "count": len(results), "results": results}


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


@app.post("/browse/{dataset_id}/preview")
def browse_preview(dataset_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        if "user" not in payload:
            raise HTTPException(status_code=400, detail="user is required")
        return browse.preview(
            dataset_id=dataset_id,
            user=payload.get("user", "anonymous"),
            purpose=payload.get("purpose", "analysis"),
            limit=min(int(payload.get("limit", 100)), 100),
            offset=max(int(payload.get("offset", 0)), 0),
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
    return {
        "question": query,
        "mapped_term": top.term,
        "user": user,
        "purpose": purpose,
        "policy_scope": "catalog_discovery",
        "policy": decision.model_dump(),
        "recommendations": ontology.concept_assets(top.term),
    }


@app.post("/llm/draft-query")
def draft_query(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        request = QueryDraftRequest(**payload)
        return orchestrator.draft_sql(request)
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/browse/query")
def browse_query(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        request = QueryExecutionRequest(**payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    result = orchestrator.execute_query(request)
    if result.status == "REJECTED":
        raise HTTPException(status_code=400, detail={"status": result.status, "warnings": result.warnings})
    if result.status == "DENIED":
        raise HTTPException(status_code=403, detail={"status": result.status, "warnings": result.warnings})

    return result.model_dump()


@app.post("/api/v1/browse/query")
def browse_query_v1(payload: dict[str, Any]) -> dict[str, Any]:
    return browse_query(payload)
