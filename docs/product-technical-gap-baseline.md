# Semantic Data Portal 제품·기술 Gap 기준선

- **제품:** `ContextualWisdomLab/semantic-data-portal`
- **기준일:** 2026-09-04
- **보호된 통합 대상:** `main`
- **OpenMetadata 구현 소유자:** Semantic Data Portal
- **주요 delivery issue:** #95
- **Normalization 후보:** PR #96, Draft
- **Admission receipt repair 후보:** PR #99, Draft
- **Stale predecessor:** PR #97, #99의 완전 승계 전까지 유지

이 문서는 OpenMetadata를 연결했다는 선언이 아니라, 구매자가 실제로 사용할 수 있는 상호운용 vertical이 어디까지 닫혔는지를 기록합니다. Source가 존재하거나 review bot이 통과한 것만으로는 released capability가 아닙니다. 보호된 source, immutable version, current exact-head checks, executable contract evidence와 consumer adoption을 함께 확인합니다.

PR head SHA를 이 문서에 고정하면 문서 수정 순간 낡으므로 authoritative head는 GitHub PR metadata에서 조회합니다. 이전 head의 check·review·coverage 결과는 다음 head로 이전하지 않습니다.

## 권위와 Context 경계

| 관심사 | Canonical owner | SDP 책임 | 금지하는 결합 |
|---|---|---|---|
| Data·AI catalog context | `semantic-data-portal` | Metadata admission, governance, search, policy-filtered publication | Domain product가 SDP DB에 직접 write |
| OpenMetadata interoperability | `semantic-data-portal` | Exact-version ACL, source·projection evidence, controlled synchronization | 모든 제품이 독립 OpenMetadata SDK·credential을 보유 |
| Cross-product external observation contract | `context-graph-contracts` | Immutable release가 생기면 exact version으로 소비 | Mutable sibling PR head 또는 파일 복사 |
| Enterprise architecture decision | `enterprise-architecture-core` | Governed Data·AI projection 제공 | EA Core가 OpenMetadata·SDP DB를 직접 조회 |
| Physical database observation | `pg-erd-cloud` | Released schema observation과 receipt 수용 | Physical truth를 OpenMetadata·SDP로 이전 |
| MHTML extraction·schema proposal | `mhtml-etl-gateway` | Validated observed/proposed schema·lineage 수용 | Gateway가 business truth를 직접 publish |
| Agent context | `contextual-orchestrator` | Policy-filtered context bundle 제공 | External text가 instruction·tool·routing을 변경 |
| Ontology generation·release | `ConceptWeave` | Released ontology label·mapping 소비 | Product-domain truth를 공용 ontology로 이전 |
| Identity·federation | `keyverse` | Verified OIDC actor·tenant·role 소비 | Caller-controlled tenant 또는 local credential authority |
| Outbound HTTP | `EgressWeave` 또는 released canonical egress | 향후 OpenMetadata API access 위임 | 임의 URL·request credential·직접 network client |

## 현재 후보 stack

### PR #96 — authenticated read-only normalization

Source 기준으로 다음이 구현되어 있습니다.

- OpenMetadata `2.0.1`·`2.0.1-release`를 하나의 immutable compatibility profile로 정규화
- Upstream repository·exact revision·schema path 보존
- Bearer OIDC/JWKS 검증과 integration role admission
- Verified actor tenant와 body tenant의 일치, cross-tenant 404
- Tenant·`source_instance_id`·external UUID를 결합한 projection identity
- Upstream-valid sparse Table·EntityReference 수용, 선택값의 invented default 금지
- Snapshot-wide UUID/type/name/FQN 일관성
- Bounded nested column, safe aggregate profile, table·column lineage
- Sample row, SQL/DDL, query·join, column profile, extension, transformation text 제외
- True cycle·shared alias 구분, collection/depth/text/URL/UUID/finite-number guard
- Chunked body를 포함한 8 MiB router-level 제한
- README, ADR, integration guide, compliance matrix와 연구 근거

PR #96은 Draft이며 current exact-head hosted gate가 terminal success가 되기 전에는 integrated 또는 released로 표현하지 않습니다.

