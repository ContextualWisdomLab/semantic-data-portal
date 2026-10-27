from __future__ import annotations

from typing import Any, Dict, List

from .authz import can_access_tenant
from .catalog import get_dataset, get_dataset_profile, ingest_event
from .domain import ColumnMetadata, Dataset
from sdp_core.contracts import masked_column_rules
from .policy import evaluate, evaluate_dataset_scope_refusal
from .quality_warnings import quality_warning_summary

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


# The fixed ceiling on one preview page, and the number the request contract
# publishes as this property's bound. It was a bare ``100`` in two comparisons
# and in no document: the published description said only that policy may
# require a lower cap, so a client sending ``limit: 500`` met a 400 the document
# never mentioned. Named here so the contract can reference the same value
# rather than restate it.
MAX_PREVIEW_ROWS = 100
MIN_PREVIEW_ROWS = 1


def _invalid_pagination_reason(limit: int, offset: int) -> tuple[str, str] | None:
    """The audit reason and caller message for out-of-range pagination, if any.

    Returned rather than raised so the caller can record the refusal before it
    becomes an exception. The message is the one the caller already received
    before this was governed, so the HTTP contract is unchanged; what changes is
    that the refusal now leaves a row.
    """
    if limit < MIN_PREVIEW_ROWS:
        return "invalid_pagination_limit", f"limit must be at least {MIN_PREVIEW_ROWS}"
    if limit > MAX_PREVIEW_ROWS:
        return "invalid_pagination_limit", f"preview limit cannot exceed {MAX_PREVIEW_ROWS}"
    if offset < 0:
        return "invalid_pagination_offset", "offset must be greater than or equal to 0"
    return None


