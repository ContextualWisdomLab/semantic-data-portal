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
`SDP_LOG_SINK_URL=file://.local/sdp-requests.jsonl`과 `SDP_REQUEST_ID_HEADER=X-Request-Id`를 지정하면 request id, tenant, actor, route, status, latency, evidence ids만 body 없이 request observation log로 기록됩니다.
REST connector secret은 `SDP_CONNECTOR_SECRET_REF_PREFIX=SDP_CONNECTOR_SECRET_` 기준의 env secret reference로 조회합니다. 예: `SDP_CONNECTOR_SECRET_REST_CONNECTOR_MARKETING_CAMPAIGN_TOKEN` 값은 presence만 검증하며 API 응답에는 노출하지 않습니다.
OIDC token verification은 `SDP_OIDC_ISSUER`, `SDP_OIDC_AUDIENCE`, `SDP_OIDC_JWKS_URL`, `SDP_OIDC_GROUP_ROLE_MAP`를 사용합니다.

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

이 프로파일은 `semantic-data-portal-postgres`를 `http://localhost:8001`에 열고, `SDP_DATABASE_URL`과 `POSTGRES_PASSWORD`를 필수 env로 요구합니다. `POSTGRES_USER`는 `sdp_app` 기본값이 있지만 명시 설정을 권장합니다. Postgres host port는 기본적으로 `127.0.0.1:54329`에만 바인딩되어 managed Postgres 경로와 동일한 store protocol을 로컬에서 검증합니다.

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

### 파일 지식 온톨로지

`CWL File Knowledge Profile 0.1`은 파일 내용의 SHA-256 정체성과 물리 저장 위치를
분리합니다. 같은 bytes가 로컬/Synology 동기화 폴더, S3, S3 호환 저장소, Azure Blob에
복제되어도 하나의 `FileAsset`과 여러 DCAT `Distribution`으로 표현됩니다. 기계 판독
프로파일과 shape는 `ontology/cwl-file-profile.ttl`, `ontology/cwl-file-shapes.ttl`에 있으며,
ingest/validate 때 pySHACL로 실제 실행됩니다.

- `POST /file-assets` — 관리자 정책을 통과한 자산·후보 주장 적재
- `GET /file-assets/{asset_id}` — 자산과 의미 관계 조회
- `GET /file-assets/{asset_id}/jsonld` — 기본 locator 비공개 JSON-LD
- `GET /file-assets/{asset_id}/validate` — pySHACL 검증 리포트
- 지원 reader: `filesystem`(로컬/UNC/Synology 포함), `s3`, `s3_compatible`, `azure_blob`
- 지원 본문 추출: TXT/Markdown/CSV/JSON/XML, DOCX/PPTX/XLSX, PDF

