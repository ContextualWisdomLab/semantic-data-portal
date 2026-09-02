# Semantic Data Portal

Semantic Data Portal is ContextualWisdomLab's ontology-driven data catalog and semantic discovery service. It connects business concepts, datasets, and columns through governed catalog metadata, graph relationships, and semantic retrieval while keeping operational data ownership in the systems that own it.

[Ask DeepWiki](https://deepwiki.com/ContextualWisdomLab/semantic-data-portal) · [Repository](https://github.com/ContextualWisdomLab/semantic-data-portal) · [Releases](https://github.com/ContextualWisdomLab/semantic-data-portal/releases)

> This landing describes protected-branch product truth. Open pull requests, Draft ADRs, queued checks, planned catalog expansion, and unpublished deployment/release evidence are not shipped capability.

## Start here

- [Operator and product README](../README.md)
- [Product and technical requirements](prd-trd.md)
- [Product boundary / MSA](msa.md)
- [Implementation compliance map](implementation-compliance.md)
- [Architecture decisions](adr/README.md)
- [Standards and references](REFERENCES.md)
- [Research and attached-paper notes](papers/README.md)
- [Contributing](../CONTRIBUTING.md)

## Product responsibility

The portal owns catalog and ontology truth, tenant-scoped catalog browsing, concept resolution, graph traversal, semantic retrieval, governed data-preview/query surfaces, and the evidence needed to explain catalog and policy decisions. It can run standalone and can be called by composition hubs through published HTTP contracts.

The portal does not take ownership of source document bodies, psychometric scoring kernels, temporal measurement engines, lineage-specialist UIs, or identity authority. Those capabilities stay behind explicit product boundaries and are referenced through contracts rather than copied into the catalog.

## Architecture

The service combines catalog and ontology APIs with optional graph/vector infrastructure. A local in-memory mode supports development and contract testing; PostgreSQL-backed evidence storage and an Apache AGE + pgvector graph profile are documented integration surfaces. Purpose-bound authorization, audit evidence, and bounded external-connector behavior remain part of the operational boundary.

Configuration or preflight success does not by itself prove production authentication, data-access authorization, deployment acceptance, or commercial-license compliance. Current README/operator documentation must remain fail-closed where required runtime dependency provenance is unresolved.

## Evidence and releases

The README and versioned documentation are the source of truth for current operator behavior and product boundaries. Draft ADRs and requirements remain draft until their documented review conditions are satisfied; open pull requests are not treated as shipped capability. Current-head tests, security/SAST checks, reviews, and repository governance are integration evidence. Predecessor-head, queued, skipped, model-only, or local-only results are not shipped proof.

Published releases provide the versioned delivery record and remain distinct from source availability.

## Publication boundary

This file is a GitHub Pages source candidate, not evidence that Pages is already live. Publication is complete only after protected integration, organization-owned Pages configuration/deployment, and live HTTPS content verification succeed.

## License

Semantic Data Portal original source is licensed under the [MIT License](https://github.com/ContextualWisdomLab/semantic-data-portal/blob/main/LICENSE). Third-party components retain their own license obligations. The repository's MIT grant does not relicense runtime dependencies, and this documentation lane remains blocked from commercial integration while the separately tracked incompatible PostgreSQL-driver path is unresolved.

## Documentation status

This page is intentionally a compact public landing surface. Detailed operator steps, architecture decisions, standards references, security boundaries, and implementation mappings remain in the repository so documentation evolves through the same governance path as the product.
