# 제품·기술 격차 기준선 (product-technical gap baseline)

**제품 홈:** ContextualWisdomLab/semantic-data-portal (ontology 기반 semantic catalog).
**독자:** catalog steward / tenant operator.
**다음 행동:** 아래 병합 순서로 unlock stack을 올리고, 이 저장소에 local IdP나 policy registry를 만들지 마십시오.
**기준일:** 2026-08-24 (main `e48aa13`).
**Figma file ID:** `JjYSqr6nWxpARUjaVKhG16` (KRDS 기반 디자인 시스템; `docs/design-tokens.md:3`의 토큰 계약과 동일 파일). 새 Figma 파일을 만들지 말고 이 파일을 소비하십시오.

이 파일은 포털의 살아있는 격차 목록입니다. 열린 PR이 병합되거나 consume-only 계약이 바뀌면 갱신하십시오. GitHub review 대기는 작업 중지로 보지 마십시오.

## 경계 (consume-only vs own)

| 관심사 | Owner | 포털 의무 |
| --- | --- | --- |
| Identity, SCIM, tenant header, purpose-limited authorization | Keyverse | 검증된 OIDC claim으로 tenant identity를 만들고, Keyverse가 발행한 `X-CWL-Tenant-Reference`가 없거나 불일치하면 fail-closed. 포털은 이 헤더를 자체 서명하지 않습니다. Observability용 `X-SDP-Tenant`는 인가 결정에 쓰지 않습니다. local IdP 없음. |
| Policy, control, evidence, audit truth | GRC 홈 | 컨트롤 정의는 GRC에서 소비하고, 포털은 자기 쪽 결정·감사 증거를 생산합니다. `policy.evaluate()`는 모든 로컬 정책 결정을 `record_policy_decision`으로 남기고(`src/sdp/evidence.py:37-48`), browse/catalog 동작은 설정된 evidence store에 감사 이벤트를 기록합니다. local policy registry 없음. |
| Organization security gates | CWL Security | 중앙 워크플로를 상속합니다. 포함: Security Scan, Strix, CodeQL, Semgrep, python-security, osv-scan, diff-scoped dependency-review, repo-wide trivy-fs(fixable CRITICAL/HIGH). 두 번째 gate loop를 포크하지 마십시오. |
| Ontology registry and catalog plane | **this repo** | Glossary, catalog objects, bindings, provenance pointers. |
| Document knowledge graph | **naruon** | naruon이 이메일/파일을 DOM 분해하여 영속 KG를 소유합니다. 포털은 그 KG에 write하지 않고 commons provenance pointer만 저장합니다. sender-ontology는 consume-only. |
| Lineage DAG reconstruction / weekly report | LineageWeave (#74) | 산발 레코드에서 lineage thread를 재구성하는 것은 LineageWeave 소관입니다. 포털은 결과를 소비하고 provenance pointer만 저장하며, 어떤 KG write 경로도 호출하지 않습니다. #74→main은 포털 블로커가 아닙니다. |
| IRT / linking scores | fast-mlsirm | 호출만 하고 재구현하지 마십시오. |
| Employment tree | Orgmetra | affiliation key만 소비. |
| Office authoring | naruon | sender-ontology consumer only. |
| Measurement import | TEPP | Import/REST only. |
| Disk inventory | DiskSage | Catalog ingest/preview adapter only. |

PII는 업무에 그대로 필요합니다. **현행 계약을 유지하십시오:** `browse.preview`의 policy-driven `apply_mask`는 PRD P0 통제(`docs/prd-trd.md:402`, `:431`)이며 그대로 둡니다. 카탈로그 plane에 *새로운* masking을 추가하지 마십시오. purpose-limited authorization 계약 주인은 Keyverse, 응답 최소화·redaction·evidence export 계약 주인은 GRC입니다. authorization+audit은 접근 주체와 사후 추적을 제어할 뿐 response 복사본을 제거하지 않으므로, redaction 소유자는 GRC임을 명시해 둡니다.

main `e48aa13`에서 `/browse/{dataset_id}/preview`는 caller-supplied `user` 문자열을 받아 로컬 정적 맵으로 해석합니다(`src/sdp/api.py:804-814`). 즉 Keyverse-bound fail-closed identity는 목표 계약이지 현행 상태가 아닙니다. 이 격차는 아래 operator-facing 격차 표에 열려 있습니다. PR `#80` (`9897376`)은 인가된 steward preview에서 원문 값을 보여주도록 steward 경로만 바꾸며, policy masking obligation과 GRC evidence export redaction은 그대로 유지합니다. `#51` security-lock과 섞지 말고, squash는 현재 SHA OpenCode APPROVE 뒤에서만 하십시오.

## 이미 채택한 표준 (APA 7th)

Albertoni, R., Browning, D., Cox, S., Gonzalez Beltran, A., Perego, A., & Winstanley, P. (Eds.). (2024). *Data Catalog Vocabulary (DCAT) — Version 3*. World Wide Web Consortium. https://www.w3.org/TR/vocab-dcat-3/  
포털 계약: catalog object·distribution·dataset 식별은 DCAT 3 resource 모델을 따릅니다.

International Organization for Standardization. (2023). *Information technology — Metadata registries (MDR) — Part 1: Framework* (ISO/IEC 11179-1:2023). https://www.iso.org/standard/78914.html  
포털 계약: glossary term과 administered item 식별은 MDR framework의 등록 의미를 따릅니다. 유료 본문은 인용만 하고 전문을 복제하지 않습니다.

Moreau, L., & Missier, P. (Eds.). (2013). *PROV-DM: The PROV data model*. World Wide Web Consortium. https://www.w3.org/TR/prov-dm/  
포털 계약: catalog 변경은 provenance pointer(PROV entity/activity)로만 남깁니다. document-KG write owner는 naruon, lineage 재구성은 LineageWeave 소관이며, 포털은 어느 쪽 write 경로도 호출하지 않습니다.

이후 커밋이 이 계약과 어긋나면 인용을 바꾸지 말고 코드를 고치십시오.

## 병합 순서 (steward)

1. PR `#81` — cryptography 49.0.0 → 50.0.0 (CVE-2026-69247 / GHSA-g6cj-pr64-35w5). trivy-fs는 merge ref를 스캔하므로 이 PR이 main에 올리면 모든 열린 PR이 상속해 풀립니다. `#51`의 cryptography hunk와 동일한 변경이므로 병합 시 중복 없이 정리됩니다.
2. PR `#51` `558dd2f` — outbound URL harden + security lock (cryptography 부분은 `#81`이 흡수). Frozen. 이 head를 push하지 마십시오. 이 SHA에 OpenCode APPROVE가 붙은 뒤 Product Manager squash.
3. PR `#58` `80966ae` — bounded Keyverse claim aliases. Frozen. 같은 merge gate.
4. PR `#35` `9c12f5d` **그리고** PR `#32` `76fcfb6` (SQL gate). 둘 다 catalog plane SQL 표면의 전제입니다. **`#32`는 non-blocking이 아닙니다. `#73`보다 먼저** 병합하십시오. Frozen heads는 push하지 마십시오.
5. PR `#73` `bfa409f` — catalog/ontology plane (#13). 제품 검사는 초록, 남은 빨강은 `trivy-fs` inherit(위 `#81`으로 해소 예정). push 보류. **`#75`는 `#73`이 main에 올 때까지 Draft.**
6. PR `#28` after PR `#37` — trusted document deps 위의 hybrid file ontology.
7. PR `#59` / `#61` — DiskSage ingest and preview boundary.
8. PR `#64` product names, then PR `#65` setuptools, then Dependabot.

PR `#51` security-lock 파일을 catalog/docs PR에 섞지 마십시오. 이 문서 PR(`#79`)도 보안 unlock stack 뒤에서 squash하십시오. `#80`은 `#51` security-lock과 별개이며 squash는 현재 SHA OpenCode APPROVE 뒤에만 합니다.

## 열린 PR과 각 PR이 닫는 격차

| PR | Head | 격차 | 포털 소유? | 상태 2026-08-24 |
| --- | --- | --- | --- | --- |
| #51 | `558dd2f` | Outbound URL allowlist + security lock (cryptography CVE 부분은 `#81`이 선행 흡수) | Yes (security lock) | HOLD. 현재 SHA OpenCode APPROVE 없음. |
| #81 | `fce7045` | cryptography 50.0.0 — CVE-2026-69247, repo-wide trivy-fs unlock | Yes (shared base) | Open. 최우선 병합. |
| #58 | `80966ae` | Keyverse claim aliases fail-closed | Keyverse 소비, adapter는 여기 | HOLD. 이전 APPROVE는 옛 SHA. |
| #35 | `9c12f5d` | SQL comma-join allowlist bypass | Yes | HOLD. CI 초록. |
| #32 | `76fcfb6` | SELECT..INTO / volatile SQL bypass | Yes | #73 전제. #35/#51 뒤에 유지. |
| #73 | `bfa409f` | Catalog plane above the document KG (#13) | Yes | HOLD. trivy inherit only. |
| #75 | `56b0ad2` Draft | Framework-neutral data-management evidence *profiles* (GRC registry 아님) | Yes (catalog evidence shape) | Draft until #73. |
| #59 | `65e4fd7` | DiskSage catalog ingest | Adapter yes | HOLD. |
| #61 | `0c248d2` | DiskSage preview boundary | Adapter yes | Open; Analyze flake — extra-push 금지. |
| #28 | `5e4b11c` | Hybrid file ontology | Yes after #37 | Wait #37. |
| #37 | `00ee8af` | Trusted document semantic deps | Yes (build) | Open. |
| #64 | `4b78611` | Current CWL product names | Yes (docs) | After #51. |
| #65 | `19603c3` | setuptools 83 | Yes (build) | After unlock. |
| #72 | `2295b0d` Draft | Operator README / draft ADRs | Yes (docs) | Draft. |
| #79 | `a6c983f` | 이 기준선 문서 | Yes (docs) | 보안 unlock stack 뒤에 squash. |
| #80 | `9897376` | steward preview에서 인가된 steward에게 원문 값 제공 (policy masking obligation·GRC redaction은 유지) | Yes (catalog browse) | Open. OpenCode APPROVE on current SHA 후 squash. `#51`과 섞지 말 것. |
| Dependabot #27 #29 #57 #62 #63 #67 #68 #69 #70 #71 | various | Dependency currency | Yes after unlock | trivy inherit이 빨간 동안 land 금지. |

## 아직 PR이 없는 operator-facing 격차

| 격차 | steward가 체감하는 이유 | Lane |
| --- | --- | --- |
| Catalog plane이 main에 없음 | `SDP_DATABASE_DSN`은 graph-store backend만 선택합니다. `e48aa13` 기준 catalog create/patch는 여전히 모듈 전역 `catalog._DATA`를 변경하므로 DSN을 세팅해도 카탈로그 쓰기는 영속되지 않습니다(`src/sdp/catalog.py:25`, `:414`, `:445`). 유료 파일럿 persistence는 #73에만 있음 | Portal — land #73 |
| Keyverse 없이 tenant-bound catalog 없음 | 현행 preview는 caller-supplied `user` 문자열을 받아 로컬 맵으로 해석 — fail-closed identity는 목표 계약. #58 병합 + browse 인증 결선이 필요 | Consume Keyverse |
| DiskSage batch를 main에서 preview 못 함 | inventory metadata를 catalog UI에서 다룰 수 없음 | Portal adapters #59/#61 |
| Hybrid file types | 업로드 office/binary가 file ontology에 매핑되지 않음 | Portal #28 after #37 |
| Storybook scene/edge-case event inventory | 디자인 토큰·Figma file ID(`JjYSqr6nWxpARUjaVKhG16`)는 있으나 Storybook 장면별/Edge case별 event 정의가 미완 | Portal UI — Storybook stories 추가 |

## 명시적 비격차 (여기서 만들지 말 것)

- naruon document-KG write path, LineageWeave weekly-report write path (owner는 각각 naruon / LineageWeave; 포털은 pointer만).
- IRT scoring kernel.
- Keyverse issuance, SCIM, PAT minting.
- GRC control library or audit ledger.
- naruon editor, calendar, HWPX.
- 카탈로그 plane에 새로운 PII masking (현행 policy-driven `apply_mask`는 PRD P0 통제로 유지; steward 원문 노출 변경만 `#80`에서).
- 분 시각 :17의 두 번째 hourly merge loop.

## 운영 메모

- Database objects: 두 단어 이상 `snake_case`, 3NF. Catalog plane 테이블은 #73의 `migrations/0002_ontology_catalog_plane.sql`.
- 기본 CI store는 in-memory. DSN-backed store는 paid-pilot 경로이며 catalog 쓰기 영속화 자체는 #73의 범위입니다.
- `NVIDIA_NIM_API_KEY`는 contextual-orchestrator가 쓰는 **외부 connector 변수**입니다. 이 저장소의 워크플로·테스트·모듈은 현재 이 값을 참조하지 않으며, 이 문서가 유일한 언급 지점입니다. 이 저장소에서 이름을 바꾸지 마십시오. 포털 쪽 매핑은 orchestrator 계약의 `SDP_` prefix 변수를 따르고, 계약을 확인하기 전에는 새로 만들지 마십시오. `COPILOT_GITHUB_TOKEN`은 쓰지 않습니다. review-bot 키를 재조정하지 마십시오.
- Analyze (actions) 503 SARIF upload는 flake입니다. 재실행만을 위한 추가 커밋을 넣지 마십시오.
