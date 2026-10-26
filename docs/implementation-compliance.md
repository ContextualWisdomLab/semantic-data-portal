# PRD/TRD 요구사항 대응 서술 (semantic-data-portal MVP)

본 문서는 `docs/prd-trd.md` 요구사항 중 **일부**에 대해 구현 경계와 설계 근거를
길게 서술하는 증빙 문서다. **전수 목록이 아니다.**

전수 상태는 생성 문서 [`docs/requirements-coverage.md`](requirements-coverage.md)를
본다. 이 문서는 PRD의 74건 중 13건만 언급하고 있었고 P0 34건 중 25건이 빠져 있었다
(손으로 유지하는 매트릭스가 낡는 방향이 이쪽이다). 전수 매트릭스는 PRD를 파싱해
생성하고 `tests/test_requirements_coverage.py`가 강제하므로 같은 방식으로 낡지
않는다. 여기에 서술이 있는 요구사항은 생성 문서의 `증빙` 포인터가 가리키는 코드와
테스트를 해설하는 것으로 읽으면 된다.

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
- ONT-003 SKOS 계층: `GET /ontology/search`, `GET /ontology/concept/{concept}`,
  `GET /ontology/term/{term}/graph`, 그리고 SKOS 직렬화
  `GET /ontology/vocabulary/jsonld`
- **ONT-004 버전관리**: 이 줄은 전에 "ONT-004~006: 용어 제안-승인-노출 흐름"으로
  묶여 있었고, 그것은 ONT-005의 내용입니다(ONT-004는 버전관리입니다). 실제 대응:
  - `GET /ontology/version` — revision + content digest (공개, 식별자 없음)
  - `GET /ontology/change-log?user=<actor>` — 변경 로그 + 심사자 기록 (거버닝 읽기)
  - `GET /ontology/vocabulary/jsonld` — revision이 이름 붙이는 SKOS/RDFS artifact
  - `GET /ontology/search`·`POST /ontology/resolve` — 버전 스탬프 + digest pin
  - 미해결 경계: OWL axiom이 없고 reasoner가 release를 검증하지 않습니다(ONT-007,
    NFR-QUAL-002). revision·변경 로그·심사자 기록은 프로세스 메모리 한정이며
    `revision_is_durable: false`로 선언합니다. 버전 범위는 어휘와 alias index뿐이고
    `ontology._INDEX`(개념↔dataset 매핑)는 import 시점에 고정됩니다.
- ONT-005 제안-승인-노출 흐름 + **게시 전 ConceptShape 평가**, ONT-006 매핑
  상태(`proposed/approved/rejected`), 근거 문자열/신뢰도
  - `POST /ontology/patches`
  - `POST /ontology/patches/{id}/review`
  - `GET /ontology/patches?user=<actor>` — 제안 큐 읽기는 거버닝 읽기입니다.
    모든 행이 제안자/심사자 신원을 담으므로 `/ontology/change-log`와 같은 게이트를
    쓰고, 공개로 남는 `/enterprise/steward-review`는 `requestor`를 담지 않습니다
    (`withheld_review_item_fields`로 선언).
  - 게이트는 공유 pre-write 검증기(`ontology.validate_concept_registration`)에
    있으므로 두 게시 경로가 하나의 검사로 막힌다. 응답의 `concept_validation`이
    평가 결과를 담는다.
  - 미해결 경계: reasoner 없음(ONT-007). 엔진은 `builtin_shape_checks`,
    `shacl_engine_executed: false`. 계층 target 제약은 warning(시드 어휘가 10회
    위반하므로 violation으로 올릴 수 없다).
