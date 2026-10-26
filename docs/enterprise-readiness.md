# Semantic Data Portal 엔터프라이즈 완성 기준

이 문서는 `Semantic Data Portal`을 20억 원 수준의 인수·라이선스 검토가 가능한 프로그램으로 만들기 위한 구현 기준을 정의한다. 기준은 `GET /enterprise/readiness`의 기계 판독 가능한 manifest와 동일한 구조를 따른다.

## 핵심 판단

- 목표 가치: `2,000,000,000 KRW`
- 완성 기준: 구매자가 자기 조직의 우선 도메인을 연결해 catalog, ontology, policy, audit, query 데모를 코드 수정 없이 실행하고, 거버넌스 증빙을 확인할 수 있어야 한다.
- 라이브러리 분리: `sdp_core`를 먼저 분리한다. 현재는 별도 repository나 submodule이 아니라 같은 monorepo 안의 순수 계약 패키지로 둔다.
- submodule 판단: 아직 독립 릴리스 주기와 별도 CI/secrets 정책을 가진 외부 connector가 없으므로 보류한다. 첫 실제 SQL/RDF/file connector가 별도 운영 주체를 가지면 `sdp_connectors`를 별도 패키지 또는 submodule로 승격한다.
- Figma 판단: Figma/FigJam은 IA, flow, component state, token handoff에 사용한다. Figma Code Connect는 사용하지 않는다. 최신 운영자 콘솔 capture는 `https://www.figma.com/design/JjYSqr6nWxpARUjaVKhG16?node-id=3-2`에 둔다.
- 디자인 토큰 판단: Figma가 소유하는 primitive·semantic 토큰을 코드가 동일하게 소비하도록 `src/sdp/design_tokens.py`에 3계층(primitive/semantic/component) CSS 변수 원천을 둔다. 운영자 콘솔은 임의 hex/px 대신 `var(--sdp-*)` 토큰만 참조한다(무회귀 리팩터, `tests/test_design_tokens.py`가 보장). 상세 매핑과 Gap은 `docs/design-tokens.md` 참조.

## 패키지 경계

| 경계 | 역할 | 분리 조건 |
|---|---|---|
| `sdp_core` | domain/store/connector/readiness 계약 | 두 번째 앱 또는 외부 connector가 같은 계약을 소비할 때 버전 패키지로 분리 |
| `sdp_app` | FastAPI route, demo data, orchestration | 배포·운영 소유권이 core와 갈라질 때 분리 |
| `sdp_design_system` | Figma/FigJam flow, IA, component states | UI 구현과 token governance consumer가 생긴 뒤 별도 관리 |
| `sdp_connectors` | SQL/RDF/REST/file adapters | 첫 실제 adapter가 contract test, CI, secrets policy를 갖출 때 생성 |

## 판매 가능성 게이트

| Gate | 목표 | 현재 상태 |
|---|---|---|
| Policy/Audit coverage | preview, query, catalog mutation 100%가 policy decision 또는 audit evidence를 노출 | 구현됨 |
| Metadata quality | buyer priority dataset의 validation pass 95% 이상, SHACL 호환 리포트 노출 | 구현됨 |
| Ontology mapping coverage | 핵심 business glossary term 70% 이상 mapping | 구현 기반 있음 |
| Tenant authorization | actor tenant context와 dataset tenant가 맞지 않으면 preview/query/schema 접근 차단 | 구현됨 |
| Buyer demo activation | 2주 안에 SQL/RDF/REST/file 중 하나로 priority domain 온보딩 | demo SQL/RDF/file fixture 구현됨, REST adapter는 env secret reference가 있으면 ready_for_demo |
| Query safety | dataset-bound governed query만 허용하고 literal tautology/comment/multi-statement/forbidden keyword를 fail-closed 처리 | 구현됨 |
| OIDC preview/JWKS guardrail | 만료/subject/tenant claim shape 검증, issuer/audience/JWKS 서명 검증, tenant scoped group-to-role mapping, group별 binding audit event, 직접 roles claim 무시 | 구현됨 |
| Production integration | paid pilot 전 Postgres evidence store, OIDC JWKS verification, connector credential vault, request observability export 필요 항목을 숨기지 않고 manifest로 추적 | Postgres evidence store, OIDC JWKS verification, request observability export, connector credential vault 구현됨, paid pilot blocker 0건 |
| Operational diligence | 중앙 required workflow, security scan, coverage evidence, OSSF baseline 통과 | PR #2/#4 병합됨, PR #5 보안 보강 후 중앙 체크 대기 |

## API 증빙

