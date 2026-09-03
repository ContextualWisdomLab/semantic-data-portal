# ADR-0002: OpenMetadata admission previews use structural digests and scoped replay identity

- **Status:** Proposed
- **Date:** 2026-09-03
- **Decision owner:** Semantic Data Portal
- **Related issue:** #95
- **Parent decision:** ADR-0001
- **Implementation PR:** #97

## Context

ADR-0001 establishes an exact-version, read-only OpenMetadata anti-corruption layer. Its normalized Table projection is safe to inspect, but a durable admission system still needs a deterministic identity for four different facts:

1. which OpenMetadata installation supplied the candidate;
2. which submitted Table and optional EntityLineage values were observed;
3. which safe SDP projection was derived from those values;
4. whether a retried operation represents the same admission candidate.

Hashing `json.dumps()` output is not a cross-language contract. Python, JavaScript, and Rust can serialize floating-point values and object keys differently. Hashing only the safe projection would also miss changes to source fields deliberately omitted from that projection. Embedding the original payload in a general receipt would copy sample rows, SQL, DDL, extensions, and transformation text across a broader access boundary.

Transport parsing creates another ambiguity. Standard JSON object member names are expected to be unique, but common decoders silently keep the last duplicate. Python's decoder also accepts `NaN` and infinity by default. A receipt created after last-key-wins parsing would not prove that every producer and consumer interpreted the same request.

## Decision

Semantic Data Portal provides a deterministic, non-mutating admission preview before any database admission.

```text
POST /integrations/openmetadata/v1/table-snapshots:admission-preview
```

The operation:

1. validates strict UTF-8 JSON transport;
2. rejects duplicate object member names, NaN, infinity, lone Unicode surrogates, oversized request bodies, and decoder recursion failure;
3. validates tenant, source installation, timezone-qualified observation time, and the exact OpenMetadata compatibility profile;
4. computes a digest of the submitted Table and optional EntityLineage structure, including values omitted from the safe projection;
5. invokes the verified normalizer from ADR-0001;
6. computes a separate digest of the safe projection;
7. derives an installation- and tenant-scoped replay key;
8. returns a typed receipt and projection without persistence, publication, or outbound I/O.

### Receipt semantics

```text
receipt_contract_version = 1.0.0
digest_profile_id = cwl-json-structural-sha256-v1
admission_status = accepted_for_review
raw_payload_persisted = false
catalog_mutation_performed = false
omitted_source_values_copied = false
```

`accepted_for_review` means that the candidate passed compatibility and shape validation. It does not mean that a catalog asset was admitted, published, certified, or promoted to authoritative truth.

### Three identities

`source_snapshot_digest` covers this structural value:

```json
{
  "table": "the submitted Table object",
  "lineage": "the submitted EntityLineage object or null"
}
```

It includes omitted source values in the digest but never embeds them in the receipt. Because a fingerprint of restricted source content can itself be sensitive metadata, durable storage and retrieval must remain tenant- and purpose-scoped.

`projection_digest` covers the complete JSON-mode `OpenMetadataTableProjection`, including the compatibility profile and upstream revision.

`replay_key` covers:

```text
receipt contract version
+ digest profile ID
+ tenant ID
+ source instance ID
+ source authority
+ compatibility profile ID
+ external entity ID
+ source snapshot digest
+ projection digest
```

`receipt_id` is a tenant-scoped URN whose suffix is the replay-key SHA-256 value.

`observed_at` is not part of replay identity. Two deliveries of the same source candidate at different observation times are retries of one candidate and therefore produce the same replay key and receipt ID, while retaining their respective observation timestamps. Durable persistence may record repeated observation events separately while admitting the normalized revision once.

## Structural digest profile

`cwl-json-structural-sha256-v1` is not RFC 8785 JCS and must not be described as such. It is a CWL-defined type-preserving structural encoding that is straightforward to reproduce in Rust, TypeScript, and Python.

### Scalar encoding

| JSON value | Encoding |
|---|---|
| `null` | `n` |
| `true` | `b1` |
| `false` | `b0` |
| signed 64-bit integer | `i` + base-10 integer + `;` |
| finite binary64 number | `f` + 16 lowercase hexadecimal IEEE-754 big-endian bytes + `;` |
| string | `s` + UTF-8 byte length + `:` + strict UTF-8 bytes |

Booleans are encoded before integer handling because Python booleans are integer subclasses. Integers outside the signed 64-bit range, non-finite numbers, lone surrogate code points, tuples, sets, custom container types, and non-string object keys are rejected.

### Container encoding

| JSON value | Encoding |
|---|---|
| array | `a` + element count + `[` + encoded elements in source order + `]` |
| object | `o` + member count + `{` + encoded key/value pairs + `}` |

