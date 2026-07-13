# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트 개요

온톨로지 기반 데이터 카탈로그/브라우징 플랫폼 MVP. FastAPI 단일 앱(`sdp.api:app`)이 카탈로그 검색, 온톨로지 용어 해석, 정책 기반 브라우징(민감 컬럼 마스킹), SQL draft 오케스트레이션, enterprise 증빙(evidence) 엔드포인트를 제공한다. PRD/TRD 원문은 `docs/prd-trd.md`, 요구사항 대응 매트릭스는 `docs/implementation-compliance.md`에 있다.

## 자주 쓰는 명령어

```bash
# 의존성 설치 (hash-pinned; dev extra 포함)
python -m pip install --require-hashes -r requirements-dev.txt

# 로컬 서버 실행
PYTHONPATH=src uvicorn sdp.api:app --reload

# 전체 테스트
PYTHONPATH=src pytest

# 단일 테스트
PYTHONPATH=src pytest tests/test_api.py -k test_health

# readiness smoke (ready gate 미충족 시 exit 1)
PYTHONPATH=src python -m sdp.demo_smoke

# Docker 데모 (SQLite evidence store, http://localhost:8000)
docker compose up --build

# Postgres evidence store 포함 paid-pilot 프로파일 (http://localhost:8001)
export POSTGRES_USER=sdp_app
export POSTGRES_PASSWORD='<strong-postgres-password>'
export SDP_DATABASE_URL='postgresql://sdp_app:<url-encoded-password>@postgres:5432/sdp'
docker compose --profile postgres up --build
```

- 패키지는 pip install 되지 않는다. 항상 `PYTHONPATH=src`로 `src/sdp`, `src/sdp_core`를 import 경로에 올린다 (Dockerfile도 `PYTHONPATH=/app/src` 사용).
- pytest 옵션은 `pyproject.toml`의 `addopts = "-q"`가 기본 적용된다.
- lint/formatter 설정은 없다. lint 명령을 만들어내지 말 것.
- CI 워크플로는 `.github/workflows/tests.yml`, `.github/workflows/fuzz.yml`, `.github/workflows/scorecard-analysis.yml`을 사용한다. 테스트는 로컬에서 위 명령으로도 검증한다.

## 의존성 변경 절차

`pyproject.toml`이 원천이고, `requirements.txt` / `requirements-dev.txt`는 uv로 hash와 함께 컴파일된 산출물이다. 의존성을 바꾸면 반드시 두 파일을 재생성해야 한다 (`--require-hashes` 설치가 깨진다):

```bash
uv pip compile pyproject.toml --generate-hashes -o requirements.txt
uv pip compile pyproject.toml --extra dev --generate-hashes -o requirements-dev.txt
```

supply-chain 하드닝 유지: base image는 digest-pinned(`python:3.12-slim@sha256:...`), 컨테이너는 non-root(uid 10001), GitHub Actions는 commit SHA로 pin. Dockerfile/requirements/workflow를 수정할 때 이 속성을 되돌리지 말 것.

## 아키텍처

### 패키지 경계 (src/ 하위 2개 패키지)

- `src/sdp_core/` — FastAPI 의존성이 없는 library 계층.
  - `contracts.py`: Pydantic 계약 (Dataset, PolicyDecision, AuditEvent, Query* 등). 모든 도메인 타입의 원천.
  - `demo_seed.py`: buyer demo domain + SQL/RDF/file/API seed dataset의 단일 계약. 카탈로그 seed, `/enterprise/demo-plan`, connector probe가 모두 이 데이터를 공유한다.
  - `stores.py`: evidence store protocol 구현 2종 — `SQLiteEvidenceStore`(로컬/데모), `PostgresEvidenceStore`(paid pilot, tenant_id 컬럼 + 마이그레이션 DDL 내장).
  - `readiness.py` / `enterprise.py` / `kpis.py` / `production.py` / `rbac.py`: `/enterprise/*` 엔드포인트가 그대로 노출하는 manifest 계약들.