- ONT-002 concept/data asset class 분리 — **거부 + 검증** 두 축
  - `POST /catalog/datasets`, `PATCH /catalog/datasets/{id}` — 그래프 미러가 쓸
    노드 id(데이터셋 id = kind `dataset`, `{id}:{컬럼}` = kind `column`)가 이미
    다른 kind로 존재하면 **카탈로그 행을 건드리기 전에** 409. 적대적 검증이
    kind 변경 경로를 전수 열거하면서 찾은 두 구멍이고, kind 규칙을 넣은 커밋
    자체에서 생긴 것이다 — 측정: create는 **500**에 카탈로그 행이 생성·제공되고
    이후 모든 `seed_store`가 raise(한 번의 요청으로 시딩이 영구 불능),
    patch는 **400 "request body is not valid"**인데 제목과 schema 변경이 이미
    적용된 상태. 거부는 자기 사유로 감사 기록된다(허용 결정의 사유가 아니라).
    충돌은 `NodeKindConflict` 전용 타입이다 — `except ValueError`로 잡으면
    `pydantic.ValidationError`도 `ValueError`이므로 잘못된 본문이 409가 된다(측정).
  - 위 가드는 네 개의 카탈로그 mutation 중 두 개만 덮었고, create 경로에서는
    **엉뚱한 id를 검사**했다. 2라운드 적대적 검증 측정:
    - `request.id`를 검사했으므로 id를 생략한 요청(카탈로그가 `dataset-NNN`을
      배정)에서는 `None` 노드를 묻고 통과 → **500 + 행 생성 + 시딩 불능**이 그대로
      남아 있었다. 지금은 `register_dataset`의 `before_commit` 훅으로 id가 확정된
      뒤·첫 쓰기 전에 검사한다.
    - `POST /catalog/datasets/{id}/publish`는 **400**, `.../deprecate`는 **500**인데
      상태/버전 변경이 이미 적용되고 감사 행은 `result='success'`였다 — 호출자가 본
      실패와 장부가 반대로 기록된다. 둘 다 저장된 행의 컬럼으로 사전 검사해 409.
    - patch 가드가 `request.schema is not None`에 걸려 있어 제목만 바꾸는 patch는
      검사를 건너뛰었다(데이터셋 **자기 노드**는 모든 미러가 다시 쓴다). 무조건 검사.
    - 중복 dataset id는 잡히지 않는 bare `ValueError`로 **500**이었다 — 같은 성격의
      거부(id가 이미 점유됨)이므로 `DatasetAlreadyExists` 전용 타입 + 409.
  - 그래프 reconciliation이 선언되지 않은 `has_column` **대상 노드를 무조건 삭제**해
    같은 손상 상태를 두 번의 정상 요청으로 만들 수 있었다 — `POST /graph/edges`로
    개념 노드를 가리키는 `has_column` 간선을 만든 뒤 schema patch를 하면 그 개념
    노드와 그에 닿는 모든 간선이 사라져, 용어 해석 경로가 정의되지 않은 개념처럼
    응답했다. 지금은 `seed_dataset`이 직접 쓰는 `{dataset_id}:` 노드로만 범위를
    좁힌다(간선은 그대로 제거 — 그것은 이 데이터셋의 간선이다).
  - `POST /graph/edges`, `POST /ontology/concepts` — `broader`/`narrower`의 끝점이
    이미 dataset/column 노드면 409. 개념 경로는 어휘 레코드가 먼저 기록되므로
    pre-write 검증기에서 막는다(스토어 게이트만 두면 같은 요청이 **500**이고
    어휘 레코드와 그래프 노드가 이미 기록된다 — 측정값).
  - `GET /enterprise/shacl-validation` → `hierarchy_class_separation` —
    `ConceptHierarchyShape`를 그래프 현재 상태에 평가한다. 쓰기 게이트는 쓰는
    시점에 알려진 kind만 읽으므로, 끝점이 없을 때 쓴 간선의 끝점이 나중에
    dataset으로 생기는 순서는 리포트만 잡는다(측정: `conforms` false,
    `hierarchy_pass_rate` 0.875).
