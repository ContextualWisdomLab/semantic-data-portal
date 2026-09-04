# OpenMetadata interoperability

Semantic Data Portal provides the ContextualWisdomLab anti-corruption layer for OpenMetadata. The integration preserves external identity and provenance while preventing an external catalog payload from becoming authoritative domain truth without review.

## Current support

| Capability | Candidate owner | Status |
|---|---|---|
| Exact OpenMetadata 2.0.1 compatibility admission | PR #96 | Implemented, unreleased |
| OIDC bearer verification and tenant binding | PR #96 | Implemented, unreleased |
| Source-installation-scoped projection identity | PR #96 | Implemented, unreleased |
| Table identity and descriptive metadata | PR #96 | Implemented, unreleased |
| Nested column metadata | PR #96 | Implemented, unreleased |
| Owners, domains, data products, data contract, classifications | PR #96 | Implemented, unreleased |
| Aggregate table profile summary | PR #96 | Implemented, unreleased |
| Table and column lineage | PR #96 | Implemented, unreleased |
| Payload, reference, and 8 MiB request-body hardening | PR #96 | Implemented, unreleased |
| Strict JSON, source/projection digest, candidate and observation receipt | PR #99 | Implemented candidate, exact-head verification pending |
| Receipt tamper revalidation | PR #99 | Implemented candidate, exact-head verification pending |
| Persistent catalog admission | successor | Not implemented |
| Change Event/webhook ingestion | successor | Not implemented |
| Live OpenMetadata API retrieval | successor | Not implemented |
| Outbound synchronization | successor | Not implemented |
| Pipelines, dashboards, metrics, ML models, agents, quality incidents | issue #95 | Planned |

The verified compatibility profile is `openmetadata-table-lineage-2.0.1`. It is bound to:

- upstream repository: `open-metadata/OpenMetadata`;
- upstream tag: `2.0.1-release`;
- upstream commit: `bf621b166ec12e8c99fcb1c1443442723386fa41`;
- Table schema: `openmetadata-spec/src/main/resources/json/schema/entity/data/table.json`;
- EntityLineage schema: `openmetadata-spec/src/main/resources/json/schema/type/entityLineage.json`.

The request may use `2.0.1` or `2.0.1-release`; both normalize to the canonical release value `2.0.1`. A different syntactically valid 2.x label, such as `2.1.0`, is rejected until an exact upstream revision, fixtures, schema-drift review, and a new compatibility profile have been added. Major-version syntax validation alone is not compatibility evidence.

## Authority boundary

```text
Verified tenant actor
    │ bearer token, role, tenant
    ▼
OpenMetadata source installation
    │ source instance, external UUID, version, hash, references
    ▼
OpenMetadata anti-corruption layer
    │ exact release-profile admission
    │ validated and privacy-bounded observation
    ▼
SDP projection: truth_status = observed
    │
    ├─ non-mutating candidate/observation receipt (PR #99)
    ├─ durable steward admission in a successor slice
    ├─ policy-filtered context bundle
    └─ impact consumers
```

The normalizer and admission preview do not publish a catalog asset, write to OpenMetadata, fetch a remote URL, or persist credentials. Domain owners continue to own their business facts.

## Authentication and tenant isolation

Both OpenMetadata POST endpoints require `Authorization: Bearer ...`. They reuse the SDP OIDC/JWKS verifier configured with `SDP_OIDC_ISSUER`, `SDP_OIDC_AUDIENCE`, `SDP_OIDC_JWKS_URL`, and `SDP_OIDC_GROUP_ROLE_MAP`.

Allowed roles are:

- `data-analyst`;
- `admin`;
- `platform-admin`.

The verified `ActorContext.tenant_id` must equal the request `tenant_id`. A mismatch returns `404 resource not found` so the endpoint does not disclose another tenant's namespace. A request body cannot override the verified tenant used to construct a projection or receipt.

## Normalization endpoint

```http
POST /integrations/openmetadata/v1/table-snapshots:normalize
Authorization: Bearer <verified OIDC token>
Content-Type: application/json
```

Request bodies are limited to 8 MiB at the router boundary. The same bound applies when another FastAPI application embeds the router directly, including clients that stream a body without `Content-Length`.

Request:

```json
{
  "tenant_id": "tenant_acme",
  "source_instance_id": "metadata_primary",
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
      "name": "orders",
      "fullyQualifiedName": "warehouse.sales.public.orders"
    },
    "nodes": [],
    "upstreamEdges": [],
    "downstreamEdges": []
  }
}
```

The response is a typed `OpenMetadataTableProjection` with a tenant- and installation-scoped CWL identifier:

```text
urn:cwl:{tenant_id}:sdp:openmetadata_table:{source_instance_id}:{openmetadata_uuid}
```

Two OpenMetadata installations may legally reuse the same entity UUID. `source_instance_id` prevents those observations from colliding inside one tenant. It is an operator-controlled opaque identifier, not a hostname or credential.

