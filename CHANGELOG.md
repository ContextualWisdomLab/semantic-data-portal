# Changelog

## Unreleased

### Changed

- Qualified ContextualWisdomLab-owned catalog metadata names: `DatasetDistribution.id/format/endpoint` are now internally `distribution_id`/`distribution_format`/`distribution_endpoint`, and `ColumnMetadata.name` is internally `column_name`, while the established external wire keys remain compatible.
- Qualified buyer-demo and enterprise-readiness contracts with bounded-context names such as `demo_domain_id`, `dataset_id`, `dataset_title`, `dataset_domain`, `dataset_sensitivity`, `dataset_steward`, `package_boundary_id`, `connector_capability_id`, `enterprise_gate_id`, `workflow_step_id`, and `product_name`. Historical readiness/demo JSON keys remain at the serialization adapter boundary.
- Replaced generic readiness nested dictionaries with typed semantic contracts for submodule strategy, design artifacts, and planned package splits. No database schema or persistence migration is involved.
