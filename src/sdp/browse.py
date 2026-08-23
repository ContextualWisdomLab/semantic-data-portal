from __future__ import annotations

from typing import Any, Dict, List

from .catalog import get_dataset, ingest_event
from .policy import evaluate


def preview(dataset_id: str, user: str, purpose: str, limit: int = 100, offset: int = 0) -> Dict[str, Any]:
    """Return authorized preview rows with steward-usable PII.

    Access is fail-closed by Keyverse purpose-limited authorization.
    This portal does not mask columns. Response minimization and redaction
    belong to the GRC evidence contract, not this catalog plane.
    """
    if limit < 1:
        raise ValueError("limit must be at least 1")
    if limit > 100:
        raise ValueError("preview limit cannot exceed 100")
    if offset < 0:
        raise ValueError("offset must be greater than or equal to 0")

    dataset = get_dataset(dataset_id)
    if not dataset:
        ingest_event(
            event_type="browse.preview",
            actor=user,
            dataset_id=dataset_id,
            decision="denied",
            reason="dataset_not_found",
            details={"policy_decision_id": None},
        )
        raise KeyError("dataset not found")

    decision = evaluate(subject=user, resource=dataset_id, action="preview", purpose=purpose)
    if decision.effect != "allow":
        ingest_event(
            event_type="browse.preview",
            actor=user,
            dataset_id=dataset_id,
            decision="denied",
            reason=decision.reason,
            decision_id=decision.decision_id,
            details={"purpose": purpose, "policy_decision_id": decision.decision_id},
        )
        raise PermissionError(decision.reason)

    rows = [
        {
            "customer_id": "C-1001",
            "customer_email": "alice@example.com",
            "signup_at": "2026-01-15T00:00:00Z",
            "event_timestamp": "2026-06-20T12:10:00Z",
            "device_id": "dev-88",
        },
        {
            "customer_id": "C-1002",
            "customer_email": "bob@example.com",
            "signup_at": "2026-01-20T00:00:00Z",
            "event_timestamp": "2026-06-21T09:11:00Z",
            "device_id": "dev-01",
        },
    ]

    selected = [row.copy() for row in rows[offset : offset + limit]]
    obligated_mask = list(decision.obligations.get("masking", []))
    ingest_event(
        event_type="browse.preview",
        actor=user,
        dataset_id=dataset_id,
        decision="allowed",
        reason="ok",
        decision_id=decision.decision_id,
        details={
            "purpose": purpose,
            "requested_offset": offset,
            "requested_limit": limit,
            "returned_rows": len(selected),
            "row_filter": decision.obligations.get("row_filter"),
            "policy_decision_id": decision.decision_id,
            "masking_applied": False,
            "grc_redaction_obligated_columns": obligated_mask,
        },
    )
    return {
        "dataset_id": dataset.id,
        "policy_decision": decision.model_dump(),
        "columns": [column.name for column in dataset.schema],
        "rows": selected,
        "row_count": min(limit, len(selected)),
        "offset": offset,
        "masking_summary": {
            "masked_columns": [],
            "masking_applied": False,
            "grc_redaction_obligated_columns": obligated_mask,
        },
        "has_more": offset + len(selected) < len(rows),
        "sampling_note": "샘플 결과이며 전체 데이터 대표성을 보장하지 않습니다.",
        "policy_decision_id": decision.decision_id,
        "applied_row_filter": decision.obligations.get("row_filter"),
    }


def apply_mask(row: Dict[str, Any], masked_columns: List[str]) -> Dict[str, Any]:
    """Kept for import compatibility. Never redacts; GRC owns redaction."""
    del masked_columns
    return row


def schema(dataset_id: str, user: str, purpose: str = "analysis") -> Dict[str, Any]:
    """Return dataset schema for an authorized steward without masking columns."""
    dataset = get_dataset(dataset_id)
    if not dataset:
        raise KeyError("dataset not found")

    decision = evaluate(subject=user, resource=dataset_id, action="schema", purpose=purpose)
    if decision.effect != "allow":
        ingest_event(
            event_type="browse.schema",
            actor=user,
            dataset_id=dataset_id,
            decision="denied",
            reason=decision.reason,
            decision_id=decision.decision_id,
            details={"purpose": purpose, "policy_decision_id": decision.decision_id},
        )
        raise PermissionError(decision.reason)

    ingest_event(
        event_type="browse.schema",
        actor=user,
        dataset_id=dataset_id,
        decision="allowed",
        reason=decision.reason,
        decision_id=decision.decision_id,
        details={"purpose": purpose, "policy_decision_id": decision.decision_id},
    )
    return {
        "dataset_id": dataset.id,
        "policy_decision_id": decision.decision_id,
        "schema": [column.model_dump() for column in dataset.schema],
        "mappings": [mapping.model_dump() for mapping in dataset.mappings],
        "masked_columns": [],
        "grc_redaction_obligated_columns": decision.obligations.get("masking", []),
        "quality": {"quality_score": dataset.quality_score, "freshness_score": dataset.freshness_score},
    }
