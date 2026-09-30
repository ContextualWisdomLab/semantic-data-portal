# Product and Technical Gap Baseline

## Dependency security admission

| Gap | Evidence | Owner action | Status |
| --- | --- | --- | --- |
| Shared locks retained vulnerable PyJWT 2.13.0; the graph lock also retained AnyIO 4.14.1. | PR #28 exact predecessor head `8aefd06df864e07d9a2f40de687ffcfa6082ed36`; Security Scan run `36671696821`, jobs `109784585922`, `109784585930`, and `109784586129`. | PR #81 adds RED lock-contract coverage, patches the source dependency, constrains the Python 3.12 graph resolution, and regenerates every affected hash lock. | Owner and consumer stack integrated locally; refreshed #28 exact-head Checks pending publication. |
| Downstream pypdf advisories require the first common fixed release. | PR #28 dependency-review and OSV evidence; PR #37 owns the existing `pypdf==6.16.1` delta. | Preserve PR #37 after ordinary integration of PR #81, then integrate the refreshed owner stack into PR #28. | PR #81 and #37 integrated locally; refreshed #28 exact-head Checks pending publication. |

### Acceptance evidence

- Exact-head Checks are authoritative; skipped, queued, or pending jobs are not treated as passing.
- The owner repair is accepted only after lock-contract tests, hash-required installation of all four locks, and the full repository test suite pass on the repaired head.
- PR #37 and PR #28 remain Draft until their refreshed exact heads complete required Checks; no failed PR is closed to manufacture zero open work.
- Local owner evidence on 2026-09-30: dependency lock-contract tests passed; Python 3.12 hash-required dry-run installation passed for runtime, development, test, and graph locks; the repository test suite exited successfully with eight graph tests skipped by their documented optional-runtime guard.
- A warnings-as-errors diagnostic also exposed pre-existing Pydantic field-shadowing, Starlette TestClient transition, FastAPI lifespan, AnyIO alias, and short HMAC fixture warnings. These are preserved as a separate source/test debt lane rather than hidden or suppressed in the dependency security repair.
- PR #37 integration evidence: the pypdf lock contract first failed because the newly inherited graph lock omitted `pypdf==6.16.1`; regenerating that lock from the merged source graph made the focused contracts, Python 3.12 hash-required graph installation, and full repository suite pass.
- PR #28 integration evidence: focused lock contracts passed, all four Python 3.12 hash-required install plans passed, the complete ontology suite passed with eight documented optional graph tests skipped, and `sdp.demo_smoke` reported `ready: true`. The PR remains Draft pending hosted exact-head Checks.
