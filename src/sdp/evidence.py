from __future__ import annotations

import os

from sdp_core import AuditEvent, PolicyDecision, SQLiteEvidenceStore

EvidenceStore = SQLiteEvidenceStore | None

_STORE: EvidenceStore = SQLiteEvidenceStore(os.environ["SDP_SQLITE_PATH"]) if os.environ.get("SDP_SQLITE_PATH") else None
_POLICY_DECISION_LOG: list[PolicyDecision] = []


def configure_evidence_store(store: EvidenceStore) -> EvidenceStore:
    global _STORE
    previous = _STORE
    _STORE = store
    return previous


def has_configured_evidence_store() -> bool:
    return _STORE is not None


def record_policy_decision(decision: PolicyDecision) -> PolicyDecision:
    if _STORE:
        _STORE.record_decision(decision)
    else:
        _POLICY_DECISION_LOG.append(decision)
    return decision


def append_audit_event(event: AuditEvent) -> AuditEvent:
    if _STORE:
        _STORE.append_event(event)
    return event


def list_persisted_audit_events(*, resource: str | None = None, limit: int = 100) -> list[AuditEvent]:
    if not _STORE:
        return []
    return _STORE.list_events(resource=resource, limit=limit)


def list_policy_decisions(*, resource: str | None = None, limit: int = 100) -> list[PolicyDecision]:
    if _STORE:
        return _STORE.list_decisions(resource=resource, limit=limit)

    decisions = [
        decision
        for decision in reversed(_POLICY_DECISION_LOG)
        if not resource or decision.resource == resource
    ]
    return decisions[:limit]


def list_persisted_policy_decisions(*, resource: str | None = None, limit: int = 100) -> list[PolicyDecision]:
    if not _STORE:
        return []
    return _STORE.list_decisions(resource=resource, limit=limit)
