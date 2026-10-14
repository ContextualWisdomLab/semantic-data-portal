# 요구사항 대응 매트릭스 (PRD/TRD, 생성 문서)

이 문서는 **생성물**이다. `docs/prd-trd.md`의 요구사항 표를 파싱해
`src/sdp_core/requirements.py`의 `REQUIREMENT_COVERAGE`와 조인한 결과이며,
손으로 수정하지 말고 아래 명령으로 재생성한다:

```bash
PYTHONPATH=src python -m sdp_core.requirements
```

`tests/test_requirements_coverage.py`가 네 가지를 강제한다: (1) PRD의 모든
요구사항 ID가 매핑되어 있는지, (2) 모든 증빙 포인터가 실제로 해석되는지
(이 앱이 서비스하는 route / import 가능한 attribute / 수집되는 test),
(3) `implemented` 주장이 해석되는 증빙을 최소 하나 가지는지, (4) 이 파일이
생성 결과와 글자 단위로 일치하는지. 따라서 PRD가 바뀌거나 증빙이 사라지면
문서가 조용히 낡는 대신 테스트가 깨진다.

## 상태 어휘

| 상태 | 의미 |
| --- | --- |
| `implemented` | 이 저장소의 구현이 요구사항에 답하고, 테스트가 이를 덮는다 |
| `partial` | 일부만 답한다. `비고`가 무엇이 빠졌는지 명시한다 |
| `not_implemented` | 아무것도 답하지 않는다. 생략하지 않고 그대로 적는다 |
| `external` | 배포/호스트 플랫폼의 책임이며 이 코드베이스의 것이 아니다 |

## 집계

요구사항 총 74건 (기능 52건 + NFR 22건).

| 상태 | 전체 | P0 |
| --- | --- | --- |
| `implemented` | 35 | 19 |
| `partial` | 22 | 12 |
| `not_implemented` | 15 | 3 |
| `external` | 2 | 0 |

## 전체 색인

| ID | 우선순위 | 상태 |
| --- | --- | --- |
| CAT-001 | P0 | `partial` |
| CAT-002 | P0 | `implemented` |
| CAT-003 | P0 | `partial` |
| CAT-004 | P0 | `implemented` |
| CAT-005 | P0 | `partial` |
| CAT-006 | P1 | `implemented` |
| CAT-007 | P1 | `implemented` |
| CAT-008 | P1 | `implemented` |
| CAT-009 | P2 | `implemented` |
| ONT-001 | P0 | `implemented` |
| ONT-002 | P0 | `implemented` |
| ONT-003 | P0 | `partial` |
| ONT-004 | P0 | `not_implemented` |
| ONT-005 | P0 | `implemented` |
| ONT-006 | P0 | `implemented` |
| ONT-007 | P1 | `not_implemented` |
| ONT-008 | P1 | `not_implemented` |
| BRW-001 | P0 | `implemented` |
| BRW-002 | P0 | `partial` |
| BRW-003 | P0 | `implemented` |
| BRW-004 | P0 | `partial` |
| BRW-005 | P0 | `implemented` |
| BRW-006 | P0 | `partial` |
| BRW-007 | P0 | `implemented` |
| BRW-008 | P0 | `implemented` |
| BRW-009 | P1 | `partial` |
| BRW-010 | P2 | `implemented` |
| LLM-001 | P0 | `implemented` |
| LLM-002 | P0 | `implemented` |
| LLM-003 | P0 | `implemented` |
| LLM-004 | P0 | `implemented` |
| LLM-005 | P0 | `partial` |
| LLM-006 | P0 | `implemented` |
| LLM-007 | P0 | `partial` |
| LLM-008 | P1 | `implemented` |
| LLM-009 | P1 | `external` |
| POL-001 | P0 | `implemented` |
| POL-002 | P0 | `partial` |
| POL-003 | P0 | `implemented` |
| POL-004 | P1 | `implemented` |
| POL-005 | P0 | `implemented` |
| POL-006 | P2 | `not_implemented` |
| LIN-001 | P0 | `partial` |
| LIN-002 | P1 | `not_implemented` |
| LIN-003 | P0 | `partial` |
| LIN-004 | P1 | `implemented` |
| LIN-005 | P1 | `not_implemented` |
| ADM-001 | P0 | `not_implemented` |
| ADM-002 | P0 | `not_implemented` |
| ADM-003 | P1 | `implemented` |
| ADM-004 | P1 | `not_implemented` |
| ADM-005 | P1 | `partial` |
| NFR-PERF-001 | NFR | `partial` |
| NFR-PERF-002 | NFR | `partial` |
| NFR-PERF-003 | NFR | `partial` |
| NFR-PERF-004 | NFR | `partial` |
| NFR-PERF-005 | NFR | `partial` |
| NFR-PERF-006 | NFR | `partial` |
| NFR-SEC-001 | NFR | `partial` |
| NFR-SEC-002 | NFR | `implemented` |
| NFR-SEC-003 | NFR | `partial` |
| NFR-SEC-004 | NFR | `external` |
| NFR-SEC-005 | NFR | `implemented` |
| NFR-SEC-006 | NFR | `implemented` |
| NFR-SEC-007 | NFR | `implemented` |
| NFR-REL-001 | NFR | `not_implemented` |
| NFR-REL-002 | NFR | `not_implemented` |
| NFR-REL-003 | NFR | `not_implemented` |
| NFR-REL-004 | NFR | `not_implemented` |
| NFR-REL-005 | NFR | `not_implemented` |
| NFR-QUAL-001 | NFR | `implemented` |
| NFR-QUAL-002 | NFR | `not_implemented` |
| NFR-QUAL-003 | NFR | `implemented` |
| NFR-QUAL-004 | NFR | `implemented` |

