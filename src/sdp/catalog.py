from __future__ import annotations

import re
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

from sdp_core import buyer_demo_datasets
from sdp_core.contracts import REQUIRED_METADATA_FIELDS

from .profile_provenance import (
    declared_unavailable_metrics,
    profile_metric_provenance,
)
from .quality_warnings import quality_warning_summary

from .domain import (
    AuditEvent,
    ColumnMetadata,
    Dataset,
    DatasetCreateRequest,
    DatasetPatchRequest,
)
from .evidence import (
    MAX_IN_MEMORY_AUDIT_EVENTS,
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


# Connection-string keys that are locators rather than secrets. An ALLOW-list,
# not a deny-list of password-ish names: a deny-list leaks the moment a driver
# uses a key nobody listed, and that is exactly how the URL-only version of this
# function leaked. Anything not named here is dropped.
_SAFE_CONNECTION_KEYS = frozenset(
    {
        "account",
        "data source",
        "database",
        "dbname",
        "driver",
        "host",
        "hostaddr",
        "port",
        "server",
        "service_name",
        "sslmode",
        "warehouse",
    }
)

# Schemes that wrap another URL (``jdbc:postgresql://user:pw@host/db``). The
# wrapper makes ``urlsplit`` read the whole inner URL as a *path*, so the
# authority - and the userinfo in it - is never parsed.
_WRAPPER_SCHEMES = frozenset({"jdbc", "odbc"})


def _redacted_keyword_value_dsn(source_system: str) -> str:
    """Keep only the allow-listed locator keys of a keyword/value connection string."""
    tokens: list[str] = []
    for chunk in re.split(r"[;\s]+", source_system):
        if "=" not in chunk:
            continue
        key, _, value = chunk.partition("=")
        if key.strip().lower() in _SAFE_CONNECTION_KEYS:
            tokens.append(f"{key.strip()}={value}")
    return " ".join(tokens) if tokens else "redacted"


def redacted_source_system(source_system: str) -> str:
    """Describe a dataset's source system without the credentials its DSN may carry.

    ``source_system`` is a governed field that ``catalog.discovery_view``
    withholds, and a DSN routinely carries a password - in a URL's userinfo
    (``postgresql://user:secret@host/db``), as a keyword/value pair
    (``host=h user=u password=secret``), inside an ODBC string
    (``Driver={PostgreSQL};Uid=u;Pwd=secret;``), or behind a wrapper scheme
    (``jdbc:postgresql://u:secret@h/db``). The connector evidence needs the
    locator, never the secret, so this drops the credential on every path -
    including the authorized one, since no caller needs it.

    The first version of this function assumed ``source_system`` is always a URL
    with an authority, and returned the input unchanged when ``urlsplit`` found
    no host. Measured across ten real connection-string forms, **six leaked the
    secret verbatim**::

        postgresql://u:PW123@h:5432/db                 -> postgresql://h:5432/db      ok
        host=h port=5432 user=u password=PW123 dbname=db  -> unchanged                LEAK
        jdbc:postgresql://u:PW123@h:5432/db            -> unchanged                   LEAK
        Driver={PostgreSQL};Server=h;Uid=u;Pwd=PW123;  -> unchanged                   LEAK
        postgresql://h:5432/db password=PW123          -> unchanged                   LEAK
        Server=h;Database=db;User Id=u;Password=PW123; -> unchanged                   LEAK
        PW123                                          -> unchanged                   LEAK

    ``audited_patch_values`` is the one redaction on a patched ``source_system``,
    so the cleartext password was written three times into the audit event
    (``changes``, ``before``, ``after``) and returned by
    ``GET /catalog/datasets/{id}/audit?user=analyst`` - to the very roles for
    which every read route withholds ``source_system`` entirely. The existing
    test passed because it only ever patched the one form that worked.

    It now fails closed: a string without a parseable authority keeps only
    allow-listed locator keys, and a string with no recognizable structure
    becomes ``"redacted"`` rather than being echoed.
    """
    try:
        parts = urlsplit(source_system)
    except ValueError:
        return "redacted"

    # A wrapper scheme hides the real URL in the path; unwrap and re-parse once.
    if parts.scheme in _WRAPPER_SCHEMES and "//" in parts.path:
        inner = redacted_source_system(source_system.split(":", 1)[1])
        return f"{parts.scheme}:{inner}"

    if not parts.scheme:
        return _redacted_keyword_value_dsn(source_system)
    try:
        host = parts.hostname
    except ValueError:
        return f"{parts.scheme}://redacted"
    if host is None:
        # No authority: the remainder is not a locator we can trust to be
        # secret-free, so only the allow-listed keys of it survive.
        remainder = _redacted_keyword_value_dsn(parts.path)
        return f"{parts.scheme}:{remainder}" if remainder != "redacted" else f"{parts.scheme}:redacted"
    try:
        port = parts.port
    except ValueError:
        port = None
    authority = f"{host}:{port}" if port else host
    # The path can carry a trailing secret of its own
    # (``postgresql://h/db password=PW``), so it is filtered the same way.
    path = parts.path
    if "=" in path:
        safe = _redacted_keyword_value_dsn(path)
        path = f"/{safe}" if safe != "redacted" else "/redacted"
    return urlunsplit((parts.scheme, authority, path, "", ""))


# The same boundary at column granularity. The schema-history and schema-diff
# routes publish stored column signatures, so without this they re-published the
# per-column PII classification that discovery_view withholds.
_GOVERNED_COLUMN_FIELDS = ("pii", "quality_issues", "classification")


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


def mutation_response_view(dataset: Dataset) -> Dict[str, Any]:
    """Project a mutated dataset for the response that confirms the mutation.

    The four catalog mutations returned ``dataset.model_dump()`` verbatim, which
    carries ``source_system`` with its credential - userinfo *and* query - while
    every read surface withholds that field entirely
    (``_GOVERNED_DATASET_FIELDS``) and ``redacted_source_system``'s own docstring
    says the credential is dropped "on every path - including the authorized
    one, since no caller needs the credential". Measured on a dataset registered
    with ``postgresql://dsnuser:SUPERSEKRET123@analytics.dw:5432/crm?sslcert=TOKENINQUERY``:

        POST   /catalog/datasets/{id}/publish    -> 200, secret in response: True
        POST   /catalog/datasets/{id}/deprecate  -> 200, secret in response: True
        PATCH  /catalog/datasets/{id}            -> 200, secret in response: True

        GET    /catalog/datasets/{id}            -> secret in response: False
        GET    /catalog/datasets/{id}/jsonld     -> secret in response: False
        GET    /browse/{id}/schema               -> secret in response: False

    ``deprecate`` carries no ``source_system`` in its request at all and still
    handed it back, so the DSN the governance boundary says nobody may read was
    retrievable on demand by any admin-role principal - and copied into whatever
    logs, proxies and browser consoles handle the mutation response.

    Unlike ``discovery_view`` this keeps the governed fields: the response
    confirms what the mutation did, and an admin who just wrote the schema may
    see it back. Only the credential is removed.
    """
    projected = dataset.model_dump()
    source_system = projected.get("source_system")
    if isinstance(source_system, str):
        projected["source_system"] = redacted_source_system(source_system)
    return projected


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


GOOD_COMPLETENESS_BADGE_SCORE = 0.8


def completeness_badge(dataset: Dataset) -> str:
    """Grade a dataset's metadata completeness, never above its validation result.

    ``src/sdp_core/kpis.py`` publishes this guardrail on the
    ``metadata_completeness`` KPI, verbatim: **"Completeness must not hide failed
    validation."** The badge broke it. Measured on a dataset with no owner, no
    steward, no distributions and no mappings:

        GET /catalog/datasets/<id>/validate -> is_valid: false, critical: true
        GET /catalog/datasets/<id>          -> completeness_badge: "good"

    because the badge read only ``metadata_recommendation_score >= 0.8`` and
    never consulted validation. A dataset that fails validation critically is now
    ``invalid``; one that fails non-critically is at best ``partial``.

    The threshold also lived in two places - here and in the search-result
    projection - so it is defined once and both read it.
    """
    report = validate_metadata(dataset)
    if not report.get("is_valid", True):
        return "invalid" if report.get("critical") else "partial"
    if dataset.metadata_recommendation_score >= GOOD_COMPLETENESS_BADGE_SCORE:
        return "good"
    return "partial"


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
    published["completeness_badge"] = completeness_badge(dataset)
    # LIN-004's warnings, dataset-scope only. ``include_column_scope=False`` is
    # the same boundary the lines above enforce: a column-scope warning names a
    # column and reads per-column statistics this projection withholds, so the
    # count travels instead of the content and a short list cannot read as a
    # clean dataset. The governed schema route publishes the full set.
    published["quality_warnings"] = quality_warning_summary(
        dataset, include_column_scope=False
    )
    return published


# The in-memory fallback logs were unbounded lists, so any caller that can reach
# an audited route could grow process memory without limit. Denials stay audited -
# dropping them would hide exactly the attempts an auditor looks for - but the
# in-memory window is bounded, matching the observability ring buffer's design.
#
# The cap is imported from ``evidence`` rather than declared here. Capping this
# list alone did not bound memory: ``_record_audit_event`` writes each event to
# both lists, and ``evidence._AUDIT_EVENT_LOG`` had no cap, so 2600 refused
# requests left this list at 2000 and that one at 2600.


def _record_audit_event(event: AuditEvent) -> AuditEvent:
    append_audit_event(event)
    if not has_configured_evidence_store():
        _AUDIT_LOG.append(event)
        if len(_AUDIT_LOG) > MAX_IN_MEMORY_AUDIT_EVENTS:
            del _AUDIT_LOG[:-MAX_IN_MEMORY_AUDIT_EVENTS]
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


def _commit_dataset_with_evidence(dataset: Dataset, event: AuditEvent) -> Dataset:
    """Store a dataset, snapshot its schema and record its audit row, or undo all three.

    All four catalog mutations had the same three lines in the same order::

        _DATA[dataset_id] = updated
        _record_schema_snapshot(updated)
        _record_audit_event(payload)

    and the audit row is written **last**, through the configured evidence
    store. That store is a real external dependency in both documented
    deployments (``SDP_SQLITE_PATH`` for the Docker demo,
    ``SDP_DATABASE_URL`` for the paid-pilot profile), so its write can fail -
    a dropped table, a full disk, Postgres unreachable - and when it did, the
    mutation was already committed. Measured against a store whose
    ``append_event`` raises, with its ``record_decision`` healthy::

        PATCH /catalog/datasets/crm-customer-master {"description": ...}
          -> 400 {"error": "invalid_request", "reason": "request body is not valid"}
             description changed:  True
             audit rows for it:    0

        POST /catalog/datasets           -> 500, catalog row created
        POST .../publish, .../deprecate  -> 500, status changed

    Every one of them is the violation this product's central claim rules out:
    a governed write that landed with no evidence that it was authorised. The
    patch route additionally reported a **server-side storage failure as a 400
    "request body is not valid"**, telling the caller their request was
    malformed when nothing was wrong with it.

    So the write is undone when its evidence cannot be recorded. The previous
    dataset is restored - or the key removed, for a registration that had no
    previous value - and the schema snapshot this mutation appended is popped,
    before the store's exception is re-raised for the route to map. The policy
    decision recorded before the mutation is deliberately kept: authorization
    *was* evaluated and granted, and the ledger saying so while no audit row
    and no mutation exist is the honest record of a write that failed.

    This is not a transaction. Two writers in different processes against one
    Postgres store still have no serialisation point, and a failure *after* the
    store commits but before this function returns would leave the row written
    and the mutation rolled back. What it removes is the single-process case
    that the shipped configurations actually produce.
    """
    previous = _DATA.get(dataset.id)
    history = _SCHEMA_HISTORY.get(dataset.id)
    history_depth = len(history) if history is not None else None

    _DATA[dataset.id] = dataset
    _record_schema_snapshot(dataset)
    try:
        _record_audit_event(event)
    except Exception:
        # Undo in the reverse order, so an exception in the rollback itself
        # cannot leave the dataset visible with the snapshot already gone.
        appended = _SCHEMA_HISTORY.get(dataset.id)
        if appended is not None:
            if history_depth is None:
                del _SCHEMA_HISTORY[dataset.id]
            else:
                del appended[history_depth:]
        if previous is None:
            _DATA.pop(dataset.id, None)
        else:
            _DATA[dataset.id] = previous
        raise
    return dataset


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
        # LIN-003's acceptance criterion: the metric timestamp and the
        # computation scope. Without them these figures read as measurements
        # this service took, and it took none - there is no profiler here.
        "metric_provenance": profile_metric_provenance(dataset.profile),
        "declared_unavailable_metrics": declared_unavailable_metrics(),
    }


