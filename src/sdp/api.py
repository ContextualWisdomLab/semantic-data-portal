from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sdp_core import (
    buyer_demo_activation_plan,
    enterprise_controls_manifest,
    enterprise_kpi_framework,
    enterprise_rbac_matrix,
    enterprise_readiness_manifest,
)

from . import authz, browse, catalog, connectors, ontology, orchestrator
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
from .policy import evaluate


app = FastAPI(
    title="Semantic Data Portal",
    description="온톨로지 기반 데이터 카탈로그 및 브라우징 MVP",
    version="0.2.1",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _actor(payload: dict[str, Any] | None) -> str:
    if not payload:
        return "anonymous"
    return str(payload.get("actor", "anonymous"))


def _require_actor(payload: dict[str, Any]) -> str:
    return _actor(payload)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "at": datetime.now(timezone.utc).isoformat()}


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


@app.get("/enterprise/evidence-pack")
def enterprise_evidence_pack() -> dict[str, Any]:
    return build_enterprise_evidence_pack()


@app.post("/enterprise/auth/oidc-preview")
def enterprise_oidc_preview(payload: dict[str, Any]) -> dict[str, Any]:
    claims = payload.get("claims", payload)
    if not isinstance(claims, dict):
        raise HTTPException(status_code=400, detail="claims must be an object")

    role_map = payload.get("role_map")
    if role_map is not None and not isinstance(role_map, dict):
        raise HTTPException(status_code=400, detail="role_map must be an object")

    context = authz.resolve_oidc_actor_context(claims, role_map=role_map)
    return {
        "mode": "claim_mapping_preview",
        "token_verification": "external_or_planned",
        "actor_context": context.model_dump(),
        "groups": claims.get("groups", []),
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
    return ontology.concept_graph(term)


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
