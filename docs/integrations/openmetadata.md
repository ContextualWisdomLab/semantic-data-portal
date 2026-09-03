# OpenMetadata interoperability

Semantic Data Portal provides the ContextualWisdomLab anti-corruption layer for OpenMetadata. The integration preserves external identity and provenance while preventing an external catalog payload from becoming authoritative domain truth without review.

## Current support

| Capability | Status in PR #96 |
|---|---|
| Exact OpenMetadata 2.0.1 compatibility admission | Implemented |
| Table identity and descriptive metadata | Implemented |
| Nested column metadata | Implemented |
| Owners, domains, data products, data contract, classifications | Implemented |
| Aggregate table profile summary | Implemented |
| Table and column lineage | Implemented |
| Payload and reference hardening | Implemented |
| Persistent catalog admission | Not in this slice |
| Change Event/webhook ingestion | Not in this slice |
| Live OpenMetadata API retrieval | Not in this slice |
| Outbound synchronization | Not in this slice |
| Pipelines, dashboards, metrics, ML models, agents, quality incidents | Planned in issue #95 |

The verified compatibility profile is `openmetadata-table-lineage-2.0.1`. It is bound to:

- upstream repository: `open-metadata/OpenMetadata`;
- upstream tag: `2.0.1-release`;
- upstream commit: `bf621b166ec12e8c99fcb1c1443442723386fa41`;
- Table schema: `openmetadata-spec/src/main/resources/json/schema/entity/data/table.json`;
- EntityLineage schema: `openmetadata-spec/src/main/resources/json/schema/type/entityLineage.json`.

The request may use `2.0.1` or `2.0.1-release`; both normalize to the canonical release value `2.0.1`. A different syntactically valid 2.x label, such as `2.1.0`, is rejected until an exact upstream revision, fixtures, schema-drift review, and a new compatibility profile have been added. Major-version syntax validation alone is not compatibility evidence.

## Authority boundary

```text
OpenMetadata entity
    │ external UUID, FQN, version, hash, references
    ▼
OpenMetadata anti-corruption layer
    │ exact release-profile admission
    │ validated and privacy-bounded observation
    ▼
SDP projection: truth_status = observed
    │
    ├─ steward admission in a successor slice
    ├─ policy-filtered context bundle
    └─ impact consumers
```

The normalizer does not publish a catalog asset, write to OpenMetadata, fetch a remote URL, or persist credentials. Domain owners continue to own their business facts.

## Endpoint

```http
POST /integrations/openmetadata/v1/table-snapshots:normalize
Content-Type: application/json
```

Request:

```json
{
  "tenant_id": "tenant_acme",
  "source_release": "2.0.1-release",
  "table": {
    "id": "11111111-1111-4111-8111-111111111111",
    "name": "orders",
    "displayName": "Orders",
    "fullyQualifiedName": "warehouse.sales.public.orders",
    "columns": [
      {
        "name": "order_id",
        "dataType": "UUID",
        "constraint": "PRIMARY_KEY"
      }
    ]
  },
  "lineage": {
    "entity": {
      "id": "11111111-1111-4111-8111-111111111111",
      "type": "table",
      "name": "warehouse.sales.public.orders"
    },
    "nodes": [],
    "upstreamEdges": [],
    "downstreamEdges": []
  }
}
```

The response is a typed `OpenMetadataTableProjection` with a tenant-scoped CWL identifier:

```text
urn:cwl:{tenant_id}:sdp:openmetadata_table:{openmetadata_uuid}
```

Every response carries the compatibility evidence needed by a downstream consumer:

```json
{
  "source_authority": "openmetadata",
  "source_release": "2.0.1",
  "compatibility_profile_id": "openmetadata-table-lineage-2.0.1",
  "upstream_repository": "open-metadata/OpenMetadata",
  "upstream_revision": "bf621b166ec12e8c99fcb1c1443442723386fa41",
  "truth_status": "observed"
}
```

The upstream revision identifies the contract source used to build and test the adapter. It is provenance, not an assertion that arbitrary payload bytes were fetched from that commit. Durable admission will add source-instance, payload-digest, observation-time, and receipt evidence separately.

## Field mapping

