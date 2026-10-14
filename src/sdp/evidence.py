from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

from sdp_core import AuditEvent, PolicyDecision, PostgresEvidenceStore, SQLiteEvidenceStore
from sdp_core.stores import _audit_tenant_id, _policy_tenant_id

EvidenceStore = SQLiteEvidenceStore | PostgresEvidenceStore | None


def _build_configured_evidence_store(environ: Mapping[str, str]) -> EvidenceStore:
    if environ.get("SDP_DATABASE_URL"):
        return PostgresEvidenceStore(
            environ["SDP_DATABASE_URL"],
            sslmode=environ.get("SDP_DATABASE_SSLMODE"),
        )
    if environ.get("SDP_SQLITE_PATH"):
        return SQLiteEvidenceStore(environ["SDP_SQLITE_PATH"])
    return None


_STORE: EvidenceStore = _build_configured_evidence_store(os.environ)
# Every gated route evaluates policy before refusing, so an unauthenticated
# caller can add one row per request to whichever in-memory list is unbounded.
# Both fallback lists are therefore capped, and ``catalog`` imports
# ``MAX_IN_MEMORY_AUDIT_EVENTS`` from here rather than declaring its own number:
# the previous round capped ``catalog._AUDIT_LOG`` at a local 2000 while
# ``append_audit_event`` kept appending the *same* event to the unbounded list
# below, so the cap did not bound memory at all. Measured over 2600 refused
# ``POST /browse/crm-customer-master/preview`` calls with no store configured:
#
#     catalog._AUDIT_LOG        = 2000   (capped)
#     evidence._AUDIT_EVENT_LOG = 2600   (grew with the request count)
#
# One number, imported, is what makes the two windows unable to drift again.
MAX_IN_MEMORY_POLICY_DECISIONS = 2000
MAX_IN_MEMORY_AUDIT_EVENTS = 2000

_POLICY_DECISION_LOG: list[PolicyDecision] = []
# Audit events recorded while no store is configured. Without this the event was
# returned to the caller and written nowhere, so the OIDC group-to-role mapping
# records - who was granted admin or platform-admin - were lost in the documented
# `uvicorn sdp.api:app` configuration while the API still handed back an
# `audit_event_id`. Policy decisions already had this fallback.
_AUDIT_EVENT_LOG: list[AuditEvent] = []

# Trimming a window makes "did this get recorded?" unanswerable from the window
# alone: once the cap is reached ``len()`` is constant, so a length comparison
# reads as "nothing was recorded" for every subsequent write. These counters are
# monotonic over the process, so the question stays answerable, and a count
# reported to a buyer does not silently stop rising at the cap.
_RECORDED_POLICY_DECISION_COUNT = 0
_RECORDED_AUDIT_EVENT_COUNT = 0


def configure_evidence_store(store: EvidenceStore) -> EvidenceStore:
    global _STORE
    previous = _STORE
    _STORE = store
    return previous


def has_configured_evidence_store() -> bool:
    return _STORE is not None


def record_policy_decision(decision: PolicyDecision) -> PolicyDecision:
    global _RECORDED_POLICY_DECISION_COUNT
    _RECORDED_POLICY_DECISION_COUNT += 1
    if _STORE:
        _STORE.record_decision(decision)
    else:
        _POLICY_DECISION_LOG.append(decision)
        if len(_POLICY_DECISION_LOG) > MAX_IN_MEMORY_POLICY_DECISIONS:
            del _POLICY_DECISION_LOG[:-MAX_IN_MEMORY_POLICY_DECISIONS]
    return decision


def append_audit_event(event: AuditEvent) -> AuditEvent:
    global _RECORDED_AUDIT_EVENT_COUNT
    _RECORDED_AUDIT_EVENT_COUNT += 1
    if _STORE:
        _STORE.append_event(event)
    else:
        _AUDIT_EVENT_LOG.append(event)
        if len(_AUDIT_EVENT_LOG) > MAX_IN_MEMORY_AUDIT_EVENTS:
            del _AUDIT_EVENT_LOG[:-MAX_IN_MEMORY_AUDIT_EVENTS]
    return event


