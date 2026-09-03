# OpenMetadata interoperability

Semantic Data Portal owns the ContextualWisdomLab anti-corruption and admission boundary for OpenMetadata. The integration preserves external identity and provenance without making an external catalog authoritative for CWL product domains.

## Current implementation stack

| Capability | Owning PR | Status on the branch |
|---|---:|---|
| Exact OpenMetadata 2.0.1 compatibility profile | #96 | Implemented, not released |
| Table, nested Column, owner, domain, data-product, data-contract, tag, and structural references | #96 | Implemented, not released |
| Aggregate-only profile summary | #96 | Implemented, not released |
| Table and column lineage with endpoint integrity | #96 | Implemented, not released |
| Sensitive source-field omission and hostile payload bounds | #96 | Implemented, not released |
| Deterministic non-mutating admission preview | #97 | Implemented, not released |
| Cross-language structural digest golden vectors | #97 | Implemented, not released |
| Strict transport JSON for both POST routes | #97 | Implemented, not released |
| Persistent catalog admission and replay history | successor after #97 | Not implemented |
| Restricted immutable raw evidence | later successor | Not implemented |
| Change Event/webhook ingestion | later successor | Not implemented |
| Live API retrieval and controlled writeback | later successors | Not implemented |
| Additional entity profiles | issue #95 | Not implemented |

“Implemented” means source and tests exist on the PR branch. It does not mean protected `main`, an immutable package release, or full exact-head verification is complete.

## Verified release profile

```text
profile_id: openmetadata-table-lineage-2.0.1
canonical_release: 2.0.1
accepted_labels: 2.0.1, 2.0.1-release
upstream_repository: open-metadata/OpenMetadata
upstream_tag: 2.0.1-release
upstream_revision: bf621b166ec12e8c99fcb1c1443442723386fa41
```

The profile references the upstream Table and EntityLineage schemas at that exact revision. A syntactically valid label such as `2.1.0` is rejected until a distinct immutable profile, source identity, schema-drift review, positive and hostile fixtures, omission tests, and exact-head evidence exist.

## Authority boundary

```text
OpenMetadata Table and EntityLineage
    │ external UUID, FQN, version, hash, references
    ▼
Exact release-profile admission
    │ validated, bounded, privacy-limited observation
    ▼
SDP projection: truth_status = observed
    │
    ├─ deterministic admission preview and replay identity
    ├─ durable admission in a successor
    ├─ policy-filtered context event
    └─ EA and Agent consumers
```

OpenMetadata remains the authority for the external entities it hosts. Each CWL domain product remains the authority for its own business facts. Neither normalization nor admission preview publishes a catalog asset, contacts OpenMetadata, writes a database row, retains a raw payload, or grants outbound synchronization authority.

## HTTP operations

### Normalize

```http
POST /integrations/openmetadata/v1/table-snapshots:normalize
Content-Type: application/json
```

Returns a typed `OpenMetadataTableProjection` whose identity is:

```text
urn:cwl:{tenant_id}:sdp:openmetadata_table:{openmetadata_uuid}
```

Every projection includes:

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

The upstream revision identifies the contract source used to build and test the adapter. It does not prove that a submitted payload originated from that commit.

### Admission preview

```http
POST /integrations/openmetadata/v1/table-snapshots:admission-preview
Content-Type: application/json
```

Adds tenant-local `source_instance_id` and timezone-qualified `observed_at`, then returns:

- `source_snapshot_digest` over submitted Table and optional EntityLineage structures;
- `projection_digest` over the complete safe projection;
- tenant- and source-instance-scoped `replay_key`;
- deterministic receipt URN;
- explicit `accepted_for_review` status;
- explicit evidence that no raw payload was persisted and no catalog mutation occurred.

See [`openmetadata-admission-preview.md`](openmetadata-admission-preview.md) and ADR-0002 for the exact digest grammar, replay semantics, privacy boundary, and golden vectors.

## Mapped content

