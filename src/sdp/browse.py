from __future__ import annotations

from typing import Any, Dict, List

from .catalog import get_dataset, ingest_event
from .policy import evaluate


def preview(dataset_id: str, user: str, purpose: str, limit: int = 100, offset: int = 0) -> Dict[str, Any]:
    """Authorize a dataset preview request and fail closed without source execution."""
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

    ingest_event(
        event_type="browse.preview",
        actor=user,
        dataset_id=dataset_id,
        decision="unavailable",
        reason="source_preview_backend_not_configured",
        decision_id=decision.decision_id,
        details={
            "purpose": purpose,
            "requested_offset": offset,
            "requested_limit": limit,
            "row_filter": decision.obligations.get("row_filter"),
            "policy_decision_id": decision.decision_id,
        },
    )
    raise RuntimeError("source_preview_backend_not_configured")


def apply_mask(row: Dict[str, Any], masked_columns: List[str]) -> Dict[str, Any]:
    """Replace explicitly masked columns without changing unrelated values."""
    if not masked_columns:
        return row
    for col in masked_columns:
        if col in row:
            row[col] = "***"
    return row


def schema(dataset_id: str, user: str, purpose: str = "analysis") -> Dict[str, Any]:
    """Return policy-authorized catalog schema metadata for one dataset."""
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
        "masked_columns": decision.obligations.get("masking", []),
        "quality": {"quality_score": dataset.quality_score, "freshness_score": dataset.freshness_score},
    }