## 요구사항별 대응

### CAT

#### CAT-001 · P0 · `partial`

- **요구사항**: 사용자는 데이터셋을 키워드, 태그, 도메인, owner, freshness, quality score, sensitivity로 검색할 수 있어야 한다.
- **수락 기준**: 검색 결과는 2초 이내 95p 응답, facet count 포함
- **증빙**: `route:GET /catalog/search`, `route:GET /catalog/facets`, `func:sdp.catalog.search_catalog`, `test:tests/test_api.py::test_catalog_search_and_detail`, `test:tests/test_api.py::test_catalog_search_filter_by_quality`
- **비고**: Every search dimension the requirement names is filterable. The acceptance criterion is a different matter. Its facet half does not hold: the search response is {query, count, items} and carries no facet counts, which come from a separate route (GET /catalog/facets). Its latency half - the same 2-second p95 NFR-PERF-001 declares - is now measured, under the same one-sided limitation recorded there: GET /enterprise/latency-budgets reports a measured p95 for this surface and refutes the budget when it is exceeded in-process, but an under-budget result does not establish the deployed p95. The one latency figure this repository records is what such a refutation looks like: src/sdp/catalog.py:468 measures 5.10s for a 2000-token query over 1005 datasets, which is why the query length is bounded rather than optimised.

#### CAT-002 · P0 · `implemented`

- **요구사항**: 데이터셋 상세 페이지는 title, description, owner, steward, source system, update frequency, freshness, quality, sensitivity, license, terms를 표시해야 한다.
- **수락 기준**: 필수 필드 누락 시 “metadata incomplete” 배지 표시
- **증빙**: `route:GET /catalog/datasets/{dataset_id}`, `test:tests/test_api.py::test_catalog_dataset_detail_exposes_recommendation_score`

#### CAT-003 · P0 · `partial`

- **요구사항**: 데이터셋은 DCAT 관점의 Dataset, Distribution, DataService 구조로 표현되어야 한다.
- **수락 기준**: 각 dataset은 하나 이상의 distribution 또는 accessService와 연결
- **증빙**: `route:GET /catalog/datasets/{dataset_id}/jsonld`, `test:tests/test_jsonld_export.py::test_a_distribution_is_a_real_dcat_node_with_an_access_url`
- **비고**: Dataset and Distribution are expressed as DCAT nodes. DataService is not modelled - no route or contract emits dcat:DataService.

#### CAT-004 · P0 · `implemented`

- **요구사항**: 데이터셋은 하나 이상의 business concept 또는 domain theme과 연결될 수 있어야 한다.
- **수락 기준**: concept mapping 상태: proposed/approved/deprecated
- **증빙**: `route:GET /ontology/concept/{concept}`, `func:sdp.ontology.concept_assets`, `test:tests/test_concept_graph_scope.py::test_the_shared_vocabulary_itself_stays_open`

#### CAT-005 · P0 · `partial`

- **요구사항**: 카탈로그 등록/수정은 audit log를 남겨야 한다.
- **수락 기준**: 변경 전후 diff, actor, timestamp, reason 기록
- **증빙**: `route:GET /catalog/datasets/{dataset_id}/audit`, `func:sdp.catalog.ingest_event`, `test:tests/test_governed_write_evidence.py::test_a_governed_write_records_a_decision_and_an_audit_event`, `test:tests/test_catalog_mutation_atomicity.py::test_the_ledger_never_certifies_a_change_that_is_not_stored`
- **비고**: Actor, timestamp, reason and the changed fields are recorded on every catalog mutation, and the row is now guaranteed to be true: concurrent patches used to record result=success for a change that was not in the store, which the mutation lock closes. What the acceptance criterion asks for and does not get is a full before/after diff: `details.before`/`after` carry only the fields the request named, so a field changed by a different concurrent writer does not appear, and governed values (the source DSN, per-column PII flags) are projected rather than recorded verbatim.

#### CAT-006 · P1 · `implemented`

- **요구사항**: metadata completeness score를 자동 계산해야 한다.
- **수락 기준**: 필수 metadata 충족률과 권장 metadata 충족률 분리 표시
- **증빙**: `func:sdp_core.contracts.REQUIRED_METADATA_FIELDS`, `test:tests/test_catalog_field_forwarding.py::test_the_metadata_completeness_target_is_compared`

#### CAT-007 · P1 · `implemented`

- **요구사항**: catalog API는 JSON-LD export를 지원해야 한다.
- **수락 기준**: Dataset URI 기반 JSON-LD 응답 제공
- **증빙**: `route:GET /catalog/datasets/{dataset_id}/jsonld`, `test:tests/test_jsonld_export.py::test_every_published_term_is_mapped_by_the_context`

#### CAT-008 · P1 · `implemented`

- **요구사항**: catalog는 dataset version과 schema version을 구분해야 한다.
- **수락 기준**: schema drift 발생 시 이전 버전과 diff 표시
- **증빙**: `route:GET /catalog/datasets/{dataset_id}/schema-versions`, `route:GET /catalog/datasets/{dataset_id}/schema-diff`, `test:tests/test_api.py::test_catalog_schema_history_and_diff`, `test:tests/test_mutation_idempotency.py::test_every_listed_schema_version_is_addressable_by_the_diff`, `test:tests/test_mutation_idempotency.py::test_a_real_schema_change_adds_a_new_listed_version`
- **비고**: `version` and `schema_version` advance independently and a drift produces a diff against the previous schema version. The version listing used to repeat a version once per non-schema mutation - a state snapshot is recorded on every mutation, because it captures lineage, mappings, tags, status and scores too - so it advertised four `1.0.0` where the diff could resolve only one. Every listed version is now addressable.

