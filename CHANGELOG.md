# Changelog

All notable changes to Semantic Data Portal are recorded here.

## [Unreleased]

### Added

- OpenMetadata read-only anti-corruption layer for Table and EntityLineage payloads.
- Immutable `openmetadata-table-lineage-2.0.1` compatibility profile bound to the official `2.0.1-release` upstream commit `bf621b166ec12e8c99fcb1c1443442723386fa41`.
- Tenant-scoped `observed` table projections preserving external UUID, fully qualified name, entity version, ownership, domains, data products, data contracts, classifications, safe profile aggregates, nested columns, and table/column lineage.
- Compatibility profile ID, upstream repository, and exact upstream revision in every normalized projection.
- Typed `POST /integrations/openmetadata/v1/table-snapshots:normalize` endpoint.
- OpenMetadata authority ADR, integration guide, source traceability, and product/technical Gap baseline.
- Exact OpenMetadata 2.0.1 fixtures, compatibility-profile tests, and hostile-input regression tests.

### Changed

- `2.0.1` and `2.0.1-release` now resolve to one canonical `2.0.1` projection contract.
- A syntactically valid but unverified OpenMetadata 2.x release is rejected until an exact upstream revision, schema-drift review, fixtures, and a distinct compatibility profile are added.

### Security

- Excluded sample rows, SQL/DDL, query text, join samples, column profiles, custom metrics, extension payloads, and lineage transformation text from general catalog projections.
- Added bounds for payload nesting, aggregate text, containers, columns, references, lineage edges, and column mappings.
- Rejected cyclic direct-call containers, conflicting external references, broken lineage endpoints, unsafe URL schemes, embedded URL credentials, malformed UUIDs, control characters, invalid aggregate number types, and unverified release contracts.

### Not yet included

- Deterministic admission receipts and durable external metadata admission.
- Live OpenMetadata API retrieval or credential handling.
- Signed Change Event/webhook processing.
- Outbound synchronization or steward-approved conflict resolution.
- Additional OpenMetadata entity types beyond Table and EntityLineage.
