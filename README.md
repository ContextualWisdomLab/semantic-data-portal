# Semantic Data Portal

[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/ContextualWisdomLab/semantic-data-portal)

온톨로지 기반 **데이터 카탈로그**입니다. ContextualWisdomLab(CWL)에서
개념·데이터셋·컬럼의 **의미 진실(ontology / catalog truth)** 을 소유하는 leaf
서비스입니다. 분석가·거버넌스 담당자가 **이 저장소만**으로 기동할 수 있고,
hub(naruon, gyeot)는 게시된 HTTP 계약으로 **호출**할 수 있습니다.

이 페이지는 운영자·구매자용입니다. 기여자 절차는 [CONTRIBUTING.md](CONTRIBUTING.md)를,
아키텍처 경계는 [docs/msa.md](docs/msa.md)를, 결정 기록은 [docs/adr/](docs/adr/)를
보세요.

## 이 카탈로그가 하는 일

- 비즈니스 용어와 데이터셋을 연결해 **찾아주고** 해석합니다.
- 카탈로그 검색, 용어 해석, 그래프 순회, 시맨틱 검색, JSON-LD export를
  같은 HTTP 표면으로 제공합니다.
- 데이터 접근은 **목적(purpose) 기반 접근 제어**, 암호화, 감사(audit) 아래에
  둡니다. 인가된 개인정보는 사용 가능해야 합니다. 이 제품은 마스킹을
  처방하지 않습니다.
- 자체 그래프 엔진(기본 in-memory, 선택적으로 Postgres + Apache AGE +
  pgvector)을 가집니다. 다른 CWL 저장소를 checkout 하거나 submodule로
  넣지 않아도 부팅됩니다.

## 이 카탈로그가 하지 않는 일

