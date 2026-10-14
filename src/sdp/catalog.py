from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

from sdp_core import buyer_demo_datasets

from .domain import (
    AuditEvent,
    ColumnMetadata,
    Dataset,
    DatasetCreateRequest,
    DatasetPatchRequest,
)
from .evidence import (
    append_audit_event,
    audit_tenant_id,
    has_configured_evidence_store,
    list_persisted_audit_events,
    tenant_is_in_scope,
)


def _seed_datasets() -> List[Dataset]:
    return buyer_demo_datasets("customer_intelligence")


_DATA = {dataset.id: dataset for dataset in _seed_datasets()}
for _dataset in _DATA.values():
    _dataset.recompute_scores()
_AUDIT_LOG: list[AuditEvent] = []
_SCHEMA_HISTORY: dict[str, list[dict[str, Any]]] = {}


# The catalog discovery surface is served without an actor, so it must publish
# strictly less than the governed paths do. ``/browse/{id}/schema`` evaluates the
# tenant/role/sensitivity policy and audits the release of a dataset's column
# schema; a discovery payload that carried the same schema - with its ``pii``
# flags - plus the source-system connection string would make that denial
# decorative. These fields therefore stay behind the governed path.
_GOVERNED_DATASET_FIELDS = ("schema", "source_system", "profile", "tenant_id")


def redacted_source_system(source_system: str) -> str:
    """Describe a dataset's source system without the credentials its DSN may carry.

    ``source_system`` is a governed field that ``catalog.discovery_view``
    withholds, and a DSN routinely carries a password in its userinfo component
    (``postgresql://user:secret@host/db``). The connector evidence needs the
    locator, never the secret, so userinfo and query are dropped on every path -
    including the authorized one, since no caller needs the credential.
    """
    try:
        parts = urlsplit(source_system)
    except ValueError:
        return "redacted"
    if not parts.scheme:
        return source_system
    try:
        host = parts.hostname
    except ValueError:
        return f"{parts.scheme}://redacted"
    if host is None:
        return urlunsplit((parts.scheme, "", parts.path, "", ""))
    try:
        port = parts.port
    except ValueError:
        port = None
    authority = f"{host}:{port}" if port else host
    return urlunsplit((parts.scheme, authority, parts.path, "", ""))


# The same boundary at column granularity. The schema-history and schema-diff
# routes publish stored column signatures, so without this they re-published the
# per-column PII classification that discovery_view withholds.
_GOVERNED_COLUMN_FIELDS = ("pii", "quality_issues")


def discovery_column_view(column: Dict[str, Any]) -> Dict[str, Any]:
    """Copy one stored column signature without its governed fields."""
    return {key: value for key, value in column.items() if key not in _GOVERNED_COLUMN_FIELDS}


def _changed_governed_column_fields(before: Dict[str, Any], after: Dict[str, Any]) -> list[str]:
    """Name the withheld column fields whose values differ between two snapshots.

    A PII reclassification is real schema drift, so the diff still reports which
    governed field changed; only the classification itself stays withheld.
    """
    return [
        field
        for field in _GOVERNED_COLUMN_FIELDS
        if before.get(field) != after.get(field)
    ]


def audited_patch_values(values: Dict[str, Any]) -> Dict[str, Any]:
    """Project patched field values for an audit record.

    The audit feed is a read surface like any other, so it must not republish
    what ``discovery_view``/``discovery_column_view`` withhold: a patched
    ``source_system`` would put the DSN - credentials included - into the record,
    and a patched ``schema`` would put the per-column ``pii`` classification
    there. The change stays auditable: the field name is kept, the source keeps
    its non-secret locator, columns keep their names and types, and a profile
    keeps the list of keys that moved.
    """
    projected: Dict[str, Any] = {}
    for key, value in values.items():
        if key == "source_system" and isinstance(value, str):
            projected[key] = redacted_source_system(value)
        elif key == "schema" and isinstance(value, list):
            projected[key] = [
                discovery_column_view(column if isinstance(column, dict) else column.model_dump())
                for column in value
            ]
        elif key == "profile" and isinstance(value, dict):
            projected[key] = {"withheld_keys": sorted(value)}
        else:
            projected[key] = value
    return projected