def datasets_in_scope(tenant_ids: list[str] | None) -> List[Dataset]:
    """Return the datasets a reader may see, scoped to a set of tenants.

    ``None`` means every tenant and is reserved for the explicit platform-admin
    crossing; an empty list yields nothing. The discovery surface previously
    iterated the whole catalog with no tenant predicate, so an unauthenticated
    caller received every tenant's inventory - ids, titles, owners and status -
    while the governed path refused the same dataset. ``src/sdp_core/kpis.py``
    publishes the guardrail that contradicts: "No unauthorized dataset existence
    disclosure."
    """
    if tenant_ids is None:
        return list(_DATA.values())
    allowed = set(tenant_ids)
    return [dataset for dataset in _DATA.values() if dataset.tenant_id in allowed]


def dataset_in_scope(dataset_id: str, tenant_ids: list[str] | None) -> Optional[Dataset]:
    """Return one dataset only when the reader's tenant scope covers it."""
    dataset = _DATA.get(dataset_id)
    if dataset is None:
        return None
    if tenant_ids is None or dataset.tenant_id in set(tenant_ids):
        return dataset
    return None



def get_join_candidates(
    dataset_id: str, *, limit: int = 10, tenant_ids: list[str] | None = None
) -> list[dict[str, Any]]:
    dataset = get_dataset_or_404(dataset_id)
    candidates = []

    dataset_columns = {column.name for column in dataset.schema}
    dataset_terms = {term for term in dataset.terms}
    # Scoped: an id the caller legitimately owns was a pivot that named its
    # neighbours in other tenants, together with their overlapping column names.
    for other in datasets_in_scope(tenant_ids):
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


