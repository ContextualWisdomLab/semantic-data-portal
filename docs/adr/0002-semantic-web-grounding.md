# ADR 0002 — Semantic Web grounding

- Status: Draft
- Date: 2026-08-18
- Supersedes: none

## Context

카탈로그는 비즈니스 용어로 데이터셋을 찾고, 개념 계층을 노출하며,
데이터셋을 JSON-LD로 내보내고, metadata validation 리포트를 냅니다.
PRD는 OWL / RDF / SKOS / SHACL / SPARQL / PROV / DCAT을 목표 어휘로
적습니다. 구현은 그 전체 스택의 런타임이 아닙니다.

확인한 사실(이 브랜치):

- 용어 그래프는 `broader` / `narrower` / `related`를 가집니다 (SKOS식
  계층·연관). OWL reasoner는 없습니다.
- `GET /catalog/datasets/{id}/jsonld`는
  `https://www.w3.org/TR/vocab-dcat-3/`를 `@context`로 쓰는 JSON-LD
  객체를 반환합니다.
- `/enterprise/shacl-validation`과 dataset semantic-validation은
  **SHACL-compatible** 리포트입니다. 전체 SHACL 엔진이 아닙니다.
- `/graph/query`는 시작 노드·관계 허용 목록·방향·깊이 제한입니다.
  SPARQL 엔드포인트가 아니고, 호출자 raw openCypher도 받지 않습니다.
- `/catalog/datasets/{id}/lineage`는 `lineage_inputs` /
  `lineage_outputs` 목록입니다. PROV-O 직렬화가 아닙니다.

ISO/IEC 11179는 iso.org에서 이 결정과 맞춰 채택한 기록이 없어
인용하지 않습니다.

## Decision

의미 웹 **권고안을 정렬 목표**로 둡니다. 구현 완료 선언이 아닙니다.

1. **OWL 2** — 온톨로지 언어의 형식 의미. 클래스/속성/개체를 RDF로
   교환하는 목표. 이 브랜치는 OWL reasoner를 추가하지 않습니다.
2. **RDF 1.1** — 트리플·그래프·IRI 데이터 모델. 카탈로그 의미는 RDF로
   표현 가능해야 합니다.
3. **JSON-LD 1.1** — HTTP에서 Linked Data를 JSON으로 내보내는 직렬화.
   현재 dataset export가 이 경로입니다.
4. **DCAT 3** — 데이터 카탈로그 어휘. JSON-LD `@context`가 가리키는
   권고안입니다.
5. **SKOS** — glossary의 broader / narrower / related. 용어 계층이
   실제로 이 관계를 씁니다.
6. **SHACL** — RDF 그래프를 shape로 검증하는 언어. 현재 리포트는
   호환 요약이며, 전체 SHACL 실행기가 아닙니다.
7. **SPARQL 1.1** — RDF 질의 언어. metadata KG / competency question의
   정렬 목표입니다. 게시된 그래프 질의는 파라미터 바인딩된 property-graph
   순회입니다.
8. **PROV-DM / PROV-O** — provenance를 entity / activity / agent로
   말하는 모델. 카탈로그 lineage를 앞으로 표현할 때의 어휘입니다.
   현재 lineage API는 그 직렬화가 아닙니다.

## Consequences

- 문서와 ADR은 W3C Recommendation URL만 근거로 씁니다.
- “SHACL 통과”를 전체 SHACL engine 도입으로 읽지 마십시오.
- “그래프 질의”를 SPARQL 엔드포인트로 읽지 마십시오.
- ISO/IEC 11179, 취소된 OpenCode/Strix 본문, 확인하지 않은 control ID는
  근거가 아닙니다.
- 이 ADR은 draft입니다.

## References

Albertoni, R., Browning, D., Cox, S. J. D., Gonzalez Beltran, A., Perego, A., & Winstanley, P. (Eds.). (2024, August 22). *Data catalog vocabulary (DCAT) — Version 3* (W3C Recommendation). World Wide Web Consortium. https://www.w3.org/TR/vocab-dcat-3/

Harris, S., & Seaborne, A. (Eds.). (2013, March 21). *SPARQL 1.1 query language* (W3C Recommendation). World Wide Web Consortium. https://www.w3.org/TR/sparql11-query/

JSON-LD Working Group. (2020, July 16). *JSON-LD 1.1: A JSON-based serialization for linked data* (W3C Recommendation). World Wide Web Consortium. https://www.w3.org/TR/json-ld11/

Lebo, T., Sahoo, S., & McGuinness, D. (Eds.). (2013, April 30). *PROV-O: The PROV ontology* (W3C Recommendation). World Wide Web Consortium. https://www.w3.org/TR/prov-o/

Miles, A., & Bechhofer, S. (Eds.). (2009, August 18). *SKOS simple knowledge organization system reference* (W3C Recommendation). World Wide Web Consortium. https://www.w3.org/TR/skos-reference/

Moreau, L., & Missier, P. (Eds.). (2013, April 30). *PROV-DM: The PROV data model* (W3C Recommendation). World Wide Web Consortium. https://www.w3.org/TR/prov-dm/

RDF Data Shapes Working Group. (2017, July 20). *Shapes constraint language (SHACL)* (W3C Recommendation). World Wide Web Consortium. https://www.w3.org/TR/shacl/

RDF Working Group. (2014, February 25). *RDF 1.1 concepts and abstract syntax* (W3C Recommendation). World Wide Web Consortium. https://www.w3.org/TR/rdf11-concepts/

W3C OWL Working Group. (2012, December 11). *OWL 2 web ontology language document overview* (Second edition) (W3C Recommendation). World Wide Web Consortium. https://www.w3.org/TR/owl2-overview/
