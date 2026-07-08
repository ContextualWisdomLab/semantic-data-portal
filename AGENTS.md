# AGENTS.md

Cross-agent conventions for `semantic-data-portal` (readable by any coding agent:
Claude, Codex, Cursor, opencode, …). This repo is a Python / FastAPI MVP
(`src/sdp`, tests in `tests/`). Install with `pip install -e .[dev]`, run
`uvicorn sdp.api:app --reload`, test with `pytest`.

<!-- BEGIN cwl-agent-guidance -->
## Agent guidance (CWL governance)

### Security & review gate
- Every PR (including stacked PRs, on each PR base) runs a **central org "Security
  Scan" required gate**: `osv-scan` + `dependency-review` (diff-scoped) and
  `trivy-fs` (repo-wide, CRITICAL/HIGH, fixable). The gate is applied centrally —
  don't expect its workflow to live in this repo.
- **A failing `trivy-fs` is a REAL finding, not a flake.** Read the job log (it
  prints each finding's rule id / severity / file) or the run's SARIF results,
  then **remediate**:
  - Dependency CVE → bump the pin in `pyproject.toml` (`fastapi`, `uvicorn`,
    `pydantic`, or a dev dep) and let the resolver pull the fixed version.
  - Config/misconfig → fix the flagged file. This repo ships no Dockerfile or k8s
    manifests, so the misconfig surface is the YAML under `.github/workflows/`
    (e.g. over-broad workflow `permissions:`, unpinned action SHAs). Fix it there.
  - Genuine false positive → add a **narrow, documented** `.trivyignore.yaml`
    entry (specific rule id + reason). Never broaden severity, drop paths, or
    disable the gate.
- **Reproduce locally correctly**: a stale local DB misses findings. Refresh the
  DB first, then scan the **merge ref** (not just the PR head), e.g.
  `trivy fs --format table .` to read the exact rule id / severity / file.
- The org `code_scanning` ruleset is intentionally **CodeQL-only** — multiple
  code-scanning tools can't converge on one PR ref. Gating is by the Security
  Scan **job result**, not the `code_scanning` rule. **Do not add tools to that
  rule.**

### Code exploration
- There is **no `.codegraph/` index** in this repo, so use normal search
  (grep/find/ripgrep) to locate and understand code. If a `.codegraph/` directory
  is later added at the repo root, prefer CodeGraph
  (`codegraph explore "<query>"`, or the code-review-graph MCP tools) **before**
  grep/find — it surfaces callers/callees/impact that text search misses.

### Config & secrets (KV, not env)
- **Org rule: do NOT read runtime config/secrets via `os.getenv()` / raw
  environment variables.** Read them from a KV / credential registry. Org Actions
  secrets (e.g. `OPENAI_API_KEY`) flow **into** the KV via a bootstrap/CI step;
  runtime reads from the KV — env is only transport into the KV, never the
  runtime source.
- **Reference implementation:** xtrmLLMBatchPython's pgcrypto-encrypted Postgres
  credential registry (`get_credential(name)`). Reuse that pattern (a DB-backed KV
  is fine) unless a dedicated KV is adopted.
- **Status in this repo:** the service is an in-memory MVP that reads **no**
  runtime secrets today — no `os.getenv`, no DB credentials, no external API keys,
  nothing in CI. So there is no deviation to migrate; this rule is forward-looking.
  The moment real credentials appear — e.g. wiring `/llm/*` to an actual LLM
  provider, or `orchestrator`/`browse` to a real database — pull them from the KV
  via `get_credential(...)`, **not** `os.getenv`.
<!-- END cwl-agent-guidance -->