- `GET /enterprise/readiness`: 본 문서 기준의 manifest
- `GET /enterprise/demo-plan`: buyer priority domain, connector 선택, seed dataset, analyst/governance question, 10일 활성화 workflow, acceptance criteria
- `GET /enterprise/kpis`: 20억 판매 가능성 판단용 primary KPI, guardrail KPI, 목표, 측정 원천
- `GET /enterprise/controls`: `sdp_enterprise` feature gate 아래 retention, SSO/OIDC, RBAC, deployment, 중앙 workflow diligence 상태
- `GET /enterprise/rbac-matrix`: role/action/tenant-scope permission matrix
- `GET /enterprise/observability`: health, metrics, evidence count, request observation, bodyless structured log sink, alert condition·전달 실측(`alert_delivery`) 운영 증빙
- `GET /enterprise/production-readiness`: demo-ready와 paid-pilot-ready를 분리해 Postgres evidence store, OIDC JWKS verification, connector credential vault, request observability export의 환경변수·acceptance criteria·blocker를 노출. Postgres evidence store는 `SDP_DATABASE_URL`/`SDP_DATABASE_SSLMODE`, OIDC JWKS verification은 `SDP_OIDC_ISSUER`/`SDP_OIDC_AUDIENCE`/`SDP_OIDC_JWKS_URL`, request observability export는 `SDP_LOG_SINK_URL`/`SDP_REQUEST_ID_HEADER`, connector credential vault는 `SDP_CONNECTOR_SECRET_REF_PREFIX`/`SDP_CONNECTOR_VAULT_PROVIDER` 기반 구현 증빙으로 paid-pilot blocker에서 제거되었다.
- `GET /enterprise/evidence-pack`: buyer diligence용 metadata validation, ontology mapping coverage, policy/audit evidence, proof endpoint 요약
- `GET /enterprise/shacl-validation`: buyer priority dataset 전체의 SHACL 호환 validation pass rate와 shape/report 요약
- `GET /enterprise/steward-review`: SHACL validation failure와 ontology patch proposal을 묶은 steward 검토 대기열 및 buyer handoff readiness 요약
- `GET /enterprise/console`: evidence, KPI, control, connector status를 한 화면에서 확인하는 운영자 콘솔
- `POST /enterprise/auth/oidc-preview`: 실제 JWKS token verification 전 단계에서 만료/subject/tenant claim shape를 검증하고, `groups` 기반 role mapping만 `ActorContext`로 검토하는 증빙 endpoint. 직접 `roles` claim은 권한으로 쓰지 않고 `ignored_role_claims`로 반환한다. role 부여는 token tenant claim이 허용하는 scope에서만 이뤄지므로 한 tenant에서 role을 주는 group이 다른 tenant에서는 아무것도 주지 못한다.
- `POST /enterprise/auth/oidc-verify`: issuer, audience, expiry, token `kid`, JWKS 서명을 검증한 뒤 같은 tenant scoped group mapping으로 `ActorContext`를 생성한다. Raw token은 응답에 포함하지 않는다. 검증 기준은 `SDP_OIDC_ISSUER`/`SDP_OIDC_AUDIENCE`/`SDP_OIDC_JWKS`(또는 `SDP_OIDC_JWKS_URL`)/`SDP_OIDC_GROUP_ROLE_MAP`이며, body는 `token`만 받는다. 두 endpoint 모두 group별 `group_role_bindings`와 `audit_event_id`를 반환하고 `enterprise/auth/oidc` resource audit event를 남긴다.
- `GET /enterprise/connectors/{connector_id}/probe`: demo dataset 기준 connector contract, source metadata, control evidence, proof endpoint 확인
- `GET /catalog/datasets/{dataset_id}/validate`: metadata quality
- `GET /catalog/datasets/{dataset_id}/semantic-validation`: dataset 단위 SHACL 호환 shape, conformance, violation path 리포트
- `GET /catalog/datasets/{dataset_id}/lineage`: lineage evidence
- `POST /browse/{dataset_id}/preview`: policy-before-data + audit
- `POST /browse/query`: governed query path. 현재 demo executor는 실제 source query 전 단계에서 dataset-bound `SELECT`와 집계형 preview만 허용하고, string literal, boolean operator, comment, multi-statement, forbidden DML/DDL keyword를 거절한다.
- `GET /policy/decisions`: policy decision evidence inspection
- `GET /audit/events`: audit trail
- `GET /metrics`: minimal Prometheus-style metrics
- `GET /ontology/search`, `POST /ontology/resolve`, `GET /ontology/patches?user=<actor>`: ontology coverage 및 steward workflow. 제안 큐는 제안자/심사자 신원을 담으므로 거버닝 읽기이며 actor 없이는 403입니다.

