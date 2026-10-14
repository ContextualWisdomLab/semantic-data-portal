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
. .venv/Scripts/Activate.ps1
python -m pip install --require-hashes -r requirements-dev.txt
PYTHONPATH=src uvicorn sdp.api:app --reload
```

`SDP_DATABASE_URL=postgresql://...`를 지정하면 policy decision과 audit event가 tenant/resource/evidence id 기준의 Postgres evidence store에 기록됩니다. `SDP_DATABASE_SSLMODE=require`처럼 SSL mode를 함께 지정할 수 있습니다.
`SDP_SQLITE_PATH=.local/sdp-evidence.sqlite3`를 지정하면 production credential 없이도 같은 evidence store protocol을 로컬 SQLite fallback으로 검증할 수 있습니다. `SDP_DATABASE_URL`이 있으면 Postgres가 SQLite보다 우선합니다.
`SDP_LOG_SINK_URL=file:///data/sdp-requests.jsonl`(절대 경로, `file://` 뒤 authority 없이 슬래시 세 개)과 `SDP_REQUEST_ID_HEADER=X-Request-Id`를 지정하면 request id, tenant, actor, route, status, latency, evidence ids만 body 없이 request observation log로 기록됩니다. `file://.local/...`처럼 상대 경로로 보이는 값은 **거부됩니다** — authority가 경로로 접혀 들어가 파일시스템 루트(`//.local/...`)를 가리켰고, 컨테이너는 `USER 10001`로 `/data`만 쓸 수 있어 매 요청이 `PermissionError`로 실패하는데 manifest는 계속 `implemented`라고 보고했습니다. 이제 쓸 수 없는 설정은 `GET /enterprise/observability`가 `configured: false`와 `invalid_configuration` 사유로 보고합니다(설정값 자체는 공개하지 않습니다 — sink의 내부 호스트와 경로가 담겨 있습니다).
http(s) sink도 지원합니다. URL에 credential을 담은 형태(`https://sdp-ingest:TOKEN@logs.example.net/loki/api/v1/push` — Loki·Elastic·서명 webhook의 문서화된 push URL 형태)는 userinfo를 URL에서 분리해 `Authorization` 헤더로 보냅니다(password가 있으면 `Basic`, token 하나면 `Bearer`; `@`·`:`를 담은 password는 percent-encoding). 이전에는 URL 전체를 `urllib`에 넘겨 userinfo가 연결 host로 남았고(`sdp-ingest:TOKEN@logs.example.net` → `InvalidURL: nonnumeric port`), 모든 export가 실패하는 동안 manifest는 `configured: true`로 보고했으며 예외 메시지가 authority를 인용해 credential이 export error ring에 남았습니다. host가 없거나 port가 숫자가 아닌 http sink도 이제 file sink와 같은 경로로 `configured: false` + `invalid_configuration`으로 보고합니다.
`SDP_ALERT_WEBHOOK_URL`은 **선언만 되어 있고 구현되지 않았습니다**. 이 값을 읽는 코드는 `_sink_status`가 설정 여부(`alert_webhook_configured`)를 보고하는 한 곳뿐이고, 이 URL로 POST하는 코드도 `GET /enterprise/observability`가 공개하는 alert 조건을 평가하는 코드도 없습니다. 그래서 이 변수는 `required_environment`에서 빠지고 `declared_unimplemented_environment`로 이동했습니다 — 라우팅하지 않는 값을 설정해서 paid-pilot gate를 통과할 수 있으면 그 gate는 아무것도 측정하지 않습니다. 공개되는 alert 규칙은 삭제하지 않고(조건 자체는 올바르고 operator가 자기 모니터링 스택에 그대로 구현할 수 있습니다) `alert_evaluation: declared_not_evaluated`, 규칙별 `evaluated: false`, `alert_webhook_routing: declared_unimplemented`로 표시합니다.
sink export breaker는 closed/open에 half-open을 추가했습니다. 이전에는 cooldown이 끝나는 순간 모든 요청이 죽은 sink를 동시에 다시 호출해 (모든 동기 route가 공유하는) anyio threadpool의 빈 slot을 전부 `SDP_LOG_SINK_TIMEOUT_MS`만큼 점유했습니다 — 측정: 동시 요청 20건에서 slot 8개면 sink 호출 8회, 무제한이면 20회, outage가 계속되는 동안 cooldown마다 반복. 이제 cooldown 만료 후 정확히 한 요청만 probe하고(측정: 1회) 나머지는 skip하며, probe가 성공하면 그 즉시 모두에게 breaker가 닫힙니다.
REST connector secret은 `SDP_CONNECTOR_SECRET_REF_PREFIX=SDP_CONNECTOR_SECRET_` 기준의 env secret reference로 조회합니다. 예: `SDP_CONNECTOR_SECRET_REST_CONNECTOR_MARKETING_CAMPAIGN_TOKEN` 값은 presence만 검증하며 API 응답에는 노출하지 않습니다.
OIDC token verification은 `SDP_OIDC_ISSUER`, `SDP_OIDC_AUDIENCE`, `SDP_OIDC_JWKS_URL`(또는 JWKS 문서를 그대로 담는 `SDP_OIDC_JWKS`), `SDP_OIDC_GROUP_ROLE_MAP`를 사용합니다. 이 네 가지는 **operator 설정 전용**입니다. `POST /enterprise/auth/oidc-verify`의 body는 `token` 하나만 받고, `issuer`·`audience`·`jwks`·`role_map`이 body에 오면 400으로 거절합니다 — 호출자가 자기 토큰의 신뢰 기준을 지정할 수 있으면 스스로 서명한 토큰으로 임의 tenant의 platform-admin을 발급받을 수 있기 때문입니다.
`SDP_OIDC_GROUP_ROLE_MAP`은 두 가지 형태를 받습니다. flat `{"group": ["role"]}`은 모든 tenant에 적용되는 wildcard scope(`*`)가 되고, tenant scoped `{"tenant": {"group": ["role"]}}`은 해당 tenant에만 적용됩니다. 같은 group이 두 scope에 모두 있으면 tenant scope가 wildcard를 대체하므로, tenant scope에 빈 role 목록을 쓰면 wildcard 부여를 해당 tenant에서만 회수할 수 있습니다. 두 형태를 한 map에 섞으면 tenant 식별자를 group 이름으로 잘못 읽는 설정 오류이므로 요청이 400으로 거절됩니다.
`POST /enterprise/auth/oidc-preview`와 `POST /enterprise/auth/oidc-verify`는 group별 `group_role_bindings`(group 이름, 부여한 tenant scope, 부여된 role)와 `audit_event_id`를 함께 반환하고, 같은 내용을 `enterprise/auth/oidc` resource의 audit event로 기록합니다. token과 raw claim payload는 응답에도 evidence store에도 기록되지 않습니다.

