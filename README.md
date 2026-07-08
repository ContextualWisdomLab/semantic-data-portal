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

### 단독 실행 (Docker Compose — SDP + Postgres/AGE/pgvector)

```bash
docker compose up --build
curl localhost:8000/healthz   # DB/AGE/pgvector 준비 상태 확인
```

### in-memory 백엔드 (DB 불필요)

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e .[dev]
uvicorn sdp.api:app --reload
```

### 마이그레이션 + 시드 (DB 백엔드)

```bash
# 부트스트랩 전송(transport) 용도로만 env 사용 — 앱 설정/시크릿은 config_entries 테이블에서 로드
SDP_DATABASE_DSN=postgresql+psycopg://sdp:sdp@localhost:5432/sdp \
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

### Catalog / ontology / browse (기존)
- `GET /catalog/search?q=...`, `GET /catalog/datasets`, `GET /catalog/datasets/{id}`
- `GET /catalog/datasets/{id}/jsonld`, `GET /catalog/datasets/{id}/validate`
- `POST /policy/decision`, `POST /ontology/resolve`, `GET /ontology/concept/{concept}`
- `GET /browse/{id}/schema`, `POST /browse/{id}/preview`
- `POST /llm/search`, `POST /llm/draft-query`

## 설정 (Config) — KV 규칙

앱 시크릿/설정은 런타임에 `os.getenv`로 읽지 않습니다. 부트스트랩 단계에서 **전송(transport)**
좌표(`SDP_DATABASE_DSN`, `SDP_CONFIG_NAMESPACE`, `SDP_ENV`)만 환경변수로 읽어 DB/KV에 도달하고,
그 이후 CORS 허용목록·임베딩 차원·그래프명 등 모든 앱 설정은 `config_entries` KV 테이블에서
로드합니다. DB가 없으면 번들된 안전 기본값을 사용합니다. CORS는 `"*"`에서 설정 가능한
허용목록(allowlist)으로 강화되었습니다.

## 표준 컨테이너 / 서브모듈

- **standalone**: `docker compose up` — SDP + Postgres(AGE+pgvector) 스택.
- **submodule-embeddable**: DB DSN 없이 `uvicorn sdp.api:app`로 in-memory 백엔드 실행.
  Dockerfile은 비루트(non-root, uid 10001) 사용자, `EXPOSE 8000`, `/healthz` readiness 포함.

## 테스트

```bash
pytest
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

## 요구사항 대응 증적

- PRD/TRD: `docs/prd-trd.md`
- 요구사항 대응 매트릭스: `docs/implementation-compliance.md`

