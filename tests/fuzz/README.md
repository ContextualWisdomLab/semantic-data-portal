# Fuzzing

This directory fuzzes the highest-value **untrusted-input** surfaces of the
Semantic Data Portal — the code paths that turn an arbitrary user string into a
query, a policy decision, or an ontology lookup. Targets were selected with
CodeGraph by tracing the request/DTO boundary inward to the parsers and the
NL→SQL drafter.

## Targets

| Surface | Module / symbol | Invariant asserted |
| --- | --- | --- |
| NL→SQL drafter | `sdp.orchestrator.draft_sql` / `_safe_identifier` | no crash; no SQL metacharacter or forbidden keyword leaks into the generated statement through a user-controlled identifier; limits bounded |
| Query executor | `sdp.orchestrator.execute_query` | always returns a well-formed response; any forbidden keyword is `REJECTED`, never `SUCCEEDED` |
| Ontology resolver | `sdp.ontology.resolve_terms` / `search_concepts` / `concept_graph` | no crash on arbitrary text; scores in `[0,1]`; results score-sorted; only known concepts surfaced |
| Catalog search | `sdp.catalog.search_catalog` | no crash on regex-metacharacter input (tokens are escaped); results bounded by `limit` and score-sorted |
| Request DTOs | `QueryDraftRequest`, `QueryExecutionRequest`, `DatasetCreateRequest` | arbitrary dicts yield either a valid model or a `ValidationError` — never an uncontrolled exception |

The crash-oracle for every invariant lives in a single place — `invariants.py` —
so the Hypothesis tests and the Atheris harnesses check exactly the same
properties.

## Two layers

### 1. Hypothesis property tests (runs in the normal suite)

[Hypothesis](https://hypothesis.readthedocs.io/) (MPL-2.0). Fast, deterministic,
cross-platform — part of `pytest`:

```bash
python -m pip install --require-hashes -r requirements-test.txt
PYTHONPATH=src python -m pytest tests/fuzz/test_fuzz_properties.py
```

### 2. Atheris coverage-guided harnesses (bounded CI job)

[Atheris](https://github.com/google/atheris) (Apache-2.0) drives libFuzzer for
coverage-guided mutation. The runtime supports **CPython ≤ 3.12**.

```bash
python -m pip install --require-hashes -r requirements-test.txt
python -m pip install --require-hashes -r fuzz-requirements.txt
# 60s per target (CI PR default); override with FUZZ_SECONDS
PYTHONPATH=src:. FUZZ_SECONDS=60 tests/fuzz/run_atheris.sh

# or a single target against its seed corpus
PYTHONPATH=src:. python tests/fuzz/atheris/fuzz_draft_sql.py -max_total_time=30 tests/fuzz/corpus/draft_sql
```

Seed corpora live in `corpus/<target>/`. A reproducing crash is written to a
`crash-*` file in the working directory; re-run the harness with that file as
its argument to replay it.

## CI

`.github/workflows/fuzz.yml` runs the property tests plus a **bounded** Atheris
job (60s/target on PRs, 300s nightly via `schedule`) so fuzzing never blows CI
cost. A crash fails the job and uploads the `crash-*` artifact.

## Background

`docs/papers/miller1990-fuzzing-unix-utilities.pdf` — Miller, Fredriksen & So,
*An Empirical Study of the Reliability of UNIX Utilities* (1990), the paper that
introduced fuzzing: feed random input, assert the program does not crash. That
is exactly the contract these harnesses enforce on the portal's input surfaces.