| 책임 | 소유 |
| --- | --- |
| LineageWeave weekly-report 지식그래프 UI | LineageWeave ([PR #74](https://github.com/ContextualWisdomLab/LineageWeave/pull/74)). 포털이 그 UI를 소유·구현·restyle하지 않습니다. |
| IRT / linking / score kernel | `fast-mlsirm`. 점수를 여기서 재구현하지 않습니다. |
| 측정값 import / measurement REST | TEPP. measurement kernel을 여기서 만들지 않습니다. |
| 문서 KG 저장소 | naruon. 이 서비스는 naruon 문서 KG **위**의 카탈로그/온톨로지 평면입니다. |

naruon과 gyeot는 **composition hub**이며 이 leaf를 호출할 수 있습니다. hub 링크를
끊지 마십시오. 반대로 이 서비스를 기동하려고 형제 저장소, path dependency,
다른 CWL home의 git submodule을 **요구하지 마십시오**.

## 단독 실행 (officer / analyst)

패키지는 `pip install -e .`로 설치하지 않습니다. `PYTHONPATH=src`로
`src/sdp`를 올립니다.

### venv — in-memory (데이터베이스 불필요)

```bash
python -m venv .venv
. .venv/bin/activate          # Windows: .venv\Scripts\Activate.ps1
python -m pip install --require-hashes -r requirements-dev.txt
PYTHONPATH=src uvicorn sdp.api:app --reload
```

기본 포트는 `http://127.0.0.1:8000`입니다. 확인:

```bash
curl -s http://127.0.0.1:8000/health
```

### Docker Compose — SQLite evidence store

```bash
docker compose up --build
```

컨테이너는 `SDP_SQLITE_PATH=/data/sdp-evidence.sqlite3`를 쓰고 `/health`
healthcheck를 노출합니다. 호스트 포트는 `8000`입니다.

### Compose — Postgres evidence store (paid-pilot 프로파일)

정책 결정·감사 이벤트를 Postgres evidence store에 기록하려면:

```bash
export POSTGRES_USER=sdp_app
export POSTGRES_PASSWORD='<strong-postgres-password>'
export SDP_DATABASE_URL='postgresql://sdp_app:<url-encoded-password>@postgres:5432/sdp'
docker compose --profile postgres up --build
```

앱은 `http://localhost:8001`에 열립니다. `SDP_DATABASE_URL`과
`POSTGRES_PASSWORD`는 필수입니다. Postgres host port는 기본적으로
`127.0.0.1:54329`에만 바인딩됩니다.

### Compose — 그래프 엔진 (Apache AGE + pgvector)

```bash
export GRAPH_POSTGRES_USER=sdp_graph_app
export GRAPH_POSTGRES_PASSWORD='<strong-graph-password>'
export SDP_DATABASE_DSN='postgresql+psycopg://sdp_graph_app:<url-encoded-password>@graph_db:5432/sdp'
docker compose --profile graph up --build
curl -s http://127.0.0.1:8002/healthz
```

`sdp_api`는 필수 `SDP_DATABASE_DSN`으로 그래프 백엔드에 연결합니다.
`GRAPH_POSTGRES_PASSWORD`도 필수입니다. Graph DB host port는 기본적으로
`127.0.0.1:5432`에만 바인딩됩니다. DSN이 없으면 동일 HTTP 계약이
in-memory 백엔드로 동작합니다.

수동 마이그레이션:

```bash
SDP_DATABASE_DSN='postgresql+psycopg://sdp_graph_app:<url-encoded-password>@localhost:5432/sdp' \
  python -m migrations.run_migrations
```

### 운영자가 이미 쓰는 환경 변수

| 변수 | 역할 |
| --- | --- |
| `SDP_DATABASE_URL` / `SDP_DATABASE_SSLMODE` | Postgres evidence store (정책·감사). 있으면 SQLite보다 우선. |
| `SDP_SQLITE_PATH` | 로컬 SQLite evidence store. |
| `SDP_DATABASE_DSN` | 그래프 엔진(AGE + pgvector) 부트스트랩. |
| `SDP_LOG_SINK_URL` / `SDP_REQUEST_ID_HEADER` | body 없는 request observation. |
| `SDP_OIDC_ISSUER` / `SDP_OIDC_AUDIENCE` / `SDP_OIDC_JWKS_URL` / `SDP_OIDC_GROUP_ROLE_MAP` | OIDC 검증. |
| `SDP_CONNECTOR_SECRET_REF_PREFIX` (`SDP_CONNECTOR_SECRET_*`) | connector secret **참조**. 값은 presence만 확인하고 API 응답에 노출하지 않습니다. |

## Hub가 호출하는 HTTP 계약

Hub는 이 서비스를 **독립 프로세스로** 띄운 뒤 HTTP로 호출합니다. 아래는
보호된 소스에 존재하는 표면을 설명합니다. 새 런타임이나 새 엔드포인트를
이 문서가 만들지 않습니다.

### Health

- `GET /health` — liveness
- `GET /healthz` — 그래프 백엔드 준비. AGE/pgvector가 필요하면 미준비 시 503
- `GET /metrics` — Prometheus text

### Catalog

- `GET /catalog/search?q=...`
- `GET /catalog/datasets`
- `GET /catalog/datasets/{dataset_id}`
- `GET /catalog/datasets/{dataset_id}/jsonld` — DCAT 3 컨텍스트 JSON-LD
- `GET /catalog/datasets/{dataset_id}/lineage`
- `GET /catalog/datasets/{dataset_id}/validate`

### Ontology / graph / semantic search

- `POST /ontology/resolve`
- `GET /ontology/concept/{concept}`
- `GET /ontology/term/{term}/graph` — broader / narrower / related
- `POST /graph/query` — 시작 노드 + 관계 허용 목록 + 방향 + 깊이 제한.
  호출자가 raw openCypher를 보내지 않습니다. 서버가 파라미터 바인딩된
  순회를 만듭니다.
- `POST /search/semantic` — 임베딩 KNN (in-memory cosine 또는 pgvector)
- `GET /graph/stats`
- `POST /graph/nodes`, `POST /graph/edges`, `POST /ontology/concepts` —
  업스트림 푸시 (쓰기 권한 필요)

### Browse / policy / enterprise

스키마·미리보기·SQL draft는 **목적 바운드 정책 평가와 감사**를 통과합니다.
인가된 데이터는 그 조건 아래에서 사용 가능해야 합니다.

- `GET /browse/{dataset_id}/schema`
- `POST /browse/{dataset_id}/preview`
- `POST /browse/query`
- `POST /policy/decision`, `GET /policy/decisions`
- `GET /enterprise/readiness`, `/enterprise/console`, `/enterprise/evidence-pack`

전체 경로와 구현 대응은 [docs/implementation-compliance.md](docs/implementation-compliance.md)와
[docs/enterprise-readiness.md](docs/enterprise-readiness.md)에 있습니다.

## 표준·ADR·참고문헌

| 문서 | 내용 |
| --- | --- |
| [docs/msa.md](docs/msa.md) | leaf / hub MSA와 제품 경계 |
| [docs/adr/](docs/adr/) | 아키텍처 결정. **Status: Draft** — 최종이 아닙니다. |
| [docs/REFERENCES.md](docs/REFERENCES.md) | APA 7th 서지. 인용은 사람이 재검증하기 전까지 draft입니다. |
| [docs/papers/README.md](docs/papers/README.md) | 첨부 PDF 라이선스 메모. 서지 원천은 REFERENCES.md. |
| [docs/prd-trd.md](docs/prd-trd.md) | 제품/기술 요구(draft). 운영 규칙이 충돌하면 보호된 코드·승인된 ADR·현재 운영 계약이 우선합니다. |

## 로컬 검증

```bash
PYTHONPATH=src pytest
PYTHONPATH=src python -m sdp.demo_smoke
```

이 명령은 저장소 구현의 회귀와 smoke 동작을 확인하기 위한 개발 증거입니다. 개별 배포의 보안 검토, 데이터 거버넌스 승인, 규제 적합성, 고객 채택 또는 상용 운영 준비를 대신하지 않습니다. 보호된 브랜치와 immutable release가 실제 배포 가능 상태의 권위입니다.

## 지원·보안·기여

- 사용법과 운영 계약은 이 README 및 `docs/`의 보호된 브랜치 문서를 기준으로 확인합니다.
- 취약점과 보안 경계는 [SECURITY.md](SECURITY.md)를 따릅니다.
- 기여 절차와 개발 환경은 [CONTRIBUTING.md](CONTRIBUTING.md)에 둡니다. 고객용 README에 내부 자동화 절차를 복제하지 않습니다.

## License

Semantic Data Portal의 저장소 소스는 [MIT License](LICENSE)로 제공됩니다. 보호된 `main`의 라이선스 파일은 `Copyright (c) 2026 ContextualWisdomLab`을 명시합니다. 제3자 의존성·컨테이너 이미지·데이터베이스 확장은 각각의 라이선스 조건을 유지하며, 저장소 자체의 MIT grant와 혼동하지 않습니다.