Every response carries the compatibility evidence needed by a downstream consumer:

```json
{
  "source_authority": "openmetadata",
  "source_instance_id": "metadata_primary",
  "source_release": "2.0.1",
  "compatibility_profile_id": "openmetadata-table-lineage-2.0.1",
  "upstream_repository": "open-metadata/OpenMetadata",
  "upstream_revision": "bf621b166ec12e8c99fcb1c1443442723386fa41",
  "truth_status": "observed"
}
```

The upstream revision identifies the contract source used to build and test the adapter. It is provenance, not an assertion that arbitrary payload bytes were fetched from that commit.

## Field mapping

| OpenMetadata source | SDP projection |
|---|---|
| request installation identifier | `source_instance_id` and projection identity |
| declared release label | canonical `source_release`, compatibility profile, upstream source revision |
| `id` | `external_entity_id` and projection identity |
| `name` | `name` |
| `displayName` | `title`, falling back to `name` |
| `fullyQualifiedName` | optional `fully_qualified_name` |
| `version` | finite `entity_version` |
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

The pinned upstream Table schema requires `id`, `name`, and `columns`; `fullyQualifiedName` is optional. The pinned EntityReference schema requires `id` and `type`; `name`, `displayName`, `fullyQualifiedName`, and `href` are optional. A missing optional value remains `null` or an empty collection rather than becoming an invented identity or default.

Within one submitted snapshot, the same external UUID must retain one entity type and non-conflicting name/FQN identity. Optional display labels and resource links may enrich an earlier reference but do not redefine the external entity.

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

`omitted_fields` records which source field classes were present, without carrying their values. A later restricted evidence store may preserve an encrypted raw payload under a separate retention and access policy; that is not part of these endpoints.

## Validation and failure behavior

The public admission boundary rejects:

- missing or invalid bearer authentication;
- a verified actor without an integration-facing role;
- a request tenant that differs from the verified actor tenant;
- a missing or malformed source installation identifier;
- a release label outside OpenMetadata 2.x syntax;
- a syntactically valid 2.x release without an exact verified compatibility profile;
- a non-object table or lineage body;
- missing or malformed entity UUIDs;
- conflicting reuse of one UUID for different identities;
- a lineage response whose primary entity differs from the table;
- an edge whose endpoint is not the primary entity or a declared node;
- missing required column names or types;
- duplicate flattened column paths;
- column nesting deeper than 16;
- more than 10,000 normalized columns;
- excessive reference, edge, or column-lineage collections;
- true cyclic containers or excessive generic payload nesting;
- control characters in projected text;
- non-HTTP(S) links and links containing credentials;
- negative, floating-point, boolean, or text values where an integer aggregate is required;
- `NaN`, positive infinity, and negative infinity as table versions;
- request bodies larger than 8 MiB;
- invalid UTF-8, malformed JSON, duplicate members, non-standard JSON numbers, and lone surrogates;
- receipt values that no longer match the nested projection or derived identities.

Repeated references to the same acyclic Python container are aliases, not cycles, and remain valid. Only a back-edge on the active traversal path is rejected as a cycle.

Pydantic request-shape failures return HTTP 422. Unsupported release profiles and invalid external contracts return bounded HTTP 400 responses without echoing the source payload. Authentication failures return 401, insufficient roles return 403, cross-tenant requests return 404, and oversized bodies return 413.

## Admission preview candidate

PR #99 adds:

```http
POST /integrations/openmetadata/v1/table-snapshots:admission-preview
```

The endpoint uses the same authentication, tenant, body-size, strict JSON and compatibility boundary as normalization. It returns:

- a digest of submitted source structure;
- a separate digest of the safe projection;
- a replay key and stable admission candidate identity;
- a distinct observation receipt identity;
- the safe projection;
- explicit `false` statements for raw-payload persistence, catalog mutation and omitted-value copying.

Transport validation recomputes the nested projection digest, replay key, candidate ID and receipt ID. Details and the normative structural digest vector are in `docs/integrations/openmetadata-admission-preview.md` and ADR-0002.

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

1. Merge and release PR #96 after exact-head repository/security/review gates.
2. Restack PR #99 onto that protected merge result and prove complete valid-delta inheritance from PR #97.
3. Merge and release the non-mutating admission receipt contract.
4. Add normalized external source, snapshot, observation receipt, admission candidate, projection-history and supersession tables.
5. Enforce idempotent concurrent admission by tenant, source installation, entity UUID, release profile and replay key.
6. Add restricted immutable raw-payload evidence and purpose-bound retrieval.
7. Add signed Change Event/webhook inbox, replay protection, ordering, dead-letter evidence and rollback.
8. Add credential-registry and canonical-egress based OpenMetadata API retrieval.
9. Add steward-approved outbound writes with version/ETag preconditions and operation receipts.
10. Add further entity mappings and released cross-product contracts.

See ADR-0001, ADR-0002 and issue #95 for the ownership and delivery decisions.