## 로컬 데모 Smoke

서버 실행 없이 핵심 buyer evidence contract를 확인한다.

```bash
PYTHONPATH=src python -m sdp.demo_smoke
```

성공 조건은 20억 valuation target, 10일 이하 demo activation plan, 3개 이상의 seed dataset, metadata validation pass rate 95% 이상, SHACL 호환 validation pass rate 95% 이상, steward review queue 0건, ontology mapping coverage 70% 이상, KPI framework, enterprise controls manifest, SQL/RDF/file connector probe와 REST adapter evidence, production readiness manifest가 모두 준비 상태인 것이다. `ready=true`는 demo release 기준이며, paid pilot 상태는 `/enterprise/production-readiness`의 `paid_pilot_ready`와 `paid_pilot_blockers`로 확인한다.

## Evidence Store

`SDP_DATABASE_URL`를 지정하면 audit event와 policy decision이 Postgres에 기록된다. 각 행은 tenant, resource, decision id, timestamp, immutable payload snapshot을 함께 저장한다. `SDP_DATABASE_SSLMODE`로 managed database의 SSL mode를 지정할 수 있다.

```bash
PYTHONPATH=src SDP_DATABASE_URL='postgresql://sdp_app:<url-encoded-password>@localhost:5432/sdp' SDP_DATABASE_SSLMODE=require uvicorn sdp.api:app --reload
```

`SDP_SQLITE_PATH`를 지정하면 audit event와 policy decision이 stdlib SQLite 파일에 기록된다. production credential 없이 같은 store protocol을 검증하는 로컬 fallback이다. `SDP_DATABASE_URL`이 있으면 Postgres가 우선한다.

```bash
PYTHONPATH=src SDP_SQLITE_PATH=.local/sdp-evidence.sqlite3 uvicorn sdp.api:app --reload
```

## 다음 구현 순서

1. 완료: `Dataset`, `PolicyDecision`, `AuditEvent`, `QueryExecution` 계약은 `sdp_core.contracts`가 소유하고, `sdp.domain`은 app 호환 re-export로 유지한다.
2. 완료: demo SQL connector adapter를 `SourceConnector` contract test와 함께 추가한다.
3. 완료: demo RDF/SPARQL connector adapter를 semantic glossary fixture와 `SourceConnector` contract test로 추가한다.
4. 완료: demo file lake connector adapter를 S3/parquet fixture와 `SourceConnector` contract test로 추가한다.
5. 완료: demo REST connector adapter를 governed API fixture와 `SourceConnector` contract test로 추가하고, credential vault control은 env secret reference presence로 fail-closed 처리한다.
6. 완료: `PostgresEvidenceStore`와 `SQLiteEvidenceStore` fallback으로 audit event와 policy decision의 지속성을 검증한다.
7. 완료: local `ActorContext` 기반 tenant authorization을 preview/query/schema policy path에 적용한다.
8. 완료: buyer demo seed를 도메인별 fixture로 분리하고, `GET /enterprise/demo-plan` 및 connector probe와 연결한다.
9. 완료: retention policy, SSO/RBAC, deployment template를 `sdp_enterprise` feature gate manifest로 묶고 RBAC matrix와 Dockerfile/Compose deployment template를 추가한다.
10. 완료: buyer evidence pack endpoint로 metadata, ontology, policy, audit, controls 증빙을 한 번에 요약한다.
11. 완료: health, metrics, evidence count, alert condition을 `/enterprise/observability`와 `/metrics`로 노출한다. 게시되는 alert 규칙 3건 중
    `policy_audit_gap`은 **평가된다** — policy-gated 라우트가 2xx인데 policy decision도
    audit event도 기록하지 않은 횟수를 미들웨어가 세고, manifest가 `observed_total`과
    `firing`을, `/metrics`가 `sdp_governed_requests_without_evidence_total`을 공표한다.
    선언된 조건보다 **좁다**(요청 시점에 세므로 사후에 원장에서 지워진 행은 보이지
    않고, decision은 있고 audit 행만 없는 경우도 세지 않는다)는 사실은 규칙 자체가
    `not_covered`로 공표한다. governed 경계는 `(method, path)` 쌍이다 — path만으로
    파생했을 때 열린 `GET /ontology/concepts`가 `POST`의 403을 물려받아 미인증 요청
    한 번에 critical 규칙이 발화했다(측정).
    두 번째 평가 규칙 `connector_probe_failure`도 같은 원칙으로 좁다 — probe의
    `verdict_basis` 중 **빌드가 소유하는** 실패(선언된 adapter 미구현, 선언한
    proof endpoint를 이 빌드가 서비스하지 않음, 또는 빌드가 소유하는 runtime 검증
    control의 효과가 성립하지 않음)만 세고, 정상 배포에서 0이다. 세 번째 사유는 뒤늦게
    추가됐다 — 그 전에는 `verdict_basis`의 세 conjunct 중 둘만 읽었고, 효과가 실제로
    측정되는 유일한 control(`ontology_version_pin`)이 깨져도 규칙이 0을 보고했다.
    seed catalogue 20쌍 측정 결과 "ready_for_demo가 아닌 probe"를 세는 조건은 배포되는
    demo image에서 발화하고(그 1건은 optional secret reference 대기 상태이며
    `demo_smoke`의 ready gate가 그 상태를 단언하고 통과한다), scheme이 맞지 않는 15쌍은
    caller가 잘못된 쌍을 지목한 것이므로 path segment 오타가 운영자의 pager를 울리게
    된다 — 두 제외 모두 규칙의 `not_covered`가 공표한다.
    전달(routing)은 **구현되었다**: routable 규칙이 not-firing→firing으로 전이할 때
    평가 지점에서 episode당 1회 POST하며, 미인증으로 열려 있는 두 게시 라우트
    (`/enterprise/observability`, `/metrics`)의 read path에서는 절대 전송하지 않는다.
    routable은 3건 중 2건이므로 reset 사이 한 worker의 POST 총량은 2로 상한이 정해지고,
    이미 firing인 동안 억제된 증가 횟수도 함께 게시한다. 재시도·큐·내구성 있는 실패
    기록은 없고 실패는 예외 타입과 단계만 보관한다(URL은 남기지 않는다).
    `central_workflow_backlog`은 이 서비스가 볼 수 없는 GitHub Actions
    상태라 선언 상태로 남고 `routable: false`이며 그 이유를 함께 공표한다.