Docker 기반 로컬 데모는 다음 명령으로 실행합니다.

```bash
docker compose up --build
```

컨테이너는 `SDP_SQLITE_PATH=/data/sdp-evidence.sqlite3`를 사용하고 `/health` healthcheck를 노출합니다.

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
| `409` | 상한이 있는 자원이 가득 찼고 비울 수 있는 항목이 없음 (시드 개념 어휘는 eviction 대상 아님) |

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
- `POST /graph/nodes` — 노드 업스트림 푸시
- `POST /graph/edges` — 엣지 업스트림 푸시
- `POST /ontology/concepts` — 온톨로지 개념 업스트림 푸시
- `GET  /graph/nodes/{node_id}`
- `GET  /graph/stats`

### Graph traversal + semantic retrieval
- `POST /graph/query` — openCypher/BFS 그래프 순회 (edge_types/direction/max_depth, AGE 백엔드는 raw cypher 지원)
- `GET  /ontology/term/{term}/graph` — 개념 그래프 (그래프 스토어 백엔드)
- `POST /search/semantic` — pgvector KNN 시맨틱 검색 (kind 필터)

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
- `POST /ontology/resolve`
- `GET /ontology/concept/{concept}`
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
- 요구사항 대응 매트릭스: `docs/implementation-compliance.md`
