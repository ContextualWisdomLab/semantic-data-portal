# PRD/TRD 요구사항 대응 매트릭스 (semantic-data-portal MVP)

본 문서는 `docs/prd-trd.md` 요구사항을 현재 구현 기준으로 추적하기 위한 증빙용 매핑이다.

## 구현 상태 개요

- 분기: `codex/sdp-enterprise-foundation`
- 기준 커밋: PR #5 current head
- 증빙: API 엔드포인트, 도메인 모델, 테스트(`tests/test_api.py`)

## 1) 필수 기능 요구사항 대응

### CAT-001 검색
- 대응: `GET /catalog/search`, `GET /catalog/facets`, `GET /catalog/datasets`
- 핵심 코드:
  - [src/sdp/catalog.py: search_catalog](src/sdp/catalog.py)
  - [src/sdp/catalog.py: list_facet_counts](src/sdp/catalog.py)
- 증빙 테스트:
  - `tests/test_api.py::test_catalog_search_and_detail`
  - `tests/test_api.py::test_catalog_search_filter_by_quality`
  - `tests/test_api.py::test_catalog_facets_and_audit_events`

### CAT-002 상세 정보
- 대응: `GET /catalog/datasets/{dataset_id}`, `GET /catalog/datasets/{dataset_id}/lineage`, `GET /catalog/datasets/{dataset_id}/schema-history`, `GET /catalog/datasets/{dataset_id}/schema-versions`, `GET /catalog/datasets/{dataset_id}/schema-diff`
- 핵심 코드: [src/sdp/catalog.py: get_dataset](src/sdp/catalog.py), [discovery_view](src/sdp/catalog.py), [get_dataset_lineage](src/sdp/catalog.py), [get_dataset_schema_history](src/sdp/catalog.py), [get_dataset_schema_diff](src/sdp/catalog.py), [list_dataset_schema_versions](src/sdp/catalog.py)
- 경계: 목록/상세는 actor 없이 서비스되는 discovery 표면이므로 `catalog.discovery_view()`가
  publish 가능한 필드만 투영한다. 컬럼 스키마(`pii` 플래그 포함), `source_system` 접속 문자열,
  row-count `profile`, 소유 `tenant_id`은 withhold하고 `schema_field_count`만 공개한다. 해당
  필드는 정책을 평가하고 감사 기록을 남기는 `GET /browse/{dataset_id}/schema` 경로가 유일한
  공개 지점이다.
- 같은 경계를 컬럼 단위로도 적용한다. `schema-history`/`schema-diff`는 저장된 컬럼 signature를
  공개하므로 `catalog.discovery_column_view()`가 `pii`/`quality_issues`를 제거한 **사본**을
  투영한다(저장 snapshot은 drift 탐지용으로 완전한 상태를 유지). `pii` 재분류는 실제 schema
  drift이므로 diff는 해당 컬럼을 계속 changed로 보고하고 `changed_withheld_fields`로 어떤 withhold
  필드가 바뀌었는지 알리되 분류값 자체는 공개하지 않는다.
- 증빙 테스트:
  - `tests/test_api.py::test_catalog_search_and_detail`
  - `tests/test_api.py::test_dataset_profile_endpoint`
  - `tests/test_api.py::test_catalog_discovery_routes_do_not_publish_governed_dataset_internals`
  - `tests/test_api.py::test_catalog_discovery_payload_field_set_is_pinned`
  - `tests/test_api.py::test_catalog_schema_history_and_diff`

### CAT-003 DCAT 구조
- 대응: `GET /catalog/datasets/{dataset_id}/jsonld`
- 핵심 코드: [src/sdp/api.py: dataset_jsonld](src/sdp/api.py)

### CAT-004 용어 매핑 상태
- 대응: `list_dataset.mappings`, `browse`, `ontology`
- 핵심 코드:
  - [src/sdp/domain.py: BusinessMapping / MappingStatus]
  - [src/sdp/ontology.py: Concept/patch workflow]
  - [src/sdp/catalog.py: mapping_candidates / concept_assets]
- 증빙 테스트:
  - `tests/test_api.py::test_ontology_patch_workflow`
  - `tests/test_api.py::test_ontology_resolve`