- `src/sdp/` — application 계층. `api.py`가 모든 라우트를 정의하고 도메인 모듈로 위임한다.
  - `catalog.py`: in-memory dataset store (`_DATA`, `buyer_demo_datasets()`로 seed). 검색/facet/lineage/schema history/audit.
  - `ontology.py`: 용어 해석, concept assets, ontology patch queue (propose/review).
  - `browse.py`: schema/preview — policy 평가 후 PII 컬럼 마스킹(`***`) 적용.
  - `policy.py`: `evaluate(subject, resource, action, purpose)` — RBAC 역할, tenant boundary, sensitivity, purpose 기반 allow/deny. 모든 판단은 `evidence.record_policy_decision`으로 기록된다.
  - `orchestrator.py`: SQL draft 생성 + `validate_sql_query` 안전성 검사 (SELECT-only, 단일 statement, 금지 키워드, source table allowlist). fuzz 대상.
  - `evidence.py`: 모듈 로드 시 env로 store 선택 — `SDP_DATABASE_URL` → Postgres, 없으면 `SDP_SQLITE_PATH` → SQLite, 둘 다 없으면 in-memory list fallback.
  - `authz.py`: actor role/tenant 해석, OIDC claim mapping preview + JWKS 서명 검증 (PyJWT).
  - `observability.py`: request observation ring buffer, `/metrics` Prometheus text, `SDP_LOG_SINK_URL` file/http sink.
  - `console.py` + `design_tokens.py`: `/enterprise/console` 읽기 전용 HTML 콘솔.
  - `domain.py`: `sdp_core.contracts` 호환 re-export (신규 타입은 sdp_core에 추가).
  - `demo_smoke.py`: readiness/demo-plan/validation/connector probe를 집계해 `ready` gate를 판정하는 smoke 진입점.

### 데이터 흐름 (governance invariant)

요청 → `api.py` 라우트 → 데이터 접근 전 `policy.evaluate()` → decision(allow/deny + masking/row_filter obligations)과 audit event를 evidence store에 기록 → 응답에 `policy_decision_id`와 masking 결과 포함. **카탈로그 mutation(create/publish/patch/deprecate)과 browse/query 경로에 정책 평가와 evidence 기록을 생략하는 변경은 회귀다.**

### docker-compose 서비스 구성

- `semantic-data-portal` (기본): 앱 단독, `SDP_SQLITE_PATH=/data/sdp-evidence.sqlite3` + `sdp-evidence` volume, 8000 포트, `/health` healthcheck.
- `--profile postgres` 활성화 시: `postgres`(digest-pinned `postgres:16-alpine`, loopback host port 54329) + `semantic-data-portal-postgres`(필수 `POSTGRES_PASSWORD`/`SDP_DATABASE_URL`, `POSTGRES_USER` 기본값은 `sdp_app`, 호스트 8001) 추가. 두 앱 인스턴스로 SQLite/Postgres store protocol 동등성을 검증하는 구성이다.

### Fuzzing

`fuzz/fuzz_query_safety.py`는 Atheris로 `validate_sql_query` invariant를 검사한다. Atheris wheel은 Linux x86_64 전용(`fuzz-requirements.txt`)이며 `.clusterfuzzlite/Dockerfile` 이미지에서 `python fuzz/fuzz_query_safety.py -runs=1000`으로 실행된다.

## 주요 컨벤션

- **에러 매핑**: 도메인 모듈은 `KeyError`(→404), `ValueError`(→400), `PermissionError`(→403)를 raise하고, `api.py` 라우트가 `HTTPException`으로 변환한다. 도메인 계층에서 HTTPException을 직접 raise하지 않는다.
- **테스트 격리**: `tests/test_api.py`의 autouse fixture `isolate_in_memory_app_state`가 `catalog._DATA`, `_AUDIT_LOG`, `_SCHEMA_HISTORY`, `evidence._POLICY_DECISION_LOG`, observability buffer를 snapshot/restore한다. 모듈 레벨 mutable 상태를 새로 추가하면 이 fixture에도 반영해야 테스트 간 오염이 없다.
- **디자인 토큰**: `/enterprise/console` CSS는 임의 hex/px 리터럴 대신 `design_tokens.py`의 `var(--sdp-*)` 변수만 참조한다. 토큰 3계층(primitive/semantic/component)과 Figma 매핑 규칙은 `docs/design-tokens.md` 참조, `tests/test_design_tokens.py`가 무회귀를 강제한다.
- **환경 변수**: 모두 `SDP_` prefix — evidence store(`SDP_DATABASE_URL`, `SDP_DATABASE_SSLMODE`, `SDP_SQLITE_PATH`), observability(`SDP_LOG_SINK_URL`, `SDP_REQUEST_ID_HEADER`, `SDP_ALERT_WEBHOOK_URL`), OIDC(`SDP_OIDC_ISSUER`, `SDP_OIDC_AUDIENCE`, `SDP_OIDC_JWKS_URL`, `SDP_OIDC_GROUP_ROLE_MAP`), connector secret(`SDP_CONNECTOR_SECRET_REF_PREFIX` 기준 `SDP_CONNECTOR_SECRET_*` env reference — 값은 presence만 검증하고 API 응답에 노출 금지).
- **문서/문자열 언어**: README·docs와 사용자 노출 메시지(정책 사유 등)는 한국어 + 영문 기술 용어 혼용이다. 기존 스타일을 유지한다.
- 기능을 추가하면 README의 API 목록/구현 대응 표와 `docs/implementation-compliance.md`의 매트릭스를 함께 갱신한다.
