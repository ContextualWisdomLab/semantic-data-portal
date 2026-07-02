# Semantic Data Portal 엔터프라이즈 완성 기준

이 문서는 `Semantic Data Portal`을 20억 원 수준의 인수·라이선스 검토가 가능한 프로그램으로 만들기 위한 구현 기준을 정의한다. 기준은 `GET /enterprise/readiness`의 기계 판독 가능한 manifest와 동일한 구조를 따른다.

## 핵심 판단

- 목표 가치: `2,000,000,000 KRW`
- 완성 기준: 구매자가 자기 조직의 우선 도메인을 연결해 catalog, ontology, policy, audit, query 데모를 코드 수정 없이 실행하고, 거버넌스 증빙을 확인할 수 있어야 한다.
- 라이브러리 분리: `sdp_core`를 먼저 분리한다. 현재는 별도 repository나 submodule이 아니라 같은 monorepo 안의 순수 계약 패키지로 둔다.
- submodule 판단: 아직 독립 릴리스 주기와 별도 CI/secrets 정책을 가진 외부 connector가 없으므로 보류한다. 첫 실제 SQL/RDF/file connector가 별도 운영 주체를 가지면 `sdp_connectors`를 별도 패키지 또는 submodule로 승격한다.
- Figma 판단: Figma/FigJam은 IA, flow, component state, token handoff에 사용한다. Figma Code Connect는 사용하지 않는다.

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
| Metadata quality | buyer priority dataset의 validation pass 95% 이상 | 구현 기반 있음 |
| Ontology mapping coverage | 핵심 business glossary term 70% 이상 mapping | 구현 기반 있음 |
| Tenant authorization | actor tenant context와 dataset tenant가 맞지 않으면 preview/query/schema 접근 차단 | 구현됨 |
| Buyer demo activation | 2주 안에 SQL/RDF/REST/file 중 하나로 priority domain 온보딩 | demo SQL/RDF fixture 구현됨, 실제 buyer connector pilot은 다음 단계 |
| Operational diligence | 중앙 required workflow, security scan, coverage evidence, OSSF baseline 통과 | GitHub Actions 중앙 체크 대기 |

## API 증빙

- `GET /enterprise/readiness`: 본 문서 기준의 manifest
- `GET /enterprise/demo-plan`: buyer priority domain, connector 선택, seed dataset, analyst/governance question, 10일 활성화 workflow, acceptance criteria
- `GET /enterprise/kpis`: 20억 판매 가능성 판단용 primary KPI, guardrail KPI, 목표, 측정 원천
- `GET /enterprise/controls`: `sdp_enterprise` feature gate 아래 retention, SSO/OIDC, RBAC, deployment, 중앙 workflow diligence 상태
- `GET /enterprise/rbac-matrix`: role/action/tenant-scope permission matrix
- `GET /enterprise/observability`: health, metrics, evidence count, alert condition 운영 증빙
- `GET /enterprise/evidence-pack`: buyer diligence용 metadata validation, ontology mapping coverage, policy/audit evidence, proof endpoint 요약
- `POST /enterprise/auth/oidc-preview`: 실제 token verification 전 단계에서 OIDC claim-to-role/tenant mapping을 `ActorContext`로 검토하는 증빙 endpoint
- `GET /enterprise/connectors/{connector_id}/probe`: demo dataset 기준 connector contract, source metadata, control evidence, proof endpoint 확인
- `GET /catalog/datasets/{dataset_id}/validate`: metadata quality
- `GET /catalog/datasets/{dataset_id}/lineage`: lineage evidence
- `POST /browse/{dataset_id}/preview`: policy-before-data + audit
- `POST /browse/query`: governed query path
- `GET /policy/decisions`: policy decision evidence inspection
- `GET /audit/events`: audit trail
- `GET /metrics`: minimal Prometheus-style metrics
- `GET /ontology/search`, `POST /ontology/resolve`, `GET /ontology/patches`: ontology coverage 및 steward workflow

## 로컬 데모 Smoke

서버 실행 없이 핵심 buyer evidence contract를 확인한다.

```bash
PYTHONPATH=src python -m sdp.demo_smoke
```

성공 조건은 20억 valuation target, 10일 이하 demo activation plan, 3개 이상의 seed dataset, metadata validation pass rate 95% 이상, ontology mapping coverage 70% 이상, KPI framework, enterprise controls manifest, SQL connector probe와 demo context가 모두 준비 상태인 것이다.

## 로컬 Evidence Store

`SDP_SQLITE_PATH`를 지정하면 audit event와 policy decision이 stdlib SQLite 파일에 기록된다. 운영 Postgres 저장소를 붙이기 전 demo/pilot 환경의 로컬 지속성 fallback이다.

```bash
SDP_SQLITE_PATH=.local/sdp-evidence.sqlite3 uvicorn sdp.api:app --reload
```

## 다음 구현 순서

1. 완료: `Dataset`, `PolicyDecision`, `AuditEvent`, `QueryExecution` 계약은 `sdp_core.contracts`가 소유하고, `sdp.domain`은 app 호환 re-export로 유지한다.
2. 완료: demo SQL connector adapter를 `SourceConnector` contract test와 함께 추가한다.
3. 완료: demo RDF/SPARQL connector adapter를 semantic glossary fixture와 `SourceConnector` contract test로 추가한다.
4. 완료: `SQLiteEvidenceStore` fallback으로 audit event와 policy decision의 로컬 지속성을 검증한다.
5. 완료: local `ActorContext` 기반 tenant authorization을 preview/query/schema policy path에 적용한다.
6. 완료: buyer demo seed를 도메인별 fixture로 분리하고, `GET /enterprise/demo-plan` 및 connector probe와 연결한다.
7. 완료: retention policy, SSO/RBAC, deployment template를 `sdp_enterprise` feature gate manifest로 묶고 RBAC matrix와 Dockerfile/Compose deployment template를 추가한다.
8. 완료: buyer evidence pack endpoint로 metadata, ontology, policy, audit, controls 증빙을 한 번에 요약한다.
9. 완료: health, metrics, evidence count, alert condition을 `/enterprise/observability`와 `/metrics`로 노출한다.
10. Figma/FigJam 산출물의 IA와 component state를 구현 backlog와 연결하되 Code Connect는 사용하지 않는다.