| OpenMetadata source | SDP projection |
|---|---|
| declared release label | canonical `source_release`, compatibility profile, upstream source revision |
| `id` | `external_entity_id` and projection identity |
| `name` | `name` |
| `displayName` | `title`, falling back to `name` |
| `fullyQualifiedName` | `fully_qualified_name` |
| `version` | `entity_version` |
| `updatedAt`, `updatedBy` | `updated_at`, `updated_by` |
| `sourceHash`, `sourceUrl` | `source_hash`, validated `source_url` |
| `tableType`, `serviceType`, `entityStatus` | typed status fields |
| `owners` | external owner references |
| `domains` | external domain references |
| `dataProducts` | external data-product references |
| `dataContract` | external data-contract reference |
| `databaseSchema`, `database`, `service` | external structural references |
| `tags[].tagFQN` | stable classification/tag FQNs |
| `columns` and nested `children` | ordered flattened column paths |
| `profile.rowCount` | aggregate `row_count` |
| `profile.columnCount` | aggregate `column_count` |
| `profile.sizeInByte` | aggregate `size_in_bytes` |
| EntityLineage edges | validated table lineage edges |
| `columnsLineage` identities | source/target column identities |

A missing optional value remains `null` or an empty collection. The adapter does not turn unknown quality, freshness, ownership, or nullability into a numeric zero or an invented default.

## Deliberately omitted content

The general catalog projection never copies these values:

- table sample rows;
- DDL or schema definition text;
- query and SQL text;
- join samples or join statistics;
- column data profiles and custom metrics;
- arbitrary extension payloads;
- lineage transformation functions;
- SQL attached to a lineage edge.

`omitted_fields` records which source field classes were present, without carrying their values. A later restricted evidence store may preserve an encrypted raw payload under a separate retention and access policy; that is not part of this endpoint.

## Validation and failure behavior

The public admission boundary rejects:

- a release label outside OpenMetadata 2.x syntax;
- a syntactically valid 2.x release without an exact verified compatibility profile;
- a non-object table or lineage body;
- missing or malformed entity UUIDs;
- conflicting reuse of one UUID for different references;
- a lineage response whose primary entity differs from the table;
- an edge whose endpoint is not the primary entity or a declared node;
- missing required column names or types;
- duplicate flattened column paths;
- column nesting deeper than 16;
- more than 10,000 normalized columns;
- excessive reference, edge, or column-lineage collections;
- direct-call cyclic containers or excessive generic payload nesting;
- control characters in projected text;
- non-HTTP(S) links and links containing credentials;
- negative, floating-point, boolean, or text values where an integer aggregate is required.

Pydantic request-shape failures return HTTP 422. A valid request shape with an unsupported release profile or invalid external contract returns a bounded HTTP 400 error and does not echo the source payload.

## Adding another OpenMetadata release

A later OpenMetadata release is not enabled by widening a regular expression. A change must add all of the following on one reviewable branch:

1. exact upstream tag and commit identity;
2. immutable Table and EntityLineage schema references;
3. representative positive fixtures authored for the CWL contract tests;
4. hostile and malformed fixtures;
5. a field-level schema-drift review covering additions, removals, type changes, required fields, enums, and sensitive fields;
6. serialization tests proving that omitted source classes still do not cross the boundary;
7. a new `OpenMetadataReleaseProfile` entry;
8. CHANGELOG, ADR, integration documentation, and exact-head CI evidence.

Existing profiles remain immutable. A changed upstream tag target or incompatible schema requires a distinct profile identity rather than rewriting prior compatibility evidence.

## Use by other CWL products

Products must not add independent OpenMetadata runtime clients merely to publish their own metadata.

- `pg-erd-cloud` publishes released physical-schema observations to SDP.
- `mhtml-etl-gateway` publishes schema proposals and lineage evidence to SDP after its own validation and steward workflow.
- learning, HR, billing, psychometrics, security, and AI products retain their domain truth and publish only released metadata/evidence contracts.
- `enterprise-architecture-core` consumes released SDP context for impact analysis; it does not query OpenMetadata directly.
- Contextual Orchestrator consumes policy-filtered SDP context bundles. OpenMetadata text remains untrusted data and cannot alter orchestration policy.

## Successor implementation order

1. Deterministic normalization/admission receipt with payload and projection digests.
2. Normalized external source, snapshot, admission receipt, and projection-history tables.
3. Idempotent admission by tenant, source authority, entity UUID, source version, and source hash.
4. Restricted immutable raw-payload evidence and purpose-bound retrieval.
5. Signed Change Event/webhook inbox, replay protection, ordering, dead-letter evidence, and rollback.
6. Credential-registry and canonical-egress based OpenMetadata API retrieval.
7. Steward-approved outbound writes with version/ETag preconditions and operation receipts.
8. Additional entity mappings and cross-product contract publication.

See ADR-0001 and issue #95 for the ownership and delivery decisions.
