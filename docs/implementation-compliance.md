# PRD/TRD 요구사항 대응 매트릭스 (semantic-data-portal MVP)

본 문서는 `docs/prd-trd.md` 요구사항을 현재 구현 기준으로 추적하기 위한 증빙용 매핑이다.

## 구현 상태 개요

- 기본 제품 기준선: `main`
- OpenMetadata normalization 후보: PR #96 `feat/openmetadata-2-read-adapter`
- OpenMetadata admission receipt repair 후보: PR #99 `feat/openmetadata-admission-receipt-repair`
- stale predecessor: PR #97 — #99가 유효 delta를 완전히 승계하고 exact-head gate를 통과하기 전까지 유지
- 증빙: API 엔드포인트, 도메인 모델, OpenMetadata 계약·보안·회귀 테스트, ADR과 운영 문서
- PR 후보 기능은 보호된 `main` 병합과 immutable release 전에는 released capability로 간주하지 않는다.

## 1) 필수 기능 요구사항 대응

### CAT-001 검색
- 대응: `GET /catalog/search`, `GET /catalog/facets`, `GET /catalog/datasets`
- 핵심 코드:
  - [src/sdp/catalog.py: search_catalog](../src/sdp/catalog.py)
  - [src/sdp/catalog.py: list_facet_counts](../src/sdp/catalog.py)
- 증빙 테스트:
  - `tests/test_api.py::test_catalog_search_and_detail`
  - `tests/test_api.py::test_catalog_search_filter_by_quality`
  - `tests/test_api.py::test_catalog_facets_and_audit_events`

### CAT-002 상세 정보
- 대응: `GET /catalog/datasets/{dataset_id}`, `GET /catalog/datasets/{dataset_id}/lineage`, `GET /catalog/datasets/{dataset_id}/schema-history`, `GET /catalog/datasets/{dataset_id}/schema-versions`, `GET /catalog/datasets/{dataset_id}/schema-diff`
- 핵심 코드: [src/sdp/catalog.py](../src/sdp/catalog.py)
- 증빙 테스트:
  - `tests/test_api.py::test_catalog_search_and_detail`
  - `tests/test_api.py::test_dataset_profile_endpoint`
  - `tests/test_api.py::test_catalog_schema_history_and_diff`

### CAT-003 DCAT 구조
- 대응: `GET /catalog/datasets/{dataset_id}/jsonld`
- 핵심 코드: [src/sdp/api.py: dataset_jsonld](../src/sdp/api.py)

### CAT-004 용어 매핑 상태
- 대응: `list_dataset.mappings`, `browse`, `ontology`
- 핵심 코드:
  - [src/sdp/domain.py](../src/sdp/domain.py)
  - [src/sdp/ontology.py](../src/sdp/ontology.py)
  - [src/sdp/catalog.py](../src/sdp/catalog.py)
- 증빙 테스트:
  - `tests/test_api.py::test_ontology_patch_workflow`
  - `tests/test_api.py::test_ontology_resolve`

### CAT-005 감사 로그
- 대응: Catalog 변경 감사 + preview/query 감사
- 핵심 코드: `src/sdp/catalog.py`, `src/sdp/browse.py`
- 증빙 테스트:
  - `tests/test_api.py::test_audit_event_includes_policy_decision_id_for_preview`
  - `tests/test_api.py::test_catalog_facets_and_audit_events`
  - `tests/test_api.py::test_dataset_mutation_policy_and_lifecycle`

### CAT-006 완성도 점수
- 대응: `Dataset.metadata_completeness`, `Dataset.metadata_recommendation_score`, API 재구성 `completeness_badge`
- 핵심 코드: `src/sdp/domain.py`, `src/sdp/catalog.py`
- 증빙 테스트:
  - `tests/test_api.py::test_catalog_dataset_detail_exposes_recommendation_score`

### CAT-007 JSON-LD Export
- 대응: `GET /catalog/datasets/{dataset_id}/jsonld`
- 증빙 테스트: `tests/test_api.py::test_catalog_search_and_detail`

### CAT-008 버전/스키마 버전 분리
- 대응: `Dataset.version`, `Dataset.schema_version`, `schema-history`, `schema-versions`, `schema-diff`
- 증빙 테스트: `tests/test_api.py::test_catalog_schema_history_and_diff`

### CAT-009 관련 데이터셋/Join 후보
- 대응: `GET /catalog/datasets/{dataset_id}/related`, `GET /catalog/datasets/{dataset_id}/join-candidates`
- 핵심 코드: `src/sdp/catalog.py`
- 증빙 테스트: `tests/test_api.py::test_join_candidate_endpoint`

## 2) Ontology / Terminology

- ONT-001 동의어/다국어: `src/sdp/ontology.py`
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

- API: `GET /browse/{dataset_id}/schema`, `POST /browse/{dataset_id}/preview`, `POST /browse/query`, `POST /llm/draft-query`
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

