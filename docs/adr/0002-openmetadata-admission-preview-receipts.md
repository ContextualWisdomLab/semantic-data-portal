# ADR-0002: OpenMetadata admission candidate와 observation receipt를 분리한다

- **상태:** Proposed
- **결정일:** 2026-09-04
- **결정 소유자:** Semantic Data Portal
- **관련 이슈:** #95
- **선행 결정:** ADR-0001
- **구현 후보:** PR #99
- **대체 대상:** PR #97의 유효 delta를 검증 후 승계

## 문제

ADR-0001의 OpenMetadata anti-corruption layer는 Table과 EntityLineage를 안전한 `observed` projection으로 바꾼다. 그러나 projection만으로는 다음 질문에 답할 수 없다.

- 어느 tenant의 어떤 OpenMetadata 설치에서 관측했는가?
- 제출된 source snapshot과 안전한 projection은 각각 어떤 바이트 의미를 가졌는가?
- 같은 payload의 재시도와, 같은 candidate를 나중에 다시 관측한 사건은 어떻게 구분하는가?
- 전송 이후 receipt 내부 값이 바뀌지 않았음을 어떻게 검증하는가?
- sample row, SQL, DDL, extension처럼 projection에서 제외한 값의 변경을 raw payload 복사 없이 어떻게 감지하는가?

`json.dumps(sort_keys=True)` 결과를 그대로 해시하면 Python 구현에는 편리하지만 Rust와 TypeScript가 수치·문자열·키 정렬을 동일하게 재현한다는 계약이 없다. 반대로 raw payload를 receipt에 넣으면 일반 metadata 경계로 민감한 원문이 확산된다.

기존 PR #97은 필요한 identity·digest 아이디어를 담았지만, 오래된 #96 ancestry를 사용해 Bearer 인증, verified tenant binding, request-body 제한과 source-instance projection identity를 되돌릴 수 있었다. 또한 tamper 검증 테스트가 요구하는 재계산 validator가 receipt model에 없었다. 따라서 그 branch를 그대로 restack하지 않고 현재 보안 경계에서 successor를 재구축한다.

## 결정

Semantic Data Portal은 catalog mutation 이전에 다음 endpoint로 **비영속 admission preview**를 제공한다.

```http
POST /integrations/openmetadata/v1/table-snapshots:admission-preview
Authorization: Bearer <Keyverse/OIDC access token>
Content-Type: application/json
```

처리 순서는 다음과 같다.

1. route class가 chunked body를 포함해 8 MiB 상한을 적용한다.
2. strict JSON parser가 invalid UTF-8, duplicate member, NaN·Infinity, lone surrogate와 parser recursion failure를 거부한다.
3. 기존 OIDC/JWKS verifier가 Bearer token을 검증하고 integration role을 확인한다.
4. verified actor tenant와 body tenant가 다르면 자원 존재를 노출하지 않고 404로 거부한다.
5. domain normalizer가 tenant, source instance, exact OpenMetadata compatibility profile, Table과 lineage 계약을 검증한다.
6. 제출 source structure와 안전한 projection에 서로 다른 digest를 계산한다.
7. replay key와 `admission_candidate_id`를 계산한다.
8. candidate와 UTC observation instant로 `receipt_id`를 계산한다.
9. receipt model이 nested projection, digest, replay key, candidate ID와 receipt ID를 다시 계산해 transport tampering을 거부한다.
10. raw payload, catalog row, credential, outbound request는 생성하지 않는다.

## Aggregate와 identity

### Source snapshot

`source_snapshot_digest`는 아래 구조를 대상으로 한다.

```json
{
  "table": "submitted Table value",
  "lineage": "submitted EntityLineage value or null"
}
```

Projection에서 제외한 sample row나 SQL도 digest에는 영향을 주지만 receipt에는 값 자체가 들어가지 않는다. Digest 역시 restricted metadata이므로 future durable store에서는 tenant·purpose 범위로 취급한다.

### Safe projection

`projection_digest`는 JSON mode의 전체 `OpenMetadataTableProjection`을 대상으로 한다. 이 projection에는 `tenant_id`에서 파생한 scope, `source_instance_id`, external UUID, exact release profile과 upstream revision이 포함된다. 따라서 같은 payload라도 source installation이 다르면 projection identity와 digest가 달라진다.

### Admission candidate

Candidate는 다음을 결합한다.

```text
receipt contract version
+ digest profile ID
+ tenant ID
+ source instance ID
+ source authority
+ canonical source release
+ compatibility profile ID
+ upstream repository and revision
+ external entity ID
+ source snapshot digest
+ projection digest
```

`observed_at`은 candidate identity에 포함하지 않는다. 같은 candidate를 다시 관측해도 replay key와 `admission_candidate_id`는 유지된다.

```text
urn:cwl:{tenant_id}:sdp:openmetadata_admission_candidate:{replay_key_hex}
```

### Observation receipt

Receipt는 candidate와 observation instant를 결합한다.

```text
receipt contract version
+ admission candidate ID
+ observed_at normalized to YYYY-MM-DDTHH:MM:SS.ffffffZ
```

동일 candidate와 동일 instant의 delivery retry는 같은 `receipt_id`를 사용한다. 같은 candidate를 이후에 다시 관측하면 candidate identity는 유지하되 receipt ID는 달라진다.

```text
urn:cwl:{tenant_id}:sdp:openmetadata_admission_preview:{observation_digest_hex}
```