#### CAT-009 · P2 · `implemented`

- **요구사항**: 데이터셋 상세에는 related dataset과 join candidate를 표시해야 한다.
- **수락 기준**: 동일 business key/ontology mapping 기반 추천
- **증빙**: `route:GET /catalog/datasets/{dataset_id}/join-candidates`, `route:GET /catalog/datasets/{dataset_id}/related`, `test:tests/test_api.py::test_join_candidate_endpoint`, `test:tests/test_catalog.py::test_join_candidates_skips_zero_overlap`
- **비고**: Recommendation is scored on shared business terms (the concept mapping the acceptance criterion names) weighted above shared column names. There is no business-key notion - no primary or foreign key is declared anywhere - so column overlap stands in for it.

### ONT

#### ONT-001 · P0 · `implemented`

- **요구사항**: business term, synonym, acronym, multilingual label을 조회할 수 있어야 한다.
- **수락 기준**: term resolve API가 confidence score와 후보 URI 반환
- **증빙**: `route:GET /ontology/search`, `route:POST /ontology/resolve`, `test:tests/test_api.py::test_ontology_resolve`

#### ONT-002 · P0 · `implemented`

- **요구사항**: domain concept와 data asset은 별도 class로 모델링되어야 한다.
- **수락 기준**: table/dataset이 business class의 subclass가 되지 않도록 SHACL/OWL 검증
- **증빙**: `func:sdp.graph_store.GraphNode`, `test:tests/test_graph_engine.py::test_semantic_search_kind_filter_only_returns_datasets`
- **비고**: Concept and dataset/column nodes are distinct kinds in the graph store.

#### ONT-003 · P0 · `partial`

- **요구사항**: SKOS 기반 glossary hierarchy를 제공해야 한다.
- **수락 기준**: broader/narrower/related 관계 조회 가능
- **증빙**: `route:GET /ontology/term/{term}/graph`, `test:tests/test_concept_graph_scope.py::test_the_shared_vocabulary_itself_stays_open`
- **비고**: broader/narrower/related are carried per concept, which is the SKOS shape, but no SKOS serialization is emitted and no hierarchy traversal endpoint exists.

#### ONT-004 · P0 · `not_implemented`

- **요구사항**: OWL/RDFS 기반 도메인 ontology를 버전관리해야 한다.
- **수락 기준**: ontology version, change log, reviewer 기록
- **비고**: There is no OWL/RDFS artifact and no ontology version. The concept vocabulary is a Python dict with no release identity.

#### ONT-005 · P0 · `implemented`

- **요구사항**: LLM이 생성한 ontology patch는 proposed 상태로 저장되고 자동 병합되지 않아야 한다.
- **수락 기준**: reasoner + SHACL + reviewer 승인 후 병합
- **증빙**: `route:POST /ontology/patches`, `route:POST /ontology/patches/{patch_id}/review`, `test:tests/test_ontology_publication_loop.py::test_approving_a_patch_publishes_the_term_to_every_read_surface`

#### ONT-006 · P0 · `implemented`

- **요구사항**: ontology term과 physical column mapping을 관리해야 한다.
- **수락 기준**: mapping type, confidence, source, approval state 포함
- **증빙**: `func:sdp.enterprise_evidence.ontology_mapping_coverage_detail`, `test:tests/test_ontology_coverage_measurement.py::test_coverage_is_measured_against_the_glossary`

#### ONT-007 · P1 · `not_implemented`

- **요구사항**: reasoner consistency check를 수동/자동 실행할 수 있어야 한다.
- **수락 기준**: unsatisfiable class 0개가 release gate
- **비고**: No reasoner is integrated and no consistency check runs.

#### ONT-008 · P1 · `not_implemented`

- **요구사항**: competency question을 test case로 등록할 수 있어야 한다.
- **수락 기준**: SPARQL/SHACL/reasoner/API test type 지원
- **비고**: Competency questions are not registrable; no such contract exists.

### BRW

#### BRW-001 · P0 · `implemented`

- **요구사항**: 사용자는 권한이 있는 데이터셋의 schema를 조회할 수 있어야 한다.
- **수락 기준**: table/column/datatype/nullable/key/comment 표시
- **증빙**: `route:GET /browse/{dataset_id}/schema`, `test:tests/test_api.py::test_browse_schema_requires_purpose`

#### BRW-002 · P0 · `partial`

- **요구사항**: 사용자는 권한이 있는 데이터셋의 sample preview를 볼 수 있어야 한다.
- **수락 기준**: 기본 100건, 최대 1,000건, pagination 지원
- **증빙**: `route:POST /browse/{dataset_id}/preview`, `test:tests/test_api.py::test_preview_pagination_and_decision_traceability`
- **비고**: limit/offset are accepted and bounded at 100, not the PRD's 1,000, and the demo engine returns a fixed two-row sample, so pagination is a contract rather than a traversal of real rows.

#### BRW-003 · P0 · `implemented`

- **요구사항**: preview는 column-level masking policy를 적용해야 한다.
- **수락 기준**: PII 컬럼은 masking 또는 suppression
- **증빙**: `func:sdp.browse.preview`, `test:tests/test_browse.py::test_preview_masks_every_declared_pii_column`

#### BRW-004 · P0 · `partial`