### CAT-005 감사 로그
- 대응: `Catalog` 변경 감사 + preview/query 감사
- 핵심 코드: `src/sdp/catalog.py`의 `_AUDIT_LOG`, `register_dataset`, `patch_dataset`, `publish_dataset`, `deprecate_dataset`, `ingest_event`  
 - Browse 계열 감사: `src/sdp/browse.py`
- 증빙 테스트:
  - `tests/test_api.py::test_audit_event_includes_policy_decision_id_for_preview`
  - `tests/test_api.py::test_catalog_facets_and_audit_events`
  - `tests/test_api.py::test_dataset_mutation_policy_and_lifecycle`

### CAT-006 완성도 점수
- 대응: `Dataset.metadata_completeness`, `Dataset.metadata_recommendation_score`, API 재구성 `completeness_badge`
- 핵심 코드:
  - [src/sdp/domain.py: Dataset]
  - [src/sdp/catalog.py: validate_metadata, recompute_scores]
- 증빙 테스트:
  - `tests/test_api.py::test_catalog_dataset_detail_exposes_recommendation_score`

### CAT-007 JSON-LD Export
- 대응: `GET /catalog/datasets/{dataset_id}/jsonld`
- 증빙 테스트: `tests/test_api.py::test_catalog_search_and_detail` (ID 조회 후 JSON-LD 별도 API 호출은 필요 시 확장 가능)

### CAT-008 버전/스키마 버전 분리
- 대응: `Dataset.version`, `Dataset.schema_version`, `schema-history`, `schema-versions`, `schema-diff`
- 증빙 테스트: `tests/test_api.py::test_catalog_schema_history_and_diff`

### CAT-009 관련 데이터셋/Join 후보
- 대응: `GET /catalog/datasets/{dataset_id}/related`, `GET /catalog/datasets/{dataset_id}/join-candidates`
- 핵심 코드: [src/sdp/catalog.py: get_related_datasets](src/sdp/catalog.py), [get_join_candidates](src/sdp/catalog.py)
- 증빙 테스트: `tests/test_api.py::test_join_candidate_endpoint`

## 2) Ontology / Terminology

- ONT-001 동의어/다국어: [src/sdp/ontology.py: _build_index, search_concepts]
- ONT-003 SKOS 계층: `GET /ontology/search`, `GET /ontology/concept/{concept}`, `GET /ontology/term/{term}/graph`
- ONT-004~006: 용어 제안-승인-노출 흐름, 매핑 상태(`proposed/approved/rejected`), 근거 문자열/신뢰도
  - `POST /ontology/patches`
  - `POST /ontology/patches/{id}/review`
- 증빙 테스트:
  - `tests/test_api.py::test_ontology_search`
  - `tests/test_api.py::test_ontology_concept_graph`
  - `tests/test_api.py::test_ontology_resolve`
  - `tests/test_api.py::test_ontology_patch_workflow`

## 3) Browse / Query

- API: `GET /browse/{dataset_id}/schema`, `POST /browse/{dataset_id}/preview`, `POST /browse/query`, `POST /browse/query`, `POST /llm/draft-query`
- 정책 + 마스킹: `src/sdp/browse.py`, `src/sdp/policy.py`
- 쿼리 허용/거부: `src/sdp/orchestrator.py: execute_query`, `draft_sql`
- preview row 경계: 샘플 row는 `browse._sample_rows()`가 **지정된 데이터셋의 선언
  스키마에 투영**해 만든다. 데이터셋이 선언하지 않은 컬럼은 들어갈 칸이 없으므로
  다른 dataset_id로 남의 PII 컬럼에 도달할 수 없다. 마스킹은 floor로 적용한다 —
  정책 obligation과 데이터셋이 `pii`로 선언한 컬럼의 합집합을 마스킹하고, 응답과
  감사 기록에는 실제 적용된 집합을 보고한다.
- 증빙 테스트:
  - `tests/test_api.py::test_preview_policy_denies_missing_dataset`
  - `tests/test_api.py::test_preview_pagination_and_decision_traceability`
  - `tests/test_api.py::test_preview_denies_low_privilege_actor`
  - `tests/test_browse.py::test_preview_rows_never_leave_the_named_dataset_schema`
  - `tests/test_browse.py::test_preview_masks_every_declared_pii_column`
  - `tests/test_browse.py::test_preview_masks_declared_pii_even_if_the_obligation_omits_it`
  - `tests/test_api.py::test_browse_query_success`
  - `tests/test_api.py::test_browse_query_denied_without_user`
  - `tests/test_api.py::test_draft_query`

