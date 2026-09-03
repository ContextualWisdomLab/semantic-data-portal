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

A second interoperability risk is version ambiguity. A major-version regular expression can establish that a label looks like OpenMetadata 2.x, but it cannot prove that the payload matches schemas or behavior tested by CWL. Treating every future 2.x release as compatible would allow schema drift to enter the catalog without an explicit decision or reproducible source identity.

## Decision

`semantic-data-portal` owns the OpenMetadata anti-corruption layer and the admitted Data/AI Context projection.

OpenMetadata remains an external metadata authority. Its entity UUID, fully qualified name, entity version, source hash, updated time, and entity references are preserved. The projection is marked `observed`; it is not silently promoted to authoritative CWL domain truth.

The first implementation slice is read-only and deterministic:

1. Accept an explicitly declared OpenMetadata Table payload and optional EntityLineage payload only through an exact verified release profile.
2. Normalize table identity, nested columns, owners, domains, data products, data contract, classifications, safe aggregate profile fields, and table/column lineage.
3. Reject malformed UUIDs, conflicting references, unknown lineage endpoints, duplicate column paths, excessive nesting, excessive collections, cyclic direct-call containers, non-HTTP references, and URLs containing credentials.
4. Exclude sample rows, DDL, SQL/query text, join samples, column profiles, custom metrics, extension payloads, and transformation functions from the general catalog projection.
5. Record the omitted source field classes without copying their values.
6. Expose the result through `POST /integrations/openmetadata/v1/table-snapshots:normalize`.
7. Return the compatibility profile, upstream repository, and exact upstream commit used as the adapter's contract source.

### Exact compatibility profile

The first profile is immutable and has the following identity:

```text
profile_id: openmetadata-table-lineage-2.0.1
canonical_release: 2.0.1
accepted_labels: 2.0.1, 2.0.1-release
upstream_repository: open-metadata/OpenMetadata
upstream_tag: 2.0.1-release
upstream_revision: bf621b166ec12e8c99fcb1c1443442723386fa41
```

It is tested against these upstream schema paths at that revision:

```text
openmetadata-spec/src/main/resources/json/schema/entity/data/table.json
openmetadata-spec/src/main/resources/json/schema/type/entityLineage.json
```

The public package and HTTP route resolve the release profile before invoking the pure normalizer. The internal syntax validator remains separate so tests can distinguish malformed release labels from well-formed but unverified releases. `2.0.1-release` is normalized to `2.0.1` in the projection. A label such as `2.1.0` fails closed until a distinct verified profile is added.

The upstream revision is contract-source provenance. It does not, by itself, prove that a submitted payload was fetched from that Git commit. A successor admission receipt must bind the actual submitted payload digest, normalized projection digest, source instance, observation time, and profile identity.

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
- A release label is not compatibility evidence without a profile bound to exact upstream source and executable fixtures.
- Existing compatibility profiles are not rewritten when a later release changes schema or behavior.

## Alternatives considered

### Use OpenMetadata as the organization-wide system of record

Rejected. It would move product-domain truth into an external catalog model and weaken the existing federated ownership model. HR, billing, learning, psychometrics, security, and enterprise-architecture facts have different invariants and approval lifecycles.

### Add an OpenMetadata SDK to each CWL product

Rejected. This creates incompatible mappings and distributes credentials, retry behavior, version drift, and conflict logic across repositories.

### Accept every syntactically valid OpenMetadata 2.x release

Rejected. Semantic-version syntax and a shared major version do not establish field-level compatibility. New required properties, enum members, reference shapes, lineage semantics, or sensitive payload classes could be silently misinterpreted. Compatibility must be established by a new immutable profile, schema-drift review, and exact fixtures.

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
- Downstream consumers can identify the exact compatibility profile and upstream contract source.
- Future release support requires an auditable change rather than an implicit regular-expression expansion.
- The first slice can be tested without network credentials or a live OpenMetadata server.

### Costs

- Only explicitly profiled OpenMetadata releases are admitted.
- Bidirectional synchronization is not available in the first slice.
- Additional entity types require explicit mappings and contract tests.
- Durable replay, conflict resolution, and write receipts need a later persistence model.
- OpenMetadata release drift must be monitored and tested rather than assumed compatible.

## Required successor decisions

1. Deterministic payload, source-identity, and normalized-projection digests plus admission-preview receipt.
2. 3NF external metadata source, snapshot, admission receipt, and projection history.
3. Raw payload retention classification and restricted immutable evidence storage.
4. Signed webhook/change-event verification, inbox deduplication, ordering, replay, and dead-letter evidence.
5. Canonical egress and credential-bound outbound synchronization.
6. Steward approval and optimistic concurrency for ownership, glossary, classification, quality, and lineage writes.
7. Contract ownership split between `semantic-data-portal` and `context-graph-contracts` once multiple independent consumers exist and an immutable released contract is available.

## Verification

The implementation must retain RED-before-GREEN history and prove:

- production statement coverage 100%;
- production branch coverage 100%;
- public API docstrings 100%;
- exact OpenMetadata 2.0.1 fixtures;
- equivalence of the `2.0.1` and `2.0.1-release` aliases;
- rejection of a well-formed but unverified release such as `2.1.0`;
- exact profile, upstream repository, and upstream revision in every projection;
- hostile and malformed input tests;
- absence of sample, SQL, DDL, and transformation text in serialized projections;
- no outbound network calls, credentials, persistence, or cross-service SQL in this slice.

## References

OpenMetadata. (2026). *OpenMetadata 2.0.1 release*. GitHub tag `2.0.1-release`, commit `bf621b166ec12e8c99fcb1c1443442723386fa41`.

OpenMetadata. (2026). *Table JSON schema*. `openmetadata-spec/src/main/resources/json/schema/entity/data/table.json`, commit `bf621b166ec12e8c99fcb1c1443442723386fa41`.

OpenMetadata. (2026). *EntityLineage JSON schema*. `openmetadata-spec/src/main/resources/json/schema/type/entityLineage.json`, commit `bf621b166ec12e8c99fcb1c1443442723386fa41`.
