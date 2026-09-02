# Product / Technical Gap Baseline

## 목적

이 문서는 `ContextualWisdomLab/semantic-data-portal`의 buyer-facing product contract와 technical gap을 한 곳에서 추적한다. 현재 집중 범위는 organization naming contract이며, public HTTP wire compatibility를 유지하면서 ContextualWisdomLab-owned Python/domain/persistence vocabulary를 bounded-context 의미가 드러나는 multiword identifier로 정규화하는 것이다.

## Buyer PRD / TRD baseline

- Product responsibility: ontology-driven dataset catalog, glossary, governance, policy/audit, governed browse/query, enterprise readiness surface.
- Core package boundary: `sdp_core`는 FastAPI-independent domain contract/library 계층이고 `sdp`는 application/API orchestration 계층이다.
- Buyer outcome: evaluator가 priority dataset을 검색하고 semantic mapping, policy decision, audit evidence, connector proof, production-readiness evidence를 재현 가능하게 검증할 수 있어야 한다.
- Compatibility invariant: 기존 `/enterprise/*`, catalog JSON, demo JSON, governed-query JSON wire key는 깨지지 않아야 하며 generic external/public key를 유지해야 할 때는 Pydantic alias/serializer adapter에서 격리한다.
- Persistence invariant: policy/audit evidence는 SQLite demo/pilot store와 managed PostgreSQL paid-pilot store 모두에서 동일 logical aggregate와 semantic schema vocabulary를 유지해야 한다.

## DDD bounded contexts / ubiquitous language

| Bounded context | Aggregate / entity / value object | Organization-owned ubiquitous language |
| --- | --- | --- |
| Catalog metadata | `Dataset`, `ColumnMetadata`, `DatasetDistribution` | `column_name`, `distribution_id`, `distribution_format`, `distribution_endpoint` |
| Buyer demo | `BuyerDemoDomain`, `BuyerDemoDatasetSummary` | `demo_domain_id`, `demo_domain_label`, `dataset_id`, `dataset_title`, `dataset_domain`, `dataset_sensitivity`, `dataset_steward` |
| Governed query | `QueryExecutionResponse`, `execute_query` | `request_id`, `dataset_id`, `query_id`, `policy_decision_id`, `query_status`, `execution_metadata`, `query_warnings`, `build_query_response`, `record_query_audit` |
| Enterprise readiness | `EnterpriseReadinessManifest`, `EnterpriseGate`, `ConnectorCapability` | `product_name`, `enterprise_gate_id`, `gate_status`, `connector_capability_id`, `connector_protocol` |
| Saleability KPI | `KPIFramework`, `SaleabilityKPI` | `kpi_id`, `kpi_label`, `kpi_definition`, `kpi_target`, `review_cadence`, `implementation_status` |
| Enterprise controls | `EnterpriseControlsManifest`, `EnterpriseControl` | `enterprise_control_id`, `control_label`, `control_status`, `control_evidence` |
| Authorization | `RBACMatrix`, `RolePermission` | `role_permissions`, `role_name`, `permission_evidence` |
| Production readiness | `ProductionReadinessManifest`, `ProductionIntegration` | `product_name`, `production_integrations`, `production_integration_id`, `integration_status` |
| Policy evidence persistence | `PolicyDecision`, `SQLiteEvidenceStore`, `PostgresEvidenceStore` | `decision_id`, `decision_subject`, `policy_resource`, `policy_action`, `decision_effect`, `decision_payload`, `tenant_id` |
| Audit evidence persistence | `AuditEvent`, `SQLiteEvidenceStore`, `PostgresEvidenceStore` | `audit_event_id`, `actor_subject`, `audit_action`, `audit_resource`, `audit_result`, `audit_payload`, `decision_id`, `tenant_id` |

Context map에서 catalog/governance/readiness/governed-query domain model은 organization-owned semantic vocabulary를 사용하고, historical HTTP payload는 anti-corruption/compatibility adapter를 통해 legacy key를 계속 노출한다. Evidence Store는 API/domain payload와 physical database schema 사이의 persistence adapter다. 의미 있는 기존 multiword snake_case identifier는 casing/style churn 대상으로 보지 않는다.

## Naming contract status

PR `#89`에서 다음 contract가 TDD로 보강되었다.

