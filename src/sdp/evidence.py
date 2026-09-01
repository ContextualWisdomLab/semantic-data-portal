from __future__ import annotations

import os
from collections.abc import Mapping

from sdp_core import AuditEvent, PolicyDecision, PostgresEvidenceStore, SQLiteEvidenceStore

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


def append_audit_event(audit_event: AuditEvent) -> AuditEvent:
    if _STORE:
        _STORE.append_event(audit_event)
    return audit_event


def list_persisted_audit_events(
    *,
    resource_reference: str | None = None,
    limit: int = 100,
    **compatibility_filters: object,
) -> list[AuditEvent]:
    legacy_resource = compatibility_filters.pop("resource", None)
    if compatibility_filters:
        unexpected_names = ", ".join(sorted(compatibility_filters))
        raise TypeError(f"unexpected audit-event filter(s): {unexpected_names}")
    if resource_reference is not None and legacy_resource is not None:
        if resource_reference != legacy_resource:
            raise TypeError("resource_reference and legacy resource filter disagree")
    if resource_reference is None and legacy_resource is not None:
        resource_reference = str(legacy_resource)

    if not _STORE:
        return []
    return _STORE.list_events(resource_reference=resource_reference, limit=limit)


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