### 조회 게이트가 매트릭스와 어긋나 있었습니다 (정정)

앞 절에서 저는 "매트릭스는 역할 단위로 일관되고 문제는 seed 번들링뿐"이라고 적었습니다.
**그 결론이 틀렸습니다.** `policy._has_reader_role`가 `security`를 포함했고, 조회 게이트가
`query`/`preview`/`schema`/`search`/`list`를 **하나로** 묶어 검사했으므로 `security` 역할
자체가 `preview_data`와 `run_governed_query`를 얻었습니다 — 매트릭스가 `denied_actions`로
공개하는 바로 그 두 개입니다. 기본 OIDC map `sdp-security → ['security']`에는
`platform-admin`이 없으므로, **실제 federated security 검토자**가 거부된다고 공개된 데이터
접근을 갖고 있었습니다(측정: `user=security` preview → 200, rows=2).

게이트를 행위 종류로 분리했습니다.

| 행위 | 필요 역할 | 매트릭스가 `security`에 대해 |
| --- | --- | --- |
| `schema`, `search`, `list` | `_METADATA_READER_ROLES` (= data readers + `security`) | 허용 (`view_schema`, `discover_catalog`) |
| `preview`, `query` | `_DATA_READER_ROLES` (`data-analyst`, `admin`, `platform-admin`) | 거부 (`preview_data`, `run_governed_query`) |

수리 후 `security` 역할만 가진 subject는 schema/search는 allow, preview/query는 deny입니다.
seed의 `security` subject는 `platform-admin`도 들고 있어 여전히 preview가 되며, 그것은
매트릭스가 정직하게 공개하는 권한입니다(앞 절의 `seeded_subject_bindings`).

### RBAC 매트릭스와 seed 번들링

`GET /enterprise/rbac-matrix`는 **역할 단위** 매트릭스이고 그 자체로 일관됩니다 —
`platform-admin` 행은 `all_tenants`와 전체 action을 정직하게 적습니다. 매트릭스만으로
보이지 않던 것은 **seed가 그 역할을 다른 subject에 묶어 넣는다**는 사실입니다.

| subject | roles | tenant 교차 |
| --- | --- | --- |
| `admin` | `admin`, `data-analyst`, `platform-admin` | 예 |
| `security` | `security`, `platform-admin` | 예 |
| `data-admin` | `admin`, `data-analyst` | 아니오 |
| `analyst` | `data-analyst` | 아니오 |
| `external-analyst` | `data-analyst` (tenant `external`) | 아니오 |

따라서 구매자가 `security → platform_evidence_only` 행을 읽고 나서 `security` subject가
다른 tenant의 `critical` 데이터셋을 preview(200)하고 deprecate(200)하는 것을 측정하게
됩니다. **두 사실은 동시에 참입니다** — 그 subject가 두 번째 역할을 들고 있기 때문입니다.
`authz.seeded_subject_bindings()`를 매니페스트에 함께 실어 페이지가 오해를 만들지
않게 했습니다.

`security`가 `platform-admin`을 들고 있어야 하는지는 **제품 결정이므로 여기서 바꾸지
않았습니다.** 역할을 빼앗는 쪽이든 매트릭스를 바꾸는 쪽이든 의도를 알아야 고를 수
있습니다. 대신 scope 주장이 실제 grant보다 좁아지면 실패하는 contract test
(`tests/test_api.py::test_rbac_matrix_scope_claims_match_the_seeded_grants`)를 두어,
앞으로 seed가 바뀌면 거짓 주장이 배포되기 전에 깨지게 했습니다.

## 4) Policy & Audit

