# 제품·기술 격차 기준선 (product-technical gap baseline)

**제품 홈:** ContextualWisdomLab/semantic-data-portal (ontology 기반 semantic catalog).
**독자:** catalog steward / tenant operator.
**다음 행동:** 아래 병합 순서로 unlock stack을 올리고, 이 저장소에 local IdP나 policy registry를 만들지 마십시오.
**기준일:** 2026-08-23 (main `e48aa13`).
**Figma file ID:** not assigned.

이 파일은 포털의 살아있는 격차 목록입니다. 열린 PR이 병합되거나 consume-only 계약이 바뀌면 갱신하십시오. GitHub review 대기는 작업 중지로 보지 마십시오.

## 경계 (consume-only vs own)

| 관심사 | Owner | 포털 의무 |
| --- | --- | --- |
| Identity, SCIM, tenant header, purpose-limited authorization | Keyverse | 검증된 OIDC claim으로 tenant identity를 만들고, Keyverse가 발행한 `X-CWL-Tenant-Reference`가 없거나 불일치하면 fail-closed. 포털은 이 헤더를 자체 서명하지 않습니다. Observability용 `X-SDP-Tenant`는 인가 결정에 쓰지 않습니다. local IdP 없음. |
| Policy, control, evidence, audit truth | GRC 홈 | evidence contract만 소비. local policy registry 없음. |
| Organization security gates | CWL Security | 중앙 워크플로를 상속합니다. 포함: Security Scan, Strix, CodeQL, Semgrep, python-security, osv-scan, diff-scoped dependency-review, repo-wide trivy-fs(fixable CRITICAL/HIGH). 두 번째 gate loop를 포크하지 마십시오. |
| Ontology registry and catalog plane | **this repo** | Glossary, catalog objects, bindings, provenance pointers. |
| Document knowledge graph / weekly report | LineageWeave (#74) | #74→main을 포털 블로커로 보지 마십시오. commons provenance만 소비. |
| IRT / linking scores | fast-mlsirm | 호출만 하고 재구현하지 마십시오. |
| Employment tree | Orgmetra | affiliation key만 소비. |
| Office authoring | naruon | sender-ontology consumer only. |
| Measurement import | TEPP | Import/REST only. |
| Disk inventory | DiskSage | Catalog ingest/preview adapter only. |

PII는 업무에 그대로 필요합니다. 이 저장소에는 masking을 넣지 마십시오. purpose-limited authorization의 계약 주인은 Keyverse이고, 응답 최소화·redaction·evidence export 계약 주인은 GRC입니다. 포털은 두 계약을 fail-closed로 소비할 뿐, unmasked 노출이 허용된다는 뜻이 아닙니다.

## 이미 채택한 표준 (APA 7th)

Albertoni, R., Browning, D., Cox, S., Gonzalez Beltran, A., Perego, A., & Winstanley, P. (Eds.). (2024). *Data Catalog Vocabulary (DCAT) — Version 3*. World Wide Web Consortium. https://www.w3.org/TR/vocab-dcat-3/  
포털 계약: catalog object·distribution·dataset 식별은 DCAT 3 resource 모델을 따릅니다.

International Organization for Standardization. (2023). *Information technology — Metadata registries (MDR) — Part 1: Framework* (ISO/IEC 11179-1:2023). https://www.iso.org/standard/78914.html  
포털 계약: glossary term과 administered item 식별은 MDR framework의 등록 의미를 따릅니다. 유료 본문은 인용만 하고 전문을 복제하지 않습니다.

Moreau, L., & Missier, P. (Eds.). (2013). *PROV-DM: The PROV data model*. World Wide Web Consortium. https://www.w3.org/TR/prov-dm/  
포털 계약: catalog 변경은 provenance pointer(PROV entity/activity)로만 남기고 KG write는 LineageWeave에 두지 않습니다.

이후 커밋이 이 계약과 어긋나면 인용을 바꾸지 말고 코드를 고치십시오.

## 병합 순서 (steward)

1. **#51** `558dd2f` — outbound URL harden + cryptography CVE. 다른 포털 PR의 `trivy-fs`를 풉니다. Frozen. 이 head를 push하지 마십시오. 이 SHA에 OpenCode APPROVE가 붙은 뒤 Product Manager squash.
2. **#58** `80966ae` — bounded Keyverse claim aliases. Frozen. 같은 merge gate.
3. **#35** `9c12f5d` **그리고 #32** `76fcfb6` (SQL gate). 둘 다 catalog plane SQL 표면의 전제입니다. **#32는 non-blocking이 아닙니다. #73보다 먼저** 병합하십시오. Frozen heads는 push하지 마십시오.
4. **#73** `bfa409f` — catalog/ontology plane (#13). 제품 검사는 초록, 남은 빨강은 #51에서 inherit한 `trivy-fs`. push 보류. **#75는 #73이 main에 올 때까지 Draft.**
5. **#28** after **#37** — trusted document deps 위의 hybrid file ontology.
6. **#59** / **#61** — DiskSage ingest and preview boundary.
7. **#64** product names (#51 이후, docs 실패로 trivy inherit을 받지 않게), then **#65** setuptools, then Dependabot.

#51 security-lock 파일을 catalog/docs PR에 섞지 마십시오. 이 문서 PR(#79)도 #51보다 먼저 병합하지 마십시오.

## 열린 PR과 각 PR이 닫는 격차

| PR | Head | 격차 | 포털 소유? | 상태 2026-08-23 |
| --- | --- | --- | --- | --- |
| #51 | `558dd2f` | Cryptography CVE / trivy-fs unlock; outbound URL allowlist | Yes (security lock) | HOLD. 현재 SHA OpenCode APPROVE 없음. |
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
| #79 | `6ff7288` | 이 기준선 문서 | Yes (docs) | #51 뒤에만 squash. |
| Dependabot #27 #29 #57 #62 #63 #67 #68 #69 #70 #71 | various | Dependency currency | Yes after unlock | trivy inherit이 빨간 동안 land 금지. |

## 아직 PR이 없는 operator-facing 격차

| 격차 | steward가 체감하는 이유 | Lane |
| --- | --- | --- |
| Catalog plane이 main에 없음 | `SDP_DATABASE_DSN`이 없으면 glossary/catalog가 프로세스 재시작에 사라짐. 유료 파일럿 persistence는 #73에만 있음 | Portal — land #73 |
| Keyverse 없이 tenant-bound catalog 없음 | fail-closed는 맞음. #58 병합 전에는 steward가 browse할 수 없음 | Consume Keyverse |
| DiskSage batch를 main에서 preview 못 함 | inventory metadata를 catalog UI에서 다룰 수 없음 | Portal adapters #59/#61 |
| Hybrid file types | 업로드 office/binary가 file ontology에 매핑되지 않음 | Portal #28 after #37 |
| Storybook + design tokens | `docs/design-tokens.md`는 있음. Figma file ID 없음. scene/edge-case event inventory 미완 | Portal UI — Figma ID를 만들지 말 것 |

## 명시적 비격차 (여기서 만들지 말 것)

- LineageWeave weekly report / KG write path.
- IRT scoring kernel.
- Keyverse issuance, SCIM, PAT minting.
- GRC control library or audit ledger.
- naruon editor, calendar, HWPX.
- PII masking.
- 분 시각 :17의 두 번째 hourly merge loop.

## 운영 메모

- Database objects: 두 단어 이상 `snake_case`, 3NF. Catalog plane 테이블은 #73의 `migrations/0002_ontology_catalog_plane.sql`.
- 기본 CI store는 in-memory. DSN-backed store는 paid-pilot 경로.
- `NVIDIA_NIM_API_KEY`는 contextual-orchestrator가 쓰는 **외부 connector 변수**입니다. 이 저장소에서 이름을 바꾸지 마십시오. 포털 쪽 매핑은 orchestrator 계약의 `SDP_` prefix 변수를 따르고, 계약을 확인하기 전에는 새로 만들지 마십시오. `COPILOT_GITHUB_TOKEN`은 쓰지 않습니다. review-bot 키를 재조정하지 마십시오.
- Analyze (actions) 503 SARIF upload는 flake입니다. 재실행만을 위한 추가 커밋을 넣지 마십시오.
