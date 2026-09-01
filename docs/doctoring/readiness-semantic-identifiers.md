# Readiness semantic identifier contract

## Scope

The enterprise-readiness and buyer-demo models are ContextualWisdomLab-owned contracts in the catalog/governance bounded context. Their internal Python vocabulary must identify the semantic role of a field rather than rely on a generic one-word name whose meaning is supplied only by the surrounding class.

## Internal vocabulary

The canonical internal names are now semantically qualified:

- `BuyerDemoDomain.id` → `demo_domain_id`
- `BuyerDemoDomain.label` → `demo_domain_label`
- `BuyerDemoDomain.description` → `demo_domain_description`
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

Nested readiness dictionaries were also converted to typed anti-corruption models so organization-owned Python code uses `submodule_strategy`/`decision_reason`, `design_artifact_id`/`artifact_type`/`artifact_url`, and `package_name`/`split_action` rather than generic `decision`, `reason`, `id`, `type`, `url`, `package`, and `action` identifiers.

## Compatibility boundary

The established `/enterprise/readiness` and `/enterprise/demo-plan` JSON wire keys remain unchanged. Pydantic aliases plus the shared readiness serializer translate semantic internal field names back to the historical wire vocabulary. Legacy Python attribute lookup is isolated in an explicit `legacy_attribute_map`; new organization-owned code should use the semantic field names.

This is a contract-boundary refactor, not a database migration. It changes no table, column, index, constraint, sequence, view, ORM mapping, partition key, UPSERT path, lock behavior, or read/write separation policy.

## Regression evidence

`tests/test_buyer_demo_domain_naming_contract.py` pins the buyer-demo domain field ownership and legacy wire aliases. `tests/test_readiness_naming_contract.py` pins readiness model ownership and the established serialized payload. Existing API tests remain the downstream compatibility suite for the public readiness endpoints.

Fresh GitHub required-workflow evidence must be taken from the exact current PR head after the repair; predecessor checks are not transferable.
