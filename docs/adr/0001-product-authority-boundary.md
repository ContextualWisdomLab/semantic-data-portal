# ADR 0001 — Product and authority boundary

- Status: Draft
- Date: 2026-08-18
- Supersedes: none

## Context

CWL는 여러 standalone program을 키운 뒤 hub가 조합합니다.
`semantic-data-portal`은 온톨로지·카탈로그 home입니다. 동시에 naruon
문서 KG, LineageWeave 주간보고 UI, `fast-mlsirm` 점수 커널, TEPP
측정 import가 각각 다른 home에 있습니다. 경계를 문서에 고정하지 않으면
leaf가 hub UI·점수·측정을 흡수하거나, 부팅이 형제 checkout에 묶입니다.

이 저장소는 이미 단독 FastAPI 앱과 HTTP 계약을 제공합니다. 그래프
백엔드는 in-memory 또는 이 저장소 Compose의 AGE+pgvector입니다.

## Decision

1. **이 leaf가 온톨로지/카탈로그 진실을 소유한다.** 데이터셋 메타데이터,
   용어 해석, broader/narrower/related 개념 그래프, JSON-LD export,
   정책 결정과 감사 evidence의 원천은 이 서비스입니다.
2. **Hub는 호출할 수 있다.** naruon과 gyeot는 composition hub이며 게시된
   HTTP 계약으로 이 leaf를 호출할 수 있습니다. hub 링크를 제거하지
   않습니다.
3. **부팅은 형제 저장소에 의존하지 않는다.** 다른 CWL home의 checkout,
   path-dep, git submodule을 기동 조건으로 두지 않습니다. 이 트리는
   독립 실행과 호출 대상이 동시에 되어야 합니다.
4. **LineageWeave #74가 weekly-report KG UI를 소유한다.** 포털은 그 UI를
   소유·구현·restyle하지 않습니다. 카탈로그 lineage 필드와
   `/catalog/datasets/{id}/lineage`는 데이터셋 입출력 목록이며
   LineageWeave 화면이 아닙니다.
5. **점수는 `fast-mlsirm`, 측정 import는 TEPP.** IRT / linking / score
   kernel과 measurement REST를 여기서 재구현하거나 발명하지 않습니다.
6. **개인정보.** 인가된 데이터는 목적 바운드 접근 제어, 암호화, 감사
   아래에서 사용 가능해야 합니다. 마스킹을 제품 규칙으로 처방하지
   않습니다.

## Consequences

- 운영 문서(README, MSA)는 단독 기동과 hub 호출을 함께 설명합니다.
- UI·점수·측정 요구는 해당 저장소로 넘깁니다.
- 구 PRD의 마스킹 처방은 이 결정과 README를 이기지 못합니다.
- 이 ADR은 draft입니다. 제품 경계를 코드로 강제하지 않습니다.

## References

Albertoni, R., Browning, D., Cox, S. J. D., Gonzalez Beltran, A., Perego, A., & Winstanley, P. (Eds.). (2024, August 22). *Data catalog vocabulary (DCAT) — Version 3* (W3C Recommendation). World Wide Web Consortium. https://www.w3.org/TR/vocab-dcat-3/

Moreau, L., & Missier, P. (Eds.). (2013, April 30). *PROV-DM: The PROV data model* (W3C Recommendation). World Wide Web Consortium. https://www.w3.org/TR/prov-dm/

Product tracker (not a bibliographic source): LineageWeave pull request 74, https://github.com/ContextualWisdomLab/LineageWeave/pull/74
