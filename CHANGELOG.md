# CHANGELOG

이 문서는 `claude/semantic-portal-pr-merge-e5a48k` 브랜치(PR
[#102](https://github.com/ContextualWisdomLab/semantic-data-portal/pull/102))가
베이스 대비 더하는 변경을 사람이 읽을 수 있게 묶은 것입니다. 164개 커밋 중 112개는
gap-baseline 문서 작업이고, 아래는 제품 동작이 바뀐 나머지입니다.

형식은 [Keep a Changelog](https://keepachangelog.com/)를 따릅니다.

## [Unreleased]

**릴리즈된 것이 아닙니다.** 이 브랜치는 병합되지 않았고, PR #102는 현재 독립
승인 0건이며 필수 체크는 계정 Actions 과금 잠금으로 디스패치 전에 거부되고
있습니다(저장소 자체 워크플로의 마지막 성공: 2026-10-02T09:03:05Z. 그 이후의
성공은 GitHub 자체 할당량으로 도는 Dependabot 뿐이며, 이는 계정 잠금 해제의
증거가 아닙니다). 태그와 릴리즈는 사람의 승인 없이 만들지 않습니다.

아래 모든 항목의 유일한 실행 증거는 로컬 CI 동형 실행입니다:

    pytest                    661 passed, 11 skipped
    pytest (역방향/난수 순서)  순서 무관 통과 (역순 + seed 11/29/77)
    pytest tests/fuzz          11 passed
    python -m sdp.demo_smoke   exit 0, "ready": true

### Security — 테넌트 경계와 존재 oracle

- 데이터셋을 **지목할 수 있는 모든 수단**(경로 파라미터, 요청 본문, 쿼리
  파라미터, 변경 라우트, what-if 리소스)에 대해, 타 테넌트 데이터셋과 존재하지
  않는 id의 응답이 **상태 코드와 본문까지 동일**해집니다. 같은 결함이 여섯 번
  반복됐기 때문에 검사도 URL 모양이 아니라 명명 수단 단위로 열거합니다.
- `/policy/decision`의 측면 채널을 닫았습니다. 인증 없이 호출 가능했고 데이터셋의
  존재 여부와 **소유 테넌트까지** 드러냈으며, 같은 내용을 읽는 형제 라우트는 이미
  403이었습니다. (원 MVP 병합 이후 main에서 동일하게 재현되는 사전 결함입니다.)
- 증빙 표면을 통한 oracle도 닫았습니다: 거부 기록이 prober가 읽을 수 있는 원장에
  나타나는 방식이 "비어 있는 id일 때만 보이는" 신호가 되지 않도록, 두 거부를 모두
  prober 범위 밖에 파일링합니다. 소유 테넌트의 감사자는 자기 자산에 대한 시도를
  그대로 봅니다.
- 카탈로그 discovery / 데이터셋별 조회 / 그래프 읽기 / 증빙 읽기 / SHACL 요약 /
  steward 큐를 전부 호출자 테넌트로 범위화했습니다. 범위에서 빠진 항목은
  `withheld_*` 카운터로 **선언**합니다 — 짧은 목록이 빈 큐로 읽히지 않도록.
- preview row를 지목된 데이터셋의 스키마로 제한했습니다(다른 데이터셋의 PII
  컬럼에 도달하던 경로 차단). 선언된 PII 컬럼은 정책 obligation이 빠뜨려도
  마스킹됩니다 — 마스킹은 최선이 아니라 하한입니다.
- 정책 엔진의 fail-open을 닫았습니다: 평가할 수 없는 action에 `allow`를 주고
  있었고, 공개된 action 이름 10개 전부가 그 경로였습니다.
- SQL validator 우회 3건, 수식된 테이블 우회, 금지 키워드의 부분 문자열 일치를
  고쳤습니다(이제 단어 단위).
- OIDC: `oidc-verify`가 operator 설정만 신뢰합니다(요청 본문이 trust anchor를
  공급해 self-signed platform-admin을 만들던 경로 차단). group→role 매핑은
  tenant scoped이고 매핑마다 audit event를 남깁니다.
- DSN 자격증명 노출과 log sink 자격증명의 공개 manifest 노출을 제거했습니다.
- 호출자가 제어하는 작업량과 메모리 증가에 상한을 두었습니다(쿼리 길이, 개념
  어휘, 제안 큐, 두 증빙 원장). 상한이 생기면 창의 길이로는 "기록됐는가"에 답할
  수 없으므로 단조 카운터를 함께 추가했습니다.

### Fixed — 문서화된 워크플로가 실제로 동작하지 않던 것들

- 문서화된 draft→execute 워크플로에 **통과 경로가 없었습니다**. 통과합니다.
- 제안→승인→노출 루프가 두 개의 단절된 개념 저장소 때문에 승인에서 멈춰
  있었습니다. 승인이 실제로 노출로 이어집니다.
- 온보딩한 데이터셋이 그래프에 전혀 도달하지 않았습니다(`POST /catalog/datasets`
  200 직후 `/graph/nodes/<new>` 404). 이제 도달하고, **삭제도 반영**됩니다 —
  미러가 append-only여서 카탈로그에서 제거된 PII 컬럼이 그래프에 남아 semantic
  search 최상위 결과로 나왔습니다.
- DCAT/JSON-LD export가 소비 불가능했습니다. `@id` 키워드, 실제 컨텍스트 문서,
  그리고 **중첩 속성**까지 매핑했습니다(distribution과 business mapping의
  속성들이 conforming 프로세서에서 전부 버려지고 있었습니다 — pyld로 확인).
- `/llm/draft-query`가 모든 실패에 200을 답하고 증거를 남기지 않았습니다.
- `dataset_ids` 누락 시 500, 문자열 아닌 `user`/`purpose`에 500 → 400.
- 운영 콘솔이 미인증 뷰에서 스스로를 "evidence load failed"로 보고했습니다.
  분류를 상태 코드 allow-list에서 **actor 유무**로 바꿨으므로 어떤 4xx로 바뀌어도
  다시 깨지지 않습니다. actor 안내 문구도 죽은 코드였습니다 — 이제 표시됩니다.
- 증빙 팩이 공개한 proof 링크를 그대로 따라가면 403이었습니다. 열린 링크와
  actor가 필요한 링크를 분리해 게시합니다.
- 죽은 log sink가 API 처리량의 상한이 되지 않도록 breaker를 넣고, sink export를
  event loop에서 내렸습니다.
- 마이그레이션이 끝까지 실패하면 컨테이너가 기동을 거부합니다.

- URL에 credential을 담은 http(s) 로그 sink는 **단 한 건도 전송되지 않았습니다**.
  URL 전체를 `urllib`에 넘겨 userinfo가 연결 host로 남았기 때문입니다 — Loki·Elastic·
  서명 webhook의 문서화된 push URL 형태가 전부 여기에 해당합니다. 측정:
  `https://sdp-ingest:TOKEN@logs.example.net/push`로 설정하면 urllib가
  `sdp-ingest:TOKEN@logs.example.net`에 접속을 시도해 `InvalidURL: nonnumeric port`로
  실패하는데, manifest는 `configured: true, target: logs.example.net`을 계속
  보고했습니다. 게다가 그 예외 메시지가 authority를 인용해 **credential이
  `_EXPORT_ERRORS` 링에 프로세스 수명 내내 보존**되었습니다. 이제 userinfo를 URL에서
  분리해 `Authorization` 헤더(password 있으면 `Basic`, token 하나면 `Bearer`)로
  보내고, host가 없거나 port가 숫자가 아닌 http sink도 file sink와 같은 resolver를
  통과해야 `configured: true`가 됩니다.
- sink export breaker에 **half-open 상태가 없었습니다**. cooldown이 끝나는 순간 모든
  요청이 죽은 sink를 동시에 재시도해, 모든 동기 route가 공유하는 anyio threadpool의
  빈 slot을 `SDP_LOG_SINK_TIMEOUT_MS`만큼 전부 점유했습니다 — breaker를 추가한 이유
  그 자체가 cooldown마다 되돌아왔습니다. 측정(실제 async 경로, 응답하지 않는 sink,
  cooldown 만료 직후 동시 20건): slot 8개면 sink 호출 **8회**, 무제한이면 **20회**,
  outage가 계속되는 동안 cooldown마다 반복. 이제 정확히 **1회**만 probe하고 나머지는
  skip하며, probe가 성공하면 그 즉시 모두에게 닫힙니다. 실패한 probe는 cooldown을
  다시 걸되 claim을 놓아 주므로 복구가 영구히 막히지 않습니다.

### Changed — 정직한 측정

- `paid_pilot_ready`가 작성된 `status` 리터럴에서만 유도되어 **반증 불가능**했습니다.
  이제 배포에서 측정합니다. 더불어 게이트를 충족시키던
  `SDP_EVIDENCE_RETENTION_DAYS`는 `src/` 어디에도 소비자가 없었고 `'banana'`로도
  통과했습니다 — 게이트에서 빼고 `unimplemented_environment`로 **게시**합니다.
  보존 기능은 구현하지 않았습니다(타이머로 감사 기록을 지우는 것은 결함 수정이
  아니라 제품 결정입니다). 레지스트리 전체에 대해 소비자 없는 변수를 금지하는
  기계적 검사를 추가했습니다.
- `local_evidence_retention` 컨트롤은 이름이 보존 정책을 주장하는데 실제로는
  **내구성**(재시작 생존)만 제공했습니다. label과 설명을 사실에 맞췄습니다.
- 같은 이유로 `SDP_ALERT_WEBHOOK_URL`도 게이트에서 뺐습니다. 이 변수를 읽는 코드는
  `_sink_status`가 **설정 여부**를 보고하는 한 곳뿐이고, 이 URL로 POST하는 코드도
  `GET /enterprise/observability`가 게시하는 alert 조건을 평가하는 코드도 없습니다.
  이 사례는 위의 "소비자 없는 변수 금지" 검사의 한계를 드러냅니다 — 소비자가
  **존재**했고(자기 자신의 존재 여부만 읽는 소비자) 검사를 통과했습니다. 그래서
  능력에 대한 증빙은 이름 검색이 아니라 전용 테스트가 담당합니다. 게시되는 alert
  규칙은 삭제하지 않았습니다(조건 자체는 올바르고 operator가 자기 모니터링 스택에
  그대로 구현할 수 있습니다) — 대신 `alert_evaluation: declared_not_evaluated`,
  규칙별 `evaluated: false`, `alert_webhook_routing: declared_unimplemented`로
  표시합니다. alert 평가와 라우팅은 구현하지 않았습니다.
- mock 실행의 수치에 출처 라벨을 붙였습니다. 하나의 라벨
  (`catalog_profile_estimate`)이 세 가지 provenance에 쓰이고 있었고, 그 중 하나는
  주장하는 추정값과 **600배** 차이나는 상한이었습니다. 네 provenance에 네 라벨.
- 거버닝 쓰기의 mutation 이전 감사 행이 `allowed`라고 주장했습니다 —
  `authorized`로 바꾸고, 결과를 아는 라우트는 실제 결과를 기록합니다. 리뷰 한 건이
  증거를 두 번 남기던 문제도 함께.
- `ontology_mapping_coverage`는 **커버리지를 줄이면 올라갔습니다**. `승인 mapping /
  전체 mapping`이었고, 자기 KPI 정의("buyer critical glossary terms 중 매핑된 비율")와 분모가
  달랐습니다. 측정: mapping 12건 중 7건을 지우면 0.917 → **1.0**. 이 값은 `demo_smoke`의
  `ready`와 saleability gate를 0.7 기준으로 통제합니다. 그 분모는 두 가지를 더 가렸습니다 —
  mapping이 전혀 없는 glossary 개념 `이탈 고객`(분모에 없어서 유일한 실제 갭이 보이지 않았음),
  그리고 ontology가 정의하지 않은 개념을 가리키는 mapping 3건(`고객 이탈`·`전환`·`캠페인`;
  이 중 2건이 approved여서 **미정의 개념에 대한 승인 mapping이 ontology coverage의 분자**였습니다).
  세 수치를 각자의 이름으로 게시합니다: glossary 기준 coverage(0.8), 옛 숫자인
  `ontology_mapping_approval_rate`(0.917), 그리고 `unmapped_glossary_concepts` /
  `unregistered_mapping_concept_count`. KPI 정의의 "또는 진행 중인 steward patch 제안" 구절은
  같은 KPI의 guardrail과 모순이었고 구현이 guardrail을 따르고 있었으므로, 숫자를 느슨하게
  맞추는 대신 정의를 엄격한 쪽으로 정정했습니다. **0.8 ≥ 0.7이므로 gate와 `ready`는
  불변입니다** — 결함 수정이고 제품 결정이 아닙니다.

- 게시된 SHACL shape catalog가 **평가되지 않았습니다**. `required_properties`를 읽은
  사람은 그것이 `conforms`를 만든 제약이라고 받아들이는데, 실제로 돌던 것은 shape id만
  빌려 쓴 손으로 쓴 규칙 세 개였습니다. 측정: `format`과 `endpoint`가 빈 distribution →
  `conforms: true`, violation 0건. `concept`가 빈 mapping → `concept`를 지목하는 violation
  없음. 그리고 `DatasetShape`는 실제로 강제되는 `description`·`sensitivity`·`title`·
  `update_frequency`를 게시 목록에서 빠뜨렸습니다 — 카탈로그가 **양방향으로** 틀렸습니다
  (검사하지 않는 property를 게시하고, 검사하는 property를 게시하지 않음). 이제 게시된 모든
  property가 그것을 선언한 항목에 의해 평가되고, `DatasetShape`는 `REQUIRED_METADATA_FIELDS`에서
  유도되어 다시 어긋날 수 없으며, "승인 mapping 최소 1건"은 property 존재 검사가 아니라
  cardinality로 선언됩니다. `shacl_compatible`은 하드코딩 `true`에서 "게시된 모든 shape가
  평가되는가"로 바뀌었고, SHACL 엔진이 돌지 않는다는 사실(`pyshacl`은 의존성이 아닙니다)을
  `validation_engine`/`shacl_engine_executed`로 함께 게시합니다. **시드는 이미 모든 shape를
  만족하므로 `validation_pass_rate`는 1.0에서 움직이지 않았습니다** — gate가 더 많이 측정하면서
  숫자는 그대로입니다.

### Added — 기계가 읽는 계약

- **거부 계약을 OpenAPI 문서에 게시**합니다. 변경 전: 에러 상태를 하나라도
  문서화한 operation이 60개 중 **0개**. 이제 42개이고, 남은 18개는 실제로 거부가
  없는 열린 읽기입니다. 계약은 표 하나에 있고, 코드가 낼 수 있는 상태는
  `sdp.api`의 AST를 따라 유도해 **양방향**으로 대조합니다.
- **요청 본문 계약을 게시**합니다. 네 라우트(`POST /catalog/datasets`,
  `PATCH /catalog/datasets/{id}`, `POST /llm/draft-query`, `POST /browse/query`)는
  이미 pydantic 모델로 검증되고 있었지만 문서에는 `additionalProperties: true`로만
  나타났습니다. 런타임은 그대로이고(400 형태 유지), 게시한 모델이 핸들러가 실제로
  생성하는 모델인지 AST로 확인합니다.
- demo smoke의 `ready` 게이트가 12단계 HTTP 표면을 실제로 통과해야 참이 됩니다.
- 테스트 격리를 `tests/conftest.py`의 autouse fixture 하나로 모든 파일에
  적용했습니다. 이전에는 `test_api.py`에만 있어서 파일 순서를 뒤집으면 5건이
  실패했습니다.

### Known limitations (덮지 않고 적어 둡니다)

- `PostgresGraphStore`의 삭제 경로(`edges_for`/`delete_edge`/`delete_node`)는
  라이브 Postgres+AGE+pgvector에서 **실행해 보지 못했습니다**. in-memory 쪽은
  테스트가 덮고, 실제 DB가 필요한 단언은 `tests/test_integration_age.py`에
  있습니다(DSN 없으면 skip).
- 200 응답 스키마 60건은 미게시입니다. `response_model`은 필드를 필터링하므로
  동작 변경 위험이 크고 별도 변경이어야 합니다.
- 요청 본문 10건은 모델이 없는 라우트입니다(느슨한 키 읽기). 스키마를 손으로
  써 붙이면 핸들러가 읽는 것과 어긋날 수 있고, 모델을 주면 400이 422로 바뀝니다.
- 그래프 스토어 싱글턴은 테스트 격리 대상에서 제외했습니다(snapshot API가 없고,
  테스트를 위해 제품 API를 만드는 것은 범위를 넘습니다).
- alert 조건 평가와 `SDP_ALERT_WEBHOOK_URL` 라우팅은 구현되지 않았습니다(위 참조).
  조건은 게시하지만 계산하지 않습니다.
- http(s) sink의 `Authorization` 분리는 **로컬에서 포착한 요청 객체**로 검증했습니다
  (urllib이 다이얼하는 host, 재구성된 URL, 헤더). 실제 원격 sink에 대한 왕복은
  실행하지 않았습니다.
- SHACL 엔진은 돌지 않습니다. 게시된 shape가 SHACL로 표현 가능하고 동등한 in-process
  검사로 강제된다는 것이 이 표면이 할 수 있는 정직한 주장이며, 그 둘을 모두 게시합니다.
  `pyshacl`을 의존성으로 들이는 것은 (RDF 스택을 끌어오고 CI가 hash-pinned 설치를 쓰므로)
  별도 결정입니다.
- `docs/product-technical-gap-baseline.md`의 `ontology_mapping_coverage | 0.917` 표기는
  head `52bc571` 당시의 보존된 스냅샷이라 고치지 않았습니다. 그 문서가 이미 해당 문단을
  "현재 상태로 인용하지 말 것"이라고 표시하고 있습니다.