파일 의미 추출과 embedding은 OpenAI를 직접 호출하지 않고
[`ContextualWisdomLab/contextual-orchestrator`](https://github.com/ContextualWisdomLab/contextual-orchestrator)만
사용합니다. 의미 추출은 `/v1/chat/completions`, embedding은 orchestrator에 추가된 동기
`/v1/embeddings`를 사용합니다. `orchestrator_base_url`, `semantic_model`,
`embedding_model`은 `config_entries` KV 설정이고, inference token은 주입된 credential
registry에서만 가져옵니다. `embedding_dimension`은 `/v1/embeddings`의 `dimensions`로
전달되어 pgvector 차원과 일치해야 합니다. 운영 graph store도 같은 orchestrator client의
`embed_one`을 ingest와 검색에 주입합니다. OpenAI/provider key는 포털에 두지 않습니다.

`/file-assets/*`는 요청 본문이나 query의 `actor`를 신뢰하지 않습니다. 검증된 OIDC Bearer
토큰에서 subject/role/tenant를 도출합니다. `FileAsset.tenant_id`와 중앙 policy decision을
대조해 tenant 경계를 적용하며, locator 포함 응답은 같은 tenant의 `admin` 또는
`platform-admin`만 요청할 수 있습니다. 같은 SHA-256이나 파일 관계 대상이 다른 tenant에
이미 속하면 ingest를 거부해 distribution/assertion을 섞지 않습니다. `/graph/nodes`,
`/graph/edges`, `/graph/query`, `/search/semantic`, `/ontology/concepts`도 동일한 Bearer
context를 요구하고 body `actor`를 거부합니다. 일반 graph API는 governed file
node/edge를 수정할 수 없으며, traversal/search 결과는 tenant로 필터링되고 locator는
항상 redaction됩니다.

GitHub Secret에 값을 저장하는 것만으로는 런타임 주입이 되지 않습니다. 배포 호스트는
secret manager에서 token을 읽는 `CredentialRegistry` 구현을 만든 뒤
`sdp.api.create_app(registry)`로 ASGI 앱을 구성해야 합니다. KV에
`orchestrator_base_url`이 있는데 `CONTEXTUAL_ORCHESTRATOR_TOKEN`이 주입되지 않으면
lifespan/startup이 fail-closed하며, registry 교체 시 credential을 캡처한 graph store도
폐기·재생성됩니다. TTL profile/shape는 `sdp/resources/*.ttl` package data로 배포되므로
wheel과 공식 컨테이너에서도 pySHACL 검증이 동일하게 동작합니다.

읽기 전용 로컬 파일럿은 다음처럼 실행합니다. `--no-llm`은 파일 이동·삭제나 네트워크
호출 없이 중복·추출 상태만 확인합니다.

```powershell
$env:PYTHONPATH='src'
py -m sdp.file_pilot --root '<approved-read-only-root>' --output '<local-gitignored-manifest.json>' --name-regex '효성중공업|중공업VOC' --max-files 12 --no-llm
```

LLM을 사용할 때는 `--orchestrator-url`을 주거나 KV의 `orchestrator_base_url`을 사용하며,
inference token은 숨김 prompt로만 입력합니다. manifest에는 원문 조각·근거 인용문·API
응답·credential을 저장하지 않습니다. 실제 파일명과 locator가 들어가므로 출력은 로컬의
Git 제외 경로에만 보관합니다.

### Catalog / governance / enterprise (기존)

- `GET /health`
- `GET /metrics`
- `GET /catalog/search?q=...`
- `GET /catalog/datasets`
- `GET /catalog/datasets/{dataset_id}`
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
| File Knowledge Profile | `src/sdp/file_ontology.py`, `src/sdp/storage_readers.py`, `src/sdp/document_semantics.py`, `src/sdp/file_pilot.py`, `/file-assets/*` |
| JSON-LD Export | `/catalog/datasets/{id}/jsonld` |
| Enterprise Core Contracts | `src/sdp_core/contracts.py`, `src/sdp_core/readiness.py`, `src/sdp_core/demo_seed.py`, `src/sdp_core/enterprise.py`, `src/sdp_core/rbac.py`, `src/sdp/enterprise_evidence.py`, `src/sdp/semantic_validation.py`, `src/sdp/steward_review.py`, `src/sdp/observability.py`, `/enterprise/*` |

`src/sdp_core/demo_seed.py`는 buyer demo domain, SQL/RDF/file/API seed dataset, analyst/governance question을 catalog seed, `/enterprise/demo-plan`, connector probe가 함께 쓰는 단일 계약으로 둡니다.
`src/sdp/semantic_validation.py`는 현재 metadata gate와 approved mapping을 SHACL 호환 리포트 형태로 노출해 `/enterprise/shacl-validation`과 smoke readiness가 같은 validation pass rate를 쓰게 합니다.
`src/sdp/steward_review.py`는 SHACL 호환 validation report와 ontology patch queue를 `/enterprise/steward-review`에 모아 buyer handoff 전 검토 대기열을 확인하게 합니다.

## 요구사항 대응 증적

- PRD/TRD: `docs/prd-trd.md`
- 요구사항 대응 매트릭스: `docs/implementation-compliance.md`