| OpenMetadata source | SDP projection |
|---|---|
| release label | canonical release, compatibility profile, upstream source revision |
| `id` | external entity and projection identity |
| `name`, `displayName`, `fullyQualifiedName`, `description` | safe descriptive fields |
| `version`, `updatedAt`, `updatedBy`, `sourceHash`, `sourceUrl` | source revision and provenance fields |
| `tableType`, `serviceType`, `entityStatus` | typed status fields |
| `owners`, `domains`, `dataProducts`, `dataContract` | external governed references |
| `databaseSchema`, `database`, `service` | external structural references |
| `tags[].tagFQN` | stable tag/classification FQNs |
| `columns` and `children` | ordered flattened column paths |
| table `profile` counts and size | aggregate-only profile summary |
| EntityLineage edges | validated table lineage |
| `columnsLineage` identities | source and target column identities |

Missing optional values remain unknown. The adapter does not turn unknown quality, freshness, ownership, or nullability into numeric zero or an invented value.

## Content excluded from general projections and receipts

- sample rows;
- DDL and schema definition text;
- query and SQL text;
- join samples and statistics;
- column profiles and custom metrics;
- arbitrary extension payloads;
- lineage SQL and transformation functions.

`omitted_fields` records which source field classes were present without carrying their values. Admission preview includes omitted values in the source fingerprint but never embeds the source object in the receipt.

Descriptions, labels, ownership references, classifications, fingerprints, FQNs, and lineage can still be restricted tenant metadata. The contract guarantees `omitted_source_values_copied=false`; it does not claim that every projected field is non-sensitive.

## Strict transport and semantic validation

Both POST routes reject the request before operation execution when the raw body contains:

- more than 16 MiB;
- invalid UTF-8;
- malformed JSON or decoder recursion overflow;
- duplicate object members at any level;
- NaN or infinity;
- lone Unicode surrogate code points.

The semantic boundary then rejects unsupported release profiles, malformed UUIDs, conflicting references, broken lineage endpoints, missing column names/types, duplicate column paths, excessive nesting or collection sizes, cyclic host containers, unsafe URLs, embedded URL credentials, invalid aggregate types, and control characters in projected text.

Infrastructure must also enforce body limits before application buffering. Application validation alone is not an edge-level denial-of-service control.

## Adding another release

Release support is never added by widening a regular expression. A reviewable change must provide:

1. exact upstream tag and commit;
2. immutable schema paths and digests where available;
3. representative positive fixtures;
4. malformed and hostile fixtures;
5. field-level additions/removals/type/required/enum/sensitivity review;
6. omission and serialization regressions;
7. a distinct `OpenMetadataReleaseProfile`;
8. ADR, integration guide, Gap baseline, CHANGELOG, and exact-head evidence.

Existing profiles remain immutable. A changed tag target or incompatible schema requires a new profile identity.

## Cross-product adoption

Products publish or consume released provider-neutral contracts; they do not share databases or mutable branches.

- `pg-erd-cloud` publishes physical-schema observations.
- `mhtml-etl-gateway` publishes validated schema proposals and lineage evidence.
- learning, HR, billing, psychometrics, security, and AI products retain their domain truth.
- `enterprise-architecture-core` consumes admitted SDP context for impact analysis.
- Contextual Orchestrator consumes policy-filtered context bundles; OpenMetadata content remains untrusted data.
- `context-graph-contracts` will own the released provider-neutral envelope after its foundation stack reaches protected source and an immutable version is published.

## Successor order

1. Merge and release #96 exact compatibility normalization.
2. Non-force restack and merge #97 deterministic receipt and strict transport boundary.
3. Add 3NF source, observation, snapshot, receipt, projection-revision, and supersession persistence.
4. Add restricted immutable raw evidence with tenant/purpose authorization.
5. Add signed Change Event/webhook inbox, ordering, retry, dead letter, and replay.
6. Add credential-registry and canonical-egress live retrieval.
7. Add steward-approved writeback with version/ETag preconditions and receipts.
8. Add exact profiles for additional entity types and released consumer integrations.

See ADR-0001, ADR-0002, issue #95, and `docs/product-technical-gap-baseline.md`.
