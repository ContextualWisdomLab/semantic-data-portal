# Semantic Data Portal product and technical Gap baseline

- **Product:** ContextualWisdomLab/semantic-data-portal
- **Baseline date:** 2026-09-04
- **Protected integration target:** `main`
- **OpenMetadata implementation owner:** Semantic Data Portal
- **Primary delivery issue:** #95
- **Current normalization PR:** #96, Draft
- **Current admission-preview successor:** #97, Draft and dependent on #96

This document is the live evidence baseline for buyer-visible product capability and cross-product interoperability. A PR description, issue label, queued workflow, local focused test, or planned consumer is not evidence that a capability is released. Every status below must be evaluated from protected source, the current PR head, immutable release identity, and executable contract evidence.

A commit SHA embedded in this file would become stale when this file itself changes. The authoritative exact head is therefore the GitHub PR metadata for #96; the PR body and check runs must bind their evidence to that head. Previous-head results never transfer automatically.

## Authority and context boundaries

| Concern | Canonical owner | SDP responsibility | Forbidden coupling |
|---|---|---|---|
| Data and AI catalog context | `semantic-data-portal` | Admit, govern, search, and publish policy-filtered metadata context | Domain products writing SDP tables directly |
| OpenMetadata interoperability | `semantic-data-portal` | Exact-version anti-corruption layer, admission, provenance, and controlled synchronization | Independent OpenMetadata SDK and credentials in every product |
| Cross-product external-reference and event contracts | `context-graph-contracts` | Consume immutable released contracts when available | Mutable sibling PR-head dependency |
| Enterprise architecture decisions | `enterprise-architecture-core` | Publish governed data/AI projections for impact consumers | EA Core calling OpenMetadata or SDP databases directly |
| Physical database observation | `pg-erd-cloud` | Receive released schema observations and receipts | Moving physical-schema truth into OpenMetadata or SDP |
| MHTML extraction and schema proposal | `mhtml-etl-gateway` | Receive observed/proposed schema and lineage evidence after source validation | Gateway directly publishing business truth to OpenMetadata |
| LLM routing and agent context | `contextual-orchestrator` | Provide policy-filtered context bundles with evidence and omission classes | OpenMetadata text changing system instructions, tools, or routing |
| Ontology generation and release | `ConceptWeave` | Consume released ontology labels and mappings | Moving product-domain truth into a shared ontology registry |
| Identity and federation | `keyverse` | Reuse verified OIDC actor, tenant, and role claims | Caller-controlled tenant or local credential authority in the catalog |
| Outbound HTTP | `EgressWeave` or the released canonical egress boundary | Route future OpenMetadata API access through approved egress | Raw runtime URL access or credentials in request payloads |

## Current OpenMetadata capability candidate

PR #96 implements the first read-only anti-corruption slice. It is source-complete only as a Draft candidate; it is not released and has not yet satisfied the hosted exact-head merge gate.

### Verified compatibility profile

```text
profile_id: openmetadata-table-lineage-2.0.1
canonical_release: 2.0.1
accepted_labels: 2.0.1, 2.0.1-release
upstream_repository: open-metadata/OpenMetadata
upstream_tag: 2.0.1-release
upstream_revision: bf621b166ec12e8c99fcb1c1443442723386fa41
```

The profile is bound to the upstream Table, EntityLineage, and EntityReference schema paths at that exact revision. A different 2.x release is unsupported until a distinct immutable profile, field-level drift review, positive and hostile fixtures, omission tests, and exact-head evidence exist.

### Implemented in #96 source

- OIDC/JWKS bearer verification through the existing SDP identity adapter;
- role admission for `data-analyst`, `admin`, and `platform-admin`;
- fail-closed actor-tenant/request-tenant equality with cross-tenant 404;
- tenant- and `source_instance_id`-scoped `observed` Table projection;
- collision-resistant identity for equal UUIDs from separate OpenMetadata installations;
- exact compatibility-profile admission at the actual normalization sink;
- self-validating immutable release-profile definitions;
- upstream-compatible sparse Table and EntityReference admission;
- optional external FQN, name, display name, and href preservation without invented defaults;
- snapshot-wide UUID/type/name/FQN consistency checks;
- bounded nested-column flattening;
- aggregate-only table profile summary;
- table and column lineage with declared-node endpoint integrity;
- omission of sample rows, DDL, SQL/query text, joins, column profiles, custom metrics, extension payloads, lineage SQL, and transformation functions;
- explicit omitted-field classes;
- strict UUID, URL, credential, text, number, collection, depth, true-cycle, and non-finite-version guards;
- acyclic shared-container alias acceptance;
- authenticated typed normalization HTTP endpoint;
- router-level 8 MiB body limit for Content-Length and chunked/direct-router requests;
- exact compatibility profile and upstream contract-source provenance;
- README, ADR, integration guide, implementation matrix, doctoring, CHANGELOG, and this Gap baseline.

