# ADR 0004 — Docs-only scope on this branch

- Status: Draft
- Date: 2026-08-18
- Supersedes: none

## Context

운영 README는 에이전트 작업 수첩과 구현 매핑 표에 가깝고, `docs/adr/`가
없으며, 마스킹을 제품 기능처럼 적고 있었습니다. 동시에 열린 feat/fix/chore
PR(#28, #32, #35, #37, #51, #58, #59, #61, #64 등)과 보안 게이트를 이
문서 작업이 건드리면 leaf 계약과 런타임이 섞입니다.

## Decision

1. **이 브랜치는 문서만 변경한다.** README, CONTRIBUTING, MSA, ADR,
   REFERENCES, papers README 안내. 워크플로, CODEOWNERS, Semgrep/SAST,
   lockfile, 런타임 코드, 기본 브랜치 설정, 보안 게이트를 바꾸지 않습니다.
2. **`main`에 직접 쌓지 않는다.** 열린 feat/fix/chore PR 위에 스택하지
   않습니다.
3. **새 런타임을 발명하지 않는다.** 패키지, 카탈로그 데이터베이스,
   테스트 하네스, 엔드포인트를 이 브랜치에서 추가하지 않습니다.
   이미 있는 health / catalog / graph query / semantic search / JSON-LD만
   운영 사실로 적습니다.
4. **인용은 draft이다.** 연 공식 TR·Crossref·arXiv 기록만 쓰고, 사람이
   재검증하기 전까지 최종이 아닙니다. 확인하지 않은 논문·DOI·control ID,
   취소된 OpenCode/Strix 본문을 근거로 쓰지 않습니다.

## Consequences

- 구매자 README는 기동과 호출 계약에 남고, 기여자 절차는 CONTRIBUTING으로
  갑니다.
- 구현 매핑 표는 `docs/implementation-compliance.md`에 남습니다.
- 이 ADR 자체도 draft이며 런타임을 바꾸지 않습니다.

## References

JSON-LD Working Group. (2020, July 16). *JSON-LD 1.1: A JSON-based serialization for linked data* (W3C Recommendation). World Wide Web Consortium. https://www.w3.org/TR/json-ld11/

RDF Working Group. (2014, February 25). *RDF 1.1 concepts and abstract syntax* (W3C Recommendation). World Wide Web Consortium. https://www.w3.org/TR/rdf11-concepts/