def discovery_view(dataset: Dataset) -> Dict[str, Any]:
    """Project a dataset onto the fields the ungated catalog surface may publish.

    The per-column schema (and its ``pii`` flags), the source-system connection
    string, the row-count profile, and the owning tenant id are withheld; the
    column count is published in their place so discovery still describes the
    dataset's shape. ``tests/test_api.py`` pins the resulting key set so that a
    new ``Dataset`` field is an explicit publish-or-withhold decision.
    """
    published = dataset.model_dump()
    for field in _GOVERNED_DATASET_FIELDS:
        published.pop(field, None)
    published["schema_field_count"] = len(dataset.schema)
    published["metadata_completeness"] = dataset.metadata_completeness
    published["metadata_recommendation_score"] = dataset.metadata_recommendation_score
    published["completeness_badge"] = "good" if dataset.metadata_recommendation_score >= 0.8 else "partial"
    return published


def _record_audit_event(event: AuditEvent) -> AuditEvent:
    append_audit_event(event)
    if not has_configured_evidence_store():
        _AUDIT_LOG.append(event)
    return event


def _column_signature(columns: list[ColumnMetadata]) -> list[dict[str, Any]]:
    return [column.model_dump(exclude_unset=True) for column in columns]


def _make_schema_snapshot(dataset: Dataset) -> dict[str, Any]:
    return {
        "version": dataset.version,
        "schema_version": dataset.schema_version,
        "snapshot_at": datetime.now(timezone.utc).isoformat(),
        "schema": _column_signature(dataset.schema),
        "lineage_inputs": list(dataset.lineage_inputs),
        "lineage_outputs": list(dataset.lineage_outputs),
        "mappings": [mapping.model_dump() for mapping in dataset.mappings],
        "tags": list(dataset.tags),
        "terms": list(dataset.terms),
        "status": dataset.status,
        "quality_score": dataset.quality_score,
        "freshness_score": dataset.freshness_score,
    }


def _record_schema_snapshot(dataset: Dataset) -> None:
    history = _SCHEMA_HISTORY.setdefault(dataset.id, [])
    history.append(_make_schema_snapshot(dataset))


