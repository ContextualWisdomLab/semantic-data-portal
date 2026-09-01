# Dataset distribution semantic identifiers 결정 기록

## Decision

catalog bounded context는 dataset distribution의 identity, representation format, access endpoint 의미를 소유한다. 따라서 조직이 소유하는 Python identifier는 generic one-word 이름인 `id`, `format`, `endpoint` 대신 `distribution_id`, `distribution_format`, `distribution_endpoint`를 authoritative internal vocabulary로 사용한다.

이 규칙은 casing 강제가 아니라 semantic specificity 규칙이다. Python에서는 idiomatic `snake_case`를 유지하며, 다른 ecosystem에서 multiword camelCase 또는 PascalCase가 관례라면 그대로 유효하다.

## Compatibility boundary

기존 catalog HTTP/OpenAPI/SHACL-facing distribution representation은 `id`, `format`, `endpoint` key를 사용한다. 이 key들은 이미 consumer-visible contract이므로 silent rename하지 않고 외부 compatibility boundary로 유지한다.

`DatasetDistribution`은 Pydantic alias를 사용해 historical input key를 계속 수용하고, wrap model serializer를 통해 historical wire representation을 출력한다. serializer는 `model_dump(include=...)`와 `model_dump(exclude=...)`의 field filtering도 보존한 뒤 internal semantic field를 wire key로 변환한다. compatibility property는 기존 Python attribute read/write를 유지하지만, 조직 소유 internal construction은 qualified name을 사용한다. 즉 anti-corruption boundary 내부의 ubiquitous language는 구체적으로 유지하면서 기존 external consumer의 wire schema는 바꾸지 않는다.

Nested `Dataset.model_dump()` output도 명시적으로 검증한다. catalog list/detail/create/publish/patch endpoint가 `Dataset` object를 직접 serialize하므로 nested distribution이 계속 `{id, format, endpoint}` 형태로 출력되는지 compatibility regression으로 고정한다.

## TDD evidence

regression-first commit `38fec1397ffbff5cc78c9630cee8ea1b726ca07d`는 production 변경 전에 semantic model field를 요구하는 contract test를 추가했다. 이후 source repair에서 semantic model field를 도입하고 buyer-demo constructor를 전파했으며 legacy wire serialization을 추가했다. 후속 regression은 legacy Python compatibility, nested dataset serialization, 그리고 `include`/`exclude` field filtering 계약을 함께 고정한다.

Focused verification command:

```bash
PYTHONPATH=src pytest tests/test_dataset_distribution_naming_contract.py
```

Repository verification command:

```bash
PYTHONPATH=src pytest
```

## Persistence and database impact

Persistence schema 변경은 없다. `DatasetDistribution`은 `sdp_core`의 Pydantic catalog contract이며, 이번 변경은 Postgres/SQLite evidence-store table, foreign key, index, constraint, ORM mapping, UPSERT path, partitioning, locking, read/write separation을 변경하지 않는다. 따라서 data migration 또는 rollback DDL도 필요하지 않다.

## Naming follow-up boundary

이번 변경은 catalog의 모든 one-word property를 기계적으로 rename하지 않는다. 후속 repair는 각각 bounded-context ownership, consumer compatibility, blast radius를 별도로 확인해야 한다. 외부 protocol이나 기존 public contract가 요구하는 generic vocabulary는 breaking change가 되는 경우 adapter boundary에 유지하고, 조직이 소유하는 runtime vocabulary는 semantic owner가 명확할 때 qualified multiword name으로 사용한다.
