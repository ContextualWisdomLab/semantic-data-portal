# MSA — Semantic Data Portal as a callable leaf

**Status:** Draft (documentation). This note describes the composition
boundary that already exists. It does not add a runtime, package, catalog
database, or test harness.

## Context

CWL는 여러 **standalone program**을 키운 뒤 hub가 조합하는 생태계입니다.
`semantic-data-portal`은 그 중 **ontology / semantic catalog home**입니다.
naruon(문서 KG)과 gyeot는 composition hub일 수 있고, 이 leaf를 HTTP로
호출할 수 있습니다. 이 서비스는 hub 없이 기동되어야 하고, hub는 이 서비스
없이 자기 책임을 유지해야 합니다.

## Decision

1. **이 저장소가 소유하는 것.** 카탈로그 메타데이터, 용어(glossary)와
   broader/narrower/related 개념 그래프, 데이터셋 JSON-LD, 정책 결정과
   감사 evidence, 그래프 순회와 시맨틱 검색 HTTP 계약. 의미 진실의
   원천은 여기입니다.
2. **이 저장소가 소유하지 않는 것.**
   - LineageWeave weekly-report 지식그래프 UI — LineageWeave
     [PR #74](https://github.com/ContextualWisdomLab/LineageWeave/pull/74).
   - IRT / linking / score kernel — `fast-mlsirm`.
   - 측정값 import와 measurement REST — TEPP.
   - naruon 문서 KG 저장소 자체.
3. **기동 독립성.** 기본 경로는 in-memory 백엔드입니다. 선택 프로파일
   (SQLite evidence, Postgres evidence, AGE+pgvector)은 이 저장소의
   Compose 정의만 사용합니다. 형제 저장소 checkout, path-dep, 다른 CWL
   home의 git submodule을 부팅 조건으로 두지 않습니다.
4. **호출 가능성.** Hub는 게시된 HTTP 계약(` /health`, `/catalog/*`,
   `/ontology/*`, `/graph/query`, `/search/semantic`,
   `/catalog/datasets/{id}/jsonld` 등)으로 이 leaf를 호출합니다. Hub
   링크를 문서에서 지우지 않습니다.
5. **개인정보.** 인가된 데이터는 목적 바운드 접근 제어, 암호화, 감사
   아래에서 사용 가능해야 합니다. 마스킹을 제품 규칙으로 처방하지
   않습니다.

## Runtime planes (already shipped)

이 앱은 단일 FastAPI 프로세스(`sdp.api:app`)입니다. 논리 평면만 나눕니다.

| Plane | 책임 | 이 브랜치의 표면 |
| --- | --- | --- |
| Catalog | 데이터셋 검색·상세·lineage | `/catalog/*` |
| Ontology | 용어 해석, 개념 그래프, patch queue | `/ontology/*` |
| Graph + vector | 노드/엣지 수집, 제한된 순회, KNN | `/graph/*`, `/search/semantic` |
| Browse / query | 스키마·preview·governed SQL draft | `/browse/*`, `/llm/*` |
| Policy / evidence | 목적·역할·tenant 판단과 감사 | `/policy/*`, evidence store |
| Enterprise | readiness / console / evidence pack | `/enterprise/*` |

그래프 스토어는 교체 가능합니다. DSN이 없으면 in-memory(BFS + cosine
KNN), `SDP_DATABASE_DSN`이 있고 AGE/pgvector가 준비되면 Postgres
백엔드입니다. API 계약은 같습니다.

## Consequences

- 구매자는 이 저장소만으로 카탈로그를 시연할 수 있습니다.
- Hub 통합은 HTTP와 계약 문서에 의존합니다. 소스 트리를 합치지 않습니다.
- 점수·측정·주간보고 UI 요구는 해당 home으로 보냅니다.
- 구 PRD 문장의 “민감 컬럼 마스킹” 처방은 이 MSA와 README의
  개인정보 규칙을 이기지 못합니다.

## References

서지 원천은 [REFERENCES.md](REFERENCES.md)입니다. 관련 draft ADR:
[0001](adr/0001-product-authority-boundary.md),
[0002](adr/0002-semantic-web-grounding.md),
[0003](adr/0003-graph-vector-retrieval.md),
[0004](adr/0004-docs-only-scope.md).