### Focused TDD evidence already obtained

The repair sequence reproduced the reviewed defects before implementation. Focused local suites then reached:

- review-regression slice: 10/10 passing after the initial 9-failure RED run;
- review-regression plus existing guard slice: 17/17 passing;
- source-instance-expanded slice: 20/20 passing;
- authentication, tenant, chunked-body, and source-instance HTTP slice: 12/12 passing.

These results establish causal repair for the selected boundaries. They do not replace the full repository, coverage, fuzz, SAST, dependency, security, package, or central policy workflows on the current head.

### Evidence still required before #96 integration

- unchanged current-head repository test result;
- production statement and branch coverage 100% for the changed production boundary;
- public API docstrings 100%;
- current-head fuzz, SAST, Security Scan, OSV/dependency, Scorecard, and other required central workflow results;
- all valid review findings resolved against the current source;
- qualifying independent approval on the current head;
- ordinary protected merge without force push or administrative bypass.

Queued, pending, cancelled, skipped, missing, neutral, or predecessor workflow execution is non-passing. Review-bot summaries are not substitutes for executable gates.

## OpenMetadata Gap register

| Gap ID | Buyer-visible problem | Owner and delivery path | Current status | Exit evidence |
|---|---|---|---|---|
| OM-001 | A customer cannot prove which source snapshot produced a candidate projection | SDP stacked successor #97 | In progress, Draft | deterministic source/projection digests, replay identity, golden vectors, strict transport JSON, receipt self-verification, no mutation |
| OM-002 | Restart-safe admission and replay history do not exist | SDP successor after #97 | Open | 3NF source/snapshot/receipt/projection history, PostgreSQL integration, idempotent replay, migration and rollback |
| OM-003 | Raw payload evidence has no restricted immutable retention path | SDP evidence-store successor | Open | encrypted object evidence, tenant/purpose authorization, retention, legal hold, export receipt |
| OM-004 | OpenMetadata Change Events cannot be consumed safely | SDP webhook successor | Open | signature verification, inbox deduplication, version ordering, bounded retry, dead letter, replay, deprecation history |
| OM-005 | SDP cannot retrieve live OpenMetadata metadata | SDP outbound connector successor | Open | credential registry, canonical egress, capability discovery, pagination, rate/backoff, operation receipt |
| OM-006 | Approved SDP changes cannot be synchronized back | SDP controlled-write successor | Open | steward approval, field authority matrix, ETag/version precondition, conflict receipt, rollback |
| OM-007 | Only Table/Column/EntityLineage are profiled | SDP entity-profile successors | Open | exact profiles for pipelines, dashboards/charts/metrics, ML models/features/agents, quality/tests/incidents, domains/products/contracts, glossary/classification |
| OM-008 | Cross-product contracts are not released | `context-graph-contracts#26` after its protected foundation stack | Blocked on owner foundation | immutable schema/SDK release, conformance fixtures, source provenance, consumer exact-version tests |
| OM-009 | Physical schema producer is not connected | `pg-erd-cloud#1072` after released contracts | Planned | PostgreSQL schema observation → SDP admission → OpenMetadata-ready projection E2E |
| OM-010 | Extracted MHTML schema proposals are not connected | `mhtml-etl-gateway#66` after released contracts | Planned | immutable MHTML evidence → approved proposal → SDP receipt E2E |
| OM-011 | EA impact paths do not include governed OpenMetadata assets | `enterprise-architecture-core#44` after released contracts and SDP durable admission | Planned | source authority/truth/provenance-preserving impact path and idempotent projection receipt |
| OM-012 | Agents cannot retrieve policy-filtered OpenMetadata context | `contextual-orchestrator#1042` after SDP context bundle release | Planned | injection-safe SDP bundle → orchestrator tool result → evidence-backed synthesis E2E |
| OM-013 | OpenMetadata release drift can silently break a future adapter | SDP compatibility-profile lane | Partially closed by #96 candidate | automated exact-source schema diff, explicit profile addition, old-profile immutability, supported-release matrix |
| OM-014 | No buyer-operable connection, mapping, conflict, or replay workflow exists | SDP admin/operator UX after runtime contracts | Open | Figma IDs/tokens in ADR, Storybook normal/loading/empty/error/permission/conflict/replay states, keyboard/mobile/i18n E2E |
| OM-015 | No supported OpenMetadata interoperability release exists | SDP release lane | Open | version bump, CHANGELOG release section, signed artifact, SBOM, provenance, upgrade/rollback runbook, compatibility matrix |
| OM-016 | External identity could previously choose another tenant namespace | SDP PR #96 | Source repaired; merge evidence pending | authenticated OIDC integration tests, current-head security gates, protected integration |
| OM-017 | Independent OpenMetadata installations could collide on an external UUID | SDP PR #96 | Source repaired; merge evidence pending | source-instance projection tests, receipt propagation in #97, durable uniqueness constraints in OM-002 |
| OM-018 | Upstream-valid sparse Table/EntityReference payloads were rejected | SDP PR #96 | Source repaired; merge evidence pending | exact upstream schema tests and current-head repository GREEN |
| OM-019 | A direct internal import could bypass release-profile admission | SDP PR #96 | Source repaired; merge evidence pending | sink-level unverified-release RED/GREEN and current-head repository GREEN |
| OM-020 | HTTP input could exceed parser budgets when the router was embedded directly | SDP PR #96 | Source repaired; merge evidence pending | Content-Length/chunked/direct-router 413 tests and current-head security GREEN |

