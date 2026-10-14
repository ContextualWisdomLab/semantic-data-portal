from __future__ import annotations

from typing import Any, Dict, List

from .catalog import get_dataset, ingest_event
from .domain import ColumnMetadata, Dataset
from .policy import evaluate

# Demo sample values, keyed by the column they belong to. The preview rows are
# built by projecting these onto the *named* dataset's declared schema, so a
# preview can only ever carry columns that dataset declares. A fixed row set
# served for every dataset leaked one dataset's PII column through another
# dataset's id: the masking obligation is computed from the named dataset's
# ``pii`` flags, so naming a dataset with no PII column returned
# ``customer_email`` in the clear.
_SAMPLE_COLUMN_VALUES: Dict[str, tuple[str, ...]] = {
    "broader_concept": (
        "https://semantic-data-portal.local/concepts/party",
        "https://semantic-data-portal.local/concepts/customer",
    ),
    "campaign_id": ("cmp-1001", "cmp-1002"),
    "channel": ("email", "push"),
    "concept_uri": (
        "https://semantic-data-portal.local/concepts/customer",
        "https://semantic-data-portal.local/concepts/active-customer",
    ),
    "customer_email": ("alice@example.com", "bob@example.com"),
    "customer_id": ("C-1001", "C-1002"),
    "device_id": ("dev-88", "dev-01"),
    "event_id": ("evt-1001", "evt-1002"),
    "event_timestamp": ("2026-06-20T12:10:00Z", "2026-06-21T09:11:00Z"),
    "order_amount": ("129000.00", "48500.00"),
    "order_id": ("ord-1001", "ord-1002"),
    "preferred_label": ("고객", "활성 고객"),
    "signup_at": ("2026-01-15T00:00:00Z", "2026-01-20T00:00:00Z"),
    "target_segment": ("active_customers", "churn_risk"),
}

# Fallback sample values for a column the demo seed does not describe - a
# dataset registered through POST /catalog/datasets, for instance.
_SAMPLE_DATATYPE_VALUES: Dict[str, tuple[str, ...]] = {
    "boolean": ("true", "false"),
    "date": ("2026-01-15", "2026-01-20"),
    "decimal": ("1000.00", "2000.00"),
    "integer": ("1", "2"),
    "iri": (
        "https://semantic-data-portal.local/resource/sample-1",
        "https://semantic-data-portal.local/resource/sample-2",
    ),
    "timestamp": ("2026-01-15T00:00:00Z", "2026-01-20T00:00:00Z"),
}

_SAMPLE_ROW_COUNT = 2


def _sample_value(column: ColumnMetadata, row_index: int) -> str:
    """Pick this column's demo value for one sample row, deterministically."""
    values = _SAMPLE_COLUMN_VALUES.get(column.name) or _SAMPLE_DATATYPE_VALUES.get(column.datatype)
    if values:
        return values[row_index % len(values)]
    return f"{column.name}-sample-{row_index + 1}"


def _sample_rows(dataset: Dataset) -> List[Dict[str, Any]]:
    """Build the demo preview rows from the dataset's own declared schema.

    Projecting the sample values onto ``dataset.schema`` is what keeps a preview
    inside the named dataset: a column the dataset does not declare has no cell
    to appear in, so another dataset's id cannot reach it.
    """
    return [
        {column.name: _sample_value(column, row_index) for column in dataset.schema}
        for row_index in range(_SAMPLE_ROW_COUNT)
    ]


def preview(dataset_id: str, user: str, purpose: str, limit: int = 100, offset: int = 0) -> Dict[str, Any]:
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

    rows = _sample_rows(dataset)

    # Masking is a floor rather than a best effort: the obligation is the policy's
    # instruction, and a column the dataset itself declares as PII is masked even
    # if a future policy change stopped listing it.
    obligated = decision.obligations.get("masking") or []
    declared_pii = [column.name for column in dataset.schema if column.pii]
    masked_columns = list(dict.fromkeys([*obligated, *declared_pii]))

    selected = rows[offset : offset + limit]
    masked = [apply_mask(row.copy(), masked_columns) for row in selected]
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
            "returned_rows": len(masked),
            "masked_columns": masked_columns,
            "row_filter": decision.obligations.get("row_filter"),
            "policy_decision_id": decision.decision_id,
        },
    )
    return {
        "dataset_id": dataset.id,
        "policy_decision": decision.model_dump(),
        "columns": [column.name for column in dataset.schema],
        "rows": masked,
        "row_count": min(limit, len(masked)),
        "offset": offset,
        "masking_summary": {"masked_columns": masked_columns},
        "has_more": offset + len(masked) < len(rows),
        "sampling_note": "샘플 결과이며 전체 데이터 대표성을 보장하지 않습니다.",
        "policy_decision_id": decision.decision_id,
        "applied_row_filter": decision.obligations.get("row_filter"),
    }


def apply_mask(row: Dict[str, Any], masked_columns: List[str]) -> Dict[str, Any]:
    if not masked_columns:
        return row
    for col in masked_columns:
        if col in row:
            row[col] = "***"
    return row


def schema(dataset_id: str, user: str, purpose: str = "analysis") -> Dict[str, Any]:
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
