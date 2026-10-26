# Semantic Data Portal

온톨로지 기반 **그래프 + 벡터** 시맨틱 데이터 카탈로그 서비스입니다. 개념/데이터셋/컬럼을
속성 그래프(property graph)로 저장하고, 의미 기반 검색(semantic search)으로 데이터를
"찾아주는" 것을 목표로 합니다. 단독(standalone) 실행과 서브모듈(submodule) 임베딩을 모두 지원합니다.

## 그래프 엔진 (Graph Engine)

- **엔진**: 단일 Postgres 인스턴스에서 **Apache AGE**(property graph, openCypher 그래프 순회)
  + **pgvector**(임베딩 KNN 시맨틱 검색)를 함께 사용합니다.
- **영속성(persistence)**: 모듈 전역 dict 대신 DB 백엔드로 이전. 마이그레이션(`migrations/`)이
  그래프/벡터 스키마를 생성하고, 시드(seed)가 카탈로그 + 5개 온톨로지 개념을 멱등(idempotent)하게 적재합니다.
- **폴백(fallback)**: DB DSN이 없으면 의존성 없는 in-memory 백엔드로 동일 API가 동작하여
  CI/서브모듈 환경에서도 그대로 실행됩니다.

### 새 데이터베이스 객체 (2+ word snake_case)

`ontology_concepts`, `concept_edges`(→ `graph_edges`), `dataset_nodes`, `graph_nodes`,
`embedding_vectors`, `config_entries`, `schema_migrations`.

## 목표

- 데이터 탐색: 키워드 카탈로그 검색 + 유사어/용어(ontology) 해석 + **그래프 순회** + **시맨틱 검색**
- 지식 그래프 수집(ingestion): NODES/EDGES/CONCEPTS 업스트림 푸시
- 브라우징: 스키마 조회, 샘플 미리보기, 민감 컬럼 마스킹
- 거버넌스: 정책 판단(PERMISSION), 샘플 정책 근거(Decision/Omission) 노출
- 오케스트레이션: 자연어 질문 기반 질의 후보 추천 + SQL draft 제시

첨부 문서는 다음 경로에 보관됩니다.

- `docs/prd-trd.md`
- `docs/papers/` — 지식그래프/온톨로지/그래프+벡터 하이브리드 검색 논문(인용/요약)

## 로컬 실행

### 로컬 개발 (venv, in-memory 백엔드 — DB 불필요)

```bash
python -m venv .venv
. .venv/bin/activate          # Windows PowerShell: .\.venv\Scripts\Activate.ps1
python -m pip install --require-hashes -r requirements-dev.txt
PYTHONPATH=src uvicorn sdp.api:app --reload
```

이 블록은 한 셸에서 그대로 실행됩니다. 이전에는 `bash` 펜스 안에 PowerShell
활성화 경로(`.venv/Scripts/Activate.ps1`)가 있고 그다음 줄은 POSIX 전용
`VAR=value command` 구문이어서, 어느 셸에서도 통째로 실행할 수 없었습니다.
`requirements-dev.txt`는 **프로젝트 자체를 설치하지 않으므로** `PYTHONPATH=src`가
필요합니다(이것이 이 저장소의 문서화된 경로입니다). `pip install -e .[dev]`로
editable 설치를 하면 `PYTHONPATH` 없이도 import되지만, 그 경로는 hash-pinned
lock을 우회합니다.

`SDP_DATABASE_URL=postgresql://...`를 지정하면 policy decision과 audit event가 tenant/resource/evidence id 기준의 Postgres evidence store에 기록됩니다. `SDP_DATABASE_SSLMODE=require`처럼 SSL mode를 함께 지정할 수 있습니다.
`SDP_SQLITE_PATH=.local/sdp-evidence.sqlite3`를 지정하면 production credential 없이도 같은 evidence store protocol을 로컬 SQLite fallback으로 검증할 수 있습니다. `SDP_DATABASE_URL`이 있으면 Postgres가 SQLite보다 우선합니다.
`SDP_LOG_SINK_URL=file:///data/sdp-requests.jsonl`(절대 경로, `file://` 뒤 authority 없이 슬래시 세 개)과 `SDP_REQUEST_ID_HEADER=X-Request-Id`를 지정하면 request id, tenant, actor, route, status, latency, evidence ids만 body 없이 request observation log로 기록됩니다. `file://.local/...`처럼 상대 경로로 보이는 값은 **거부됩니다** — authority가 경로로 접혀 들어가 파일시스템 루트(`//.local/...`)를 가리켰고, 컨테이너는 `USER 10001`로 `/data`만 쓸 수 있어 매 요청이 `PermissionError`로 실패하는데 manifest는 계속 `implemented`라고 보고했습니다. 이제 쓸 수 없는 설정은 `GET /enterprise/observability`가 `configured: false`와 `invalid_configuration` 사유로 보고합니다(설정값 자체는 공개하지 않습니다 — sink의 내부 호스트와 경로가 담겨 있습니다).
http(s) sink도 지원합니다. URL에 credential을 담은 형태(`https://sdp-ingest:TOKEN@logs.example.net/loki/api/v1/push` — Loki·Elastic·서명 webhook의 문서화된 push URL 형태)는 userinfo를 URL에서 분리해 `Authorization` 헤더로 보냅니다(password가 있으면 `Basic`, token 하나면 `Bearer`; `@`·`:`를 담은 password는 percent-encoding). 이전에는 URL 전체를 `urllib`에 넘겨 userinfo가 연결 host로 남았고(`sdp-ingest:TOKEN@logs.example.net` → `InvalidURL: nonnumeric port`), 모든 export가 실패하는 동안 manifest는 `configured: true`로 보고했으며 예외 메시지가 authority를 인용해 credential이 export error ring에 남았습니다. host가 없거나 port가 숫자가 아닌 http sink도 이제 file sink와 같은 경로로 `configured: false` + `invalid_configuration`으로 보고합니다.
데이터셋 상세(`GET /catalog/datasets/{id}`)와 거버닝 스키마 조회
(`GET /browse/{id}/schema`)는 `quality_warnings` 블록을 함께 공개합니다(LIN-004).
규칙 여섯 개 — 선언된 quality/freshness score, 필수 metadata 충족률, 컬럼별 null 비율·
distinct 비율·선언된 quality issue — 를 임계값과 비교하고, 위반마다 `rule`,
`observed_value`, `threshold`를 담습니다. 이전에는 이 숫자들이 모두 저장·공개되고 있었지만
임계값을 선언한 코드가 없어서 위반이 성립할 수 없었습니다 — **임계값 없는 숫자는 품질
신호가 아닙니다**. 두 가지 경계가 의도적입니다. (1) 비교할 수 없는 입력(값 없음, 숫자 아님,
NaN/inf, bool)은 통과가 아니라 `unevaluated`로 보고합니다 — 없는 데이터가 "깨끗하다"로
읽히면 품질 표면의 목적이 뒤집힙니다. (2) 컬럼 범위 경고는 컬럼 이름과 `discovery_view`가
withhold하는 컬럼별 통계를 담으므로 **정책 게이트 뒤에서만** 공개하고, 공개 표면에는
`withheld_quality_warning_count`를 적습니다(짧은 목록이 깨끗한 데이터셋으로 읽히지 않게).
임계값은 제품 전역 기본값이며 테넌트/도메인별 설정이 아닙니다 — 모든 경고에
`threshold_source: product_default`로 적습니다.

