# Semantic Data Portal 제품·기술 Gap 기준선

- **제품:** `ContextualWisdomLab/semantic-data-portal`
- **기준일:** 2026-09-04
- **보호된 통합 대상:** `main`
- **OpenMetadata 구현 소유자:** Semantic Data Portal
- **주요 delivery issue:** #95
- **현재 normalization PR:** #96, Draft
- **현재 admission-preview successor:** #97, Draft이며 #96에 의존

이 문서는 구매자가 체감하는 제품 역량과 제품 간 상호운용 상태를 기록하는 살아 있는 evidence baseline입니다. PR 설명, issue label, queued workflow, focused local test, 예정된 consumer만으로 기능이 release됐다고 판단하지 않습니다. 아래 상태는 보호된 source, 현재 PR exact head, immutable release identity, executable contract evidence를 함께 확인해야 합니다.

이 파일 안에 PR head SHA를 적으면 파일 자체를 갱신하는 순간 값이 낡습니다. 따라서 #96의 authoritative exact head는 GitHub PR metadata에서 조회하고, PR 본문과 Check run이 그 head에 묶여 있어야 합니다. 이전 head의 결과는 자동으로 이전되지 않습니다.

## 권위와 Context 경계

| 관심사 | Canonical owner | SDP 책임 | 금지하는 결합 |
|---|---|---|---|
| Data·AI catalog context | `semantic-data-portal` | metadata context admission, governance, search, policy-filtered publication | Domain product가 SDP table에 직접 write |
| OpenMetadata interoperability | `semantic-data-portal` | exact-version anti-corruption layer, admission, provenance, controlled synchronization | 모든 제품이 독립 OpenMetadata SDK와 credential을 보유 |
| Cross-product external reference·event contract | `context-graph-contracts` | immutable released contract가 생기면 이를 소비 | Mutable sibling PR head에 의존 |
| Enterprise architecture decision | `enterprise-architecture-core` | Impact consumer에 governed Data·AI projection 제공 | EA Core가 OpenMetadata 또는 SDP DB를 직접 호출 |
| Physical database observation | `pg-erd-cloud` | Released schema observation과 receipt 수용 | Physical-schema truth를 OpenMetadata·SDP로 이전 |
| MHTML extraction·schema proposal | `mhtml-etl-gateway` | Source validation 이후 observed/proposed schema·lineage evidence 수용 | Gateway가 business truth를 OpenMetadata에 직접 publish |
| LLM routing·agent context | `contextual-orchestrator` | Evidence와 omission class를 보존한 policy-filtered context bundle 제공 | OpenMetadata text가 system instruction, tool, routing을 변경 |
| Ontology generation·release | `ConceptWeave` | Released ontology label·mapping 소비 | Product-domain truth를 공유 ontology registry로 이전 |
| Identity·federation | `keyverse` | 검증된 OIDC actor, tenant, role claim 재사용 | Caller-controlled tenant 또는 catalog 내부 credential authority |
| Outbound HTTP | `EgressWeave` 또는 released canonical egress boundary | 향후 OpenMetadata API access를 승인된 egress로 전달 | Runtime이 임의 URL에 접근하거나 request payload에 credential 포함 |

## 현재 OpenMetadata 기능 후보

PR #96은 첫 read-only anti-corruption slice를 구현합니다. Source 기준으로 기능 후보는 존재하지만 Draft이며, hosted exact-head merge gate를 아직 충족하지 않았습니다. 따라서 integrated 또는 released capability로 표현하지 않습니다.

### 검증된 Compatibility profile

```text
profile_id: openmetadata-table-lineage-2.0.1
canonical_release: 2.0.1
accepted_labels: 2.0.1, 2.0.1-release
upstream_repository: open-metadata/OpenMetadata
upstream_tag: 2.0.1-release
upstream_revision: bf621b166ec12e8c99fcb1c1443442723386fa41
```

이 profile은 위 exact revision의 Table, EntityLineage, EntityReference schema path에 묶입니다. 다른 2.x release는 별도의 immutable profile, field-level drift review, positive·hostile fixture, omission test, exact-head evidence가 생기기 전까지 지원하지 않습니다.

