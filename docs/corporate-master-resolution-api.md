# Corporate-master resolution API contract

**Status:** Accepted target; no executable endpoint is claimed  
**Contract:** `sdp.corporate-master-resolution/v1`

## Responsibility

Semantic Data Portal resolves an authorized source organization label against
one tenant's governed corporate-master catalog. The caller owns source access
and authorization. The portal owns catalog snapshot identity, aliases,
stewardship state, and the final `unique` / `miss` / `tie` outcome.

## Target resource

```text
POST /api/v1/corporate-master-resolutions
```

### Request envelope

```json
{
  "contract_version": "sdp.corporate-master-resolution/v1",
  "resolution_request_id": "opaque-request-id",
  "tenant_reference": "opaque-tenant-reference",
  "source_label": "Synthetic Organization",
  "source_language": "en",
  "source_evidence_references": ["https://evidence.example.invalid/ref/1"],
  "catalog_snapshot_id": "opaque-snapshot-id"
}
```

The production identity and purpose headers remain governed by ADR 0001. The
request is bounded, rejects unknown fields, and carries references rather than
document bodies. The snapshot is explicit; the service never silently switches
to a newer catalog during one resolution.

### Result envelope

```json
{
  "contract_version": "sdp.corporate-master-resolution/v1",
  "resolution_request_id": "opaque-request-id",
  "catalog_snapshot_id": "opaque-snapshot-id",
  "resolution_method_id": "accepted-method-id",
  "resolution_method_version": "method-version",
  "outcome": "tie",
  "bound_entity_reference": null,
  "candidate_entity_references": ["opaque-entity-a", "opaque-entity-b"],
  "source_evidence_references": ["https://evidence.example.invalid/ref/1"],
  "limitations": ["multiple_catalog_entities_remain_admissible"],
  "result_digest": "sha256:hex-digest"
}
```

## Outcome invariants

| Outcome | Bound entity | Candidate references | Required caller action |
| --- | --- | --- | --- |
| `unique` | exactly one | the same one entity | Use the returned reference with its result digest. |
| `miss` | `null` | empty | Keep the source label unbound and request stewardship if needed. |
| `tie` | `null` | two or more distinct entities | Keep the source label unbound and request disambiguating evidence or stewardship. |

Candidate order is evidence, not a hidden tie-break. No numeric confidence is
part of v1: a later calibrated measure requires its own method contract and may
not change these three outcomes or authorize a binding by itself.

## Failure contract

Malformed, oversized, cross-tenant, unauthorized, stale-snapshot, unknown
method, unimplemented, or unavailable requests fail closed with a stable error
code and a customer-action message. They do not become `miss`, create an entity,
or invoke a consumer-local fallback.

## Implementation acceptance

An executable route is not accepted until a follow-up ADR identifies the
authoritative method and proves, with synthetic fixtures:

1. unique, miss, and tie recovery without an arbitrary threshold;
2. tenant and snapshot isolation;
3. alias merge/split and catalog-revision behavior;
4. exact request/result digest binding and replay behavior;
5. bounded input/output and redacted errors; and
6. consumer contract tests showing unavailable resolution remains unbound.