`GET /enterprise/latency-budgets`는 PRD가 선언한 여섯 개 p95 예산(NFR-PERF-001~006)을
그 예산이 적용되는 라우트에 묶어 두고, 이 워커가 실제로 관측한 성공 응답의 nearest-rank p95와
비교합니다. 이전에는 미들웨어가 요청별 `latency_ms`를 기록하고 manifest가 그것을 공개하면서도
어떤 코드도 예산을 호명하지 않았습니다 — 비교 대상이 없는 목표는 gate가 아닙니다.
**측정은 단방향입니다.** 관측은 이 프로세스(in-memory store, seed 데이터, 단일 워커, 클라이언트와
앱 사이에 네트워크 없음)에서 나오고, 배포에는 데이터베이스·실제 데이터셋 규모·동시성·네트워크 홉이
더해져 요청이 느려지기만 합니다. 따라서 in-process p95는 배포 p95의 **하한**이고, 예산 초과는
결정적이지만 예산 미달은 배포에 대해 아무것도 증명하지 않습니다. 그래서 공개하는 필드는
`within_budget`이 아니라 `budget_refuted`이며, `budget_confirmation_possible: false`와 그 사유를
함께 적습니다. 표본이 `minimum_sample`(20) 미만인 표면은 `insufficient_sample`로 보고하고
**어느 방향으로도** 판정하지 않습니다 — 표본 몇 개의 p95는 이름만 백분위인 표본 최댓값입니다.
공개되는 것은 라우트 **템플릿**뿐입니다(구체 경로에는 dataset id가 박혀 있어 manifest가 요청별
피드를 withhold하는 것과 같은 경계입니다).

`SDP_ALERT_WEBHOOK_URL`은 **구현되었고 선택 사항입니다**. 한동안은 선언만 되어 있었고 — 이 값을 읽는 코드가 `_sink_status`가 설정 여부(`alert_webhook_configured`)를 보고하는 한 곳뿐이었으므로 `required_environment`에서 `declared_unimplemented_environment`로 옮겨져 있었습니다. 전달이 들어온 지금 그 선언은 철회했고, `required_environment`로 **옮기지는 않았습니다**: 경보는 선택 사항이고, 게이트는 `_is_set`으로 presence만 보므로 scheme이 없어 POST 자체가 불가능한 값이 게이트를 통과하게 됩니다 — 라우팅하지 않는 값이 paid-pilot gate를 통과할 수 있으면 그 gate는 아무것도 측정하지 않습니다. **평가(evaluation)와 전달(routing)은 여전히 다릅니다**: 공개되는 세 규칙 중 `policy_audit_gap`과 `connector_probe_failure`는 **이 서비스가 직접 계산하고**(`evaluated: true`, `evaluation: measured_in_process`, `firing`과 `observed_total`을 함께 공개하고 `/metrics`가 `sdp_governed_requests_without_evidence_total`·`sdp_connector_probe_failures_total`로 내보냅니다) **전달 대상**입니다(`routable: true`). `central_workflow_backlog`은 이 서비스가 볼 수 없는 GitHub Actions 상태가 필요하므로 `evaluated: false`·`routable: false`로 남고 `not_evaluated_because`가 그 이유를 함께 공개합니다. 최상위 `alert_evaluation`은 세 규칙에 하나의 주장을 하지 않도록 `per_rule`이고, `alert_routing: implemented` 옆에 `alert_delivery`가 실제로 측정된 전이·전달·억제 횟수를 함께 게시합니다 — 전달 주장이 아니라 전달 사실입니다. 전달 경계는 좁습니다: routable rule이 not-firing→firing으로 전이할 때 **episode당 1회** POST하고, 이미 firing인 동안의 2..N번째 증가는 세어서 버리며(그 수도 게시합니다), 재시도·큐·내구성 있는 실패 기록은 없고, 실패는 예외 타입과 단계만 보관합니다(URL은 어디에도 남기지 않습니다 — userinfo를 담은 webhook에서 urllib가 만드는 메시지가 복호화된 credential 자체이기 때문입니다). 공개 surface에는 alert 대상 호스트를 **redact해서도** 게시하지 않습니다. 이 단락은 한동안 두 규칙 **모두** 평가되지 않는다고 적고 있었고, 그것은 `policy_audit_gap`에 계산이 들어온 뒤로 거짓이었습니다 — README를 믿은 운영자는 이 서비스가 실제로 계산하는 규칙에 모니터링을 붙이지 않게 됩니다. 같은 문장이 세 곳(여기, `observability.py`의 alert 블록 주석, `production.py`의 주석)에 남아 각각 한 라운드 뒤에 발견됐으므로, 이제 `tests/test_honest_metrics.py`가 평가에 대한 그 문장과 전달에 대한 같은 종류의 문장을 모두 기계적으로 금지합니다.
sink export breaker는 closed/open에 half-open을 추가했습니다. 이전에는 cooldown이 끝나는 순간 모든 요청이 죽은 sink를 동시에 다시 호출해 (모든 동기 route가 공유하는) anyio threadpool의 빈 slot을 전부 `SDP_LOG_SINK_TIMEOUT_MS`만큼 점유했습니다 — 측정: 동시 요청 20건에서 slot 8개면 sink 호출 8회, 무제한이면 20회, outage가 계속되는 동안 cooldown마다 반복. 이제 cooldown 만료 후 정확히 한 요청만 probe하고(측정: 1회) 나머지는 skip하며, probe가 성공하면 그 즉시 모두에게 breaker가 닫힙니다.
`GET /enterprise/shacl-validation`과 `/catalog/datasets/{id}/semantic-validation`이 게시하는
shape catalog는 **실제로 평가됩니다**. 이전에는 `required_properties`를 게시하면서 평가하지 않았습니다 —
측정: `format`과 `endpoint`가 빈 distribution은 `conforms: true`에 violation 0건이었고,
`concept`가 빈 mapping도 마찬가지였으며, `DatasetShape`는 실제로 강제되는
`description`·`sensitivity`·`title`·`update_frequency`를 게시 목록에서 빠뜨렸습니다(양방향 오류).
이제 `DatasetShape.required_properties`는 `REQUIRED_METADATA_FIELDS`에서 유도되고, mapping과
distribution은 각자의 shape로 평가되며(violation path는 `distributions[0].format`처럼 색인됩니다),
"승인된 mapping 최소 1건"은 property 존재 검사가 아니라 `min_approved_count` cardinality로 선언됩니다.
`shacl_compatible`은 하드코딩 `true`가 아니라 "게시된 모든 shape가 평가되는가"로 유도되고,
`validation_engine: builtin_shape_checks` / `shacl_engine_executed: false`를 함께 게시합니다
(`pyshacl`은 이 저장소의 의존성이 아닙니다 — SHACL 엔진이 돌았다고 주장하지 않습니다).
시드 데이터셋은 모두 게시된 shape를 이미 만족하므로 `validation_pass_rate`는 1.0에서 변하지 않습니다.

