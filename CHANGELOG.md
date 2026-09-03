# Changelog

All notable changes to Semantic Data Portal are recorded here.

## [Unreleased]

### Added

- OpenMetadata read-only anti-corruption layer for Table and EntityLineage payloads.
- Immutable `openmetadata-table-lineage-2.0.1` compatibility profile bound to the official `2.0.1-release` upstream commit `bf621b166ec12e8c99fcb1c1443442723386fa41`.
- Tenant-scoped `observed` table projections preserving external UUID, fully qualified name, entity version, ownership, domains, data products, data contracts, classifications, safe profile aggregates, nested columns, and table/column lineage.
- Compatibility profile ID, upstream repository, and exact upstream revision in every normalized projection.
- Typed `POST /integrations/openmetadata/v1/table-snapshots:normalize` endpoint.
- Deterministic `POST /integrations/openmetadata/v1/table-snapshots:admission-preview` endpoint that returns source-snapshot, safe-projection, and replay digests without persistence or publication.
- Versioned `cwl-json-structural-sha256-v1` digest profile with normative cross-language golden bytes, signed-64-bit integers, exact IEEE-754 binary64 identity, strict UTF-8 strings, array order, and UTF-8 object-key ordering.
- Strict transport JSON admission for both OpenMetadata endpoints, including duplicate-member, non-standard-number, invalid-Unicode, oversized-body, malformed-JSON, and decoder-recursion rejection.
- OpenMetadata authority and admission-receipt ADRs, integration guides, source traceability, and product/technical Gap baseline.
- Exact OpenMetadata 2.0.1 fixtures, compatibility-profile tests, deterministic replay tests, digest golden vectors, and hostile-input regressions.

### Changed

- `2.0.1` and `2.0.1-release` resolve to one canonical `2.0.1` projection and receipt contract.
- A syntactically valid but unverified OpenMetadata 2.x release is rejected until an exact upstream revision, schema-drift review, fixtures, and a distinct compatibility profile are added.
- Admission replay identity is scoped by tenant, source installation, compatibility profile, external entity, source snapshot, and safe projection; observation time is retained as evidence but does not create a duplicate candidate.
- General receipts state the narrower, verifiable guarantee `omitted_source_values_copied = false` rather than claiming that every projected description, label, owner, classification, fingerprint, or lineage field is non-sensitive.

### Security

- Excluded sample rows, SQL/DDL, query text, join samples, column profiles, custom metrics, extension payloads, and lineage transformation text from general catalog projections and admission receipts.
- Added bounds for request bytes, payload nesting, aggregate text, containers, columns, references, lineage edges, and column mappings.
- Rejected cyclic direct-call containers, conflicting external references, broken lineage endpoints, unsafe URL schemes, embedded URL credentials, malformed UUIDs, control characters, invalid aggregate number types, unverified release contracts, duplicate JSON members, NaN/infinity, lone Unicode surrogates, and non-reproducible host-language containers.
- Classified source and projection fingerprints as restricted tenant metadata rather than treating hashes as automatically non-sensitive.

### Not yet included

- Durable 3NF external source, observation, snapshot, receipt, projection-revision, and supersession storage.
- Restricted immutable raw-payload evidence, encryption, retention, legal hold, and purpose-bound retrieval.
- Live OpenMetadata API retrieval or credential handling.
- Signed Change Event/webhook processing.
- Outbound synchronization or steward-approved conflict resolution.
- Released Rust and TypeScript implementations of the structural digest profile.
- Additional OpenMetadata entity types beyond Table and EntityLineage.