# Imported, not duplicated: ``Dataset.metadata_completeness`` scores the same
# list. They were two lists of different lengths (7 vs 10), so a dataset the
# validator calls critically invalid still published
# ``metadata_completeness: 1.0``.
_REQUIRED_METADATA_FIELDS = list(REQUIRED_METADATA_FIELDS)


def _bump_version(version: str) -> str:
    parts = version.split(".")
    if len(parts) != 3:
        return "1.0.1"
    major, minor, patch = [int(part) for part in parts]
    return f"{major}.{minor}.{patch + 1}"


def _to_set(values: list[str] | None) -> set[str]:
    return set(values or [])


def _compiled_query_tokens(tokens: list[str]) -> list[re.Pattern[str]]:
    """Compile each search token once, for reuse across every dataset.

    ``_term_score`` compiled inside its own loop and ``search_catalog`` calls it
    once per dataset, making the cost datasets x tokens: at 1005 datasets a
    10-token query took 0.03s, 500 tokens 1.39s and 2000 tokens 5.10s.
    """
    return [re.compile(re.escape(token), re.IGNORECASE) for token in tokens if token]


def _term_score(dataset: Dataset, token_patterns: list[re.Pattern[str]], query: str) -> float:
    score = 0.0
    for token_re in token_patterns:
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
    tenant_ids: list[str] | None = None,
) -> list[SearchResult]:
    tokens = [t.strip() for t in query.split() if t.strip()]
    token_patterns = _compiled_query_tokens(tokens)
    if not tokens:
        return []

    by_token: list[SearchResult] = []
    tags_filter = _to_set(tags)
    domain_filter = _to_set(domain)
    owner_filter = _to_set(owner)
    sensitivity_filter = _to_set(sensitivity)
    status_filter = _to_set(status)
    license_filter = _to_set(license)

    for dataset in datasets_in_scope(tenant_ids):
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

        score = _term_score(dataset, token_patterns, query)
        if score > 0:
            by_token.append(SearchResult(dataset=dataset, score=score))

    by_token.sort(key=lambda row: row.score, reverse=True)
    return by_token[:limit]