`ontology_mapping_coverage`는 **glossary 기준으로 측정**합니다. 이전에는 `승인 mapping / 전체
mapping`이었고, 자기 KPI 정의("buyer critical glossary terms 중 매핑된 비율")와 분모가 달랐습니다 —
분모가 "우연히 존재하는 mapping"이었기 때문에 **커버리지를 줄이면 숫자가 올라갔습니다**(측정: mapping
12건 중 7건을 지우면 0.917 → 1.0). 이 값은 `sdp.demo_smoke`의 `ready`와 saleability gate를 0.7
기준으로 통제합니다. 또한 그 분모는 두 가지를 가렸습니다: mapping이 전혀 없는 glossary 개념
`이탈 고객`(분모에 없어서 유일한 실제 갭이 보이지 않았음)과, ontology에 정의되지 않은 개념을 가리키는
mapping 3건(`고객 이탈`·`전환`·`캠페인` — 이 중 2건이 approved여서 **미정의 개념에 대한 승인 mapping이
ontology coverage의 분자로 계산**되었습니다). 이제 세 수치를 각자의 이름으로 게시합니다:
`ontology_mapping_coverage`(승인 mapping이 1건 이상인 glossary 개념 비율, 측정 0.8),
`ontology_mapping_approval_rate`(옛 숫자, 0.917), `unmapped_glossary_concepts`,
`unregistered_mapping_concept_count`. KPI 정의의 "또는 진행 중인 steward patch 제안" 구절은 같은 KPI의
guardrail("제안 mapping은 승인으로 취급하지 않는다")과 모순이었고, 구현이 guardrail을 따르고 있었으므로
정의를 엄격한 쪽으로 정정했습니다. 0.8 ≥ 0.7이므로 gate와 `ready`는 그대로입니다.
`GET /enterprise/connectors/{connector_id}/probe`의 control 판정은 **사전 멤버십 동어반복**이었습니다.
`implemented = bool(_IMPLEMENTED_PROOF.get(control, []))` — "이 control이 구현되었는가"를
"이 control 이름이 같은 파일의 손으로 쓴 dict의 키인가"로 답했습니다. 측정(유효한 커넥터×데이터셋 5쌍,
필수 control 11종 전부): dict에 11/11이 있으므로 `planned`는 **도달 불가능**했고, 판정을 움직일 수 있는
것은 `credential_vault`의 secret 존재 확인 하나뿐이었습니다(그래서 전체 행렬에서
`rest_connector`/`marketing-campaign`만 `contract_only`였습니다 — 측정하는 유일한 control이 정보를
전부 나르고 있었습니다). 이제 control이 선언한 proof endpoint를 **이 빌드가 실제로 서비스하는지** 확인하고
(라우트 이름이 바뀌면 control이 `planned`로 내려갑니다), 행마다 증거 강도를 함께 게시합니다 —
`declared_only` / `proof_route_served` / `runtime_probe_verified`와 probe 단위 집계
`control_verification_counts`, 그리고 `verdict_basis`(판정이 무엇을 주장하고 무엇을 주장하지 않는지).
여기서 나오는 정직한 숫자: 기본 데모 배포에서 runtime으로 검증되는 control은 **0개**입니다
(runtime 확인이 있는 control은 `credential_vault` 하나이고, 그것을 요구하는 커넥터의 secret reference가
설정되어 있지 않습니다). secret을 설정하면 1개가 됩니다. 또한 `credential_vault`의
`proof_endpoints`에 들어 있던 환경변수 이름 `SDP_CONNECTOR_SECRET_REF_PREFIX`는 endpoint가 아니므로
`config_proof` 필드로 분리했습니다.
`GET /openapi.json`이 **쓸 수 있는 200 스키마를 60개 operation 중 0개**에 게시하고 있었습니다
(측정: 54개가 `{"type":"object","additionalProperties":true}`, 4개가 빈 배열, 1개가 빈 스키마,
1개가 타입만). 모든 핸들러가 `-> dict[str, Any]`로 선언되어 있어 사실이지만 소비자에게는 아무 정보가
없고, 문서로 클라이언트를 생성하는 구매자는 카탈로그·evidence pack·모든 거버닝 읽기에 대해
`Dict[str, Any]`를 받았습니다. 거부 계약과 요청 본문을 게시한 것과 같은 이유로, 세 번째이자 마지막
계약으로 200 본문을 게시합니다(JSON을 반환하는 GET **38개**).

스키마는 **라우트를 실행해서 유도**합니다 — 손으로 쓴 응답 스키마는 이 제품이 거부하는 바로 그
drift(코드와 일치하지 않는 게시된 주장)이기 때문입니다. `tests/test_api_response_contract.py`가
게시된 모든 operation을 호출해 실제 응답이 게시 스키마를 만족하는지 검증하므로 drift는 CI에서
실패합니다. 유도 규칙은 과대 주장을 막도록 선택했습니다: `required`를 **아무 것도** 표시하지 않고
(상태에 따라 없는 필드가 있습니다), 숫자는 `integer`가 아니라 항상 `number`이며, `null`로 관측된
값과 빈 배열의 items는 `type: null`이 아니라 `{}`("any")로, 서로 다른 타입이 관측되면 둘 중 하나를
고르지 않고 `{}`로 게시합니다. 게시하지 않는 것은 **선언**합니다: 본문이 필요한 non-GET 20개
(mutation을 구동해야 하고, 그러면 검증 테스트가 그래프 스토어 상태를 남깁니다 — 요청 본문 쪽은
이미 게시되어 있습니다). `GET /metrics`는 `application/json` + 빈 스키마로 문서화되어 있어 생성된
클라이언트가 Prometheus 텍스트를 JSON으로 파싱하려 했을 것이므로, 실제 content type
(`text/plain; version=0.0.4; charset=utf-8`)으로 정정했습니다.
**거버넌스 경계 5건 수리.** 모두 한쪽 방향으로는 유지되고 다른 방향으로 열려 있던 것들입니다.

1. **purpose binding이 공백 하나로 우회**되었습니다. `policy.evaluate`는 `action`을
   `.strip().lower()`로 정규화하면서 다른 호출자 제어 차원인 `purpose`는 `.lower()`만
   했습니다. 측정: `'external-export'`·`'EXTERNAL-EXPORT'` → 403이지만
   `' external-export'`·`'external-export '`·`'external-export\t'` → **200**
   (preview와 governed query 양쪽). 기록된 결정은 `effect: allow`였으므로 **증빙 원장이
   해당 반출을 정책 승인된 것으로 증명**했습니다. 대소문자는 막히므로 통합 담당자가 공백
   민감성을 의심할 이유가 없었습니다. 같은 필드의 거울 결함도 함께: high sensitivity
   데이터셋의 row-level filter가 `purpose == "analysis"` 정확 비교였으므로 `'Analysis'`나
   `' analysis'`에서 **조용히 사라졌습니다**(거부가 아니라 obligation 누락). 진입점에서 한 번
   정규화해 두 분기가 다시 어긋나지 않게 했습니다.
