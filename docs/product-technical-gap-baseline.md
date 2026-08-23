# Product and technical gap baseline

**Product home:** ContextualWisdomLab/semantic-data-portal (ontology-driven semantic catalog).
**Audience:** catalog steward / tenant operator.
**Next action:** merge the unlock stack in the order below; do not stand up a local identity provider or policy registry in this repository.
**As of:** 2026-08-23 (main `e48aa13`).
**Figma file ID:** not assigned.

This file is the living gap list for the portal. Update it when an open pull request lands or a consume-only contract changes. Do not treat GitHub review wait as a stop.

## Boundary (consume-only vs own)

| Concern | Owner | Portal duty |
| --- | --- | --- |
| Identity, SCIM, tenant header, purpose-limited authorization | Keyverse | Consume signed claims fail-closed (`X-CWL-Tenant-Reference`, OIDC subject). No local IdP. |
| Policy, control, evidence, audit truth | GRC home | Consume evidence contracts. No local policy registry. |
| Organization security gates (Security Scan, Strix, CodeQL, Semgrep, python-security) | CWL Security | Inherit org workflows; do not fork a second gate loop. |
| Ontology registry and catalog plane | **this repo** | Glossary, catalog objects, bindings, provenance pointers. |
| Document knowledge graph / weekly report | LineageWeave (#74) | Do not block on #74→main. Consume commons provenance only. |
| IRT / linking scores | fast-mlsirm | Call out; do not reimplement. |
| Employment tree | Orgmetra | Consume affiliation keys. |
| Office authoring | naruon | Sender-ontology consumer only. |
| Measurement import | TEPP | Import/REST only. |
| Disk inventory | DiskSage | Catalog ingest/preview adapters only. |

PII stays usable. Purpose-limited access plus audit replace masking. Do not add a masker in this repo.

## Standards already adopted (APA 7th)

Albertoni, R., Browning, D., Cox, S., Gonzalez Beltran, A., Perego, A., & Winstanley, P. (Eds.). (2024). *Data Catalog Vocabulary (DCAT) — Version 3*. World Wide Web Consortium. https://www.w3.org/TR/vocab-dcat-3/

International Organization for Standardization. (2023). *Information technology — Metadata registries (MDR) — Part 1: Framework* (ISO/IEC 11179-1:2023).

Moreau, L., & Missier, P. (Eds.). (2013). *PROV-DM: The PROV data model*. World Wide Web Consortium. https://www.w3.org/TR/prov-dm/

If a later commit contradicts these, change the code, not the citation.

## Merge order (steward)

1. **#51** `558dd2f` — outbound URL harden + cryptography CVE. Unlocks `trivy-fs` for every other portal PR. Frozen; do not push this head. Needs OpenCode APPROVE on this exact SHA, then Product Manager squash.
2. **#58** `80966ae` — bounded Keyverse claim aliases. Frozen. Same merge gate.
3. **#35** `9c12f5d` (and #32 SQL gate) — fail-closed SQL allowlist. Frozen.
4. **#73** `bfa409f` — catalog/ontology plane (#13). Product checks green; remaining red is inherited `trivy-fs` from #51. Hold pushes. **#75** stays Draft until #73 is on main.
5. **#28** after **#37** — hybrid file ontology on trusted document deps.
6. **#59** / **#61** — DiskSage ingest and preview boundary.
7. **#64** product names (after #51 so trivy is not inherited as a docs failure), then **#65** setuptools, then Dependabot.

Do not mix #51 security-lock files into a catalog or docs PR.

## Open pull requests and the gap each closes

| PR | Head | Gap | Portal-owned? | Status 2026-08-23 |
| --- | --- | --- | --- | --- |
| #51 | `558dd2f` | Cryptography CVE / trivy-fs unlock; outbound URL allowlist | Yes (security lock) | HOLD. No current-SHA OpenCode APPROVE. |
| #58 | `80966ae` | Keyverse claim aliases fail-closed | Consume Keyverse; implement adapter here | HOLD. Prior APPROVE was on an older SHA. |
| #35 | `9c12f5d` | SQL comma-join allowlist bypass | Yes | HOLD. CI green; waiting current-SHA APPROVE. |
| #32 | `76fcfb6` | SELECT..INTO / volatile SQL bypass | Yes | Open; keep stacked behind #35/#51. |
| #73 | `bfa409f` | Catalog plane above the document KG (#13) | Yes | HOLD. trivy inherit only. |
| #75 | `56b0ad2` Draft | Framework-neutral data-management evidence *profiles* (not a GRC registry) | Yes (catalog evidence shape) | Draft until #73. |
| #59 | `65e4fd7` | DiskSage catalog ingest | Adapter yes | HOLD. |
| #61 | `0c248d2` | DiskSage preview boundary | Adapter yes | Open; Analyze flake — do not extra-push. |
| #28 | `5e4b11c` | Hybrid file ontology | Yes after #37 | Wait #37. |
| #37 | `00ee8af` | Trusted document semantic deps | Yes (build) | Open. |
| #64 | `4b78611` | Current CWL product names | Yes (docs) | After #51. |
| #65 | `19603c3` | setuptools 83 | Yes (build) | After unlock. |
| #72 | `2295b0d` Draft | Operator README / draft ADRs | Yes (docs) | Draft. |
| Dependabot #27 #29 #57 #62 #63 #67 #68 #69 #70 #71 | various | Dependency currency | Yes after unlock | Do not land while trivy inherit is red. |

## Operator-facing gaps not yet in a PR

| Gap | Why a steward feels it | Lane |
| --- | --- | --- |
| Catalog plane not on main | Glossary and catalog objects die on process restart unless `SDP_DATABASE_DSN` is set; paid-pilot persistence is in #73 only | Portal — land #73 |
| No tenant-bound catalog without Keyverse | Fail-closed is correct; the steward still cannot browse until #58 is merged | Consume Keyverse |
| DiskSage batches not previewable on main | Inventory metadata cannot be stewarded in the catalog UI | Portal adapters #59/#61 |
| Hybrid file types | Uploaded office/binary files are not typed against the file ontology | Portal #28 after #37 |
| Storybook + design tokens | `docs/design-tokens.md` exists; no Figma file ID; scene/edge-case event inventory is incomplete | Portal UI — do not invent a Figma ID |
| `docs/product-technical-gap-baseline.md` | This file (bootstrap) | Portal |

## Explicit non-gaps (do not build here)

- LineageWeave weekly report / KG write path.
- IRT scoring kernel.
- Keyverse issuance, SCIM, PAT minting.
- GRC control library or audit ledger.
- naruon editor, calendar, HWPX.
- PII masking.
- A second hourly merge loop at minute :17.

## Operability notes

- Database objects: two-or-more-word `snake_case`, 3NF. Catalog plane tables live in `migrations/0002_ontology_catalog_plane.sql` on #73.
- Default CI store is in-memory; DSN-backed store is the paid-pilot path.
- LLM tests and Actions schedulers use `NVIDIA_NIM_API_KEY` via contextual-orchestrator. Do not use `COPILOT_GITHUB_TOKEN`. Do not retune review-bot keys.
- Analyze (actions) 503 SARIF upload is a flake: do not push a new commit only to rerun it.