def list_facet_counts(
    field: str, query: Optional[str] = None, *, tenant_ids: list[str] | None = None
) -> Dict[str, int]:
    if field not in {"domain", "owner", "sensitivity", "update_frequency", "license", "status"}:
        raise ValueError("unsupported facet field")

    if query:
        tokens = [t.strip() for t in query.split() if t.strip()]
    else:
        tokens = []
    token_patterns = _compiled_query_tokens(tokens)

    counts: Dict[str, int] = {}
    # An aggregate is a disclosure: the owner facet named another tenant's owner.
    for dataset in datasets_in_scope(tenant_ids):
        if tokens:
            row = SearchResult(dataset=dataset, score=_term_score(dataset, token_patterns, query))
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


def list_datasets(tenant_ids: list[str] | None = None) -> list[Dataset]:
    return datasets_in_scope(tenant_ids)


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
    """The distinct schema versions this dataset has had, oldest first.

    One entry per *snapshot* before this, which duplicated a version that had
    not changed: a snapshot is recorded on every mutation (it captures lineage,
    mappings, tags, status and scores as well as the columns, which is what
    drift detection reads), so three non-schema patches published
    ``["1.0.0", "1.0.0", "1.0.0", "1.0.0"]``. Every entry here is now
    addressable by ``get_dataset_schema_diff``, which resolves a version
    through a dict keyed on it and so could only ever reach one snapshot per
    version anyway - the listing advertised four and the diff served one.
    """
    get_dataset_or_404(dataset_id)
    history = _SCHEMA_HISTORY.get(dataset_id, [])
    versions: list[str] = []
    for entry in history:
        version = entry["schema_version"]
        if version not in versions:
            versions.append(version)
    return versions


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


