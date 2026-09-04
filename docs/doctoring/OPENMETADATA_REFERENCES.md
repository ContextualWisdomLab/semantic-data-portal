# OpenMetadata source and research traceability

This file records the exact external sources used for the first OpenMetadata compatibility contract. It does not copy OpenMetadata product documentation, schema text, or academic papers into the Semantic Data Portal runtime.

## Version baseline

- **Repository:** `open-metadata/OpenMetadata`
- **Release:** `2.0.1-release`
- **Upstream commit:** `bf621b166ec12e8c99fcb1c1443442723386fa41`
- **Published:** 2026-09-02
- **License:** Apache License 2.0
- **CWL decision date:** 2026-09-03
- **CWL implementation issue:** `ContextualWisdomLab/semantic-data-portal#95`
- **CWL implementation PR:** `ContextualWisdomLab/semantic-data-portal#96`

The adapter admits only releases with an immutable compatibility profile. The first profile accepts `2.0.1` and `2.0.1-release`, normalizes both to `2.0.1`, and binds the claim to the exact upstream commit above. Other labels that merely match 2.x syntax fail closed until a separate profile, schema-drift review, positive/hostile fixtures, omission checks, and current-head verification exist.

## Normative source files used

| Source artifact | Upstream path at the pinned commit | CWL use |
|---|---|---|
| Table schema | `openmetadata-spec/src/main/resources/json/schema/entity/data/table.json` | Required `id`, `name`, `columns`; optional FQN and descriptive fields; nested Column, ownership, domain, data product, data contract, classification, profile-summary, status, and source mapping |
| EntityReference schema | `openmetadata-spec/src/main/resources/json/schema/type/entityReference.json` | Required `id`, `type`; optional name, display name, FQN, href; snapshot-wide external-reference consistency |
| EntityLineage schema | `openmetadata-spec/src/main/resources/json/schema/type/entityLineage.json` | Primary entity, node inventory, upstream/downstream edge, pipeline reference, and column-lineage identity validation |
| ChangeEvent schema | `openmetadata-spec/src/main/resources/json/schema/type/changeEvent.json` | Successor design for incremental signed event ingestion; no runtime implementation in PR #96 |
| LifeCycle schema | `openmetadata-spec/src/main/resources/json/schema/type/lifeCycle.json` | Successor design for lifecycle projection; PR #96 currently preserves entity status and source timestamps only |
| License | `LICENSE` | Apache License 2.0 confirmation |

## Research basis

### Mediated interoperability

Wiederhold describes mediators as integration components that encode knowledge needed to connect autonomous information sources with higher-level applications. PR #96 applies this principle through an anti-corruption layer: OpenMetadata retains external authority, CWL domain owners retain their truth, and SDP performs bounded translation without either side adopting the other's complete model.

### Explicit schema matching and evaluation

Bernstein, Madhavan, and Rahm describe schema matching as a distinct integration task requiring explicit techniques, combinations, and evaluation rather than assumptions based on surface similarity. PR #96 therefore uses an exact release profile, upstream commit, required-field tests, hostile fixtures, omission tests, and future profile-per-release drift review instead of accepting every label with the same major version.

No paper PDF is redistributed. The repository stores citations, decision summaries, and executable evidence only.

## APA 7th-style references

Apache Software Foundation. (2004). *Apache License, Version 2.0*. https://www.apache.org/licenses/LICENSE-2.0

Bernstein, P. A., Madhavan, J., & Rahm, E. (2011). Generic schema matching, ten years later. *Proceedings of the VLDB Endowment, 4*(11), 695–701. https://doi.org/10.14778/3402707.3402710

OpenMetadata. (2026, September 2). *OpenMetadata 2.0.1* [Software release]. GitHub. `open-metadata/OpenMetadata`, tag `2.0.1-release`, commit `bf621b166ec12e8c99fcb1c1443442723386fa41`.

OpenMetadata. (2026). *Table JSON schema* [JSON Schema]. `openmetadata-spec/src/main/resources/json/schema/entity/data/table.json`, commit `bf621b166ec12e8c99fcb1c1443442723386fa41`.

OpenMetadata. (2026). *EntityReference JSON schema* [JSON Schema]. `openmetadata-spec/src/main/resources/json/schema/type/entityReference.json`, commit `bf621b166ec12e8c99fcb1c1443442723386fa41`.

