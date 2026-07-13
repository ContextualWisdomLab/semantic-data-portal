# Reference papers — graph + vector semantic retrieval

Academic grounding for the Semantic Data Portal graph engine (ontology-driven
retrieval over a property graph combined with vector similarity search). Only
papers under a redistribution-permitting license are attached as PDFs; the rest
are cited with a link + summary, respecting copyright.

---

## 1. GraphRAG — attached (CC BY 4.0)

> Darren Edge, Ha Trinh, Newman Cheng, Joshua Bradley, Alex Chao, Apurva Mody,
> Steven Truitt, Dasha Metropolitansky, Robert Osazuwa Ness, Jonathan Larson.
> **"From Local to Global: A Graph RAG Approach to Query-Focused
> Summarization."** arXiv:2404.16130, 2024.

- Link: https://arxiv.org/abs/2404.16130
- License: **Creative Commons Attribution 4.0 International (CC BY 4.0)** —
  redistributable with attribution. PDF included: [`graphrag-edge-2024-ccby.pdf`](./graphrag-edge-2024-ccby.pdf)
- Why it's relevant: motivates building an **entity/concept knowledge graph**
  and traversing it (community/neighbourhood structure) rather than relying on
  flat vector search alone. SDP mirrors this: concepts/datasets/columns are
  graph nodes with `broader/narrower/related/mapping/lineage` edges (Apache
  AGE, openCypher) that back `/graph/query` and `/ontology/term/{t}/graph`.

## 2. Unifying LLMs and Knowledge Graphs — cite + link only

> Shirui Pan, Linhao Luo, Yufei Wang, Chen Chen, Jiapu Wang, Xindong Wu.
> **"Unifying Large Language Models and Knowledge Graphs: A Roadmap."**
> IEEE Transactions on Knowledge and Data Engineering (TKDE), 2024.
> arXiv:2306.08302.

- Link: https://arxiv.org/abs/2306.08302
- License: arXiv.org perpetual non-exclusive license (redistribution of the PDF
  is not granted) → **not attached**; cited here per copyright rules.
- Why it's relevant: frames KG-enhanced retrieval and the synergy between
  structured graphs (interpretability, explicit relations) and learned
  representations. SDP keeps the ontology as an explicit, auditable property
  graph while layering pgvector embeddings for meaning-based recall.

## 3. HybridRAG — cite + link only

> Bhaskarjit Sarmah, Benika Hall, Rohan Rao, Sunil Patel, Stefano Pasquali,
> Dhagash Mehta. **"HybridRAG: Integrating Knowledge Graphs and Vector
> Retrieval Augmented Generation for Efficient Information Extraction."**
> arXiv:2408.04948, 2024.

- Link: https://arxiv.org/abs/2408.04948
- License: arXiv.org perpetual non-exclusive license → **not attached**; cited
  here per copyright rules.
- Why it's relevant: shows a hybrid of knowledge-graph retrieval and vector
  retrieval beating either alone. This is exactly SDP's architecture: **Apache
  AGE** graph traversal for structured relations + **pgvector** KNN for
  semantic ("찾아주는") recall, co-located in one Postgres datastore.

---

### How these map to the implementation

| Paper idea | SDP component |
| --- | --- |
| Entity/concept knowledge graph | `graph_nodes` / `graph_edges` / `ontology_concepts` (AGE `semantic_graph`) |
| Graph traversal for retrieval | `POST /graph/query`, `GET /ontology/term/{t}/graph` (openCypher) |
| Vector similarity retrieval | `embedding_vectors` (pgvector), `POST /search/semantic` |
| Hybrid graph + vector | single Postgres instance running AGE **and** pgvector |
