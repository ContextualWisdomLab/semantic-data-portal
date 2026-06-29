# PRD/TRD 요구사항 대응 매트릭스 (semantic-data-portal MVP)

본 문서는 `docs/prd-trd.md` 요구사항을 현재 구현 기준으로 추적하기 위한 증빙용 매핑이다.

## 구현 상태 개요

- 분기: `codex/sdp-complete-impl`
- 기준 커밋: `origin/codex/sdp-complete-impl`
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
- 핵심 코드: [src/sdp/catalog.py: get_dataset](src/sdp/catalog.py), [get_dataset_lineage](src/sdp/catalog.py), [get_dataset_schema_history](src/sdp/catalog.py), [get_dataset_schema_diff](src/sdp/catalog.py), [list_dataset_schema_versions](src/sdp/catalog.py)
- 증빙 테스트:
  - `tests/test_api.py::test_catalog_search_and_detail`
  - `tests/test_api.py::test_dataset_profile_endpoint`
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
- 증빙 테스트:
  - `tests/test_api.py::test_preview_policy_denies_missing_dataset`
  - `tests/test_api.py::test_preview_pagination_and_decision_traceability`
  - `tests/test_api.py::test_preview_denies_low_privilege_actor`
  - `tests/test_api.py::test_browse_query_success`
  - `tests/test_api.py::test_browse_query_denied_without_user`
  - `tests/test_api.py::test_draft_query`

## 4) Policy & Audit

- `POST /policy/decision`
- Catalog mutation guard: `create`, `publish`, `patch`, `deprecate`
- Browse guard: `preview`, `schema`, `query`
- 증빙 테스트:
  - `tests/test_api.py::test_create_requires_admin`
  - `tests/test_api.py::test_dataset_mutation_policy_and_lifecycle`
  - `tests/test_api.py::test_browse_schema_requires_purpose`

## 5) 운영/품질

- 단위 테스트: `tests/test_api.py` (헬스체크 + 엔드포인트별 동작 + 정책/감사 검증)
- 워크플로우: `.github/workflows/opencode-review.yml`, `.github/workflows/pr-review-merge-scheduler.yml`, `.github/workflows/strix.yml`
- 정적/CI 게이트: 워크플로우 내 OpenCode/Strix/coverage evidence 단계

## 6) 다음 단계 (현재 브랜치에서 미반영 권고)

1. 조직 정책 기준으로 `search` 및 `list` 에 대한 사용 권한/발견성 정책을 명시적으로 강화
2. API level 감사 이벤트 보존 기간 및 위변조 방지(로그 저장소 정책) 적용
3. OpenCode/PR 리뷰 증적 저장(`PR`, `review`, `merge` 로그)과 main 병합 완료 상태 정기 기록

## 7) 구현 완료 증적(현재 HEAD 기준)

- 대상 브랜치: `codex/sdp-complete-impl`
- 기준 SHA: `e981dca` (remote: `origin/codex/sdp-complete-impl`)
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
- PR 상태: `open`. 조직 리뷰 증적은 `e981dca` 기준까지 반영되었는지 확인 필요하며, OpenCode는 workflow 재실행 큐에서 최신 실행으로의 동기화가 진행 중입니다.
- 현재 잠재 블로커: 마지막 동기화 단계의 상태 불일치(오래된 체크 코멘트). 추적 파일:
  - [docs/retrigger-evidence.md](/C:/Users/Seongho%20Bae/Documents/Codex/2026-06-29/f/semantic-data-portal/docs/retrigger-evidence.md)
  - [최근 워크플로우 이벤트](/C:/Users/Seongho%20Bae/Documents/Codex/2026-06-29/f/semantic-data-portal/.github/workflows/opencode-review.yml)