### PR #99 — secured admission candidate와 observation receipt

PR #97의 유효 목적은 유지하되 오래된 ancestry에서 발생한 보안·계약 회귀를 그대로 가져오지 않도록 현재 #96 위에서 다시 구현했습니다.

구현 후보 범위:

- `POST /integrations/openmetadata/v1/table-snapshots:admission-preview`
- #96과 동일한 Bearer, role, verified tenant, strict JSON, 8 MiB body-limit 경계
- `cwl-json-structural-sha256-v1` exact-byte digest profile
- Submitted Table·lineage 전체를 묶는 `source_snapshot_digest`
- Safe projection 전체를 묶는 `projection_digest`
- Candidate deduplication용 replay key와 `admission_candidate_id`
- Candidate와 UTC observation instant를 묶는 `receipt_id`
- Retry와 later re-observation의 identity 분리
- Nested projection·digest·replay·candidate·receipt identity 재계산
- Source payload와 분리된 deep projection snapshot
- Raw payload persistence, catalog mutation, external network, credential, publication, authority promotion 없음

원본 #97에서 폐기한 delta:

- 인증·tenant binding·body limit이 없는 오래된 router
- `source_instance_id`를 projection까지 전달하지 않는 호출
- Tamper test만 있고 실제 receipt validator가 없는 model
- Invalid tenant·release를 검사하기 전에 source 전체를 hashing하는 순서
- Source instance가 달라도 projection digest가 같다는 잘못된 기대
- 구현과 다른 16 MiB 문서 표기

PR #97은 #99가 파일·행동·문서·테스트 기준으로 유효 delta를 완전히 승계하고 exact-head gate를 통과하기 전까지 닫지 않습니다.

## Evidence 판정

### 확보된 설계·소스 증거

- PR #96 review finding은 현재 source와 upstream `2.0.1-release` schema를 대조해 수리·해소
- Table required set는 `id`, `name`, `columns`
- EntityReference required set는 `id`, `type`
- PR #99 RED contract가 production 구현 전에 생성됨
- Golden structural digest vector와 hostile scalar/container cases
- Source/projection/replay/candidate/receipt tamper tests
- Same-instant retry, later re-observation, timezone-equivalent instant tests
- Strict transport JSON과 authenticated cross-tenant route tests
- ADR-0002, 운영 가이드, README, compliance matrix, CHANGELOG 갱신

### 아직 없는 release evidence

- PR #96과 #99 current exact-head repository Tests terminal success
- Changed production statement·branch coverage 100%
- Public API docstring 100%
- Current-head fuzz, SAST, Security Scan, OSV/dependency, Scorecard와 required central gates terminal success
- Current-head independent approval
- Protected `main` ordinary merge
- Immutable package/version/SBOM/provenance
- Rust·TypeScript digest conformance
- Live OpenMetadata instance E2E

Queued, pending, cancelled, skipped, neutral, missing, startup-failed 또는 predecessor workflow는 non-passing입니다. Bot review status는 executable gate를 대체하지 않습니다.

## 연구·표준 근거

ADR-0001은 autonomous source와 consumer 사이에 mediator를 둔다는 Wiederhold의 구조와, release별 schema matching·evaluation이 필요하다는 Bernstein·Madhavan·Rahm의 연구를 OpenMetadata ACL에 연결합니다.

ADR-0002는 RFC 8259 JSON 문법, IEEE 754 binary64 identity, FIPS 180-4 SHA-256과 RFC 8785의 canonicalization 요구를 검토합니다. 현재 구현은 RFC 8785 JCS를 부분 구현했다고 주장하지 않고, 실제로 검증한 structural grammar에 별도 profile ID를 부여합니다.