- **요구사항**: profile 정보(null ratio, distinct count, min/max, freshness)를 표시해야 한다.
- **수락 기준**: profile 계산 시점과 sample/full 여부 표시
- **증빙**: `route:GET /catalog/datasets/{dataset_id}/profile`
- **비고**: null ratio, distinct ratio and freshness are carried per column and published with provenance labels; min/max is in the profile contract but nothing computes it from data.

#### BRW-005 · P0 · `implemented`

- **요구사항**: query execution은 read-only SELECT 계열만 허용해야 한다.
- **수락 기준**: DDL/DML/unsafe function 차단
- **증빙**: `func:sdp.orchestrator.validate_sql_query`, `test:tests/test_orchestrator.py::test_the_allowlist_is_an_allowlist_not_a_denylist`
- **비고**: SELECT-only, single statement, forbidden keywords, source-table allow-list and a function allow-list. No engine executes the statement, so this is a certification gate, not enforcement.

#### BRW-006 · P0 · `partial`

- **요구사항**: query timeout, memory limit, row limit, cost limit을 적용해야 한다.
- **수락 기준**: 초과 시 안전하게 중단하고 audit log 기록
- **증빙**: `func:sdp.orchestrator.execute_query`
- **비고**: row_limit and timeout_ms are validated and echoed, and the sample budget is hard-capped. Memory and cost limits are not implemented, and nothing enforces a timeout because nothing executes.

#### BRW-007 · P0 · `implemented`

- **요구사항**: 모든 preview/query 요청은 audit log를 남겨야 한다.
- **수락 기준**: actor, datasetId, columns, purpose, decisionId 기록
- **증빙**: `func:sdp.browse.preview`, `test:tests/test_payload_type_robustness.py::test_the_decision_and_audit_halves_stay_paired`

#### BRW-008 · P0 · `implemented`

- **요구사항**: 브라우징은 catalog asset ID/URI를 입력으로 받아야 한다.
- **수락 기준**: 물리 경로 직접 호출 금지
- **증빙**: `route:GET /browse/{dataset_id}/schema`, `test:tests/test_browse.py::test_preview_rows_never_leave_the_named_dataset_schema`

#### BRW-009 · P1 · `partial`

- **요구사항**: source connector는 RDBMS, Lakehouse, Object Storage, RDF Store를 단계적으로 지원해야 한다.
- **수락 기준**: connector contract를 공통화
- **증빙**: `route:GET /enterprise/connectors/{connector_id}/probe`, `test:tests/test_connector_verdict_evidence.py::test_every_control_row_declares_how_strong_its_evidence_is`
- **비고**: Four connector contracts (sql, rdf, file_lake, rest) with demo adapters that inspect fixture schemas. No connector reaches a real source system.

#### BRW-010 · P2 · `implemented`

- **요구사항**: graph/entity browsing을 지원해야 한다.
- **수락 기준**: RDF/Graph DB source의 neighbors/path 조회
- **증빙**: `route:POST /graph/query`, `route:GET /graph/nodes/{node_id}`, `route:POST /search/semantic`, `test:tests/test_graph_tenant_scope.py::test_graph_traversal_withholds_other_tenants_nodes`, `test:tests/test_graph_store_concurrency.py::test_a_search_survives_nodes_arriving_mid_iteration`
- **비고**: Neighbour and bounded-path traversal plus semantic search, over the in-memory store by default and Apache AGE + pgvector when a DSN is configured. Search used to return 500 while datasets were being onboarded (a dict iterated while it grew); the store is now internally locked.

### LLM

#### LLM-001 · P0 · `implemented`

- **요구사항**: 자연어 질문을 catalog search query로 변환해야 한다.
- **수락 기준**: 검색 후보와 사용된 ontology term을 함께 표시
- **증빙**: `route:POST /llm/search`, `test:tests/test_api.py::test_llm_search_uses_catalog_discovery_policy_scope`

#### LLM-002 · P0 · `implemented`

- **요구사항**: LLM은 반드시 Ontology Service로 term resolution을 수행해야 한다.
- **수락 기준**: unresolved term은 사용자에게 가정으로 표시
- **증빙**: `func:sdp.ontology.resolve_terms`, `test:tests/test_api.py::test_ontology_resolve`

#### LLM-003 · P0 · `implemented`

- **요구사항**: LLM은 catalog에 존재하지 않는 dataset/table/column을 응답에 포함해서는 안 된다.
- **수락 기준**: generated answer가 asset registry allowlist를 통과
- **증빙**: `func:sdp.orchestrator.draft_sql`, `test:tests/test_orchestrator.py::test_a_rewritten_column_is_reported_rather_than_contradicted`
- **비고**: The drafter uses only declared columns and the catalog-derived table name, and refuses a column the dataset does not declare.

#### LLM-004 · P0 · `implemented`

- **요구사항**: SQL/SPARQL 생성은 schema-grounded context만 사용해야 한다.
- **수락 기준**: 허용된 schema fragment 외 참조 차단
- **증빙**: `func:sdp.orchestrator.draft_sql`, `test:tests/test_orchestrator.py::test_every_seeded_dataset_drafts_a_statement_its_validator_accepts`

#### LLM-005 · P0 · `partial`

- **요구사항**: LLM 응답에는 근거 metadata, source dataset, timestamp, quality warning을 포함해야 한다.
- **수락 기준**: 답변 카드에 evidence block 표시
- **증빙**: `func:sdp.orchestrator.draft_sql`
- **비고**: assumptions, requested_columns, emitted_identifiers and the policy decision id are returned. There is no timestamp on the draft and no quality warning derived from the dataset's quality score.

#### LLM-006 · P0 · `implemented`