def preview(
    dataset_id: str,
    user: str,
    purpose: str,
    limit: int = MAX_PREVIEW_ROWS,
    offset: int = 0,
) -> Dict[str, Any]:
    # The pagination bounds are checked *after* the dataset lookup and the
    # policy call, not before them. They used to be first, which was harmless
    # only while the route clamped the values and made them unreachable over
    # HTTP; ``4d9e3d3`` stopped clamping - rightly, a clamp silently rewrote
    # what the caller asked for - and that turned them into a refusal path that
    # returned before any policy evaluation and filed no evidence at all.
    # Measured: ``limit: 9999`` answered 400 with zero audit events and zero
    # policy decisions, for an authorised caller, for a denied caller, and for
    # an absent dataset alike. On the policy-gated data-access surface of a
    # product whose claim is the evidence trail, and against the invariant
    # CLAUDE.md states outright.
    #
    # Deny first, so the answer a caller gets is the authorisation answer: one
    # who may not read the dataset is told that, and never learns what this
    # route thinks of their pagination.
    #
    # The existence lookup comes before the policy call, and that is not a
    # regression of the policy-before-access order: no data is read here, and
    # the generic ``evaluate`` cannot file an absent-id refusal safely.
    #
    # ``evaluate`` resolves the owning tenant from the catalog, so a *foreign*
    # id files its deny row to that tenant and the prober reads nothing - but an
    # *absent* id has no owner, so ``_effective_tenant_id`` falls through to the
    # prober's own tenant and the row lands in the prober's readable scope.
    # Measured through the caller's own ``GET /policy/decisions``, with the HTTP
    # bodies already identical::
    #
    #     POST /browse/{foreign}/preview  -> 404   decisions visible to prober: 0
    #     POST /browse/{absent}/preview   -> 404   decisions visible to prober: 1
    #
    # A row appearing exactly when the id is free answers the question the 404
    # collapse exists to refuse, and the row even confirms it was filed into the
    # prober's tenant. Every sibling dataset-resolving route already routes its
    # refusals through ``policy.evaluate_dataset_scope_refusal``, which files to
    # the owning tenant or the reserved ``unresolved`` scope; preview was the one
    # caller that did not, so this is a missed caller rather than a new design.
    dataset = get_dataset(dataset_id)
    if not dataset:
        refusal = evaluate_dataset_scope_refusal(user, dataset_id)
        ingest_event(
            event_type="browse.preview",
            actor=user,
            dataset_id=dataset_id,
            decision="denied",
            reason="dataset_not_found",
            decision_id=refusal.decision_id,
            details={"policy_decision_id": refusal.decision_id},
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
        _refuse(user, dataset, decision)

    invalid_pagination = _invalid_pagination_reason(limit, offset)
    if invalid_pagination is not None:
        reason, message = invalid_pagination
        ingest_event(
            event_type="browse.preview",
            actor=user,
            dataset_id=dataset_id,
            decision="denied",
            reason=reason,
            decision_id=decision.decision_id,
            details={
                "purpose": purpose,
                "policy_decision_id": decision.decision_id,
                "requested_limit": limit,
                "requested_offset": offset,
            },
        )
        raise ValueError(message)

    rows = _sample_rows(dataset)

    # Masking is a floor rather than a best effort: the obligation is the policy's
    # instruction, and a column the dataset itself declares as PII is masked even
    # if a future policy change stopped listing it.
    obligated = decision.obligations.get("masking") or []
    # The floor is every column the dataset's own declarations require masking
    # for, not just the ``pii`` bool: POL-003 names sensitive and confidential
    # too, and a floor narrower than the policy would release a column the
    # policy masked if a future policy change stopped listing it.
    declared = [rule["column"] for rule in masked_column_rules(dataset.schema)]
    masked_columns = list(dict.fromkeys([*obligated, *declared]))

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



def _refuse(user: str, dataset: Dataset, decision: Any) -> None:
    """Raise the refusal a denied decision deserves, without disclosing existence.

    A caller outside the dataset's tenant must not be able to tell a dataset it
    may not see from one that is not there. Measured before this change:

        GET /browse/zeta-b/schema?user=analyst          -> 403 tenant boundary denied
        GET /browse/no-such-dataset/schema?user=analyst -> 404 dataset not found

    Dataset ids are enumerable, so that pair is an existence oracle over the whole
    catalog - the same disclosure the discovery surface was repaired to close, and
    an earlier commit in this series left it open here on the reasoning that "the
    caller already names the id". Naming an id is not knowing it exists, so that
    reasoning was wrong.

    Nothing is lost for compliance: the policy decision row and the audit event
    are written before this raises, both carrying the real reason, so a denial is
    still evidence. Only the client is told less. A denial for any other cause -
    insufficient role, critical sensitivity, export purpose - stays a 403, because
    a caller inside the tenant may legitimately know the dataset exists.
    """
    if not can_access_tenant(user, dataset.tenant_id):
        raise KeyError("dataset not found")
    raise PermissionError(decision.reason)

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
        _refuse(user, dataset, decision)

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
        # The full LIN-004 set, column scope included: this route is already
        # publishing the per-column statistics those rules read, behind the
        # policy gate that just allowed the caller.
        "quality_warnings": quality_warning_summary(dataset, include_column_scope=True),
    }


def dataset_profile(dataset_id: str, user: str, purpose: str = "analysis") -> Dict[str, Any]:
    """Return one dataset's profile behind the same gate as its schema.

    The payload is the governed content itself - dataset ``profile`` (row counts,
    quality issues) and per-column ``quality_issues`` plus null/distinct ratios -
    which ``catalog.discovery_view`` and ``catalog.discovery_column_view``
    deliberately withhold from the actor-less discovery surface. Stripping those
    fields would leave the route with nothing to say, so the release is gated and
    audited instead, exactly as ``schema()`` is.
    """
    dataset = get_dataset(dataset_id)
    if not dataset:
        raise KeyError("dataset not found")

    decision = evaluate(subject=user, resource=dataset_id, action="schema", purpose=purpose)
    if decision.effect != "allow":
        ingest_event(
            event_type="browse.profile",
            actor=user,
            dataset_id=dataset_id,
            decision="denied",
            reason=decision.reason,
            decision_id=decision.decision_id,
            details={"purpose": purpose, "policy_decision_id": decision.decision_id},
        )
        _refuse(user, dataset, decision)

    ingest_event(
        event_type="browse.profile",
        actor=user,
        dataset_id=dataset_id,
        decision="allowed",
        reason=decision.reason,
        decision_id=decision.decision_id,
        details={"purpose": purpose, "policy_decision_id": decision.decision_id},
    )
    return {**get_dataset_profile(dataset_id), "policy_decision_id": decision.decision_id}