OpenMetadata. (2026). *EntityLineage JSON schema* [JSON Schema]. `openmetadata-spec/src/main/resources/json/schema/type/entityLineage.json`, commit `bf621b166ec12e8c99fcb1c1443442723386fa41`.

OpenMetadata. (2026). *ChangeEvent JSON schema* [JSON Schema]. `openmetadata-spec/src/main/resources/json/schema/type/changeEvent.json`, commit `bf621b166ec12e8c99fcb1c1443442723386fa41`.

OpenMetadata. (2026). *LifeCycle JSON schema* [JSON Schema]. `openmetadata-spec/src/main/resources/json/schema/type/lifeCycle.json`, commit `bf621b166ec12e8c99fcb1c1443442723386fa41`.

Wiederhold, G. (1992). Mediators in the architecture of future information systems. *Computer, 25*(3), 38–49. https://doi.org/10.1109/2.121508

## Decision-to-evidence mapping

| Product decision | External evidence | Implementation evidence |
|---|---|---|
| Preserve OpenMetadata without adopting it as CWL domain truth | Mediator architecture and CWL Context Fabric boundaries | `truth_status = observed`, ADR-0001, no mutation or cross-service SQL |
| Require exact compatibility profiles | Schema-matching literature and pinned upstream source | `OpenMetadataReleaseProfile`, sink-level resolver, unverified-release tests |
| Admit sparse schema-valid Table input | Table `required` contract | optional `fully_qualified_name`, minimal Table tests |
| Admit unnamed schema-valid references | EntityReference `required` contract | optional reference name/display/FQN/href and unnamed-reference tests |
| Scope external identity to the installation | OpenMetadata deployments are independently operated sources | `source_instance_id`, installation-scoped projection URN, collision tests |
| Prevent request tenant spoofing | Existing Keyverse-compatible OIDC tenant authority | bearer verification, actor-role gate, actor/body tenant equality, 401/403/404 tests |
| Flatten nested columns without losing path identity | Table `Column.children` schema | `_flatten_columns` and duplicate/depth/count tests |
| Validate full lineage endpoint inventory | EntityLineage `entity`, `nodes`, and edge UUIDs | `_lineage_edges` and broken-endpoint tests |
| Preserve one identity for a reused UUID | EntityReference identity fields | snapshot-wide registry and cross-field conflict tests |
| Preserve column lineage identities but omit transformations | EntityLineage `columnsLineage`, `function`, and SQL-bearing details | `OpenMetadataColumnLineageProjection`, `omitted_fields`, no-secret serialization tests |
| Preserve safe profile aggregates only | Table profile reference | `OpenMetadataProfileSummary` and strict integer tests |
| Distinguish aliases from cycles | Runtime hostile-input boundary | active-path cycle detector, shared-container and true-back-edge tests |
| Reject non-portable numeric provenance | JSON interoperability requirement | finite-version guard for NaN and infinities |
| Bound HTTP parser exposure | Untrusted external payload boundary | router-level 8 MiB buffering and chunked/direct-router 413 tests |

## Verification evidence classes

| Evidence class | Current meaning |
|---|---|
| RED commits and focused local tests | Causal evidence that selected defects were reproduced and repaired |
| Current-head repository Tests | Required proof that the branch integrates with the complete repository |
| Current-head fuzz/SAST/security/dependency gates | Required proof of hostile-input and supply-chain fitness |
| Independent review | Required human or qualifying independent review of the unchanged candidate |
| Protected integration | Evidence that the source is part of canonical `main` |
| Immutable release | Evidence that consumers may depend on a versioned artifact |

Focused local evidence does not promote queued, missing, cancelled, skipped, predecessor, or non-terminal hosted checks to passing.

## Known gaps

- No complete JSON Schema validation against every transitive upstream definition yet.
- No deterministic payload/projection admission receipt in the base PR; this is the purpose of stacked PR #97.
- No live server API client or credential/egress boundary.
- No durable source/snapshot/admission history.
- No ChangeEvent signature, ordering, replay, or dead-letter handling.
- No restricted immutable raw-evidence retention path.
- No outbound writeback or conflict protocol.
- No pipeline, dashboard, metric, ML model, AI agent, glossary, quality-test, or incident mapping.
- No protected immutable OpenMetadata interoperability release.

These gaps are tracked in issue #95 and `docs/product-technical-gap-baseline.md`.