# CAT-005's acceptance criterion names four things a catalog-write audit row
# must carry: the before/after diff, the actor, the timestamp and the **reason**.
# The first three were recorded; the reason was not. ``_build_dataset_payload``
# hardcodes ``reason="ok"`` - which is the row's *outcome*, not the caller's
# reason for the change - and only ``deprecate`` accepted one at all. Measured
# before this:
#
#     PATCH /catalog/datasets/{id} {"reason": "buyer audit reason"}
#       -> 200, details keys: after, before, changes, tenant_id  (no reason)
#
# A caller's reason was accepted with 200 and dropped, because the request
# models declare no such field and pydantic ignores an extra one.
#
# The reason is read from the raw request payload rather than added to
# ``DatasetCreateRequest``/``DatasetPatchRequest`` deliberately: it is metadata
# *about* the change, not dataset state, and those models' fields are a strict
# subset of ``Dataset``'s - an invariant ``tests/test_catalog_field_forwarding``
# asserts and a ``reason`` field would break.
#
# The key is published even when no reason was given, as ``None``. Omitting it
# would leave a reader unable to tell "the caller gave no reason" from "this
# surface does not record one", which is the distinction the row exists to make.
CHANGE_REASON_DETAIL_KEY = "change_reason"


def change_reason_details(change_reason: str | None) -> dict[str, Any]:
    """The audit-detail fragment carrying a caller-supplied change reason."""
    return {CHANGE_REASON_DETAIL_KEY: change_reason}


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