- `POST /policy/decision`
- Catalog mutation guard: `create`, `publish`, `patch`, `deprecate`
- Browse guard: `preview`, `schema`, `query`
- Evidence row의 tenant 귀속: `PostgresEvidenceStore`는 policy decision은
  `obligations["tenant_id"]`, audit event는 `details["tenant_id"]`에서 tenant를 읽어
  `tenant_id TEXT NOT NULL` 컬럼과 tenant 선행 인덱스로 행을 scope한다. 따라서
  생산 측에서 모든 분기에 tenant를 stamp한다 — `policy._effective_tenant_id()`는
  존재하는 데이터셋의 소유 tenant를, 데이터셋을 지칭하지 않는 행위(`create`,
  discovery, 없는 resource)는 actor의 tenant를 쓴다. `catalog.ingest_event()`와
  `catalog._build_dataset_payload()`가 audit event에 같은 값을 넣는다.
  둘 다 해결되지 않으면 `sdp_core.stores.UNRESOLVED_TENANT_ID`로 표시한다.
  **`demo`는 실제 tenant(seed 데이터셋의 소유자)이므로 fallback 값으로 쓰지 않는다** —
  이전 `or "demo"` fallback은 tenant-scoped 질의가 남의 행을 보고 자기 행을
  놓치게 만들었다.
- 증빙 테스트:
  - `tests/test_api.py::test_create_requires_admin`
  - `tests/test_api.py::test_dataset_mutation_policy_and_lifecycle`
  - `tests/test_api.py::test_browse_schema_requires_purpose`
  - `tests/test_api.py::test_catalog_mutation_guard_denies_non_admin_actors`
    (publish/patch/deprecate x analyst/guest/anonymous/actor 키 없음 = 12건, 거부 후 상태 불변까지 확인)
  - `tests/test_api.py::test_catalog_mutation_denial_is_recorded_as_evidence`
  - `tests/test_policy.py::test_every_decision_branch_stamps_the_owning_tenant`
  - `tests/test_policy.py::test_decision_without_a_resolvable_tenant_is_not_attributed_to_demo`
  - `tests/test_browse.py::test_browse_audit_events_carry_the_owning_tenant`
  - `tests/test_catalog.py::test_mutation_audit_events_carry_the_dataset_tenant`
  - `tests/test_evidence_tenant_scope.py` (store helper + 마이그레이션 backfill)
  - `tests/test_evidence_tenant_read_scope.py` (읽기 경로 tenant scope)
- Evidence **읽기** 경로도 같은 tenant로 scope한다. `GET /audit/events`,
  `GET /policy/decisions`, `GET /catalog/datasets/{id}/audit`는 actor를 받아 정책을
  평가하고(`_authorize_evidence_read`), `policy.accessible_tenant_ids()`가 돌려주는
  tenant 집합으로 행을 제한한다. `None`은 platform-admin의 명시적 교차 하나뿐이고,
  tenant를 해석할 수 없는 reader는 빈 목록 → **0행**이다(unscoped read로 흐르지 않는다).
  두 store 모두 `tenant_ids`를 받아 SQL에서 필터하며(Postgres는 tenant 선행 인덱스를
  그대로 사용, SQLite는 같은 프로토콜을 위해 `tenant_id` 컬럼과 인덱스를 추가 —
  기존 파일은 `PRAGMA table_info` 확인 후 `ALTER TABLE`로 마이그레이션하고 레거시 행은
  `UNRESOLVED_TENANT_ID`를 받는다), in-memory fallback도 동일하게 필터한다.

## 5) 운영/품질

- 단위 테스트: `tests/test_api.py` (헬스체크 + 엔드포인트별 동작 + 정책/감사 검증 + enterprise readiness)
- 워크플로우: 조직 공통 규칙셋 `CWL Central required workflows`의 중앙 required workflow를 사용한다.
- 정적/CI 게이트: repo-local OpenCode/Strix workflow 복사본은 `main`에서 제거되었으므로 이 브랜치도 중앙 workflow 정책을 따른다.
- 로컬 증빙: `PYTHONPATH=src python3 -m pytest -q` 결과로 전체 테스트 통과 상태를 검증한다.

## 6) Enterprise / Buyer Evidence