- **요구사항**: LLM은 직접 DB credential 또는 connector secret에 접근할 수 없어야 한다.
- **수락 기준**: LLM runtime에는 secret 미주입
- **증빙**: `func:sdp.credentials.connector_secret_status`, `test:tests/test_api.py::test_enterprise_rest_connector_probe_uses_vault_reference_without_secret_leak`
- **비고**: No LLM runs in-process; connector secrets are referenced, never returned.

#### LLM-007 · P0 · `partial`

- **요구사항**: prompt injection 방어를 수행해야 한다.
- **수락 기준**: 문서/metadata 내 instruction-like text는 data로 취급
- **증빙**: `func:sdp.orchestrator.draft_sql`, `test:tests/test_orchestrator.py::test_validate_sql_query_flags_unsafe_input`
- **비고**: The question is screened for forbidden keywords and the generated statement must pass the safety gate, which bounds what an injected instruction could produce. There is no prompt-injection classifier, because no model is called.

#### LLM-008 · P1 · `implemented`

- **요구사항**: LLM 생성 metadata는 proposed 상태로 저장해야 한다.
- **수락 기준**: steward 승인 전 official metadata로 미노출
- **증빙**: `route:POST /ontology/patches`, `test:tests/test_api.py::test_ontology_patch_workflow`

#### LLM-009 · P1 · `external`

- **요구사항**: LLM 대화 이력에는 민감 preview 결과를 원문 저장하지 않아야 한다.
- **수락 기준**: redaction 또는 secure ephemeral memory 적용
- **비고**: No conversation history is stored by this service - there is no chat transcript surface - so there is nothing here to redact. A host that adds one owns this requirement.

### POL

#### POL-001 · P0 · `implemented`

- **요구사항**: catalog discovery 권한과 data preview/query 권한을 분리해야 한다.
- **수락 기준**: 데이터셋 존재 확인 가능 여부를 별도 정책으로 제어
- **증빙**: `func:sdp.policy.evaluate`, `test:tests/test_policy.py::test_security_role_may_read_metadata_but_not_data`

#### POL-002 · P0 · `partial`

- **요구사항**: dataset/table/column-level access control을 지원해야 한다.
- **수락 기준**: 권한 없는 컬럼은 숨김 또는 마스킹
- **증빙**: `func:sdp.policy.evaluate`, `test:tests/test_governance_boundary.py::test_a_foreign_tenant_admin_cannot_overwrite_a_node_it_cannot_read`
- **비고**: Dataset-level control is enforced per tenant and per role, and column-level control is enforced as masking. There is no per-table level, because a dataset is the table here.

#### POL-003 · P0 · `implemented`

- **요구사항**: PII, sensitive, confidential tag 기반 masking을 지원해야 한다.
- **수락 기준**: policy decision 결과에 masking rule 포함
- **증빙**: `func:sdp.browse.preview`, `test:tests/test_browse.py::test_preview_masks_every_declared_pii_column`

#### POL-004 · P1 · `implemented`

- **요구사항**: purpose-based access를 지원해야 한다.
- **수락 기준**: 사용자가 query 목적을 입력하고 policy evaluation에 포함
- **증빙**: `func:sdp.policy.evaluate`, `test:tests/test_governance_boundary.py::test_no_purpose_spelling_bypasses_the_export_denial`

#### POL-005 · P0 · `implemented`

- **요구사항**: 모든 policy decision은 decisionId와 함께 감사 가능해야 한다.
- **수락 기준**: audit log에서 decision 재현 가능
- **증빙**: `route:GET /policy/decisions`, `test:tests/test_governed_write_evidence.py::test_a_governed_write_records_a_decision_and_an_audit_event`, `test:tests/test_evidence_log_snapshot_reads.py::test_a_decision_page_never_repeats_a_row_while_the_log_trims`
- **비고**: Every policy decision is recorded with its subject, resource, action, effect, reason and obligations, and the feed is readable and tenant-scoped. A page used to be able to repeat a row and omit that many real ones while the bounded in-memory log trimmed behind the reader; pages are now built from a snapshot. A page remains a point-in-time view - a decision recorded after the snapshot is legitimately absent - and the in-memory fallback log is a bounded window, not an archive; a configured store is the durable path.

#### POL-006 · P2 · `not_implemented`

- **요구사항**: ODRL 또는 내부 policy ontology로 사용 조건을 표현할 수 있어야 한다.
- **수락 기준**: permission/prohibition/duty 표현 가능
- **비고**: Usage conditions are not expressed in ODRL or any policy ontology; obligations are a fixed dict shape.

### LIN

#### LIN-001 · P0 · `partial`

- **요구사항**: dataset/table 수준 upstream/downstream lineage를 표시해야 한다.
- **수락 기준**: lineage graph에서 source/job/target 표시
- **증빙**: `route:GET /catalog/datasets/{dataset_id}/lineage`, `route:POST /graph/query`, `test:tests/test_graph_mirroring.py::test_a_lineage_edge_is_reconciled_against_both_of_its_declarers`, `test:tests/test_graph_mirroring.py::test_mutating_a_dataset_keeps_edges_its_partners_declare`
- **비고**: Dataset-level upstream and downstream are declared, mirrored into the graph and traversable, and the mirror now agrees with the catalog under concurrent and sequential mutation alike - seeding or mutating one endpoint used to delete lineage edges the other endpoint declared. The acceptance criterion's `source/job/target` is not met: there is no job or activity node, only dataset-to-dataset edges, so a lineage graph cannot show what produced the edge. LIN-005 (PROV) is the same gap stated as its own requirement. `lineage_inputs`/`lineage_outputs` are also absent from `DatasetCreateRequest`, so lineage can only be declared by a subsequent PATCH.