2. **`GET /ontology/term/{term}/graph`가 미인증 호출자에게 모든 테넌트의 dataset id를
   제공**했습니다 — 정책 평가 0건, 감사 이벤트 0건. 같은 사실을 제공하는 두 형제 라우트
   (`/ontology/concept/{concept}`는 `dataset_ids: []` + `withheld 4`,
   `POST /llm/search`는 403)는 이를 거부합니다. 이 payload의 **세 번째** 유출 경로이며,
   앞의 두 건은 `ontology.concept_assets`에 tenant scope를 주어 닫았지만 이 라우트는 graph
   store의 `concept_graph`를 읽습니다. 이제 `policy.scope_concept_graph`를 통과하고
   `withheld_dataset_count`를 선언합니다. 개념 어휘(정의·alias)는 공유 자산이므로 그대로
   열려 있습니다. 네 번째 호출자를 잡기 위해 **게시된 응답 계약에서 `dataset_ids`를 반환하는
   라우트를 열거**해 익명 호출에 타 테넌트 id가 섞이지 않는지 기계적으로 강제합니다.
3. **그래프 쓰기 경계가 fail-open**이었습니다. `_authorize_graph_write`가 `create` 액션을
   `target_tenant_id` 없이 평가했고, `create`는 카탈로그에서 소유 테넌트를 해석할 수 없는
   유일한 분기이므로 테넌트 검사를 **건너뛰었습니다**. 측정: tenant=demo인 `data-admin`이
   `zeta-secret:customer_email`을 **읽으면 404**인데 **쓰면 200**이고 `pii: true → false`로
   바뀌었습니다. 읽을 수도 없는 컬럼의 PII 분류를 외부 테넌트 admin이 조용히 뒤집을 수
   있었고, 그 메타데이터는 `POST /search/semantic`·`POST /graph/query`가 사용합니다. 엣지는
   source만 검사했으므로 target도 함께 검사합니다. 남은 구별(존재하지 않는 데이터셋 접두사는
   허용, 외부 테넌트는 403)은 `admin` 역할이 필요하므로 익명·analyst로 닫은 oracle보다
   좁으며, 테스트로 **명시**해 두었습니다.
4. **preview 거부가 원장을 통해 존재를 누출**했습니다. HTTP 본문은 이미 동일했지만 호출자
   자신의 `GET /policy/decisions`는 아니었습니다 — 외부 id는 0행, 없는 id는 1행. 형제
   라우트는 모두 `policy.evaluate_dataset_scope_refusal`을 쓰는데 preview만 빠져 있었습니다.
5. **`POST /browse/query`가 500**이었습니다. `profile.row_count`가 JSON 문자열이면
   (`POST /catalog/datasets`가 그대로 저장합니다) `_row_count_estimate`가 `TypeError`로
   죽었고, 그 crash가 **정책 결정과 감사 기록 사이**에 떨어져 `decisions +1 audits +0` —
   CLAUDE.md가 타협 불가로 선언한 짝을 깼습니다. 모든 타입을 열거해 처리하며, 숫자가 아닌
   값은 추정치로 **라벨하지 않고** `unusable_catalog_profile_row_count`로 보고합니다.
**SQL 안전성 게이트 4건 수리.** `validate_sql_query`는 실제 엔진이 뒤에 놓일 문서화된 경계이므로,
경고 0건으로 통과시킨 질의는 엔진이 할 일에 대한 **주장**입니다.

- **식별자 연속 문자로 테이블 이름을 짧게 만들 수 있었습니다.** 토큰이 `[A-Za-z_][\w.]*`여서 `$`와
  0x80 이상 바이트에서 끊겼고, 하나의 식별자를 둘로 쪼갠 뒤 뒷부분을 alias로 버렸습니다. 측정
  (allowlist = `customer`): `FROM customer$pii_raw` → 경고 **0건**, parsed `['customer']`.
  PostgreSQL의 identifier continuation은 `[A-Za-z\200-\377_0-9$]`이므로 엔진은 단일 테이블
  `customer$pii_raw`를 읽습니다 — allowlist가 질의가 지칭하지 않는 이름에 대해 증명한 셈입니다
  (이미 critical로 분류해 닫은 comma-FROM 우회와 같은 unsoundness 부류). 토큰을 넓혀 참조가 통째로
  파싱되어 비교되게 했고, 증명할 수 없는 이름은 거부됩니다(fail-closed).
- **함수 allowlist가 없었습니다.** literal guard가 인자 있는 호출
  (`pg_read_file($$...$$)` → `literal_values_not_allowed`)은 잡지만, **무인자·정수인자** 호출은
  안전 경로에 남아 있었습니다. 측정, 모두 경고 0건: `pg_terminate_backend(12345)`,
  `lo_unlink(1)`, `pg_sleep(100000)`, `pg_reload_conf()`. `docs/prd-trd.md`의 BRW-005
  ("read-only SELECT만 허용 … DDL/DML/unsafe function 차단")는 **P0 요구사항**입니다. deny-list는
  무한집합이라 증명할 수 없으므로 allowlist(`count`·`sum`·`avg`·`min`·`max` — drafter가 실제로
  내보내는 것 + 표준 집계)로 막고, 밖의 호출은 `unauthorized_function_call`입니다. 이 저장소에는
  살아 있는 엔진이 없고 `execute_query`는 SQL을 실행하지 않으므로, 위 함수들의 부작용과 `$`의
  식별자 의미는 PostgreSQL 문서 기준이며 **측정한 것은 게이트의 판정**입니다.
- **drafter가 자기 validator가 거부하는 SQL을 내보냈습니다.** source table 이름이 SQL 절
  키워드(`order` 등 24개)와 겹치면 파서가 테이블 목록을 벗어나 `None`을 반환하고 validator가
  `unauthorized_table_reference`로 거부합니다. 측정: draft 200 → execute **400**. 문서화된
  draft-then-execute 흐름에서 제품이 자기 출력을 거버넌스 위반으로 고발하는 셈이고,
  `FROM order`는 인용 없는 예약어 SQL이라 PostgreSQL도 거부합니다. 이제 명확한 사유와 함께
  거부하며, 더불어 **완성된 질의를 자기 validator로 자체 검사**해 세 번째 원인을 보고 없이
  잡습니다(이 부류는 이미 두 번 — `interval '<n> day'` 리터럴, 절 키워드 — 하나씩 고쳐졌습니다).
- **선언된 컬럼명을 조용히 다른 식별자로 바꾸고 원래 이름을 보고**했습니다. `order amount`가
  `order_amount`로 나가는데 `requested_columns`는 `order amount`를 보고하고 assumptions는
  "카탈로그에서 검증된 컬럼만 사용"이라고 주장했습니다 — 구매자는 창고가
  `column "order_amount" does not exist`라고 답할 때 알게 됩니다. 변환 자체는 유지합니다(이 게이트가
  큰따옴표를 `literal_values_not_allowed`로 거부하므로 인용 식별자는 애초에 실행될 수 없고,
  하이픈이 SQL에 닿지 않게 하는 기존 계약도 있습니다). 대신 `emitted_identifiers`로 **보고**하고,
  변환이 다른 선언 컬럼과 충돌해 **모호하면 거부**합니다(매핑이 injective가 아니므로 엉뚱한 컬럼을
  집계할 수 있었습니다).
**게시된 수치/계약 4건 수리.**

