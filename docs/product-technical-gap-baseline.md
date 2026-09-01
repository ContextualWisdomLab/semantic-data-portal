# Product and technical gap baseline

Updated for the audit-evidence naming repair on code head `953cbf30f4007b9cba914242423bfa518715583a`.

## Buyer product boundary

Semantic Data Portal is the ontology-driven catalog and governance plane above source systems and lower-level knowledge-graph products. The buyer workflow is: discover a governed dataset, understand its business meaning and lineage, preview/query it only after policy evaluation, and retain evidence that the governed operation was allowed, denied, or rejected.

The PRD/TRD divides responsibility into metadata, data-access, semantic, orchestration, and governance planes. `sdp_core` owns reusable domain contracts and evidence-store boundaries; `sdp` owns the FastAPI/application orchestration layer.

## DDD context map and ubiquitous language

| Bounded context | Aggregate/entity/value vocabulary | Owned invariants | Upstream/downstream relationship |
| --- | --- | --- | --- |
| Catalog | Dataset, dataset metadata, schema history, lineage | Metadata remains versioned and discoverable. | Supplies governed resource references to policy, browse/query, and audit. |
| Governance policy | Policy decision, policy obligation, actor context | Policy is evaluated before governed data access or mutation. | Upstream authority for audit evidence through `policy_decision_id`. |
| Audit evidence | Audit event, actor subject, audit action, resource reference, audit result | Every governed operation can be reconstructed from durable evidence without guessing generic field meaning. | Consumes policy decision identity and governed resource reference; exposed to buyer/operator audit views. |
| Browse/query | Preview request, query execution, masking obligation | Data access cannot bypass policy and audit recording. | Downstream of Catalog and Governance; emits Audit events. |
| Connector | Source connector, connector capability, connector control | Unsupported or uncontrolled source paths fail closed. | Bridges governed source systems into Browse/query. |

The Audit evidence aggregate now uses the authoritative organization-owned vocabulary `audit_event_id`, `actor_subject`, `audit_action`, `resource_reference`, `audit_result`, `policy_decision_id`, `audit_reason`, and `audit_details`. Legacy generic JSON names are compatibility aliases only; they are not the internal ubiquitous language.

## Naming-contract status

### Repaired in this change

- `AuditEvent.id` authoritative field -> `audit_event_id`.
- `AuditEvent.actor` -> `actor_subject`.
- `AuditEvent.action` -> `audit_action`.
- `AuditEvent.resource` -> `resource_reference`.
- `AuditEvent.result` -> `audit_result`.
- `AuditEvent.decision_id` -> `policy_decision_id`.
- `AuditEvent.reason` -> `audit_reason`.
- `AuditEvent.details` -> `audit_details`.
- `audit_events.id/actor/action/resource/result/decision_id/payload` database columns -> `audit_event_id/actor_subject/audit_action/resource_reference/audit_result/policy_decision_id/event_payload`.
- Audit-list internals and event-producing application callers now use semantic multiword names.

### Compatibility boundary

Pydantic aliases keep the legacy external JSON contract stable. Existing Python property access is retained read-only as an adapter seam. Existing `resource=` evidence-list calls are translated at the adapter boundary to `resource_reference=`. Persisted JSON remains in the prior wire shape so historical rows deserialize without rewrite.

### Remaining audit scope

The organization-wide naming sweep is not complete. Other owned contracts in this repository still contain candidate generic one-word names, including Dataset, PolicyDecision, query contracts, readiness manifests, configuration/persistence surfaces, and buyer-facing examples. Those candidates must be repaired only after bounded-context meaning and compatibility impact are established; valid multiword camelCase/PascalCase/snake_case names are not defects.

## Persistence, ERD, and migration baseline

The evidence-store ERD remains two independent evidence aggregates:

```text
policy_decisions
  decision_id (PK)
  ... policy snapshot ...

          optional causal reference
                  |
                  v

audit_events
  audit_event_id (PK)
  tenant_id
  actor_subject
  audit_action
  resource_reference
  audit_result
  policy_decision_id
  event_payload
  created_at
```

No new relationship or denormalized authority is introduced. `event_payload` is an immutable compatibility/evidence snapshot; structured columns remain the query path. This change does not alter 3NF, source partitioning, hot-key selection, read/write separation, or the logical UPSERT key.

SQLite upgrades legacy columns transactionally at store initialization. Postgres performs conditional metadata-only `ALTER TABLE ... RENAME COLUMN` operations during initialization, then recreates the tenant/resource/time index under the semantic name. The Postgres rename briefly requires an `ACCESS EXCLUSIVE` table lock; rollout therefore requires coordinated application startup rather than concurrent old-version writers. Transaction failure rolls the migration back.

## Security, test, and operability baseline

The repository's central security contract requires OSV/dependency review/Trivy and the repository also runs its own test/fuzz workflows. The naming repair does not weaken security gates or suppress findings. `tests/test_audit_event_naming_contract.py` covers semantic model fields, legacy serialization/deserialization, SQLite legacy-column migration/data retention, and old/new filter compatibility. Full repository verification remains `PYTHONPATH=src pytest` after focused regression verification.

Operationally, the rename keeps the same audit-event primary-key conflict semantics and the same `(tenant_id, resource_reference, created_at DESC)` query locality that the previous index provided. No new partition, queue, or background writer is introduced.

## UI evidence

This repair changes domain/persistence vocabulary, not the rendered operator console. No Storybook/Figma/screenshot claim is added by this change. Existing design evidence remains governed by the repository's `docs/design-tokens.md` and enterprise-readiness artifacts.

## Current product gaps

Highest-leverage gaps remain durable production-grade catalog/ontology storage, buyer source integrations, operational evidence export/retention controls, and completion of organization-wide semantic naming normalization without breaking public contracts. Naming work should prioritize persisted/public contracts and shared `sdp_core` boundaries before cosmetic local-variable cleanup.

## Traceability

The product's catalog vocabulary and provenance/evidence model align with current or stable authoritative web standards rather than inventing incompatible metadata semantics:

- World Wide Web Consortium. (2024, August 22). *Data Catalog Vocabulary (DCAT) – Version 3*. https://www.w3.org/TR/vocab-dcat-3/
- World Wide Web Consortium. (2013, April 30). *PROV-O: The PROV Ontology*. https://www.w3.org/TR/prov-o/

DCAT 3 is a W3C Recommendation for interoperable catalog/dataset descriptions; PROV-O supplies a stable provenance vocabulary. These references support interoperable catalog/provenance semantics but do not override the ContextualWisdomLab bounded-context naming contract for internal code and persistence.