def recorded_policy_decision_count() -> int:
    """How many policy decisions this process has recorded, ignoring trimming.

    ``len(_POLICY_DECISION_LOG)`` stops rising at the cap, so it cannot answer
    "was this decision recorded?" once a long-lived process has passed it.
    """
    return _RECORDED_POLICY_DECISION_COUNT


def recorded_audit_event_count() -> int:
    """How many audit events this process has recorded, ignoring trimming."""
    return _RECORDED_AUDIT_EVENT_COUNT


def decision_tenant_id(decision: PolicyDecision) -> str:
    """Return the tenant a policy decision belongs to, as the store files it."""
    return _policy_tenant_id(decision)


def audit_tenant_id(event: AuditEvent) -> str:
    """Return the tenant an audit event belongs to, as the store files it."""
    return _audit_tenant_id(event)


def tenant_is_in_scope(tenant_id: str, tenant_ids: list[str] | None) -> bool:
    """Match one row's tenant against a read scope (``None`` means every tenant)."""
    if tenant_ids is None:
        return True
    return tenant_id in tenant_ids


# Read the bounded in-memory logs through a snapshot, never the live list.
#
# ``reversed(_POLICY_DECISION_LOG)`` is a lazy iterator over the list itself,
# and ``record_policy_decision`` trims the front with
# ``del _POLICY_DECISION_LOG[:-MAX_IN_MEMORY_POLICY_DECISIONS]``. A reverse
# iterator whose list has its front removed mid-iteration re-visits shifted
# elements and skips others, so a page could contain the same ``decision_id``
# twice and silently omit that many real rows. Measured with two readers and two
# writers against a log already at its cap:
#
#     pages read 14303, pages containing a duplicated decision_id 142
#
# ``list(...)`` of a list is one C-level copy, so the snapshot is taken either
# side of a trim and never mid-trim; a lock is not needed on this read path. The
# append-then-trim pair is two steps, so a reader can briefly see one row past
# the cap - an extra row, not a torn page.
def _log_snapshot(log: list[Any]) -> list[Any]:
    """A point-in-time copy of a bounded log, safe to iterate."""
    return list(log)


def list_persisted_audit_events(
    *, resource: str | None = None, limit: int = 100, tenant_ids: list[str] | None = None
) -> list[AuditEvent]:
    if _STORE:
        return _STORE.list_events(resource=resource, limit=limit, tenant_ids=tenant_ids)

    events = [
        event
        for event in reversed(_log_snapshot(_AUDIT_EVENT_LOG))
        if (not resource or event.resource == resource)
        and tenant_is_in_scope(_audit_tenant_id(event), tenant_ids)
    ]
    return events[:limit]


def list_policy_decisions(
    *, resource: str | None = None, limit: int = 100, tenant_ids: list[str] | None = None
) -> list[PolicyDecision]:
    if _STORE:
        return _STORE.list_decisions(resource=resource, limit=limit, tenant_ids=tenant_ids)

    decisions = [
        decision
        for decision in reversed(_log_snapshot(_POLICY_DECISION_LOG))
        if (not resource or decision.resource == resource)
        and tenant_is_in_scope(_policy_tenant_id(decision), tenant_ids)
    ]
    return decisions[:limit]


def count_policy_decisions(
    *, resource: str | None = None, tenant_ids: list[str] | None = None
) -> tuple[int, bool]:
    """How many policy decisions exist in scope, and whether that is a lower bound.

    See ``catalog.count_audit_events`` for the measurement that made the
    published gauges wrong: both were ``len()`` of a 500-row page.
    """
    from .catalog import EVIDENCE_COUNT_CEILING

    decisions = list_policy_decisions(
        resource=resource, limit=EVIDENCE_COUNT_CEILING, tenant_ids=tenant_ids
    )
    return len(decisions), len(decisions) >= EVIDENCE_COUNT_CEILING


def list_persisted_policy_decisions(
    *, resource: str | None = None, limit: int = 100, tenant_ids: list[str] | None = None
) -> list[PolicyDecision]:
    if not _STORE:
        return []
    return _STORE.list_decisions(resource=resource, limit=limit, tenant_ids=tenant_ids)
