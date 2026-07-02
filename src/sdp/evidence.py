from __future__ import annotations

import os

from sdp_core import AuditEvent, PolicyDecision, SQLiteEvidenceStore

EvidenceStore = SQLiteEvidenceStore | None

_STORE: EvidenceStore = SQLiteEvidenceStore(os.environ["SDP_SQLITE_PATH"]) if os.environ.get("SDP_SQLITE_PATH") else None


def configure_evidence_store(store: EvidenceStore) -> EvidenceStore:
    global _STORE
    previous = _STORE
    _STORE = store
    return previous


def record_policy_decision(decision: PolicyDecision) -> PolicyDecision:
    if _STORE:
        _STORE.record_decision(decision)
    return decision


def append_audit_event(event: AuditEvent) -> AuditEvent:
    if _STORE:
        _STORE.append_event(event)
    return event


def list_persisted_audit_events(*, resource: str | None = None, limit: int = 100) -> list[AuditEvent]:
    if not _STORE:
        return []
    return _STORE.list_events(resource=resource, limit=limit)
