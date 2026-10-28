from __future__ import annotations

from typing import Any, Dict, List

from .authz import can_access_tenant
from .catalog import get_dataset, get_dataset_profile, ingest_event
from .domain import ColumnMetadata, Dataset
from sdp_core.contracts import masked_column_rules
from .policy import (
    ROW_FILTER_ABSENT_NOTE,
    ROW_FILTER_ENFORCEMENT_NOTE,
    evaluate,
    evaluate_dataset_scope_refusal,
)
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

# The declared spellings each sample family answers for. A warehouse writes
# ``double``, ``bigint``, ``float`` and ``datetime`` as often as the six keys
# ``_SAMPLE_DATATYPE_VALUES`` happened to hold, and a type with no entry fell
# through to ``f"{column.name}-sample-{n}"``: a dataset declaring
# ``touch_revenue_krw: double`` was served the string
# ``"touch_revenue_krw-sample-1"``, which is not merely synthetic but unparseable
# as its own declared type, so a consumer binding the rows to the published
# schema breaks. One table, read by one picker.
_SAMPLE_DATATYPE_FAMILIES: Dict[str, tuple[str, ...]] = {
    "boolean": ("bool", "boolean"),
    "date": ("date",),
    "decimal": ("decimal", "double", "double precision", "float", "money", "numeric", "number", "real"),
    "integer": ("bigint", "int", "int2", "int4", "int8", "integer", "long", "serial", "smallint"),
    "iri": ("iri", "uri", "url"),
    "timestamp": ("datetime", "time", "timestamp", "timestamptz", "timestamp with time zone"),
}


def _sample_datatype_family(datatype: str) -> str | None:
    """Which sample family a declared datatype belongs to, or ``None``.

    Case and length modifiers are stripped, so ``DOUBLE PRECISION`` and
    ``numeric(18,2)`` resolve like ``double`` and ``numeric``. ``None`` is the
    honest answer for a type this sampler cannot shape a value like - the preview
    publishes those column names rather than letting the mismatch pass as data.
    """
    normalized = datatype.strip().lower().split("(")[0].strip()
    if not normalized:
        return None
    for family, spellings in _SAMPLE_DATATYPE_FAMILIES.items():
        if normalized in spellings or normalized == family:
            return family
    return None


def _sample_value(column: ColumnMetadata, row_index: int) -> str:
    """Pick this column's demo value for one sample row, deterministically."""
    values = _SAMPLE_COLUMN_VALUES.get(column.name)
    if not values:
        family = _sample_datatype_family(column.datatype)
        if family:
            values = _SAMPLE_DATATYPE_VALUES.get(family)
    if values:
        return values[row_index % len(values)]
    return f"{column.name}-sample-{row_index + 1}"


def _declared_source_row_count(dataset: Dataset) -> int | None:
    """The row count the catalog declares for this dataset's source, if any.

    Read from the dataset's own ``profile`` rather than recomputed, and ``None``
    when the profile declares none or declares it unparseably - absent is not
    zero, and a dataset with no declared size must not read as an empty one.
    """
    raw = (getattr(dataset, "profile", None) or {}).get("row_count")
    if isinstance(raw, bool) or not isinstance(raw, (int, float, str)):
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _untyped_sample_columns(dataset: Dataset) -> List[str]:
    """Columns whose sample value cannot be shaped like their declared type.

    Named in the response rather than left for a consumer to discover by parse
    failure. A column the demo seed describes by name is typed by that
    description, so it is not listed.
    """
    return [
        column.name
        for column in dataset.schema
        if column.name not in _SAMPLE_COLUMN_VALUES
        and _sample_datatype_family(column.datatype) is None
    ]


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

    # Declared, not applied: the rows below are sliced by offset/limit alone.
    declared_row_filter = decision.obligations.get("row_filter") or []

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
            # ``row_filter`` stood here, beside ``returned_rows``, and nothing
            # applied it: an auditor joining this row to its decision read a
            # department-scoped read of 2 rows that never happened. The predicate
            # stays recorded - it is the obligation the policy declared - under a
            # name that says what it is, with the enforcement fact beside it.
            "declared_row_filter": declared_row_filter,
            "row_filter_enforced": False,
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
        # The machine-readable half of that sentence, in the vocabulary the
        # sibling data-bearing route already publishes
        # (``/browse/query``'s ``execution.measurement_status`` /
        # ``rows_source`` / ``row_count_source``). Measured before this, the
        # preview's only provenance was the Korean note above, while
        # ``has_more: false`` with two rows said the preview had shown
        # everything - for ``crm-event`` the profile route says 54,000,000 rows.
        # An integrator who learned from ``/browse/query`` that simulated
        # figures are labelled had every reason to read these rows as real.
        "sample_provenance": {
            "rows_source": "fixed_mock_sample",
            "measurement_status": "synthetic_sample_no_real_data",
            "row_count_source": "fixed_sample_size_below_catalog_profile_estimate",
            "sample_row_count": len(masked),
            # What the catalog declares the source holds, so ``has_more: false``
            # cannot be read as "this is the whole dataset". ``None`` when the
            # dataset declares no row count - absent, not zero.
            "declared_source_row_count": _declared_source_row_count(dataset),
            # Columns whose sample value cannot be shaped like the type they are
            # declared as; a consumer binding rows to the published schema will
            # fail to parse exactly these.
            "untyped_sample_columns": _untyped_sample_columns(dataset),
        },
        "policy_decision_id": decision.decision_id,
        # ``applied_row_filter`` stood here. The name was the defect: it asserted
        # that a row-level control governed the rows above, and the slice above
        # applies no predicate at all. Grouped like ``masking_summary``, and
        # published for every read so that silence cannot be read as "no
        # row-level obligation was declared" either.
        "row_filter_summary": {
            "declared_predicates": declared_row_filter,
            "filter_enforced": False,
            "enforcement_note": (
                ROW_FILTER_ENFORCEMENT_NOTE if declared_row_filter else ROW_FILTER_ABSENT_NOTE
            ),
        },
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
        # The absent-id refusal is filed, like every sibling route's. Raising
        # ``KeyError`` here without filing left this route the only
        # dataset-scoped surface whose evidence differs between "not yours" and
        # "does not exist", and the difference is published **without a
        # credential**: ``GET /metrics`` carries the global
        # ``sdp_audit_events_observed_total`` and
        # ``sdp_policy_decisions_observed_total`` gauges, so reading them,
        # calling this route with a candidate id and reading them again answered
        # the question the identical 404 exists to refuse. Measured, both
        # answering 404::
        #
        #     GET /browse/{id}/schema    foreign +1/+1    absent +0/+0
        #     POST /browse/{id}/preview  foreign +1/+1    absent +1/+1
        #
        # ``evaluate_dataset_scope_refusal`` is what keeps filing from becoming
        # the leak itself: it files to the owning tenant or the reserved
        # ``unresolved`` scope, never to the prober's, so the owning tenant's
        # auditor still sees attempts on its own assets while the prober's own
        # ledger learns nothing. The earlier existence-oracle guard measured
        # that tenant-scoped ledger and read 0/0 here, correctly - its premise
        # was a channel that needs a credential, and this one needs none.
        refusal = evaluate_dataset_scope_refusal(user, dataset_id)
        ingest_event(
            event_type="browse.schema",
            actor=user,
            dataset_id=dataset_id,
            decision="denied",
            reason="dataset_not_found",
            decision_id=refusal.decision_id,
            details={"policy_decision_id": refusal.decision_id},
        )
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
