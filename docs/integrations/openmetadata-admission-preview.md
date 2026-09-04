# OpenMetadata admission preview

`table-snapshots:admission-preview`는 검증된 OpenMetadata Table·EntityLineage 입력을 catalog에 쓰기 전에, replay와 observation을 구분할 수 있는 receipt로 변환합니다. 이 endpoint는 PR #99 후보이며 보호된 `main` 병합과 immutable release 전에는 released capability가 아닙니다.

```http
POST /integrations/openmetadata/v1/table-snapshots:admission-preview
Authorization: Bearer <access token>
Content-Type: application/json
```

## 요청

```json
{
  "tenant_id": "tenant_acme",
  "source_instance_id": "metadata_primary",
  "source_release": "2.0.1-release",
  "observed_at": "2026-09-04T00:00:00Z",
  "table": {
    "id": "11111111-1111-4111-8111-111111111111",
    "name": "orders",
    "columns": [
      {
        "name": "order_id",
        "dataType": "UUID"
      }
    ]
  },
  "lineage": null
}
```

`source_instance_id`는 tenant 내부에서 OpenMetadata 설치를 구분하는 opaque identifier입니다. hostname, URL, DSN, token 또는 credential을 넣지 않습니다. `observed_at`은 timezone이 있어야 하며 UTC로 정규화됩니다.

Bearer token은 기존 OIDC/JWKS verifier로 검증합니다. `data-analyst`, `admin`, `platform-admin` 중 하나의 역할이 필요합니다. 검증된 actor tenant와 body tenant가 다르면 404를 반환해 다른 tenant의 integration resource 존재 여부를 드러내지 않습니다.

## 응답

```json
{
  "receipt_contract_version": "1.0.0",
  "digest_profile_id": "cwl-json-structural-sha256-v1",
  "admission_candidate_id": "urn:cwl:tenant_acme:sdp:openmetadata_admission_candidate:<hex>",
  "receipt_id": "urn:cwl:tenant_acme:sdp:openmetadata_admission_preview:<hex>",
  "admission_status": "accepted_for_review",
  "tenant_id": "tenant_acme",
  "source_instance_id": "metadata_primary",
  "source_authority": "openmetadata",
  "source_release": "2.0.1",
  "compatibility_profile_id": "openmetadata-table-lineage-2.0.1",
  "upstream_repository": "open-metadata/OpenMetadata",
  "upstream_revision": "bf621b166ec12e8c99fcb1c1443442723386fa41",
  "observed_at": "2026-09-04T00:00:00Z",
  "external_entity_id": "11111111-1111-4111-8111-111111111111",
  "source_snapshot_digest": "sha256:<64 lowercase hex>",
  "projection_digest": "sha256:<64 lowercase hex>",
  "replay_key": "sha256:<64 lowercase hex>",
  "omitted_fields": [],
  "raw_payload_persisted": false,
  "catalog_mutation_performed": false,
  "omitted_source_values_copied": false,
  "projection": {}
}
```

`projection`은 응답 예시에서 줄였지만 실제 OpenAPI contract에는 전체 `OpenMetadataTableProjection`이 들어갑니다.

## 각 identity의 용도

### `source_snapshot_digest`

제출된 `table`과 `lineage` 구조 전체를 대상으로 합니다. Sample row·SQL·DDL처럼 safe projection에서 제외한 값도 digest에는 영향을 주지만 receipt에 값 자체는 복사하지 않습니다.

### `projection_digest`

전체 safe projection을 대상으로 합니다. Tenant, source installation, exact compatibility profile, upstream revision과 external entity identity가 포함됩니다. 같은 source bytes라도 `source_instance_id`가 다르면 projection ID와 digest도 달라집니다.

### `replay_key`와 `admission_candidate_id`

동일 tenant·source installation·source observation·safe projection이 같은 candidate인지 판정합니다. Future durable admission store의 idempotency key입니다. `observed_at`은 포함하지 않으므로 같은 candidate를 나중에 재관측해도 candidate ID는 유지됩니다.

### `receipt_id`

Candidate와 UTC observation instant를 결합한 사건 ID입니다. 동일 instant의 exact retry는 같은 receipt ID를 내고, 같은 candidate를 나중에 관측하면 다른 receipt ID를 냅니다. 서로 다른 timezone 표기로 같은 instant를 표현하면 같은 receipt ID가 됩니다.

## Tamper 검증

`OpenMetadataAdmissionReceipt.model_validate()`는 transport 이후 다음 관계를 다시 계산합니다.

- top-level source·release·provenance·external ID와 nested projection의 일치
- tenant·source instance·external UUID 기반 projection ID
- projection digest
- source/projection digest를 포함한 replay key
- replay key 기반 candidate ID
- candidate와 observation time 기반 receipt ID

Raw source는 receipt에 없으므로 receipt만으로 `source_snapshot_digest`의 원문을 재계산하지는 못합니다. 대신 source digest를 바꾸면 replay key가 불일치합니다. Durable admission 단계에서는 제한 evidence store의 source reference와 digest를 추가로 대조해야 합니다.

## Strict transport boundary

Normalization과 admission-preview 두 endpoint 모두 다음 입력을 operation 전에 거부합니다.

- 8 MiB를 넘는 request body, chunked body 포함
- invalid UTF-8
- malformed JSON 또는 parser recursion overflow
- 같은 object의 duplicate member
- NaN, Infinity, -Infinity
- lone Unicode surrogate

Application-level 제한만으로 upstream proxy의 buffering 비용을 막을 수는 없으므로 production ingress에도 동일하거나 더 작은 body limit을 설정해야 합니다.

## `accepted_for_review`의 의미

포함하는 의미:

- exact OpenMetadata `2.0.1` compatibility profile을 통과함
- Table·lineage ACL 검증과 safe projection 생성이 가능함
- candidate·receipt identity를 결정적으로 계산함
- receipt 자체의 tamper 관계를 검증할 수 있음

포함하지 않는 의미:

- catalog row insertion 또는 publication
- steward approval
- raw payload retention
- OpenMetadata와의 live API 통신
- payload origin의 cryptographic attestation
- `authoritative` domain truth 승격

## 후속 durable admission

다음 aggregate를 별도로 구현합니다.

```text
external_metadata_source
external_observation_receipt
external_snapshot_record
metadata_admission_candidate
metadata_projection_revision
metadata_supersession_record
```

Candidate uniqueness와 observation receipt uniqueness를 분리합니다.

```text
candidate uniqueness
= tenant + source instance + receipt contract version + replay key

observation uniqueness
= tenant + source instance + receipt contract version + receipt ID
```

동시 제출에서는 candidate 하나만 생성하되 서로 다른 observation receipt는 append-only로 보존해야 합니다. 세부 근거와 encoding contract는 ADR-0002를 따릅니다.