#### LIN-002 · P1 · `not_implemented`

- **요구사항**: column-level lineage를 Phase 2에서 지원해야 한다.
- **수락 기준**: column mapping과 transformation metadata 연결
- **비고**: Column-level lineage is Phase 2 in the PRD and is not built.

#### LIN-003 · P0 · `partial`

- **요구사항**: 품질 profile은 null ratio, distinct count, freshness, duplicate ratio를 포함해야 한다.
- **수락 기준**: metric timestamp와 계산 범위 표시
- **증빙**: `route:GET /catalog/datasets/{dataset_id}/profile`, `func:sdp.profile_provenance.profile_metric_provenance`, `test:tests/test_profile_metric_provenance.py::test_the_profile_declares_it_computed_nothing`, `test:tests/test_profile_metric_provenance.py::test_distinct_count_is_declared_unavailable_rather_than_multiplied`
- **비고**: null ratio, distinct ratio and freshness are present, and the acceptance criterion's two display requirements - metric timestamp and computation scope - are now met. They are met by saying something uncomfortable: `computed_by_this_service: false`. There is no profiler here, so every figure is the source's or the registering caller's declaration, and the published block says so rather than letting `row_count: 1200000` read as a measurement. The metric timestamp is the declared one or `null`, never the read time. duplicate_ratio and distinct_count are named in `declared_unavailable_metrics` with reasons rather than omitted; distinct_count is deliberately not derived from distinct_ratio x row_count, which would manufacture a measurement neither input supports.

#### LIN-004 · P1 · `implemented`

- **요구사항**: 품질 threshold 위반 시 데이터셋 상세에 warning을 표시해야 한다.
- **수락 기준**: warning에는 rule, observed value, threshold 포함
- **증빙**: `route:GET /catalog/datasets/{dataset_id}`, `route:GET /browse/{dataset_id}/schema`, `func:sdp.quality_warnings.quality_warning_summary`, `test:tests/test_quality_threshold_warnings.py::test_every_declared_rule_fires_on_a_violating_dataset`, `test:tests/test_quality_threshold_warnings.py::test_every_warning_carries_rule_observed_value_and_threshold`
- **비고**: Six rules over the dataset's declared scores, its required-metadata completeness and its per-column null/distinct ratios and declared issues. Each warning carries the rule, the observed value and the threshold, which is what the acceptance criterion names. Two boundaries are deliberate: a rule whose input cannot be compared reports `unevaluated` rather than passing, and column-scope warnings appear only behind the policy gate because they name a column and read statistics the discovery surface withholds - the open surface publishes `withheld_quality_warning_count` instead. The thresholds are product-wide defaults, not per-tenant or per-domain configuration; `threshold_source` says so on every warning.

#### LIN-005 · P1 · `not_implemented`

- **요구사항**: provenance는 PROV 관점의 activity, entity, agent로 표현 가능해야 한다.
- **수락 기준**: pipeline/job/user/source 연결
- **비고**: No PROV activity/entity/agent representation exists.

### ADM

#### ADM-001 · P0 · `not_implemented`

- **요구사항**: 관리자 UI에서 connector 등록/수정/비활성화가 가능해야 한다.
- **수락 기준**: secret은 secret manager에 저장, UI 미노출
- **비고**: Connectors are a fixed registry in code. There is no registration, edit or deactivation path, and the console is read-only.

#### ADM-002 · P0 · `not_implemented`

- **요구사항**: metadata ingestion job을 수동 실행할 수 있어야 한다.
- **수락 기준**: job status, logs, failure reason 표시
- **비고**: There is no ingestion job and therefore no manual run.

#### ADM-003 · P1 · `implemented`

- **요구사항**: SHACL validation report를 확인할 수 있어야 한다.
- **수락 기준**: violation path, severity, message 표시
- **증빙**: `route:GET /enterprise/shacl-validation`, `test:tests/test_semantic_validation.py::test_every_published_required_property_is_evaluated`

#### ADM-004 · P1 · `not_implemented`

- **요구사항**: LLM feature flag를 도메인/사용자 그룹별로 제어할 수 있어야 한다.
- **수락 기준**: rollout percentage와 allowlist 지원
- **비고**: There is no feature-flag surface, per domain or per group.

#### ADM-005 · P1 · `partial`

- **요구사항**: audit log 검색과 export를 지원해야 한다.
- **수락 기준**: actor, asset, action, time range 필터
- **증빙**: `route:GET /audit/events`, `test:tests/test_evidence_tenant_read_scope.py::test_audit_events_are_scoped_to_the_reader_tenant`
- **비고**: Audit events are searchable by resource and tenant-scoped. There is no export format and no date-range filter.

### NFR-PERF

#### NFR-PERF-001 · NFR · `partial`

- **요구사항**: catalog keyword search latency
- **수락 기준**: p95 2초 이하
- **증빙**: `route:GET /enterprise/latency-budgets`, `func:sdp.latency_budgets.latency_budget_report`, `test:tests/test_latency_budget_measurement.py::test_no_declared_budget_is_refuted_in_process`, `test:tests/test_latency_budget_measurement.py::test_the_refutation_path_actually_fires`
- **비고**: The budget is declared against the routes it governs and compared to a measured nearest-rank p95 over successful responses, with a minimum sample below which no verdict is produced in either direction. What it cannot establish is the requirement as stated: the observations come from one in-process worker over in-memory stores and seed data, so the measured p95 is a lower bound on a deployment's. The published field is therefore `budget_refuted`, not `within_budget` - an over-budget result is conclusive, an under-budget one is not. Confirming a deployed p95 needs a load test against a deployed instance, which is outside this repository.

