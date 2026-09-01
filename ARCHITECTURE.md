# Architecture

Semantic Data Portal is an ontology-driven catalog and governance application with a reusable `sdp_core` library boundary.

## Product boundaries

- `src/sdp_core/` owns reusable domain contracts, readiness manifests, source-connector protocols, and SQLite/Postgres evidence-store implementations.
- `src/sdp/` owns application orchestration, policy enforcement, catalog workflows, connector adapters, HTTP-facing behavior, and buyer-demo surfaces.
- Governed browse/query/catalog mutations evaluate policy before access and emit durable audit evidence.

## Governance evidence boundary

`PolicyDecision` is the authorization/explanation aggregate. `AuditEvent` is the append-oriented evidence aggregate produced by governed operations. The causal link is `policy_decision_id` when a policy decision exists.

Authoritative AuditEvent ubiquitous language is:

`audit_event_id`, `actor_subject`, `audit_action`, `resource_reference`, `audit_result`, `policy_decision_id`, `audit_reason`, `audit_details`, `created_at`.

Legacy JSON keys (`id`, `actor`, `action`, `resource`, `result`, `decision_id`, `reason`, `details`) are external compatibility aliases only. New organization-owned code must not treat those aliases as its domain vocabulary.

## Persistence

SQLite is the local/demo evidence store; Postgres is the managed paid-pilot store. Both persist semantic audit-event columns. Historical JSON payloads remain readable through Pydantic aliases.

The Postgres audit query index is `(tenant_id, resource_reference, created_at DESC)`, preserving tenant/resource/time locality. Audit-event UPSERT identity is `audit_event_id`. The rename adds no new foreign keys, partitions, queues, or read/write topology.

Schema migration details and locking/rollback constraints are recorded in `docs/doctoring/audit-event-semantic-identifiers.md`.

## Compatibility policy

A public or external contract may retain a generic field only at an explicit adapter boundary. Internal organization-owned models, persistence, events, configuration, and domain APIs use bounded-context-specific multiword names while following the host language's casing convention.

## Verification

Behavior- or contract-affecting changes require focused regression coverage plus the repository test suite. The audit-event naming contract is pinned in `tests/test_audit_event_naming_contract.py`; the full suite remains `PYTHONPATH=src pytest`.
