# Evidence store database semantic naming repair

## 결정

`semantic-data-portal`의 Evidence Store bounded context는 `policy_decisions`와 `audit_events`를 조직 소유 persisted schema로 관리한다. 따라서 이 저장소가 소유하는 database column은 generic single-word 이름 대신 정책 결정과 감사 이벤트의 의미를 드러내는 multiword `snake_case` 이름을 사용한다.

| Legacy column | Semantic column | Owning context |
| --- | --- | --- |
| `policy_decisions.subject` | `policy_decisions.decision_subject` | policy decision actor/subject evidence |
| `policy_decisions.resource` | `policy_decisions.policy_resource` | policy-evaluated resource |
| `policy_decisions.action` | `policy_decisions.policy_action` | policy-evaluated action |
| `policy_decisions.effect` | `policy_decisions.decision_effect` | policy decision outcome |
| `policy_decisions.payload` | `policy_decisions.decision_payload` | serialized policy decision contract |
| `audit_events.id` | `audit_events.audit_event_id` | audit-event identity |
| `audit_events.actor` | `audit_events.actor_subject` | audit actor/subject |
| `audit_events.action` | `audit_events.audit_action` | audited action |
| `audit_events.resource` | `audit_events.audit_resource` | audited resource |
| `audit_events.result` | `audit_events.audit_result` | audited execution result |
| `audit_events.payload` | `audit_events.audit_payload` | serialized audit-event contract |

`decision_id`, `tenant_id`, `recorded_at`, `created_at`는 이미 bounded-context 의미를 가진 multiword 이름이므로 그대로 유지한다. Table 이름 `policy_decisions`와 `audit_events`도 이미 multiword `snake_case`라 변경하지 않는다.

## Compatibility와 migration boundary

`SQLiteEvidenceStore`와 `PostgresEvidenceStore`의 initialization path가 migration authority를 가진다. Fresh database는 semantic column으로 생성되고, legacy database는 startup initialization에서 in-place `ALTER TABLE ... RENAME COLUMN`을 수행한다. Row payload나 primary-key 값은 다시 쓰지 않는다.

Migration은 old/new column이 동시에 존재하는 partial/ambiguous schema를 발견하면 fail closed 한다. 이 경계는 자동으로 어느 쪽 값을 신뢰할지 추측하지 않아 split-brain persistence contract를 만들지 않는다.

Pydantic/API wire contract는 이번 변경의 대상이 아니다. Serialized `PolicyDecision`과 `AuditEvent` payload 안의 기존 외부 contract는 그대로 유지하며, database storage vocabulary만 semantic하게 구체화한다.

## 3NF, UPSERT, index와 concurrency 검토

두 persisted aggregate는 계속 별도 table에 저장되며 새로운 반복 그룹이나 중복 entity를 추가하지 않아 기존 3NF 수준을 저하시키지 않는다. `PolicyDecision`과 `AuditEvent` 간 `decision_id` reference도 그대로 유지한다.

Postgres UPSERT는 `policy_decisions(decision_id)`와 `audit_events(audit_event_id)`의 기존 logical identity를 유지하며 모든 renamed column reference를 같은 변경에서 전파한다. Tenant/resource/time read path index는 기존 index 이름을 유지하되 indexed column을 `policy_resource`와 `audit_resource`로 전환한다. PostgreSQL의 column rename은 기존 index dependency를 동일 column object에 유지하므로 index rebuild를 요구하지 않는다; `CREATE INDEX IF NOT EXISTS`는 fresh install과 legacy install 모두에서 idempotent safety net으로 남는다.

`ALTER TABLE ... RENAME COLUMN`은 PostgreSQL에서 table-level DDL lock을 짧게 획득할 수 있다. 이 migration은 application startup initialization 경로에서 실행되므로 paid-pilot deployment에서는 bounded maintenance/startup window에 수행하고, 장시간 transaction이 해당 evidence table을 점유하지 않는지 먼저 확인한다. Read/write separation이나 partition key는 이 변경에서 새로 도입하거나 변경하지 않는다. Hot-partition 특성도 row distribution을 바꾸지 않으므로 악화시키지 않는다.

## Rollback

Rollback이 필요한 경우 semantic→legacy 방향으로 동일한 column rename을 수행한 뒤 이전 application version을 기동할 수 있다. Migration이 row data를 변환하지 않기 때문에 data-copy rollback은 필요하지 않는다. 다만 새 application이 semantic column을 사용하는 동안 이전 binary를 동시에 쓰는 mixed-version rolling deployment는 허용하지 않는다. Schema/application version을 함께 전환해야 한다.

## Executable evidence

`tests/test_evidence_store_database_naming_contract.py`가 다음을 고정한다.

- fresh SQLite schema가 semantic multiword column만 생성하는지;
- legacy SQLite schema가 row loss 없이 in-place rename되는지;
- migrated row가 기존 `PolicyDecision`/`AuditEvent` contract로 다시 읽히는지;
- fresh Postgres DDL이 동일 semantic vocabulary를 사용하는지.

Repository의 기존 Evidence Store tests는 persistence CRUD, tenant scoping, Postgres UPSERT, SQLite reopen behavior를 계속 검증한다. Exact-head GitHub checks가 최종 통합 증거이며 predecessor-head 결과는 재사용하지 않는다.
