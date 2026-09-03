# ADR-0001: OpenMetadata interoperability uses an SDP anti-corruption layer

- **Status:** Proposed
- **Date:** 2026-09-03
- **Decision owner:** Semantic Data Portal
- **Related issue:** #95
- **Implementation PR:** #96

## Context

ContextualWisdomLab products produce physical schema observations, lineage, data quality evidence, ontology labels, data products, contracts, dashboards, model assets, and AI-agent context. Customers may already operate OpenMetadata and expect these products to exchange metadata with it.

Making OpenMetadata the authority for every CWL domain would collapse distinct bounded contexts. Embedding an OpenMetadata SDK in every product would also duplicate mapping, credentials, version handling, retry behavior, privacy controls, and conflict resolution.

The existing Context Fabric architecture assigns Data and AI context to `semantic-data-portal`, enterprise transformation decisions to `enterprise-architecture-core`, cross-product identifiers and event contracts to `context-graph-contracts`, physical schema observations to `pg-erd-cloud`, and inferred relations to LineageWeave. OpenMetadata support must preserve those ownership boundaries.

## Decision

`semantic-data-portal` owns the OpenMetadata anti-corruption layer and the admitted Data/AI Context projection.

OpenMetadata remains an external metadata authority. Its entity UUID, fully qualified name, entity version, source hash, updated time, and entity references are preserved. The projection is marked `observed`; it is not silently promoted to authoritative CWL domain truth.

The first implementation slice is read-only and deterministic:

1. Accept an explicitly declared OpenMetadata 2.x Table payload and optional EntityLineage payload.
2. Normalize table identity, nested columns, owners, domains, data products, data contract, classifications, safe aggregate profile fields, and table/column lineage.
3. Reject malformed UUIDs, conflicting references, unknown lineage endpoints, duplicate column paths, excessive nesting, excessive collections, cyclic direct-call containers, non-HTTP references, and URLs containing credentials.
4. Exclude sample rows, DDL, SQL/query text, join samples, column profiles, custom metrics, extension payloads, and transformation functions from the general catalog projection.
5. Record the omitted source field classes without copying their values.
6. Expose the result through `POST /integrations/openmetadata/v1/table-snapshots:normalize`.

The contract is initially pinned and tested against the official OpenMetadata `2.0.1-release` Table and EntityLineage schemas. The request must state its source release. Pre-2.x payloads are rejected instead of being reinterpreted.

Durable admission, signed change-event ingestion, outbound synchronization, and additional asset types are successor slices. They must not be hidden inside this read-only normalization PR.

## Context map

```text
CWL domain owner
    │ released domain/evidence contract
    ▼
semantic-data-portal
    │ safe governed projection
    ├──────────────► Contextual Orchestrator / MCP context
    ├──────────────► enterprise-architecture-core impact consumer
    └──────────────► OpenMetadata adapter boundary
                         │
                         ▼
                    OpenMetadata
```

Rules:

- CWL products do not query another product database.
- `enterprise-architecture-core` consumes released SDP context; it does not call OpenMetadata directly.
- `context-graph-contracts` owns cross-product envelope schemas, not the OpenMetadata client runtime.
- OpenMetadata webhook or API input is untrusted and cannot change CWL policy or truth status.
- LLM/inferred proposals require steward approval before any future outbound write.

## Alternatives considered

### Use OpenMetadata as the organization-wide system of record

Rejected. It would move product-domain truth into an external catalog model and weaken the existing federated ownership model. HR, billing, learning, psychometrics, security, and enterprise-architecture facts have different invariants and approval lifecycles.

### Add an OpenMetadata SDK to each CWL product

Rejected. This creates incompatible mappings and distributes credentials, retry behavior, version drift, and conflict logic across repositories.

### Create a new `openmetadata-gateway` repository immediately

Rejected for the current maturity level. The first capability is a narrow SDP-owned anti-corruption layer without an independent database, release lifecycle, or buyer surface. A separate service is justified later only if throughput, network isolation, or independent deployment establishes a real bounded context.

### Copy all OpenMetadata entities into the existing generic graph tables

Rejected. Generic graph nodes are useful read projections, not a business-rule system of record. Durable ingestion requires normalized external-source, snapshot, receipt, relation, and provenance records before graph projection.

## Consequences

### Benefits

- One compatibility boundary for all CWL products.
- OpenMetadata upgrades are isolated from domain models.
- External and internal authority remain distinguishable.
- Sensitive source content is excluded by construction.
- The first slice can be tested without network credentials or a live OpenMetadata server.

### Costs

- Bidirectional synchronization is not available in the first slice.
- Additional entity types require explicit mappings and contract tests.
- Durable replay, conflict resolution, and write receipts need a later persistence model.
- OpenMetadata release drift must be monitored and tested rather than assumed compatible.

## Required successor decisions

1. 3NF external metadata source, snapshot, admission receipt, and projection history.
2. Raw payload retention classification and restricted immutable evidence storage.
3. Signed webhook/change-event verification, inbox deduplication, ordering, replay, and dead-letter evidence.
4. Canonical egress and credential-bound outbound synchronization.
5. Steward approval and optimistic concurrency for ownership, glossary, classification, quality, and lineage writes.
6. Contract ownership split between `semantic-data-portal` and `context-graph-contracts` once multiple independent consumers exist.

## Verification

The implementation must retain RED-before-GREEN history and prove:

- production statement coverage 100%;
- production branch coverage 100%;
- public API docstrings 100%;
- exact OpenMetadata 2.0.1 fixtures;
- hostile and malformed input tests;
- absence of sample, SQL, DDL, and transformation text in serialized projections;
- no outbound network calls, credentials, persistence, or cross-service SQL in this slice.

## References

OpenMetadata. (2026). *OpenMetadata 2.0.1 release*. GitHub release `2.0.1-release`.

OpenMetadata. (2026). *Table JSON schema*. `openmetadata-spec/src/main/resources/json/schema/entity/data/table.json`, release `2.0.1-release`.

OpenMetadata. (2026). *EntityLineage JSON schema*. `openmetadata-spec/src/main/resources/json/schema/type/entityLineage.json`, release `2.0.1-release`.
