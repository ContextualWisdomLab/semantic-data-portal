# Changelog

All notable changes to Semantic Data Portal are recorded here.

## [Unreleased]

### Added

- OpenMetadata 2.x read-only anti-corruption layer for Table and EntityLineage payloads.
- Tenant-scoped `observed` table projections preserving external UUID, fully qualified name, entity version, ownership, domains, data products, data contracts, classifications, safe profile aggregates, nested columns, and table/column lineage.
- Typed `POST /integrations/openmetadata/v1/table-snapshots:normalize` endpoint.
- OpenMetadata authority ADR, integration guide, source traceability, and product/technical Gap baseline.
- Exact OpenMetadata 2.0.1 fixtures and hostile-input regression tests.

### Security

- Excluded sample rows, SQL/DDL, query text, join samples, column profiles, custom metrics, extension payloads, and lineage transformation text from general catalog projections.
- Added bounds for payload nesting, aggregate text, containers, columns, references, lineage edges, and column mappings.
- Rejected cyclic direct-call containers, conflicting external references, broken lineage endpoints, unsafe URL schemes, embedded URL credentials, malformed UUIDs, control characters, and invalid aggregate number types.

### Not yet included

- Durable external metadata admission and replay receipts.
- Live OpenMetadata API retrieval or credential handling.
- Signed Change Event/webhook processing.
- Outbound synchronization or steward-approved conflict resolution.
- Additional OpenMetadata entity types beyond Table and EntityLineage.