### #96 source에 구현된 범위

- 기존 SDP identity adapter를 통한 OIDC/JWKS bearer verification
- `data-analyst`, `admin`, `platform-admin` 역할 admission
- Verified actor tenant와 request tenant의 exact equality; cross-tenant 요청은 404로 fail-closed
- Tenant와 `source_instance_id`로 범위를 정한 `observed` Table projection
- 같은 UUID를 쓰는 복수 OpenMetadata installation의 identity 충돌 방지
- 실제 normalization sink에서 exact compatibility-profile admission
- Immutable release-profile definition의 self-validation
- Upstream schema가 허용하는 sparse Table·EntityReference 수용
- Optional external FQN·name·display name·href 보존과 invented default 금지
- Snapshot 전체에 적용되는 UUID/type/name/FQN consistency 검증
- Bounded nested-column flattening
- Aggregate-only table profile summary
- Declared-node endpoint integrity를 갖는 table·column lineage
- Sample row, DDL, SQL/query text, join, column profile, custom metric, extension payload, lineage SQL, transformation function 제외
- Omitted source field class 기록
- UUID, URL, credential, text, number, collection, depth, true cycle, non-finite version guard
- Shared acyclic container alias 허용
- Authenticated typed normalization HTTP endpoint
- Content-Length와 chunked/direct-router 요청에 동일한 8 MiB body limit
- Exact compatibility profile과 upstream contract-source provenance
- README, ADR, integration guide, implementation matrix, doctoring, CHANGELOG, 이 Gap 기준선

### 이미 확보한 Focused TDD evidence

검토에서 지적된 결함을 production code 수정 전에 재현했습니다. 이후 focused local suite는 다음 상태에 도달했습니다.

- Review-regression slice: 최초 RED 10개 중 9개 실패·1개 통과 → 수정 후 10/10 통과
- Review-regression + 기존 guard slice: 17/17 통과
- Source-instance 확장 slice: 20/20 통과
- Authentication·tenant·chunked-body·source-instance HTTP slice: 12/12 통과

이는 선택한 결함의 causal repair evidence입니다. 전체 repository test, coverage, fuzz, SAST, dependency, security, package, central policy workflow를 대신하지 않습니다.

### #96 통합 전에 필요한 Evidence

- 변경되지 않은 current exact head의 repository test 결과
- 변경 production boundary의 statement·branch coverage 100%
- Public API docstring 100%
- Current-head fuzz, SAST, Security Scan, OSV/dependency, Scorecard와 기타 required central workflow 결과
- 유효한 review finding의 current-source 반영과 thread resolution
- Current head에 대한 qualifying independent approval
- Force push나 administrative bypass가 없는 ordinary protected merge

Queued, pending, cancelled, skipped, missing, neutral 또는 predecessor workflow는 non-passing입니다. Review bot summary도 executable gate를 대체하지 않습니다.

## 연구 근거와 적용

이 interoperability boundary는 외부 제품을 CWL domain model에 흡수하지 않고, 독립 source와 consumer 사이에 의미 변환 책임을 둡니다. Wiederhold의 mediator architecture는 autonomous source와 application 사이에 integration knowledge를 담당하는 mediator를 두는 구조를 제시합니다. #96의 OpenMetadata anti-corruption layer가 이 mediator 역할을 하며, OpenMetadata와 CWL domain owner의 authority를 모두 보존합니다.

Bernstein, Madhavan, Rahm의 schema matching 연구는 schema 간 대응을 표면적인 이름 유사성으로 가정하지 않고, 별도의 matching·combination·evaluation 문제로 다룹니다. 이에 따라 #96은 “같은 2.x”라는 이유로 미래 release를 자동 수용하지 않고 exact upstream commit, release-specific profile, required-field regression, hostile fixture, omission test를 요구합니다.

전체 citation과 decision-to-evidence mapping은 `docs/doctoring/OPENMETADATA_REFERENCES.md`와 ADR-0001에 기록했습니다. 논문 PDF는 재배포 권한을 확인하지 않았으므로 저장소에 복제하지 않았습니다.

