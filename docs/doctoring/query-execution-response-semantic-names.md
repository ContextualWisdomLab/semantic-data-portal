# Query execution response semantic names

## Decision

`QueryExecutionResponse` is owned by the governed-query bounded context in `sdp_core`. Its historical HTTP response keys are already consumed as `status`, `execution`, and `warnings`, but those single-word names are underspecified inside ContextualWisdomLab-owned Python code.

The internal authoritative vocabulary is therefore:

- `status` → `query_status`
- `execution` → `execution_metadata`
- `warnings` → `query_warnings`

The existing wire contract remains unchanged. Pydantic aliases keep `status`, `execution`, and `warnings` as input/output keys at the HTTP compatibility boundary, while explicit compatibility properties preserve legacy Python reads and writes. New organization-owned callers use the semantic names.

## Bounded-context rationale

The response represents one governed dataset-query execution, not an arbitrary workflow or generic execution. `query_status` identifies the query lifecycle outcome, `execution_metadata` carries execution-engine evidence such as elapsed time/source/bytes scanned, and `query_warnings` carries query-policy or query-safety warnings. These names match the existing `request_id`, `query_id`, `policy_decision_id`, and `row_count` ubiquitous language instead of inventing a repository prefix.

`src/sdp/orchestrator.py` now propagates that vocabulary through its response builder. The local generic helper names `response` and `audit` were replaced by `build_query_response` and `record_query_audit`; audit helper arguments were likewise qualified where their semantic owner is clear.

## Compatibility contract

No HTTP key is removed or renamed. Both legacy and semantic constructor names are accepted, and `model_dump(..., by_alias=True)` emits the historical `status`, `execution`, and `warnings` keys. Compatibility properties keep `response.status`, `response.execution`, and `response.warnings` available for existing Python consumers while the Pydantic model fields themselves remain semantically specific.

This slice does not change database tables, columns, indexes, constraints, migrations, UPSERT paths, partitioning, locking, or read/write separation.

## TDD / verification

The RED regression was committed first in `tests/test_query_execution_response_naming_contract.py` at `9d16b1a267ebc0732936b39405acbb0cce1c8a88`. It requires semantic authoritative fields and verifies legacy wire/Python compatibility. Production repairs followed in ordinary non-force history.

Fresh exact-head repository checks remain authoritative; predecessor check evidence is not transferable. The PR remains draft until all required checks are terminal-success, valid review findings and threads are resolved, and a current qualifying independent non-author approval covers the final unchanged head.