- ONT-007 consistency check — **거부 + 공표**, reasoner는 없음
  - `POST /graph/edges`, `POST /ontology/concepts` — 포섭 순환(자기 자신 포함)을
    닫는 간선은 409. 방향은 `graph_store.subsumption_pair`가 한 번 정규화한다
    (`narrower: A -> B` == `broader: B -> A`; 시드가 둘을 양쪽에서 선언한다).
    이미 게시된 개념도 같은 규칙을 받는다 — 등록기는 재제출을 버리지만 그래프
    미러는 제출된 broader/narrower를 쓰므로, 그 필드만 조기 반환 위로 올렸다
    (측정: 아래에 두면 같은 요청이 미게시 개념에는 409, 시드 개념에는 500).
  - `GET /enterprise/shacl-validation` → `hierarchy_consistency` —
    `cyclic_group_count`(서로 포섭하는 개념 묶음 = 강결합 성분), 그 구성원,
    `consistency_engine: builtin_graph_checks`,
    `reasoner_executed: false`.
  - 미해결 경계: reasoner·OWL axiom 없음, SKOS S27 미검사(시드는 측정상 깨끗),
    이 숫자를 묶을 릴리즈 게이트 자체가 저장소에 없음. 순환성은 그래프의 성질이라
    SHACL shape 목록에 넣지 않았다. 게이트는 kind가 아니라 간선을 읽으므로 단일
    쓰기로는 순환이 생기지 않고, 리포트는 게이트가 본 적 없는 간선(게이트 이전
    데이터, `upsert_edge`를 우회하는 경로, Postgres의 동시 쓰기 창)을 위한 것이다.
  - 미해결 경계: SHACL 프로세서·reasoner 없음, `kind`는 자유 문자열,
    끝점이 없는 간선은 violation이 아니라 `unknown_endpoint_count`(시드가 2회,
    violation으로 올리면 시드 로드 자체가 실패한다 — 역검증). 리포트 범위는
    어휘에 걸린 간선뿐이며 `conformance_scope`가 그 사각을 선언한다.
- 증빙 테스트:
  - `tests/test_api.py::test_ontology_search`
  - `tests/test_api.py::test_ontology_concept_graph`
  - `tests/test_api.py::test_ontology_resolve`
  - `tests/test_api.py::test_ontology_patch_workflow`
  - `tests/test_ontology_version_identity.py` (버전·변경 로그·심사자 기록·동시성)
  - `tests/test_ontology_vocabulary_export.py` (SKOS/RDFS export·IRI 단사성·pin)
  - `tests/test_concept_shape_gate.py` (ConceptShape 게이트·warning 경계·플랫폼 수치)
  - `tests/test_graph_hierarchy_class_separation.py` (ONT-002 계층 간선 거부 +
    ConceptHierarchyShape 평가·범위 선언)
  - `tests/test_catalog_mirror_kind_conflict.py` (카탈로그 미러 kind 충돌 409·
    무기록·감사 사유·잘못된 본문은 400 유지; 네 verb 전수 + 카탈로그가 배정한 id·
    중복 id·reconciliation 범위)
  - `tests/test_graph_hierarchy_consistency.py` (ONT-007 순환 거부 +
    cyclic_group_count 공표·방향 정규화·종료성·선형 비용)

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
  - 같은 이유로 `SDP_ALERT_WEBHOOK_URL`도 `required_environment`에서
    `declared_unimplemented_environment`로 옮겼습니다. 이 변수를 읽는 코드는
    `observability._sink_status`가 **설정 여부**(`alert_webhook_configured`)를 보고하는
    한 곳뿐이고, 이 URL로 POST하는 코드도 `GET /enterprise/observability`가 게시하는 alert
    조건을 평가하는 코드도 없습니다. 이 사례는
    `test_every_required_variable_has_a_consumer`의 한계를 드러냅니다 — 소비자가
    **존재**했고(자기 자신의 존재 여부만 읽는 소비자) 검사를 통과했습니다. 능력에 대한
    증빙은 이름 검색이 아니라
    `tests/test_honest_metrics.py::test_nothing_posts_to_the_alert_webhook`이 담당합니다.
    게시되는 alert 규칙은 삭제하지 않고 `alert_evaluation: declared_not_evaluated`,
    규칙별 `evaluated: false`, `alert_webhook_routing: declared_unimplemented`로 표시합니다.
  - 같은 integration의 **첫 번째** acceptance criterion(`request id, tenant, actor,
    route, status, latency, and evidence ids`)은 문구만 만족하고 있었습니다.
    `evidence_ids`를 caller가 보낸 `X-SDP-Evidence-Ids` 헤더에서 읽었기 때문입니다 —
    로그 행을 증빙 원장(`/policy/decisions`, `/audit/events`)에 연결하는 **그 키**를
    행의 주체인 caller가 정했습니다. 측정: 인증된 governed preview 1회에
    `X-SDP-Evidence-Ids: 00000000-dead-beef-...,another-forged-id`를 보내면 export된
    행의 `evidence_ids`가 그 두 값이고, 서버가 실제 기록한 decision
    `4ff4d6c7-...`은 로그에 없습니다. 어떤 라우트도 이 헤더를 설정하지 않으므로
    평상시 값은 빈 리스트였고, 그 상태로 `fields` 목록에 `evidence_ids`가 공표돼
    있었습니다. 이는 `tenant_id`가 이미 주석으로 인정한 결함(caller 자기주장)과
    같은 종류인데, `tenant_id`는 주장값으로 **선언**되고 미인증 manifest에서
    집계만 공개되는 반면 `evidence_ids`는 correlation 키로 공표됐다는 차이가
    있습니다. 지금은 증빙 행이 지나는 두 지점에서 요청 단위로 수집하고
    (`evidence.collect_request_evidence_ids`), 헤더는 읽지 않습니다.
    manifest는 `evidence_id_source: server_recorded`와
    `caller_asserted_fields: [tenant_id, actor, request_id]`를 함께 공표합니다.
    드리프트 가드는 AST 기반입니다 —
    `tests/test_honest_metrics.py::test_the_log_correlation_key_is_not_read_from_a_request_header`가
    `src` 안에서 그 헤더 이름을 **호출 인자로** 넘기는 곳을 금지합니다(주석은 허용).
  - `SDP_LOG_SINK_URL`의 http(s) 형태는 URL에 담긴 credential을 `Authorization` 헤더로
    분리합니다. 이전에는 URL 전체를 `urllib`에 넘겨 userinfo가 연결 host로 남아
    (`sdp-ingest:TOKEN@logs.example.net` → `InvalidURL: nonnumeric port`) 모든 export가
    실패하는 동안 manifest가 `configured: true`를 보고했고, 예외 메시지가 authority를
    인용해 credential이 `_EXPORT_ERRORS`에 보존되었습니다. http sink도 file sink와 같은
    resolver를 통과해야 `configured: true`가 됩니다.
  - sink export breaker에 half-open 상태를 추가했습니다. cooldown이 끝나는 순간 모든
    요청이 죽은 sink를 동시에 재시도해 (모든 동기 route가 공유하는) anyio threadpool slot을
    전부 점유했습니다 — 측정: 동시 20건에서 slot 8개면 sink 호출 8회, 무제한이면 20회.
    이제 cooldown 만료 후 정확히 1회만 probe합니다.
