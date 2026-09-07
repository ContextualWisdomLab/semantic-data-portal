# 제품·기술 격차 기준선 (product-technical gap baseline)

**제품 홈:** ContextualWisdomLab/semantic-data-portal (ontology 기반 semantic catalog).
**독자:** catalog steward / tenant operator.
**다음 행동:** 아래 병합 순서로 unlock stack을 올리고, 이 저장소에 local IdP나 policy registry를 만들지 마십시오.
**기준일:** 2026-09-07 (main `e48aa13`, 변동 없음).
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
| Lineage DAG reconstruction / weekly report | [`ContextualWisdomLab/LineageWeave`](https://github.com/ContextualWisdomLab/LineageWeave) | 산발 레코드에서 lineage thread를 재구성하는 것은 LineageWeave 소관입니다. 포털은 결과를 소비하고 provenance pointer만 저장하며, 어떤 KG write 경로도 호출하지 않습니다. LineageWeave 쪽 작업은 포털 블로커가 아닙니다. **정정(2026-09-07):** 이전 판은 이 lane을 맨 `#74`로 인용했지만, 맨 `#74`는 이 저장소의 issue #74([Product Gap] framework-neutral data management evidence, `#75`가 구현)로 해석되어 다른 대상을 가리켰습니다. 추적 대상을 잃지 않도록 소유 저장소를 직접 링크했습니다. 개별 issue/PR을 인용할 때는 조직 규약대로 `ContextualWisdomLab/LineageWeave#<번호>` 형태로 쓰십시오 — 구체 번호는 이 저장소에 기록된 바 없으므로, 확인한 사람이 이 줄에 채워 넣으십시오. |
| IRT / linking scores | fast-mlsirm | 호출만 하고 재구현하지 마십시오. |
| Employment tree | Orgmetra | affiliation key만 소비. |
| Office authoring | naruon | sender-ontology consumer only. |
| Measurement import | TEPP | Import/REST only. |
| Disk inventory | DiskSage | Catalog ingest/preview adapter only. |
| CEFR / RLD official prose | Council of Europe / licensed language-profile authority | 메타데이터·opaque descriptor 참조만 등록. 공식 descriptor 본문, 번역, 표, RLD 어휘 목록, 매뉴얼 텍스트를 복제하지 마십시오. 계약 소유는 `learning-interoperability-contracts` (`cwl_cefr_language_assessment/v1`). |

PII는 업무에 그대로 필요합니다. **현행 계약을 유지하십시오:** `browse.preview`의 policy-driven `apply_mask`는 PRD P0 통제(`docs/prd-trd.md:402`, `:431`)이며 그대로 둡니다. 카탈로그 plane에 *새로운* masking을 추가하지 마십시오. purpose-limited authorization 계약 주인은 Keyverse, 응답 최소화·redaction·evidence export 계약 주인은 GRC입니다. authorization+audit은 접근 주체와 사후 추적을 제어할 뿐, response 복사본을 제거하지 않으므로, redaction 소유자는 GRC임을 명시해 둡니다.

main `e48aa13`에서 `/browse/{dataset_id}/preview`는 caller-supplied `user` 문자열을 받아 로컬 정적 맵으로 해석합니다(`src/sdp/api.py:804-814`). 즉 Keyverse-bound fail-closed identity는 목표 계약이지 현행 상태가 아닙니다. 이 격차는 아래 operator-facing 격차 표에 열려 있습니다. PR `#80` (`01f9720`)은 인가된 steward preview에서 원문 값을 보여주도록 steward 경로만 바꾸며, policy masking obligation과 GRC evidence export redaction은 그대로 유지합니다. `#51` security-lock과 섞지 말고, squash는 현재 SHA OpenCode APPROVE 뒤에서만 하십시오. 이 PR에 다시 restore를 올리지 마십시오.

## 이미 채택한 표준 (APA 7th)

Albertoni, R., Browning, D., Cox, S., Gonzalez Beltran, A., Perego, A., & Winstanley, P. (Eds.). (2024). *Data Catalog Vocabulary (DCAT) — Version 3*. World Wide Web Consortium. https://www.w3.org/TR/vocab-dcat-3/
포털 계약: catalog object·distribution·dataset 식별은 DCAT 3 resource 모델을 따릅니다.

International Organization for Standardization. (2023). *Information technology — Metadata registries (MDR) — Part 1: Framework* (ISO/IEC 11179-1:2023). https://www.iso.org/standard/78914.html
포털 계약: glossary term과 administered item 식별은 MDR framework의 등록 의미를 따릅니다. 유료 본문은 인용만 하고 전문을 복제하지 않습니다.

Moreau, L., & Missier, P. (Eds.). (2013). *PROV-DM: The PROV data model*. World Wide Web Consortium. https://www.w3.org/TR/prov-dm/
포털 계약: catalog 변경은 provenance pointer(PROV entity/activity)로만 남깁니다. document-KG write owner는 naruon, lineage 재구성은 LineageWeave 소관이며, 포털은 어느 쪽 write 경로도 호출하지 않습니다.

Council of Europe. (2020). *Common European Framework of Reference for Languages: Learning, teaching, assessment — Companion volume*. Council of Europe Publishing. https://www.coe.int/en/web/common-european-framework-reference-languages
포털 계약: CEFR 프레임워크·descriptor·language-profile 참조만 등록합니다. 공식 본문을 복제하지 않고, 점수·연계·인증 권한을 주장하지 않습니다. 구현은 `learning-interoperability-contracts` PR #5가 머지되고 계약이 릴리스된 뒤에만 시작합니다.

이후 커밋이 이 계약과 어긋나면 인용을 바꾸지 말고 코드를 고치십시오.

## 병합 순서 (steward)

1. PR `#81` `ce40bd8` — cryptography 49.0.0 → 50.0.0 (CVE-2026-69247 / GHSA-g6cj-pr64-35w5). trivy-fs는 merge ref를 스캔하므로 이 PR이 main에 올리면 모든 열린 PR이 상속해 풀립니다. OpenCode exact-head APPROVE 확인(comment 5469292683) 뒤에만 PM squash. 3초 `opencode-review` stub는 receipt가 아닙니다. `#51`과 섞지 마십시오.
   **상태 변경(2026-09-07): 이 PR은 현재 Draft입니다.** head는 `ce40bd8` 그대로지만 본문이 `Draft / source+lock repair present`로 바뀌었습니다. 즉 unlock stack의 1번 항목이 스스로 merge 대기열에서 빠진 상태이며, repo-wide trivy-fs unlock은 이 PR이 Ready로 돌아올 때까지 열리지 않습니다. Draft를 우회하려고 다른 PR에 cryptography bump를 복제하지 마십시오 — single writer는 `#81`입니다. 조치는 `#81`의 repair를 끝내고 Ready 전환하는 것이며, 그 전까지 2번 이하 항목의 trivy-fs 상속 실패는 예상된 상태입니다.
2. PR `#51` `558dd2f` — outbound URL harden + security lock (cryptography 부분은 `#81`이 흡수). Frozen. 이 head를 push하지 마십시오. 이 SHA에 OpenCode APPROVE가 붙은 뒤 Product Manager squash.
3. PR `#58` `0ce6d1f` — bounded Keyverse claim aliases. Frozen (strix fail on this head). 이전 APPROVE는 `80966ae`/`47e2215c` 뒷 SHA. extra-push 금지.
4. PR `#35` `9c12f5d` **그리고** PR `#32` `76fcfb6` (SQL gate). 둘 다 catalog plane SQL 표면의 전제입니다. **`#32`는 non-blocking이 아닙니다. `#73`보다 먼저** 병합하십시오. Frozen heads는 push하지 마십시오.
5. PR `#73` `311668e` — catalog/ontology plane (#13). Frozen. trivy-fs inherit + strix fail. `#84` corporate-master 구현은 이 PR 뒤; extra-push 금지. **`#75`는 `#73`이 main에 올 때까지 Draft.**
6. PR `#28` after PR `#37` — trusted document deps 위의 hybrid file ontology.
7. PR `#59` / `#61` — DiskSage ingest and preview boundary.
8. PR `#64` product names after `#51`, then PR `#65` setuptools, then Dependabot.
9. PR `#82` `a797e30` — customer-next-action copy. `#81` 뒤, Dependabot 앞.
10. PR `#88` `8e281de` — Measurement Context Registry. `#81`/`#51`/`#58`/`#73` 뒤. 점수·응답·판정 소유 없음.
11. ~~PR `#90` — public Pages landing source~~ — **2026-09-02에 병합 없이 closed(정상 승계).** `docs/index.md`는 `#72` `10096ce`가 담고 있으므로 landing은 `#72` 순서를 따릅니다. `#72`는 현재 Draft이며, Ready·병합 시 landing이 main에 올라갑니다. Pages-source PR을 새로 만들지 마십시오.
12. PR `#89` `3b59d90` Draft — DatasetDistribution 식별자 의미화 (`distribution_id` / `distribution_format` / `distribution_endpoint`); 와이어 계약 `{id, format, endpoint}` 유지. `#81`/`#51`/`#58`/`#73`보다 앞세우지 말 것. checks가 초록이 될 때까지 Draft 유지. (head가 `0a06e20`에서 `3b59d90`으로 이동했습니다.)
13. PR `#92` `51fb384` Draft — evidence store의 영속 식별자 의미화. `#89`와 같은 명명 규약(두 단어 이상 snake_case) 작업이며, evidence 스키마를 건드리므로 `#73` 뒤에 둡니다. Draft 유지.
14. PR `#93` `1dcca7b` / PR `#100` `5bba1e6` — Actions 검증 워크플로 정리. **두 PR이 서로 겹칩니다(아래 CI 거버넌스 절 참조).** 겹침을 정리하기 전에는 어느 쪽도 병합하지 마십시오.
15. PR `#96` `baa536b` → `#97` `dff4668` / `#99` `c3f0162` (모두 Draft) — OpenMetadata 2.x read-only 정규화 경계와 admission receipt. `#97`과 `#99`는 둘 다 `#96`의 브랜치(`feat/openmetadata-2-read-adapter`)를 base로 하는 stacked PR입니다. `#96`이 먼저이고, `#99`는 `#97`의 보안 경계 repair successor로 보입니다 — 둘 중 하나를 닫기 전에 delta 승계를 확인하십시오. consume-only 경계(외부 catalog는 read-only)를 넘지 마십시오.

PR `#51` security-lock 파일을 catalog/docs PR에 섞지 마십시오. 이 문서 PR(`#79`)도 보안 unlock stack 뒤에서 squash하십시오. `#80`은 `#51` security-lock과 별개이며 squash는 현재 SHA OpenCode APPROVE 뒤에만 합니다. (`#90`은 closed되어 이 순서에서 빠졌고, 그 landing delta는 `#72`가 잇습니다.)

## 열린 PR과 각 PR이 닫는 격차

Head SHA와 draft 여부는 2026-09-07 GitHub API 응답에서 그대로 옮겼습니다. 열린 PR은 35건입니다.

| PR | Head | 격차 | 포털 소유? | 상태 2026-09-07 |
| --- | --- | --- | --- | --- |
| #81 | `ce40bd8` **Draft** | cryptography 50.0.0 — CVE-2026-69247, repo-wide trivy-fs unlock. 추적 issue #101 | Yes (shared base) | **Draft로 내려감**(본문 `source+lock repair present`). head는 그대로. Ready 전환 전까지 unlock stack 전체가 대기. issue #101은 열려 있으므로 CVE는 미해결 상태입니다. bump를 다른 PR로 복제하지 말 것. |
| #51 | `558dd2f` | Outbound URL allowlist + security lock (cryptography CVE 부분은 `#81`이 선행 흡수) | Yes (security lock) | HOLD. extra-push 금지. |
| #58 | `0ce6d1f` | Keyverse claim aliases fail-closed | Keyverse 소비, adapter는 여기 | HOLD. strix fail. extra-push 금지. |
| #35 | `9c12f5d` | SQL comma-join allowlist bypass | Yes | HOLD. extra-push 금지. |
| #32 | `76fcfb6` | SELECT..INTO / volatile SQL bypass | Yes | #73 전제. #35/#51 뒤. |
| #73 | `311668e` | Catalog plane above the document KG (#13). ADR 0002 / stacked #83 already on this branch | Yes | HOLD. trivy-fs + strix fail. `#84` extra-push 금지. |
| #75 | `6cba648` Draft | Framework-neutral data-management evidence *profiles* (GRC registry 아님). issue #74 구현 | Yes (catalog evidence shape) | Draft. base가 main이 아니라 `#73`의 브랜치(`cursor/ontology-catalog-plane-90aa…`)이므로 `#73` 뒤에서만 의미가 있습니다. dirty. Ready로 돌아가면 다시 Draft. |
| #82 | `a797e30` | customer-next-action copy, hide internal boundaries | Yes (UX copy) | `#81` 뒤. |
| #88 | `8e281de` | Measurement Context Registry (Draft/Published/Superseded) | Yes (catalog aggregate) | Ready. `#81`/`#51`/`#58`/`#73` 뒤. 점수·응답·판정 없음. |
| #59 | `65e4fd7` | DiskSage catalog ingest | Adapter yes | HOLD. extra-push 금지. |
| #61 | `0c248d2` | DiskSage preview boundary | Adapter yes | Open; Analyze flake — extra-push 금지. |
| #28 | `5e4b11c` | Hybrid file ontology | Yes after #37 | Wait #37. |
| #37 | `00ee8af` | Trusted document semantic deps | Yes (build) | Open. |
| #64 | `4b78611` | Current CWL product names | Yes (docs) | After #51. |
| #65 | `19603c3` | setuptools 83 | Yes (build) | After unlock. |
| #72 | `10096ce` Draft | Operator README / draft ADRs **+ public Pages landing `docs/index.md`** (`#90`에서 승계) | Yes (docs) | Draft. head가 `e1fe375`에서 이동했습니다. 이제 landing의 single writer이므로 `#90`을 되살리거나 Pages-source를 복제하지 마십시오. |
| #79 | `21bcc86` | 이 기준선 문서 | Yes (docs) | 보안 unlock stack 뒤에 squash. main에는 아직 없음. |
| #89 | `3b59d90` Draft | DatasetDistribution 식별자 의미화; 와이어 `{id, format, endpoint}` 유지 | Yes (catalog naming) | Draft. `#81`/`#73` 뒤. Ready 전환 금지 until checks green. extra-push 금지. |
| #92 | `51fb384` Draft | evidence 영속 식별자 의미화(두 단어 이상 snake_case) | Yes (evidence naming) | Draft. `#89`와 같은 명명 lane, evidence 스키마를 건드리므로 `#73` 뒤. |
| #80 | `01f9720` | steward preview에서 인가된 steward에게 원문 값 제공 (policy masking obligation·GRC redaction은 유지) | Yes (catalog browse) | Open. restore 재시도 금지. |
| #93 | `1dcca7b` | Scorecard 중앙 reusable 위임 + ghost workflow 11건 비활성 + docs-only fuzz skip(`#94` 흡수) + 동시성 그룹 | Yes (CI) | Open. **`#100`과 겹침** — 아래 CI 거버넌스 절. |
| #100 | `5bba1e6` | PR 동시성 격리 + Draft/closed PR runner job skip | Yes (CI) | Open. **`#93`과 겹침** — 아래 CI 거버넌스 절. |
| #96 | `baa536b` Draft | OpenMetadata 2.x read-only 정규화 경계 | Yes (consume-only adapter) | Draft. `#97`/`#99`의 base. |
| #97 | `dff4668` Draft | 결정적 OpenMetadata admission preview receipt | Yes (adapter) | Draft. base = `#96` 브랜치. `#99`와 같은 base — 승계 관계 확인 필요. |
| #99 | `c3f0162` Draft | admission receipt를 보안 경계 위에서 재구성 | Yes (adapter) | Draft. base = `#96` 브랜치. `#97`의 repair successor로 보임; delta 승계 확인 전 어느 쪽도 닫지 말 것. |
| Dependabot #27 #29 #57 #62 #63 #67 #68 #69 #70 #71 | `8aad3b4` `3205628` `fb48fc9` `8d1c6c0` `3de2562` `cc1e623` `a0116a0` `b874efd` `4342b06` `e53e921` | Dependency currency | Yes after unlock | `#81` 이전 land 금지. |

### 2026-09-07에 목록에서 빠진 PR

| PR | 결과 | 조치 |
| --- | --- | --- |
| #90 `3a23f87` | 병합 없이 closed (2026-09-02) | **정상 승계이며 복구 대상이 아닙니다.** PR 본문에 따르면 이 lane의 publication·license 경계 값이 `#72`의 `10096ce`로 흡수되었고, `#72`가 이미 더 강한 `docs/index.md`(48줄 신규)를 담고 있습니다. `#72` 파일 목록에서 확인했습니다. 별도 Pages-source PR을 다시 만들지 마십시오 — landing의 single writer는 `#72`입니다. |
| #94 | 병합 없이 closed | `#93`이 docs-only fuzz skip delta를 본문에서 명시적으로 흡수했습니다("Supersede #94"). 정상적인 승계 후 종료이며 복구 대상이 아닙니다. |

## 아직 PR이 없는 operator-facing 격차

| 격차 | steward가 체감하는 이유 | Lane |
| --- | --- | --- |
| Catalog plane이 main에 없음 | `SDP_DATABASE_DSN`은 graph-store backend만 선택합니다. `e48aa13` 기준 catalog create/patch는 여전히 모듈 전역 `catalog._DATA`를 변경하므로 DSN을 세팅해도 카탈로그 쓰기는 영속되지 않습니다(`src/sdp/catalog.py:25`, `:414`, `:445`). 유료 파일럿 persistence는 #73에만 있음 | Portal — land #73 |
| Keyverse 없이 tenant-bound catalog 없음 | 현행 preview는 caller-supplied `user` 문자열을 받아 로컬 맵으로 해석 — fail-closed identity는 목표 계약. #58 병합 + browse 인증 결선이 필요 | Consume Keyverse |
| DiskSage batch를 main에서 preview 못 함 | inventory metadata를 catalog UI에서 다룰 수 없음 | Portal adapters #59/#61 |
| Hybrid file types | 업로드 office/binary가 file ontology에 매핑되지 않음 | Portal #28 after #37 |
| Storybook scene/edge-case event inventory | 디자인 토큰·Figma file ID(`JjYSqr6nWxpARUjaVKhG16`)는 있으나 Storybook 장면별/Edge case별 event 정의가 미완 | Portal UI — Storybook stories 추가 |
| Public Pages landing이 main에 없음 | `docs/index.md`는 `#72`(Draft, `10096ce`)에만 있고 main에는 없습니다. `#90`은 그 delta를 `#72`로 넘기고 닫혔으므로 PR 없는 격차가 아니라 **`#72` 대기** 상태입니다. 잠재 구매자가 볼 진입점은 `#72`가 Ready·병합될 때 열립니다 | Portal docs — land `#72` |
| Data management evidence console (#78) / persist registry (#76) | 프로필(#75) 뒤에 console·영속 API. #75는 #73 전까지 Draft | Portal after #73/#75 |
| Governed corporate-master unique/miss/tie (#84) | ADR 0002 / `sdp.corporate-master-resolution/v1`은 #73 보드(스택 #83 merged). 실행 엔드포인트는 #73가 main에 온 뒤. extra-push 금지 | Portal after #73 |
| CEFR framework / descriptor / language-profile registry (#86, #87) | 공식 descriptor 정보·권리 메타데이터가 카탈로그에 없음. `cwl_cefr_language_assessment/v1` 구현은 LIC PR #5가 머지되고 계약이 릴리스된 뒤에만 | Portal after released contract; no scoring |

## 명시적 비격차 (여기서 만들지 말 것)

- naruon document-KG write path, LineageWeave weekly-report write path (owner는 각각 naruon / LineageWeave; 포털은 pointer만).
- IRT scoring kernel.
- Keyverse issuance, SCIM, PAT minting.
- GRC control library or audit ledger.
- naruon editor, calendar, HWPX.
- CEFR 공식 descriptor 본문 복제, Council of Europe logo, 점수 kernel, certification claim.
- 카탈로그 plane에 새로운 PII masking (현행 policy-driven `apply_mask`는 PRD P0 통제로 유지; steward 원문 노출 변경만 `#80`에서).
- 분 시각 :17의 두 번째 hourly merge loop.

## ADR 번호 충돌 (repair finding, 2026-09-07) — issue #103

추적 issue는 #103입니다. `main`에는 `docs/adr/` 디렉터리가 아직 없습니다. 그런데 열린 PR 다섯 건이 같은 네 자리 번호를 서로 다른 주제로 각자 추가하고 있습니다.

| 번호 | PR | 파일 | 주제 |
| --- | --- | --- | --- |
| 0001 | #72 | `docs/adr/0001-product-authority-boundary.md` | 제품 권한 경계 |
| 0001 | #73 | `docs/adr/0001-ontology-catalog-plane.md` | ontology/catalog plane |
| 0001 | #88 | `docs/adr/0001-measurement-context-registry.md` | measurement context registry |
| 0001 | #96 | `docs/adr/0001-openmetadata-anti-corruption-boundary.md` | OpenMetadata ACL 경계 |
| 0002 | #72 | `docs/adr/0002-semantic-web-grounding.md` | semantic web grounding |
| 0002 | #73 | `docs/adr/0002-corporate-master-resolution-owner.md` | corporate-master 소유 |
| 0002 | #97 / #99 | `docs/adr/0002-openmetadata-admission-preview-receipts.md` | admission preview receipt |

`#97`과 `#99`가 같은 경로를 쓰는 것은 둘이 같은 lane의 승계 관계이므로 예외입니다. 나머지는 서로 무관한 결정을 같은 번호로 주장합니다.

**왜 문제인가.** 먼저 병합되는 PR이 그 번호를 선점하고, 뒤따르는 PR은 add/add 충돌을 내거나 조용히 같은 번호의 다른 결정을 덮습니다. 결정 기록의 식별자가 흔들리면 "ADR 0002"라는 참조가 시점에 따라 다른 문서를 가리키게 됩니다. 실제로 이 기준선 문서도 `#73`의 corporate-master 결정을 "ADR 0002"로 인용하고 있는데, `#72`가 먼저 병합되면 그 번호는 semantic-web-grounding을 가리키게 됩니다.

**조치는 rename이지 redesign이 아닙니다.** 어떤 PR도 닫지 말고 내용도 바꾸지 마십시오. 번호만 병합 순서대로 재배정하고, 각 PR 안의 상호 참조와 이 문서의 인용을 함께 고칩니다. 위 병합 순서를 그대로 적용하면 다음과 같이 떨어집니다.

| 순서 근거 | PR | 배정 |
| --- | --- | --- |
| 병합 순서 5번 | #73 | `0001` ontology-catalog-plane, `0002` corporate-master-resolution-owner (현행 유지, rename 불필요) |
| 병합 순서 10번 | #88 | `0003` measurement-context-registry |
| 병합 순서 15번 | #96 | `0004` openmetadata-anti-corruption-boundary |
| `#96` 뒤 | #97 / #99 | `0005` openmetadata-admission-preview-receipts (승계된 한쪽만) |
| Draft, 순서 미정 | #72 | `0006`~`0009` (product-authority-boundary, semantic-web-grounding, graph-vector-retrieval, docs-only-scope). Ready 전환 시점에 남은 번호로 확정 |

번호 배정은 owner 결정입니다. 위 표는 현재 문서화된 병합 순서에서 기계적으로 도출한 기본안이며, 순서가 바뀌면 배정도 같이 바뀝니다. 확정 전까지 새 ADR을 `0001`/`0002`로 추가하지 마십시오.

## CI 거버넌스: PR 동시성 그룹과 `#93`/`#100` 겹침

조직 계약상 PR Actions의 `concurrency.group`은 `{workflow명}-{repository}-{PR번호}`입니다. 간접 호출이라 PR 번호를 못 얻으면 그룹을 조립하지 말고 실패시키십시오. 취소는 같은 그룹의 구형 실행에만(`cancel-in-progress: true`) 적용하고, 다른 workflow·repository·PR은 서로 독립입니다. merge·release·deploy·migration은 취소 대상이 아니며 lock·idempotency·exact-head로 직렬화합니다.

`#93` `1dcca7b`와 `#100` `5bba1e6`은 이 계약을 각자 구현하면서 **같은 파일 세 개를 동시에 건드립니다.**

| 파일 | `#93` | `#100` |
| --- | --- | --- |
| `.github/workflows/fuzz.yml` | 수정 | 수정 |
| `.github/workflows/tests.yml` | 수정 | 수정 |
| `tests/test_workflow_concurrency_contract.py` | **신규 추가** | **신규 추가** |
| `.github/workflows/scorecard-analysis.yml` | 수정 | — |

같은 경로를 양쪽이 `added`로 올리므로 먼저 병합된 쪽이 상대에게 add/add 충돌을 남깁니다. 그룹 식은 사실상 같습니다 — `#93`은 `github.event.pull_request.number || github.run_id`, `#100`은 `github.event_name == 'pull_request' && github.event.pull_request.number || github.run_id`로 event 종류를 명시적으로 검사합니다.

각자 상대에게 없는 delta가 있습니다.

- `#93`만: Scorecard를 중앙 immutable reusable workflow로 위임, ghost workflow 등록 11건 비활성, docs-only fuzz skip(`#94` 흡수).
- `#100`만: Draft·closed PR에서 runner job을 시작하지 않는 `if:` 가드. 이것도 조직 계약에 포함된 요구사항입니다.

**조치: 어느 쪽도 닫지 마십시오.** 단일 writer를 정하고 나머지 delta를 그 PR로 합치는 것이 규약입니다(폐기가 아니라 통합). `#93`이 상위 집합에 가까우므로 `#93`을 동시성 계약 파일의 writer로 두고 `#100`의 Draft/closed 가드를 `#93`으로 옮기는 편이 충돌 표면이 작습니다. 반대로 정하려면 `#93`의 Scorecard·ghost workflow·docs-only skip delta가 통째로 승계되어야 합니다. 어느 쪽이든 `tests/test_workflow_concurrency_contract.py`는 최종적으로 한 PR에서만 추가되어야 합니다.

## 운영 메모

- Database objects: 두 단어 이상 `snake_case`, 3NF. Catalog plane 테이블은 #73의 `migrations/0002_ontology_catalog_plane.sql`.
- 기본 CI store는 in-memory. DSN-backed store는 paid-pilot 경로이며 catalog 쓰기 영속화 자체는 #73의 범위입니다.
- `NVIDIA_NIM_API_KEY`는 contextual-orchestrator가 쓰는 **외부 connector 변수**입니다. 이 저장소의 워크플로·테스트·모듈은 현재 이 값을 참조하지 않으며, 이 문서가 유일한 언급 지점입니다. 이 저장소에서 이름을 바꾸지 마십시오. 포털 쪽 매핑은 orchestrator 계약의 `SDP_` prefix 변수를 따르고, 계약을 확인하기 전에는 새로 만들지 마십시오. `COPILOT_GITHUB_TOKEN`은 쓰지 않습니다. review-bot 키를 재조정하지 마십시오.
- Analyze (actions) 503 SARIF upload는 flake입니다. 재실행만을 위한 추가 커밋을 넣지 마십시오.
