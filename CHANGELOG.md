# Changelog

## Unreleased

### Changed

- Qualified ContextualWisdomLab-owned catalog metadata names: `DatasetDistribution.id/format/endpoint` are now internally `distribution_id`/`distribution_format`/`distribution_endpoint`, and `ColumnMetadata.name` is internally `column_name`, while the established external wire keys remain compatible.
- Qualified buyer-demo and enterprise-readiness contracts with bounded-context names such as `demo_domain_id`, `dataset_id`, `dataset_title`, `dataset_domain`, `dataset_sensitivity`, `dataset_steward`, `package_boundary_id`, `connector_capability_id`, `enterprise_gate_id`, `workflow_step_id`, and `product_name`. Historical readiness/demo JSON keys remain at the serialization adapter boundary.
- Qualified buyer-facing KPI, enterprise-control, RBAC, and production-readiness contracts with semantic internal names including `kpi_id`, `implementation_status`, `enterprise_control_id`, `control_status`, `role_name`, `permission_evidence`, `production_integration_id`, and `integration_status`. Existing `/enterprise/*` response keys remain at explicit Pydantic alias boundaries.
- Replaced generic readiness nested dictionaries with typed semantic contracts for submodule strategy, design artifacts, and planned package splits.
- Qualified Evidence Store persisted columns in both SQLite and PostgreSQL. `policy_decisions.subject/resource/action/effect/payload` now migrate in place to `decision_subject`/`policy_resource`/`policy_action`/`decision_effect`/`decision_payload`; `audit_events.id/actor/action/resource/result/payload` now migrate to `audit_event_id`/`actor_subject`/`audit_action`/`audit_resource`/`audit_result`/`audit_payload`. Fresh stores create only the semantic schema; legacy stores use fail-closed in-place column renames with row data, policy/audit wire payloads, tenant scope, UPSERT identity, and read ordering preserved.