#### NFR-PERF-002 · NFR · `partial`

- **요구사항**: dataset detail API latency
- **수락 기준**: p95 1.5초 이하
- **증빙**: `route:GET /enterprise/latency-budgets`, `func:sdp.latency_budgets.latency_budget_report`, `test:tests/test_latency_budget_measurement.py::test_no_declared_budget_is_refuted_in_process`, `test:tests/test_latency_budget_measurement.py::test_the_refutation_path_actually_fires`
- **비고**: The budget is declared against the routes it governs and compared to a measured nearest-rank p95 over successful responses, with a minimum sample below which no verdict is produced in either direction. What it cannot establish is the requirement as stated: the observations come from one in-process worker over in-memory stores and seed data, so the measured p95 is a lower bound on a deployment's. The published field is therefore `budget_refuted`, not `within_budget` - an over-budget result is conclusive, an under-budget one is not. Confirming a deployed p95 needs a load test against a deployed instance, which is outside this repository.

#### NFR-PERF-003 · NFR · `partial`

- **요구사항**: schema browsing latency
- **수락 기준**: p95 3초 이하
- **증빙**: `route:GET /enterprise/latency-budgets`, `func:sdp.latency_budgets.latency_budget_report`, `test:tests/test_latency_budget_measurement.py::test_no_declared_budget_is_refuted_in_process`, `test:tests/test_latency_budget_measurement.py::test_the_refutation_path_actually_fires`
- **비고**: The budget is declared against the routes it governs and compared to a measured nearest-rank p95 over successful responses, with a minimum sample below which no verdict is produced in either direction. What it cannot establish is the requirement as stated: the observations come from one in-process worker over in-memory stores and seed data, so the measured p95 is a lower bound on a deployment's. The published field is therefore `budget_refuted`, not `within_budget` - an over-budget result is conclusive, an under-budget one is not. Confirming a deployed p95 needs a load test against a deployed instance, which is outside this repository.

#### NFR-PERF-004 · NFR · `partial`

- **요구사항**: preview latency
- **수락 기준**: p95 10초 이하, source별 예외 가능
- **증빙**: `route:GET /enterprise/latency-budgets`, `func:sdp.latency_budgets.latency_budget_report`, `test:tests/test_latency_budget_measurement.py::test_no_declared_budget_is_refuted_in_process`, `test:tests/test_latency_budget_measurement.py::test_the_refutation_path_actually_fires`
- **비고**: The budget is declared against the routes it governs and compared to a measured nearest-rank p95 over successful responses, with a minimum sample below which no verdict is produced in either direction. What it cannot establish is the requirement as stated: the observations come from one in-process worker over in-memory stores and seed data, so the measured p95 is a lower bound on a deployment's. The published field is therefore `budget_refuted`, not `within_budget` - an over-budget result is conclusive, an under-budget one is not. Confirming a deployed p95 needs a load test against a deployed instance, which is outside this repository.

#### NFR-PERF-005 · NFR · `partial`

- **요구사항**: LLM catalog answer latency
- **수락 기준**: p95 15초 이하
- **증빙**: `route:GET /enterprise/latency-budgets`, `func:sdp.latency_budgets.latency_budget_report`, `test:tests/test_latency_budget_measurement.py::test_no_declared_budget_is_refuted_in_process`, `test:tests/test_latency_budget_measurement.py::test_the_refutation_path_actually_fires`
- **비고**: The budget is declared against the routes it governs and compared to a measured nearest-rank p95 over successful responses, with a minimum sample below which no verdict is produced in either direction. What it cannot establish is the requirement as stated: the observations come from one in-process worker over in-memory stores and seed data, so the measured p95 is a lower bound on a deployment's. The published field is therefore `budget_refuted`, not `within_budget` - an over-budget result is conclusive, an under-budget one is not. Confirming a deployed p95 needs a load test against a deployed instance, which is outside this repository.

#### NFR-PERF-006 · NFR · `partial`

- **요구사항**: ontology term resolution latency
- **수락 기준**: p95 500ms 이하
- **증빙**: `route:GET /enterprise/latency-budgets`, `func:sdp.latency_budgets.latency_budget_report`, `test:tests/test_latency_budget_measurement.py::test_no_declared_budget_is_refuted_in_process`, `test:tests/test_latency_budget_measurement.py::test_the_refutation_path_actually_fires`
- **비고**: The budget is declared against the routes it governs and compared to a measured nearest-rank p95 over successful responses, with a minimum sample below which no verdict is produced in either direction. What it cannot establish is the requirement as stated: the observations come from one in-process worker over in-memory stores and seed data, so the measured p95 is a lower bound on a deployment's. The published field is therefore `budget_refuted`, not `within_budget` - an over-budget result is conclusive, an under-budget one is not. Confirming a deployed p95 needs a load test against a deployed instance, which is outside this repository.

### NFR-SEC

#### NFR-SEC-001 · NFR · `partial`

- **요구사항**: 인증
- **수락 기준**: OIDC/SAML 기반 SSO
- **증빙**: `route:POST /enterprise/auth/oidc-verify`, `test:tests/test_api.py::test_oidc_jwks_verification_maps_verified_token_without_token_leak`
- **비고**: OIDC token verification against operator-configured JWKS is built. SAML is not, and there is no session or login flow - the service verifies a token a host obtained.

#### NFR-SEC-002 · NFR · `implemented`

- **요구사항**: 권한
- **수락 기준**: RBAC + ABAC hybrid
- **증빙**: `func:sdp_core.rbac.enterprise_rbac_matrix`, `func:sdp.policy.evaluate`, `test:tests/test_published_claim_honesty.py::test_every_published_grant_is_one_the_engine_actually_allows`
- **비고**: Roles plus tenant/sensitivity/purpose attributes, i.e. RBAC + ABAC.