def _coerce_version_index(history: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {entry["schema_version"]: entry for entry in history}


def get_dataset_profile(dataset_id: str) -> dict[str, Any]:
    dataset = get_dataset_or_404(dataset_id)
    schema_profile: list[dict[str, Any]] = []
    for column in dataset.schema:
        schema_profile.append(
            {
                "name": column.name,
                "datatype": column.datatype,
                "null_ratio": column.nullable_ratio,
                "distinct_ratio": column.distinct_ratio,
                "quality_issues": list(column.quality_issues),
            }
        )
    return {
        "dataset_id": dataset.id,
        "row_count": dataset.profile.get("row_count"),
        "profile_updated_at": dataset.profile.get("updated_at"),
        "quality_issues": dataset.profile.get("quality_issues", []),
        "schema_profile": schema_profile,
    }


def get_join_candidates(dataset_id: str, *, limit: int = 10) -> list[dict[str, Any]]:
    dataset = get_dataset_or_404(dataset_id)
    candidates = []

    dataset_columns = {column.name for column in dataset.schema}
    dataset_terms = {term for term in dataset.terms}
    for other in _DATA.values():
        if other.id == dataset.id:
            continue
        if other.status not in {"published", "registered"}:
            continue
        overlap_terms = sorted(dataset_terms.intersection({term for term in other.terms}))
        overlap_columns = sorted(dataset_columns.intersection({column.name for column in other.schema}))
        score = len(overlap_terms) * 2 + len(overlap_columns)
        if score == 0:
            continue
        candidates.append(
            {
                "dataset_id": other.id,
                "title": other.title,
                "status": other.status,
                "score": score,
                "overlap_terms": overlap_terms,
                "overlap_columns": overlap_columns,
                "recommended_because": "business term / schema overlap",
            }
        )

    candidates.sort(key=lambda row: row["score"], reverse=True)
    return candidates[:limit]


def _initialize_schema_history() -> None:
    for _dataset in _DATA.values():
        _record_schema_snapshot(_dataset)


_initialize_schema_history()


@dataclass(frozen=True)
class SearchResult:
    dataset: Dataset
    score: float


_REQUIRED_METADATA_FIELDS = [
    "owner",
    "steward",
    "title",
    "description",
    "domain",
    "sensitivity",
    "update_frequency",
    "source_system",
    "schema",
    "distributions",
]


def _bump_version(version: str) -> str:
    parts = version.split(".")
    if len(parts) != 3:
        return "1.0.1"
    major, minor, patch = [int(part) for part in parts]
    return f"{major}.{minor}.{patch + 1}"


def _to_set(values: list[str] | None) -> set[str]:
    return set(values or [])


def _term_score(dataset: Dataset, tokens: list[str], query: str) -> float:
    score = 0.0
    for token in tokens:
        if token == "":
            continue
        token_re = re.compile(re.escape(token), re.IGNORECASE)
        if token_re.search(dataset.title):
            score += 1.0
        if token_re.search(dataset.description):
            score += 0.8
        for tag in dataset.tags:
            if token_re.search(tag):
                score += 0.5
        for term in dataset.terms:
            if token_re.search(term):
                score += 0.7
        for mapping in dataset.mappings:
            if token_re.search(mapping.concept):
                score += 0.6

    if dataset.sensitivity == "low":
        score += 0.1
    if query in {"활성", "활성 고객", "customer"}:
        for m in dataset.mappings:
            if m.concept == "활성 고객":
                score += 0.4
    return score


def search_catalog(
    query: str,
    *,
    tags: Optional[list[str]] = None,
    domain: Optional[list[str]] = None,
    owner: Optional[list[str]] = None,
    sensitivity: Optional[list[str]] = None,
    status: Optional[list[str]] = None,
    license: Optional[list[str]] = None,
    min_quality: Optional[float] = None,
    min_freshness: Optional[float] = None,
    include_inactive: bool = False,
    limit: int = 20,
) -> list[SearchResult]:
    tokens = [t.strip() for t in query.split() if t.strip()]
    if not tokens:
        return []

    by_token: list[SearchResult] = []
    tags_filter = _to_set(tags)
    domain_filter = _to_set(domain)
    owner_filter = _to_set(owner)
    sensitivity_filter = _to_set(sensitivity)
    status_filter = _to_set(status)
    license_filter = _to_set(license)

    for dataset in _DATA.values():
        if tags_filter and not tags_filter.intersection(set(dataset.tags)):
            continue
        if domain_filter and dataset.domain not in domain_filter:
            continue
        if owner_filter and dataset.owner not in owner_filter:
            continue
        if sensitivity_filter and dataset.sensitivity not in sensitivity_filter:
            continue
        if status_filter and dataset.status not in status_filter:
            continue
        if license_filter and dataset.license not in license_filter:
            continue
        if min_quality is not None and dataset.quality_score < min_quality:
            continue
        if min_freshness is not None and dataset.freshness_score < min_freshness:
            continue
        if not include_inactive and dataset.metadata_completeness < 0.8:
            continue

        score = _term_score(dataset, tokens, query)
        if score > 0:
            by_token.append(SearchResult(dataset=dataset, score=score))

    by_token.sort(key=lambda row: row.score, reverse=True)
    return by_token[:limit]


def list_facet_counts(field: str, query: Optional[str] = None) -> Dict[str, int]:
    if field not in {"domain", "owner", "sensitivity", "update_frequency", "license", "status"}:
        raise ValueError("unsupported facet field")

    if query:
        tokens = [t.strip() for t in query.split() if t.strip()]
    else:
        tokens = []

    counts: Dict[str, int] = {}
    for dataset in _DATA.values():
        if tokens:
            row = SearchResult(dataset=dataset, score=_term_score(dataset, tokens, query))
            if row.score <= 0:
                continue

        values = getattr(dataset, field)
        if isinstance(values, list):
            for value in values:
                counts[str(value)] = counts.get(str(value), 0) + 1
        else:
            counts[str(values)] = counts.get(str(values), 0) + 1
    return counts


def get_dataset(dataset_id: str) -> Dataset | None:
    return _DATA.get(dataset_id)


def get_dataset_or_404(dataset_id: str) -> Dataset:
    dataset = _DATA.get(dataset_id)
    if not dataset:
        raise KeyError("dataset not found")
    return dataset


def list_datasets() -> list[Dataset]:
    return list(_DATA.values())


def get_dataset_schema_history(dataset_id: str) -> dict[str, Any]:
    get_dataset_or_404(dataset_id)
    history = _SCHEMA_HISTORY.get(dataset_id, [])
    if not history:
        raise KeyError("no schema history found")
    # Project a copy: drift detection reads the stored snapshot, which keeps the
    # governed column fields.
    published = [
        {
            **entry,
            "schema": [discovery_column_view(column) for column in entry.get("schema", [])],
        }
        for entry in history
    ]
    return {
        "dataset_id": dataset_id,
        "history": published,
    }


def list_dataset_schema_versions(dataset_id: str) -> list[str]:
    get_dataset_or_404(dataset_id)
    history = _SCHEMA_HISTORY.get(dataset_id, [])
    return [entry["schema_version"] for entry in history]


def get_dataset_schema_diff(dataset_id: str, from_version: str, to_version: str) -> dict[str, Any]:
    get_dataset_or_404(dataset_id)
    history = _coerce_version_index(_SCHEMA_HISTORY.get(dataset_id, []))
    from_snapshot = history.get(from_version)
    to_snapshot = history.get(to_version)
    if not from_snapshot or not to_snapshot:
        available = sorted(history.keys())
        raise ValueError(
            f"schema_version not found: requested ({from_version}, {to_version}), available={available}"
        )

    before_names = {column["name"]: column for column in from_snapshot.get("schema", [])}
    after_names = {column["name"]: column for column in to_snapshot.get("schema", [])}
    added = [column["name"] for name, column in after_names.items() if name not in before_names]
    removed = [column["name"] for name, column in before_names.items() if name not in after_names]
    unchanged = [
        name
        for name in before_names.keys() & after_names.keys()
        if before_names[name] == after_names[name]
    ]
    changed = [
        {
            "name": name,
            "before": discovery_column_view(before_names[name]),
            "after": discovery_column_view(after_names[name]),
            "changed_withheld_fields": _changed_governed_column_fields(
                before_names[name], after_names[name]
            ),
        }
        for name in before_names.keys() & after_names.keys()
        if before_names[name] != after_names[name]
    ]
    return {
        "from_version": from_version,
        "to_version": to_version,
        "added_columns": sorted(added),
        "removed_columns": sorted(removed),
        "changed_columns": changed,
        "unchanged_columns": sorted(unchanged),
    }


def _build_dataset_payload(
    dataset: Dataset,
    *,
    actor: str,
    action: str,
    decision_id: str | None = None,
    details: dict[str, object] | None = None,
) -> AuditEvent:
    # The evidence store scopes an audit row by details["tenant_id"], so the
    # owning tenant has to travel with the event; the Dataset is right here.
    event_details: dict[str, object] = {"tenant_id": dataset.tenant_id}
    event_details.update(details or {})
    return AuditEvent(
        id=str(uuid4()),
        actor=actor,
        action=action,
        resource=dataset.id,
        decision_id=decision_id,
        result="success",
        reason="ok",
        details=event_details,
        created_at=datetime.now(timezone.utc),
    )


def validate_metadata(dataset: Dataset) -> Dict[str, object]:
    missing = [field for field in _REQUIRED_METADATA_FIELDS if not getattr(dataset, field, None)]
    return {
        "required_fields": list(_REQUIRED_METADATA_FIELDS),
        "missing": missing,
        "is_valid": len(missing) == 0,
        "critical": bool(missing),
        "completeness_score": dataset.completeness_score,
    }


def register_dataset(
    payload: DatasetCreateRequest,
    *,
    actor: str = "system",
    decision_id: str | None = None,
) -> Dataset:
    if not payload.id:
        dataset_id = f"dataset-{len(_DATA) + 1:03d}"
    else:
        dataset_id = payload.id

    if dataset_id in _DATA:
        raise ValueError("dataset already exists")

    now = datetime.now(timezone.utc)
    dataset = Dataset(
        id=dataset_id,
        tenant_id=payload.tenant_id,
        title=payload.title,
        description=payload.description,
        owner=payload.owner,
        steward=payload.steward,
        domain=payload.domain,
        source_system=payload.source_system,
        sensitivity=payload.sensitivity,
        update_frequency=payload.update_frequency,
        quality_score=payload.quality_score,
        freshness_score=payload.freshness_score,
        tags=list(payload.tags),
        terms=list(payload.terms),
        related_datasets=list(payload.related_datasets),
        schema=list(payload.schema),
        distributions=list(payload.distributions),
        mappings=list(payload.mappings),
        profile=dict(payload.profile),
        status="registered",
        created_at=now,
        updated_at=now,
    )
    dataset.recompute_scores()
    _DATA[dataset.id] = dataset
    _record_schema_snapshot(dataset)
    _record_audit_event(_build_dataset_payload(dataset, actor=actor, action="dataset.register", decision_id=decision_id))
    return dataset


def patch_dataset(
    dataset_id: str,
    patch: DatasetPatchRequest,
    *,
    actor: str = "system",
    decision_id: str | None = None,
) -> Dataset:
    dataset = get_dataset_or_404(dataset_id)
    before = dataset.model_dump()
    data = dataset.model_dump()
    updates = patch.model_dump(exclude_unset=True)

    for key, value in updates.items():
        if key in {"tags", "terms", "related_datasets", "lineage_inputs", "lineage_outputs", "mappings", "profile"} and value is None:
            continue
        if value is not None:
            data[key] = value

    data["updated_at"] = datetime.now(timezone.utc)
    if "schema" in updates:
        data["schema_version"] = _bump_version(dataset.schema_version)

    data["version"] = _bump_version(dataset.version)
    updated = Dataset.model_validate(data)
    updated.recompute_scores()
    _DATA[dataset_id] = updated
    _record_schema_snapshot(updated)
    _record_audit_event(
        _build_dataset_payload(
            updated,
            actor=actor,
            decision_id=decision_id,
            action="dataset.patch",
            details={
                "changes": audited_patch_values(updates),
                "before": audited_patch_values({k: before[k] for k in updates}),
                "after": audited_patch_values({k: data[k] for k in updates}),
            },
        )
    )
    return updated


def publish_dataset(
    dataset_id: str,
    *,
    actor: str = "system",
    decision_id: str | None = None,
) -> Dataset:
    dataset = get_dataset_or_404(dataset_id)
    validation = validate_metadata(dataset)
    if not validation["is_valid"]:
        raise ValueError("cannot publish dataset: metadata validation failed")

    if dataset.status == "published":
        _record_audit_event(
            _build_dataset_payload(
                dataset,
                actor=actor,
                decision_id=decision_id,
                action="dataset.publish",
                details={"status": dataset.status, "noop": True},
            )
        )
        return dataset

    data = dataset.model_dump()
    data["status"] = "published"
    data["updated_at"] = datetime.now(timezone.utc)
    data["version"] = _bump_version(dataset.version)
    published = Dataset.model_validate(data)
    published.recompute_scores()
    _DATA[dataset_id] = published
    _record_schema_snapshot(published)
    _record_audit_event(
        _build_dataset_payload(
            published,
            actor=actor,
            decision_id=decision_id,
            action="dataset.publish",
            details={"previous_status": dataset.status},
        )
    )
    return published


def deprecate_dataset(
    dataset_id: str,
    *,
    actor: str = "system",
    reason: str = "deprecated",
    decision_id: str | None = None,
) -> Dataset:
    dataset = get_dataset_or_404(dataset_id)
    dataset_data = dataset.model_dump()
    dataset_data["status"] = "deprecated"
    dataset_data["version"] = _bump_version(dataset.version)
    dataset_data["updated_at"] = datetime.now(timezone.utc)
    deprecated = Dataset.model_validate(dataset_data)
    deprecated.recompute_scores()
    _DATA[dataset_id] = deprecated
    _record_schema_snapshot(deprecated)
    _record_audit_event(
        _build_dataset_payload(
            deprecated,
            actor=actor,
            action="dataset.deprecate",
            decision_id=decision_id,
            details={"reason": reason},
        )
    )
    return deprecated


def list_audit_events(
    *,
    limit: int = 100,
    resource: str | None = None,
    tenant_ids: list[str] | None = None,
) -> list[AuditEvent]:
    """List audit events, optionally scoped to a set of tenants.

    ``tenant_ids=None`` means every tenant and is reserved for the explicit
    platform-admin crossing; an empty list yields no rows. The in-memory fallback
    log is filtered the same way the stores filter in SQL, so a reader sees the
    same scope whichever backend is configured.
    """
    events = list(_AUDIT_LOG)
    if resource:
        events = [event for event in events if event.resource == resource]
    events = [event for event in events if tenant_is_in_scope(audit_tenant_id(event), tenant_ids)]

    # Always merge: with no store configured the evidence module keeps its own
    # fallback log, which is where the OIDC mapping events live. Deduping by id
    # absorbs the overlap with _AUDIT_LOG.
    persisted = list_persisted_audit_events(resource=resource, limit=limit, tenant_ids=tenant_ids)
    by_id = {event.id: event for event in events}
    for event in persisted:
        by_id[event.id] = event
    events = list(by_id.values())

    events = sorted(events, key=lambda row: row.created_at, reverse=True)
    return events[:limit]


def get_dataset_audit_events(
    dataset_id: str, *, limit: int = 100, tenant_ids: list[str] | None = None
) -> list[AuditEvent]:
    return list_audit_events(limit=limit, resource=dataset_id, tenant_ids=tenant_ids)


def mapping_candidates(dataset: Dataset, concept: str) -> list[str]:
    aliases = {"고객": ["고객", "구매자"], "이탈": ["탈퇴", "이탈"], "활성 고객": ["유효 고객", "액티브 고객"]}
    normalized = concept.strip()
    candidates = set([normalized])
    for base, extra in aliases.items():
        if normalized == base:
            candidates.update(extra)
    return [candidate for candidate in dataset.terms if candidate in candidates]


def ingest_event(
    *,
    event_type: str,
    actor: str,
    dataset_id: str,
    decision: str,
    decision_id: str | None = None,
    reason: str = "",
    details: dict[str, object] | None = None,
) -> AuditEvent:
    # Stamp the owning tenant so the evidence store can scope the row. A denial
    # for a dataset that does not exist has no owning tenant; it is left for the
    # store to mark unresolved rather than attributed to a real tenant.
    event_details: dict[str, object] = {}
    dataset = _DATA.get(dataset_id)
    if dataset and dataset.tenant_id:
        event_details["tenant_id"] = dataset.tenant_id
    event_details.update(details or {})
    event = AuditEvent(
        id=str(uuid4()),
        actor=actor,
        action=event_type,
        resource=dataset_id,
        result=decision,
        decision_id=decision_id,
        reason=reason,
        details=event_details,
        created_at=datetime.now(timezone.utc),
    )
    return _record_audit_event(event)


def get_related_datasets(dataset_id: str) -> list[str]:
    dataset = get_dataset_or_404(dataset_id)
    return list(set(dataset.related_datasets))


def get_dataset_lineage(dataset_id: str) -> Dict[str, list[str]]:
    dataset = get_dataset_or_404(dataset_id)
    return {
        "dataset_id": dataset.id,
        "lineage_inputs": list(dataset.lineage_inputs),
        "lineage_outputs": list(dataset.lineage_outputs),
    }
