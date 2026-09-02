# ADR 0003 — Graph + vector retrieval

- Status: Draft
- Date: 2026-08-18
- Supersedes: none

## Context

카탈로그는 키워드 검색만으로 동의어·상위/하위 개념·의미 유사 자산을
찾기 어렵습니다. 이 저장소는 이미 두 경로를 같이 둡니다.

- **그래프 순회:** 개념/데이터셋/컬럼 노드와
  broader / narrower / related / mapping / lineage 엣지.
  `POST /graph/query`는 시작 노드, 관계 허용 목록, 방향, 최대 깊이
  (1–6)입니다. 서버가 순회를 만들고 호출자 raw Cypher를 받지 않습니다.
- **벡터 검색:** `POST /search/semantic`. in-memory는 cosine KNN,
  Postgres 백엔드는 같은 인스턴스의 pgvector입니다.

문헌 근거는 `docs/papers/README.md`에 이미 이름이 있는 세 편으로
제한합니다. Crossref·arXiv 공식 기록을 연 뒤에만 인용합니다.
Miller (1990) fuzzing 문헌은 온톨로지 근거가 아니므로 쓰지 않습니다.

## Decision

1. **명시 그래프와 임베딩 검색을 함께 유지한다.** 그래프는 해석 가능한
   관계, 벡터는 의미 유사 재현입니다. 한쪽만으로 카탈로그 검색을
   대체하지 않습니다.
2. **백엔드는 교체 가능하고 계약은 같다.** DSN이 없으면 in-memory.
   AGE+pgvector가 준비되면 Postgres. 단독 기동과 CI가 DB에 묶이지
   않습니다.
3. **질의는 제한된 순회 API이다.** raw openCypher / 임의 SPARQL을
   공개 계약으로 두지 않습니다.
4. **문헌은 정렬용이다.** GraphRAG는 엔티티 그래프를 만들어 순회하는
   동기를, Pan 등은 KG와 학습 표현의 보완을, HybridRAG는 그래프 검색과
   벡터 검색을 같이 쓰는 실증을 제공합니다. 이 서비스가 해당 논문을
   재구현한다고 주장하지 않습니다.

## Consequences

- `/graph/query`와 `/search/semantic`은 운영 README에 남는 정직한
  계약입니다.
- 새 PDF를 첨부하지 않습니다. 재배포가 허용된 기존 GraphRAG PDF만
  `docs/papers/`에 있습니다.
- 인용은 [../REFERENCES.md](../REFERENCES.md)와 이 ADR에 APA 7th로
  모읍니다. draft이며 사람이 재검증하기 전 최종이 아닙니다.

## References

Edge, D., Trinh, H., Cheng, N., Bradley, J., Chao, A., Mody, A., Truitt, S., Metropolitansky, D., Ness, R. O., & Larson, J. (2024). *From local to global: A Graph RAG approach to query-focused summarization*. arXiv. https://doi.org/10.48550/arXiv.2404.16130

Pan, S., Luo, L., Wang, Y., Chen, C., Wang, J., & Wu, X. (2024). Unifying large language models and knowledge graphs: A roadmap. *IEEE Transactions on Knowledge and Data Engineering, 36*(7), 3580–3599. https://doi.org/10.1109/TKDE.2024.3352100

Sarmah, B., Hall, B., Rao, R., Patel, S., Pasquali, S., & Mehta, D. (2024). *HybridRAG: Integrating knowledge graphs and vector retrieval augmented generation for efficient information extraction*. arXiv. https://doi.org/10.48550/arXiv.2408.04948