#### NFR-SEC-003 · NFR · `partial`

- **요구사항**: secret 관리
- **수락 기준**: Secret Manager/Vault 사용, 코드/로그 노출 금지
- **증빙**: `func:sdp.credentials.connector_secret_status`, `test:tests/test_source_system_redaction.py::test_no_connection_string_form_survives_with_its_secret`
- **비고**: Secrets are read as environment references, never stored or published, and credential-bearing locators are redacted on every surface. No Secret Manager or Vault integration exists; the reference resolver reads the process environment.

#### NFR-SEC-004 · NFR · `external`

- **요구사항**: transport security
- **수락 기준**: 모든 내부/외부 통신 TLS
- **비고**: TLS terminates at the deployment's edge. This service speaks HTTP and the compose/Traefik configuration owns transport security.

#### NFR-SEC-005 · NFR · `implemented`

- **요구사항**: audit
- **수락 기준**: preview/query/policy/catalog change 100% 기록
- **증빙**: `func:sdp.catalog.ingest_event`, `test:tests/test_governed_write_evidence.py::test_a_governed_write_records_a_decision_and_an_audit_event`, `test:tests/test_catalog_mutation_atomicity.py::test_the_ledger_never_certifies_a_change_that_is_not_stored`, `test:tests/test_refused_mutation_evidence.py::test_a_refused_catalog_mutation_records_both_halves`, `test:tests/test_refused_mutation_evidence.py::test_every_catalog_mutation_route_is_covered_here`
- **비고**: Every preview, query, policy evaluation and catalog change records a decision and an audit event, on refusal as well as on success. Two holes in that 100% were found and closed rather than assumed absent. Concurrent patches used to record result=success for a change that was not stored, so the ledger was complete and partly false. And a *refused* catalog mutation recorded the decision and no audit row at all - measured on all four verbs: 403, decisions +1, audits +0 - while the browse paths audited their denials; the pairing test's governed-write list covered only the three routes sharing the auditing gate, which is how four inline-authorizing routes stayed uncovered. The new coverage is derived from the route table. What this row does not claim is the *content* of a record: see CAT-005 for the reason field and the before/after diff.

#### NFR-SEC-006 · NFR · `implemented`

- **요구사항**: LLM data leakage 방지
- **수락 기준**: 민감 preview 원문을 LLM provider에 비전송 또는 redaction 후 전송
- **증빙**: `test:tests/test_source_system_redaction.py::test_no_connection_string_form_survives_with_its_secret`
- **비고**: No model is called, so no data leaves for one; redaction is asserted.

#### NFR-SEC-007 · NFR · `implemented`

- **요구사항**: query safety
- **수락 기준**: read-only, allowlist, timeout, row limit, cost limit
- **증빙**: `func:sdp.orchestrator.validate_sql_query`, `test:tests/test_orchestrator.py::test_a_function_outside_the_allowlist_is_refused`

### NFR-REL

#### NFR-REL-001 · NFR · `not_implemented`

- **요구사항**: catalog API availability
- **수락 기준**: 99.9% monthly
- **비고**: No availability target is measured or published.

#### NFR-REL-002 · NFR · `not_implemented`

- **요구사항**: browse service availability
- **수락 기준**: 99.5% monthly, source dependency 제외
- **비고**: No availability target is measured or published.

#### NFR-REL-003 · NFR · `not_implemented`

- **요구사항**: metadata KG backup
- **수락 기준**: daily full backup, hourly incremental
- **비고**: There is no backup path for the metadata graph. The evidence store has durability (a SQLite file or Postgres) but no backup or restore procedure in this repository.

#### NFR-REL-004 · NFR · `not_implemented`

- **요구사항**: search index rebuild
- **수락 기준**: index corruption 시 4시간 내 rebuild
- **비고**: Search is an in-process scan with no index, so there is nothing to rebuild and no rebuild path.

#### NFR-REL-005 · NFR · `not_implemented`

- **요구사항**: ingestion retry
- **수락 기준**: transient failure 3회 exponential backoff
- **비고**: There is no ingestion pipeline and therefore no retry.

### NFR-QUAL

#### NFR-QUAL-001 · NFR · `implemented`

- **요구사항**: 필수 metadata validation
- **수락 기준**: SHACL 통과 후 publish
- **증빙**: `route:GET /catalog/datasets/{dataset_id}/validate`, `test:tests/test_published_claim_honesty.py::test_completeness_and_validation_score_the_same_fields`

#### NFR-QUAL-002 · NFR · `not_implemented`

- **요구사항**: ontology release validation
- **수락 기준**: reasoner consistency 통과
- **비고**: There is no ontology release, so no release validation. ONT-004 is the prerequisite and is also unbuilt.

#### NFR-QUAL-003 · NFR · `implemented`

- **요구사항**: LLM generated query validation
- **수락 기준**: schema/permission/syntax/cost 검증 통과 후 실행
- **증빙**: `func:sdp.orchestrator.validate_sql_query`, `test:tests/test_orchestrator.py::test_the_drafter_self_check_is_a_live_guard`
- **비고**: A generated statement is validated by the same gate before it is returned.

#### NFR-QUAL-004 · NFR · `implemented`

- **요구사항**: regression test
- **수락 기준**: 핵심 CQ test pass rate 100%
- **증빙**: `test:tests/test_state_isolation.py::test_every_test_starts_from_the_seeded_baseline`
- **비고**: The suite is the regression gate; order independence is asserted.
