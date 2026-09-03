# OpenMetadata source traceability

This file records the exact external sources used for the first OpenMetadata compatibility contract. It does not copy OpenMetadata product documentation or schema text into the Semantic Data Portal runtime.

## Version baseline

- **Repository:** `open-metadata/OpenMetadata`
- **Release:** `2.0.1-release`
- **Published:** 2026-09-02
- **License:** Apache License 2.0
- **CWL decision date:** 2026-09-03
- **CWL implementation issue:** `ContextualWisdomLab/semantic-data-portal#95`
- **CWL implementation PR:** `ContextualWisdomLab/semantic-data-portal#96`

The adapter accepts explicitly declared OpenMetadata 2.x payloads. The schema fixtures and documented compatibility claim are initially limited to `2.0.1-release`. A later 2.x release must pass schema-drift and regression verification before it is added to the compatibility matrix.

## Normative source files used

| Source artifact | Upstream path | CWL use |
|---|---|---|
| Table schema | `openmetadata-spec/src/main/resources/json/schema/entity/data/table.json` | Table, nested Column, ownership, domain, data product, data contract, classification, profile-summary, status, and source identity mapping |
| EntityLineage schema | `openmetadata-spec/src/main/resources/json/schema/type/entityLineage.json` | Primary entity, node inventory, upstream/downstream edge, pipeline reference, and column-lineage identity validation |
| ChangeEvent schema | `openmetadata-spec/src/main/resources/json/schema/type/changeEvent.json` | Successor design for incremental signed event ingestion; no runtime implementation in PR #96 |
| LifeCycle schema | `openmetadata-spec/src/main/resources/json/schema/type/lifeCycle.json` | Successor design for lifecycle projection; PR #96 currently preserves entity status and source timestamps only |
| License | `LICENSE` | Apache License 2.0 confirmation |

## APA 7th-style references

OpenMetadata. (2026, September 2). *OpenMetadata 2.0.1* [Software release]. GitHub. `open-metadata/OpenMetadata`, tag `2.0.1-release`.

OpenMetadata. (2026). *Table JSON schema* [JSON Schema]. `openmetadata-spec/src/main/resources/json/schema/entity/data/table.json`, release `2.0.1-release`.

OpenMetadata. (2026). *EntityLineage JSON schema* [JSON Schema]. `openmetadata-spec/src/main/resources/json/schema/type/entityLineage.json`, release `2.0.1-release`.

OpenMetadata. (2026). *ChangeEvent JSON schema* [JSON Schema]. `openmetadata-spec/src/main/resources/json/schema/type/changeEvent.json`, release `2.0.1-release`.

OpenMetadata. (2026). *LifeCycle JSON schema* [JSON Schema]. `openmetadata-spec/src/main/resources/json/schema/type/lifeCycle.json`, release `2.0.1-release`.

Apache Software Foundation. (2004). *Apache License, Version 2.0*.

## Decision-to-evidence mapping

| Product decision | External evidence | Implementation evidence |
|---|---|---|
| Preserve UUID and fully qualified name | Table and EntityReference schemas | `OpenMetadataReferenceProjection`, `OpenMetadataTableProjection` |
| Flatten nested columns without losing path identity | Table `Column.children` schema | `_flatten_columns` and duplicate-path tests |
| Validate full lineage endpoint inventory | EntityLineage `entity`, `nodes`, and edge UUIDs | `_lineage_edges` and broken-endpoint tests |
| Preserve column lineage identities but omit transformations | EntityLineage `columnsLineage` and `function` | `OpenMetadataColumnLineageProjection`, `omitted_fields` |
| Preserve safe profile aggregates only | Table profile reference | `OpenMetadataProfileSummary` |
| Treat source metadata as observation | CWL Context Fabric authority model | `truth_status = observed`, ADR-0001 |
| Reject pre-2.x reinterpretation | Explicit compatibility baseline | request pattern and HTTP 422 regression test |

## Known gaps

- No complete JSON Schema validation against every upstream referenced definition yet.
- No live server API client or credential boundary.
- No durable snapshot/admission model.
- No ChangeEvent signature, ordering, replay, or dead-letter handling.
- No outbound writeback or conflict protocol.
- No pipeline, dashboard, metric, ML model, AI agent, glossary, quality-test, or incident mapping.

These gaps are tracked in issue #95 and `docs/product-technical-gap-baseline.md`.
