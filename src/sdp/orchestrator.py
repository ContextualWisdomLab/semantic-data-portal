from __future__ import annotations

from .catalog import get_dataset, get_dataset
from .domain import QueryDraftRequest
from .policy import evaluate


def draft_sql(req: QueryDraftRequest) -> dict:
    dataset = get_dataset(req.dataset_id)
    if not dataset:
        return {"error": "dataset_not_found"}

    decision = evaluate(subject=req.user, resource=req.dataset_id, action="query", purpose=req.purpose)
    if decision.effect != "allow":
        return {"error": "policy_denied", "reason": decision.reason}

    if req.group_by and req.group_by not in {column.name for column in dataset.schema}:
        return {"error": "invalid_group_by", "reason": "요청한 그룹화 컬럼이 데이터셋에 없습니다."}

    table_name = dataset.source_system.split("/")[-1]
    where_clause = f"WHERE created_at >= current_date - interval '{req.date_window_days} day'" 
    select_fields = "customer_id, count(*) AS active_customer_count"
    if req.group_by:
        select_fields = f"{req.group_by}, count(*) AS active_customer_count"
        group_clause = f"GROUP BY {req.group_by}"
    else:
        group_clause = ""

    sql = f"SELECT {select_fields} FROM {table_name} {where_clause} {group_clause} LIMIT 1000"
    assumptions = [
        "카탈로그에서 검증된 테이블명/컬럼명만 사용",
        "목적별 정책으로 PII 필드는 SELECT 대상에서 제거",
        "read-only SELECT만 허용",
    ]

    return {
        "dataset_id": req.dataset_id,
        "query": sql,
        "assumptions": assumptions,
        "policy_decision": decision.dict(),
        "preview_required": req.purpose == "analysis",
    }

