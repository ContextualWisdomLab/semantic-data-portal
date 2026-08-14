# SQL read-only function admission boundary

## Decision

`validate_sql_query()` treats a user-supplied PostgreSQL function call as executable authority, not as inert SELECT syntax. The query gate therefore uses a **positive allowlist** for reviewed read-only aggregate functions (`avg`, `count`, `max`, `min`, and `sum`) and rejects every other function call with `unsafe_function_call`. Schema-qualified function calls are rejected even when their final identifier resembles an allowlisted function, because qualification can select a different implementation.

This replaces the earlier unsafe-function denylist. The denylist could block known families such as `pg_sleep` or `dblink` but could not establish a closed read-only boundary: `nextval`, `setval`, large-object functions, advisory locks, newly installed extensions, and future side-effecting functions remained open unless every name was anticipated.

## Security rationale

PostgreSQL classifies functions as `IMMUTABLE`, `STABLE`, or `VOLATILE`. A `VOLATILE` function may modify the database, and functions with side effects must be classified `VOLATILE`. PostgreSQL also documents `setval()` as an example of a side-effecting function. Consequently, the lexical fact that a statement begins with `SELECT` is not proof that executing it is read-only.

The application gate deliberately does not attempt to reconstruct PostgreSQL's full catalog, extension state, overload resolution, or volatility semantics from user text. Instead, it admits only the small function set required by the product's governed analytic contract. New function capability must be added test-first after reviewing its PostgreSQL semantics and operational resource bounds.

## Test-first evidence

The RED head `12725aad0a2253de3d146c5e34c9409744c5f3f2` added `tests/test_sql_readonly_function_gate.py` before production changed. Exact-head Tests run `31184015453` failed eight adversarial cases because `nextval`, `setval`, `lo_creat`, `lo_get`, `lo_lseek`, `pg_advisory_lock`, a schema-qualified advisory-lock call, and an unknown extension function passed with no `unsafe_function_call` warning.

GREEN head `8d6facbcd3a05c8a21fbf4453408e732dff3a8cd` replaced the open-ended unsafe-name list with positive function admission. The same regression preserves ordinary aggregate analytics through positive cases for `count`, `sum`, `avg`, `min`, and `max`.

## Layered enforcement and limitations

This lexical gate is an application safety boundary, not a substitute for database authority. When a real PostgreSQL execution backend is enabled, the connection role should still use least privilege, an explicit read-only transaction where compatible with the execution design, bounded statement timeouts, and no unnecessary sequence, large-object, extension, file, or administrative privileges. PostgreSQL documents transaction access mode separately; a read-only transaction prevents ordinary non-temporary-table writes, while product authorization and function admission remain independent controls.

The current product execution path remains mock-backed. Therefore this change proves fail-closed application admission semantics, not production PostgreSQL privilege isolation or end-to-end database non-interference. Those require a live restricted-role integration test before a real query engine is enabled.

## Rollback

Do not roll back to prefix/denylist function filtering. If a required analytic function is rejected, add a failing compatibility regression, review the exact function semantics and resource behavior, extend the smallest positive allowlist, and rerun the complete exact-head security and coverage gates. If safe semantics cannot be established, keep the function unavailable.

## References

PostgreSQL Global Development Group. (2026). *Function volatility categories*. In *PostgreSQL 18 documentation*. https://www.postgresql.org/docs/18/xfunc-volatility.html

PostgreSQL Global Development Group. (2026). *CREATE FUNCTION*. In *PostgreSQL 18 documentation*. https://www.postgresql.org/docs/18/sql-createfunction.html

PostgreSQL Global Development Group. (2026). *SET TRANSACTION*. In *PostgreSQL 18 documentation*. https://www.postgresql.org/docs/18/sql-set-transaction.html