- **거버넌스 카운트가 페이지 크기였습니다.** `sdp_request_observations_total`은 이미 고쳤지만 감사·정책
  gauge는 같은 방식으로 읽히고 있었습니다. 측정(원장에 거버닝 mutation 700건): `catalog._AUDIT_LOG`
  700, 그런데 `/metrics` `sdp_audit_events_observed_total` **500**,
  `/enterprise/evidence-pack` `audit_event_count` **500**, `/enterprise/observability` **500** —
  세 표면 모두 `list_*(limit=500)`의 `len()`이었습니다. 자기 페이지를 넘을 수 없는 카운터는 카운터가
  아니며, 이 숫자는 구매자가 거버넌스 추적이 실재하는지 판단하는 근거입니다. 실제 카운트를 쓰고,
  상한에 도달하면 값이 아니라 **하한**으로 게시합니다(`*_is_lower_bound`). 다음 사례는 AST 검사가
  잡습니다 — `list_*(limit=N)`에서 대입된 변수의 `len()`이 `*_count`/`*_total` 키로 게시되는 모양을
  열거합니다.
- **반쯤 적용된 tenant 마이그레이션이 영구히 복구되지 않았습니다.** `_add_tenant_column`이 컬럼이
  이미 있으면 **자기 backfill 전에** 반환했습니다. 이 메서드는 ALTER만 하는 형태로 먼저 출시되었으므로
  그 빌드로 업그레이드된 SQLite 원장은 전부 컬럼이 있는 상태이고 backfill이 영원히 돌지 않습니다
  (ALTER와 UPDATE 사이에서 죽은 프로세스도 같은 상태). 측정(payload에 복구 가능한 tenant가 있는
  원장): 현재 스토어로 열어도 `['unresolved']` 그대로 — 소유 테넌트의 감사자가 모든 과거 행을
  잃습니다. SQLite는 문서화된 데모/파일럿 배포(영속 볼륨)이므로 바로 이 in-place 업그레이드
  경우입니다. 이제 backfill이 매번 돌고(미복구 행만 건드리므로 idempotent), 두 가지 tenant 표기를
  모두 복구합니다.
- **`license`를 어떤 API 경로로도 설정할 수 없었습니다.** `Dataset`은 처음부터 이 필드를 갖고
  있었지만 두 request 모델에 없어 값이 조용히 버려졌습니다 — 측정: create에 `CC-BY-4.0`을 보내도
  `internal`, patch에 `MIT`를 보내도 `internal`, 시드 전체가 `internal`. 데이터 카탈로그에서
  라이선스는 diligence 독자가 가장 먼저 확인하는 필드이고, `metadata_completeness` KPI 정의가
  세는 필드 목록에도 들어 있습니다. 노출만으로는 부족했습니다: `register_dataset`이 필드를 손으로
  나열해 생성했기 때문에 새 필드를 또 무시했습니다. 이제 request의 필드를 그대로 펼쳐 생성하고,
  **모든 request 필드가 저장 모델에 도달하는지 기계적으로** 검사합니다.
- **`metadata_completeness` KPI의 target을 아무것도 비교하지 않았습니다.**
  `target: ">=90 percent display coverage"`, `status: implemented`인데 코드에 0.90 비교가
  없었습니다(증빙 경로의 임계값은 `metadata_validation_pass_rate` 0.95 — 더 엄격한 다른 측정 —
  과 ontology coverage 0.7뿐). 비교하지 않는 target은 게이트가 아닙니다.
  `/enterprise/evidence-pack`이 `mean_metadata_completeness`를 측정해 0.90으로 게이트합니다.
REST connector secret은 `SDP_CONNECTOR_SECRET_REF_PREFIX=SDP_CONNECTOR_SECRET_` 기준의 env secret reference로 조회합니다. 예: `SDP_CONNECTOR_SECRET_REST_CONNECTOR_MARKETING_CAMPAIGN_TOKEN` 값은 presence만 검증하며 API 응답에는 노출하지 않습니다.
OIDC token verification은 `SDP_OIDC_ISSUER`, `SDP_OIDC_AUDIENCE`, `SDP_OIDC_JWKS_URL`(또는 JWKS 문서를 그대로 담는 `SDP_OIDC_JWKS`), `SDP_OIDC_GROUP_ROLE_MAP`를 사용합니다. 이 네 가지는 **operator 설정 전용**입니다. `POST /enterprise/auth/oidc-verify`의 body는 `token` 하나만 받고, `issuer`·`audience`·`jwks`·`role_map`이 body에 오면 400으로 거절합니다 — 호출자가 자기 토큰의 신뢰 기준을 지정할 수 있으면 스스로 서명한 토큰으로 임의 tenant의 platform-admin을 발급받을 수 있기 때문입니다.
`SDP_OIDC_GROUP_ROLE_MAP`은 두 가지 형태를 받습니다. flat `{"group": ["role"]}`은 모든 tenant에 적용되는 wildcard scope(`*`)가 되고, tenant scoped `{"tenant": {"group": ["role"]}}`은 해당 tenant에만 적용됩니다. 같은 group이 두 scope에 모두 있으면 tenant scope가 wildcard를 대체하므로, tenant scope에 빈 role 목록을 쓰면 wildcard 부여를 해당 tenant에서만 회수할 수 있습니다. 두 형태를 한 map에 섞으면 tenant 식별자를 group 이름으로 잘못 읽는 설정 오류이므로 요청이 400으로 거절됩니다.
`POST /enterprise/auth/oidc-preview`는 **운영자가 설정한 role map을 열거할 수 있는 oracle**이었습니다.
측정(`SDP_OIDC_GROUP_ROLE_MAP={"acme-finance": {"admins": ["platform-admin"]}}`, 자격증명 없음):
임의 subject/tenant로 `groups: ["admins"]`를 보내면 200과 함께
`actor_context.roles: ["platform-admin"]`, `group_role_bindings[0].tenant_scope: "acme-finance"`가
돌아왔고, 매핑되지 않은 group은 빈 scope·빈 role로 돌아와 **구별 가능**했으므로 group 이름을 하나씩
추측해 배포의 group→role 정책과 유효한 tenant scope를 전부 읽을 수 있었습니다. trust anchor를 request
body에서 거절하는 이유, 그리고 이 라우트의 원장 기록에 actor를 요구한 이유와 같은 범주입니다. 수정은
의도적으로 좁습니다 — 호출자가 **직접 보낸** `role_map`에 대한 preview는 그대로 열려 있고(이 라우트의
목적), 저장소에 상수로 들어 있는 **기본 map**도 비밀이 아니므로 그대로 동작합니다. actor 없이 숨기는
것은 배포 자신의 `SDP_OIDC_GROUP_ROLE_MAP`뿐이며, 응답의 `role_map_source`
(`request`/`shipped_default`/`operator_configured`/`withheld_...`)가 어느 map을 썼는지 밝힙니다.
`actor_context_verified: false`도 함께 반환합니다 — 이 값은 해석된 `ActorContext`와 같은 모양이지만
서명을 검증하지 않은 "이런 claim이면 이렇게 매핑된다"의 결과입니다.

