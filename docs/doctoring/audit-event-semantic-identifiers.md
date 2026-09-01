# Audit-event semantic identifier migration

## Bounded context

Semantic Data Portal owns governance evidence in `sdp_core.AuditEvent` and the SQLite/Postgres evidence stores. The audit event is not a generic transport envelope: it records who performed a governed action, which governed resource was involved, what outcome occurred, and which policy decision authorized or denied the action.

## Terminology repair

The authoritative organization-owned vocabulary is now:

| Legacy compatibility name | Authoritative name | Meaning |
| --- | --- | --- |
| `id` | `audit_event_id` | Stable identity of one governance audit event. |
| `actor` | `actor_subject` | Authenticated or synthetic subject that performed the action. |
| `action` | `audit_action` | Governed operation recorded by the event. |
| `resource` | `resource_reference` | Dataset or other governed resource reference. |
| `result` | `audit_result` | Outcome of the governed operation. |
| `decision_id` | `policy_decision_id` | Causal policy-decision identity, when present. |
| `reason` | `audit_reason` | Human/executable explanation for the result. |
| `details` | `audit_details` | Structured event-specific evidence. |
| `payload` (DB column) | `event_payload` | Serialized compatibility payload for the event. |

`created_at` and `tenant_id` were already semantically specific multiword names and are unchanged.

## Compatibility boundary

The Python domain model uses the authoritative names above. Pydantic aliases continue to accept and serialize the legacy external JSON keys `id`, `actor`, `action`, `resource`, `result`, `decision_id`, `reason`, and `details`; stored JSON payloads also remain in that legacy wire shape. Read-only compatibility properties preserve existing `AuditEvent.id`, `.actor`, `.action`, `.resource`, `.result`, `.decision_id`, `.reason`, and `.details` access for existing `sdp_core` consumers. New ContextualWisdomLab code must use the semantic fields.

The old `resource=` keyword on evidence-list APIs is accepted only at the adapter boundary and translated to `resource_reference`; conflicting old/new filters fail closed.

## Persistence migration

SQLite startup initialization creates the semantic schema for new databases and transactionally renames legacy `audit_events` columns in existing databases. The rename is data-preserving; the persisted JSON payload is not rewritten. `INSERT OR REPLACE` now targets `audit_event_id` and the semantic columns.

Postgres initialization creates the semantic schema for new databases and conditionally renames legacy columns inside the initialization transaction. `ON CONFLICT` changes from the legacy `id` column to `audit_event_id`, preserving the same primary-key/UPSERT semantics. The previous `idx_audit_events_tenant_resource_created` index is replaced by `idx_audit_events_tenant_resource_reference_created` on `(tenant_id, resource_reference, created_at DESC)`.

The rename does not change normalization: each audit row remains one event, policy decisions remain separately identified by `policy_decision_id`, and the JSON snapshot is evidence payload rather than a second normalized source of truth. No foreign-key relationship is added or removed. No partition key changes, new hot partitions, or read/write split changes are introduced.

Postgres column renames are metadata-only but take an `ACCESS EXCLUSIVE` table lock while the DDL runs. The current product performs store initialization during application startup, so deployments must coordinate the application version with this migration rather than run old SQL writers concurrently through the rename. Any failure in the initialization transaction rolls back the DDL. SQLite applies its rename statements inside the connection transaction and likewise rolls back on failure.

## Verification contract

`tests/test_audit_event_naming_contract.py` proves that:

- authoritative model fields use the semantic vocabulary;
- legacy JSON still deserializes and serializes with the old wire keys;
- a legacy SQLite database migrates to the semantic database columns without data loss;
- both `resource_reference=` and the compatibility-only `resource=` filter retrieve the migrated event.

Focused verification command:

```bash
PYTHONPATH=src pytest -q tests/test_audit_event_naming_contract.py
```

Repository verification remains:

```bash
PYTHONPATH=src pytest
```