12. 완료: `/catalog/datasets/{dataset_id}/semantic-validation`과 `/enterprise/shacl-validation`으로 SHACL 호환 validation report와 95% pass rate 증빙을 노출한다.
13. 완료: `/enterprise/steward-review`로 validation failure와 ontology patch proposal 검토 대기열, 2영업일 SLA, buyer handoff readiness를 노출한다.
14. 완료: `/enterprise/auth/oidc-preview` claim-shape 검증과 직접 role-claim 무시 동작을 추가한다. `/enterprise/auth/oidc-verify`는 issuer/audience/expiry/JWKS 서명 검증 후 같은 group allow-list mapping을 적용한다.
15. 완료: `/browse/query` literal tautology injection을 query-safety validation에서 fail-closed로 거절한다.
16. 완료: `/enterprise/console`로 evidence, KPI, controls, connector probe 상태를 한 화면에 노출한다.
17. 완료: request observability export를 `SDP_LOG_SINK_URL=file://...` 또는 `http(s)://...` sink로 연결하고, request id, tenant, actor, route, status, latency, evidence ids만 body 없이 기록한다. `evidence_ids`는 **서버가 기록한 것**이다 — 이전에는 caller가 보낸 `X-SDP-Evidence-Ids` 헤더에서 읽었으므로 그 행이 가리키는 증빙을 그 행의 주체인 caller가 고를 수 있었고, 측정 결과 서버가 실제로 기록한 decision id는 로그에 없었다. 지금은 모든 증빙 행이 지나는 두 지점(`evidence.record_policy_decision` / `append_audit_event`)에서 요청 단위로 수집한다. `tenant_id`/`actor`는 여전히 caller 주장값이며 manifest가 `caller_asserted_fields`로 그렇게 공표한다.
18. 완료: connector credential vault를 `SDP_CONNECTOR_SECRET_REF_PREFIX` 기반 env provider로 구현하고, REST connector probe가 raw secret 없이 secret reference presence만 노출하게 한다.
19. 완료: OIDC JWKS verification을 PyJWT crypto 기반으로 구현하고, 테스트 JWKS로 서명 검증 성공/잘못된 audience 거절/raw token 미노출을 검증한다.
20. 완료: group-to-role mapping을 tenant scoped 형태로 확장하고 group별 binding을 audit event로 기록해 `sso_oidc_adapter` control을 구현 상태로 올린다. wildcard/tenant scope 혼합 설정은 거절하고, tenant scope는 wildcard 부여를 회수할 수 있다.
21. Figma/FigJam 산출물의 IA와 component state를 구현 backlog와 연결하되 Code Connect는 사용하지 않는다.