claim 목록은 개수와 값 길이에 상한이 있습니다(`MAX_CLAIM_VALUES` / `MAX_CLAIM_VALUE_CHARS` = 256).
이전에는 둘 다 무제한이었고 group 이름이 `groups`와 `group_role_bindings[].group_name`에 **두 번**
돌아와, 자격증명이 필요 없는 라우트가 증폭기였습니다 — 측정: group 100,000개 → 7.58 MB / 642 ms,
2 MB짜리 group 이름 하나 → 4.00 MB(요청보다 큰 응답). 지금은 각각 17.8 KB, 1.2 KB이고 잘린 양은
`declared_group_count`/`withheld_group_count`와 `...[truncated]` 표시로 **선언**합니다.
`oidc-verify`에서는 이 상한이 권한 결과를 바꿀 수 있습니다(상한을 넘은 group은 role을 부여하지 않음 —
부여가 아니라 보류이므로 fail-closed). 그래서 같은 두 카운터를 verify 응답에도 게시합니다.
`POST /enterprise/auth/oidc-preview`와 `POST /enterprise/auth/oidc-verify`는 group별 `group_role_bindings`(group 이름, 부여한 tenant scope, 부여된 role)와 `audit_event_id`를 함께 반환하고, 같은 내용을 `enterprise/auth/oidc` resource의 audit event로 기록합니다. token과 raw claim payload는 응답에도 evidence store에도 기록되지 않습니다.

Docker 기반 로컬 데모는 다음 명령으로 실행합니다.

```bash
docker compose up --build
```

컨테이너는 `SDP_SQLITE_PATH=/data/sdp-evidence.sqlite3`를 사용하고 healthcheck로
`/healthz`를 조회합니다 — `Dockerfile`과 `docker-compose.yml`이 실제로 조회하는
경로이며, 상수를 돌려주는 `/health`가 아니라 백엔드 준비 상태를 보고 503을 낼 수
있는 쪽입니다(아래 Postgres 프로파일 설명과 같은 구분입니다).

Postgres evidence store까지 포함한 paid-pilot 프로파일은 다음 명령으로 실행합니다.

```bash
export POSTGRES_USER=sdp_app
export POSTGRES_PASSWORD='<strong-postgres-password>'
export SDP_DATABASE_URL='postgresql://sdp_app:<url-encoded-password>@postgres:5432/sdp'
docker compose --profile postgres up --build
```

이 프로파일은 `semantic-data-portal-postgres`를 `http://localhost:8001`에 열고(앱 서비스 host port는 세 개 모두 `127.0.0.1`에만 바인딩되며, 컨테이너 healthcheck는 상수를 돌려주는 `/health`가 아니라 백엔드 준비 상태를 보고 503을 내는 `/healthz`를 조회합니다), `SDP_DATABASE_URL`과 `POSTGRES_PASSWORD`를 필수 env로 요구합니다. `POSTGRES_USER`는 `sdp_app` 기본값이 있지만 명시 설정을 권장합니다. Postgres host port는 기본적으로 `127.0.0.1:54329`에만 바인딩되어 managed Postgres 경로와 동일한 store protocol을 로컬에서 검증합니다.

그래프 엔진(Postgres + Apache AGE + pgvector) 프로파일은 다음 명령으로 실행합니다.

```bash
export GRAPH_POSTGRES_USER=sdp_graph_app
export GRAPH_POSTGRES_PASSWORD='<strong-graph-password>'
export SDP_DATABASE_DSN='postgresql+psycopg://sdp_graph_app:<url-encoded-password>@graph_db:5432/sdp'
docker compose --profile graph up --build
curl localhost:8002/healthz   # DB/AGE/pgvector 준비 상태 확인
```

`sdp_api` 서비스는 필수 `SDP_DATABASE_DSN`으로 그래프 백엔드에 연결하며, `GRAPH_POSTGRES_PASSWORD`도 필수입니다. `GRAPH_POSTGRES_USER`는 `sdp_graph_app` 기본값이 있지만 명시 설정을 권장합니다. 기동 시 마이그레이션 + 시드를 멱등하게 적용합니다. Graph DB host port도 기본적으로 `127.0.0.1:5432`에만 바인딩됩니다.

### 마이그레이션 + 시드 (그래프 DB 백엔드, 수동 실행)

```bash
# 부트스트랩 전송(transport) 용도로만 env 사용 — 앱 설정/시크릿은 config_entries 테이블에서 로드
SDP_DATABASE_DSN='postgresql+psycopg://sdp_graph_app:<url-encoded-password>@localhost:5432/sdp' \
  python -m migrations.run_migrations
```

## API

### 거부(refusal) 계약 — `GET /openapi.json`에 게시됨

이 제품의 특징적인 동작은 **거부**입니다. 그 계약이 OpenAPI 문서에 들어 있으므로,
클라이언트를 생성하면 거부가 타입에 그대로 나타납니다.

| 상태 | 의미 |
|---|---|
| `400` | 요청 본문/파라미터 계약 위반, 금지 SQL 키워드, 허용되지 않은 식별자 — 정책 평가 **전** 거부 |
| `403` | 정책 거부 (역할·민감도·목적). 호출자가 해당 데이터셋의 **테넌트에 접근할 수 있을 때만** 403 |
| `404` | 존재하지 않음 **또는** 호출자의 테넌트 범위 밖 — 두 경우의 상태 코드와 본문이 동일합니다 |
| `409` | 충돌. 여섯 가지다 — (1) 상한이 있는 자원이 가득 찼고 비울 수 있는 항목이 없음 (시드 개념 어휘는 eviction 대상 아님), (2) 요청이 고정한 온톨로지 content digest가 현재 어휘와 다름(형식 오류는 400), (3) 이미 다른 kind로 존재하는 node id에 쓰려 함 — node의 kind는 불변 (카탈로그 mutation 네 개도 그래프 미러가 쓸 node id를 **카탈로그 행을 건드리기 전에** 같은 규칙으로 검사하므로 같은 409다), (4) 이미 존재하는 dataset id로 등록, (5) `broader`/`narrower`의 끝점이 개념과 데이터 자산의 class 경계를 넘음(ONT-002), (6) `broader`/`narrower`가 포섭 순환을 닫거나 자기 자신을 포섭함(ONT-007) |

`404`가 두 경우를 합치는 것은 의도적입니다. 데이터셋 id는 열거 가능하므로
"접근 거부"와 "없음"을 구별할 수 있는 응답 자체가 존재 oracle이 됩니다. 실제
사유는 호출자가 읽을 수 없는 증빙 원장에만 남습니다 — 소유 테넌트의 감사자는
자기 자산에 대한 시도를 `deny / tenant boundary denied`로 그대로 봅니다.

응답 본문은 `{"detail": ...}`이며 `detail`은 대부분 문자열, 일부 경로는 구조화된
객체입니다(예: 알 수 없는 `status` 필터는 `requested`와 `known_statuses`를 함께
반환). 두 형태 모두 스키마에 선언되어 있습니다.

계약은 `src/sdp/api_error_contract.py`의 표 하나에 있고,
`tests/test_api_error_contract.py`가 **양방향**으로 검증합니다 — 코드가 낼 수 있는
거부가 모두 게시되었는지, 그리고 게시된 거부가 모두 실제로 발생 가능한지. 라우트가
낼 수 있는 상태는 `sdp.api`의 AST를 따라 유도하므로 손으로 적은 목록이 아닙니다.

### 요청 본문 스키마