Object keys are sorted by their strict UTF-8 byte sequence. Repeated references to one non-cyclic host object are allowed and encode as repeated JSON values. Active recursion cycles and nesting deeper than 64 are rejected.

The SHA-256 identifier is the lowercase digest of those bytes with a `sha256:` prefix. The exact golden vector in `tests/test_openmetadata_structural_digest.py` is part of the contract. Changing any tag, ordering rule, number representation, bound, or error behavior requires a new digest profile ID; existing receipts are never reinterpreted.

## Strict transport JSON

Both OpenMetadata POST routes apply the same pre-operation transport check to the cached request body while preserving their typed Pydantic OpenAPI models.

The check rejects:

- more than 16 MiB of request bytes;
- non-UTF-8 bytes;
- malformed JSON;
- decoder recursion overflow;
- repeated member names at any nesting level;
- `NaN`, `Infinity`, and `-Infinity`;
- strings or keys containing lone UTF-16 surrogate code points.

The later semantic payload limits remain in force. The 16 MiB transport bound does not replace reverse-proxy, ASGI server, or edge request-size enforcement because the application receives the body before validating it.

## Alternatives considered

### Hash Python `json.dumps(sort_keys=True)` output

Rejected. It is deterministic inside one constrained Python implementation but does not define the same floating-point and key-order behavior for Rust and JavaScript consumers.

### Adopt RFC 8785 JCS immediately

Rejected for this slice. JCS is a valid future option, but correct ECMAScript number serialization and UTF-16 key ordering require a fully conforming implementation and cross-language conformance suite. Mislabeling a partial implementation as JCS would be worse than declaring a narrow CWL profile. A later released `context-graph-contracts` profile may adopt JCS under a new contract and migration rule.

### Hash only the normalized projection

Rejected. A change confined to omitted source fields would become invisible, so two different source observations could share one replay identity.

### Include the raw payload in the receipt

Rejected. General receipts would copy data samples, SQL, DDL, extension content, or other restricted values. Raw evidence belongs in a separately authorized immutable evidence store.

### Include `observed_at` in replay identity

Rejected. Network retries or repeated observation of an unchanged candidate would generate duplicate admission identities and make idempotent persistence harder.

### Trust the framework's default JSON parser

Rejected. Last-key-wins parsing, non-standard numbers, and Unicode-scalar ambiguity are incompatible with reproducible cross-product evidence.

## Consequences

### Benefits

- Python, Rust, and TypeScript implementations can reproduce one published golden vector.
- Source changes that do not cross the safe projection boundary still change source identity.
- Safe projection changes remain separately diagnosable.
- Retries are scoped to tenant and source installation.
- Receipts contain no raw payload and perform no catalog mutation.
- Durable admission can use the replay key as an idempotency input without inventing a new identity scheme.
- Ambiguous transport JSON is rejected before normalization.

### Costs and limitations

- The digest profile is CWL-specific until released through `context-graph-contracts` or replaced by a versioned standard profile.
- Signed 64-bit integer and binary64 constraints are stricter than the abstract JSON number grammar.
- A source digest can be sensitive even though it is irreversible in ordinary operation.
- Application-level body-size validation does not prevent the edge from buffering an oversized request; infrastructure controls remain required.
- The preview is not durable evidence and does not attest to how the caller obtained the payload.
- Duplicate observations at different times need separate observation records in the future store even though they share one admission identity.

## Required successor decisions

1. 3NF source installation, observation, snapshot, admission receipt, projection revision, and supersession records.
2. Uniqueness and locking rules for replay under concurrent writers.
3. Restricted raw-payload object storage, encryption, retention, legal hold, and purpose-bound retrieval.
4. Released Rust and TypeScript implementations of the same digest profile and golden vectors.
5. Change Event/webhook signature and source-origin evidence.
6. If a standard canonicalization profile is adopted later, explicit dual-digest migration without rewriting prior receipts.

## Verification

The implementation must prove:

- RED-before-GREEN history for the admission-preview API;
- exact digest golden bytes and SHA-256 result;
- source-object insertion order does not affect identity;
- release aliases yield one canonical receipt;
- source-instance changes alter replay identity but not source/projection digests;
- observation-time changes preserve replay identity;
- omitted source changes alter source digest without entering the receipt;
- signed zero remains distinguishable by binary64 bits;
- invalid number, integer, key, Unicode, container, cycle, depth, body, and duplicate-member cases fail closed;
- new production statement and branch coverage 100%;
- public API docstrings 100%;
- no database, external request, credential, publication, or catalog mutation in this slice.
