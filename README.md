# Semantic Data Portal (MVP)

온톨로지 기반 데이터 카탈로그/브라우징 플랫폼 PRD/TRD(v0.1, 2026-06-29) 기반의 MVP 구현입니다.

## 목표

- 데이터 탐색: 키워드 기반 카탈로그 검색 + 유사어/용어(ontology) 해석
- 브라우징: 스키마 조회, 샘플 미리보기, 민감 컬럼 마스킹
- 거버넌스: 정책 판단(PERMISSION), 샘플 정책 근거(Decision/Omission) 노출
- 오케스트레이션: 자연어 질문 기반 질의 후보 추천 + SQL draft 제시

첨부 문서는 다음 경로에 보관됩니다.

- `docs/prd-trd.md`

## 로컬 실행

```bash
python -m venv .venv
. .venv/Scripts/Activate.ps1
pip install -e .[dev]
uvicorn sdp.api:app --reload
```

`SDP_SQLITE_PATH=.local/sdp-evidence.sqlite3`를 지정하면 policy decision과 audit event가 로컬 SQLite evidence store에 기록됩니다.

Docker 기반 로컬 데모는 다음 명령으로 실행합니다.

```bash
docker compose up --build
```

컨테이너는 `SDP_SQLITE_PATH=/data/sdp-evidence.sqlite3`를 사용하고 `/health` healthcheck를 노출합니다.

## API

- `GET /health`
- `GET /catalog/search?q=...`
- `GET /catalog/datasets`
- `GET /catalog/datasets/{dataset_id}`
- `GET /catalog/datasets/{dataset_id}/jsonld`
- `GET /catalog/datasets/{dataset_id}/validate`
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
- `GET /enterprise/evidence-pack`
- `GET /enterprise/connectors/{connector_id}/probe`

## 테스트

```bash
pytest
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
| Enterprise Core Contracts | `src/sdp_core/contracts.py`, `src/sdp_core/readiness.py`, `src/sdp_core/demo_seed.py`, `src/sdp_core/enterprise.py`, `src/sdp/enterprise_evidence.py`, `/enterprise/*` |

`src/sdp_core/demo_seed.py`는 buyer demo domain, seed dataset, analyst/governance question을 catalog seed, `/enterprise/demo-plan`, connector probe가 함께 쓰는 단일 계약으로 둡니다.

## 요구사항 대응 증적

- PRD/TRD: `docs/prd-trd.md`
- 요구사항 대응 매트릭스: `docs/implementation-compliance.md`