- `DatasetDistribution`: generic `id` / `format` / `endpoint` 제거, historical wire aliases 유지.
- `ColumnMetadata`: generic `name` 제거, historical wire alias 유지.
- buyer demo domain/dataset summary: generic owned field를 `demo_domain_*` / `dataset_*` vocabulary로 이동.
- `QueryExecutionResponse`: generic `status` / `execution` / `warnings`를 `query_status` / `execution_metadata` / `query_warnings`로 이동하고 historical HTTP/Python compatibility adapter를 유지. `src/sdp/orchestrator.py`의 organization-owned callers와 helper도 semantic vocabulary로 전파.
- readiness/KPI/enterprise-control/RBAC/production-readiness: generic `id`, `label`, `status`, `evidence`, `role`, `product`, `integrations` 등을 bounded-context semantic names로 이동.
- readiness nested dictionaries: submodule strategy, design artifact, planned package split을 typed semantic model로 승격.
- Evidence Store database columns: `policy_decisions.subject/resource/action/effect/payload`를 `decision_subject`/`policy_resource`/`policy_action`/`decision_effect`/`decision_payload`로, `audit_events.id/actor/action/resource/result/payload`를 `audit_event_id`/`actor_subject`/`audit_action`/`audit_resource`/`audit_result`/`audit_payload`로 이동.

`QueryExecutionResponse`의 RED naming regression은 `9d16b1a267ebc0732936b39405acbb0cce1c8a88`에서 먼저 추가됐고, production model repair `8f870abab3438711c3e30b5fdf8a613af2a46c76`와 orchestrator propagation `259ca1a1794650d2a69a6f9eb0888b1ce362d0fe`가 ordinary non-force history로 뒤따랐다. Regression contract는 `tests/test_*_naming_contract.py`, `tests/test_query_execution_response_naming_contract.py`, `tests/test_evidence_store_database_naming_contract.py`에서 authoritative model fields, legacy serialized payload, fresh DB schema, legacy SQLite migration/readback을 검증한다. Legacy compatibility access는 explicit property 또는 `legacy_attribute_map`에 격리하며 신규 organization-owned caller는 semantic field를 사용한다.

## Database / persistence impact

Evidence Store naming slice는 실제 persisted-schema migration이다. Table 이름 `policy_decisions`와 `audit_events`, 이미 semantic한 `decision_id`, `tenant_id`, `recorded_at`, `created_at`는 유지한다. Generic organization-owned columns만 bounded-context multiword `snake_case`로 rename한다. Governed-query response naming slice는 database object를 변경하지 않는다.

### Migration / backward compatibility

- Fresh SQLite/PostgreSQL stores는 semantic columns만 생성한다.
- Legacy SQLite는 store initialization에서 `ALTER TABLE ... RENAME COLUMN`으로 in-place migration한다. Row payload나 primary-key 값은 다시 쓰지 않는다.
- Legacy PostgreSQL도 initialization에서 old/new column existence를 검사한 뒤 in-place rename한다. old/new가 동시에 존재하는 partial migration state는 임의 병합하지 않고 fail closed 한다.
- `PolicyDecision`과 `AuditEvent`의 serialized JSON wire/domain payload는 이번 database rename과 분리되어 그대로 읽힌다. 따라서 external API payload compatibility를 database column 이름에 의존시키지 않는다.
- `QueryExecutionResponse`는 Pydantic aliases와 explicit compatibility properties로 기존 `status`, `execution`, `warnings` wire/Python access를 유지하므로 별도 data migration이 없다.

### 3NF / key / UPSERT

- `policy_decisions`와 `audit_events` aggregate table 분리는 그대로이며 새로운 repeating group이나 denormalized duplicate entity를 추가하지 않아 기존 3NF 수준을 유지한다.
- `policy_decisions(decision_id)` logical identity와 `audit_events(audit_event_id)` logical identity를 유지한다.
- PostgreSQL `ON CONFLICT` path는 renamed primary-key/column vocabulary를 같은 source change에서 전파한다. Policy decision UPSERT는 `decision_id`, audit event UPSERT는 `audit_event_id`를 canonical conflict key로 사용한다.
- `audit_events.decision_id` reference semantics는 변경하지 않는다.

### Index / hot partition / read-write separation

