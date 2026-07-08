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

### This repo's role in the ecosystem
- **`semantic-data-portal`** is the higher-level ontology-driven dataset catalog /
  glossary / governance plane with its **OWN graph engine + persistence** (target:
  Postgres + Apache AGE + pgvector) for semantic retrieval; layered **above**
  naruon's document KG, **not** the document-KG store itself.
- **Ecosystem context:** the org is an ecosystem around **naruon** (the hub:
  email/PIM that DOM-decomposes emails/files into a persisted knowledge graph).
  Each component is a **standalone program that must ALSO work as a git
  submodule** — grown separately and together:
  - `waf-ids-ai-soc` — WAF / IDS / AI SOC / LB / APIM
  - `clearfolio` — document viewer
  - `pg-erd-cloud` — ERD tool
  - `contextual-orchestrator` — LLM cost/perf/upstream-LB gateway (beyond LiteLLM)
  - `codec-carver` — STT / omni-modal speech-video codec
  - `fast-mlsirm` — LLM-as-a-Judge calibration + evaluation-item quality (uses
    aFIPC FIPC + kaefa item-fit)
  - `feelanet-adfs` — passwordless SSO (OIDC/SCIM/ADFS/LDAP/FIDO2/OAuth2.1,
    eliminate passwords)
  - `newsdom-api` — PDF→DOM sidecar
  - `semantic-data-portal` — upper ontology / catalog / governance plane with its
    own graph engine (this repo)

### Research grounding (attach paper PDFs)
- **Org rule:** substantive feature/process PRs should find the relevant academic
  papers and **commit their PDFs into the PR** (e.g. a `docs/papers/` or
  `references/` dir) with **full citations**, **respecting copyright** — attach the
  PDF only when redistribution is permissible; otherwise **cite + link +
  summarize** instead of committing the file.
- **For this repo (graph/ontology retrieval):** e.g. a PR adding semantic retrieval
  over the catalog should ground it in graph/ontology-retrieval and vector-search
  literature (knowledge-graph embeddings, ontology alignment, GraphRAG / hybrid
  dense+graph retrieval) under `docs/papers/`.
<!-- END cwl-agent-guidance -->
