# Product / Technical Gap Baseline

## 목적

이 문서는 `ContextualWisdomLab/semantic-data-portal`의 buyer-facing product contract와 technical gap을 한 곳에서 추적한다. 현재 집중 범위는 organization naming contract이며, public HTTP wire compatibility를 유지하면서 ContextualWisdomLab-owned Python/domain vocabulary를 bounded-context 의미가 드러나는 multiword identifier로 정규화하는 것이다.

## Buyer PRD / TRD baseline

- Product responsibility: ontology-driven dataset catalog, glossary, governance, policy/audit, governed browse/query, enterprise readiness surface.
- Core package boundary: `sdp_core`는 FastAPI-independent domain contract/library 계층이고 `sdp`는 application/API orchestration 계층이다.
- Buyer outcome: evaluator가 priority dataset을 검색하고 semantic mapping, policy decision, audit evidence, connector proof, production-readiness evidence를 재현 가능하게 검증할 수 있어야 한다.
- Compatibility invariant: 기존 `/enterprise/*`, catalog JSON, demo JSON wire key는 깨지지 않아야 하며 generic external/public key를 유지해야 할 때는 Pydantic alias/serializer adapter에서 격리한다.

## DDD bounded contexts / ubiquitous language

| Bounded context | Aggregate / entity / value object | Organization-owned ubiquitous language |
| --- | --- | --- |
| Catalog metadata | `Dataset`, `ColumnMetadata`, `DatasetDistribution` | `column_name`, `distribution_id`, `distribution_format`, `distribution_endpoint` |
| Buyer demo | `BuyerDemoDomain`, `BuyerDemoDatasetSummary` | `demo_domain_id`, `demo_domain_label`, `dataset_id`, `dataset_title`, `dataset_domain`, `dataset_sensitivity`, `dataset_steward` |
| Enterprise readiness | `EnterpriseReadinessManifest`, `EnterpriseGate`, `ConnectorCapability` | `product_name`, `enterprise_gate_id`, `gate_status`, `connector_capability_id`, `connector_protocol` |
| Saleability KPI | `KPIFramework`, `SaleabilityKPI` | `kpi_id`, `kpi_label`, `kpi_definition`, `kpi_target`, `review_cadence`, `implementation_status` |
| Enterprise controls | `EnterpriseControlsManifest`, `EnterpriseControl` | `enterprise_control_id`, `control_label`, `control_status`, `control_evidence` |
| Authorization | `RBACMatrix`, `RolePermission` | `role_permissions`, `role_name`, `permission_evidence` |
| Production readiness | `ProductionReadinessManifest`, `ProductionIntegration` | `product_name`, `production_integrations`, `production_integration_id`, `integration_status` |

Context map에서 catalog/governance/readiness domain model은 organization-owned semantic vocabulary를 사용하고, historical HTTP payload는 anti-corruption/compatibility adapter를 통해 legacy key를 계속 노출한다. 의미 있는 기존 multiword snake_case identifier는 casing/style churn 대상으로 보지 않는다.

## Naming contract status

PR `#89`에서 다음 contract가 TDD로 보강되었다.

- `DatasetDistribution`: generic `id` / `format` / `endpoint` 제거, historical wire aliases 유지.
- `ColumnMetadata`: generic `name` 제거, historical wire alias 유지.
- buyer demo domain/dataset summary: generic owned field를 `demo_domain_*` / `dataset_*` vocabulary로 이동.
- readiness/KPI/enterprise-control/RBAC/production-readiness: generic `id`, `label`, `status`, `evidence`, `role`, `product`, `integrations` 등을 bounded-context semantic names로 이동.
- readiness nested dictionaries: submodule strategy, design artifact, planned package split을 typed semantic model로 승격.

Regression contract는 `tests/test_*_naming_contract.py`에서 authoritative `model_fields`와 legacy serialized payload를 함께 검증한다. Legacy compatibility access는 explicit property 또는 `legacy_attribute_map`에 격리하며 신규 organization-owned caller는 semantic field를 사용한다.

## Database / persistence impact

이번 naming slice는 database schema migration이 아니다. Table/column/index/constraint/sequence/view/function 이름, FK, ORM mapping, partition key, UPSERT path를 변경하지 않는다. 따라서 3NF, hot-partition, locking, read/write separation, rollback migration의 runtime behavior는 기존 상태를 유지한다. Persisted schema naming 변경이 필요해지는 후속 slice에서는 별도 migration + backward-read/forward-write contract와 rollback evidence가 필요하다.

## Security / test / operability baseline

- No branch-protection bypass, self-approval, force-push, synthesized status를 사용하지 않는다.
- Compatibility tests는 direct model serialization뿐 아니라 nested `/enterprise/demo-plan`, KPI/control/RBAC/production-readiness payload shape을 고정한다.
- Source repair는 ordinary non-force history로 수행되었고 predecessor check evidence는 final head에 이전하지 않는다.
- Fresh required workflows가 final exact head에서 terminal-success가 되기 전에는 merge-ready로 간주하지 않는다.
- Review thread와 independent non-author approval도 마지막 source/docs push 이후 다시 current해야 한다.

## Current gap / causal blocker status

현재 naming repair의 source-level compatibility boundary는 구현되어 있으나, final exact-head required workflow와 independent approval이 완료되기 전까지 delivery gap은 열린 상태다. Large-blast-radius core contracts인 `Dataset`, `BusinessMapping`, policy/audit store protocol 등은 caller/API/persistence dependency를 전수 추적한 뒤 별도 safe slice로 판단해야 하며, 단순 search hit만으로 churn rename하지 않는다.

## UI / accessibility evidence

이번 slice는 UI component나 Storybook/Figma artifact를 변경하지 않는다. `/enterprise/*` response key compatibility를 유지하므로 기존 console rendering contract를 깨지 않는 것이 acceptance criterion이다. UI 변경이 발생하는 후속 slice에서 screenshot, keyboard/focus, accessible-name, Storybook/Figma evidence를 추가한다.

## Traceability

Repository authority는 `AGENTS.md`, `CLAUDE.md`, `docs/prd-trd.md`, `docs/enterprise-readiness.md`, doctoring 문서, PR review thread와 exact-head GitHub Checks를 우선한다. Semantic/metadata architecture 연구 추적은 `docs/papers/README.md`에 유지된 repository-selected literature와 standards trace를 재사용하며, 이 naming-only slice에서 새로운 학술 주장이나 APA reference를 임의로 추가하지 않는다.