- 단위 테스트: `tests/test_api.py`와 `tests/test_openmetadata_*.py`
- 워크플로우: 조직 공통 규칙셋 `CWL Central required workflows`의 중앙 required workflow를 사용한다.
- 정적/CI 게이트: repo-local OpenCode/Strix workflow 복사본은 `main`에서 제거되었으므로 이 브랜치도 중앙 workflow 정책을 따른다.
- 로컬 증빙: `PYTHONPATH=src python3 -m pytest -q`로 전체 테스트 상태를 검증한다.
- exact-head 원칙: 이전 commit의 테스트·리뷰·보안 결과를 현재 PR head의 증거로 이전하지 않는다.

## 6) Enterprise / Buyer Evidence

- `GET /enterprise/readiness`: package/submodule decision, storage/connector capability와 enterprise gates를 노출한다.
- `GET /enterprise/production-readiness`: demo release와 paid pilot readiness를 분리한다.
- `POST /enterprise/auth/oidc-verify`: issuer/audience/expiry/JWKS 서명 검증 후 group allow-list mapping으로 `ActorContext`를 생성하고 raw token은 응답에 포함하지 않는다.
- `GET /enterprise/evidence-pack`: metadata validation, SHACL-compatible validation, steward queue, ontology mapping coverage, policy/audit counts, controls, KPI ids, proof endpoints.
- `GET /enterprise/console`: buyer/operator가 evidence, KPI, controls, connector 상태를 확인하는 no-build-dependency UI.
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

## 7) OpenMetadata interoperability — PR #96 normalization candidate

### INT-OM-001 exact compatibility profile

- 대응: `2.0.1`과 `2.0.1-release`만 immutable `openmetadata-table-lineage-2.0.1` profile로 admission한다.
- upstream contract identity: `open-metadata/OpenMetadata@bf621b166ec12e8c99fcb1c1443442723386fa41`
- 핵심 코드:
  - `src/sdp/openmetadata/compatibility.py`
  - `src/sdp/openmetadata/normalizer.py`
- 증빙 테스트:
  - `tests/test_openmetadata_release_profile.py`
  - `tests/test_openmetadata_upstream_contract_regressions.py`

### INT-OM-002 schema-valid safe projection

- 대응: Table의 필수 `id`, `name`, `columns`와 EntityReference의 필수 `id`, `type`을 보존하고 선택 필드를 임의의 필수조건으로 만들지 않는다.
- source installation과 external UUID를 합성한 tenant-scoped projection ID를 사용한다.
- 샘플, SQL/DDL, query/join, column profile, extension, lineage 변환 텍스트는 일반 projection에 복사하지 않는다.
- 핵심 코드:
  - `src/sdp/openmetadata/models.py`
  - `src/sdp/openmetadata/normalizer.py`
  - `src/sdp/openmetadata/source_identity.py`
- 증빙 테스트:
  - `tests/test_openmetadata_integration.py`
  - `tests/test_openmetadata_review_regressions.py`
  - `tests/test_openmetadata_source_instance.py`

### INT-OM-003 hostile-input boundary

- 대응: UUID, URL scheme/credential, control character, 깊이, 컨테이너 수, 컬럼 수, lineage endpoint, non-finite version을 fail-closed로 거부한다.
- Python 객체 alias와 실제 back-edge cycle을 구분한다.
- 본문은 route 수준에서 chunked input을 포함해 8 MiB로 제한한다.
- 핵심 코드:
  - `src/sdp/openmetadata/validation.py`
  - `src/sdp/openmetadata_routes.py`
- 증빙 테스트:
  - `tests/test_openmetadata_validation.py`
  - `tests/test_openmetadata_normalizer_guards.py`
  - `tests/test_openmetadata_router_invariants.py`

### INT-OM-004 authentication and tenant isolation

- 대응: `POST /integrations/openmetadata/v1/table-snapshots:normalize`
- Bearer token을 기존 OIDC/JWKS verifier로 검증한다.
- `data-analyst`, `admin`, `platform-admin` 역할만 사용 가능하다.
- verified actor tenant와 body tenant가 다르면 외부 자원 존재 여부를 숨기는 404를 반환한다.
- 핵심 코드: `src/sdp/openmetadata_routes.py`, `src/sdp/authz.py`
- 증빙 테스트: `tests/test_openmetadata_authorization.py`

### INT-OM-005 authority and mutation boundary

- projection은 항상 `truth_status = observed`이며 OpenMetadata나 CWL 도메인 원장의 authoritative truth를 대체하지 않는다.
- 이 slice는 outbound network, credential persistence, catalog mutation, raw payload persistence, webhook 또는 writeback을 구현하지 않는다.

## 8) OpenMetadata admission evidence — PR #99 repair candidate

### INT-OM-006 strict transport admission

