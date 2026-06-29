from __future__ import annotations

from typing import Any, Dict, List

from .catalog import get_dataset
from .policy import evaluate


def preview(dataset_id: str, user: str, purpose: str, limit: int = 100) -> Dict[str, Any]:
    dataset = get_dataset(dataset_id)
    if not dataset:
        raise KeyError("dataset not found")
    decision = evaluate(subject=user, resource=dataset_id, action="preview", purpose=purpose)
    if decision.effect != "allow":
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

    masked = [apply_mask(row.copy(), decision.obligations.get("masking", []), purpose) for row in rows[:limit]]
    return {
        "dataset_id": dataset.id,
        "policy_decision": decision.dict(),
        "columns": [column.name for column in dataset.schema],
        "rows": masked,
        "row_count": min(limit, len(masked)),
        "sampling_note": "샘플 결과이며 전체 데이터 대표성을 보장하지 않습니다.",
    }


def apply_mask(row: Dict[str, Any], masked_columns: List[str], purpose: str) -> Dict[str, Any]:
    if "admin" in purpose.lower():
        return row
    for col in masked_columns:
        if col in row:
            row[col] = "***"
    return row


def schema(dataset_id: str) -> Dict[str, Any]:
    dataset = get_dataset(dataset_id)
    if not dataset:
        raise KeyError("dataset not found")
    return {
        "dataset_id": dataset.id,
        "schema": [column.model_dump() for column in dataset.schema],
        "quality": {"quality_score": dataset.quality_score, "freshness_score": dataset.freshness_score},
    }