- `GET /enterprise/readiness`: 20억 원 valuation target, package/submodule decision, storage/connector capability, enterprise gates, Figma Code Connect disabled artifact.
- `GET /enterprise/production-readiness`: demo release와 paid pilot readiness를 분리하고, Postgres evidence store, OIDC JWKS verification, connector credential vault, request observability export의 환경변수·acceptance criteria·blocker를 노출한다. Postgres evidence store, OIDC JWKS verification, request observability export, connector credential vault가 구현되어 남은 paid-pilot blocker는 0개다.
- `POST /enterprise/auth/oidc-verify`: issuer/audience/expiry/JWKS 서명 검증 후 tenant scoped group mapping으로 `ActorContext`를 생성하고 raw token은 응답에 포함하지 않는다. 신뢰 기준(issuer, audience, JWKS, role map)은 operator 환경 설정에서만 읽으며, request body가 이 네 필드를 보내면 검증 전에 400으로 거절한다.
- `POST /enterprise/auth/oidc-preview`, `POST /enterprise/auth/oidc-verify`: group별 `group_role_bindings`(group 이름, 부여한 tenant scope, 부여된 role)와 `audit_event_id`를 반환하고 `enterprise/auth/oidc` resource audit event를 남긴다. `sso_oidc_adapter` control은 이로써 `implemented`가 되고 `GET /enterprise/controls`의 `planned_controls`는 0, `status`는 `pilot_ready`가 된다.
- `GET /enterprise/evidence-pack`: metadata validation, SHACL-compatible validation, steward queue, ontology mapping coverage, policy/audit counts, controls, KPI ids, proof endpoints.
- `GET /enterprise/console`: buyer/operator가 evidence, KPI, controls, connector 상태를 브라우저에서 확인하는 no-build-dependency UI.
- 증빙 테스트:
  - `tests/test_api.py::test_enterprise_readiness_manifest_exposes_saleable_gates`
  - `tests/test_api.py::test_enterprise_production_readiness_tracks_paid_pilot_integrations`
  - `tests/test_api.py::test_enterprise_evidence_pack_summarizes_buyer_diligence`
  - `tests/test_api.py::test_request_observability_export_writes_bodyless_jsonl`
  - `tests/test_api.py::test_enterprise_rest_connector_probe_uses_vault_reference_without_secret_leak`
  - `tests/test_api.py::test_oidc_jwks_verification_maps_verified_token_without_token_leak`
  - `tests/test_api.py::test_oidc_jwks_verification_rejects_wrong_audience`
  - `tests/test_api.py::test_oidc_preview_scopes_group_roles_to_claimed_tenant`
  - `tests/test_api.py::test_oidc_mapping_audit_event_records_bindings_without_claim_leak`
  - `tests/test_api.py::test_oidc_jwks_verification_records_group_role_bindings`
  - `tests/test_authz.py::test_tenant_scope_overrides_wildcard_group_entry`
  - `tests/test_api.py::test_enterprise_console_renders_operator_surface`
  - `tests/test_api.py::test_enterprise_demo_smoke_summary_is_ready`

## 7) 다음 단계 (현재 브랜치에서 미반영 권고)

1. 조직 정책 기준으로 `search` 및 `list` 에 대한 사용 권한/발견성 정책을 명시적으로 강화
2. API level 감사 이벤트 보존 기간 및 위변조 방지(로그 저장소 정책) 적용
3. OpenCode/PR 리뷰 증적 저장(`PR`, `review`, `merge` 로그)과 main 병합 완료 상태 정기 기록

## 8) 구현 완료 증적(현재 HEAD 기준)

- 대상 브랜치: `codex/sdp-enterprise-foundation`
- 기준: `origin/main` 병합 후 현재 브랜치 HEAD
- 증적 파일:
  - `src/sdp/api.py`
  - `src/sdp/catalog.py`
  - `src/sdp/browse.py`
  - `src/sdp/orchestrator.py`
  - `src/sdp/policy.py`
  - `src/sdp/ontology.py`
  - `tests/test_api.py`
  - `docs/implementation-compliance.md`
  - `docs/retrigger-evidence.md`
- PR 상태: `open`. `origin/main`의 repo-local central workflow 삭제 정책과 충돌을 해소했다.
- 현재 잠재 블로커: GitHub Actions required workflow 재실행 및 review state 갱신 대기. 추적 파일:
  - [docs/retrigger-evidence.md](docs/retrigger-evidence.md)
