# OpenMetadata interoperability

Semantic Data Portal provides the ContextualWisdomLab anti-corruption layer for OpenMetadata. The integration preserves external identity and provenance while preventing an external catalog payload from becoming authoritative domain truth without review.

## Current support

| Capability | Status in PR #96 |
|---|---|
| OpenMetadata 2.x release gate | Implemented |
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

The compatibility baseline is OpenMetadata `2.0.1-release`. Later 2.x releases require fixture and schema-drift verification before being declared supported.

## Authority boundary

```text
OpenMetadata entity
    │ external UUID, FQN, version, hash, references
    ▼
OpenMetadata anti-corruption layer
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
  "source_release": "2.0.1",
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

The projection keeps `source_authority = openmetadata` and `truth_status = observed`.

## Field mapping

| OpenMetadata source | SDP projection |
|---|---|
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

The adapter rejects:

- a release that is not explicitly identified as OpenMetadata 2.x;
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

Pydantic request-shape failures return HTTP 422. A valid request shape with an invalid external contract returns a bounded HTTP 400 error and does not echo the source payload.

## Use by other CWL products

Products must not add independent OpenMetadata runtime clients merely to publish their own metadata.

- `pg-erd-cloud` publishes released physical-schema observations to SDP.
- `mhtml-etl-gateway` publishes schema proposals and lineage evidence to SDP after its own validation and steward workflow.
- learning, HR, billing, psychometrics, security, and AI products retain their domain truth and publish only released metadata/evidence contracts.
- `enterprise-architecture-core` consumes released SDP context for impact analysis; it does not query OpenMetadata directly.
- Contextual Orchestrator consumes policy-filtered SDP context bundles. OpenMetadata text remains untrusted data and cannot alter orchestration policy.

## Successor implementation order

1. Normalized external source, snapshot, admission receipt, and projection-history tables.
2. Idempotent admission by tenant, source authority, entity UUID, source version, and source hash.
3. Restricted immutable raw-payload evidence and purpose-bound retrieval.
4. Signed Change Event/webhook inbox, replay protection, ordering, dead-letter evidence, and rollback.
5. Credential-registry and canonical-egress based OpenMetadata API retrieval.
6. Steward-approved outbound writes with version/ETag preconditions and operation receipts.
7. Additional entity mappings and cross-product contract publication.

See ADR-0001 and issue #95 for the ownership and delivery decisions.
