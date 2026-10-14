from __future__ import annotations

import re
from datetime import datetime, timezone
from .catalog import get_dataset, ingest_event
from .domain import QueryDraftRequest
from .policy import evaluate
from .domain import QueryExecutionRequest
from .domain import QueryExecutionResponse


# Statement-initiating or write-capable keywords. `into`, `create` and `copy`
# matter even though the guard already demands a leading `select `: PostgreSQL
# reads `SELECT ... INTO <name>` as CREATE TABLE AS, so a write can hide inside
# a statement that opens like the read the guard is looking for.
_FORBIDDEN_KEYWORDS = {
    "alter",
    "call",
    "copy",
    "create",
    "delete",
    "drop",
    "exec",
    "execute",
    "grant",
    "insert",
    "into",
    "lock",
    "merge",
    "prepare",
    "revoke",
    "truncate",
    "union",
    "update",
    "vacuum",
}

# A dollar-quoted string ($$text$$ or $tag$text$tag$) is a PostgreSQL string
# literal that contains neither quote character, so it smuggles an argument past
# a guard that only looks for ' and ".
_DOLLAR_QUOTE = re.compile(r"\$[A-Za-z_]*\$")

# Keywords that end a table list. Anything else following a table identifier is
# an alias (with or without AS) and is not itself a table.
_TABLE_CLAUSE_TERMINATORS = frozenset(
    {
        "cross",
        "except",
        "fetch",
        "from",
        "full",
        "group",
        "having",
        "inner",
        "intersect",
        "into",
        "join",
        "lateral",
        "left",
        "limit",
        "natural",
        "offset",
        "on",
        "order",
        "right",
        "select",
        "union",
        "using",
        "where",
        "window",
    }
)

_TABLE_LIST_TOKEN = re.compile(r",|[A-Za-z_][\w.]*")


def _safe_identifier(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in value)


def _safe_request_id() -> str:
    return "req-" + str(datetime.now(timezone.utc).timestamp()).replace(".", "")


def _source_table_name(source_system: str) -> str:
    return _safe_identifier(source_system.rstrip("/").rsplit("/", 1)[-1])


def _referenced_source_tables(sql: str) -> list[str] | None:
    """List every table identifier that a FROM or JOIN clause references.

    One FROM clause may name several tables in a comma-separated list, each
    optionally aliased, so reading only the identifier that follows the keyword
    leaves every table after the first comma invisible to the allow-list check.
    Returns ``None`` when a clause cannot be read as a table list, so the caller
    refuses the query instead of guessing what it touches.
    """
    tokens = _TABLE_LIST_TOKEN.findall(sql)
    tables: list[str] = []
    index = 0
    while index < len(tokens):
        keyword = tokens[index].lower()
        index += 1
        if keyword not in {"from", "join"}:
            continue
        expect_table = True
        while index < len(tokens):
            token = tokens[index]
            if token == ",":
                index += 1
                if expect_table:
                    return None
                expect_table = True
                continue
            if token.lower() in _TABLE_CLAUSE_TERMINATORS:
                break
            index += 1
            if expect_table:
                tables.append(token)
                expect_table = False
        if expect_table:
            return None
    return tables


def _matched_forbidden_keyword(text: str) -> str | None:
    """Return the first forbidden keyword appearing in ``text`` as a whole word.

    Every gate that consults ``_FORBIDDEN_KEYWORDS`` goes through here, because
    they did not agree before: ``validate_sql_query`` matched on word boundaries
    while ``draft_sql`` and ``execute_query`` matched on bare substrings. The
    canonical validator therefore returned no warning for
    ``select created_at from customer`` while ``/browse/query`` rejected the
    identical SQL as hostile.

    Substring matching refuses ordinary identifiers: ``create`` is inside
    ``created_at``, ``update`` inside ``updated_at``, ``delete`` inside
    ``deleted_flag``, and the same holds for ``merged_at``, ``locked_at``,
    ``granted_scope``, ``execution_count``, ``dropoff_rate`` and ``intopic`` -
    nine shapes an ordinary warehouse column carries. Word boundaries still
    catch the real cases (``drop table``, ``select ... into exfil``), which is
    what the keyword list exists for.

    The list is iterated in sorted order so the keyword reported back to the
    caller is deterministic rather than set-iteration dependent.
    """
    lowered = text.lower()
    for token in sorted(_FORBIDDEN_KEYWORDS):
        if re.search(rf"\b{re.escape(token)}\b", lowered):
            return token
    return None


