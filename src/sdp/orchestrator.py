from __future__ import annotations

from .catalog import get_dataset
from .domain import QueryDraftRequest
from .policy import evaluate


_FORBIDDEN_KEYWORDS = {"drop", "delete", "truncate", "alter", "insert", "update", "merge", "exec", "union"}


def _safe_identifier(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in value)


def draft_sql(req: QueryDraftRequest) -> dict:
    if req.date_window_days < 1 or req.date_window_days > 365:
        return {"error": "invalid_date_window", "reason": "date_window_days must be between 1 and 365"}

    dataset = get_dataset(req.dataset_id)
    if not dataset:
        return {"error": "dataset_not_found"}

    decision = evaluate(subject=req.user, resource=req.dataset_id, action="query", purpose=req.purpose)
    if decision.effect != "allow":
        return {"error": "policy_denied", "reason": decision.reason}

    question = req.question.strip().lower()
    if any(token in question for token in _FORBIDDEN_KEYWORDS):
        return {"error": "policy_denied", "reason": "허용되지 않은 키워드가 질의에 포함되었습니다."}

    allowed_columns = {column.name for column in dataset.schema if column.datatype}
    if req.group_by and req.group_by not in allowed_columns:
        return {"error": "invalid_group_by", "reason": "요청한 그룹화 컬럼이 데이터셋에 없습니다."}

    where_clause = f"WHERE created_at >= current_date - interval '{req.date_window_days} day'"
    table_name = _safe_identifier(dataset.source_system.rsplit("/", 1)[-1])

    if req.group_by:
        group_clause = f"GROUP BY {req.group_by}"
        select_fields = f"{_safe_identifier(req.group_by)}, count(*) AS active_customer_count"
    else:
        group_clause = ""
        select_fields = "count(*) AS active_customer_count"

    sql = f"SELECT {select_fields} FROM {table_name} {where_clause} {group_clause} LIMIT 1000"

    assumptions = [
        "카탈로그에서 검증된 테이블/컬럼만 사용",
        "read-only SELECT만 허용",
        "목적별 정책으로 PII 필드는 masking 또는 집계 제한",
    ]
    if req.group_by in {"signup_at", "event_timestamp", "created_at"}:
        assumptions.append("날짜 집계는 기간 기반 집계로만 제한")

    masked_pii = [col.name for col in dataset.schema if col.pii]
    if masked_pii and req.purpose == "analysis":
        assumptions.append(f"PII 컬럼({', '.join(masked_pii)})은 별도 집계/마스킹 필요")

    if not req.group_by:
        assumptions.append("기본 집계는 건수 카운트 기반으로 반환")

    return {
        "dataset_id": req.dataset_id,
        "query": sql,
        "assumptions": assumptions,
        "policy_decision": decision.dict(),
        "preview_required": req.purpose == "analysis",
        "dialect": "postgresql",
    }