- Bernstein, P. A., Madhavan, J., & Rahm, E. (2011). Generic schema matching, ten years later. *Proceedings of the VLDB Endowment, 4*(11), 695–701. https://doi.org/10.14778/3402707.3402710
- Wiederhold, G. (1992). Mediators in the architecture of future information systems. *Computer, 25*(3), 38–49. https://doi.org/10.1109/2.121508
- Bray, T. (2017). *The JavaScript Object Notation (JSON) data interchange format* (RFC 8259). Internet Engineering Task Force. https://doi.org/10.17487/RFC8259
- Rundgren, A., Jordan, B., & Erdtman, S. (2020). *JSON Canonicalization Scheme (JCS)* (RFC 8785). Internet Engineering Task Force. https://doi.org/10.17487/RFC8785

재배포 권한을 확인하지 않은 논문 PDF는 저장소에 복제하지 않습니다. 상세 적용은 `docs/doctoring/OPENMETADATA_REFERENCES.md`, ADR-0001과 ADR-0002에 기록합니다.

## OpenMetadata Gap register

| Gap ID | 구매자 문제 | Owner·delivery path | 현재 상태 | Exit evidence |
|---|---|---|---|---|
| OM-001 | Source와 safe projection의 관계·retry·observation을 증명할 receipt가 없음 | SDP PR #99 | Source 후보 구현, exact-head gate 대기 | Golden digest, tamper validation, secured route, no-mutation proof, protected merge·release |
| OM-002 | Restart-safe admission·replay history가 없음 | #99 이후 SDP successor | Open | 3NF source/observation/candidate/projection/supersession, Postgres integration, migration·rollback |
| OM-003 | Raw source evidence를 제한적으로 보존할 경로가 없음 | SDP evidence successor | Open | Encrypted immutable object evidence, tenant/purpose authorization, retention·legal hold |
| OM-004 | OpenMetadata ChangeEvent를 안전하게 소비하지 못함 | SDP webhook successor | Open | Signature, inbox dedup, version ordering, bounded retry, dead letter, replay |
| OM-005 | Live OpenMetadata metadata를 조회하지 못함 | SDP connector successor | Open | Credential registry, canonical egress, capability discovery, pagination, rate/backoff, receipt |
| OM-006 | 승인된 변경을 OpenMetadata로 동기화하지 못함 | SDP controlled-write successor | Open | Steward approval, field authority matrix, ETag/version precondition, conflict·rollback receipt |
| OM-007 | Table·Column·EntityLineage 이외 자산이 없음 | SDP entity-profile successor | Open | Pipeline, dashboard/chart/metric, ML model/feature/agent, quality/test/incident profile |
| OM-008 | Provider-neutral cross-product contract가 release되지 않음 | `context-graph-contracts#26` | Foundation blocked | Immutable schema/SDK, conformance, source provenance, consumer exact-version tests |
| OM-009 | Physical schema producer가 연결되지 않음 | `pg-erd-cloud#1072` | Planned | PostgreSQL schema observation → SDP admission → OpenMetadata-ready projection E2E |
| OM-010 | MHTML schema proposal이 연결되지 않음 | `mhtml-etl-gateway#66` | Planned | Immutable source → approved proposal → SDP receipt E2E |
| OM-011 | EA impact path에 governed OpenMetadata asset이 없음 | `enterprise-architecture-core#44` | Planned | Authority/truth/provenance를 보존한 impact path와 idempotent receipt |
| OM-012 | Agent가 policy-filtered OpenMetadata context를 쓰지 못함 | `contextual-orchestrator#1042` | Planned | Injection-safe bundle → tool result → evidence-backed synthesis E2E |
| OM-013 | Release drift가 조용히 adapter를 깨뜨릴 수 있음 | SDP compatibility lane | #96으로 일부 해소 | Exact-source schema diff, explicit profile addition, old-profile immutability |
| OM-014 | Connection·mapping·conflict·replay 운영 UI가 없음 | Runtime contract 이후 SDP UX | Open | Figma/token ADR, Storybook normal/loading/empty/error/permission/conflict/replay, i18n E2E |
| OM-015 | Immutable interoperability release가 없음 | SDP release lane | Open | Version, signed artifact, SBOM, provenance, compatibility matrix, upgrade·rollback runbook |
| OM-016 | 서로 다른 installation이 UUID에서 충돌할 수 있었음 | SDP PR #96/#99 | Source repaired, release evidence 대기 | Projection·receipt source-instance tests, durable uniqueness |
| OM-017 | Receipt를 수정해도 model이 수용할 수 있었음 | SDP PR #99 | Source repaired, exact-head gate 대기 | Projection/replay/candidate/receipt tamper suite |
| OM-018 | Strict transport JSON이 operation별로 달랐음 | SDP PR #99 | Source repaired, exact-head gate 대기 | Normalize·admission-preview duplicate/NaN/UTF-8/surrogate tests |
| OM-019 | Source hashing이 cheap identity validation보다 먼저 실행될 수 있었음 | SDP PR #99 | Source repaired, exact-head gate 대기 | Hash-not-called RED/GREEN regression |
| OM-020 | Python digest contract를 다른 언어가 재현할 normative vector가 없음 | `context-graph-contracts` + consumer SDK | Python vector 후보만 존재 | Released profile, Rust/TypeScript golden-vector conformance |

