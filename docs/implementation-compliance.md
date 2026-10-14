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
- 증빙 테스트: `tests/test_jsonld_export.py` (9건). 이전에는
  `tests/test_api.py::test_catalog_search_and_detail`을 인용하고 "JSON-LD 별도 API
  호출은 필요 시 확장 가능"이라고 적혀 있었는데, 그 테스트는 export의 **형태를 전혀
  보지 않습니다** — 그래서 문서가 DCAT 준수를 주장하는 동안 export는 소비 불가능한
  상태였습니다.
- 실제 상태: `@id` 키워드(이전에는 보통 용어 `id`), 인라인 컨텍스트(이전에는 HTML
  명세 페이지를 가리킴), **중첩 속성 매핑**. 마지막 항목이 가장 오래 남아 있었습니다 —
  컨텍스트를 추가한 수정이 최상위만 고쳤고, `distribution`/`mappings` 안의 속성은
  conforming 프로세서가 전부 버렸습니다. pyld 3.3.0 실측: `dcat:distribution`이
  `[{}]`로 확장(access URL·format·식별자 없음), business mapping은 `concept`·
  `source`·`approved_at` 유실. 시드 5개 전부, 중첩 용어 51건.
- 계약 테스트는 이제 **재귀**입니다. 이전에는 `for term in body`로 한 단계만 보아
  0건을 보고했고, 같은 규칙을 재귀 적용하면 51건이었습니다. 중첩 문서의 한 단계에만
  적용한 규칙은 라우트 계열의 한 라우트에만 적용한 검사와 같은 결함 유형입니다.

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

### 제 수리의 형제 경로 자체 점검 (2026-10-14)

evidence/catalog 읽기에 `tenant_ids` scope를 넣을 때 **기본값을 `None`(= 전체 tenant)**
으로 두었습니다. 이는 fail-open 기본값이므로, scope를 넘기지 않는 호출처가 하나라도
있으면 조용히 전체를 봅니다. 직접 전수 점검했습니다.

| 호출처 | 판정 |
| --- | --- |
| `api.py:430` `catalog.search_catalog(` | **오탐** — 다음 줄에서 `tenant_ids=tenant_ids`를 넘깁니다(여러 줄 호출을 grep이 놓침) |
| `/enterprise/evidence-pack` | 타 tenant 내용 없음 — 집계만 공개 |
| `/enterprise/observability` | **실제 누출** — 미인증 GET 응답에 `acme-payroll`이 포함 |
| `ontology`/`steward_review`/`semantic_validation`/`seed`의 `list_datasets()` | 집계·내부용. 타 tenant 식별 내용을 응답에 싣지 않음 |

누출 하나는 `recent_requests`였습니다. 관측 레코드마다 호출자의 `actor`,
`tenant_id`, 그리고 **데이터셋 id가 박힌 `route`** 가 들어 있고 manifest는 actor 없이
서비스됩니다. 즉 한 tenant의 governed-access 활동 기록이 누구에게나 읽혔습니다.

**관측의 `tenant_id`로 필터링하는 방식은 쓰지 않았습니다.** 그 값은 호출자가 보낸
`X-SDP-Tenant` 헤더에서 나오므로(`build_request_observation`), 필터 대상이 될 행을 쓴
바로 그 호출자가 스스로 주장한 값입니다. 자기 신고 값으로 tenant scope를 만들 수는
없습니다. 그래서 미인증 manifest에서는 요청 단위 상세를 **공개하지 않고** 집계만
남깁니다(`recent_request_count`, `export_error_count`). sink 예외 문자열이 sink URL을
인용할 수 있으므로 `export_errors`도 같이 withhold합니다. 추적은 배포로 tenant가
정해지는 설정된 sink에서 그대로 가능합니다.

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
- `GET /enterprise/production-readiness`: demo release와 paid pilot readiness를 분리하고, Postgres evidence store, OIDC JWKS verification, connector credential vault, request observability export의 환경변수·acceptance criteria·blocker를 노출한다.
  - **정정**: 이 항목은 "남은 paid-pilot blocker는 0개다"라고 적고 있었습니다. 그것이
    가능했던 이유는 `paid_pilot_ready`가 작성된 `status` 리터럴에서만 유도되어
    **반증 불가능**했기 때문입니다 — 설정이 전혀 없고 자신이 지목한 proof 엔드포인트가
    실패하는 상태에서도 `paid_pilot_ready: true`, `paid_pilot_blockers: []`였습니다.
    이제 `status`(코드베이스에 대한 주장)와 `configured_integrations` /
    `missing_environment`(배포에서 **측정**)를 분리하고 둘 다 요구합니다. 따라서
    blocker 수는 배포에 따라 달라지며, 설정되지 않은 배포에서 0이 아닙니다.
  - 게이트는 **존재하는 능력만** 측정합니다. `SDP_EVIDENCE_RETENTION_DAYS`는 `src/`
    어디에도 소비자가 없는데 게이트를 충족시켰고(`'banana'`, `'0'`, `'-1'`로도 통과),
    두 증빙 스토어 중 어느 쪽도 prune/purge 경로가 없습니다. 변수는
    `declared_unimplemented_environment`로 옮기고 manifest가
    `unimplemented_environment`로 **게시**합니다. 레지스트리 전체에 대해 소비자 없는
    변수를 금지하는 기계적 검사:
    `tests/test_production_readiness_measurement.py::test_every_required_variable_has_a_consumer`.
  - `local_evidence_retention` control은 이름이 보존 정책을 주장하면서 실제로는
    **내구성**(재시작 생존)만 제공했습니다. label과 설명을 사실에 맞췄습니다.
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

