# Reference papers — attachment and license notes

APA 7th 서지와 검증 로그는 **[../REFERENCES.md](../REFERENCES.md)** 가
원천입니다. 여기에는 재배포 가능한 PDF 첨부와 저작권 메모만 둡니다.
새 PDF를 이 브랜치에서 첨부하지 않습니다.

Academic grounding for the catalog’s graph + vector retrieval. Only papers
under a redistribution-permitting license are attached as PDFs; the rest
are cite + link, respecting copyright.

---

## 1. GraphRAG — attached (CC BY 4.0)

APA: Edge et al. (2024). See REFERENCES.md.

- Abstract page: https://arxiv.org/abs/2404.16130
- arXiv DOI (opened): https://doi.org/10.48550/arXiv.2404.16130
- License: Creative Commons Attribution 4.0 International (CC BY 4.0) —
  redistributable with attribution. PDF included:
  [`graphrag-edge-2024-ccby.pdf`](./graphrag-edge-2024-ccby.pdf)
- Why it is listed: motivates an entity/concept graph rather than flat
  vector search alone. This catalog stores concepts/datasets/columns as
  graph nodes with broader/narrower/related/mapping/lineage edges.

## 2. Unifying LLMs and Knowledge Graphs — cite + link only

APA: Pan et al. (2024), *IEEE Transactions on Knowledge and Data
Engineering*. See REFERENCES.md.

- Journal DOI (Crossref work record opened):
  https://doi.org/10.1109/TKDE.2024.3352100
- arXiv abs (opened): https://arxiv.org/abs/2306.08302
- License: publisher / arXiv terms do not grant PDF redistribution here →
  **not attached**.
- Why it is listed: frames structured graphs (explicit relations,
  interpretability) beside learned representations.

## 3. HybridRAG — cite + link only

APA: Sarmah et al. (2024). See REFERENCES.md.

- Abstract page: https://arxiv.org/abs/2408.04948
- arXiv DOI (opened): https://doi.org/10.48550/arXiv.2408.04948
- License: arXiv perpetual non-exclusive license → **not attached**.
- Why it is listed: reports hybrid knowledge-graph + vector retrieval
  outperforming either alone. This catalog’s optional Postgres backend
  colocates AGE traversal and pgvector KNN.

These notes do not claim the service reimplements the papers. Draft
citations remain draft until a human/researcher re-verifies
REFERENCES.md.
