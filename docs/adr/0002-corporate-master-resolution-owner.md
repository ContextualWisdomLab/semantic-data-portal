# ADR 0002 — Corporate-master entity resolution ownership

**Status:** Accepted target contract  
**Date:** 2026-08-26  
**Consumers:** ContextualWisdomLab/LineageWeave and other authorized catalog clients

## Context

Consumers need to bind an observed organization label to an authoritative
corporate-master entity. LineageWeave reconstructs record lineage and presents
authorized evidence; it does not own the corporate master, alias lifecycle, or
cross-product entity identity. Keyverse owns account identity, not business
entity master data. TEPP owns temporal and psychometric measurement, and
RankWeave owns retrieval fusion. None of those responsibilities authorizes a
consumer to decide corporate identity locally.

Semantic Data Portal already owns the tenant-scoped ontology, glossary, catalog
identity, aliases, concept bindings, stewardship, and governance plane under
ADR 0001 and PRD ONT-001–ONT-006. Corporate-master resolution is therefore a
catalog identity decision and belongs at this boundary.

## Decision

Semantic Data Portal is the ecosystem owner of corporate-master entity
resolution. It will publish the versioned contract in
[`docs/corporate-master-resolution-api.md`](../corporate-master-resolution-api.md).

The public outcome is exactly one of:

- `unique`: one catalog entity is supported by the accepted owner method;
- `miss`: no catalog entity is supported; or
- `tie`: multiple catalog entities remain equally admissible.

Only `unique` may return a binding. `miss` and `tie` leave the caller's source
label unbound. A tie is not collapsed into a miss, and no catalog row is
created as a side effect of resolution.

The envelope binds the request, tenant, catalog snapshot, method and contract
versions, source evidence references, outcome, candidates where applicable,
limitations, and result digest. The source representation remains caller-owned;
the API does not ingest document bodies or expose cross-tenant aliases.

## Scientific and policy boundary

This decision introduces no matching algorithm, suffix vocabulary, similarity
threshold, score weight, or fallback. An implementation requires a separate
accepted ADR with authoritative evidence, synthetic unique/miss/tie recovery
tests, and an explicit abstention contract. Until then the endpoint is a target
contract and consumers must report resolution as unavailable rather than run a
local heuristic.

TEPP may provide provenance-bearing temporal/event evidence, and RankWeave may
return a versioned ranking artifact, but neither artifact is corporate identity
authority. Semantic Data Portal validates any such reference under the accepted
resolution method and remains the outcome owner.

## Consequences

- LineageWeave can remove local corporate-name similarity and suffix rules once
  an implemented, released contract is pinned.
- Other products reuse the same tenant-scoped master identity and preserve the
  same unique/miss/tie semantics.
- Catalog stewardship, alias changes, merge/split corrections, and resolution
  audit evidence remain in one governance plane.
- The contract does not expand Keyverse, TEPP, RankWeave, or LineageWeave into
  corporate-master stores.

## Alternatives considered

1. **Keep resolution in each consumer** — rejected because aliases, ties, and
   catalog corrections would diverge across products.
2. **Assign it to Keyverse** — rejected because account authentication and
   business-entity master data are different products and trust boundaries.
3. **Assign it to TEPP or RankWeave** — rejected because measurement/ranking
   evidence does not own canonical catalog identity.
4. **Create a new repository** — rejected because Semantic Data Portal already
   owns the reusable ontology/catalog identity and persistence boundary.

## Rollback

Consumers keep source labels unbound and record the service as unavailable.
They must not restore local heuristic binding or fabricate an `AUTO-*` entity.

## Standards references — APA 7th

Miles, A., & Bechhofer, S. (Eds.). (2009). *SKOS simple knowledge
organization system reference*. World Wide Web Consortium.
https://www.w3.org/TR/skos-reference/

World Wide Web Consortium. (2024). *Data catalog vocabulary (DCAT)—Version
3*. https://www.w3.org/TR/vocab-dcat-3/
