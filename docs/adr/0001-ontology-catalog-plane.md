# ADR 0001 — Ontology/catalog plane above the document knowledge graph

**Status:** Accepted  
**Date:** 2026-08-18  
**Issue:** ContextualWisdomLab/semantic-data-portal#13

## Context

naruon owns the document knowledge graph (`content_graph`, `project_graph`).
Semantic Data Portal (SDP) is the upper ontology and catalog plane: buyers
browse glossary terms and catalog objects that *resolve* document-KG identity,
they do not store email/file bodies here (ContextualWisdomLab/naruon#974).

DiskSage catalog ingest and preview live in open PRs #59 and #61. This plane
must consume those objects as opaque references, not duplicate the adapters.
Keyverse remains the identity provider; SDP only consumes the OIDC subject and
`X-CWL-Tenant-Reference`.

## Decision

1. Expose a tenant-bound plane (`/plane/catalog-objects`, `/plane/query`) that
   supports create, list, get, query, document-KG linking, and concept binding.
2. Fail closed when the Keyverse OIDC subject or `X-CWL-Tenant-Reference` is
   missing or when the header does not match the OIDC tenant claim. SDP does
   not provision tenants, an IdP, or SCIM.
3. Persist catalog identity in 3NF tables with two-or-more-word `snake_case`
   names (`catalog_objects`, `object_definitions`, `object_aliases`,
   `document_kg_links`, `concept_object_bindings`, `commons_score_references`,
   `object_stewards`). Repeating groups are rows, not JSON blobs.
4. Keep steward display names usable. Access is purpose-limited
   (`X-CWL-Access-Purpose`). The plane reuses existing `policy.evaluate()`
   (create/search) and records `policy_decision_id`; it does not add a local
   GRC policy registry and does not mask PII.
5. Plane contracts live in `sdp_core.catalog_plane` (not `contracts.py`) so the
   library layer stays split: demo Dataset contracts vs tenant-bound plane
   objects.
6. If a psychometric or commons score is needed, store only an https TEPP or
   commons REST pointer. SDP does not compute item scores.
7. Cite OWL, RDF, and PROV as vocabulary references only. Deep doctoring stays
   with CWL Researcher.
8. `Authorization: Bearer <Keyverse access token>` is the production identity
   path. Raw `X-CWL-Oidc-Subject` authentication is disabled by default even
   when JWKS coordinates are absent. A local demo or CI environment may opt in
   only by setting `SDP_ALLOW_UNVERIFIED_SUBJECT_HEADER=true`; the code still
   rejects that header whenever Keyverse JWKS is configured. Externally
   reachable gateways must strip caller-supplied subject headers, and a paid
   pilot must not enable the demo flag.

## Standards cited (APA 7th)

Lebo, T., Sahoo, S., & McGuinness, D. (Eds.). (2013). *PROV-O: The PROV
ontology*. World Wide Web Consortium. https://www.w3.org/TR/prov-o/

World Wide Web Consortium. (2012). *OWL 2 web ontology language document
overview* (2nd ed.). https://www.w3.org/TR/owl2-overview/

World Wide Web Consortium. (2014). *RDF 1.1 concepts and abstract syntax*.
https://www.w3.org/TR/rdf11-concepts/

## Consequences

- Buyers can register and browse catalog/ontology objects for one Keyverse
  tenant without waiting for DiskSage ingest PRs to merge.
- Document content, people/team/legal-entity KG, weekly lineage reports, and
  IRT scoring remain outside this repository.
- Postgres AGE + pgvector remain the graph engine under the plane; the new
  tables are the relational catalog identity layer above that engine.
- In-memory is the CI / pytest default. When ``SDP_DATABASE_DSN`` is set the
  plane reads and writes the 0002 tables so a paid-pilot restart keeps
  glossary and catalog rows. This plane does not use Apache AGE or pgvector.
- Test fixtures must opt into the demo subject-header path explicitly; deleting
  the opt-in exercises the same fail-closed behavior as an external deployment.