## 첫 release-worthy cross-product vertical

```text
OpenMetadata Table·EntityLineage
→ authenticated exact release-profile normalization
→ source/projection admission candidate + observation receipt
→ durable tenant/source-instance history
→ released provider-neutral context event
→ EA impact path·Contextual Orchestrator context bundle
```

각 화살표가 immutable released contract를 소비하고 verifiable receipt를 생산해야 vertical이 닫힙니다. Issue, mutable branch, copied fixture, direct SQL, manual JSON handoff는 완료 evidence가 아닙니다.

## Data·security invariant

- OpenMetadata는 CWL HR, billing, learning, psychometrics, security, EA domain truth의 authority가 아닙니다.
- `observed`, `inferred`, `proposed`, `authoritative`, `superseded`, `rejected`를 구분합니다.
- External ID는 tenant와 source installation 범위에서 해석합니다.
- Request tenant는 verified actor tenant를 덮어쓰지 못합니다.
- Historical observation은 validity를 닫거나 supersede하며 hard delete하지 않습니다.
- Sample value, credential, token, DSN, SQL/DDL, query, unrestricted extension을 general projection·receipt·context bundle에 넣지 않습니다.
- Unknown quality·freshness·ownership·optional identity·mapping을 0이나 invented value로 바꾸지 않습니다.
- Cross-service SQL, mutable sibling source, provider DB access, runtime implementation 복사를 금지합니다.
- LLM output은 truth, ownership, policy 또는 outbound approval을 승격하지 못합니다.
- Source·projection digest는 restricted metadata이며 tenant 밖으로 노출하지 않습니다.
- `accepted_for_review`는 validation result이지 admission·approval·publication이 아닙니다.

## Durable admission acceptance target

아래 수치는 미래 durable slice의 목표이며 현재 성능을 주장하지 않습니다.

- 동일 source candidate 10,000회 replay 시 duplicate candidate revision 0건
- 서로 다른 observation instant는 append-only receipt로 모두 보존
- Table observation 100,000개, column·lineage relation 1,000,000개 reference fixture
- Hot source instance에 대한 concurrent UPSERT·lock contention profile과 retry evidence
- Admission API p95 ≤20 ms 목표는 raw snapshot 크기 구간별로 측정하고 hash 비용을 제외하거나 표본을 축소하지 않음
- Crash·restart·migration rollback 후 replay identity와 history 불변

## 실행 순서

1. PR #96의 current exact-head checks·review·approval을 완료하고 보호된 `main`에 병합합니다.
2. PR #99를 그 merge result 위로 non-force restack합니다.
3. PR #99와 #97의 valid delta를 비교하고 #99 exact-head gate를 완료합니다.
4. 완전 승계가 증명된 뒤에만 #97을 successor supersession으로 닫습니다.
5. PR #99를 병합·release한 뒤 3NF durable admission을 TDD로 구현합니다.
6. `context-graph-contracts`에 provider-neutral observation·receipt contract를 protected source에서 release합니다.
7. `pg-erd-cloud`, MHTML gateway, EA Core, Contextual Orchestrator가 그 exact version만 채택합니다.
8. 실제 OpenMetadata 2.x instance로 end-to-end와 rollback을 검증합니다.