- `POST /enterprise/auth/oidc-verify`: issuer/audience/expiry/JWKS 서명 검증 후 tenant scoped group mapping으로 `ActorContext`를 생성하고 raw token은 응답에 포함하지 않는다. 신뢰 기준(issuer, audience, JWKS, role map)은 operator 환경 설정에서만 읽으며, request body가 이 네 필드를 보내면 검증 전에 400으로 거절한다.
- `POST /enterprise/auth/oidc-preview`, `POST /enterprise/auth/oidc-verify`: group별 `group_role_bindings`- **정정(oidc-preview 경계)**: 이 라우트는 운영자 설정 role map의 열거 oracle이었습니다.
  측정: 자격증명 없이 임의 subject/tenant로 `groups: ["admins"]` → `roles: ["platform-admin"]`,
  `tenant_scope: "acme-finance"`. 매핑된 group과 매핑되지 않은 group이 구별 가능했습니다. 이제
  actor 없는 호출에는 `SDP_OIDC_GROUP_ROLE_MAP`을 쓰지 않고(요청이 보낸 map과 저장소의 공개 기본
  map은 그대로), `role_map_source`와 `actor_context_verified`를 게시합니다. 또한 claim 목록의
  개수·길이에 상한을 두었습니다 — 이전에는 group 100,000개가 7.58 MB, 2 MB 이름 하나가 4.00 MB
  응답을 만드는 미인증 증폭기였습니다. 잘린 양은 `declared_group_count`/`withheld_group_count`로
  선언하며, verify 경로에도 같은 카운터를 노출합니다(상한이 권한 결과를 바꿀 수 있으므로).
  증빙: `tests/test_oidc_preview_boundary.py` (13건).(group 이름, 부여한 tenant scope, 부여된 role)와 `audit_event_id`를 반환하고 `enterprise/auth/oidc` resource audit event를 남긴다. `sso_oidc_adapter` control은 이로써 `implemented`가 되고 `GET /enterprise/controls`의 `planned_controls`는 0, `status`는 `pilot_ready`가 된다.
