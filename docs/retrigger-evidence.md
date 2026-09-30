## Review Re-run

- Added a no-op documentation update at 2026-06-29 to retrigger validation runs against the latest head after resolving coverage evidence blockers.
- Added a second no-op validation trigger on 2026-06-29 (retry) to force a fresh pull_request_target OpenCode evaluation for head `c22707e87efbb49978417f282921cc98588c4320`.
- Added OpenCode workflow heredoc-repair + parser stabilization commit `e981dca` on 2026-06-29.
- Added this trace update to align implementation matrix with branch head `e981dca`; current OpenCode workflow status is expected to clear stale run comment linkage after synchronized completion.
- Added a follow-up retrigger marker on 2026-06-29 at 21:32:30 local time to force a single fresh pull_request_target OpenCode run for branch head 1ea432de350594e0ae9ca2c3b6c849c2ae215cff.
- On 2026-07-02, merged current `origin/main` into the PR repair branch, kept the main-branch removal of repo-local central review workflow files, and verified `PYTHONPATH=src python3 -m pytest -q` passes 22 tests locally.

## 2026-09-27 dependency-check RCA

- Security Scan run `36244212573` on downstream PR #37 reported `anyio==4.14.1` and `cryptography==49.0.0` from the shared runtime/development lock lineage, plus a downstream-only `pypdf==6.15.0` finding.
- PR #81 is the canonical repository-wide lock owner for the shared cryptography remediation. Its exact predecessor head was `ce40bd89e803642d62268bfab13a831171f2bc62`; it already carried `cryptography==50.0.0`, but runtime and development locks still retained vulnerable `anyio==4.14.1` while the test lock carried `4.14.2`.
- The repair adds an executable cross-lock anyio invariant and regenerates runtime, development, and test lock artifacts with `uv pip compile --upgrade-package anyio`, selecting `anyio==4.15.1` while preserving `cryptography==50.0.0`. Hash-required dry-run installs validate every regenerated lock.
- PR #37 must consume the ordinary PR #81 history before its downstream-only pypdf repair; this preserves one shared dependency writer and avoids duplicating the cryptography/anyio fix.
- PR #37 then advances its directly declared document parser from `pypdf==6.15.0` to the first release covering all three observed findings, `pypdf==6.16.1` (CVE-2026-84309, CVE-2026-84310, and CVE-2026-84311), and regenerates all hash-locked projections while retaining PR #81's `anyio==4.15.1` and `cryptography==50.0.0` decisions.

## 2026-09-30 dependency-check follow-up RCA

- Security Scan run `36671696821` on downstream PR #28 at exact head `8aefd06df864e07d9a2f40de687ffcfa6082ed36` failed dependency-review job `109784585922`, Trivy job `109784585930`, and OSV job `109784586129` for the same install surfaces.
- The earlier PR #81 repair at exact predecessor head `e4291e89805078a71d0b6ee1047091e178750a67` covered AnyIO and cryptography in the runtime, development, and test locks, but omitted `requirements-graph.txt` and retained `PyJWT==2.13.0` across the source contract and generated locks.
- A RED lock-contract test reproduced both omissions. The owner repair pins `PyJWT==2.14.0`, adds AnyIO and cryptography security constraints to the Python 3.12 graph lock, and regenerates all four hash-locked install surfaces without suppressing the security gate.
- Integration order remains PR #81 → PR #37 → PR #28. PR #37 retains its downstream-only `pypdf==6.16.1` repair; PR #28 retains its ontology delta. Each successor is revalidated only after ordinary non-force history integration.
- PR #28 ordinary integration regenerated runtime, development, test, and graph locks from the combined ontology and dependency source contract; focused lock contracts, every hash-required install plan, the full suite, and the demo smoke path passed locally before publication.
