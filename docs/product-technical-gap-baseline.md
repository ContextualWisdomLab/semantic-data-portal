# 제품·기술 격차 기준선 (product-technical gap baseline)

**제품 홈:** ContextualWisdomLab/semantic-data-portal (ontology 기반 semantic catalog).
**독자:** catalog steward / tenant operator.
**다음 행동 (2026-10-05 07:5xZ 갱신):** 이 저장소를 막고 있는 것은 **계정 수준 블로커 두 개**입니다. (가) 2026-10-02 18:44Z~22:30Z 사이에 걸린 **과금 잠금**이 `ubuntu-latest` job을 배정 전에 거절합니다. (나) 최소 2026-10-03 17:38Z부터 **Actions artifact 저장 용량 초과**가 self-hosted 레인의 artifact 업로드를 실패시킵니다 — 그 레인은 실행은 되지만 증거를 남기지 못합니다. 둘은 구간이 겹치지만 원인이 다르고, **둘 다 owner만 풀 수 있습니다.** 순서는 이렇습니다.

1. **`#104`를 main에 들어가는 첫 번째로 병합하십시오.** 현재-head 체크 34건이 이미 끝났고(success 25·skipped 9·실패 0) `behind 0`이라 업데이트가 필요 없습니다. 남은 조건은 **다른 신원의 승인 1건**뿐입니다(`#104`의 작성자는 `seonghobae`이고 이 세션의 리뷰 신원도 같으므로 승인 불가 — 이 차단이 모든 PR에 같게 걸리지는 않습니다. 아래 "그런데 이 차단은 PR마다 같지 않습니다" 절을 보십시오). **다른 것을 먼저 병합하면 `#104`가 `behind ≥ 1`이 되어 스케줄러가 브랜치를 업데이트할 수 있고, 움직인 head의 체크는 잠금 중 재생성되지 않습니다.** 그리고 **시한이 앞당겨졌습니다(2026-10-06 22:39Z 갱신).** PR head 브랜치를 직접 쓰는 예정 워크플로(`.github`의 `pr-auto-rebase.yml`, 약 3시간 주기)가 schedule 이전으로 **이미 복귀해 성공했습니다** — 반면 움직인 head의 hosted 체크를 다시 만드는 능력은 **아직 없습니다.** 지금 `#104`를 지키는 것은 과금 잠금이 아니라 `behind 0`이라는 사실 하나뿐이므로, 시한은 "잠금 해제 직후"가 아니라 **main이 전진하기 전**입니다. 그리고 `#104` 병합에는 과금 해제도 artifact 용량 확보도 필요하지 않습니다 — **승인 한 건이면 됩니다.** 근거는 아래 "정정 — `#104`를 지켜 주던 잠금이 끝났습니다" 절에 있습니다.
2. **과금 잠금을 해제하고, 함께 Actions artifact 저장 용량도 확보하십시오 — 블로커는 하나가 아니라 둘입니다.** 과금 잠금 전까지 이 저장소의 hosted CI 증거 생산은 0입니다(PR 게이트·주간 Scorecard·야간 fuzz 전부 거절). 그리고 **self-hosted 레인은 실행은 되지만 artifact 업로드에서 실패합니다** — 최소 10-03 17:38Z부터 `Artifact storage quota has been hit`이 연속 관측됩니다. 저장 용량 회복은 즉시가 아니라 6~12시간 뒤에 반영됩니다. 자세한 근거는 아래 "정정 — self-hosted 레인은 \"정상\"이 아닙니다" 절에 있습니다. `cwlab-ci-isolated` 격리 러너 등록은 별개의 대안이며, 살아 있는 특권 풀에 그 라벨을 붙이는 우회는 금지되어 있습니다.
3. **해제 후 조합 G(`#82`·`#107`·`#110`)를 단일 writer로 병합하십시오** — cryptography 50.0.2 / pyjwt 2.15.0으로 main의 미수정 두 항목을 한 번에 닫습니다. `#82`는 실패가 `noema-review` 하나(HTTP 400, vision 모델 배정)이고 `#107`은 product CI가 로컬·CI 양쪽에서 깨끗합니다. **단, 과금 잠금 해제만으로 `noema-review`가 녹색이 된다고 가정하지 마십시오** — artifact 저장 용량이 두 번째 벽이고, 해제 후 가장 먼저 할 일은 `#82`의 `noema-review` 재실행으로 실패 원인이 HTTP 400인지 artifact quota인지 가르는 것입니다.
4. **`#109`는 병합 대상이 아니라 수리 또는 승계 대상입니다** — `trivy-fs`가 실패 중이고 자기 lock 불일치와 상관합니다.
5. **`sso_oidc_adapter`는 2026-10-05에 닫혔습니다** — group-to-role 매핑을 tenant scoped로 만들고 group별 binding을 audit event로 기록해 control을 `implemented`로 올렸습니다(`planned_controls` 1 → 0, manifest `status` `pilot_ready`). 근거와 한계는 아래 "`sso_oidc_adapter`를 닫았습니다" 절에 있습니다. **열린 제품 갭 중 코드 갭은 이제 0건이고**, 남은 하나(`central_workflow_due_diligence`)는 의도적 external이며 그 release criteria가 바로 과금 잠금이 막고 있는 두 조건입니다.

이전 판의 lead 권고였던 "`#81`을 Ready for review로 되돌리는 것"은 **여전히 유효한 개별 조치**이지만 더 이상 1번이 아닙니다 — 근거는 아래 "`#81`은 Draft라서 판정을 받을 수 없고…" 절에 그대로 있습니다. 이 저장소에 local IdP나 policy registry를 만들지 마십시오.
**기준일:** 2026-10-03 (main `e48aa13`, 2026-08-09 `#34` 이후 변동 없음 — 54일). 2026-09-09에 리뷰 판정 증거를 전수 재검증했고, 그 결과 병합 순서 1번·3번의 승인 근거와 "승인만 있으면 풀리는 세 건" 권고를 정정했습니다 — 아래 "정정(2026-09-09)" 절을 먼저 읽으십시오.
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
5. PR `#73` `1681a7f` — catalog/ontology plane (#13). Frozen. **정정(2026-09-09): `trivy-fs`와 `strix`는 현재 head에서 모두 success입니다** — 이 줄의 "trivy-fs inherit + strix fail"은 옛 head 기준이었습니다(아래 전수 측정 절). `#84` corporate-master 구현은 이 PR 뒤; extra-push 금지. **`#75`는 `#73`이 main에 올 때까지 Draft.** **정정(2026-09-09): head가 `311668e` → `1681a7f`로 이동했고(같은 날 203행이 이미 기록), 이 문서의 5번·PR 표는 옛 SHA로 남아 있었습니다.** 새 head `1681a7f`에는 `opencode-agent[bot]`의 `CHANGES_REQUESTED`(review id 5152624078)가 붙어 있습니다. 즉 이 PR은 “승인 대기”가 아니라 **요청된 수정이 남은 상태**입니다.
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

## 병합 순서 그림 (위 목록과 같은 내용)

위 15개 항목을 그림으로 옮긴 것입니다. 문장이 규범이고 그림은 그 요약입니다 — 둘이 어긋나면 문장을 따르십시오.

```mermaid
flowchart TD
  subgraph unlock["1. 보안 unlock"]
    P81["#81 Draft<br/>cryptography 50.0.0<br/>Draft라서 판정 불가"]
    P51["#51 outbound URL harden"]
    P58["#58 Keyverse claim aliases"]
  end
  subgraph plane["2. catalog plane"]
    P35["#35 SQL allowlist"]
    P32["#32 SQL gate"]
    P73["#73 catalog plane<br/>cryptography 50.0.1<br/>trivy-fs / strix success"]
    P75["#75 Draft"]
    P92["#92 Draft"]
  end
  subgraph docs["3. 문서"]
    P79["#79 이 문서의 single writer"]
    P102["#102 이 문서의 delta"]
  end
  subgraph om["4. OpenMetadata, 모두 Draft"]
    P96["#96 read-only 정규화 경계"]
    P97["#97 admission receipt"]
    P99["#99 receipt repair"]
  end
  P88["#88 measurement context registry"]
  P93["#93 / #100 CI 겹침, 정리 전 병합 금지"]

  P81 --> P51 --> P58
  P51 --> P79 --> P102
  P32 --> P73
  P35 --> P73
  P73 --> P75
  P73 --> P92
  P73 --> P88
  P58 --> P88
  P96 --> P97
  P96 --> P99
  P97 -. "승계 미완 · test 3건 누락" .-> P99
```

`#81`이 root인 이유는 trivy-fs가 merge ref를 스캔하기 때문입니다. 다만 `#73`이 자기 head에서 같은 CVE를 `50.0.1`로 이미 해소했으므로, **root를 어느 PR이 맡을지는 아직 정해지지 않았습니다**(아래 해당 절).

### 실패 check의 소유자

```mermaid
flowchart LR
  T["trivy-fs"] --> TO["포털 소유<br/>#81 또는 #73이 해소"]
  OR["opencode-review"] --> GO[".github<br/>#2040 / #2051 / #2056"]
  CQ["CodeQL compatibility analysis"] --> GO
  NR["noema-review"] --> CO["contextual-orchestrator<br/>#1106 free pool admission"]
```

네 종류 중 포털이 자기 저장소에서 고칠 수 있는 것은 `trivy-fs` 하나입니다. 나머지 셋은 상류 제어면 수리를 기다리는 lane이며 포털에서 우회하지 않습니다.

### CVE writer 문제는 `#81`로 정리되었지만 큐는 여전히 안 풀립니다 (2026-09-21 확인)

이 문서는 CVE-2026-69247 수정이 `#81`(50.0.0)·`#57`(50.0.0)·`#73`(50.0.1) 셋에 복제되어 있고 **목표 버전이 두 갈래**라고 적으면서, writer를 하나로 좁히는 것은 owner 결정이라고 남겨 두었습니다(issue #101). **그 결정이 내려졌습니다.**

`#79`의 브랜치가 `21bcc86` → `2181681`로 이동했고, 새로 들어온 여섯 커밋에 `fce7045 fix(deps): bump cryptography 49.0.0 -> 50.0.0 for CVE-2026-69247`과 **`ce40bd8`**(= `#81`의 exact head)이 포함되어 있습니다. 병합 커밋의 제목은 그대로 `merge: inherit canonical cryptography security owner`입니다. `#81`의 본문도 스스로를 "the existing implementation owner … rather than creating another duplicate implementation branch"라고 적고 있습니다. 즉 **canonical writer는 `#81`, 버전은 50.0.0**이며, `#79`는 복제하지 않고 상속하는 쪽을 택했습니다. 추론이 아니라 owner가 커밋 메시지와 PR 본문에 쓴 표현입니다.

**그럼에도 큐는 풀리지 않았습니다.** `main`은 여전히 `e48aa13`이고, 수정은 두 브랜치 위에만 있습니다. 게다가 **둘 다 Draft입니다** — `#81`은 2026-09-07부터, `#79`는 2026-09-19 20:10Z부터. 이 문서가 앞서 적은 대로 스케줄러는 Draft PR을 skip하므로 리뷰 dispatch가 발행되지 않고, 따라서 **CVE가 고쳐진 채로 어느 쪽도 merge 경로에 올라 있지 않습니다.** "수정이 존재한다"와 "수정이 main에 있다"를 섞지 마십시오.

함께 들어온 `tests/test_dependency_locks.py`는 세 lock 파일의 정렬된 hash 목록이 어긋나거나 잘리는 것을 막는 재현성 계약입니다. `#81` 본문은 이 순서가 **의도적으로 비사전식(non-lexical)**이라고 못박고 있으니, 사전순 정렬을 가정하는 검증으로 바꾸지 마십시오.

**2026-09-19 저녁에 다섯 건이 한꺼번에 Draft로 내려갔습니다** — `#64`(19:03Z), `#51`(19:13Z), `#79`(20:10Z), `#93`·`#28`(21:05Z). 현재 열린 PR은 38건, 그중 Draft가 13건입니다. 이 전환이 정리 작업인지 다른 의도인지는 여기서 판별하지 않고, **Draft 비율이 3분의 1을 넘었다는 사실만 기록합니다.**

(이 문서를 담은 `#102`는 base가 움직이면서 여섯 커밋 뒤처져 있었고, 위 커밋들을 merge해 따라붙였습니다. 들어온 변경은 requirements 세 파일과 새 테스트뿐이라 이 문서와 충돌하지 않습니다.)

### CVE가 큐 전체를 막는 것은 아닙니다 — docs-only PR은 게이트를 통과합니다 (2026-09-19 측정)

이 문서는 여러 곳에서 "상속된 CVE-2026-69247이 큐를 막고 있다"고 적었습니다. **그 서술은 너무 넓습니다.** `#104`(`docs/readme-public-package-boundary`, README 한 파일만 변경)의 현재 head `1badc79`에는 check run이 **34건** 붙어 있고, 결과는 전부 `success` 아니면 `skipped`입니다. **실패가 하나도 없습니다.**

핵심은 `trivy-fs`가 **`skipped`**라는 점입니다 — 실패가 아니라 아예 실행되지 않았습니다. 같은 Security Scan 실행(`35289642492`)에서 `osv-scan`·`scorecard`·`dependency-review`도 함께 skip되었고, 앞선 `Detect changed scope` job은 success입니다. 즉 이 게이트들은 **변경 범위에 따라 조건부로 실행**되며, 문서만 바뀐 PR에서는 돌지 않습니다.

그래서 정확한 서술은 이렇습니다. `trivy-fs`는 저장소 전체를 스캔하므로 **실행되기만 하면** 상속된 CVE를 집어 실패합니다(`#80`·`#82`·`#32`·`#64`·`#65`의 census가 그 결과입니다). 하지만 **실행 여부 자체가 변경 범위에 달려 있고, docs-only 변경은 그 조건을 만족하지 않습니다.** 따라서 CVE는 소스·의존성을 건드리는 PR을 막지, 문서 PR을 막지 않습니다.

실무적으로 두 가지가 따라옵니다.

- **문서 작업에는 merge 경로가 있습니다.** CVE 해소를 기다리지 않아도 됩니다. `#104`가 그 첫 사례입니다.
- **`#104`가 여전히 `blocked`인 이유는 checks가 아니라 승인입니다.** 리뷰를 전수 확인하면 `coderabbitai[bot]`의 `COMMENTED` 한 건뿐이고(actionable 2건), `APPROVED`는 없습니다. `opencode-review`는 **check로는 success**지만 승인 리뷰를 남기지 않았습니다 — 이 문서가 다른 곳에 적은 "2026-08-13 이후 어떤 head에도 APPROVED가 없다"와 일치합니다. **check success를 승인으로 읽지 마십시오.**

`#102`와 대조하면 범위 조건이 더 분명합니다. `#102`는 `main`이 아니라 `#79`의 브랜치를 base로 하므로 check가 **2건**(fuzz)뿐이고, `#104`는 `main`을 base로 하므로 **34건**을 받습니다. 위 "stacked PR은 fuzz 말고 아무 게이트도 돌지 않습니다" 절의 측정과 같은 결론입니다.

## 열린 PR과 각 PR이 닫는 격차

Head SHA와 draft 여부는 2026-09-07 GitHub API 응답에서 그대로 옮겼습니다. 열린 PR은 35건입니다.

| PR | Head | 격차 | 포털 소유? | 상태 2026-09-07 |
| --- | --- | --- | --- | --- |
| #81 | `ce40bd8` **Draft** | cryptography 50.0.0 — CVE-2026-69247, repo-wide trivy-fs unlock. 추적 issue #101 | Yes (shared base) | **Draft로 내려감**(본문 `source+lock repair present`). head는 그대로. issue #101은 열려 있으므로 CVE는 미해결 상태입니다. 현재 `opencode-review` 실패. **주의: 같은 bump가 `#57`(50.0.0)과 `#73`(50.0.1)에도 있습니다** — 3자 중복이며 목표 버전이 두 갈래입니다(아래 `#57` 절). |
| #51 | `558dd2f` | Outbound URL allowlist + security lock (cryptography CVE 부분은 `#81`이 선행 흡수) | Yes (security lock) | HOLD. extra-push 금지. |
| #58 | `0ce6d1f` | Keyverse claim aliases fail-closed | Keyverse 소비, adapter는 여기 | HOLD. strix fail. extra-push 금지. |
| #35 | `9c12f5d` | SQL comma-join allowlist bypass | Yes | HOLD. extra-push 금지. |
| #32 | `76fcfb6` | SELECT..INTO / volatile SQL bypass | Yes | #73 전제. #35/#51 뒤. |
| #73 | `1681a7f` | Catalog plane above the document KG (#13). ADR 0002 / stacked #83 already on this branch | Yes | HOLD. **`trivy-fs`·`strix`는 현재 head에서 success**(2026-09-09 측정); 남은 실패 4건은 전부 중앙 제어면. 현재 head에 `opencode-agent` `CHANGES_REQUESTED`. `#84` extra-push 금지. |
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

## 자칭 신원은 `preview` 한 곳이 아니라 네 경로입니다 (2026-09-09 확인)

이 문서는 caller-supplied `user` 격차를 `/browse/{dataset_id}/preview` 한 곳으로만 적어 두었습니다(위 경계 절과 격차 표). `main` `e48aa13`에서 같은 패턴을 쓰는 경로를 전수 확인한 결과 **네 개**입니다.

| 경로 | 신원이 오는 곳 | 기본값 |
| --- | --- | --- |
| `GET /browse/{dataset_id}/schema` | **query string** (`user=`) | `anonymous` (조용히) |
| `POST /browse/{dataset_id}/preview` | body | 없음 — 누락 시 400 |
| `POST /browse/query` | body (`QueryExecutionRequest.user`) | `anonymous` |
| `POST /api/v1/browse/query` | 위 함수로 위임 | `anonymous` |

`src/sdp/api.py`에는 `Header`도 `Authorization` 참조도 없습니다. `authz.verify_oidc_jwks_token`과 `resolve_oidc_actor_context`는 실재하지만 호출되는 곳은 OIDC 진단·preview 엔드포인트 네 줄(`:228`, `:237`, `:256`, `:273`)뿐이고, 데이터 경로에는 결선돼 있지 않습니다.

세 가지가 이 표에서 새로 드러납니다.

1. **`schema`가 `preview`보다 노출이 큽니다.** `preview`는 `user` 누락을 400으로 막지만 `schema`는 조용히 `anonymous`로 떨어집니다. 게다가 GET이라 자칭 신원이 URL에 실려 로그·리퍼러·캐시에 남습니다.
2. **`/api/v1/browse/query`도 같은 격차를 가집니다.** 버전이 붙은 공개 표면이므로 외부 구매자가 실제로 통합하는 경로입니다.
3. **`preview`만 고치면 나머지 셋이 남습니다.** 이 문서를 근거로 하드닝하는 사람이 정확히 그렇게 하기 쉬운 상태였습니다.

`#80`과의 관계를 분명히 해 둡니다. `#80`은 인가된 steward에게 원문 값을 보여주는 변경입니다. 신원이 자칭인 동안에는 "인가된 steward"가 `"user": "steward_..."`라고 적는 누구나가 됩니다. **`#80`은 잘못된 PR이 아니라 선행 조건이 있는 PR입니다** — browse 경로에 검증된 토큰 기반 신원이 결선된 뒤에 안전합니다. 순서를 바꾸지 마십시오.

여기서 고치지 않습니다. browse 경로의 writer는 `#80`이고 신원 결선은 `#58`(Keyverse) 뒤의 교차 관심사입니다.

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
   | #73 `1681a7f` | **`50.0.1`** | non-draft. 이 pin으로 `trivy-fs`가 **초록**이 되었습니다. 남은 실패 4건은 전부 중앙 제어면 |

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

### 2026-09-14: 워크플로가 아예 실행되지 않고 있습니다

위 절은 stacked PR이 *어떤 게이트를 받는지*를 다룹니다. 2026-09-14에는 그보다 앞단의 문제가 관측되었습니다 — **큐에 들어간 실행이 러너를 못 받고 있습니다.**

| run | event | branch | 생성 | 상태 |
| --- | --- | --- | --- | --- |
| `34821145613` | `schedule` | `main` | 09-14 08:07:58Z | **queued** |
| `34815418142` | `pull_request` | `claude/semantic-portal-pr-merge-e5a48k` | 09-14 06:54:24Z | **queued** |
| `34745806561` | `schedule` | `main` | 09-13 07:40:17Z | success |
| `34680534430` | `schedule` | `main` | 09-12 07:21:49Z | success |

10:52Z 기준으로 PR 실행은 4시간, 스케줄 실행은 2시간 45분째 `queued`이고 **실행 중인 것은 하나도 없습니다.** 직전까지 스케줄 실행은 매일 정상 완료했습니다(09-10~09-13). 즉 정지는 09-13 07:40과 09-14 06:54 사이에 시작되었습니다.

**원인을 PR·봇 작성자 쪽으로 돌리지 마십시오.** 처음에는 `pull_request` 트리거나 bot 작성 PR 특성을 의심했지만, 같은 시간대에 `main`의 `schedule` 실행도 똑같이 멈춰 있어 그 가설은 기각됩니다. 두 트리거가 동일하게 영향을 받으므로 저장소·Actions 레벨의 러너 가용성 문제로 읽는 것이 맞습니다.

이것은 포털이 소유한 결함이 아니며 포털에서 고칠 수 없습니다. 다만 지속되면 결과가 큽니다 — **큐의 어떤 PR도 check를 하나도 받을 수 없습니다.** 위 절이 "stacked PR은 fuzz만 받는다"고 적어 둔 그 fuzz조차 실행되지 않습니다.

기록의 한계 — 이 절은 관측이지 진단이 아닙니다. 러너 부족인지, 조직 단위 사용량 한도인지, GitHub 측 장애인지는 이 저장소에서 판별할 수 없습니다. 해소되면 이 절은 단발성 사건으로 남습니다.

**1차 해소(2026-09-14 15:20Z):** `1702e19`의 실행(`34835418393`)이 10:53:39에 큐에 들어가 **15:14:49에 시작**했고, 두 job 모두 success입니다 — Hypothesis 27초, Atheris 약 5분. 즉 **큐 대기 4시간 21분** 뒤 정상 속도로 실행됐습니다. job이 실패한 것이 아니라 러너를 못 받고 있었다는 위 해석과 일치합니다. 위에 적은 "어떤 PR도 check를 받을 수 없다"는 상태는 종료되었고, 이 절은 진행 중인 결함이 아니라 그날의 기록으로 읽으십시오.

**정정(2026-09-14 21:37Z): "단발성"이 아니었습니다.** 1차가 풀린 직후 같은 현상이 다시 시작됐고, 이번에는 더 길었습니다.

| 실행 | 큐 진입 | 실제 시작 | 대기 |
| --- | --- | --- | --- |
| `34835418393` | 10:53:39Z | 15:14:49Z | **4시간 21분** |
| `34861648311` | 15:21:48Z | 21:22:24Z | **6시간 01분** |
| `34899987649` | 21:39:08Z | 2026-09-15 01:47:28Z | **4시간 08분** |
| `34919145469` | 2026-09-15 01:55:09Z | 2026-09-15 07:15:21Z | **5시간 20분** |
| `34941865676` | 2026-09-15 07:28:21Z | 2026-09-15 10:45:08Z | **3시간 16분** |
| `34960150814` | 2026-09-15 10:51:07Z | 2026-09-15 14:17:40Z | **3시간 26분** |
| `34981333667` | 2026-09-15 14:23:46Z | 2026-09-15 18:03:39Z | **3시간 39분** |
| `35006062420` | 2026-09-15 18:12:51Z | 2026-09-15 21:29:12Z | **3시간 16분** |
| `35026896954` | 2026-09-15 21:40:02Z | 2026-09-16 01:11:29Z | **3시간 31분** |
| `35057397730` | 2026-09-16 04:54:05Z | 2026-09-16 09:58:41Z | **5시간 04분** |
| `35087413648` | 2026-09-16 10:53:39Z | 2026-09-16 16:58:28Z | **6시간 04분** |
| `35125911245` | 2026-09-16 17:04:38Z | 2026-09-16 21:13:04Z | **4시간 08분** |
| `35151710232` | 2026-09-16 21:19:14Z | 2026-09-17 00:50:12Z | **3시간 31분** |
| `35179880015` | 2026-09-17 03:53:45Z | 2026-09-17 09:17:54Z | **5시간 24분** |
| `35570525874` | 2026-09-21 06:55:10Z | 2026-09-21 13:50:58Z | **6시간 55분** |
| `35804075010` | 2026-09-23 00:54:38Z | 2026-09-23 03:21:18Z | **2시간 26분** |
| `36271706689` | 2026-09-26 21:05:00Z | 2026-09-27 04:12:10Z | **7시간 07분** |
| `36519227061` | 2026-09-29 03:54:38Z | 2026-09-29 12:30:24Z | **8시간 35분** |
| `36608278902` | 2026-09-29 17:54:42Z | 2026-09-30 03:02:36Z | **9시간 07분** |
| `36705380821` | 2026-09-30 10:55:39Z | 2026-09-30 11:54:21Z | **58분 42초** |

2차 실행도 두 job 모두 success이고 시작된 뒤에는 정상 속도였습니다(Hypothesis 18초, Atheris 약 5분). 즉 실패가 아니라 대기라는 해석은 두 번 다 맞았지만, **한 번으로 끝난다는 예상은 틀렸습니다.**

두 구간을 이어 보면 2차는 1차가 풀린 지 약 1분 뒤에 큐에 들어갔습니다. 따라서 06:54부터 21:32까지 약 14시간 반 동안 이 저장소의 워크플로는 15:14~15:20의 짧은 창을 빼면 사실상 실행되지 못했습니다. 그 사이 push한 head는 모두 상당 시간 검증되지 않은 상태로 남았습니다.

**16차(2026-09-23 03:26Z)까지 관측했습니다.** 열여섯 번 모두 같은 모양입니다 — 몇 시간 대기한 뒤 스스로 풀리고, 시작된 뒤에는 정상 속도로 돌고, 결과는 green입니다. 대기 시간은 2시간 26분에서 6시간 55분 사이에 흩어져 **일정하지 않습니다.** 개별 값은 위 표에 있습니다.

**이 표는 여기서 멈춥니다.** 열네 건이면 "대기가 길고, 불규칙하고, 스스로 풀리고, 결과는 green"이라는 결론에 필요한 증거는 충분하며, 앞 문단들이 보여 주듯 여기서 더 얻어낼 분포적 주장은 없습니다(세 번 시도해 세 번 틀렸습니다). 앞으로는 **경계가 움직이거나(2시간 26분 미만, 6시간 55분 초과) 현상 자체가 끝날 때만** 행을 추가하십시오. 같은 범위 안의 관측을 계속 적는 것은 문서를 길게 만들 뿐 읽는 사람에게 새로 알려 주는 것이 없습니다. 따라서 "약 N시간이면 풀린다"는 식의 예측은 세우지 마십시오 — 이 문서도 한 번 그렇게 읽었다가 2차에서 틀렸습니다.

**표본이 늘수록 범위는 좁아지지 않고 넓어졌습니다.** 네 번까지는 4시간 08분~6시간 01분이었는데, 5차가 3시간 16분으로 그 하한 아래로 내려가 지금은 3시간 16분~6시간 01분입니다. 즉 관측을 더 해도 수렴하는 것이 아니라 양쪽으로 벌어지고 있으므로, **여기서 배운 어떤 임계값도 근거로 쓸 수 없습니다.** 11차가 6시간 04분으로 상한마저 밀어 올렸고, 15차가 6시간 55분으로 다시 밀어 올렸습니다. 16차는 반대쪽에서 2시간 26분으로 하한을 내렸습니다. 지금 범위는 2시간 26분~6시간 55분입니다. **열여섯 번을 관측하는 동안 범위는 한 번도 좁아지지 않았습니다.**

6차부터 10차까지는 경계가 움직이지 않았지만, 11차가 상한을 6시간 04분으로 새로 썼습니다. 12차부터 14차까지는 다시 경계 안이었고, 15차(`35570525874`, 6시간 55분)가 상한을 한 번 더 밀어 올렸습니다.

**표의 행은 연속하지 않습니다.** 14차와 15차 사이에도 같은 현상이 세 번 더 있었지만 모두 3시간 16분~6시간 04분 범위 안이어서, 위에 적은 멈춤 규칙에 따라 행을 만들지 않았습니다. 즉 이 표는 **경계가 움직인 순간만 남긴 기록**이지 모든 관측의 목록이 아닙니다. 행 사이의 간격을 발생 빈도로 읽지 마십시오.

15차에 대해 말할 수 있는 것은 **상한이 다시 움직였다**는 사실 하나뿐입니다. 상한이 세 번(6시간 01분 → 6시간 04분 → 6시간 55분) 갱신되었다는 것을 "상한이 올라가는 중"으로 읽지 마십시오 — 이 절은 적은 점에서 방향을 읽어 이미 세 번 틀렸고, 그 사이 범위 안에 머문 관측이 훨씬 많습니다. 실무적으로 달라지는 것은 **대기가 7시간에 가까울 수 있다**는 상한 감각뿐이고, 그것도 예측이 아니라 관측된 최댓값입니다.

**여기서 이 문서가 또 한 번 성급했습니다.** 7차까지 보고 "하한 쪽 세 번이 3시간 16분 → 3시간 26분 → 3시간 39분으로 조금씩 길어졌다"고 적었는데, 8차가 정확히 3시간 16분으로 돌아왔습니다. 세 점을 방향으로 읽은 것이고, 바로 앞 문단에서 "두 점으로 추세를 말하지 말라"고 경고해 놓고 저지른 같은 종류의 잘못입니다. 그 문장은 철회합니다.

여기서 한때 **하한이 반복된다**고 적었습니다 — 3시간 16분이 두 번 정확히 재현되었고 다섯 번이 약 23분 폭 안에 모여 있었기 때문입니다. **16차가 2시간 26분으로 그 아래로 내려가 이 서술도 철회합니다.** 3시간 16분은 반복되는 하한이 아니라 그때까지 본 가장 작은 값이었을 뿐입니다.

이것으로 이 절이 데이터에서 읽어낸 규칙성은 **네 번 모두 다음 관측에 깨졌습니다**(대기 시간 드리프트, `#27` dispatch 드리프트, 검열 편향, 그리고 반복되는 하한). 네 번이면 우연이 아니라 방법의 문제입니다 — 열몇 개의 점에서 규칙성을 찾으려는 시도 자체를 그만두십시오. 남는 것은 "대기가 길고, 불규칙하고, 스스로 풀리고, 결과는 green"뿐이며, 이 문장에는 숫자가 들어가지 않습니다.

4차도 3차가 시작된 지 약 8분 뒤에 큐에 들어갔습니다. 2차·3차·4차가 모두 직전 실행이 풀린 직후 다시 대기로 들어갔다는 뜻이고, 이 저장소에서는 **연속 대기가 기본 상태**라고 읽는 편이 실제에 가깝습니다.

**이 표는 "살아남은 실행"만 담고 있습니다 (2026-09-16 확인).** `fuzz.yml`에는

```yaml
concurrency:
  group: fuzz-${{ github.ref }}
  cancel-in-progress: true
```

가 걸려 있어서, 같은 ref에 새 커밋을 push하면 **아직 큐에 있던 직전 실행이 취소됩니다.** 실제로 `35043486426`(head `eac988c`)은 01:17:24에 큐에 들어갔다가 러너를 한 번도 받지 못한 채 03:53:23에 취소되었습니다 — 이 세션이 그 시각에 `78cb173`을 push했기 때문입니다. 대기 2시간 36분이 기록 없이 사라진 것입니다.

따라서 위 표는 **"다음 push 전에 러너를 받은 실행"만 모인 편향 표본**입니다. 대기가 길수록 다음 push에 잘리기 쉬우므로 편향의 방향은 분명합니다 — **짧은 쪽으로 치우칩니다.** 범위와 하한 부근 군집도 그만큼 할인해서 읽어야 하며, 실제 분포의 꼬리는 여기 적힌 것보다 길 수 있습니다.

측정을 깨끗하게 하려면 큐에 실행이 떠 있는 동안 push하지 않아야 하지만, 이 문서는 취소를 피하려고 다른 작업을 미루지는 않았습니다. **편향이 있다는 사실을 적어 두는 쪽을 택합니다.**

**검열되지 않은 관측은 지금 열하나이고, 편향에 대한 경험적 주장은 기각합니다 (10·11·12·13·15·16·17·18·19·20·21차).** `35057397730`·`35087413648`·`35125911245`·`35151710232`·`35570525874`·`35804075010`·`36250188163`·`36271706689`·`36519227061`·`36608278902`·`36705380821`은 큐에 떠 있는 동안 한 번도 push하지 않은 실행이고, 결과는 **5시간 04분 / 6시간 04분 / 4시간 08분 / 3시간 31분 / 6시간 55분 / 2시간 26분 / 6시간 00분 / 7시간 07분 / 8시간 35분 / 9시간 07분 / 58분 42초**입니다. 전체 최댓값과 최솟값이 **둘 다 검열되지 않은 쪽에 있습니다.** 검열이 짧은 쪽으로 치우치게 만든다는 주장과 정반대 방향의 관측입니다.

13차가 3시간 31분으로 **하한 군집(3시간 16분~3시간 39분) 안에** 들어왔습니다. 바로 앞 문단에서 지켜냈던 "검열되지 않은 관측은 전부 하한 군집보다 위"라는 서술이 이것으로 깨집니다. 검열되지 않은 열하나는 58분 42초~9시간 07분으로 **전체 범위와 정확히 같은 폭**이고, 검열된 쪽과 **구분되는 차이를 보여 주지 못합니다.**

남는 것과 버리는 것을 분명히 해 둡니다. **메커니즘은 사실입니다** — `cancel-in-progress`로 대기 중 실행이 실제로 취소되고(`35043486426`이 그 예), 잘린 실행은 표에 기여하지 않으므로 표가 완전한 표본이 아니라는 점은 변하지 않습니다. **기각되는 것은 그 편향이 이 데이터에서 관측된다는 주장입니다.** 열 번의 검열되지 않은 관측으로는 짧은 쪽 치우침이 나타나지 않습니다(앞서 이 문장에 남아 있던 "다섯 번"은 위 census 갱신과 어긋난 낡은 수였습니다).

이 절이 적은 점에서 방향을 읽어 틀린 것은 이번이 **세 번째**입니다(대기 시간 드리프트, `#27` dispatch 드리프트, 그리고 이 편향). 그러니 이 데이터로 분포에 관한 주장을 더 세우지 마십시오. 확실한 것은 "대기가 길고, 불규칙하고, 스스로 풀리고, 표본이 불완전하다"까지입니다.

**17차 (2026-09-26): 이 세션이 검열을 기록하면서 스스로 한 건 만들었습니다.** `#102`에 `42a06df`를 push해 14:00:22/23Z에 큐에 들어간 job 두 건이, 55분 46초 뒤 **14:56:08Z에 취소**되었습니다 — 취소 시각이 같은 세션의 다음 push(`16dde2a`) 시각과 초 단위로 같습니다. 위 절이 서술한 `cancel-in-progress` 메커니즘을 이 문서를 쓰는 쪽이 직접 실행한 것입니다. **census 유지 목적으로만 적습니다** — 이것으로 편향 주장을 되살리지 마십시오. 같은 절이 이미 그 주장을 기각했고, 17차는 오히려 6시간 00분 33초로 상한(6시간 55분)을 넘지 못했습니다.

17차 본체는 `36250188163`으로, 큐 진입 14:56:08Z → 실제 시작 20:56:41Z = **6시간 00분 33초**입니다. 경계 안이므로 위 표에는 행을 추가하지 않았습니다(상한·하한 모두 그대로). 시작된 뒤 실행은 여전히 빠릅니다 — Hypothesis 22초, Atheris 4분 40초, 두 job 모두 success. 대기가 전부이고 실행이 아니라는 이 절의 기존 관측이 한 번 더 같게 나옵니다.

**18차 (2026-09-27): 상한이 또 움직여 7시간 07분입니다.** `36271706689`은 큐 진입 2026-09-26 21:05:00Z → 실제 시작 2026-09-27 04:12:10Z = **7시간 07분 10초**로, 직전 상한 6시간 55분을 넘었습니다. 두 job 모두 success이고 실행은 여전히 빠릅니다(Hypothesis 24초, Atheris 4분 47초). 큐에 떠 있는 7시간 동안 이 세션은 한 번도 push하지 않았으므로 검열되지 않은 관측입니다.

이것으로 이 절에서 **경계가 움직인 것이 다섯 번째**입니다. 상한은 6시간 01분 → 6시간 04분 → 6시간 55분 → 7시간 07분으로 계속 밀렸고, 그때마다 "이제 상한을 봤다"는 서술이 다음 관측에 깨졌습니다. 같은 결론을 반복합니다 — 이 데이터로 분포의 상한을 주장하지 마십시오. 표는 "여기까지 본 값"의 목록이며 최댓값은 관측의 한계일 뿐입니다.

**2026-09-29: 큐에서 24시간을 넘긴 check는 완료되지 않고 취소됩니다 — `#81`의 판정이 이렇게 사라졌습니다.**

`#81` head `e4291e89`에서 이틀 동안 `queued`였던 check 8건이 이 날 사라졌습니다. 완료된 것이 아니라 **취소**되었고, 소요 시간이 초 단위로 정확히 24시간입니다.

| check | 큐 진입 | 취소 | 소요 |
| --- | --- | --- | --- |
| `trivy-fs` | 2026-09-28 03:17:01Z | 2026-09-29 03:17:02Z | **24시간 00분** |
| `osv-scan` | 2026-09-28 03:17:01Z | 2026-09-29 03:17:02Z | **24시간 00분** |
| `dependency-review` | 2026-09-28 03:17:01Z | 2026-09-29 03:17:02Z | **24시간 00분** |
| `scorecard` | 2026-09-28 03:17:01Z | 2026-09-29 03:17:02Z | **24시간 00분** |
| `opencode-review` | 2026-09-28 03:17:54Z | 2026-09-29 03:17:55Z | **24시간 00분** |
| `coverage-source-tree` | 2026-09-28 03:17:54Z | 2026-09-29 03:17:54Z | **24시간 00분** |
| `coverage-evidence` | 2026-09-28 03:17:54Z | 2026-09-29 03:17:54Z | **24시간 00분** |
| `Detect CodeQL languages` 외 5건 | 2026-09-27 03:18:2xZ | 2026-09-28 03:18:2xZ | **24시간 00분** |

13건이 두 코호트로 나뉘어 각각 정확히 24시간에 끊겼습니다. 이것은 이 절이 이미 기록한 `cancel-in-progress`(같은 ref에 새 push가 들어오면 대기 중 실행을 취소)와 **다른 메커니즘**입니다 — push가 없었고, 시각이 진입 시각 + 24시간에 초 단위로 맞습니다. GitHub가 큐에 24시간 이상 머무른 job을 자동 취소하는 한계입니다.

**결과가 이 문서의 핵심 결론을 바꿉니다.** 지금까지 이 문서는 `#81`의 수리에 대해 "수리는 존재하고 판정은 아직 없다"고 적었습니다. 정확히 말하면 **판정은 앞으로도 생기지 않습니다** — `trivy-fs`는 이 head에서 한 번도 실행되지 않고 취소되었고, 큐 지연이 24시간을 넘는 동안에는 재실행해도 같은 24시간 시계가 다시 돌기 시작할 뿐입니다. 포털이 자기 저장소에서 고칠 수 있는 유일한 실패 check가, 고친 head에서 판정 불가 상태입니다.

**취소된 required check는 pending이 아닙니다.** 병합 게이트에서 `cancelled`는 통과가 아니며 스스로 풀리지도 않습니다. 누군가 재실행해야 하고, 재실행은 위 시계를 리셋합니다.

**위 대기 표에 구조적 상한이 있다는 뜻도 됩니다.** 표는 `큐 진입 → 실제 시작`을 기록하므로, 시작하지 못한 실행은 표에 한 행도 남기지 못합니다. 24시간을 넘긴 대기는 시작 대신 취소되므로 **표의 값은 24시간 미만일 수밖에 없습니다.** 즉 18차의 7시간 07분은 관측 가능한 범위의 상한 후보일 뿐이고, 실제 지연이 그보다 얼마나 큰지는 이 표로 알 수 없습니다. 이것은 데이터에서 읽은 규칙성이 아니라 메커니즘에서 따라 나오는 제약입니다.

**위 예측은 틀렸습니다 (2026-09-29 확인).** "`#107`과 `#102`의 코호트도 24시간 뒤 취소되어야 한다"고 적었는데, 둘 다 취소되지 않고 **서비스되었습니다.** `#102`는 새 head `365e4cd`에서 8시간 35분 46초 대기 후 시작해 두 job 모두 success, `#107`은 같은 시점에 success 21건입니다.

**따라서 24시간 취소는 queued check의 일반적 운명이 아닙니다.** `#81`에서 13건이 정확히 24시간에 끊긴 것은 사실이고 메커니즘도 사실이지만, 그것은 **큐가 끝까지 그 job을 서비스하지 않았을 때** 도달하는 상한입니다. 같은 저장소의 다른 head들은 8~9시간 대기 후 정상 실행되었습니다. `#81`이 왜 서비스되지 않았는지는 이 문서가 측정하지 못했습니다 — required workflow 집합이 더 크다는 점(30건 이상)과 head가 오래되었다는 점이 후보지만 확인하지 않았으므로 원인으로 적지 않습니다.

**19차·20차가 상한을 연달아 밀었습니다 — 8시간 35분, 그리고 9시간 07분.** `36519227061`(큐 진입 2026-09-29 03:54:38Z → 시작 12:30:24Z)과 `36608278902`(큐 진입 2026-09-29 17:54:42Z → 시작 2026-09-30 03:02:36Z)이며 둘 다 대기 중 push가 없었습니다. 경계가 움직인 것이 이제 **일곱 번째**입니다(그리고 아래 21차가 여덟 번째입니다). 이 절의 결론을 다시 확인합니다 — 상한을 주장하지 마십시오. 참고로 현재 값은 위 절의 24시간 취소 한계에 아직 한참 못 미칩니다 — 다만 이 여유를 저장소 전체의 여유로 읽으면 안 됩니다(바로 아래 정정).


**표본의 범위를 잘못 적어 두었습니다 (2026-09-30 정정).** 위 표의 19행은 전부 **이 문서 브랜치의 `fuzz` 워크플로 한 레인**입니다. 그런데도 이 절은 그 범위(2시간 26분~9시간 07분)를 저장소 전체의 대기 감각처럼 읽었습니다. 같은 저장소의 다른 레인을 한 번 읽어 보니 그 서술이 유지되지 않습니다. `#107` head `6ace6aff`의 Strix required workflow(run `36444353689`, 큐 진입 2026-09-28 15:32:27Z)입니다.

| job | 큐 진입 | 실제 시작 | 대기 |
| --- | --- | --- | --- |
| `109002667108` admit-head | 2026-09-28 15:32:28Z | 2026-09-29 09:49:34Z | **18시간 17분** |
| `109002667532` changed-scope | 2026-09-28 15:32:28Z | 2026-09-29 09:49:34Z | **18시간 17분** |
| `109351047899` strix | 2026-09-29 09:49:40Z | 2026-09-29 16:54:55Z | **7시간 05분** |

**18시간 17분 06초는 위 표 최댓값의 두 배입니다.** 이 행들을 위 표에 섞지 않았습니다 — 위 표는 한 워크플로·한 브랜치의 동질 표본이고 census도 그 표본을 셉니다. 대신 결론을 고칩니다. **위 표의 범위는 저장소의 대기 범위가 아니라 그 레인의 대기 범위입니다.** 상한이 일곱 번 움직인 것을 "경계가 조금씩 밀린다"로 읽었지만 레인을 하나 바꾸자 경계가 두 배로 뛰었습니다. 결함은 산술이 아니라 **표본 선택**이며, 이 값은 `#107`의 실패를 세던 그 run 안에 처음부터 있었는데 그때 대기를 읽지 않았습니다.

**24시간 취소는 run이 아니라 job 단위입니다.** 이 run은 큐 진입 2026-09-28 15:32:27Z에서 `strix` job 실행 시작 2026-09-29 16:54:55Z까지 **25시간 22분 28초**가 걸렸는데 취소되지 않았습니다. 단계마다 시계가 새로 돌기 때문입니다 — 18시간 17분도 7시간 05분도 각각 24시간 미만입니다. 따라서 위 `#81` 절의 "정확히 24시간에 끊겼다"는 관측은 **한 job이 혼자 24시간을 넘겼다**는 뜻이고, 다단계 required workflow가 하루를 넘겨 끝나는 것은 그 한계와 별개로 정상 경로입니다.

**21차가 하한을 절반 아래로 내렸습니다 — 58분 42초 (2026-09-30).** `36705380821`은 큐 진입 10:55:39Z → 시작 11:54:21Z이고 대기 중 push가 없었으며 두 job 모두 success입니다(Hypothesis 10초, Atheris 4분 26초). 종전 하한 2시간 26분의 **40%**입니다. 경계가 움직인 것이 이로써 여덟 번째이고, 이번에는 아래쪽입니다.

같은 날 다른 레인도 빨라졌습니다 — `#28` `103c9eb`의 Security Scan gate job은 1시간 04분에 러너를 받았는데, 같은 레인이 아침에는 2시간 22분이었습니다. **그래도 "큐가 빨라지고 있다"고 적지 않습니다.** 이 절은 적은 점에서 방향을 읽어 네 번 틀렸고, 두 점은 다섯 번째 시도를 정당화하지 않습니다. 남는 사실은 하나입니다 — 범위가 **58분 42초~9시간 07분**으로 또 넓어졌고, 열아홉 번을 관측하는 동안 한 번도 좁아지지 않았습니다.

실무적으로 달라지는 것이 하나 있습니다. **head를 새로 밀 때 잃는 현재-head 증거의 비용이 측정으로 내려갔습니다.** 직전까지 그 비용은 "다음 판정까지 3~9시간"이었는데 이번 관측에서는 한 시간 남짓입니다. 비용이 작아졌다고 push를 늘릴 이유는 없지만, 기록할 가치가 있는 변경을 비용 때문에 미룰 이유도 그만큼 줄었습니다. 다만 이것도 한 점이므로 다음 push의 대기가 다시 아홉 시간일 수 있다고 보고 계획하십시오.

**정지 규칙을 조입니다.** 두 시간 뒤 `85ee6d3`의 실행(`36712068507`)이 큐 진입 12:00:48Z → 시작 12:48:34Z = **47분 46초**로 하한을 또 내렸습니다. 규칙이 "2시간 26분 미만이면 행 추가"였으므로 이것도 행 자격이 있지만 **넣지 않았습니다.** 넣기 시작하면 한 시간마다 같은 사실("하한이 또 내려갔다")로 행이 붙고, 그것은 이 규칙이 애초에 막으려던 문서 팽창입니다. 따라서 규칙을 다음과 같이 바꿉니다 — **한 시간 미만 값은 더 이상 행을 만들지 않습니다.** 대신 한 문장으로 기록합니다: 2026-09-30에 이 레인의 하한이 2시간 26분에서 **58분 42초 → 47분 46초**로 두 시간 안에 두 번 무너졌습니다. 상한 쪽(9시간 07분 초과)과 "현상 자체가 끝날 때"는 그대로 행 자격을 유지합니다.


**대기를 읽을 때 `started_at`의 의미가 상태에 따라 바뀝니다.** job이 `queued`인 동안 job-level `started_at`은 **큐 진입 시각**이고, 실행이 시작되면 같은 필드가 **실제 시작 시각**으로 교체됩니다. 그래서 큐에 떠 있는 동안 읽은 값은 "지금까지의 대기"이고 완료 후 읽은 값은 위 표의 `실제 시작`입니다. 두 상태에서 읽은 값을 한 번의 뺄셈에 섞지 마십시오. 참고로 run-level `created_at`·`run_started_at`은 둘 다 트리거 시각(14:56:08Z)이어서 실제 시작을 알려 주지 않습니다 — 대기는 run이 아니라 job에서 읽어야 합니다.

다만 **한 점입니다.** 이 문서는 적은 점에서 방향을 읽어내 두 번 틀렸으므로, 이것도 "예측대로 나왔다" 이상으로 말하지 않습니다. 검열되지 않은 관측이 몇 번 더 쌓이기 전까지는 확증이 아니라 정합성입니다.

실무적으로 남는 것은 하나입니다. **이 저장소에서 push한 head는 몇 시간 동안 검증되지 않은 채로 있을 수 있습니다.** 그 시간 동안 checks가 비어 있는 것은 실패가 아니라 대기이며, 그것을 실패로 읽거나 재실행으로 대응하지 마십시오.

진단은 여전히 하지 않습니다. 다만 "그날의 단발성 기록"이 아니라 **2026-09-14 06:54Z부터 2026-09-21 13:50Z까지 여드레째 이어진 조건**으로 읽으십시오. 다시 관측되면 이 표에 행을 더하십시오.

**이 현상에는 조직 차원의 주인이 있습니다 (2026-09-15 확인).** `ContextualWisdomLab/.github`에 Actions 큐 적체를 전담하는 owner lane([`.github#1150`](https://github.com/ContextualWisdomLab/.github/pull/1150), "read-only Actions queue health evidence")이 열려 있고, 여기서 분류하는 사건 유형 중 하나가 **job은 만들어졌는데 러너가 배정되지 않는 상태**입니다. 위 네 건이 정확히 그 유형입니다. 따라서 이 절은 포털만의 기이한 현상이 아니라 **조직 전반에서 재현되는 알려진 유형**으로 읽으십시오.

다만 **포털은 그 lane의 allowlist에 없습니다.** `config/actions_queue_health_repositories.json`에 등재된 것은 `.github`·`ConceptWeave`·`ELUNVERA`·`TEPP`·`contextual-orchestrator`·`fast-mlsirm`·`naruon` 일곱 곳뿐입니다. 등재는 `.github` 쪽에서 allowlist 한 줄과 대응 contract test만 담은 bounded child PR로 진행하는 것이 그 lane의 관례이며(disksage·Pingora가 그렇게 처리되었습니다), **포털에서 폴링·분류 로직을 자체 구현하지 마십시오.** 등재되더라도 관측일 뿐이고 포털의 막힌 PR에 GREEN을 옮겨 주지 않습니다.

위 네 건의 측정값은 [해당 lane에 보고했습니다](https://github.com/ContextualWisdomLab/.github/pull/1150#issuecomment-5676434919). 보고에 담긴 요지는 측정 그 자체보다 **판정 기준에 대한 것**입니다. 그 lane의 RED 정의는 "러너 배정·checkout 신원·step이 없는 materialized job"인데, 위 네 건은 대기 중에 정확히 그렇게 보였다가 스스로 러너를 받아 SUCCESS로 끝났습니다. 즉 **어느 한 시점의 관측만으로는 RED와 "길지만 회복할 대기"를 구분할 수 없습니다.** 대기 시간으로도 구분되지 않습니다 — 2시간 26분에서 6시간 55분 사이로 흩어져 임계값을 세울 수 없기 때문입니다. 판정은 종료 결과를 보거나 그 외의 판별자를 써야 합니다.

포털 입장에서 실무적으로 달라지는 것은 없습니다. 여기서 고칠 것은 여전히 없고, checks가 비어 있는 동안은 여전히 대기로 읽으면 됩니다. 달라지는 것은 **이 절을 원인 미상의 관측으로 남겨 두지 않아도 된다는 점**입니다.

### stacked PR은 fuzz 말고 아무 게이트도 돌지 않습니다 (2026-09-09 측정)

이 저장소의 두 워크플로는 PR 트리거 범위가 다릅니다.

| 워크플로 | PR 트리거 | 결과 |
| --- | --- | --- |
| `tests.yml` | `pull_request: branches: [main]` | base가 `main`인 PR에서만 실행 |
| `fuzz.yml` | `pull_request:` (필터 없음) | 모든 PR에서 실행 |

따라서 **base가 feature 브랜치인 PR은 API integration suite도, coverage 게이트도 돌지 않습니다.** 측정으로 확인했습니다.

| PR | base | check run 총계 | 내역 |
| --- | --- | --- | --- |
| `#99` | `feat/openmetadata-2-read-adapter` | **2** | Atheris, Hypothesis뿐 |
| `#75` | `cursor/ontology-catalog-plane-90aa` | **2** | Atheris, Hypothesis뿐 |
| `#97` | `feat/openmetadata-2-read-adapter` | 같은 규칙 적용 | 위 규칙에서 따름 |
| `#102` | `docs/product-technical-gap-baseline` | **2** | 문서 전용이라 영향 작음 |

`#99`는 파일 21건에 신규 소스 모듈 5개와 신규 test 파일 7개를 담고 있습니다. **그 test들은 자기 PR에서 한 번도 실행되지 않습니다.** 그런데 checks 목록에는 초록 2건만 보이므로, 리뷰어에게는 "CI 통과"로 읽힙니다.

정확히 적어 둡니다 — 이것이 "검증 안 된 코드가 main에 오른다"는 뜻은 **아닙니다.** 부모 PR(`#96`, `#73`)의 base는 `main`이므로, 자식이 부모 브랜치에 병합되면 부모 PR의 checks가 `synchronize`로 다시 돌아 그 코드를 덮습니다. 실제 문제는 다른 데 있습니다.

1. **자식 PR의 승인 근거가 비어 있습니다.** 자기 diff의 test를 한 번도 돌리지 않은 초록 2건 위에서 리뷰·병합 판단이 이뤄집니다.
2. **저장소가 하드 게이트라고 선언한 것들이 자식 PR에서 실행되지 않습니다** — 100% coverage와 docstring 게이트가 그렇습니다.
3. **결함 발견이 부모로 밀립니다.** 부모에서 잡히면 diff가 훨씬 크고 어느 자식이 원인인지 귀속하기 어렵습니다.

조치는 `tests.yml`의 `branches: [main]` 제한을 푸는 것이지만, 그 파일은 이미 `#93`/`#100`/`#57` 세 PR이 동시에 고치고 있는 대상입니다(위 절). **새 writer를 더하지 마십시오** — 동시성 정리를 하는 쪽에서 base 필터까지 함께 정하는 것이 맞습니다.

### autofix dispatch가 `#27`에서 같은 head로 헛돌고 있습니다 (2026-09-09 확인, 09-15 갱신)

`opencode-agent[bot]`이 `#27`에 **완전히 같은 코멘트를 4일 연속** 남겼습니다. 본문·head SHA가 모두 동일하고 `epoch`만 다릅니다.

| 게시 시각 (UTC) | `epoch` | 본문이 명시한 head |
| --- | --- | --- |
| 2026-09-06 20:05:47 | `1788725147` | `8aad3b47...` |
| 2026-09-07 20:23:21 | `1788812600` | `8aad3b47...` |
| 2026-09-08 19:46:31 | `1788896791` | `8aad3b47...` |
| 2026-09-09 19:37:57 | `1788982677` | `8aad3b47...` |
| 2026-09-10 19:28:49 | `1789068529` | `8aad3b47...` |
| 2026-09-11 19:29:44 | `1789154984` | `8aad3b47...` |
| 2026-09-12 19:00:02 | `1789239602` | `8aad3b47...` |
| 2026-09-13 22:52:13 | `1789339933` | `8aad3b47...` |
| 2026-09-14 — 게시 없음 | — | — |
| 2026-09-15 04:55:29 | `1789448129` | `8aad3b47...` |
| 2026-09-16 03:30:26 | `1789529426` | `8aad3b47...` |
| 2026-09-17 03:52:12 | `1789617132` | `8aad3b47...` |
| 2026-09-18 05:26:50 | `1789709210` | `8aad3b47...` |
| 2026-09-21 10:03:57 | `1789985036` | `8aad3b47...` |
| 2026-09-22 03:55:26 | `1790049326` | `8aad3b47...` |
| 2026-09-23 00:00:06 | `1790121605` | `8aad3b47...` |
| 2026-09-25 07:59:41 | `1790323180` | `8aad3b47...` |
| 2026-09-26 00:54:30 | `1790384070` | `8aad3b47...` |

```text
<!-- pr-review-fix-scheduler autofix-dispatch head_sha=8aad3b47... epoch=... -->
Scheduled review-feedback autofix for this PR head.
```

**열두 번 모두 head는 `8aad3b4` 그대로입니다.** 즉 autofix가 dispatch되고, 아무것도 바꾸지 못하고, 얼마 뒤 같은 head로 다시 dispatch됩니다. 수렴하지 않는 루프이며 매 회차가 코멘트 하나를 남깁니다.

**갱신(2026-09-14): 관측 창을 4일에서 8일로 늘렸습니다.** 2026-09-06부터 09-13까지 하루도 빠짐없이 같은 내용이 게시되었고, head는 여드레 내내 한 번도 움직이지 않았습니다. 처음 나흘로 내린 "수렴하지 않는다"는 판단이 두 배의 창에서도 그대로입니다. 게시 시각은 대체로 19:00~20:23 UTC였고 09-13만 22:52로 밀렸습니다.

**정정(2026-09-15): "매일"이 아닙니다.** 09-14에는 한 건도 게시되지 않았고, 다음 dispatch는 09-15 04:55:29(`epoch=1789448129`)로 직전 회차에서 **30시간 3분** 뒤였습니다. 즉 이 루프의 주기는 24시간 고정이 아니며, 하루를 통째로 건너뛸 수 있습니다. 위 표와 제목에 쓴 "매일"은 처음 여드레의 우연한 규칙성을 일반화한 것이었으니 그대로 믿지 마십시오.

게시 시각이 계속 뒤로 밀린다고 적었던 부분은 **10차에서 틀렸습니다.** 19:00~20:23 → 22:52 → (건너뜀) → 04:55까지는 계속 늦어졌지만, 10차는 03:30으로 **오히려 앞당겨졌습니다.** 간격도 30시간 03분 → 22시간 35분 → 24시간 22분 → 25시간 35분으로 들쭉날쭉합니다. 즉 한 방향으로 밀리는 드리프트가 아니라 그냥 **불규칙**합니다. 이 문서가 몇 개의 점에서 방향을 읽어낸 잘못이 위 Actions 대기 절에 이어 여기서도 반복된 것이니, 남은 것은 방향이 아니라 "주기가 24시간이 아니고 예측되지 않는다"는 사실뿐입니다.

바뀌지 않은 것이 더 중요합니다. 열두 번째 회차에도 head는 여전히 `8aad3b4`이고, 관측 창은 이제 09-06부터 09-18까지 열사흘입니다.

**이 표도 여기서 멈춥니다.** 열두 건이면 "같은 head로 반복 dispatch되고, 주기는 22~30시간 사이로 불규칙하고, 아무것도 바뀌지 않는다"는 결론에 충분합니다. 위 Actions 대기 표와 같은 이유로, 앞으로는 **head가 움직이거나, 루프가 멈추거나, 주기가 이 범위를 크게 벗어날 때만** 행을 추가하십시오. 루프가 수렴하지 않는다는 판단은 세 배로 넓힌 창에서도 그대로입니다. **주기가 흔들린 것이지 결과가 달라진 것이 아닙니다.**

범위도 확인했습니다. 2026-09-07 이후 이 저장소 열린 PR 36건 중 **활동이 있는 것은 `#27` 하나뿐**입니다(나머지는 이 세션이 건드린 `#102`·`#80`·`#99`와 maintainer가 건드린 `#73`뿐). 코멘트는 예외 없이 `updated_at`을 올리므로, 다른 PR은 같은 dispatch를 받지 않았다고 말할 수 있습니다. `#27`은 열린 PR 중 가장 오래된 것입니다(2026-07-20 생성).

**갱신(2026-09-23): 주기가 22~30시간 범위를 아래로 벗어났습니다.** 위 멈춤 규칙이 요구하는 조건이므로 행을 더했습니다. 09-19(25시간 42분)와 09-20(25시간 49분)은 범위 안이라 행을 만들지 않았고, 범위 밖 두 건을 읽을 수 있도록 직전 회차인 09-21만 기준점으로 함께 적었습니다. 간격은 `epoch` 차이로 계산했습니다.

- 09-21 10:03:57 → 09-22 03:55:26 = **17시간 51분** (`1790049326 - 1789985036 = 64290`초)
- 09-22 03:55:26 → 09-23 00:00:06 = **20시간 05분** (`1790121605 - 1790049326 = 72279`초)

즉 이 루프의 주기는 22시간 아래로도 내려갑니다. 앞 절과 같은 이유로 여기서 방향이나 새 주기를 읽어내지 마십시오 — 이 문서는 바로 이 표에서 한 번 드리프트를 잘못 읽었습니다. 달라진 것은 폭이지 결론이 아닙니다.

**갱신(2026-09-26): 하한이 다시 내려가 16시간 54분입니다.** 09-25 07:59:41 → 09-26 00:54:30 = **16시간 54분**(`1790384070 - 1790323180 = 60890`초)로, 위 17시간 51분 아래입니다. 멈춤 규칙이 요구하는 조건이라 두 행을 더했습니다 — 범위 밖인 09-26과, 그 간격을 읽을 수 있게 하는 직전 회차 09-25입니다. 그 사이의 09-24 03:49:18(직전 간격 27시간 49분)과 09-25(28시간 10분)는 범위 안이라 행을 만들지 않았고 여기 산문으로만 적습니다.

**이제까지 관측된 폭은 16시간 54분~30시간 03분입니다.** 하한이 두 번(22시간 → 17시간 51분 → 16시간 54분), 상한이 한 번 갱신되었습니다. 스무 번째 dispatch에서도 head는 `8aad3b4`이고, 관측 창은 2026-09-06부터 09-26까지 스무하루입니다. **주기는 계속 넓어지고 결론은 계속 같습니다** — 이 표에서 주기를 예측하려는 시도는 그만두십시오.

**결론은 그대로입니다.** 열일곱 번째 dispatch에서도 head는 `8aad3b4`이고, 관측 창은 2026-09-06부터 09-23까지 열여드레입니다. 주기가 넓어졌을 뿐 루프는 여전히 수렴하지 않습니다.

**이 갱신이 늦은 이유를 적어 둡니다 — 관측 방법의 결함입니다.** 이 세션은 `search_pull_requests`의 `updated:>=` 질의로 매시간 저장소 활동을 확인했는데, 09-22 04:52Z부터 23:52Z까지 스무 번 가까이 **결과 0건**을 받았습니다. 그러나 09-22 03:55:26Z의 dispatch 코멘트는 그 내내 존재했습니다. 원인은 단정하지 않습니다(색인 지연인지 질의 의미 차이인지 확인하지 않았습니다). 확인된 사실만 적으면 **검색 질의의 0건은 "활동이 없었다"의 증거가 되지 못합니다.** 활동의 부재를 주장하려면 검색이 아니라 API 직접 조회(코멘트 목록, `updated_at` 정렬 목록)로 확인하십시오. 위 열두 건까지의 표는 API 직접 조회로 만든 것이라 영향을 받지 않지만, 그 사이 이 세션이 "변화 없음"이라고 보고한 구간에는 실제로 변화가 있었습니다.

**같은 결함이 두 번째 API 표면에서, 그것도 처방된 우회책 쪽에서 재현되었습니다 (2026-10-05 10:53Z).** 중앙 `.github`의 CLAUDE.md는
`actions/runs?status=completed`가 큐가 요동칠 때 오해를 부르는 표본이라고 적고, 그 대책으로 **`status=success`와 `status=failure`를 직접
질의하라**고 처방합니다. 이 세션은 그 처방을 그대로 따라 왔습니다. 그런데 10:53Z 조회에서 `status=failure&per_page=3`이 돌려준 "가장 새로운
실패"는 **2026-10-04 11:08:13Z** — 하루 가까이 지난 실행이었습니다. 같은 순간 필터 없는 `actions/runs?per_page=8`은 그보다 새로운
10-05 실패를 **다섯 건** 보여 줍니다(`37299110002` 10:50:20Z Secret Scan, `37298070538` 10:40:26Z SAST Semgrep,
`37296265519` 10:23:24Z Python Security, `37295909054` 10:20:04Z PR Review Autofix, `37295069246` 10:12:21Z Strix).

**누락은 삭제나 결론 변경 때문이 아닙니다.** 직전 사이클에 annotation까지 읽은 `37286873608`(10-05 08:57:18Z)을 id로 직접 조회하면
`status=completed conclusion=failure`로 그대로 존재합니다. 즉 레코드는 살아 있고 **필터 질의의 정렬·색인만 뒤쳐져 있습니다.**

그래서 이 문서의 관측 규칙을 하나 고칩니다 — **`status=` 필터 결과를 "가장 새로운 것"으로 읽지 마십시오.** 활동의 최신 상태를 알아야 할 때는
필터 없는 `actions/runs?per_page=N`으로 조회하고, `status=` 필터는 "이 결론을 가진 사례가 과거에 존재했다"는 용도로만 쓰십시오. 중앙
CLAUDE.md의 처방은 churn 구간에서 `status=completed`보다 나은 선택이라는 점에서는 여전히 맞지만, **그것이 최신성을 보장한다는 뜻은 아닙니다.**

**제 직전 보고에 대해서도 적어 둡니다.** 09:53Z에 저는 "`.github`는 08:57Z 이후 약 한 시간 조용하다"고 보고했습니다. 필터 없는 조회로
확인한 결과 08:57Z 다음 실행은 10:12:21Z이므로 **그 문장 자체는 사실이었습니다** — 그러나 근거로 쓴 질의는 지금 신뢰할 수 없다고 판명된
바로 그 질의입니다. 결론이 맞았던 것은 운이고, 방법은 틀렸습니다. 이 구분을 남기는 이유는, 같은 방법으로 만든 "조용하다"는 보고가 다음에는
틀릴 수 있기 때문입니다.

**과금 잠금의 마지막 확인 시각은 2026-10-05 10:50:25Z입니다** — 위 세 건(`111727326817` gitleaks, `111716946817` autofix,
`111714314615` strix) 전부 `steps: 0`·러너 없음이고 annotation이 동일한 billing 문구입니다. 개시 이후 약 64시간 연속입니다.

원인은 여기서 단정하지 않습니다. 다만 조직 거버넌스 문서상 autofix 편집 흐름은 **승인된 same-repository-head PR**에 대해서만 동작합니다. 이 저장소에는 2026-08-13 이후 어떤 head에도 `APPROVED`가 없으므로(위 절), `#27`도 그 전제를 만족할 수 없습니다. 그렇다면 매일의 dispatch는 **구조적으로 no-op**이며, 남는 것은 코멘트 노이즈뿐입니다.

확인의 한계 — autofix 워크플로는 이 저장소에 caller가 없습니다. 로컬 워크플로는 `tests.yml`·`fuzz.yml`·`scorecard-analysis.yml` 셋뿐이고 `pr-review-autofix.yml` 실행 이력 조회는 404입니다. 실제 job이 "전제 미충족으로 정상 종료"인지 "실패"인지는 `.github` 쪽 실행 이력에서만 판별할 수 있습니다.

포털에서 고칠 것은 없습니다. 다만 이 노이즈가 `updated_at`을 매일 올리므로, **`#27`의 갱신 시각을 실제 진전으로 읽지 마십시오.**

**그리고 autofix는 애초에 `#27`을 고칠 수 없습니다.** `#27`의 리뷰를 전수 확인하면 3건이고 전부 `opencode-agent[bot]`입니다. 현재 head `8aad3b4`에 붙은 최신 판정(review `4935228502`, 2026-08-14)이 지목하는 실패는 다음 하나입니다.

```text
Failed checks:
- Security Scan/trivy-fs: FAILURE
```

즉 `#27`의 blocker는 **리뷰 피드백이 아니라 상속된 CVE-2026-69247**입니다. autofix는 리뷰 피드백을 반영하는 흐름이므로 고칠 대상이 존재하지 않습니다. `#27`은 다른 PR과 같은 뿌리에서 막혀 있고, CVE가 main에 올라오면 함께 풀립니다. 매일의 dispatch는 그 사실을 바꾸지 않습니다.

(참고로 `#27`의 옛 head `a45ab73`에서는 실패가 `Semgrep (multi-language SAST)`였습니다. 즉 이 PR은 blocker가 한 번 바뀌었고, 지금 것은 CVE입니다.)

#### owner가 같은 결론을 job id로 확인했습니다 (2026-09-24)

**이 절의 판단은 owner 확인으로 뒷받침됩니다.** seonghobae가 `#27`의 exact head `8aad3b4`에 fleet review를 남겼습니다([comment 5811276019](https://github.com/ContextualWisdomLab/semantic-data-portal/pull/27#issuecomment-5811276019), 2026-09-24 09:12:11Z). 요지는 이 절이 적은 것과 같고, 근거가 더 구체적입니다.

- exact-head Security Scan `31738229231`이 GREEN이 아니고, **`trivy-fs` job `94574949718`이 `requirements.txt:125`에서 실패**합니다. 원인은 protected/base가 여전히 `cryptography==49.0.0`을 고르기 때문이며 CVE-2026-69247로 보고됩니다.
- 같은 head에서 Tests·fuzz·Semgrep은 GREEN입니다. 즉 **setup-python v7 delta 자체에는 결함이 없습니다.** 실패를 setup-python 탓으로 돌리거나 waive하지 마십시오.
- `#27`은 이 리뷰와 함께 **Draft로 전환되었습니다**(이 문서가 2026-09-21에 Ready로 기록한 상태에서 바뀌었습니다). head는 여전히 `8aad3b4`입니다.

**`#27`의 수락 조건이 owner 표현으로 고정되었습니다.** `#81`(또는 검증된 successor)이 coherent lock security repair를 protected `main`에 올리고, 그 뒤 `#27` 브랜치를 **force·destructive rebase 없이** 일반 Dependabot 경로로 refresh해 새 descendant에서 exact-head 필수 check를 자연히 재실행하는 것입니다. 금지 사항도 명시되었습니다 — **Trivy 억제, finding 무시, `#81`/`#106` receipt를 이 SHA로 옮기는 것**은 모두 안 됩니다.

#### `#106`이 새로 열렸습니다 — CVE 수리가 실제로 trivy-fs를 통과한다는 첫 증거

**[`#106`](https://github.com/ContextualWisdomLab/semantic-data-portal/pull/106) `fix(deps): patch cryptography CVE-2026-69247`** (2026-09-23 09:18:52Z 생성, **Draft**, head `8bcf9b2`, base `main@e48aa13`, `requirements.txt` 한 파일 50+/50−). 이 문서의 PR 표에 없던 PR이므로 여기 기록합니다.

**중요한 것은 그 exact head의 check 결과입니다.** PR 본문이 적은 바로는 `8bcf9b2`에서 **Tests·SAST Semgrep·Security Scan·fuzz가 terminal SUCCESS**이고, CodeQL PR은 nonterminal, 독립 리뷰는 0건입니다. 즉 **이 계보에서 Security Scan이 GREEN으로 끝난 head가 처음 존재합니다.** 이 문서가 여러 곳에서 "CVE가 main에 오르면 풀린다"고 적어 온 것이 이제 추론이 아니라 관측입니다. 다만 그 receipt는 `8bcf9b2`의 것이고, 아래 이유로 **다른 head에 옮겨 쓸 수 없습니다.**

**`#106`은 부분 수리입니다.** `requirements.txt`만 재생성했고, `requirements-dev.txt`와 `requirements-test.txt`는 그 head에서 여전히 `cryptography==49.0.0`·`anyio==4.14.1`입니다. PR 본문이 스스로 이전 서술을 두 군데 정정하고 있습니다 — "모든 무관한 pin을 유지했다"와 "repository-wide Trivy repair"는 둘 다 과했다는 것입니다. 따라서 `#106`을 두 번째 dependency owner로 병합하지 말고 **canonical lane(`#81`)을 수리하십시오.**

**CVE가 하나가 아닙니다 — anyio 축이 추가됩니다.** 이 문서는 지금까지 cryptography/CVE-2026-69247만 적었습니다. `#106`의 재생성은 `anyio 4.14.1 → 4.14.2`도 함께 옮기며, 그것은 무관한 pin이 아니라 **현재 보안 수리**입니다(4.14.2가 CVE-2026-64847·CVE-2026-63349 등을 고칩니다). 열린 PR 중 [`#105`](https://github.com/ContextualWisdomLab/semantic-data-portal/pull/105) `chore(deps): bump anyio from 4.14.1 to 4.14.2`가 정확히 그 축의 Dependabot lane입니다. 즉 lock 수리는 **두 floor를 동시에** 만족해야 합니다.

**다음 canonical descendant가 만족해야 할 floor**(owner가 `#106` 본문에 적은 것):

- `cryptography >= 50.0.0` (현재 생성 후보는 `50.0.1`을 선택합니다 — 이 문서가 "목표 버전이 두 갈래(50.0.0 / 50.0.1)"라고 적어 둔 분기가 여기서 `50.0.1` 쪽으로 수렴합니다)
- resolver가 AnyIO를 고르는 곳에서 `anyio >= 4.14.2`
- 세 lock projection을 **같은 source graph에서 함께 재생성**하고, 완전한 generated hash set과 기존 lock-order/duplicate 계약을 유지

**hash를 손으로 맞추지 마십시오.** 저장소의 `uv pip compile ... --generate-hashes` 명령을 쓰고, 결과 exact head에서 install·test·security 동작을 증명해야 합니다. 이 문서의 CLAUDE.md 요약("의존성을 바꾸면 두 파일을 재생성")과 같은 규칙이며, 대상이 세 파일로 늘어난 것입니다.

### `#107`이 종료 상태에 도달했고, 실패 7건 중 이 PR의 diff에서 온 것은 0건입니다 (2026-09-30)

owner가 2026-09-28에 연 `#107`(SQL 키워드 토큰 경계 수정)의 모든 check가 끝났습니다. **success 23 / failure 7 / skipped 8 / neutral 1, pending 0.** 실패 7건을 이 head의 잡 로그로 각각 확인한 결과입니다 — 상속받은 판단을 그대로 쓰지 않고 이 head에서 다시 읽었습니다.

| 실패 check | 이 head의 로그가 말하는 원인 | owner |
| --- | --- | --- |
| `trivy-fs` | `main`의 CVE 4건(`requirements.txt`) — 위 절 | **이 저장소의 `main`** |
| `opencode-review` | `No APPROVED or CHANGES_REQUESTED ... on the current head` | `.github` |
| `CodeQL compatibility analysis (python)` | `VERDICT_STATE: pending` | `.github` |
| `CodeQL compatibility analysis (actions)` | 같은 패턴 | `.github` |
| `noema-review` | job 출력이 `transport_capacity_unavailable` | 게이트웨이 |
| `continue-noema-transport` | `TRANSPORT_HTTP_STATUS: 502` 뒤 재시도가 403 — 아래 | `.github` 토큰 범위 |
| `strix` | step 25 `Run Strix (quick)`가 25분 27초 뒤 실패 — 앞선 24 step은 전부 green, 워크플로 자체의 `Classify all-429 Strix sidecar failure`는 skipped | Strix 실행 (오류 줄 미확인) |

**즉 `#107`의 diff에서 비롯한 실패는 한 건도 없습니다.** `trivy-fs`조차 이 PR이 건드리지 않은 `main`의 `requirements.txt`를 보고 실패합니다. 올바른 소규모 보안 수정이 check 23건을 통과하고도 병합되지 못하는 상태이며, 그 이유가 전부 PR 밖에 있습니다.

**새로 확인한 결함 — noema transport의 재시도 경로 자체가 막혀 있습니다.** `continue-noema-transport`(job `109528649786`)는 502를 받은 뒤 68초 대기하고 `ContextualWisdomLab/.github`로 `repository_dispatch`를 POST하는데, 그 호출이 403으로 끊깁니다.

```
TRANSPORT_HTTP_STATUS: 502
##[notice]Noema provider capacity unavailable (http_status=502, provider_attempt_count=unknown);
         waiting 68s before same-head continuation re-dispatch 1.
gh: Resource not accessible by integration (HTTP 403)
{"message":"Resource not accessible by integration",
 "documentation_url":".../repos#create-a-repository-dispatch-event","status":"403"}
```

**502는 용량 문제이고 403은 설계 문제입니다.** 용량은 기다리면 회복될 수 있지만, 재시도를 발사할 권한이 없다면 자동 복구 경로는 한 번도 작동하지 못합니다. 포털이 고칠 수 있는 것이 아니며(중앙 `.github`의 dispatch 권한), 이 문서는 원인을 여기까지만 적습니다 — 어느 토큰에 어떤 권한을 더해야 하는지는 확인하지 않았습니다.

**`strix`는 한 칸 좁혔습니다 (2026-09-30).** 위 표에서 "확인하지 않았습니다"로 남겨 둔 칸을 job `109351047899`의 step 목록으로 다시 읽었습니다. 준비 단계 24개는 전부 success이고 — trusted source checkout, 토큰 교환, 워크스페이스 구성, `Self-test Strix required workflow contract`, 시크릿 게이트, contextual-orchestrator sidecar 프로비저닝(2분 41초), `Install Strix`까지 — 실패는 step 25 `Run Strix (quick)` 한 곳입니다(16:58:24Z → 17:23:51Z, **25분 27초**). 워크플로가 자체적으로 가진 `Classify all-429 Strix sidecar failure` 분류 step은 **skipped**이므로, 이 실패는 워크플로 자신의 판정으로도 sidecar 레이트리밋이 아닙니다. 이후 `Collect`/`Upload Strix reports`는 success이고 종료 시 python 프로세스 3개가 orphan으로 정리되었습니다.

따라서 **실패 지점은 중앙 워크플로의 설정도 게이트웨이 프로비저닝도 아니라 Strix 스캐너 자신의 실행 안**이며, 이 점에서 같은 head의 다른 실패 6건과 성질이 다릅니다. 다만 **원인 줄은 읽지 못했습니다** — 이 환경에서 로그 blob 직접 다운로드가 egress 정책으로 차단되고(`productionresultssa4.blob.core.windows.net` CONNECT 403), MCP 경유 tail은 harden-runner의 DNS 주석 덤프가 끝을 전부 차지해 step 25의 오류 줄까지 닿지 않습니다. 그러므로 owner 칸은 "Strix 실행"까지만 적고 원인은 비워 둡니다. 이 한 칸이 `#107`의 실패 7건 중 유일하게 남은 미확인입니다.


### `main`의 취약점은 넷이고, 그중 하나는 이 문서가 기록하지 않은 CRITICAL입니다 (2026-09-29)

`#107`의 `trivy-fs`(job `109353653399`)가 실패하며 찍은 목록입니다. `#107`은 `src/`와 `tests/`만 건드리는 PR이고 의존성 파일을 전혀 수정하지 않았는데도 `requirements.txt`에서 넷이 나왔습니다 — 즉 **`main`의 파일이 그대로 스캔된 것**입니다.

| 심각도 | CVE | 위치 | 패키지 |
| --- | --- | --- | --- |
| **CRITICAL (9.5)** | `CVE-2026-63374` | `requirements.txt:11` | anyio |
| HIGH (8.0) | `CVE-2026-63349` | `requirements.txt:11` | anyio |
| MEDIUM (5.5) | `CVE-2026-64847` | `requirements.txt:11` | anyio |
| HIGH (8.0) | `CVE-2026-69247` | `requirements.txt:125` | cryptography |

**이 문서를 정정합니다.** 지금까지 차단 요인을 `CVE-2026-69247`(cryptography, HIGH) 하나로 서술하고 anyio는 "`>= 4.14.2`가 필요한 축" 정도로만 적었습니다. 실제로 **가장 높은 심각도는 anyio의 `CVE-2026-63374`(CRITICAL, security-severity 9.5)이며 이 CVE 번호는 이 문서에 단 한 번도 등장하지 않았습니다.** anyio 한 pin에 CVE 세 건이 걸려 있습니다.

**상속은 추론이 아니라 워크플로 자신의 지시입니다.** 잡이 실패하며 출력한 마지막 줄이 이것입니다.

```
Remediate each finding at the shared base branch so open PRs inherit the fix.
```

스캔 설정은 `TRIVY_IGNORE_UNFIXED: true`, 심각도 `CRITICAL,HIGH,MEDIUM`입니다. 즉 **네 건 모두 수정 버전이 존재하는 findings**이고, 무시 정책으로 가려진 것이 아닙니다.

**`#81`의 수리가 이 CRITICAL까지 덮는지는 확인하지 못했습니다.** `#81`은 세 lock 모두 `anyio==4.15.1`로 올렸고 `4.14.1`보다 한참 위이므로 덮을 가능성이 높지만, 이 문서는 `4.15.1`이 `CVE-2026-63374`를 해소한다는 증거를 갖고 있지 않습니다. 확인하는 방법은 `#81` head에서 `trivy-fs`를 돌려 보는 것 하나인데, **그 check가 정확히 24시간 큐 대기 후 취소된 그 check입니다.** 저장소 최고 심각도 취약점의 해소 여부가, 판정을 낼 수 없는 것과 같은 이유로 미확인입니다.


### 위 수리가 실제로 올라왔습니다 (2026-09-27, `#81` head `e4291e89`) — 단, 판정은 아직입니다

이 절이 요구한 수리가 `#81`의 새 head로 들어왔습니다. 파일 목록과 diff를 직접 확인한 내용입니다.

| 확인 항목 | 이 절의 요구 | `e4291e89`의 실제 |
| --- | --- | --- |
| lock projection 수 | 세 파일을 같은 source graph에서 함께 재생성 | `requirements.txt`·`requirements-dev.txt`·`requirements-test.txt` 세 파일 모두 변경 |
| cryptography 하한 | `>= 50.0.0` | 세 파일 모두 `49.0.0` → **`50.0.0`** |
| AnyIO 하한 | `>= 4.14.2` | 세 파일 모두 **`4.15.1`** |
| hash 처리 | 손으로 맞추지 말 것 | generated hash 블록이 파일마다 함께 갱신됨 |
| 계약의 실행 가능성 | (요구하지 않았음) | `tests/test_dependency_locks.py` 91줄 신규 — 세 파일의 pin과 generated hash 순서를 검사 |

**세 projection이 이전에 실제로 어긋나 있었다는 점이 여기서 확인됩니다.** 변경 전 `requirements-test.txt`는 `anyio==4.14.2`(하한 위)였고 나머지 두 파일은 `anyio==4.14.1`(하한 아래)였습니다. 이 문서가 "세 파일을 함께 재생성해야 한다"고 적은 이유가 추측이 아니라 실재하는 불일치였음이 diff로 드러났습니다. 이제 세 파일이 `4.15.1`로 통일되었습니다.

**버전 분기는 `50.0.1`이 아니라 `50.0.0`으로 닫혔습니다.** 위 항목에 "생성 후보는 `50.0.1`을 선택합니다"라고 적어 두었는데, 실제로 올라온 head는 세 파일 모두 `50.0.0`입니다. 그 서술은 당시 후보 생성 결과였고 최종 선택이 아니었습니다.

**그러나 이것을 "해소됨"으로 읽지 마십시오.** `#81`은 여전히 Draft이고 `mergeable_state`는 `blocked`이며, 결정적인 check가 아직 끝나지 않았습니다 — 2026-09-28 06:5x Z 조회 시점에 `trivy-fs`·`osv-scan`·`dependency-review`·`opencode-review`·`coverage-source-tree`·`coverage-evidence`·`strix`가 모두 `queued`입니다. 실패한 check는 아직 하나도 없고, 끝난 것 중에는 Semgrep 두 건·Hypothesis·Atheris·API integration suite·CodeQL `Analyze (python)`가 success입니다. 즉 **수리는 존재하고 판정은 없습니다.** 이 문서의 "판정을 읽는 규칙" 4·6번이 그대로 적용됩니다 — queued는 통과가 아니고, 다른 check의 초록은 `trivy-fs`의 판정을 대신하지 못합니다.

**이 문서의 관측 방법이 또 한 번 새는 것을 여기서 발견했습니다.** 위 두 항목(`#106` 생성 2026-09-23, owner fleet review 2026-09-24 09:12Z)은 하루 넘게 이 세션에 보이지 않았습니다. `#27`의 코멘트 목록을 **고정된 페이지 번호**(`page=30, perPage=1`)로 폴링했기 때문입니다 — 새 코멘트가 들어오면 꼬리가 다음 페이지로 밀리므로 고정 페이지는 조용히 꼬리 추적을 멈춥니다. 앞서 기록한 검색 색인 문제에 이어 **두 번째 폴링 결함**입니다. 교훈은 같습니다: **"변화 없음"은 관측 방법이 꼬리를 실제로 보고 있을 때만 의미가 있습니다.** 페이지를 고정하지 말고 마지막 페이지를 매번 다시 찾으십시오.

**두 결함의 공통 원인을 제거하는 방법을 찾았으므로 여기에 함께 적습니다.** 둘 다 "페이지나 색인을 거쳐 목록을 읽는다"는 같은 구조에서 나왔습니다. `git ls-remote origin 'refs/pull/*/head'` 한 번이면 이 저장소의 PR head SHA 91개가 페이지네이션도 검색 색인도 거치지 않고 한 응답에 들어옵니다(2026-09-26 측정, 최대 번호 `#106`). 스냅샷을 파일로 남겨 매 주기 diff하면 새 PR 생성과 head 이동은 빠짐없이 잡힙니다. **다만 이 방법이 대체하는 것은 "무엇이 움직였는가"까지입니다.** 열린 PR과 닫힌 PR을 구분하지 않고, 코멘트·리뷰·check 결론도 여기에는 나타나지 않으므로 상태 판정에는 여전히 API 직접 조회가 필요합니다. 즉 순서를 뒤집으라는 뜻입니다 — 전수 폴링으로 변화를 찾지 말고, 값싼 전수 스냅샷으로 변화 지점을 좁힌 뒤 그 지점만 비싸게 읽으십시오. **한 가지 더 — `refs/pull/N/head`는 push를 약간 늦게 따라옵니다.** 2026-09-26 14:56Z에 `git push`가 `42a06df..16dde2a`를 보고한 직후에도 이 ref는 `42a06df`를 돌려주었고 다음 시간 조회에서 `16dde2a`로 바뀌었습니다. 자기 push의 근거는 브랜치 ref이며, 이 mirror의 낡은 값은 실패가 아니라 지연입니다.


리뷰어 구성에도 비대칭이 있습니다 — bot이 작성한 PR은 CodeRabbit이 건너뜁니다(`#102`에 `Review skipped / Bot user detected`가 그대로 게시되었습니다). 그래서 `#27` 같은 Dependabot PR과 `#102`의 리뷰어 집합은 `opencode-agent` 중심으로 좁습니다. 위 census 표의 `review 총계`를 PR 간에 그대로 비교하지 마십시오 — 작성자 종류에 따라 리뷰어 수가 구조적으로 다릅니다.

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

**초록의 두 번째 형태 — 더 속기 쉬운 쪽입니다 (2026-10-05 17:38Z).** 위 표의 stub는 3~4초라서 의심하기 쉽습니다. 그런데 **수십 초 동안
실제 job을 여러 개 성공시키고도 리뷰 job만 skip된 run**이 있습니다. 저는 이것을 하마터면 "리뷰 레인이 복구되었다"로 읽을 뻔했습니다.

`ContextualWisdomLab/.github`의 닫힌 PR 브랜치 `palette/no-ux-changes-11982953672922892196`(`prs=[]`)에서 두 run이
**`conclusion: success`**로 끝났습니다.

| run | 워크플로 | 소요 | 성공한 job | **리뷰 job** |
| --- | --- | --- | --- | --- |
| `37349903461` | Required Noema Review | 33초 | `cancel-closed-pr-runs`(`cwlab-s1-05`, 3 step) | **`noema-review` skipped** |
| `37349903181` | Required OpenCode Review | 36초 | `required-workflow-bootstrap`(9 step), `coverage-evidence`(3 step), `coverage-source-tree`(3 step) | **`opencode-review` skipped** |

두 run 모두 **판정을 생산하는 job이 `skipped`·`steps: 0`**이고, run이 초록인 것은 **리뷰가 아닌 job들이 성공했기 때문**입니다. 중앙
`.github`의 CLAUDE.md가 적은 설계 그대로입니다 — "always keep one job with no output-dependent `if:` so the run concludes `success`
rather than `skipped`". 즉 **의도된 동작이고 결함이 아닙니다.** 결함은 읽는 쪽에 생깁니다.

**그래서 규칙을 하나 더 붙입니다 — run의 `conclusion`을 리뷰 증거로 쓰지 마십시오.** 소요 시간도 근거가 아닙니다(3초 stub든 36초 run이든
마찬가지). 확인해야 하는 것은 **판정 job 자신의 `conclusion`과 `steps` 수**이며, `skipped`·`steps: 0`은 "그 리뷰는 일어나지 않았다"입니다.
그리고 이 두 run은 **닫힌 PR**(`prs=[]`)에서 나왔으므로 `cancel-closed-pr-runs` 경로였습니다 — 열린 PR의 복구와는 무관합니다.
**2026-10-05 17:38Z 시점에도 이 저장소의 리뷰 레인은 복구되지 않았습니다.**

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
5. **초록의 *이유*를 읽습니다 — 과금·자격 상태로 얻은 초록이 있습니다.** 2026-09-26 `#102` head `42a06df`의 commit status 두 건은 모두 `success`인데, `description`이 각각 `Full review skipped: trial expired and no credits remaining`(Devin Review)과 `Review skipped: bot user not eligible for review`(CodeRabbit)입니다. 앞의 것은 **체험판 만료와 크레딧 소진이 초록의 이유**입니다 — 코드에 대해 아무것도 말하지 않습니다. `state`만 읽으면 둘 다 통과로 보입니다. 이런 context가 required로 지정되면 결제 상태가 게이트를 만족시키게 됩니다.
6. **commit status 집계는 check run 결과가 아닙니다.** 같은 head에서 status 집계는 `state: success`, `total_count: 2`를 돌려주는데, 같은 시점 check run 두 건(`Hypothesis property tests`, `Atheris coverage-guided (bounded)`)은 **모두 `queued`**였습니다. 두 API는 별개 목록이므로 한쪽의 초록을 전체 CI 통과로 읽지 말고 양쪽을 따로 조회하십시오.

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

**2026-09-28 갱신 — Draft 전환 sweep이 `#62`·`#63`에서 멈추지 않았습니다.** `#82`는 2026-09-26 조회에서 `ready`였고 2026-09-28 06:41:48Z 갱신 시점에는 **Draft**입니다. 같은 기간 `#37`(head `1868e89b` → `9c2f2867`)과 `#81`(`ce40bd89` → `e4291e89`)의 head도 움직였습니다. sweep의 전체 범위는 이 문서가 측정하지 않았으므로 건수를 주장하지 않습니다 — 확인된 것은 `#62`·`#63`·`#82` 세 건이 Draft로 전환되었다는 사실입니다.

**2026-09-26 갱신 — 표본 밖 PR 두 건에서 같은 구조가 확인되고, 위 서술 하나는 좁혀야 합니다.** 저장소 owner가 `#62`·`#63`에 exact-head admission 감사를 게시하고 두 PR을 Draft로 전환했습니다(blocker로 `terminal Security Scan failure + active CHANGES_REQUESTED`를 적고, open 상태와 유효 delta·review·thread는 보존하며 Close·bypass·Force Push·synthetic evidence·review dismissal은 하지 않는다고 명시). 감사가 인용한 head는 로컬 ref 스냅샷과 일치합니다 — `#62` `8d1c6c07`, `#63` `3de25626`.

`#62`의 리뷰를 직접 열어 확인한 내용은 이 절의 결론을 표본 밖에서 재확인합니다. `CHANGES_REQUESTED` 두 건이 **같은 head(`8d1c6c07`)·같은 본문**으로 2시간 21분 간격(11:43:46Z → 14:04:47Z, 2026-08-18) 중복 게시되어 있고, 지적 항목은 역시 `1. HIGH Current-head GitHub Checks` 하나이며, 이름이 적힌 실패 check는 `Security Scan/trivy-fs`(job `94689091343`)입니다. 즉 이 문서가 "포털이 자기 저장소에서 고칠 수 있는 실패 check는 `trivy-fs` 하나"라고 적은 판단이, 당시 표본에 없던 PR에서도 같게 나옵니다.

**다만 "둘 다 같은 한 문장입니다"는 일반화하지 마십시오.** `#62`의 본문은 한 문장이 아니라 `## Findings` 절과 mermaid evidence map을 갖춘 구조적 본문입니다. 실질은 같습니다 — diff에 대한 지적은 0건이고 유일한 finding이 "실패한 required check"입니다. 정확한 일반화는 분량이 아니라 **판정의 출처**입니다: 이 `CHANGES_REQUESTED`들은 diff에서 유도된 것이 아니라 check 상태에서 유도된 것입니다. 한 문장 형태는 그 변종 중 하나일 뿐입니다.

### 실패 check의 원인을 끝까지 따라가면 포털이 소유한 것은 하나뿐입니다

각 실패 check의 잡 로그를 직접 읽은 결과입니다.

| 실패 check | 나타나는 PR | 로그가 말하는 원인 | 수리 owner |
| --- | --- | --- | --- |
| `opencode-review` | `#81` | `No APPROVED or CHANGES_REQUESTED from opencode-agent on the current head` — 검증 절반이 dispatch 절반의 판정을 기다리다 fail-closed | `.github` `#2040`/`#2051`/`#2056` |
| `CodeQL compatibility analysis` (actions·python) | `#73` | `VERDICT_STATE: pending` → `CodeQL scan dispatched. The dispatch workflow will rerun this exact failed CodeQL job after publishing its terminal verdict.` dispatch는 성공했는데 되돌아와 job을 재실행하는 wake가 오지 않습니다 | `.github` `#2040`/`#2051`/`#2056` |
| `noema-review` | `#73`, `#79` | 게이트웨이 라우팅 결함 — 아래 참조 | `contextual-orchestrator` issue `#1106` (PR `#971`은 넓은 라우팅 lane) |
| `trivy-fs` | `#32`, `#79` 외 | `[HIGH] CVE-2026-69247 requirements.txt:125 - Package: cryptography` | **이 저장소** — 단, `#73`은 자체 `50.0.1` pin으로 이미 초록입니다(아래 절). 나머지는 취약한 main을 상속 |

**2026-09-28 재확인 — 두 상류 패턴이 그날 만들어진 PR에서 그대로 재현됩니다.** owner가 2026-09-28 15:32Z에 `#107`(`fix(sdp): match forbidden SQL keywords as tokens, not substrings`)을 열었고, 네 시간 뒤 head `6ace6aff`에서 실패 세 건이 나왔습니다. 세 건 모두 이 PR의 diff와 무관하며, 잡 로그를 직접 읽어 확인했습니다.

| 실패 check | job id | 로그가 말하는 원인 | owner |
| --- | --- | --- | --- |
| `opencode-review` | `109053356706` | `No APPROVED or CHANGES_REQUESTED from opencode-agent on the current head. The dispatch workflow will rerun this failed job after publishing an authenticated exact-head verdict.` | `.github` |
| `CodeQL compatibility analysis (python)` | `109052935410` | `DISPATCH_OUTCOME: success` / `VERDICT_STATE: pending` → `CodeQL scan dispatched. The dispatch workflow will rerun this exact failed CodeQL job after publishing its terminal verdict.` | `.github` |
| `CodeQL compatibility analysis (actions)` | `109052935298` | 같은 패턴(같은 run `36444353130`) | `.github` |

**즉 2026-09-09에 기록한 두 패턴이 19일 뒤에도 살아 있습니다.** 그때는 `#81`·`#73`처럼 오래 열려 있던 PR에서 관측했으므로 "낡은 head라서 그렇다"는 설명이 가능했지만, `#107`은 당일 생성된 새 PR의 첫 head입니다. head의 나이가 원인이 아님이 이것으로 드러납니다.

`#107` 자체는 검토했고 문제를 찾지 못했습니다. `_FORBIDDEN_KEYWORD_RE`(`(?<![a-z_])(...)(?![a-z0-9_])`)를 옛 `\b...\b` 술어와 무작위 문자열 20만 건으로 대조한 결과 **옛 술어가 잡던 것을 새 술어가 놓치는 사례는 0건**이었습니다 — `validate_sql_query`에서는 같거나 더 엄격합니다. 나머지 두 호출 지점(`draft_sql`·`audit`)은 순수 substring에서 완화된 것이 맞지만, 그 완화가 허용하는 것은 `updated_at`·`union1`처럼 실제 식별자입니다. 한 가지만 적어 둡니다 — `tests/fuzz/invariants.py`가 `\b...\b`로 갱신되어 production보다 약한 술어가 되었습니다. 그래서 거짓 실패는 나지 않지만(위 20만 건이 그 증거), 이 PR이 새로 잡기로 한 `1union` 부류를 property lane이 더는 누르지 않습니다. 단위 테스트가 그 부류를 덮고 있습니다.

**2026-10-27 정정 — 위 검토는 한 방향만 재서, 제 브랜치를 겨누는 방향을 비워 뒀습니다.**
20만 건으로 측정한 것은 "*새* 술어가 *옛* 술어가 잡던 것을 놓치는가"(0건)였습니다. 그
반대 — "*옛* 술어가 *새* 술어가 잡는 것을 놓치는가" — 는 재지 않았고, 그 방향이 가리키는
것이 **이 브랜치가 출하하고 있던 술어**였습니다. 제 커밋 `314df19`이 게이트 셋을
`_matched_forbidden_keyword` 하나로 합칠 때 살아남은 술어가 `\b...\b`였으므로,
`validate_sql_query`의 맹점이 `draft_sql`·`audit`에도 퍼졌습니다 — 그 둘이 맨 substring으로
잡고 있던 `1union`·`한union` 부류가 세 게이트 전부에서 사라진 것입니다. 측정하면
`/browse/query`가 `... limit 1 union all`은 400으로 거부하고 공백 하나를 뺀
`... limit 1union all`은 **200 `SUCCEEDED`**로 통과시켰습니다. 위 단락의 "`draft_sql`·`audit`은
완화된 것이 맞지만 그 완화가 허용하는 것은 실제 식별자입니다"가 틀린 지점이 여기입니다 —
완화가 허용한 것에는 식별자만 있지 않았습니다. `#107`의 비대칭 술어를 채택해 수리했고,
oracle도 독립적으로 다시 유도했습니다. 자세한 측정·변이·남은 거짓 양성은 CHANGELOG의
"게이트 셋을 하나로 합칠 때 살아남은 술어가 더 약했습니다" 항목에 있습니다.

**읽는 규칙:** 남의 PR을 검토할 때 측정 방향이 자기 코드를 겨누지 않으면, 그 통과는
그 PR에 대한 판정일 뿐 자기 브랜치에 대한 판정이 아닙니다. 이 세션에서 같은 종류의
비대칭 — 가정이 검사보다 오래 살아남는 것 — 이 "최초 실행" 주장에서도 한 번 나왔습니다.

**그 규칙을 `#32`에 적용하자 두 번째 구멍이 나왔습니다.** `#32`(함수 양성 allow-list)도
앞서 "동작으로 덮여 있다"고 적어 둔 PR입니다. 그 PR의 적대적 corpus 27건은 이 브랜치에서
전부 거부되지만, `#32`의 doctoring 문서가 명시한 규칙 — "schema-qualified function calls are
rejected even when their final identifier resembles an allowlisted function" — 은 지키지
않고 있었습니다. `_FUNCTION_CALL`이 `(` 바로 앞 식별자 하나만 집었으므로 `evil.count(*)`가
`count`로 제시되어 **경고 0건으로 통과**했습니다. 꼬리만 읽는 allow-list는 어떤 접두사로도
우회됩니다. 수리와 변이 기록은 CHANGELOG의 "함수 allow-list를 꼬리만 읽어" 항목에 있습니다.

따라서 **소유자의 보안 PR을 "동작으로 덮여 있다"고 적어 둔 앞선 판정들은 판정이 아니라
미측정으로 읽어야 합니다.** 다섯 건을 그 방향으로 쟀습니다: `#107`·`#32`·`#35`에서
무언가가 나왔고(각각 경계 술어·한정 호출·파생 테이블), `#80`·`#51`에서는 나오지
않았습니다. **음성 결과도 기록합니다** — 재지 않은 것과 재서 안 나온 것은 다릅니다.
`#80`은 결함이 아니라 소유자의 정책 변경이고 이 브랜치가 더 엄격한 쪽이며(채택하지
않았습니다), 이 브랜치의 evidence export에는 PII가 실리지 않습니다(측정: preview는
`***`, export 본문 2,973바이트에 seed PII 0건, audit 라우트는 403). `#51` 쪽에서 제가
쓴 JWKS redirect 초안은 **이 저장소의 주석이 근거와 함께 반박했고 그 근거가 맞습니다**;
평문 `http` 허용도 `NFR-SEC-004`를 `partial`로 내린 항목에 이미 호명돼 있습니다. 자세한
측정과, 그 결정이 호명하지 않은 경계 하나(설정된 host의 open redirect)는 CHANGELOG의
"`#80`·`#51`은 구멍이 아니었습니다" 항목에 있습니다.

**`#35`는 결과의 종류가 달랐습니다 — 보안이 아니라 가용성입니다.** 적대적 관계 밀반입
19건은 이 브랜치에서 **19/19 거부**되어 allow-list 자체는 건전합니다. 그런데 `#35`가
"경고 0건이어야 한다"고 단언하는 정상 단일 소스 8건 중 **6건이 거부**됐고, 그 이유가
`unauthorized_table_reference` — 지목된 테이블이 **인가된 relation 하나뿐인** 문장에
대해 "허가되지 않은 테이블을 건드린다"는 거짓 진술이었습니다. 원인은
`_TABLE_LIST_TOKEN`이 괄호를 토큰으로 보지 않아 파생 테이블의 내부 `SELECT`가 테이블
이름 자리에 도착한 것이고, 그 자리는 스캐너의 "읽을 수 없다" 분기입니다.

**이 문서가 그 수리를 검증했다고 적어 둔 대조군 5건에 파생 테이블이 없습니다**(위
2026-10-14 항목: `FROM customer`, `AS` alias, alias 생략, 수식된 이름, self-join). 결정
자체("목록을 읽을 수 없으면 거절한다")는 기록돼 있었지만 그 **결과**는 측정되지
않았습니다. 대조군이 거부 결정의 범위를 덮지 않으면, 그 결정의 비용은 기록되지 않은
채로 남습니다.

같은 측정에서 지금 열려 있던 구멍도 하나 나왔습니다 — `SELECT * FROM crm)`은 `['crm']`로
읽혀 **통과**했습니다. 읽을 수 없는 모양에 인가 판정을 내리고 있었습니다. 수리와 변이
여섯 건은 CHANGELOG의 "파생 테이블을 쓰면" 항목에 있습니다.

**`#82`에 대한 직전 기록을 좁힙니다.** 2026-09-28 06:41Z에 Draft였던 `#82`는 같은 날 15:5x Z 조회에서 head `53805c8d`로 움직이며 다시 `ready`가 되었습니다. 즉 그 Draft는 `#62`·`#63`처럼 판정을 기다리는 보류가 아니라 작업 중 표시였습니다. Draft 상태만으로 두 종류를 구분하지 마십시오.

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

**정리하면, 포털이 자기 저장소에서 고칠 수 있는 실패 check는 `trivy-fs` 하나입니다.** **정정(2026-09-09): 그 writer가 `#81`이라는 전제는 측정과 어긋납니다** — `#73`이 `50.0.1`로 같은 CVE를 고쳐 자기 head에서 `trivy-fs`를 초록으로 만든 것이 관측되었습니다(아래 절). `#81`은 Draft이고 `50.0.0`입니다. 나머지 세 종류는 전부 `.github`와 `contextual-orchestrator`의 제어면 결함입니다. 따라서 "포털에서 할 수 있는 독립 작업"으로 `#32`·`#73`의 리뷰 지적을 해소한다는 계획은 성립하지 않습니다 — 해소할 지적이 없습니다. 큐 전체가 상류 수리에 걸려 있다는 사실을 그대로 기록해 두는 편이, 없는 포털 작업을 만들어 내는 것보다 정확합니다.

### `#73`의 포털 소유 실패는 사라졌습니다 (2026-09-09 09:2x 전수 측정)

`#73` head `1681a7f`의 check run 38건을 전부 확인했습니다. 실패는 4건이고 **`trivy-fs`는 그 안에 없습니다.**

| check | 결론 | 시각 |
| --- | --- | --- |
| `trivy-fs` | **success** | 09:15:18 |
| `strix` | **success** | 09:28:23 |
| `osv-scan`·`dependency-review`·`Semgrep`·`CodeQL Analyze`·`coverage-evidence`·fuzz 2건 | success | — |
| `opencode-review` | failure | 09:26:46 |
| `CodeQL compatibility analysis (actions)` | failure | 09:18:10 |
| `CodeQL compatibility analysis (python)` | failure | 09:20:24 |
| `noema-review` | failure | 09:27:36 |

원인은 이 PR이 스스로 CVE를 고쳤기 때문입니다. maintainer가 같은 날 [09:11 코멘트](https://github.com/ContextualWisdomLab/semantic-data-portal/pull/73#issuecomment-5599388802)에서 밝힌 대로 `1681a7f`는 `cryptography==50.0.1`을 고정하고 hash-locked 산출물 3건을 재생성했습니다.

이것이 바꾸는 것:

- 이 문서의 병합 순서 5번과 PR 표는 `#73`을 "trivy-fs inherit + strix fail"로 적어 두었습니다. **둘 다 현재 head에서 초록입니다.** 정정했습니다.
- 위 owner 표의 "포털이 고칠 수 있는 실패 check는 `trivy-fs` 하나"는 저장소 전체로는 여전히 맞습니다. `#32`·`#79` 등은 아직 취약한 main을 상속합니다. 그러나 **`#73`에서는 이미 해소되었습니다.**
- single writer 지정을 다시 봐야 합니다. `#81`은 Draft이고 `50.0.0`이며 자기 승격에 필요한 판정을 받을 수 없습니다(위 절). `#73`은 non-draft이고 `50.0.1`이며, **그 pin이 check를 실제로 초록으로 만든 것이 관측되었습니다.** 어느 PR을 CVE 수리의 writer로 삼을지는 owner 결정이지만, "`#81`이 올라야 trivy-fs가 풀린다"는 전제는 더 이상 측정과 맞지 않습니다.
- `#73`에 남은 실패 4건은 전부 `.github`·`contextual-orchestrator` 제어면 lane입니다. 포털에서 고칠 것이 없습니다.

### `#99`는 `#97`을 완전히 승계하지 않습니다 (2026-09-09 확인)

이 문서는 `#97`/`#99`를 두고 "`#99`가 `#97`의 repair successor로 보임; delta 승계 확인 전 어느 쪽도 닫지 말 것"이라고만 적어 두었습니다. 확인했습니다. **완전 승계가 아닙니다.**

두 PR의 변경 파일을 대조하면 `#99`에 없는 `#97` 파일이 정확히 하나 있습니다.

| 항목 | 값 |
| --- | --- |
| `#97`에만 있는 파일 | `tests/test_openmetadata_admission_evidence_verification.py` (+90) |
| 그 파일이 정의하는 test | `test_receipt_verification_recomputes_source_and_projection_evidence`, `test_receipt_verification_rejects_another_source_snapshot`, `test_receipt_verification_rejects_another_safe_projection` |
| `#99` 전체 diff에서 세 이름의 등장 | **3건 모두 없음** |

`#99`가 새로 더한 것도 있습니다 — `README.md`, `docs/implementation-compliance.md`, `src/sdp/openmetadata/admission_identity.py`, `tests/test_openmetadata_admission_receipt_repair.py`, `tests/test_openmetadata_receipt_assurance.py`. 즉 두 PR은 포함 관계가 아니라 **양방향으로 서로에게 없는 delta를 가집니다.**

따라서 `#97`을 superseded로 닫으면 receipt 검증 test 3건이 사라집니다. 이 저장소의 close 기준은 완전 승계이므로 **지금 상태에서 `#97`을 닫으면 안 됩니다.** 먼저 그 3건을 `#99`로 옮기거나, 다른 이름의 test가 같은 보장을 이미 덮는다는 것을 successor 쪽에서 입증해야 합니다.

한계도 적어 둡니다 — 확인한 것은 **함수 이름의 부재**입니다. 다른 이름으로 동일한 보장을 덮고 있을 가능성까지 배제하지는 못했습니다. 입증 책임은 승계를 주장하는 쪽에 있습니다.

### 이 문서의 single writer가 네 명이 되었습니다 (repair finding, 2026-09-09)

`docs/product-technical-gap-baseline.md`는 `#79`를 single writer로 두고 `#102`가 그 브랜치 위에 delta를 쌓는 구조입니다. 그런데 OpenMetadata lane의 두 PR도 같은 파일을 고칩니다.

| PR | 이 파일 변경량 |
| --- | --- |
| `#79` | single writer (원본) |
| `#102` | `#79` 브랜치 위 delta |
| `#97` | +28 / -8 |
| `#99` | **+154 / -134** |

`#99`의 변경은 절 단위 재작성 규모입니다. `#79`·`#102`와 같은 파일을 동시에 다시 쓰고 있으므로, 어느 쪽이 먼저 main에 오르든 나머지에 충돌이 남습니다. 이것은 close 사유가 아니라 **repair finding**입니다 — adapter lane의 PR이 기준선 문서를 함께 고쳐야 할 이유가 있다면 그 delta를 `#79` 쪽으로 옮기고, adapter PR은 자기 경계(`src/sdp/openmetadata/`, `docs/integrations/`)만 건드리게 하십시오.

### 상류 수리 lane은 살아 있습니다 (2026-09-09 14:52Z 확인)

이 문서가 지목한 `.github` 세 lane은 **전부 열려 있고 같은 시간대에 갱신되고 있습니다.**

| lane | 제목 | 최종 갱신 |
| --- | --- | --- |
| `.github` `#2056` | `fix(codeql): serialize exact dispatch wakeups` | 2026-09-09 14:52Z |
| `.github` `#2051` | `fix(codeql): coordinate failed-job wake once` | 2026-09-09 14:29Z |
| `.github` `#2040` | `fix(codeql): wake required jobs with the exchanged target app token` | 2026-09-09 14:09Z |

즉 "상류가 방치되어 있다"고 읽으면 안 됩니다. `.github`는 이 lane에서 계속 병합도 하고 있습니다 — `#2008`·`#2009`(2026-09-07), `#2028`(2026-09-08, `status publish 403` 시 dispatch scan을 깨끗하게 유지)까지 이미 main에 올라 있습니다.

그런데 **그 병합들이 이 저장소의 증상을 아직 없애지 못했습니다.** `#73`의 `CodeQL compatibility analysis`는 `#2028` 병합(09-08 03:07Z) 이후인 **2026-09-09 09:18Z에도 실패**했고, 같은 실행에서 `Dispatch current-head CodeQL scan`은 success였습니다. dispatch는 나가는데 실패한 job을 되돌아와 깨우는 절반이 아직 닫히지 않았다는 뜻이며, 그것이 정확히 `#2040`/`#2051`/`#2056`이 다루는 부분입니다.

포털에서 할 일은 여전히 없습니다. 이 절은 대기의 성격을 기록하기 위한 것입니다 — 이것은 방치가 아니라 진행 중인 수리이고, 우회하거나 재촉해서 해결할 대상이 아닙니다.

### `opencode-review`가 코드 지적을 내지 못한 이유가 자기 로그에 있습니다

`opencode-agent[bot]`이 `#73`에 남긴 현재-head overview(2026-09-09 09:52 갱신)는 다음을 함께 적고 있습니다.

```text
- Head SHA: 1681a7f28adc86b4aa6db48d05b20535fa5dc499
- Gate result: REQUEST_CHANGES
- Coverage gate: success
- Model pool: exhausted
- Verdict: REQUEST_CHANGES
```

`Model pool: exhausted`는 리뷰어가 **모델을 하나도 얻지 못했다**는 뜻입니다. 위에서 "현재 head `CHANGES_REQUESTED`에는 코드 지적이 없습니다"라고 기록한 현상의 원인이 이것입니다 — 지적을 생성할 모델이 없었고, 남은 결정론적 경로(실패 check 유무)만으로 판정이 나왔습니다.

조직 규칙상 이 상황의 옳은 동작은 유료 우회 없이 fail closed 하는 것이고, 실제로 그렇게 동작했습니다. 따라서 이것은 포털이 고칠 결함이 아니라 free pool 용량 lane의 증거 한 건입니다. noema의 429 deferred-route 사례(`contextual-orchestrator` `#1106`)와 같은 뿌리를 가리킵니다.

순서도 함께 기록해 둡니다. `opencode-review` job은 **09:26:46에 실패**했고, 그 판정(review `5152624078`)을 담은 overview는 **09:52에 갱신**되었습니다. 즉 현재 head에는 판정이 존재하는데, 그것을 읽어야 할 check는 판정이 도착하기 전에 이미 fail-closed로 끝나 있습니다. maintainer의 [09:28 코멘트](https://github.com/ContextualWisdomLab/semantic-data-portal/pull/73#issuecomment-5599598492)도 같은 시점을 "판정이 아직 없어 fail closed"로 기록하고 있습니다. 이 job을 다시 깨우는 것이 `.github` `#2040`/`#2051`/`#2056` lane이며, 포털에서 재실행하거나 우회하지 않습니다.

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

**이 저장소의 protected main은 2026-08-09 이후 병합이 없습니다.** **정정(2026-10-01): 이 문장은 날짜와 PR을 둘 다 틀리게 적고 있었습니다.** `main`의 tip은 `e48aa13`이고 그 커밋은 **`#34`**(`fix(sdp): unblock CI — fuzz OOM + crash-log visibility + base SAST remediation`, committer 2026-08-09T17:52:09Z)이며, 그 직전 커밋은 2026-07-13의 `#12`입니다. 즉 **`#66`은 `main`에 없습니다** — squash든 merge commit이든 `main`에 올랐다면 `main`의 로그에 나타나야 하는데 없습니다(`#83`이 `main`이 아니라 `#73`의 브랜치로 병합된 것과 같은 패턴일 수 있습니다). 그 뒤 `#83`이 2026-08-26에 병합됐지만 대상은 main이 아니라 `#73`의 브랜치였습니다. 즉 main 기준 **53일**(2026-08-09 → 2026-10-01), 열린 PR 35건, 저장소 역사 전체의 병합이 22건입니다.

**재측정(2026-09-14): 아직도 같은 커밋입니다.** `main`은 여전히 `e48aa13`이고, 2026-09-09 이후 닷새 동안 어떤 PR의 head도 움직이지 않았습니다. 유일한 변화는 `#27`이 매일 받는 autofix 코멘트뿐이며, 그것은 위 절에 적은 대로 진전이 아닙니다. 따라서 위 문장의 "23일"은 2026-09-14 기준 **28일**이었고(2026-10-01 기준으로는 **53일**이며, 기준일 자체가 2026-08-17이 아니라 2026-08-09로 정정되었습니다), 아래 절들이 23일 기준으로 적어 둔 대기 비용도 같은 비율로 읽으십시오. 열린 PR 수(36건)와 CVE 노출 기간도 함께 늘어났습니다.

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

이 문서의 병합 순서는 전 항목이 "현재 head `opencode-agent` APPROVE 수령"을 전제로 서 있습니다. 그런데 조직에서 실제로 병합되는 PR들은 그 receipt 없이 병합되고 있습니다. 즉 **이 저장소는 조직이 실무로 지키는 기준보다 엄격한 기준을 스스로에게 적용하며 53일째 대기 중**입니다.

두 가지 중 하나가 참입니다. 조직의 나머지가 게이트를 충분히 적용하지 않고 있거나, 이 저장소가 오지 않을 receipt를 기다리고 있거나. **어느 쪽이든 agent가 판단할 사안이 아닙니다.** 게이트를 낮추거나, 스스로 승인하거나, 보호 규칙을 우회하는 조치는 이 문서의 다른 모든 절과 마찬가지로 금지입니다.

사람 유지보수자에게 필요한 결정은 이것입니다.

1. `opencode-review` 현재-head 판정을 이 저장소의 실제 필수 게이트로 유지할 것인가. 유지한다면 dispatch 수리(`.github` `#2040`/`#2051`/`#2056`)가 선행 조건이며, 그때까지 큐가 멈춰 있는 것은 정상 동작입니다.
2. 유지하지 않는다면, 조직 공통 계약을 `.github`에서 명시적으로 고쳐야 합니다 — 저장소별로 다르게 적용되는 현재 상태가 아니라.
3. 그와 별개로 **`main`에 HIGH 등급 CVE-2026-69247이 53일째 남아 있다는 사실**은 위 결정과 무관하게 그 자체로 시급합니다. single writer는 `#81`입니다.

3번은 이 문서가 계속 1번 항목으로 적어 온 것과 같지만, 이제 대기 비용이 측정됩니다 — 취약한 main으로 **53일**, 그 뒤에 35건이 줄 서 있습니다. **그리고 비용의 성격이 바뀌었습니다 (2026-10-01 12:53Z).** 2026-09-30 16:52Z부터 2026-10-01 12:52Z까지 루프가 21회 발화하는 동안 `main`도 92개 PR head도 **하나도 움직이지 않았습니다.** `#28`은 여전히 `draft: true` / `mergeable_state: blocked` / head `103c9eb`이고 `updated_at`은 2026-09-30T10:42:44Z입니다. 즉 위 절의 green(trivy-fs 포함, 2026-09-30 12:43Z)은 **하루 동안 그대로 유효하면서 병합되지 않은 상태**입니다. 증거가 없어서 막힌 것이 아니라 증거가 완비된 채 멈춰 있습니다. 왜 멈춰 있는지는 단정하지 않습니다 — owner의 순서가 `#81`을 먼저 두고 있고 `#81` 자기 head의 required check 결과는 이 세션이 아직 읽지 못했습니다.

### 정정 — 깨진 runtime lock은 PR 게이트에 보이지 않습니다 (2026-09-30 07:52Z)

바로 위에서 "깨진 lock은 설치 단계에서 fail closed로 막히므로 병합 위험은 낮다"고 적었습니다. **실행 증거가 그 반대입니다.**

`#28`의 `Tests`(run `36671696817`, job `109747873606`)가 `8aefd06`에서 **success**로 끝났습니다. step 4 `Install dependencies`가 12초에 green입니다. 이유는 설치 대상이 다르기 때문입니다.

| 레인 | 설치하는 파일 | `8aefd06`의 annotated-types pin |
| --- | --- | --- |
| `tests.yml` → `Tests` | `requirements-test.txt` | `0.7.0` (정상) |
| `Dockerfile` (CI 아님) | `requirements.txt` | **`0.7.1` (존재하지 않음)** |

그리고 `main`의 저장소 로컬 워크플로는 `fuzz.yml`·`scorecard-analysis.yml`·`tests.yml` **셋뿐이며 이미지를 빌드하는 것은 하나도 없습니다.** `requirements.txt`를 `--require-hashes`로 설치하는 곳은 `Dockerfile` 19행뿐입니다.

**따라서 이 저장소의 어떤 PR check도 `requirements.txt`를 설치하지 않습니다.** 깨진 runtime lock은 게이트 전체에 보이지 않고, 깨끗해 보이는 병합을 지나 **이미지 빌드 시점에야** 드러납니다. 위의 "fail closed" 서술은 설치가 어딘가에서 일어난다는 가정 위에 있었고 그 가정이 틀렸습니다.

중앙 check가 알아챌지는 **확인하지 못했습니다.** `Security Scan`의 trivy는 `requirements.txt`를 읽지만 manifest를 파싱할 뿐 PyPI에 해석을 요청하지 않으므로, 존재하지 않는 버전은 오류가 아니라 **취약점 데이터 없음**으로 지나갈 가능성이 큽니다. 그 job은 아직 queued여서 결과를 보지 못했으므로 추정으로만 남깁니다.

부수적으로 레인 간 대기 관측이 하나 더 나왔습니다 — 이 `Tests` job은 큐 진입 05:04:01Z → 실제 시작 07:28:15Z로 **2시간 24분 14초**입니다. 위 대기 표(fuzz 레인)에는 넣지 않았습니다. 같은 저장소에서 Strix 레인 18시간 17분과 이 레인 2시간 24분이 같은 날 관측된다는 점만 적어 둡니다.

## 이 문서를 싣고 있는 `#102`가 docs-only PR이 아닙니다 (repair finding, 2026-09-30)

2026-09-30 06:08Z에 `#102`가 Draft로 내려갔고, 근거는 exact-head 감사 코멘트입니다 — head `03241c46`, 판정은 `stack depends on predecessor #79`. Close도 force push도 없었고 delta는 보존되었습니다. **이 판정은 맞습니다.** 그리고 이 문서와 이 세션이 `#102`를 여러 차례 "docs PR"이라고 적어 온 것이 틀렸습니다.

`main`(`e48aa13`) 기준 three-dot diff입니다.

| 경로 | 변화 | 출처 |
| --- | --- | --- |
| `docs/product-technical-gap-baseline.md` | +1216 (main에 없는 새 파일) | `#79` 120행 + 이 브랜치 71커밋 |
| `requirements.txt` | 94행 | **`#79`** |
| `requirements-dev.txt` | 94행 | **`#79`** |
| `requirements-test.txt` | 94행 | **`#79`** |
| `tests/test_dependency_locks.py` | +62 (새 파일) | **`#79`** |

`#79`의 head `2181681`은 이 브랜치의 **조상**이고(확인: `merge-base --is-ancestor`), 이 브랜치는 그 위에 71커밋을 더 얹어 문서를 120행에서 1216행으로 키운 것입니다. `#81`의 head `e4291e89`는 조상이 아닙니다. 즉 **`#102`를 병합하면 문서만 들어오는 것이 아니라 `#79`의 lock delta가 문서 PR의 부수효과로 함께 들어옵니다.** 감사가 막은 것이 정확히 이것입니다.

**동시에 lock의 single writer 서술도 고쳐야 합니다.** 이 문서는 cryptography lock 수리의 single writer를 `#81`이라고 반복해 적었습니다. 실제 pin은 이렇습니다.

| | cryptography | anyio |
| --- | --- | --- |
| `main` | 49.0.0 | 4.14.1 |
| `#79` | **50.0.0** | 4.14.1 |
| `#81` | **50.0.0** | **4.15.1** |
| `#102` head | 50.0.0 | 4.14.1 (`#79`에서 상속) |

`#79`가 cryptography 49 → 50의 writer이고(head 커밋 메시지도 `merge: inherit canonical cryptography security owner`), `#81`은 그 위에 anyio 4.14.1 → 4.15.1을 더한 상위집합입니다. anyio 3건 — CRITICAL `CVE-2026-63374` 포함 — 을 겨냥하는 부분은 `#81`에만 있습니다. **열린 PR 두 개가 같은 hash-pinned lock 세 파일을 쓰고 있고**, 그중 하나가 이 문서 PR 아래에 깔려 있습니다. `#81` 하나만 single writer로 적은 것은 부정확했습니다.

**이 세션은 base를 고치지 못합니다.** 처방은 `main`에서 바로 갈라져 문서 delta만 싣는 successor exact head이고, 검증은 successor와 원본의 diff로 문서 delta가 빠짐없이 옮겨졌음을 보이는 것입니다(narrowing은 delta를 자동으로 옮기지 않습니다). 그런데 successor는 **다른 브랜치로의 push**이고, 이 브랜치를 `main`으로 리셋해 문서만 다시 얹는 방법은 **force push**입니다. 두 경로 모두 이 세션의 권한 밖입니다 — 지정 브랜치는 `claude/semantic-portal-pr-merge-e5a48k`이며 다른 브랜치 push에는 명시적 허가가 필요하고, force push는 금지되어 있습니다. 그래서 `#102`는 Draft로 두고 Ready로 되돌리지 않았습니다.

**이 결함의 성질을 분명히 해 둡니다.** 이 문서는 "stale PR의 충돌 범위는 스냅샷"이나 "narrowing은 delta를 자동으로 옮기지 않는다" 같은 교훈을 남 얘기로 적어 왔는데, 이번 것은 같은 계열의 자기 결함입니다 — **자기 PR을 `main`과 한 번도 three-dot로 대조하지 않았습니다.** 위 대기 표의 표본 범위 오류와 같은 종류이고, 두 번 모두 "이미 열어 본 자리에 답이 있었는데 읽지 않았다"입니다.

## owner가 의존성 보안 스택을 세 단으로 수리했습니다 (2026-09-30 10:52Z 확인)

head 세 개가 동시에 움직였고, 확인해 보니 owner의 계획된 스택 수리입니다. 순서는 **`#81` → `#37` → `#28`**이며 세 head는 엄격한 조상 관계입니다(`merge-base --is-ancestor` 양쪽 확인).

| PR | 새 head | 커밋 | 시각(KST) |
| --- | --- | --- | --- |
| `#81` | `4f83feb` | `fix(security): complete generated dependency lock repair` | 19:26:41 |
| `#37` | `3384004` | `merge: integrate dependency security owner #81` | 19:33:40 |
| `#28` | `103c9eb` | `merge: integrate dependency security stack #37` | 19:42:13 |

### `#28`의 autofix 결함은 수리되었습니다 — 제 제안보다 낫습니다

위 절에 적은 존재하지 않는 `annotated-types==0.7.1`이 사라졌습니다. 새 head `103c9eb`는 세 공용 lock 모두 `annotated-types==0.8.0`이고, hash도 PyPI와 대조해 정확합니다 — sdist `13b2beaa…`, wheel `f072f4d8…`로 PyPI의 0.8.0 digest와 한 글자도 다르지 않습니다. **이 문서가 제안한 "0.7.0으로 한 줄 되돌리기"보다 나은 수리입니다** — 실재하는 상위 버전으로 올리면서 세 projection에 일관되게 적용했습니다. 따라서 그 조치 요청은 종결하고, 위 절은 발생한 사실의 기록으로만 남깁니다.

### `#81`의 lock 수리는 완결되었고 hash까지 맞습니다

| 패키지 | `main` | `#81` `4f83feb` |
| --- | --- | --- |
| anyio | 4.14.1 / 4.14.1 / **4.14.2** / 4.14.1 | **4.15.1** (네 projection 전부) |
| cryptography | 49.0.0 | **50.0.0** |
| pyjwt | **2.13.0** | **2.14.0** |
| annotated-types | 0.7.0 | 0.7.0 (변화 없음) |

`anyio==4.15.1`의 hash도 대조했습니다 — wheel `6152fdbb…`, sdist `9f283060…`로 PyPI와 일치합니다. `main`의 `requirements-test.txt`만 `anyio==4.14.2`였던 불일치도 여기서 해소됩니다.

### 이 문서가 lock 개수를 잘못 세고 PyJWT를 빠뜨렸습니다

이 문서는 lock projection을 **세 개**로 다뤄 왔지만 실제로는 **네 개**입니다 — `requirements.txt`, `requirements-dev.txt`, `requirements-test.txt`, 그리고 **`requirements-graph.txt`**. 넷 다 `--require-hashes`이고, `Dockerfile`은 그중 runtime과 graph 둘을 설치합니다(19–20행). `main`의 graph lock은 `anyio==4.14.1`을 그대로 들고 있었습니다.

그리고 **`main`의 세 공용 lock에 `pyjwt==2.13.0`이 있는데 이 문서는 한 번도 적지 않았습니다.** 위 CVE 4건(anyio 3건 + cryptography 1건)은 `#107`의 `trivy-fs` 출력에서 읽은 것이고, 그 출력이 취약점의 전체 목록이라고 가정한 것이 잘못이었습니다. `#81`의 문서가 PyJWT와 graph lock을 함께 적고 있고 양쪽 다 트리에서 확인됩니다. `#37`이 소유한 `pypdf==6.16.1` delta도 같은 맥락이며 `main`의 lock에는 pypdf가 없습니다.

### `docs/product-technical-gap-baseline.md`의 writer가 둘입니다 (repair finding)

**`#81`은 이 파일을 새 파일로 만듭니다** — 16행, `## Dependency security admission` 한 절입니다. 그런데 `#79`(그리고 그 위의 `#102`)도 같은 경로를 새 파일로 만듭니다 — 현재 1267행입니다. 즉 **어느 쪽이 먼저 병합되든 나머지는 add/add 충돌**입니다. 두 문서는 중복이 아닙니다: `#81`의 것이 훨씬 좁고 최신이며, 위에 적은 PyJWT·graph lock·pypdf 순서·네 lock의 hash-required dry-run 같은 사실은 **이 문서에 없던 것들**입니다.

`#81`의 acceptance evidence가 순서를 이미 정해 두었습니다 — `#81`을 먼저 넣고, `#37`·`#28`은 갱신된 head가 required Checks를 통과할 때까지 Draft로 둡니다. 그러면 `#102`는 `#81` 위로 rebase해 두 문서를 합쳐야 합니다. **이 세션은 그것을 하지 못합니다** — 다른 브랜치 push이거나 force push이기 때문입니다. 이 충돌은 `#102`의 base 의존성(`#79`)과는 별개의 두 번째 정리 항목입니다.

### 덧붙임 — 이 세션의 push 간격이 `#102`의 현재-head 증거를 지우고 있었습니다

`#102`의 fuzz 실행 세 건(`a33d563`·`b42532f` 및 그 앞)이 연달아 다음 push에 취소되었습니다. 두 사이클 push를 멈추자 `c8e083f`에서 **처음으로 완료**됐고 두 job 모두 success입니다(Hypothesis 9초, Atheris 4분 38초). 대기는 큐 진입 07:54:36Z → 시작 10:32:22Z = 2시간 37분 46초로 위 표 범위 안이므로 **행은 추가하지 않았습니다.** 남는 교훈은 분포가 아니라 운영입니다 — 매 시간 push하면 어떤 head도 현재-head 판정을 모으지 못하고, 그것은 큐가 아니라 간격이 만든 차단입니다.

## 중앙 autofix가 `#28`에 존재하지 않는 버전을 적었습니다 (repair finding, 2026-09-30)

이 세션이 이 저장소에서 처음으로 관측한 **외부 head 이동**이고, 내용이 좋지 않습니다. 2026-09-30 05:03:53Z에 `github-actions[bot]`이 `#28`(branch `codex/standards-file-ontology`)에 `8aefd06`을 push했습니다 — 메시지는 `fix(pr-28): address review feedback`, 변경은 `requirements.txt` 한 줄입니다.

```
-annotated-types==0.7.0 \
+annotated-types==0.7.1 \
     --hash=sha256:1f02e8b43a8fbbc3f3e0d4f0f4bfc8131bcb4eebe8849b8e5c773f3a1c582a53 \
     --hash=sha256:aff07c09a53a08bc8cfccb9c85b05f1aa9a2a6f23728d790723543408344ce89
```

세 가지를 확인했습니다.

| 확인 | 결과 |
| --- | --- |
| PyPI에 `annotated-types 0.7.1`이 있는가 | **없습니다.** 공개된 릴리즈는 `0.1.0`·`0.2.0`·`0.3.0`·`0.3.1`·`0.4.0`·`0.5.0`·`0.6.0`·`0.7.0`·`0.8.0` — `0.7.1`은 그 사이에 없습니다 |
| 남겨진 두 hash는 어느 버전의 것인가 | **`0.7.0`의 것입니다.** PyPI JSON의 `0.7.0` wheel `1f02e8b4…`, sdist `aff07c09…`와 한 글자도 다르지 않습니다 |
| 다른 lock projection도 같이 바뀌었는가 | **아닙니다.** 같은 head의 `requirements-dev.txt`와 `main`의 `requirements.txt`는 둘 다 `0.7.0` + 같은 hash 그대로입니다 |

그래서 결함이 둘 겹쳐 있습니다. **버전이 존재하지 않으므로** `pip install --require-hashes -r requirements.txt`는 hash 검증에 닿기도 전에 resolution에서 멈춥니다. 설령 존재했더라도 **hash가 옛 버전의 것이므로** `--require-hashes`가 다시 막습니다. 그리고 세 projection 중 하나만 손으로 고쳐졌으므로, `#81`이 수리 중인 것과 **같은 종류의 lock 불일치**가 하나 더 생겼습니다. 이 저장소의 절차는 `pyproject.toml`을 고치고 `uv pip compile --generate-hashes`로 두 파일을 **함께** 재생성하는 것인데(CLAUDE.md), 이 커밋은 한 파일의 한 줄을 직접 편집했습니다.

설치를 실제로 실행해 보지는 않았습니다 — 위 판단의 근거는 PyPI 인덱스에 그 버전이 없다는 사실과 hash 대조이며, 그 둘로 실패는 확정됩니다. **실행 증거가 아직 없는 이유도 적어 둡니다 (06:52Z 확인).** `8aefd06`의 check는 05:04:00Z에 큐에 들어간 뒤 1시간 48분째 전부 `queued`입니다 — `Tests`·`fuzz`·`Security Scan`·`SAST Semgrep`·OpenCode·Noema 모두이며, `CodeQL PR`과 merge scheduler만 skipped입니다. 즉 **아직 어떤 run도 설치를 시도하지 않았습니다.** 위 대기 절의 조건이 그대로 적용되는 상태이고, check가 비어 있는 것을 통과로도 실패로도 읽지 마십시오.

**이 bump가 무엇을 고치려던 것인지는 알 수 없습니다.** 위 절의 CVE 4건은 anyio 3건과 cryptography 1건이고 annotated-types는 거기 없습니다. 즉 보안 수리로 보기도 어렵습니다.

**조치는 한 줄 되돌리기입니다** — `0.7.1` → `0.7.0`. 그러면 파일에 이미 들어 있는 hash, 같은 head의 `requirements-dev.txt`, 그리고 `main`과 모두 바이트 단위로 맞습니다. 다만 **이 세션은 그 push를 하지 않았습니다.** 지정 브랜치가 `claude/semantic-portal-pr-merge-e5a48k`이고 다른 브랜치로의 push는 명시적 허가가 있어야 하기 때문입니다. `#28`의 head는 같은 저장소 브랜치이므로 기술적으로는 가능하지만, 권한 경계를 루프 편의로 넘기지 않습니다.

**"병합 위험은 낮다"고 적은 것은 틀렸습니다 (2026-09-30 07:52Z 정정).** 아래 절이 실행 증거로 이를 뒤집습니다. 이 결함의 비용은 지연이 아니라 **PR 게이트를 그대로 통과한다는 것**이고, 더 중요한 것은 **편집 권한이 있는 자동 수리가 존재하지 않는 의존성 버전을 만들어 냈다**는 사실 자체입니다. `.github`의 governance 서술은 결정론적 코드가 "관측 결과를 발명하지 않는다"고 적고 있는데, 이 커밋은 그 경계 밖에 있습니다. 소관은 중앙에 있습니다 — 커밋 author는 `github-actions[bot]`이고 그 head의 check를 띄운 triggering actor는 `opencode-agent[bot]`입니다. 다만 **어느 워크플로 파일이 이 커밋을 만들었는지는 확인하지 않았으므로** `pr-review-autofix.yml`이나 `scripts/ci/pr_review_fix_scheduler.py`를 범인으로 지목하지 않습니다(둘은 후보입니다). 포털이 고칠 수 있는 것은 자기 파일의 한 줄뿐입니다.

## 수리된 스택에서 `trivy-fs`가 통과했습니다 (2026-09-30 12:43Z)

이 문서가 하루 종일 열어 둔 질문 — "`#81`의 lock 수리가 실제로 취약점을 지우는가" — 에 **exact-head 증거가 나왔습니다.** `#28`의 수리된 head `103c9eb`에서 Security Scan run `36704039282`이 **success**로 끝났습니다.

| job | 결과 | 비고 |
| --- | --- | --- |
| `trivy-fs` | **success** | 스캔 12초, `Print Trivy findings that failed the gate` success, SARIF 업로드됨 |
| `osv-scan` | **success** | `Mark clean OSV SARIF as comprehensive`가 실행됨 |
| `dependency-review` | **success** | — |
| `scorecard` | **success** | — |
| `Detect changed scope` | success | gate job |
| `gitleaks` | skipped | — |

같은 head의 다른 required check도 함께 green입니다 — `Tests` success, `SAST Semgrep` success, `fuzz` success, `CodeQL PR` skipped, 그리고 **`Required Noema Review` success**입니다. `#107`에서 `transport_capacity_unavailable`로 실패했던 그 check가 여기서는 통과했다는 사실만 적고, 이유는 확인하지 않았으므로 적지 않습니다.

**주장의 범위를 정확히 해 둡니다.** 이 게이트는 `TRIVY_SEVERITY: CRITICAL,HIGH,MEDIUM` + `TRIVY_IGNORE_UNFIXED: true`로 돌므로, 통과가 뜻하는 것은 **그 head에 그 세 등급의 수정 가능한 findings가 남아 있지 않다**는 것입니다. "`CVE-2026-63374`이 anyio 4.15.1로 해소되었다"는 CVE 단위 서술로 바꾸지 마십시오 — 이 문서가 가진 것은 게이트 결과이고, pin에서 CVE 해소를 추론한 것이 아닙니다. 또한 이 green은 `#81`과 `#37`을 상속한 **`#28`의 결합 내용**에 대한 것이며, `#81`·`#37` 각자의 head에서 같은 스캔이 어떻게 나왔는지는 읽지 않았습니다.

**그래서 남은 것은 병합뿐입니다.** `main`은 여전히 `anyio==4.14.1`/`cryptography==49.0.0`/`pyjwt==2.13.0`을 들고 있고, 그것을 고치는 내용은 이제 required check를 통과한 head 위에 있습니다. 이 문서가 1번 항목으로 적어 온 "취약한 main"의 해소 경로에서 **증거 부족은 더 이상 장애물이 아닙니다.** 순서는 `#81` → `#37` → `#28`이며 `#81`의 acceptance evidence가 그렇게 정해 두었습니다.

대기도 한 줄 적어 둡니다 — `trivy-fs` job은 큐 진입 11:47:00Z → 시작 12:42:51Z로 **55분 51초**입니다. fuzz 레인이 아니므로 위 표에는 넣지 않았고, 같은 날 세 번째 한 시간 미만 관측입니다.

## `#81`의 본문이 자기 head보다 낡았습니다 (2026-09-30 13:52Z)

`#81`은 owner가 정한 병합 순서의 첫 번째이므로 그 PR 본문을 읽었습니다. 본문은 스스로를 "Current authority — 2026-09-24"로 선언하고 이렇게 적고 있습니다.

| 본문이 말하는 것 | 실제 head `4f83feb` |
| --- | --- |
| exact head `ce40bd89…` | `4f83feb959cb85a2ab61869202095cade9714644` |
| 영향 범위 = lock 3개 + `tests/test_dependency_locks.py` | **11개 파일** (lock 4개, `requirements-test.in`, `pyproject.toml`, `constraints-graph.txt`, `CHANGELOG.md`, 문서 2개, 테스트) |
| anyio 보안 하한 = **4.14.2** (CVE-2026-64847, CVE-2026-63349 인용) | **4.15.1** (하한보다 위) |
| lock projection 3개 | **4개** (graph lock 포함) |

즉 2026-09-30의 재생성이 본문에 반영되지 않았습니다. 본문 자체가 "lifecycle: Draft / needs current regeneration"이라고 적고 있으니 그 재생성이 이미 일어났다는 사실만 뒤늦은 것이고, 내용이 틀린 것은 아닙니다. **다만 이 PR의 authority 블록을 현재 상태로 읽으면 안 됩니다.**

한 가지는 방향이 다릅니다. 본문은 anyio 하한을 **4.14.2**로 잡고 그 근거로 CVE-2026-64847과 CVE-2026-63349를 듭니다. 그런데 이 문서가 `#107`의 `trivy-fs`에서 읽은 anyio 관련 findings에는 **CRITICAL `CVE-2026-63374`**도 있었고 본문은 그것을 언급하지 않습니다. 적용된 pin이 4.15.1이라 실무적으로는 덮였지만, **본문이 선언한 하한(4.14.2)만 지켰다면 그 CRITICAL이 남았을지 이 문서는 알지 못합니다.** 어느 쪽도 단정하지 않고, 하한 선언과 관측된 findings 목록이 어긋난다는 사실만 적습니다.

**`#28`의 green은 `#81`의 수락 조건을 대신하지 못합니다.** 본문의 required repair 5번은 "하나의 변하지 않은 exact head에서 frozen/hash-checked 설치, 전체 테스트, 현재 Trivy/Security, SAST, CodeQL, 저장소 required gate 전부"를 요구합니다. 위 절에 적은 green은 `#28` head `103c9eb`의 것이고 `#81` head `4f83feb`의 것이 아닙니다. `4f83feb`의 required check 결과는 이 세션이 읽지 못했습니다 — 최근 실행 목록에 나타나지 않지만, **그것을 "없다"는 증거로 쓰지 않습니다.** 같은 착오를 `#107`의 `trivy-fs`에서 한 번 했고(생성 전이었을 뿐), 영 결과는 부재의 증거가 아닙니다.

덧붙여 `103c9eb`에서 **`Strix Security Scan`도 success**입니다. `#107` `6ace6aff`에서 실패했던 그 check인데, head가 다르므로 이것이 `#107`의 실패를 설명하거나 닫지는 않습니다 — 수리된 head에서 통과한다는 사실만 추가합니다.

## dependabot `#109`은 조용한 부분 수리이고, lock의 다섯 번째 writer입니다 (repair finding, 2026-10-01)

2026-10-01 16:13:07Z에 `dependabot[bot]`이 `#109` `409ae68`을 열었습니다 — `chore(deps): bump pyjwt from 2.13.0 to 2.15.0`, base는 `main`(`e48aa13`) 직접, 4개 파일입니다.

| 파일 | `#109` | `#81` |
| --- | --- | --- |
| `pyproject.toml` | `PyJWT[crypto]==2.15.0` | — |
| `requirements-test.in` | `PyJWT[crypto]==2.15.0` | `PyJWT[crypto]==2.14.0` |
| `requirements.txt` | `pyjwt==2.15.0` | `pyjwt==2.14.0` |
| `requirements-dev.txt` | `pyjwt==2.15.0` | `pyjwt==2.14.0` |
| **`requirements-test.txt`** | **`pyjwt==2.13.0` — 손대지 않았습니다** | `pyjwt==2.14.0` |
| `requirements-graph.txt` | pyjwt 없음(`main`과 같음) | `pyjwt[crypto]==2.14.0` |

**입력은 올리고 컴파일된 lock은 올리지 않았습니다.** `requirements-test.in`은 2.15.0인데 거기서 생성되는 `requirements-test.txt`는 2.13.0 그대로입니다. 그리고 `requirements-test.txt`는 **`tests.yml`이 `--require-hashes`로 설치하는 바로 그 파일**입니다(위 절). 즉 manifest는 2.15.0을 주장하는데 테스트 레인은 취약한 2.13.0을 계속 설치합니다.

**실패하지 않는다는 점이 더 나쁩니다.** `#28`의 autofix 결함은 존재하지 않는 버전이어서 resolution에서 멈췄지만, 이쪽은 lock 내부가 정합합니다(2.13.0 + 2.13.0 hash). 그래서 설치는 성공하고 **수리가 되지 않은 사실만 조용히 남습니다.**

**그 tree에는 drift를 잡을 장치도 없습니다.** `tests/test_dependency_locks.py`는 `main`에도 `#109`에도 **없습니다** — `#79`/`#81` 계열 브랜치에만 있습니다. 즉 prod/dev/test 불일치를 deterministic RED로 만드는 가드가 정확히 그것이 필요한 PR에는 빠져 있습니다.

**그리고 같은 파일의 writer가 하나 더 늘었습니다.** `#81`은 pyjwt를 네 projection 전부 **2.14.0**으로 올리고(그 과정에서 `main`에는 없는 pyjwt를 graph lock에 추가), `#109`는 같은 파일들을 **2.15.0**으로 올립니다. 목표 버전이 다르고 범위도 다릅니다. `#28`·`#37`이 `#81`을 상속하므로 이 lock 세트를 건드리는 열린 PR은 이제 `#79`·`#81`·`#37`·`#28`·`#109`입니다.

**조치는 포털 소관이지만 이 세션 소관은 아닙니다.** 올바른 수리는 `requirements-test.txt`를 자기 `.in`에서 재생성해 네 projection을 한 버전으로 맞추는 것이고, 순서상 `#81`이 먼저 들어간 뒤 dependabot이 그 위에서 다시 열리는 편이 깔끔합니다. `#109`의 head는 dependabot 브랜치이므로 이 세션은 push하지 않았습니다.

## 같은 lock 네 파일을 쓰는 열린 PR이 일곱이 되었고 목표 버전이 서로 다릅니다 (repair finding, 2026-10-01)

2026-10-01 18:44~18:51Z에 owner가 `#82`와 `#107`의 head를 옮겼습니다 — `#82` `69a73bc`(`fix(policy): give authorized next actions in denial guidance`), `#107` `147d00d`(`fix(deps): repair advisory floors and portable hash locks`). 둘 다 lock을 건드립니다. 현재 pin을 전부 읽은 결과입니다.

| 대상 | cryptography | anyio | pyjwt |
| --- | --- | --- | --- |
| `main` | 49.0.0 | 4.14.1 (test만 4.14.2) | 2.13.0 |
| `#79` | 50.0.0 | 4.14.1 | 2.13.0 |
| `#81` | 50.0.0 | **4.15.1** (네 projection) | 2.14.0 |
| `#37`·`#28` | `#81` 상속 | `#81` 상속 | `#81` 상속 |
| `#82` | **50.0.1** | 4.14.2 | **2.13.0** (그대로) |
| `#107` | **50.0.2** | 4.15.1 — **단 test만 4.14.2** | **2.15.0** |
| `#109` | — | — | 2.15.0 — **단 test만 2.13.0** |

**cryptography 목표가 네 가지(49.0.0·50.0.0·50.0.1·50.0.2), pyjwt 목표가 세 가지(2.13.0·2.14.0·2.15.0)입니다.** 그리고 `#107`·`#109` 두 PR은 자기 안에서도 `requirements-test.txt`만 뒤처져 있습니다 — `#107`의 커밋 메시지가 `repair ... portable hash locks`인데 test lock의 anyio는 4.14.2로 남아 있고, `#109`는 pyjwt를 test lock에서만 2.13.0으로 남겨 둡니다.

**`#82`는 pyjwt를 건드리지 않습니다.** cryptography를 50.0.1로, anyio를 4.14.2로 올리면서 pyjwt는 `main`의 2.13.0 그대로입니다. 즉 세 패키지 중 하나만 미해결로 남는 조합이 또 하나 생겼습니다.

**새 add/add 충돌도 하나 생겼습니다.** `tests/test_dependency_advisories.py`는 `main`에 없고 `#82`(52행, blob `b0127a93`)와 `#107`(69행, blob `bce98356`)이 **각자 새 파일로 만듭니다.** 내용이 다르므로 둘 중 하나가 먼저 병합되면 나머지는 충돌합니다. 이 문서가 기록한 `docs/product-technical-gap-baseline.md`의 add/add(`#81` vs `#79`/`#102`)와 같은 모양이고, 이제 두 건입니다.

**실무적으로 남는 것.** 이 네 lock 파일의 writer는 `#79`·`#81`·`#37`·`#28`·`#82`·`#107`·`#109` **일곱**입니다. 어느 하나가 먼저 들어가면 나머지 여섯은 재생성이 필요하고, 재생성 없이 병합되면 위 표의 불일치 중 하나가 `main`에 실립니다. 이 문서는 어느 조합이 옳은지 판정하지 않습니다 — 그것은 owner의 순서 결정입니다. 다만 **`#81` 하나를 single writer로 적어 온 서술은 이제 세 번째로 부정확해졌고**, 실제 상태는 "하나의 writer"가 아니라 "조정되지 않은 일곱"입니다.

### 정정 — `#82`·`#107`이 수렴했고, "test lock이 뒤처졌다"는 제 판단은 과했습니다 (2026-10-01 19:52Z)

한 시간 전에 적은 표가 이미 낡았습니다. owner가 2026-10-02 04:29Z(KST)에 두 PR을 다시 밀었고 **pin이 동일해졌습니다** — `#82` `93321a9`(`fix(deps): clear advisories and preserve Python 3.10 hash closure`), `#107` `b802cfb`(`fix(deps): restore Python 3.10 closure across every lock`). 둘 다 네 projection에서 cryptography **50.0.2**, pyjwt **2.15.0**, anyio는 runtime/dev/graph **4.15.1** · test **4.14.2**입니다.

따라서 목표 버전의 분기가 줄었습니다 — cryptography는 넷에서 **셋**으로(`main` 49.0.0 / `#79`·`#81`·`#37`·`#28` 50.0.0 / `#82`·`#107` 50.0.2), pyjwt도 셋(`main`·`#79` 2.13.0 / `#81`·`#37`·`#28` 2.14.0 / `#82`·`#107`·`#109` 2.15.0)입니다. **그리고 `#82`가 pyjwt를 2.13.0으로 남겨 둔다고 적은 것도 이 head에서는 해소되었습니다.**

**더 중요한 것은 제 판단의 정정입니다.** 저는 test lock의 anyio 4.14.2를 두 번 "뒤처짐"·"drift"로 적었고, `#107`의 커밋 메시지가 자기 말과 어긋난다고까지 썼습니다. 그렇게 단정할 근거가 없었습니다.

| 확인 | 결과 |
| --- | --- |
| anyio 4.15.1이 Python 3.10을 지원하는가 | **지원합니다.** PyPI의 `requires_python`은 4.14.1·4.14.2·4.15.0·4.15.1 모두 `>=3.10`입니다. 즉 "Python 3.10 하한" 자체가 4.14.2를 설명하지는 못합니다 |
| 두 lock의 입력이 같은가 | **다릅니다.** `requirements.txt`는 `pyproject.toml`에서, `requirements-test.txt`는 `requirements-test.in`에서 `--universal --python-version 3.12`로 컴파일됩니다(헤더에 기록되어 있음) |
| test lock에서 anyio는 어디서 오는가 | **전이 의존뿐입니다** — `# via httpx, starlette`. 반면 `requirements.txt`에서는 `# via semantic-data-portal (pyproject.toml), starlette`로 **직접 의존**입니다 |

즉 test lock에는 anyio에 대한 직접 제약이 없고, 그 값은 그 입력 집합에서 httpx·starlette가 허용하는 해에 따라 결정됩니다. **같은 숫자가 아닌 것이 곧 재생성 누락이라는 뜻은 아닙니다.** 어느 쪽인지는 이 문서가 확인하지 못했으므로 "drift"라는 단정을 철회하고 "입력이 다르므로 값이 다를 수 있다"까지만 남깁니다. 판별하려면 `requirements-test.in`과 그 전이 제약을 그 명령으로 다시 컴파일해 결과가 4.14.2인지 보아야 하며, 이 세션은 그것을 하지 않았습니다.

같은 조심이 `#109`에도 적용됩니다 — 거기서는 `requirements-test.in`이 pyjwt를 **직접** 2.15.0으로 올렸는데 `requirements-test.txt`가 2.13.0이므로, 그쪽은 입력과 출력의 직접 불일치입니다. anyio 쪽과 성질이 다르니 두 사례를 한 묶음으로 읽지 마십시오.

## `#110`이 CI를 self-hosted로 옮기려 합니다 — 그리고 제 앞선 기록 두 건을 정정합니다 (2026-10-03)

2026-10-03 12:44:23 KST에 `#110` `f035b10`이 열렸습니다 — `ci: stage isolated self-hosted routing for all workflow jobs`, 18개 파일입니다. **`#107`의 후손입니다**(`merge-base --is-ancestor` 확인), 즉 경쟁하는 writer가 아니라 같은 레인의 다음 단계입니다.

변경의 핵심은 네 product CI job의 실행 위치입니다.

```
-    runs-on: ubuntu-latest
+    runs-on: [self-hosted, linux, x64, cwlab-ci-isolated]
```

`fuzz.yml`의 두 job, `tests.yml`, `scorecard-analysis.yml` 전부이고, `tests/test_self_hosted_ci_contract.py`가 `runs-on:` 선언이 **정확히 네 개**이며 모두 그 라벨이어야 한다고 못 박습니다.

**이 문서가 3주간 21회 측정한 큐 대기와 직접 닿는 변경입니다.** 다만 **지금 이것이 대기를 줄인다고 읽으면 안 됩니다.** `docs/self-hosted-ci-migration.md`가 스스로 적고 있습니다 — "This is a staged source change, not verified runtime activation. **No registered runner carried `cwlab-ci-isolated` in the preparation API read.**" 즉 라벨을 받을 러너가 아직 없으므로, 이 상태로 병합되면 네 job은 **영구히 큐에 남습니다.** 문서는 그래서 isolated capacity와 canary 증거가 생길 때까지 Draft를 유지하라고 하고, 유혹적인 우회를 명시적으로 금지합니다 — "do not add this label to an existing privileged host solely to release the queue." 순서도 적혀 있습니다: `#82`와 `#107`이 병합되기 전에 issue108을 시작하지 말 것.

### 정정 1 — `tests/test_dependency_advisories.py`의 add/add 충돌은 해소되었습니다

어제 적은 "`#82`(52행, blob `b0127a93`)와 `#107`(69행, blob `bce98356`)이 서로 다른 내용으로 같은 파일을 만든다"는 관측은 **더 이상 유효하지 않습니다.** 지금 세 PR이 같은 blob을 들고 있습니다.

| PR | blob | 행 |
| --- | --- | --- |
| `#82` | `c15f19f6` | 108 |
| `#107` | `c15f19f6` | 108 |
| `#110` | `c15f19f6` | 108 |

**이것은 owner가 수렴시킨 것이고, 제 쪽 실수도 하나 있습니다.** `#82`는 그 뒤 `93321a9`로 head가 움직였는데 저는 그 시점에 pin만 다시 읽고 advisories 파일은 옛 head의 값을 그대로 들고 있었습니다. 이 문서가 다른 PR에 대해 반복해 적어 온 규칙 — head가 움직이면 다시 읽어라 — 을 제 기록에 적용하지 않은 것입니다. add/add 충돌 건수는 둘에서 **하나**로 줄었고, 남은 것은 `docs/product-technical-gap-baseline.md`(`#81` 16행 vs `#79`/`#102`)입니다.

### 정정 2 — lock writer는 여덟이 아니라 그대로 일곱입니다

`#110`도 네 lock을 모두 건드리지만 pin은 `#107`과 동일하고(cryptography 50.0.2, pyjwt 2.15.0, anyio 4.15.1 / test 4.14.2) 그 조상입니다. 따라서 **독립 writer가 늘어난 것이 아닙니다.** 앞 절의 일곱(`#79`·`#81`·`#37`·`#28`·`#82`·`#107`·`#109`)에 `#110`을 더해 여덟이라고 세지 마십시오 — `#110`은 `#107` 계보 안입니다.

## 큐 대기의 끝은 러너 부족이 아니라 계정 과금 잠금이었습니다 (2026-10-03 03:54Z)

이 문서가 3주간 21회 측정한 큐 대기에 종착지가 생겼습니다. **GitHub-hosted job은 더 이상 대기하지 않고 즉시 거절됩니다.** 2026-10-03 03:54:33Z에 이 PR의 head `fa957b4`로 생성된 `fuzz` run `37094749626`의 두 job이 GitHub 자신의 annotation으로 이유를 적었습니다.

```
The job was not started because your account is locked due to a billing issue.
```

| 측정 | 값 |
| --- | --- |
| job `111122277682` / `111122277879` | `created_at` = `started_at` = 03:54:34Z, `completed_at` = 03:54:37Z |
| 실행된 step | **0개** (`steps: []`) |
| 배정된 러너 | 없음 (`runner_name` 빈 문자열) |
| 라벨 | `ubuntu-latest` |
| annotation level | `failure`, 위 문장 그대로 |

**한 번 재실행했고 동일하게 재현되었습니다.** `rerun-failed-jobs`로 attempt 2를 띄웠더니 job `111123086499`/`111123086695`가 03:59:29Z에 생성·시작되어 03:59:33Z에 같은 annotation으로 끝났습니다 — step 0, 러너 없음. 일시적 장애가 아니라 03:59:33Z 시점에 활성인 상태입니다.

### 이것은 이 PR의 결함도, 이 저장소의 결함도 아닙니다

같은 문장이 다른 저장소에서도 나옵니다. `noema`의 job `111063753435`(2026-10-02T22:58:50Z)과 중앙 `.github`의 job `111123489781`(2026-10-03T04:01:47Z)이 글자 그대로 같은 annotation을 들고 있습니다. 계정 단위이므로 어떤 PR의 diff로도 고칠 수 없습니다.

시작 시점은 두 관측 사이로 좁혀집니다. 마지막으로 **실제 배정된** hosted job은 `contextual-orchestrator` `110974297309`입니다 — 러너 `GitHub Actions 1002242315`를 받아 18:31:59Z에 시작해 step 16개를 수행하고 18:44:07Z에 끝났습니다. 처음 **즉시 거절된** job은 같은 저장소 `111056099003`으로, 22:30:34Z에 생성·시작되어 step 0·러너 없음으로 22:30:38Z에 끝났습니다. 즉 잠금은 **2026-10-02 18:44Z ~ 22:30Z**(KST 10-03 03:44~07:30) 사이에 걸렸습니다. 그 사이에 생성된 run이 없어 더 좁힐 수는 없습니다.

### 레인이 셋이고, 셋의 운명이 다릅니다

15분 안에 같은 조직에서 측정한 세 가지입니다. **이 구분이 조치를 정합니다.**

| 레인 (labels) | 배정 | 결과 | 증거 |
| --- | --- | --- | --- |
| `ubuntu-latest` / `ubuntu-24.04` (GitHub-hosted) | 배정 전 거절, 러너 없음, step 0 | 3~5초 `failure` + 과금 annotation | sdp `111122277682`, `.github` `111123489781` |

**그 "3~5초"는 job 수준에서 재야 합니다 — run 수준 시간은 이 판정에 쓸 수 없습니다.**
2026-10-27 14:5xZ에 같은 브랜치의 네 head를 run 수준으로 보면
`updated_at - run_started_at`이 4초·80초·114초·176초·234초·587초로 흩어져 있어, 긴 쪽은
**CI가 실제로 돌다가 실패한 것처럼 읽힙니다.** job 수준으로 같은 run들을 다시 재면
`started_at - completed_at`이 전부 **2~5초**이고 job은 하나, step은 0입니다
(`40522135278/122251758683` 2초, `40517828809/122235956769` 3초,
`40526477858` 4초). run 수준의 차이는 큐·정리 시간이고 실행 시간이 아닙니다. 이 구분을
놓치면 존재하지 않는 테스트 실패를 쫓게 되므로, 이 표의 판정 기준은 **job 수준**입니다.
| `[self-hosted, linux, x64]`, `+cwlab-control` | **약 3초에 배정** | 정상 실행 (step 9·6·26개 수행) | `.github` `111121081820`(`cwlab-s1-05`), `111121081851`(`cwlab-s1-07`), `111121123986`(`cwlab-s1-02`) |
| `[self-hosted, linux, x64, cwlab-ci-isolated]` | 거절되지 않음, 러너 없음 | **무한 큐** | `.github` `111121080117`(03:46:56Z 큐), sdp `#110` `111121092591`(03:47:01Z 큐) |

두 가지를 분명히 해야 합니다. **첫째, 중앙 리뷰 레인은 살아 있습니다.** `cwlab-s1-01/02/05/07`이 `[self-hosted, linux, x64]`를 받아 지금도 OpenCode·Noema 판정을 수행합니다. 막힌 것은 리뷰가 아니라 product CI입니다. **둘째, `semantic-data-portal`의 product CI job 네 개는 전부 `ubuntu-latest`입니다**(`fuzz.yml` 2개, `tests.yml`, `scorecard-analysis.yml`). 따라서 **이 저장소의 어떤 head도 지금은 product check를 green으로 만들 수 없습니다.** 이 문서가 PR별 조치에 적어 온 "체크 재검증"은 전부 현재 실행 불가이며, 그것은 해당 PR의 결함이 아닙니다.

### `#110`의 평가를 고칩니다 — staged가 아니라 복구 경로이고, 러너 라벨 하나가 비어 있습니다

앞 절에서 `#110`을 "지금 대기를 줄인다고 읽으면 안 되는 staged 변경"으로 적었습니다. 그 경고는 유효하지만 **이유가 바뀌었습니다.** hosted 레인이 닫힌 지금 `#110`의 방향(self-hosted로 옮기기)은 이 저장소 CI를 되살릴 수 있는 경로이고, 막는 것은 단 하나 — `cwlab-ci-isolated`를 가진 러너가 없다는 사실입니다. 그리고 이 공백은 이 저장소만의 것이 아닙니다: **중앙 `.github` 자신이 PR 2565에서 같은 함정에 빠져 있습니다**(Security Scan run `37094344655`, 03:46:56Z 이후 큐 유지).

살아 있는 `[self-hosted, linux, x64]` 풀이 바로 옆에 있으므로 **가장 유혹적인 우회가 지금 가장 위험합니다.** `docs/self-hosted-ci-migration.md`가 그것을 정확히 금지합니다 — "do not add this label to an existing privileged host solely to release the queue." 큐를 풀기 위해 `cwlab-s1-0x`에 `cwlab-ci-isolated`를 붙이면 격리 전제가 사라집니다. 올바른 조치는 **격리된 capacity를 새로 등록해 그 라벨을 주는 것**이거나 **과금 잠금을 해제해 hosted 레인을 되살리는 것**이며, 둘 중 하나 없이는 어떤 PR도 병합 증거를 만들 수 없습니다.

### 21행 dwell 표를 다시 읽는 방법 (가설로 표시합니다)

hosted job이 수 시간 큐에 머무르다 결국 하드 거절로 끝났고, 같은 시각 self-hosted job은 3초에 배정됩니다. 이 대비는 **"대기의 원인이 조직의 러너 용량이 아니라 hosted 자격의 저하였다"**는 읽기를 강하게 지지합니다. 다만 **확인된 관측이 아니라 가설로 표시합니다.** 잠금은 마지막 dwell 측정 이후에 걸렸고, 그 이전 대기가 같은 과금 조건의 전단계였는지는 증명되지 않았습니다. 확인에 필요한 것은 계정의 billing 상태이며 이 세션에서는 읽을 수 없습니다 — `orgs/ContextualWisdomLab/settings/billing/actions`와 사용자 billing endpoint 모두 proxy가 403으로 막고(저장소 범위 바인딩), `repos/.../actions/runners`도 403입니다. 따라서 러너 인벤토리는 job 레코드에 남은 이름·라벨로만 관측했습니다.

**조치는 owner만 할 수 있습니다.** (1) Actions를 소유한 계정의 과금 잠금 해제, 또는 (2) `cwlab-ci-isolated` 격리 러너 등록 후 `#110` 계열 병합. 그 전까지 이 문서의 모든 "check 재검증" 행은 보류이고, 거절된 check를 PR의 품질 신호로 읽어서는 안 됩니다.

**잠금의 마지막 확인 시각을 갱신합니다 — 2026-10-05 05:52:48Z.** `ContextualWisdomLab/.github` PR `#2581`(head `9e482e14`)의 `Security Scan` 실행 `37269721729`에서 `gitleaks (secret scan)`과 `Detect changed scope` 두 job이 각각 2초에 끝났고, check-run annotation이 `The job was not started because your account is locked due to a billing issue.`를 그대로 담고 있습니다. 같은 배치에서 self-hosted `Required PR Review Merge Scheduler`는 성공했습니다. 즉 2026-10-02 18:44Z~22:30Z 사이 개시 이후 **약 59시간 연속 활성**이며, 세 레인 구분(hosted 거절 / self-hosted 정상 / `cwlab-ci-isolated` 무한 대기)도 그대로입니다. **지속 시간은 근거가 아닙니다** — 이 행도 annotation을 읽어 확인했습니다. 이 문서에서 2초~6초 hosted 실패를 과금 잠금으로 읽을 때는 항상 annotation을 확인하십시오.

### 정정 — self-hosted 레인은 "정상"이 아닙니다. 두 번째 독립 블로커가 있습니다 (2026-10-05 07:00Z)

**이 문서가 여러 곳에서 "self-hosted 레인은 정상"이라고 적은 것은 틀렸습니다.** 그 레인은 **실행은 되지만 artifact를 올리는 job을 끝내지 못합니다.**
`ContextualWisdomLab/.github`의 `Required Noema Review` 실행 `37275376360`에서 `noema-review` job(`111651200610`)이 self-hosted
러너 `cwlab-s1-06`에 배정되어 **28개 step을 모두 수행**한 뒤 340초 지점에서 실패했고, annotation은 과금 잠금이 아니라 이것입니다.

```
Failed to CreateArtifact: Artifact storage quota has been hit. Unable to upload any new artifacts.
Usage is recalculated every 6-12 hours.
```

**일회성이 아닙니다.** 같은 annotation을 다섯 개 실행에서 확인했습니다 — `37141225499`(10-03 17:38Z, `cwlab-s1-06`),
`37174635139`(10-04 03:38Z, `cwlab-s1-02`), `37203661799`(10-04 12:53Z, `cwlab-s1-02`), `37246380405`(10-05 00:09Z, `cwlab-s1-02`),
`37271919729`(10-05 06:20Z, `cwlab-s1-02`). 전부 28 step 수행 후 artifact 업로드에서 실패했습니다. 즉 **최소 10-03 17:38Z부터 약 37시간
연속**이고, 이것은 과금 잠금(10-02 18:44~22:30Z 개시)과 **구간이 겹치지만 원인이 다른 별개의 account 수준 블로커**입니다.

**그래서 레인 그림을 이렇게 고쳐 읽으십시오.**

| 레인 | 배정 | 실행 | artifact 업로드 |
| --- | --- | --- | --- |
| `ubuntu-latest` / `ubuntu-24.04` | **거절**(과금 잠금) | 없음 | 해당 없음 |
| `[self-hosted, linux, x64]` + `cwlab-control` | 약 3초에 배정 | **정상** | **실패**(저장 용량 초과) |
| `+cwlab-ci-isolated` | 무한 대기 | 없음 | 해당 없음 |

**지속 시간 함정이 반대 방향으로도 성립합니다.** 이 문서는 "2~6초 hosted 실패를 과금 잠금으로 단정하지 말고 annotation을 읽으라"고
적어 왔습니다. 이번 사례는 **긴 지속 시간도 같은 함정**임을 보여 줍니다 — `#82`의 `noema-review` 실패는 `HTTP Error 400 … duration=362.7s`
(provider 쪽 원인)였고, 위 `37275376360`은 **363초**입니다. 지속 시간이 사실상 같은데 원인은 전혀 다릅니다. 긴 실행이라서 "진짜 리뷰가
돌다가 모델 문제로 실패했다"고 읽으면 틀립니다.

**이것이 병합 순서에 미치는 영향 — 과금 잠금 해제만으로는 `noema-review`가 녹색이 되지 않을 가능성이 큽니다.** 이 문서의 3번 권고
(해제 후 조합 G 병합)는 리뷰 레인의 유일한 블로커가 과금 잠금이라는 전제에 서 있었습니다. 그 전제는 더 이상 유지되지 않습니다.
**다만 범위를 정확히 적습니다** — 위 다섯 건은 모두 `.github` 저장소 자신의 noema 실행입니다. artifact 저장 용량은 account/org 수준
자원이므로 semantic-data-portal의 `pull_request_target` noema 실행도 같은 벽에 부딪힐 것이라는 **강한 예상**이지만, 지금 그 실행을
재시도할 수단이 없으므로 **확인된 관측이 아니라 예상으로 표시합니다.** 해제 후 가장 먼저 할 일은 `#82`의 `noema-review` 재실행이고,
그 결과가 HTTP 400인지 artifact quota인지가 다음 조치를 가릅니다.

**owner 조치가 하나 늘었습니다.** (1) 과금 잠금 해제, (2) `cwlab-ci-isolated` 격리 러너 등록, 그리고 **(3) Actions artifact 저장 용량
확보**(오래된 artifact 삭제 또는 한도 상향). (3)은 즉시 반영되지 않습니다 — annotation 자체가 `Usage is recalculated every 6-12 hours`라고
적고 있으므로, 삭제 후에도 수 시간 뒤에야 업로드가 복구됩니다. 해제 작업을 계획할 때 이 지연을 앞에 두십시오.

**artifact 벽은 noema 하나가 아니라 OpenCode 리뷰 레인도 막고 있습니다 — 인과 사슬을 확인했습니다 (2026-10-05 23:08Z).**
`.github`의 `opencode-review-dispatch.yml` 실행 `37386742068`(`event: repository_dispatch`, branch `main`)에서 job
`validate-pr-metadata`(`112021736216`)가 self-hosted 러너 **`cwlab-s1-04`**(지금까지 보지 못한 호스트)에서 **7개 step을 수행한 뒤**
같은 annotation으로 실패했습니다 — `Failed to CreateArtifact: Artifact storage quota has been hit.` 그 결과 같은 run의
`coverage-evidence`와 **`opencode-review`가 둘 다 `skipped`·`steps: 0`**이 되었습니다.

**사슬은 이렇습니다 — artifact 용량 초과 → `validate-pr-metadata` 실패 → `opencode-review` skip → 현재-head OpenCode 판정 없음.**
이것은 `#107`의 기록된 블로커(`Fail closed without a current-head OpenCode verdict`)와 **형태가 일치합니다.** 이 문서는 그 블로커의
원인을 적지 못한 상태로 남겨 두었고, `opencode-review`가 self-hosted라서 "지금도 실행된다"고 적었습니다. **그 서술은 불충분했습니다** —
리뷰 job 자체는 실행 가능하더라도 그 앞의 metadata 검증이 artifact 업로드에서 죽으면 리뷰는 시작되지 않습니다.

**범위를 좁혀 적습니다.** 이 실행은 `.github`의 `repository_dispatch`이고 `prs=[]`이므로 **어느 저장소의 PR을 위해 dispatch된 것인지
확인하지 못했습니다.** 따라서 "`#107`의 OpenCode 블로커 원인이 artifact 용량이다"는 것은 **같은 중앙 워크플로의 같은 실패 지점에서
나오는 강한 기계적 추론이지 확인된 인과가 아닙니다.** 확인에는 `#107`의 head에서 dispatch를 재실행해 그 run의
`validate-pr-metadata`를 읽는 것이 필요하고, 지금은 수단이 없습니다.

**그리고 artifact 블로커의 구간이 늘었습니다 — 최소 2026-10-03 17:38Z부터 2026-10-05 23:08:42Z까지 약 53시간 30분 연속입니다.**
annotation이 `Usage is recalculated every 6-12 hours`라고 적는데 그 창이 네 번 이상 지나갔음에도 복구되지 않았습니다. 즉 **재계산을
기다리는 것으로는 풀리지 않고, 실제로 artifact를 삭제하거나 한도를 올려야 합니다.** 그리고 이 둘을 합치면 **중앙 리뷰 레인(noema와
OpenCode) 양쪽이 artifact 벽에 막혀 있으므로, 과금 잠금만 해제해도 판정은 생산되지 않을 가능성이 높습니다.** owner 조치 (3)은
선택이 아니라 (2)와 함께 필요한 항목입니다.

**그리고 self-hosted 레인에는 artifact 말고도 세 번째 실패 유형이 있습니다 — target별 dispatch 권한 (2026-10-05 11:25Z).**
`ContextualWisdomLab/.github`의 `hourly-review-repair.yml` 실행 `37302726382`에서 `dispatch-review-repair (quarantine)` job
(`111739122778`, `cwlab-s1-05`, 10 step)이 8번째 step `Dispatch review-feedback autofix`에서 실패했고 annotation은 이것입니다.

```
PR_REVIEW_MERGE_TOKEN, OPENCODE_APPROVE_TOKEN, or the exchanged OpenCode app token is required;
github.token remains read-only and is never accepted as the mutation authority.
```

**그러나 같은 run의 3번째 step `Exchange OpenCode app token for scheduler mutations`는 성공했습니다.** 교환이 성공했는데 dispatch가
권한 부재를 보고하므로 둘 중 하나는 실제 권한 상태를 반영하지 않습니다 — 어느 쪽인지는 확인하지 않았습니다.

**세운 가설 하나는 증거로 기각했습니다.** 처음에는 "앞선 성공들이 할 일이 없어서 성공한 공허한 성공"이라고 의심했습니다. 틀렸습니다 —
`37295716153`(10:18Z, target `originweave`)과 `37286291164`(08:51Z, target `psychometrics-commons`)는 둘 다 같은
`dispatch-review-repair` job을 10 step 수행하고 **성공**했습니다. 즉 이 실패는 레인 전체의 성질이 아니라 **target별**입니다. 같은
self-hosted 풀, 같은 워크플로, 같은 step 수인데 target이 `quarantine`일 때만 권한이 없습니다.

**범위를 좁혀 적습니다.** 이것은 `ContextualWisdomLab/.github`가 소유한 제어면 결함이고 **대상 target은 semantic-data-portal이 아닙니다.**
이 저장소의 병합 블로커 목록에 추가되지 않습니다. 이 문서에 남기는 이유는 단 하나 — 위에서 고친 레인 모델("self-hosted는 실행은 되지만
artifact 업로드에서 실패")이 여전히 부족하다는 것입니다. **artifact를 올리지 않는 self-hosted job도 target별 권한 때문에 실패할 수
있습니다.** 그러므로 self-hosted 성공 하나를 "레인이 건강하다"의 근거로 쓰지 마십시오 — 그 성공은 자기 target에 대해서만 말합니다.
이 결함을 고치는 것은 `.github`의 일이며 이 세션은 손대지 않았습니다.

### 잠금은 PR 게이트만이 아니라 main의 예정된 보안 증거 생산도 멈춥니다 (2026-10-03 06:44Z)

`scorecard-analysis.yml`의 주간 예정 실행이 처음으로 거절되었습니다. run `37104019217`은 `event: schedule`, 브랜치 `main`(`e48aa13c`)이고 job `111148946931`이 06:44:15Z에 생성·시작되어 06:44:18Z에 끝났습니다 — step 0, 러너 없음, **같은 과금 annotation**. 이 워크플로의 예정 실행 14건 중 앞선 13건은 전부 `success`였습니다.

즉 이 저장소는 지금 **PR 게이트도, main의 예정된 스캔도** 돌지 않습니다. `fuzz.yml`은 `0 3 * * *`(야간), `scorecard-analysis.yml`은 `30 1 * * 6`(주간) cron을 갖고 있고 둘 다 `ubuntu-latest`입니다. OpenSSF Scorecard 점수는 이번 주부터 갱신이 멈춥니다 — 구매자가 보는 외부 신호입니다.

**그리고 이 사태를 알려 줄 감시 장치 자체가 같은 잠금에 걸려 있습니다 (2026-10-05 06:51Z).** `ContextualWisdomLab/.github`의
`.github/workflows/actions-queue-health.yml`은 `event: schedule`로 돌는 큐 건강 감시 워크플로이고, 그 job 이름은 문자 그대로
`Collect exact-head queue evidence`입니다. run `37274546730`의 job `111648593914`이 06:51:25Z에 시작해 4초에 끝났습니다 — step 0,
러너 없음, annotation은 같은 `The job was not started because your account is locked due to a billing issue.`입니다. 같은 분
`Organization Commercial Readiness`의 `coordinate` job(`111648346386`)도 같은 이유로 거절됐습니다.

**이것이 이 사태의 가장 불편한 성질입니다.** 과금 잠금을 자동으로 알려 줄 장치는 hosted 러너에서 도는 감시 워크플로인데, 과금 잠금이
hosted 러너를 거절하므로 **감시가 먼저 죽습니다.** 즉 owner는 자기 모니터링으로부터 이 조건에 대한 신호를 받지 못합니다 —
조직의 commercial-readiness 리포팅도 같이 멈춰 있습니다. 이 저장소의 체크 실패만 보고 "PR 쪽 문제"로 좁혀 읽으면 안 되는 이유이고,
해제 뒤에는 감시 워크플로를 self-hosted 레인으로 옮기는 것(또는 잠금에도 살아남는 외부 알림 경로를 두는 것)을 별도로 검토해야 하는
이유입니다. 그 설계 판단은 `.github`의 소유이며 이 저장소에서 바꿀 것이 아닙니다.

### 예정 실행은 잠금 이전에도 몇 시간씩 늦게 생성되고 있었습니다 (가설의 두 번째 신호)

cron 시각과 실제 run 생성 시각을 대조했습니다. **수 주에 걸쳐 일관되게 늦습니다.**

| 워크플로 | cron (UTC) | 최근 예정 run 생성 시각 | 지연 |
| --- | --- | --- | --- |
| `fuzz.yml` | `0 3 * * *` | 10-02 09:03, 10-01 09:27, 09-30 09:02, 09-29 09:07, 09-28 08:59, 09-27 08:35 | **+5h35m ~ +6h27m** |
| `scorecard-analysis.yml` | `30 1 * * 6` | 10-03 06:44, 09-26 06:17, 09-19 06:09, 09-12 06:03, 09-05 05:58 | **+4h28m ~ +5h14m** |

이것은 큐 대기(배정 지연)와 다른 층입니다 — **run 자체가 늦게 만들어집니다.** 앞 절의 "hosted 자격 저하" 가설에 독립적인 두 번째 신호이지만, **같은 자료가 그 가설의 단순한 형태를 약화시키기도 합니다.** 예정 `fuzz` run의 run 길이(생성→종료, 대기와 실행을 합친 값)는 09-27 86,658초(24.07시간), 09-28 78,608초, 09-29 27,973초, 09-30 8,621초, 10-01 1,245초, 10-02 1,260초입니다. 즉 **수 시간 대기는 10-01에 이미 정상(약 21분)으로 회복했고, 하드 잠금은 그로부터 이틀 뒤 10-02 18:44Z에 왔습니다.** 따라서 "서서히 나빠져 잠금에 이르렀다"고 읽으면 틀립니다 — 저하 → 회복 → 하드 잠금의 순서이고, 지속되는 신호는 run 생성 지연 쪽입니다.

**오늘 야간 `fuzz` 예정 실행은 06:52Z 기준 아직 생성되지 않았고, "누락"으로 적지 않았습니다** — 지연 창 안이었기 때문입니다. **08:52Z에 해소되었습니다.** run `37110204132`(`event: schedule`, main `e48aa13c`)이 **08:35:12Z에 생성**되었습니다 — cron 03:00 대비 **+5h35m**으로, 위 표의 측정 범위(+5h35m ~ +6h27m) 하단에 정확히 들어갑니다. 그리고 두 job(`111166453163`·`111166453347`)은 08:35:12Z 생성·시작 → 08:35:15Z 종료, step 0, 러너 없음, 같은 과금 annotation으로 거절되었습니다. 즉 예정 실행은 사라진 것이 아니라 **늦게 생성되어 거절**됩니다 — 야간 fuzz도 이제 증거를 만들지 못합니다.

### 거절된 두 체크를 로컬에서 CI와 같은 방식으로 재현했습니다 — 내용은 깨끗합니다 (2026-10-03 07:5xZ)

과금 잠금은 체크를 **실패로 기록**하지만 그 실패는 코드에 대해 아무것도 말하지 않습니다. 그 공백을 메우기 위해 거절된 두 job을 **CI의 설치 명령과 인터프리터를 그대로 써서** 로컬에서 돌렸습니다. head는 `2bdd3c6`입니다.

재현 조건은 워크플로 파일에서 그대로 옮겼습니다 — Python 3.12, `python -m pip install --require-hashes -r requirements-test.txt`(`tests.yml`·`fuzz.yml` 공통), Atheris job은 추가로 `fuzz-requirements.txt`, 실행은 `PYTHONPATH=src`(Atheris는 `src:.`), `FUZZ_SECONDS=60`(CI의 PR 예산).

| 체크 | CI에서 | 로컬 재현 결과 |
| --- | --- | --- |
| `Tests` (API integration suite) | Draft라 생성되지 않음 | **258 passed, 8 skipped** / exit 0 |
| `Hypothesis property tests` | **과금 거절**(step 0) | **10 passed** / exit 0 |
| `Atheris coverage-guided (bounded)` | **과금 거절**(step 0) | **4 harness 전부 61초 완주, exit 0, reproducer 0건** |

설치된 pin도 이 브랜치의 test lock과 일치했습니다 — cryptography 50.0.0, anyio 4.14.2, pyjwt 2.13.0, hypothesis 6.156.6.

Atheris 실행량은 harness별로 다음과 같습니다. `crash-*`·`oom-*`·`timeout-*` 파일은 하나도 생성되지 않았고 작업 트리도 깨끗했습니다(로그에서 `crash`에 걸리는 네 줄은 libFuzzer의 무해한 `__sanitizer_acquire_crash_state` 경고입니다).

| harness | 실행 횟수 (61초) |
| --- | --- |
| `fuzz_draft_sql` | 2,276,110 |
| `fuzz_execute_query` | 584,996 |
| `fuzz_resolve_terms` | 307,010 |
| `fuzz_search_catalog` | 136,200 |

8건 skip은 전부 `tests/test_integration_age.py`의 `SDP_DATABASE_DSN not set`입니다 — CI 러너에도 DSN이 없으므로 녹색이던 시절에도 같은 8건이 skip되었습니다.

**이것이 무엇을 말하고 무엇을 말하지 않는지 적습니다.** 말하는 것: 지금 PR에 붙어 있는 두 `failure`는 **코드 결함의 신호가 아니며**, 잠금이 품질 문제를 가리고 있는 것이 아닙니다. 말하지 않는 것: **로컬 통과는 병합 증거가 아닙니다.** GitHub 기록에 check run이 없고 formal approval도 없으며, `merge_approval_block_reason`은 현재-head 독립 승인과 체크 결과를 모두 요구합니다. 또한 재현은 설치 명령과 인터프리터만 같고 러너 이미지는 다릅니다(위 sanitizer 경고가 그 차이의 흔적입니다). Atheris 예산도 PR용 60초이며 야간 300초가 아닙니다. 그리고 이 결과는 head `2bdd3c6` 한 지점에 대한 것이고, 다른 PR의 head에 대해서는 아무 말도 하지 않습니다.

## 열린 PR을 전수 세어 보니 lock writer는 일곱이 아니라 스물여섯입니다 (repair finding, 2026-10-03 05:53Z)

**먼저 제 방법의 결함을 적습니다.** 이 세션은 `git ls-remote origin 'refs/pull/*/head'` 스냅샷을 매 주기 비교해 **움직인 head만** 추적했습니다. 그 probe는 **한 번도 움직이지 않은 PR을 보지 못합니다.** 아래 26건 중 19건이 세션 내내 head가 고정이었고, 그래서 diff에 한 번도 나타나지 않았습니다. 열린 PR 42건을 전수 측정한 결과 lock writer 수가 제가 적어 온 일곱이 아니라 **스물여섯**이었습니다.

측정은 `git diff --name-only origin/main...refs/pull/N/head`를 42건 전수에 돌려 네 lock 파일(`requirements.txt`, `-dev`, `-test`, `-graph`) 중 무엇을 쓰는지 센 것입니다(three-dot, `main` 팁 `e48aa13`).

| 쓰는 lock 파일 수 | PR | 건수 |
| --- | --- | --- |
| 네 개 전부 | `#28` `#37` `#81` `#82` `#88` `#107` `#110` | 7 |
| 세 개 (`run`·`dev`·`test`) | `#35` `#51` `#57` `#58` `#59` `#61` `#73` `#79` `#102` | 9 |
| 두 개 (`run`·`dev`) | `#67` `#68` `#69` `#70` `#105` `#109` | 6 |
| 두 개 (`dev`·`test`) | `#62` | 1 |
| 한 개 | `#63`(`graph`) `#71`(`test`) `#106`(`run`) | 3 |

**앞 절의 "일곱"은 수가 아니라 집합이 틀렸습니다.** 제 목록(`#79`·`#81`·`#37`·`#28`·`#82`·`#107`·`#109`)에는 네 파일을 다 쓰는 `#88`·`#110`이 빠져 있고, 더 적게 쓰는 `#79`·`#109`가 들어 있었습니다. 그리고 **`#88`·`#105`·`#106`은 census에 아예 없었습니다.**

### 세 패키지 pin 조합이 열 가지입니다

`cryptography` / `anyio` / `pyjwt`를 runtime lock(`requirements.txt`)과 test lock(`requirements-test.txt`)에서 각각 읽어 동일 조합끼리 묶었습니다. extra 표기(`pyjwt[crypto]`)까지 읽도록 패턴을 고친 뒤의 값입니다.

| 조합 | runtime (crypto / anyio / pyjwt) | test (crypto / anyio / pyjwt) | PR |
| --- | --- | --- | --- |
| main | 49.0.0 / 4.14.1 / 2.13.0 | 49.0.0 / 4.14.2 / 2.13.0 | `main` (`e48aa13`) |
| A | 50.0.0 / 4.15.1 / 2.14.0 | 50.0.0 / 4.15.1 / 2.14.0 | `#28` `#37` `#81` |
| B | 50.0.0 / 4.14.1 / 2.13.0 | 50.0.0 / 4.14.2 / 2.13.0 | `#35` `#58` `#59` `#61` `#79` `#102` |
| C | 50.0.0 / **4.14.2** / 2.13.0 | 50.0.0 / **4.14.1** / 2.13.0 | `#51` |
| D | 50.0.0 / 4.14.1 / 2.13.0 | 50.0.0 / **4.14.1** / 2.13.0 | `#57` |
| E | 49.0.0 / 4.14.1 / 2.13.0 | 49.0.0 / 4.14.2 / 2.13.0 | `#62` `#63` `#67` `#68` `#69` `#70` `#71` |
| F | 50.0.1 / 4.14.1 / 2.13.0 | 50.0.1 / 4.14.2 / 2.13.0 | `#73` `#88` |
| G | 50.0.2 / 4.15.1 / 2.15.0 | 50.0.2 / 4.14.2 / 2.15.0 | `#82` `#107` `#110` |
| H | 49.0.0 / **4.14.2** / 2.13.0 | 49.0.0 / 4.14.2 / 2.13.0 | `#105` |
| I | **50.0.1** / 4.14.2 / 2.13.0 | **49.0.0** / 4.14.2 / 2.13.0 | `#106` |
| J | 49.0.0 / 4.14.1 / **2.15.0** | 49.0.0 / 4.14.2 / **2.13.0** | `#109` |

조합 E의 여섯 값은 **main과 동일합니다.** 즉 그 일곱은 lock 파일은 건드리지만 이 세 패키지의 버전은 바꾸지 않습니다(다른 패키지 줄을 씁니다). 단 `#71`은 버전은 같고 요구 표기가 `pyjwt[crypto]`로 달라집니다 — 아래 정정 절에서 따로 다룹니다. 따라서 세 패키지를 두고 실제로 경합하는 PR은 26건이 아니라 **19건**입니다. `cryptography` 목표는 넷입니다 — **49.0.0(9건, main과 동일하므로 CVE-2026-69247 미수정)**, 50.0.0(11건), 50.0.1(3건), 50.0.2(3건).

### 신규 결함 1 — `#106`은 제목이 약속한 수리를 절반만 합니다

`#106`의 제목은 `fix(deps): patch cryptography CVE-2026-69247`입니다. 그런데 runtime lock만 50.0.1로 올리고 **test lock은 49.0.0 그대로 둡니다**(조합 I). `requirements.txt` 한 파일만 쓰는 유일한 PR이기도 합니다. 이것은 `#109`에 대해 이미 기록한 결함군과 동일합니다 — `#109`는 runtime pyjwt를 2.15.0으로 올리고 test lock을 2.13.0에 남깁니다(조합 J). **같은 결함이 두 PR에 독립적으로 있습니다.** `tests.yml`이 설치하는 것은 `requirements-test.txt`이므로, 두 PR 모두 "수리됐다"는 신호를 게이트에서 받으면서 test 경로에는 낡은 pin을 남깁니다.

### 신규 결함 2 — `#51`·`#57`은 test lock의 `anyio`를 main보다 내립니다

main은 runtime 4.14.1 / test 4.14.2입니다. `#57`은 test를 **4.14.1로 내리고**(조합 D), `#51`은 runtime 4.14.2 / test 4.14.1로 **main의 관계를 뒤집습니다**(조합 C). 앞서 이 문서는 "두 lock은 입력이 다르므로 값이 달라도 정당할 수 있다"고 정정한 바 있습니다 — 그 정정은 유효합니다. 여기서 지적하는 것은 값의 불일치가 아니라 **방향**입니다: 두 PR은 main이 이미 갖고 있는 test pin보다 낮은 값을 싣습니다.

### 정정 — `#71`에 대한 첫 측정은 제 스크립트 결함이었습니다

첫 census에서 `#71`의 test lock에 `pyjwt`가 없다고 나왔습니다. **사실이 아닙니다.** 실제 값은 `pyjwt[crypto]==2.13.0`이고 제 정규식이 extra 표기를 읽지 못한 것입니다. 발표 전에 확인해 고쳤습니다. 다만 그 과정에서 실제 사실 하나가 드러났습니다 — `#71`의 제목은 `hypothesis` 범프인데, test lock에서 `pyjwt`를 `pyjwt[crypto]`로 바꾸고 658행에서 733행으로 재컴파일합니다(+151/−76). 제목이 알리지 않는 범위입니다.

### PyPI 교차검증 — 이번에는 조작된 버전이 없습니다

핀된 버전이 실재하는지 PyPI에서 확인했습니다. `cryptography` 50.0.0·50.0.1·50.0.2, `anyio` 4.14.1·4.14.2·4.15.1, `pyjwt` 2.14.0·2.15.0 전부 실재합니다 — `#28`의 autofix가 적었던 존재하지 않는 `annotated-types==0.7.1` 같은 사례는 없습니다. 최신값은 `cryptography` **50.0.2**, `anyio` **4.15.1**, `pyjwt` **2.15.1**입니다.

**따라서 single writer 후보는 조합 G(`#82`·`#107`·`#110`)입니다.** 세 pin 중 `cryptography`와 `anyio`가 최신이고 `pyjwt`만 한 단계(2.15.0 vs 2.15.1) 뒤입니다. 다만 **50.0.1·50.0.2가 50.0.0 위에 어떤 보안 수정을 더 담는지는 이 측정으로 확인되지 않았습니다.** 확인에 쓸 저장소 Dependabot alert은 `403 Resource not accessible by integration`으로 읽을 수 없었습니다. 즉 "G가 가장 높다"는 것은 버전 순서의 사실이고, "G만이 CVE를 닫는다"는 주장은 하지 않습니다.

### 정정 — 위 "신규 결함" 두 건 중 하나는 결함이 아니고, `#71`에 대한 제 의심은 틀렸습니다 (2026-10-03 09:5xZ)

앞 절을 쓴 뒤 세 PR의 **본문·커밋·전체 diff를 직접 읽었고**, 제 기록 세 곳을 고칩니다. 앞 절은 lock 파일의 pin 값만 보고 쓴 것이었습니다.

**정정 1 — `#106`을 결함으로 적은 것은 부당합니다.** 관측 자체(runtime lock 50.0.1 / test lock 49.0.0)는 맞습니다. 그러나 `#106`은 **스스로 그 한계를 선언하고 있습니다.** 본문에 이렇게 적혀 있습니다 — "lifecycle: Draft / **partial generated-lock candidate / do not merge independently**", 그리고 "canonical repository-wide cryptography owner: `#81`". 즉 부분 수리임을 밝히고 단독 병합을 금지하며 정식 owner까지 지목합니다. 바꾸는 파일도 `requirements.txt` 하나뿐입니다(50+/50−). 커밋은 둘(`8424e57` cryptography, `8bcf9b2` AnyIO)이고 diff는 anyio 4.14.1→4.14.2, cryptography 49.0.0→50.0.1입니다. **"제목이 약속한 수리를 절반만 한다"는 제 표현을 철회합니다** — 제목이 두 번째 커밋(AnyIO)을 반영하지 못해 낡은 것은 사실이지만, 그것은 결함이 아니라 라벨 지연입니다.

**정정 2 — `#109`은 반대로 더 날카롭게 적어야 합니다.** `#109`는 **Draft가 아니고**(병합 가능한 상태로 제시됨) dependabot 본문은 릴리즈 노트 덤프이며 **test lock에 대한 언급이 없습니다.** 바꾸는 파일은 넷 — `pyproject.toml`, `requirements.txt`, `requirements-dev.txt`, 그리고 **`requirements-test.in`**(입력 파일을 `PyJWT[crypto]==2.15.0`으로 올림)입니다. 그런데 **컴파일된 `requirements-test.txt`는 손대지 않아 `pyjwt==2.13.0`에 남아 있습니다.** 즉 이 PR의 test lock은 **자기 자신이 선언한 입력과 모순**합니다 — 누가 `.in`에서 다시 컴파일하면 2.15.0이 나오는데, CI(`tests.yml`)가 설치하는 것은 2.13.0입니다. `#106`과 `#109`를 "같은 결함군"으로 묶은 것은 과했습니다: 모양은 비슷하지만 `#106`은 한계를 문서화하고 단독 병합을 막았고, `#109`는 그러지 않은 채 non-draft입니다.

**정정 3 — `#71`에 대한 제 의심을 철회합니다.** 앞 절에서 "제목은 hypothesis 범프인데 test lock의 pyjwt를 `pyjwt[crypto]`로 바꾸고 658→733행 재컴파일한다 — 제목이 알리지 않는 범위"라고 적었습니다. **확인해 보니 `#71`은 제목 그대로의 일을 합니다.**

| 확인 항목 | 결과 |
| --- | --- |
| hypothesis pin | main `6.156.6` → `#71` **`6.165.8`** (제목과 일치) |
| 바꾸는 파일 | `requirements-test.txt` **한 개** |
| compile 명령 | main과 **동일**(`uv pip compile --generate-hashes --universal --python-version 3.12 requirements-test.in`) |
| `cryptography` 존재 | `#71`에도 `49.0.0` **그대로 있음** |
| 패키지 집합 차이 | `-colorama` `-tzdata` `+exceptiongroup` `+tomli` (마커 차이) |

`pyjwt[crypto]`·`psycopg[binary]` 형태는 **main의 `requirements-test.in`이 이미 그렇게 선언**하고 있고(`PyJWT[crypto]==2.13.0`, `psycopg[binary]==3.3.4`), 같은 명령의 출력이 한쪽은 extra를 인라인으로, 한쪽은 분리해 적은 것입니다 — **uv 버전 차이로 생긴 표기 차이**이며 의존성이 사라지거나 추가된 것이 아닙니다. 행 수 증가도 그 표기와 마커 네 건의 결과입니다.

**교훈을 적어 둡니다.** 앞 절은 lock 파일의 **값**만 읽고 썼습니다. 값은 의도를 말하지 않습니다 — PR 본문의 lifecycle 선언, 커밋 분할, 바꾸는 파일의 범위, 그리고 lock의 **입력 파일**(`.in`)까지 읽어야 "부분 수리"와 "선언된 부분 수리"를 구별할 수 있습니다. 이 문서가 다른 PR에 대해 반복해 적어 온 "head가 움직이면 다시 읽어라"의 자매 규칙입니다: **값이 같아 보이면 의도를 읽어라.**

## 단일 writer 후보 `#107`을 끝까지 검증했습니다 — 막는 것은 product CI가 아니라 리뷰 레인입니다 (2026-10-03 09:5xZ)

앞 절은 "조합 G(`#82`·`#107`·`#110`)가 single writer 후보"라고 버전 순서만 근거로 적었습니다. 이번에는 **`#107` head `742e7a7e`를 실행해서** 확인했습니다 — 로컬 CI 동등 재현과 GitHub가 그 head에 남긴 40건의 check run 양쪽입니다.

### 로컬 CI 동등 재현 (`#107` 자신의 test lock으로 설치)

설치된 pin은 cryptography **50.0.2**, pyjwt **2.15.0**, anyio 4.14.2, hypothesis 6.156.6입니다.

| 체크 | 로컬 결과 |
| --- | --- |
| `Tests` (API integration suite) | **819 passed, 8 skipped** / exit 0 |
| `Hypothesis property tests` | **10 passed** / exit 0 |
| `Atheris coverage-guided (bounded)` | **4 harness 전부 61초 완주, exit 0, reproducer 0건** (draft_sql 2,308,139 / execute_query 767,719 / resolve_terms 276,368 / search_catalog 138,117 runs) |

**819라는 수를 분해해 둡니다** — `#102` 쪽 258건에서 늘어난 561건은 `#107`이 추가한 두 파일의 파라미터화입니다: `tests/fuzz/test_execute_query_oracle.py` **528건**, `tests/test_dependency_advisories.py` **31건**(lock 4종 × 패키지 × python 3.10/3.12). 258 + 528 + 31 = 817, 기존 파일에 추가된 2건을 더해 819로 맞습니다. 274행 추가가 561 테스트가 된 이유를 세어 확인한 것입니다.

**이 로컬 결과는 GitHub 자신의 기록과 일치합니다.** 같은 head `742e7a7e`에서 `API integration suite`·`Hypothesis property tests`·`Atheris coverage-guided (bounded)` 셋 모두 CI가 `success`로 기록해 두었습니다(잠금 이전 2026-10-02 05:48 실행). 서로 독립적인 두 경로가 같은 답을 냈습니다.

### 그 head의 40개 check run을 읽으면 막는 것이 분명합니다

| 구분 | check |
| --- | --- |
| **녹색 (product CI)** | `API integration suite`, `Hypothesis property tests`, `Atheris coverage-guided (bounded)` |
| **녹색 (보안·증거)** | `trivy-fs`, `osv-scan`, `osv-scanner`, `dependency-review`, `Trivy`, `Semgrep (multi-language SAST)`, `Semgrep OSS`, `CodeQL`, `Analyze (python)`, `Analyze (actions)`, `scorecard`, `coverage-evidence`, `coverage-source-tree` |
| **실패** | `opencode-review`, `noema-review`, `continue-noema-transport`, `CodeQL compatibility analysis (python)`, `CodeQL compatibility analysis (actions)` |
| **취소/중립** | `strix`(cancelled), `Scorecard`(neutral) |

`mergeable_state`는 `blocked`이고 non-draft입니다. **즉 `#107`을 막는 것은 테스트도 보안 스캔도 아니라 리뷰 레인입니다.**

`opencode-review`의 실패 지점은 단계 이름이 그대로 말해 줍니다. job `110723606649`(러너 `cwlab-s1-05`)의 4단계 중 2단계 `Request current-head OpenCode review execution`은 **success**이고, 3단계 **`Fail closed without a current-head OpenCode verdict`**가 failure입니다(15초). 즉 dispatch는 나갔고 **현재-head 판정이 끝내 생기지 않아** 설계대로 fail closed한 것입니다 — 코드 결함이 아닙니다. 중앙 `.github`의 `opencode-review.yml` 511행에서 그 단계 정의를 확인했습니다.

### 새 구조적 사실 — 리뷰 레인이 러너 종류로 갈립니다

| 리뷰 워크플로 | 러너 | 잠금 중 운명 |
| --- | --- | --- |
| `opencode-review` | **self-hosted** (`cwlab-s1-01`/`-05`/`-07`, `[self-hosted, linux, x64]`) | **실행됨.** 단 현재-head 판정이 없어 fail closed |
| `noema-review`, `continue-noema-transport` | **GitHub-hosted** (`ubuntu-24.04`, `GitHub Actions 10022405xx`) | **시작 자체가 불가.** 과금 거절 대상 |

`noema-review`의 본 job은 잠금 이전에 57분 46초(28단계) 돌고 실패했습니다. 지금은 그 재시도조차 배정 전에 거절됩니다. 따라서 **`noema-review`를 필수로 요구하는 PR은 과금 잠금이 풀리기 전까지 구조적으로 녹색이 될 수 없습니다** — 리뷰 레인이 전부 살아 있다고 읽으면 틀립니다. 앞 절에서 "중앙 리뷰 레인은 살아 있습니다"라고 쓴 것은 `.github`에서 관측한 self-hosted job들에 근거한 것이었고, 이 저장소의 `noema-review`는 hosted이므로 **그 문장은 워크플로별로 제한해 읽어야 합니다.**

### 한계

로컬 통과는 병합 증거가 아닙니다 — GitHub 기록상 판정도 승인도 생기지 않습니다. 재현은 설치 명령과 인터프리터만 CI와 같고 러너 이미지는 다르며, Atheris 예산은 PR용 60초입니다. 그리고 이 절은 **`CodeQL compatibility analysis` 두 건과 `strix` 취소의 원인을 규명하지 않았습니다** — 로컬에서 재현할 수 없는 게이트이고, job 로그는 이 세션에서 받을 수 없습니다(`gh`가 blob 호스트 리다이렉트를 거부하고, 해당 호스트는 egress 차단입니다). 즉 "`#107`은 product CI가 깨끗하다"까지가 증명된 범위이고, "병합 가능하다"는 주장은 하지 않습니다.

### `#107`을 막는 네 가지를 전부 규명했습니다 — 코드 결함은 하나도 없습니다 (2026-10-03 10:5xZ)

앞 절은 `CodeQL compatibility analysis` 두 건과 `strix` 취소의 원인을 "규명하지 못했다"고 적어 두었습니다. **check run의 annotation으로 넷 모두 밝혀졌습니다.** job 로그는 여전히 받을 수 없지만(blob 호스트 리다이렉트 거부 + egress 차단) annotation은 API로 읽힙니다.

| 막는 것 | 원인 (annotation 원문 근거) | 러너 |
| --- | --- | --- |
| `opencode-review` | 2단계 dispatch는 success, 3단계 **`Fail closed without a current-head OpenCode verdict`**가 failure — 판정이 생기지 않아 설계대로 닫힘 | **self-hosted** |
| `noema-review` · `continue-noema-transport` | **"Noema gateway transport failed: HTTPError: HTTP Error 429: Too Many Requests; caller attempts=1, duration=2615.5s, phase=response_error, served_model=`google/gemma-4-31b-it:free`, outcome=provider_capacity_unavailable"** | GitHub-hosted |
| `CodeQL compatibility analysis (python)` · `(actions)` | **"CodeQL scan dispatched. The dispatch workflow will rerun this exact failed CodeQL job after publishing its terminal verdict."** — 실패가 설계이고 재실행이 와야 닫히는데 그 재실행이 오지 않았습니다 | GitHub-hosted |
| `strix` | job `110723570305`이 05:48:38Z→11:48:55Z, **21,617초(6시간 17초)** 뒤 cancelled. GitHub의 job 최대 실행시간 21,600초(360분)를 17초 넘긴 값입니다 | GitHub-hosted |

네 가지 모두 **인프라·오케스트레이션 사정이고 코드 결함이 아닙니다.** 특히 둘은 이 저장소가 소유하지 않은 원인입니다 — noema의 429는 무료 모델 풀(`orchestrator/free`) 용량 소진이고, 이는 "capability가 없으면 유료 우회 없이 fail closed"라는 정책이 그대로 작동한 결과입니다. CodeQL 호환 분석은 **일부러 실패하도록 설계된 자리표시자**이며 dispatch가 terminal 판정을 발행한 뒤 같은 job을 재실행해 닫아야 합니다. 같은 head에서 `Dispatch current-head CodeQL scan`과 `CodeQL`·`Analyze (python)`·`Analyze (actions)`는 모두 `success`이므로 **스캔은 돌았고 닫는 재실행만 오지 않았습니다.**

**그리고 과금 잠금이 이 셋을 얼어붙게 합니다.** 넷 중 **셋이 GitHub-hosted**이므로 지금은 재시도 자체가 배정 전에 거절됩니다. 즉 `#107`의 남은 블로커는 "원인을 알지만 잠금이 풀리기 전에는 손댈 수 없는" 상태입니다. self-hosted인 `opencode-review`만 지금도 실행되지만, 현재-head 판정을 발행하는 경로가 복구되지 않는 한 같은 자리에서 다시 fail closed합니다.

부수적으로 중앙 워크플로의 유지보수 항목 하나를 기록해 둡니다(이 저장소 소유가 아님): noema 리뷰 job의 annotation에 `actions/setup-node@49933ea5288caeca8642d1e84afbd3f7d6820020`가 Node.js 20을 타깃하여 Node.js 24로 강제 실행된다는 deprecation 경고가 남아 있습니다.

## `#104` 하나는 이미 전부 녹색입니다 — 막는 것은 승인 한 건뿐입니다 (2026-10-03 11:5xZ)

53일 동안 아무것도 병합되지 않은 이 저장소에서, **열린 PR 42건 중 한 건은 자기 head에서 모든 체크가 끝나 있습니다.**

| `#104` (`docs(readme): keep internal implementation paths out of the package description`) | 값 |
| --- | --- |
| head | `2856e91f` (non-draft) |
| 바꾸는 것 | **`README.md` 한 파일** (docs-only) |
| main과의 거리 | **ahead 4 / behind 0** — 업데이트 불필요 |
| check run | **34건: success 25, skipped 9, 실패 0** |
| `mergeable` / `mergeable_state` | `true` / **`blocked`** |
| 현재-head 승인 | **없음.** 리뷰 5건은 모두 `COMMENTED`이고 그중 최신도 낡은 커밋 `837b17bd` 기준 |

성공한 25건에는 **리뷰 게이트가 포함됩니다** — `opencode-review` **success**, `noema-review` **success**, 그리고 `CodeQL compatibility analysis (python)`·`(actions)`도 **success**입니다. skip된 9건은 docs-only diff라 changed-scope 게이트가 건너뛴 보안 스캔들입니다(`trivy-fs`, `osv-scan`, `dependency-review`, `scorecard`, `gitleaks`, `strix`, `Dispatch current-head CodeQL scan` 등).

**이것이 두 가지를 증명합니다.** 첫째, 파이프라인은 근본적으로 고장난 것이 아닙니다 — PR은 두 리뷰 에이전트를 포함해 모든 게이트를 통과할 수 있습니다. 둘째, `#107`에서 끝내 오지 않았던 **`CodeQL compatibility analysis`의 닫는 재실행이 여기서는 실제로 왔습니다** — 즉 그 메커니즘은 작동하며 `#107`의 두 실패는 메커니즘 부재가 아니라 그 head에서 재실행이 오지 않은 사건입니다.

### 막는 것은 하나이고, 제가 할 수 없는 일입니다

모든 체크가 녹색인데 `mergeable_state`가 `blocked`이므로 남은 조건은 **현재-head 승인**입니다. 그리고 **이 세션의 GitHub 신원은 `seonghobae`**(`gh api user`로 확인: login `seonghobae`, id 8172694)이고 `#104`의 작성자도 같은 계정입니다. GitHub는 자기 PR에 `event=APPROVE`를 거부하므로(422) **제가 승인할 수 없습니다.** 이는 중앙 `.github`의 CLAUDE.md가 적어 둔 "에이전트 세션이 하나의 신원을 공유하므로 서로의 PR을 승인할 수 없다"는 조건이 이 저장소에서 그대로 확인된 것입니다. 저장소 branch protection 규칙 자체는 읽지 못했습니다 — `branches/main/protection`이 이 integration에 `403 Resource not accessible by integration`입니다. 따라서 "승인 요구"는 규칙을 읽어서가 아니라 **전부 녹색 + `blocked`** 조합에서 좁힌 결론입니다.

**그런데 이 차단은 PR마다 같지 않습니다 — 그리고 저는 이 점을 앞서 과잉 일반화했습니다 (2026-10-05).** 열린 PR 42건 중 non-draft는 다섯 건(`#82`·`#102`·`#104`·`#107`·`#109`)이고, 작성자를 확인하면 이렇습니다.

| PR | 작성자 | 세션 신원(`seonghobae`)과 동일? | `mergeable_state` |
| --- | --- | --- | --- |
| `#82` | `seonghobae` | 예 → 승인 불가(422) | `blocked` |
| `#104` | `seonghobae` | 예 → 승인 불가(422) | `blocked` |
| `#107` | `seonghobae` | 예 → 승인 불가(422) | `blocked` |
| `#109` | `dependabot[bot]` | 아니오 | `blocked` |
| `#102` | **`claude[bot]`** | **아니오** | `unstable` |

즉 "이 세션은 작성자와 신원이 같아 승인할 수 없다"는 결론은 **`#82`·`#104`·`#107`에만 해당합니다.** `#102`의 작성자는 `claude[bot]`이고 이 세션의 리뷰 신원은 `seonghobae`이므로, GitHub의 자기-PR 거부(422)는 `#102`에 걸리지 않습니다. `seonghobae`가 `#102`의 현재 head에 `event=APPROVE`를 보내면 **형식상으로는** 비작성자 승인이 되어 `pr_review_merge_scheduler_core.py`의 `has_independent_current_head_approval`을 만족시킬 수 있습니다.

**그래서 하지 않았습니다.** `#102`의 커밋을 만들고 push한 것은 이 세션이고, 작성자 필드가 `claude[bot]`인 것은 커밋 identity와 PR 생성 경로가 다른 데서 오는 **기록상의 차이일 뿐 독립적인 검토자가 생겼다는 뜻이 아닙니다.** 중앙 `.github`의 CLAUDE.md가 이 조건을 "우회할 형식이 아니다(not a formality to route around)"라고 명시하고, keyverse의 운영 규칙도 "어떤 에이전트도 self-approve하지 않는다"로 같은 선을 긋습니다. 형식이 통과한다는 사실이 실질을 바꾸지 않습니다 — 자기가 쓴 변경을 자기가 승인하면 그것은 독립 승인이 아닙니다.

**이것을 거버넌스 공백으로 보고합니다.** 승인 게이트는 "작성자 ≠ 리뷰어"라는 GitHub의 기계적 검사에 의존하는데, 같은 운영 주체가 두 신원(`claude[bot]` 작성 / `seonghobae` 리뷰)을 쓰는 순간 그 검사는 독립성을 보장하지 못합니다. `#109`(`dependabot[bot]`)도 같은 구조적 위치에 있습니다. 막는 수단은 owner 쪽에만 있습니다 — 예컨대 bot 작성 PR에 사람 리뷰어를 요구하는 규칙, 또는 리뷰 신원을 작성 신원과 분리하지 않는 운영 약속입니다. 이 문서는 이 공백을 **알고도 쓰지 않았다는 사실과 함께** 남깁니다.

### 시급한 경고 — 지금 `#104`의 브랜치를 건드리면 유일한 녹색을 잃습니다

`#104`는 `behind 0`이므로 **업데이트가 필요 없습니다.** 그리고 지금 업데이트해서는 안 됩니다. 새 커밋이나 base 병합으로 head가 움직이면 현재-head 체크가 전부 무효가 되고, 다시 만들어야 하는 체크들(`API integration suite`, `Hypothesis property tests`, `Atheris coverage-guided (bounded)`, CodeQL 계열)은 **`ubuntu-latest`이므로 과금 잠금이 풀리기 전에는 배정 전에 거절됩니다.** 즉 **head를 건드리는 순간 `#104`는 "전부 녹색"에서 "복구 불가하게 막힌" 상태로 바뀝니다.** 머지 스케줄러의 자동 branch update 대상이 되지 않도록 주의가 필요합니다(이 문서가 기록해 온 스케줄러는 승인 이후와 dispatch 이전 두 경우에 branch를 업데이트합니다).

**권고: 잠금 해제를 기다리지 말고, 다른 신원의 승인 한 건으로 `#104`를 지금 병합하십시오.** 1파일 README 변경이라 위험이 가장 낮고, 53일 만의 첫 병합으로 파이프라인 전 구간을 실증하게 됩니다. 제가 직접 병합하지 않은 이유는 두 가지입니다 — `blocked` 상태에서 GitHub가 거부하며, 우회 병합은 branch protection 우회이므로 하지 않습니다.

### 정정과 순서 규칙 — 스케줄러는 `behind 0`인 `#104`를 건드리지 않습니다. 단 main이 움직이면 달라집니다 (2026-10-03 12:5xZ)

앞 절에서 "머지 스케줄러의 자동 branch update 대상이 되지 않도록 주의가 필요합니다"라고 적었습니다. **그 경고는 지금 상태에 대해서는 과했습니다.** 중앙 `scripts/ci/pr_review_merge_scheduler_core.py`를 직접 읽어 확인했습니다.

| 위치 | 조건 |
| --- | --- |
| 4827행 | `behind_by = branch_outdated_by_base(pr, merge_state)` |
| 4828행 | `if behind_by and (current_head_approved or auto_merge_enabled):` — 승인 이후 업데이트 경로 |
| 4954행 | `if behind_by and trigger_reviews:` — 리뷰 dispatch 이전 업데이트 경로 |
| 1627~1632행 | `branch_outdated_by_base`는 `merge_state == "BEHIND"`이거나 `compareStatus == "behind"`일 때만 최소 1을 돌려주고, 그 밖에는 `compareBehindBy`(여기서는 0)를 그대로 돌려줍니다 |

**두 업데이트 경로 모두 `behind_by`가 0이 아닐 것을 요구합니다.** `#104`는 `behind 0`이고 mergeability도 `BEHIND`가 아니므로 **현재 상태에서는 스케줄러가 그 브랜치를 업데이트하지 않습니다.** 지금 당장 증거가 깎일 위험은 없습니다.

**그래서 위험의 정확한 형태는 "스케줄러의 변덕"이 아니라 "main의 전진"입니다.** 다른 PR이 main에 먼저 병합되는 순간 `#104`는 `behind ≥ 1`이 되고, 그때 4954행(리뷰 dispatch 이전) 경로가 조건을 만족해 브랜치를 업데이트할 수 있습니다. 업데이트는 head를 움직이고, 움직인 head의 체크는 `ubuntu-latest`이므로 **과금 잠금 중에는 다시 만들어지지 않습니다.**

**그리고 head를 움직일 수 있는 두 번째 경로를 이름까지 특정했습니다 — 그 경로는 지금 과금 잠금 덕분에 멈춰 있습니다 (2026-10-05 14:38Z).**
`ContextualWisdomLab/.github`의 `.github/workflows/pr-auto-rebase.yml`은 `cron: "17 */3 * * *"`로 도는 예정 워크플로이고, 자기 주석에
목적을 이렇게 적습니다 — *"it must be able to write PR head branches in TARGET_REPOSITORY"*. 실제로 `Exchange OpenCode app token for
cross-repo git writes` step으로 cross-repo 쓰기 토큰을 교환합니다. **즉 merge 스케줄러와 별개로, PR head 브랜치를 직접 쓰는 예정
작업이 존재합니다.**

지금은 그것이 돌지 않습니다. 최근 예정 실행 여섯 건이 **전부 실패**입니다 — `37326284058`(10-05 14:38:07Z), `37268758692`(10-05 05:39Z),
`37245588713`(10-04 23:57Z), `37225193335`(10-04 18:38Z), `37201815970`(10-04 12:21Z), `37181107755`(10-04 05:52Z). 14:38Z 건의
job `111817755504`(`auto-rebase`)는 `steps: 0`·러너 없음이고 annotation이 과금 잠금 문구입니다. 생성 시각이 `:17`이 아닌 것은 이 문서가
이미 기록한 "예정 실행이 수 시간 늦게 생성된다"와 일치합니다.

**그래서 `#104`의 체크 34건은 지금 "막혀 있기 때문에" 안전합니다.** 이것이 순서 규칙의 시간 제약을 바꿉니다 — 과금 잠금이 풀리는 순간
이 보호도 같이 사라지고, 3시간 주기의 auto-rebase 패스가 되살아납니다. **따라서 `#104` 병합은 "잠금 해제 후 언젠가"가 아니라 "해제 직후의
창" 안에서 이뤄져야 합니다.** 해제와 병합 사이에 auto-rebase 패스가 한 번 끼면 head가 움직이고, 그 head의 hosted 체크는 다시 만들어야
합니다(그리고 artifact 벽이 남아 있다면 그조차 완주하지 못합니다).

**확인하지 못한 것을 명시합니다 — 예정 실행의 대상 저장소입니다.** `TARGET_REPOSITORY`는
`client_payload.target_repository || inputs.target_repository || vars.AUTO_REBASE_TARGET_REPOSITORY || github.repository`로 해석되고,
`event: schedule`에는 payload도 input도 없으므로 **저장소 변수 `vars.AUTO_REBASE_TARGET_REPOSITORY`가 값을 가지면 그 저장소, 없으면
`.github` 자신**입니다. 그 변수는 읽지 못했습니다(`repos/.../actions/variables`가 이 proxy에서 403). 따라서 **"예정 auto-rebase가
semantic-data-portal의 PR head를 쓴다"는 것은 확인된 사실이 아니라 변수에 달린 가능성**입니다. 다만 `repository_dispatch`와
`workflow_dispatch` 경로는 명시적으로 임의 `target_repository`를 받으므로, 대상 지정은 언제든 이 저장소가 될 수 있습니다.
위 순서 권고는 그 가능성만으로도 성립합니다 — 잃는 쪽의 비용(복구 불가한 체크 34건)이 비대칭적으로 크기 때문입니다.

**따라서 순서 규칙은 하나입니다 — `#104`를 main에 들어가는 첫 번째로 병합하십시오.** `#104`보다 먼저 다른 것을 병합하면, 이 저장소에서 유일하게 완성된 현재-head 증거를 잠금이 풀릴 때까지 복구할 수 없습니다. 반대로 `#104`가 먼저 들어가면 그 뒤에 무엇이 병합되어도 잃을 것이 없습니다.

## `#82`는 실패 하나뿐이고, 그 하나는 `#107`과 **다른** 원인입니다 (2026-10-03 13:5xZ)

`#82`(non-draft, head `93321a98`, 17파일)의 현재-head check run 39건을 읽었습니다.

| 구분 | 수 | 비고 |
| --- | --- | --- |
| success | 23 | product CI·보안 스캔 포함 |
| skipped | 14 | `opencode-review`, `strix`, `gitleaks (secret scan)`, `Dispatch current-head CodeQL scan`, `continue-noema-transport`, `CodeQL compatibility analysis (${{ matrix.language }})` 등 |
| neutral | 1 | `Scorecard` |
| **failure** | **1** | **`noema-review`** |

**그 하나의 원인은 `#107`의 것과 다릅니다.** annotation 원문입니다.

| PR | noema 실패 원문 | 분류 |
| --- | --- | --- |
| `#107` | `HTTPError: HTTP Error 429: Too Many Requests; duration=2615.5s, served_model=google/gemma-4-31b-it:free, outcome=provider_capacity_unavailable` | 용량 소진 |
| `#82` | `HTTPError: HTTP Error 400: Bad Request; duration=362.7s, served_model=meta/llama-3.2-90b-vision-instruct` | **요청 거부** |

즉 "noema가 불안정하다"로 뭉개면 안 됩니다. 한쪽은 무료 풀의 용량이 없어서 실패하고, 다른 한쪽은 **vision-instruct 모델이 선택되어 요청이 400으로 거부**되었습니다. 코드 리뷰 요청에 `llama-3.2-90b-vision-instruct`가 배정된 것 자체가 게이트웨이의 모델 선택 문제를 가리킵니다. 두 사례는 각각 다른 수리를 요구합니다.

**다만 `#82`를 "체크 하나만 남았다"로 읽으면 안 됩니다.** `opencode-review`가 **success가 아니라 skipped**이고, 현재-head 승인도 없습니다. 머지 게이트는 체크 결론과 별개로 `reviewDecision == APPROVED`와 현재-head 독립 승인을 요구합니다. 또한 skip된 14건 중 `CodeQL compatibility analysis (${{ matrix.language }})`는 **matrix 표현식이 전개되지 않은 이름 그대로** 기록되어 있습니다 — 이름만으로는 어떤 언어의 자리였는지 알 수 없습니다.

## 제품 자체의 ready gate는 통과합니다 — 다만 스스로 두 가지 갭을 보고합니다 (2026-10-03 13:5xZ)

CI가 증거를 만들지 못하는 동안, 저장소가 정의한 **구매자 데모 readiness gate**를 로컬에서 직접 돌렸습니다. `PYTHONPATH=src python -m sdp.demo_smoke`, head `52bc571`, **exit 0 · `"ready": true`** 입니다. 이 head는 main과 `src/`가 동일합니다(차이는 문서 1건·lock 3건·`tests/test_dependency_locks.py`뿐이므로 제품 코드 결과는 main에 그대로 적용됩니다).

| gate 출력 | 값 |
| --- | --- |
| `ready` | **true** |
| `metadata_validation_pass_rate` / `shacl_validation_pass_rate` | 1.0 / 1.0 |
| `ontology_mapping_coverage` | 0.917 |
| `steward_review_queue_count` / `steward_buyer_handoff_ready` | 0 / true |
| `production_current_stage` | `pilot_candidate` |
| `production_demo_release_ready` / `production_paid_pilot_ready` / blockers | true / true / 0 |
| **`enterprise_controls` / `implemented_enterprise_controls`** | **7 / 5** |
| **`rest_connector_probe_status`** | **`contract_only`** (sql·rdf·file_lake는 `ready_for_demo`) |

**gate는 통과하지만 두 숫자가 구매자 체감 갭을 그대로 가리킵니다** — enterprise control 7개 중 **2개 미구현**, 그리고 네 커넥터 중 REST만 **계약만 있고 데모 준비는 아님**(어댑터는 `implemented`). 이 둘은 제 판단이 아니라 제품이 자기 gate에서 스스로 보고하는 값입니다. 과금 잠금이 풀린 뒤 다음 개발 대상을 고를 때 이 두 항목이 가장 먼저 봐야 할 자리입니다.

**이 문단의 두 숫자는 모두 이후에 정정되었습니다.** "2개 미구현"은 틀렸습니다(아래 "정정 1": planned 1 + 의도적 external 1), 그리고 그 planned 1건마저 2026-10-05에 닫혀 지금은 `implemented 6 / planned 0 / external 1`입니다. REST는 코드 갭이 아니라 secret reference 설정 갭입니다(아래 "정정 2"). 이 문단은 당시의 읽기를 보존하기 위해 남겨 두었을 뿐이므로, 현재 상태로 인용하지 마십시오.

**한계:** 로컬 gate 통과는 배포 증거가 아니고, 이 측정에는 DB가 없으므로 `tests/test_integration_age.py`가 요구하는 `SDP_DATABASE_DSN` 경로(AGE 그래프 통합)는 포함되지 않습니다.

### 정정 — 방금 적은 "구매자 갭 둘"은 둘 다 성격을 잘못 적었습니다 (2026-10-03 14:5xZ)

직전 절에서 ready gate 출력만 보고 "enterprise control 7개 중 2개 미구현"과 "REST 커넥터는 계약만 있다"로 적었습니다. **레지스트리와 probe를 직접 읽으니 둘 다 틀렸습니다.**

**정정 1 — 미구현은 2개가 아니라 1개입니다.** `sdp_core.enterprise.enterprise_controls_manifest()`는 7개를 `implemented 5 / planned 1 / external 1`로 분류합니다.

| 상태 | control id | label |
| --- | --- | --- |
| implemented | `tenant_authorization` | Tenant authorization boundary |
| implemented | `local_evidence_retention` | Local evidence retention |
| implemented | `rbac_matrix` | RBAC matrix |
| implemented | `deployment_template` | Deployment template |
| implemented | `operational_observability` | Operational observability |
| implemented (2026-10-05 닫힘) | `sso_oidc_adapter` | SSO/OIDC adapter |
| **external** | `central_workflow_due_diligence` | Central workflow due diligence |

**실제 제품 갭은 `sso_oidc_adapter` 하나였습니다(2026-10-05에 닫혔습니다).** 그 release criteria가 무엇을 요구하는지도 레지스트리에 적혀 있습니다 — ① OIDC issuer·audience·JWKS를 환경에서 구성, ② **group-to-role 매핑이 tenant scoped이고 감사 가능**, ③ preview가 누락·만료 claim을 거부하고 직접적인 role escalation claim을 무시. ①과 ③은 이미 구현되어 있었고 **②만 비어 있었습니다** — 매핑이 tenant 구분 없는 평면 map이었고 매핑 결과가 어디에도 기록되지 않았습니다. 그 한 칸을 닫은 기록이 아래 "`sso_oidc_adapter`를 닫았습니다" 절입니다. 이 표의 숫자는 그래서 `implemented 6 / planned 0 / external 1`이고 manifest `status`는 `pilot_ready`입니다.

나머지 하나는 **미구현이 아니라 의도적으로 외부 소유**입니다(`external`). 그리고 그 control의 release criteria가 공교롭습니다 — "Required checks pass on current head"와 "Open PR queue has no source-code blocker". **지금 과금 잠금이 막고 있는 바로 그 두 조건입니다.** 제품의 enterprise-control 매니페스트가 자기 항목 하나를 통해 이 사태를 가리키고 있습니다.

**정정 2 — REST 커넥터는 코드 갭이 아니라 설정 갭입니다.** `connector_probe("rest_connector", "marketing-campaign")`를 직접 돌려 미충족 control을 특정했습니다.

```
UNSATISFIED: control=credential_vault status=implemented secret_present=False
             ref=SDP_CONNECTOR_SECRET_REST_CONNECTOR_MARKETING_CAMPAIGN_TOKEN
```

`connectors.py` 312행의 판정은 `adapter_status == "implemented" and satisfied_controls == len(required_controls)`이고, REST는 adapter가 **implemented**이며 3개 control 중 `credential_vault`만 미충족입니다. 그 control은 **코드가 구현되어 있고**(`status=implemented`) 다만 이 측정 환경에 secret 참조가 없어 `secret_present=False`가 된 것입니다. 다른 세 커넥터(`sql`·`rdf`·`file_lake`)는 미충족 control이 없어 `ready_for_demo`입니다.

**따라서 "REST는 데모 준비가 안 됐다"가 아니라 "그 환경에 `SDP_CONNECTOR_SECRET_REST_CONNECTOR_MARKETING_CAMPAIGN_TOKEN`이 없으면 `contract_only`로 보고된다"가 맞습니다.** owner의 실제 데모 환경이 그 참조를 설정하는지는 여기서 관측할 수 없습니다 — 제 컨테이너에 없다는 것만 확인했습니다.

**교훈을 하나 더 적습니다.** 앞 절은 gate의 **집계 숫자**만 읽고 갭의 성격을 추정했습니다. `7 / 5`는 "2개 미구현"이 아니었고, `contract_only`는 "미구현"이 아니었습니다. 이 문서가 이미 두 번 적은 규칙 — 값이 같아 보이면 의도를 읽어라 — 의 세 번째 사례입니다: **집계를 읽었으면 항목을 펼쳐 보라.**

## `#109`의 `trivy-fs` 실패는 자기 lock 불일치와 정확히 상관합니다 (2026-10-03 15:5xZ)

네 개 non-draft PR의 `trivy-fs`(저장소 전역, fixable CRITICAL/HIGH)를 전수 비교했습니다. **실패는 `#109` 하나입니다.**

| PR | head | `trivy-fs` | 실행 시간 | test lock의 `pyjwt` |
| --- | --- | --- | --- | --- |
| `#82` | `93321a98` | **success** | 30초 | **2.15.0** |
| `#107` | `742e7a7e` | **success** | 15초 | **2.15.0** |
| `#104` | `2856e91f` | skipped | — | (docs-only diff라 scope에서 제외) |
| `#109` | `409ae68d` | **failure** | 20초 | **2.13.0** |

**상관이 정확합니다** — 통과한 두 PR은 compiled test lock이 `pyjwt==2.15.0`이고, 실패한 `#109`만 `2.13.0`입니다. 그리고 `#109`는 `pyproject.toml`·`requirements.txt`·`requirements-dev.txt`와 **입력 파일 `requirements-test.in`을 `PyJWT[crypto]==2.15.0`으로** 올리면서 **컴파일된 `requirements-test.txt`만 2.13.0에 남겨 둔** PR입니다(앞 절에 기록). 즉 이 문서가 "자기 입력과 모순되는 lock"이라고 적은 바로 그 불일치가 보안 게이트에서 실패로 나타난 것으로 보입니다.

**인과는 추정이고, 상관은 관측입니다.** job 로그를 받을 수 없어(blob 리다이렉트 거부 + egress 차단) annotation은 `Process completed with exit code 1.` 한 줄뿐이고 어떤 CVE가 걸렸는지는 확인하지 못했습니다. 로컬 재현도 불가합니다 — 이 컨테이너에 `trivy`·`pip-audit`·`osv-scanner`가 모두 없습니다. 제가 처음 떠올린 대안(DB 다운로드 실패 같은 인프라 사고)은 **약해졌습니다**: 실패 실행 시간 20초가 성공한 두 실행(15초·30초)과 같은 범위이므로 "스캔 전에 죽었다"로 읽기 어렵습니다.

**그리고 여기서 main에 대한 사실 하나가 따라옵니다.** `trivy-fs`는 중앙 워크플로의 PR 게이트이므로 **main 자체는 이 스캔을 받지 않습니다**(이 저장소의 예정 실행은 `fuzz`와 `scorecard-analysis`뿐입니다). main의 네 lock은 `pyjwt==2.13.0`을 그대로 들고 있으므로, `#109`를 실패시킨 조건이 main에도 있을 수 있는데 **그것을 알려 줄 스캔이 main에는 돌지 않습니다.** 이 문서가 이미 기록한 "main의 `cryptography==49.0.0` CVE 미수정"에 **pyjwt 2.13.0이 두 번째 항목으로 추가**되어야 하고, 둘 다 조합 G(`#82`·`#107`·`#110`, cryptography 50.0.2 / pyjwt 2.15.0)가 한 번에 닫습니다.

**따라서 `#109`에 대한 권고는 "병합"이 아니라 "수리 또는 승계"입니다.** non-draft이지만 보안 게이트가 실패 중이고, 그 실패가 자기 lock 불일치와 상관합니다. `requirements-test.txt`를 `.in`에서 다시 컴파일하면 자기 모순이 사라지고 실패 조건도 함께 사라질 가능성이 높습니다 — 다만 그 재컴파일은 이 세션의 브랜치 권한 밖이므로 하지 않았습니다. 조합 G가 병합되면 `#109`는 **완전 승계로 닫히는 후보**입니다(G는 네 lock 모두 2.15.0).

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
| 포털이 자체 수리 가능한 실패 check | 위 원인 대조 | **1종뿐** — `trivy-fs`(CVE-2026-69247). **writer가 `#81`이라는 판단은 아래 행에서 정정됨** |
| `#73` 현재-head check 전수 | `GET /pulls/73` check runs 38건 | **정정** — 실패는 4건뿐이고 `trivy-fs`·`strix`는 **success**입니다. 이 문서가 `#73`을 "trivy-fs inherit + strix fail"로 적어 둔 것은 옛 head 기준이었습니다. `1681a7f`가 `cryptography==50.0.1`을 고정해 스스로 초록으로 만들었습니다 |
| CVE 수리의 실제 writer | `#81`·`#57`·`#73` 세 head 대조 | **전제 오류** — `#81`(Draft·`50.0.0`)은 판정을 받을 수 없고, `#73`(non-draft·`50.0.1`)은 이미 check를 초록으로 만들었습니다. "`#81`이 올라야 풀린다"는 서술 철회. 버전·writer 선택은 owner 결정 |
| `opencode-review`의 빈 `CHANGES_REQUESTED` 사유 | 해당 bot의 현재-head overview 본문 | **원인 확인** — `Model pool: exhausted`. 모델을 얻지 못해 결정론적 경로만으로 판정. 조직 규칙대로 유료 우회 없이 fail closed 한 것이며 free pool 용량 lane(`contextual-orchestrator#1106`)의 증거 |
| 판정과 게이트 job의 순서 | job `102407231836` 종료시각 대 overview 갱신시각 | **경합 확인** — job 09:26:46 실패, 판정 게시 09:52. 판정이 게이트보다 늦게 도착해 check는 이미 fail-closed. 재실행 wake는 `.github` lane 소관 |
| `#102` head의 test suite (CI가 돌리지 않는 게이트) | 로컬에서 CI와 같은 절차 재현 — `requirements-test.txt` 설치 후 `PYTHONPATH=src python -m pytest` | **256 passed, 8 skipped** (head `86d18ce`). stacked PR이라 CI에서는 이 suite가 돌지 않으므로 직접 실행했습니다. 주의: `python -m pytest`여야 합니다 — `pytest` 콘솔 스크립트는 CWD를 `sys.path`에 넣지 않아 `tests.fuzz` import가 깨집니다 |
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

## `sso_oidc_adapter`를 닫았습니다 — 비어 있던 칸은 release criterion ②뿐이었습니다 (2026-10-05)

이 문서가 "실제 제품 갭은 하나"라고 적어 온 control을 구현했습니다. 먼저 **무엇이 비어 있었는지 정확히** 적습니다. 레지스트리의 release criteria 세 개를
코드와 대조하면 ①(issuer·audience·JWKS 환경 구성)은 `verify_oidc_jwks_token`이 `SDP_OIDC_ISSUER`/`SDP_OIDC_AUDIENCE`/`SDP_OIDC_JWKS_URL`로 이미
만족하고 있었고, ③(누락·만료 claim 거부, 직접 role claim 무시)도 `validate_oidc_claim_shape`와 `oidc_role_claims`로 이미 만족하고 있었습니다.
**②(group-to-role 매핑이 tenant scoped이고 감사 가능)만 비어 있었습니다** — 두 단어 모두 비어 있었습니다.

- **tenant scoped가 아니었습니다.** `load_oidc_role_map()`이 돌려주는 것은 `{"group": ["role"]}` 평면 map이고 `resolve_oidc_actor_context()`는
  token의 tenant claim과 무관하게 그 map을 적용했습니다. 즉 **IdP의 group 하나가 모든 tenant에서 같은 role을 부여**했습니다. 이 저장소가 `policy.evaluate`
  단계에서 tenant 경계를 막고 있으므로 이것이 곧 cross-tenant 유출은 아니지만, control이 약속한 "tenant scoped 매핑"은 아니었습니다.
- **감사 가능하지 않았습니다.** 매핑 결과는 응답의 `actor_context`로만 나가고 evidence store에는 아무것도 남지 않았습니다. 이 저장소의 governance
  invariant는 "정책 판단과 audit event를 evidence store에 기록한다"인데, 신원→role 매핑은 그 기록에서 빠져 있었습니다.

### 구현한 의미 (`src/sdp/authz.py`)

`normalize_group_role_map()`이 설정을 하나의 형태로 정규화합니다. 평면 `{"group": ["role"]}`은 **모든 tenant에 적용되는 wildcard scope(`*`)**가 되고,
`{"tenant": {"group": ["role"]}}`은 그 tenant에만 적용됩니다. `tenant_scoped_group_roles()`가 wildcard를 먼저 깔고 token tenant의 scope로
**같은 group 키를 덮어씁니다.** 덮어쓰기(합집합이 아니라 교체)를 고른 이유는 그렇게 해야 **tenant scope에서 빈 role 목록으로 wildcard 부여를 회수**할 수
있기 때문입니다. 합집합이면 회수가 표현 불가능합니다.

두 형태를 한 map에 섞으면 `ValueError`로 거절합니다(HTTP 400). 섞인 map은 거의 항상 **tenant 식별자를 group 이름으로 잘못 읽는 설정 오류**이고, 그 오류의
결과는 "의도하지 않은 role 부여"이므로 조용히 절반만 적용하는 쪽이 더 위험합니다. 빈 tenant scope 키도 같은 이유로 거절합니다 — 어떤 tenant claim과도
매칭되지 않는 죽은 설정입니다. 그리고 **명시적으로 빈 `role_map`은 "아무것도 부여하지 않음"**입니다(이전의 `role_map or load_oidc_role_map()`은 빈 map을
"설정을 읽어라"로 해석했습니다 — 명시적 거부가 묵시적 fallback으로 바뀌는 쪽이 더 위험합니다).

감사 쪽은 `oidc_group_role_bindings()`가 **group마다 한 행**을 만듭니다 — `group_name`, 부여한 `tenant_scope`, `granted_roles`. 어떤 scope도
매핑하지 않은 group은 `tenant_scope: ""`와 빈 role로 남깁니다. **거절을 보이게 남기는 것이 요점입니다**: 부여만 기록하면 "왜 이 사용자가 role을 못 받았는지"를
사후에 읽을 수 없습니다. `record_oidc_mapping_audit_event()`가 그 행들을 `enterprise/auth/oidc` resource의 audit event로 기록하고, 두 endpoint는
`group_role_bindings`와 `audit_event_id`를 응답에 함께 돌려줍니다.

**기록되지 않는 것을 명시합니다.** event `details`의 키는 정확히 `mapping_mode`, `tenant_id`, `granted_roles`, `group_bindings`,
`ignored_role_claims` 다섯 개입니다. token, 서명, raw claim payload는 응답에도 evidence store에도 들어가지 않습니다. 이 다섯 개라는 사실 자체를
테스트가 집합 비교로 고정합니다(`test_oidc_mapping_audit_event_records_bindings_without_claim_leak`) — 나중에 claim을 하나 더 흘리면 그 테스트가 깨집니다.

### 검증 (로컬 CI parity)

| 항목 | 결과 |
| --- | --- |
| 전체 테스트 (`PYTHONPATH=src pytest`) | 277 passed, 8 skipped (기준선 258 + 신규 19) |
| Hypothesis property suite (`tests/fuzz`) | 10 passed |
| `src/sdp/authz.py` statement/branch coverage | 165/165, branch 64/64 — **100%** |
| `src/sdp_core/enterprise.py` coverage | **100%** |
| docstring coverage (AST 검사, private 포함) | 두 모듈 **100%** |
| readiness gate (`python -m sdp.demo_smoke`) | `ready: true`, `implemented_enterprise_controls: 6`, exit 0 |

신규 19건 중 12건은 `tests/test_authz.py`(정규화 네 형태, 혼합·빈 scope 거절, wildcard 회수, tenant claim 우선순위, 중복 group 축약, 빈 map,
설정 fallback, unmapped audit), 7건은 `tests/test_api.py`(tenant scoping 3분기, binding 응답, 혼합 map 400, audit event 무유출, verify 경로 기록,
그리고 이 두 endpoint에 **원래부터 커버되지 않았던 payload 검증 가드 5줄**). 마지막 항목은 제 변경이 만든 공백이 아니라 기존 공백인데, 같은 endpoint를
건드리는 참에 닫았습니다 — 그 결과 OIDC 영역에는 커버되지 않은 줄이 남아 있지 않습니다. `api.py` 전체는 84%이고 나머지 공백은 이 변경과 무관한 다른
route들입니다(이 저장소에는 coverage gate가 설정되어 있지 않습니다).

### 이 증거의 한계

**CI는 이 변경을 검증하지 않았습니다 — 추정이 아니라 관측입니다.** 커밋 `254054d`를 push하고 `#102`를 Ready로 올린 직후,
이 저장소의 이 head에서 `Hypothesis property tests`(check run `111638403035`)와 `Atheris coverage-guided (bounded)`(`111638403487`)가
2026-10-05 06:11:59Z에 시작해 각각 2~3초에 실패로 끝났고, 두 annotation 모두
`The job was not started because your account is locked due to a billing issue.`입니다. 앞 절들의 잠금 증거는 `.github`의 다른 PR에서 온
것이었지만 **이 행은 이 저장소·이 head의 1차 증거**입니다. 위 표는 **CI의 설치 명령과 인터프리터를 그대로 쓴 로컬 재현**이며, 이 문서가 `#102`와
`#107`에 대해 같은 방식으로 만든 증거와 같은 등급입니다 — 즉 **required check의 대체물이 아닙니다.** 잠금이 풀리면 이 head의 체크를 먼저 돌려
로컬 결과와 대조하십시오.

**재실행하지 않았습니다.** 거절은 job 내용과 무관한 계정 상태이므로 재실행은 같은 annotation을 한 번 더 만들 뿐입니다 — 통과시킬 수단이 제게 없습니다.
관측 시점에 이 head에는 check run이 두 건만 올라와 있었습니다(`#104`의 34건과 달리). 나머지가 아직 dispatch 전인지 injection이 생략된 것인지는
확인하지 않았으므로 **"두 건뿐"을 이 head의 최종 체크 집합으로 읽지 마십시오.**

그리고 이것은 **control 하나를 닫은 것이지 SSO 통합을 완성한 것이 아닙니다.** 이 저장소는 여전히 local IdP도 session 발급도 갖지 않습니다 — `preview`와
`verify`는 외부 IdP의 claim을 검토·검증하는 증빙 endpoint이고, 실제 로그인 흐름·세션·token 갱신은 `keyverse`(cwl-idp)가 소유합니다. 여기에 IdP나
policy registry를 만들지 마십시오. 또한 `/browse/{dataset_id}/preview`가 `payload.get("user", "anonymous")`로 호출자 주장 신원을 그대로 믿는
문제는 **이 변경이 건드리지 않았습니다** — 그 둘을 잇는 것(검증된 `ActorContext`를 데이터 경로의 신원으로 쓰는 것)은 별개의 변경이고, 이 문서의 해당 절에
그대로 남아 있습니다.

## 정정 — `#104`를 지켜 주던 잠금이 끝났습니다. 수리 능력은 돌아오지 않았습니다 (2026-10-06 22:39Z)

**제가 쓴 보호 논리가 뒤집혔습니다.** 이 문서는 "`#104`의 체크 34건은 지금 *막혀 있기 때문에* 안전하고, 과금 잠금이 풀리는 순간 그
보호도 사라진다"고 적었습니다. **그 전제가 틀렸습니다 — 보호는 과금 잠금이 풀리지 않은 상태에서 먼저 끝났습니다.**

`pr-auto-rebase.yml`의 예정 실행 `37541917338`이 **2026-10-06 22:39:03Z→22:39:51Z에 성공했습니다.** job `auto-rebase`
(`112536697949`)가 self-hosted **`cwlab-s1-02`**에서 **7개 step**을 수행했습니다. 직전 일곱 번의 예정 실행은 모두 과금 잠금으로
거절됐었습니다(10-04 05:52Z ~ 10-06 06:20Z). 즉 **PR head 브랜치를 직접 쓰는 그 워크플로가 schedule 이전 덕분에 다시 살아났습니다.**

**이번 패스는 `#104`를 건드리지 않았습니다.** 확인했습니다 — head는 여전히 `2856e91f`, `updated_at`은 `2026-09-30T17:11:26Z`,
체크는 success 25 / skipped 9 / 실패 0입니다. 이유는 단순합니다: `#104`는 `behind 0`이고 rebase 패스는 **behind인 PR만** 손댑니다.

### 그래서 위험이 커졌습니다 — 완화된 것이 아닙니다

전에 적은 그림은 "잠금 해제 → 보호 종료 → 그 직후 창 안에서 `#104` 병합"이었습니다. 지금의 실제 그림은 이렇습니다.

| 항목 | 전에 적은 상태 | 지금 확인된 상태 |
| --- | --- | --- |
| head를 쓰는 예정 rebase | 과금 잠금으로 정지 | **self-hosted에서 복귀, 약 3시간 주기** |
| hosted PR 체크 재생성 | 잠금 해제와 함께 복구 | **여전히 불가**(`pull_request` 트리거는 거절) |
| `#104` 보호 근거 | 잠금이 rebase를 막는다 | **`behind 0`이라는 사실 하나뿐** |

**두 조건이 분리되었습니다.** 브랜치를 움직이는 능력은 돌아왔는데, 움직인 head의 체크를 다시 만드는 능력은 돌아오지 않았습니다.
그러므로 **`#104`가 `behind ≥ 1`이 되는 순간이 곧 체크 34건을 잃는 순간**이고, 그 순간을 만드는 것은 **main의 전진 — 즉 다른 PR의
병합 — 입니다.** 시한은 "잠금 해제 직후"가 아니라 **"main이 전진하기 전"**입니다. 다른 PR을 먼저 병합하면 몇 시간 안에 rebase 패스가
`#104`의 head를 움직이고, 그 head의 hosted 체크는 지금도 재생성할 수 없습니다.

**순서 규칙은 그대로이지만 근거가 더 강해졌습니다 — `#104`를 main에 들어가는 첫 번째로 병합하십시오.** 그리고 이것은 승인 한 건에만
달려 있습니다(현재-head 체크는 이미 완료, `behind 0`). 과금 해제도 artifact 용량 확보도 `#104` 병합의 **선행 조건이 아닙니다**.

## 중앙 schedule이 self-hosted로 이전되었습니다 — PR 게이트는 그대로입니다 (2026-10-06 21:5xZ)

**나흘 만의 첫 외부 변화입니다.** `ContextualWisdomLab/.github`의 `main`이 2026-09-30 이후 처음 전진했고, 내용이 바로 이 사태에 대한
대응입니다.

| 커밋 | 시각 | 제목 |
| --- | --- | --- |
| `9a1aa120` | 10:51:34Z | `ci: run billing-locked central schedules on existing self-hosted runners` (PR #2586) |
| `2161ef0c` | 11:07:07Z | `ci: attach trusted schedules to the MCP runner group` (PR #2590) |

**효과는 관측됩니다.** 그 전까지 `steps: 0`·러너 없음·과금 annotation으로 거절되던 두 예정 워크플로가 이제 **실제로 실행됩니다** —
`GitHub Actions queue health`(job `112512995452`, `cwlab-s1-02`, **9 step**)와 `Repository Metadata Reconcile`
(job `112516836609`, `cwlab-s1-02`, **13 step**). 실패 메시지도 과금 문구가 아니라 `Process completed with exit code 1`/`2`입니다.

**그래서 제 서술 하나의 함의를 정정합니다.** 이 문서는 "잠금을 알려 줄 감시 장치가 같은 잠금에 걸려 있어 owner가 자기 모니터링으로부터
신호를 받지 못한다"고 적었습니다. 관측 사실(감시 워크플로가 거절되고 있었다)은 그대로 맞지만, **그로부터 "owner가 모른다"는 함의는
틀렸습니다** — owner는 알고 있었고 같은 날 오전에 이전 작업을 병합했습니다. 감시가 죽은 것이 인지를 막지는 않았습니다.

### 그러나 이 저장소의 블로커는 하나도 풀리지 않았습니다

**첫째, 이전 대상은 schedule뿐입니다.** 커밋 제목이 그렇게 적고 있고(`central schedules`), 관측도 일치합니다 — 이전이 끝난
11:07Z 이후로도 `pull_request` 트리거 실행은 계속 거절됩니다. `Security Scan`(`37523658515`)·`Python Security`·`SAST Semgrep`이
**20:04:22Z**에, 즉 이전 9시간 뒤에 5초로 실패했고, 같은 계열의 17:52Z 배치는 annotation까지 읽어 과금 잠금임을 확인했습니다.
**따라서 `#102`·`#104`·`#107`·`#82`의 PR 체크는 여전히 hosted이고 여전히 배정 전에 거절됩니다.**

**둘째, 이전된 감시조차 아직 녹색이 아닙니다.** queue-health job의 step을 열어 보면 1~4번(`Set up job`, 러너 하드닝 ×2,
`Checkout trusted queue-health source`)은 성공하고 **5번 `Collect read-only repository and runner evidence`에서 실패**하며,
6번 `Upload queue-health evidence`는 **skip**됩니다. 즉 실행 자리는 생겼지만 증거 수집이 아직 깨져 있습니다.

**셋째, 이전과 함께 네 번째 실패 유형이 나타났습니다 — self-hosted 러너의 통신 유실.** 21:26~21:44Z 구간에서 두 건이 각각 약 601초
뒤 이 annotation으로 끝났습니다.

```
The self-hosted runner lost communication with the server. Verify the machine is running
and has a healthy network connection.
```

`Organization Commercial Readiness`의 `coordinate`(job `112512790513`, **`cwlab-s1-06`**, 10 step)와
`Daily Review Recovery`의 `Resolve target(s)`(job `112510056128`, **`cwlab-s1-01`**, 2 step)입니다. **서로 다른 두 러너**가 몇 분
안에 같은 방식으로 떨어졌고 둘 다 ~601초에서 끊겼으므로, 단일 호스트의 일시적 장애보다는 **부하·네트워크·러너 그룹 재구성과 관련된
문제**로 읽는 편이 자연스럽습니다. 다만 원인은 확인하지 못했습니다 — `actions/runners` 인벤토리가 이 proxy에서 403이고, 두 번째
커밋(`attach trusted schedules to the MCP runner group`)이 러너 그룹을 건드렸다는 사실과 시간적으로 가깝다는 점만 적어 둡니다.
**이전 작업이 원인이라고 단정하지 마십시오 — 상관만 관측했습니다.**

### 그래서 owner 조치는 셋에서 줄지 않았습니다

schedule 이전은 **PR 병합 경로에 대해서는 아무것도 바꾸지 않습니다.** 남은 것은 그대로입니다 — (1) artifact 저장 용량 확보
(10-06 18:35:17Z에도 `Artifact storage quota has been hit` 확인, 6~12시간 지연), (2) **PR 게이트용 과금 잠금 해제**(또는 PR
트리거 워크플로까지 self-hosted로 이전), (3) `#104`에 독립 승인 1건. 다만 이전 작업이 보여 준 길이 하나 있습니다 — **같은 방식으로
`pull_request` 트리거 워크플로를 self-hosted로 옮기면 과금 해제 없이도 PR 게이트를 되살릴 수 있습니다.** 그 판단은 `.github`의
소유이고 `pull_request_target` 신뢰 경계에 직접 닿으므로, 이 문서는 가능성만 적고 권고하지 않습니다.

## 열린 non-draft PR이 5건에서 6건이 되었습니다 — 새 1건도 같은 자리에서 멈췄습니다 (2026-10-08 ~ 10-11 확인)

`#111` `chore(dependabot): stop hosted-only version updates` 가 2026-10-08T04:02:30Z에 열렸습니다. owner `seonghobae`,
non-draft, `behind 0`, 커밋 1개, 바뀐 파일은 `.github/dependabot.yml` 하나뿐이고 `+0 / −15`입니다. 코드는 한 줄도
건드리지 않습니다.

그 head(`7ec43999`)의 check run은 6건이고 **6건 전부 `failure`, 성공 0건**입니다. 여섯 모두 같은 annotation을 답니다 —
`The job was not started because your account is locked due to a billing issue.`

| check run | 시작 → 종료 | 결론 |
| --- | --- | --- |
| `API integration suite` | 04:02:34Z → 04:02:37Z | failure (billing) |
| `Atheris coverage-guided (bounded)` | 04:02:33Z → 04:02:36Z | failure (billing) |
| `Hypothesis property tests` | 04:02:33Z → 04:02:36Z | failure (billing) |
| `Analyze (python)` ×2 · `Analyze (actions)` | 동일 분 | failure (billing) |

읽을 것은 이것입니다. **설정 한 파일을 지우는, 제품 코드 위험이 0인 PR도 초록 체크를 한 건도 얻지 못합니다.** `#111`을
막는 것은 내용이 아니라 레인입니다. 그리고 작성자가 `seonghobae` — 이 세션과 같은 identity — 이므로 이 세션은 `#111`을
승인할 수 없습니다. `#82`·`#104`·`#107`과 정확히 같은 자리입니다.

잠금은 아직 살아 있습니다. main의 일일 `fuzz` schedule이 10-07·10-08·10-09·10-10·10-11 전부 `failure`이고, 가장 최근
중앙 주입 실행(`dynamic/github-code-scanning/codeql`, run `38162977170`, 2026-10-11T18:14:29Z → 18:14:35Z)의 두 job
`114539597274`·`114539597474`는 `runner=""`, `steps: 0`, 3초, 같은 billing annotation입니다. 즉 **최소 2026-10-11
18:14Z까지** 과금 잠금이 유효합니다. 현재 큐는 비어 있습니다(`status=queued` → 0).

### 수리 PR이 수리 대상 게이트 뒤에 서 있습니다 — `#110`

`#110` `ci: stage all workflows on isolated self-hosted runners` 는 2026-10-03T03:46:57Z에 만들어졌고
10-03T04:01:27Z 이후 변동 없이 **9일째 draft**입니다. `behind 0`, 커밋 5개, 파일 6개 —
`.github/workflows/tests.yml`, `.github/workflows/fuzz.yml`, `.github/workflows/scorecard-analysis.yml`,
`.github/actionlint.yaml`, `docs/self-hosted-ci-migration.md`, `tests/test_self_hosted_ci_contract.py`.

이 저장소 **자신의** 게이트(`Tests`, `fuzz`, `Scorecard analysis`)를 거절당하는 hosted 레인에서 빼내는 변경이 이미
작성되어 있다는 뜻입니다. 그것이 머지되지 않았기 때문에 10-08의 `#111`에서도 `Tests`와 `fuzz`가 hosted에서 그대로
거절됐습니다. 수리가 수리 대상 게이트 뒤에 서 있습니다.

`#110`을 ready로 올리지 않았습니다. 이유는 둘입니다.

- **isolated 레인 용량을 확인할 수 없습니다.** `#110`의 check run은 2건뿐이고 둘 다 `cancelled`(2026-10-03T03:47:01Z
  시작) — draft 생성 직후 취소된 것이므로 `cwlab-ci-isolated` 용량에 대한 증거가 아닙니다. `actions/runners`(repo·org
  모두)는 이 세션의 프록시에서 403이므로 등록 여부를 저는 읽을 수 없습니다. 기존 관측(`+cwlab-ci-isolated` = 무한 대기)이
  아직 유효하다면 ready 전환은 체크를 영원히 대기 상태로 만들 뿐입니다.
- **승인이 여전히 1건 필요하고 그 1건을 이 세션이 할 수 없습니다.** 작성자가 같은 identity입니다.

둘 중 어느 것도 제가 못 바꾸는데 head만 흔드는 전환은 손해만 남습니다. 그래서 관측만 기록합니다.

### 순서에 대한 정정

`#110`은 `#104` 뒤에 줄 서는 항목이 **아닙니다.** 두 PR은 서로 독립입니다.

- `#104`는 이미 완전한 현재-head 증거(25 success / 9 skipped / 0 failure, `behind 0`)를 들고 있어 **추가 체크가 필요
  없습니다.** 필요한 것은 독립 승인 1건이고, 시한은 "main이 전진하기 전"입니다.
- `#110`은 **앞으로의** 모든 PR이 증거를 만들 수 있게 하는 변경입니다. 필요한 것은 독립 승인 1건 + isolated 용량입니다.

그래서 owner 조치 목록은 넷으로 늘었습니다 — (1) `#104`에 독립 승인 1건(선행 조건 없음, 시한 있음), (2) `#110`에
독립 승인 1건 + isolated 용량 등록, (3) artifact 저장 용량 확보, (4) PR 게이트용 과금 잠금 해제. (2)가 서면
(3)·(4) 없이도 이 저장소 자체 게이트는 되살아납니다. 중앙 required 워크플로(OpenCode·Noema·Strix·스케줄러)는 여전히
`.github`의 소유이고 `pull_request_target` 신뢰 경계에 닿으므로 이 문서는 범위 밖으로 둡니다.

## main에 CRITICAL이 하나 서 있습니다 — `anyio` 세 건이고, 수리는 이미 draft `#105`에 있습니다 (2026-10-12)

`#109`(dependabot, `pyjwt 2.13.0 → 2.15.0`)는 과금 잠금 **이전**인 2026-10-01에 돌았습니다. 그래서 이 저장소에서 실질
증거를 가진 몇 안 되는 head 중 하나입니다 — success 23, skipped 7, neutral 2, failure 5(`trivy-fs`,
`opencode-review`, `noema-review`, `CodeQL compatibility analysis (python)`/`(actions)`).

그 `trivy-fs`(job `110464116105`, 2026-10-01T16:13:28Z → 16:13:48Z)는 플레이크가 아닙니다. 로그에 **진짜 발견 4건**이
적혀 있습니다.

| 심각도 | CVE | 위치 | 패키지 |
| --- | --- | --- | --- |
| CRITICAL (security-severity=9.5) | CVE-2026-63374 | `requirements.txt:11` | anyio |
| HIGH (8.0) | CVE-2026-63349 | `requirements.txt:11` | anyio |
| MEDIUM (5.5) | CVE-2026-64847 | `requirements.txt:11` | anyio |
| HIGH (8.0) | CVE-2026-69247 | `requirements.txt:125` | cryptography |

워크플로가 조치 위치까지 지시합니다 — `Remediate each finding at the shared base branch so open PRs inherit the fix.`

수정 버전을 확인했습니다. anyio 세 건은 전부 **4.14.2**에서 고쳐졌고, cryptography CVE-2026-69247은 **50.0.0**
(상류 권고 `GHSA-g6cj-pr64-35w5`)입니다.

- `CVE-2026-63374` — `TLSStream`이 호스트명을 IDNA 2003으로 인코딩해 **위조된 TLS 인증서를 받아들일 수 있습니다.** 이
  저장소의 런타임 경로(fastapi → starlette → anyio, httpx → anyio)가 그대로 지나갑니다.
- `CVE-2026-63349` — `open_process()`가 `extra_groups`를 백엔드의 `group`으로 넘겨 자식 프로세스가 부모의 보조 그룹을
  유지할 수 있습니다(권한 하강 실패).
- `CVE-2026-64847` — 프로세스 풀 워커의 stderr 파이프를 부모가 읽지 않아, 워커가 충분히 쓰면 호출이 무한 블록됩니다(DoS).

### 이 브랜치의 실제 상태와 조치

조치 전 pin은 파일마다 달랐습니다 — `requirements.txt`·`requirements-dev.txt`·`requirements-graph.txt`가
`anyio==4.14.1`, `requirements-test.txt`만 `anyio==4.14.2`. cryptography는 이 브랜치가 이미 `50.0.0`입니다(main은
아직 `49.0.0`).

`#105`(dependabot, 커밋 `be7799f`)가 정확히 그 수리입니다 — `requirements.txt`와 `requirements-dev.txt`의 anyio
블록만 `+3/−3`으로 바꾸는 수술적 변경. 그래서 **같은 커밋을 그대로 cherry-pick했습니다**(`0b88fdb`, `-x`로 출처 기록,
저자는 dependabot 유지). 해시를 손으로 만들지 않았습니다.

이 환경에서 락을 재생성하지 않은 이유는 분명합니다. 이 컨테이너의 uv(0.8.17 / Linux / CPython 3.12)로
`uv pip compile pyproject.toml --generate-hashes -o requirements.txt`를 그대로 돌리면 anyio 외에
**`colorama`와 `tzdata` 두 항목이 사라집니다.** 커밋된 락은 이 둘을 환경 마커 없이 담고 있으므로, 재컴파일은 수리가
아니라 플랫폼 지원 축소를 함께 싣는 변경이 됩니다. 그래서 재생성이 아니라 이전을 택했습니다.

### 로컬 검증 — 죽은 hosted 레인이 만들 수 없는 증거

- `python3.12 -m pip install --require-hashes -r requirements-dev.txt` → `anyio-4.14.2`, `cryptography-50.0.0`
  설치 성공. `--require-hashes`가 받은 산출물과 해시를 대조하므로, **옮겨 온 해시가 진짜라는 것이 이 설치로
  증명됩니다**(손으로 꾸민 값이면 설치가 실패합니다).
- CI parity(`.github/workflows/tests.yml`와 동일한 경로):
  `pip install --require-hashes -r requirements-test.txt` → `PYTHONPATH=src python -m pytest` →
  **277 passed, 8 skipped** (head `0b88fdb`, Python 3.12.3).
- `PYTHONPATH=src python -m sdp.demo_smoke` → `"ready": true`.

이 수리 자체에는 hosted 증거가 **없습니다.** cherry-pick을 올린 head `6e0eb766`의 `Hypothesis property tests`
(job `114701908249`)와 `Atheris coverage-guided (bounded)`(job `114701908478`)는 2026-10-12T07:11:19Z → 07:11:22Z,
`runner=""`, `steps: 0`, 3초로 같은 billing annotation을 답니다. 직전 head `1de2681c`(run `38215388598`)도 동일합니다.
그래서 **잠금은 최소 2026-10-12 07:11Z까지 유효**하고, CRITICAL을 지우는 변경의 유일한 증거는 위 로컬 검증뿐입니다.
승인자는 hosted 체크가 아니라 그 로컬 증거를 읽어야 합니다. 이 실패 유형은 `#102`에 이미 한 번 코멘트했으므로 다시
코멘트하지 않았고, 재실행 수단도 없어 계속 관찰만 합니다.

### 남은 것 하나와, 하지 않은 것

`requirements-graph.txt:15`는 아직 `anyio==4.14.1`입니다. 이 파일은 uv가 아니라 pip-compile 산출물이고
(`pip-compile --constraint=constraints-graph.txt --extra=graph --generate-hashes ...`) 같은 플랫폼 해상도 문제를
가지므로 이 컨테이너에서 충실히 재생성할 수 없습니다. 손으로 고치지 않았습니다. trivy는 같은 패키지·버전을 파일마다
중복 보고하지 않으므로(4건 모두 `requirements.txt`만 가리켰습니다), `requirements.txt`가 고쳐진 뒤의 스캔에서 **이
파일이 새로 드러날 수 있습니다.** graph extra 락의 재생성은 owner 환경에서 해야 합니다.

`#105`를 승인하지 않았습니다. 저자가 dependabot이므로 GitHub의 "자기 PR 승인" 422에 걸리지 않고 이 세션이 기계적으로
승인할 수는 있습니다. 하지만 (ㄱ) `#105`는 draft여서 병합 대상이 아니고, (ㄴ) 필수 체크가 과금 잠금으로 증거를 만들지
못하는 상태에서 증거 기반 리뷰어를 제 판단으로 갈아끼우는 일이 됩니다. 그래서 승인 대신 위 검증 기록만 남깁니다.

`#105`는 여전히 독립 carrier입니다. 이 cherry-pick이 `#105`를 superseded로 만들지 않습니다 — 같은 내용을 이 브랜치가
들고 있을 뿐이고 **main은 아직 `anyio==4.14.1`입니다.** main에 먼저 닿는 쪽이 수리하는 쪽입니다. 그래서 owner 조치에
하나가 더해집니다: **`#105`(또는 같은 내용을 담은 다른 PR) 하나가 main에 닿아야 CRITICAL이 사라집니다.**

## 이미지는 `anyio` 수리를 조용히 되돌리고 있었습니다 — 재현하고 막았습니다 (2026-10-12)

`requirements.txt`를 고치는 것만으로는 **빌드된 이미지가 고쳐지지 않습니다.** `Dockerfile`은 두 락을 순서대로
설치합니다.

```dockerfile
RUN python -m pip install --require-hashes -r requirements.txt \
  && python -m pip install --require-hashes -r requirements-graph.txt \
```

두 번째 파일이 `anyio==4.14.1`을 고정하고 있었으므로, pip은 첫 설치가 올려 둔 4.14.2를 **제거하고 4.14.1을 다시
설치합니다.** 추측이 아니라 이 컨테이너에서 같은 순서로 재현했습니다.

```text
=== Dockerfile line 19 ===  Name: anyio / Version: 4.14.2
=== Dockerfile line 20 ===  Found existing installation: anyio 4.14.2
                            Uninstalling anyio-4.14.2: Successfully uninstalled anyio-4.14.2
                            Successfully installed anyio-4.14.1 greenlet-3.2.5 sqlalchemy-2.0.51
=== final ===               Name: anyio / Version: 4.14.1
```

읽을 것은 이것입니다. **`#105`만으로는 CRITICAL이 사라지지 않습니다.** `#105`는 `requirements.txt`와
`requirements-dev.txt`만 바꾸므로, 그 수리가 머지되어도 이미지는 CVE-2026-63374(위조 TLS 인증서 수용) /
CVE-2026-63349 / CVE-2026-64847에 그대로 노출됩니다. 이 결함은 눈에 띄지 않습니다 — trivy는 같은 패키지·버전을
파일마다 중복 보고하지 않아 `requirements.txt` 한 줄만 가리키고, 빌드 로그의 downgrade는 성공 로그 사이에 섞입니다.

### 조치 — 생성 블록 이전 + 회귀 테스트

`requirements-graph.txt`의 anyio 블록을 `requirements.txt`의 것과 **바이트 동일하게** 옮겼습니다(버전 줄 + 해시 두
줄). 해시를 손으로 만들지 않았고, 이 환경에서 pip-compile로 이 파일을 재생성하지 않은 이유는 측정해 두었습니다 —
문서화된 명령 그대로 `--upgrade-package anyio==4.14.2`를 붙여 돌리면 diff가 195줄이 되고, anyio 외에 이런 변화가
함께 실립니다.

| 재생성이 함께 바꾸는 것 | 내용 |
| --- | --- |
| 추가 | `cryptography==50.0.2`, `cffi==2.1.1`, `pycparser==3.11`, `pyjwt[crypto]==2.13.0` |
| 삭제 | `colorama==0.4.6`, `tzdata==2026.2` (커밋된 파일은 마커 없이 담고 있음) |

추가분이 뜻하는 바가 하나 더 있습니다. **커밋된 `requirements-graph.txt`는 `pyproject.toml`보다 오래됐습니다** —
`PyJWT[crypto]`가 `[project].dependencies`에 들어오기 전에 생성되어 pyjwt·cryptography·cffi·pycparser를 하나도
담고 있지 않습니다. 이미지가 깨지지 않는 이유는 `Dockerfile`이 그 전에 `requirements.txt`를 설치하기 때문일
뿐입니다. 또 `cryptography==50.0.2`는 `tests/test_dependency_locks.py`가 다른 세 락에 대해 고정한 `50.0.0`과
어긋나므로, 재생성은 수리가 아니라 세 가지 변경을 한꺼번에 싣는 일이 됩니다. graph extra 락의 정식 재생성은 커밋된
파일과 같은 플랫폼 집합을 재현하는 owner 환경에서 해야 합니다.

대신 이 결함 유형이 다시는 조용히 지나가지 않도록 회귀 테스트를 넣었습니다 —
`test_image_locks_agree_on_every_shared_pin`은 `Dockerfile`이 함께 설치하는 두 락이 **공유하는 모든 pin**에 대해
버전 일치를 요구합니다(현재 공유 pin 17개). 범위를 이 두 파일로 한정한 것은 의도적입니다: `requirements-test.txt`는
이미지에 들어가지 않고 `greenlet`(3.5.3 vs 3.2.5)·`tzdata`(2026.3 vs 2026.2)에서 이미 갈라져 있으므로, 전체 락에
일괄 규칙을 걸면 보안과 무관한 이유로 실패합니다.

### 검증 (로컬, head 반영)

- **RED 확인**: graph 락을 4.14.1로 되돌리면 새 테스트가 정확히 그 충돌을 보고하며 실패합니다 —
  `AssertionError: ... {'anyio': ('4.14.2', '4.14.1')}`. 되돌림을 취소하면 통과합니다.
- `pip install --require-hashes -r requirements.txt` → `requirements-graph.txt` 순서 재현 결과 최종
  `anyio 4.14.2`, `cryptography 50.0.0`. 두 번째 설치는 `greenlet`·`sqlalchemy`만 추가하고 아무것도 내리지 않습니다.
  `--require-hashes`가 통과했으므로 **옮겨 온 해시가 graph 락에서도 진짜임이 증명**됩니다.
- CI parity 전체 스위트: **278 passed, 8 skipped** (새 테스트 1건 포함).
- `PYTHONPATH=src python -m sdp.demo_smoke` → `"ready": true`.

### 이 브랜치의 보안 델타는 정확히 두 건이고, 네 건 전부 닫혔습니다 (2026-10-12 08:5xZ 확인)

`origin/main...HEAD`에서 의존성 파일이 바뀐 범위를 pin 단위로 비교했습니다. 바뀐 것은 **보안 범프 두 개뿐이며 새로
들어온 pin은 없습니다** — 즉 2026-10-01 실측 trivy 스캔이 보지 못한 패키지는 이 브랜치에 하나도 없습니다.

| 락 파일 | main | 이 브랜치 |
| --- | --- | --- |
| `requirements.txt` | anyio 4.14.1 · cryptography 49.0.0 | anyio **4.14.2** · cryptography **50.0.0** |
| `requirements-dev.txt` | anyio 4.14.1 · cryptography 49.0.0 | anyio **4.14.2** · cryptography **50.0.0** |
| `requirements-test.txt` | anyio 4.14.2 · cryptography 49.0.0 | anyio 4.14.2 · cryptography **50.0.0** |
| `requirements-graph.txt` | anyio 4.14.1 | anyio **4.14.2** |
| `fuzz-requirements.txt` | — | main과 동일 |

따라서 10-01 스캔의 발견 4건은 이미지가 설치하는 모든 파일에서 닫혔습니다 — anyio 세 건은 네 락 모두 4.14.2,
cryptography 한 건은 세 락 모두 50.0.0(graph 락은 cryptography를 담지 않습니다). 남은 작업은 수리가 아니라
**graph extra 락의 정식 재생성**이고, 그것은 커밋된 플랫폼 집합을 재현하는 owner 환경의 일입니다.

### 열린 "7번째 control"은 갭이 아니라 외부 소유입니다 — 다만 지금 그 외부가 꺼져 있습니다

`demo_smoke`의 `enterprise_controls: 7 / implemented_enterprise_controls: 6`을 미구현 1건으로 읽으면 틀립니다.
manifest는 `planned_controls: 0`, `external_controls: 1`이고, 그 한 건은 `central_workflow_due_diligence`
(status `external`)입니다. 이 저장소가 구현할 대상이 아닙니다.

읽어 둘 것은 그 release criteria입니다 — "Required checks pass on current head", "Open PR queue has no
source-code blocker". **두 조건 모두 지금 충족 불가능합니다**(과금 잠금으로 현재-head 체크가 증거를 만들지 못하고,
PR 큐는 소스 결함이 아닌 이유로 멈춰 있습니다). 그렇다고 이 저장소가 외부 CI 상태를 스스로 보고하도록 바꾸지는
않았습니다 — 포털은 org 파이프라인에 접근 권한이 없고, 접근 없이 외부 시스템의 상태를 단언하는 필드를 추가하는 것은
정직한 증거가 아니라 추측을 계약으로 만드는 일입니다. 상태 보고의 위치는 이 문서이고, 조치 위치는 owner입니다.

## 다중 렌즈 감사로 CRITICAL 하나를 찾아 닫았습니다 — `/enterprise/auth/oidc-verify` (2026-10-14)

PR 경로가 전부 막힌 사이, 저장소 위험면을 여덟 개 렌즈로 병렬 감사하고 각 후보를 **서로 다른 세 관점의 반박자**
(코드 정독 / 도달 가능성 / 실제 실행)에게 넘겨 다수결로 살아남은 것만 채택했습니다. 원시 발견 31건 → 중복 제거 31건 →
심각도 상위 14건 검증 → **12건 생존**. 하위 17건은 검증 대상에서 제외했고 그 사실을 로그에 남겼습니다(조용한 절단 없음).

### 고친 것 — 호출자가 자기 토큰의 신뢰 기준을 지정할 수 있었습니다

`POST /enterprise/auth/oidc-verify`가 `issuer`, `audience`, `jwks`, `role_map`을 **request body에서** 받아
`verify_oidc_jwks_token`에 그대로 넘겼고, 그 함수는 `issuer or os.getenv(...)` 순서로 해석했습니다. 즉 **body가
operator 설정을 이겼습니다.** 에이전트 보고를 믿지 않고 직접 재현했습니다 — `SDP_OIDC_ISSUER`,
`SDP_OIDC_AUDIENCE`, `SDP_OIDC_JWKS_URL`을 진짜 IdP로 설정한 상태에서, 공격자가 만든 RSA 키로 자기 서명한 토큰과
자기 공개 JWK를 함께 보냈더니:

```text
HTTP 200
"token_verification": "jwks_signature_verified"
"actor_context": {"subject": "attacker@evil.test", "tenant_id": "victim-tenant", "roles": ["platform-admin"]}
"audit_event_id": "189fbb69-..."
```

설정된 IdP는 **한 번도 조회되지 않습니다.** body의 `role_map`은 알려진 group 이름조차 필요 없게 만들어 주고,
감사 이벤트는 정상 매핑처럼 기록됩니다. enterprise manifest가 `sso_oidc_adapter` control의 증빙으로 내세우는
엔드포인트가, 아무 서명 권한 없는 익명 호출자에게 임의 tenant의 platform-admin 신원을 발급하고 있었습니다.

수리는 계약을 되돌리는 것입니다. 신뢰 기준은 operator 설정에서만 읽고, body는 `token` 하나만 받습니다. 네 필드가
body에 오면 **조용히 무시하지 않고 400으로 거절**합니다 — 무시하면 호출자는 자기 값이 반영된 줄 알게 됩니다.
오프라인·에어갭 배포를 위해 JWKS 문서를 그대로 담는 `SDP_OIDC_JWKS` 설정 채널을 추가했습니다(요청 채널이 아니라
설정 채널입니다). RED를 먼저 확인했습니다: 새 테스트 2건이 수리 전에는 실패하고 수리 후에 통과하며, 위 재현
스크립트는 이제 `HTTP 400`과 `actor_context: null`을 돌려줍니다.

기존 테스트 4건이 **취약한 계약을 고정하고 있었기 때문에** 함께 고쳤습니다 — body에 issuer/audience/jwks를 넣어
200을 기대하던 세 건과, `"jwks must be an object"` 메시지를 기대한 한 건입니다. 테스트가 보안 구멍을 지키고 있던
경우이므로 변경 사실을 여기 명시합니다. 검증: CI parity 전체 스위트 **280 passed, 8 skipped**, `sdp.demo_smoke`
ready=true. 문서(README, enterprise-readiness, implementation-compliance)와 `sso_oidc_adapter` /
`oidc_jwks_verification` manifest의 release/acceptance criteria도 같은 커밋에서 갱신했습니다.

### 아직 고치지 않은 11건 — 제가 직접 재현하지 않았습니다

아래는 반박자 다수결을 통과한 나머지 항목입니다. **이 11건은 감사 에이전트의 검증 결과이고, 제가 손으로 재현한
것은 위 CRITICAL 하나뿐입니다.** 각 항목은 고치기 전에 같은 방식으로 직접 재현해야 합니다.

| 심각도 | 위치 | 주장 | 반박 투표 |
| --- | --- | --- | --- |
| critical | `src/sdp/orchestrator.py:50` | Comma-separated FROM list defeats the source-table allowlist | 0/3 refuted |
| critical | `src/sdp/observability.py:103` | Log-sink URL credentials are published verbatim on the unauthenticated /enterprise/observability endpoint | 1/3 refuted |
| high | `src/sdp/api.py:427` | GET /catalog/datasets/{dataset_id} returns full dataset state (schema, PII flags, source DSN) with no policy evaluation and no evidence record | 1/3 refuted |
| high | `src/sdp/orchestrator.py:12` | SELECT ... INTO passes the read-only SELECT guard and writes a new table | 0/3 refuted |
| high | `src/sdp/orchestrator.py:38` | Dollar-quoted strings bypass the literal_values_not_allowed guard | 0/3 refuted |
| high | `src/sdp/browse.py:60` | preview PII masking is bypassed by naming a different dataset_id in the path | 1/3 refuted |
| high | `src/sdp_core/stores.py:25` | PostgresEvidenceStore writes tenant_id='demo' for every audit event, mis-attributing every tenant's audit trail | 0/3 refuted |
| high | `src/sdp_core/stores.py:21` | Policy denials are recorded under tenant 'demo' because deny branches omit tenant_id from obligations | 0/3 refuted |
| high | `docker/entrypoint.sh:13` | Entrypoint execs the app after 30 failed migration attempts, and the /health healthcheck cannot detect it | 0/3 refuted |
| high | `src/sdp/api.py:131` | Synchronous sink export runs on the event loop in the async observability middleware, serializing every request | 0/3 refuted |
| high | `tests/test_api.py:1258` | Catalog publish/patch/deprecate authorization guard is defended by no test | 0/3 refuted |

위 표는 **보고된 그대로의 기록**이고, 소진 상황은 아래 "감사 큐 소진" 절들이 가집니다. 2026-10-14 기준
11건 중 9건이 닫혔습니다 — orchestrator 3건(소진 1), observability 1건(소진 2), `api.py:427` + `/catalog/datasets`
목록(소진 3), `browse.py:60`(소진 4), `stores.py:21`+`:25`(소진 5), `entrypoint.sh:13`(소진 6).
2026-10-14 기준 **11건 전부 닫혔습니다** — 소진 1~8 절이 각 항목의 재현·수리·검증 기록입니다.

이 목록 자체는 증거가 아니라 **작업 큐**입니다. 다음 순서로 직접 재현 → RED → 수리 → 로컬 검증을 반복합니다:
SQL validator 세 건(`FROM a, b` 콤마 조인으로 allowlist 우회, `SELECT ... INTO`가 read-only 가드를 통과,
`$$...$$` dollar-quote가 literal 가드를 우회)이 서로 같은 함수에 모여 있어 한 묶음으로 처리하기 적합하고,
observability의 netloc userinfo 노출은 한 줄 수리입니다.

### 감사 큐 소진 (1) — SQL validator 우회 세 건을 닫았습니다 (2026-10-14)

감사 큐의 SQL-safety 세 건은 모두 `validate_sql_query` 한 함수에 모여 있어 한 묶음으로 처리했습니다. 에이전트
보고를 믿지 않고 **직접 실행해 재현**했습니다 — 세 입력 모두 경고 0개(= 통과)였고, 대조군(`CROSS JOIN` 형태)은
올바르게 거절되고 있었습니다.

| 입력 | 수리 전 | 수리 후 |
| --- | --- | --- |
| `SELECT customer_id FROM customer, secret_table` | `[]` | `['unauthorized_table_reference']` |
| `SELECT * INTO exfil_table FROM customer` | `[]` | `['forbidden_keyword_detected']` |
| `SELECT pg_read_file($$/etc/passwd$$) FROM customer` | `[]` | `['literal_values_not_allowed']` |
| `SELECT lo_import($x$/etc/passwd$x$) FROM customer` | `[]` | `['literal_values_not_allowed']` |

원인은 각각 하나씩입니다.

- **콤마 FROM 목록**: 기존 정규식은 `from`/`join` **직후 식별자 하나만** 캡처했습니다. 콤마 뒤의 테이블은
  allowlist 검사에 아예 보이지 않았습니다. 같은 조인을 `CROSS JOIN`으로 쓰면 거절되는데 콤마로 쓰면 통과하는,
  문법 형태에만 의존하는 구멍이었습니다.
- **`SELECT ... INTO`**: PostgreSQL에서 `SELECT ... INTO <name>`은 `CREATE TABLE AS`입니다. `into`와 `create`가
  금지 키워드 집합에 없었으므로, 가드가 찾는 `select `로 시작하는 문장 안에 쓰기가 숨을 수 있었습니다.
- **Dollar-quote**: literal 검사가 `'`와 `"`만 봤습니다. `$$...$$` / `$tag$...$tag$`는 두 문자를 포함하지 않는
  문자열 리터럴이므로 임의 인자를 통과시켰습니다(그래서 인자가 필요한 함수 호출이 "안전" 레인에 들어왔습니다).

수리는 세 지점입니다 — 테이블 목록을 **콤마와 alias를 포함해 전부** 파싱하는 `_referenced_source_tables()`
(목록을 읽을 수 없으면 비어 있는 것으로 취급하지 않고 `unauthorized_table_reference`로 **거절**합니다),
금지 키워드에 `into`·`create`·`copy`·`grant`·`revoke`·`execute`·`prepare`·`vacuum`·`lock`·`call` 추가,
literal 검사에 dollar-quote 정규식 추가.

검증: RED를 먼저 확인(새 우회 테스트 7건 전부 실패 → 수리 후 통과), **대조군 5건**(`FROM customer`,
`AS` alias, alias 생략, `analytics.customer` 수식, 같은 테이블 self-join)은 수리 후에도 경고 0개로 유지,
CI parity 전체 **292 passed / 8 skipped**, Hypothesis fuzz mirror 10 passed, `sdp.demo_smoke` ready=true.
Atheris 타깃의 불변식(`len(warnings) == len(set(warnings))`, 예외 없음)을 깨지 않는지 **4,019개 입력**
(빈 문자열, 콤마만, 유니코드, 200개 콤마, 잘린 `FROM`/`AS`/`$`, 무작위 조합)으로 따로 확인했습니다 — 문제 0건.

### 감사 큐 소진 (2) — 인증 없는 manifest가 log sink 자격증명을 그대로 싣고 있었습니다 (2026-10-14)

`GET /enterprise/observability`는 인증 의존성이 없는 공개 엔드포인트입니다(`src/sdp/api.py:187`). 그런데
`_sink_status()`가 `target`에 `urlparse().netloc`을 넣었고, **`netloc`은 userinfo를 포함합니다.** 직접 재현했습니다.

| `SDP_LOG_SINK_URL` | 수리 전 `target` | 수리 후 |
| --- | --- | --- |
| `https://sdp-ingest:s3cr3t-token@logs-prod.grafana.net/loki/api/v1/push` | `sdp-ingest:s3cr3t-token@logs-prod.grafana.net` | `logs-prod.grafana.net` |
| `syslog://user:pw@logs.example.net/path?api-key=TOPSECRET` | **URL 전체**(userinfo + query 포함) | `logs.example.net` |
| `https://logs-prod.grafana.net/loki/api/v1/push` (대조) | `logs-prod.grafana.net` | 동일 |
| `https://logs.example.net:8443/push` (대조) | `logs.example.net:8443` | 동일 |

http(s)가 아닌 scheme의 `else` 분기가 더 나빴습니다 — `sink_url`을 그대로 반환하므로 query string에 담긴 토큰까지
통째로 노출됩니다. 문서화된 Grafana Cloud Loki push 형식이 바로 userinfo 형태라서, 가설이 아니라 운영에서 나오는
설정입니다. 그리고 이 저장소가 같은 control에 스스로 적는 release criterion이
`src/sdp_core/enterprise.py:147` — "Health and metrics endpoints are exposed without source credentials." 입니다.
즉 **자기 기준을 자기 응답이 위반**하고 있었습니다.

수리: `_redacted_sink_target()`을 추가해 모든 scheme에서 host(:port)만 보고합니다. `parsed.hostname`/`parsed.port`는
userinfo와 query를 포함하지 않고, 읽을 수 없는 authority는 raw URL이 아니라 `redacted` 표식이 됩니다(잘못된 port
문자열에 `ValueError`가 나는 경우도 포함).

검증: RED 선확인(단위 3건 + `/enterprise/observability` end-to-end 1건 실패 → 통과). 기존 테스트 1건이
`target == "tcp://opaque-target"`로 **raw URL 반환을 고정**하고 있었으므로 함께 고쳤습니다(이제 `opaque-target`).
전체 **295 passed / 8 skipped**, Hypothesis fuzz mirror 10 passed, `sdp.demo_smoke` ready=true.

### 감사 큐 소진 (3) — browse 403이 보호하던 payload가 catalog 상세에 그대로 있었습니다 (2026-10-14)

`GET /browse/{dataset_id}/schema`는 tenant/role/sensitivity 정책을 평가해 403을 돌려주고 그 거부를 감사
기록에 남깁니다. 그런데 같은 익명 호출자가 `GET /catalog/datasets/{dataset_id}`에서 **같은 스키마를 `pii`
플래그까지 붙은 채로** 받고 있었습니다. 직접 재현했습니다.

| 호출 (actor 없음) | 결과 |
| --- | --- |
| `GET /browse/crm-customer-master/schema?user=nobody` | `403 tenant boundary denied` |
| `GET /catalog/datasets/crm-customer-master` | `200` |
| └ `source_system` | `postgresql://analytics.dw/customer` |
| └ `schema`의 pii 컬럼 | `['customer_email']` |
| └ `profile` | `{'row_count': 1200000, 'updated_at': ...}` |
| └ policy decision / audit event 증가분 | `0` / `0` |

`GET /catalog/datasets`(목록)도 같은 `Dataset.model_dump()` 전체를 **모든 데이터셋에 대해** 돌려주고 있어서,
상세만 고치는 것은 의미가 없었습니다. 즉 접근 제어가 단지 없는 것이 아니라 **우회 가능**했고, 그게 더 나쁩니다.

수리 범위를 고르는 데 판단이 필요했습니다. discovery 라우트를 정책 게이트 뒤로 보내면 README에 공개로 적힌
라우트가 403이 됩니다 — 그건 "카탈로그는 공개 발견 표면인가"라는 제품 posture 결정이고, 저장소 문서가
정하지 않은 사항입니다. 그래서 **더 작고 모호하지 않은 쪽**을 택했습니다: 라우트는 문서대로 200으로 두고,
governed 필드를 payload에서 뺍니다. `catalog.discovery_view()`가 `schema`(및 `pii`/`quality_issues`),
`source_system`, `profile`, `tenant_id`을 withhold하고 형태 정보는 `schema_field_count`로 대체합니다.
스키마의 공개 지점은 정책을 평가·감사하는 browse 경로 하나로 남습니다.

payload key 집합을 고정하는 contract test를 함께 넣었습니다. `Dataset`에 필드가 추가될 때 인증 없는
payload로 자동 편입되지 않고 publish/withhold를 명시적으로 결정하게 됩니다(deny-list의 fail-open 성질 보완).

검증: RED 2건 선확인 → 수리, 전체 **297 passed / 8 skipped**, `sdp.demo_smoke` ready=true.
기존 상세 테스트는 `id`/`status`/`metadata_recommendation_score`만 확인하고 있어 governed 필드를 고정한
테스트는 **하나도 없었습니다** — 즉 이 payload는 계약이 아니라 `model_dump()`의 부작용이었습니다.

### 감사 큐 소진 (4) — preview가 어떤 데이터셋을 물어도 같은 CRM row를 돌려줬습니다 (2026-10-14)

보고된 내용("다른 dataset_id를 대면 PII 마스킹이 우회된다")보다 실제가 더 나빴습니다. `browse.preview()`는
**고정된 CRM row 집합 하나**를 모든 데이터셋에 돌려주면서, 마스킹 목록은 *지정된* 데이터셋의 `pii`
플래그에서 계산했습니다. 직접 재현한 전수 결과입니다.

| dataset_id | `masking_summary` | `rows[0]['customer_email']` |
| --- | --- | --- |
| `crm-customer-master` | `['customer_email']` | `***` |
| `crm-event` | `[]` | `alice@example.com` |
| `marketing-campaign` | `[]` | `alice@example.com` |
| `sales-order` | `[]` | `alice@example.com` |
| `semantic-glossary` | `[]` | `alice@example.com` |

응답의 `columns`와 `rows`도 서로 다른 데이터셋을 가리켰습니다 (`semantic-glossary`는
`columns=['concept_uri', ...]`인데 row는 CRM 필드). 그리고 `DemoSQLConnector.preview()`가 이 함수에
위임하므로 connector 경로도 같이 새고 있었습니다.

이는 저장소가 스스로 광고하는 control을 무효화합니다. `sdp_core/demo_seed.py:65`의 데모 체크포인트가
"PII 컬럼이 preview/query에서 마스킹되고 policy decision id가 남는지 확인한다"이고,
`connectors._IMPLEMENTED_PROOF["pii_masking"]`가 바로 이 엔드포인트를 그 control의 증빙으로 지목하며
`connector_probe`가 이를 `ready_for_demo` 판정에 계산해 넣습니다.

수리는 근본 원인을 닫습니다. `_sample_rows()`가 샘플 값을 **데이터셋의 선언 스키마에 투영**해 row를
만듭니다 — 데이터셋이 선언하지 않은 컬럼은 들어갈 칸이 없으므로 어떤 dataset_id로도 남의 PII 컬럼에
도달할 수 없고, `columns`/`rows` 불일치도 사라집니다. 마스킹은 **floor**로 바꿨습니다: 정책 obligation과
데이터셋이 `pii`로 선언한 컬럼의 합집합을 마스킹하고 실제 적용 집합을 응답·감사에 보고합니다. 데모 가치는
오히려 올라갑니다 — 각 데이터셋이 자기 스키마에 맞는 row를 보여줍니다.

검증: RED 2건 선확인(3번째는 회귀 방지 대조군) → 수리, 전체 **300 passed / 8 skipped**,
`tests/fuzz` 10 passed, `sdp.demo_smoke` ready=true.

### 감사 큐 소진 (5) — NOT NULL tenant 컬럼이 사실상 상수였습니다 (2026-10-14)

`stores.py:21,25` 두 건은 같은 결함의 두 면이라 한 묶음으로 처리했습니다. `PostgresEvidenceStore`는
`tenant_id TEXT NOT NULL`과 tenant 선행 인덱스(`idx_*_tenant_resource_created`)로 행을 scope하는데, 그
값을 읽는 helper 두 개가 `or "demo"` fallback을 갖고 있었고 생산 측은 대부분 tenant를 전달하지 않았습니다.
**`demo`는 이 제품의 실제 tenant(seed 데이터셋 소유자)이므로**, 이 fallback은 값을 잃는 것이 아니라 남의
tenant로 행을 오귀속시킵니다. tenant=`acme-corp` 데이터셋을 심고 직접 재현했습니다.

| 분기 | 저장되던 tenant | 수리 후 |
| --- | --- | --- |
| deny tenant boundary | `acme-corp` (유일하게 stamp하던 분기) | 동일 |
| deny external-export / mutation role | `demo` | 소유 tenant |
| deny missing dataset (`obligations={}`) | `demo` | actor tenant |
| allow create / search | `demo` | actor tenant |
| audit event 전부 (`details['tenant_id']`를 쓰는 코드가 없었음) | `demo` | 소유 tenant |

가장 날카로운 결과: `acme-customer-master`에 대한 **tenant 경계 위반 거부 감사 기록** — tenant 격리
감사자가 정확히 찾는 그 행 — 이 `demo` 아래 들어갔습니다. tenant-scoped 질의는 자기 행을 놓치고 남의 행을
봅니다. NOT NULL + 인덱스가 붙은 컬럼이 상수에 가까우면 컬럼이 없는 것보다 나쁩니다. 소비자가 신뢰하기 때문입니다.
같은 resource에 대한 결정이 분기에 따라 `acme-corp`과 `demo`로 갈리므로, 컬럼이 *누구의* tenant를
뜻하는지조차 일관되지 않았습니다.

수리: `policy._effective_tenant_id()`가 존재하는 데이터셋이면 소유 tenant, 데이터셋을 지칭하지 않는
행위(`create`/discovery/없는 resource)면 actor tenant를 돌려주고 `_decision()`이 모든 분기에 stamp합니다
(명시값 보존). `catalog.ingest_event()`와 `_build_dataset_payload()`가 audit event에 같은 값을 넣습니다.
store fallback은 `UNRESOLVED_TENANT_ID`로 바꿨습니다 — 귀속 불가 행은 어떤 tenant도 소유하지 않고 데이터
품질 신호로 남습니다. 레거시 backfill DDL 두 곳도 같은 marker를 쓰고, JSON에서 꺼낸 빈 문자열도 unresolved로
취급합니다(이전에는 `COALESCE`가 `''`를 통과시켜 NOT NULL만 만족하는 빈 tenant가 남았습니다).

검증: RED 9건 선확인 → 수리, 전체 **313 passed / 8 skipped**, `tests/fuzz` 10 passed,
`sdp.demo_smoke` ready=true.

### 감사 큐 소진 (6) — 마이그레이션이 끝까지 실패해도 컨테이너가 서비스를 시작했습니다 (2026-10-14)

`docker/entrypoint.sh`의 재시도 루프는 30회 실패 후 `break`로 빠져나와 `exec "$@"`로 떨어졌습니다. 즉
**스키마가 한 번도 적용되지 않은 데이터베이스를 상대로 서비스가 뜹니다.** 실제 스크립트를 `sh`로 실행해
재현했습니다 — `python` stub을 항상 실패하게, `sleep` stub을 즉시 반환하게 PATH에 올리면 60초 대기 없이
30회 루프가 돌고, 앱 커맨드가 **실행되어 marker 파일이 생겼습니다**(종료 코드 0).

루프는 "DB가 아직 안 떴다"와 영구 실패(잘못된 DSN, 실패하는 마이그레이션)를 구분할 수 없으므로, 영구
실패도 60초를 태우고 나서 무시됩니다. `/health`는 DB를 보지 않으므로 컨테이너는 정상으로 보고되고,
`graph_store.build_store()`는 DSN이 있을 때 `readiness()`를 확인해 **fail-closed로 `RuntimeError`를
던지므로**, 결과는 "healthy한 컨테이너 뒤에서 요청마다 실패"입니다. README 82행이 적은 계약
("기동 시 마이그레이션 + 시드를 멱등하게 적용합니다")과도 어긋납니다.

수리: `break`를 `exit 1`로 바꿨습니다. 부트스트랩 실패는 컨테이너 기동 실패여야 하고, orchestrator의 재시작
정책이 실제 원인을 드러내게 합니다.

검증: `tests/test_container_entrypoint.py`가 실제 스크립트를 `sh`로 돌립니다 — RED 1건 선확인(marker 생성 +
exit 0) → 수리 후 marker 없음 + 비정상 종료. 대조군 2건(마이그레이션 성공 시 앱 기동, DSN 없으면 in-memory
backend로 기동)은 수리 전후 모두 통과. `sh -n`으로 문법 확인, 전체 **316 passed / 8 skipped**.

### 감사 큐 소진 (7) — 동기 sink export가 event loop를 막아 요청을 직렬화했습니다 (2026-10-14)

`record_request_observability` 미들웨어는 `async def`인데, `finally`에서 호출하는
`_export_to_sink()`는 blocking `urlopen`(또는 파일 append)입니다. 즉 **sink 왕복이 event loop
스레드에서 실행**되어 동시 요청 전부가 그 뒤에 줄을 섭니다. 측정했습니다 — `httpx.ASGITransport`로
실제 앱에 `/health` 8개를 동시에 던지고, `urlopen`을 0.2초 sleep으로 치환했습니다.

| | 수리 전 | 수리 후 |
| --- | --- | --- |
| 8개 동시 요청 소요 | **1.63s** | **0.23s** |
| sink 왕복 1회(0.2s) 대비 | 8.1x (완전 직렬화) | 1.1x |
| 완전 직렬화 기준선 | 1.60s | — |

기본 `SDP_LOG_SINK_TIMEOUT_MS=500`이므로 sink가 죽으면 요청 10개가 ~0.5초가 아니라 ~5초를
직렬로 소모합니다. 이것은 성능 취향이 아니라 가용성 결함입니다 — telemetry sink 하나가 API 전체의
처리량 상한이 됩니다.

수리: `record_request_observation_async()`를 추가해 미들웨어가 이를 await합니다. ring buffer append는
**동기로 유지**해 요청이 끝난 즉시 `/metrics` 독자에게 보이고 순서가 흔들리지 않게 했고, blocking sink
write만 `anyio.to_thread.run_sync`로 worker 스레드에 넘깁니다. 동기 `record_request_observation()`은
그대로 두었습니다(테스트·비-loop 호출자용 진입점이며 `production.py` 증빙도 두 함수를 함께 가리킵니다).

**남은 경계(확장하지 않았습니다):** 각 응답은 여전히 *자기* export를 기다리며, 그 상한은 문서화된
`SDP_LOG_SINK_TIMEOUT_MS`입니다. 이번 수리가 없앤 것은 *다른* 요청들이 그 뒤에 직렬화되는 현상입니다.
응답과 export를 완전히 분리하려면 fire-and-forget 태스크와 종료 시 drain 정책이 필요하고, 그건 보고된
결함의 범위를 넘습니다.

검증: RED 선확인(동일 테스트가 1.62s로 실패) → 수리 후 통과. 임계값은 "완전 직렬화의 1/2"로 느슨하게
두어 머신 속도가 아니라 blocking 성질을 측정합니다. async 분기 2건(export=False, sink 실패 시 오류
기록만 하고 요청을 깨지 않음)도 동기 쪽과 동등하게 덮었습니다. 전체 **319 passed / 8 skipped**,
`tests/fuzz` 10 passed, `sdp.demo_smoke` ready=true.

### 감사 큐 소진 (8) — mutation 인가 가드에 테스트가 없었습니다 (2026-10-14)

마지막 항목은 코드 결함이 아니라 **커버리지 공백**이었습니다. 먼저 돌아가는 앱에 직접 물어
가드가 실제로 동작하는지 확인했습니다 — 결함이 아님을 확인하는 것이 먼저입니다.

| actor | publish | patch | deprecate |
| --- | --- | --- | --- |
| `admin` | 200 | 200 | 200 |
| `analyst` | 403 | 403 | 403 |
| `guest` | 403 | 403 | 403 |
| `anonymous` | 403 | 403 | 403 |
| `actor` 키 자체를 생략 | 403 | 403 | 403 |

가드는 정확합니다. 그런데 이를 고정하는 테스트가 없었습니다. `test_create_requires_admin`은
`create` 하나만 덮고, `test_dataset_mutation_policy_and_lifecycle`은 세 verb를 **`admin`으로만**
구동하는 happy path입니다. `tests/test_policy.py`는 정책 함수 수준에서 `patch` 하나만 덮고 있었습니다.
즉 라우트 수준 인가는 세 verb 모두 무방비였습니다.

테스트가 실제로 효력이 있는지 **가드를 제거한 mutant로 검증**했습니다(이 경우 RED가 자연히 나지
않으므로 이것이 RED의 등가물입니다). `if decision.effect != "allow": raise HTTPException(403)`을
6개 지점에서 모두 지우고 돌렸습니다.

| | 결과 |
| --- | --- |
| `test_catalog_mutation_guard_denies_non_admin_actors` 12건 | **전부 실패** (가드 제거를 잡음) |
| `test_catalog_mutation_denial_is_recorded_as_evidence` 3건 | 통과 |

살아남은 3건이 무엇인지도 확인했습니다. `evaluate()`는 `raise`를 지워도 여전히 deny decision을
기록하므로, 증빙 테스트는 **기록**을 고정하고 **집행**은 고정하지 않습니다. 둘은 다른 것을 재는
테스트이고 합쳐서 완전합니다 — 집행은 앞의 12건이, 기록은 뒤의 3건이 책임집니다. 전자는 거부
*후* 상태가 변하지 않았는지(`status`/`title` 불변)까지 확인합니다. 변경 후 거부하는 가드는 가드가
없는 것보다 나쁩니다.

검증: 전체 **334 passed / 8 skipped**. mutant는 복원했고 `git diff`로 `api.py`에 미커밋 변경이
없음을 확인했습니다.

**이로써 2026-10-14 감사 큐 11건이 모두 소진되었습니다.** 9건은 직접 재현한 결함(수리), 1건은
커버리지 공백(테스트 추가), 그리고 큐에 올라온 `api.py:427`은 목록 라우트까지 범위가 넓어져
2건으로 처리되었습니다.

### 감사 큐 소진 (4) 후속 — 같은 누출이 schema-history에 남아 있었습니다 (2026-10-14)

소진 (4)에서 discovery 표면의 `schema`를 withhold했는데, **형제 라우트를 전수 확인하니 같은 값이
한 곳에 더 남아 있었습니다.** 부분 수리는 수리가 아니므로 이어서 닫았습니다. 익명 호출자로 11개
라우트를 모두 찔러 측정했습니다.

| 라우트 | `pii` 플래그 | `postgresql://` | `example.internal` |
| --- | --- | --- | --- |
| `/catalog/datasets/{id}/schema-history` | **YES** → 제거 | - | - |
| `/catalog/datasets/{id}/jsonld` | - | - | YES (의도된 DCAT distribution) |
| `/profile`, `/schema-versions`, `/join-candidates`, `/validate`, `/semantic-validation`, `/lineage`, `/related`, `/audit`, `/catalog/search` | - | - | - |

`schema-history` snapshot은 `_column_signature()` = `column.model_dump(exclude_unset=True)`이므로
`{"name": "customer_email", ..., "pii": true}`를 그대로 내보냈습니다. `schema-diff`의
`changed_columns`도 `before`/`after`에 완전한 컬럼 dict를 싣습니다.

`discovery_column_view()`가 `pii`/`quality_issues`를 제거한 **사본**을 투영합니다. 저장 snapshot은
완전한 상태를 유지합니다 — drift 탐지가 그것을 읽기 때문입니다(전용 테스트로 in-place 제거가
아님을 고정했습니다). `pii` 재분류는 그 자체가 실제 schema drift이므로, 투영 때문에 신호가 사라지면
수리가 가치를 파괴합니다. 그래서 diff는 해당 컬럼을 계속 changed로 보고하고
`changed_withheld_fields: ["pii"]`로 **어떤 withhold 필드가 바뀌었는지**는 알리되 분류값은 공개하지
않습니다.

`/jsonld`의 `example.internal` endpoint는 누출로 보지 않습니다. DCAT 내보내기의 목적이 distribution
endpoint 공개이고, `distributions`는 discovery view에도 의도적으로 남겨 두었습니다. 경계를 바꾸려면
제품 결정이 필요하므로 범위를 넓히지 않았습니다.

검증: RED 2건 선확인 → 수리, 대조군 1건(저장 snapshot 불변)도 함께. 전체 **337 passed / 8 skipped**,
`tests/fuzz` 10 passed, `sdp.demo_smoke` ready=true, 11개 라우트 재측정으로 `pii` 소멸 확인.

### 독립 다중 렌즈 감사 (2026-10-14) — 32건 발견, 직접 재현 후 수리

이전 감사 큐(11건)를 소진한 뒤, 같은 방식을 신뢰하지 않고 **독립적인 8개 렌즈**로
다시 쓸었습니다(authz 공개 범위, tenant 격리, 자격증명 노출, 비신뢰 입력, 증빙 무결성,
가용성, 컨테이너·공급망, 계약 드리프트). 렌즈별로 발견을 모으고 각 발견마다 **서로 다른
관점의 반박자 3명**(control flow / 재현 / 영향)을 붙였습니다. 7개 렌즈가 32건을
보고했습니다.

**중요한 방법론 한계를 먼저 적습니다.** 저는 감사가 돌아가는 동안 확인된 항목을 먼저
고쳤습니다. 그래서 반박 단계가 **"이미 수리됨"을 이유로 refute**하기 시작했습니다 —
반박자들은 현재 트리를 정확히 읽고 "이 발견은 수리 이전 head를 서술한다"고 판정했습니다.
따라서 이 워크플로의 최종 `confirmed` 목록은 **실재성의 척도가 아니라** 제 동시 수리의
부작용입니다. 그 목록을 "32건 중 N건만 진짜였다"로 읽으면 틀립니다.

실제 판정 기준은 **제가 직접 재현했는지**입니다. 아래가 그 결과입니다.

| 수리 | 직접 측정한 증거 |
| --- | --- |
| evidence 읽기 경로 tenant scope 부재 | 미인증 `GET /audit/events` 한 번에 `{'bank-a': 1, 'bank-b': 1}`. 읽기 경로 **어느 함수에도 tenant 파라미터가 없었음** — 오늘 아침 제 stamp 수리가 소비자 없는 절반이었다는 뜻 |
| `create`가 tenant 검사 건너뜀 | `data-admin`(tenant demo, platform-admin 아님)이 `tenant_id=acme-bank`로 심기 → 200, 같은 자산 PATCH/PREVIEW → 403 |
| 그래프 표면 | `/graph/nodes/{id}` 인가 전무, `pii: true` 공개. traversal이 공유 concept 노드를 지나 depth 2에서 타 tenant 도달 — 진입 게이트만으로 불가 |
| connector probe | `postgresql://svc_user:S3cr3t-Pa55@payroll.acme.internal:5432/payroll`을 **미인증** 호출자에게, 타 tenant `critical` 자산에 대해 |
| SQL validator (재발) | `pg_catalog.sales`, `otherdb.otherschema.sales`, `JOIN finance.sales` 모두 통과 — leaf만 비교. **제가 오늘 추가한 대조군에 `analytics.customer`를 "허용"으로 넣은 것이 바로 그 구멍** |
| `/profile` (재발) | `row_count: 1200000`과 컬럼별 `quality_issues`를 actor 없이. **제 형제-라우트 스윕이 리터럴 마커 3개만 grep해서 clean으로 표시** |
| patch 감사 기록 | 패치된 `source_system` DSN이 `changes`/`before`/`after` 세 군데에 |
| `append_audit_event` | store 없으면 이벤트를 버리면서 `audit_event_id`는 반환 — platform-admin 부여 기록이 사라짐 |
| ontology steward 서명 | 익명 승인 + body로 `reviewed_by: biz-admin` 위조, 증빙 0건 |
| 자원 상한 | 2 MiB semantic query → 2.87s CPU, `search_catalog` 2000토큰 → 5.10s, 5만 자 patch 제안에 **정책 평가 0건**, 없는 데이터셋 preview가 audit +5 / policy +0 |
| 계수기 포화 | `sdp_request_observations_total`이 buffer 500 대비 **25에서 멈춤** |
| `_relationship_label` | `$`가 개행 앞에서도 매칭 → `KeyError('\n')` → 500 |
| pagination 강제 변환 | JSON 배열/객체에 `TypeError` → 500 |
| `file://` sink | 절대 서버 경로와 UNC 내부 호스트명을 공개 manifest에 |
| healthcheck | Dockerfile + compose 2곳이 상수 `/health`를 조회 — 백엔드 죽은 컨테이너가 healthy |
| 앱 포트 | DB는 `127.0.0.1`인데 앱 3개는 모든 인터페이스에 공개 |
| `/app` 소유권 | 서빙 uid가 자기 `PYTHONPATH`를 소유 |

**세 건은 오늘 제 수리의 형제 경로였습니다** (governed 필드, SQL validator, sink
redaction). 패턴이 분명합니다 — 수리는 맞았지만 **같은 결함 부류의 다른 경로를 전수
확인하지 않았습니다.** 특히 `/profile`은 제가 "11개 라우트를 쓸었다"고 적은 그 스윕이
놓친 것인데, 원인은 제가 **방금 정의한 governed 필드 목록과 대조하지 않고 리터럴 문자열
3개만 grep**했기 때문입니다. 마커 검색은 경계 검증이 아닙니다.

**에이전트 보고를 정정한 것 3건:**
1. ontology review로 `buyer_handoff_ready`를 true로 되돌릴 수 있다 → **거짓**. 측정값은
   `False -> False`. 실재하는 것은 미인증 승인과 reviewer 위조입니다.
2. `/catalog/search` 4000토큰으로 93.4초 → **HTTP로 재현 불가**. httpx가 URL 길이로
   클라이언트 측에서 거절하고 실제 edge도 request-line 한계를 갖습니다. 서버 내부
   호출로는 5.10초를 확인했으므로 비용은 실재하나 도달 경로는 좁습니다.
3. RBAC 매트릭스가 코드에 반박된다 → **진단이 어긋남**. 매트릭스는 역할 단위로 일관되고
   `platform-admin` 행은 정직합니다. 실제는 seed가 그 역할을 `admin`/`security` subject에
   묶는다는 **불완전한 공개**였습니다.
4. 한 에이전트가 기준선을 "345 passed"로 보고 → 실제 **337**. 에이전트의 숫자는 제가
   확인하기 전까지 증거가 아닙니다.

**제품 결정이어서 남긴 것:** `security`가 `platform-admin`을 들고 있어야 하는지.
역할을 빼앗는 쪽이든 매트릭스를 바꾸는 쪽이든 의도를 알아야 고를 수 있으므로, 번들링을
공개하고 scope 주장이 grant보다 좁아지면 깨지는 contract test만 두었습니다.

### pgvector 빌드 입력 핀 — 기록만 했던 항목을 닫았습니다 (2026-10-26)

`docker/postgres-age-pgvector.Dockerfile`은 pgvector를 **가변 GitHub 태그 URL**에서
받아 체크섬·서명 검증 없이 root로 컴파일해 `make install`했습니다. 이 저장소에서
digest/commit SHA/hash로 고정되지 않은 **유일한 빌드 입력**이었습니다. governed 그래프와
증빙 데이터를 담는 Postgres 서버에 들어가는 확장이므로 공급망 관점에서 실재하는 결함입니다.

**2026-10-14에는 고치지 않고 기록만 했습니다.** 이 컨테이너에서 해당 tarball을 받을 수
없기 때문입니다 — `curl https://github.com/pgvector/pgvector/archive/refs/tags/v0.7.4.tar.gz`가
프록시에서 **403**입니다. 따라서 진짜 sha256을 계산할 수 없고, **검증하지 않은 해시를 적는
것은 핀이 아니라 핀의 외관**입니다(그 쪽이 더 위험합니다 — 이후 아무도 다시 확인하지
않습니다). 그때 적어 둔 대안이 두 가지였고, 그중 두 번째가 **이 환경에서 가능하다는 것을
확인하지 않은 채** 미결로 남아 있었습니다.

**가능했습니다. git 프로토콜은 프록시를 통과합니다.** tarball HTTP 요청만 403입니다.

```
$ git ls-remote https://github.com/pgvector/pgvector refs/tags/v0.7.4
103ac50f1a90b47a72003e8e8628a55ec372f202	refs/tags/v0.7.4
```

peeled `^{}` ref가 advertise되지 않으므로 `v0.7.4`는 lightweight 태그이고 위 이름이
**커밋 자체**입니다. 그 객체를 실제로 받아 확인했습니다 — 타입 `commit`, subject
`Version bump to 0.7.4 [skip ci]`, tree `97af667455d30dba56b092ce3b9241b991f7f888`,
tree에 `Makefile`·`src/`·`sql/`·`vector.control`이 있고 `vector.control`의
`default_version`은 `'0.7.4'`입니다.

#### 수리

tarball 다운로드를 **객체 이름을 지정한 git fetch**로 교체했습니다. 핀을 강제하는 것이
git 자신이라는 점이 핵심입니다 — `git fetch <sha>`는 받은 객체가 요청한 이름으로
해시되는지 검증하므로, 같은 이름으로 다른 내용을 주는 서버는 빌드를 **실패시킵니다**.
`git clone --branch <tag>`는 그 검증을 하지 않으므로 핀처럼 보이지만 핀이 아닙니다.

`PGVECTOR_VERSION`은 이미지 라벨로만 남기고, pin된 tree의 `vector.control`이 선언하는
버전과 빌드 중에 대조합니다. 커밋 이름이 이미 내용을 고정하므로 이 대조는 핀을 강화하지
않습니다 — 두 ARG가 따로 움직여 **이미지가 담고 있지 않은 버전을 라벨로 붙이는 것**을
막습니다. `curl`은 더 이상 설치하지 않습니다(root로 컴파일하는 레이어에 fetch 도구를
남기지 않습니다).

#### 이 핀의 한계 — 적어 둡니다

git 객체 이름은 SHA-1이므로 **sha256 content digest보다 약하고**, 가변 태그보다는
확실히 강합니다. tarball에 닿을 수 있는 환경에서 실제로 계산한 sha256으로 교체하는 것은
그대로 개선입니다. 여기서 `git archive`로 tarball을 재현해 해시를 계산하지는 않았습니다 —
GitHub의 archive 엔드포인트는 prefix·gzip 설정·mtime이 고정된 자기 형식을 쓰므로
byte 단위로 재현되지 않고, 재현되지 않은 해시는 다시 핀의 외관일 뿐입니다.

#### 회귀 가드

`tests/test_build_input_pinning.py` 10건. 고장났던 **그 파일을 지목하지 않고** 저장소의
모든 Dockerfile을 찾아 검사합니다 — 나중에 추가되는 두 번째 미고정 입력도 같은 결함이고,
파일 이름을 적어 둔 가드는 자기 목록과 대조하는 가드입니다(이 저장소가 반복해서 배운 구분).
`FROM`은 `@sha256:` digest를, 소스 archive는 가변 ref URL 금지를, 빌드 중의 git
fetch/clone은 40-hex 객체 이름을 요구하고, `*_COMMIT` ARG의 기본값도 같은 형식을
요구합니다. Dockerfile의 line continuation과 주석을 Docker와 같은 방식으로 접어
읽습니다(주석 줄에 산문이 있고 한 `RUN`이 여러 줄에 걸쳐 있으므로, raw 줄 단위로 읽는
검사는 명령과 그 플래그를 다른 줄로 갈라 놓고 놓칩니다).

역검증 5건, 모두 실패를 확인했습니다: 가변 태그 tarball 복원(2건 실패), 태그 ref로
git fetch(2건), 버전 대조 제거(1건), 축약 커밋 이름(2건), base image 태그만(1건).

### 병합 게이트 실측 (2026-10-14)

감사 큐를 소진한 뒤 병합 가능성을 다시 측정했습니다. **열린 비-draft PR 7건 전부 APPROVED 리뷰가
0건**이고, 이것이 유일한 구속 조건입니다. 아래는 추측이 아니라 API 응답입니다.

| PR | head | mergeable_state | 리뷰 | 비고 |
| --- | --- | --- | --- | --- |
| #112 | `dec20969` | blocked | 0건 | 실패 3건(billing lock) |
| #111 | `7ec43999` | blocked | 0건 | |
| #109 | `409ae68d` | blocked | 0건 | |
| #107 | `742e7a7e` | blocked | 0건 | |
| #104 | `2856e91f` | blocked | COMMENTED 5건 | **실패 0건**, 성공 25 / skipped 9, 리뷰 스레드 2건 모두 resolved |
| #102 | `9d97a7e0` | unstable | COMMENTED 3건 | 체크 2건 모두 실패(billing lock) |
| #82 | `93321a98` | blocked | COMMENTED 5건 | |

`CHANGES_REQUESTED` 리뷰는 **한 건도 없습니다** — 7건 모두 `COMMENTED`뿐입니다.

저장소 ruleset(`Lock default branch`, id `18259549`)을 읽었습니다. 핵심은
`required_approving_review_count = 0`입니다 — **GitHub 자체는 승인을 요구하지 않습니다.**
함께 걸린 것은 `required_review_thread_resolution = true`,
`require_extra_approval_for_unattributed_changes = true`, `dismiss_stale_reviews_on_push = true`이고,
이 ruleset에는 required status check 규칙이 **없습니다**(중앙 필수 워크플로는 org 레벨에서 옵니다. org
ruleset은 이 세션 권한으로 403이라 직접 읽지 못했습니다).

#104가 왜 `blocked`인지 추적했습니다. 승인 요구 0, 실패 0, 스레드 resolved, 커밋 4건 전부
`seonghobae` 계정에 귀속(unattributed 아님) — 그런데도 blocked입니다. 남은 non-success 컨텍스트는
**skipped 9건**뿐이고 그 중 6건이 중앙 security 게이트 job입니다.

| skipped 컨텍스트 | |
| --- | --- |
| `osv-scan` / `dependency-review` / `trivy-fs` | 중앙 Security Scan 3종 |
| `gitleaks (secret scan)` / `scorecard` / `strix` | 중앙 보안 게이트 |
| `Dispatch current-head CodeQL scan` / `cancel-closed-pr-runs` / `publish-manual-pr-evidence-status` | |

#104는 문서 전용 PR이므로 `Detect changed scope` 게이트(성공 4건)가 이 job들을 올바르게 skip했습니다.
**required 컨텍스트가 `skipped`로 끝나면 `success`가 아니므로 영구히 blocked됩니다.** 이것은 중앙
`.github`의 CLAUDE.md가 경고하는 바로 그 실패 양식입니다 — "always keep one job with no
output-dependent `if:` so the run concludes `success` rather than `skipped`". 다만 org ruleset을
읽지 못했으므로 이 6건이 실제로 required라는 것은 **추론이고 확정이 아닙니다**. `unstable`인 #102가
그 컨텍스트를 아예 보고하지 않았는데도 `blocked`이 아닌 점은 이 추론과 맞지 않으며, 확정에는
org ruleset 읽기 권한이 필요합니다.

#102의 커밋 100건 중 4건(`254054d6`, `f5c50b3f`, `63b8d937`, `6f5918e3`, git email `seonghobae@me.com`)은
GitHub 계정에 귀속되지 않아 `require_extra_approval_for_unattributed_changes`를 추가로 발동시킵니다.
이 세션이 만든 커밋 7건은 모두 `claude` 계정에 정상 귀속되는 것을 확인했으므로(`noreply@anthropic.com`)
히스토리 재작성은 하지 않았습니다 — 열린 PR의 100커밋을 force-push하는 비용이 이득을 넘고, 어차피
거버넌스가 요구하는 동일한 승인 1건으로 함께 해소됩니다.

**근본 원인은 변하지 않았습니다**: 계정 수준 Actions billing lock으로 hosted job이 dispatch 전에
거부되므로(`runner=""`, 3~4초, `The job was not started because your account is locked due to a billing
issue.`), 새 head에서 required check가 green이 될 수 있는 경로가 없습니다. 이 세션이 할 수 없는 일로
남은 것: 독립 승인, billing 해제, artifact storage 회수, isolated runner 용량 등록.

## paid-pilot gate가 제품을 깨뜨리는 값으로 통과했습니다 — 필수 변수 둘, 문서 누락 9건 (2026-10-26)

alert 전달 라운드 뒤 "이번 변경이 만든 환경 변수가 문서에 들어갔는가"를 확인하다 발견했습니다.
`SDP_ALERT_TIMEOUT_MS`가 README에 없다는 한 건으로 시작해 그 부류 전체를 세었습니다 — `src/`가
읽는 `SDP_` 이름 23개 중 **9건**이 README나 CLAUDE.md 중 한쪽 이상에서 누락이었고, 그중 둘이
`required_environment`였습니다.

### 두 건은 문서 문제가 아니었습니다

`GET /enterprise/production-readiness`가 `SDP_CONNECTOR_VAULT_PROVIDER`·
`SDP_CONNECTOR_TIMEOUT_MS`를 `missing_environment`로 **이름을 공표하면서** `paid_pilot_ready`를
막고 있었는데, 그 변수가 무엇이고 어떤 값을 넣어야 하는지 어느 문서에도 없었습니다. 조치할 수
없는 blocker를 공표하는 것은 blocker가 없는 것보다 나쁩니다.

그리고 `_is_set`은 비어 있지 않은 문자열만 봅니다. 운영자가 자연스럽게 고를 값으로 그 구멍에
닿습니다 — 측정:

```
SDP_CONNECTOR_VAULT_PROVIDER='vault'       gate 통과, probe 라우트 400
SDP_CONNECTOR_VAULT_PROVIDER='hashicorp'   gate 통과, probe 라우트 400
SDP_CONNECTOR_TIMEOUT_MS='2s'              gate 통과, probe 라우트 400
```

`vault`·`hashicorp`는 운영자가 쓰는 제품 이름이고 `2s`는 사람이 timeout을 적는 방식입니다. 즉
readiness가 진척을 보고하는 동안 connector probe가 네 connector 전부에 400을 돌려주고 있었습니다.
required 변수 전수를 같은 방식으로 찔러 본 결과 이 둘만 해당했습니다 — 나머지는 presence 검사가
정직한 한계인 것들(DSN·issuer 등 이 모듈이 닿을 수 없는 대상)입니다.

**이것은 `SDP_EVIDENCE_RETENTION_DAYS` 결함보다 나쁩니다.** 그쪽은 아무것도 하지 않는 값으로
gate를 통과시켰고, 이쪽은 gate가 측정한다고 주장하는 능력을 **깨뜨리는** 값으로 통과시켰습니다.

### 수리

registry가 값 도메인을 `environment_value_rules`로 선언합니다(의도적으로 닫힌 형태 — 열거된 값
집합, 또는 하한 있는 정수. regex도 callable도 없습니다). manifest는 설정됐지만 거절된 값을
`rejected_environment`에 이유와 함께 따로 공표합니다 — `missing`과 합치면 변수를 방금 설정한
운영자가 이름의 오타를 찾으러 가기 때문입니다.

**역방향 검사가 과잉 선언 하나를 잡았습니다.** `minimum=1`을 선언했는데 `int()`는 `0`·`-5`를
받아들였습니다. gate가 코드에 없는 요구를 발명하는 것은 gate가 느슨한 것과 같은 결함이므로,
수리를 gate가 아니라 `credentials.connector_secret_status`로 옮겼습니다 — `timeout_ms`는 probe의
control evidence로 **공표되는 값**이고 `0`은 timeout으로서 거짓 공표된 숫자이므로 읽는 지점에서
검증하는 것이 맞습니다. registry는 그 도메인을 거울처럼 선언합니다.

### 구조적 원인과 가드

README에는 환경 변수가 본문 여기저기 산문으로만 있어서 **어디도 전수 목록이 아니었습니다**. 그것이
9건이 잊힌 이유이므로 `## 환경 변수 전수 목록` 표를 넣었습니다 — 23개 전부, 측정한 기본값,
paid-pilot gate 여부, 값 도메인.

가드 8건. `tests/test_environment_documentation.py`는 변수 집합을 `src/`에서 **파생**해 양쪽
문서에 있는지와 역방향(코드가 읽지 않는 변수를 문서가 약속하지 않는지)을 확인합니다. 문자열
리터럴 기준인 이유: 이 저장소는 `os.getenv`·`os.environ.get`·`os.environ[...]`·설정 로더 전달 네
형태로 읽으므로 `os.getenv`만 보는 검사는 23개 중 18개만 찾습니다.
`tests/test_environment_value_domains.py`는 **강제하는 함수를 직접 실행해** 선언과 양방향으로
비교합니다 — 두 리스트를 서로 대조하는 것은 이 저장소가 반복해 찾아낸 결함의 모양입니다.

**기존 테스트가 같은 결함을 품고 있었습니다.** `_fully_configured_environment`가 모든 required
변수를 리터럴 `"configured"`로 채우면서 docstring에 "as an operator would"라고 적고 있었고, 측정
결과 그 값들은 probe를 400으로 만듭니다 — gate가 의미 있음을 증명하려고 존재하는 테스트 안에서
바로 그 결함이 재현되고 있었습니다. 값은 이제 선언된 도메인에서 파생합니다.

역검증 4건, 모두 실패 확인: README에서 변수 제거, 읽지 않는 변수 문서화, gate를 presence-only로
되돌림, gate를 코드보다 엄격하게 선언.

## 문서가 안내하는 readiness 명령이 진단 대신 traceback을 돌려줬습니다 (2026-10-26)

`SDP_CONNECTOR_TIMEOUT_MS`를 읽는 지점에서 검증하게 만든 뒤 그 변경이 `demo_smoke`에 어떻게
도착하는지 확인하다 나왔습니다. **대부분은 그 전부터 있던 결함**이고, 부모 head(`88ae5d5`)에서
측정해 구분했습니다:

```
SDP_CONNECTOR_TIMEOUT_MS=2s         exit 1, JSON 없음, ValueError traceback   (기존)
SDP_CONNECTOR_VAULT_PROVIDER=vault  exit 1, JSON 없음, ValueError traceback   (기존)
SDP_CONNECTOR_TIMEOUT_MS=0          exit 0, JSON 있음, "ready": true          (이번 변경이 바꿈)
```

`PYTHONPATH=src python -m sdp.demo_smoke`는 README와 `sdp_core.enterprise`가 안내하는 명령이고
계약은 exit code + JSON 보고서입니다. 앞의 둘은 exit code는 맞고 **무엇을 고칠지 알려 주는 쪽을
잃었습니다**. 세 번째는 timeout을 `0`으로 공표하면서 ready라고 답했습니다.

`smoke_summary`가 configuration 거절을 `connector_configuration_errors` 항목으로 보고하고
`ready: false`·exit 1을 유지합니다. `KeyError`는 의도적으로 잡지 않습니다 — seed에 dataset이
없다는 것은 배포 설정이 아니라 빌드 결함이므로 환경 파일로 보내면 안 됩니다.

**메시지 비대칭 하나를 테스트가 잡았습니다.** `"unsupported connector vault provider: vault"`는
어떤 설정이 그 값을 들고 있는지 말하지 않았습니다(timeout 메시지는 말합니다). 이 보고서가 운영자가
받는 전부이므로 변수를 지목하게 고쳤고, 그 메시지를 측정값으로 인용하던 세 곳도 함께 갱신했습니다.

**역검증이 이번 라운드 세 번째로 같은 모양의 구멍을 찾았습니다.** `ready` 식에서
`and not configuration_errors`를 지워도 새 파일 전부가 통과했습니다. helper가 오류를 기록할 때
정확히 `None`을 돌려주고 네 probe 모두 gate에 필드가 있으므로 실패한 probe가 이미 자기 clause에서
걸립니다. 측정 결과 네 개 중 **하나만**(`rest_connector`) configuration 오류를 낼 수 있습니다 —
`credential_vault`가 그 connector의 `required_controls`에만 있습니다. 즉 그 clause는 지금 중복이고,
중복이라고 적어 두는 것이 요점입니다: probe 필드는 "데모 준비됐는가", 이 clause는 "설정이 쓸 수
있었는가"를 묻고 지금 우연히 겹칩니다. 동작 테스트는 중복인 clause와 없는 clause를 구별할 수
없으므로 소스에서 확인합니다.

## 열린 PR 전수 재측정, 그리고 main이 여전히 담고 있는 것 (2026-10-26)

루프 과제 1(열린 PR 전수 확인)을 12일 만에 다시 측정했습니다. 2026-10-14 측정은
비-draft 7건 전부 APPROVED 0건이었고, 지금도 같습니다 — 다만 이번에는 PR별로 묻지 않고
한 번의 권위 있는 질의로 확인했습니다.

```
GET /search/issues?q=repo:...+is:pr+is:open+review:approved
  -> total_count: 0
```

열린 PR은 **40건**(비-draft 7: `#112` `#111` `#109` `#107` `#104` `#102` `#82`)이고,
**승인된 리뷰는 전 저장소에 0건**입니다. `#104`는 리뷰 5건이 모두 `COMMENTED`,
`#107`은 리뷰 0건입니다. 즉 병합을 막는 두 조건(독립 승인 0건, 필수 체크가 과금 잠금으로
디스패치 전 거절)은 **둘 다 owner 측이고 12일 동안 변하지 않았습니다.**

### main은 SQL validator 우회 세 건을 여전히 담고 있습니다

"감사 큐 소진 (1)"은 세 우회를 **이 브랜치에서** 닫았다고 기록했고, `origin/main`이 어떤
상태인지는 적지 않았습니다. 두 트리에서 같은 입력을 **직접 실행해** 측정했습니다:

| 입력 | `origin/main` (`e48aa13`) | 이 브랜치 (`2f9f61d`) |
| --- | --- | --- |
| `select id from crm_customer_master, pg_catalog.pg_authid` | `[]` 통과 | `['unauthorized_table_reference']` |
| `select id into exfil from crm_customer_master` | `[]` 통과 | `['forbidden_keyword_detected']` |
| `select $$abc$$ from crm_customer_master` | `[]` 통과 | `['literal_values_not_allowed']` |

**영향 범위를 정확히 적습니다 — 과장하지 않기 위해 실행 경로를 확인했습니다.**
`execute_query`는 SQL을 **실행하지 않습니다**: 응답이 `"source": "mock-trino"`,
`"measurement_status": "mock_execution_no_real_data"`, `elapsedMs`/`bytesScanned`는 고정
상수이고 row count는 카탈로그 추정치입니다. 따라서 이 세 건은 **오늘 당장 악용 가능한 SQL
injection이 아니라, 게시된 안전 게이트가 자기 설계대로 동작하지 않는 상태**입니다.
`validate_sql_query`는 `/browse/query`와 draft 경로의 게이트이고 `/enterprise/*`가 control로
게시하므로, 실제 실행 백엔드가 들어오는 순간 — 즉 읽는 사람이 "이 게이트는 원래 작동했다"고
가정할 바로 그 시점에 — 악용 가능해집니다.

### 그래서 `#35`·`#107`을 superseded로 닫지 마십시오

`#35`("close SQL source-table allowlist bypass via comma joins")와 `#107`(금지 키워드를
substring이 아니라 토큰으로 매칭)은 이 영역을 다룹니다. 수리가 **이 브랜치에만** 있고
main에는 없으므로, 둘은 **main에 의해 승계된 것이 아닙니다.** 닫으면 이 브랜치가 끝내
병합되지 않을 경우 수리 자체가 사라집니다. 이 문서 140행이 cryptography에 대해 적은 원칙이
그대로 적용됩니다 — "수정이 존재한다"와 "수정이 main에 있다"를 섞지 마십시오. 이번에는
SQL validator에 적용해 둡니다.

이 절은 측정 기록이고 병합 허가가 아닙니다. PR을 닫거나 상태를 바꾸는 것은 owner 결정이며,
이 세션은 어느 PR도 닫지 않았습니다.

## 적대적 리뷰 6개 렌즈가 26건을 보고했습니다 — 그중 하나는 테스트가 한 건도 돌지 않게 만들고 있었습니다 (2026-10-26)

`81752fc..88ae5d5` 범위에 6개 렌즈(tripwire 효능, 동시성, disclosure, probe 조건, 요청 경로,
게시된 주장)를 돌렸습니다. 26건이 돌아왔고 중복을 묶으면 14개 결함입니다. 6개 렌즈가
**독립적으로 같은 것을 1순위로 보고한** 한 건이 있습니다.

### 전체 수집이 중단되고 있었습니다 (6개 렌즈가 독립 보고)

`tests/test_build_input_pinning.py::_dockerfiles()`가 `.claude`/`.git` 제외를 후보의
**절대 경로** 조각에 물었습니다. 제외의 목적은 에이전트 하네스가 `<repo>/.claude/worktrees/<id>`에
남기는 사본을 건너뛰는 것인데, 체크아웃 자체가 그 경로에 있으면 저장소의 모든 파일이
제외됩니다. 6개 렌즈 전부가 그런 worktree에서 돌았고, 거기서 이 저장소의 테스트는 한 건도
실행되지 않았습니다:

    tests/test_build_input_pinning.py:74: in _dockerfiles
        assert found, "no Dockerfile was found; re-point this test"
    !!!! Interrupted: 1 error during collection !!!!
    no tests collected, 1 error

모듈 수준 `assert`가 `@pytest.mark.parametrize` 인자를 평가하는 중에 터지므로 **파일 하나가
아니라 세션 전체**가 끝납니다. 이것이 측정 환경에 대해 말해 주는 것: 이 브랜치의 리뷰·수리
작업은 전부 worktree에서 돌고, 그 환경에서는 `647cc41` 이후 어떤 테스트도 돌지 않았습니다.
주 체크아웃에서만 초록이었습니다.

### 자격증명이 리다이렉트를 건너갔습니다

두 http(s) 내보내기 경로(로그 싱크, alert webhook)가 설정 URL의 userinfo를 `Authorization`
헤더로 옮깁니다. `urllib.request.urlopen`은 POST에 대한 302를 따라가고, GET으로 바꾸고,
헤더를 전부 다시 보냅니다:

    POST /webhook      Host 127.0.0.1:35661  Authorization: Basic c2VjcmV0...
    GET  /exfiltrated  Host 127.0.0.2:39469  Authorization: Basic c2VjcmV0...

운영자 자격증명이 두 번째 authority에 도착하고, 본문은 메서드와 함께 사라지고, 교환은
204로 끝나므로 전달은 `succeeded`로 집계됩니다. 싱크 쪽이 더 오래된 경로이므로 alert만
고치면 원래 누출이 남습니다. 둘 다 리다이렉트를 거부합니다.

### "전달됨"이 시도 횟수였습니다

`alerts_delivered`·`alerts_delivered_total`·`sdp_alerts_delivered_total`이 모두
`attempted`를 읽었고, 정직한 숫자를 담은 `deliveries_succeeded`는 아무도 읽지 않았습니다.
거부된 POST 한 번이 `alerts_delivered: 1` + `alerts_failed: 1`로 게시됩니다. gauge의 HELP는
"attempted", 이름은 "delivered"였습니다. 실패 gauge는 아예 없었습니다.

### probe 규칙이 `verdict_basis`의 세 conjunct 중 둘만 읽었습니다

빠진 세 번째는 control의 **효과가 실제로 측정되는** 유일한 conjunct입니다. 핀 비교를 깨면:

    probe status     contract_only
    row verification proof_route_served    ← route는 서비스되므로 declared_only가 안 됩니다
    failure_reason   ''
    rule report      observed_total 0, firing False
    gauge            0

critical 규칙이 진짜 빌드 결함에 0을 보고하는 동안, 세 게시 표면이 이 규칙이 "빌드가
소유하는 절반"을 덮는다고 주장했습니다. `demo_smoke`는 실패했으므로 피해 범위가 줄어든
것이고 없어진 것은 아닙니다.

### 요청 스레드에 가드가 없었습니다

`_deliver_alert`의 넓은 `except`는 스폰된 스레드만 감쌉니다. 래치 뒤에 요청 스레드가 직접
하는 일은 가드가 없었으므로, 거기서 raise가 나면 governed 요청이 500을 답하고 policy
decision +1 / audit event +0을 남깁니다 — 그 `except`의 주석이 스스로 막는다고 적어 둔
전례입니다.

### 게시된 경계가 불변식이 아니었습니다

`firing`을 lock 밖에서 읽고 결정을 lock 안에서 적용했으므로, "firing 아님"을 먼저 관찰하고
lock을 나중에 잡은 평가가 그 사이에 세워진 래치를 지웁니다. "reset 사이 워커당 최대 2
POST"는 성립하지 않았습니다.

### 내 테스트의 구멍이 다섯 건 더 있었습니다

이 라운드에서 **내가 쓴 테스트**가 자기 docstring이 약속한 것을 잡지 못한 경우:

| 구멍 | 측정 |
|---|---|
| 미들웨어 지점의 핸드셰이크 예산 | 예산을 지우면 호출이 **5012.93 ms**, 스위트 초록 |
| 미들웨어 지점의 join | join을 지우면 호출이 1 ms 미만, 스위트 초록 |
| stash 검사의 질문 | `ast.Name` 전부 제외 → 모듈 수준 stash(자기 메시지가 두 번 부르는 경우)를 제외 |
| disclosure payload 스캔 | routable 규칙 둘 중 하나만 몰았음 |
| 자격증명 반사 스캔 | 실패 경로에서만 돌았음 |
| ring generation 가드 테스트(첫 판) | stale generation을 처음부터 건네줘서 ring에 도달하지 않았음 |

마지막 줄은 이 라운드에 내가 **직접** 만든 구멍입니다. 가드를 지우고도 초록이었고, reset이
POST 비행 중에 들어와야 실패 경로가 stale generation으로 실행된다는 것을 보고 고쳤습니다.

### 두 건은 반박을 받았고, 그 반박을 기록해 둡니다

disclosure 두 건(규칙 하나만 모는 payload 스캔, 실패 경로만 보는 자격증명 스캔)은 재현
에이전트가 "확실히 실재"로, 반박 에이전트가 "실재 아님(likely)"으로 판정했습니다. 사실
하위 주장은 양쪽 모두 확인했습니다 — 변형이 통과하고, 스캔이 절반만 봅니다. 반박의
요지는 심각도입니다: `_alert_payload`에는 규칙별 코드가 **없으므로** 배포된 본문에 누출이
없고, 성공 분기에 URL을 남기는 변형의 `_ALERT_ROUTING`은 **게시 표면이 아닙니다**
(`alert_routing_state()`가 고정 키만 열거합니다). 그 지적이 맞습니다. 이 두 건은 "지금
새고 있는 것"이 아니라 **커버리지 비대칭**이고, 고치는 비용이 parametrize 두 줄이므로
고쳤습니다. 심각도를 high로 적었던 CHANGELOG 항목을 그에 맞게 정정했습니다.

### 산문 가드를 하나 더 만들지 않았습니다

낡은 주장이 대문자 하나로 금지 목록을 빠져나간 것이 이 주기 다섯 번째 "자기 목록에 걸린
가드"입니다. 열 번째 fragment를 추가하는 대신, 제품에서 값을 읽어 같은 키에 다른 값을 적은
문서를 거부하는 **파생** 가드를 넣었습니다. 손으로 쓴 목록은 이 주기에 다섯 번 자기
자신에게 걸렸습니다.

이 절은 측정 기록이고 병합 허가가 아닙니다.

## 기본 테스트 게이트가 stacked PR에서 한 번도 돌지 않았습니다 — check 목록을 세어서 찾았습니다 (2026-10-26 21:00Z)

워크플로 파일을 읽어서가 아니라 **PR의 check run을 세어서** 찾았습니다. 이 구분이 이 항목의
요점입니다 — 워크플로 파일은 넷 다 그럴듯하게 생겼고, 틀린 것은 그중 하나가 **만들어 내지
않는 결과**였습니다.

```
GET /repos/.../pulls/102/check-runs  ->  total_count: 2
  Hypothesis property tests          (fuzz.yml)
  Atheris coverage-guided (bounded)  (fuzz.yml)
```

`Tests / API integration suite`가 없습니다. 원인은 트리거 한 줄입니다:

| 워크플로 | `pull_request` 트리거 | #102(base: `#79` 브랜치)에서 |
|---|---|---|
| `fuzz.yml` | `pull_request:` (필터 없음) | 돈다 → 위 두 체크 |
| `tests.yml` | `pull_request: branches: [main]` | **돌지 않는다** |
| `scorecard-analysis.yml` | 없음(`push`/`schedule`만) | 무관 |

`branches` 필터는 PR의 **base** 브랜치에 걸립니다. 이 저장소의 merge order는 PR을
**의도적으로** 쌓으므로(`README`의 "Merge order"), 기본 테스트 게이트는 가장 많은 변경을
싣고 있는 PR들에서 정확히 돌지 않았습니다.

**24일 동안 드러나지 않은 이유**는 계정 Actions 과금 잠금이 모든 job을 디스패치 전에
거부해서 어느 쪽도 돌지 않았기 때문입니다. 즉 이 결함은 **다른 결함에 가려져** 있었습니다.
드러나는 시점은 잠금이 풀리는 순간이고, 그때 PR은 fuzz 레인의 결과를 보여 주고 `Tests`
결과는 보여 주지 않습니다 — "체크 통과"를 읽는 리뷰어는 두 레인 중 하나만 읽습니다.

`88c39a3`에서 필터를 제거하고 효과를 즉시 확인했습니다:

```
GET /repos/.../pulls/102/check-runs  ->  total_count: 3
  API integration suite              ← 이 PR에 처음 등장 (run 40400861406)
  Hypothesis property tests
  Atheris coverage-guided (bounded)
```

**부수 효과로 과금 잠금에 대한 독립 증거가 하나 생겼습니다.** 이 PR에서 한 번도 돈 적 없는
레인이 최초 디스패치에서 `21:01:58Z → 21:02:01Z` **3초** 만에 같은 방식으로 거절되었습니다.
거절이 특정 워크플로·특정 head·특정 diff의 성질이 아니라 계정 상태라는 뜻입니다 — 이전
열두 행이 signature로 보여 준 것을 이 한 행이 **구성으로** 보여 줍니다.

형제 저장소가 같은 필터를 이미 기록해 두었습니다 — `contextual-orchestrator`의 "Stacked
quality checks: zero check runs can result from the former `pull_request.branches: [main]`
filter excluding the PR base. Keep the quality trigger unfiltered." 같은 결함이 두 번째
저장소에 독립적으로 있었고, 거기서는 워크플로를 읽어서 찾았고 여기서는 결과를 세어서
찾았습니다. 조직 차원의 교훈은 **트리거를 읽지 말고 산출된 check를 세라**는 것입니다.

가드는 `tests.yml`을 이름으로 부르지 않고 **파생**합니다
(`tests/test_workflow_triggers.py`): 저장소가 소유한 워크플로를 전부 읽어
`pull_request` 트리거에 base 브랜치 필터(`branches`/`branches-ignore`)가 있으면 거부합니다.
나중에 같은 필터를 달고 추가되는 워크플로도 이 파일을 고치지 않고 걸립니다. `types`는 base가
아니라 이벤트 종류를 좁히므로 범위 밖입니다. PyYAML이 lock에 없고 가드 하나를 위해 의존성을
추가하는 것은 잘못된 교환이므로 트리거 블록을 텍스트로 읽으며, **파서 자체를 합성 텍스트로
몰아 테스트합니다** — 아무도 측정하지 않은 파서를 가진 가드는 자기 가정에 대해 검사된
가드이고, 이 주기에 그 형태로 다섯 번 실패했습니다.

이 절은 측정 기록이고 병합 허가가 아닙니다.

## 드래프트 SQL의 `FROM`이 relation이 아니라 연결 locator였습니다 — 안전 게이트도 같은 추측을 공유합니다 (2026-10-26 22:25Z)

`POST /llm/draft-query`가 `assumptions`에 `카탈로그에서 검증된 테이블/컬럼만 사용`을
공표했습니다. **컬럼**은 카탈로그 선언에서 옵니다. **테이블**은 아닙니다 —
`_source_table_name()`이 `source_system`의 마지막 경로 조각을 `_safe_identifier`로 통과시킨
값이고, `source_system`은 relation이 아니라 *연결* locator입니다. `9cf278e`에서 시드
카탈로그 다섯 건을 전수 측정했습니다:

| dataset | `source_system` | 공표된 `FROM` | 카탈로그가 선언한 relation |
| --- | --- | --- | --- |
| `crm-customer-master` | `postgresql://analytics.dw/customer` | `customer` | `crm_customer_master` (`postgresql.table` distribution) |
| `crm-event` | `s3://analytics/events/crm` | `crm` | 없음 (관계형 아님) |
| `sales-order` | `postgresql://analytics.dw/sales` | `sales` | 없음 |
| `semantic-glossary` | `sparql://semantic.graph/customer-intelligence` | `customer_intelligence` | 없음 (named graph) |
| `marketing-campaign` | `https://api.example.internal/marketing/campaigns` | `campaigns` | 없음 (REST 경로) |

두 가지가 동시에 틀립니다. libpq URI의 그 조각은 **데이터베이스** 이름이지 relation
이름이 아니고, 다섯 중 셋은 **애초에 관계형이 아닙니다** — 객체 prefix, named graph, REST
경로입니다. 그런데도 다섯 건 모두 `"dialect": "postgresql"` SQL을 받습니다. 즉 **어느
draft도 대상 시스템에 존재하는 relation을 지목하지 않았고**, 붙여 넣은 구매자는
`relation "customer" does not exist`를 받습니다.

### 자기 모순: 게이트가 카탈로그 자신의 relation을 거부합니다

`validate_sql_query`의 source-table allow-list가 드래프터와 **같은 파생**에서 만들어지므로,
카탈로그가 `postgresql.table` distribution으로 공표한 진짜 relation을 넣으면 거부하고
추측한 이름은 통과시킵니다:

```
validate_sql_query("... FROM crm_customer_master ...")  -> ['unauthorized_table_reference']
validate_sql_query("... FROM customer ...")             -> []
```

구매자 쪽에서 보면 **고치면 거부되고, 거부되지 않으면 실행되지 않습니다.**

### 이번에 한 것 (`8ed985d`) — 전달 지점 라벨

관계형이 아닌 source에 대해 draft를 **거부**하는 설계를 먼저 쓰고 되돌렸습니다. 네 파일
11건이 red가 되고, 그중 `tests/test_latency_budget_measurement.py`는 이 라우트를 **지연
표본 수집용 트래픽 인프라**로 씁니다(fixture 오류 7건). 다른 측정이 올라서 있는 표면을
없애는 것은 결함보다 큰 변경이고, 결함은 draft의 존재가 아니라 **거짓 주장**입니다.

그래서 `/graph/stats`의 instance-wide 카운트와 mock executor의 provenance 필드에서와 같은
선택을 했습니다 — 응답이 전달 지점에서 스스로를 라벨합니다. `source_kind`(공유 분류기
`sdp_core.demo_seed.classify_source_type`에서 파생),
`executable_against_source`(다섯 건 모두 `False` — 그게 현재 사실입니다),
`execution_caveat`(이름이 **locator에서 왔다**는 것과 진짜 이름이 **카탈로그
distribution에 있다**는 것 둘 다). 거짓 assumption은 참인 두 문장으로 교체했습니다.

### 남은 수리 — **들어왔습니다** (`2026-10-27 00:50Z` 절)

아래 다섯 단계는 모두 수행되었고, 결과와 fuzz seam이 찾은 추가 결함은 이 문서의
"드래프트가 카탈로그가 선언한 relation을 지목합니다" 절에 있습니다. 이 목록은 그때의
계획 기록으로 남겨 둡니다 — 수리된 것을 미해결로 읽히게 두지 않기 위해 제목에 적습니다.

`8ed985d`의 코드 주석과 커밋 메시지가 "the separate repair recorded in the gap baseline"을
참조합니다. **그 기록이 바로 이 절입니다** — 참조를 적을 때 대상이 없으면 그 참조 자체가
이 문서가 반복해 고쳐 온 거짓 진술이므로, 같은 인터벌에 적어 둡니다.

해야 할 것은 하나의 파생을 두 소비자가 공유하게 만드는 것입니다:

1. dataset의 `distributions`에서 `format`에 `table`을 담은 항목의 `endpoint` 마지막 조각을
   relation으로 해석합니다(`crm-customer-master` → `crm_customer_master`).
2. `validate_sql_query`의 allow-list를 **같은 함수**에서 세웁니다. 지금처럼 두 곳이 각자
   추측하면 위의 자기 모순이 되돌아옵니다.
3. 선언이 없는 dataset(관계형 아님 또는 distribution 미기재)은 relation이 없으므로
   `executable_against_source`가 계속 `False`이고, 그 사유를 `execution_caveat`가 말합니다.
4. `validate_sql_query`는 fuzz target(`fuzz/fuzz_query_safety.py`)이고 같은 invariant의
   Hypothesis 미러가 `tests/fuzz`에 있습니다. allow-list 파생이 바뀌면 **둘 다** 같이
   움직여야 하고, 미러를 고치지 않은 변경은 fuzz 레인에서만 늦게 드러납니다.
5. 들어오면 SQL source가 `executable_against_source: True`로 바뀌고
   `tests/test_draft_source_kind.py`의 기대도 같이 바뀝니다 — 그 파일은 그 전환을 **놓치지
   않도록** 현재 사실을 고정해 둔 것입니다.

### 같은 라운드에서 확인했지만 아직 수리하지 않은 것

사유를 적어 두는 쪽이 재탐색보다 쌉니다. 모두 재현해 측정했고, 수리는 하지 않았습니다.

- `POST /catalog/datasets`는 actor를 **요청 본문**(`_actor(payload)`)에서 읽는데, 거부
  메시지는 쿼리 파라미터 기준으로 적힙니다. 그래서 본문에 권한 있는 actor를 담아도
  `create 작업은 admin 권한만 가능`이 돌아오고, 사유가 실제 원인을 가리키지 않습니다.
  이 라운드에 저 메시지 때문에 재현을 네 번 헛돌렸습니다 — 사유가 틀린 거부는 호출자뿐
  아니라 다음 측정자도 잘못된 곳을 보게 만듭니다.
- `POST /ontology/patches/{patch_id}/review`가 같은 `create 작업은 admin 권한만 가능`으로
  거부하고, 존재하지 않는 patch에 대해 `{"detail":"'patch not found'"}`를 돌려줍니다 —
  바깥 따옴표가 `KeyError` repr이 그대로 직렬화된 흔적입니다.
- ~~`validation_pass_rate` 게이트가 비율 없이 판정만 공표합니다~~ — **이 항목의
  진단이 틀렸고, 다음 커밋에서 바로잡아 닫았습니다.** 비율은 공표되고 있었습니다
  (`/enterprise/evidence-pack`의 최상위 `metadata_validation_pass_rate = 1.0`).
  틀린 것은 `bc2ebb2`가 쓴 **포인터**입니다 — 같은 이름의 한 단계 아래
  `saleability_gates.metadata_validation_pass_rate`를 가리켰고 그 값은 `'pass'`입니다.
  `measured: True` KPI 넷 중 **셋**이 그랬습니다(아래 절).
- `/enterprise/console`의 상태 chip이 네 상태 전부에서 `class="badge ok"`입니다
  (`className`/`classList` 사용 0건이고 amber `.badge.warn`은 이미 CSS에 있습니다).
- `/catalog/facets`가 seed domain 값을 필드 이름처럼 공표하고, audit-trail·policy-decision
  스키마가 실제 응답 모양과 어긋납니다.

이 절은 측정 기록이고 병합 허가가 아닙니다.

## `measured: True` KPI 넷 중 셋이 측정값 대신 **게이트 판정**을 가리켰습니다 (2026-10-26 22:50Z)

`bc2ebb2`가 KPI 계약에 `measurement_surface`를 넣고 그 필드의 계약을 "where this KPI's
own figure is published"로 적었습니다. 가드는 **포인터가 resolve되는지**를 봅니다. 셋은
resolve됩니다 — 문자열 `'pass'`로. `c27958f`에서 넷 전수 측정:

| KPI | target | 포인터 | resolve 결과 |
| --- | --- | --- | --- |
| `metadata_completeness` | `>=90 percent` | `…#saleability_gates.metadata_completeness` | `'pass'` |
| `policy_audit_coverage` | `100 percent` | `…#metrics.governed_requests_without_evidence_total` | `0` |
| `ontology_mapping_coverage` | `>=70 percent` | `…#saleability_gates.ontology_mapping_coverage` | `'pass'` |
| `validation_pass_rate` | `>=95 percent` | `…#saleability_gates.metadata_validation_pass_rate` | `'pass'` |

**숫자는 처음부터 공표되고 있었습니다.** `/enterprise/evidence-pack`의 최상위에
`mean_metadata_completeness = 1.0`, `ontology_mapping_coverage = 0.8`,
`metadata_validation_pass_rate = 1.0`이 있고, 포인터는 그 **옆에 있는 판정**을 가리켰습니다.
`metadata_completeness`의 경우 숫자 키 이름(`mean_…`)이 게이트 이름과 달라서 게이트를
집기 쉬웠습니다.

판정은 제품이 **측정에 대해 내린 자기 의견**입니다. 측정 자리에 의견을 놓으면 읽는 사람이
값도, 비교된 임계도, 여유도 볼 수 없습니다 — 이 라운드가 드래프터와 `/graph/stats`에서
고친 것과 같은 치환입니다.

### `bc2ebb2`가 이걸 알면서 **틀린 전제로** 넘겼습니다

`validation_pass_rate` 옆에 당시 제가 쓴 주석이 있었습니다 — "The comparison runs and its
verdict is published; the raw rate behind it is not, which is a smaller honesty gap recorded
in the gap baseline rather than closed here." 뒷부분이 사실이 아닙니다. raw rate는 공표되고
있었고, 결함은 **포인터**였습니다. 틀린 전제로 미루면 그 다음 커밋에서도 안 보입니다. 이
문서의 직전 절도 같은 틀린 진단(`shacl_validation.validation_pass_rate`가 `None`)을 담고
있었고, 둘 다 같은 커밋에서 바로잡았습니다.

### 가드를 성질에 맞췄습니다

resolve 가능성은 **더 약한** 성질입니다. 두 가드를 추가했습니다
(`tests/test_kpi_measurement_disclosure.py`):

1. 포인터는 **숫자**로 resolve돼야 합니다. `bool`은 `int`의 서브클래스이므로 명시적으로
   제외합니다 — 불리언도 판정입니다.
2. 포인터는 `saleability_gates` 블록을 가리킬 수 없습니다. 나중에 그 블록 안에 숫자가
   들어오면 1번만으로는 통과하는데, 두 블록은 역할이 다르고 포인터는 **측정을 담는 쪽**을
   이름으로 불러야 합니다.

역검증 둘: 포인터를 게이트로 되돌리면 두 가드가 그 KPI에 대해 red, 불리언 키
(`ontology_revision_is_durable`)를 가리키면 1번만 red — `bool` 제외가 실제로 살아 있다는
증거입니다.

### 닫지 않은 것: `policy_audit_coverage`는 **여집합**을 가리킵니다

넷 중 하나는 숫자로 resolve되지만 그 숫자가 KPI의 양이 아닙니다. target은
`100 percent`이고 포인터는 `governed_requests_without_evidence_total = 0` — 증빙 없는
요청의 **개수**입니다. 0이면 100 percent가 따라오지만, 읽는 사람이 `0`을 `100 percent`와
직접 비교할 수는 없습니다.

**지금 비율을 공표할 수는 없습니다.** 분모가 `request_observations_total`이고 기본 데모에서
`0`이므로 비율은 정의되지 않습니다(0/0). 0을 100 percent로 공표하면 측정하지 않은 것을
측정값으로 적는 것이고, 이 문서가 반복해 고쳐 온 결함입니다. 그래서 여집합 포인터를
유지하고 **그 사실을 여기 적습니다** — 새 필드를 만들어 의미를 겹치게 하는 것보다, 양이
정의되는 조건(관측 ≥ 1)이 생길 때 한 번에 바꾸는 쪽이 맞습니다. 가드는 이 포인터를
통과시킵니다(숫자이므로). 그 한계가 가드의 결함이 아니라 **측정의 현재 상태**입니다.

이 절은 측정 기록이고 병합 허가가 아닙니다.

## 거부 사유가 **대상**을 말했습니다. 읽기 라우트는 같은 호출자에게 **인증**을 말합니다 (2026-10-26 23:20Z)

인증되지 않은 호출자 하나로, 시드 카탈로그가 소유한 데이터셋 하나(`crm-customer-master`)에
대해 `0b19c91`에서 측정했습니다:

```
GET   /catalog/datasets/{id}            -> 403 "목록 조회는 인증된 사용자만 가능합니다."
PATCH /catalog/datasets/{id}            -> 404 "dataset not found"
POST  /catalog/datasets/{id}/publish    -> 404 "dataset not found"
POST  /catalog/datasets/{id}/deprecate  -> 404 "dataset not found"
```

**한 주체, 한 자원, 같은 질문에 두 답**입니다. 읽기는 "인증하라"고 하고 mutation 셋은
데이터셋이 없다고 합니다. 있습니다 — 같은 프로세스에서 인가된 독자에게 카탈로그가 바로
내줍니다. 그래서 mutation 거부는 **거짓 사유**를 말하고, 호출자는 그 사유를 따라 자격증명이
아니라 dataset id를 보러 갑니다. 이 세션의 기록이 바로 거기서 재현을 네 번 헛돌렸습니다.

404 자체는 의도된 것이고 `api.py`에 사유가 적혀 있습니다 — **외부 테넌트** 데이터셋은 없는
것과 구분되지 않아야 하고, 이전 판은 둘 다 403을 주면서 사유 문자열로 그 차이를
흘렸습니다. 그 성질은 유지합니다.

### 첫 설계를 측정이 거부했습니다

scope 없는 주체는 역할 검사에서 거부되므로 사유가 데이터셋에 의존하지 않을 것이라고
가정하고 `decision.reason`을 그대로 공표했습니다. **틀렸습니다:**

```
anonymous POST .../crm-customer-master/publish  -> "tenant boundary denied"
anonymous POST .../no-such-dataset/publish      -> "존재하지 않는 데이터셋입니다."
```

정책 엔진은 존재·테넌트를 역할보다 **먼저** 평가합니다(`policy.py`의 mutation 경로:
`get_dataset` → 테넌트 → 민감도/목적 → 역할). 즉 404가 존재하는 이유가 바로 이것이고,
제 첫 설계는 그 oracle을 되열었습니다. **제가 쓴 테스트가 그것을 잡았습니다** — 현재
있는 것과 없는 것을 둘 다 몰아 상태와 본문을 비교하는 가드입니다.

### 그래서: 데이터셋에 의존할 수 **없는** 사유

scope 없는 주체에게는 `resource="catalog"`에 대한 discovery 거부를 답합니다. 그 사유는
세 자원(카탈로그, 있는 dataset, 없는 dataset)에 대해 모두 동일하다고 측정했습니다 —
`search` 분기가 데이터셋을 보기 전에 return하기 때문입니다. `_authorize_catalog_discovery`가
공표하는 것과 **같은 결정**이므로, 읽기 라우트와 mutation 라우트가 문자열을 맞춰 두는
방식이 아니라 **구성상** 한 답을 줍니다.

사유 문구도 하나만 고쳤습니다: `목록 조회는 인증된 사용자만 가능합니다.` →
`카탈로그 접근은 인증된 사용자만 가능합니다.` 이 분기가 거부하는 모든 호출자에게 참인
문장입니다(목록 읽기에만 해당하는 문구는 mutation 호출자에게 틀린 동작을 지목했습니다).
production 참조는 한 곳뿐이고, 테스트 두 곳의 언급은 docstring/주석이었습니다.

또 세 라우트에 인라인 복사되어 있던 거부 분기를 `_catalog_mutation_refusal` 하나로
합쳤습니다 — 사본 셋을 각각 고치는 것은 이 저장소가 대가를 기록한 형태입니다.

### 선행 결정을 덮었으므로, 그 테스트와 근거를 같이 고쳤습니다

`tests/test_api.py::test_catalog_mutation_guard_denies_non_admin_actors`가 scope 없는
호출자에 대해 404를 **근거와 함께** 단언하고 있었습니다("403-for-foreign plus
404-for-missing is an existence oracle"). 조용히 뒤집지 않고, 측정과 이유를 그 주석에
적고 단언을 바꿨습니다. "a scope refusal must not explain itself"는 **유지**합니다 —
사유는 호출자를 말할 수 있고 자산은 말할 수 없습니다(`tenant`·dataset id·`존재하지 않`
모두 금지로 단언).

역검증 넷: 인증 분기 제거(두 파일 red), 데이터셋 의존 사유 공표(oracle 가드까지 red —
제 첫 실수를 막는 가드가 살아 있다는 증거), 외부 테넌트 숨김 제거(cross-tenant 가드 red),
사유가 자산을 말하게(읽기·mutation 양쪽 red).

### 닫지 않은 것: untyped 본문 라우트 다섯이 `actor`를 공표하지 않습니다

같은 측정에서 나왔습니다. `additionalProperties: true`를 공표하는 라우트 열 중 **다섯**이
인가 주체를 본문에서 읽습니다(`/catalog/datasets/{id}/publish`·`/deprecate`,
`/enterprise/auth/oidc-preview`, `/ontology/patches`, `/ontology/patches/{id}/review`).
공표된 스키마만 보고 만든 본문은 **유효하지만 호출을 성립시키지 못합니다** — 이것이
`api_request_contract`의 자기 docstring이 경고하는 "a schema that cannot be used to make
the call it describes"이고, untyped 문을 통해 들어옵니다. 그 모듈의 주석은 파생 가드가
"so the next one cannot be forgotten"이라고 적지만, 가드는 `REQUEST_BODY_MODELS`에 있는
라우트만 파라미터로 돕니다 — untyped 열 개는 범위 밖입니다(`test_the_untyped_bodies_that_
remain_are_the_ones_with_no_model`이 그 경계를 의도적으로 측정합니다). 즉 **공표 주장이
가드보다 넓습니다.** 다음 항목으로 처리합니다.

이 절은 측정 기록이고 병합 허가가 아닙니다.

## 공표된 문서로는 POST 라우트 **열 개**를 호출할 수 없었습니다 (2026-10-26 23:50Z)

`api_request_contract`가 모델이 있는 라우트 열다섯을 수리했습니다. 공표 본문 스키마가
`{"type": "object", "additionalProperties": true}`인 라우트 **열**이 남아 있었고, 그 열
개가 **전부** 본문에서 이름 있는 키를 읽습니다. `5af3adf`에서 AST로 전수 측정:

```
POST /catalog/datasets/{id}/publish     actor, reason
POST /catalog/datasets/{id}/deprecate   actor, reason
POST /enterprise/auth/oidc-preview      actor, claims, role_map
POST /ontology/patches                  actor, concept, suggestion
POST /ontology/patches/{id}/review      actor, comment, decision, reviewer
POST /browse/{id}/preview               limit, offset, purpose, user
POST /enterprise/auth/oidc-verify       token
POST /llm/search                        purpose, question, user
POST /ontology/resolve                  text + 버전 핀
POST /policy/decision                   action, purpose, resource, subject, user
```

`additionalProperties: true`는 문서로 만든 본문을 **유효하게** 만들고 호출은 성립시키지
못합니다 — `api_request_contract`의 자기 docstring이 경고하는 "a schema that cannot be
used to make the call it describes"가 typed 문이 아니라 **untyped 문**으로 들어온
것입니다. 열 중 다섯은 인가 주체를 이렇게 읽으므로 그 호출은 핸들러에 닿기도 전에
거부됩니다.

**주체의 키 이름이 통일되어 있지도 않습니다** — 모든 GET은 쿼리 `?user=`, 이 라우트 중
다섯은 본문 `actor`, 셋은 본문 `user`입니다. 경로만 보고 유도할 수 있는 규칙이 아니고,
바로 이것이 문서가 있어야 하는 이유입니다.

### 공표 주장이 가드보다 넓었습니다

그 모듈의 주석은 파생 가드가 "fails if a handler reads a body key this table does not
publish, so the next one cannot be forgotten"이라고 적습니다. 가드는
`REQUEST_BODY_MODELS`만 파라미터로 돌므로 **모델 없는 열 개는 애초에 범위 밖**이었습니다.
`test_the_untyped_bodies_that_remain_are_the_ones_with_no_model`이 그 경계를 측정하긴
하지만, 그것은 "모델이 없다"를 확인할 뿐 "읽는 키를 공표한다"를 확인하지 않습니다.

### 고친 것

* 열 라우트의 본문 키 전부를 설명과 함께 표에 추가했습니다(주체 키가 라우트마다 다르다는
  것을 각 설명이 말합니다).
* 생성기를 확장했습니다. 모델이 없으면 라우트를 **건너뛰고** 있었으므로, 표만 채워도
  문서에는 아무것도 나타나지 않았습니다. 이제 인라인 스키마에 properties를 병합하며,
  스키마는 **열린 채로** 둡니다 — 모델이 없는 라우트는 본문을 검증하지 않으므로 문서에서
  닫으면 핸들러가 강제하지 않는 엄격함을 공표하는 반대 방향의 거짓이 됩니다. `dict | None`
  본문의 `anyOf`도 평탄화하지 않고 object 멤버에만 병합합니다(평탄화하면 선택적 본문을
  필수로 공표하게 됩니다).
* 스캐너가 모듈 상수 키(`payload.get(ontology_version.PIN_PARAMETER)`)를 **읽어서**
  해석합니다. 문자열을 가드에 하드코딩하면 사본이 하나 더 생기므로, 상수를 import해서
  읽고 표의 값이 그 상수와 같은지 단언합니다 — 상수 이름이 바뀌면 문서가 아무도 읽지 않는
  키를 공표하는 대신 테스트가 깨집니다.
* 스캐너는 형제 테스트에서 **import**합니다. 같은 모듈에 대한 같은 질문이고, 스캐너 사본
  둘은 맞춰 둘 것이 하나 더 생기는 것입니다.

### 역검증에서 **제 테스트 둘이 green으로 돌아왔습니다**

(1) 생성기가 untyped 라우트를 건너뛰게 만드는 변이 — 즉 이 수리의 **전부를 되돌리는**
변이 — 가 전부 통과했습니다. 단언이 공표된 문서가 아니라 **표**를 보고 있었기 때문입니다.
표는 원천이고 문서가 산출물이며, 클라이언트가 읽는 것은 산출물입니다. 모든 단언을
`/openapi.json`에서 읽도록 바꿨고, 이제 그 변이는 가드 다섯을 red로 만듭니다.
(2) description 공백 변이는 제가 **엉뚱한 자리**를 집어서 통과했습니다(앵커 불일치가 아니라
뒤에 오는 같은 키가 덮었습니다). 올바른 앵커로 다시 돌려 red를 확인했습니다. 변이가
green이면 가드보다 변이를 먼저 의심한다는 규칙이 두 번 다 맞았습니다.

나머지 역검증 둘: review 라우트의 `actor` 키 제거(가드 셋 red), 핀 키 이름 변경(상수
대조 가드 red).

이 절은 측정 기록이고 병합 허가가 아닙니다.

## 콘솔 readiness chip의 **색**이 네 상태 전부에서 초록이었습니다 (2026-10-27 00:15Z)

`#readyBadge`는 콘솔에서 가장 먼저 읽히는 요소입니다. **문구**는 네 상태를 따라 바뀌는데
**class**는 한 번도 바뀌지 않았습니다. `bf93653` 측정:

* 서버가 `<span class="badge ok" id="readyBadge">pilot evidence</span>`를 렌더합니다.
* 네 분기 모두 `text('readyBadge', ...)`를 호출하고, 그 헬퍼는 `textContent`만 씁니다.
* `className`/`classList`가 모듈 전체에서 **0건**입니다.

즉 초록 chip이 `evidence load failed: connectors`와 `refused for this actor: …`를
announce했습니다. 구매자 핸드오프 대시보드에서는 **색이 문구보다 먼저 읽힙니다.** amber
`.badge.warn`은 스타일시트에 이미 있고 같은 헤더의 정적 chip 둘이 그것을 씁니다 — 어휘는
있었고 상태가 거기까지 가지 않았을 뿐입니다.

고친 것: 문구와 class를 **한 헬퍼**가 함께 씁니다(상태마다 호출 둘은 갈라지는 방식입니다).
실패·거부는 `warn`, ready는 `ok`, signed-out은 **중립**입니다 — amber는 플랫폼 문제를
보고하는 것이고 초록은 아무도 가져오지 않은 증빙을 주장하는 것이므로, 중립이 정직한 세
번째 답이고 그 class는 이미 존재합니다. 서버가 렌더하는 초기 chip도 중립으로 바꿨습니다:
스크립트가 돌지 않으면(CSP 거부·JS 오류·크롤러) 페이지는 서버가 칠한 것을 유지하고,
placeholder 문구에 초록은 로드되지 않은 증빙에 대한 주장입니다. `className`을 쓰고
innerHTML은 도입하지 않습니다.

### 역검증에서 **이 수리를 전부 되돌리는 변이가 green으로 돌아왔습니다**

헬퍼 본문을 고정된 `node.className = 'badge ok'`로 바꾸는 변이 — 호출부는 여전히 `'warn'`을
넘기지만 헬퍼가 무시하는 상태 — 가 이 파일의 다른 모든 테스트를 통과했습니다. 테스트가
**선언**(호출부가 tone을 넘긴다)을 보고 **효과**(헬퍼가 그 tone을 쓴다)를 보지 않았기
때문입니다. 이 라운드에서 같은 형태가 세 번째입니다(앞의 둘: 생성기를 건너뛰게 한 변이,
표만 보던 단언).

JS 런타임이 없으므로 효과를 실행할 수는 없습니다(브라우저 하네스 미도입은 기록된 유지보수자
결정입니다). 그래서 형식이 허용하는 가장 좁은 성질을 단언합니다: class 대입식이 **매개변수
`tone`에서 파생**되어야 하고, 성공 class가 스크립트 어디에도 **리터럴로** 나타나지 않아야
합니다. 그 변이가 이제 red입니다.

나머지 역검증 넷: 실패 상태를 초록으로(가드 둘 red), 서버 초기 chip을 다시 초록으로(red),
signed-out을 amber로(red), `.badge.warn`을 스타일시트에서 제거(스타일시트 대조 가드 red —
tone 집합을 나열하지 않고 **서버가 보낸 CSS에서 파생**하므로 한쪽만 바뀌면 걸립니다).

이 절은 측정 기록이고 병합 허가가 아닙니다.

## 드래프트가 카탈로그가 선언한 relation을 지목합니다. 게이트도 같은 파생을 씁니다 (2026-10-27 00:50Z)

이 문서의 "드래프트 SQL의 `FROM`이 relation이 아니라 연결 locator였습니다" 절이 **남은
수리**로 적어 둔 것이 들어왔습니다. 그 절의 다섯 단계를 그대로 따랐습니다.

카탈로그는 답을 처음부터 갖고 있었습니다 — 시드 다섯 중 둘이 `postgresql.table`
distribution으로 relation을 선언합니다:

```
crm-customer-master  postgresql://analytics.dw/customer -> FROM crm_customer_master
  (선언: https://example.internal/api/table/crm_customer_master)
sales-order          postgresql://analytics.dw/sales    -> FROM sales_order
  (선언: https://example.internal/api/table/sales_order)
```

나머지 셋은 `parquet`·`sparql.graph`·`rest.json`을 선언합니다 — 지목할 relation이 **없고**,
locator 파생 이름과 그 사실을 계속 말합니다. 다섯을 모두 executable로 뒤집는 것은 같은
over-claim을 새 자리에 놓는 것입니다.

자기 모순도 닫혔습니다. `validate_sql_query`의 allow-list가 **같은 파생**을 쓰므로:

```
validate("... FROM crm_customer_master ...")  -> []                               (이전: 거부)
validate("... FROM customer ...")             -> ['unauthorized_table_reference']  (이전: 통과)
```

`source_relation_name` 하나를 드래프터와 게이트가 **공유**합니다. 사본 둘이면 갈라지고, 그
갈라짐이 애초의 결함이었습니다. `DRAFT_SQL_DIALECT` 상수 하나가 응답의 `dialect`와 어떤
distribution을 relation으로 읽을지를 **동시에** 정하므로 둘이 어긋날 수 없습니다.

### fuzz seam이 결함 하나를 찾았습니다

새 invariant(`check_validate_sql_query`)를 양쪽 엔진이 공유하도록 넣었고, Hypothesis가
`declared_relation="0"`을 반례로 돌려줬습니다. `_safe_identifier("0")`은 `"0"`을 그대로
돌려주는데 **선두 숫자는 식별자가 아닙니다**: 발행된 `FROM 0`은 테이블 참조가 아니고,
`FROM 0abc`는 파서가 테이블 **`abc`**로 읽습니다 — 쓴 이름과 인가된 이름이 다른 문자열이
됩니다. 어느 쪽이든 draft 자신의 allow-list 검사가 `unauthorized_table_reference`로
거부하는데, 그것은 **네이밍 문제에 보안 모양의 사유**를 붙이는 것입니다.

그래서 `source_relation_name`은 발행된 이름이 **자기 자신으로 다시 읽히지 않으면**
선언을 거절하고 locator 이름과 "파생이지 선언이 아님" caveat를 유지합니다. 판정은
PostgreSQL 식별자 규칙을 여기서 다시 쓰지 않고 **production 파서에게 묻습니다**
(`_referenced_source_tables(f"select 1 from {name}") == [name]`) — allow-list가 참조하는
그 파서와 일치하는 것이 중요한 성질입니다.

### 역검증에서 변이 하나가 green으로 돌아왔습니다

dialect 제한(`postgresql.table`만)을 "table이 포함된 아무 format"으로 넓히는 변이가
전부 통과했습니다. 시드에 비-PostgreSQL `.table` distribution이 **없어서** 그 변이가
시드 위에서는 행동상 무해하기 때문입니다. 제 테스트는 "시드의 모든 `.table` 선언이
`postgresql.table`이다"를 단언했는데, 그것은 **시드에 대한 진술**이고 규칙에 대한 진술이
아닙니다. 합성 데이터셋으로 `mysql.table`·`snowflake.table`·`delta.table`·
`postgresql.table.backup`·`not_postgresql.table`을 몰아 규칙 자체를 단언하도록 고쳤고,
그 변이가 이제 red입니다. 비-발행가능 이름도 같은 이유로 합성으로만 측정됩니다 — 시드가
그 경우를 표현할 수 없고, 그래서 fuzz 실행이 찾아야 했습니다.

나머지 역검증 다섯: resolver가 항상 None(가드 다섯 red), 게이트가 자기 추측 유지(열넷 red —
fuzz invariant 포함), draft가 locator 이름 유지(열하나 red), 전부 executable로 주장(셋 red),
읽히지 않는 이름을 그대로 발행(declined 가드 red).

### 호출자 쪽 변화

`/browse/query`가 같은 해석을 쓰므로, 구매자가 **카탈로그가 공표한 relation 이름**으로
질의하면 통과하고 추측된 이름은 거부됩니다 — 이전의 정반대입니다. 저장소 안에서는 route를
통과하던 테스트 열둘이 red로 바뀌었고 전부 선언된 relation으로 고쳤습니다. 그중 둘은
`validate_sql_query`를 `declared_relation` 없이 부르고 있었는데(= fuzz fallback 경로),
**제품이 검증하는 방식과 다르게 검증하던 것**이므로 그 자리를 제품과 같게 맞췄습니다.
production 호출자는 둘뿐이고 둘 다 해석을 넘깁니다 — 전수 확인했습니다.

이 절은 측정 기록이고 병합 허가가 아닙니다.

## 공표 응답 계약을 재생성하는 스크립트가 **존재하지 않았습니다** (2026-10-27 01:40Z)

`api_response_contract`의 docstring은 "These schemas are derived by executing the routes,
**not written by hand**"이고, 손으로 쓴 응답 스키마는 이 제품이 거부하기 위해 존재하는 바로
그 drift라고 적습니다. 그리고 "Regenerate with the script recorded in that test's
docstring"이라고 안내합니다. 그 테스트의 docstring은 scratchpad의 heredoc을 가리키고,
**그 파일은 저장소에도 scratchpad에도 없습니다.** 테스트 자신이 "the generator, which lives
outside the repository"라고 적고 있었고, probe 설정을 "복사해 둔다"는 주석과 함께 중복으로
갖고 있었습니다.

**실행할 수 없는 규칙은 규칙이 아닙니다.** 그래서 그 파일은 손으로 편집되어 있었습니다 —
`a2f50c2`에서 재생성해 보니 바뀐 곳이 **정확히 두 군데**이고 둘 다 들여쓰기가 주변 블록과
맞지 않는 삽입(`8cda569`의 `probe_semantics`, `41dffb1`의 alert 카운터)이었습니다.
**들여쓰기가 증거입니다.**

### 재구성이 드러낸 것

커밋된 파일을 그대로 재현하려 하자 생성기가 세 가지를 모르고 있었습니다. 셋 다 제품 쪽
사실이고, 알아낸 방법은 전부 **테스트가 red로 알려 준 것**입니다.

1. **path placeholder 하나에 값 하나**로는 부족합니다. probe 라우트의 행은 connector와
   dataset에 따라 달라지므로, `sql_connector`/`crm-customer-master` 한 쌍에서 파생한 스키마는
   다른 쌍이 돌려주는 키 **열한 개**를 빠뜨립니다. 이제 placeholder마다 여러 값을 union하고,
   connector·dataset id는 **제품에서 읽습니다** — 손으로 적은 목록이 이 파일의 짧은 수명
   안에서 이미 한 번 낡았습니다(`api_connector`·`file_connector`로 추측했는데 제품은
   `rest_connector`·`file_lake_connector`입니다). 테스트도 같은 두 출처를 읽으므로 양쪽이
   **구성상** 일치합니다.
2. **"아직 관찰 없음"과 "관찰했고 아무 타입이나"를 같은 `{}`로 적으면 안 됩니다.** 어떤
   데이터셋에서 `null`이고 다른 데이터셋에서 문자열인 필드가 `string`으로 공표되어, 라이브
   응답 `steward: None`이 계약 테스트를 깨뜨렸습니다 — 생성기가 만족시키려고 존재하는 그
   테스트입니다. sentinel을 분리했습니다.
3. **키가 데이터인 객체**는 `properties`가 아니라 `additionalProperties`로 공표해야 합니다 —
   아래 절.

### `/catalog/facets`의 `counts`가 시드의 도메인 값을 **필드 이름**으로 공표했습니다

```
counts: {'고객': number, '고객행동': number, '매출': number, '온톨로지': number, '마케팅': number}
```

문서로 클라이언트를 생성하면 map이어야 할 자리에 **필드 다섯 개짜리 struct**가 나옵니다.
데모 시드가 아닌 어떤 카탈로그에서도 깨지고, 시드 데이터가 타입 정의로 새어 나갑니다.
생성기는 **두 번째 카탈로그 상태**를 찍어 map과 field list를 구분합니다(새 도메인 데이터셋
하나를 공개 API로 온보딩). 다른 상태에만 있는 키는 데이터이고, 단지 **없는** 키는 아닙니다 —
`required`를 공표하지 않으므로 조건부 필드는 정상입니다.

데이터 키 노드는 넷입니다: `/catalog/facets.counts`, `audit/events[].details`,
`dataset_status_counts`, `/policy/decisions[].obligations`. 전부 값이 카탈로그·요청에 따라
달라지는 자리입니다.

**첫 판 규칙이 과도하게 발화했습니다.** 배열의 경우 union된 item properties를 두 번째 상태의
**첫 원소**와만 비교해서, 원소가 서로 다른 모양인 배열(observability의 alerts, SHACL shape
목록, JSON-LD `@graph`)이 전부 타입 없는 map으로 붕괴했습니다. 원소들의 키 집합을 union해서
비교하도록 고쳤고, 발화 지점이 9곳에서 4곳으로 줄었습니다.

### 지금 지켜지는 성질

* `scripts/generate_response_contract.py`가 **저장소에** 있고, docstring이 안내하는 명령이
  실제로 그 파일을 가리킵니다.
* 재생성이 커밋된 모듈을 **byte 단위로** 재현해야 합니다 — 손 편집이 이제 테스트를
  깨뜨립니다(두 번 연속 실행이 "already up to date").
* 테스트가 probe 설정을 생성기에서 **import**합니다. 사본 둘은 맞춰 둘 것이 하나 더
  생기는 것이고, 그 사본이 이 결함의 일부였습니다.
* 생성기의 각 규칙이 **그 규칙을 위한 가드**로 방어됩니다. 생성기를 변이시키고 **재생성한
  뒤** 확인했습니다: map 규칙 제거 → facets 행동 테스트 red, connector 하나만 찍기 →
  connector 전수 테스트 red, null/미관찰 혼동 → 라이브 일치 테스트 red. 생성기 파일 삭제는
  수집 단계에서 error, 계약 손 편집은 멱등성 테스트 red.

16개 라우트의 스키마가 바뀌었고(42개 항목·순서 동일), 전부 더 **넓은 관찰**의 결과입니다 —
공표가 좁아진 라우트는 없습니다.

이 절은 측정 기록이고 병합 허가가 아닙니다.

## 카탈로그에 대한 한 문장이 네 plane의 거부를 답했습니다 (2026-10-27 18:50Z)

```
403 '카탈로그 접근은 인증된 사용자만 가능합니다.'  /catalog/search       (참)
                                           같은 문장  /policy/decisions · /audit/events
                                           같은 문장  /ontology/change-log · /ontology/patches
                                           같은 문장  /graph/nodes/{id}
```

discovery 분기는 **action**으로 키가 잡히고 사유는 **자원 plane**을 이름 지었습니다. 같은
문자열의 앞선 수리가 "이 분기가 거부하는 모든 호출자에게 참"이라는 기준을 스스로 적어 두고,
그 수리가 열거한 호출자들에게만 충족했습니다.

**수리:** 선언된 plane 어휘(`policy.REFUSAL_PLANES`) + 자산 없는 fallback. `resource`를 그대로
쓰면 안 되는 이유는 이 분기가 자산으로도 도달한다는 것입니다(graph node id, dataset id) —
되읊으면 404가 닫아 둔 존재 oracle이 열립니다. 모든 변형이 `인증된 사용자만`을 유지하고
(mutation 거부가 같은 결정이고 테스트가 그 구절을 읽습니다), 문구는 `접근`을 씁니다
(`POST /ontology/patches`가 쓰기로 도달하므로 `읽기`는 같은 결함의 반복).

제가 쓴 가드 둘이 틀렸고 둘 다 측정이 잡았습니다 — ① `GET /ontology/patches`는 제품이
**증빙 읽기**로 분류하므로 제 기대가 틀렸고, ② 두 번째 테스트는 "모든 리터럴"을 덮는다고
적고 `evaluate(resource="…")`만 봐서 `"graph"`를 덮지 않았습니다(한 홉 전달). `graph`를
지우는 변이가 green이었고, 한 홉을 따라가도록 넓힌 뒤 red입니다.

변이 넷 전부 red.

### 닫지 않은 것

plane 어휘는 **인증 거부**만 덮습니다. 역할·민감도·목적 거부 사유는 데이터셋을 본 뒤에
나오므로 별개 범위입니다.

이 절은 측정 기록이고 병합 허가가 아닙니다.

## 증빙 팩이 "거부 자체가 증거"라고 적은 곳에서 그 거부가 증거를 남기지 않았습니다 (2026-10-27 18:05Z)

```
공표된 그대로, actor만 떼고:
  404 {'detail': 'dataset not found'}  /enterprise/connectors/sql_connector/probe?dataset_id=crm-customer-master
  403 (셋)                             /policy/decisions · /audit/events · /ontology/change-log
probe 라우트 exit 셋:
  404 익명(있음) -> audit+0 decision+0   404 익명(없음) -> audit+0 decision+0
  200 허용       -> audit+1 decision+1
```

`actor_scoped_proof_note`는 "403으로 거부되며, 그 거부 자체가 증거입니다"라고 적습니다.
넷 중 첫 번째에서 두 절이 다 거짓이었습니다. 404는 의도된 설계이고(존재 열거 차단, 403보다
강한 통제) 어디에도 공표되지 않아 독자는 데모 데이터셋이 없다고 읽습니다. 그리고 권한 없는
호출자가 실제로 도달하는 거부가 exit 셋 중 아무 증거도 남기지 않는 유일한 exit이었습니다.

**수리:** 결정을 존재 확인 앞으로 옮겨 하나만 내리고, 404 분기도 감사 행을 남깁니다. 응답은
불변 — `evaluate`가 두 사유를 자기 reason에서 가르므로 응답이 합쳐도 되는 것을 원장이
가릅니다. note는 코드 둘과 그 차이의 이유, 거부 행을 읽는 곳을 말합니다. 원장 읽기 셋이
감사 행을 남기지 않는 것은 결함이 아니고(plane 읽기에는 데이터셋이 없습니다), 처음 쓴
테스트가 넷 모두에 두 원장을 요구해 셋을 틀리게 지목했으므로 좁혔습니다.

변이 여섯 전부 red. M1은 `evaluate` 호출을 앞에 남겨 결정이 계속 쌓였으므로 순서까지
되돌리는 M6을 따로 돌렸습니다.

### 닫지 않은 것

거부 메시지의 plane은 이 절을 쓸 때 그대로였습니다 — `/policy/decisions`·`/audit/events`·
`/ontology/change-log`의 403이 "카탈로그 접근은 인증된 사용자만 가능합니다"라고 답했습니다.
**닫혔습니다**: 위의 "카탈로그에 대한 한 문장이 네 plane의 거부를 답했습니다" 절을 보십시오
(측정해 보니 셋이 아니라 네 plane이었고, 그래프 node 읽기도 포함입니다).

이 절은 측정 기록이고 병합 허가가 아닙니다.

## 더 완전한 관측이 공표를 좁혔고, 그 기제에 대한 설명은 세 번 틀렸습니다 (2026-10-27 18:05Z)

위 수리의 부수 효과로 `/policy/decisions[].obligations`가 map에서 닫힌 5-키 struct가
되었습니다. probe의 404 거부가 결정을 기록하기 시작해 첫 상태의 관측 키가 0 → 5가 되자,
두 번째 상태에 "새로운" 키가 남지 않아 `as_map_where_keys_are_data`가 조용해진 것입니다.
`policy.py`는 이 노드를 11개 키로 채우므로, 5개를 필드 목록으로 공표하는 것은 기존 가드
둘이 거부하라고 있는 좁히기입니다. 노드는 덜 가변적이 되지 않았습니다.

**분류기가 표본에 대해 보고합니다, 노드에 대해서가 아니라.** 생성기 주석은 같은 충돌로
되돌린 시도 둘을 이미 기록하고 있었고, 이번이 세 번째이며 제품 코드에서 왔습니다. 기제에
대한 설명도 세 번 틀렸습니다 — ① 제거된 헬퍼 지목(변이 green), ② `REQUIRED_QUERY` 페이지
크기 지목(선언 후 측정: **그 항목을 빼도 생성 파일 무변화**), ③ 실제로는 "첫 상태가 아무
키도 관측하지 못했다"는 우연.

**수리:** `DATA_KEYED_BY_DECLARATION` 선언 + `policy.py` 소스에서 네 표기를 읽어 도출한
11키 어휘와 비교. 방향은 `declared - observed`이므로 도출이 불완전하면 규칙이 덜 발동할
뿐이고, 관측이 늘어 격차가 닫히면 멈춥니다(단조). 틀린 설명 둘은 측정과 함께 정정했습니다.

### 닫지 않은 것

두 상태 diff 분류기 자체는 그대로이고 나머지 네 data-keyed 노드는 여전히 표본 차이로
판정됩니다. "조건부로 없는 필드"와 "키가 데이터인 노드"를 두 표본만으로 구조적으로 가를 수
없다는 것이 원인이며(생성기의 비대칭 주석이 그 이유를 기록합니다), 남은 넷의 일반 해법은
별개 범위입니다.

이 절은 측정 기록이고 병합 허가가 아닙니다.

## `resolve`의 `aliases`가 데이터셋의 업무 용어를 개념의 동의어로 게시했습니다 (2026-10-27 17:10Z)

```
POST /ontology/resolve {"text": "이탈 고객"}
  term=고객 / 활성 고객 / 이탈 / 비즈니스 용어   aliases=['고객', '이탈']   (네 행 전부 동일)
  term=이탈 고객                                aliases=['churn 고객','이탈 고객','탈퇴 고객','휴면 고객']
GET /ontology/search?q=고객 · GET /ontology/concept/고객
                                              aliases=['고객','customer','클라이언트','이용자','회원']
POST /ontology/resolve {"text": "매출"}
  term=전환  aliases=['매출']  defined_in_vocabulary=False
```

한 리스트가 개념 자신, 본문에 나타난 선언 별칭, **첫 매핑 데이터셋의 업무 용어**를 함께
누적했습니다. 데이터셋 용어는 무엇의 동의어도 아니므로, glossary가 정의하지 않는 `전환`이
`매출`을 자기 별칭으로 달았습니다. 같은 이름의 필드를 게시하는 형제 둘은 개념의 실제 별칭
집합을 돌려주며 서로 일치합니다. 정상적인 집합을 담은 단 한 행은 **다른 분기**(정확 구절
일치)에서 와서, 필드 전체를 믿을 만하게 보이게 했습니다.

**수리:** `aliases`는 개념 자신의 집합으로 좁히고, 일치한 토큰은 `matched_terms`로 이름을
바꿔 유지합니다. 점수 계산은 불변(테스트가 1.0·0.55·0.5를 고정). 정확 구절 분기는
`search_concepts`의 술어를 다시 계산해 본문에 실제로 있던 이름만 싣습니다.

변이 넷 전부 red. M3(데이터셋 용어의 점수 기여 제거)에서 제 점수 단언이 처음 통과했는데,
`... == 0.5 if "전환" in rows else True`로 쓰여 있어 행이 사라지면 공허하게 참이 되기
때문입니다. 무조건으로 바꿨습니다 — 이 문서가 `or True`로 끝나는 단언에 대해 이미 기록한
것과 같은 종류입니다.

### 닫지 않은 것

랭킹 인공물은 그대로입니다. `이탈 고객`을 해석하면 `매출`이 0.5로 올라오고, 이유는 `매출`의
첫 매핑 데이터셋이 `고객`을 용어로 담기 때문입니다 — `docs/requirements-coverage.md`의
LLM-001이 별개 격차로 이미 기록한 것이고 이 수리는 점수를 바꾸지 않습니다. 바뀐 것은
`matched_terms`가 그 인공물을 **읽을 수 있게** 만든다는 점뿐입니다.

이 절은 측정 기록이고 병합 허가가 아닙니다.

## 어휘 쓰기 둘이 아무것도 게시하지 않고 게시했다고 답했습니다 (2026-10-27 16:30Z)

```
review(approve) on 고객  -> 200 published_concept '고객' · revision 1->1 · digest 그대로
                            감사 행 result: 'approved_without_publication'
upsert 고객              -> 200 published_concept '고객' · revision 2->2 · digest 그대로
POST /ontology/concepts {..., ontology_content_digest: 'deadbeef'*8} -> 200 (pin 무시, 버전 신원 없음)
```

승인이 게시된 정의를 덮어쓰지 않는 것은 의도된 설계이고, 원장은 어느 쪽인지 이미 말합니다 —
응답만 말하지 않았습니다. 그리고 읽기 라우트가 409/400으로 집행하는 pin 토큰을 두 쓰기가
조용히 버렸습니다(타입 있는 요청 모델에서 pydantic이 알 수 없는 필드를 버립니다).

**수리:** `publication_status`(`published`/`existing_definition_kept`)를 두 응답에 공표하고
`published_concept`는 실제 게시에만 이름을 싣습니다. 두 쓰기가 첫 쓰기 전에 읽기와 같은
헬퍼로 pin을 검사하고 `ontology_version`을 스탬프합니다.

### 닫지 않은 것

이미 게시된 정의를 **개정하는 경로 자체는 없습니다**(ONT-005 별개 범위). 이 수리는 그 사실을
말하게 만든 것입니다.

## preview가 합성 행을 아무 표시 없이 내보냈습니다 (2026-10-27 15:55Z)

```
crm-customer-master  has_more False  row_count 2  profile row_count 1,200,000
crm-event            has_more False  row_count 2  profile row_count 54,000,000
응답의 provenance 키: ['sampling_note'] (한국어 문장 하나)
double로 선언된 컬럼의 값: "touch_revenue_krw-sample-1"
```

형제 라우트 `/browse/query`는 자기 mock을 `measurement_status`·`rows_source`·
`row_count_source`로 전부 라벨하므로, 거기서 규칙을 배운 통합자는 preview 행을 실데이터로
읽습니다. 그리고 fallback 값이 자기 선언 타입으로 파싱되지 않습니다.

**수리:** 같은 어휘로 `sample_provenance`를 공표하고, `has_more` 옆에
`declared_source_row_count`를 놓고, 선언 철자를 family로 정규화하고, 모양을 맞출 수 없는
타입은 `untyped_sample_columns`로 이름을 공표합니다.

### 닫지 않은 것

값은 여전히 전부 문자열입니다(`decimal`도 `'129000.00'`) — JSON 숫자로 바꾸는 것은 별개 계약
변경입니다. 2행 고정 샘플 자체도 그대로입니다(BRW-002).

## 정정 — "원장을 읽으면 원장이 밀린다"는 발견은 **이미 공표된 파라미터로 해소됩니다** (2026-10-27 16:05Z)

여정 감사가 medium으로 올린 항목입니다: `GET /policy/decisions`를 읽을 때마다 결정 행이
하나 쌓이므로 500번 검토하면 유일한 무필터 뷰가 전부 검토자 자신의 읽기가 된다는 것. 재서
확인했고, **프레이밍을 좁힙니다.** 증빙 읽기의 결정 행은 `resource: "evidence"`를 달고
있습니다 — 데이터 접근 행과 **구분 가능하고**, 이미 공표된 `?resource=` 필터가 그것을
완전히 제외합니다:

```
preview 1회 + 원장 읽기 30회 뒤
  /policy/decisions?limit=500                        -> evidence 31행, crm-customer-master 1행
  /policy/decisions?limit=500&resource=crm-customer-master -> 1행 (그 preview)
```

즉 "자기 행에 도달할 수 없다"는 쪽은 실제 결함이었고 이번 라운드에서
`offset`·`decision_id`로 닫았지만, **"원장 읽기가 원장을 가린다"는 쪽은 스코프 없는 기본
뷰의 성질**이고 해법이 이미 라우트에 있습니다.

**바꾸지 않기로 한 것.** 기본 뷰에서 `resource: "evidence"` 행을 숨기지 않습니다 — 누가
원장을 읽었는지도 감사 대상이고, 그것을 기본에서 빼면 이 저장소가 이번 라운드 내내 수리한
"공표된 숫자가 전부인 것처럼 읽히는" 결함을 증빙 자체에 만드는 셈입니다. 라우트가 bare JSON
배열을 돌려주므로 응답에 안내 문구를 넣을 자리도 없습니다(배열 → 객체는 별개 계약 변경).
그래서 남은 격차는 **발견 가능성**이고, README의 라우트 항목에 스코프 방법을 적는 것으로
닫습니다.

## 호출자가 자기 200이 알려 준 증빙 행에 도달할 수 없었습니다 (2026-10-27 15:30Z)

```
자기 preview가 돌려준 policy_decision_id: 직후 조회됨 / 600요청 뒤 조회 안 됨
공표 선택자: limit, resource, user 뿐 · offset·cursor·decision_id는 받아들이고 무시
```

모든 store가 최신순 정렬 뒤 자르므로 호출자 자신의 행이 가장 먼저 밀려납니다. 데이터셋 경로도
같아서, 자격증명 없는 거부 600건이 그 데이터셋의 정당한 접근 이력 전체를 밀어냅니다.

**수리:** `offset`·`decision_id`를 읽기 경로 끝까지(라우트 3, reader 2, SQLite·Postgres SQL).
두 증빙 테이블은 `decision_id`를 일급 컬럼으로 이미 들고 있습니다. 병합 reader는 merge 전에
`offset + limit`까지 over-fetch합니다.

### 닫지 않은 것

`offset`은 안정 커서가 아닙니다 — 증빙 읽기가 원장에 결정 행을 남기므로 연속한 두 요청의
페이지가 그 수만큼 겹칩니다(가드가 상한으로 단언). 안정 커서는 decision `recorded_at` 공표가
선행 조건이고 POL-005가 그 부재를 기록합니다. in-memory fallback의 2000행 보존 창도 그대로
입니다. Postgres SQL은 서명 가드만 걸려 있습니다(서비스가 필요).

## 쓰기 응답이 재전송 가능했고, 재전송하면 저장된 locator가 지워졌습니다 (2026-10-27 14:15Z)

```
POST {source_system: 'warehouse-postgres'}    -> 200, echo 'redacted', 저장 'warehouse-postgres'
PATCH {title: ..., source_system: 'redacted'} -> 200, 저장 'redacted'
audit details -> before == after == 'redacted'  (파괴가 "변경 없음"으로 기록)
```

자격증명이 없는 가장 덜 민감한 값이 가장 완전하게 파괴됩니다. 하류의 `source_kind` 분류도
`source_system`에서 나오므로 데이터셋 취급 자체가 조용히 바뀝니다.

**수리:** 쓰기는 마커를 저장하지 않습니다(create·patch 양쪽, typed 거절, 이유가 필드와 해법을
말함). 그리고 원장은 투영이 보여 줄 수 없을 때도 필드가 바뀌었는지 말합니다
(`source_system_changed`, 원시 값으로 계산).

### 닫지 않은 것

`redacted`를 실제 locator 이름으로 쓰는 데이터셋은 등록할 수 없습니다(거부가 그것을 말합니다).
리댁터가 평범한 라벨을 마커로 바꾸는 것 자체도 그대로입니다 — 라벨과 비밀번호를 구조로
구분하는 일은 하지 않았고, 쓰기 경로만 막았습니다.

## 게시한 데이터셋이 발견 라우트 둘에 보이지 않으면서 둘 다 withheld 0을 공표했습니다 (2026-10-27 13:45Z)

`고객`을 term으로 선언한 데이터셋을 온보딩·게시한 뒤 `user=data-admin`으로:

```
GET  /catalog/search?q=고객    -> 포함  |  GET /ontology/term/고객/graph -> 포함
GET  /ontology/concept/고객    -> 없음, withheld_dataset_count: 0
POST /llm/search {고객}        -> 없음, withheld_dataset_count: 0
```

`withheld_dataset_count`는 짧은 목록이 전체 매핑으로 읽히지 않게 하려고 있는 필드이고, 여기서
짧은 목록이 전체 매핑으로 읽혔습니다. 근본 원인(import 시점 고정)은 **범위 메모로** 기록돼
있었고, 그래서 응답이 전체 커버리지를 주장한다는 사실은 기록돼 있지 않았습니다.

**수리:** 읽는 곳에서 파생(`concept_dataset_index()`). 재구축 비용은 `resolve_terms` 자신의
2.5%이므로 캐시도 무효화도 새 모듈 상태도 없습니다 — 오히려 복원 대상 상태가 하나 줄었습니다.
거짓이 된 산문 다섯 곳(requirements 비고 둘, implementation-compliance, README,
ontology_version·api 주석)을 같이 좁혔습니다.

### 닫지 않은 것

맵은 여전히 버전 범위 밖입니다 — 매핑이 바뀌어도 `ontology_revision`은 움직이지 않고
`sdp:datasetMappingIsVersioned false`는 그대로 참입니다. tenant 술어도 여전히 맵에는 없고
`concept_assets`가 scope를 적용합니다.

## 가정 질문의 답이 다른 tenant의 원장에 라벨 없이 기록됐습니다 (2026-10-27 13:30Z)

`POST /policy/decision`의 행은 subject의 tenant 원장에 들어가고, `provenance` 라벨은
감사자가 질문을 사건으로 읽지 않게 하려고 있습니다. `policy.evaluate`의 세 분기가 그 인자를
받지 못했습니다 — `analyst`가 `external-analyst`에 대해 물으면:

```
discover_catalog allow · register_dataset deny · search allow  -> 라벨 없음
preview deny -> evaluation_mode/asked_by/subject_is_caller 있음
```

**수리:** 세 분기에 인자를 넘기고, 엔진의 action 어휘에서 파생한 전수 가드와 AST 가드
(이 함수의 모든 `_decision` 호출이 인자를 넘기는지)를 더했습니다.

### 닫지 않은 것

`subject`를 호출자가 주는 설계 자체는 그대로입니다 — 라벨은 읽을 수 있게 할 뿐 막지 않으며,
그 경계는 Keyverse 소관입니다.

## 한 payload가 `missing: []`와 `completeness_score: 0.909`를 함께 공표했습니다 (2026-10-27 13:30Z)

`recompute_scores`에 `required_total = 11`짜리 세 번째 집계가 남아 있었고, 거기에 validator가
요구하지 않는 `tags`가 들어 있었습니다. `tags`만 다른 두 데이터셋이 각각 1.0과 0.909(=10/11)를
공표하면서 둘 다 `missing: []`·`is_valid: true`입니다. 공표 위치는 `/catalog/search` 행,
데이터셋 상세, JSON-LD이고 KPI 게이트는 `metadata_completeness`만 읽습니다.

**수리:** `REQUIRED_METADATA_FIELDS`에서 파생. 태그는 `recommended_score`에서만 셉니다.

### 닫지 않은 것

두 필드가 항상 같은 값이 되었으므로 `completeness_score`는 중복입니다. 공표된 필드를 지우는
것은 JSON-LD 매핑까지 건드리는 별개 변경입니다.

## 리뷰 큐의 `confidence`가 제안문의 글자 수였습니다 (2026-10-27 13:00Z)

`POST /ontology/patches`, `GET /ontology/patches`, 그리고 자격증명 없이 읽히는
`GET /enterprise/steward-review`가 `len(suggestion) / 220.0`을 confidence로 공표했습니다.

```
len=  8  confidence=0.3     "해지 고객 비율"   | len=300  confidence=0.95  "ㅁ"*300
GET /enterprise/steward-review (actor 없음) -> 최고 confidence 행은 ㅁ 300자
```

호출자가 confidence를 줄 수도 없으므로(route는 concept·suggestion만 읽습니다) 제품에 근거가
없습니다. **수리:** `confidence: null` + `confidence_basis: "not_measured"`. 필드는 유지합니다
— 스튜어드가 읽어도 되는 제안 내용으로 이미 고정돼 있습니다.

### 닫지 않은 것

두 배열(`patches`, `review_items`)의 **행 모양이 공표 응답 계약에 없습니다**(`items: {}`) —
생성기 프로브 시점에 큐가 비어 있기 때문입니다. 구매자는 그 원소에 대해 `Any`를 받습니다.

## facet 라우트가 공표된 적 없는 어휘를 집행하고, PRD가 facet이라고 적은 둘을 거부했습니다 (2026-10-27 13:00Z)

여정 검증 둘이 CONFIRMED로 돌려준 발견입니다.

```
GET /catalog/facets?field=tags|terms -> 400 "unsupported facet field"
README grep -in facet -> 0건 · OpenAPI field 파라미터에 enum·description 없음
```

유효한 값을 알 방법이 소스뿐이었고, 거부는 거절된 값도 지원 집합도 말하지 않았습니다. 형제
라우트(`?status=`)는 `requested`/`known_statuses`를 담는 반대 패턴을 이미 씁니다. 그리고
거부된 두 차원이 PRD가 facet으로 적은 둘입니다 — `list_facet_counts`의 list 분기는 허용된
스칼라 여섯 중 어느 것도 닿을 수 없었으므로, 능력은 거부되던 차원들을 위해 있었습니다.

**수리:** 어휘를 `FACET_FIELDS` 상수로 올리고 `tags`·`terms`를 더하고, 거부에
`requested`/`known_fields`를 담고, OpenAPI description과 README 라우트 목록을 그 집합에서
파생시킵니다.

### 닫지 않은 것

PRD 표 전체를 파싱해 "PRD가 facet이라고 적은 차원이 집합에 다 있는지"를 대조하지는 않습니다 —
두 값에 대해서만 단언합니다.

## 선언만 되고 집행되지 않는 행 레벨 필터를 "적용됐다"고 공표했습니다 (2026-10-27 10:15Z)

구성된 구매자 여정(온보딩 → 발견 → preview)을 `TestClient`로 끝까지 몰아 본 라운드에서
나왔습니다. 표면별 감사는 이 obligation을 여러 번 지나쳤고, 매번 "있다"만 확인했습니다.

`crm-event`(이 엔진에서 obligation이 닿는 유일한 `sensitivity: high` 데이터셋):

```
published columns              ['event_id', 'customer_id', 'event_timestamp', 'device_id']
'business_unit' among them     False
purpose='analysis'   applied_row_filter=['business_unit = current_user_unit']  row_count=2
purpose='marketing'  applied_row_filter=None                                   row_count=2
rows byte-identical            True
audit details                  {'row_filter': [...], 'returned_rows': 2, ...}
draft assumptions              ['행 레벨 필터 적용: business_unit = current_user_unit']
'business_unit' in drafted SQL False
```

술어는 선언되지 않은 컬럼을 가리키고, 행은 필터 없는 행과 같은 바이트이며, 감사자가
`decision_id`로 join하면 부서 범위 조회로 읽힙니다. 행 레벨 집행이 없는 것은 PRD §6.2가
Phase 2로 둔 **의도된 범위**입니다 — 결함은 `applied_`라는 이름과 원장 행입니다.

**수리:** 술어가 공표되는 모든 곳에 집행 상태를 같이 공표합니다 — obligation에
`row_filter_enforcement: declared_not_enforced`, preview에 `row_filter_summary`
(`declared_predicates`/`filter_enforced`/`enforcement_note`), 원장에
`declared_row_filter` + `row_filter_enforced: false`, draft assumption은 SQL에 없다는 사실.
`tests/test_row_filter_is_declared_not_applied.py`가 이것을 성질로 고정합니다(변이 5건 red).

### 닫지 않은 것

행 레벨 집행은 없습니다. `PolicyDecision`에 `purpose`가 없다는 POL-005의 본래 지적도
그대로입니다 — 그 비고에서 사실이 아니게 된 "unexplained" 한 단어만 고쳐 재생성했습니다.

## 거부된 SQL 드래프트가 decision은 남기고 감사 이벤트는 남기지 않았습니다 (2026-10-27 10:15Z)

`docs/requirements-coverage.md:559`가 NFR-SEC-005를 `implemented`로, "두 구멍을 찾아
닫았다"고 공표합니다. 한 라우트에 네 개가 더 열려 있었습니다. 호출당 델타:

```
success / policy_denied(purpose)                 decisions +1  audits +1
policy_denied(keyword) / invalid_columns
  / invalid_group_by / draft_rejected_by_validator  decisions +1  audits +0
dataset_not_found / invalid_date_window           decisions +0  audits +0   (대칭, 구멍 아님)
```

AST로 세면 decision 이후 종료점은 여덟 개이고 넷은 요청 계약이 먼저 거부해 HTTP로 닿지
않습니다. **수리:** 형제 라우트 `execute_query`처럼 모든 거부를 감사하는 지역 헬퍼로 모으고,
decision 이후의 모든 `return`이 그 헬퍼를 지나는지를 AST 가드가 단언합니다.

### 닫지 않은 것

`/browse/query`는 pre-policy 거부도 `policy_stage`를 붙여 감사하고, 드래프트 라우트는 그
경로를 기록하지 않습니다. 어느 쪽이 옳은지는 결정하지 않았습니다.

## 깨끗한 데이터셋의 드래프트가 "허가되지 않은 테이블"로 거부됐습니다 (2026-10-27 10:15Z)

`source_system`의 마지막 segment만 다른 두 데이터셋:

```
s3://analytics/events/2024    /validate is_valid=true · /policy/decision allow
                              /llm/draft-query -> 400 unauthorized_table_reference
s3://analytics/events/orders  /llm/draft-query -> 200  FROM orders
```

허가되지 않은 것은 없습니다. 질의가 지목하는 유일한 테이블은 제품이 그 데이터셋의
`source_system`에서 파생한 이름이고, 선행 숫자는 식별자가 아니므로 allow-list의 파서가
테이블을 찾지 못합니다(`2024`) 또는 다른 것을 찾습니다(`2024_q1` → `_q1`). 날짜로 파티션된
레이크 prefix가 이 모양입니다. 이유가 거짓이고, 파생 이름·locator·원인·수리 방법 중 아무것도
말하지 않습니다.

**수리:** 열거가 아니라 파서에 묻습니다 — `_reads_back_as_one_table`이 거짓이면 참된 이유
(`unquotable_source_table`)로 거부하고 파생 이름·(자격증명을 지운) locator·
`postgresql.table` distribution 선언을 메시지에 담습니다. 24개 절 키워드를 열거한 선행
수리와 같은 계열이고, 이쪽은 열거 없이 둘 다 덮습니다.

### 닫지 않은 것

컬럼 이름이 절 키워드인 경우는 열려 있습니다 — `select`라는 컬럼을 `group_by`로 주면
`SELECT select, count(*) ... FROM orders`를 200으로 받습니다. 대상 엔진이 거부할 SQL이고,
이 게이트의 키워드 목록에 `select`가 없어 자기 검사도 통과합니다.

## 배포 endpoint의 자격증명은 어디에서도 지워지지 않았고, PATCH는 그 필드를 조용히 버렸습니다 (2026-10-27 10:15Z)

위 거부가 가리키는 수리 방법이 실제로 동작하는지 확인하다 나왔습니다.

```
PATCH /catalog/datasets/{id} distributions: [postgresql.table] -> 200
저장된 distributions                                            -> [csv]  (변화 없음)
POST  /llm/draft-query                                          -> 400 (그대로)

endpoint에 자격증명을 담아 등록하면
POST /catalog/datasets      -> 200, 응답에 secret: True
GET  /catalog/datasets/{id} -> 응답에 secret: True, query token: True
```

`DatasetPatchRequest`에 `distributions`가 없습니다 — 다른 모든 컬렉션 필드는 있고, `license`가
같은 결함의 첫 사례로 이미 기록돼 있습니다. 그리고 `redacted_source_system`의 규칙("모든
경로에서, 인가된 경로에서도 지운다")을 같은 모양의 URL인 `endpoint`가 전부 비켜 갔습니다.
리댁터는 그 URL을 이미 올바르게 처리하므로 라우팅이 없었을 뿐입니다.

**수리:** `published_distribution` 하나를 `discovery_view`·`mutation_view`·
`audited_patch_values`·JSON-LD 노드에 적용(locator 자체는 계속 공표), `distributions`를 patch
계약에 추가, create/patch 차집합이 선언된 면제 셋(`id`·`tenant_id`·`owner`)과 같은지를 구조
가드로 단언. patch 루프의 죽은 분기(컬렉션 일곱을 열거해 `None`을 skip — 바로 다음 조건과
결과가 같아 아무 일도 하지 않으면서 그 일곱에만 적용되는 규칙처럼 읽혔습니다)도 제거했습니다.

### 닫지 않은 것

`owner`는 여전히 패치할 수 없고, 이 수리는 그 결정을 선언만 했습니다. endpoint 자격증명이
**저장**되는 것도 그대로입니다 — 공표에서만 지웁니다(`source_system`도 같습니다).

## 중앙 Security Scan 게이트가 체크 목록에 **아예 없습니다** (2026-10-27 05:25Z)

`AGENTS.md` 13–14행은 모든 PR에 중앙 Security Scan(`osv-scan` + diff-scoped
`dependency-review` + repo-wide `trivy-fs`)을 필수로 요구합니다. 현재 head `06b26be`의
체크는 4건뿐이고(로컬 셋 + CodeRabbit skipped) **Security Scan 세 건은 실패가 아니라
생성되지 않았습니다.**

`coderabbitai[bot]`가 먼저 지적했고(comment 6434387988) 1차 출처로 확인했습니다.

### stacked base 때문이 아닙니다 — 2026-10-02에 저장소 전체에서 멈췄습니다

| PR | base | Security Scan | 시점 |
|---|---|---|---|
| `#107` | main | 세 건 **success** | 2026-10-02 05:48Z |
| `#104` | main | 세 건 **skipped** | 2026-09-19 19:48Z |
| `#111` | main | **없음** | updated 2026-10-08 |
| `#112` | main | **없음** | updated 2026-10-14 |
| `#102` | `docs/product-technical-gap-baseline` | **없음** | — |

`main`을 target하는 PR에서도 2026-10-02 이후 생성되지 않습니다. 이 문서의 마지막 저장소
워크플로 성공(2026-10-02T09:03:05Z)과 하드 잠금(2026-10-02 18:44Z)과 같은 경계입니다.

### `88c39a3`의 결함과 다릅니다

그것은 `tests.yml`의 `pull_request: branches: [main]` 필터가 **stacked PR에서만** 게이트를
없앴던 것이고 이 저장소에서 고칠 수 있었습니다. 이것은 다른 결함입니다 — 로컬 워크플로는
`failure` 행을 남기고, 중앙 워크플로는 **행을 남기지 않습니다.** 중앙 워크플로는
`ContextualWisdomLab/.github`의 ruleset이 주입하므로 이 저장소에서 고칠 수 없습니다.

**2026-10-27 정정 — 이것을 "같은 과금 잠금의 다른 증상"이라고 적었고, 그 인과는 제가
측정한 것이 아닙니다.** `coderabbitai[bot]`이 지적했고(comment `6434535662`·`6434551848`)
맞습니다. 제가 가진 것은 둘입니다: (1) 미생성 경계가 하드 잠금 시점과 **겹친다**,
(2) `main`을 target하는 PR에서도 사라졌으므로 **stacked base만의 문제라는 설명은
배제된다**. 그 둘은 "잠금이 원인이다"를 세우지 못합니다. 세우려면 중앙 워크플로의
적용·트리거·실행 기록을 봐야 하고, 그것은 `ContextualWisdomLab/.github`에 있어 이
세션이 읽을 수 없습니다(저장소 범위 바인딩). 그러므로 **원인 미확인**으로 읽으십시오.
같은 이유로 "과금 잠금 해제가 중앙 게이트 복구의 유일한 길"도 확정된 주장이 아닙니다.

**무엇이 바뀌지 않는지가 중요합니다.** 미생성은 여전히 **통과가 아닙니다**. 원인을
모른다는 것은 그 게이트에 판정이 없다는 사실을 약화시키지 않고, 오히려 그 반대입니다 —
원인을 모르는 공백은 아는 공백보다 더 열려 있습니다.

### 판정을 읽는 규칙에 추가

**실패한 Security Scan이 없다는 것을 통과로 읽지 마십시오.** 이 head에서 그 게이트는 판정이
없습니다. 이 문서의 기존 규칙("queued는 통과가 아니다", "다른 check의 초록은 trivy-fs의
판정을 대신하지 못한다")과 같은 계열이고, 더 약한 형태입니다 — **행 자체가 없는 것**은
queued보다 읽기 쉽게 오해됩니다.

### 같은 라운드의 정정: `mergeable_state`를 과하게 읽었습니다

직전 기록에서 "세 체크는 필수가 아니고 과금 잠금은 병합 블로커가 아니다"로 적었습니다.
`mergeable: true`는 **충돌 없음**이고 병합 허가가 아니며, `unstable` 하나로 비필수 여부나
조직 요건 충족을 확정할 수 없습니다(base branch protection은 403으로 읽을 수 없음).
측정이 지지하는 것은 "GitHub이 `blocked`이 아니라 `unstable`로 보고하고 충돌이 없다"까지이고,
위 Security Scan 미생성은 **판정 없는 필수 게이트가 하나 더 있다**는 사실을 더합니다.

이 절은 측정 기록이고 병합 허가가 아닙니다.

## ClusterFuzzLite 엔트리포인트가 처음으로 실제 퍼징됐습니다 (2026-10-27 05:20Z)

`5607d8c`가 고친 `fuzz/fuzz_query_safety.py`는 그때까지 import에서 죽어 한 입력도 퍼징하지
못했고, 수리는 "import가 통과한다"까지만 확인돼 있었습니다(이 문서의 해당 절이 그렇게 적어
뒀습니다). 실행으로 확인했습니다 — **79,381 inputs / 31s, `cov: 91 ft: 229 corp: 54`,
crash 0**. `declared_relation` near-miss 모드도 그 안에서 돌았습니다.

이 하네스는 `run_atheris.sh`의 목록에 없으므로 그 스크립트를 돌린 과거 실행에는 포함된 적이
없습니다 — 그래서 이 하네스에 한해 처음입니다.

### 저장소 최초가 아닙니다 — 아래 2026-10-03 절을 보십시오

그 절이 이미 head `2bdd3c6`에서 Python 3.12 + `requirements-test.txt` +
`fuzz-requirements.txt` + `FUZZ_SECONDS=60`으로 **네 하네스**를 돌려 두었고 실행량이 이번보다
훨씬 큽니다(`fuzz_draft_sql` 2,276,110 대 306,785). 이번에 네 하네스를 같이 돌린 것은
재확인이며(537,562 inputs, 각 21초, exit 0), 새 사실이 아닙니다.

### 3.12 실행도 최초가 아니라 갱신입니다

2026-10-03 측정은 스위트 **258 passed, 8 skipped** 시점이고 지금은 **1698**입니다. 그
측정은 현재 head에 대해 아무것도 말하지 않으므로 다시 돌렸습니다 — **1698 passed,
31 skipped**, 3.11과 동일.

### 제 오류: 가정이 문서보다 오래 살아남았습니다

이 세션은 "로컬에 Atheris wheel이 없다"를 여러 번 적었고, 근거는 3.11 venv 하나였습니다.
**이 문서에 3.12에서 설치해 돌린 기록이 이미 있었습니다.** 환경에 대한 가정을 반복하기 전에
이 문서를 검색했어야 했고, 그 검색이 지금 제 주장을 반증했습니다("처음"이라는 표현을 두 번
썼고 둘 다 과장이었습니다).

### 닫지 않은 것

* **CI 자체는 돌지 않았습니다.** 같은 인터프리터·핀이지만 같은 러너가 아닙니다.
* 이번 퍼징 예산은 20~31초로 CI의 PR 예산(60초)보다 짧고 nightly(300초)보다 훨씬 짧습니다.
  crash 0은 그 예산 안에서의 결과입니다.

이 절은 측정 기록이고 병합 허가가 아닙니다.

## 같은 sentinel 혼동이 `union`에 **세 군데** 있었습니다 (2026-10-27 05:00Z)

`None`("아직 관찰 없음")과 `{}`("관찰했고 아무 타입이나")의 구분을 기본값 셋이 전부 틀리게
적었습니다. 앞 커밋이 `properties` 쪽 하나를 고쳤고, 나머지 둘:

* `derive([])`가 `items: {}` — 빈 배열은 원소에 대해 아무것도 관찰하지 않습니다. probe
  페이로드 하나의 `lineage_inputs: []`가 다른 페이로드의 `string`을 지웠습니다. 수리 후
  노드 여덟 개가 원소 타입을 되찾습니다.
* map ∪ struct에서 struct를 "any"로 읽었습니다. struct 관찰은 map 값에 대해 말합니다(값들의
  union). "any"로 읽어 struct 관찰 하나가 `counts`·`dataset_status_counts`의 `number`를
  지웠습니다.

**근본 원인은 하나이고 현장은 셋입니다.** 첫 수리에서 "같은 기본값이 재귀에도 쓰인다"고
적었지만 같은 *함수*의 다른 두 분기는 보지 않았습니다.

## `demo_context`가 non-nullable로 공표됐습니다 (같은 커밋)

`buyer_demo_context_for_dataset`는 buyer-demo 도메인 밖 데이터셋에 `None`을 돌려주고 모든
시드 데이터셋은 그 도메인 안에 있습니다. `null`이 관찰된 적이 없으니 non-nullable 객체로
공표되고, 문서로 만든 클라이언트는 도메인 밖 첫 데이터셋에서 깨집니다.

세 번째 probe 상태(도메인 밖 데이터셋 하나)를 **map 규칙 뒤에** 타입만 union합니다.

### 틀린 시도 둘을 기록합니다

(a) 두 번째 상태를 공표 타입에 union, (b) 그 데이터셋을 첫 관찰 앞에서 온보딩. 둘 다 map
규칙을 파괴합니다 — 규칙은 스키마 키 집합을 두 번째 상태와 비교하므로, 그 키가 이미
스키마에 있으면 다를 것이 없습니다. `details`가 map → 닫힌 struct로 되돌아갔습니다. 순서가
성질이므로 가드가 생성기 소스에서 순서를 단언하고 map 규칙의 결과도 같이 봅니다. 세 번째
상태를 앞으로 옮기는 변이가 **5건**을 red로 만듭니다.

### 닫지 않은 것

`demo_context`는 이제 `{}`("객체이거나 null")입니다 — 객체일 때의 **내부 모양은
공표되지 않습니다.** nullable 객체를 표현하려면 `anyOf`나 `type: [object, "null"]`이
필요하고 이 생성기에는 둘 다 없습니다. 같은 한계가 null로 관찰된 모든 필드에 적용됩니다
(`steward` 등). 별도 항목입니다.

이 절은 측정 기록이고 병합 허가가 아닙니다.

## 산문 넷이 자기 코드와 어긋났고, 가드 하나는 네 철자 중 하나만 봤습니다 (2026-10-27 04:35Z)

### obligations: 아홉 키 중 넷만 공표

제품이 결정 분기별로 `refusal_cause`·`known_actions`·`unmapped_published_action`·
`actor_tenant_id`·`redact`를 더 설정하는데 공표는 닫힌 4키 struct였습니다. `required`가
없으므로 틀린 것은 아니고 절반 넘게 침묵한 것입니다.

원인은 ledger 페이지 크기입니다. newest-first·기본 100행이고 probe 순서가 이 라우트를 읽기
전에 100건 넘게 기록하므로, 거부 분기 행이 페이지 밖에 있었습니다. probe의 `limit`을 500
(라우트 상한)으로 올리니 map으로 분류됩니다.

### 효과를 보일 수 없는 기계장치를 지웠습니다

그 분기를 일부러 구동하는 헬퍼를 먼저 썼습니다. 넣고/빼고 재생성한 출력이 **byte 단위로
동일**합니다 — 평범한 probe가 이미 전부 건드리고 있었습니다. 알려 준 것은 헬퍼 삭제 변이가
**green으로 돌아온 것**입니다. 그 상태로 남기면 "이게 성질을 지탱한다"는 거짓 docstring이
딸린 죽은 코드가 됩니다. 지웠고, 실제로 일한 한 줄에 측정을 적었습니다.

### data-keyed 목록이 양방향으로 틀렸습니다

"four nodes"라 적고 `/catalog/datasets/{dataset_id}/audit[].details`를 빠뜨렸고,
`/policy/decisions[].obligations`를 넣었는데 그 노드는 당시 struct였습니다. 다섯 모두
스키마 주소 방식대로 적고, 가드가 스키마에서 파생해 양방향 비교합니다.

### 목록 가드가 열거가 아니라 docstring 전체를 봤습니다

열거에서 노드를 지워도 아래 설명 단락의 언급으로 통과했습니다 — 변이가 green. 열거 문장만
보도록 좁혔습니다. 이 라운드에서 "선언을 보고 효과를 보지 않는 가드"의 일곱 번째입니다.

### detail 가드의 구멍

`str(exc)`만 매칭하고 `f"{exc}"`·`.format(exc)`·`% exc`는 못 봤습니다. 오늘 쓰는 핸들러는
없으므로 제품 결함이 아니라 가드 구멍입니다. 검출기를 한 함수로 빼서 가드와 자기 검증
테스트가 같은 코드를 쓰게 했습니다.

### 산문 셋

* `orchestrator.py`: "Relational SQL is drafted only for a relational source" — 아래 코드에
  대해 거짓. 다섯 시드 전부에 PostgreSQL을 emit하고 셋은 비관계형입니다. 수리는 거절이
  아니라 공개였습니다.
* `/enterprise/auth/oidc-preview`의 `actor`: "없으면 거부됩니다" — 거짓. 200입니다. 형제
  라우트 다섯에서 복사된 문장입니다. **2026-10-27 정정**: 그 자리에 제가 적은 "`audit_recorded`만
  달라집니다"도 거짓이었습니다 — 기본 설정에서 **2개**(`audit_recorded`·`audit_event_id`),
  `SDP_OIDC_GROUP_ROLE_MAP`을 설정한 운영 설정에서는 **5개**(`actor_context`·`audit_event_id`·
  `audit_recorded`·`group_role_bindings`·`role_map_source`)가 달라집니다. 즉 actor가
  운영자 매핑을 받을지 빈 매핑을 받을지를 결정합니다. 더 나쁜 문장을 좁히는 데 그쳐 **덜
  나쁜 거짓**을 남긴 것이고, 공표 문구와 `tests/test_oidc_preview_actor_description.py`로
  고쳤습니다.
* `test_mutation_refusal_names_its_cause.py`: "scope 없는 주체는 dataset을 보지 않는 role
  체크에서 거부된다" — 이 파일을 쓰는 동안 거짓으로 측정된 전제입니다. 엔진에 없는 성질을
  엔진에 돌리면 다음 사람이 dataset 범위 호출을 되살려도 된다고 결론 냅니다.

### 닫지 않은 것

`obligations`가 `additionalProperties: {}`이므로 **키별 타입은 공표되지 않습니다**
(`masking`은 배열, `tenant_id`는 문자열). 키 집합이 결정 분기마다 달라지는 노드에 대해
map이 올바른 분류이지만, 아홉 키의 고정 어휘에 타입을 주는 표현(예: 키별 스키마를 가진
map)은 이 생성기에 없습니다 — 별도 항목입니다.

이 절은 측정 기록이고 병합 허가가 아닙니다.

## 공표된 설명 둘이 **제품에 없는 규칙**을 적고 있었습니다 (2026-10-27 04:15Z)

**`action`**: "평가할 동작(`search`·`read`·`create`·`publish` 등)". `read`는 평가되지
않습니다 — nonsense 문자열과 **동일하게** `평가할 수 없는 action입니다.`로 거부됩니다.
독자가 가장 먼저 시도할 예시가 작동하지 않는 것이었고, 거부 사유는 문서가 틀렸다는 말을
하지 않습니다. 설명과 `enum`을 엔진의 `KNOWN_ACTIONS`·`CATALOG_ACTION_ALIASES`에서
파생합니다.

**`limit`**: "정책이 더 낮은 상한을 요구하면 그쪽이 적용됩니다"만 적고 고정 상한 100을
적지 않았습니다. 그리고 측정하다 **라우트의 조용한 clamp**를 찾았습니다 —
`limit=min(limit, 100)`, `offset=max(offset, 0)`. `browse.preview`의 ValueError 가드는
HTTP에서 도달 불가능했습니다:

    limit=101  -> 200    limit=500 -> 200    offset=-5 -> 200

호출자가 보낸 값과 다른 페이지를 받으면서 그 사실을 모릅니다. change-reason truncation과
같은 형태이고 같은 방식으로 거부합니다. 상한·하한을 `MAX_PREVIEW_ROWS`/`MIN_PREVIEW_ROWS`
상수로 올려 계약이 참조하고, `offset`의 하한도 같은 커밋에서 공표했습니다 — 수리가 만든
새 400을 미공표로 두면 그게 이 절의 결함입니다.

### 파생이 자동으로 정직을 주지는 않습니다

설명을 `KNOWN_ACTIONS`에서 파생하면 둘은 **구성상** 일치합니다. `KNOWN_ACTIONS` 자신이
엔진과 어긋나면 그 일치는 아무것도 보장하지 않습니다. 그래서 제안된 action 전부를 라이브
라우트로 보내 어느 것도 "평가할 수 없는"으로 돌아오지 않음을 단언합니다 —
`KNOWN_ACTIONS`에 `read`를 더하는 변이가 그 단언만 red로 만듭니다.

### 가드 작성 중의 두 실수

* backtick 추출기가 `deny`를 제안된 action으로 집었습니다(설명이 거부 효과를 backtick으로
  적으므로). 값이 아닌 토큰을 명시 목록으로 뺐습니다 — 패턴으로 거르면 세 번째가 조용히
  들어옵니다.
* `from .policy import CATALOG_ACTION_ALIASES`가 mutable dict에 두 번째 이름을 붙여
  module-state 가드가 red가 됐습니다. 가드가 옳습니다. 모듈 자격 참조로 바꿨습니다.

### 닫지 않은 것

`minimum`/`maximum`/`enum`을 이번에 넣은 세 속성 밖에서, 공표된 제약이 실제로 강제되는지는
여전히 전수 측정하지 않았습니다. `maxLength` 다섯과 이 셋이 측정된 전부입니다.

이 절은 측정 기록이고 병합 허가가 아닙니다.

## 공표된 `maxLength: 512`가 **어디에서도 규칙이 아니었습니다** (2026-10-27 04:00Z)

`api_request_contract`가 본문 속성 다섯(카탈로그 mutation 넷의 `reason`, patch review의
`comment`)에 `maxLength: 512`를 공표합니다. 측정:

    publish reason 1000자  -> 200, audit의 change_reason 길이 512  (조용한 truncation)
    review comment 1000자  -> 200, review_comment 길이 1000        (한도 없음)

하나의 공표 아래 서로 다른 두 가지 잘못된 동작입니다. truncation 쪽이 더 나쁩니다 — 사람
auditor가 읽는 행이 호출자가 쓰지 않은 지점에서 끊긴 글을 담고, 200은 그걸 말하지 않습니다.

### 거부로 고쳤습니다

공표된 한도를 참으로 만드는 유일한 선택입니다. 한도를 넓히는 쪽은 이미 공표된 숫자를
조용히 바꾸는 것이라 하지 않았습니다.

### 기존 가드 넷이 반응했습니다 (전부 옳게)

* `test_change_reason_evidence.py`가 truncation을 단언하고 있었습니다 — 행동을 기록하고
  판단하지 않은 테스트. 이 라운드 두 번째 같은 형태입니다.
* 본문 키 스캔이 `payload.get(field)`를 해석 불가로 보고 — 동적 키는 문서와 대조할 수
  없으므로 옳습니다. 헬퍼가 값을 받도록 바꿔 리터럴을 호출 지점에 남겼습니다.
* error 계약 가드가 `deprecate`의 새 400이 미공표라고 보고 — 테이블에 넣었습니다.

### 제 structural 가드가 자기 설명문에 걸렸습니다

`"[:MAX_CHANGE_REASON_CHARS]"` 문자열 검사가 **지운 코드를 인용한 docstring**에 걸렸습니다.
산문과 코드를 구별하지 못하는 가드는 다음 사람에게 설명을 쓰지 말라고 압박합니다. 구문
트리로 바꿨습니다.

### 닫지 않은 것

`maxLength`가 아닌 다른 공표 제약(`minLength`, `pattern`, 숫자 범위)이 실제로 강제되는지는
전수 측정하지 않았습니다. 이 라운드에서 센 것은 `maxLength` 다섯 개뿐입니다.

이 절은 측정 기록이고 병합 허가가 아닙니다.

## 드래프트가 **고쳐 쓴** 테이블 이름을 "카탈로그가 선언한 relation"이라고 공표했습니다 (2026-10-27 03:45Z)

`source_relation_name`이 선언 이름을 `_safe_identifier`로 통과시켰고, 드래프트는 그 고쳐 쓴
이름을 `assumptions`·`execution_caveat`에서 "카탈로그에 선언된 relation"이라고 공표했습니다.

    선언 analytics.sales_order  ->  FROM analytics_sales_order
    선언 "sales order"          ->  FROM sales_20order   (%20이 남은 뒤 % -> _)

둘 다 `executable_against_source: true`, `emitted_identifiers: {}`. 같은 응답의 **컬럼
경로는 같은 rewrite를 공개합니다.** 한 응답 안에 같은 rewrite에 대한 반대의 정직성이
있었습니다. 그리고 고쳐 쓴 relation 이름은 이 함수가 고치려고 존재하는 결함입니다.

### 고친 방식: 고쳐 쓰지 않고 거절

URL 디코드 후, 점으로 구분된 평범한 식별자 1~3개일 때만 **적힌 대로** 반환합니다. 아니면
`None` — locator 이름과 "파생, 선언 아님" caveat. 수식된 이름을 emit할 수 있는 이유는
allow-list가 raw 비교로 바뀌었기 때문입니다(같은 라운드의 선행 항목).

### 테스트가 rewrite를 "측정한 대로" 적어 두고 있었습니다

`("table$x", "table_x")`에 "Asserted as measured"라고 달려 있었습니다. 측정해서 적어 둔 것과
받아들인 것은 다릅니다. 측정 기록이 결함 승인으로 굳는 경로가 이것입니다.

### 수리가 거짓 주장을 다른 거짓 주장으로 바꾸지 않도록

`None`의 원인이 둘인데 caveat은 "distribution을 선언하지 않았으므로" 하나만 말했습니다.
`sales order`를 선언한 데이터셋에는 거짓이고, 운영자를 없는 distribution을 찾으러
보냅니다. 두 원인을 분리했습니다.

### 변이 둘이 green으로 돌아왔습니다 (그리고 왜)

* URL 디코드 제거 → green. `sales%20order`는 디코드와 무관하게 거절되므로 그 케이스는
  디코드를 **증명하지 않습니다.** 가르는 케이스는 `%5F`(디코드하면 `sales_order`).
* caveat 분기를 `False`로 → green. 이름이 caveat 테스트인데 헬퍼만 보고 문장을 보지
  않았습니다. 응답에서 문장을 읽도록 고쳤습니다.

둘 다 "선언을 보고 효과를 보지 않는 가드"의 같은 형태입니다. 이 라운드에서 같은 형태가
여섯 번 나왔습니다.

### 닫지 않은 것

컬럼 쪽 rewrite는 그대로입니다 — 선언 컬럼 `order amount`가 `order_amount`로 emit되고,
`emitted_identifiers`에 공개되긴 하지만 거절되지는 않습니다. 테이블 쪽과 같은 규칙(고쳐
쓰지 않고 거절)을 적용할지는 별도 항목입니다. 그리고 수식된 relation을 emit하게 된 것은
allow-list의 raw 비교에 의존하므로, 그 둘은 이제 한 쌍으로 유지해야 합니다.

이 절은 측정 기록이고 병합 허가가 아닙니다.

## 생성기가 **두 번째 관찰만 가진 필드의 타입을 버려** 34개 노드를 "any"로 공표했습니다 (2026-10-27 03:30Z)

`scripts/generate_response_contract.py`의 `union`이 docstring에서 `None`("아직 관찰 없음")과
`{}`("관찰했고 아무 타입이나")를 구분한 뒤, 한 단락 뒤에서 위반합니다:

    properties[key] = union(properties.get(key, {}), item)

`.get(key, {})`는 왼쪽이 갖지 않은 키에 "관찰했고 아무 타입이나"를 말하고,
`union({}, typed)`는 `{}`로 붕괴합니다. 결과: **두 번째 probe가 들여온 모든 필드가 측정된
타입을 잃습니다.** 같은 기본값이 재귀에 쓰여 중첩도 같이 잃습니다.

    union({"a": string}, {"a": string, "b": integer}) -> {"a": string, "b": {}}

### 되찾은 것

기본값을 `NOTHING_OBSERVED`로 바꾸고 재생성: 빈 스키마가 103 → 69, 즉 **34개 노드**가
측정된 타입을 되찾았습니다. 문서로 클라이언트를 만드는 구매자 쪽에서는 그 34개 필드가
"아무 타입이나"였다가 `number`·`array of string`·`boolean`·`string`이 됩니다.

### 과잉 교정 쪽도 고정했습니다

`{}`의 의미가 이 생성기의 존재 이유입니다. `steward`가 한 데이터셋에서 `None`, 다른
데이터셋에서 문자열인데 `string`으로 공표해 라이브 응답이 계약 테스트를 깨뜨린 것이 첫 판의
결함이었습니다. 가드 넷이 반대 방향을 지킵니다: null 관찰은 여전히 `{}`, 충돌 타입도 `{}`,
왼쪽에만 있는 필드는 타입 유지, sentinel은 `{}`가 아님. 변이로 양방향 확인했습니다.

### 가드 작성 중의 실수 하나

여섯 가드 전부가 처음에 red였습니다 — 기대한 둘이 아니라. 원인은 제품이 아니라 제 import
이름(`generator`)이 그 파일에 없던 것이었습니다. **여섯이 전부 red인 것은 "결함이 여섯
군데"가 아니라 "가드가 로드되지 않았다"는 신호였습니다.** 모듈을 import한 뒤 red는 정확히
둘이 됐습니다.

이 절은 측정 기록이고 병합 허가가 아닙니다.

## `or True`로 끝나는 단언이, 자기가 감싸고 있던 **거짓 주석**을 살려 뒀습니다 (2026-10-27 03:20Z)

    assert "innerHTML = " not in script.replace("panelHtml", "") or True

구성상 실패할 수 없는 단언입니다. 우회하던 사실은 참이었습니다 — `src/sdp/console.py`의
controls·KPI·connector 패널이 각각 `innerHTML`을 씁니다. 그리고 그 세 줄 **위**의 주석이
"the console stays free of innerHTML"이라고 적고 있었습니다. 헤지가 거짓 주석의 수명을
연장한 것입니다.

보안상으로는 세 보간 모두 `esc()`를 지나고 `esc`는 `& < > " '` 다섯 글자를 치환하므로
실제 취약점은 아닙니다. 결함은 **주장과 가드**입니다.

### 성립하는 성질로 바꿨습니다

HTML을 담은 템플릿 리터럴의 모든 `${...}`는 `esc(...)` 호출이거나 양쪽 분기가 문자열
리터럴인 삼항이어야 합니다. 스크립트 텍스트에서 백틱 리터럴을 파싱하고 중괄호 균형을
맞춰 보간을 꺼냅니다. `esc` 자신이 치환하는 다섯 글자도 따로 단언합니다 — 방어의 전부가
그 함수이므로.

삼항 술어의 첫 판("`?` 뒤에 `.`이 없으면 통과")은 `flag ? someIdentifier : 'warn'`을
통과시킵니다. 양쪽 분기가 인용된 문자열이어야 하도록 조였고, 변이 둘로 확인했습니다
(property access 분기, 맨 식별자 분기).

### 적용되지 않은 변이의 green은 증거가 아닙니다

변이 하나를 셸 `python3 -c`로 넣었고 앵커에 `${`가 있어 셸이 먹었습니다. 스크립트가
AssertionError로 죽었는데 **그 뒤의 테스트 실행은 green을 보고했습니다** — 변이가 적용되지
않았으므로 당연합니다. Python heredoc으로 다시 돌려 red를 확인했습니다. 변이 결과를 읽을
때 변이가 **적용됐는지** 먼저 확인해야 합니다.

이 절은 측정 기록이고 병합 허가가 아닙니다.

## prober가 **자기 ledger로** 404가 거부한 질문에 답할 수 있었습니다 (2026-10-27 03:05Z)

다섯 라우트(`GET /graph/nodes/{id}`, `POST /graph/query`, publish, deprecate, PATCH)가
foreign과 absent를 동일한 404로 합치면서, prober 자신이 읽는 정책 결정 ledger에는 차이를
남겼습니다. `external-analyst`로 측정, HTTP 본문은 이미 동일:

    foreign id -> prober가 보는 행 0
    absent  id -> prober가 보는 행 1

그 행이 답을 평문으로 적습니다: mutation 셋은
`reason="존재하지 않는 데이터셋입니다." tenant_id="external"`, graph 둘은
`effect=allow reason="카탈로그 발견 정책 통과"` — 404 뒤의 allow 행입니다.

### 원인은 거부 기록이 아니라 그 **앞의** 평가입니다

* graph: `_authorize_graph_read(actor, node_id)`. 그 helper의 docstring이 스스로
  "establishes authentication only"라고 적습니다 — 그 id에 관한 판단이 아닌 것을 id별 행으로
  남깁니다. 다른 두 호출자는 이미 `"graph"`를 넘깁니다.
* mutation: `evaluate(..., resource=dataset_id)`가 먼저 돌고 `_catalog_mutation_refusal`은
  행이 이미 기록된 뒤에 답을 고릅니다.

`browse.py`의 순서가 맞습니다: reachability → 범위 밖 기록 → 평가. 다섯 라우트를 그렇게
바꿨습니다(`_unreachable_dataset_refusal`, `_refuse_mutation_on_unreachable_dataset`).

### graph의 두 번째 결함

`can_see_graph_node`는 소유 테넌트가 없는 id에 **True**입니다(거부할 것이 없음). 그래서
absent 노드는 거부 분기를 건너뛰고 id별 allow 행을 받은 뒤 라우트의 `get_node` 404를
만났습니다. 존재 확인을 같은 분기로 끌어와 둘을 한 경로에 둡니다. 성공 읽기는 여전히 행
하나(resource=node_id)이고, 익명 호출자는 두 id에 동일한 403을 받습니다.

### 큐레이션 목록이 자기가 세지 않은 것에 green을 보고합니다

가드의 첫 판은 표면 여덟 개를 손으로 적었고, 같은 파일의 커버리지 체크가 측정되지 않은
dataset-scoped 라우트 **열한 개**를 보고했습니다. 열한 개 전부 깨끗했지만 그 결과는
큐레이션 목록이 스스로 낼 수 없는 결과입니다 — 방문하지 않고 같은 green을 냈을 것이므로.
표면 목록을 `app.routes`에서 파생하도록 바꿨습니다. 본문으로 id를 받는 `POST /graph/query`는
경로 스캔이 못 찾으므로 명시 등록하고, 그 등록이 유지되는지 따로 단언합니다.

### prober의 채널을 닫는 것이 증거 삭제여서는 안 됩니다

거부 기록을 통째로 지우는 변이가 위 단언 전부를 green으로 통과했습니다 — 소유자 쪽을 보는
단언이 없었기 때문입니다. 전체 스위트는 `tests/test_refused_mutation_evidence.py`로 잡지만,
자기가 다루는 것을 제거하면 만족되는 계열은 자족적이지 않으므로 소유 테넌트 auditor 쪽
절반을 같은 파일에 넣었습니다. 그 단언의 첫 판은 audit 필드를 `decision`으로 물어
**AssertionError가 아니라 AttributeError로 터졌습니다**(실제 이름은 `result`) — 터지는
가드는 재는 가드가 아닙니다.

### 닫지 않은 것

측정은 `external-analyst`(테넌트 하나) 기준입니다. 여러 테넌트를 가진 호출자, 그리고
`/audit/events`·`/enterprise/*` 같은 다른 증거 표면의 전수 측정은 하지 않았습니다 —
dataset-scoped 라우트 19개는 파생으로 전수 측정되지만, 증거 **읽기** 표면 쪽은 아직
`/policy/decisions`와 `/catalog/datasets/{id}/audit` 둘만 쟀습니다.

이 절은 측정 기록이고 병합 허가가 아닙니다.

## 테이블 allow-list가 **정규화로 일치를 만들어** 다른 relation을 통과시켰습니다 (2026-10-27 02:50Z)

`validate_sql_query`의 source-table allow-list가 각 테이블 참조를 `_safe_identifier`로
정규화한 뒤 선언 relation과 비교했습니다. 그 함수는 영숫자가 아닌 모든 바이트를 `_`로
바꾸고, 이 카탈로그의 relation은 전부 `_`를 담습니다 — 정규화가 일치를 **만들어 냈습니다**.

선언 `crm_customer_master`에 대해 서로 다른 relation **아홉 개**가 경고 0건:
`crm.customer_master`, `crm$customer_master`, `crm_customer.master`,
`crm_customer$master`, `crm.customer.master`, `crm.customer$master`, 그리고 토큰 안에 남는
비ASCII `.` confusable 셋(U+00B7, U+2024, U+FF0E). `POST /browse/query`는 시드 데이터셋
`crm-customer-master`에 대해 `select customer_id from crm.customer_master limit 10`에
**200**을 답했습니다.

### 주석이 같은 메커니즘에서 반대 결론을 적고 있었습니다

"`_safe_identifier`가 dot을 `_`로 바꾸므로 qualified name이 bare name과 충돌할 수 없다" —
정규화가 expected에 **없는** 문자를 더하는 경우(`pg_catalog.customer`)에만 맞는 추론입니다.
선언 이름이 그 문자를 이미 담고 있으면 매핑은 충돌 생성기입니다.

### raw 비교

참조는 호출자의 신뢰할 수 없는 텍스트, 선언 relation은 `source_relation_name`이 이미
sanitise하고 한 테이블로 읽히는지 확인한 값입니다. 신뢰할 수 없는 쪽을 신뢰하는 쪽에 맞춰
rewrite하는 것이 거꾸로입니다. raw 비교는 엄격하게 더 좁고(거부만 늘고 수락은 늘지 않음),
드래프터는 선언 이름을 그대로 emit하므로 자기 출력은 통과합니다. 전체 스위트에 느슨한
동작에 의존한 테스트는 **없었습니다**: 1523 → 1549, 실패 0.

### 성질을 더했는데 vacuous였습니다

공유 oracle에 "참조가 인증 이름과 문자 단위로 같지 않으면 반드시 거부"를 더했습니다. 그런데
Hypothesis가 `query`와 `declared_relation`을 독립적으로 뽑으므로 충돌 쌍에 도달하지 않고,
수리를 되돌려도 green이었습니다. 우연을 **만드는** 전략(underscore 이름 → `_` 하나를 충돌
문자로 치환)을 더하자 최소 반례 `a.a` vs `a_a`로 falsify합니다. 성질을 적는 것과 성질이
발화하는 입력에 도달하는 것은 다릅니다.

충돌 문자 집합은 측정했습니다. 첫 목록의 `crm customer_master`, `crm-customer_master`,
`crm/customer_master`는 제 충돌 가드가 거절했습니다 — `_TABLE_LIST_TOKEN`이
`[A-Za-z_\u0080-\uffff][\w.$\u0080-\uffff]*`이므로 공백·하이픈·슬래시는 토큰을 끝내고 테이블
`crm`으로 파싱되어 이미 다른 이유로 거부됩니다.

### 하네스 본문을 로컬에서 구동합니다

near-miss 구성은 oracle 모듈이 소유합니다(`COLLIDING_SEPARATORS`, `near_miss_reference`).
Atheris 하네스에 같은 모드를 넣었고, wheel이 없으므로 본문을 가짜 provider로 직접
구동하는 테스트를 더했습니다. 첫 판 가짜 provider는 `a-z`만 내서 인증 이름에 `_`가 없었고
분기에 들어가도 64번 전부 `None`이었습니다 — 진짜 provider는 임의 유니코드를 내고
`_safe_identifier`가 거기서 `_`를 만들므로 이미지에서는 계속 발화합니다.

### 닫지 않은 것

Atheris **coverage-guided 실행**은 여전히 로컬 증거가 아닙니다 — 확인한 것은 본문이 가짜
provider 64입력에서 실행되고 oracle이 성립한다는 것까지입니다. 그리고 컬럼 쪽에는 여전히
allow-list가 없습니다: `requirements.py`가 적어 둔 대로 선언 컬럼의 rewrite를 다시 검사하는
경로가 없습니다(별도 항목).

이 절은 측정 기록이고 병합 허가가 아닙니다.

## ClusterFuzzLite 하네스가 **한 입력도 퍼징하지 못하고** import에서 죽었습니다 (2026-10-27 02:20Z)

`a2f50c2`가 두 엔진의 oracle을 하나로 모으면서 `fuzz/fuzz_query_safety.py`에
`from tests.fuzz.invariants import check_validate_sql_query`를 넣었습니다. 이미지에서
`ModuleNotFoundError: No module named 'tests'`가 첫 입력 전에 뜹니다. 원인이 **둘**입니다:

* `WORKDIR /src` + `PYTHONPATH=/src/src` + `CMD python fuzz/fuzz_query_safety.py`에서
  `sys.path[0]`은 **스크립트의 디렉터리**(`/src/fuzz`)이고 `/src`는 경로에 없습니다.
* 이미지가 `tests`를 **담지 않았습니다**(`COPY src`, `COPY fuzz`, requirements 둘). 복사되지
  않은 파일은 `sys.path`로 닿을 수 없습니다.

### 왜 아무도 몰랐나

`fuzz.yml`의 Atheris 잡은 `tests/fuzz/run_atheris.sh`를 돌리고, 그 스크립트는
`tests/fuzz/atheris/fuzz_*.py` 네 개(`draft_sql`, `execute_query`, `resolve_terms`,
`search_catalog`)만 돌립니다. `fuzz_query_safety`는 그 목록에 **없습니다** — 이 하네스는
ClusterFuzzLite 이미지에서만 실행됩니다. Hypothesis 미러는 oracle을 직접 import하므로
영향이 없습니다. 즉 `validate_sql_query`의 coverage-guided 커버리지는 그 이미지에만
있었고, 그 이미지에서 죽어 있었습니다. CHANGELOG의 "미러가 `tests/fuzz`에서 돕니다"라는
문장이 이 공백을 덮고 있었으므로 같은 커밋에서 고쳤습니다.

### 이동이 아니라 복사로 고쳤습니다

먼저 oracle을 `fuzz/invariants.py`로 옮겨 봤고 수집 단계가 거절했습니다: `tests/`에
`__init__.py`가 없어 `tests/fuzz`가 pytest에서 **top-level `fuzz`로** import되므로 새
모듈을 가립니다(`ImportError: cannot import name 'invariants' from 'fuzz'
(.../tests/fuzz/__init__.py)`). 그래서 oracle은 `tests/fuzz/invariants.py`에 남고,
Dockerfile이 `COPY tests/fuzz ./tests/fuzz`로 그 디렉터리만 담습니다. 하네스에는 repo
root bootstrap이 있습니다. `chown -R`은 추가된 `COPY` 뒤이고, digest 고정과 uid 10001은
그대로입니다.

### 가드: 경로 순서가 아니라 파일 집합

첫 판 가드(`tests/test_fuzz_harness_imports.py`)는 `sys.path` **순서**만 재현해서 체크아웃
에서 green이었습니다 — 시뮬레이션 대상 이미지에는 `tests/`가 없는 동안. 지금은 Dockerfile
에서 COPY 집합·`WORKDIR`·`PYTHONPATH`·`CMD`를 읽어 샌드박스를 만들고 그 안에서 하네스
본문을 실행합니다. oracle의 모듈 경로는 하네스의 import 문에서 파싱하므로 하네스를 따라
움직입니다.

샌드박스는 **복사**입니다. symlink 판에서 변이 둘이 green으로 돌아왔습니다 — 하네스의
bootstrap이 `Path(__file__).resolve()`이고 `resolve()`가 symlink를 따라가서, 샌드박스의
`fuzz` 링크가 실제 체크아웃으로 풀려 진짜 repo root가 `sys.path`에 올랐습니다. 밖으로
나갈 수 있는 샌드박스는 이미지가 아닙니다.

변이 4건 전부 행동 프로브까지 red입니다: bootstrap 제거 / `COPY tests/fuzz` 제거 /
`COPY tests/fuzz/corpus`로 좁히기 / `PYTHONPATH=/src/src` → `/src`.

### 닫지 않은 것

`fuzz_query_safety`는 여전히 `run_atheris.sh`의 목록에 없습니다. 이미지가 유일한 실행
경로인 상태 자체는 그대로이고, 이제 그 경로가 살아 있다는 것만 가드됩니다. 로컬에 Atheris
wheel이 없어 이 저장소에서 **실제 퍼징 실행**을 확인한 것은 아닙니다 — 확인한 것은 하네스가
이미지의 파일 집합 안에서 import를 통과하고 oracle을 바인딩한다는 것까지입니다.

이 절은 측정 기록이고 병합 허가가 아닙니다.

## 운영 메모

- Database objects: 두 단어 이상 `snake_case`, 3NF. Catalog plane 테이블은 #73의 `migrations/0002_ontology_catalog_plane.sql`.
- 기본 CI store는 in-memory. DSN-backed store는 paid-pilot 경로이며 catalog 쓰기 영속화 자체는 #73의 범위입니다.
- `NVIDIA_NIM_API_KEY`는 contextual-orchestrator가 쓰는 **외부 connector 변수**입니다. 이 저장소의 워크플로·테스트·모듈은 현재 이 값을 참조하지 않으며, 이 문서가 유일한 언급 지점입니다. 이 저장소에서 이름을 바꾸지 마십시오. 포털 쪽 매핑은 orchestrator 계약의 `SDP_` prefix 변수를 따르고, 계약을 확인하기 전에는 새로 만들지 마십시오. `COPILOT_GITHUB_TOKEN`은 쓰지 않습니다. review-bot 키를 재조정하지 마십시오.
- Analyze (actions) 503 SARIF upload는 flake입니다. 재실행만을 위한 추가 커밋을 넣지 마십시오.