`POST /catalog/datasets`(온보딩)와 `POST /browse/query`(거버닝 쿼리)를 포함한 네
라우트는 이미 pydantic 계약(`DatasetCreateRequest`, `DatasetPatchRequest`,
`QueryDraftRequest`, `QueryExecutionRequest`)으로 검증되고 있었지만, 라우트 파라미터가
`dict`라서 OpenAPI 문서에는 `additionalProperties: true`로만 나타났습니다 — 생성된
클라이언트가 필드 이름을 하나도 볼 수 없었습니다. 이제 문서가 해당 모델을 게시합니다.

런타임은 바뀌지 않았습니다: 파라미터는 여전히 `dict`이고, 스키마 위반은 FastAPI의
422가 아니라 이 저장소의 `400 {"error": "invalid_request", "fields": [...]}` 형태를
유지합니다. `tests/test_api_request_contract.py`가 **각 라우트가 게시한 모델이 그
핸들러가 실제로 생성하는 모델인지** AST로 확인하므로, 아무도 검증하지 않는 스키마를
문서가 광고할 수 없습니다.

게시 기준은 "스키마가 있다"가 아니라 **"그 스키마로 호출이 되는가"** 입니다. 모델만
게시한 첫 버전은 타입이 있으면서 **틀렸습니다**: 카탈로그 변경 라우트는 `actor`를
모델 **밖에서** 읽으므로, 게시된 `DatasetCreateRequest` 필드만 보내는 클라이언트는
403을 받습니다(`actor`를 추가하면 200). 그래서 그런 라우트는 `<Model>Body` 변형을
게시하고 `actor`를 **required**로 표시합니다 — 검증이 요구하지 않아도 그것 없이는
호출이 거부되기 때문입니다. 핸들러가 읽는 본문 키는 AST로 유도해 대조하며, 해석할 수
없는 동적 읽기가 있으면 스키마를 게시하지 않고 **실패**합니다.

나머지 10개 라우트는 모델 없이 `payload.get(...)`로 느슨한 키를 읽습니다. 스키마를
손으로 써 붙이면 핸들러가 읽는 것과 어긋날 수 있고, 모델을 주면 검증이 pydantic으로
넘어가 게시된 400이 422로 바뀝니다 — 문서 수정이 아니라 기존 클라이언트에 대한 계약
변경이므로 범위에서 제외했습니다.

### Health / readiness
- `GET /health` — liveness
- `GET /healthz` — readiness (그래프 백엔드 DB/AGE/pgvector 준비 검증, 미준비 시 503)

### Graph ingestion (지식 그래프 수집)
- `POST /graph/nodes` — 노드 업스트림 푸시. kind는 **불변**이다: 이미 존재하는 id를
  다른 kind로 다시 쓰면 409. kind 허용목록이 아니라 재분류 금지이므로 새 id에는
  자유로운 kind를 그대로 쓸 수 있다.
- `POST /graph/edges` — 엣지 업스트림 푸시
- `POST /ontology/concepts` — 온톨로지 개념 업스트림 푸시. 이미 **다른 kind**로 존재하는
  node id에는 쓸 수 없다(409) — node의 kind는 바뀌지 않는다.
- `GET  /graph/nodes/{node_id}`
- `GET  /graph/stats`

### Graph traversal + semantic retrieval
- `POST /graph/query` — openCypher/BFS 그래프 순회 (edge_types/direction/max_depth, AGE 백엔드는 raw cypher 지원)
- `GET  /ontology/term/{term}/graph` — 개념 그래프 (그래프 스토어 백엔드)
- `POST /search/semantic` — pgvector KNN 시맨틱 검색 (kind 필터)

### Ontology versioning (ONT-004)
- `GET /ontology/version` — 어휘의 현재 버전. 공개(open) — 식별자 없이 수치만.
  `ontology_revision`(단조 증가)과 `content_digest`(sha256)를 함께 게시하고,
  revision은 프로세스 수명 한정이라 `revision_is_durable: false`로 선언한다.
  `digest_matches_recorded_revision`은 버전 경로를 거치지 않은 어휘 변경을 **보고**한다.
- `GET /ontology/change-log?user=<actor>` — 무엇이 바뀌었고 누가 게시/심사했는지.
  **거버닝 읽기**(`/audit/events`·`/policy/decisions`와 같은 게이트) — 모든 항목이
  actor와, 승인 경로에서는 reviewer 신원을 담기 때문이다. 공개된 쪽은 수치뿐이다.
- `GET /ontology/vocabulary/jsonld` — 어휘의 SKOS/RDFS JSON-LD 직렬화.
  `owl:versionInfo`에 revision+digest를 담는다. 공개이며 **dataset id를 담지 않는다**
  (`_INDEX`에는 tenant 술어가 없다 — `concept_assets`가 바로 그 이유로 고쳐졌다).
  정의되지 않은 10개 계층 edge는 IRI를 만들지 않고 선언하고, alias 전용 target은
  alias index로 해소한다(휴면 고객 → 이탈 고객).
- `GET /ontology/search`·`POST /ontology/resolve` — 응답에 `ontology_version` 스탬프.
  `ontology_content_digest`로 **버전 고정(pin)** 가능: 불일치는 409, 형식 오류는 400.
  (`/ontology/search`에서는 query parameter라 OpenAPI 문서에 실리지만,
  `/ontology/resolve`에서는 `dict[str, str]` 본문의 느슨한 키이므로 문서에는
  실리지 않습니다 — 모델 없는 본문 10개의 선언된 경계 안입니다.)
  revision은 고정 대상이 아니다(`revision_is_pinnable: false`) — 재시작 후 내용이
  달라도 같은 번호를 다시 쓰므로, 조용히 고정이 풀리는 pin이 된다.

### Catalog / governance / enterprise (기존)

- `GET /health`
- `GET /metrics`
- `GET /catalog/search?q=...`
- `GET /catalog/datasets`
- `GET /catalog/datasets/{dataset_id}` — discovery 표면. 컬럼 스키마(`pii` 플래그),
  `source_system`, row-count `profile`, `tenant_id`은 응답에 포함되지 않는다
  (`schema_field_count`만 공개). 스키마는 정책을 평가·감사하는
  `GET /browse/{dataset_id}/schema`에서만 받는다.
- `GET /catalog/datasets/{dataset_id}/jsonld`
- `GET /catalog/datasets/{dataset_id}/validate`
- `GET /catalog/datasets/{dataset_id}/semantic-validation`
- `POST /policy/decision`
- `GET /policy/decisions`
- `POST /ontology/resolve` — `defined_in_vocabulary`로 glossary가 **정의하지 않은**
  dataset 선언 용어(캠페인·전환·비즈니스 용어)를 구분해 게시한다
- `GET /ontology/concept/{concept}`
- `GET /ontology/version`
- `GET /ontology/change-log?user=<actor>`
- `GET /ontology/vocabulary/jsonld`
- `GET /ontology/patches?user=<actor>` — steward 제안 큐. **거버닝 읽기**: 모든 행이
  제안자를, 승인된 행은 심사자와 심사 사유까지 담으므로 `/ontology/change-log`와
  같은 게이트를 쓴다(인증 없는 호출은 403). 권한 검사가 `?status=` 검증보다
  **먼저** 실행된다 — 권한 없는 호출자가 payload 규칙을 알게 되면 안 되므로
  `?status=nope`는 actor 없이는 403, actor와 함께는 400이다.
  `/enterprise/steward-review`는 공개 증빙 링크로 남고 `requestor`를 담지 않으며,
  그 사실을 `withheld_review_item_fields`로 선언한다.
