# Readiness semantic identifier contract

## Scope

The enterprise-readiness and buyer-demo models are ContextualWisdomLab-owned contracts in the catalog/governance bounded context. Their internal Python vocabulary must identify the semantic role of a field rather than rely on a generic one-word name whose meaning is supplied only by the surrounding class.

## Internal vocabulary

The canonical internal names are now semantically qualified:

- `BuyerDemoDomain.id` → `demo_domain_id`
- `BuyerDemoDomain.label` → `demo_domain_label`
- `BuyerDemoDomain.description` → `demo_domain_description`
- `BuyerDemoDatasetSummary.id` → `dataset_id`
- `BuyerDemoDatasetSummary.title` → `dataset_title`
- `BuyerDemoDatasetSummary.domain` → `dataset_domain`
- `BuyerDemoDatasetSummary.sensitivity` → `dataset_sensitivity`
- `BuyerDemoDatasetSummary.steward` → `dataset_steward`
- `PackageBoundary.id` → `package_boundary_id`
- `PackageBoundary.kind` → `package_kind`
- `PackageBoundary.owns` → `owned_responsibilities`
- `StoreCapability.id` → `store_capability_id`
- `StoreCapability.responsibility` → `store_responsibility`
- `ConnectorCapability.id` → `connector_capability_id`
- `ConnectorCapability.protocol` → `connector_protocol`
- `ConnectorCapability.proof` → `connector_proof`
- `EnterpriseGate.id` → `enterprise_gate_id`
- `EnterpriseGate.label` → `gate_label`
- `EnterpriseGate.target` → `gate_target`
- `EnterpriseGate.evidence` → `gate_evidence`
- `EnterpriseGate.status` → `gate_status`
- `DemoWorkflowStep.id` → `workflow_step_id`
- `DemoWorkflowStep.owner` → `step_owner`
- `DemoWorkflowStep.outcome` → `step_outcome`
- `BuyerDemoActivationPlan.workflow` → `demo_workflow_steps`
- `EnterpriseReadinessManifest.product` → `product_name`
- `EnterpriseReadinessManifest.package_boundary` → `package_boundaries`
- `SaleabilityKPI.id/label/definition/target/cadence/owner/guardrails/status` → `kpi_id` / `kpi_label` / `kpi_definition` / `kpi_target` / `review_cadence` / `kpi_owner` / `kpi_guardrails` / `implementation_status`
- `KPIFramework.product` → `product_name`
- `EnterpriseControl.id/label/status/evidence` → `enterprise_control_id` / `control_label` / `control_status` / `control_evidence`
- `EnterpriseControlsManifest.status/controls` → `manifest_status` / `enterprise_controls`
- `ProductionIntegration.id/label/status` → `production_integration_id` / `integration_label` / `integration_status`
- `ProductionReadinessManifest.product/integrations` → `product_name` / `production_integrations`
- `RolePermission.role/evidence` → `role_name` / `permission_evidence`
- `RBACMatrix.roles` → `role_permissions`

Nested readiness dictionaries were also converted to typed anti-corruption models so organization-owned Python code uses `submodule_strategy`/`decision_reason`, `design_artifact_id`/`artifact_type`/`artifact_url`, and `package_name`/`split_action` rather than generic `decision`, `reason`, `id`, `type`, `url`, `package`, and `action` identifiers.

## Compatibility boundary

The established `/enterprise/readiness`, `/enterprise/demo-plan`, `/enterprise/kpis`, `/enterprise/controls`, `/enterprise/rbac-matrix`, and `/enterprise/production-readiness` JSON wire keys remain unchanged. Pydantic aliases and alias serialization translate semantic internal field names back to the historical wire vocabulary. `BuyerDemoDatasetSummary` therefore still exposes `id`, `title`, `domain`, `sensitivity`, and `steward` over the wire; KPI/control/RBAC/production endpoints similarly retain their historical response keys while organization-owned Python code uses qualified vocabulary. Legacy Python attribute access is isolated in explicit compatibility properties or `legacy_attribute_map`; new organization-owned code should use the semantic field names.

The evidence-pack consumer was propagated to semantic internal names (`product_name`, `dataset_id`, and `kpi_id`) so the adapter boundary does not spread generic vocabulary back into internal callers.

This is a contract-boundary refactor, not a database migration. It changes no table, column, index, constraint, sequence, view, ORM mapping, partition key, UPSERT path, lock behavior, or read/write separation policy.

## Regression evidence

The naming regressions are pinned by:

- `tests/test_buyer_demo_domain_naming_contract.py`
- `tests/test_buyer_demo_dataset_summary_naming_contract.py`
- `tests/test_readiness_naming_contract.py`
- `tests/test_kpi_naming_contract.py`
- `tests/test_enterprise_control_naming_contract.py`
- `tests/test_production_readiness_naming_contract.py`
- `tests/test_rbac_naming_contract.py`

Each compatibility test asserts both the semantic authoritative Pydantic fields and the established serialized wire vocabulary. Existing API tests remain the downstream compatibility suite for the public enterprise endpoints.

Fresh GitHub required-workflow evidence must be taken from the exact current PR head after the repair; predecessor checks are not transferable.
