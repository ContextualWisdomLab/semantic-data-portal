# SQL read-only function admission boundary

## Decision

`validate_sql_query()` treats a user-supplied PostgreSQL function call as executable authority, not as inert SELECT syntax. The query gate therefore uses a **positive allowlist** for reviewed read-only aggregate functions (`avg`, `count`, `max`, `min`, and `sum`) and rejects every other function call with `unsafe_function_call`. Schema-qualified function calls are rejected even when their final identifier resembles an allowlisted function, because qualification can select a different implementation.

`validate_sql_query()`는 사용자가 입력한 PostgreSQL 함수 호출을 단순한 SELECT 구문이 아니라 실행 권한으로 취급한다. 따라서 검토된 읽기 전용 집계 함수만 허용하고, 스키마로 한정된 함수까지 포함한 나머지 호출은 닫힌 상태로 거부한다.

This replaces the earlier unsafe-function denylist. The denylist could block known families such as `pg_sleep` or `dblink` but could not establish a closed read-only boundary: `nextval`, `setval`, large-object functions, advisory locks, newly installed extensions, and future side-effecting functions remained open unless every name was anticipated.

SELECT 목록 자체도 동일한 positive allowlist를 사용한다. 현재 계약은 컬럼 식별자, `*`, 검토된 집계 함수와 선택적 `AS` 별칭만 허용한다. 연산자, cast, scalar subquery, window clause, array constructor는 `unsafe_select_expression`으로 거부한다.

## 보안 근거 (Security rationale)

PostgreSQL classifies functions as `IMMUTABLE`, `STABLE`, or `VOLATILE`. A `VOLATILE` function may modify the database, and functions with side effects must be classified `VOLATILE`. PostgreSQL also documents `setval()` as an example of a side-effecting function. Consequently, the lexical fact that a statement begins with `SELECT` is not proof that executing it is read-only.

The application gate deliberately does not attempt to reconstruct PostgreSQL's full catalog, extension state, overload resolution, or volatility semantics from user text. Instead, it admits only the small function set required by the product's governed analytic contract. New function capability must be added test-first after reviewing its PostgreSQL semantics and operational resource bounds.

애플리케이션은 사용자 문자열만으로 PostgreSQL catalog, extension, overload resolution, volatility 의미를 재구성하지 않는다. 제품에 필요한 최소 분석 문법만 허용하며, 새 기능은 PostgreSQL 의미와 자원 한계를 검토한 실패 테스트부터 추가한다.

## 테스트 우선 증거 (Test-first evidence)

The RED head `12725aad0a2253de3d146c5e34c9409744c5f3f2` added `tests/test_sql_readonly_function_gate.py` before production changed. Exact-head Tests run `31184015453` failed eight adversarial cases because `nextval`, `setval`, `lo_creat`, `lo_get`, `lo_lseek`, `pg_advisory_lock`, a schema-qualified advisory-lock call, and an unknown extension function passed with no `unsafe_function_call` warning.

GREEN head `8d6facbcd3a05c8a21fbf4453408e732dff3a8cd` replaced the open-ended unsafe-name list with positive function admission. The same regression preserves ordinary aggregate analytics through positive cases for `count`, `sum`, `avg`, `min`, and `max`.

후속 regression은 함수 이름뿐 아니라 SELECT expression의 형태도 검증한다. 허용된 집계와 식별자는 유지하면서 연산자, cast, subquery, window, array 형태가 실패하는지 확인한다.

## 계층형 집행과 한계 (Layered enforcement and limitations)

This lexical gate is an application safety boundary, not a substitute for database authority. When a real PostgreSQL execution backend is enabled, the connection role should still use least privilege, an explicit read-only transaction where compatible with the execution design, bounded statement timeouts, and no unnecessary sequence, large-object, extension, file, or administrative privileges. PostgreSQL documents transaction access mode separately; a read-only transaction prevents ordinary non-temporary-table writes, while product authorization and function admission remain independent controls.

The current product execution path is validation-only rather than mock-backed. A dry run returns `VALIDATED` after policy and SQL validation. A non-dry-run request returns `UNAVAILABLE` when no execution backend is configured; it never returns synthetic rows. Therefore this change proves fail-closed application admission semantics, not production PostgreSQL privilege isolation or end-to-end database non-interference. Those require a live restricted-role integration test before a real query engine is enabled.

현재 제품 경로는 mock 결과를 만들지 않는 validation-only 경계다. dry run은 정책과 SQL 검증 후 `VALIDATED`를 반환하고, 실행 backend가 없는 실제 실행 요청은 합성 행 없이 `UNAVAILABLE`을 반환한다. 실제 PostgreSQL 권한 격리와 비간섭은 제한된 역할을 사용하는 live integration test가 추가되어야 입증된다.

## 롤백 (Rollback)

Do not roll back to prefix/denylist function filtering. If a required analytic function is rejected, add a failing compatibility regression, review the exact function semantics and resource behavior, extend the smallest positive allowlist, and rerun the complete exact-head security and coverage gates. If safe semantics cannot be established, keep the function unavailable.

prefix 또는 denylist 방식으로 되돌리지 않는다. 필요한 분석 표현식이 거부되면 호환성 실패 테스트를 먼저 추가하고, 정확한 의미와 자원 동작을 검토한 뒤 가장 작은 allowlist만 확장한다.

## 참고문헌 (References)

PostgreSQL Global Development Group. (2026). *Function volatility categories*. In *PostgreSQL 18 documentation*. https://www.postgresql.org/docs/18/xfunc-volatility.html

PostgreSQL Global Development Group. (2026). *CREATE FUNCTION*. In *PostgreSQL 18 documentation*. https://www.postgresql.org/docs/18/sql-createfunction.html

PostgreSQL Global Development Group. (2026). *SET TRANSACTION*. In *PostgreSQL 18 documentation*. https://www.postgresql.org/docs/18/sql-set-transaction.html
