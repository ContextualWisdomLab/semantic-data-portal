# OpenMetadata admission preview receipts

The admission-preview endpoint turns a verified OpenMetadata Table snapshot into replay-safe evidence without writing a catalog record or storing the source payload.

```http
POST /integrations/openmetadata/v1/table-snapshots:admission-preview
Content-Type: application/json
```

## Request

```json
{
  "tenant_id": "tenant_acme",
  "source_instance_id": "metadata_prod",
  "source_release": "2.0.1-release",
  "observed_at": "2026-09-03T12:00:00Z",
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
  "lineage": null
}
```

`source_instance_id` is the tenant-local identity of the OpenMetadata installation that supplied the candidate. It is not an OpenMetadata entity UUID and it must not contain a hostname, token, DSN, or credential.

`observed_at` must include a timezone. The response normalizes it to fixed-width UTC. It does not alter candidate replay identity, but it does identify the individual observation receipt.

## Response

```json
{
  "receipt_contract_version": "1.0.0",
  "digest_profile_id": "cwl-json-structural-sha256-v1",
  "admission_candidate_id": "urn:cwl:tenant_acme:sdp:openmetadata_admission_candidate:<replay-key-hex>",
  "receipt_id": "urn:cwl:tenant_acme:sdp:openmetadata_admission_preview:<observation-digest-hex>",
  "admission_status": "accepted_for_review",
  "tenant_id": "tenant_acme",
  "source_instance_id": "metadata_prod",
  "source_authority": "openmetadata",
  "source_release": "2.0.1",
  "compatibility_profile_id": "openmetadata-table-lineage-2.0.1",
  "upstream_repository": "open-metadata/OpenMetadata",
  "upstream_revision": "bf621b166ec12e8c99fcb1c1443442723386fa41",
  "observed_at": "2026-09-03T12:00:00Z",
  "external_entity_id": "11111111-1111-4111-8111-111111111111",
  "source_snapshot_digest": "sha256:<hex>",
  "projection_digest": "sha256:<hex>",
  "replay_key": "sha256:<hex>",
  "omitted_fields": [],
  "raw_payload_persisted": false,
  "catalog_mutation_performed": false,
  "omitted_source_values_copied": false,
  "projection": {}
}
```

The response example abbreviates the nested projection. The OpenAPI response schema exposes the complete `OpenMetadataTableProjection`.

## Status meaning

`accepted_for_review` means:

- strict transport JSON was unambiguous;
- the declared release matched an exact verified compatibility profile;
- the Table and optional EntityLineage payload passed the anti-corruption contract;
- a safe projection, admission candidate, and observation receipt could be produced.

It does not mean:

- the raw payload was retained;
- a catalog row was inserted;
- a catalog asset was published;
- a steward approved ownership, glossary, classification, quality, or lineage;
- OpenMetadata was contacted;
- payload origin was cryptographically attested;
- any value became authoritative CWL domain truth.

## Identity and digest roles

### `source_snapshot_digest`

Covers the submitted `table` and `lineage` structures. Values excluded from the safe projection still affect this digest. This allows two source observations to be distinguished without putting their omitted values into the receipt.

### `projection_digest`

Covers the complete safe projection after release-profile admission and normalization. It changes when the admitted mapping or projection contract changes.

### `replay_key` and `admission_candidate_id`

The replay key covers the receipt version, digest profile, tenant, source instance, source authority, compatibility profile, external entity UUID, source digest, and projection digest. It is the idempotency input for the future durable admission store.

`admission_candidate_id` is a tenant-scoped URN derived directly from that replay key. A repeated observation of the same source candidate retains this identity.

### `receipt_id`

The receipt ID identifies one observation event. It is derived from:

```text
receipt contract version
+ admission candidate ID
+ observed_at in fixed-width UTC
```

The timestamp representation is:

```text
YYYY-MM-DDTHH:MM:SS.ffffffZ
```

An exact retry with the same normalized instant preserves `receipt_id`. The same candidate observed later preserves its replay key and candidate ID but receives a different receipt ID. Equivalent instants expressed with different offsets, such as `2026-09-03T12:00:00Z` and `2026-09-03T21:00:00+09:00`, produce the same receipt identity.

## Structural digest profile

`cwl-json-structural-sha256-v1` is a declared CWL profile, not RFC 8785 JCS.

It preserves:

- `null`, Boolean, integer, number, and string types;
- signed 64-bit integer text;
- exact IEEE-754 binary64 bits, including signed zero;
- strict UTF-8 string bytes and byte lengths;
- array order;
- object keys sorted by UTF-8 bytes;
- object and array member counts.

It rejects:

- integers outside signed 64-bit range;
- NaN and infinity;
- strings with lone surrogate code points;
- non-string object keys;
- tuples, sets, and custom host-language containers;
- cyclic containers;
- nesting deeper than 64.

The golden byte vector in `tests/test_openmetadata_structural_digest.py` is normative for this implementation. Rust and TypeScript consumers must pass that vector before their outputs are accepted as equivalent.

## Strict HTTP JSON

Both the normalization and admission-preview endpoints reject the request before the operation runs when the raw body contains:

- more than 16 MiB;
- invalid UTF-8;
- malformed JSON;
- decoder recursion overflow;
- duplicate member names at any nesting level;
- NaN or infinity;
- lone Unicode surrogate code points.

This preserves typed FastAPI/OpenAPI request models while avoiding last-key-wins ambiguity. Edge and reverse-proxy body limits remain required because application validation occurs after the server has received the body.

## Privacy and authorization

The receipt carries the safe projection, which can still contain descriptions, labels, ownership references, and classifications. `omitted_source_values_copied=false` is deliberately narrower than claiming that every projected field is non-sensitive.

Treat these as restricted tenant metadata:

- `source_snapshot_digest` and `projection_digest`;
- replay key and admission candidate identity;
- source installation identity;
- external entity UUID and FQN;
- ownership and classification references;
- the complete projection and lineage.

The current endpoint is a contract slice, not the final production authorization surface. Durable admission must apply verified Keyverse tenant/actor/purpose context, database-level tenant enforcement, audit evidence, and purpose-bound response selection.

## Retry and re-observation examples

An exact request retry preserves every identity:

```text
source instance: metadata_prod
source payload: unchanged
observed_at: 2026-09-03T12:00:00Z
```

A later observation of the same candidate behaves differently:

```text
source instance: metadata_prod
source payload: unchanged
observed_at: 2026-09-03T12:05:00Z
```

The two observations share:

- `source_snapshot_digest`;
- `projection_digest`;
- `replay_key`;
- `admission_candidate_id`.

They have different:

- `observed_at`;
- `receipt_id`.

Changing `source_instance_id`, any submitted source value, the compatibility profile, or the safe projection changes admission candidate identity.

## Durable-admission handoff

A future persistence command should consume the typed receipt and the separately protected source evidence reference. It must not recompute an identity from a different serialization rule.

Minimum future records:

```text
external_metadata_source
external_observation_receipt
external_snapshot_record
metadata_admission_candidate
metadata_projection_revision
metadata_supersession_record
```

The store needs two uniqueness boundaries:

```text
candidate uniqueness
= tenant + source instance + receipt contract version + replay key

observation receipt uniqueness
= tenant + source instance + receipt contract version + receipt ID
```

Concurrent submissions of one replay key must result in one admitted projection revision. Distinct `receipt_id` values remain separately auditable observation events and must not overwrite one another.

See ADR-0002 and `docs/product-technical-gap-baseline.md` for the exact decision and successor gates.