## 6-1) 기계가 읽는 계약 (`GET /openapi.json`)

이 제품의 차별점은 **거부**인데, 그 중 하나도 기계가 읽는 계약에 들어 있지
않았습니다. 변경 전 실측:

| 항목 | 이전 | 현재 |
| --- | --- | --- |
| 에러 상태를 하나라도 문서화한 operation | 0 / 60 | 42 / 60 |
| 요청 본문에 타입이 있는 라우트 | 5 / 20 | 10 / 20 |
| 200 응답에 `$ref` 스키마가 있는 operation | 0 / 60 | 0 / 60 (미반영) |

- 거부 계약: `src/sdp/api_error_contract.py`의 표 하나. `tests/test_api_error_contract.py`가
  **양방향**으로 대조합니다 — 코드가 낼 수 있는 거부가 모두 게시되었는지, 그리고
  게시된 거부가 모두 실제로 발생 가능한지(낼 수 없는 거부를 문서화하는 것은 신중함이
  아니라 거짓 주장입니다). 라우트가 낼 수 있는 상태는 `sdp.api`의 AST를 따라
  유도하며, 리터럴로 보이지 않는 경우(`_DRAFT_QUERY_ERROR_STATUS.get(...)`)는
  `DYNAMIC_REFUSALS`에 명시합니다.
- 요청 본문 계약: `src/sdp/api_request_contract.py`. 네 라우트는 이미 pydantic
  모델로 검증되고 있었고 문서만 그 사실을 말하지 않았습니다. 런타임은 그대로이며
  (파라미터는 `dict`, 스키마 위반은 422가 아니라 이 저장소의 400 형태),
  게시한 모델이 핸들러가 **실제로 생성하는** 모델인지 AST로 확인합니다.
- 남은 18개 operation과 10개 본문은 각각 실제로 거부가 없는 열린 읽기, 그리고
  모델 없이 느슨한 키를 읽는 라우트입니다 — 경계를 테스트가 측정으로 고정합니다.

## 7) 다음 단계 (현재 브랜치에서 미반영 권고)

1. 조직 정책 기준으로 `search` 및 `list` 에 대한 사용 권한/발견성 정책을 명시적으로 강화
2. API level 감사 이벤트 보존 기간 및 위변조 방지(로그 저장소 정책) 적용
3. OpenCode/PR 리뷰 증적 저장(`PR`, `review`, `merge` 로그)과 main 병합 완료 상태 정기 기록

## 8) 구현 완료 증적(현재 HEAD 기준)

- 대상 브랜치: `claude/semantic-portal-pr-merge-e5a48k` (PR #102). 이 줄은
  `codex/sdp-enterprise-foundation`을 가리키고 있었습니다 — 오래된 값입니다.
- 기준: PR 베이스(`docs/product-technical-gap-baseline`) 대비 현재 브랜치 HEAD
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
- 현재 블로커(둘 다 소유자만 해결 가능): **독립 승인 1건**과 **Actions billing
  해제**. 필수 체크는 디스패치 전에 거부되며(2~4초, 주석
  `The job was not started because your account is locked due to a billing issue.`),
  저장소 자체 워크플로의 마지막 성공은 2026-10-02T09:03:05Z입니다. 그 이후의 성공은
  GitHub 자체 할당량으로 도는 Dependabot 뿐이므로 계정 잠금 해제의 증거가 아닙니다.
  자기 승인은 하지 않습니다. 추적 파일:
  - [docs/retrigger-evidence.md](docs/retrigger-evidence.md)