# Every catalog mutation is a read-modify-write over this module's dicts:
# ``get_dataset_or_404`` then ``model_dump`` then ``_bump_version`` then
# ``_DATA[id] = updated``. FastAPI runs these ``def`` handlers in a worker
# threadpool, so two requests genuinely interleave, and nothing serialised them.
# Measured by forcing the interleaving (pause one writer between its read and
# its write) through ``patch_dataset``:
#
#     PATCH description=FIRST   -> 200
#     PATCH steward=SECOND      -> 200
#     stored: description=FIRST, steward=<unchanged>, version=1.0.1
#     audit: success {"description": "FIRST"}
#     audit: success {"steward": "SECOND"}
#
# The lost write is bad; the audit row is worse. This product's governance
# invariant is that a decision and an audit event accompany every governed
# write, and here the ledger certified a change that is not in the store - the
# event is built from the writer's own ``updates`` and never re-read from
# ``_DATA``. Unsynchronised, 50 concurrent patches advanced the version by 25.
#
# Generated ids had the same shape of defect at the check-then-store boundary:
# eight concurrent id-less creates each answered 200 and the catalog grew by
# five, because ``len(_DATA) + 1`` and ``if dataset_id in _DATA`` and the store
# write were three separate steps.
#
# Reentrant, because ``api`` holds this lock across a mutation *and* its graph
# mirror (two unsynchronised steps let the catalog and the graph disagree
# permanently) and the mutation it calls acquires the lock again.
_MUTATION_LOCK = threading.RLock()


@contextmanager
def catalog_mutation_lock() -> Iterator[None]:
    """Hold the catalog mutation lock across a caller-composed critical section.

    ``api`` uses this to make "mutate the catalog, then mirror it into the
    graph" one atomic step. Two concurrent schema patches otherwise applied in
    one order to the catalog and the opposite order to the graph, leaving the
    graph holding a ``pii: true`` column the catalog does not declare - which
    ``/search/semantic`` then served and ``/browse/{id}/schema`` could not mask,
    because for the catalog that column does not exist.
    """
    with _MUTATION_LOCK:
        yield


def _next_generated_dataset_id() -> str:
    """The first free ``dataset-NNN`` id. Call with the mutation lock held.

    ``len(_DATA) + 1`` collided for two independent reasons: concurrently,
    several callers computed the same number before any of them stored; and
    sequentially, the count says nothing about which ids are taken once a
    caller has registered a ``dataset-NNN`` id of its own. Scanning for the
    first free id answers the question actually being asked.
    """
    index = 1
    while f"dataset-{index:03d}" in _DATA:
        index += 1
    return f"dataset-{index:03d}"


class DatasetAlreadyExists(ValueError):
    """A registration naming an id the catalog already holds.

    A distinct type because the route has to tell this apart from a malformed
    body: ``pydantic.ValidationError`` is also a ``ValueError``, so an
    ``except ValueError`` arm cannot say which of the two it caught. A
    duplicate id is the client asking for a second dataset under one name -
    409 - while a malformed body is 400.
    """


def register_dataset(
    payload: DatasetCreateRequest,
    *,
    actor: str = "system",
    decision_id: str | None = None,
    change_reason: str | None = None,
    before_commit: Callable[[str, List[str]], None] | None = None,
) -> Dataset:
    with _MUTATION_LOCK:
        return _register_dataset_locked(
            payload,
            actor=actor,
            decision_id=decision_id,
            change_reason=change_reason,
            before_commit=before_commit,
        )


def _register_dataset_locked(
    payload: DatasetCreateRequest,
    *,
    actor: str = "system",
    decision_id: str | None = None,
    change_reason: str | None = None,
    before_commit: Callable[[str, List[str]], None] | None = None,
) -> Dataset:
    """Register one dataset. Call with the mutation lock held.

    ``before_commit`` receives the id this call is about to take and the
    column names it will declare, and may refuse the registration by raising.
    It exists because the caller's own precondition - that the graph mirror
    ``api`` writes next will not have to reclassify an existing node - cannot
    be checked before this function runs: when the request omits ``id``, the
    id is assigned *here*, and a check run outside against ``payload.id``
    tests ``None``. Raising from the hook leaves nothing written, so a refused
    registration is a refusal rather than a half-applied mutation.
    """
    dataset_id = payload.id or _next_generated_dataset_id()

    if dataset_id in _DATA:
        raise DatasetAlreadyExists("dataset already exists")

    if before_commit is not None:
        before_commit(dataset_id, [column.name for column in payload.schema or []])

    now = datetime.now(timezone.utc)
    # Built from the request's own fields rather than a hand-written list of
    # them. The hand-written version silently dropped ``license``: ``Dataset``
    # has carried the field all along, ``DatasetCreateRequest`` did not expose
    # it, and when it was exposed this constructor still ignored it - so a
    # ``POST`` naming a licence answered 200 and stored the default. A catalog
    # whose licence cannot be set is missing the field a diligence reader checks
    # first, and ``metadata_completeness``'s own definition counts it.
    #
    # ``DatasetCreateRequest``'s fields are a strict subset of ``Dataset``'s
    # (asserted by ``tests/test_catalog_field_forwarding.py``), so the spread is
    # exact rather than lenient, and a field added to the request in future
    # reaches the stored dataset without a second edit here.
    dataset = Dataset(
        **{
            key: value
            for key, value in payload.model_dump().items()
            if key != "id"
        },
        id=dataset_id,
        status="registered",
        created_at=now,
        updated_at=now,
    )
    dataset.recompute_scores()
    return _commit_dataset_with_evidence(
        dataset,
        _build_dataset_payload(
            dataset,
            actor=actor,
            action="dataset.register",
            decision_id=decision_id,
            details=change_reason_details(change_reason),
        ),
    )