- Existing tenant/resource/time index 이름은 이미 multiword이므로 churn rename하지 않는다. Indexed resource column만 `policy_resource` 또는 `audit_resource`로 전환한다.
- PostgreSQL column rename은 existing index dependency를 동일 column object에 유지한다. Fresh install의 `CREATE INDEX IF NOT EXISTS`도 semantic column을 사용한다.
- Row distribution, tenant key, timestamp ordering, partition key를 변경하지 않아 hot-partition 특성을 새로 악화시키지 않는다.
- Read/write separation이나 transaction boundary를 바꾸지 않는다. Store construction이 migration authority인 기존 architecture를 유지한다.

### Locking / deployment / rollback

`ALTER TABLE ... RENAME COLUMN`은 PostgreSQL에서 짧은 table-level DDL lock을 획득할 수 있다. Paid-pilot deployment는 evidence table을 점유하는 장기 transaction이 없는 bounded maintenance/startup window에서 schema/application version을 함께 전환해야 한다. Mixed-version writers가 old/new column vocabulary를 동시에 사용하는 rolling window는 허용하지 않는다.

Rollback은 semantic→legacy 방향의 동일 rename을 실행한 뒤 이전 binary를 기동하는 방식이다. Row data transformation이나 destructive copy가 없으므로 data-copy rollback은 필요하지 않는다. Partial dual-column schema는 fail-closed guard가 막는다. 세부 운영 계약은 `docs/doctoring/evidence-store-database-semantic-names.md`가 소유한다. Governed-query response slice는 DB rollback이 아니라 application binary rollback만 필요하고 기존 wire keys가 유지되므로 consumer migration window가 필요하지 않다.

## Security / test / operability baseline

- No branch-protection bypass, self-approval, force-push, synthesized status를 사용하지 않는다.
- Compatibility tests는 direct model serialization뿐 아니라 governed-query response aliases와 nested `/enterprise/demo-plan`, KPI/control/RBAC/production-readiness payload shape을 고정한다.
- Evidence Store regression은 fresh SQLite schema, legacy SQLite data-preserving migration/readback, fresh PostgreSQL DDL vocabulary를 고정한다.
- Source repair는 ordinary non-force history로 수행되었고 predecessor check evidence는 final head에 이전하지 않는다.
- Fresh required workflows가 final exact head에서 terminal-success가 되기 전에는 merge-ready로 간주하지 않는다.
- Review thread와 independent non-author approval도 마지막 source/docs push 이후 다시 current해야 한다.

## Current gap / causal blocker status

Current canonical naming owner는 PR `#89`다. Catalog/readiness contract naming, governed-query response naming, Evidence Store persisted-column naming repair는 source에 반영되었고, database migration behavior와 query-wire compatibility boundary도 doctoring으로 고정되었다. Final delivery gap은 current exact-head test/security checks와 independent non-author review다. Temporary source-fix workflow가 test fixture를 semantic SQL column contract에 맞춘 뒤에는 workflow 자체가 successor commit에서 삭제되어야 하며 deletion을 exact head에서 확인해야 한다.

Large-blast-radius core contracts인 `Dataset`, `BusinessMapping`, `PolicyDecision`, `AuditEvent`의 Python/public field vocabulary는 caller/API/persistence dependency를 전수 추적한 뒤 별도 safe slice로 판단해야 한다. 단순 search hit만으로 churn rename하지 않는다. Persisted schema repair가 완료되었다고 해서 public wire model의 generic field를 자동으로 breaking rename하지 않는다. `QueryExecutionResponse`는 caller surface가 좁고 established wire keys를 alias boundary에서 그대로 보존할 수 있어 이번 run에서 안전하게 분리 수정했다.

## UI / accessibility evidence

이번 slice는 UI component나 Storybook/Figma artifact를 변경하지 않는다. `/enterprise/*` 및 governed-query response key compatibility를 유지하므로 기존 console/client rendering contract를 깨지 않는 것이 acceptance criterion이다. UI 변경이 발생하는 후속 slice에서 screenshot, keyboard/focus, accessible-name, Storybook/Figma evidence를 추가한다.

## Traceability

Repository authority는 `AGENTS.md`, `CLAUDE.md`, `docs/prd-trd.md`, `docs/enterprise-readiness.md`, `docs/doctoring/evidence-store-database-semantic-names.md`, `docs/doctoring/query-execution-response-semantic-names.md`, 기타 doctoring 문서, PR review thread와 exact-head GitHub Checks를 우선한다. Semantic/metadata architecture 연구 추적은 `docs/papers/README.md`에 유지된 repository-selected literature와 standards trace를 재사용하며, 이 naming/persistence slice에서 새로운 학술 주장을 임의로 추가하지 않는다.
