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

- 단위 테스트: `tests/test_api.py` (헬스체크 + 엔드포인트별 동작 + 정책/감사 검증 + enterprise readiness)
- 워크플로우: 조직 공통 규칙셋 `CWL Central required workflows`의 중앙 required workflow를 사용한다.
- 정적/CI 게이트: repo-local OpenCode/Strix workflow 복사본은 `main`에서 제거되었으므로 이 브랜치도 중앙 workflow 정책을 따른다.
- 로컬 증빙: `PYTHONPATH=src python3 -m pytest -q` 결과로 전체 테스트 통과 상태를 검증한다.

## 6) Enterprise / Buyer Evidence

- `GET /enterprise/readiness`: 20억 원 valuation target, package/submodule decision, storage/connector capability, enterprise gates, Figma Code Connect disabled artifact.
- `GET /enterprise/production-readiness`: demo release와 paid pilot readiness를 분리하고, Postgres evidence store, OIDC JWKS verification, connector credential vault, request observability export의 환경변수·acceptance criteria·blocker를 노출한다. Postgres evidence store, OIDC JWKS verification, request observability export, connector credential vault가 구현되어 남은 paid-pilot blocker는 0개다.
- `POST /enterprise/auth/oidc-verify`: issuer/audience/expiry/JWKS 서명 검증 후 group allow-list mapping으로 `ActorContext`를 생성하고 raw token은 응답에 포함하지 않는다.
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
  - `tests/test_api.py::test_enterprise_console_renders_operator_surface`
  - `tests/test_api.py::test_enterprise_demo_smoke_summary_is_ready`

## 7) File Knowledge / Hybrid Ontology

- 표준 프로파일: RDF/OWL 2/SKOS/SHACL/DCAT 3/DCMI/PROV-O/SPDX/JSON-LD 기반 `ontology/cwl-file-profile.ttl`, `ontology/cwl-file-shapes.ttl`; `validate_file_asset`가 pySHACL로 shape를 실행한다.
- 정체성/위치 분리: SHA-256 `FileAsset` 하나에 filesystem/S3/S3-compatible/Azure Blob `Distribution` 여러 개를 결합한다.
- 읽기 전용 수집: `src/sdp/storage_readers.py`는 list/read만 제공하고 이동·삭제·원격 mutation 기능이 없다.
- 의미 근거: `SemanticAssertion`은 confidence, proposed review status, chunk SHA-256, 문자 offset을 보존하며 원문 인용은 저장하지 않는다.
- LLM 경계: `src/sdp/document_semantics.py::ContextualOrchestratorClient`가 `/v1/chat/completions`와 `/v1/embeddings`만 호출한다. 포털에는 OpenAI/provider key가 없다.
- provider 중립성: Synology는 filesystem 배치일 뿐 필수 구성요소가 아니며, 파일 정체성은 저장소 URL과 독립적이다.
- 정책/API: `POST /file-assets`, `GET /file-assets/{asset_id}`, `/jsonld`, `/validate`는 검증된 OIDC Bearer actor context와 저장된 `FileAsset.tenant_id`를 중앙 policy decision에 전달한다. body/query `actor`는 권한 근거가 아니며 locator 공개는 동일 tenant의 admin 또는 platform-admin이 필요하다.
- 그래프 격리: 같은 SHA 및 파일 관계 대상의 cross-tenant merge를 거부한다. generic graph mutation은 file/distribution node를 다룰 수 없고 graph traversal/semantic search는 OIDC tenant policy로 file node를 필터링하며 locator를 redaction한다.
- 운영 패키징: SHACL/OWL TTL은 `sdp/resources/*.ttl` package data로 wheel/container에 포함되고, `orchestrator_base_url` 구성 시 app lifespan은 runtime `CredentialRegistry` token이 없으면 fail-closed한다.
- 벡터 일관성: KV `embedding_dimension`을 orchestrator `dimensions`에 전달하고 같은 orchestrator embedder를 memory/Postgres graph store의 ingest와 검색에 주입한다.
- 파일럿: `src/sdp/file_pilot.py`가 content deduplication, 안전한 문서 추출, graph projection, 로컬 전용 manifest를 수행한다.
- 2026-07-21 live 파일럿: `contextual-orchestrator`를 거친 OpenAI structured output으로 12개 파일을 10개 content-addressed 자산과 12개 distribution, 근거·신뢰도 포함 proposed assertion 286건으로 변환했다. 12개 모두 `extracted`, manifest의 10개 자산 모두 pySHACL conform이며 원문 조각·근거 인용문·credential marker는 0건이다. 민감한 파일명과 locator가 포함된 결과는 Git 제외 로컬 `outputs/hyosung-voc-file-index-live.json`에만 보관한다.
- 증빙 테스트:
  - `tests/test_file_knowledge.py::test_orchestrator_extractor_uses_strict_schema_and_persists_only_evidence_reference`
  - `tests/test_file_knowledge.py::test_orchestrator_client_uses_sync_embeddings_endpoint`
  - `tests/test_file_knowledge.py::test_local_pilot_deduplicates_content_and_writes_no_raw_text`
  - `tests/test_file_knowledge.py::test_file_asset_api_requires_policy_and_redacts_jsonld_locator`
  - `tests/test_graph_engine.py::test_config_loads_from_kv_mapping`

## 8) 다음 단계 (현재 브랜치에서 미반영 권고)

1. 조직 정책 기준으로 `search` 및 `list` 에 대한 사용 권한/발견성 정책을 명시적으로 강화
2. API level 감사 이벤트 보존 기간 및 위변조 방지(로그 저장소 정책) 적용
3. OpenCode/PR 리뷰 증적 저장(`PR`, `review`, `merge` 로그)과 main 병합 완료 상태 정기 기록

## 9) 구현 완료 증적(현재 HEAD 기준)

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