def validate_sql_query(sql: str, *, source_system: str) -> list[str]:
    stripped = sql.strip()
    lowered = stripped.lower()
    warnings: list[str] = []

    if not lowered.startswith("select "):
        warnings.append("only_select_allowed")
    if ";" in stripped:
        warnings.append("single_statement_required")
    if "--" in stripped or "/*" in stripped or "*/" in stripped:
        warnings.append("sql_comments_not_allowed")
    if "'" in stripped or '"' in stripped or _DOLLAR_QUOTE.search(stripped):
        warnings.append("literal_values_not_allowed")
    if re.search(r"\b(and|or)\b", lowered):
        warnings.append("boolean_operator_not_allowed")

    if _matched_forbidden_keyword(lowered) is not None:
        warnings.append("forbidden_keyword_detected")

    referenced = _referenced_source_tables(stripped)
    if referenced is None:
        # An unreadable table list is refused rather than treated as empty: the
        # query does touch tables, we just cannot prove which ones are allowed.
        warnings.append("unauthorized_table_reference")
        return warnings
    if not referenced:
        warnings.append("missing_source_table")
        return warnings

    expected = _source_table_name(source_system).lower()
    # Compare the WHOLE reference. Taking only the last dot-separated component
    # made any qualification whose leaf matched pass the allow-list:
    # pg_catalog.customer, otherdb.otherschema.customer and
    # information_schema.customer all reduce to "customer". The drafter emits the
    # bare name (_source_table_name), so a qualified reference is one the
    # allow-list cannot prove. _safe_identifier maps the dot to "_", so a
    # qualified name can never collide with the bare one.
    referenced_tables = {_safe_identifier(table).lower() for table in referenced}
    if referenced_tables != {expected}:
        warnings.append("unauthorized_table_reference")

    return warnings


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
    # The reason names the offending keyword: the previous message said only
    # that "a" keyword was present, so an integrator whose question mentioned
    # created_at had no way to tell which word was refused - or that the refusal
    # was spurious.
    forbidden_in_question = _matched_forbidden_keyword(question)
    if forbidden_in_question is not None:
        return {
            "error": "policy_denied",
            "reason": f"허용되지 않은 키워드가 질의에 포함되었습니다: {forbidden_in_question}",
        }

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
    table_name = _source_table_name(dataset.source_system)

    row_limit = min(req.row_limit, 2000)
    if row_limit <= 0:
        return {"error": "invalid_row_limit", "reason": "row_limit must be a positive integer"}

    timeout_ms = req.timeout_ms
    if timeout_ms < 500 or timeout_ms > 120000:
        return {"error": "invalid_timeout", "reason": "timeout_ms must be between 500 and 120000"}

    if req.group_by:
        group_identifier = _safe_identifier(req.group_by)
        group_clause = f"GROUP BY {group_identifier}"
        select_fields = f"{group_identifier}, count(*) AS active_customer_count"
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
        "policy_decision": decision.model_dump(),
        "preview_required": req.purpose == "analysis",
        "dialect": "postgresql",
        "row_limit": max_rows,
        "requested_columns": requested_columns,
        "timeout_ms": timeout_ms,
        "estimated_cost": estimated_cost,
    }


