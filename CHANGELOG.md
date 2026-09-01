# Changelog

## Unreleased

### Changed

- Replaced generic organization-owned `AuditEvent` field names with bounded-context-specific `audit_event_id`, `actor_subject`, `audit_action`, `resource_reference`, `audit_result`, `policy_decision_id`, `audit_reason`, and `audit_details` names.
- Renamed SQLite/Postgres `audit_events` columns to semantic snake_case names, including `event_payload`, while preserving the existing primary-key and UPSERT behavior.
- Renamed the Postgres audit lookup index to `idx_audit_events_tenant_resource_reference_created` without changing tenant/resource/time query locality.
- Propagated the semantic audit vocabulary through browse, connector, query-orchestration, catalog, evidence-store, and `AuditEventStore` protocol code.

### Compatibility

- Existing external JSON keys `id`, `actor`, `action`, `resource`, `result`, `decision_id`, `reason`, and `details` remain accepted/serialized through the Pydantic adapter boundary.
- Existing read-only Python `AuditEvent` generic property access remains available as a compatibility shim; new ContextualWisdomLab code uses semantic fields.
- Historical persisted event JSON remains readable without payload rewrite.
- Legacy `resource=` evidence-list filtering remains accepted only at the compatibility boundary and is translated to `resource_reference=`.

### Verification

- Added `tests/test_audit_event_naming_contract.py` to pin domain aliases, legacy deserialization/serialization, SQLite schema migration/data retention, and filter compatibility.
- Added architecture, doctoring, and product/technical gap documentation for the migration and bounded-context rationale.
