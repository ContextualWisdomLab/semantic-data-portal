# Changelog

## Unreleased

### Added

- Accepted Semantic Data Portal as the corporate-master entity-resolution
  owner and published the target `sdp.corporate-master-resolution/v1` contract.
  The contract preserves distinct `unique`, `miss`, and `tie` outcomes and adds
  no matching heuristic, threshold, weight, or executable endpoint claim.

## 0.3.1 — 2026-08-18

### Added

- Buyer-facing ontology/catalog plane above the document KG (`/plane/catalog-objects`,
  `/plane/query`) for issue #13: create, list, get, query, document-KG links, and
  concept bindings.
- Fail-closed Keyverse binding on `X-CWL-Oidc-Subject` / Bearer JWT,
  `X-CWL-Tenant-Reference`, and `X-CWL-Access-Purpose`.
- 3NF migration `0002_ontology_catalog_plane.sql` and ADR 0001 (OWL/RDF/PROV
  cited in APA 7th only).
- Catalog/ontology plane persistence: in-memory remains the CI default;
  `SDP_DATABASE_DSN` reads and writes the 0002 tables so a paid-pilot restart
  keeps glossary/catalog rows.

### Security

- Disabled raw `X-CWL-Oidc-Subject` authentication by default. Local demo and CI
  must explicitly set `SDP_ALLOW_UNVERIFIED_SUBJECT_HEADER=true`; production and
  paid-pilot deployments use verified Keyverse Bearer JWTs, and JWKS-configured
  deployments reject the raw header even when the demo flag is present.
