# Semantic Data Portal

Semantic Data Portal은 ContextualWisdomLab의 ontology 기반 semantic data catalog 및 탐색 서비스입니다. catalog metadata, ontology concept, graph traversal, semantic retrieval, governed preview, evidence-backed readiness surface를 하나의 독립 실행 가능한 HTTP service 경계에서 제공합니다.

> 이 landing은 보호된 `main`의 현재 제품 사실만 설명합니다. 열린 pull request, draft ADR, 계획된 catalog 확장, queued verification을 이미 제공되는 기능처럼 표시하지 않습니다.

## 시작하기

- [저장소 개요와 로컬 실행 가이드](https://github.com/ContextualWisdomLab/semantic-data-portal#readme)
- [제품·기술 요구사항](prd-trd.html)
- [구현 compliance](implementation-compliance.html)
- [Research notes](papers/README.html)
- [GitHub Releases](https://github.com/ContextualWisdomLab/semantic-data-portal/releases)
- [Ask DeepWiki](https://deepwiki.com/ContextualWisdomLab/semantic-data-portal)

## 제품 책임

Semantic Data Portal은 semantic catalog와 ontology metadata, graph/vector retrieval contract, governed catalog browsing, 조회 결과에 결합되는 policy/evidence surface, 그리고 다른 ContextualWisdomLab 제품이 catalog 의미를 소비하는 API 경계를 소유합니다. sibling repository checkout 없이 in-memory development backend 또는 구성된 persistence/graph service로 실행할 수 있습니다.

반면 document body, psychometric scoring kernel, 고용·조직 기록, 다른 제품의 workflow state는 이 저장소의 source of truth가 아닙니다. 각 시스템은 명시적인 contract를 통해 통합되고 자체 권위를 유지합니다.

## 현재 운영 모델

보호된 기본 브랜치는 health/readiness, graph ingestion 및 traversal, ontology resolution, semantic search, catalog search/detail, governed schema·preview, policy decision, query-draft assistance, enterprise evidence/readiness endpoint를 제공합니다. 구성은 root README에 설명된 local development fallback 또는 PostgreSQL-backed evidence/graph profile을 사용할 수 있습니다.

고객별 credential과 외부 identity/provider 설정은 deployment가 소유하는 secret/configuration 경계에 둡니다. 설정 또는 preflight가 성공했다는 사실만으로 production authentication, data-access, integration acceptance가 완료되었다고 간주하지 않습니다.

## 검증과 릴리스 경계

보호된 브랜치의 test, fuzzing, security/SAST gate, exact-current-head review, repository governance가 통합 증거입니다. predecessor head, skipped/queued check, active pull request, draft document, local-only result는 shipped proof가 아닙니다. public release와 deployment evidence도 source availability와 별도로 검증합니다.

## GitHub Pages 발행 경계

이 파일은 GitHub Pages source candidate이며 Pages가 실제로 live라는 증거가 아닙니다. 보호된 브랜치 통합, 조직 소유 control path를 통한 Pages configuration/deployment, 공개 HTTPS content 재검증까지 완료되어야 publication을 완료로 간주합니다.

## 라이선스

Semantic Data Portal 원저작 source는 [MIT License](https://github.com/ContextualWisdomLab/semantic-data-portal/blob/main/LICENSE)로 제공됩니다. third-party component는 각자의 license obligation을 유지합니다.
