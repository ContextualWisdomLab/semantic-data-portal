# 제품·기술 격차 기준선 (product-technical gap baseline)

**제품 홈:** ContextualWisdomLab/semantic-data-portal (ontology 기반 semantic catalog).
**독자:** catalog steward / tenant operator.
**다음 행동:** 아래 병합 순서로 unlock stack을 올리고, 이 저장소에 local IdP나 policy registry를 만들지 마십시오.
**기준일:** 2026-09-09 (main `e48aa13`, 변동 없음). 2026-09-09에 리뷰 판정 증거를 전수 재검증했고, 그 결과 병합 순서 1번·3번의 승인 근거와 "승인만 있으면 풀리는 세 건" 권고를 정정했습니다 — 아래 "정정(2026-09-09)" 절을 먼저 읽으십시오.
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

1. PR `#81` `ce40bd8` — cryptography 49.0.0 → 50.0.0 (CVE-2026-69247 / GHSA-g6cj-pr64-35w5). trivy-fs는 merge ref를 스캔하므로 이 PR이 main에 올리면 모든 열린 PR이 상속해 풀립니다. **정정(2026-09-09): 이 자리에 있던 “OpenCode exact-head APPROVE 확인(comment 5469292683)” 지시는 틀렸습니다.** comment 5469292683은 승인 receipt가 아니라 seonghobae가 `@opencode-agent`에게 승인을 **요청한** 코멘트입니다(2026-08-30T14:33:54Z, 본문 첫 줄 `Please APPROVE exact current head ce40bd8...`). `GET /repos/ContextualWisdomLab/semantic-data-portal/pulls/81/reviews`는 `opencode-agent[bot]`의 리뷰를 **어느 커밋에서도 0건** 반환합니다. 즉 이 PR에는 승인은 물론 `CHANGES_REQUESTED`조차 없습니다. 요청 코멘트를 승인 증거로 읽지 마십시오 — squash 조건은 여전히 미충족입니다. **그리고 이 PR은 Draft인 한 그 조건을 충족할 수 없습니다** — 스케줄러가 Draft PR을 skip하므로 리뷰 dispatch 자체가 발행되지 않습니다(아래 "`#81`은 Draft라서 판정을 받을 수 없고…" 절). 먼저 필요한 것은 승인이 아니라 **Ready 전환**입니다. 3초 `opencode-review` stub는 receipt가 아닙니다. `#51`과 섞지 마십시오.
   **상태 변경(2026-09-07): 이 PR은 현재 Draft입니다.** head는 `ce40bd8` 그대로지만 본문이 `Draft / source+lock repair present`로 바뀌었습니다. 즉 unlock stack의 1번 항목이 스스로 merge 대기열에서 빠진 상태이며, repo-wide trivy-fs unlock은 이 PR이 Ready로 돌아올 때까지 열리지 않습니다. Draft를 우회하려고 다른 PR에 cryptography bump를 복제하지 마십시오 — single writer는 `#81`입니다. 조치는 `#81`의 repair를 끝내고 Ready 전환하는 것이며, 그 전까지 2번 이하 항목의 trivy-fs 상속 실패는 예상된 상태입니다.