## First closed cross-product vertical

The first release-worthy buyer path is:

```text
OpenMetadata Table and EntityLineage
→ authenticated exact release-profile admission
→ deterministic source and projection receipt
→ durable tenant/source-instance observation history
→ policy-filtered context event
→ EA impact path and Contextual Orchestrator context bundle
```

The path is complete only when every arrow consumes an immutable released contract and produces a verifiable receipt. An issue, mutable branch, copied fixture, direct SQL query, or manual JSON handoff does not close the vertical.

## Data and security invariants

- OpenMetadata is not the authority for CWL HR, billing, learning, psychometrics, security, EA, or other product-domain facts.
- `observed`, `inferred`, `proposed`, `authoritative`, `superseded`, and `rejected` remain distinct.
- External IDs are tenant- and source-installation-scoped.
- Request tenant values cannot override a verified actor tenant.
- Historical observations close validity or are superseded; they are not hard-deleted.
- Sample values, credentials, tokens, DSNs, SQL/DDL, query text, and unrestricted raw extension payloads do not enter general projections or context bundles.
- Unknown quality, freshness, ownership, optional identity fields, or mapping remain unknown rather than numeric zero or an invented value.
- No cross-service SQL, mutable sibling source, provider database access, or copied runtime implementation.
- LLM output cannot promote truth status, ownership authority, policy, or outbound write approval.
- Source and projection fingerprints are restricted metadata and must not be exposed across tenants.
- The normalization route is non-mutating; durable admission is a distinct successor boundary.

## Performance and operability targets for durable admission

These are acceptance targets for the future durable slice, not claims about current performance.

- replay of 10,000 identical snapshots: zero duplicate admitted revisions;
- 100,000 Table observations and 1,000,000 column/lineage relations in the reference dataset;
- admission API p95 at or below 20 ms excluding external network and restricted raw-evidence object upload;
- bounded memory proportional to the configured payload, column, reference, and lineage limits;
- no warm-cache-only benchmark or reduced validation path;
- source outage, PostgreSQL restart, duplicate event, reversed event order, and partial projection failure recovery;
- observable queue depth, projection lag, rejection reason, dead-letter count, replay count, and receipt latency;
- backup, point-in-time recovery, restore, rollback, and contract downgrade rehearsal.

## Update rule

Update this file whenever an OpenMetadata PR changes base, scope, status, release identity, contract version, owner boundary, verification result, or successor order. Resolve the exact head from GitHub at verification time. State a capability as implemented only when the source exists; state it as integrated only when it is on the protected branch; state it as released only when an immutable artifact carries the executable contract and its evidence.