def patch_dataset(
    dataset_id: str,
    patch: DatasetPatchRequest,
    *,
    actor: str = "system",
    decision_id: str | None = None,
    change_reason: str | None = None,
) -> Dataset:
    with _MUTATION_LOCK:
        return _patch_dataset_locked(
            dataset_id,
            patch,
            actor=actor,
            decision_id=decision_id,
            change_reason=change_reason,
        )


def _patch_dataset_locked(
    dataset_id: str,
    patch: DatasetPatchRequest,
    *,
    actor: str = "system",
    decision_id: str | None = None,
    change_reason: str | None = None,
) -> Dataset:
    """Apply one patch. Call with the mutation lock held."""
    dataset = get_dataset_or_404(dataset_id)
    before = dataset.model_dump()
    data = dataset.model_dump()
    updates = patch.model_dump(exclude_unset=True)

    effective: dict[str, Any] = {}
    for key, value in updates.items():
        if key in {"tags", "terms", "related_datasets", "lineage_inputs", "lineage_outputs", "mappings", "profile"} and value is None:
            continue
        if value is not None:
            data[key] = value
            effective[key] = value

    # A patch that changes nothing changes nothing. ``{"actor": "admin"}`` names
    # no patchable field, and a body whose every value is ``None`` is skipped by
    # the rules above, yet both used to bump ``version``, move ``updated_at``
    # and append a schema snapshot - so the dataset claimed a modification time
    # for a request that modified nothing, and the version sequence stopped
    # counting changes. ``publish_dataset`` already models the answer: record the
    # no-op in the ledger and return the dataset untouched.
    if not effective:
        _record_audit_event(
            _build_dataset_payload(
                dataset,
                actor=actor,
                decision_id=decision_id,
                action="dataset.patch",
                details={
                    "changes": {},
                    "before": {},
                    "after": {},
                    "noop": True,
                    **change_reason_details(change_reason),
                },
            )
        )
        return dataset

    data["updated_at"] = datetime.now(timezone.utc)
    if "schema" in updates:
        data["schema_version"] = _bump_version(dataset.schema_version)

    data["version"] = _bump_version(dataset.version)
    updated = Dataset.model_validate(data)
    updated.recompute_scores()
    return _commit_dataset_with_evidence(
        updated,
        _build_dataset_payload(
            updated,
            actor=actor,
            decision_id=decision_id,
            action="dataset.patch",
            details={
                "changes": audited_patch_values(effective),
                "before": audited_patch_values({k: before[k] for k in effective}),
                "after": audited_patch_values({k: data[k] for k in effective}),
                **change_reason_details(change_reason),
            },
        ),
    )


def publish_dataset(
    dataset_id: str,
    *,
    actor: str = "system",
    decision_id: str | None = None,
    change_reason: str | None = None,
) -> Dataset:
    with _MUTATION_LOCK:
        return _publish_dataset_locked(
            dataset_id,
            actor=actor,
            decision_id=decision_id,
            change_reason=change_reason,
        )


