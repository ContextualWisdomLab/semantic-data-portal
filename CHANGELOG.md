# Changelog

All notable changes to Semantic Data Portal are recorded here.

## [Unreleased]

### Added

- OpenMetadata read-only anti-corruption layer for Table and EntityLineage payloads.
- Immutable `openmetadata-table-lineage-2.0.1` compatibility profile bound to the official `2.0.1-release` upstream commit `bf621b166ec12e8c99fcb1c1443442723386fa41`.
- Tenant- and source-installation-scoped `observed` table projections preserving external UUID, optional fully qualified name, finite entity version, ownership, domains, data products, data contracts, classifications, safe profile aggregates, nested columns, and table/column lineage.
- Compatibility profile ID, source installation, upstream repository, and exact upstream revision in every normalized projection.
- Authenticated `POST /integrations/openmetadata/v1/table-snapshots:normalize` endpoint with OIDC/JWKS verification, role admission, verified-tenant binding, and an 8 MiB request-body limit.
- Snapshot-wide external-reference registry that rejects contradictory UUID/type/name/FQN identities while permitting optional descriptive enrichment.
- OpenMetadata authority ADR, integration guide, research and source traceability, capability index, and product/technical Gap baseline.
- Exact OpenMetadata 2.0.1 fixtures plus compatibility, authorization, source-instance, body-limit, sparse-schema, hostile-input, and omission regression tests.

### Changed

- `2.0.1` and `2.0.1-release` resolve to one canonical `2.0.1` projection contract at the actual normalization sink.
- A syntactically valid but unverified OpenMetadata 2.x release is rejected until an exact upstream revision, schema-drift review, fixtures, and a distinct compatibility profile are added.
- Table `fullyQualifiedName` and EntityReference `name`, `displayName`, `fullyQualifiedName`, and `href` remain optional in accordance with the pinned upstream schemas.
- Projection identity now includes `source_instance_id` so independent OpenMetadata installations in one tenant cannot collide on a reused UUID.
- Request `tenant_id` is descriptive input only; the effective projection tenant is taken from the verified actor and must match the request.
- Repeated references to one acyclic Python container are treated as aliases, while a true active-path back-edge remains a rejected cycle.
- OpenMetadata routes remain in a focused application module registered by the composition root rather than expanding the already broad `api.py` surface.

### Security

- Excluded sample rows, SQL/DDL, query text, join samples, column profiles, custom metrics, extension payloads, and lineage transformation text from general catalog projections.
- Added bounds for HTTP body size, payload nesting, aggregate text, containers, columns, references, lineage edges, and column mappings.
- Rejected missing or invalid bearer authentication, insufficient integration roles, cross-tenant namespace spoofing, invalid source installation identifiers, cyclic direct-call containers, contradictory external references, broken lineage endpoints, unsafe URL schemes, embedded URL credentials, malformed UUIDs, control characters, invalid aggregate number types, non-finite entity versions, and unverified release contracts.
- Authentication and contract failures return bounded status-specific responses without echoing source payload or token-verification details.

### Fixed

- Valid OpenMetadata 2.0.1 Tables without `fullyQualifiedName` and EntityReferences without `name` are no longer rejected.
- Direct imports of the internal normalizer can no longer bypass exact compatibility-profile admission.
- Shared acyclic containers are no longer misclassified as cyclic input.
- The same external UUID can no longer acquire contradictory identities across table, structural, ownership, domain, product, lineage-node, or pipeline fields within one snapshot.
- `NaN`, positive infinity, and negative infinity can no longer enter `entity_version` provenance.
- Directly embedding the OpenMetadata router no longer bypasses chunked request-body limits.

### Not yet included

- Deterministic admission receipts and durable external metadata admission.
- Live OpenMetadata API retrieval or credential handling.
- Signed Change Event/webhook processing.
- Outbound synchronization or steward-approved conflict resolution.
- Additional OpenMetadata entity types beyond Table and EntityLineage.
