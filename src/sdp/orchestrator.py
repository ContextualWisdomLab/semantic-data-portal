from __future__ import annotations

from datetime import datetime
from .catalog import get_dataset
from .domain import QueryDraftRequest
from .policy import evaluate
from .domain import QueryExecutionRequest
from .domain import QueryExecutionResponse


_FORBIDDEN_KEYWORDS = {"drop", "delete", "truncate", "alter", "insert", "update", "merge", "exec", "union"}


def _safe_identifier(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in value)


def _safe_request_id() -> str:
    return "req-" + str(datetime.utcnow().timestamp()).replace(".", "")


def draft_sql(req: QueryDraftRequest) -> dict:
    if req.date_window_days < 1 or req.date_window_days > 365:
        return {"error": "invalid_date_window", "reason": "date_window_days must be between 1 and 365"}

    dataset = get_dataset(req.dataset_id)
    if not dataset:
        return {"error": "dataset_not_found"}
    if dataset.status != "published":
        return {"error": "policy_denied", "reason": "dataset is not published"}
    if not dataset.schema:
        return {"error": "missing_schema", "reason": "dataset schema must be present to draft query"}

    decision = evaluate(subject=req.user, resource=req.dataset_id, action="query", purpose=req.purpose)
    if decision.effect != "allow":
        return {"error": "policy_denied", "reason": decision.reason}

    question = req.question.strip().lower()
    if any(token in question for token in _FORBIDDEN_KEYWORDS):
        return {"error": "policy_denied", "reason": "허용되지 않은 키워드가 질의에 포함되었습니다."}

    allowed_columns = {column.name for column in dataset.schema if column.datatype}
    if req.columns:
        unknown = sorted(set(req.columns) - allowed_columns)
        if unknown:
            return {
                "error": "invalid_columns",
                "reason": f"요청한 컬럼이 데이터셋에 없습니다: {', '.join(unknown)}",
            }

    requested_columns = req.columns or ["*"]
    if req.group_by and req.group_by not in allowed_columns:
        return {"error": "invalid_group_by", "reason": "요청한 그룹화 컬럼이 데이터셋에 없습니다."}

    where_clause = f"WHERE created_at >= current_date - interval '{req.date_window_days} day'"
    table_name = _safe_identifier(dataset.source_system.rsplit("/", 1)[-1])

    row_limit = min(req.row_limit, 2000)
    if row_limit <= 0:
        return {"error": "invalid_row_limit", "reason": "row_limit must be a positive integer"}

    timeout_ms = req.timeout_ms
    if timeout_ms < 500 or timeout_ms > 120000:
        return {"error": "invalid_timeout", "reason": "timeout_ms must be between 500 and 120000"}

    if req.group_by:
        group_clause = f"GROUP BY {req.group_by}"
        select_fields = f"{_safe_identifier(req.group_by)}, count(*) AS active_customer_count"
    else:
        group_clause = ""
        if "*" in requested_columns:
            select_fields = "count(*) AS active_customer_count"
        else:
            select_fields = ", ".join(_safe_identifier(column) for column in requested_columns)
            select_fields = f"{select_fields}, count(*) AS active_customer_count"

    max_rows = min(row_limit, 2000)
    if "*" in requested_columns and len(requested_columns) > 1:
        requested_columns = ["*"]

    estimated_cost = max(1, len(requested_columns) * row_limit // 200 + 1)
    sql = f"SELECT {select_fields} FROM {table_name} {where_clause} {group_clause} LIMIT {max_rows}"

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

    row_filter = decision.obligations.get("row_filter")
    if row_filter:
        assumptions.append(f"행 레벨 필터 적용: {', '.join(row_filter)}")

    if not req.group_by:
        assumptions.append("기본 집계는 건수 카운트 기반으로 반환")

    return {
        "dataset_id": req.dataset_id,
        "query": sql,
        "policy_decision_id": decision.decision_id,
        "assumptions": assumptions,
        "policy_decision": decision.dict(),
        "preview_required": req.purpose == "analysis",
        "dialect": "postgresql",
        "row_limit": max_rows,
        "requested_columns": requested_columns,
        "timeout_ms": timeout_ms,
        "estimated_cost": estimated_cost,
    }


def execute_query(req: QueryExecutionRequest) -> QueryExecutionResponse:
    if req.language.strip().upper() != "SQL":
        return QueryExecutionResponse(
            request_id=_safe_request_id(),
            dataset_id=req.dataset_ids[0],
            query_id="",
            policy_decision_id="",
            status="REJECTED",
            row_count=0,
            columns=[],
            rows=[],
            execution={"elapsedMs": 0, "source": "validation", "bytesScanned": 0},
            warnings=["unsupported_language"],
        )

    lowered = req.query.lower()
    if any(token in lowered for token in _FORBIDDEN_KEYWORDS):
        return QueryExecutionResponse(
            request_id=_safe_request_id(),
            dataset_id=req.dataset_ids[0],
            query_id="",
            policy_decision_id="",
            status="REJECTED",
            row_count=0,
            columns=[],
            rows=[],
            execution={"elapsedMs": 0, "source": "validation", "bytesScanned": 0},
            warnings=["forbidden_keyword_detected"],
        )

    if len(req.dataset_ids) > 1:
        return QueryExecutionResponse(
            request_id=_safe_request_id(),
            dataset_id=req.dataset_ids[0],
            query_id="",
            policy_decision_id="",
            status="REJECTED",
            row_count=0,
            columns=[],
            rows=[],
            execution={"elapsedMs": 0, "source": "validation", "bytesScanned": 0},
            warnings=["cross_source_join_not_supported"],
        )

    dataset_id = req.dataset_ids[0]
    dataset = get_dataset(dataset_id)
    if not dataset:
        return QueryExecutionResponse(
            request_id=_safe_request_id(),
            dataset_id=dataset_id,
            query_id="",
            policy_decision_id="",
            status="REJECTED",
            row_count=0,
            columns=[],
            rows=[],
            execution={"elapsedMs": 0, "source": "validation", "bytesScanned": 0},
            warnings=["dataset_not_found"],
        )

    decision = evaluate(subject=req.user, resource=dataset_id, action="query", purpose=req.purpose)
    if decision.effect != "allow":
        return QueryExecutionResponse(
            request_id=_safe_request_id(),
            dataset_id=dataset.id,
            query_id="",
            policy_decision_id=decision.decision_id,
            status="DENIED",
            row_count=0,
            columns=[],
            rows=[],
            execution={"elapsedMs": 0, "source": "policy", "bytesScanned": 0},
            warnings=[decision.reason],
        )

    if req.dry_run:
        row_count = 0
    else:
        row_count = min(2000, dataset.profile.get("row_count", 1000))

    now = datetime.utcnow().isoformat() + "Z"
    return QueryExecutionResponse(
        request_id=_safe_request_id(),
        dataset_id=dataset.id,
        query_id=f"qry-{now.replace(':', '')}",
        policy_decision_id=decision.decision_id,
        status="SUCCEEDED",
        row_count=row_count,
        columns=["week", "active_count"] if "group by" in lowered else ["result"],
        rows=[
            {"week": now[:10], "active_count": 1}
        ] if "group by" in lowered else [
            {"result": row_count}
        ],
        execution={"elapsedMs": 100, "source": "mock-trino", "bytesScanned": 1024},
        warnings=["mock_execution_no_real_data"],
    )
