# Evidence database semantic identifiers

## 결정과 bounded context

`policy_decisions`와 `audit_events`는 Semantic Data Portal이 직접 소유하는 durable evidence persistence다. 기존 physical columns의 `subject`, `resource`, `action`, `effect`, `payload`, `id`, `actor`, `result`는 단일 lexical word라서 policy decision인지 audit event인지 스키마만 보고 구분하기 어렵다. 제품의 evidence/audit ubiquitous language에 맞춰 아래처럼 organization-owned database vocabulary를 구체화한다.

- `policy_decisions.subject` → `policy_subject`
- `policy_decisions.resource` → `policy_resource`
- `policy_decisions.action` → `policy_action`
- `policy_decisions.effect` → `policy_effect`
- `policy_decisions.payload` → `decision_payload`
- `audit_events.id` → `audit_event_id`
- `audit_events.actor` → `audit_actor`
- `audit_events.action` → `audit_action`
- `audit_events.resource` → `audit_resource`
- `audit_events.result` → `audit_result`
- `audit_events.payload` → `audit_payload`

이미 의미가 충분한 `decision_id`, `tenant_id`, `recorded_at`, `created_at`은 churn을 피하기 위해 유지한다. Table names인 `policy_decisions`와 `audit_events`도 이미 multiword snake_case이므로 변경하지 않는다.

## SQLite migration과 rollback

SQLite store는 기존 table을 발견하면 같은 connection transaction에서 `ALTER TABLE ... RENAME COLUMN`을 수행한다. Rename은 row copy/dual-write를 만들지 않고 기존 primary key와 evidence rows를 유지한다. Legacy column과 semantic column이 동시에 존재하는 partial migration 상태에서는 임의 merge를 하지 않고 fail closed한다.

Rollback은 old binary를 먼저 배포하지 않는다. 필요하면 동일한 maintenance window에서 reverse rename (`policy_subject→subject`, `policy_resource→resource`, `policy_action→action`, `policy_effect→effect`, `decision_payload→payload`, `audit_event_id→id`, `audit_actor→actor`, `audit_action→action`, `audit_resource→resource`, `audit_result→result`, `audit_payload→payload`)을 수행한 뒤 old binary를 시작한다. Mixed-version dual-write compatibility는 제공하지 않는다.

## PostgreSQL migration, locking, indexes

PostgreSQL store도 기존 table에 대해 conditional `ALTER TABLE ... RENAME COLUMN`을 사용하며, legacy/semantic column이 동시에 있으면 `RAISE EXCEPTION`으로 중단한다. `ALTER TABLE` rename은 PostgreSQL DDL lock을 요구하므로 rolling mixed-version deployment가 아니라 짧은 coordinated cutover로 취급한다. Migration 중에는 새/구 binary가 동시에 해당 table에 write하지 않도록 deployment orchestration이 먼저 traffic/write를 quiesce해야 한다.

기존 query shape `(tenant_id, resource, created_at DESC)`는 의미적으로 유지하되 physical column과 index 이름을 함께 갱신한다.

- `idx_policy_decisions_tenant_resource_created` → `idx_policy_decisions_tenant_policy_resource_created`
- `idx_audit_events_tenant_resource_created` → `idx_audit_events_tenant_audit_resource_created`

UPSERT key는 policy decision에서 계속 `decision_id`, audit event에서 renamed primary key인 `audit_event_id`를 사용한다. 기존 `decision_id` logical link는 유지하며 새 foreign key를 추가하거나 제거하지 않는다.

## 3NF, hot partition, read/write separation

이번 repair는 새로운 entity/table 또는 duplicated transactional source-of-truth를 추가하지 않는다. `decision_payload`와 `audit_payload`는 원래부터 immutable evidence envelope의 snapshot이고, searchable projection columns와 JSON evidence를 함께 보존하는 audit/evidence design이다. 따라서 이번 rename 자체가 새로운 normalization dependency를 만들지는 않는다. 별도 partition key를 추가하지 않으며 기존 tenant/resource composite access path를 그대로 유지하므로 새로운 hot partition을 만들지 않는다. Demo tenant 집중 가능성은 기존 operability 특성으로 남고 이번 naming migration에서 악화시키지 않는다. Read/write connection separation과 transaction scope도 변경하지 않는다.

## External/API compatibility

이 변경은 physical database contract만 수정한다. `PolicyDecision`과 `AuditEvent`의 기존 API/JSON wire keys는 이번 PR에서 변경하지 않는다. 따라서 HTTP consumers와 persisted JSON envelope은 그대로 호환되고, database access는 `SQLiteEvidenceStore`/`PostgresEvidenceStore` adapter 내부의 semantic physical names로 격리된다.

## Verification

`tests/test_evidence_store_database_naming.py`는 fresh SQLite schema의 exact multiword columns, legacy SQLite row-preserving migration, legacy-name 제거, PostgreSQL create/DML/index/UPSERT SQL을 고정한다. 기존 evidence-store integration tests는 persisted decision/audit round-trip과 tenant-scoped listing이 semantic physical columns에서도 유지되는지 계속 검증해야 한다. Merge evidence는 predecessor run이 아니라 unchanged current head의 required checks와 independent approval만 사용한다.