## Structural digest profile

`cwl-json-structural-sha256-v1`은 RFC 8785 JCS가 아니다. 부분 구현을 표준으로 오인시키지 않고, 현재 CWL이 실제로 검증하는 구조 encoding을 명시한다.

| 값 | Encoding |
|---|---|
| `null` | `n` |
| Boolean | `b1` 또는 `b0` |
| signed 64-bit integer | `i` + 10진수 + `;` |
| finite binary64 | `f` + IEEE-754 big-endian 16자리 lowercase hex + `;` |
| string | `s` + UTF-8 byte length + `:` + strict UTF-8 bytes |
| array | `a` + element count + `[` + source order values + `]` |
| object | `o` + member count + `{` + UTF-8 byte order key/value + `}` |

다음 값은 fail-closed로 거부한다.

- signed 64-bit 범위 밖의 integer
- NaN과 ±Infinity
- lone surrogate
- non-string object key
- tuple, set, custom container
- active-path cycle
- 64단계를 넘는 nesting

`tests/test_openmetadata_structural_digest.py`의 exact byte vector가 이 profile의 normative fixture다. Encoding tag·수치 표현·정렬·bound를 바꾸면 기존 receipt를 재해석하지 않고 새 digest profile ID를 발행한다.

## Tamper 검증 범위

Receipt 재수신 시 다음 값의 정합성을 다시 계산한다.

- top-level source instance, authority, release profile, upstream revision와 nested projection
- tenant·source instance·external UUID로 만든 projection ID
- nested projection의 structural digest
- source/projection digest를 포함한 replay key
- replay key에서 만든 candidate ID
- candidate와 observation instant에서 만든 receipt ID

`source_snapshot_digest`는 raw source가 receipt에 없으므로 receipt 단독으로 원문까지 재계산할 수 없다. 대신 그 digest를 바꾸면 replay key 검증이 실패한다. Future durable admission은 별도 제한 저장소의 source evidence reference와 digest를 대조해야 한다.

## 상태 의미

`accepted_for_review`는 exact compatibility·shape·identity·digest 계산을 통과했다는 뜻이다. 다음을 의미하지 않는다.

- catalog admission 또는 publication
- steward approval
- OpenMetadata origin attestation
- domain truth의 `authoritative` 승격
- raw payload retention
- outbound synchronization

## 검토한 대안

### PR #97을 그대로 merge/rebase

기각했다. 오래된 router를 다시 적용하면 이미 보강된 authentication·tenant·body-limit·source-instance 계약을 회귀시킨다. 유효 delta는 #99가 현재 #96에서 다시 구현하고 비교 검증한다.

### Python JSON serialization을 해시

기각했다. 언어별 number와 ordering 차이를 계약으로 통제하지 못한다.

### RFC 8785 JCS라고 표기

기각했다. JCS는 유효한 향후 선택지지만 ECMAScript number serialization과 UTF-16 property ordering을 완전하게 구현·검증하지 않은 현재 코드를 JCS로 부르는 것은 잘못이다.

### Raw payload를 receipt에 포함

기각했다. sample, query, DDL, extension과 변환식이 일반 metadata plane으로 복제된다.

### Candidate ID와 observation receipt ID 통합

기각했다. 같은 candidate의 서로 다른 관측 사건이 하나의 ID에 다른 timestamp를 갖게 되어 append-only evidence와 idempotency를 동시에 지킬 수 없다.

## 결과와 한계

이 결정으로 Python consumer는 candidate deduplication과 observation audit을 구분하고, receipt transport tampering을 자체 검증할 수 있다. 다만 #99는 아직 Draft이며 durable evidence가 아니다. Rust·TypeScript conformance, 3NF persistence, concurrent UPSERT·locking, raw evidence retention, signed ChangeEvent, canonical egress와 writeback은 후속 결정이다.

PR #97은 #99가 유효 delta를 모두 승계하고 current exact-head gate를 통과하기 전까지 닫지 않는다.

## 검증 기준

- RED commit `de152b16f73c9fa774200018892e13582c1e9b21` 이후 production 구현
- strict transport JSON과 8 MiB chunked body limit
- source-instance-scoped projection·candidate identity
- exact golden structural bytes
- source/projection/replay/candidate/receipt tamper rejection
- retry와 re-observation 분리
- omitted source change가 source digest만 바꾸며 값은 receipt에 들어가지 않음
- Bearer authentication과 cross-tenant 404 유지
- new production statement·branch coverage 100%
- public API docstring coverage 100%
- exact-head Tests·fuzz·SAST·Security Scan·review·approval terminal success

## 참고 문헌

Bray, T. (2017). *The JavaScript Object Notation (JSON) data interchange format* (RFC 8259). Internet Engineering Task Force. https://doi.org/10.17487/RFC8259

Institute of Electrical and Electronics Engineers. (2019). *IEEE standard for floating-point arithmetic* (IEEE Std 754-2019). https://doi.org/10.1109/IEEESTD.2019.8766229

National Institute of Standards and Technology. (2015). *Secure Hash Standard (SHS)* (FIPS PUB 180-4). https://doi.org/10.6028/NIST.FIPS.180-4

Rundgren, A., Jordan, B., & Erdtman, S. (2020). *JSON Canonicalization Scheme (JCS)* (RFC 8785). Internet Engineering Task Force. https://doi.org/10.17487/RFC8785