- Bernstein, P. A., Madhavan, J., & Rahm, E. (2011). Generic schema matching, ten years later. *Proceedings of the VLDB Endowment, 4*(11), 695–701. https://doi.org/10.14778/3402707.3402710
- Wiederhold, G. (1992). Mediators in the architecture of future information systems. *Computer, 25*(3), 38–49. https://doi.org/10.1109/2.121508

## OpenMetadata Gap register

| Gap ID | 구매자 문제 | Owner·delivery path | 현재 상태 | Exit evidence |
|---|---|---|---|---|
| OM-001 | 어떤 source snapshot이 candidate projection을 만들었는지 증명할 수 없음 | SDP stacked successor #97 | 진행 중, Draft | Deterministic source/projection digest, replay identity, golden vector, strict transport JSON, receipt self-verification, no mutation |
| OM-002 | Restart-safe admission·replay history가 없음 | #97 이후 SDP successor | Open | 3NF source/snapshot/receipt/projection history, PostgreSQL integration, idempotent replay, migration·rollback |
| OM-003 | Raw payload evidence를 제한적으로 immutable 보존할 경로가 없음 | SDP evidence-store successor | Open | Encrypted object evidence, tenant/purpose authorization, retention, legal hold, export receipt |
| OM-004 | OpenMetadata Change Event를 안전하게 소비하지 못함 | SDP webhook successor | Open | Signature verification, inbox deduplication, version ordering, bounded retry, dead letter, replay, deprecation history |
| OM-005 | SDP가 live OpenMetadata metadata를 조회하지 못함 | SDP outbound connector successor | Open | Credential registry, canonical egress, capability discovery, pagination, rate/backoff, operation receipt |
| OM-006 | 승인된 SDP 변경을 OpenMetadata에 되돌려 보낼 수 없음 | SDP controlled-write successor | Open | Steward approval, field authority matrix, ETag/version precondition, conflict receipt, rollback |
| OM-007 | Table·Column·EntityLineage만 profiling됨 | SDP entity-profile successor | Open | Pipeline, dashboard/chart/metric, ML model/feature/agent, quality/test/incident, domain/product/contract, glossary/classification exact profile |
| OM-008 | Cross-product contract가 release되지 않음 | `context-graph-contracts#26`, protected foundation stack 이후 | Owner foundation에 blocked | Immutable schema/SDK release, conformance fixture, source provenance, consumer exact-version test |
| OM-009 | Physical schema producer가 연결되지 않음 | Released contract 이후 `pg-erd-cloud#1072` | Planned | PostgreSQL schema observation → SDP admission → OpenMetadata-ready projection E2E |
| OM-010 | MHTML에서 추출한 schema proposal이 연결되지 않음 | Released contract 이후 `mhtml-etl-gateway#66` | Planned | Immutable MHTML evidence → approved proposal → SDP receipt E2E |
| OM-011 | EA impact path에 governed OpenMetadata asset이 없음 | Released contract·SDP durable admission 이후 `enterprise-architecture-core#44` | Planned | Source authority/truth/provenance를 보존한 impact path와 idempotent projection receipt |
| OM-012 | Agent가 policy-filtered OpenMetadata context를 조회하지 못함 | SDP context bundle release 이후 `contextual-orchestrator#1042` | Planned | Injection-safe SDP bundle → orchestrator tool result → evidence-backed synthesis E2E |
| OM-013 | OpenMetadata release drift가 미래 adapter를 조용히 깨뜨릴 수 있음 | SDP compatibility-profile lane | #96 candidate로 일부 해소 | Automated exact-source schema diff, explicit profile addition, old-profile immutability, supported-release matrix |
| OM-014 | Connection, mapping, conflict, replay를 운영할 buyer workflow가 없음 | Runtime contract 이후 SDP admin/operator UX | Open | Figma ID/token ADR, Storybook normal/loading/empty/error/permission/conflict/replay state, keyboard/mobile/i18n E2E |
| OM-015 | 지원되는 OpenMetadata interoperability release가 없음 | SDP release lane | Open | Version bump, CHANGELOG release section, signed artifact, SBOM, provenance, upgrade/rollback runbook, compatibility matrix |
| OM-016 | External identity가 다른 tenant namespace를 선택할 수 있었음 | SDP PR #96 | Source repaired, merge evidence 대기 | Authenticated OIDC integration test, current-head security gate, protected integration |
| OM-017 | 독립 OpenMetadata installation이 external UUID에서 충돌할 수 있었음 | SDP PR #96 | Source repaired, merge evidence 대기 | Source-instance projection test, #97 receipt propagation, OM-002 durable uniqueness constraint |
| OM-018 | Upstream-valid sparse Table·EntityReference가 거부됐음 | SDP PR #96 | Source repaired, merge evidence 대기 | Exact upstream schema test와 current-head repository GREEN |
| OM-019 | Internal direct import가 release-profile admission을 우회할 수 있었음 | SDP PR #96 | Source repaired, merge evidence 대기 | Sink-level unverified-release RED/GREEN과 current-head repository GREEN |
| OM-020 | Router 직접 embedding 시 parser body budget을 우회할 수 있었음 | SDP PR #96 | Source repaired, merge evidence 대기 | Content-Length/chunked/direct-router 413 test와 current-head security GREEN |

