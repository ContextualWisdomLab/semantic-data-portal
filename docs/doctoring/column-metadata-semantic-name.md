# Column metadata semantic name compatibility

## 결정

`ColumnMetadata`는 catalog schema의 개별 column을 표현하는 ContextualWisdomLab-owned domain contract다. 기존 authoritative Python field인 `name`은 어떤 object의 이름인지 드러내지 않는 one-word generic identifier이므로 내부 ubiquitous language를 `column_name`으로 구체화한다.

`docs/prd-trd.md`는 schema metadata를 `columnNames`로 명시하고 있으며, catalog/search/query 경계에서도 dataset column이 독립적인 domain concept로 사용된다. 따라서 arbitrary prefix가 아니라 기존 bounded-context language인 `column` + `name`을 채택한다.

## Compatibility / anti-corruption boundary

기존 catalog HTTP/OpenAPI payload와 schema-history snapshot은 `{"name": ...}` 형태를 이미 사용하므로 wire key `name`은 breaking change 없이 유지한다. `ColumnMetadata`는 Pydantic `alias="name"`, `populate_by_name=True`, explicit `model_serializer`를 사용해 외부 `name`을 받아들이고 내보내면서 organization-owned Python code에서는 `column_name`을 authoritative field로 사용한다. Legacy Python consumer를 위한 `.name` property는 adapter boundary로만 남긴다.

Internal caller는 `src/sdp_core/demo_seed.py`, `src/sdp/seed.py`, `src/sdp/browse.py`, `src/sdp/catalog.py`, `src/sdp/orchestrator.py`와 관련 tests에서 `column_name` vocabulary로 전환한다. API response와 persisted schema-history representation의 `name` key는 compatibility contract로 유지한다.

## Persistence / migration impact

이 변경은 database DDL 변경이 아니다. Table, column, index, foreign key, constraint, sequence, view, ORM mapping, UPSERT path, partition key, lock/read-write separation은 변경하지 않는다. Existing in-memory schema-history snapshot도 serializer를 통해 계속 `name` key를 사용하므로 persisted representation migration이나 rollback DDL이 필요하지 않다.

## Verification

`tests/test_column_metadata_naming_contract.py`는 authoritative model field가 `column_name`이고 bare `name`이 model field가 아님을 고정한다. 동시에 legacy `name=` deserialization, `.name` compatibility access, `model_dump()` serialization, nested `Dataset` serialization에서 기존 wire key가 유지되는지 검증한다. `tests/test_catalog.py`는 schema patch 이후 내부 caller가 `column_name`을 사용하는 lifecycle regression을 유지한다.
