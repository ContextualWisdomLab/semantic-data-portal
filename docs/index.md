# Semantic Data Portal

Semantic Data Portal is ContextualWisdomLab's ontology-driven semantic data catalog and browsing service. It combines catalog metadata, ontology concepts, graph traversal, semantic retrieval, governed previews, and evidence-backed enterprise readiness surfaces behind one independently runnable HTTP service.

> This landing describes protected `main` product truth. Open pull requests, draft ADRs, planned catalog-plane expansions, and queued verification are not presented as shipped capabilities.

## Start here

- [Repository overview and local run guide](https://github.com/ContextualWisdomLab/semantic-data-portal#readme)
- [Product and technical requirements](prd-trd.md)
- [Implementation compliance](implementation-compliance.md)
- [Research notes](papers/)
- [Repository releases](https://github.com/ContextualWisdomLab/semantic-data-portal/releases)
- [Ask DeepWiki](https://deepwiki.com/ContextualWisdomLab/semantic-data-portal)

## Product responsibility

Semantic Data Portal owns semantic catalog and ontology metadata, graph and vector retrieval contracts, governed catalog browsing, policy/evidence surfaces attached to those reads, and the API boundary through which other ContextualWisdomLab products consume catalog meaning. It can run with an in-memory development backend or configured persistence and graph services without requiring a sibling repository checkout.

The portal does not become the source of truth for document bodies, psychometric scoring kernels, employment/organization records, or another product's workflow state. Those systems integrate through explicit contracts and retain their own authority.

## Current operating model

The protected default branch exposes health/readiness, graph ingestion and traversal, ontology resolution, semantic search, catalog search/detail, governed schema and preview operations, policy decisions, query-draft assistance, and enterprise evidence/readiness endpoints. Configuration can use local development fallbacks or PostgreSQL-backed evidence and graph profiles as documented in the root README.

Customer-specific credentials and external identity/provider configuration stay in deployment-owned secret/configuration boundaries. Successful configuration or preflight evidence is not the same as production authentication, data-access, or integration acceptance.

## Verification and release boundary

Protected-branch tests, fuzzing, security/SAST gates, exact-current-head reviews, and repository governance are integration evidence. A predecessor head, skipped or queued check, active pull request, draft document, or local-only result is not treated as shipped proof. Public releases and deployment evidence remain separate from source availability.

## Publication boundary

This file is a GitHub Pages source candidate, not proof that Pages is live. Publication is complete only after protected integration, repository Pages configuration/deployment through the organization-owned control path, and live HTTPS content verification.

## License

Semantic Data Portal source is licensed under the [MIT License](https://github.com/ContextualWisdomLab/semantic-data-portal/blob/main/LICENSE). Third-party components retain their own license obligations.