def _publish_dataset_locked(
    dataset_id: str,
    *,
    actor: str = "system",
    decision_id: str | None = None,
    change_reason: str | None = None,
) -> Dataset:
    """Publish one dataset. Call with the mutation lock held."""
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
                details={
                    "status": dataset.status,
                    "noop": True,
                    **change_reason_details(change_reason),
                },
            )
        )
        return dataset

    data = dataset.model_dump()
    data["status"] = "published"
    data["updated_at"] = datetime.now(timezone.utc)
    data["version"] = _bump_version(dataset.version)
    published = Dataset.model_validate(data)
    published.recompute_scores()
    return _commit_dataset_with_evidence(
        published,
        _build_dataset_payload(
            published,
            actor=actor,
            decision_id=decision_id,
            action="dataset.publish",
            details={
                "previous_status": dataset.status,
                **change_reason_details(change_reason),
            },
        ),
    )


def deprecate_dataset(
    dataset_id: str,
    *,
    actor: str = "system",
    reason: str | None = None,
    decision_id: str | None = None,
) -> Dataset:
    with _MUTATION_LOCK:
        return _deprecate_dataset_locked(
            dataset_id, actor=actor, reason=reason, decision_id=decision_id
        )


def _deprecate_dataset_locked(
    dataset_id: str,
    *,
    actor: str = "system",
    reason: str | None = None,
    decision_id: str | None = None,
) -> Dataset:
    """Deprecate one dataset. Call with the mutation lock held."""
    dataset = get_dataset_or_404(dataset_id)

    # ``publish_dataset`` guards its already-published case; this did not, so a
    # replayed deprecate wrote a fresh "dataset.deprecate / success" row to the
    # governance ledger, bumped the version and appended a snapshot every time.
    # Measured over three identical calls: version 1.0.1 -> 1.0.2 -> 1.0.3, three
    # audit rows, three snapshots - a ledger reader could not tell a retried
    # request from three deliberate deprecations.
    if dataset.status == "deprecated":
        _record_audit_event(
            _build_dataset_payload(
                dataset,
                actor=actor,
                decision_id=decision_id,
                action="dataset.deprecate",
                details={
                    "status": dataset.status,
                    "noop": True,
                    **change_reason_details(reason),
                },
            )
        )
        return dataset

    dataset_data = dataset.model_dump()
    dataset_data["status"] = "deprecated"
    dataset_data["version"] = _bump_version(dataset.version)
    dataset_data["updated_at"] = datetime.now(timezone.utc)
    deprecated = Dataset.model_validate(dataset_data)
    deprecated.recompute_scores()
    return _commit_dataset_with_evidence(
        deprecated,
        _build_dataset_payload(
            deprecated,
            actor=actor,
            action="dataset.deprecate",
            decision_id=decision_id,
            details=change_reason_details(reason),
        ),
    )


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


# A published count must not be the size of the page it was read from.
#
# ``sdp_request_observations_total`` had this defect and was fixed; the audit and
# policy gauges were read the same way and were left behind. Measured with 700
# governed mutations in the ledger::
#
#     catalog._AUDIT_LOG                              700
#     /metrics sdp_audit_events_observed_total         500
#     /enterprise/evidence-pack audit_event_count      500
#     /enterprise/observability audit_events_observed  500
#
# Three published surfaces reported 500 for 700 events, because each read
# ``list_*(limit=500)`` and took ``len()`` of the page. A counter that cannot
# exceed its page is not a counter, and these are the numbers a buyer's
# procurement reader uses to judge whether the governance trail is real.
#
# The ceiling exists because the store-backed path needs a bound, and a count
# that hits it is published as a **lower bound** rather than as the count - the
# same rule the rest of this product follows for a truncated list.
EVIDENCE_COUNT_CEILING = 100_000


def count_audit_events(
    *, resource: str | None = None, tenant_ids: list[str] | None = None
) -> tuple[int, bool]:
    """How many audit events exist in scope, and whether that is a lower bound.

    Scoped exactly as :func:`list_audit_events` scopes its page, so the count
    and the page agree about what they are counting.
    """
    events = list_audit_events(
        limit=EVIDENCE_COUNT_CEILING, resource=resource, tenant_ids=tenant_ids
    )
    return len(events), len(events) >= EVIDENCE_COUNT_CEILING


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