def execute_query(req: QueryExecutionRequest) -> QueryExecutionResponse:
    request_id = _safe_request_id()

    def response(
        *,
        dataset_id: str,
        query_id: str = "",
        policy_decision_id: str = "",
        status: str,
        row_count: int = 0,
        columns: list[str] | None = None,
        rows: list[dict[str, str | int | float | bool | None]] | None = None,
        execution: dict[str, object] | None = None,
        warnings: list[str] | None = None,
    ) -> QueryExecutionResponse:
        return QueryExecutionResponse(
            request_id=request_id,
            dataset_id=dataset_id,
            query_id=query_id,
            policy_decision_id=policy_decision_id,
            status=status,
            row_count=row_count,
            columns=columns or [],
            rows=rows or [],
            execution=execution or {"elapsedMs": 0, "source": "validation", "bytesScanned": 0},
            warnings=warnings or [],
        )

    def audit(
        *,
        dataset_id: str,
        result: str,
        reason: str,
        decision_id: str | None = None,
        details: dict[str, object] | None = None,
    ) -> None:
        audit_details = {"purpose": req.purpose, "request_id": request_id, "dry_run": req.dry_run}
        if details:
            audit_details.update(details)
        ingest_event(
            event_type="browse.query",
            actor=req.user,
            dataset_id=dataset_id,
            decision=result,
            decision_id=decision_id,
            reason=reason,
            details=audit_details,
        )

    dataset_id = req.dataset_ids[0]
    if req.language.strip().upper() != "SQL":
        audit(dataset_id=dataset_id, result="rejected", reason="unsupported_language")
        return response(
            dataset_id=dataset_id,
            status="REJECTED",
            warnings=["unsupported_language"],
        )

    lowered = req.query.lower()
    if _matched_forbidden_keyword(lowered) is not None:
        audit(dataset_id=dataset_id, result="rejected", reason="forbidden_keyword_detected")
        return response(
            dataset_id=dataset_id,
            status="REJECTED",
            warnings=["forbidden_keyword_detected"],
        )

    if len(req.dataset_ids) > 1:
        audit(dataset_id=dataset_id, result="rejected", reason="cross_source_join_not_supported")
        return response(
            dataset_id=dataset_id,
            status="REJECTED",
            warnings=["cross_source_join_not_supported"],
        )

    dataset = get_dataset(dataset_id)
    if not dataset:
        audit(dataset_id=dataset_id, result="rejected", reason="dataset_not_found")
        return response(
            dataset_id=dataset_id,
            status="REJECTED",
            warnings=["dataset_not_found"],
        )

    decision = evaluate(subject=req.user, resource=dataset_id, action="query", purpose=req.purpose)
    if decision.effect != "allow":
        audit(
            dataset_id=dataset.id,
            result="denied",
            reason=decision.reason,
            decision_id=decision.decision_id,
            details={"policy_decision_id": decision.decision_id},
        )
        return response(
            dataset_id=dataset.id,
            policy_decision_id=decision.decision_id,
            status="DENIED",
            execution={"elapsedMs": 0, "source": "policy", "bytesScanned": 0},
            warnings=[decision.reason],
        )

    validation_warnings = validate_sql_query(req.query, source_system=dataset.source_system)
    if validation_warnings:
        audit(
            dataset_id=dataset.id,
            result="rejected",
            reason="query_safety_validation_failed",
            decision_id=decision.decision_id,
            details={
                "policy_decision_id": decision.decision_id,
                "warnings": validation_warnings,
            },
        )
        return response(
            dataset_id=dataset.id,
            policy_decision_id=decision.decision_id,
            status="REJECTED",
            execution={"elapsedMs": 0, "source": "query_safety", "bytesScanned": 0},
            warnings=validation_warnings,
        )

    if req.dry_run:
        row_count = 0
    else:
        row_count = min(2000, dataset.profile.get("row_count", 1000))

    now = datetime.now(timezone.utc).isoformat()
    query_id = f"qry-{now.replace(':', '')}"
    columns = ["week", "active_count"] if "group by" in lowered else ["result"]
    rows = (
        [{"week": now[:10], "active_count": 1}]
        if "group by" in lowered
        else [{"result": row_count}]
    )
    execution = {"elapsedMs": 100, "source": "mock-trino", "bytesScanned": 1024}
    audit(
        dataset_id=dataset.id,
        result="allowed",
        reason="ok",
        decision_id=decision.decision_id,
        details={
            "policy_decision_id": decision.decision_id,
            "query_id": query_id,
            "row_count": row_count,
            "bytes_scanned": execution["bytesScanned"],
        },
    )
    return response(
        dataset_id=dataset.id,
        query_id=query_id,
        policy_decision_id=decision.decision_id,
        status="SUCCEEDED",
        row_count=row_count,
        columns=columns,
        rows=rows,
        execution=execution,
        warnings=["mock_execution_no_real_data"],
    )