- 대응: normalization과 admission-preview endpoint에서 raw request를 먼저 검사한다.
- duplicate JSON member, invalid UTF-8, malformed/deep JSON, NaN·Infinity, lone surrogate를 거부한다.
- route class가 Content-Length 유무와 무관하게 chunked body 누적 크기를 8 MiB로 제한한다.
- 핵심 코드:
  - `src/sdp/openmetadata/strict_json.py`
  - `src/sdp/openmetadata_routes.py`
- 증빙 테스트:
  - `tests/test_openmetadata_strict_json.py`
  - `tests/test_openmetadata_router_invariants.py`

### INT-OM-007 source and projection evidence split

- 대응: `source_snapshot_digest`는 submitted Table·lineage 전체를, `projection_digest`는 safe projection 전체를 대상으로 한다.
- omitted source 값은 source digest에는 영향을 주지만 receipt에 값 자체를 복사하지 않는다.
- source instance가 달라지면 source bytes가 같더라도 projection identity·projection digest·candidate identity가 달라진다.
- 핵심 코드:
  - `src/sdp/openmetadata/structural_digest.py`
  - `src/sdp/openmetadata/admission_preview.py`
- 증빙 테스트:
  - `tests/test_openmetadata_structural_digest.py`
  - `tests/test_openmetadata_admission_preview.py`
  - `tests/test_openmetadata_admission_receipt_repair.py`

### INT-OM-008 candidate and observation identity

- 대응: replay key와 `admission_candidate_id`는 source candidate를 식별하고, `receipt_id`는 candidate와 UTC observation instant를 결합한다.
- exact retry는 candidate·receipt ID를 유지한다.
- 같은 candidate의 later re-observation은 candidate ID를 유지하고 receipt ID만 변경한다.
- equivalent timezone instant는 같은 receipt ID로 정규화한다.
- 핵심 코드: `src/sdp/openmetadata/admission_identity.py`
- 증빙 테스트:
  - `tests/test_openmetadata_admission_identity.py`
  - `tests/test_openmetadata_admission_preview.py`

### INT-OM-009 tamper-evident receipt

- 대응: transported receipt를 재수신할 때 nested projection scope·digest, replay key, candidate ID와 receipt ID를 다시 계산한다.
- top-level release·profile·upstream revision·external ID·omitted field와 nested projection의 정합성을 확인한다.
- receipt model은 frozen이며 source input으로부터 deep detached projection을 보유한다.
- 핵심 코드: `src/sdp/openmetadata/admission_models.py`
- 증빙 테스트:
  - `tests/test_openmetadata_receipt_integrity.py`
  - `tests/test_openmetadata_admission_receipt_repair.py`

### INT-OM-010 secured non-mutating route

- 대응: `POST /integrations/openmetadata/v1/table-snapshots:admission-preview`
- #96과 같은 Bearer verifier, role set, verified tenant 404, strict JSON과 body limit을 재사용한다.
- `accepted_for_review`만 반환하며 raw payload 저장, catalog mutation, external network, credential, publication과 authority promotion을 수행하지 않는다.
- 핵심 코드: `src/sdp/openmetadata_routes.py`
- 증빙 테스트:
  - `tests/test_openmetadata_admission_preview.py`
  - `tests/test_openmetadata_admission_receipt_repair.py`

## 9) Stack·release 다음 단계

1. PR #96 current exact head의 Tests·fuzz·SAST·Security Scan·required central gates를 완료하고 유효 review finding과 approval을 정리한다.
2. #96을 보호된 `main`에 정상 병합한다.
3. PR #99를 #96 merge result 위로 non-force restack하고 fresh exact-head evidence를 취득한다.
4. #99와 #97 delta를 파일·행동·문서·테스트별로 비교해 완전 승계를 확인한 뒤에만 #97을 successor supersession 사유로 닫는다.
5. #99를 병합·release한 뒤 3NF persistence → signed ChangeEvent inbox → canonical egress → steward-approved writeback 순서로 진행한다.
6. `context-graph-contracts`의 provider-neutral source·observation·projection receipt contract가 immutable release되기 전에는 downstream consumer가 mutable PR head를 채택하지 않는다.

## 10) 구현 증적 판정

- PR #96과 #99 상태는 GitHub metadata와 current exact-head Checks로 판단한다.
- focused test나 review bot status는 hosted repository/security gate를 대체하지 않는다.
- PR #96·#99·#97은 현재 Draft/open 상태이므로 GA 또는 immutable release로 표현하지 않는다.
- 관련 증적 파일:
  - `src/sdp/openmetadata/`
  - `src/sdp/openmetadata_routes.py`
  - `tests/test_openmetadata_*.py`
  - `docs/adr/0001-openmetadata-anti-corruption-boundary.md`
  - `docs/adr/0002-openmetadata-admission-preview-receipts.md`
  - `docs/integrations/openmetadata.md`
  - `docs/integrations/openmetadata-admission-preview.md`
  - `docs/product-technical-gap-baseline.md`
  - `docs/retrigger-evidence.md`