- `POST /ontology/concepts`·`POST /ontology/patches/{id}/review` — 게시 전에
  **ConceptShape**를 평가하고(`definition` 필수) 결과를 `concept_validation`으로
  응답에 담는다. 비적합 개념은 게시되지 않는다(400). 계층 target이 등록된 개념으로
  해소되지 않는 제약은 **warning** — 시드 어휘가 10회 위반하므로 게시를 막지 않는다.
- `POST /graph/edges` — `broader`/`narrower`는 "~의 한 종류"를 주장하는 유일한
  관계이므로, 양 끝 중 하나가 이미 **dataset/column 노드**면 409로 거부된다
  (ONT-002: data asset은 business class 계층에 들어갈 수 없다). `mapping`은
  dataset↔concept를 잇는 모델링된 관계이고 `related`는 SKOS에서 연관 관계라서
  둘 다 거부 대상이 아니다. 같은 규칙이 `POST /ontology/concepts`의 `broader`/
  `narrower`에도 **쓰기 전에** 적용된다(어휘 레코드가 먼저 기록되기 때문).
  아직 노드가 아닌 끝점은 거부하지 않는다 — 시드 자체가 정의되지 않은 계층
  target을 선언하고 `upsert_concept`가 target 등록보다 먼저 간선을 쓰므로,
  거부하면 시드 로드가 실패한다.
- `POST /graph/edges`·`POST /ontology/concepts` — 계층이 **순환**하면 409.
  `broader`/`narrower`가 주장하는 포섭 관계에서 순환(자기 자신을 포함)을 닫는
  간선은 거부된다 (ONT-007). 방향은 한 번만 정규화한다 — `narrower: A -> B`와
  `broader: B -> A`는 같은 주장이고 시드가 다섯 개 포섭 중 둘을 양쪽에서
  선언하므로, 반대 주장으로 읽으면 시드 자체가 순환이 된다. 이미 게시된 개념도
  같은 규칙을 받는다: 등록기가 재제출을 버리더라도 **그래프 미러는 제출된
  broader/narrower를 쓰기 때문**이다.
- `GET /enterprise/shacl-validation` — 데이터셋 conformance에 더해
  `concept_conformance`(어휘 전체의 ConceptShape 적합률 + warning 수)와
  `hierarchy_class_separation`(**ConceptHierarchyShape** — 계층 간선 양 끝의
  class 제약을 그래프 현재 상태에 평가; 끝점이 없는 간선은 violation이 아니라
  `unknown_endpoint_count`로 따로 센다)을 게시한다. 쓰기 게이트가 볼 수 없는
  순서 — 끝점이 없을 때 쓴 간선의 끝점이 나중에 dataset으로 생기는 경우 — 는
  이 리포트가 잡는다. SHACL 프로세서나 reasoner는 여전히 실행되지 않는다
  (`shacl_engine_executed: false`). 여기에 `hierarchy_consistency`가 더해진다 —
  서로 포섭하는 개념 묶음 수(`cyclic_group_count`)와 그 구성원, 그리고
  `consistency_engine: builtin_graph_checks` / `reasoner_executed: false`.
  릴리즈 게이트가 읽을 수 있는 숫자이고, 수용 기준이 부르는 "unsatisfiable
  class"가 **아니라** 실제로 계산한 것(순환 수)으로 이름을 붙였다. 순환성은
  노드나 간선이 아니라 그래프의 성질이므로 SHACL shape 목록에는 넣지 않는다.
- `GET /browse/{dataset_id}/schema`
- `POST /browse/{dataset_id}/preview`
- `POST /llm/search`
- `POST /llm/draft-query`
- `GET /enterprise/readiness`
- `GET /enterprise/demo-plan`
- `GET /enterprise/kpis`
- `GET /enterprise/controls`
- `GET /enterprise/rbac-matrix`
- `GET /enterprise/observability`
- `GET /enterprise/latency-budgets`
- `GET /enterprise/production-readiness`
- `GET /enterprise/evidence-pack`
- `GET /enterprise/shacl-validation`
- `GET /enterprise/steward-review`
- `GET /enterprise/console`
- `POST /enterprise/auth/oidc-preview`
- `POST /enterprise/auth/oidc-verify`
- `GET /enterprise/connectors/{connector_id}/probe`

## 테스트

```bash
PYTHONPATH=src pytest
PYTHONPATH=src python -m sdp.demo_smoke
```

## 구현 대응 요약

| PRD/TRD 항목 | 구현 |
|---|---|
| Catalog Service | `src/sdp/catalog.py`, `/catalog/*` |
| Ontology / Terminology | `src/sdp/ontology.py`, `/ontology/*` |
| Browse/Query | `src/sdp/browse.py`, `/browse/*` |
| Policy Service | `src/sdp/policy.py`, `/policy/decision` |
| LLM Orchestrator | `src/sdp/orchestrator.py`, `/llm/*` |
| JSON-LD Export | `/catalog/datasets/{id}/jsonld` |
| Enterprise Core Contracts | `src/sdp_core/contracts.py`, `src/sdp_core/readiness.py`, `src/sdp_core/demo_seed.py`, `src/sdp_core/enterprise.py`, `src/sdp_core/rbac.py`, `src/sdp/enterprise_evidence.py`, `src/sdp/semantic_validation.py`, `src/sdp/steward_review.py`, `src/sdp/observability.py`, `/enterprise/*` |

`src/sdp_core/demo_seed.py`는 buyer demo domain, SQL/RDF/file/API seed dataset, analyst/governance question을 catalog seed, `/enterprise/demo-plan`, connector probe가 함께 쓰는 단일 계약으로 둡니다.
`src/sdp/semantic_validation.py`는 현재 metadata gate와 approved mapping을 SHACL 호환 리포트 형태로 노출해 `/enterprise/shacl-validation`과 smoke readiness가 같은 validation pass rate를 쓰게 합니다.
`src/sdp/steward_review.py`는 SHACL 호환 validation report와 ontology patch queue를 `/enterprise/steward-review`에 모아 buyer handoff 전 검토 대기열을 확인하게 합니다.

## 요구사항 대응 증적

- PRD/TRD: `docs/prd-trd.md`
- 요구사항 대응 매트릭스(**전수, 생성 문서**): `docs/requirements-coverage.md` —
  PRD의 요구사항 74건(기능 52 + NFR 22)을 파싱해 각 건의 상태를
  `implemented` / `partial` / `not_implemented` / `external` 중 하나로 적고
  증빙 포인터(route / 함수 / 테스트)를 붙인다. 손으로 쓰지 않고
  `PYTHONPATH=src python -m sdp_core.requirements`로 재생성하며,
  `tests/test_requirements_coverage.py`가 모든 ID의 매핑 존재, 증빙 포인터의
  실제 해석 가능성, `implemented` 주장의 증빙 보유, 문서와 생성 결과의 일치를
  강제한다.
- 요구사항 대응 서술(일부 요구사항 상세): `docs/implementation-compliance.md` —
  경계/설계 근거를 길게 서술하는 문서이며 전수 목록이 아니다. 전수 상태는 위의
  생성 문서를 본다.