- `GET /enterprise/evidence-pack`: metadata validation, SHACL-compatible validation, steward queue, ontology mapping coverage, policy/audit counts, controls, KPI ids, proof endpoints.
  - **정정(게시 수치/계약 4건)**: (1) 감사·정책 카운트가 `list_*(limit=500)`의 `len()`이어서 700건을
    500으로 보고(세 표면) — 실제 카운트 + `*_is_lower_bound`, 그리고 이 모양을 AST로 열거하는 검사.
    (2) `_add_tenant_column`이 컬럼 존재 시 backfill 전에 반환해 반쯤 적용된 마이그레이션이 영구히
    복구되지 않음(ALTER만 하는 빌드가 먼저 출시됨) — 매번 실행되는 idempotent backfill.
    (3) `license`를 create/patch로 설정할 수 없었고 `register_dataset`도 무시 — request 필드를
    펼쳐 생성 + 전 필드 forwarding 기계 검사. (4) `metadata_completeness` target(≥90%)을 비교하는
    코드가 없었음 — `mean_metadata_completeness` 측정 + 게이트. 증빙:
    `tests/test_honest_metrics.py` (+3건), `tests/test_api.py` (+2건),
    `tests/test_catalog_field_forwarding.py` (34건).
  - **정정(SQL 게이트 4건)**: (1) 토큰이 `$`·0x80+ 에서 끊겨 `FROM customer$pii_raw`가 경고 0건
    (parsed `['customer']`)으로 통과 — PostgreSQL identifier continuation 전체를 포함하도록 확장.
    (2) 함수 allowlist 부재로 `pg_terminate_backend(12345)`·`pg_sleep(100000)`·`pg_reload_conf()`가
    경고 0건 — PRD BRW-005(P0)가 요구하는 차단을 allowlist로 구현. (3) source table 이름이 절
    키워드면 drafter가 validator가 거부하는 SQL을 내보냄(draft 200 → execute 400) — 명시적 거부 +
    완성 질의 자체 검사. (4) 선언 컬럼명을 조용히 변환하고 원래 이름을 보고 — `emitted_identifiers`로
    보고하고 모호한 변환은 거부. 증빙: `tests/test_orchestrator.py` (+52건, 절 키워드 24개 전수).
    실행 엔진이 없으므로 함수 부작용과 `$`의 식별자 의미는 PostgreSQL 문서 기준이며 측정한 것은
    게이트 판정입니다.
  - **정정(거버넌스 경계 5건)**: (1) purpose가 `.strip()` 없이 비교되어 `' external-export'`로
    403→200 우회, 기록된 결정은 `allow`. row-level filter는 같은 필드의 정확 비교로
    `'Analysis'`에서 조용히 사라짐. 진입점 정규화로 둘 다 수리. (2)
    `GET /ontology/term/{term}/graph`가 미인증으로 전 테넌트 dataset id 제공(정책 0, 감사 0);
    `policy.scope_concept_graph` 통과 + `dataset_ids` 반환 라우트 열거 강제. (3) 그래프 쓰기가
    `target_tenant_id` 없이 평가되어 외부 테넌트 컬럼의 `pii`를 뒤집을 수 있었음(읽기는 404);
    노드와 엣지 양 끝점 모두 검사. (4) preview 거부가 호출자 자신의 `/policy/decisions`에
    존재를 누출; `evaluate_dataset_scope_refusal`로 라우팅. (5)
    `profile.row_count`가 문자열이면 `/browse/query`가 500이고 결정-감사 짝이 깨짐; 전 타입
    열거 처리 + `unusable_catalog_profile_row_count` 라벨. 증빙:
    `tests/test_governance_boundary.py` (22건), `tests/test_concept_graph_scope.py` (8건),
    `tests/test_payload_type_robustness.py` (+12건).
  - **200 응답 계약 게시**: 변경 전 쓸 수 있는 200 스키마가 60개 중 **0개**였습니다(54개 bare
    `object/additionalProperties`, 4개 bare array, 1개 빈 스키마, 1개 타입만). JSON을 반환하는
    GET **38개**에 대해 라우트를 실행해 유도한 스키마를 게시하고,
    `tests/test_api_response_contract.py`가 실제 응답과 대조합니다(유도 과정의 narrowing 버그 1건을
    이 테스트가 잡았습니다 — `null`로 관측된 필드에 `string`을 게시하던 것). 게시하지 않는 22개는
    사유와 함께 `UNPUBLISHED_RESPONSES`로 선언하며, 선언이 실제와 맞는지도 테스트가 강제합니다.
    `GET /metrics`의 content type도 `application/json`에서 실제 Prometheus 텍스트 타입으로
    정정했습니다.
  - **정정(connector control 판정)**: `implemented`가 `bool(_IMPLEMENTED_PROOF.get(control, []))`
    였습니다 — 같은 파일의 손으로 쓴 dict 멤버십. 측정: 필수 control 11종이 모두 dict에 있어
    `planned`는 도달 불가능했고, 유효한 5쌍 전부에서 11행이 모두 `implemented`였습니다. 이제
    선언된 proof endpoint를 이 빌드가 서비스하는지 확인하고(거짓이 될 수 있는 조건), 증거 강도를
    `declared_only`/`proof_route_served`/`runtime_probe_verified`로 행마다 게시하며
    `control_verification_counts`와 `verdict_basis`를 함께 노출합니다. 기본 데모 배포에서
    runtime 검증 control은 0개입니다. 증빙: `tests/test_connector_verdict_evidence.py` (14건).
  - **정정(shape catalog)**: 게시된 `required_properties`가 평가되지 않았습니다. 측정:
    `format`/`endpoint`가 빈 distribution과 `concept`가 빈 mapping이 모두
    `conforms: true`·violation 0건이었고, `DatasetShape`는 실제 강제되는 네 필드를
    게시하지 않았습니다. 이제 게시된 모든 property가 평가되며
    (`tests/test_semantic_validation.py::test_every_published_required_property_is_evaluated`가
    shape별·property별로 열거해 강제), `shacl_compatible`은 "게시된 모든 shape가 평가되는가"로
    유도되고 `validation_engine`/`shacl_engine_executed`를 함께 게시합니다. 시드는 이미 만족하므로
    `validation_pass_rate`는 1.0 그대로입니다.
  - **정정(ontology coverage)**: `ontology_mapping_coverage`는 `승인 mapping / 전체 mapping`이어서
    **커버리지를 줄이면 올라갔습니다**(측정: mapping 12 → 5, 0.917 → 1.0). 분모를 glossary로 바꿨고
    (측정 0.8), 옛 숫자는 `ontology_mapping_approval_rate`로 이름을 바꿔 유지합니다. 미정의 개념을
    가리키는 mapping 3건은 분자에서 제외하고 `unregistered_mapping_concept_count`로 세며, mapping이
    없는 glossary 개념은 `unmapped_glossary_concepts`로 선언합니다. KPI 정의가 자기 guardrail과
    모순이던 부분도 정정했습니다. 0.8 ≥ 0.7이므로 gate와 `ready`는 불변입니다.
    증빙: `tests/test_ontology_coverage_measurement.py` (11건).
    `docs/product-technical-gap-baseline.md`의 `0.917` 표기는 head `52bc571` 당시의 보존된
    스냅샷이며 그 문서가 이미 "현재 상태로 인용하지 말 것"이라고 명시하고 있습니다.
- `GET /enterprise/console`: buyer/operator가 evidence, KPI, controls, connector 상태를 브라우저에서 확인하는 no-build-dependency UI.
- 증빙 테스트:
  - `tests/test_api.py::test_enterprise_readiness_manifest_exposes_saleable_gates`
  - `tests/test_api.py::test_enterprise_production_readiness_tracks_paid_pilot_integrations`
  - `tests/test_api.py::test_enterprise_evidence_pack_summarizes_buyer_diligence`
  - `tests/test_api.py::test_request_observability_export_writes_bodyless_jsonl`
  - `tests/test_request_evidence_correlation.py` (로그 correlation 키가 서버 기록 값이고 caller가 바꿀 수 없음·거부 요청도 상관 가능·요청 간 격리·상한과 withheld 공표)
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