2. PR `#51` `558dd2f` — outbound URL harden + security lock (cryptography 부분은 `#81`이 흡수). Frozen. 이 head를 push하지 마십시오. 이 SHA에 OpenCode APPROVE가 붙은 뒤 Product Manager squash.
3. PR `#58` `0ce6d1f` — bounded Keyverse claim aliases. Frozen (strix fail on this head). extra-push 금지. **정정(2026-09-09): 이 줄의 “이전 APPROVE” 표현은 API 상태와 어긋납니다.** 현재 head `0ce6d1f`에 붙은 `opencode-agent[bot]` 리뷰는 존재하지만 API `state`가 `DISMISSED`입니다. 그 리뷰 **본문** 끝에 `- Result: APPROVE`와 `- Head SHA: 80966ae...`가 적혀 있어 승인처럼 보이지만, 본문이 주장하는 SHA는 그 리뷰 자신의 `commit_id`(`0ce6d1f`)와도 다릅니다. 판정은 리뷰 본문 산문이 아니라 API의 `state` + `commit_id`로만 읽으십시오.
4. PR `#35` `9c12f5d` **그리고** PR `#32` `76fcfb6` (SQL gate). 둘 다 catalog plane SQL 표면의 전제입니다. **`#32`는 non-blocking이 아닙니다. `#73`보다 먼저** 병합하십시오. Frozen heads는 push하지 마십시오.
5. PR `#73` `1681a7f` — catalog/ontology plane (#13). Frozen. trivy-fs inherit + strix fail. `#84` corporate-master 구현은 이 PR 뒤; extra-push 금지. **`#75`는 `#73`이 main에 올 때까지 Draft.** **정정(2026-09-09): head가 `311668e` → `1681a7f`로 이동했고(같은 날 203행이 이미 기록), 이 문서의 5번·PR 표는 옛 SHA로 남아 있었습니다.** 새 head `1681a7f`에는 `opencode-agent[bot]`의 `CHANGES_REQUESTED`(review id 5152624078)가 붙어 있습니다. 즉 이 PR은 “승인 대기”가 아니라 **요청된 수정이 남은 상태**입니다.
6. PR `#28` after PR `#37` — trusted document deps 위의 hybrid file ontology.
7. PR `#59` / `#61` — DiskSage ingest and preview boundary.
8. PR `#64` product names after `#51`, then PR `#65` setuptools, then Dependabot.
9. PR `#82` `a797e30` — customer-next-action copy. `#81` 뒤, Dependabot 앞.
10. PR `#88` `8e281de` — Measurement Context Registry. `#81`/`#51`/`#58`/`#73` 뒤. 점수·응답·판정 소유 없음.
11. ~~PR `#90` — public Pages landing source~~ — **2026-09-02에 병합 없이 closed(정상 승계).** `docs/index.md`는 `#72` `10096ce`가 담고 있으므로 landing은 `#72` 순서를 따릅니다. `#72`는 현재 Draft이며, Ready·병합 시 landing이 main에 올라갑니다. Pages-source PR을 새로 만들지 마십시오.
12. PR `#89` `3b59d90` Draft — DatasetDistribution 식별자 의미화 (`distribution_id` / `distribution_format` / `distribution_endpoint`); 와이어 계약 `{id, format, endpoint}` 유지. `#81`/`#51`/`#58`/`#73`보다 앞세우지 말 것. checks가 초록이 될 때까지 Draft 유지. (head가 `0a06e20`에서 `3b59d90`으로 이동했습니다.)
13. PR `#92` `51fb384` Draft — evidence store의 영속 식별자 의미화. `#89`와 같은 명명 규약(두 단어 이상 snake_case) 작업이며, evidence 스키마를 건드리므로 `#73` 뒤에 둡니다. Draft 유지.
14. PR `#93` `1dcca7b` / PR `#100` `5bba1e6` — Actions 검증 워크플로 정리. **두 PR이 서로 겹칩니다(아래 CI 거버넌스 절 참조).** 겹침을 정리하기 전에는 어느 쪽도 병합하지 마십시오.
15. PR `#96` `baa536b` → `#97` `dff4668` / `#99` `c3f0162` (모두 Draft) — OpenMetadata 2.x read-only 정규화 경계와 admission receipt. `#97`과 `#99`는 둘 다 `#96`의 브랜치(`feat/openmetadata-2-read-adapter`)를 base로 하는 stacked PR입니다. `#96`이 먼저입니다. `#99`가 `#97`의 successor라는 점은 추측이 아니라 `#99`의 ADR에 명시돼 있습니다 — `대체 대상: PR #97의 유효 delta를 검증 후 승계`. 즉 승계 관계가 문서화된 정상 lane이므로, `#97`은 delta 승계가 확인된 뒤에 닫으십시오. consume-only 경계(외부 catalog는 read-only)를 넘지 마십시오.

PR `#51` security-lock 파일을 catalog/docs PR에 섞지 마십시오. 이 문서 PR(`#79`)도 보안 unlock stack 뒤에서 squash하십시오. `#80`은 `#51` security-lock과 별개이며 squash는 현재 SHA OpenCode APPROVE 뒤에만 합니다. (`#90`은 closed되어 이 순서에서 빠졌고, 그 landing delta는 `#72`가 잇습니다.)

## 열린 PR과 각 PR이 닫는 격차

Head SHA와 draft 여부는 2026-09-07 GitHub API 응답에서 그대로 옮겼습니다. 열린 PR은 35건입니다.

| PR | Head | 격차 | 포털 소유? | 상태 2026-09-07 |
| --- | --- | --- | --- | --- |
| #81 | `ce40bd8` **Draft** | cryptography 50.0.0 — CVE-2026-69247, repo-wide trivy-fs unlock. 추적 issue #101 | Yes (shared base) | **Draft로 내려감**(본문 `source+lock repair present`). head는 그대로. issue #101은 열려 있으므로 CVE는 미해결 상태입니다. 현재 `opencode-review` 실패. **주의: 같은 bump가 `#57`(50.0.0)과 `#73`(50.0.1)에도 있습니다** — 3자 중복이며 목표 버전이 두 갈래입니다(아래 `#57` 절). |
| #51 | `558dd2f` | Outbound URL allowlist + security lock (cryptography CVE 부분은 `#81`이 선행 흡수) | Yes (security lock) | HOLD. extra-push 금지. |
| #58 | `0ce6d1f` | Keyverse claim aliases fail-closed | Keyverse 소비, adapter는 여기 | HOLD. strix fail. extra-push 금지. |
| #35 | `9c12f5d` | SQL comma-join allowlist bypass | Yes | HOLD. extra-push 금지. |
| #32 | `76fcfb6` | SELECT..INTO / volatile SQL bypass | Yes | #73 전제. #35/#51 뒤. |
| #73 | `1681a7f` | Catalog plane above the document KG (#13). ADR 0002 / stacked #83 already on this branch | Yes | HOLD. trivy-fs + strix fail. 현재 head에 `opencode-agent` `CHANGES_REQUESTED`. `#84` extra-push 금지. |
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
| Dependabot #27 #29 #62 #63 #67 #68 #69 #70 #71 | `8aad3b4` `3205628` `8d1c6c0` `3de2562` `cc1e623` `a0116a0` `b874efd` `4342b06` `e53e921` | Dependency currency | Yes after unlock | `#81` 이전 land 금지. |
| **#57** | `fb48fc9` | **Dependabot 아님 — 아래 "#57" 절 참조.** 제목·본문은 codeql-action bump지만 실제로는 outbound HTTPS 보안 경계 + CI gate + cryptography bump | Yes (security + CI) | Dependabot 묶음에서 분리했습니다. 일반 dependency로 취급하지 마십시오. |

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
| `CHANGELOG.md`가 main에 없음 | 커밋 100건·버전 `0.3.0`인데 main에 변경 이력 문서가 없습니다. **다만 `#88`이 Keep a Changelog 형식(`[Unreleased]` 절 포함)으로 추가하고 있으므로 PR 없는 격차가 아니라 `#88` 대기입니다.** | Portal docs — land `#88` |
| 태그·릴리즈가 0건 | 버전 문자열만 있고 대응하는 불변 아티팩트가 없어, 어떤 커밋이 `0.3.0`인지 지목할 수 없습니다 | Portal release — CVE 해소 뒤 |
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

### 성급한 Accepted (같은 lane의 별개 findings)

`main`에 `docs/adr/`가 없는데 `#73`의 ADR 두 건은 이미 `Accepted`를 주장합니다. 나머지 PR은 병합 전 상태를 올바르게 씁니다.

| PR | ADR | 선언된 상태 | 판정 |
| --- | --- | --- | --- |
| #73 | `0001-ontology-catalog-plane.md` | `**Status:** Accepted` (2026-08-18) | **성급함** — PR은 아직 open이고 trivy-fs·strix가 실패 중입니다 |
| #73 | `0002-corporate-master-resolution-owner.md` | `**Status:** Accepted target contract` | **성급함** — 같은 이유 |
| #72 | `0001`~`0004` | `Status: Draft` | 적절 |
| #88 | `0001-measurement-context-registry.md` | `Status: **Proposed**` | 적절 |
| #96 | `0001-openmetadata-anti-corruption-boundary.md` | `**Status:** Proposed` | 적절 |
| #97 / #99 | `0002-openmetadata-admission-preview-receipts.md` | `**상태:** Proposed` | 적절 |

병합되지 않은 PR 안에서만 존재하는 결정이 `Accepted`를 주장하면, 보호 브랜치에 올라간 결정과 제안 단계 결정을 문서만 보고 구분할 수 없습니다. 조직 규약대로 queued·pending·미병합 상태는 수용 근거가 아닙니다. `#73`이 실제로 main에 오르기 전까지는 `Proposed`로 낮추고, 병합과 함께 `Accepted`로 올리십시오. ADR 본문·결정 내용은 바꾸지 마십시오 — 상태 한 줄만 고치는 일입니다.

참고로 `#73`의 ADR은 상호 참조를 `ContextualWisdomLab/semantic-data-portal#13`, `ContextualWisdomLab/naruon#974`처럼 규약대로 쓰고 있습니다. 저장소 밖 참조 형식은 이미 이 저장소에서 지켜지고 있으므로, 위 lineage 행의 맨 `#74`가 예외였습니다.

## `#57`은 Dependabot bump가 아닙니다 (repair finding, 2026-09-07)

`#57`의 제목과 본문은 `github/codeql-action/upload-sarif` 4.36.3 → 4.37.6 bump이고, 본문은 Dependabot 기본 생성 텍스트 그대로입니다. 그런데 실제 내용은 커밋 18개·파일 18개이며 bump와 무관한 변경이 대부분입니다.

| 실제로 들어 있는 것 | 파일 |
| --- | --- |
| outbound HTTPS 보안 경계 (신규 모듈) | `src/sdp/network_security.py` (+128, 신규) |
| OIDC JWKS 목적지 검증 | `src/sdp/authz.py` |
| observability sink 목적지 검증 | `src/sdp/observability.py` |
| **cryptography 49.0.0 → 50.0.0** | `requirements.txt`, `requirements-dev.txt`, `requirements-test.txt` |
| 차등 커버리지 gate (신규 도구) | `tools/check_diff_coverage.py` (+143, 신규), `tests/test_diff_coverage.py` |
| 워크플로 변경 | `.github/workflows/fuzz.yml`, `tests.yml`, `scorecard-analysis.yml` |
| 보안 결정 기록 | `docs/doctoring/outbound-https-security.md` (+159, 신규) |

커밋 이력을 보면 의도된 병합입니다 — `Merge main into fix/security-gates-checkout-7-0-1`, `Merge security gate fix into CodeQL action update`. 보안 게이트 브랜치를 Dependabot 브랜치 위로 합친 것인데, **제목과 본문이 갱신되지 않았습니다.**

### 이것이 만드는 세 가지 문제

1. **분류 오류.** 이 문서도 직전 판까지 `#57`을 Dependabot 묶음에 넣고 "dependency currency, `#81` 이전 land 금지"로 적고 있었습니다. steward가 본문만 읽으면 routine bump로 오판합니다. 위 표에서 분리했습니다.
2. **`#81`의 single-writer 위반 — 2026-09-09 기준 3자, 그리고 목표 버전이 서로 다릅니다.** `#57`은 `requirements.txt`에서 `cryptography==49.0.0` → `50.0.0`을 그대로 바꿉니다. `#81`이 존재하는 이유가 정확히 그 변경입니다. 여기에 `#73`이 2026-09-09에 head를 `311668e`에서 `1681a7f`로 올리면서 같은 줄을 **`50.0.1`로** 바꿨습니다.

   | PR | cryptography 목표 | 상태 |
   | --- | --- | --- |
   | #81 `ce40bd8` | `50.0.0` | Draft |
   | #57 `fb48fc9` | `50.0.0` | 제목 불일치, check 통과 |
   | #73 `1681a7f` | **`50.0.1`** | non-draft, check 4건 실패 |

   즉 CVE-2026-69247 수정이 세 PR에 복제돼 있고 **목표 버전이 두 갈래**입니다. 먼저 병합되는 쪽이 나머지 둘에 `requirements.txt` 충돌을 남기며, `50.0.0`이 먼저 오르면 `#73`은 곧바로 다시 bump하는 PR이 됩니다. 이 문서가 `#81` 행에 "bump를 다른 PR로 복제하지 말 것"이라고 적어 둔 상태에서 이미 복제가 셋입니다. **어느 버전을 쓸지부터 정한 뒤 writer를 하나로 좁히십시오** — 버전 선택은 owner 결정이며, 여기서는 세 갈래가 존재한다는 사실만 기록합니다.
3. **동시성 파일 충돌은 2자가 아니라 3자입니다.** `#57`도 `fuzz.yml`의 concurrency group을 바꿉니다. 그런데 세 번째 변형이며 조직 계약을 지키지 않습니다.

| PR | `fuzz.yml` group 식 | `{workflow}-{repository}-{PR번호}` 계약 |
| --- | --- | --- |
| #93 | `${{ github.workflow }}-${{ github.repository }}-${{ github.event.pull_request.number \|\| github.run_id }}` | 준수 |
| #100 | `${{ github.workflow }}-${{ github.repository }}-${{ github.event_name == 'pull_request' && github.event.pull_request.number \|\| github.run_id }}` | 준수 |
| **#57** | `fuzz-${{ github.event.pull_request.number \|\| github.ref }}` | **미준수** — `fuzz-` 하드코딩, repository 성분 없음 |

### 조치

닫지 마십시오. 세 가지를 분리해서 결정해야 합니다.

- **cryptography bump**: single writer를 하나로 정하십시오. `#81`이 그 목적의 PR이므로 `#57`에서 빼는 편이 자연스럽지만, `#81`이 Draft로 내려간 상태이므로 반대로 `#57`을 writer로 삼는 선택도 가능합니다. 어느 쪽이든 **두 PR이 동시에 main에 오르면 안 됩니다.**
- **concurrency group**: `#57`의 식은 계약 미준수이므로 `#93`/`#100` 통합 결과를 따르게 하십시오. `fuzz.yml`을 세 PR이 각자 고치는 상태를 유지하지 마십시오.
- **제목·본문**: 실제 내용에 맞게 고치십시오. 지금 본문으로는 리뷰어가 보안 모듈과 CI gate 추가를 인지할 수 없습니다.

## CI 거버넌스: PR 동시성 그룹과 `#93`/`#100` 겹침

조직 계약상 PR Actions의 `concurrency.group`은 `{workflow명}-{repository}-{PR번호}`입니다. 간접 호출이라 PR 번호를 못 얻으면 그룹을 조립하지 말고 실패시키십시오. 취소는 같은 그룹의 구형 실행에만(`cancel-in-progress: true`) 적용하고, 다른 workflow·repository·PR은 서로 독립입니다. merge·release·deploy·migration은 취소 대상이 아니며 lock·idempotency·exact-head로 직렬화합니다.

`#93` `1dcca7b`와 `#100` `5bba1e6`은 이 계약을 각자 구현하면서 **같은 파일 세 개를 동시에 건드립니다.**

| 파일 | `#93` | `#100` |
| --- | --- | --- |
| `.github/workflows/fuzz.yml` | 수정 | 수정 |
| `.github/workflows/tests.yml` | 수정 | 수정 |
| `tests/test_workflow_concurrency_contract.py` | **신규 추가** | **신규 추가** |
| `.github/workflows/scorecard-analysis.yml` | 수정 | — |

여기에 더해 `#57`도 `fuzz.yml`의 concurrency group을 세 번째 변형으로 바꿉니다(위 `#57` 절). 즉 `fuzz.yml`을 세 PR이 각자 고치고 있습니다.

같은 경로를 양쪽이 `added`로 올리므로 먼저 병합된 쪽이 상대에게 add/add 충돌을 남깁니다. 그룹 식은 사실상 같습니다 — `#93`은 `github.event.pull_request.number || github.run_id`, `#100`은 `github.event_name == 'pull_request' && github.event.pull_request.number || github.run_id`로 event 종류를 명시적으로 검사합니다.

각자 상대에게 없는 delta가 있습니다.

- `#93`만: Scorecard를 중앙 immutable reusable workflow로 위임, ghost workflow 등록 11건 비활성, docs-only fuzz skip(`#94` 흡수).
- `#100`만: Draft·closed PR에서 runner job을 시작하지 않는 `if:` 가드. 이것도 조직 계약에 포함된 요구사항입니다.

**조치: 어느 쪽도 닫지 마십시오.** 단일 writer를 정하고 나머지 delta를 그 PR로 합치는 것이 규약입니다(폐기가 아니라 통합). `#93`이 상위 집합에 가까우므로 `#93`을 동시성 계약 파일의 writer로 두고 `#100`의 Draft/closed 가드를 `#93`으로 옮기는 편이 충돌 표면이 작습니다. 반대로 정하려면 `#93`의 Scorecard·ghost workflow·docs-only skip delta가 통째로 승계되어야 합니다. 어느 쪽이든 `tests/test_workflow_concurrency_contract.py`는 최종적으로 한 PR에서만 추가되어야 합니다.

## 무엇이 실제로 막고 있는가 (2026-09-07 측정)

열린 PR 16건을 표본으로 head SHA 기준 check run과 review를 전수 대조했습니다. 승인 부재는 예외가 없고, 그와 별개로 실패 중인 check가 다수 존재합니다.

| PR | check run 총계 | 리뷰 게이트 check | review 총계 | **현재 head의 APPROVED** | mergeable_state |
| --- | --- | --- | --- | --- | --- |
| #51 | 60 | 7 | 28 | **0** | blocked |
| #82 | 32 | 3 | 3 | **0** | blocked |
| #88 | 4 | **0** | 7 | **0** | blocked |
| #80 | 32 | 3 | 14 | **0** | blocked |
| #73 | 32 | 3 | 28 | **0** | blocked |
| #58 | 32 | 3 | 8 | **0** | blocked |
| #35 | 32 | 3 | 14 | **0** | blocked |
| #32 | 32 | 3 | 9 | **0** | blocked |
| #64 | 32 | 3 | 2 | **0** | blocked |
| #65 | 32 | 3 | 2 | **0** | blocked |
| #93 | 37 | 4 | 4 | **0** | blocked |
| #100 | 37 | 4 | 3 | **0** | blocked |

표본을 16건으로 넓혀 실패 중인 check까지 전수 대조한 결과입니다.

| PR | check 총계 | 실패 중인 check | 현재 head APPROVED |
| --- | --- | --- | --- |
| #51 | 60 | — | 0 |
| #35 | 32 | — | 0 |
| #59 | 32 | — | 0 |
| #88 | 4 | — (필수 검사 자체가 안 붙음) | 0 |
| #82 | 32 | `trivy-fs` | 0 |
| #80 | 32 | `trivy-fs` | 0 |
| #32 | 32 | `trivy-fs` | 0 |
| #64 | 32 | `trivy-fs` | 0 |
| #65 | 32 | `trivy-fs` | 0 |
| #58 | 32 | `strix` | 0 |
| #73 | 32 | `strix`, `trivy-fs` | 0 |
| #37 | 32 | `dependency-review`, `osv-scan`, `trivy-fs` | 0 |
| #28 | 56 | `dependency-review`, `osv-scan`, `strix`, `trivy-fs` 외 | 0 |
| #61 | 55 | `Analyze (actions)`, `Analyze (python)` | 0 |
| #93 | 37 | `Scorecard`, `noema-review`, `opencode-review` 외 | 0 |
| #100 | 37 | `CodeQL compatibility analysis` 외 | 0 |

두 가지 서로 다른 원인이 겹쳐 있습니다.

1. **승인 부재는 예외 없이 전부에 해당합니다 — 16/16이 현재 head에 `APPROVED` 0건입니다.** `#51`은 리뷰가 28건 쌓였는데 27건이 `COMMENTED`, 1건이 `DISMISSED`이고 승인은 없습니다. 승인은 기다린다고 생기지 않으며, 어떤 agent도 승인하거나 branch protection을 우회할 수 없으므로 이 축은 사람 결정입니다.
2. **실패 중인 check는 16건 중 12건에 있습니다.** 최다는 `trivy-fs`(7건)이며, 이는 main의 `cryptography==49.0.0` 상속 그대로입니다. 즉 이 문서가 줄곧 말해 온 "`#81`이 올라가면 상속이 풀린다"는 예측이 실측으로 확인됩니다.

**승인만 있으면 바로 풀리는 PR은 `#51`, `#35`, `#59` 세 건입니다.** 실패 중인 check가 하나도 없고 오직 승인만 없습니다. 우선순위를 하나만 고른다면 이 세 건입니다 — 다른 어떤 수리도 필요 없고 판정만 남기면 됩니다.

나머지는 승인 전에 check 수리가 먼저입니다. 대부분은 cryptography single writer를 main에 올리는 것으로 `trivy-fs` 7건이 한 번에 정리됩니다.

### 정정(2026-09-09): 위 두 표의 "실패 중인 check 없음"은 그대로 읽으면 안 됩니다

위 권고 — **"승인만 있으면 바로 풀리는 PR은 `#51`, `#35`, `#59` 세 건"** — 은 철회합니다. 근거로 삼은 초록이 두 가지 이유로 증거가 되지 못합니다.

**첫째, `opencode-review` check에는 세대가 둘 있고 셋 다 옛 세대입니다.**

2026-08-18까지의 세대는 아무것도 검증하지 않는 `echo` 한 줄입니다. 잡 본문 전체가 이렇습니다.

```
Run echo "Review approval remains a separate current-head PR review requirement produced by the authenticated dispatch workflow."
```

`gh api`도, `/pulls/N/reviews` 조회도, `jq`도, `opencode-agent` 문자열도 로그에 없습니다. 실패할 수 있는 경로 자체가 없으므로 이 check의 초록은 판정이 아니라 상수입니다.

2026-08-30 세대는 다릅니다. reviews API를 실제로 조회해 head SHA와 `opencode-agent` 판정을 맞춰 보고, 없으면 fail-closed합니다.

```
##[error]No APPROVED or CHANGES_REQUESTED from opencode-agent on the current head.
This required check is not a review and must not succeed until the authenticated dispatch posts a current-head verdict.
```

세대 판별 결과입니다. 실행 시간 자체가 지표입니다 — 3~4초는 `echo`, 10초는 API 조회입니다.

| PR | job id | 결론 | 실행 시각 | 소요 | 세대 |
| --- | --- | --- | --- | --- | --- |
| #59 | `95467498879` | success | 2026-08-17T18:46:42Z | 3초 | **no-op stub** |
| #51 | `95715500577` | success | 2026-08-18T12:49:36Z | 4초 | **no-op stub** |
| #35 | `95568388849` | success | 2026-08-18T01:45:56Z | 4초 | **no-op stub** |
| #81 | `99291035386` | **failure** | 2026-08-30T17:01:50Z | 10초 | fail-closed 게이트 |

`#51`은 stub 실행이 3건 있고 그중 가장 최근 것이 그 PR 전체에서 가장 새로운 check run입니다(2026-08-18T12:49:36Z). 즉 이후에 새 세대가 덮어쓴 적이 없습니다.

**둘째, 초록 자체가 3주 지난 것입니다.** `#51`의 최신 check run은 2026-08-18, `#59`는 2026-08-17입니다. 이 문서의 측정일(2026-09-07)보다 3주 앞섭니다. 그 사이에 취약점 DB도, 게이트 세대도 바뀌었습니다. 실측 근거는 `#79`에 있습니다 — 같은 main 계보인데 2026-09-01 스캔에서 `trivy-fs`가 이렇게 떨어졌습니다(job `99954799788`).

```
Trivy filesystem scan reported 1 finding(s):
  [HIGH (security-severity=8.0)] CVE-2026-69247 requirements.txt:125 - Package: cryptography
Remediate each finding at the shared base branch so open PRs inherit the fix.
```

`#35`·`#59`는 `requirements.txt`를 건드리지 않으므로 지금 다시 돌리면 같은 finding을 상속할 것으로 예상됩니다. 옛 초록은 "통과"가 아니라 "그때는 통과했다"입니다.

**따라서 우선순위 판단이 뒤집힙니다.** 이 문서는 `#81`을 가장 막힌 PR로, `#35`를 가장 풀기 쉬운 PR로 적어 왔습니다. 실제로는 반대입니다. `#81`은 리뷰 게이트가 **실제로 돌아서** 빠진 판정을 정확히 보고하는 유일한 PR이고, `#35`·`#51`·`#59`는 게이트가 **돈 적이 없는** PR입니다. 검증되지 않은 초록을 검증된 빨강보다 앞세우지 마십시오.

### 판정을 읽는 규칙 (2026-09-09)

이 문서가 과거에 승인을 잘못 기록한 경로가 셋 있었습니다. 같은 실수를 막기 위해 규칙으로 고정합니다.

1. **요청 코멘트는 판정이 아닙니다.** `@opencode-agent Please APPROVE ...`는 issue comment이며 리뷰가 아닙니다. `#81`의 comment 5469292683이 이 경우입니다.
2. **리뷰 본문 산문은 판정이 아닙니다.** `#58`의 head-matching 리뷰는 본문에 `- Result: APPROVE`가 적혀 있으나 API `state`는 `DISMISSED`입니다. 판정은 `state`로만 읽습니다.
3. **`commit_id`가 현재 head와 같아야 합니다.** 본문이 주장하는 SHA와 리뷰 자신의 `commit_id`가 다른 사례가 실재합니다(`#58`).
4. **초록 check에는 실행 시각과 잡 세대를 함께 확인합니다.** 3~4초 `opencode-review`는 no-op입니다.

확인 명령은 이것 하나입니다. 표시(라벨·본문·코멘트)가 아니라 이 응답이 근거입니다.

```
gh api repos/ContextualWisdomLab/semantic-data-portal/pulls/<번호>/reviews \
  --jq '.[] | select(.user.login|test("opencode-agent")) | {state, commit_id, submitted_at}'
```

2026-09-09 기준 `#51`·`#58`·`#35`·`#32`·`#73`·`#79`·`#102` 일곱 건 전수 대조 결과, **어떤 리뷰어의 `APPROVED`도 0건**입니다. `opencode-agent`가 남긴 상태는 `DISMISSED`와 `CHANGES_REQUESTED`뿐입니다. 그중 현재 head에 붙은 `CHANGES_REQUESTED`는 `#32` `76fcfb6`와 `#73` `1681a7f` 두 건이며, 이 둘은 "승인 대기"가 아니라 **요청된 수정이 남은 상태**입니다.

### `#81`은 Draft라서 판정을 받을 수 없고, 판정이 없어서 Draft를 벗어날 수 없습니다

`#81`만 유독 `opencode-agent` 판정이 0건인 이유를 중앙 워크플로 소스에서 확인했습니다. 교착입니다.

판정을 만들어 내는 dispatch를 보내는 주체는 PR Review Merge Scheduler입니다 — `ContextualWisdomLab/.github`의 `scripts/ci/pr_review_merge_scheduler.py:2205`가 `"event_type": "opencode-review"`로 `repository_dispatch`를 발행하고, 그것을 `opencode-review-dispatch.yml`이 받아 리뷰를 실행·게시합니다. 저장소 쪽 `opencode-review` check는 그 결과를 조회하는 검증 절반일 뿐입니다.

그런데 같은 스크립트의 PR 단위 판단 함수는 **첫 동작으로 Draft를 걸러냅니다.**

```python
if pr.get("isDraft"):
    return Decision(number, "skip", "draft PR")
```

이 `return`은 `cancel_stale_pr_runs`보다, base_ref 분기보다, 그리고 dispatch에 닿는 모든 경로보다 앞섭니다. 즉 **Draft PR에는 리뷰 dispatch가 발행되지 않습니다.**

여기에 `#81` 본문의 Promotion acceptance 4번이 겹칩니다 — "a qualifying independent non-author approval is current". 정리하면 이렇습니다.

1. `#81`이 Draft다 → 2. 스케줄러가 skip한다 → 3. dispatch가 발행되지 않는다 → 4. `opencode-agent` 판정이 생기지 않는다 → 5. 승격 조건 4번이 충족되지 않는다 → 6. Draft로 남는다 → 1로 돌아갑니다.

관측된 비대칭이 이것으로 설명됩니다. `#73`은 Draft가 아니고 2026-09-09에 판정(`CHANGES_REQUESTED`)을 받았습니다. `#81`은 Draft이고 판정이 0건입니다. 리뷰 기구 자체는 이 저장소에서 살아 있습니다 — `#81`에만 닿지 않을 뿐입니다.

**mention 경로는 현재 대안이 못 됩니다.** `agent-mention-opencode-dispatch.yml`에는 Draft 필터가 없으므로 원리상 `@opencode-agent` 멘션으로 우회할 수 있어야 합니다. 그러나 `#81`에는 2026-08-25·08-26·08-30·08-31 네 번의 승인 요청 멘션이 있고 어느 것도 판정을 만들지 못했습니다. 그 경로 자체가 수리 중입니다 — `ContextualWisdomLab/.github#2058`(review-agent mention을 native로 라우팅)이 2026-09-09 현재 열려 있습니다.

**조치는 사람 몫이며 한 가지입니다.** `#81`을 Ready for review로 되돌리면 `opencode-review.yml`의 `ready_for_review` 트리거가 걸리고 스케줄러가 더 이상 skip하지 않으므로, 판정을 받을 수 있는 상태가 됩니다. 그 판정이 `APPROVED`일지 `CHANGES_REQUESTED`일지는 별개이며, 어느 쪽이든 지금처럼 무한정 대기하는 것보다 낫습니다.

owner lane은 `ContextualWisdomLab/.github` issue `#2045`(Ready 전환 뒤 exact-head 리뷰 job 재생성)입니다. 다만 그 issue의 canary 두 건(html4tree#600, wardnet#130)은 Draft→Ready를 **건넌 뒤** 옛 GREEN이 남는 반대 방향입니다. `#81`은 전환 자체를 못 건너는 쪽이라 세 번째 canary로 [코멘트](https://github.com/ContextualWisdomLab/.github/issues/2045#issuecomment-5601146614)에 기록했습니다. issue의 수리 계약 2번이 "Ready 전환 **또는** 중앙 reconciliation"으로 쓰여 있는데, 전환이 막힌 PR에는 앞쪽 절반이 도움이 되지 않으므로 뒤쪽 절반이 Draft 상태의 PR에도 닿거나, 판정이 Draft 탈출의 선행조건이 아님을 계약에 명시해야 한다는 점을 덧붙였습니다.

**agent가 이 전환을 대신 하지 않습니다.** Draft 전환은 `#81` 저자가 본문에 승격 조건을 명시하며 의도적으로 내린 결정이고, 그 결정을 제3자가 뒤집는 것은 이 문서의 다른 모든 절이 금지하는 종류의 행위입니다. 여기서는 교착의 존재와 해제 지점만 기록합니다.

부수적으로 같은 함수의 non-draft 경로에 이런 주석이 있습니다 — "Stacked/cascade PR (base is another feature branch). Org required workflows are only injected for default-branch-target PRs, so these PRs never receive an OpenCode review on their own — dispatch one here." 이 문서를 담은 `#102`도 base가 `#79`의 브랜치인 stacked PR이므로 같은 경로에 해당합니다. `#102`에 check가 2건(fuzz)만 붙어 있는 것은 이 구조 때문이며 결함이 아닙니다.

### `opencode-review` dispatch의 owner는 이 저장소가 아닙니다

`#81`에서 실패한 것은 검증 쪽 절반입니다. 판정을 실제로 생성해 게시하는 dispatch 절반은 `ContextualWisdomLab/.github`의 중앙 워크플로에 있고, 그쪽에 수리 PR이 이미 떠 있습니다 — `ContextualWisdomLab/.github#2040`(exchanged target app token으로 required job 깨우기), `#2051`(실패 job wake 1회 조정), `#2056`(exact dispatch wakeup 직렬화).

포털에서 우회하지 마십시오. 게이트를 약화하거나, stub 세대로 되돌리거나, 판정 없이 승인 라벨을 붙이는 조치는 모두 금지입니다.

### 현재 head `CHANGES_REQUESTED`에는 코드 지적이 없습니다

`#32`와 `#73`이 받은 현재-head `CHANGES_REQUESTED`를 "요청된 수정"으로 읽으면 안 됩니다. 본문을 열어 보면 둘 다 같은 한 문장입니다.

```
OpenCode could not approve from deterministic current-head evidence
because GitHub Checks have failed.
```

지적 항목은 `1. HIGH Current-head GitHub Checks - Fix failed required checks before approval` 하나뿐이고, 조치는 "실패한 check를 고치고 재실행하라"입니다. 코드 findings는 없습니다. 실제로 미해결 리뷰 스레드도 0건입니다 — `#73`은 스레드 31건 전부 resolved, `#32`는 3건 전부 resolved입니다. 즉 **구현할 리뷰 지적이 남아 있지 않습니다.**

`#32`의 두 `CHANGES_REQUESTED`(4940679912 / 4941269691)는 같은 head·같은 본문·같은 실패 check로 87분 간격을 두고 중복 게시된 것입니다. 한 건을 고치면 둘 다 풀립니다.

### 실패 check의 원인을 끝까지 따라가면 포털이 소유한 것은 하나뿐입니다

각 실패 check의 잡 로그를 직접 읽은 결과입니다.

| 실패 check | 나타나는 PR | 로그가 말하는 원인 | 수리 owner |
| --- | --- | --- | --- |
| `opencode-review` | `#81` | `No APPROVED or CHANGES_REQUESTED from opencode-agent on the current head` — 검증 절반이 dispatch 절반의 판정을 기다리다 fail-closed | `.github` `#2040`/`#2051`/`#2056` |
| `CodeQL compatibility analysis` (actions·python) | `#73` | `VERDICT_STATE: pending` → `CodeQL scan dispatched. The dispatch workflow will rerun this exact failed CodeQL job after publishing its terminal verdict.` dispatch는 성공했는데 되돌아와 job을 재실행하는 wake가 오지 않습니다 | `.github` `#2040`/`#2051`/`#2056` |
| `noema-review` | `#73`, `#79` | 게이트웨이 라우팅 결함 — 아래 참조 | `contextual-orchestrator` issue `#1106` (PR `#971`은 넓은 라우팅 lane) |
| `trivy-fs` | `#32`, `#79` 외 | `[HIGH] CVE-2026-69247 requirements.txt:125 - Package: cryptography` | **이 저장소** (`#81`) |

`noema-review`(job `102406024468`, 2026-09-09)는 특히 분명한 상류 결함입니다. 같은 잡의 preflight가 후보 24건 중 16건을 probe해 `ready` 4건과 `deferred` 4건을 이미 구분해 두었습니다.

```
"ready_count": 4, "deferred_count": 4, "rejected_count": 8, "target_ready": 8
...
{ "agent_id": "openrouter_dots_studio_dots_3_note_preview_free",
  "http_status": 429, "status": "deferred" }
```

그런데 실제 호출은 `ready` 4건을 두고 방금 `deferred`로 표시한 그 429 라우트를 골랐고, 366.4초를 쓴 뒤 같은 429로 죽었습니다.

```
##[error]Noema gateway transport failed: HTTPError: HTTP Error 429: Too Many Requests;
caller attempts=1, duration=366.4s, phase=response_error,
served_model=dots-studio/dots-3-note-preview:free
##[warning]... caller attempts=1 (gateway owns repair/failover).
```

경고문이 스스로 밝히듯 failover 책임은 게이트웨이에 있습니다. 호출자(포털·noema)가 재시도로 덮을 문제가 아닙니다.

owner lane은 `ContextualWisdomLab/contextual-orchestrator` issue `#1106`(free-pool admission을 게이트웨이가 소유하고 leaf heuristic preflight를 제거)입니다. 그 issue는 2026-09-08자 실패 3건을 이미 기록하고 있고, 위 2026-09-09 건을 네 번째 사례로 [코멘트](https://github.com/ContextualWisdomLab/contextual-orchestrator/issues/1106#issuecomment-5601096976)에 붙였습니다. 이번 건이 더한 사실은 **preflight가 `deferred`로 표시한 라우트를 같은 실행이 그대로 서빙했다**는 점입니다 — issue에 적힌 `REVIEW_PREFLIGHT_DEFERRED_PRIORITY_PENALTY = 1000`이 배제가 아니라 순위 감점이라서 deferred 라우트가 계속 후보로 남습니다. PR `#971`은 같은 저장소의 넓은 라우팅/선택 lane이며, 이 결함의 추적 대상은 `#1106`입니다. 포털에서는 재시도·우회를 넣지 않습니다.

**정리하면, 포털이 자기 저장소에서 고칠 수 있는 실패 check는 `trivy-fs` 하나이고 그 single writer는 `#81`입니다.** 나머지 세 종류는 전부 `.github`와 `contextual-orchestrator`의 제어면 결함입니다. 따라서 "포털에서 할 수 있는 독립 작업"으로 `#32`·`#73`의 리뷰 지적을 해소한다는 계획은 성립하지 않습니다 — 해소할 지적이 없습니다. 큐 전체가 상류 수리에 걸려 있다는 사실을 그대로 기록해 두는 편이, 없는 포털 작업을 만들어 내는 것보다 정확합니다.

### 승인은 "오지 않는" 것이 아니라 2026-08-13에 멈췄습니다

병합된 PR의 리뷰 이력을 보면 승인 기구는 정상 작동한 적이 있습니다. `opencode-agent[bot]`이 2026-07-11부터 2026-08-13까지 승인을 냈고(병합된 PR 10건에 18건), 그 뒤로 **어떤 PR에도 `APPROVED`가 붙지 않았습니다.**

| 기간 | `opencode-agent`의 `APPROVED` |
| --- | --- |
| 2026-07-11 ~ 2026-08-13 | 18건 (병합 PR 10건) |
| 2026-08-13 이후 현재까지 | **0건** |

리뷰 자체가 끊긴 것은 아닙니다. 열린 PR 36건 중 20건에 `opencode-agent` 리뷰가 있고, 최신 판정은 대부분 `CHANGES_REQUESTED`(일부 `DISMISSED`)이며 2026-08-24까지 이어집니다. 즉 **리뷰어는 계속 판정하되 8-13 이후로는 승인을 내지 않는 상태**입니다. 이것이 대기로 풀리지 않는 이유입니다.

### 그래서 PR마다 필요한 조치가 다릅니다

`CHANGES_REQUESTED`가 현재 head에 붙어 있으면 승인이 아니라 **요청된 수정**이 먼저입니다. 반면 판정이 과거 head에 남은 stale 상태면 성격이 다릅니다.

| PR | 최신 `opencode` 판정 | 현재 head 기준 | 실패 check | 필요한 것 |
| --- | --- | --- | --- | --- |
| #51 | `DISMISSED` | stale (`9e06c45`) | 없음 | 승인만 |
| #59 | 리뷰 이력 없음 | — | 없음 | 승인만 |
| #35 | `CHANGES_REQUESTED` | stale (`4c12f25`) | 없음 | dismiss-stale 설정에 따라 다름 |
| #32 | `CHANGES_REQUESTED` | **현재 head** | `trivy-fs` | 수정 후 재판정 |
| #27 | `CHANGES_REQUESTED` | **현재 head** | `trivy-fs` | 수정 후 재판정 |
| #64 | `CHANGES_REQUESTED` | **현재 head** | `trivy-fs` | 수정 후 재판정 |
| #58 | `DISMISSED` | 현재 head | `strix` | check 수리 먼저 |
| #73 | `CHANGES_REQUESTED` | stale (`bfa409f`) | `strix`, `trivy-fs` | check 수리 먼저 |

`#35`의 stale `CHANGES_REQUESTED`가 병합을 막는지 여부는 branch protection의 stale review dismissal 설정에 달려 있는데, 이 설정은 현재 토큰 권한으로 읽을 수 없습니다(`Resource not accessible by integration`). 설정을 볼 수 있는 사람이 확인해야 합니다.

### `#88`의 원인은 규명되었습니다 — 워크플로가 실행 승인을 기다립니다

`#88`은 실패도 아니고 미부착도 아닙니다. 현재 head `8e281de`에서 워크플로 실행 4건이 **`action_required` 상태로 멈춰 있습니다.**

| 워크플로 | head `8e281de` (현재) | head `39efbb8` (직전) |
| --- | --- | --- |
| Tests | `action_required`, check run 0건 | `success` |
| fuzz | `action_required`, check run 0건 | `success` |
| SAST Semgrep | `action_required`, check run 0건 | `success` |
| Security Scan | `action_required`, check run 0건 | `failure` |

직전 head에서는 같은 워크플로가 정상 실행됐습니다. 즉 설정이나 path filter 문제가 아닙니다(`tests.yml`은 `pull_request: branches: [main]`만 걸고 path filter가 없습니다). `action_required`는 GitHub가 **maintainer의 "Approve and run" 클릭을 기다리는** 상태입니다.

따라서 `#88`에 필요한 조치는 리뷰 승인이 아니라 **워크플로 실행 승인**입니다. 검사가 돌아야 통과 여부를 알 수 있고, 그 다음에야 리뷰 승인 단계로 갑니다. 이 PR을 "검사 통과" 목록에 넣지 마십시오 — 검사는 아직 시작조차 하지 않았습니다.

## 이 저장소만 유독 멈춰 있습니다 (2026-09-09 측정)

병합 순서를 다시 쓰기 전에, 이 저장소의 대기가 조직 표준과 같은 것인지 확인했습니다. 같지 않았습니다.

**이 저장소의 protected main은 2026-08-17 이후 병합이 없습니다.** 마지막은 `#66`(fail closed on non-string OIDC subject claims, 2026-08-17T16:37:09Z)입니다. 그 뒤 `#83`이 2026-08-26에 병합됐지만 대상은 main이 아니라 `#73`의 브랜치였습니다. 즉 main 기준 23일, 열린 PR 35건, 저장소 역사 전체의 병합이 22건입니다.

같은 기간 조직 전체는 멈춰 있지 않습니다. 병합 누계 7,454건이고, 2026-09-09 당일에도 여러 저장소가 병합했습니다. **정지는 조직 현상이 아니라 이 저장소 현상입니다.**

그래서 조직이 실제로 무엇을 기다리고 병합하는지 표본으로 확인했습니다. 세션 범위 안의 6개 저장소에서 가장 최근 병합된 PR을 하나씩 골라 리뷰를 전수 조회했습니다.

| 저장소 | 최근 병합 PR | 병합 시각 | 리뷰 수 | `APPROVED` | `opencode-agent` 판정 |
| --- | --- | --- | --- | --- | --- |
| contextual-orchestrator | `#1081` | 2026-09-06T01:35:46Z | 0 | 없음 | 없음 |
| naruon | `#1616` | 2026-09-08T19:47:51Z | 2 (모두 `COMMENTED`) | 없음 | 없음 |
| fast-mlsirm | `#1760` | 2026-09-05T09:20:42Z | 0 | 없음 | 없음 |
| bandscope | `#1165` | 2026-09-04T09:48:51Z | 0 | 없음 | 없음 |
| wardnet | `#206` | 2026-09-08T13:55:20Z | 0 | 없음 | 없음 |
| `.github` | `#2028` | 2026-09-08T03:07:12Z | 6 | 없음 | `CHANGES_REQUESTED` @ `1d9c70b` |

**6건 중 0건이 병합된 head에 `opencode-agent` `APPROVED`를 달고 있었습니다.** 4건은 리뷰 자체가 0건이었습니다. 가장 분명한 사례는 거버넌스 owner인 `.github` `#2028`입니다 — 병합 head는 `af7c6e3`인데 유일한 `opencode-agent` 판정은 `1d9c70b`에 붙은 `CHANGES_REQUESTED`였습니다. 리뷰된 head와 병합된 head가 다릅니다.

**표본의 한계를 함께 적어 둡니다.** 각 PR의 base ref를 확인하지 않았으므로 일부(예: wardnet `#206` "adopt current #199 into #200")는 protected main이 아니라 다른 PR의 브랜치로 병합된 stack 수렴일 수 있고, 그 경우 보호 규칙이 적용되지 않습니다. 저장소당 1건 표본이며 6개 저장소입니다. 이 한계 안에서도 `.github` `#2028`은 protected main 사례로서 유효합니다.

### 이것이 뜻하는 바

이 문서의 병합 순서는 전 항목이 "현재 head `opencode-agent` APPROVE 수령"을 전제로 서 있습니다. 그런데 조직에서 실제로 병합되는 PR들은 그 receipt 없이 병합되고 있습니다. 즉 **이 저장소는 조직이 실무로 지키는 기준보다 엄격한 기준을 스스로에게 적용하며 23일째 대기 중**입니다.

두 가지 중 하나가 참입니다. 조직의 나머지가 게이트를 충분히 적용하지 않고 있거나, 이 저장소가 오지 않을 receipt를 기다리고 있거나. **어느 쪽이든 agent가 판단할 사안이 아닙니다.** 게이트를 낮추거나, 스스로 승인하거나, 보호 규칙을 우회하는 조치는 이 문서의 다른 모든 절과 마찬가지로 금지입니다.

사람 유지보수자에게 필요한 결정은 이것입니다.

1. `opencode-review` 현재-head 판정을 이 저장소의 실제 필수 게이트로 유지할 것인가. 유지한다면 dispatch 수리(`.github` `#2040`/`#2051`/`#2056`)가 선행 조건이며, 그때까지 큐가 멈춰 있는 것은 정상 동작입니다.
2. 유지하지 않는다면, 조직 공통 계약을 `.github`에서 명시적으로 고쳐야 합니다 — 저장소별로 다르게 적용되는 현재 상태가 아니라.
3. 그와 별개로 **`main`에 HIGH 등급 CVE-2026-69247이 23일째 남아 있다는 사실**은 위 결정과 무관하게 그 자체로 시급합니다. single writer는 `#81`입니다.

3번은 이 문서가 계속 1번 항목으로 적어 온 것과 같지만, 이제 대기 비용이 측정됩니다 — 취약한 main으로 23일, 그 뒤에 35건이 줄 서 있습니다.

## 릴리즈 준비 상태 (2026-09-07): 아직 아닙니다

| 항목 | 상태 |
| --- | --- |
| `pyproject.toml` version | `0.3.0` |
| git tag | 없음 (0건) |
| GitHub release | 없음 (0건) |
| `CHANGELOG.md` | main에는 없음. `#88`이 추가 중(`[Unreleased]` 포함) |
| main의 cryptography pin | **`cryptography==49.0.0`** — CVE-2026-69247 미수정 |

**지금 릴리즈하면 안 되는 이유는 CVE입니다.** main(`e48aa13`)의 `requirements.txt`는 여전히 `cryptography==49.0.0`을 hash pin으로 고정하고 있습니다. 수정은 `#81`(Draft)과 `#57`(제목 불일치) 두 곳에만 있고 어느 쪽도 병합되지 않았으며, 추적 issue #101은 열려 있습니다. 알려진 미수정 취약점을 담은 pin으로 태그를 끊는 것은 구매자에게 그대로 전달되는 문제입니다. **cryptography single writer를 정해 main에 올린 뒤에 릴리즈를 논의하십시오.**

부수적으로 드러난 격차 두 가지를 기록해 둡니다.

- **`CHANGELOG.md`가 main에 없습니다.** 커밋 100건, 버전 `0.3.0`을 선언하면서 main에 변경 이력 문서가 없습니다. 새로 만들지 마십시오 — `#88`이 Keep a Changelog 형식으로 이미 추가하고 있으며, 그쪽이 single writer입니다.
- **태그·릴리즈가 한 번도 없습니다.** 버전 문자열만 있고 그 버전에 대응하는 불변 아티팩트가 없습니다. 어떤 커밋이 `0.3.0`인지 지금은 아무도 지목할 수 없습니다.

두 항목 모두 CVE 해소 뒤 첫 릴리즈를 끊을 때 함께 만드는 것이 자연스럽습니다. CVE가 열려 있는 동안 태그부터 만들지 마십시오.

## 검증 기록 (2026-09-09)

2026-09-09 재검증입니다. `#81`이 왜 Draft에 머무는지 추적하다가 이 문서 자체의 증거 오류를 찾았습니다.

| 검사 | 방법 | 결과 |
| --- | --- | --- |
| `#81`의 승인 존재 여부 | `GET /pulls/81/reviews` 전수 | **오류 발견** — `opencode-agent[bot]` 리뷰 0건. 병합 순서 1번이 근거로 인용한 comment 5469292683은 승인이 아니라 승인 **요청** 코멘트였습니다. 정정 완료 |
| `#58`의 "이전 APPROVE" | 같은 API의 `state`/`commit_id` 대조 | **오류 발견** — head-matching 리뷰의 `state`는 `DISMISSED`인데 본문에 `- Result: APPROVE`가 적혀 있었습니다. 본문과 `commit_id`도 불일치. 정정 완료 |
| `opencode-review` 초록의 의미 | 잡 로그 4건 직접 확인(`95467498879`·`95715500577`·`95568388849`·`99291035386`) | **오류 발견** — `#51`·`#35`·`#59`의 초록은 `echo` 한 줄짜리 no-op 세대(3~4초). `#81`의 빨강만 실제 API 조회 세대(10초). "승인만 있으면 풀리는 세 건" 권고 철회 |
| 초록 check의 신선도 | 각 PR의 최신 `completed_at` | **오류 발견** — `#51` 2026-08-18, `#59` 2026-08-17로 측정일보다 3주 낡음. `#79`는 2026-09-01 재스캔에서 `trivy-fs`가 CVE-2026-69247로 실패(job `99954799788`) |
| `#73` head SHA | `GET /pulls/73` | **오류 발견** — 병합 순서 5번과 PR 표가 `311668e`로 낡아 있었습니다(203행은 이미 `1681a7f`로 갱신됨). 정정 완료. 새 head에 `CHANGES_REQUESTED` 있음 |
| 일곱 PR 승인 전수 | `#51`·`#58`·`#35`·`#32`·`#73`·`#79`·`#102` | **확인** — 어떤 리뷰어의 `APPROVED`도 0건. 이 축에 대한 기존 서술(16/16 승인 0건)은 유지됩니다 |
| `opencode-review` dispatch owner | `.github` 열린 PR 조회 | **확인** — 수리는 `ContextualWisdomLab/.github#2040`/`#2051`/`#2056`에서 진행 중. 포털에서 우회하지 않습니다 |
| `#32`·`#73`의 `CHANGES_REQUESTED` 내용 | 리뷰 본문 + 스레드 전수 | **확인** — 코드 findings 0건, 미해결 스레드 0건(`#73` 31건·`#32` 3건 모두 resolved). 전부 check-rollup 사유이며 `#32`의 두 건은 같은 head 중복 |
| `#73` 실패 check 3건의 원인 | 잡 로그 `102406319401`·`102406024468` 직접 확인 | **상류 결함** — CodeQL은 `VERDICT_STATE: pending`으로 dispatch wake 대기, noema는 게이트웨이가 자기 preflight에서 `deferred`(429)로 표시한 라우트를 골라 366.4초 뒤 429. 각각 `.github`, `contextual-orchestrator#971` 소관 |
| 포털이 자체 수리 가능한 실패 check | 위 원인 대조 | **1종뿐** — `trivy-fs`(CVE-2026-69247), single writer는 `#81` |
| `#81`만 판정 0건인 이유 | `.github`의 `scripts/ci/pr_review_merge_scheduler.py` 소스 확인 | **교착 발견** — 리뷰 dispatch를 보내는 것이 이 스케줄러(`:2205`)인데 PR 판단 함수가 첫 줄에서 Draft를 skip합니다(`:2383`). Draft → dispatch 없음 → 판정 없음 → 승격 조건 미충족 → Draft 유지. 해제 지점은 Ready 전환이며 사람 결정입니다 |

## 검증 기록 (2026-09-07)

열린 PR 36건 전체를 기계적으로 훑은 결과입니다. 문제가 없던 항목도 적어 둡니다 — 다음 사람이 같은 검사를 되풀이하지 않도록 하기 위함입니다.

| 검사 | 방법 | 결과 |
| --- | --- | --- |
| ADR 번호 중복 | 열린 PR 전체의 `docs/adr/*.md` 파일명 수집 후 네 자리 번호별 집계 | **발견** — `0001` 4건, `0002` 4건 충돌 (issue #103) |
| 성급한 `Accepted` | ADR 본문의 status 행 파싱 | **발견** — `#73` 2건 (issue #103 코멘트) |
| 단일 writer 위반 | 같은 파일을 `added`로 올리는 PR 교차 비교 | **발견** — `fuzz.yml`·`tests.yml`·동시성 계약 테스트를 `#57`/`#93`/`#100`이 각자 수정 |
| 중복 delta | `requirements.txt`의 동일 변경 비교 | **발견** — cryptography 49→50이 `#81`과 `#57`에 중복 |
| 누락 test | `src/`를 건드리는 PR이 `tests/`도 건드리는지 확인 | **없음** — 해당 18건 모두 테스트 동반 |
| supply-chain 하드닝 후퇴 | 추가된 `uses:` 행의 40자 SHA pin 여부, 추가된 `FROM` 행의 digest 여부 | **없음** — 미pin action·image를 새로 들여오는 PR 0건 |
| 소스 라인 인용 정확성 | 이 문서가 인용한 `src/…:line`을 `origin/main`에서 대조 | **정확** — `catalog.py:25/414/445`, `evidence.py:37-48`, `api.py:804-814` 모두 일치 |

마지막 항목의 확인 결과, `/browse/{dataset_id}/preview`가 `payload.get("user", "anonymous")`로 호출자가 준 문자열을 그대로 신뢰한다는 이 문서의 서술은 `e48aa13` 기준 사실입니다. 토큰 검증이 없으므로 호출자는 임의 신원을 주장할 수 있습니다.

## 운영 메모

- Database objects: 두 단어 이상 `snake_case`, 3NF. Catalog plane 테이블은 #73의 `migrations/0002_ontology_catalog_plane.sql`.
- 기본 CI store는 in-memory. DSN-backed store는 paid-pilot 경로이며 catalog 쓰기 영속화 자체는 #73의 범위입니다.
- `NVIDIA_NIM_API_KEY`는 contextual-orchestrator가 쓰는 **외부 connector 변수**입니다. 이 저장소의 워크플로·테스트·모듈은 현재 이 값을 참조하지 않으며, 이 문서가 유일한 언급 지점입니다. 이 저장소에서 이름을 바꾸지 마십시오. 포털 쪽 매핑은 orchestrator 계약의 `SDP_` prefix 변수를 따르고, 계약을 확인하기 전에는 새로 만들지 마십시오. `COPILOT_GITHUB_TOKEN`은 쓰지 않습니다. review-bot 키를 재조정하지 마십시오.
- Analyze (actions) 503 SARIF upload는 flake입니다. 재실행만을 위한 추가 커밋을 넣지 마십시오.
