# Dataset distribution semantic identifiers

## Decision

The catalog bounded context owns the meaning of a dataset distribution's identity, representation format, and access endpoint. Organization-owned Python identifiers therefore use the explicit names `distribution_id`, `distribution_format`, and `distribution_endpoint` instead of the generic one-word names `id`, `format`, and `endpoint`.

This is a semantic-specificity rule, not a casing rule. Python remains idiomatic `snake_case`; equivalent multiword camelCase or PascalCase names are valid in ecosystems where those conventions are idiomatic.

## Compatibility boundary

The existing catalog HTTP/OpenAPI/SHACL-facing distribution representation uses the keys `id`, `format`, and `endpoint`. Those keys are already consumer-visible and are therefore treated as a compatibility contract rather than silently renamed.

`DatasetDistribution` now uses Pydantic aliases to accept the historical input keys and a model serializer to emit the historical wire representation. Compatibility properties retain existing Python attribute reads/writes while organization-owned internal construction uses the qualified names. This creates an anti-corruption boundary: internal ubiquitous language is specific, while existing external consumers see no wire-schema change.

Nested `Dataset.model_dump()` output is covered explicitly because catalog list/detail/create/publish/patch endpoints serialize `Dataset` objects directly. The compatibility test proves nested distributions still serialize exactly as `{id, format, endpoint}`.

## TDD evidence

The regression-first commit `38fec1397ffbff5cc78c9630cee8ea1b726ca07d` introduced a contract test that requires the semantic model fields before production code was changed. The source repair then introduced the semantic model fields, propagated all buyer-demo constructors, and added explicit legacy wire serialization. Follow-up coverage pins legacy Python compatibility and nested dataset serialization.

Focused verification command:

```bash
PYTHONPATH=src pytest tests/test_dataset_distribution_naming_contract.py
```

Repository verification command:

```bash
PYTHONPATH=src pytest
```

## Persistence and database impact

None. `DatasetDistribution` is a Pydantic catalog contract in `sdp_core`; this change does not alter Postgres/SQLite evidence-store tables, foreign keys, indexes, constraints, ORM mappings, UPSERT paths, partitioning, locking, or read/write separation. No data migration or rollback DDL is required.

## Naming follow-up boundary

This change intentionally does not mechanically rename every one-word property in the catalog. Subsequent repairs must establish bounded-context ownership, consumer compatibility, and blast radius independently. Generic external/protocol vocabulary should remain at adapters when changing it would break consumers; organization-owned runtime vocabulary should be qualified where the semantic owner is clear.
