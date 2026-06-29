from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from . import browse, catalog, ontology, orchestrator
from .catalog import validate_metadata
from .domain import QueryDraftRequest
from .policy import evaluate


app = FastAPI(
    title="Semantic Data Portal",
    description="온톨로지 기반 데이터 카탈로그 및 브라우징 MVP",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "at": datetime.utcnow().isoformat() + "Z"}


@app.get("/catalog/search")
def catalog_search(
    q: str = Query(..., min_length=1),
    tags: list[str] | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=50),
) -> dict[str, Any]:
    results = catalog.search_catalog(q, tags=tags, limit=limit)
    return {
        "query": q,
        "count": len(results),
        "items": [
            {
                "id": row.dataset.id,
                "title": row.dataset.title,
                "tags": row.dataset.tags,
                "owner": row.dataset.owner,
                "steward": row.dataset.steward,
                "domain": row.dataset.domain,
                "quality": row.dataset.quality_score,
                "search_score": row.score,
                "metadata_completeness": row.dataset.metadata_completeness,
            }
            for row in results
        ],
    }


@app.get("/catalog/datasets")
def list_datasets() -> list[dict[str, Any]]:
    return [dataset.model_dump() for dataset in catalog.list_datasets()]


@app.get("/catalog/datasets/{dataset_id}")
def dataset_detail(dataset_id: str) -> dict[str, Any]:
    dataset = catalog.get_dataset(dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="dataset not found")
    return dataset.model_dump()


@app.get("/catalog/datasets/{dataset_id}/jsonld")
def dataset_jsonld(dataset_id: str) -> dict[str, Any]:
    dataset = catalog.get_dataset(dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="dataset not found")
    return {
        "@context": "https://www.w3.org/TR/vocab-dcat-3/",
        "@type": "Dataset",
        "id": f"https://semantic-data-portal.local/datasets/{dataset.id}",
        "title": dataset.title,
        "description": dataset.description,
        "distribution": [d.model_dump() for d in dataset.distributions],
    }


@app.get("/catalog/datasets/{dataset_id}/validate")
def validate(dataset_id: str) -> dict[str, Any]:
    dataset = catalog.get_dataset(dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="dataset not found")
    return validate_metadata(dataset)


@app.post("/policy/decision")
def policy_decision(payload: dict[str, str]) -> dict[str, Any]:
    decision = evaluate(
        subject=payload.get("subject", "anonymous"),
        resource=payload.get("resource", ""),
        action=payload.get("action", "preview"),
        purpose=payload.get("purpose", "analysis"),
    )
    return decision.dict()


@app.post("/ontology/resolve")
def resolve_terms(payload: dict[str, str]) -> dict[str, Any]:
    text = payload.get("text", "")
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


@app.get("/browse/{dataset_id}/schema")
def browse_schema(dataset_id: str) -> dict[str, Any]:
    try:
        return browse.schema(dataset_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="dataset not found")


@app.post("/browse/{dataset_id}/preview")
def browse_preview(dataset_id: str, payload: dict[str, str]) -> dict[str, Any]:
    try:
        return browse.preview(
            dataset_id=dataset_id,
            user=payload.get("user", "anonymous"),
            purpose=payload.get("purpose", "analysis"),
            limit=min(int(payload.get("limit", 100)), 100),
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="dataset not found")
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


@app.post("/llm/search")
def llm_search(payload: dict[str, str]) -> dict[str, Any]:
    query = payload.get("question", "")
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
    top = resolved[0].term
    return {"question": query, "mapped_term": top, "user": user, "purpose": purpose, "recommendations": ontology.concept_assets(top)}


@app.post("/llm/draft-query")
def draft_query(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        request = QueryDraftRequest(**payload)
        return orchestrator.draft_sql(request)
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=400, detail=str(exc))

