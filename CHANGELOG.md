# Changelog

## 0.3.1 — 2026-08-18

### Added

- Buyer-facing ontology/catalog plane above the document KG (`/plane/catalog-objects`,
  `/plane/query`) for issue #13: create, list, get, query, document-KG links, and
  concept bindings.
- Fail-closed Keyverse binding on `X-CWL-Oidc-Subject` / Bearer JWT,
  `X-CWL-Tenant-Reference`, and `X-CWL-Access-Purpose`.
- 3NF migration `0002_ontology_catalog_plane.sql` and ADR 0001 (OWL/RDF/PROV
  cited in APA 7th only).