## 첫 Cross-product vertical

첫 release-worthy buyer path는 다음과 같습니다.

```text
OpenMetadata Table·EntityLineage
→ authenticated exact release-profile admission
→ deterministic source·projection receipt
→ durable tenant/source-instance observation history
→ policy-filtered context event
→ EA impact path·Contextual Orchestrator context bundle
```

각 화살표가 immutable released contract를 소비하고 verifiable receipt를 생산해야 vertical이 닫힙니다. Issue, mutable branch, copied fixture, direct SQL query, manual JSON handoff는 완료 evidence가 아닙니다.

## Data·security invariant

- OpenMetadata는 CWL HR, billing, learning, psychometrics, security, EA 등 product-domain fact의 authority가 아닙니다.
- `observed`, `inferred`, `proposed`, `authoritative`, `superseded`, `rejected`를 구분합니다.
- External ID는 tenant와 source installation 범위에서 해석합니다.
- Request tenant는 verified actor tenant를 덮어쓰지 못합니다.
- Historical observation은 validity를 닫거나 supersede하며 hard delete하지 않습니다.
- Sample value, credential, token, DSN, SQL/DDL, query text, unrestricted extension payload를 general projection이나 context bundle에 넣지 않습니다.
- Unknown quality, freshness, ownership, optional identity field, mapping을 0이나 invented value로 바꾸지 않습니다.
- Cross-service SQL, mutable sibling source, provider database access, runtime implementation 복사를 금지합니다.
- LLM output은 truth status, ownership authority, policy, outbound write approval을 승격하지 못합니다.
- Source·projection fingerprint는 restricted metadata이며 tenant 밖으로 노출하지 않습니다.
- Normalization route는 non-mutating이며 durable admission은 별도 successor boundary입니다.

## Durable admission의 Performance·operability target

아래는 미래 durable slice의 acceptance target이며 현재 성능을 주장하는 수치가 아닙니다.

- 동일 snapshot 10,000회 replay 시 duplicate admitted revision 0건
- Reference dataset에서 Table observation 100,000개와 column/lineage relation 1,000,000개
- External network와 restricted raw-evidence upload를 제외한 admission API p95 20ms 이하
- Configured payload·column·reference·lineage limit에 비례하는 bounded memory
- Warm-cache-only benchmark 또는 validation 축소 금지
- Source outage, PostgreSQL restart, duplicate event, reversed event order, partial projection failure 복구
- Queue depth, projection lag, rejection reason, dead-letter count, replay count, receipt latency 관측
- Backup, point-in-time recovery, restore, rollback, contract downgrade rehearsal

## 갱신 규칙

OpenMetadata PR의 base, scope, status, release identity, contract version, owner boundary, verification result, successor order가 바뀌면 이 파일을 갱신합니다. Exact head는 검증 시 GitHub에서 조회합니다. Source가 존재할 때만 implemented, protected branch에 들어갔을 때만 integrated, immutable artifact에 executable contract와 evidence가 실렸을 때만 released라고 기록합니다.
