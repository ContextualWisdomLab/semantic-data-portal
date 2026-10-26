# CHANGELOG

이 문서는 `claude/semantic-portal-pr-merge-e5a48k` 브랜치(PR
[#102](https://github.com/ContextualWisdomLab/semantic-data-portal/pull/102))가
베이스 대비 더하는 변경을 사람이 읽을 수 있게 묶은 것입니다. **235개** 커밋 중 125개는
gap-baseline 문서 작업이고, 아래는 제품 동작이 바뀐 나머지 110개입니다. 이 숫자는 **이
줄을 담은 커밋을 포함한** 값입니다 — 측정 시점의 234에 이 커밋을 더한 것. 측정 명령:

    git rev-list --count origin/docs/product-technical-gap-baseline..HEAD
    git log --format=%H origin/docs/product-technical-gap-baseline..HEAD \
      --name-only -- docs/product-technical-gap-baseline.md | grep -c '^[0-9a-f]\{40\}$'

앞서 적혀 있던 164/112, 186/113, 199/122/77, 203/122/81, 211/122/89, 212/122/90, 213/122/91, 214/122/92, 215/122/93, 216/122/94, 218/122/96, 219/122/97, 220/122/98, 221/122/99, 222/122/100, 223/122/101, 224/122/102, 225/122/103, 226/122/104, 228/122/106, 230/123/107, 231/123/108, 233/124/109은 각각 그 시점의 값이고 이후
커밋을 반영하지 않은 숫자였습니다 — 자기 문서의 수치도 측정해서 맞춰 둡니다. 199는 이
줄을 쓴 뒤 3개 커밋이 더 쌓여 낡아 203으로, 203은 다음 커밋에서 낡아 204로, 204는 또
두 커밋 뒤에 206으로 다시 측정해 고쳤습니다. 206도 그 값을 담은 커밋 자신 때문에 도착
즉시 낡았습니다 — 측정하고 쓴 뒤 커밋하는 순서상 피할 수 없는 off-by-one이라, 이제는
**이 커밋을 포함한** 값을 적습니다. 그래도 다음 커밋이 쌓이면 또 낡고, 그때는 같은
결함입니다.

형식은 [Keep a Changelog](https://keepachangelog.com/)를 따릅니다.

## [Unreleased]

**릴리즈된 것이 아닙니다.** 이 브랜치는 병합되지 않았고, PR #102는 현재 독립
승인 0건이며 필수 체크는 계정 Actions 과금 잠금으로 디스패치 전에 거부되고
있습니다(저장소 자체 워크플로의 마지막 성공: 2026-10-02T09:03:05Z. 그 이후의
성공은 GitHub 자체 할당량으로 도는 Dependabot 뿐이며, 이는 계정 잠금 해제의
증거가 아닙니다). 태그와 릴리즈는 사람의 승인 없이 만들지 않습니다.

아래 모든 항목의 유일한 실행 증거는 로컬 CI 동형 실행입니다:

    pytest                       1359 passed, 16 skipped
    pytest (파일 순서 정/역/난수)  각 1347 passed, 15 skipped — 순서 무관
                                 (정순 · 역순 · seed 11/707/31337; 트리거 가드 커밋 이전 head)
    pytest tests/fuzz            11 passed
    python -m sdp.demo_smoke     exit 0, "ready": true

alert 전달 커밋이 테스트를 34건(새 파일 넷 33건 + `test_honest_metrics.py` 1건),
pgvector 핀 커밋이 10건, event-loop 수리 커밋이 2건, 환경 변수 문서·gate 커밋이 8건
(새 파일 둘), readiness 진단 커밋이 7건(새 파일 하나) 늘렸고, 그 뒤 2026-10-26 적대적 리뷰
수리 여섯 커밋이 3+3+3+4+4+3건을 더했으므로 위 숫자는 앞서 적혀 있던
1266 → 1300 → 1310 → 1312 → 1320 → 1327 → 1330 → 1333 → 1336 → 1340 → 1344 → 1347로
올라갔습니다. 다섯 순서 측정은 트리를 동결한 상태에서
돌렸고, 그 뒤에 바뀐 파일은 이 CHANGELOG 하나입니다 — CHANGELOG 내용을 읽는 테스트는
파일 순서와 무관한 산술 가드
(`test_every_published_node_breakdown_sums_to_its_own_total`) 하나뿐이므로, 순서 성질을
다시 재지 않고 전체 정순 실행으로만 확인합니다. 측정하고 쓴 뒤 커밋하는 순서상 이
숫자가 자기 커밋 때문에 낡는 것은 위 off-by-one과 같은 종류입니다.

위 다섯 순서 숫자는 2026-10-26 적대적 리뷰 수리 여섯 커밋이 모두 들어온 뒤의 측정입니다.
각 중간 커밋은 **전체 정순 1회**만을 증거로 가졌고, 다섯 순서는 묶음이 끝난 뒤 한 번
재서 이 블록을 갱신했습니다 — 중간 head에 대해 다섯 순서를 주장하지 않습니다. 이 커밋이
바꾼 파일은 CHANGELOG와 gap 문서 둘뿐이고, CHANGELOG 내용을 읽는 테스트는 파일 순서와
무관한 산술 가드 하나뿐이므로 순서 성질을 다시 재지 않고 전체 정순 실행으로만 확인합니다.

skip 15건의 내역을 적어 둡니다 — 숫자만 적으면 읽는 사람이 해석할 수 없습니다:
`SDP_DATABASE_DSN not set` 11건(Postgres 통합)과 `pyld is a dev-only dependency`
4건입니다. `pyld`는 `requirements-dev.txt`에도 `pyproject.toml`에도 없으므로 CI도 같이
skip합니다 — 앞서 적혀 있던 `11 skipped`는 `pyld`가 어쩌다 깔려 있던 환경의 값이었습니다.
파일 순서 측정 대상에 `tests/fuzz/test_*.py`를 포함시켰으므로 전체 실행과 수치가
같습니다(앞서는 `tests/test_*.py`만 세어 1221 - 1210 = 11건의 차이가 났고, 그 11건이
순서 측정에서 빠져 있었습니다). 트리를 **동결**한 상태에서만 측정합니다 — 이 세션에서
백그라운드 측정 중에 트리를 고친 탓에 seed 11이 4건 실패로 나온 일이 있고, 그것은 결함이
아니라 동시 편집이었습니다. Atheris(`fuzz/fuzz_query_safety.py`)는 로컬에 wheel이 없어
실행하지 않았습니다 — 같은 invariant의 Hypothesis 미러가 `tests/fuzz`에서 돕니다.

### Fixed — "정직한 숫자"라고 적은 문단의 숫자가 12일 동안 거짓이었습니다 (high)

`README.md`와 `docs/implementation-compliance.md`가 둘 다 기본 데모 배포에서 runtime 검증되는
control이 **0개**이고 runtime 확인을 가진 control은 `credential_vault` **하나**라고 적고
있었습니다. 둘 다 쓰인 시점에는 참이었고 둘 다 12일 동안 거짓이었습니다:

    c74ba8e  2026-10-14 12:27  README 문단 작성 (그때는 credential_vault 하나가 맞았습니다)
    1a62855  2026-10-14 17:25  ontology_version_pin 추가 — 5시간 뒤
    측정 2026-10-26            runtime 확인을 가진 control 2개
                               기본 데모 배포에서 runtime 검증되는 것 1개
                               REST secret을 설정하면 2개

**처음에 이 drift를 제 커밋(`e6d08ac`) 탓으로 적었고, 그것은 틀렸습니다.** `e6d08ac`는
`_RUNTIME_CONTROL_CHECKS`를 `control -> (검사, 소유자)` 형태로 재구성했을 뿐이고, 두 번째
runtime 확인을 넣은 것은 12일 전 `1a62855`입니다. 더 깔끔한 이야기가 되는 쪽으로 책임을
가져오지 않고 측정한 대로 적습니다. 제 것인 부분은 따로 있습니다 — `e6d08ac`에서 **바로 그
코드를 읽으면서** 문서를 확인하지 않았습니다.

누구도 잘못 추론하지 않았습니다. 같은 숫자를 **두 문서가 손으로** 들고 있었고 그 숫자를
만드는 코드가 움직였습니다. 그래서 수리는 문장을 고치는 것으로 끝내지 않았습니다:

* 숫자를 README의 **기계가 읽는 블록 한 곳**으로 옮겼습니다
  (`controls_with_a_runtime_check` / `runtime_verified_in_the_default_demo`).
  `fast-mlsirm`이 runtime contract에 쓰는 형태와 같습니다.
* `docs/implementation-compliance.md`는 **개수를 아예 적지 않습니다** — control 이름만
  적고 숫자는 README를 가리킵니다. 두 사본이 12일을 만든 원인이므로 사본을 없앴습니다.
* README **산문에서도** 숫자를 뺐습니다. 블록을 만들고도 산문에 "2개/1개/2개"를 남겨 두면
  같은 습관이 그대로 남습니다.
* 가드는 제품에서 세 값을 계산해 블록과 **정확히** 대조하고, 두 번째 문서가 숫자를 다시
  들면 거부합니다.

**가드의 첫 판은 거의 공허했습니다.** 산문에서 숫자를 찾는 방식이었고, 낡은 README 문장을
되돌려도 개수 검사는 **초록**이었습니다 — 같은 문단이 자기 몫의 "1"과 "2"를 공급하기
때문입니다. 그때 걸린 것은 control **이름** 검사뿐이었습니다. 산문에서 숫자를 찾는 검사는
그 숫자를 이웃과 구별할 수 없습니다. 측정하고 나서 블록 비교로 바꿨습니다.

증거: 세 변형을 각각 되돌렸습니다. M1(블록이 제품과 다른 값을 적음): 개수 검사 1건 red
(첫 판에서는 green이었습니다 — 그것이 이 수리의 요점입니다). M2(소스에 세 번째 runtime
확인 추가, 문서 그대로): 개수·이름 2건 red. M3(두 번째 문서가 손으로 센 숫자를 다시 듦):
1건 red. 전체 정순 `pytest` 1359 passed, 16 skipped (1353에서 +6).

### Fixed — dry run이 데이터 행을 하나 지어내면서 "0건"이라고 보고했습니다 (high)

구매자 체감 갭 탐색(6개 표면)의 query-path 렌즈가 찾았습니다. `execute_query`의 `row_count`는
`_row_count_estimate(dataset, dry_run=req.dry_run)`로 계산되어 dry run에서 올바르게 `0`을
돌려주는데, 그 아래 `rows`/`columns` 구성이 **`req.dry_run`을 전혀 보지 않았습니다**:

    dry_run=True [plain  ]  row_count=0  len(rows)=1  rows=[{'result': 0}]
    dry_run=True [group by]  row_count=0  len(rows)=1
                             rows=[{'week': '2026-10-26', 'active_count': 1}]
    audit:  {"dry_run": true, "row_count": 0, "measurement_status": "mock_execution_no_real_data", ...}

한 응답이 **자기와 모순**합니다(0건이라면서 1건을 전달). group-by 경로에서는 그 1건이
**오늘 날짜의 0이 아닌 지어낸 측정치**(`active_count: 1`)입니다. 그리고 compliance 원장은
"전달된 행 없음"을 기록하는 동안 호출자는 행을 들고 있습니다 — 이 저장소의 표준 규칙이
"원장에 올라간 라벨 없는 추정치는 지어낸 측정치"이므로, 라벨이 붙은 mock 표시와 별개로
이것은 원장의 거짓 진술입니다.

`rows`를 dry run 분기에서 비웁니다. `columns`는 **계속 게시합니다** — 선언된 결과 모양은
dry run이 존재하는 이유이고, 비는 것은 데이터뿐입니다.

`tests/test_orchestrator.py::test_execute_query_dry_run_succeeds_with_zero_rows`는 이름이
"zero rows"인데 `row_count == 0`만 단언하고 `rows == []`는 **한 번도 단언하지 않았으므로**,
행을 실어 보내는 응답에 대해 통과했습니다. 이 주기에 자기 이름이 약속한 것을 검사하지 않는
테스트 **일곱 번째**입니다. 그 단언을 추가하고 group-by 경로 케이스를 더했습니다.

**내 테스트가 두 번 틀렸고, 둘 다 적어 둡니다.**

1. 첫 판은 `dry_run` 양쪽에서 `recorded == row_count == len(rows)`를 요구했습니다. live
   실행에서 이것은 거짓이고 **거짓이어야 합니다** — 거기서 `row_count`는 라벨 붙은
   추정치(2000, 카탈로그 프로필)이고 `rows`는 고정된 예시 한 줄입니다. 같기를 요구하면
   mock이 2000행을 지어내야 하고, 그것은 라벨 붙은 한 줄보다 **더 나쁩니다.** 코드가
   주장하지 않은 값 도메인을 단언한 것과 같은 종류의 과잉이고, 이 주기에 `minimum=1`로
   한 번 했던 실수입니다. 다만 그 과잉이 진짜 갭 하나를 드러냈습니다: 이 응답의 모든
   수치가 출처 라벨을 달고 있는데(`elapsed_ms_source`·`bytes_scanned_source`·
   `row_count_source`) **`rows`만 없었고**, 바로 위 주석이 "아래 모든 수치는 출처가
   라벨된다"고 적고 있었습니다. `rows_source`를 추가했습니다 —
   `withheld_dry_run` 또는 `fixed_mock_sample`.
2. 두 번째 판은 최신 audit event를 `events[-1]`로 읽었습니다.
   `catalog.list_audit_events`는 **최신이 먼저**이므로 그것은 가장 오래된 행이고, 루프
   두 번째 패스에서는 **이전 호출의 event**였습니다 — 제품이 2000행 응답에 대해
   `row_count: 0`을 기록하는 것처럼 보였습니다. 순서를 가정하지 않고 확인한 것이 결함과
   오독을 가른 지점이고, 그 문장을 테스트 docstring에 적어 두었습니다.

증거: 두 수리를 각각 되돌렸습니다. M1(dry run이 다시 행을 전달): 3건 red. M2(`rows_source`
라벨 제거): 1건 red. 전체 정순 `pytest` 1353 passed, 16 skipped (1351에서 +2).

### Fixed — 기본 테스트 게이트가 stacked PR에서 아예 돌지 않고 있었습니다 (high)

PR #102의 check run을 세어 보고 찾았습니다. **두 건뿐입니다**:

    GET /repos/.../pulls/102/check-runs  ->  total_count: 2
      Hypothesis property tests          (fuzz.yml)
      Atheris coverage-guided (bounded)  (fuzz.yml)

`Tests / API integration suite`가 **아예 없습니다.** 원인은 한 줄입니다 — `fuzz.yml`은
`pull_request:`를 필터 없이 선언하고, `tests.yml`은 `pull_request: branches: [main]`로
선언했습니다. 그 필터는 PR의 **base** 브랜치에 걸립니다. #102의 base는 `main`이 아니라
`#79` 브랜치이고(이 저장소의 merge order가 **의도적으로** PR을 쌓습니다), 따라서 기본
테스트 게이트는 stacked PR에서 단 한 번도 돌지 않았습니다.

24일 동안 아무도 눈치채지 못한 이유는 계정 Actions 과금 잠금이 모든 job을 디스패치 전에
거부해서 어느 쪽도 돌지 않았기 때문입니다. 결과가 드러나는 시점은 그 잠금이 풀리는
순간입니다: PR은 fuzz 레인의 결과를 보여 주고 `Tests` 결과는 **보여 주지 않으며**,
"체크 통과"를 읽는 리뷰어는 두 레인 중 하나만 읽게 됩니다.

이것은 형제 저장소가 이미 기록한 결함입니다 — `contextual-orchestrator`의
"Stacked quality checks: zero check runs can result from the former
`pull_request.branches: [main]` filter excluding the PR base. Keep the quality trigger
unfiltered." 같은 필터가 두 번째 저장소에 있었고, 워크플로 파일을 읽어서가 아니라 **check
목록을 세어서** 찾았습니다.

가드는 `tests.yml`을 이름으로 부르지 않고 **파생**합니다: 이 저장소가 소유한 워크플로를 전부
읽어 `pull_request` 트리거에 base 브랜치 필터(`branches`/`branches-ignore`)가 있으면
거부합니다. 나중에 같은 필터를 달고 추가되는 워크플로도 이 파일을 고치지 않고 걸립니다.
`scorecard-analysis.yml`은 `pull_request` 트리거가 아예 없으므로 예외가 아니라 **무관**이고,
그래서 skip 1건이 늘었습니다. `types`는 base가 아니라 이벤트 종류를 좁히므로 범위에
넣지 않습니다.

PyYAML이 이 저장소의 lock에 없고 가드 하나를 위해 의존성을 추가하는 것은 잘못된 교환이므로
트리거 블록을 텍스트로 읽습니다 — `tests/test_container_entrypoint.py`와
`tests/test_api.py`가 이미 `docker-compose.yml`과 `fuzz.yml`을 읽는 방식 그대로입니다.
**파서 자체를 합성 텍스트로 몰아 테스트합니다**(필터 있음/없음, `types`, push 전용,
`branches-ignore`) — 아무도 측정하지 않은 파서를 가진 가드는 자기 가정에 대해 검사된
가드이고, 이 주기에 그 형태로 다섯 번 실패했습니다.

증거: 두 수리를 각각 되돌렸습니다. M1(`branches: [main]` 필터 복원): `[tests.yml]`
parametrization 1건 red. M2(파서가 `types`를 base 필터로 보고하게 함): 파서 테스트 1건 red.
전체 정순 `pytest` 1351 passed, 16 skipped (1347 passed, 15 skipped에서 +4 통과, skip +1).

### Fixed — 대문자 하나로 빠져나간 낡은 주장, 그리고 전달 표면의 절반만 보던 disclosure 스캔 (high / 뒤 두 건은 low)

**이 주기 다섯 번째 "자기 목록에 걸린 가드"의 다음 형태: 대소문자.**
`observability.py:907`의 주석이 `"Nothing posts to it, so the capability is stated next to
the configuration fact."`라고 적고 있었고, 두 줄 아래가
`"alert_webhook_routing": ALERT_ROUTING_STATUS`(= `implemented`)입니다. 바로 그 문구를
금지하려고 추가한 가드의 fragment는 `("nothing posts ", "to it")`이고, 공백 정규화한
파일 전체에 **대소문자 구분** substring으로 물었으므로 대문자 `N` 하나로 통과했습니다.
아홉 개 금지 fragment를 README·CLAUDE·docs·src·tests 전체에 돌려 보면 대소문자만
어긋나는 누락은 정확히 이 한 건입니다. 비교를 casefold하고, 주석은 더 이상 사실이 아니므로
사실로 바꿨습니다(설정 여부와 전달 능력을 양방향으로 혼동할 수 없게 적습니다).

`docs/implementation-compliance.md`가 `alert_webhook_routing: declared_unimplemented`를
한 라운드 동안 그대로 들고 있었습니다 — 전달이 구현됐다고 적은 바로 위 항목에서 세 줄
뒤입니다. "2건 중"도 규칙이 둘이던 시절의 숫자입니다. 둘 다 고쳤습니다.

그 문구를 금지 목록에 **열 번째 fragment로 추가하지 않았습니다.** 대신 제품에서 값을 읽어
같은 키에 다른 값을 적은 문서를 거부하는 가드를 넣었습니다
(`alert_webhook_routing`·`alert_routing`·`alert_evaluation`을 `ALERT_ROUTING_STATUS`/
`ALERT_EVALUATION_SCOPE`와 비교). 상태 값의 이름이 바뀌면 이 가드는 고칠 필요가 없고,
뒤처진 문서는 걸립니다. 손으로 쓴 목록이 자기 자신에게 걸린 횟수가 이 주기에 다섯 번이므로,
같은 장치를 하나 더 만드는 대신 파생되는 쪽을 택했습니다.

**disclosure 스캔이 전달 표면의 절반만 봤습니다.** alert 본문을 디코드하는 테스트는 하나뿐이고
routable 규칙 **둘 중 하나**(`policy_audit_gap`)만 몰았습니다. 측정: `_alert_payload`가
`connector_probe_failure` 본문에만 `list_request_observations()` 행을 붙여도 전체 스위트가
1312 passed로 초록이었습니다 — 금지된 값 넷과 키 넷이 모두 익명 `GET`으로 도달 가능한
규칙의 본문에 실려 off-box로 나갑니다. 즉 alert를 유발한 caller가 **무엇이 새는지도**
고릅니다. 규칙별 driver를 `ROUTABLE_ALERT_RULE_IDS`로 parametrize하고, driver 없는
routable 규칙은 조용히 스캔되지 않는 대신 실패합니다.

**자격증명 반사 스캔은 실패 경로에서만 돌았습니다.** `_retained_stores()`는 모듈의 모든
module-level 컨테이너를 reflection으로 훑고, 이 파일 docstring이 "routing 변경이 추가한
ring은 여기 이름을 적지 않아도 스캔된다"를 보증으로 내세웁니다. 그런데 그것을 호출하는
유일한 테스트가 seam을 `failure_from_url`로 설치했으므로 **성공 분기에서 쓰인 상태는 한
번도 보지 않았습니다.** 측정: 성공 분기가 설정된 URL을 `_ALERT_ROUTING`에 남기면 전체
스위트가 1312 passed로 초록이고, 다섯 자격증명 형태 중 셋이 익명으로 답하는 모듈의
module-level dict에 앉아 있습니다. `test_honest_metrics`의 one-way-read 가드도 못 잡습니다 —
그 대입의 우변은 지역 변수이고, 가드는 변수 **이름**을 grep합니다. 두 결과 모두에 대해
parametrize하고, 각 분기가 실제로 그 분기였는지 `deliveries_failed`/`deliveries_succeeded`로
단언합니다(그 단언이 없으면 한쪽이 조용히 다른 쪽을 돌 수 있습니다).

**정정 — 뒤 두 건의 심각도.** 위 두 disclosure 항목을 처음 적을 때 리뷰의 high 등급을
그대로 옮겨 적었는데, 그 두 건은 반박 판정을 받았고 반박이 맞습니다. 사실 하위 주장은
양쪽 모두 확인됩니다(변형이 통과하고, 스캔이 절반만 봅니다). 다만 **지금 새고 있는 것은
없습니다**: `_alert_payload`에는 규칙별 코드가 없으므로 배포된 probe 규칙 본문에
caller 통제 내용이 없고, 성공 분기에 URL을 남기는 변형의 `_ALERT_ROUTING`은 게시 표면이
아닙니다(`alert_routing_state()`가 고정 키만 열거합니다). 두 건은 **커버리지 비대칭**이고
심각도는 low입니다. 고치는 비용이 parametrize 두 줄이라서 고쳤을 뿐, "누출을 막았다"가
아닙니다.

증거: 네 수리를 각각 되돌렸습니다. M1(문서의 낡은 문장 복원): 파생 가드 1건 red.
M2(낡은 주석 복원): casefold 가드 1건 red — 같은 텍스트에 대해 대소문자 구분 가드는
green(이것이 결함 그 자체입니다). M3(probe 규칙 본문에만 트래픽 첨부):
`[connector_probe_failure]` parametrization 1건 red. M4(성공 분기에 URL 보존):
`[succeeded]` parametrization 1건 red. 전체 정순 `pytest` 1347 passed, 15 skipped
(1344에서 +3).

### Fixed — probe 규칙이 읽지 않은 conjunct. 효과가 측정되는 유일한 control이 빠져 있었습니다 (high)

`verdict_basis`의 conjunct는 셋입니다: adapter 구현 + required control의 선언된 proof
endpoint가 서비스됨 + runtime 검증 control이 통과. `connector_probe_failure_reason`은
**둘만** 읽었습니다. 빠진 세 번째는 route가 존재한다는 사실에서 추론하는 것이 아니라
control의 **효과를 실제로 측정하는** 유일한 conjunct이고, 그 절반은 빌드 소유입니다 —
runtime 검증 control 둘 중 `credential_vault`의 결과는 운영자의 `SDP_CONNECTOR_SECRET_*`
설정이지만, `ontology_version_pin`의 결과는 이 소스 트리의 술어입니다.

핀 비교를 깨고 측정했습니다(`_verify_ontology_version_pin`의 docstring이 "비교를 깨면 이
control은 구현됐다고 주장하지 않는다"고 적어 둔 바로 그 상태):

    probe status       contract_only
    row verification   proof_route_served      ← route는 여전히 서비스됨
    row gap_reason     the version pin predicate did not hold in both directions
    failure_reason     ''
    rule report        observed_total 0, firing False
    gauge              sdp_connector_probe_failures_total 0

`declared_only`에 키를 물렸기 때문에 놓쳤습니다 — route는 서비스되므로 행은
`proof_route_served`에 머무릅니다. 진짜 빌드 결함에 critical 규칙이 0을 보고하는 동안,
세 개의 게시 표면이 이 규칙이 "`verdict_basis` 중 빌드가 소유하는 절반"을 덮는다고
주장했습니다(함수 docstring, `GET /enterprise/production-readiness`의 acceptance
criterion, 그리고 이 CHANGELOG). `python -m sdp.demo_smoke`는 그 쌍에 대해
`status == "ready_for_demo"`를 단언하므로 **실패했습니다** — 피해 범위가 줄어든 것이고
없어진 것이 아닙니다. runtime alert와 gauge와 게시된 주장은 그대로 틀렸습니다.

세 번째 사유를 더했습니다. 소유권은 한 곳에만 씁니다 — `_RUNTIME_CONTROL_CHECKS`가
`control -> (검사, 소유자)`를 담고, `BUILD_OWNED_RUNTIME_CONTROLS`와 제외가 모두 거기서
파생됩니다. 그 매핑의 주석이 이미 적어 둔 교훈입니다: 같은 집합을 손으로 두 번 쓰면
어긋나고, 게시 판정을 결정하는 쪽이 조용히 이깁니다. 행마다
`runtime_check_owner`를 게시하므로 읽는 사람이 어느 쪽인지 알 수 있습니다.
`credential_vault`는 제외를 유지합니다 — 거기서 발화하면 배포되는 demo image에서
발화합니다. 규칙의 `condition`과 `not_covered`, production readiness 기준,
`docs/enterprise-readiness.md`를 모두 사실로 고쳤습니다.

**부수로 찾은 것: probe 라우트의 게시된 응답 스키마가 5개 모양 중 1개에서 파생돼
있었습니다.** `_fetch`가 `connector_id`를 하나만 치환하므로, 스키마는 그 connector의
control 행에서 파생되고 위의 parametrize 검사는 같은 하나에 대해서만 검증합니다. 200을
답하는 모든 connector/dataset 쌍에 대해 측정하면 라이브 행이 스키마에 없는 키 **11개**를
담고 있었습니다 — `gap_reason`, ontology 핀의 관찰 4개, credential vault의 4개,
그리고 `runtime_check_owner`. 하나의 모양에서 파생된 게시 스키마는 이 모듈이 존재해서
거부하는 바로 그 drift입니다(모듈 docstring 자신의 표현). 11개를 게시하고, 모든 쌍을
도는 테스트를 더했습니다.

증거: 세 수리를 각각 되돌렸습니다. M1(세 번째 사유 제거): 1건 red. M2(`credential_vault`를
빌드 소유로 표시 — demo image를 페이지하게 됨): 5건 red. M3(스키마에서
`runtime_check_owner` 제거): 새 전수 테스트 1건 red. 전체 정순 `pytest`
1344 passed, 15 skipped (1340에서 +4).

### Fixed — alert 경로의 예외 가드가 요청 스레드에 없었고, 래치 결정이 관찰 순서를 지키지 않았습니다 (high)

**가드가 엉뚱한 스레드에 있었습니다.** `_deliver_alert`의 넓은 `except Exception`은 스폰된
스레드의 본문만 감쌉니다 — 그 스레드는 애초에 요청에 닿을 수 없습니다. 래치 뒤에 **요청
스레드가 직접** 하는 일(rule의 report 호출, payload 생성, `worker.start()`)은 가드가
없었으므로, 거기서 raise가 나면 governed 요청으로 빠져나가 그 `except`의 주석이 스스로
"막는다"고 적어 둔 전례를 그대로 재현합니다: governed probe가 실제 워커를 통해 500을
답하고 **policy decision +1, audit event +0** — 감사하지 않은 결정. `api.py`가
`connector_probe`가 돌아온 **뒤에** audit event를 기록하기 때문입니다.

`_begin_alert_delivery`가 `_begin_alert_delivery_locked`를 감싸고 아무것도 요청으로 새지
않습니다. 평가 단계에서 raise한 것은 stage `evaluation`으로 보존되고
`evaluation_failures`에 셉니다 — `deliveries_failed`가 아닙니다. POST를 시도하지 않았으므로
`failed`에 세면 `attempted` 없는 `failed`를 게시하게 되고, 그것이 바로 위 항목에서 닫은
자기모순입니다.

**래치 결정이 관찰 순서를 지키지 않았습니다.** `firing`을 lock **밖에서** 읽고 그 결정을
lock 안에서 적용했으므로, "firing 아님"을 먼저 관찰하고 lock을 나중에 잡은 평가가 그
사이에 세워진 래치를 지웠습니다. 다음 increment가 다시 래치하고 **같은 episode에 두 번째
POST**를 보냅니다. 게시된 경계 — rule당 firing episode 하나에 POST 하나, 그래서 reset
사이에 워커당 최대 둘 — 은 불변식이 아니었습니다. report를 lock **안에서** 읽습니다. 두
report 모두 I/O도 자체 lock도 없는 메모리 dict 읽기이므로 직렬화 비용은 마이크로초
단위이고, 사는 것은 순서입니다.

**핸드셰이크 예산과 join이 미들웨어 지점에서 전혀 고정돼 있지 않았습니다.**
`ALERT_HANDSHAKE_BUDGET_SECONDS`는 firing 요청이 wedged webhook 값을 치르는 **유일한**
이유인데, 미들웨어 평가 지점의 비용에 대한 단언이 없었습니다. 예산을 지우고(`worker.join()`)
측정하면 그 호출이 5000 ms alert 타임아웃에 대해 **5012.93 ms**가 걸리고 전체 스위트는
초록이었습니다 — loop-block 테스트는 tick 간격을 재고, probe-route 테스트는 이 평가 지점이
있지도 않은 라우트를 잽니다. 바닥도 없었습니다: join이 없으면 호출이 1 ms 안에 돌아오고,
join이 존재하는 이유인 "평가 지점에서 episode당 POST 하나가 관측 가능하다"는 뒷받침이 없는
주장이 됩니다. 천장(1000 ms)과 바닥(예산의 60%)을 양쪽 지점에 모두 걸었습니다. sync 지점의
기존 테스트는 다섯 요청의 최댓값만 재는데 그중 전이는 첫 번째 하나뿐이므로, 바닥은 전이
요청 단독으로 읽어야 합니다.

`test_the_alert_webhook_value_is_read_one_way_and_stashed_nowhere`의 stash 검사는 **범위**가
아니라 대상 종류를 물었습니다. 모든 `ast.Name` 대상을 제외했으므로 자기 메시지가 두 번
이름을 부르는 바로 그 경우 — 모듈 수준 `_WEBHOOK = os.environ.get("SDP_ALERT_WEBHOOK_URL", "")`
— 를 제외했습니다. 측정: `os.environ.get`을 쓰는 모듈 수준 stash는 위쪽 `os.getenv` 읽기
집계에도 걸리지 않아 테스트 전체가 초록이었습니다(`os.getenv` 쪽 stash는 읽기/함수 개수
단언에 걸립니다 — 검사 하나가 멀었던 것이고 테스트 전체가 멀었던 것은 아닙니다. 그렇게
적습니다). 이제 모듈 수준 `Name`도 stash입니다.

증거: 네 수리를 각각 되돌렸습니다. M1(요청 스레드 가드 제거): 1건 red. M2(양쪽 join에서
예산 제거): 3건 red(25.99 s). M3(join 자체 제거): 2건 red. M4(`firing`을 lock 밖에서 읽기):
1건 red. stash 검사는 `os.environ.get` 모듈 stash로 red, 예전 검사로 되돌리면 같은 변형에
green. 전체 정순 `pytest` 1340 passed, 15 skipped (1336에서 +4).

### Fixed — 실패한 alert를 "전달됨"으로 게시했습니다. 이름이 읽는 카운터와 달랐습니다 (high)

`_alert_delivery_fields`가 게시 키 `alerts_delivered`를 `_ALERT_ROUTING["attempted"]`에
물렸고, `metrics.alerts_delivered_total`과 `sdp_alerts_delivered_total` gauge도 같은 시도
횟수를 읽었습니다. 정직한 숫자를 담고 있던 `deliveries_succeeded`는 **아무도 읽지
않았습니다.** 그래서 webhook이 거부한 POST 한 번이 `alerts_delivered: 1`과
`alerts_failed: 1`로 **같은 POST를 두 번** 게시하고, gauge는 1을 내보냈습니다. gauge의 HELP
문구는 "attempted"라고 적혀 있었고 이름은 "delivered"였으며, per-rule JSON 키에는 그런
단서조차 없었습니다.

이름을 읽는 카운터로 고쳤습니다: per-rule은 `alerts_attempted`·`alerts_succeeded`·
`alerts_failed`, metrics는 `alerts_attempted_total`·`alerts_succeeded_total`·
`alerts_failed_total`, gauge는 셋 모두 내보냅니다(이전에는 실패 gauge가 아예 없어서
운영자가 gauge만 보고는 거부된 전달을 알 수 없었습니다). `succeeded` gauge의 HELP에
"attempted에서 이 값을 빼서 페이지하라"고 적었습니다.

매니페스트는 `alert_routing_state()`를 **한 번만** 읽고 세 gauge와 `alert_delivery` 블록이
그 한 snapshot을 공유합니다. 두 번 읽으면 전달이 진행되는 동안 한 문서가 자기와 다른 숫자를
담을 수 있습니다.

같은 bookkeeping의 두 번째 결함: 보존 실패 ring에 generation 가드가 없었습니다. 카운터
쓰기는 reset된 episode의 것을 버리는데 ring은 그대로 append했으므로, 게시된
`alert_delivery`가 `deliveries_failed: 0` 옆에 그 rule의 보존 실패를 함께 들고 있을 수
있었습니다 — 문서가 자기와 어긋나는 것, 이 필드가 존재하는 이유 그 자체입니다.
`_bump_alert_counter`가 적용 여부를 돌려주고 ring append가 그것을 따릅니다. 시작 시점에
이미 stale한 스레드는 **POST 자체를 하지 않습니다**: POST는 아직 프로세스를 떠나지 않았고,
아무도 세지 않는 episode의 전달이며, 이 스위트에서는 다음 테스트의 double에 도착합니다.

**내 테스트에 또 구멍이 있었습니다(이 주기 네 번째).** ring 가드 테스트의 첫 판은 stale
generation을 처음부터 건네줬고, 가드를 지워도 초록이었습니다 — 시작 시점 stale 스레드는
ring까지 가지도 않으므로 그 테스트는 가드를 전혀 지나지 않았습니다. reset이 **POST가
비행 중일 때** 들어와야 실패 경로가 stale generation으로 실행됩니다. webhook double이
`reset_alert_routing()`을 호출한 뒤 거부하도록 고쳤고, 그 뒤에 가드를 지우면 빨개집니다.

증거: 세 수리를 각각 되돌렸습니다. M1(이름을 `alerts_delivered`로 복원): firing-discipline
2건 + 응답 계약 1건 red. M2(ring 가드 제거): 고친 테스트 1건 red(고치기 전에는 green —
위 문단). M3(stale 스레드도 POST): 1건 red. 전체 정순 `pytest` 1336 passed, 15 skipped
(1333에서 +3).

### Security — 리다이렉트를 따라가며 운영자 자격증명을 다른 authority로 다시 보냈습니다 (high)

`sdp.observability`의 http(s) 내보내기 경로 **둘 다** — 로그 싱크와 alert webhook — 설정된
URL의 userinfo에서 자격증명을 꺼내 `Authorization` 헤더로 옮깁니다(urllib이 userinfo가 든
authority로 연결할 수 없기 때문입니다). 그 다음 `urllib.request.urlopen`은 POST에 대한
301/302/303 응답을 **따라가고**, 메서드를 GET으로 바꾸고, 받은 헤더를 전부 — 방금 옮긴
`Authorization`을 포함해 — 응답의 `Location`이 가리키는 호스트로 다시 보냅니다.

기본 opener로 측정했습니다. loopback 서버 둘, 첫 번째가 302와
`Location: http://127.0.0.2:<port>/exfiltrated`를 답합니다:

    POST /webhook      Host 127.0.0.1:35661  Authorization: Basic c2VjcmV0...
    GET  /exfiltrated  Host 127.0.0.2:39469  Authorization: Basic c2VjcmV0...

결과가 셋입니다. (1) 운영자의 webhook 자격증명이 **두 번째 authority에 도착**했습니다.
(2) 메서드가 GET으로 바뀌면서 alert 본문이 사라졌으므로 **전달된 것이 없습니다.**
(3) 교환이 204로 끝났으므로 `_deliver_alert`가 `succeeded`로 셌고, 매니페스트는 일어나지
않은 전달을 게시했습니다.

두 경로가 리다이렉트를 **거부하는** opener(`_RefuseRedirect` / `SinkRedirectRefused`)로
엽니다. 리다이렉트하는 싱크는 설정 오류이고, 이제 집계되는 실패입니다. userinfo lift가
싱크 쪽 헬퍼(`_http_sink_request_parts`)에 있으므로 alert 경로만 고치면 **더 오래된 누출이
그대로 남습니다** — 그래서 싱크 쪽도 같은 커밋에서 닫고, 싱크 쪽 테스트는
`_EXPORT_ERRORS`에 남는 메시지가 자격증명을 담지 않는 것까지 봅니다(그 ring에 자격증명이
들어간 전례가 이 모듈 docstring에 기록돼 있습니다).

`authz`의 JWKS fetch는 **일부러** 바꾸지 않았습니다: 그 요청은 자격증명을 싣지 않고,
리다이렉트가 빠져나갈 호스트 allow-list가 없고(스킴만 http(s)로 제한), urllib은 http(s)가
아닌 스킴으로의 리다이렉트를 이미 거부하며, 리다이렉트로 서비스되는 JWKS 엔드포인트는
평범한 배치입니다.

테스트는 loopback 서버에 대해 **실제** opener를 돌립니다. disclosure 계열은 일부러
그러지 않습니다(seam을 바꿔서 seam에 무엇이 건네지는지 봅니다) — 이 결함은 urllib이
*응답*을 어떻게 다루는지에 있으므로 double로는 보이지 않습니다. 그래서 두 계열은 합칠 수
없고, 새 파일 `tests/test_http_export_redirects.py`로 들어갑니다.

증거: opener를 `build_opener()`(기본 리다이렉트)로 되돌려 새 테스트 2건이 빨개지는 것을
확인했습니다. 전체 정순 `pytest` 1333 passed, 15 skipped (1330에서 +3).

### Fixed — 전체 수집을 중단시키던 테스트, 비어 있던 stage 예외, 미고정 입력을 하나로 세었던 주장 (high)

2026-10-26 적대적 리뷰 6개 렌즈가 **독립적으로 같은 결함을 보고했습니다.** 6개 렌즈 모두
`<repo>/.claude/worktrees/<id>` 아래의 worktree에서 돌았고, 거기서는 이 저장소의 테스트가
한 건도 실행되지 않았기 때문입니다.

`tests/test_build_input_pinning.py::_dockerfiles()`가 `.claude`/`.git` 제외를 후보의
**절대 경로** 조각에 물었습니다. 제외가 존재하는 이유는 에이전트 하네스가 남기는
`<repo>/.claude/worktrees/<id>` 사본을 건너뛰는 것인데, 체크아웃 자체가 그 경로에 있으면
`.claude`가 체크아웃 자신의 조각이 되어 **저장소의 모든 파일이 제외됩니다.** `found`가 `[]`가
되고, 모듈 수준 `assert`가 `@pytest.mark.parametrize` 인자를 평가하는 중에 터지므로 pytest는
이 파일 하나가 아니라 세션 전체를 끝냅니다. 이 파일과 Dockerfile 두 개만 담은 합성 트리에서
재현했습니다:

    $ cd .../.claude/checkout && pytest tests/test_build_input_pinning.py
    tests/test_build_input_pinning.py:74: in <module>
        @pytest.mark.parametrize("dockerfile", _dockerfiles(), ...)
    E   AssertionError: no Dockerfile was found; re-point this test
    !!!! Interrupted: 1 error during collection !!!!
    no tests collected, 1 error in 0.33s

제외를 `path.relative_to(root).parts`에 묻습니다. 중첩된 낡은 사본은 그대로 제외됩니다 —
그것이 제외의 목적입니다. 합성 트리를 실제로 걷는 테스트로 고정했고, 술어만 보는 테스트도
따로 두었습니다(결함은 술어가 아니라 **술어에 건네진 경로**에 있었습니다).

같은 파일의 digest 게이트에는 다른 구멍이 있었습니다. `" AS " not in line.upper()`가
`AS`를 포함한 모든 줄을 면제했으므로 `FROM python:3.12-slim AS builder` — 맨 `FROM`과 똑같이
레지스트리에서 가져오는 줄 — 이 미고정으로 통과하고, 그 뒤에 교집합을 취하던 `named_stages`
집합은 죽은 코드였습니다. 면제는 **앞선 `AS`가 선언한 이름**에만 줍니다. 지금 이 저장소에
multi-stage 빌드가 없어서 산 피해자가 없었고, 첫 multi-stage 빌드가 조용히 물려받을
것이었습니다.

`docker/postgres-age-pgvector.Dockerfile`의 주석은 pgvector tarball이 "이 저장소에서
content-addressed되지 않은 유일한 빌드 입력"이라고 적었습니다. 사실이 아닙니다. 같은 `RUN`
레이어가 apt 패키지 네 개를 이름만으로 받습니다(세 개는 뒤에서 purge, `ca-certificates`는
남습니다). 주석을 사실로 고치고, 그 네 개를 **일부러** 고정하지 않는 이유를 적었습니다 —
apt 버전 핀은 미러가 그 버전을 아카이브에서 내리는 순간 빌드를 깨고, 미러 회전마다 다시
추측해야 하는 핀은 다시 "핀의 외관"입니다. 한계를 주장으로 덮지 않고 기록했습니다.

이 세 수리에는 산문 가드를 붙이지 않았습니다. 이번 주기에 산문을 매칭하는 가드가 자기
목록에 걸려 실패한 것이 다섯 번이고, 바로 아래 항목이 여섯 번째이므로, 여기서 같은 장치를
하나 더 만드는 것은 측정이 아니라 반복입니다.

증거: 세 수리를 각각 결함 형태로 되돌려 해당 테스트가 빨개지는 것을 확인했습니다(M1
`relative_to(root)` → `path.parts`: 새 테스트 2건 red. M2 `AS` 면제 복원: 1건 red. M3는
주석이므로 되돌림 대상이 아닙니다). 전체 정순 `pytest` 1330 passed, 15 skipped
(1327에서 +3).

### Fixed — 문서가 안내하는 readiness 명령이 진단 대신 traceback을 돌려줬습니다 (medium)

바로 전 커밋(`b278e20`)이 `SDP_CONNECTOR_TIMEOUT_MS`를 읽는 지점에서 검증하게 만든 뒤, 그 변경이
`demo_smoke`에 어떻게 도착하는지 확인하다 나왔습니다. **대부분은 제 변경이 만든 것이 아니라 그 전부터
있던 결함이고**, 측정으로 구분했습니다 — 부모 head(`88ae5d5`)에서:

```
SDP_CONNECTOR_TIMEOUT_MS=2s         exit 1, JSON 없음, ValueError traceback   (기존 결함)
SDP_CONNECTOR_VAULT_PROVIDER=vault  exit 1, JSON 없음, ValueError traceback   (기존 결함)
SDP_CONNECTOR_TIMEOUT_MS=0          exit 0, JSON 있음, "ready": true          (제 변경이 바꾼 것)
```

`PYTHONPATH=src python -m sdp.demo_smoke`는 README와 `sdp_core.enterprise`가 "배포가 준비됐는지
물어보는 방법"으로 안내하는 명령이고, 계약은 **exit code + JSON 보고서**입니다. 앞의 두 경우는
exit code는 맞았고 **무엇을 고쳐야 하는지 알려 주는 쪽을 잃었습니다** — timeout을 잘못 적은 운영자가
진단이 있어야 할 자리에서 Python traceback을 받았습니다. 세 번째는 더 나빴습니다(timeout을 `0`으로
공표하면서 ready라고 답했습니다). 그 세 번째를 읽는 지점에서 거절하게 만든 것이 세 경우를 모두
같은 자리로 데려왔습니다.

`smoke_summary`가 네 probe의 configuration 거절을 **보고서의 한 항목으로** 바꿉니다 —
`connector_configuration_errors`에 변수 이름과 문제를 담고, `ready`는 False, exit code는 1입니다.
exit code는 기존 동작이 맞게 하고 있던 절반이므로, 보고서를 고치면서 그것을 잃으면 수리가 아니라
교환입니다. `KeyError`는 **의도적으로 잡지 않습니다** — seed catalogue에 이 함수가 지목한 dataset이
없다는 뜻이고 그것은 배포 설정이 아니라 빌드의 결함이므로, "ready 아님, 환경을 확인하세요"로
보고하면 이미지의 버그를 두고 운영자를 환경 파일로 보내게 됩니다.

**테스트가 메시지 하나의 비대칭을 잡았습니다.** 각 항목이 자기 변수를 지목하는지 단언했더니
provider 쪽이 실패했습니다 — `"unsupported connector vault provider: vault"`는 **어떤 설정이 그 값을
들고 있는지 말하지 않습니다**(제가 쓴 timeout 메시지는 말합니다). 이 보고서가 운영자가 받는 전부이므로
메시지를 고쳤고(`unsupported SDP_CONNECTOR_VAULT_PROVIDER: 'vault' (only 'env' is implemented)`),
그 메시지를 측정값으로 인용하던 세 곳(`production.py` docstring,
`tests/test_environment_value_domains.py` docstring, README의 환경 변수 절)도 함께 갱신했습니다 —
공개된 인용이 코드가 내는 것과 달라지는 것이 이 저장소가 기계적으로 금지하는 바로 그 결함입니다.

**역검증이 제 테스트에서 이번 라운드 세 번째로 같은 모양의 구멍을 찾았습니다.** `ready` 식에서
`and not configuration_errors`를 지워도 이 파일 7건이 전부 통과했습니다(6 passed). helper가 오류를
기록할 때 정확히 `None`을 돌려주고 네 probe 모두 gate에 자기 필드가 있으므로, 실패한 probe는 이미
자기 clause에서 걸립니다. 측정 결과 네 개 중 **하나만** configuration 오류를 낼 수 있습니다 —
`credential_vault`가 `rest_connector`의 `required_controls`에만 있어서 나머지 셋은
`connector_secret_status`에 닿지 않습니다. 즉 그 clause는 **지금은 중복입니다**. 중복이라고 적어 두는
것이 요점입니다: probe 필드 검사는 "데모 준비됐는가"를 묻고 이 clause는 "설정이 애초에 쓸 수 있었는가"를
물으며, 둘은 지금 우연히 겹칩니다. 나중에 `rest_probe` 필드가 gate에서 빠지거나 vault가 다른
connector로 확장되면 그 우연이 끝나고 아무도 보고하지 않습니다. **동작 테스트는 중복인 clause와 없는
clause를 구별할 수 없으므로** 소스에서 확인합니다 — 같은 라운드에서 미들웨어 호출 지점에 쓴 것과 같은
장치입니다.

역검증 4건(S1~S3 + 재검증), 모두 실패를 확인했습니다: configuration 거절을 다시 raise하게 함(5건 실패),
진단은 공표하지만 gate는 통과(소스 가드 1건 — 처음에는 통과했고 그래서 가드를 넣었습니다),
깨진 seed를 설정 오류로 보고(1건).

### Fixed — paid-pilot gate가 제품을 **깨뜨리는** 값으로 통과했고, 필수 변수 둘은 어느 문서에도 없었습니다 (high)

alert 전달 라운드를 마치고 "이번 변경이 새로 만든 환경 변수는 문서에 들어갔는가"를 확인하다
나왔습니다. 처음 찾은 것은 `SDP_ALERT_TIMEOUT_MS`가 README에 없다는 것 하나였는데, 그 부류 전체를
세어 보니 훨씬 컸습니다.

```
src/가 읽는 SDP_ 이름 23개 중 9개가 README나 CLAUDE.md 중 한쪽 이상에서 누락
  SDP_CONNECTOR_TIMEOUT_MS         required_environment, 양쪽 다 없음
  SDP_CONNECTOR_VAULT_PROVIDER     required_environment, 양쪽 다 없음
  SDP_ALERT_TIMEOUT_MS             CLAUDE.md에만
  SDP_DATABASE_DSN                 README.md에만
  SDP_CONFIG_NAMESPACE             양쪽 다 없음
  SDP_ENV                          양쪽 다 없음
  SDP_OIDC_JWKS_TIMEOUT_SECONDS    양쪽 다 없음
  SDP_OIDC_JWKS_TTL_SECONDS        양쪽 다 없음
  SDP_EVIDENCE_RETENTION_DAYS      declared-unimplemented, 양쪽 다 없음
```

**앞의 두 건은 문서 문제가 아닙니다.** `production_integration_registry`가 둘을
`connector_credential_vault`의 `required_environment`에 넣어 두었으므로
`GET /enterprise/production-readiness`가 `missing_environment`로 **이름을 공표하면서**
`paid_pilot_ready`를 막고 있었는데, 그 변수가 무엇이고 어떤 값을 넣어야 하는지는 어느 문서에도
없었습니다. 조치할 수 없는 blocker를 공표하는 것은 blocker가 없는 것보다 나쁩니다.

#### 그리고 그 둘은 gate를 통과하는 값으로 제품을 깨뜨릴 수 있었습니다

`_is_set`은 비어 있지 않은 문자열이 있는지만 봅니다. 대부분의 변수에는 그것이 정직한 한계입니다 —
이 모듈은 DSN이나 issuer가 실재하는지 알아보려고 데이터베이스나 IdP에 닿을 수 없습니다. 그러나 이
둘은 한계가 아니었고, 운영자가 **자연스럽게 고를 값**으로 그 구멍에 닿습니다. 측정:

```
SDP_CONNECTOR_VAULT_PROVIDER='vault'       gate 통과, probe 라우트 400
  GET /enterprise/connectors/rest_connector/probe?dataset_id=marketing-campaign&user=admin
  -> {"detail": "unsupported connector vault provider: vault"}
SDP_CONNECTOR_VAULT_PROVIDER='hashicorp'   gate 통과, 같은 라우트 400
SDP_CONNECTOR_TIMEOUT_MS='2s'              gate 통과, 같은 라우트 400
  -> {"detail": "invalid literal for int() with base 10: '2s'"}
```

`vault`·`hashicorp`는 운영자가 실제로 쓰는 제품 이름이고 `2s`는 사람이 timeout을 적는 방식입니다.
즉 readiness 문서가 `paid_pilot_ready`로 가는 진척을 보고하는 동안 connector probe — buyer demo의
핵심 surface — 가 네 connector 전부에 400을 돌려주고 있었습니다. 나머지 required 변수 전수를 같은
방식으로 찔러 봤고(그럴듯하지만 틀린 값 + 가장 손상이 드러날 라우트), 이 둘만 해당했습니다.

**이것은 이 registry가 애초에 막으려던 결함보다 나쁩니다.** `SDP_EVIDENCE_RETENTION_DAYS`는
*아무것도 하지 않는* 값으로 gate를 통과시켰고, 이쪽은 gate가 측정한다고 주장하는 능력을
*깨뜨리는* 값으로 통과시켰습니다. 모듈 자신의 문장이 "A gate may only measure capabilities that
exist"인데, **능력을 비활성화하는 값으로 만족되는 gate는 아무것도 측정하지 않습니다.**

#### 수리

registry가 값 도메인을 `environment_value_rules`로 선언합니다 — 의도적으로 **닫힌** 형태입니다
(열거된 값 집합, 또는 하한이 있는 정수. regex도 callable도 타입 변환도 없습니다). manifest는
설정됐지만 거절된 값을 `rejected_environment`에 **이유와 함께** 따로 공표합니다. `missing`과
합치지 않은 이유: 변수를 방금 설정한 운영자에게 "missing"이라고 말하면 이름의 오타를 찾으러
가는데, 필요한 것은 값의 허용 도메인입니다. 설정되지 않은 변수는 `missing`에만, 거절된 값은
`rejected`에만 나옵니다 — 한 문제에 한 항목입니다.

**과잉 선언 하나를 역방향 검사가 잡았습니다.** `minimum=1`을 선언했는데 `int()`는 `0`과 `-5`를
받아들였습니다. gate가 코드에 없는 요구를 발명하는 것은 gate가 느슨한 것과 같은 종류의 결함이므로,
수리를 gate가 아니라 `credentials.connector_secret_status`로 옮겼습니다 — `timeout_ms`는 rest
connector probe의 control evidence로 **공표되는 값**이고 `0`이나 `-5`는 timeout으로서 거짓 공표된
숫자이므로, 읽는 지점에서 검증하는 것이 맞습니다. 그 다음에 registry가 그 도메인을 **거울처럼**
선언합니다.

**가드 8건, 두 파일.** `tests/test_environment_documentation.py`는 변수 집합을 `src/`에서
**파생**해(문자열 리터럴 기준 — 이 저장소는 `os.getenv`·`os.environ.get`·`os.environ[...]`·
설정 로더 전달 네 가지 형태로 읽으므로, `os.getenv`만 보는 검사는 23개 중 18개만 찾습니다) README와
CLAUDE.md 양쪽에 있는지, 그리고 역방향으로 코드가 읽지 않는 변수를 문서가 약속하지는 않는지
확인합니다(후자의 유일한 예외가 `declared_unimplemented_environment`입니다).
`tests/test_environment_value_domains.py`는 선언과 코드가 어긋나지 않도록 **강제하는 함수를 직접
실행해** 양방향으로 비교합니다 — 두 리스트를 서로 대조하는 것은 이 저장소가 반복해서 찾아낸
결함의 모양이기 때문입니다.

**기존 테스트 하나가 같은 결함을 품고 있었습니다.**
`test_production_readiness_measurement.py`의 `_fully_configured_environment`는 모든 required
변수를 리터럴 `"configured"`로 채우면서 docstring에 "as an operator would"라고 적고 있었습니다.
운영자는 그렇게 설정하지 않고, 측정 결과 그 값들은 probe를 400으로 만듭니다 — **gate가 의미 있음을
증명하려고 존재하는 테스트 안에서 바로 그 결함이 재현되고 있었습니다.** 값은 이제 선언된 도메인에서
파생합니다(나중에 추가되는 규칙도 자동으로 만족시킵니다).

README에는 **`## 환경 변수 전수 목록` 표**를 새로 넣었습니다. 전에는 환경 변수가 README 본문
여기저기 산문으로만 있어서 **어디도 전수 목록이 아니었고**, 그것이 9건이 잊힌 구조적 이유입니다.
표에는 변수 23개 전부와 측정한 기본값, paid-pilot gate 여부, 그리고 값 도메인이 있는 두 건의
허용 집합이 있습니다.

역검증 4건, 모두 실패를 확인했습니다: README에서 변수 하나 제거(1건 실패), 아무것도 읽지 않는
변수를 문서에 추가(1건), gate를 presence-only로 되돌림(1건), gate를 코드보다 엄격하게 선언(3건 —
양방향 합의 검사가 과잉 선언 쪽도 잡습니다).

### Fixed — 제가 바로 전에 넣은 alert 전달이 event loop를 막았습니다 (high)

alert 전달을 구현한 커밋(`8895868`)을 직접 다시 읽으면서 찾았습니다. 평가 지점 두 곳의
실행 컨텍스트가 **다릅니다**:

- `connectors.connector_probe`는 route handler가 `def`이므로 FastAPI가 `anyio` worker
  스레드에서 돌립니다 — bounded join이 그 스레드를 막는 것은 맞습니다.
- `note_governed_request_without_evidence`는 `sdp.api`의 **`async` 미들웨어**
  `finally` 블록에서 호출됩니다 — 같은 join이 **loop 스레드**를 막습니다.

그 요청 자신의 지연은 budget 이상으로 늘지 않습니다. 문제는 **그 사이 다른 모든 요청이
직렬화된다**는 것입니다. 10 ms asyncio ticker로 측정했습니다(handshake를 받고 응답하지
않는 소켓, `SDP_ALERT_TIMEOUT_MS=5000`):

```
loop 위의 sync 호출 (결함)     call= 251.15 ms   최악 tick gap= 261.61 ms
async 진입점 (수리)            call= 252~263 ms  최악 tick gap=  11.50~20.69 ms (8회)
webhook 미설정 (대조군)        call=   0.10 ms   최악 tick gap=  11.82 ms
```

**새로운 위험이 아닙니다.** 이 저장소는 같은 결함을 log sink에 대해 이미 한 번 고쳤고
(gap-baseline 감사 7번: "동기 sink export가 event loop를 막아 요청을 직렬화했습니다"),
미들웨어에는 alert 호출에서 **두 줄 아래**에 "The sink write is blocking, so it is awaited
off the event loop"라는 주석이 그대로 적혀 있습니다. 그 주석 두 줄 위에 같은 결함을
넣었습니다.

**수리는 새 장치가 아니라 같은 장치입니다.** `_begin_alert_delivery`가 latch 처리(lock 안의
dict 쓰기 몇 번)를 하고 기다릴 스레드를 돌려주고, 동기 형태는 그 스레드를 직접 join하고,
`_route_alert_async`는 `anyio.to_thread.run_sync`로 **loop 밖에서 await**합니다 —
`record_request_observation_async`가 sink의 blocking write에 하는 것과 같은 분할입니다.
미들웨어는 `note_governed_request_without_evidence_async`를 await합니다. 동기 형태는
worker 스레드에서 도는 probe 경로와 직접 호출자(테스트)용으로 남습니다. 카운팅 절반은
`_count_governed_request_without_evidence` 하나로 공유해 두 진입점이 세는 것이 갈라질 수
없게 했습니다.

**가드 둘, 각각 다른 절반을 잡습니다.** 하나는 async 진입점을 직접 호출해 ticker gap이
100 ms 미만임을 단언하고(측정값과 결함 사이에서 양쪽으로 최소 2.6배 여유), 다른 하나는
**미들웨어가 그것을 await하는지**를 소스에서 확인합니다. 둘이 필요한 이유를 역검증이
보여줍니다 — 함수 안의 join만 loop 위로 되돌리면 전자만 실패하고, 호출 지점만 동기
형태로 되돌리면(함수는 그대로 둔 채) **후자만** 실패합니다. 타이밍 테스트 하나로는 호출
지점 회귀를 못 잡습니다. 이 사이클이 반복해서 배운 구분입니다.

`TestClient`로는 이 결함을 관측할 수 없습니다 — 요청을 한 번에 하나씩 보내므로 직렬화 자체가
드러나지 않습니다. 그래서 ticker이고, 그래서 호출 지점은 소스로 확인합니다.

`test_the_alert_webhook_value_is_read_one_way_and_stashed_nowhere`가 이 변경을 **스스로
보고했습니다** — webhook을 읽는 함수 집합에 `_route_alert`가 아니라
`_begin_alert_delivery`가 들어왔다고 실패했습니다. 전달 결정이 옮겨 간 것을 통과시키지 않고
알려 준 것이므로, 기대 집합을 고치고 그 사실을 테스트 메시지에 적었습니다.

### Fixed — 하나 남아 있던 미고정 빌드 입력을 닫았습니다. 막고 있던 것은 환경이 아니었습니다 (medium)

`docs/product-technical-gap-baseline.md`가 2026-10-14에 **수리하지 않고 기록만 한** 항목으로
남겨 둔 것입니다. `docker/postgres-age-pgvector.Dockerfile`이 pgvector를 가변 GitHub 태그
tarball URL에서 받아 체크섬 검증 없이 root로 컴파일해 `make install`했습니다 — 이 저장소에서
content-addressed되지 않은 **유일한 빌드 입력**이고, 들어가는 곳이 governed 그래프와 증빙
데이터를 담는 Postgres 서버입니다. 태그는 가변 ref이므로 force-push 한 번으로 같은 URL이
다른 바이트를 서비스합니다.

**이 문장은 그때 과장이었습니다** — "유일한"이 아니었습니다. 같은 `RUN` 레이어가
`build-essential`·`ca-certificates`·`git`·`postgresql-server-dev-16` 네 개를 가변 Debian
아카이브에서 이름만으로, root로 받습니다. 아래 "미고정 입력을 하나로 세었던 주장"
항목에서 고쳤습니다.

당시 기록한 이유는 정당했습니다 — tarball을 받을 수 없어(프록시 403) sha256을 계산할 수
없고, **검증하지 않은 해시는 핀이 아니라 핀의 외관**입니다. 그런데 그 기록은 대안 두 가지를
적어 두고 **두 번째가 이 환경에서 가능한지 확인하지 않았습니다.** 가능했습니다:

```
$ git ls-remote https://github.com/pgvector/pgvector refs/tags/v0.7.4
103ac50f1a90b47a72003e8e8628a55ec372f202	refs/tags/v0.7.4
```

tarball HTTP 요청만 403이고 **git 프로토콜은 프록시를 통과합니다.** peeled `^{}` ref가
advertise되지 않으므로 `v0.7.4`는 lightweight 태그이고 위 이름이 커밋 자체입니다. 그 객체를
실제로 받아 확인했습니다 — 타입 `commit`, subject `Version bump to 0.7.4 [skip ci]`, tree
`97af667455d30dba56b092ce3b9241b991f7f888`, tree에 `Makefile`·`src/`·`sql/`·`vector.control`,
그리고 `vector.control`의 `default_version`이 `'0.7.4'`입니다. 한 달 가까이 "환경이 막는다"로
남아 있던 항목인데, **막고 있던 것은 환경이 아니라 한 번도 시도하지 않은 명령**이었습니다.

**핀을 강제하는 것이 git 자신입니다.** 그래서 download가 아니라 fetch입니다 —
`git fetch <sha>`는 받은 객체가 요청한 이름으로 해시되는지 검증하므로, 같은 이름으로 다른
내용을 주는 서버는 빌드를 실패시킵니다. `git clone --branch <tag>`는 그 검증을 하지 않으므로
핀처럼 보이지만 핀이 아니고, 아래 가드가 그 형태를 거절합니다. `PGVECTOR_VERSION`은 이미지
라벨로만 남기고 pin된 tree의 `vector.control`과 빌드 중에 대조합니다 — 커밋 이름이 이미
내용을 고정하므로 핀을 강화하지는 않고, 두 ARG가 따로 움직여 **이미지가 담고 있지 않은
버전을 라벨로 붙이는 것**을 막습니다. `curl`은 더 이상 설치하지 않습니다.

**한계를 적어 둡니다**: git 객체 이름은 SHA-1이므로 sha256 content digest보다 약하고, 가변
태그보다는 확실히 강합니다. tarball에 닿는 환경에서 계산한 sha256으로 교체하는 것은 그대로
개선입니다. `git archive`로 tarball을 재현해 해시를 뽑지는 않았습니다 — GitHub archive
엔드포인트는 prefix·gzip 설정·mtime이 고정된 자기 형식이라 byte 단위로 재현되지 않고,
재현되지 않은 해시는 다시 핀의 외관일 뿐입니다.

**회귀 가드 `tests/test_build_input_pinning.py` 10건.** 고장났던 그 파일을 지목하지 않고
저장소의 모든 Dockerfile을 찾아 검사합니다 — 나중에 추가되는 두 번째 미고정 입력도 같은
결함이고, 파일 이름을 적어 둔 가드는 자기 목록과 대조하는 가드입니다. `FROM`은 `@sha256:`
digest를, 소스 archive는 가변 ref URL 금지를, 빌드 중의 git fetch/clone은 40-hex 객체
이름을, `*_COMMIT` ARG 기본값도 같은 형식을 요구합니다. Dockerfile의 line continuation과
주석을 Docker와 같은 방식으로 접어 읽습니다 — 주석 줄에 산문이 있고 한 `RUN`이 여러 줄에
걸쳐 있으므로, raw 줄 단위로 읽는 검사는 명령과 그 플래그를 다른 줄로 갈라 놓고 놓칩니다.

역검증 5건, 모두 실패를 확인했습니다: 가변 태그 tarball 복원(2건 실패), 태그 ref로 git
fetch(2건), 버전 대조 제거(1건), 축약 커밋 이름(2건), base image 태그만(1건).

**정리하지 못한 것 하나**: `.claude/worktrees/` 아래에 완료된 workflow의 worktree 11개가
154 MB로 남아 있습니다. gitignore 대상이라 저장소에는 영향이 없고 디스크도 28 GB 여유가
있어 급하지 않습니다. 일괄 제거 명령이 권한 분류기에서 거절되었으므로 우회하지 않고
그대로 두었습니다 — `git worktree remove --force` 11건이 필요합니다.

### Added — alert 전달(routing)과 세 번째 alert 규칙 (feature)

`SDP_ALERT_WEBHOOK_URL`은 이 저장소에서 가장 오래된 "선언만 되어 있고 구현되지 않은"
항목이었습니다 — 패키지 전체에서 이 값을 읽는 곳이 `_sink_status`의
`bool(alert_webhook_url)` 하나였고, `production.py`의
`declared_unimplemented_environment`가 그 사실을 공표하고 있었습니다. 전달을
구현했습니다. 함께 `request_observability_export` 인수 기준이 "이름만 지목되고 한 번도
게시된 적 없다"고 적어 둔 **connector-probe-failure 규칙**도 게시·평가합니다.

구현보다 먼저 결정해야 했던 것은 **빈도**입니다. `policy_audit_gap` 카운터는 미들웨어가
요청마다 올리고, 그 표면은 credential을 요구하지 않습니다. 측정: 익명 probe 요청 25건이
197.1 ms에 끝납니다. 따라서 "firing이면 POST"를 증가 지점에서 평가하면 **익명 트래픽
200 ms당 운영자의 webhook으로 POST 25건**입니다. 규칙은 이렇게 정했습니다 —

* **episode당 1회.** routable 규칙이 not-firing→firing으로 **전이**할 때만 보냅니다.
  이미 firing인 동안의 2..N번째 증가는 세어서 버리고, 그 수(`increments_suppressed`)도
  함께 게시합니다 — 1건의 alert가 1000건을 대표할 때 운영자가 억제와 거부를 구별할 수
  있어야 하므로, breaker의 `skipped_exports`와 같은 규율입니다.
* **re-arm은 타이머가 아니라 규칙 자신의 flag를 따릅니다.** `firing`은
  `observed_total > 0`이고 `src/` 어디에도 이 카운터를 **감소시키는 경로가 없습니다** —
  배포된 worker에서 한 번 발화한 규칙은 재시작까지 firing으로 남습니다. 최소 간격 규칙은
  결코 해소되지 않는 조건에 영원히 재전송하고, "첫 전이만"은 reset 이후의 진짜 episode를
  침묵시킵니다. 그래서 latch는 규칙이 firing을 그만둘 때 풀리고,
  `reset_request_observability()`가 그 유일한 경로입니다.
* **상한이 숫자입니다.** routable은 3건 중 2건이므로 reset 사이 한 worker가 보내는 POST는
  버스트 크기와 무관하게 최대 2건입니다. `central_workflow_backlog`은 이 서비스가 관측할
  수 없는 GitHub Actions 상태가 조건이므로 `routable: false`로 공표합니다 — routable로
  적으면 결코 발화할 수 없는 전달을 약속하게 됩니다.
* **read path에서는 절대 보내지 않습니다.** `build_observability_manifest`와
  `prometheus_metrics_text`는 미인증으로 열린 두 라우트가 도달하고, manifest는 규칙의
  `firing` flag를 이미 게시합니다 — read path 구현이 바로 그 값으로 행동하려 들 지점입니다.
* **요청이 webhook을 기다리지 않습니다.** 전달은 자기 스레드에서 돌고 평가 지점은
  `ALERT_HANDSHAKE_BUDGET_SECONDS`(0.25초)만 join합니다. 측정된 선례: 요청이 직접
  await하는 log sink는 handshake만 받고 응답하지 않는 소켓에 대해 500 ms timeout에서
  요청당 507.8–514.5 ms를 물렸습니다.

**조건을 정직하게 고르는 것이 이 작업의 절반입니다.** connector-probe 규칙의 뻔한 조건
("`ready_for_demo`에 도달하지 못한 probe를 센다")은 **배포되는 demo image에서 발화합니다**.
seed catalogue 20쌍(connector 4 × dataset 5) 측정:

    20쌍  4 ready_for_demo · 1 contract_only · 15 scheme mismatch(ValueError) · 0 기타

`contract_only` 1건(`rest_connector`/`marketing-campaign`)은 고장난 것이 아닙니다 —
optional한 `SDP_CONNECTOR_SECRET_*` 하나가 설정되지 않아 `credential_vault`가 fail-closed한
것이고, 그 이름 하나를 설정하면 `ready_for_demo`로 바뀝니다(같은 프로세스에서 측정).
`demo_smoke`의 ready gate는 `status == "ready_for_demo"`가 아니라
`adapter_status == "implemented"`를 단언하며 그 상태로 `ready: true`를 보고합니다. 나머지
15쌍은 caller가 dataset을 받치지 않는 connector를 지목한 것이고, `connector_id`는 caller가
주는 path segment입니다 — 세면 path segment 오타가 운영자의 pager를 울립니다.

남는 정직한 조건은 probe 자신의 `verdict_basis` 중 **빌드가 소유하는** 실패입니다:
레지스트리가 선언한 adapter를 이 빌드가 구현하지 않음, 또는 required control이 선언한
proof endpoint를 이 빌드가 서비스하지 않음. 둘 다 caller 통제도 설정도 아니고, 측정 결과
20쌍 전부에서 0입니다. 규칙은 제외한 두 결과(설정 gap과 caller 실수)와, seed 20개
control 행 중 19개가 `proof_route_served`에 기대고 있다는 사실을 `not_covered`로
함께 공표합니다 — 0이 "모든 control이 통과했다"는 주장이 아니기 때문입니다.

**이 "빌드가 소유하는 실패"는 그때 두 개가 아니라 세 개였어야 했습니다.** `verdict_basis`의
conjunct는 셋이고 이 조건은 둘만 읽었습니다. 뒤의 "읽지 않은 conjunct" 항목에서 고쳤습니다.

**공개 표면에 추가되는 것과 되지 않는 것.** `alert_routing: implemented` 옆에
`alert_delivery`가 실측 전이·전달·억제 횟수를 게시하고, 규칙마다 `routable`·
`alerts_delivered`·`alerts_failed`·`increments_suppressed`가 붙고, `/metrics`가
`sdp_connector_probe_failures_total`·`sdp_alerts_delivered_total`을 내보냅니다.
(뒤 항목에서 `alerts_delivered`/`sdp_alerts_delivered_total`은 **시도** 횟수를 읽고
있었으므로 이름을 고쳤습니다 — 지금 이름은 `alerts_attempted`/`alerts_succeeded`/
`alerts_failed`와 세 gauge입니다.)
alert **대상 호스트는 redact해서도 게시하지 않습니다** — log sink가 redacted `target`을
게시하는 이유(설정 오류와 미설정을 구별)는 `invalid_configuration`과
`alert_webhook_routing`으로 이미 충족되고, 운영자의 paging endpoint 호스트는 이 서비스의
거버넌스에 대한 사실이 아닙니다. webhook의 userinfo는 urllib가 보기 전에
`_http_sink_request_parts`가 `Authorization` 헤더로 들어올립니다. 측정: userinfo를 담은
webhook은 네트워크에 도달조차 하지 않고 `http.client`가 **복호화된 credential을 그대로
인용하며** 예외를 던집니다.

    https://sdp-alerts:p%40ssw0rd-42@alerts.invalid.example/hook
      InvalidURL  "nonnumeric port: 'p@ssw0rd-42@alerts.invalid.example'"

그래서 실패는 `str(exc)`가 아니라 **예외 타입과 단계만** 보관합니다 — URL의 어떤 조각도
남기지 않습니다. alert body도 규칙과 그 보고서만 싣습니다. 이 모듈이 가진 context는
`list_request_observations()`이고 그 행은 caller가 주장한 `tenant_id`·`actor`·
`request_id`와 **구체적 경로**를 담습니다 — manifest가 per-request feed를 거부할 때 든
바로 그 세 가지이고, alert webhook은 인증된 tenant 표면이 아니라 제3자 운영자 endpoint이므로
붙이면 한 tenant의 governed-access 활동을 off-box로 재수출하는 것이 됩니다.

**`declared_unimplemented_environment`에서 변수를 빼고, `required_environment`로
옮기지는 않았습니다.** 낡은 "구현되지 않았다"는 선언은 섣부른 "구현되었다"와 같은 결함을
같은 독자에게 저지릅니다. 그러나 게이트는 `_is_set`으로 **presence만** 보므로, 요구로
돌리면 scheme이 없어 POST 자체가 불가능한 `'banana'`가 게이트를 통과합니다 — 이 레지스트리가
거부하려는 결함이 반대 방향에서 도착하는 것입니다. 경보는 선택 사항입니다. 변수는
`current_evidence`에 소비자·테스트와 함께 나열합니다.

**역검증(mutate → 측정 → 복원), 모두 실패를 확인했습니다**: latch 제거(7건 실패),
join 무제한(wedged webhook을 요청이 지불, 1건), 조건을 `status`로 keying(demo image에서
발화, 4건), 원본 URL을 urlopen에 + `str(exc)` 보관(credential이 표면에, 1건), payload에
observation 행 첨부(tenant/actor off-box, 1건), reset이 latch를 남김(다음 episode 침묵,
2건), chokepoint 제거(직접 호출자 미집계, 5건), scheme gate 제거(1건), counter를
dataset id로 keying(3건), backlog를 routable로 선언(1건), alert target 게시(1건).

**역검증이 제 테스트에서 구멍 셋을 찾았고, 셋 다 메웠습니다.**

1. **read-path 테스트 둘이 공허했습니다.** `build_observability_manifest` 맨 위에서 두
   routable 규칙을 라우팅하는 mutation — 그 테스트들이 이름으로 지목하는 바로 그 결함 —
   을 넣었는데 **통과했습니다(23 passed)**. 각 테스트는 seam이 살아 있음을 먼저 증명하려고
   진짜 전이 하나를 일으키고, 그 전이가 규칙을 latch하므로 read-path 호출은 억제 분기에
   떨어집니다. docstring이 호출 지점 제약의 공로로 돌린 일을 latch가 하고 있었고, latch가
   있는 한 호출 지점 제약은 **측정되지 않았습니다**. 수리: liveness 전이 뒤에 latch만
   비웁니다(`_disarm_the_latch`) — 규칙은 firing으로 남고 latch는 비므로 read-path 구현이면
   첫 manifest build에서 POST합니다. 같은 mutation이 이제 두 테스트를 실패시킵니다.
2. **scheme gate를 재는 테스트가 gate를 재지 않았습니다.** gate를 삭제해도 `ftp://`
   케이스는 통과합니다 — 값이 `_http_sink_request_parts`를 지나 host가 해석되고 연결
   가능한 URL이 만들어진 뒤 **DNS에서** 실패하기 때문입니다(측정: `URLError [Errno -2]`).
   둘을 가르는 결함은 `file://`입니다. 측정: `file://` URL로의 POST는 실패하지 않고
   `FileHandler`가 **로컬 경로를 열어 내용을 돌려줍니다** — gate가 없으면 firing episode마다
   서버의 로컬 파일 읽기가 되고 **성공한 전달로 집계·게시됩니다**. 두 scheme 모두
   구동하고, `file://` 케이스는 `deliveries_succeeded == 0`을 단언합니다. 그리고 URL은
   `Path.as_uri()`가 아니라 명시적 `localhost` authority로 만듭니다 — 측정 결과
   빈 authority 형태(`file:///...`)는 host 요구 조건에 걸려서, `as_uri()`로 쓰면 gate가
   없는데도 있는 것처럼 보고합니다.
3. **억제 횟수가 트래픽으로 채워질 수 있었습니다.** `note_connector_probe`에서
   `observed_increment=True`를 무조건 넘기는 mutation(즉 정상 probe도 억제로 집계)이
   **전부 통과했습니다(28 passed)**. gap 규칙은 이것을 잡을 수 없습니다 — 그 평가 지점의
   모든 호출은 실제 증가이기 때문입니다. probe 규칙이 정상 트래픽에도 호출되는 유일한
   규칙입니다. "1건 alert, 499건 억제"를 읽는 운영자는 governed 실패 500건을 결론해야
   하는데, 정상 probe가 섞이면 그 숫자는 실패의 이름을 쓴 트래픽 양입니다. 혼합을
   구동하는 테스트를 넣었습니다 — proof endpoint를 깨면 네 connector 모두 실패하므로,
   대신 한 connector의 adapter를 제거해 그 하나만 실패하고 나머지 셋은 정상으로 둡니다.

새 RED 테스트 33건(네 파일)과 `test_honest_metrics.py` 1건, 합계 **+34건**. 네 파일의
prose는 측정된 head(= 이 커밋의 부모)를 가리키도록 과거형으로 다시 썼습니다 — RED 명세로
쓰인 글을 현재형으로 두면 자신이 지키는 코드의 반대를 주장하는 파일 넷을 싣게 되고, 그것이
이 저장소가 반복해서 찾아내는 결함 그 자체입니다.

**이전 가드는 설계대로 실패했고, 설계대로 다시 썼습니다.**
`test_nothing_posts_to_the_alert_webhook`의 docstring이 약속한 대로입니다. 후속 가드 둘:
값의 **읽기 방식이 하나**임을 AST로 단언합니다(측정: `SDP_ALERT_WEBHOOK_URL="   "`일 때
strip한 읽기는 falsy고 manifest는 `alert_webhook_configured: false`를 게시하지만, 같은
변수의 strip하지 않은 읽기는 **truthy**입니다 — 전달 경로가 strip하지 않으면 manifest가
"미설정"이라 적는 동안 `"   "`를 webhook으로 삼습니다), 그리고 값이 **어디에도 저장되지
않음**(모든 대입 대상이 평범한 지역 이름; `_ALERT_TARGET["url"] = ...` 한 줄이면 공개
manifest가 답하는 그 집합에 운영자 credential이 들어갑니다). 두 번째 후속 가드는
"전달되지 않는다"는 문장을 README·CLAUDE.md·docs·src·tests에서 기계적으로 금지합니다 —
평가에 대한 같은 종류의 가드가 이미 있었고, 전달 쪽에만 없으면 첫 재발은 잡고 두 번째는
놓칩니다. 금지 문장은 **현재형만** 대상입니다(과거형 역사 기술은 남겨 둡니다).

**가드가 자기 설명과 대조되는 결함이 이 사이클에서 다섯 번째였습니다.** 새 금지 목록도
처음에는 자기 파일을 적발했습니다 — 목록의 리터럴 자체가 적발 대상이었습니다. 두 조각의
연결로 조립해 리터럴이 소스에 존재하지 않게 했고(`tests/test_state_isolation.py`가 같은
이유로 도달한 방법), 설명하는 산문에서는 금지 문장을 **인용하지 않고 바꿔 씁니다**.

### Fixed — 그래프 스토어 제외의 *결론*이 세 파일에 현재형으로 남아 있었습니다 (medium)

적대적 리뷰가 `c50eae7`을 대상으로 "제외 주장이 다섯 파일에 그대로 있고, 그것을 막으려고
추가한 재발 가드가 통과한다"고 보고했습니다. HEAD에서 다시 측정했습니다 — **제외 주장
자체는 모두 사라졌습니다**. `dd0c3f3`이 그 다섯 사이트를 잡는 문구 둘을
`_RETRACTED_EXCLUSION_CLAIMS`에 추가했고, 지금 가드는 어느 것도 적발하지 않습니다.
리뷰는 7개 커밋 뒤처진 head를 재고 있었습니다.

남아 있던 것은 **한 단계 아래**이고 가드는 그쪽을 보지 않습니다. 세 docstring이 제외에서
**파생된 규칙** — 그래프 수치에 의존하는 테스트는 자기 baseline을 잡아야 한다 — 을 현재의
표준 규칙으로 제시하고 있었고, 그중 하나는 `56259e0`이 삭제한 `tests/conftest.py`의
문장을 인용하고 있었습니다(측정: `grep -n "own baseline" tests/conftest.py` → 결과 없음).
주장과 같은 이유로 문제입니다 — 이것이 표준 규칙이라고 읽은 사람은 파일별 그래프 cleanup을
계속 쓰게 되고, 그것은 fixture 자신의 docstring이 "이 fixture가 막으려고 존재하는 바로 그
구성"이라고 부르는 것입니다. 세 사이트를 고치고, 파생된 지시문 문구를 가드에 추가했습니다.

파일별 fixture 자체는 **남겨 둡니다**. fixture docstring이 선행 사본들에 대해 이미
정리한 바 — 중앙 fixture 안에 중첩되고 같은 값으로 복원하므로 틀린 것이 아니라 중복 —
이고, 셋 중 둘은 여전히 유효한 두 번째 이유를 기록하고 있습니다(공유 스토어에 위반이나
cycle을 남긴 테스트는 이후의 모든 단언을 파일 순서에 의존하게 만듭니다). 다만 중복이라는
사실을 측정해서 적어 둡니다 — `test_graph_mirroring.py`의 fixture 본문을 빈 `yield`로
바꿔도 그 파일 단독 14건과 스토어를 공유하는 두 파일과 함께 43건이 통과합니다.

역검증: 철회한 지시문을 세 사이트가 쓰던 문구로 되돌리면
`test_no_published_text_still_says_the_graph_store_is_excluded`가 실패합니다.

### Fixed — alert 라우팅을 막는다는 tripwire가 실제로는 막지 않았습니다 (high)

다음 기능(alert 라우팅)의 RED 테스트를 설계시키던 중, 에이전트 하나가 **그 기능을 막는
가드가 작동하지 않는다**는 것을 측정해 왔습니다. 직접 재현했습니다.

`tests/test_honest_metrics.py::test_nothing_posts_to_the_alert_webhook`의 docstring은
"라우팅 경로가 추가되면 이 테스트가 실패하고, 추가한 사람이 변수를
`required_environment`로 되돌리게 된다"고 적습니다. 본문은 세 가지를 단언했습니다 —
변수를 언급하는 파일이 정확히 둘, `os.getenv` 읽기가 정확히 하나, 그 읽기의 정확한 텍스트.
**셋 모두 작동하는 라우팅 경로와 양립합니다.** 값에 무슨 일이 일어나는지 보는 단언이
하나도 없기 때문입니다. 측정:

    observability.py에 _deliver_alert 추가
      (urllib Request를 만들어 urlopen으로 POST)
    기존 단일 getenv 읽기에서 _ALERT_TARGET["url"] = alert_webhook_url 한 줄로 급전
      -> test_nothing_posts_to_the_alert_webhook: 3 passed

즉 **라우팅이 완전히 구현된 상태에서 가드가 녹색입니다.** docstring이 본문이 치지 않는
덫을 약속하고 있었습니다 — 이 사이클의 다른 모든 가드와 같은 모양(자기 목록과 대조하고,
설명하는 대상과는 대조하지 않음)이고, 이번에는 **아직 만들지도 않은 기능을 막는 가드**가
그랬습니다.

**네 번째 단언을 넣었습니다.** 값은 한 번 읽히고 **boolean 문맥에서만** 쓰입니다 —
`alert_webhook_configured` 필드를 위한 `bool(alert_webhook_url)` 두 번. 라우팅은 문자열
자체가 필요하므로(파싱하든 접속하든 저장하든), 어떤 라우팅 경로든 값을 저장하거나
넘기거나 반환하거나 변수를 다시 읽어야 합니다. AST로 파싱합니다 — 도달 대입과 그 사용은
구조이기 때문입니다. 그리고 **load 단위로 identity 비교**합니다: 문장 단위로 쓴 첫 버전은
허용된 두 사용이 모두 return 안의 dict 리터럴 안에 있어서 둘 다 escape로 보고했습니다.

역검증: 예전 tripwire를 통과시킨 바로 그 라우팅 경로를 넣으면 이제
`observability.py` 411행을 이름으로 말하며 실패합니다.

**이 수리의 효과는 다음 커밋에서 나타납니다** — 라우팅을 구현하면 이 테스트가 설계대로
실패하고, 그때 비로소 "의도적으로 다시 쓰고 변수를 `required_environment`로 옮긴다"는
docstring의 약속이 지켜집니다.

### Fixed — 6라운드: 공표된 열거가 **일어날 수 없는** 사유를 담고 있었습니다 (high)

5라운드 커밋 둘(`56259e0`·`c50eae7`)을 다섯 축으로 다시 공격했습니다. 가장 심각한 것은
제가 "고쳤다"고 적은 열거 자체였습니다.

**1. 409 사유 (1)은 어떤 요청으로도 도달할 수 없습니다 (high).** 5라운드가 "여섯 가지"로
넓힌 그 열거의 첫 항목 — "상한이 있는 리소스가 가득 찼고 비울 수 있는 항목이 없다
(시드 개념 어휘는 eviction 대상이 아니다)" — 은 **구조적으로 죽은 코드**입니다.
`_evict_one_registered_concept`의 `raise`는 상한에 도달한 모든 항목이 시드일 때만
실행되는데, `SEEDED_CONCEPTS`는 5개 고정이고 `MAX_REGISTERED_CONCEPTS`는 500이므로
루프는 항상 caller-added 개념을 찾아냅니다. 측정, 상한을 560회 넘겨 등록:

    status 집계      {200: 560}
    어휘 크기        500 (시드 5개 전부 생존, caller-added 495)
    첫 409           없음

독립 재측정은 더 강했습니다 — 순차 1200회, 24스레드 동시 1500회, 그리고 상한에서 시드
이름을 그대로·공백 패딩·새 개념의 alias로 재등록 시도까지: **cap-full 거부는 한 번도
발생하지 않습니다.** writer census도 시드 항목이 떠날 수 없고 상한을 낮출 수 없음을
보였습니다. 어떤 테스트도 그 `raise`에 닿지 않습니다.

`raise` 자체는 남깁니다 — 두 상수가 교차하면 evictor가 출하된 어휘를 지우는 것을 막는
가드입니다. 하지만 **클라이언트가 볼 수 없는 것을 클라이언트용 열거에 적는 것은
과대 주장**이므로 열거는 다섯 가지가 되었습니다. 열거를 "빠짐없이" 만드는 수리가 그
자리에 일어날 수 없는 항목을 넣은 것입니다.

**1b. 그 테스트는 자리를 보지 않았습니다 (medium).** 각 문구가 **자기 번호 항목** 안에
있는지가 아니라 설명 문자열 **어딘가에** 있는지만 봤습니다. 두 가지 회피가 실증되었고
둘 다 전 스위트 녹색이었습니다:

    (a) 사유를 재배열해 digest 사유가 (6)이 되게 하고 꼬리의
        "(2)에서 형식이 잘못된 digest는 ... 400이다"를 그대로 두면,
        공표된 교차참조가 node-kind 충돌을 가리킵니다 (GET /openapi.json이 서빙).
    (b) 사유 (4)를 alias 충돌로 바꾸고 사유 (3)을 "dataset id"를 담도록 고쳐 쓰면,
        문서화된 사유가 사라지는데 문구 센서스는 통과합니다.

문구 k를 마커 k에 묶는 것이 아무것도 없었습니다 — **자기 목록과 비교하는 목록**과 같은
모양입니다. 지금은 `(n)` 마커로 항목을 쪼개 문구 k가 항목 k 안에 있는지 단언하고,
꼬리의 교차참조가 digest 사유의 번호를 가리키는지도 함께 단언합니다. 역검증: 두 회피
모두 이제 어느 사유가 틀렸는지 이름으로 말하며 실패합니다.

**2. 그 테스트의 낡음 방지 주장이 거짓이었습니다 (medium).** 5라운드 docstring은 "코드에
일곱 번째 409가 생기고 문서에 안 적히면 테스트가 빠진 것을 이름으로 말한다"고 적었지만,
테스트는 문서를 **이 파일의 `_409_CAUSES`와** 비교합니다 — 코드와 비교하지 않습니다.
양쪽이 다섯에서 일치하면 녹색입니다.

**철회하면서 반대쪽으로 넓히지 않도록 경계를 측정했습니다.** 검증 에이전트가 "스위트가
새 409에 완전히 눈이 멀었다"는 서술은 과하다고 지적했고, 맞았습니다 —
`tests/test_api_error_contract.py`가 `api.py`를 AST로 전이 파싱해 라우트별 raiseable
status를 `ROUTE_REFUSALS`와 양방향 대조합니다. 양쪽을 직접 측정했습니다:

    409을 선언하지 않는 GET /audit/events에 도달 가능한 409 추가
      -> test_every_refusal_the_code_can_raise_is_published 실패:
         "these routes can refuse with statuses the OpenAPI document does not
          mention: {('GET', '/audit/events'): [409]}"

    이미 409을 선언한 PATCH /catalog/datasets/{id}에 여섯 번째 409 **사유** 추가
      -> 대상 실행 exit 0, 스위트에서 아무것도 알아채지 못함

즉 **라우트가 답할 수 있는 status는 지켜지고, 열거의 내용은 지켜지지 않습니다.** 그리고
새 409 사유를 낼 수 있는 라우트는 전부 이미 409을 선언하고 있으므로(카탈로그 mutation 네
개, graph·ontology write), 실무적으로 새 사유가 정확히 그 사각지대입니다. 과소 주장도
과대 주장과 같은 결함이므로 양쪽 측정을 함께 적어 둡니다.

**3. 그래프 스토어 제외 철회가 다섯 곳을 놓쳤고, 재발 가드가 통과했습니다 (high).**
5라운드가 네 곳을 고치고 세 가지 문구를 금지했는데, **다섯 개 파일이 네 번째 문구**를
쓰고 있었습니다(`test_catalog_mirror_kind_conflict.py`·`test_concept_graph_scope.py`·
`test_graph_hierarchy_class_separation.py`·`test_graph_hierarchy_consistency.py`·
`test_graph_mirroring.py`) — 그중 하나는 같은 파일 안에서 철회문 70줄 아래입니다.
다섯 곳을 모두 현재 상태로 고치고 네 번째 문구를 금지 목록에 넣었습니다.

**그리고 가드의 한계 둘을 적어 두었습니다** — 닫았다고 주장하지 않습니다. (a) 문구
목록은 그 계열이 아닙니다. 아는 문구의 재발만 잡으며, 이것은 **409 열거의 결함이 옷을
바꿔 입은 것**입니다(자기 목록과 비교하는 목록). (b) skip 조건이 구멍입니다 —
`_graph_restore`를 이름만 바꾸면 복원은 그대로 동작하는데 가드는 "주장이 다시 참"이라는
이유로 skip하고 보호 대상 전부가 다시 공표 가능해집니다.

**4. baseline 가드가 노드만 단언했고, 복원의 근거는 간선이었습니다 (medium).**
`_GRAPH_COLLECTIONS`에서 `_edges`만 빼고 측정:

    누출 노드 0건   누출 간선 233건   전체 스위트 1265 passed, 15 skipped

즉 이 테스트가 지키려고 만든 쪽을 **전 테스트 녹색인 채로** 제거할 수 있었습니다 —
보지 않는 절반에 대해 성공을 보고하는 가드입니다. 간선 집합도 같은 방식으로
**파생**해 단언합니다(일회용 스토어에 `seed_store`를 돌려 읽습니다. 설치하지 않으므로
싱글턴을 건드리지 않습니다 — 이전 라운드가 정반대 방향으로 틀렸던 그 구분입니다).

**5. 누출 내역이 네 번째 kind를 빠뜨려 합이 맞지 않았습니다 (low).** 전체 스위트
누출을 277건이라고 적고 내역은 dataset·column·concept 세 kind만 열거했는데, 그 셋의 합은
275입니다 — `service` 2건(`authz-node`·`svc-A`)이 빠졌습니다. 합이 맞지 않는 내역은
맞지 않는 개수와 같은 결함입니다.

**그리고 같은 수치가 세 곳에 있었는데 두 곳만 고쳤습니다** — 이 사이클에서 네 번째로
같은 모양입니다(N곳에 공표하고 N보다 적게 고치기). 세 번째 곳(이 문서의 5라운드 절)은
리뷰어가 "세 곳"이라고 적은 것을 세어 보고 나서야 찾았습니다. 그래서 숫자 하나가 아니라
**산술 자체**를 기계화했습니다: 공표된 텍스트에서 "N nodes (a kind, b kind, …)" 형태를
찾아 괄호 안의 합이 N과 같은지 단언합니다. 측정이 필요 없으므로 세 곳을 동시에 잡으며,
빠진 kind를 이름으로 말할 수는 없지만 합이 틀렸다는 것은 말합니다.

**6. 응답 스키마를 공표하지 않는 남은 사유가 20개 중 11개에 거짓이었습니다 (medium).**
5라운드가 그래프 누출 사유를 철회하면서 "mutation을 구동해야 하므로"를 유일한 사유로
남겼는데, `/browse/query`·`/graph/query`·`/ontology/resolve`·`/search/semantic`·
`/policy/decision`·`/llm/*`·`/enterprise/auth/*` 등 **열한 개는 본문을 받는 읽기이고 아무
것도 쓰지 않습니다.** 진짜 사유는 도구 경계입니다 — 생성기가 **GET만 실행합니다**
(`tests/test_api_response_contract.py`의 docstring이 그렇게 적고 있습니다). 원칙처럼
들리는 사유를 지어내 놓은 셈이어서, 실제 사유로 바꿨습니다.

역검증 4건: `_edges`를 빼면 간선 가드가 누출된 간선을 이름으로 말하며 실패하고(이전에는
녹색) · 네 번째 문구를 다시 공표하면 넓힌 가드가 그 파일을 이름으로 말하며 실패하고 ·
일어날 수 없는 사유를 문서에만 다시 넣으면 마커 연속성 단언이 실패하고 · 개수 단어만
"네 가지"로 바꾸면 파생된 개수와 불일치로 실패합니다.

### Fixed — 카탈로그 mutation이 증빙 없이 커밋될 수 있었습니다 (high)

적대적 리뷰가 **이 제품의 중심 주장 자체에 대한 위반**을 찾았습니다. 네 개의 카탈로그
mutation은 모두 같은 세 줄을 같은 순서로 실행합니다 — `_DATA[id] = updated` ·
schema 스냅샷 · **마지막에** 감사 행. 그 감사 행은 설정된 evidence store를 통해
쓰이고, 그 store는 문서화된 두 배포 모두에서 실제 외부 의존성입니다
(Docker 데모의 `SDP_SQLITE_PATH`, paid-pilot 프로파일의 `SDP_DATABASE_URL`).
그 쓰기가 실패하면 — 테이블 드롭, 디스크 가득, Postgres 도달 불가 — **mutation은 이미
커밋되어 있었습니다.** `record_decision`은 정상이고 `append_event`만 raise하는 store로 측정:

    PATCH /catalog/datasets/crm-customer-master {"description": ...}
      -> 400 {"error": "invalid_request", "reason": "request body is not valid"}
         description 변경됨:   True
         그 변경의 감사 행:     0건

    POST /catalog/datasets            -> 500, 카탈로그 행 생성됨
    POST .../publish, .../deprecate   -> 500, status 변경됨

네 건 모두 **승인되었다는 증빙 없이 착륙한 governed write**입니다 — 이 저장소가
`CLAUDE.md`에 "카탈로그 mutation과 browse/query 경로에 정책 평가와 evidence 기록을
생략하는 변경은 회귀다"라고 적은 바로 그 회귀입니다. 그리고 patch 라우트는 추가로
**서버측 저장 실패를 400 "request body is not valid"로 보고**했습니다 — 호출자의 본문에는
아무 문제가 없는데 본문이 잘못됐다고 말한 것입니다.

**두 가지를 고쳤습니다.**

**1. 증빙을 기록할 수 없으면 write를 되돌립니다.** `_commit_dataset_with_evidence` 하나가
저장·스냅샷·감사를 수행하고, 감사 쓰기가 raise하면 이전 dataset을 복원하거나(등록이라면
키를 삭제하고) 이 mutation이 추가한 schema 스냅샷을 되돌린 뒤 store의 예외를 다시
던집니다. 네 writer 전부 이 함수를 통과합니다. mutation 이전에 기록된 **정책 결정은 일부러
남깁니다** — 권한은 실제로 평가되고 허용되었고, 감사 행도 mutation도 없는 상태에서 원장이
그렇게 말하는 것이 실패한 write의 정직한 기록입니다.

이것은 트랜잭션이 아닙니다. 한 Postgres store를 보는 서로 다른 프로세스의 두 writer에는
여전히 직렬화 지점이 없고, store가 커밋한 **뒤** 이 함수가 반환하기 전에 실패하면 행은
쓰이고 mutation은 되돌아갑니다. 제거한 것은 배포된 구성이 실제로 만들어내는 단일 프로세스
경우입니다. 이 경계를 코드와 테스트에 적어 둡니다.

**2. patch 라우트의 400 arm을 `ValueError`로 좁혔습니다.** 네 mutation 중 **이 하나만**
`except Exception` 포괄 arm을 가지고 있었고, 그래서 이 하나만 서버 실패를 클라이언트
오류로 보고했습니다(`publish`는 이미 `ValueError`, `create`·`deprecate`는 400 arm 자체가
없어 500으로 올라갑니다). `ValueError`는 "이 본문이 검증을 통과하지 못했다"의 정확한
계열이고(`pydantic.ValidationError`가 그것이며, `NodeKindConflict`는 위에서 잡히므로
좁히기가 conflict를 흘려보내지 않습니다), store 실패(`RuntimeError`·`sqlite3.Error`·
`psycopg.Error`·`OSError`)는 어느 것도 아니므로 이제 나머지 셋과 같이 5xx로 올라갑니다.

**드리프트 가드도 넣었습니다.** 다섯 번째 writer가 `_DATA`를 직접 대입하면 테스트가
실패합니다 — 이 영역의 이전 수리들이 전부 "넷 중 둘"만 덮었던 모양이기 때문입니다
(kind 충돌 가드, IPv6 authority). 가드가 묻는 질문은 "`_record_audit_event`를 호출하는가"가
아니라 "`_DATA`를 직접 대입하는가"입니다 — 전자로 쓴 첫 버전은 patch의 **no-op 분기**에서
실패했습니다. 패치할 필드를 하나도 지정하지 않은 요청은 no-op을 원장에 기록하고 dataset을
**건드리지 않고** 반환하며, 버전 범프와 스냅샷을 의도적으로 건너뜁니다. mutation 없는 감사
행에는 되돌릴 것이 없습니다.

역검증 2건: 네 writer 중 patch 하나만 원래의 세 줄로 되돌리면 동작 테스트와 드리프트 가드가
함께 실패하고(`'감사실패변경' == '고객의 상태와...'`), 포괄 arm을 되돌리면 상태 단언이
`(400, '{"detail":{"error":"invalid_request"...}}')`로 실패합니다.

### Fixed — alert routing 설계 조사가 기존 코드에서 찾아낸 결함 셋 (medium)

다음 개발 항목(`SDP_ALERT_WEBHOOK_URL` 라우팅 + connector-probe 규칙)을 설계하려고 읽기 전용
조사를 돌렸고, **기능을 만들기 전에 기존 코드의 결함 세 건**이 나왔습니다. 둘은 제가 앞선
라운드에서 넣은 것입니다.

**1. IPv6 sink 주소의 대괄호가 사라집니다 (medium).** `urlparse().hostname`은 IPv6 리터럴의
RFC 3986 대괄호를 벗기고, `_http_sink_request_parts`와 `_redacted_sink_target`은 둘 다
`f"{host}:{port}"`로 authority를 **보간해서** 다시 만들었습니다. IPv6 주소에서는 주소 안의
콜론과 포트 구분자가 구별되지 않습니다. 측정:

    SDP_LOG_SINK_URL=http://[::1]:8000/x
      재조립된 URL        http://::1:8000/x
      urlopen            URLError: [Errno 97] Address family not supported
      _sink_status()     {"configured": true, "target": "::1:8000"}

    SDP_LOG_SINK_URL=http://[2001:db8::1]:9000/push
      재조립된 URL        http://2001:db8::1:9000/push
      _sink_status()     {"configured": true, "target": "2001:db8::1:9000"}

즉 **모든 export가 실패하는 동안 manifest는 sink가 설정되어 있다고 보고하고**, 공표되는
`target`은 authority도 아닙니다 — `_http_sink_request_parts`의 docstring이 userinfo 형태에
대해 기록하고 제거한 바로 그 결함 쌍이, IPv6 형태로 살아 있었습니다. 그 수리가 authority를
한 함수에 맡기지 않고 보간으로 다시 만들었기 때문입니다. 지금은 `_authority(host, port)`
하나가 양쪽에 쓰이고, 호스트에 콜론이 있으면 대괄호를 씌웁니다. 세 번째 복사가 생기면
AST 가드가 실패합니다 — grep이 아니라 파싱인 이유는 `_authority`의 docstring이 자신이
대체한 보간을 **인용**하고 있어서, 문자열 검색으로 쓴 첫 버전이 그 설명 문구에 걸렸기
때문입니다.

**2. `/metrics`가 내보내는 gauge 개수를 두 곳이 틀리게 공표했습니다 (low).**
`requirements.py`와 거기서 **생성되는** `docs/requirements-coverage.md`가 "`/metrics` exports
seven gauges"라고 적었는데, 실제로는 여덟입니다 — `sdp_governed_requests_without_evidence_total`을
추가한 커밋(`e475384`, 제 것)이 그 문장을 다시 보지 않았습니다. 고친 방식이 중요합니다:
**숫자를 여덟으로 바꾸지 않았습니다.** 그러면 아홉 번째 gauge를 위해 같은 함정을 다시
장전하는 것이고, 이 사이클에서 409 개수 단어로 똑같이 당했습니다. 문장이 개수를 말하지
않게 바꾸고(요구사항의 논점은 "gauge만 있고 request-outcome counter가 없다"였으므로 개수는
애초에 주장이 아니었습니다), 어느 공표 문서든 gauge 개수를 적으면 실패하는 테스트를
넣었습니다 — **맞는 개수를 적어도 실패합니다.**

**3. 금지된 문장 하나가 줄바꿈으로 가드를 통과해 `main`에 살아 있었습니다 (medium).**
4라운드가 "alert 조건을 평가하는 코드가 없다"는 낡은 주장을 기계적으로 금지했는데, 그
가드는 **정확한 부분문자열**로 비교했고 `docs/implementation-compliance.md`에는 그 문장이
약 90열에서 줄바꿈된 사본이 있었습니다. 측정:

    phrase "alert 조건을 평가하는 코드도 없"
      exact match:      없음
      normalised match: docs/implementation-compliance.md

즉 **가드가 녹색인 채로 낡은 주장이 공표되고 있었습니다.** 문서를 고치고, 가드를 공백
정규화로 올렸습니다. 같은 사이클에 제가 추가한 그래프 스토어 가드는 처음부터 정규화되어
있었으므로, 둘 중 약한 쪽을 같은 기준으로 끌어올린 것입니다.

역검증 3건: IPv6 수리를 URL 쪽에만 되돌리면(한쪽만 고치는 실패 모양) 왕복 테스트와 AST
가드가 함께 실패하고 · 금지 문장을 줄바꿈된 원래 형태로 되돌리면 정규화된 가드가 그 파일을
이름으로 말하며 실패하고 · gauge 개수를 **맞게**("eight") 적어 넣어도 개수 가드가 실패합니다.

### Fixed — 5라운드: 4라운드가 남긴 결함 (high)

직전 커밋(`3fe213c`)을 다시 공격해 다섯 건을 찾았습니다. **그중 둘은 4라운드가 "고쳤다"고
적은 바로 그 항목이 덜 고쳐진 것이고, 하나는 4라운드가 추가한 테스트가 거짓 증거였습니다.**

**1. 409 열거가 아직 두 사유를 빼먹었고, 새 테스트가 틀린 개수를 고정했습니다 (high).**
3라운드가 "세 가지 → 네 가지"로 고쳤고 4라운드가 그 수리를 테스트로 묶었는데, 코드는
그때 이미 **여섯 가지** 409를 던지고 있었습니다 — 계층 거부 둘(`ONT-002` class 경계,
`ONT-007` 포섭 순환)이 처음부터 빠져 있었고, 두 라운드 모두 못 봤습니다. 그리고 새
테스트가 `assert "네 가지" in description`으로 **틀린 개수를 고정**했으므로, 빠진 둘을
채우려면 테스트부터 실패합니다.

    api.py의 status_code=409 지점: 1222 1274 1350 1406 1550 1899 2180 2213 2271 2304
    GraphIntegrityConflict 하위: NodeKindConflict ·
        HierarchyClassSeparationConflict(ONT-002) · HierarchyCycleConflict(ONT-007)
    문서가 열거한 사유: 4

개수 단어를 고정하는 것이 낡는 방식 자체입니다 — 단어와 목록이 **고칠 곳 두 개**이고
직전 라운드는 한쪽만 고쳤습니다. 지금 테스트는 개수를 적지 않습니다: `(n)` 마커를 읽어
개수를 **파생**하고, 여는 단어가 그것과 일치하는지 보고, 사유 여섯 개를 각각 문구
조각으로 호명합니다. 일곱 번째 409가 코드에 생기고 문서에 안 적히면 테스트가 빠진
것을 이름으로 말합니다. README 행도 여섯으로 맞췄습니다.

**2. "정리" 한 줄이 아무 일도 하지 않았고, 그래프 스토어 누출은 네 곳에 공표된
사실이 틀어진 문제였습니다 (high).** 4라운드가 추가한 소유권 테스트 하나는
`seed_store(InMemoryGraphStore())`로 끝났는데, `seed_store`는 **넘겨받은 스토어를 시드할
뿐 설치하지 않습니다**(설치는 `graph_store.set_store`). 일회용 스토어를 만들어 버리는
줄이 정리인 척 서 있었습니다.

누출 자체를 측정했습니다(26노드 시드 baseline 기준, 복원 비활성 상태):

    tests/test_catalog_mirror_kind_conflict.py 단독
        노드 31건 누출 (dataset 18 · column 8 · concept 5), 간선 26건
    전체 스위트
        노드 277건 누출 (dataset 121 · column 129 · concept 25 · service 2), 간선 233건

**복원을 넣으면 0건·0건입니다.** 기존 테스트 중 어느 것도 이 누출로 실패하지 않았으므로
(복원 비활성에서 정순·역순·seed 11, 활성에서 다섯 순서 전부) 잠재 결함이지 활성 결함은
아닙니다. 그대로 두지 않은 이유는 잠재성의 **모양**입니다: 이번 사이클이 "노드의 기존
kind"에 걸리는 거부를 추가했으므로, 데이터셋 shape의 id에 남은 `concept` 노드는 이제
나중 테스트의 200을 409로 만들고, 남은 `dataset` 노드는 나중 `POST /ontology/concepts`를
같은 식으로 만듭니다 — 누출이 실패로 바뀌는 경로가 kind 규칙과 함께 늘어났습니다.

제외의 근거는 "snapshot API가 없고 테스트용으로 제품 API를 만들 수 없다"였습니다. 제품
API에는 맞지만 fixture는 이미 `catalog._DATA`에 손을 넣고 있고 스토어의 backend
collection은 같은 종류의 모듈 레벨 상태이므로, 복사를 fixture 안에 두었습니다.
`PostgresGraphStore`에는 그 collection이 없고 그 백엔드로 도는 테스트도 없으므로
snapshot은 추측하지 않고 건너뜁니다.

**그리고 이것이 이 사이클에서 세 번째로 같은 모양의 결함입니다** — 사실 하나가 N곳에
공표되어 있고 한 곳만 고치는 것. 제외는 네 곳에 적혀 있었습니다: fixture docstring,
`CLAUDE.md` 컨벤션, **제품 코드**(`api_response_contract.py` — 비-GET 20개 operation의
응답 스키마를 공표하지 않는 두 사유 중 하나), 그리고 자기 정리의 근거로 그것을 인용한
테스트 주석 둘. fixture만 고치면 제품 코드와 에이전트용 컨벤션 파일이 이미 없는 제약을
우회하라고 다음 독자에게 말합니다. 네 곳 모두 고치고, alert 문장과 같은 기계적 재발
가드를 붙였습니다(README·`CLAUDE.md`·`docs/**.md`·`src/**.py`·`tests/**.py`). 가드 자체가
자기 정의에 걸렸으므로 금지 문구는 조각으로 조립해 둡니다 — 4라운드의 README 가드가
인용을 잡았을 때와 같은 함정, 반대 방향입니다.

**3. AST 가드가 대소문자를 구별해 우회 가능했습니다 (medium).** 3라운드가 "문자열
리터럴 자체 금지"로 넓혔지만 `"X-SDP-Evidence-Ids"`를 **정확히** 비교했습니다. HTTP
헤더 이름은 대소문자 무관이고 Starlette `Headers.get`도, 이 저장소의 `_header_value`도
소문자로 내려 훑으므로, `request.headers.get("x-sdp-evidence-ids")`는 **작동하는 읽기**인데
가드는 녹색입니다. 지금은 양쪽을 소문자로 비교합니다.

**4. 테스트 double이 호출되지 않는 메서드를 정의했습니다 (medium).** 증빙 id를 "스토어
쓰기 **뒤에**" 기록하는 수리는 chokepoint 두 곳(`record_policy_decision`,
`append_audit_event`) 각각의 성질인데, `_RefusingStore`는 `append_event`를 정의하고
아무도 호출하지 않았습니다 — audit 쪽은 묶여 있지 않았습니다. 측정: `append_audit_event`의
`note_request_evidence_id`를 쓰기 위로 되돌리고 테스트를 직전 형태로 두면 **21건 전부
녹색**입니다. 두 번째 arm을 넣었고, 같은 변이가 이제 실패합니다.

**5. 테스트 docstring이 그 테스트가 닿지 못하는 절을 주장했습니다 (low).**
`..._that_did_record_evidence_is_not_counted`는 gap 조건의 "증빙을 하나도 남기지 않음"
절에 대한 테스트인 것처럼 적혀 있었지만, 404는 **2xx 가드에서 먼저** 걸러지므로 그 절을
지워도 녹색입니다. 측정: `not collected.ids`를 미들웨어에서 제거하면
`test_the_gap_condition_is_zero_on_ordinary_governed_traffic`과
`test_no_governed_get_route_reports_a_gap_on_seed_data`가 실패하고 이 테스트는 통과합니다.
이름과 docstring을 실제로 증명하는 것(거부도 상관 키를 공표한다)으로 바꾸고, 그 절을
묶는 테스트 둘을 docstring에서 이름으로 가리킵니다.

역검증 6건, 각각 되돌려 실패를 확인했습니다: 개수 단어를 다섯으로 바꾸면 불일치로 실패 ·
사유 (6)을 개수까지 맞춰 지우면 `포섭 순환`을 이름으로 말하며 실패 · audit chokepoint의
기록을 쓰기 위로 올리면 새 arm이 실패(직전 테스트 형태에서는 21건 녹색) ·
`not collected.ids`를 지우면 2xx 테스트 둘만 실패 · 제외 문구를 제품 코드에 줄바꿈된
형태로 다시 넣으면 재발 가드가 그 파일을 이름으로 말하며 실패 · fixture에서
`_graph_restore`를 지우면 baseline 가드가 실패.

**같은 커밋을 다시 읽고 세 건을 더 고쳤습니다.** 리뷰 라운드를 띄우지 않고 직접
확인했습니다 — 이 세션의 지침이 에이전트/워크플로를 요청 없이 쓰지 말라고 하므로.

**a. 열거의 exhaustive 주장이 경쟁 조건에서는 성립하지 않습니다 (medium).** 열 개
409 지점을 하나씩 분류하다 보니, `ontology.register_concept`를 감싼
`except ValueError`가 어휘 상한(1)뿐 아니라 그 함수가 **락 안에서 다시 확인하는**
별칭 충돌에도 409를 답합니다. 평범한 경로에서는 그 충돌이 락 위에서 걸려 400입니다:

    POST /ontology/concepts {"concept": "새로운개념하나", "aliases": ["customer"]}
      -> 400 "alias conflict: 'customer' already belongs to '고객'"

따라서 한 별칭을 두 writer가 동시에 집을 때만 거부로 올라오고, 그때는 같은 사유가 두
status를 갖습니다. 열거에 **넣지 않고** 테스트에 경계로 적었습니다 — 400으로 문서화된
사유에 race 전용 status를 공표하면 누락보다 더 오해를 만듭니다. status가 갈리는 것 자체는
문서 문제가 아니라 코드 문제이므로 그대로 둡니다.

**b. `deepcopy`가 load-bearing인데 주석이 그 이유를 적지 않았습니다 (medium).**
`upsert_edge`는 같은 간선이 이미 있으면 교체하지 않고 `existing.properties.update(...)`로
**담긴 객체를 제자리에서** 고칩니다. 그래서 한 단계 복사는 복원이 되지 않습니다:

    one-level 스냅샷 후 upsert_edge(properties={"leaked_marker": ...}) 후 복원
      -> leaked_marker 남아 있음: True
    deepcopy 스냅샷으로 같은 절차
      -> leaked_marker 남아 있음: False

측정한 비용도 같이 적었습니다(시드 baseline 26노드·78간선·dimension 128, 200회 왕복):
deepcopy 4.53 ms/test(스위트 약 5.8초, 약 6%) vs 한 단계 0.005 ms/test. 6%를 내고
"담긴 객체의 변경에 뚫리지 않는" 스냅샷을 삽니다.

**c. baseline 단언의 메시지가 kind 불일치를 말하지 못했습니다 (low).**
`sorted(set(nodes) ^ set(expected))`는 id는 같고 **kind만 다른** 경우에 빈 집합입니다 —
그런데 그것이 이번 사이클의 규칙들이 거부하려는 바로 그 "재분류된 노드"입니다. 메시지를
`unexpected`/`missing`/`wrong_kind` 세 갈래로 바꿨습니다. 역검증: 시드 노드 하나를
`kind="concept"`로 복원시키면 `{'wrong_kind': {'crm-customer-master': ('concept', 'dataset')}}`로
실패합니다.

### Fixed — 4라운드: 직전 수리가 만든 결함 (high)

직전 커밋(`36a9407`)의 아홉 개 수리를 다시 공격했습니다. 리뷰어는 각자 자기 git worktree
에서 작업했습니다 — 3라운드에서 에이전트들이 공유 트리를 동시에 수정하는 레이스가 있었기
때문입니다. **직전 수리 중 둘이 결함이었고, 하나는 고치려던 노출을 다시 열었습니다.**

**1. 소유권 추론이 세 번째로 틀렸고, 이번에는 누출입니다 (high).** 3라운드에서 추가한
세 번째 조건("다른 `has_column` 간선이 이 노드를 가리키지 않음")은 **누가 썼는지가 아니라
누가 관심있는지**를 묻습니다. 인증된 `POST /graph/edges` 한 번으로 컬럼 노드를 영구히
고정할 수 있습니다.

    데이터셋 leakowner가 pii: true 컬럼 customer_email 선언
    POST /graph/edges  has_column  leakother -> leakowner:customer_email
    PATCH /catalog/datasets/leakowner  (컬럼 내림)        -> 200
      -> 노드 생존(leakother의 간선이 남아 있어서)
    PATCH /catalog/datasets/leakother {"title": ...}       -> 200
      -> 그 간선도 사라지지만 leakother 쪽에서는 모양 검사에 탈락
    최종: pii: true · 간선 0개 · 어떤 카탈로그 행도 선언하지 않는 고아 column 노드.
          `/search/semantic`과 `/graph/query`가 계속 서빙한다.

선언된 컬럼은 정책 게이트가 걸린 `/browse`가 마스킹하지만 고아 노드는 아무것도 지배하지
않습니다 — reconciliation이 존재하는 이유가 정확히 그 노출이고, 그것을 다시 열었습니다.

**2. 같은 규칙이 남의 노드를 여전히 파괴했습니다 (medium).** `POST /graph/nodes`는 간선을
만들지 않으므로, 다른 writer가 `kind: "column"`으로 쓴 노드가 이 데이터셋 접두사 아래
있으면 세 조건을 모두 통과하고 title만 바꾸는 patch에 삭제됩니다(닿는 간선까지).
`POST /graph/nodes`의 계약은 다른 writer가 노드의 거버닝 속성을 파괴하지 않는다는 것입니다.

**그래서 소유권을 추론하지 않고 기록합니다.** 모양 → 모양+kind → 모양+kind+간선, 세 번의
추론이 모두 한쪽으로 틀렸습니다. 지금은 `seed_dataset`이 쓰는 모든 컬럼 노드에 그 미러의
데이터셋 id를 `mirrored_from`으로 찍고, reconciliation은 **자기 도장이 찍힌 노드만**
수거합니다. 여섯 경우 전부 재측정했습니다: concept 생존 · 다른 데이터셋의 자기 노드 생존 ·
다른 데이터셋이 소유한 컬럼 노드 생존 · 고정된 pii 노드 수거(누출 해소) · 남의
`POST /graph/nodes` 노드 생존 · 자기 고아 컬럼은 여전히 수거. 선언된 경계 둘: 도장 이전에
쓰인 노드(영속 Postgres 그래프)는 다시 미러될 때까지 건드리지 않고(파괴가 아니라 보존
방향), 자기 노드에 남의 id를 일부러 찍는 writer는 그 미러의 산출물로 취급되기를 요청한
것입니다.

**3. 직전의 문서 수리가 한 단계 아래에서 같은 결함을 반복했습니다 (high).**
readiness 문서는 "규칙 자체가 `not_covered`로 공표한다"고 적는데, 3라운드가 그 괄호 안에
두 번째 사각지대("decision은 있고 audit 행만 없는 경우")를 **문서에만** 추가하고 필드는
넓히지 않았습니다. 미인증 조달 표면(`GET /enterprise/observability`)에서 규칙의 사각지대를
열거하는 감사자는 둘 중 하나만 보고 나머지는 덮인다고 결론 내립니다 — 그리고 빠진 쪽이
측정상 **정상 상태**입니다(호출 가능한 governed GET 18건 중 16건). 필드를 넓혔고,
테스트가 두 사각지대가 모두 공표되는지 단언합니다.

**4. README가 여전히 "alert 조건을 평가하는 코드가 없다"고 공표했습니다 (high).**
3라운드가 `observability.py`의 주석을, 4라운드가 `production.py`의 주석을, 그리고 README를
각각 한 라운드 뒤에 찾았습니다 — 같은 문장이 세 곳에 있었고 README는 이 저장소의 1차 공표
문서입니다. README를 믿은 운영자는 이 서비스가 실제로 계산하는 **단 하나의** 규칙에
모니터링을 붙이지 않게 됩니다(계산을 추가한 이유의 정반대). 세 번 재발했으므로
`tests/test_honest_metrics.py`가 그 문장을 README·`docs/**.md`·`src/**.py` 전체에서
기계적으로 금지합니다 — 평가에 대한 주장만 금지하고 "전달되지 않는다"는 참인 주장은
그대로 둡니다. (이 가드는 추가 직후 제 README 정정문이 그 문장을 **인용**하는 것을 잡아냈고,
가드를 약화시키는 대신 인용을 풀었습니다.)

역검증: 추론으로 되돌리면 누출 테스트와 남의 노드 테스트가 실패하고, 미러가 도장을 멈추면
4건이 실패하며, `not_covered`를 좁히면 사각지대 테스트가, README 문장을 되돌리면 재발
가드가 실패합니다.

### Fixed — 3라운드 적대적 검증: 직전 세 커밋에서 찾은 결함 (high)

직전 세 커밋(`70d19fa`, `4c8a9b9`, `e475384`)을 5개 축으로 다시 공격했습니다. 각 결함은
코드를 실행해 재현했고, 독립적으로 재측정한 뒤 고쳤습니다. **세 축이 같은 결함 하나로
수렴했고, 그것이 제일 심각했습니다.**

**1. governed 경계 파생이 HTTP method를 버렸습니다 (high).** 거부 계약은 `(method, path)`로
키가 잡히는데 `policy_gated_route_paths()`는 path만 모으고, 미들웨어도 path만 비교했습니다.
`POST /ontology/concepts`가 403을 선언하므로 path `/ontology/concepts`가 governed 집합에
들어가고, **열려 있는** `GET /ontology/concepts`까지 함께 끌려들어갔습니다 — actor도 없고
정책 평가도 없고 아무것도 기록하지 않는, 코드가 스스로 "open"이라고 적어 둔 어휘 읽기입니다.

    GET /ontology/concepts  (미인증, 1회)        -> 200
      policy_audit_gap: firing: true, observed_total: 1,
                        routes: {'/ontology/concepts': 1}   severity: critical

바로 앞 항목이 공표한 "측정값 0 · 상시 경고가 아니라 회귀 탐지기"가 **첫 평범한 요청에
깨집니다.** 그 측정은 403을 선언한 GET 템플릿만 재어 method를 고려했고 판정은 하지
않았으니, 둘이 서로 다른 "governed"를 쓰고 있었습니다 — 그리고 맞아 보이는 쪽이
측정이었습니다. 지금은 `policy_gated_route_methods()`가 `(method, path)` 쌍을 돌려주고
미들웨어가 `(request.method, route_template)`로 비교합니다. 재측정: governed 쌍 39건
(GET 22 · POST 16 · PATCH 1), 전부 앱이 실제로 서빙, 열린 method가 governed path에 얹혀
있던 경우는 `GET /ontology/concepts` 1건이고 정확히 그것만 빠집니다. 집계 키도
`"GET /catalog/datasets"` 형태로 method를 담습니다.

**2. schema를 선언하지 않는 patch가 저장된 컬럼을 검사하지 않았습니다 (high).**
직전 커밋에서 "무조건 검사"로 고쳤다고 적었지만, schema가 없으면 컬럼 목록으로 `[]`를
넘겼습니다. `patch_dataset`은 schema가 없을 때 **저장된 schema를 유지**하고
`seed_dataset`은 그 저장된 컬럼을 미러하므로, 아무도 묻지 않은 컬럼 노드가 쓰입니다.

    저장 컬럼 'c:x'의 노드 id를 개념이 점유한 상태에서
    PATCH /catalog/datasets/own {"title": "제목만 바꿈"}  -> 409
      title 적용됨 · updated_at 이동 · schema-history 스냅샷 추가
      감사 행: ('dataset.patch','success') 다음 ('dataset.patch','denied')  — 한 요청에 둘

장부가 한 요청에 대해 성공과 거부를 동시에 기록합니다. 이 가드가 막으려던 바로 그
결함이 가드를 추가한 라우트에 남아 있었습니다. 지금은 `_columns_the_mirror_will_write`가
"선언된 schema가 있으면 그것, 없으면 저장된 schema"를 돌려주고, 그것을 검사합니다.

**3. reconciliation의 소유권 판정이 모양만 봤습니다 (high).** 직전 커밋의
`_owns_column_node`는 `{dataset_id}:` 접두사만 확인했고, **모양은 소유권이 아닙니다.**

    POST /ontology/concepts {"concept": "g1:개념"} + has_column g1 -> g1:개념
    PATCH /catalog/datasets/g1 {"title": "바꿈"}        -> 200
      -> 개념 노드 삭제, GET /ontology/terms/g1:개념 -> 404

    데이터셋 "f2"와 "f2:child" + has_column f2 -> f2:child
    PATCH /catalog/datasets/f2 {"title": "x"}           -> 200
      -> 데이터셋 f2:child의 **자기 노드**가 삭제되는데
         GET /catalog/datasets/f2:child는 여전히 200 — 카탈로그/그래프 드리프트

지금은 세 가지를 모두 묻습니다: 모양, 노드의 **kind가 `column`**, 그리고 (이 데이터셋의
간선을 지운 뒤) **다른 `has_column` 간선이 더 이상 가리키지 않음**. 세 번째가 필요한
이유는 `부모셋:자식셋`이 소유한 컬럼 노드 `부모셋:자식셋:컬럼`도 `부모셋:`으로 시작하고
kind가 `column`이기 때문입니다 — 소유자의 간선만이 그것을 구별합니다.

**4. 증빙 id를 스토어 쓰기 **전에** 기록했습니다 (low).** 쓰기가 실패하면 로그 행이
원장에 없는 행을 가리키는 상관 키를 공표합니다(`evidence_id_source: server_recorded`를
같이 공표하면서). 쓰기 뒤로 옮겼습니다.

**5. `withheld_evidence_id_count`가 id 수가 아니라 시도 수를 셌습니다 (low).** 상한을
넘긴 id 하나를 다섯 번 기록하면 5를 공표했습니다. 집합으로 바꿨습니다. HTTP 표면으로는
도달 불가(한 요청이 쓰는 원장 행은 최대 2개)라는 점도 테스트가 함께 적습니다.

**6. 409 열거가 세 가지로 남아 있었습니다 (medium).** 직전 커밋이 네 번째 사유(중복
dataset id)를 추가했는데 `REFUSAL_DESCRIPTIONS[409]` — `GET /openapi.json`이 서빙하는
문장 — 은 "세 가지 경우다"로 셋만 열거했습니다. README 행도 "세 가지"라 적고 넷을
나열했습니다. 둘 다 고쳤습니다.

**7. 공표 문구가 구현보다 넓었습니다 (medium).** CHANGELOG·compliance 문서가
`policy_audit_gap`을 "모든 governed 경로에 decision과 audit 행"에 대한 자기검사라고
적었지만, 구현은 **둘 다 없을 때만** 셉니다. 측정: 호출 가능한 governed GET 18건 중
**16건이 decision만 남기고 audit 행은 남기지 않으며**, 그 상태에서 규칙은 정상적으로 0입니다.
"decision은 있고 audit 행은 없음"은 덮지 않는다는 사실을 문서에 적었습니다.

**8. 드리프트 가드의 선언이 실제 범위보다 넓었습니다 (low).** AST 가드가 "호출 인자로
넘기는 것"만 금지했는데, 헤더 이름을 모듈 상수로 올리거나(`_HEADER = "X-SDP-..."`)
mapping으로 읽으면(`headers["X-SDP-..."]`) 가드를 그대로 통과하면서 caller 제어 상관 키가
복구됩니다. 지금은 docstring을 제외한 **문자열 리터럴 자체**를 금지합니다 — 주석은 AST에
없으므로 설명은 그대로 남습니다.

**9. 알림 블록 주석이 "어떤 조건도 계산하지 않는다"고 남아 있었습니다 (low)** — 그것을
계산하는 함수 다섯 줄 위에서. 고쳤습니다.

**테스트 결함도 같이 고쳤습니다.** 탐지기가 발화하는 것을 보이는 **유일한** 테스트가
`api._POLICY_GATED_ROUTES`를 monkeypatch로 **대체**하고 있었습니다 — 정확히 그 값이
틀렸는데도 전 스위트가 녹색이던 이유입니다. 미들웨어가 쓰는 값이 파생 결과와 같은지
단언하는 테스트와, 미인증 `GET /ontology/concepts`가 세어지지 않는지 보는 테스트,
그리고 **governed GET 라우트를 전부 훑어 gap이 0인지 보는** 테스트(손으로 한 번 한
측정을 상시 테스트로)를 넣었습니다. `..._is_not_counted_as_a_gap`은 404를 몰고 있어서
이름이 주장하는 2xx 가드를 검사하지 못했고(가드를 지워도 1241건 전부 녹색), 증빙을
하나도 남기지 않는 400으로 바꿨습니다. 절대 경로 테스트는 자기 docstring이 말하는
경로(사전 검사)를 전혀 거치지 않았으므로 가드의 no-op을 직접 단언합니다. drift 헬퍼
세 곳은 재설정되지 않는 그래프 스토어 싱글턴에 `concept` 노드를 남겨 같은 프로세스의
이후 테스트를 깨뜨릴 수 있었으므로 context manager로 바꿔 치웁니다.

역검증: 9건 각각 되돌리면 자기 테스트만 실패합니다.

### Added — `policy_audit_gap` alert를 선언에서 **평가**로 (medium)

`GET /enterprise/observability`는 alert 규칙 2건을 `evaluated: false`,
`alert_evaluation: declared_not_evaluated`로 게시했습니다. 정직한 선언이지만, 그중
critical 등급인 `policy_audit_gap`은 이 제품의 중심 주장에 대한 **자기검사**입니다 —
모든 governed 경로에 policy decision과 audit 행이 남는다는 주장. 그리고 바로 위 항목
전까지는 평가할 수 없었습니다: `evidence_ids`가 caller 헤더에서 왔으므로 "이 요청이
증빙을 남겼는가"에 서버가 답할 수 있는 값이 없었습니다.

지금은 미들웨어가 셉니다 — policy-gated 라우트가 2xx인데 수집된 증빙 id가 **하나도**
없는 경우. 미들웨어만이 매칭된 라우트 템플릿·상태코드·수집된 증빙을 한 스코프에서
알기 때문입니다.

    GET /enterprise/observability  alerts[policy_audit_gap]
      evaluated: true,  evaluation: "measured_in_process"
      observed_total: 0,  firing: false,  routes: {}
      measurement_window: "this worker, since start"
    GET /metrics
      sdp_governed_requests_without_evidence_total 0

**governed 경계는 공표된 거부 계약에서 파생합니다.** 403을 답할 수 있는 라우트는
`policy.evaluate`를 물은 라우트이므로, `api_error_contract`가 이미 governed 표면을
이름 짓고 있습니다. 같은 것을 두 목록으로 두면 드리프트하므로 두 번째 목록을 만들지
않았습니다 — 새 governed 라우트는 자기 403을 선언하는 것으로 자기검사에 들어옵니다.
반대 방향 드리프트(앱에서 사라진 라우트가 계약에 남는 것)는 테스트가 막습니다.

**측정값 0입니다.** 시드 데이터로 호출 가능한 policy-gated GET 라우트 18건 전부가
2xx에서 증빙 id를 담습니다. 그래서 이 규칙은 상시 경고가 아니라 **회귀 탐지기**입니다 —
정책 평가를 빠뜨린 라우트가 추가되면 `firing: true`가 됩니다.

> **이 측정은 맞았고, 판정이 틀렸습니다.** 바로 아래 항목을 보세요 — 이 18건은 403을
> 선언한 **GET 템플릿**을 센 값(method를 고려한 값)인데, 미들웨어는 path만 비교하고
> 있었으므로 측정과 판정이 서로 다른 "governed"를 썼습니다. 그래서 이 "0"은 참이면서도
> 규칙이 미인증 요청 한 번에 발화하는 것을 막지 못했습니다.

**좁다는 사실을 함께 공표합니다.** 선언된 조건은 "preview/query 수가 decision 또는
audit 수를 초과"인데, 계산하는 것은 그 조건의 요청 단위 형태입니다. 요청 시점에 세므로
사후에 원장에서 제거된 행은 보이지 않습니다 — 규칙이 `declared_condition`과
`not_covered`를 같이 담아서, id가 가지지 않은 커버리지를 암시하지 않게 합니다. 계산한
것의 이름을 쓰는 규칙(`shacl_compatible`, `cycle_count`가 가르친 것)의 세 번째 적용입니다.

**남은 경계.** 전달은 여전히 미구현입니다 — `SDP_ALERT_WEBHOOK_URL`로 POST하는 코드는
없고 변수는 `declared_unimplemented_environment`에 그대로입니다. `central_workflow_backlog`은
GitHub Actions run 상태가 필요하므로 이 서비스가 평가할 수 있는 조건이 아니며,
`not_evaluated_because`로 그 이유를 공표합니다. 최상위 `alert_evaluation`은 두 규칙에
하나의 주장을 하지 않도록 `per_rule`로 바뀌었습니다 — 어느 쪽 문자열을 써도 절반은
거짓이기 때문입니다. acceptance criterion이 이름을 올린 세 번째 조건(connector-probe
실패)은 애초에 규칙으로 게시된 적이 없다는 사실도 criterion 본문에 적었습니다.

라우트별 카운트는 상한(32)이 있고 초과분은 선언된 한 버킷으로 접힙니다(총합은 보존).
새 모듈 레벨 가변 상태이므로 `tests/conftest.py`의 복원 fixture와
`tests/test_module_state_coverage.py`의 분류에 함께 등록했습니다 — 한 테스트가 일부러
만든 gap이 다른 테스트의 측정값이 되지 않도록.

역검증: 카운트 호출을 지우면 firing 테스트가 실패하고, governed 집합에 `/health`를
끼우면 "governed 밖은 세지 않는다" 테스트가 실패하며, 상한을 지우면 경계 테스트가,
거부 계약 파생을 끊으면 파생 테스트가 실패합니다.

### Fixed — 요청 로그의 증빙 상관 키를 caller가 정하고 있었습니다 (high)

`GET /enterprise/observability`는 `structured_logs.fields`에 `evidence_ids`를 공표하고,
readiness manifest의 `request_observability_export` acceptance criterion은 "request id,
tenant, actor, route, status, latency, **and evidence ids** without request bodies"라고
적혀 있으며 그 integration은 `implemented`입니다. 그런데 이 필드는 **caller가 보낸 요청
헤더** `X-SDP-Evidence-Ids`에서 읽혔습니다. 인증된 governed read 1회 측정:

    POST /browse/crm-customer-master/preview
      headers: X-SDP-Evidence-Ids: 00000000-dead-beef-0000-000000000000,
                                   another-forged-id
      -> 200
         서버가 실제 기록한 decision:  4ff4d6c7-52a3-4f51-a1e2-cb585180a27d
         export된 행의 evidence_ids:   ['00000000-dead-beef-...', 'another-forged-id']
         로그가 실제 decision을 담았나: False

로그 행을 증빙 원장(`/policy/decisions`, `/audit/events`)에 연결하는 **그 키**를 행의
주체인 caller가 고를 수 있었습니다. 감사자는 자기가 서버 기록이라고 믿는 값을 읽지만
실제로는 caller 주장값이고, caller는 남의 요청 증빙을 가리키거나 아무것도 보내지 않아
"증빙 없음"으로 보이게 할 수 있었습니다. 어떤 라우트도 이 헤더를 설정하지 않으므로
**평상시 모든 governed 요청의 값은 빈 리스트**였습니다 — correlation을 주장하는 필드
이름 아래에서.

이것은 `tenant_id`가 이미 주석으로 인정한 결함과 같은 종류입니다("self-asserted by the
very caller whose rows would be filtered"). 차이는 `tenant_id`는 주장값으로 **선언**되고
미인증 manifest에서 집계만 공개되는 반면, `evidence_ids`는 correlation 키로 공표됐다는
점입니다.

지금은 모든 증빙 행이 반드시 지나는 두 지점 — `evidence.record_policy_decision`과
`evidence.append_audit_event` — 에서 요청 단위로 수집하고(`collect_request_evidence_ids`),
헤더는 읽지 않습니다. 라우트마다 보고를 추가하는 방식이 아니므로 새 라우트가 증빙을
빠뜨릴 수도, 기록하지 않은 증빙을 보고할 수도 없습니다. 거부된 요청도 상관 가능합니다 —
거부는 decision이고, 그 행이 바로 "거부된 시도"를 찾는 감사자가 읽는 것입니다(이 라우트의
거부는 존재 oracle을 피하려 404로 답하므로, 사유를 담은 원장을 찾을 키가 더 중요합니다).

구현 메모 하나: 요청 단위 수집은 `ContextVar`에 **가변 객체**를 담아서 합니다. FastAPI는
이 앱의 `def` 핸들러를 threadpool에서 컨텍스트 **복사본**으로 실행하므로 핸들러 안에서
ContextVar를 다시 바인딩해도 미들웨어에 보이지 않지만, 이미 들고 있는 객체를 변형하면
보입니다. 상한(32)을 넘는 id는 버리지 않고 세어 `withheld_evidence_id_count`에 더합니다 —
이 제품의 다른 모든 상한 리스트와 같은 규칙입니다.

manifest도 계산한 것을 공표하도록 고쳤습니다: `evidence_id_source: server_recorded`,
`caller_asserted_fields: [tenant_id, actor, request_id]`. 드리프트 가드는 AST 기반입니다 —
`src` 안에서 그 헤더 이름을 **호출 인자로** 넘기는 곳을 금지하고 주석은 허용합니다(결함을
설명하는 주석까지 금지하면 설명이 사라집니다).

**남은 경계를 분명히 합니다.** 이 변경은 첫 번째 acceptance criterion을 사실로 만들 뿐이고,
같은 integration의 두 번째 criterion(alert 조건 평가 + `SDP_ALERT_WEBHOOK_URL` 라우팅)은
여전히 미구현입니다. `SDP_ALERT_WEBHOOK_URL`은 `declared_unimplemented_environment`에
그대로 있고, 게시되는 alert 규칙 두 건도 `evaluated: false`입니다. 그중
`policy_audit_gap`은 이제 in-process 상태로 평가할 수 있게 됐지만(이 키가 있어야 창
단위로 셀 수 있습니다) 그것은 별도 변경입니다. `central_workflow_backlog`은 GitHub
Actions 상태를 봐야 하므로 이 서비스가 평가할 수 있는 조건이 아닙니다.

역검증: 헤더 읽기를 되돌리면 correlation 테스트 5건과 AST 가드가 실패합니다.
`record_policy_decision`의 수집 호출을 지우면 로그에 audit event id는 남고 decision id는
사라져 3건이 실패합니다 — 두 지점이 각각 필요하다는 뜻입니다. 미들웨어 배선을 지우면
모든 행이 빈 리스트로 돌아가 5건이 실패합니다.

### Fixed — kind 충돌 가드가 네 경로 중 두 곳만 덮었고, 그 두 곳도 틀린 id를 봤습니다 (high)

바로 앞 항목의 수리를 2라운드 적대적 검증에 다시 걸었더니, **고친 쪽이 결함이었습니다.**
같은 손상(그래프 미러가 노드의 kind를 바꿔야 하는 상태에서 카탈로그가 반쯤 적용됨)에
도달하는 경로가 다섯 개 더 남아 있었고, 전부 1회 인증 요청으로 측정됐습니다.

**1. `id`를 생략한 create는 가드를 통째로 비껴갔습니다.** 가드를 라우트에서
`request.id`에 대고 불렀는데, 카탈로그가 id를 배정하는 요청에서 그 값은 `None`입니다 —
`None`이라는 이름의 노드가 있느냐고 묻고 통과했습니다.

    POST /catalog/datasets  (id 없음, dataset-001이 개념 노드)
      수리 전 가드 기준:  500   행 생성 True,  이후 seed_store raise
      지금:               409   행 생성 False, seed_store 정상

id는 `register_dataset`의 `before_commit` 훅에서 — 확정된 **뒤**, 첫 쓰기 **전** —
검사합니다. 라우트 바깥에서는 물을 수 없는 질문이었습니다.

**2. `publish`와 `deprecate`는 아무것도 묻지 않았습니다.** `seed_dataset`은 네 개의
mutation이 모두 호출하는데 가드는 두 곳에만 있었습니다.

    POST /catalog/datasets/{id}/publish    -> 400, status 변경 **적용됨**
    POST /catalog/datasets/{id}/deprecate  -> 500, status 변경 **적용됨**
    두 경우 모두 감사 행: result='success'   (호출자가 본 것은 실패)

장부가 호출자가 본 것과 반대를 기록하는 것이 이 중 가장 나쁩니다. 둘 다 저장된 행의
컬럼으로 사전 검사해 409이고, `updated_at`까지 그대로입니다.

**3. 제목만 바꾸는 patch도 가드를 건너뛰었습니다.** 검사가 `request.schema is not None`에
걸려 있었는데, 데이터셋의 **자기 노드**는 schema를 선언하지 않는 patch도 다시 씁니다 —
측정값은 400에 제목 변경이 적용된 상태. 이제 dataset id는 무조건 검사합니다.

**4. 중복 dataset id가 500이었습니다.** `_register_dataset_locked`가 어느 라우트도 잡지
않는 bare `ValueError`를 던졌습니다. 성격이 같은 거부(id가 이미 점유됨)이므로
`DatasetAlreadyExists` 전용 타입으로 올리고 409로 답합니다. `pydantic.ValidationError`도
`ValueError`이므로 전용 타입이 필요합니다 — 바로 앞 항목에서 같은 함정을 이미 한 번
밟았습니다.

**5. reconciliation이 남의 노드를 파괴했습니다(사전 결함).** 선언되지 않은 `has_column`
간선의 **대상 노드를 무조건 삭제**했습니다. `POST /graph/edges`는 `has_column` 간선을
아무 노드에나 허용하므로, 두 번의 정상 요청으로 개념 노드가 사라집니다.

    POST /graph/edges  has_column  내데이터셋 -> 고객(시드 개념)  -> 200
    PATCH /catalog/datasets/내데이터셋  (schema 선언)             -> 200
      -> 고객 노드와 그에 닿는 모든 간선 삭제. 용어 해석 경로가
         정의되지 않은 개념처럼 응답.

이것이 1~3번이 거부해야 하는 상태로 가는 **도달 경로**이기도 합니다(카탈로그 행은 남고
그래프 노드만 사라지므로, 그 id를 개념이 차지할 수 있습니다). 삭제는 `seed_dataset`이
직접 쓰는 `{dataset_id}:` 노드로만 좁혔습니다 — 간선은 그대로 제거합니다, 그것은 이
데이터셋의 간선이니까요.

역검증(각각 수리를 되돌려 자기 테스트만 실패하는지 확인): `before_commit` 인자 제거 →
no-id create 테스트 + 기존 create 테스트 3건 실패. `DatasetAlreadyExists` → bare
`ValueError` → 중복 id 테스트 실패. patch 검사를 `if request.schema is not None`으로
되돌림 → 제목만 patch 테스트 실패. `publish`/`deprecate` 사전 검사 제거(2곳) → 해당 2건
실패. `_owns_column_node` 가드 제거 → reconciliation 테스트 실패. 다른 테스트는 어느
경우에도 깨지지 않았습니다.

새 테스트 자신의 결함 하나도 같이 고쳤습니다: no-id 테스트가 공유 그래프 스토어
싱글턴(`conftest`의 복원 fixture 대상이 **아님**)에 개념 노드를 남겨
`test_change_reason_evidence` 3건을 전체 실행에서만 깨뜨렸고, 반대로 그 id가 비어 있다고
가정했더니 역순·seed 11 순서에서 자기가 깨졌습니다 — 앞서 돌아간 no-id 등록이 거기에
`dataset` 노드를 남겼기 때문입니다. 지금은 먼저 치우고 쓰고 다시 치웁니다. 같은 파일의
감사 테스트는 `list_audit_events`가 **최신 우선**으로 정렬된 한 페이지를 돌려주는데
`rows[-1]`을 읽고 있었습니다 — 복원된 baseline이 비어 페이지가 한 줄일 때만 맞는
단언이라 `rows[0]`으로 고쳤습니다.

create 거부 행의 `action`도 고쳤습니다: `dataset.create`로 적혀 있었는데 허용 경로와
403 거부 경로는 모두 `dataset.register`입니다 — action으로 필터하면 거부가 빠지므로
"같은 action에 result로 결과를 구분한다"는 이 장부의 규칙을 깨고 있었습니다.

가드의 **완전성**을 재는 테스트도 넣었습니다. 기존 테스트는 알려진 두 id 모양이
거부되는지만 봤으므로, `seed_dataset`이 세 번째 노드 쓰기를 갖게 되고 가드가 그것을
놓쳐도 계속 녹색이었습니다 — 두 라운드에서 네 번 재발견된 결함이 정확히 그 모양입니다.
컬럼·용어·매핑·양방향 lineage·연관 데이터셋을 가진 데이터셋을 사설 스토어에 미러하고,
가드가 묻는 node id 집합이 미러가 만든 집합과 **같음**을 단언합니다(간선은 노드 쓰기가
아닙니다 — `upsert_edge`는 끝점을 만들지 않습니다). 역검증: 가드에서 컬럼 루프를 지우면
이 테스트가 실패합니다.

### Fixed — 카탈로그 쓰기가 그래프 미러의 kind 충돌로 반쯤 적용되던 두 경로 (high)

적대적 검증이 "노드의 kind를 바꿀 수 있는 경로"를 전수 열거하다 찾은 두 구멍입니다. kind
규칙(`assert_node_kind_is_stable`)을 넣은 커밋 자체에서 생긴 것이고, 직전 계층 작업과는
무관합니다. 두 라우트 모두 **카탈로그 행을 먼저 쓰고 그 다음에** 그래프로 미러링하므로,
kind 거부가 너무 늦게 도착했습니다. 측정값(각 1회 인증 요청):

    POST /catalog/datasets {"id": "고객", ...}        (고객은 시드 개념)
      -> 500
         카탈로그 행 생성:               True
         GET /catalog/datasets/고객:      200
         그래프 노드 kind:               concept  (dataset 노드는 영원히 없음)
         이후 seed_store(새 스토어):      ValueError

    PATCH /catalog/datasets/{id} — 선언한 컬럼의 노드 id를 개념이 이미 점유
      -> 400 {"error": "invalid_request", "reason": "request body is not valid"}
         카탈로그 title:  '충돌검사셋 제목' -> '바뀐 제목'   (적용됨)
         카탈로그 schema: []              -> ['컬럼']       (적용됨)

첫 번째가 더 나쁩니다: 요청 한 번으로 그 프로세스가 **다시는 그래프를 시딩할 수
없게** 됩니다 — `seed_store`가 모든 카탈로그 행을 돌면서 그 행에서 raise하기 때문입니다.
두 번째는 본문이 잘못됐다고 답하면서 카탈로그는 두 변경을 모두 유지합니다.

이제 `seed.assert_dataset_mirror_kinds_are_available`를 **카탈로그 행을 건드리기 전에**
묻고 둘 다 409로 답하며 아무것도 쓰지 않습니다 — `POST /graph/nodes`와
`POST /ontology/concepts`가 같은 충돌에 이미 주는 상태입니다. 검사는 `seed_dataset` 옆에
둡니다: 그 함수가 쓰는 노드 id(데이터셋 id = kind `dataset`, `{id}:{컬럼}` = kind
`column`)를 그대로 열거하므로 한쪽을 바꾸면 다른 쪽이 옆에 보입니다. 거부는 **자기 사유로**
감사 기록됩니다 — 허용한 결정의 사유로 적으면 일어난 일의 반대로 읽힙니다.

충돌은 이제 전용 타입 `NodeKindConflict`입니다. 처음에는 `except ValueError`로 잡았는데,
`pydantic.ValidationError`도 `ValueError`이므로 숫자가 아닌 `quality_score`가 400 대신
409가 되었습니다(측정 — 제 테스트가 잡았습니다). `GraphIntegrityConflict`의 하위 타입이고
따라서 여전히 `ValueError`이므로, 기존에 `ValueError`를 잡던 핸들러는 모두 그대로
동작합니다.

### Fixed — 직전 두 커밋의 결함 세 건 (적대적 검증으로 발견, high)

앞의 두 커밋(ONT-002 class 분리, ONT-007 순환 금지)을 5개 렌즈 서브에이전트로 적대적
검증한 결과입니다. 한 건은 독립 반증 시도 네 번을 모두 견뎌 **CONFIRMED**로 확정되었고,
나머지는 제가 직접 재현했습니다. 세 건 모두 제가 만든 결함입니다.

**1. 한 요청이 스스로 순환을 선언하면 409가 아니라 500이었고, 절반이 기록되었습니다.**
`POST /ontology/concepts {"broader": "P", "narrower": ["P"]}`는 두 개의 선언이 서로
순환이지만, 쓰기 전 검증기가 **선언을 하나씩 저장된 계층에만** 비교했으므로 개별 검사는
모두 통과했습니다. 그 뒤 라우트의 (어느 `try`에도 없는) 미러 쓰기에서 스토어 게이트가
두 번째 간선을 거부합니다. 측정값:

    POST /ontology/concepts {"concept":"순환개념","broader":"상대개념",
                             "narrower":["상대개념"]}
      -> 500, 어휘 레코드는 "서로가 서로의 한 종류"라고 게시된 상태로 남고,
         그래프 노드와 두 간선 중 하나가 기록되고, 읽기 표면은 모두 200,
         SKOS export에도 포함, 그런데 `hierarchy_consistency`는 conforms: true
         (닫는 간선이 끝내 기록되지 않았으므로 리포트가 볼 수 없음),
         이후 새 스토어에 `seed_store`를 돌리면 그 레코드에서 raise.

이제 선언들을 **서로에 대해서도** 검사합니다(이미 수락한 쌍을 다음 검사로 넘기는
overlay). 결과 409, 두 스토어 모두 무변경. 직전 커밋의 docstring이 "이 잔여는
`hierarchy_consistency`가 보고한다"고 적어 두었던 것은 **거짓**이었습니다 — 리포트는
간선을 읽고, 게이트가 닫는 간선을 막으므로 모순은 어휘 레코드에만 남아 구조적으로
보이지 않았습니다. 선언된 한계에 적힌 보상 통제가 존재하지 않으면 그것도 결함입니다.

**2. 리포트가 지수 시간이었고, 인증 없이 도달 가능했습니다.** 순환 탐색이 모든 단순
경로를 열거하고 현재 경로만으로 가지치기했습니다. **순환이 없는** 합법적 SKOS
다중상속 계층에서 측정:

    개념 67개 / 포섭 88개 (모든 쓰기 인증 200, 순환 0)
      -> GET /enterprise/shacl-validation (익명)  45.6초
    같은 그래프, 수정 후                           0.001초

이 리포트는 `/enterprise/shacl-validation`(익명)과 `/enterprise/steward-review`(두 번)가
읽으므로, 평범한 쓰기 권한자가 순환 하나 없이 그 엔드포인트들을 응답 불가로 만들 수
있었습니다. Tarjan 강결합 성분(반복 구현, 선형)으로 교체했고, 어휘
상한(500개 개념)·간선 9,790개에서 어셈블리까지 0.44초입니다. 재발을 막는 비용 회귀
테스트를 넣었습니다(2,400쌍 < 1초).

여기 적혀 있던 "4,000쌍에서 0.945초"는 **분류기 수치가 아니었습니다** — 스토어를 세워
리포트를 조립하는 경로를 잰 값이 분류기 수치로 잘못 옮겨졌습니다. 다시 측정한 분류기는
2,400쌍 0.0044초, 4,000쌍 0.0078초입니다(각 3회 중 최소값). 0.945초를 분류기 수치로
읽으면 선형 교체의 효과가 120배 작아 보이고, 비용 회귀 테스트의 1초 경계가 거의 꽉 찬
것처럼 보입니다 — 실제 여유는 두 자릿수 배수입니다.

**3. `cycle_count`는 단순 순환 수가 아니라 구성원 집합 수였습니다.** 같은 정점 집합
위의 서로 다른 두 순환이 하나로 합쳐져 과소 보고됐습니다. 단순 순환 수를 세는 것은
본질적으로 지수이므로, 세지 않습니다 — 공표 키를 `cyclic_group_count` /
`cyclic_groups`로 바꿨습니다(강결합 성분 = 서로 포섭하는 개념 묶음, 또는 자기 자신을
포섭하는 개념 하나). 릴리즈 게이트가 필요한 것은 "0이면 비순환"이고, 묶음은 읽는 사람이
봐야 할 개념을 모두 이름 붙입니다. 계산한 것의 이름을 쓰는 규칙(`shacl_compatible`이
가르쳐 준 것)을 같은 자리에 두 번 적용했습니다.

**테스트 결함 두 건도 같이 고쳤습니다.** `..._terminates`는 가드를 되돌리면 실패가
아니라 **영원히 멈춰** 있었습니다(pytest는 기다리고 CI는 판정 없이 죽습니다) — 스토어
읽기 횟수에 예산을 둔 서브클래스로 바꿔 비종료가 평범한 assertion 실패가 되게 했습니다.

**세 번째 결함이 바로 그 비용 회귀 테스트 자신에 남아 있었습니다.** 2,400쌍 그래프는
600단 다이아몬드 사다리, 즉 단순 상향 경로가 2**600개입니다 — 경로 열거를 되돌리면
`hierarchy_consistency(pairs)`가 45초가 걸리는 게 아니라 **돌아오지 않습니다**. 호출이
반환된 *뒤에* 경과 시간을 보는 구조였으므로 assertion에 도달하지 못하고, 고쳤다던 결함과
똑같이 판정 없이 멈춰 있었습니다. `ec4e533`의 커밋 메시지에 적은 "경로 열거를 되돌리면
비용 테스트가 실패한다"와 docstring의 "느린 기계가 아니라 재발에 실패한다"는 둘 다
**거짓**입니다 — 당시 'F'로 읽은 것은 타임아웃으로 잘린 pytest 출력이었습니다. 푸시된
커밋 메시지는 고칠 수 없으므로 여기에 적습니다. 지금은 분류기를 워커 스레드에서 호출하고
`join(timeout=30)` 뒤 `is_alive()`를 단언합니다 — 녹색 경로에서는 밀리초 안에 조인되고,
진짜 재발만 스레드를 남깁니다(그때 스위트는 이미 빨강입니다). 역검증: 경로 열거를 되돌리니
30초 뒤 명확한 실패 판정이 나옵니다(이전에는 무한 대기).

`..._both_backends_call`의 후속 계약 테스트도 같은 종류로 약했습니다 — 소스에 이름이
들어 있기만 하면 통과했으므로, 호출을 지우고 `# TODO: restore the
self.assert_hierarchy_stays_acyclic(...) call` 주석만 남겨도 녹색이었습니다(반쯤 끝난
리팩터가 정확히 남기는 모양입니다). `ast.Call` 노드에서 이름을 모으게 바꿨습니다.
역검증: 같은 주석 치환으로 이제 실패합니다.
`..._both_backends_call`은 이름이 주장하는 것(두 백엔드가 공유 규칙을 호출한다)을 검사하지
않았습니다 — Postgres 백엔드는 이 스위트에서 실행되지 않으므로, 두 백엔드
`upsert_edge`의 **소스**가 공유 규칙 호출을 잃지 않았는지 기계적으로 확인하는 계약
테스트를 따로 넣고 원래 테스트는 실제로 검사하는 것으로 이름을 바꿨습니다.

**거짓 수치 하나**: "어휘에 걸린 계층 간선 7개가 모두 concept -> concept"은 틀렸습니다 —
5개가 concept -> concept이고 2개는 아예 노드가 아닌 target을 가리킵니다(존재하지 않는
끝점에는 kind가 없습니다). 세 곳(shape 주석, ONT-002 비고, CHANGELOG)을 고쳤습니다.

남은 경계도 선언해 둡니다: 어셈블리는 여전히 O(어휘 x 계층 간선)입니다 — 두 백엔드가
가진 `edges_for` 노드 단위 primitive로 읽기 때문이고, 간선이 훨씬 많은 그래프는
단일 패스 primitive가 필요합니다(Postgres 쪽 문장이 따로 필요하므로 별도 변경).

### Fixed — 개념이 자기 자신보다 상위가 될 수 있던 두 경로 (ONT-007/ONT-003, high)

`broader`/`narrower`는 포섭을 주장하는데, **저장된 계층이 이미 뭐라고 말하는지 아무도
읽지 않았습니다**. 측정값(각 1회 인증 요청, 시드 그대로):

    POST /graph/edges  broader  고객 -> 주문   -> 200
    POST /graph/edges  broader  주문 -> 고객   -> 200   (서로가 서로의 한 종류)
    POST /graph/edges  broader  고객 -> 고객   -> 200   (자기 순환)
    POST /ontology/concepts {"concept": "순환상위", "broader": "고객"}  -> 200
    POST /ontology/concepts {"concept": "고객", "broader": "순환상위"}  -> 200

순환이 있는 상태에서도 `GET /ontology/term/고객/graph`,
`GET /ontology/concept/고객`, `GET /ontology/search`, `POST /graph/query`가 모두
200이었습니다 — 순회에 깊이 상한이 있어서 아무것도 터지지 않고, 그래서 **조용히** 틀린
용어집이 서비스되고 있었습니다. 이것이 ONT-003의 "broader/narrower 관계 조회"이자
ONT-007의 "unsatisfiable class 0개" 양쪽에 걸린 결함입니다.

방향이 전부입니다. `narrower: 고객 -> 활성 고객`과 `broader: 활성 고객 -> 고객`은
**같은 주장**이고 시드가 다섯 개 포섭 중 둘을 그렇게 양쪽에서 선언합니다. 반대 주장으로
읽으면 시드 자체가 순환이 되므로, 방향은 `graph_store.subsumption_pair` 한 곳에서만
정규화합니다. 시드의 계층 간선 7개 = 서로 다른 `(child, parent)` 주장 5개.

**거부**: 순환을 닫는 간선은 두 게시 경로 모두에서 409. 상위로 거슬러 올라가는 탐색이라
2단 순환뿐 아니라 긴 사슬도 잡고, 자기 순환은 같은 규칙의 퇴화 사례입니다. `visited`
가드가 **이미** 순환인 계층에서도 탐색이 끝나게 합니다 — 역검증으로 확인: 순환 안에 있는
노드를 부모로 제안하면 가드 없이는 15초 타임아웃까지 반환하지 않고, 가드가 있으면 정상
반환합니다(그 간선은 순환을 닫지 않으므로). 첫 역검증 시도는 부모가 아무 부모도 없는
노드여서 탐색이 순환에 닿기 전에 끝났고, 그래서 가드가 불필요한 것처럼 보였습니다 —
그 사례를 테스트로 박아 두었습니다.

**이번에 같이 고친 선행 커밋의 결함**: 두 계층 규칙(ONT-002의 class 분리와 이 순환
규칙)은 이제 `validate_concept_registration`의 **이미 게시된 개념 조기 반환보다 위에서**
검사합니다. 그 조기 반환의 근거("저장된 레코드는 게시 때 검증되었다")는 `definition`에는
맞지만 계층 필드에는 틀립니다 — 라우트가 **제출된** broader/narrower를 그래프에
미러링하므로 버려지지 않습니다. 측정: 아래에 두면 시드 개념 다섯 개 중 하나(`고객`)에
대한 동일 요청이 **500**(미러 쓰기가 어느 try에도 없음), 미게시 개념에는 409였습니다.
이름 검사(`_assert_concept_kind_is_available`)가 그 둘보다 앞에 섭니다 — 데이터셋 id를
이름으로 쓴 개념은 "이름 충돌"이 더 정확한 진단이기 때문입니다.

**공표**: `/enterprise/shacl-validation`의 `hierarchy_consistency`가 `cycle_count`,
순환 구성 개념, `consistency_engine: builtin_graph_checks`,
`reasoner_executed: false`를 게시합니다. 릴리즈 게이트가 읽을 숫자이고, 수용 기준이
부르는 "unsatisfiable class"로 이름 붙이지 않았습니다 — 순환은 개념들을 서로 포섭하게
만들 뿐이고 불충족성에는 이 저장소에 없는 disjointness axiom이 필요하므로, 계산한 것의
이름(순환 수)을 씁니다. 순환성은 노드나 간선의 성질이 아니라 **그래프**의 성질이라
SHACL shape 목록에는 넣지 않았습니다 — 넣으면 `shacl_compatible`이 shape이 아닌 제약을
담게 됩니다.

ONT-002의 class 분리와 달리, 이 게이트는 kind가 아니라 **간선**을 읽으므로 단일 쓰기로
순환이 생기는 구멍은 없습니다(그쪽 게이트를 뚫는 순서를 이 게이트는 409로 막습니다 —
측정). 리포트는 게이트가 본 적 없는 간선을 위한 것입니다: 게이트 이전에 쓰인 계층,
`upsert_edge`를 우회하는 향후 일괄 경로, 그리고 Postgres 백엔드에서 도달 가능성 탐색이
쓰기 트랜잭션 **밖에서** 돌기 때문에 생기는 동시 쓰기 창.

미해결로 선언해 둔 것: reasoner도 OWL axiom도 없고, SKOS S27(`skos:related`와
`skos:broaderTransitive`의 disjointness — 시드는 측정상 깨끗하지만 게이트 없음)은
검사하지 않으며, 이 숫자를 묶을 릴리즈 게이트 자체가 저장소에 없습니다. ONT-007은
`not_implemented`에서 `partial`로만 올립니다.

### Fixed — data asset이 business class 계층에 들어갈 수 있던 두 경로 (ONT-002, high)

`broader`/`narrower`는 이 그래프에서 "~의 한 종류"를 주장하는 유일한 관계인데,
양 끝점의 `kind`를 **아무도 읽지 않았습니다**. 측정값(각 1회 인증 요청, 시드 그대로):

    POST /graph/edges  broader  crm-customer-master -> 고객          -> 200
    POST /graph/edges  broader  고객 -> crm-customer-master          -> 200
    POST /graph/edges  narrower crm-customer-master -> 고객          -> 200
    POST /ontology/concepts {"concept": "테스트개념하나",
                             "broader": "crm-customer-master"}       -> 200
    POST /ontology/concepts {... "narrower":
                             ["crm-customer-master:customer_id"]}     -> 200

즉 ONT-002의 수용 기준("table/dataset이 business class의 subclass가 되지 않도록")이
글자 그대로 깨져 있었고, 거부에 필요한 사실(양 끝점의 kind)은 이미 저장되어 있었습니다.
노드 id를 **재분류**하는 절반은 앞서 `assert_node_kind_is_stable`로 막혀 있었고, 이것은
간선 절반입니다.

**거부**(409 — 요청은 정상이고 충돌 대상은 저장된 kind라서, 재분류와 같은 읽기):

- `GraphStore.assert_hierarchy_respects_class_separation` — 두 백엔드가 공유하는 순수
  규칙(`hierarchy_class_separation_refusal`) 하나를 호출한다. 인메모리는 락 안에서,
  Postgres는 같은 트랜잭션 안에서 kind를 읽으므로 검사와 쓰기 사이에 창이 없고, 두
  백엔드가 거부 대상이나 메시지로 어긋날 수 없다.
- `POST /ontology/concepts`는 **쓰기 전** 검증기에서 막는다. 스토어 게이트만 두고
  역검증하면 같은 요청이 **500**이고 어휘 레코드와 그래프 노드가 이미 기록된다
  (`upsert_concept`가 노드→어휘→간선 순서로 쓰고, 라우트의 미러 쓰기는 어느 `try`에도
  들어 있지 않다). 남는 창은 kind 검사가 이미 갖고 있는 것과 같은 모양(검사와 미러
  쓰기 사이의 동시 쓰기)이고, 닫으려면 두 쓰기가 한 트랜잭션이어야 하므로 상태 코드로
  덮지 않았다.
- `mapping`과 `related`는 그대로 허용한다 — `mapping`은 dataset↔concept를 잇는
  모델링된 관계이고 `related`는 SKOS에서 연관 관계다. 규칙은 포섭 주장만 거부한다.

**검증**(수용 기준의 "검증" 쪽) — `ConceptHierarchyShape`는 이 저장소에서 class 계층을
표현하는 첫 shape이고, 계층 간선 양 끝점에 걸리는 `sh:class` 모양의 제약이다.
`/enterprise/shacl-validation`의 `hierarchy_class_separation`이 그래프의 **현재 상태**를
평가한다. 두 절반이 모두 필요한 이유는 측정으로 나온다:

- 쓰기 게이트는 쓰는 시점에 알려진 kind만 읽으므로, 끝점이 없을 때 쓴 간선의 끝점이
  나중에 dataset으로 생기면 두 쓰기 모두 200이다 — 그 뒤 리포트가 `conforms: false`,
  `hierarchy_pass_rate` 0.875로 잡는다.
- 끝점이 없는 간선을 violation으로 올리면 **시드 로드 자체가 실패한다**(역검증:
  `seed_store`가 `narrower ... target '활성 고객'`에서 raise). 시드의 78개 간선 중
  27개가 없는 노드를 가리키고 그중 2개가 계층 간선이다. 그래서 unknown은 violation이
  아니라 `unknown_endpoint_count`로 따로 센다 — ConceptShape의 계층 target 제약이
  warning에 머물러야 하는 것과 같은 판단이고, 이쪽은 violation으로 둘 수 있다
  (시드의 계층 간선 7개 중 5개가 concept -> concept이고 2개는 존재하지 않는 target을
가리켜 violation이 아니기 때문 — "7개 모두"라고 적었던 것은 틀렸고 적대적 검증이
잡았습니다).

선언해 둔 미해결 경계: SHACL 프로세서도 reasoner도 실행되지 않고
(`shacl_engine_executed: false`), `kind`는 여전히 자유 문자열이며, 리포트 범위는 어휘에
걸린 간선뿐이다 — `kind="concept"` 노드를 `POST /graph/nodes`로 직접 쓰면 어휘에 없으므로
그 노드와 나중에 dataset이 되는 노드 사이의 계층 간선은 아무도 세지 않는다(측정).
`conformance_scope`가 그 사각을 직접 선언한다. ONT-002 상태는 `partial`로 둔다 —
수용 기준이 이름을 부른 SHACL/OWL 엔진이 없기 때문이고, 거부와 검증이 생겼다는 것이
기준 전부를 충족한다는 뜻은 아니다.

### Fixed — steward 신원이 인증 없이 공개되던 두 표면 (high)

`GET /ontology/patches`는 **권한 검사를 전혀 하지 않았습니다.** `analyst`가 제안하고
`admin`이 승인한 패치 하나를 두고 측정:

    GET /ontology/patches                  200  requestor=analyst
                                                reviewed_by=admin
                                                reviewed_at=2026-10-14T18:44:32Z
                                                review_comment='스튜어드 승인 사유'
    GET /ontology/patches?user=anonymous   200  (같은 네 필드)
    GET /ontology/patches?user=nobody      200  (같은 네 필드)

같은 시점, 같은 신원에 대해:

    GET /ontology/change-log               403
    GET /audit/events                      403
    GET /policy/decisions                  403

즉 누가 어휘 변경을 제안했고 누가 승인했으며 심사자가 무슨 사유를 적었는지를 인증
없는 호출자에게 게시하면서, 같은 사실을 그걸 담도록 만든 세 표면에서는 거부하고
있었습니다. ONT-004가 변경 로그를 게이트한 근거는 `{actor_id, reviewer_id,
recorded_at}`이 **접근 기록 그 자체**라는 것이었고, 이 경로는 그 기록에 심사 사유까지
더해 서빙합니다 — 근거는 그대로 적용되며, 두 표면이 더는 엇갈리지 않습니다.
ONT-004 당시 이 불일치는 "이번 변경이 넓히지 않은 기존 결함"으로 기록만 해 두고
닫지 않았습니다. 그 기록이 이번에 닫혔습니다.

**표면은 하나가 아니라 둘이었습니다.** 앱이 서빙하는 모든 GET 라우트를 열거하고,
응답 본문을 필드 **이름으로 grep하지 않고** 파싱해 mapping key로 훑은 결과:

    /ontology/patches            requestor, reviewed_by, reviewed_at, review_comment
    /enterprise/steward-review   requestor

그래서 앞의 경로만 게이트하면 제안자 이름은 뒤의 경로로 그대로 읽혔을 것입니다 —
점검이 아니라 연극이 됩니다. 두 표면을 한 커밋에서 함께 바꿉니다.

- **`GET /ontology/patches` → 거버닝 읽기.** `_authorize_evidence_read`(변경 로그와
  같은 헬퍼, 평행 규칙이 아님)를 쓰고, 그 tenant 목록은 변경 로그와 같은 이유로
  적용하지 않습니다 — 개념 어휘는 tenant 소유가 아니라 공유 자원이므로 제안을
  범위 지을 tenant 술어가 없습니다. 적용되는 범위는 권한뿐이고, 응답은 그 사실을
  `scope_note`로, 통과한 판정을 `policy_decision_id`로 말합니다. 권한 검사는
  `?status=` 검증보다 **먼저** 돕니다(`ontology_patch_review`가 명시한 규칙):
  400 본문이 `known_statuses`를 게시하므로 순서를 바꾸면 권한 없는 호출자가 물을
  자격이 없는 질문에 답하게 됩니다. 측정: `?status=nope`는 actor 없이 403,
  actor와 함께 400. 능력은 사라지지 않습니다 — 인증된 actor는 네 필드를 포함한
  큐 전체를 그대로 읽습니다. steward가 제안을 판단하려면 제안자를 알아야 하므로
  무조건 삭제가 아니라 게이트입니다.
- **`/enterprise/steward-review` → `requestor` 미게시 + 선언.** 이쪽은 게이트하지
  않습니다: 게시된 공개 증빙 링크(`OPEN_PROOF_ENDPOINTS`)이고
  `test_every_published_proof_link_resolves_as_published`가 인쇄된 그대로 400 미만을
  요구하며, 이 요약이 답하는 조달 질문(큐가 얼마나 깊은지, 핸드오프 준비가 됐는지)에
  제안자 이름은 필요 없습니다. 짧아진 행이 "제안자 정보가 없는 행"으로 읽히지 않도록
  `withheld_review_item_fields: ["requestor"]`와, 신원이 어디 있는지 말하는 note를
  함께 게시합니다. 필드는 **권한이 있는 호출자에게도** 빠집니다 — 여기서 actor에 따라
  신원을 바꾸려면 판정 행을 남기지 않는 술어로 권한을 결정해야 하고, 그러면 증빙 없는
  권한 판단이 하나 생깁니다.

**게이트냐 리댁션이냐를 가른 측정.** 모든 GET 라우트를 돌려 익명 호출의 상태와 원장
증가를 함께 쟀습니다: 정책을 평가하는 19개 라우트는 **전부** actor 없이 403이고,
**200을 주면서 원장에 행을 쓰는 GET은 하나도 없습니다.** 그래서 "평가하고 리댁션된
200을 주는" 설계는 익명 성공에 원장 비용을 물리는 유일한 읽기를 만들게 됩니다 —
인증 없는 호출자가 통제하는 무한 증가 표면입니다.
`test_the_scoped_route_is_not_a_new_ledger_write_surface`가 한 라우트에 대해 말하던
그 불변식을 이제 플랫폼 전체에 대해 기계적으로 고정합니다.

**검사 도구 자체의 결함 세 건** — 전부 도구를 읽어서가 아니라 **돌려서** 찾았습니다.

1. **거짓 양성.** 처음 쓴 열거 도구는 응답 **본문 텍스트**에서 필드 이름을 찾았고,
   `"withheld_review_item_fields": ["requestor"]` — 그 필드가 **없다는 선언** — 을
   유출로 보고했습니다. 선언은 유출이 아닙니다. 파싱 후 mapping key 순회로 바꿨고,
   `test_the_declaration_is_not_itself_a_disclosure`가 그 구분을 고정합니다(본문
   텍스트에는 `requestor`가 **있고**, 값을 담은 key는 **없다**) — 다음 사람이 선언을
   지워 거짓 양성을 "고치지" 못하게.
2. **JSON이 아닌 200을 전부 건너뜀.** 도구가 `response.json()`에서 예외가 나면
   `continue`했고, 그 대상이 바로 200 HTML(`/enterprise/console`)과 200
   text(`/metrics`)입니다 — 큐를 서버에서 렌더링하는 표면은 그것을 잡으려고 쓴
   테스트를 그대로 통과했을 것입니다. 역검증: 콘솔 HTML에 `list_patches()`를
   심어 보니 두 검출기가 모두 걸렸습니다(심사 사유 값, 그리고 행 id). `requestor`와
   `reviewed_by`는 **구별 가능한 값으로 심을 수 없습니다** — 제안/심사 게이트를
   통과하는 실제 actor여야 하고, `analyst`를 부분문자열로 찾으면
   `/enterprise/rbac-matrix`의 `data-analyst` 역할에 걸립니다. 그래서 JSON이 아닌
   표면은 **행 자체를 담지 않음**을 증명하는 쪽으로 덮습니다(행이 없으면 그 행의
   제안자를 렌더링할 수 없습니다). 그 표면 목록도 열거해서 단언하므로 세 번째
   non-JSON 표면이 생기면 함께 검사됩니다.
3. **그 수리의 과잉 적용.** 2를 고치면서 심은 개념 이름과 patch id까지 "행 표지"로
   보고 금지했고, 다섯 표면에서 걸렸습니다 — 그리고 **다섯 다 설계상 맞습니다**:
   승인된 패치는 그 개념을 공개 어휘에 게시하고(`/ontology/concepts`,
   `/ontology/vocabulary/jsonld`, `/enterprise/evidence-pack`),
   `/enterprise/steward-review`는 큐 행의 id·concept·status·confidence를 게시합니다
   (요약이 답해야 하는 "큐가 얼마나 깊고 무엇에 대한 것인가"입니다). 그것을 유출로
   단언하면 고치려는 것과 **반대 방향의 거짓 주장**이 됩니다. 식별 값만 남겼습니다.

값 검색은 **직렬화 형식에 민감**합니다: 위 역검증에서 심사 사유는 걸렸지만
`reviewed_at`은 걸리지 않았습니다 — 콘솔은 datetime을 `2026-10-14 19:02:31+00:00`로,
라우트는 ISO `...T...Z`로 쓰기 때문입니다. 그래서 값 검색은 세 검출기 중 하나이고,
의지하는 쪽이 아닙니다. 이 한계도 테스트에 적어 둡니다.

양방향 역검증: steward 요약에 `requestor`를 되살리면 4건 실패, 큐에서 게이트를 빼면
5건 + `test_api_error_contract.py` 1건 실패, 게이트는 두고 거부 표를 되돌리면
`api_error_contract` 2건 실패. 핸들러와 표를 따로 바꾸면 어느 쪽이든 실패합니다.

**선언 자체도 파생값으로.** `withheld_review_item_fields`를 처음에는 `["requestor"]`
리터럴로 썼습니다. 그러면 누군가 그 필드를 다시 넣어도 선언은 계속 "숨긴다"고
주장합니다 — 이 제품이 거부하려는 바로 그 종류의 드리프트(코드와 어긋나는 게시된
주장)입니다. 이제 항목들로부터 파생합니다: 필드가 되살아나면 선언에서 **자동으로
빠집니다**. 역검증에서 `requestor`를 되살리니 선언이
`['reviewed_by','reviewed_at','review_comment']`로 줄었고(주장이 거짓이 될 수 없음),
그와 동시에 테스트 4건이 실패했습니다.

### Fixed — ConceptShape 게이트가 스스로 만든 결함 6건 (적대적 검증에서 발견)

바로 위 게이트를 다섯 개의 독립 렌즈로 반박 검증시켰고, 여섯 건이 재현되었습니다.
일곱 번째는 그 수리를 검증하는 과정에서 순서 무관 측정이 직접 잡았습니다.
전부 제 변경이 만든 것이거나 그에 인접한 것이므로 제가 고쳤습니다. 모든 재현은 제가
직접 다시 측정했습니다.

1. **잘못된 거부(회귀, high).** shape을 **제출된** 필드에 대해 평가했는데, 이미 게시된
   개념에서는 그 제출이 버려집니다(승인이 배포된 정의를 조용히 덮어쓰지 않도록). 그래서
   기존 개념의 graph edge·embedding을 갱신하는 유일한 경로가
   `POST /ontology/concepts {"concept": "고객", "related": [...], "aliases": [...]}`
   에서 **200 → 400**으로 회귀했습니다. 유일한 통과 방법은 어휘가 버릴 definition을
   다시 보내는 것이었고, graph store는 그것을 **저장**하므로 하나의 200 응답이 어휘가
   받아들인 적 없는 graph definition을 담았습니다. 이제 필수 속성 검사는 **새 개념에만**
   적용됩니다(`_assert_no_alias_conflict`와 같은 조건). 저장된 레코드는 게시 시점에
   검증되었으므로 다시 게이트하지 않습니다.
2. **평가 대상 미표기(medium).** 재게시 경로의 보고가 어떤 레코드에 대한 판정인지
   말하지 않아, 200 응답이 호출자가 보내지 않은 내용에 대해 `conforms: true`를 담을 수
   있었습니다. `evaluated_record`(`submitted` / `published_vocabulary`)를 둡니다 —
   `evaluated_shapes`가 제약에 대해 하는 일을 주체에 대해 합니다.
3. **상한 없는 필수 필드(medium).** `definition`을 필수로 만들면서 상한을 두지 않았고,
   측정 결과 **2,000,000자** definition이 200으로 저장되었습니다 — 500칸 프로세스
   수명 어휘에서. 개념 **이름**은 게이트 세 줄 위에서 2000자로 묶여 있고 patch 경로도
   같은 필드를 2000자로 묶습니다(2001자는 intake에서 400). shape이
   `max_property_length`를 게시하고 두 경로가 **같은 상수**를 씁니다.
4. **intake와 게이트의 술어 불일치(medium).** `POST /ontology/patches`는
   `suggestion.strip()`을, 게이트는 가시 문자 술어를 썼고 `suggestion`이 바로
   definition입니다. 그래서 U+200B·U+FEFF·U+00AD·NUL 제안이 공유 steward 큐에 200으로
   들어가 **영원히 승인될 수 없었습니다** — 모든 승인이 400이고 patch는 `proposed`에
   고정되어, 심사자에게 남은 선택은 제품 스스로 받아들인 제안을 거부하는 것뿐이었습니다.
   권한 있는 분석가가 상한 있는 공유 큐를 그런 제안으로 채울 수 있었습니다. 이제
   `propose_patch`(라이브러리 seam)가 같은 술어를 적용하고, 승인 시점 게이트는
   backstop으로 남습니다.
5. **읽기 전용 사본이 사본이 아니었습니다(medium).** `concept_vocabulary_snapshot`은
   `dict(record)` — **얕은** 복사라서 돌려주는 aliases/narrower/related 리스트가 살아
   있는 저장 리스트였습니다. 이 접근자만 써서(비공개 접근 없이)
   `snapshot()["매출"]["narrower"].append(...)`로 해소 불가능한 계층 target을 게시된
   어휘에 심을 수 있었고, alias로는 `_assert_no_alias_conflict`가 거부하는 용어를
   가져갈 수 있었습니다. 원본을 참조하는 "사본"은 사본이 없는 것보다 나쁩니다 —
   호출자가 docstring을 믿기 때문입니다. `deepcopy`로 고쳤습니다.
6. **거부 타입(low).** `definition.strip()`이 비문자열에 `AttributeError`를 냈고 두
   라우트는 `ValueError`만 매핑합니다 — 거부를 ValueError로 알린다고 문서화된 함수가
   매핑되지 않는 예외 타입을 넘겼습니다. 강제 변환이 아니라 **거부**합니다: `str(5)`는
   "5"를 정의로 게시하는 조작입니다.

7. **두 스토어가 같은 개념의 정의를 두고 갈라졌습니다(high).** 1번을 고치고 나서 순서
   무관 측정에서 드러난 것입니다 — 역순 파일 순서에서 **유지되고 있던** 테스트
   `test_the_shared_vocabulary_itself_stays_open`이 실패했습니다. 라우트가 graph store에
   **원본 제출**을 그대로 넘겼으므로, `definition`을 생략한 재-upsert가 어휘에는
   아무 영향이 없으면서 graph store에는 `''`를 썼습니다. 그리고
   `GET /ontology/term/{term}/graph`는 store를 읽으므로, 측정 결과 고객의 정의가
   **빈 문자열로 서빙**되었습니다(어휘는 실제 정의를 그대로 들고 있는 동안). 어휘가
   개념 정의의 권위이므로, 이제 mirror에 `ontology.published_concept_definition`이
   돌려주는 **게시된 정의**를 넘깁니다 — 호출자의 다른 필드는 그대로 반영됩니다.
   같은 라운드에서 제 새 테스트가 시드 개념의 graph 레코드를 건드려 상태를 흘리고
   있었던 것도 고쳤습니다(graph store 싱글턴은 conftest 복원 대상이 아니라고 그
   docstring이 선언합니다) — 자기 개념을 만들어 쓰도록 바꿨습니다.

함께 선언한 경계 하나: `concept_conformance`는 **게시된 어휘**만 셉니다.
`POST /graph/nodes {"kind": "concept", "properties": {"definition": ""}}`로 쓴 노드는
어휘에 없으므로 세지 않습니다 — 측정 결과 그런 노드가 `GET /graph/nodes`로 서빙되는
동안 pass rate는 1.0입니다. `conformance_scope`로 적어 둡니다.

이 라운드에서 고치지 않고 남긴 것: shape이 자유 텍스트 주석 속성을 유일한 violation으로
삼고, 요구사항이 실제로 말하는 `sh:class` 제약(ONT-002)은 warning입니다. 시드가 그
제약을 10회 위반하기 때문인데, **새로 제출된** edge에만 violation으로 적용하면 시드를
막지 않고 강화할 수 있습니다 — 별도 변경입니다.

### Security — 개념 하나를 등록하면 데이터셋의 거버닝 메타데이터가 파괴되었습니다

`upsert_node`는 새 `GraphNode`를 만들어 저장된 노드 **위에 덮어썼습니다**. 그래서 다른
kind가 이미 쓰고 있는 id로 쓰면 그 노드를 통째로 교체했습니다. 시드에서, 권한 있는
요청 하나로 측정:

    GET  /graph/nodes/crm-customer-master   kind=dataset
        label='고객 마스터'
        properties={domain, owner, steward, tags, terms,
                    sensitivity: 'medium', status: 'published'}

    POST /ontology/concepts {"actor": "admin",
                             "concept": "crm-customer-master",
                             "definition": "...", "broader": "고객"}
        -> 200

    GET  /graph/nodes/crm-customer-master   kind=concept
        label='crm-customer-master'
        properties={definition, aliases, multilingual}

온톨로지 쓰기 하나가 데이터셋의 분류(`sensitivity`·`owner`·`steward`·`status`)를
조용히 지웠습니다 — 테넌트 경계와 masking obligation이 근거로 삼고
`/search/semantic`·`/graph/query`가 서빙하는 바로 그 메타데이터입니다. 이 경계의 **테넌트
쪽**은 이미 닫혀 있었지만(`_authorize_graph_write`가 대상 테넌트를 해소합니다) **kind
쪽**은 권한 있는 누구에게나 열려 있었습니다.

`GraphStore.assert_node_kind_is_stable`로 **node의 kind를 불변**으로 만듭니다. 기존 id를
다른 kind로 다시 쓰는 요청은 409이고, in-memory 스토어는 락 안에서(검사와 쓰기가 한
단계), Postgres 스토어는 **같은 트랜잭션 안에서 `FOR UPDATE`로** 읽습니다 —
`get_node`로 읽으면 자기 커넥션을 열어 검사와 upsert 사이에 창이 생깁니다.

이것은 **kind 허용목록이 아닙니다.** `kind`는 계속 free-form이므로 새 kind를 들일 수
있고, 적대적 문자열을 kind로 넘기는 injection 회귀 테스트도 그대로 돕니다. 거부하는
것은 **이미 존재하는 id의 재분류**뿐입니다 — 파괴만 거부하고 정당한 것은 아무것도
거부하지 않습니다(같은 kind upsert는 카탈로그 미러·시드·개념 재등록이 모두 쓰는
경로입니다).

이 결함을 고정하고 있던 테스트가 하나 있었습니다.
`test_the_export_never_derives_dataset_identity`가 hijack upsert의 **200을 단언**하고
있었는데, 그 200이 결함입니다. 이제 409과 데이터셋 노드의 생존을 단언하고, 남은 경계는
따로 고정합니다: 존재하는 노드와 **충돌하지 않는** 데이터셋 id 모양 이름은 여전히
허용되며(ONT-002), 그것이 export에 라벨과 `@id`로 들어가되 mapping·distribution·
dataset 구조는 함께 들어오지 않습니다.

**적대적 검증 2차에서 세 건 더.** 같은 변경을 다섯 렌즈로 다시 반박시켜 나온 것들이고,
전부 제가 직접 재현했습니다.

1. **게이트가 세 경로 중 하나를 놓쳤습니다(high).** kind 검사가
   `GraphStore.upsert_node` 안에만 있었으므로 **graph node를 쓰는 경로만** 덮었습니다.
   `review_patch` → `register_concept`는 어휘만 건드리므로, 측정 결과
   `crm-customer-master` 이름의 patch 승인이 **200**으로 통과해 데이터셋 id가 어휘와
   공개 SKOS export에 들어갔습니다. 검사를 ConceptShape 게이트와 같은 공유 pre-write
   검증기로 옮겨 세 경로 모두를 덮습니다. 그리고 한 충돌에 한 상태 코드가 되도록
   `ConceptKindConflict`(ValueError 하위 클래스 — 기존 핸들러가 그대로 잡습니다)를 두고
   두 라우트 모두 409로 답합니다(승인 라우트는 모든 ValueError를 400으로 매핑하므로
   같은 충돌이 400으로 나가고 있었습니다).
2. **거부가 원장에 ALLOW만 남겼습니다(medium).** 측정 결과 거부된 승인은 정책 결정
   1건(`effect: allow`)과 감사 행 **0건**을, 거부된 upsert는 변경 **이전에** 기록되는
   `authorized` 행 하나를 남겼습니다. 거부된 거버닝 쓰기를 찾는 감사자가 보는 것은
   "게시가 허용되었다"는 기록 하나이고, 게시가 일어나지 않았다는 기록은 어디에도
   없었습니다 — 카탈로그 mutation 라우트들이 이미 같은 이유로 수리된 결함입니다. 두
   경로 모두 실제 결과를 기록합니다.
3. **아무것도 게시하지 않은 승인이 `approved`로 기록되었습니다(medium).** 이미 게시된
   개념에 대한 승인은 상태만 쓰고 아무것도 게시하지 않습니다(등록기가 저장된 레코드를
   돌려주므로 승인이 배포된 정의를 덮어쓸 수 없습니다). 측정 결과 200 + `status:
   approved`였고, 그것만 보면 게시된 것으로 읽힙니다. 감사 결과를
   `approved_without_publication`으로 적습니다.

함께 고친 순서 문제: store 쓰기가 `register_concept` **이전**이고 무조건적이었으므로,
`register_concept`의 거부(어휘 상한, 락 안에서 다시 확인하는 alias 충돌)가 409를 내면서
graph node는 이미 써진 상태가 되었습니다 — 쓰기를 막으려던 거부가 두 스토어를
갈라놓았습니다. 이제 **어휘를 먼저 쓰고 store가 그것을 mirror**하며, kind 검사를 포함한
모든 검증이 두 쓰기보다 앞에 있습니다.

4. **"우회할 수 없다"를 테스트 **이름**이 주장하고 있었습니다(medium).**
   `test_the_gate_cannot_be_bypassed_by_a_future_caller`는 검증기를 직접 불러
   거부되는지만 단언했고, 그것은 같은 파일의 다른 테스트가 이미 덮는 내용입니다 —
   호출자나 쓰기 지점에 대해서는 아무것도 말하지 않았습니다. 리뷰어가 어휘를 직접 쓰는
   함수 16줄을 `ontology.py`에 덧붙여 **전체 스위트가 그대로 green**인 것을
   측정했고(정의 없는 개념이 모든 읽기 표면에 게시되는 동안), 그 중에는 이 테스트도
   있었습니다. "우회할 수 없다"는 **코드 모양의 속성**이므로
   `tests/test_concept_write_chokepoint.py`가 AST로 검사합니다 —
   `tests/test_module_state_coverage.py`와 같은 열거 방식입니다: 어휘를 쓰는 모든
   statement가 선언된 쓰기 지점 안에 있는지, 게시 함수의 **첫 실행 문장**이 공유
   검증기인지, `register_concept`의 호출자 집합이 선언된 둘과 정확히 같은지. 리뷰어의
   그 16줄로 역검증했고, 새 테스트는 실패하고 옛 테스트는 통과합니다 — 그것이 간극의
   증명입니다. 옛 테스트는 실제로 검사하는 것으로 이름을 바꿨습니다.

고치지 않고 남긴 것 하나: `shacl_compatible`은 이름은 "SHACL로 표현 가능"으로 읽히지만
계산은 "게시된 shape 전부가 이 검증기로 평가되는가"(평가 커버리지)입니다. 게시된 키를
바꾸는 것은 계약 변경이고 테스트가 그 값을 단언하므로 이번에 묶어 넣지 않았습니다 —
별도 변경으로 적어 둡니다.

ONT-002는 여전히 `partial`입니다. 아직 열려 있는 쪽은 **edge**입니다:
`POST /graph/edges`에 kind 검사가 없으므로 데이터셋 노드에서 개념으로 `broader` edge를
붙일 수 있고, 그것이 수락 기준이 말하는 class separation 위반입니다 — 거부에 필요한
사실은 모두 이미 존재하고 쓰이지 않고 있습니다.

부수 수리: `tests/test_requirements_coverage.py`의 `func:` 포인터 해소기가
`module.attribute`만 처리해서 `func:sdp.graph_store.GraphStore.assert_node_kind_is_stable`을
"is not a package"로 거부했습니다 — 존재하지 않는 포인터가 아니라 **표현할 수 없는**
포인터였고, dangling 증빙을 잡는 것이 일인 테스트에는 잘못된 실패 방식입니다. 이제
가장 긴 import 가능한 prefix에서 점 경로를 따라가므로 클래스의 메서드도 함수와 똑같이
인용할 수 있습니다. 존재하지 않는 메서드·클래스·모듈은 여전히 각각의 정확한 사유로
거부됩니다(역검증).

### Security — 정의 없는 개념이 공유 용어집에 게시될 수 있었습니다 (ONT-005)

ONT-005(P0) 수락 기준은 "**reasoner + SHACL + reviewer 승인** 후 병합"이고, 심사자
승인이 유일한 게이트였습니다. `review_patch`는 승인 결정에서 곧바로
`register_concept`로 가고, 그 검사는 이름 비어있지 않음·길이·alias 충돌·어휘 상한뿐
입니다. 게시되는 **개념 자체를 보는 것은 아무것도 없었고**, `semantic_validation`에는
개념을 target하는 shape이 하나도 없었습니다.

HTTP로 측정한 결함:

    POST /ontology/concepts {"actor": "admin", "concept": "정의누락개념"}
        -> 200,  저장된 definition = ''
    GET  /ontology/search?q=정의누락개념   -> count 1, definition = ''
    GET  /ontology/concept/정의누락개념    -> definition = ''

모든 읽기 표면이 참조하는 공유 용어집이 **정의 없는 개념**을 담을 수 있었고, 그것이
권한 있는 라우트를 통해 게시되었습니다. 용어의 정의가 없는 용어집은 용어집이 아닙니다.

`ConceptShape`를 shape 카탈로그에 추가하고 **공유 pre-write 검증기**
(`validate_concept_registration`)에서 평가합니다. 그래서 두 게시 경로(직접 upsert와
승인)가 하나의 검사로 막히고, 세 번째 호출자가 우회할 수 없습니다. 승인 경로에서는
`register_concept`가 상태 기록 **이전에** 실행되므로(기존 순서 수리), 비적합 개념은
patch를 `approved`로 남기지 않고 `proposed`로 둡니다 — 승인은 기록되고 노출은 없는
상태를 만들지 않습니다.

shape의 강도는 경계를 명시합니다. 엔진은 `builtin_shape_checks`이고
`shacl_engine_executed`는 계속 false입니다 — shape이 SHACL로 표현 가능하고 동등한
in-process 검사로 강제된다는 것이 RDF 스택 없이 할 수 있는 가장 정직한 주장입니다
(`pyshacl`·`rdflib`은 의존성이 아니고 CI는 hash-pinned requirements로 설치하며,
`tests/test_semantic_validation.py`가 그 부재를 `pytest.raises(ImportError)`로
고정합니다).

제약 선택도 측정에 따릅니다:

- `definition`만 **필수**로 둘 수 있습니다. 최상위 개념에는 `broader`가 없고 리프에는
  `narrower`가 없으므로 둘 중 하나를 요구하면 올바른 어휘를 거부합니다. `aliases`는
  같은 이유로 **권고**(warning)입니다. 그리고 `propose_patch`는 concept+suggestion만
  만들므로, aliases/multilingual/broader에 `sh:minCount 1`을 걸면 **모든 patch 승인이
  거부**됩니다.
- 계층 target이 Concept이어야 한다는 `sh:class` 모양의 제약은 **warning**입니다.
  시드 어휘가 9개 미정의 이름에 대해 10회 위반하며, violation으로 올리면 시드 개념
  5개 전부(고객·매출·이탈·이탈 고객·활성 고객)가 비적합이 됩니다(역검증으로 측정).
  제품 자신의 시드를 거부하는 제약은 게시를 막을 수 없습니다. alias 전용 target은
  alias index로 해소되므로(휴면 고객 → 이탈 고객) warning이 아닙니다.

게시된 보고가 **어떤 shape을 적용했는지** 말합니다. 카탈로그가 4개가 되었으므로,
카탈로그만 게시하면 데이터셋 보고가 ConceptShape으로 데이터셋을 검증한 것처럼 읽힙니다
— 이 모듈의 역사가 바로 그 오독에 관한 것입니다. 각 보고가 `evaluated_shapes`를 담고,
`tests/test_semantic_validation.py::test_every_published_required_property_is_evaluated`의
열거가 ConceptShape까지 확장되어 게시된 필수 속성이 평가되지 않는 상태를 막습니다.
`/enterprise/shacl-validation`은 어휘 전체의 `concept_conformance`를 게시하므로 shape의
효과가 게시 순간이 아니라 플랫폼 단위로 측정됩니다.

**ONT-005는 여전히 `partial`입니다.** reasoner가 없고(ONT-007), 속성 존재 shape은
consistency 검사가 아니며, export에는 reasoner가 작용할 OWL axiom이 없습니다 —
NFR-QUAL-002도 그대로 미충족이고, 그 note의 "SHACL shape도 적용하지 않는다"는 서술을
정정했습니다.

### Security — "있음"의 정의가 `str.strip()`이었습니다

위 ConceptShape 게이트의 첫 버전은 `str.strip()`으로 정의 존재를 판정했습니다.
`strip`은 `str.isspace()`가 참인 문자만 제거하고 **Unicode format 범주(Cf)는
whitespace가 아닙니다**. 측정 결과 U+200B(zero-width space)·U+200C·U+00AD(soft
hyphen)·U+200E·U+2060·U+FEFF(BOM)·NUL 각각 하나로만 이루어진 정의가 게이트를
통과했고, `/ontology/search`가 그 개념을 **빈 화면으로 렌더되는 정의**와 함께
돌려주었습니다 — 게이트가 막으려던 바로 그 결함을, `strip`이 건드리지 않는 문자
부류를 통해서 재현한 것입니다.

같은 뿌리가 개념 **이름**에도 있었습니다. `validate_concept_registration`의 검사는
`strip()` 후 비어있지 않음 뿐이어서, 측정 결과 `POST /ontology/concepts`로
U+200B·U+FEFF·NUL **이름의 개념 3개가 200으로 게시**되었습니다. 읽는 사람이 볼 수
없는 이름의 개념은 해석도 검색도 인용도 되지 않으면서 상한이 있는 어휘의 자리를
차지합니다.

하나의 술어(`semantic_validation.has_visible_character`)로 둘을 닫습니다: 값에
Unicode separator(Zs/Zl/Zp)와 control/format(Cc/Cf) 범주 **밖의** 문자가 최소 하나
있어야 합니다. 이 규칙은 `sh:minCount 1`보다 **엄격합니다**(보이지 않는 literal도
minCount는 만족시킵니다) — 그래서 shape이 `required_property_basis`로 그 규칙을
게시하고, 강제하는 규칙과 선언한 규칙이 갈라지지 않습니다. 규칙은 "보이지 않는 문자가
없어야 한다"가 아니라 "보이는 문자가 하나는 있어야 한다"이므로 `"\u200b 실제 정의
\ufeff"`는 적합합니다. 역검증: `str.strip()`으로 되돌리면 7개 문자 케이스 전부가
실패합니다.

### Added — 온톨로지에 버전·변경 로그·심사자 기록이 생겼습니다 (ONT-004)

ONT-004(P0)은 "OWL/RDFS 기반 도메인 ontology를 **버전관리**해야 한다"이고 수락 기준은
"ontology version, change log, reviewer 기록"입니다. 세 가지 모두 없었습니다. 개념
어휘는 릴리즈 정체성이 없는 모듈 수준 Python dict였고, 서로 모순되는 게시 주장이
동시에 떠 있었습니다:

* 요구사항 매트릭스는 ONT-004를 `not_implemented`로 기록하고 있었고 — 맞는 기록이었습니다;
* 같은 시점에 `rdf_connector` 컨트롤 `ontology_version_pin`은
  `status: implemented` / `verification: proof_route_served`를, proof endpoint로
  `/ontology/search`와 `/ontology/resolve`를 들고 게시되고 있었습니다. 측정해 보면
  두 응답 어디에도 "version"이라는 문자열이 없습니다. 컨트롤의 proof route가 그
  컨트롤에 대해 아무것도 증명하지 않았습니다.
* 유일한 심사자 신원은 `OntologyPatch.reviewed_by`뿐이고, 이는 patch 경로에만
  존재합니다. `POST /ontology/concepts`는 모든 읽기 표면이 참조하는 공유 어휘에
  심사 기록 없이 게시했고, 그 감사 행은 `result: "authorized"`이며 **변경 이전에**
  기록됩니다 — alias 탈취 POST가 400으로 거부되어 아무것도 게시되지 않았는데도
  동일한 "authorized" 행이 남는 것을 측정했습니다. 게시가 실제로 일어났다는 증거가
  어디에도 없었습니다.

`src/sdp/ontology_version.py`가 세 가지를 모두 소유합니다(`sdp.ontology`를 import하지
않습니다 — 어휘를 인자로 받아 의존을 한 방향으로 유지합니다):

* **version**: 기록된 baseline(revision 1)에서 시작하는 단조 `ontology_revision`과,
  **매번 살아 있는 내용에서 다시 계산하는** sha256 `content_digest`. revision은
  프로세스 수명 한정이므로 `revision_is_durable: false` /
  `revision_scope: "process_lifetime"`으로 선언하고, 재시작을 넘는 정체성은 digest
  쪽입니다. digest는 **의미 기준**입니다 — aliases/multilingual/narrower/related는
  의미상 순서가 없으므로(RDF에서 무순서, alias index는 집합 취급) 정렬해서 해싱합니다.
  순서만 뒤바뀐 두 배포가 서로 다른 버전을 보고하면, 의미 없는 차이로 클라이언트의
  pin을 거절하게 됩니다. 멤버를 더하거나 빼면 여전히 움직입니다.
* **change log**: 유효 변경 1건당 1개 항목, 최신 우선, 상한 500건이고 잘린 양을
  `withheld_change_count`로 선언합니다. 이미 게시된 개념을 다시 등록하는 것은
  no-op이므로(측정: 제출한 payload 전체를 버리고 저장된 레코드를 돌려줍니다) 아무것도
  기록하지 않습니다. 어휘 상한에서의 **eviction은 자기 revision**입니다 — 게시된 용어가
  무관한 호출자의 성공의 부작용으로 온톨로지를 떠나는데, 그때까지 그 삭제의 유일한
  흔적은 그것의 부재였습니다(감사 행도, 호출자도 없었습니다).
* **reviewer 기록**: 승인된 patch는 제안자(`actor_role: proposer`)와 승인한 심사자를
  함께 기록합니다. 직접 upsert는 `reviewer_id: null` +
  `review_basis: "direct_admin_upsert"`이고, recorder는 심사가 없는 source에 대한
  reviewer를 **거부**합니다(조용히 버리지 않습니다). `catalog.deprecate_dataset`이
  `reason`을 `"deprecated"`로 기본값 처리해 호출자가 주지 않은 사유를 보고했던 것과
  같은 규칙입니다. `actor_id`의 뜻은 source마다 다르므로(직접 게시에서는 게시자,
  승인에서는 **제안자**) 항목마다 `actor_role`을 적고 전체 매핑을 공개합니다 — 한
  컬럼만 훑어 "누가 이것을 온톨로지에 넣었나"를 답하면 모든 승인에서 틀립니다.
  그리고 `actor_id`는 요청 본문에서 오는 **권한이 확인된 주장**이지 인증된 신원이
  아니므로 `actor_identity_basis`로 선언합니다.

revision이 이름 붙이는 **artifact**도 생겼습니다. `GET /ontology/vocabulary/jsonld`가
어휘를 SKOS/RDFS JSON-LD로 직렬화하고 `owl:versionInfo`에 revision+digest를 담습니다
(기존 DCAT export와 같은 방식 — 손으로 쓴 inline `@context`, 새 의존성 없음). 그
전에는 RDF artifact가 전혀 없었습니다: DCAT export는 dataset을 덮고 그
`mappings[].concept`은 평범한 literal이라, 어디에도 개념을 가리키는 triple이 없었습니다.
dict 위의 숫자는 버전관리가 아닙니다.

export가 **선언하는** 것들:

* 정의되지 않은 계층 target은 IRI를 만들지 않습니다. 측정: 시드 어휘의 19개
  broader/narrower/related edge가 13개의 서로 다른 target을 가리키고, 그 중 **10개
  edge**가 어휘가 정의하지 않는 이름(9개 distinct: 구매·거래·회원가입·구매자·재구매·
  가입자·매출 성장·매출 채널별 집계·가격)을 가리킵니다. 존재하지 않는 개념의 IRI를
  만들면 정의도 레이블도 scheme도 없는 subject 9개를 게시하는 것이므로,
  `sdp:undefinedHierarchyTarget`로 개수와 함께 선언합니다. 이 결함이 읽는 사람에게
  보이게 된 것도 이번이 처음입니다.
* alias 전용 target은 alias index로 해소합니다(활성 고객 related 휴면 고객 →
  이탈 고객). 그래프 순회는 여전히 해소하지 않습니다 — 그쪽은 ONT-003의 결함입니다.
* **dataset id를 담지 않습니다.** `ontology._INDEX`에는 tenant 술어가 없고, 그것을
  서빙하는 것이 바로 `concept_assets`가 자기 정책 결정이 거부한 호출자에게 모든
  테넌트의 dataset id를 흘렸던 경로입니다. 이 라우트는 공개이므로 어휘만 담고,
  개념↔dataset 매핑은 거버닝 읽기에 남습니다(`sdp:datasetMappingIsVersioned false`).

**버전 고정(pin)**도 가능해졌습니다. `/ontology/search`와 `/ontology/resolve`가 답한
버전을 스탬프하고, 호출자가 컴파일 시점의 digest를 `ontology_content_digest`로 고정하면
다른 어휘로 조용히 응답하는 대신 **거부**합니다(불일치 409, 형식 오류 400 — 오타를
"서버가 다른 어휘를 들고 있다"로 보고하면 클라이언트가 잘못된 조치를 합니다). revision은
고정 대상이 아닙니다: 프로세스 수명 한정이므로 재시작 뒤 내용이 완전히 달라도 같은
번호를 다시 쓰고, 그러면 조용히 고정이 풀리는 pin이 됩니다. 이로써
`ontology_version_pin`은 route 존재가 아니라 **predicate를 양방향으로 실행해**
`runtime_probe_verified`로 등급이 매겨집니다(살아 있는 digest는 통과, 한 글자 다른
digest는 거부, 형식 오류는 거부). `credential_vault`에만 있던 runtime 검사 자리는
control→검사 dispatch로 일반화했고, `_RUNTIME_VERIFIED_CONTROLS`는 그 dispatch에서
**파생**합니다(같은 집합을 손으로 두 번 쓰면 갈라지고, 게시 판정을 결정하는 쪽이
조용히 이깁니다).

남은 경계 하나는 선언해 둡니다: `ontology_content_digest`는 `/ontology/search`에서는
query parameter이므로 OpenAPI 문서에 자동으로 실리지만, `/ontology/resolve`에서는 이미
`dict[str, str]` 본문을 받는 라우트의 느슨한 키이므로 **기계 판독 계약에는 실리지
않습니다**. 이 라우트는 모델을 만들지 않는 10개 본문의 선언된 경계
(`tests/test_api_request_contract.py::test_the_untyped_bodies_that_remain_are_the_ones_with_no_model`)
안에 있고 이번 변경도 그 경계를 넘지 않지만, 그 경계에 키 하나를 **더한** 것은
사실이므로 README에 적고 여기에도 적어 둡니다.

### Fixed — 개념 IRI가 서로 다른 두 개념에 같은 식별자를 발급했습니다

`concept.replace(" ", "-")`는 단사(injective)가 아닙니다. 측정: 개념 `활성 고객`과
따로 등록 가능한 `활성-고객`이 **동일한 IRI**를 발급합니다. 해석 응답에서는 혼란스러운
식별자일 뿐이지만 RDF 문서에서는 두 개념이 하나의 subject로 합쳐져 레이블·정의·계층이
병합됩니다. IRI 세그먼트에 올 수 없는 문자(`%` 먼저, 그 다음 공백·`/`·`?`·`#`·`[`·`]`)만
percent-escape합니다 — `urllib.parse.quote`는 비ASCII 전부를 인코딩해서 `고객`이
`%EA%B3%A0%EA%B0%9D`가 되고, IRI는 Unicode를 담을 수 있으며 이 export는 사람이 읽는
문서입니다. `resolve_terms`도 같은 함수를 쓰므로 정의가 하나입니다.

### Fixed — 해석 결과가 정의되지 않은 용어에 정의된 개념과 똑같은 IRI를 붙였습니다

`_INDEX`는 `dataset.terms`로 만들어지고 그것들은 dataset이 선언한 용어이지 등록된
개념일 필요가 없습니다. 측정: `/ontology/resolve`가 캠페인·전환·비즈니스 용어에 대해
term IRI를 게시하는데, 어휘는 그 중 어느 것도 정의하지 않습니다 — 정의된 개념의 IRI와
형태가 동일해서, 클라이언트는 찾아볼 수 있는 정의와 아무데도 닿지 않는 식별자를
구별할 수 없었습니다. 각 행에 `defined_in_vocabulary`를, 응답에
`undefined_resolution_count`를 둡니다. 해석 자체는 계속 돌려줍니다 — dataset을 가리키는
진짜 포인터이기 때문입니다.

### Fixed — 어휘 변경에 락이 없었습니다

`ontology.py`에는 `threading` 참조가 하나도 없었고, 비슷한 상태를 들고 있는 형제
스토어 둘(`catalog`, `graph_store`)은 측정된 check-then-act 손상 때문에 이미 재진입
락을 갖고 있었습니다. 임계 구역은 존재 확인 읽기부터 19줄 뒤의 저장 쓰기까지입니다.
`ontology_version.vocabulary_change_lock()`(재진입)이 어휘·alias index·revision
카운터·(승인 시)patch 상태를 한 구역으로 묶고, 공개 wrapper가 **존재 확인 읽기보다
먼저** 락을 잡습니다 — 읽기 뒤에 잡으면 창이 그대로 열려 있습니다. 회귀 테스트는
경쟁시키지 않고 **읽기 안에서** 첫 번째 writer를 멈춥니다: 이 구역에는 I/O도
GIL을 놓는 호출도 없어서 CPython에서는 창이 저절로 열리지 않고, 열 수 없는 테스트는
락이 하는 일을 보여줄 수 없습니다. 역검증: 공개 wrapper의 `with ...lock()`을
`if True`로 바꾸면 한 개념에 대해 `already_published: False`가 2건 나오고 revision이
2 올라갑니다.

### Fixed — 모듈 수준 가변 상태 2건이 autouse fixture 밖에 있었습니다

`tests/conftest.py`의 autouse fixture는 20여 개 파일이 격리 fixture를 갖지 않아
역순 실행에서 5건이 깨졌기 때문에 존재합니다. 그런데 그 fixture의 재고 목록과 그것을
지키는 `test_state_isolation.py`는 **둘 다 손으로 쓴 목록**이라, 새 스토어는 누군가
기억했을 때만 덮입니다 — 바로 이 fixture가 막으려는 배치가 한 단계 위에서 반복되고
있었습니다. 측정 결과 `authz._JWKS_CACHE`와 `observability._SINK_BREAKER`가 fixture에
없었고, 그것을 더럽히는 두 파일이 테스트마다 각자 치우고 있었습니다
(`test_honest_metrics.py`는 `_SINK_BREAKER["open_until"] = 0.0`을 다섯 곳에서,
`test_authz.py`는 `clear_jwks_cache()`를 세 곳에서). 전체 스위트에 테스트별 probe를
걸어 측정한 유출은 **두 스토어 모두 0건**입니다 — 지금 깨지고 있던 것은 없고, 잠재적
취약성입니다. 둘을 fixture로 옮기고, `tests/test_module_state_coverage.py`가 두 패키지의
모듈 수준 `dict`/`list`/`set`/`deque`를 **열거**해 각각이 "fixture가 복원함" 또는
"런타임에 변경되지 않음"으로 선언되었는지 검사합니다. 선언하지 않고 추가하면 여기서
실패합니다 — 작성자에게는 한 줄 판단이고, 그러지 않으면 다음 사람에게 파일 순서에
의존하는 실패가 됩니다. 이 검사의 "fixture가 claim한 것을 실제로 복원하는가" 부분은
처음에 파일 전체를 훑어서, 복원 줄을 지우고 snapshot 줄만 남겨도 통과했습니다(측정).
`finally:` 이후로 범위를 좁혀 역검증했습니다.

### Security — 마스킹이 선언된 세 근거 중 하나만 보고 있었습니다

POL-003(P0)은 "**PII, sensitive, confidential** tag 기반 masking을 지원해야 한다"이고
수락 기준은 "policy decision 결과에 **masking rule** 포함"입니다. 정책은 세 근거 중
하나만 읽고 rule은 전혀 게시하지 않았습니다:

    obligations["masking"] = [col.name for col in dataset.schema if col.pii]

그래서 **sensitive나 confidential로 분류된 컬럼은 공개되었습니다** — `ColumnMetadata`에
분류를 적을 자리가 없었고 그것을 마스킹하는 코드도 없었습니다. 그리고 판단은 어떤
컬럼이 마스킹되는지만 말하고 **어떤 근거로**인지는 말하지 않았으므로, 감사자는 PII
마스킹과 기밀 마스킹을 구별할 수 없고 선언된 세 근거 중 둘이 한 번도 조회되지 않았다는
사실도 알 수 없었습니다.

`ColumnMetadata.classification`을 두고 세 근거 전부가 마스킹하게 했습니다.
`obligations.masking_rules`가 컬럼마다 `bases`와 `action`을 담고,
`masking` 이름 목록은 형태를 유지합니다(`apply_mask`와 게시된 응답이 읽습니다).

**알 수 없는 라벨도 마스킹합니다** — `unrecognized_classification`을 근거로 보고합니다.
마스킹은 **보류하는** 통제이므로 fail-closed 방향은 이해하지 못한 것을 마스킹하는
쪽입니다: 라벨 오타 때문에 컬럼이 공개되는 것이 문제가 되는 실패입니다.
`pii: true`와 `classification: ["pii"]`는 같은 진술이고 어느 쪽이든 마스킹하므로 둘이
결과를 두고 어긋날 수 없습니다. 대소문자와 앞뒤 공백은 라벨을 무력화하지 못합니다.

`classification`은 `pii`와 **정확히 같은 방식으로** 거버닝됩니다 — discovery 표면에서
withhold하고(컬럼의 민감도 라벨은 PII 플래그만큼 노출적입니다), schema diff는 값을
공개하지 않으면서 그 필드가 바뀌었다고 보고합니다.

`browse.preview`의 마스킹 **floor도 같이 넓혔습니다**. floor가 `column.pii`만 읽고
있었으므로 정책이 confidential 컬럼을 더 이상 나열하지 않게 되면 그것이 공개됩니다 —
정책보다 좁은 floor는 floor가 아닙니다. 테스트가 소스에서 그것을 단언합니다.

이에 따라 POL-003은 `implemented`입니다. 하지 않는 것도 적어 둡니다: obligation의
action은 항상 `mask`이고(suppression이 아니라) 컬럼을 자동 분류하는 것은 없습니다 —
라벨은 `pii`와 마찬가지로 운영자가 선언합니다.

### Security — 카탈로그 변경 사유가 기록되지 않았고, 하나는 날조되었습니다

CAT-005의 수락 기준은 네 가지를 호명합니다: "변경 전후 diff, actor, timestamp,
**reason** 기록". 앞의 셋은 기록되고 있었고 **사유는 기록되지 않았습니다**.
`_build_dataset_payload`가 모든 카탈로그 쓰기에 `reason="ok"`를 하드코딩하는데 그것은
행의 **결과**이고 호출자의 변경 사유가 아니며, 사유를 받는 경로는
`POST .../deprecate` 하나뿐이었습니다. 측정:

    PATCH /catalog/datasets/{id} {"reason": "buyer audit reason"}
      -> 200, details 키: after, before, changes, tenant_id  (reason 없음)

호출자의 사유가 200과 함께 **버려졌습니다** — 요청 모델이 그 필드를 선언하지 않고
pydantic은 추가 키를 무시하기 때문입니다.

이제 네 경로 전부 `details.change_reason`으로 기록합니다. 사유를 요청 모델에 추가하지
않고 **원시 payload에서 읽는** 이유는, 그것이 변경에 **대한** 메타데이터이고 데이터셋
상태가 아니기 때문입니다 — 요청 모델의 필드는 `Dataset` 필드의 **부분집합**이어야 하고
(`tests/test_catalog_field_forwarding.py`가 단언합니다) `reason` 필드는 그 불변식을
깨뜨립니다. 모델 밖에서 읽는 키는 문서에 선언해야 클라이언트가 보낼 수 있으므로
`REQUEST_BODY_EXTRA_PROPERTIES`에 등록했습니다 — **request-contract 테스트가 바로 그
누락을 잡았습니다**.

키는 사유가 없을 때도 `None`으로 **게시합니다**. 생략하면 "호출자가 사유를 주지
않았다"와 "이 표면은 사유를 기록하지 않는다"를 독자가 구별할 수 없고, 그 구별이 바로
이 행이 존재하는 이유입니다.

**이 작업에서 제 테스트가 날조된 기본값 하나를 잡았습니다.** `deprecate`는
`payload.get("reason", "deprecated")`로 사유 없는 호출을 **문자열 "deprecated"** 라는
사유로 바꿔 기록하고 있었습니다 — 호출자가 주지 않은 사유를 준 것처럼 적은 것이고,
이 표면이 절대 하지 말아야 할 한 가지입니다. 네 경로 모두 `None`을 보고합니다.
`deprecate`의 `details["reason"]`도 `change_reason`으로 통일했습니다 — 한 값에 두 키가
있으면 한 키로 필터링하는 원장 독자가 넷 중 셋을 찾거나 하나만 찾습니다.

빈 문자열·공백만·문자열 아님은 모두 `None`입니다("빈 사유를 보냈다"와 "사유를 보내지
않았다"는 같은 사실이고, 전자를 사유로 기록하면 산문이 있어야 할 자리에 빈 문자열이
들어갑니다). 512자 상한을 둡니다 — 호출자가 주는 값이고 행은 보존됩니다.

### Security — 거부된 카탈로그 변경이 감사 기록을 남기지 않았습니다

`CLAUDE.md`가 이 제품의 거버넌스 불변식을 선언합니다: 카탈로그 mutation과 browse/query
경로에 정책 평가 **그리고** evidence 기록이 따른다. browse 경로는 거부에서도 양쪽을
지켰지만(`browse.py`가 `ingest_event(decision="denied", ...)`를 호출합니다), 네 개 카탈로그
mutation은 정책을 평가하고 바로 raise해서 **거부된 시도가 decision만 남기고 감사 행을
남기지 않았습니다**. 권한 없는 actor로 각 verb를 측정:

    PATCH  /catalog/datasets/{id}            -> 403  decisions +1  audits +0
    POST   /catalog/datasets/{id}/publish    -> 403  decisions +1  audits +0
    POST   /catalog/datasets/{id}/deprecate  -> 403  decisions +1  audits +0
    POST   /catalog/datasets                 -> 403  decisions +1  audits +0

거부된 시도는 **감사자가 정확히 찾는 것**인데 `/audit/events`와
`/catalog/datasets/{id}/audit` 어디에도 없었습니다.

`tests/test_governed_write_evidence.py`는 이미 이 짝을 단언하고 있었지만, 그
`GOVERNED_WRITES` 목록은 `/ontology/concepts`·`/ontology/patches`·`/graph/edges` —
감사를 수행하는 `_authorize_graph_write`를 공유하는 세 라우트 — 만 덮습니다. 네 개
카탈로그 mutation은 인라인으로 권한을 검사하고, **손으로 쓴 governed-write 목록**이
바로 그것들을 빼놓는 모양입니다. 새 테스트는 커버리지를 **라우트 테이블에서 유도**하므로
다섯 번째 mutation이 추가되면 케이스를 받거나 의식적으로 제외되기 전까지 실패합니다.

응답이 숨기는 경우에도 원장은 실제 사유를 적습니다 — 범위 밖 데이터셋은 상태와 본문이
존재 oracle이 되지 않도록 일반적인 detail과 함께 404를 돌려주고, 거부된 호출자가 읽을 수
없는 원장은 엔진이 준 사유를 유지합니다. browse가 이미 하는 것과 같은 분리입니다.

### Security — 동시성: 유실된 쓰기, 거짓 증빙, 그래프 모순

4번째 적대적 스윕(8 에이전트, 모든 발견을 독립 재현으로 검증)이 올린 15건 중
`high` 4건이 여기 있습니다. FastAPI는 이 패키지의 `def` 핸들러를 워커 스레드풀에서
실행하므로 두 요청이 **실제로 교차**하는데, 모듈 dict에 대한 read-modify-write를
직렬화하는 것이 아무것도 없었습니다.

- **동시 PATCH가 쓰기를 유실시키고, 감사 원장이 그 유실을 `success`로 인증했습니다.**
  읽기와 쓰기 사이에서 한쪽 작성자를 멈춰 교차를 강제해 측정:

      PATCH description=FIRST  -> 200
      PATCH steward=SECOND     -> 200
      저장 상태: description=FIRST, steward=<변경 없음>, version=1.0.1
      audit:  success {"description": "FIRST"}
      audit:  success {"steward": "SECOND"}

  유실된 쓰기도 나쁘지만 **감사 행이 더 나쁩니다**. 이 제품이 선언한 거버넌스
  불변식은 모든 거버닝 쓰기에 정책 판단과 감사 이벤트가 따른다는 것인데, 여기서
  원장은 **저장소에 없는 변경을 인증**했습니다 — 이벤트가 작성자 자신의 `updates`로
  만들어지고 `_DATA`를 다시 읽지 않으므로 알아챌 수 없습니다. 직렬화 없이 동시 PATCH
  50건이 version을 25만 전진시켰습니다. `catalog`에 재진입 가능한 mutation lock을 두어
  네 개 mutation 전부를 감쌌습니다.
- **동시 생성이 같은 생성 id를 여러 호출자에게 주고 데이터셋을 조용히 파괴했습니다.**
  id 없는 동시 생성 8건이 각각 200을 받고 카탈로그는 5개만 늘었습니다(한 id가 세
  호출자에게 간 경우도 있습니다). `len(_DATA) + 1`과 `if dataset_id in _DATA`와 저장이
  세 개의 분리된 단계였기 때문입니다. 락 안에서 **비어 있는 첫 id를 스캔**합니다 —
  개수는 "어떤 id가 비었나"라는 실제 질문에 답하지 않습니다(호출자가 `dataset-NNN`
  형태 id를 직접 등록한 경우 순차 실행에서도 충돌합니다).
- **카탈로그와 그래프가 영구히 모순되었습니다.** 두 개의 동시 schema PATCH가 카탈로그에는
  한 순서로, 그래프에는 반대 순서로 적용되어(30회 중 11회 측정) 그래프가 카탈로그에
  없는 `pii: true` 컬럼을 보유했습니다 — `/search/semantic`이 그것을 최상위로 반환하고
  `/browse/{id}/schema`는 마스킹할 수 없었습니다(카탈로그에 없는 컬럼이므로).
  `api`가 mutation lock을 **mutation과 그래프 미러에 걸쳐** 잡습니다.
- **lineage 엣지를 선언한 쪽이 아닌 쪽의 변경이 그 엣지를 삭제했습니다.** `A -> B`는
  A의 `lineage_outputs`나 B의 `lineage_inputs` **어느 쪽으로도** 선언되고 미러는 양쪽에서
  만드는데, reconcile은 변경된 데이터셋 자신의 절반만 봤습니다. 상류만 선언한 쌍에서
  측정: 상류 seed 후 엣지 존재 → 하류 seed(아무 변경이나, 또는 시작 부트스트랩) 후
  엣지 소멸, 카탈로그는 계속 선언. 시작 부트스트랩이 모든 데이터셋을 차례로 seed하므로
  나중에 seed된 쪽이 다른 쪽 선언을 지웠습니다. 이제 **어느 엔드포인트도 선언하지 않을
  때만** 제거합니다.
- **`/search/semantic`이 온보딩 중 500을 반환했습니다** — `_embeddings`를 순회 중에
  증가시켜 `RuntimeError: dictionary changed size during iteration`. 리더 2 + 라이터 2로
  42건 중 17건(40%) 실패. 보고된 한 줄만 스냅샷하지 않고 **스토어에 락**을 넣었습니다:
  `_edges`는 `delete_edge`/`delete_node`가 통째로 재구성하는 동안 `edges_for`/`traverse`가
  순회하고, `delete_node`는 세 컬렉션을 순차로 바꾸므로 리더가 임베딩이 이미 사라진 노드를
  볼 수 있었습니다. 보고된 줄만 고치면 나머지가 남습니다.

회귀 테스트는 **경쟁을 기다리지 않고 교차를 강제**합니다 — 한쪽 작성자를 읽기와 쓰기
사이에서 멈추면 락이 없을 때 매번 실패하고 있을 때 매번 통과합니다. 임계 구역 **안의**
barrier는 검증하려는 락과 교착하므로 barrier가 아니라 일시 정지입니다. 각 수리를
되돌려(락을 no-op 컨텍스트 매니저로 교체) 해당 테스트가 실패하는 것을 확인했습니다.
`test_an_edge_read_survives_edges_being_rebuilt`는 락 없이도 통과한다는 점을 자기
docstring에 적어 둡니다 — 리스트 재할당은 CPython에서 예외를 내지 않으므로 그것은
재현이 아니라 하드닝입니다.

이에 따라 CAT-005와 LIN-001은 `implemented` → `partial`입니다(각각 수락 기준의
before/after diff와 source/job/target이 여전히 없습니다). NFR-SEC-005는 `implemented`를
유지하되 비고에 "원장이 100% 완전하면서 부분적으로 거짓이었다"는 사실을 적습니다.

### Security — 테넌트 경계와 존재 oracle

- **SQL 안전성 게이트가 증명하지 못하는 것을 증명했습니다.** 두 가지 unsoundness를
  allowlist = `customer`로 측정했습니다. (1) 토큰 `[A-Za-z_][\w.]*`가 `$`와 0x80 이상
  바이트에서 끊겨 `FROM customer$pii_raw`를 `customer` + 버려진 alias로 쪼갰습니다 → 경고
  **0건**. PostgreSQL identifier continuation은 `[A-Za-z\200-\377_0-9$]`이므로 엔진은 단일
  테이블 `customer$pii_raw`를 읽습니다. 이미 critical로 닫은 comma-FROM 우회와 같은 부류입니다.
  (2) 함수 allowlist가 없어 무인자·정수인자 호출이 안전 경로에 남았습니다 →
  `pg_terminate_backend(12345)`·`lo_unlink(1)`·`pg_sleep(100000)`·`pg_reload_conf()` 모두
  경고 0건. PRD BRW-005는 이를 **P0**로 선언합니다. deny-list는 무한집합이라 증명할 수 없으므로
  allowlist로 막습니다. 실행 엔진이 없으므로(`execute_query`는 mock) 함수 부작용과 `$`의 의미는
  측정한 것은 게이트의 판정입니다 — 어느 쪽이든 결함은 **거짓 인증**입니다.
  **정정**: PostgreSQL 쪽도 추론이 아니라 측정입니다. 이 발견에 대한 독립 검증이 일회용 UTF-8
  클러스터를 띄워 `customer`·`customer$pii_raw`·`customer×pii_raw`를 세 개의 서로 다른 테이블로
  만들고, `SELECT count(*), max(secret) FROM customer$pii_raw` → `1 | ssn-123-45-6789`,
  `SELECT count(*) FROM customer` → `0`을 확인했습니다. 즉 이 validator가 `customer`로 인증한
  인용 없는 참조는 실제로 다른 행을 가진 다른 테이블로 해석됩니다. 이 저장소에서는 아무것도
  실행되지 않으므로(`execute_query`는 mock) 여기 테스트가 측정하는 것은 게이트의 판정입니다.

- **purpose binding이 공백 하나로 우회**되었습니다. `policy.evaluate`가 `action`은
  `.strip().lower()`로 정규화하면서 `purpose`는 `.lower()`만 했습니다. 측정:
  `'external-export'`·`'EXTERNAL-EXPORT'` → 403, `' external-export'` → **200**
  (preview와 governed query 양쪽). 기록된 결정은 `effect: allow`였으므로 **증빙 원장이 그
  반출을 정책 승인으로 증명**했습니다 — 우회보다 이게 더 나쁩니다. 대소문자는 막히므로
  통합 담당자가 공백 민감성을 의심할 단서가 없었습니다. 같은 필드의 거울 결함: high
  sensitivity row-level filter가 정확 비교여서 `'Analysis'`·`' analysis'`에서 조용히
  사라졌습니다(거부 아님, obligation 누락). 진입점에서 한 번 정규화합니다.
- **`GET /ontology/term/{term}/graph`가 미인증 호출자에게 모든 테넌트의 dataset id를
  제공**했습니다 — 정책 평가 0, 감사 이벤트 0. 같은 사실을 주는 형제 두 라우트는 거부합니다
  (`/ontology/concept/{concept}` → `dataset_ids: []`, `withheld 4`; `POST /llm/search` → 403).
  이 payload의 **세 번째** 유출 경로입니다. 제품이 스스로 게시하는 guardrail("No unauthorized
  dataset existence disclosure")과 거버넌스 invariant 양쪽에 어긋납니다. 네 번째를 잡기 위해
  게시된 응답 계약에서 `dataset_ids`를 반환하는 라우트를 **열거**합니다.
- **그래프 쓰기 경계가 fail-open**이었습니다. `create`는 소유 테넌트를 카탈로그에서 해석할 수
  없는 유일한 분기이고 `target_tenant_id`를 받지 못해 테넌트 검사를 건너뛰었습니다. 측정:
  tenant=demo `data-admin`이 `zeta-secret:customer_email`을 읽으면 **404**, 쓰면 **200**,
  `pii: true → false`. 읽을 수도 없는 컬럼의 PII 분류를 외부 테넌트가 조용히 뒤집었고 그
  메타데이터는 semantic search와 graph query가 씁니다. 엣지는 두 끝점 모두 검사합니다.
  남은 구별(없는 데이터셋 접두사는 허용 / 외부 테넌트는 403)은 `admin` 역할이 필요해
  익명·analyst로 닫은 oracle보다 좁으며, 닫지 않은 이유와 함께 테스트에 명시했습니다.
- **preview 거부가 원장을 통해 존재를 누출**했습니다. HTTP 본문은 이미 동일했지만 호출자
  자신의 `GET /policy/decisions`는 외부 id에 0행, 없는 id에 1행이었습니다. 형제 라우트는
  모두 `evaluate_dataset_scope_refusal`을 쓰는데 preview만 빠진 **놓친 호출자**였습니다.

- 데이터셋을 **지목할 수 있는 모든 수단**(경로 파라미터, 요청 본문, 쿼리
  파라미터, 변경 라우트, what-if 리소스)에 대해, 타 테넌트 데이터셋과 존재하지
  않는 id의 응답이 **상태 코드와 본문까지 동일**해집니다. 같은 결함이 여섯 번
  반복됐기 때문에 검사도 URL 모양이 아니라 명명 수단 단위로 열거합니다.
- `/policy/decision`의 측면 채널을 닫았습니다. 인증 없이 호출 가능했고 데이터셋의
  존재 여부와 **소유 테넌트까지** 드러냈으며, 같은 내용을 읽는 형제 라우트는 이미
  403이었습니다. (원 MVP 병합 이후 main에서 동일하게 재현되는 사전 결함입니다.)
- 증빙 표면을 통한 oracle도 닫았습니다: 거부 기록이 prober가 읽을 수 있는 원장에
  나타나는 방식이 "비어 있는 id일 때만 보이는" 신호가 되지 않도록, 두 거부를 모두
  prober 범위 밖에 파일링합니다. 소유 테넌트의 감사자는 자기 자산에 대한 시도를
  그대로 봅니다.
- 카탈로그 discovery / 데이터셋별 조회 / 그래프 읽기 / 증빙 읽기 / SHACL 요약 /
  steward 큐를 전부 호출자 테넌트로 범위화했습니다. 범위에서 빠진 항목은
  `withheld_*` 카운터로 **선언**합니다 — 짧은 목록이 빈 큐로 읽히지 않도록.
- preview row를 지목된 데이터셋의 스키마로 제한했습니다(다른 데이터셋의 PII
  컬럼에 도달하던 경로 차단). 선언된 PII 컬럼은 정책 obligation이 빠뜨려도
  마스킹됩니다 — 마스킹은 최선이 아니라 하한입니다.
- 정책 엔진의 fail-open을 닫았습니다: 평가할 수 없는 action에 `allow`를 주고
  있었고, 공개된 action 이름 10개 전부가 그 경로였습니다.
- SQL validator 우회 3건, 수식된 테이블 우회, 금지 키워드의 부분 문자열 일치를
  고쳤습니다(이제 단어 단위).
- OIDC: `oidc-verify`가 operator 설정만 신뢰합니다(요청 본문이 trust anchor를
  공급해 self-signed platform-admin을 만들던 경로 차단). group→role 매핑은
  tenant scoped이고 매핑마다 audit event를 남깁니다.
- DSN 자격증명 노출과 log sink 자격증명의 공개 manifest 노출을 제거했습니다.
- 호출자가 제어하는 작업량과 메모리 증가에 상한을 두었습니다(쿼리 길이, 개념
  어휘, 제안 큐, 두 증빙 원장). 상한이 생기면 창의 길이로는 "기록됐는가"에 답할
  수 없으므로 단조 카운터를 함께 추가했습니다.

### Fixed — 증빙 페이지가 자기 행을 중복시키며 실제 행을 빠뜨렸습니다

`list_policy_decisions`와 `list_persisted_audit_events`는 페이지를
`reversed(_POLICY_DECISION_LOG)` — **살아 있는 리스트에 대한 lazy iterator** — 로
만들었고, `record_policy_decision`은 같은 리스트의 앞부분을
`del _POLICY_DECISION_LOG[:-MAX_IN_MEMORY_POLICY_DECISIONS]`로 잘라냅니다. 순회 중에
앞이 사라진 역방향 iterator는 밀린 원소를 다시 방문하고 다른 원소를 건너뜁니다 —
그래서 한 페이지가 같은 `decision_id`를 두 번 담고 그만큼의 실제 행을 조용히
빠뜨릴 수 있었습니다. cap에 도달한 로그에 리더 2 + 라이터 2로 측정:

    pages read 14303, 중복된 decision_id를 담은 page 142

수리는 lock이 아니라 **snapshot**입니다. 리스트의 `list(...)`는 한 번의 C 레벨
복사이므로 trim의 앞이나 뒤에서 찍히고 trim 도중에는 찍히지 않습니다 — 읽기 경로에
경합을 추가하지 않습니다. `catalog.list_audit_events`는 이미 이렇게 읽고 있었고,
그래서 `evidence`의 페이지만 찢어졌습니다. 수리 후 같은 조건에서 14817 페이지 중
**0건**입니다.

테스트가 숨기지 않고 적어 두는 한계: 페이지는 시점 뷰이므로 snapshot 이후에 추가된
행은 **정당하게** 없습니다. 단언하는 것은 어떤 행도 **두 번** 나타나지 않는다는 것과
창이 선언된 상한 안에 머문다는 것이고, 페이지가 일관된 트랜잭션 읽기라는 것이
아닙니다 — in-memory fallback 로그는 그것을 제공하지 않습니다(append-then-trim은 두
단계라 cap보다 한 행 많은 상태가 보일 수 있고, 그것은 찢어진 페이지가 아니라 여분의
한 행입니다).

이 테스트를 쓰면서 제 테스트 자신의 결함을 하나 잡았습니다: 두 라이터 스레드가 모두
`written-0`, `written-1`…을 만들어서 리더가 센 중복이 로그의 것이 아니라 테스트의
것이었습니다. 라이터마다 고유한 tag를 붙였습니다.

### Fixed — 아무것도 바꾸지 않은 요청이 증빙을 만들어냈습니다

같은 스윕의 세 건. 모양이 같습니다 — **변경하지 않은 요청이 변경한 것처럼 기록**되어
원장과 version 수열과 `updated_at`이 일어나지 않은 작업을 서술했습니다.
`publish_dataset`은 이미 정답을 구현하고 있었고(이미 published인 경우를 guard하고
그 시도를 no-op으로 기록), 다른 두 경로는 그렇지 않았습니다. `crm-customer-master`에서 측정:

    POST .../deprecate x3   -> 200, 200, 200
                               version 1.0.1 -> 1.0.2 -> 1.0.3
                               "dataset.deprecate / success" 원장 행 3개
                               snapshot 3개 추가
    PATCH {"actor": "admin"} -> 200
                               version bump, updated_at 이동, snapshot 추가, 변경 0
    GET  .../schema-versions -> ["1.0.0", "1.0.0", "1.0.0", "1.0.0"]

- **재실행된 deprecate**가 매번 version을 올리고 원장에 새 `success` 행을 쓰고 snapshot을
  추가했습니다 — 원장 독자가 재시도와 세 번의 의도적 deprecate를 구별할 수 없었습니다.
- **빈 PATCH**(`{"actor": "admin"}`은 patch 가능한 필드를 하나도 지정하지 않습니다)가
  version과 `updated_at`을 움직였습니다 — 수정하지 않은 요청에 대해 데이터셋이 수정 시각을
  주장했습니다. 값이 전부 `None`인 본문도 같습니다(검증은 통과하고 필드별로 skip됩니다).
  그래서 guard는 요청된 집합이 아니라 **실제 적용된 집합**을 봅니다 — 요청된 집합을 봤다면
  이 경우를 놓쳤습니다. 같은 이유로 원장의 `changes`/`before`/`after`도 실제 적용된
  필드만 담습니다(이전에는 skip된 필드가 적용된 변경으로 기록되었습니다).
- **`/schema-versions`가 같은 버전을 반복**했습니다. snapshot은 모든 mutation마다
  기록되고(컬럼뿐 아니라 lineage·mapping·tag·status·score도 담아 drift 탐지가 읽습니다)
  목록은 snapshot당 한 줄이었으므로, 스키마가 바뀌지 않은 patch가 버전을 복제했습니다.
  diff는 버전을 dict 키로 해석하므로 애초에 버전당 하나만 도달할 수 있었습니다 — 목록이
  넷을 광고하고 diff가 하나를 서비스했습니다. 이제 목록의 **모든 항목이 주소 지정
  가능**하고, 실제 스키마 변경은 여전히 새 항목을 만듭니다.

세 경우 모두 **감사 행은 유지합니다** — 재실행된 요청은 실재하는 사건이고 숨기는 것이
반대 방향의 결함입니다. 바뀐 것은 행이 `noop: true`를 달고 데이터셋이 그대로 반환된다는
점입니다. 각 guard를 되돌려 해당 테스트가 실패하는 것을 확인했고, 실제 변경이 여전히
bump된다는 테스트는 guard 없이도 통과하므로 그 셋은 guard의 존재만 탐지하는 것이
아닙니다.

### Fixed — 문서화된 개발자 경로가 테스트를 한 건도 돌리지 못했습니다

- **문서화된 설치로 문서화된 테스트 명령이 0건을 수집했습니다.** `requirements-dev.txt`는
  README·CLAUDE.md가 설치하라고 말하는 산출물이고 `PYTHONPATH=src pytest`는 그 다음에
  실행하라고 말하는 명령입니다. 깨끗한 venv에서 측정:

      pip install --require-hashes -r requirements-dev.txt   -> ok
      PYTHONPATH=src pytest
        -> ERROR tests/fuzz/test_fuzz_properties.py
           Interrupted: 1 error during collection
           0건 실행

  lock에 `hypothesis`·`sortedcontainers`·`sqlalchemy`·`greenlet`이 빠져 있었습니다 —
  `pyproject.toml`의 `dev` extra가 첫째와 셋째를 선언하고 **파일 자신의 헤더가 그 extra로
  컴파일했다고 주장**하는데도 그랬습니다. CI는 영향받지 않았습니다(CI는 넷을 모두 pin하는
  `requirements-test.txt`를 설치합니다) — 그래서 파이프라인의 어떤 것도 알아챌 수
  없었습니다. 수리 후 같은 깨끗한 venv에서 **968 passed**입니다.
  추가된 네 개는 **CI가 pin한 버전 그대로**입니다. 자유 해석은 `hypothesis==6.169.1`과
  `sqlalchemy==2.1.4`를 잡는데 CI는 `6.156.6`/`2.0.51`을 pin하고, SQLAlchemy는
  `src/sdp/graph_store.py`와 `src/sdp/config.py`가 올라서는 라이브러리입니다 — minor가
  갈리면 로컬 green이 CI red을 가립니다. 네 개만 묶는 `constraints-dev.txt`를 두어
  다른 pin은 전혀 움직이지 않습니다(그래서 pip-compile로 생성되는 Docker lock
  `requirements-graph.txt`와의 합의도 그대로 유지됩니다).
  `tests/test_dependency_locks.py`가 이제 강제합니다: dev extra가 선언한 모든 패키지가
  lock에 있는지, 스위트가 import하는 것을 설치할 수 있는지, dev와 CI가 공유 pin마다
  일치하는지, 각 lock의 헤더가 자신을 재생성하는 **실행 가능한** 명령인지.
  일치 테스트에는 `tzdata` 하나를 **사유와 함께 선언된 예외**로 둡니다 — 전역 합의를
  강제하려면 pip-compile로 생성되는 Docker lock(자체 `constraints-graph.txt`가
  `greenlet==3.2.5`를 pin하는)까지 재생성해야 하므로, 이 저장소가 현재 충족하지 못하는
  gate를 선언하지 않습니다. 예외가 더 이상 실재하지 않으면 테스트가 그 예외를 지우라고
  실패합니다.
- **README의 로컬 설치 블록이 어느 셸에서도 통째로 실행되지 않았습니다.** ```bash 펜스
  안에 PowerShell 활성화 경로(`.venv/Scripts/Activate.ps1`)가 있고 그다음 줄은 POSIX 전용
  `VAR=value command` 구문이었습니다. POSIX 활성화로 바꾸고 Windows 대응 경로를 주석으로
  달았습니다.
- **`docs/enterprise-readiness.md`의 두 명령이 `PYTHONPATH=src`를 빼먹었습니다.**
  문서화된 설치는 프로젝트 자체를 설치하지 않으므로 `uvicorn sdp.api:app`은
  `ModuleNotFoundError: No module named 'sdp'`로 실패합니다(측정 확인).
  같은 스윕이 `AGENTS.md`의 `pip install -e .[dev]` 경로도 같은 결함이라고 보고했는데
  **그것은 재현되지 않았습니다** — editable 설치는 실제로 동작하고 `PYTHONPATH` 없이
  import됩니다. 그래서 그 줄은 고치지 않았습니다.
- **컨테이너 healthcheck 경로를 문서가 틀리게 적고 있었습니다.** README와 CLAUDE.md는
  `/health`를 노출한다고 했지만 `Dockerfile`과 `docker-compose.yml`은 `/healthz`를
  조회합니다 — README의 더 아래 단락은 그 구분(상수 응답 vs 백엔드 준비 상태 503)을
  정확히 설명하고 있어서 같은 문서가 자신과 모순이었습니다.

### Fixed — 문서화된 워크플로가 실제로 동작하지 않던 것들
- **운영 콘솔이 유효한 actor에게 "플랫폼이 고장났다"고 보고**했습니다. 측정
  (`?user=external-analyst` — 출하되고 문서화된 유효 actor, 단 그 테넌트는 콘솔이 조회하는
  데이터셋을 소유하지 않음): connector probe가 **404**(테넌트 범위 — 경계가 동작한 것),
  나머지 패널은 200인데 badge는 `evidence load failed: connectors`였습니다. 버킷 두 개로는
  부족했습니다: 4xx는 게이트가 **이 요청**을 거부한 것이고, 플랫폼 실패는 5xx(또는 클라이언트가
  읽을 수 없는 상태)뿐입니다. Chromium 실측: signed-out → `signed-out view - add ?user=`,
  external-analyst → `refused for this actor: connectors`, analyst/admin →
  `ready for pilot review`. 패널 힌트도 버킷별로 다릅니다 — actor를 **보낸** 사람에게 "actor가
  필요합니다"라고 말하는 것은 두 번째 오답입니다. 새 버킷에 상태 allow-list를 쓰지 않았습니다:
  그게 이전 결함의 원인이고, 그것을 금지하는 테스트가 제 첫 시도를 잡았습니다.
- **반쯤 적용된 tenant 마이그레이션이 영구히 복구되지 않았습니다.** `_add_tenant_column`이
  컬럼이 이미 있으면 **자기 backfill 전에** 반환했습니다. 이 메서드는 ALTER만 하는 형태로 먼저
  출시되었으니, 그 빌드로 업그레이드된 SQLite 원장은 전부 컬럼이 있고 backfill이 영원히 돌지
  않습니다. 측정(payload에 복구 가능한 tenant가 있는 원장): 현재 스토어로 열어도
  `['unresolved']` — 소유 테넌트의 감사자가 모든 과거 행을 잃습니다. SQLite는 문서화된
  데모/파일럿 배포(영속 볼륨)이므로 정확히 이 in-place 업그레이드 경우입니다. backfill이 매번
  돌고 미복구 행만 건드리므로 idempotent이며, 복구 불가한 행은 `unresolved`로 남습니다.
- **drafter가 자기 validator가 거부하는 SQL을 내보냈습니다**(이 부류 세 번째). source table
  이름이 SQL 절 키워드(`order` 등 24개)와 겹치면 파서가 테이블 목록을 벗어나 `None`을 반환하고
  validator가 `unauthorized_table_reference`로 거부합니다 — 측정: draft **200** → execute
  **400**. 문서화된 draft-then-execute 흐름에서 제품이 자기 출력을 거버넌스 위반으로 고발하는
  셈이고, `FROM order`는 인용 없는 예약어 SQL이라 PostgreSQL도 거부합니다. 명확한 사유와 함께
  거부하고, 더불어 완성된 질의를 **자기 validator로 자체 검사**해 네 번째 원인을 보고 없이
  잡습니다(앞의 둘은 `interval '<n> day'` 리터럴과 이 절 키워드였고, 하나씩 고쳐졌습니다).
- **선언된 컬럼명을 조용히 바꾸고 원래 이름을 보고**했습니다. `order amount` → SQL은
  `order_amount`, `requested_columns`는 `order amount`, assumptions는 "카탈로그에서 검증된
  컬럼만 사용" — 응답이 스스로 모순이었고 구매자는 창고가 `column "order_amount" does not
  exist`라고 답할 때 알게 됩니다. 변환은 유지하되(인용 식별자는 이 게이트가
  `literal_values_not_allowed`로 거부하므로 실행 불가, 하이픈 차단 계약도 존재)
  `emitted_identifiers`로 보고하고, 다른 선언 컬럼과 충돌하는 **모호한 변환은 거부**합니다 —
  매핑이 injective가 아니라 엉뚱한 컬럼을 집계할 수 있었습니다.
- **`POST /browse/query`가 500**이었습니다. `profile.row_count`가 JSON 문자열이면
  (`profile`은 `Dict[str, Any]`이고 `POST /catalog/datasets`가 그대로 저장합니다)
  `_row_count_estimate`가 `TypeError`로 죽어 그 데이터셋의 governed query 경로가 영구히
  죽었습니다. 500보다 중요한 건 crash 위치입니다 — **정책 결정과 감사 기록 사이**에
  떨어져 `decisions +1 audits +0`, CLAUDE.md가 타협 불가로 선언한 짝이 깨졌습니다. 모든
  타입을 열거해 처리하고, 숫자가 아닌 값은 추정치로 라벨하지 않고
  `unusable_catalog_profile_row_count`로 보고합니다. 제 첫 수정은 `float(v) != int(v)`를
  써서 `NaN`에 `ValueError`, `Infinity`에 `OverflowError`를 냈고(둘 다 Python `json`이
  리터럴로 받으므로 **같은 함수의 두 번째 미포착 500**이었습니다) `10**30`도 오분류했습니다
  — 값 열거가 잡았습니다.
- `POST /enterprise/auth/oidc-preview`가 **운영자 role map의 열거 oracle**이었습니다.
  측정(`SDP_OIDC_GROUP_ROLE_MAP={"acme-finance": {"admins": ["platform-admin"]}}`, 자격증명
  없음): 임의 subject·tenant로 `groups: ["admins"]`를 보내면 200과 함께
  `roles: ["platform-admin"]`, `tenant_scope: "acme-finance"`가 돌아왔고 매핑되지 않은 group은
  빈 scope·빈 role이어서 **구별 가능**했습니다 — group 이름을 하나씩 추측해 배포의 group→role
  정책 전체와 유효한 tenant scope를 읽을 수 있었습니다. trust anchor를 request body에서 거절한
  이유, 이 라우트의 원장 기록에 actor를 요구한 이유와 같은 범주입니다. 수정은 좁습니다: 호출자가
  보낸 `role_map`과 저장소 상수인 기본 map은 비밀이 아니므로 그대로 두고, actor 없는 호출에서
  `SDP_OIDC_GROUP_ROLE_MAP`만 쓰지 않습니다. 매핑된 group과 매핑되지 않은 group의 응답은 이제
  이름을 제외하면 동일합니다(이 제품이 외부 테넌트 데이터셋과 없는 id에 적용하는 것과 같은 규칙).
- 같은 라우트가 **미인증 증폭기**였습니다. claim 목록이 개수·길이 모두 무제한이고 group 이름이
  `groups`와 `group_role_bindings[].group_name`에 두 번 돌아왔습니다. 측정, 요청 1건:
  group 10 → 1,162 B / group 1,000 → 72 KB / group 20,000 → 1.50 MB(135 ms) /
  group 100,000 → **7.58 MB**(642 ms), 그리고 2 MB짜리 group 이름 하나 → **4.00 MB**
  (요청보다 큰 응답). 상한은 256개/256자이고 지금은 각각 17.8 KB와 1.2 KB이며, 잘린 양은
  `declared_group_count`/`withheld_group_count`와 `...[truncated]` 표시로 선언합니다.
  `observability.py`의 무제한 관측 행과 같은 결함 범주를 다른 표면에서 만난 것입니다.
  이 상한의 **첫 구현은 권한 결과를 조용히 바꿨습니다**: 길이 제한을 `_claim_values` 안에 두어
  group→role 조회에 쓰이는 값까지 잘랐는데, map의 **키**는 자르지 않으므로 256자를 넘는 정상적인
  group 이름이 자기 map 항목과 더 이상 일치하지 않았습니다(측정: 300자 group 이름 →
  `roles: []`, 이전 `["data-analyst"]`). 부여가 아니라 보류이므로 fail-closed이지만 조용했고,
  group이 개수 상한 안에 있었으므로 `withheld_group_count`가 0이어서 사라진 이유를 알 수 없었습니다.
  매칭은 실제 값으로 하고 **내보낼 때만** 자릅니다 — 증폭기 수정에 필요했던 것은 그것뿐이었습니다
  (커진 것은 응답이었습니다). 개수 상한은 매칭에도 적용되며(group당 작업량이 미인증 호출자가
  곱할 수 있는 비용), 그쪽은 `withheld_group_count`로 선언합니다.


- 문서화된 draft→execute 워크플로에 **통과 경로가 없었습니다**. 통과합니다.
- 제안→승인→노출 루프가 두 개의 단절된 개념 저장소 때문에 승인에서 멈춰
  있었습니다. 승인이 실제로 노출로 이어집니다.
- 온보딩한 데이터셋이 그래프에 전혀 도달하지 않았습니다(`POST /catalog/datasets`
  200 직후 `/graph/nodes/<new>` 404). 이제 도달하고, **삭제도 반영**됩니다 —
  미러가 append-only여서 카탈로그에서 제거된 PII 컬럼이 그래프에 남아 semantic
  search 최상위 결과로 나왔습니다.
- DCAT/JSON-LD export가 소비 불가능했습니다. `@id` 키워드, 실제 컨텍스트 문서,
  그리고 **중첩 속성**까지 매핑했습니다(distribution과 business mapping의
  속성들이 conforming 프로세서에서 전부 버려지고 있었습니다 — pyld로 확인).
- `/llm/draft-query`가 모든 실패에 200을 답하고 증거를 남기지 않았습니다.
- `dataset_ids` 누락 시 500, 문자열 아닌 `user`/`purpose`에 500 → 400.
- 운영 콘솔이 미인증 뷰에서 스스로를 "evidence load failed"로 보고했습니다.
  분류를 상태 코드 allow-list에서 **actor 유무**로 바꿨으므로 어떤 4xx로 바뀌어도
  다시 깨지지 않습니다. actor 안내 문구도 죽은 코드였습니다 — 이제 표시됩니다.
- 증빙 팩이 공개한 proof 링크를 그대로 따라가면 403이었습니다. 열린 링크와
  actor가 필요한 링크를 분리해 게시합니다.
- 죽은 log sink가 API 처리량의 상한이 되지 않도록 breaker를 넣고, sink export를
  event loop에서 내렸습니다.
- 마이그레이션이 끝까지 실패하면 컨테이너가 기동을 거부합니다.

- URL에 credential을 담은 http(s) 로그 sink는 **단 한 건도 전송되지 않았습니다**.
  URL 전체를 `urllib`에 넘겨 userinfo가 연결 host로 남았기 때문입니다 — Loki·Elastic·
  서명 webhook의 문서화된 push URL 형태가 전부 여기에 해당합니다. 측정:
  `https://sdp-ingest:TOKEN@logs.example.net/push`로 설정하면 urllib가
  `sdp-ingest:TOKEN@logs.example.net`에 접속을 시도해 `InvalidURL: nonnumeric port`로
  실패하는데, manifest는 `configured: true, target: logs.example.net`을 계속
  보고했습니다. 게다가 그 예외 메시지가 authority를 인용해 **credential이
  `_EXPORT_ERRORS` 링에 프로세스 수명 내내 보존**되었습니다. 이제 userinfo를 URL에서
  분리해 `Authorization` 헤더(password 있으면 `Basic`, token 하나면 `Bearer`)로
  보내고, host가 없거나 port가 숫자가 아닌 http sink도 file sink와 같은 resolver를
  통과해야 `configured: true`가 됩니다.
- sink export breaker에 **half-open 상태가 없었습니다**. cooldown이 끝나는 순간 모든
  요청이 죽은 sink를 동시에 재시도해, 모든 동기 route가 공유하는 anyio threadpool의
  빈 slot을 `SDP_LOG_SINK_TIMEOUT_MS`만큼 전부 점유했습니다 — breaker를 추가한 이유
  그 자체가 cooldown마다 되돌아왔습니다. 측정(실제 async 경로, 응답하지 않는 sink,
  cooldown 만료 직후 동시 20건): slot 8개면 sink 호출 **8회**, 무제한이면 **20회**,
  outage가 계속되는 동안 cooldown마다 반복. 이제 정확히 **1회**만 probe하고 나머지는
  skip하며, probe가 성공하면 그 즉시 모두에게 닫힙니다. 실패한 probe는 cooldown을
  다시 걸되 claim을 놓아 주므로 복구가 영구히 막히지 않습니다.

### Changed — 정직한 측정
- **거버넌스 카운트가 자기 페이지 크기였습니다.** `sdp_request_observations_total`은 이미
  고쳤는데 감사·정책 gauge는 같은 방식으로 읽혀 남아 있었습니다. 측정(거버닝 mutation 700건):
  실제 700 → `/metrics` **500**, `/enterprise/evidence-pack` **500**,
  `/enterprise/observability` **500**. 세 표면 모두 `list_*(limit=500)`의 `len()`입니다. 실제
  카운트로 바꾸고, 상한 도달 시 값이 아니라 하한으로 게시합니다. 다음 사례는 **AST 검사**가
  잡습니다 — `list_*(limit=N)`에서 대입된 변수의 `len()`이 `*_count`/`*_total`로 게시되는 모양.
- **`license`를 어떤 API 경로로도 설정할 수 없었습니다.** 두 request 모델에 필드가 없어 값이
  조용히 버려졌습니다(create `CC-BY-4.0` → `internal`, patch `MIT` → `internal`, 시드 전체
  `internal`). 노출만으로는 부족했습니다: `register_dataset`이 필드를 손으로 나열해 새 필드를 또
  무시했습니다. request 필드를 펼쳐 생성하고 **전 필드 forwarding을 기계적으로** 검사합니다.
- **`metadata_completeness` KPI의 target을 비교하는 코드가 없었습니다.** `>=90 percent` +
  `status: implemented`인데 0.90 비교가 어디에도 없었습니다(있던 임계값은 다른 측정의 0.95와
  ontology의 0.7). `mean_metadata_completeness`를 측정해 게이트합니다.
- **가정적 판정이 실제 접근 시도처럼 기록**되었습니다. `POST /policy/decision`은 "이 subject라면
  정책이 뭐라고 할까"에 답하는 것이 목적이므로 `subject`는 의도적으로 호출자 지정입니다. 그런데
  그 가정적 답이 **라벨 없이** 증빙 원장에 저장되었고, 지목된 subject에 귀속되며, **누가 물었는지는
  기록되지 않았습니다**. 측정(`analyst`가 `external-analyst`에 대해 질의): 응답과 원장 모두
  `subject: external-analyst, action: preview, effect: deny, reason: tenant boundary denied` —
  감사자는 다른 테넌트의 다른 신원이 거부된 preview를 시도한 기록으로 읽습니다. 그런 시도는
  없었고, 행을 만든 호출자의 이름은 어디에도 없었습니다. `subject`는 그대로 두고(그게 목적입니다)
  행에 `evaluation_mode: hypothetical`·`asked_by`·`subject_is_caller`를 더했습니다. `provenance`는
  opt-in이므로 다른 호출자의 행 모양은 바뀌지 않습니다(테스트로 고정).

- `paid_pilot_ready`가 작성된 `status` 리터럴에서만 유도되어 **반증 불가능**했습니다.
  이제 배포에서 측정합니다. 더불어 게이트를 충족시키던
  `SDP_EVIDENCE_RETENTION_DAYS`는 `src/` 어디에도 소비자가 없었고 `'banana'`로도
  통과했습니다 — 게이트에서 빼고 `unimplemented_environment`로 **게시**합니다.
  보존 기능은 구현하지 않았습니다(타이머로 감사 기록을 지우는 것은 결함 수정이
  아니라 제품 결정입니다). 레지스트리 전체에 대해 소비자 없는 변수를 금지하는
  기계적 검사를 추가했습니다.
- `local_evidence_retention` 컨트롤은 이름이 보존 정책을 주장하는데 실제로는
  **내구성**(재시작 생존)만 제공했습니다. label과 설명을 사실에 맞췄습니다.
- 같은 이유로 `SDP_ALERT_WEBHOOK_URL`도 게이트에서 뺐습니다. 이 변수를 읽는 코드는
  `_sink_status`가 **설정 여부**를 보고하는 한 곳뿐이고, 이 URL로 POST하는 코드도
  `GET /enterprise/observability`가 게시하는 alert 조건을 평가하는 코드도 없습니다.
  이 사례는 위의 "소비자 없는 변수 금지" 검사의 한계를 드러냅니다 — 소비자가
  **존재**했고(자기 자신의 존재 여부만 읽는 소비자) 검사를 통과했습니다. 그래서
  능력에 대한 증빙은 이름 검색이 아니라 전용 테스트가 담당합니다. 게시되는 alert
  규칙은 삭제하지 않았습니다(조건 자체는 올바르고 operator가 자기 모니터링 스택에
  그대로 구현할 수 있습니다) — 대신 `alert_evaluation: declared_not_evaluated`,
  규칙별 `evaluated: false`, `alert_webhook_routing: declared_unimplemented`로
  표시합니다. alert 평가와 라우팅은 구현하지 않았습니다.
- mock 실행의 수치에 출처 라벨을 붙였습니다. 하나의 라벨
  (`catalog_profile_estimate`)이 세 가지 provenance에 쓰이고 있었고, 그 중 하나는
  주장하는 추정값과 **600배** 차이나는 상한이었습니다. 네 provenance에 네 라벨.
- 거버닝 쓰기의 mutation 이전 감사 행이 `allowed`라고 주장했습니다 —
  `authorized`로 바꾸고, 결과를 아는 라우트는 실제 결과를 기록합니다. 리뷰 한 건이
  증거를 두 번 남기던 문제도 함께.
- `ontology_mapping_coverage`는 **커버리지를 줄이면 올라갔습니다**. `승인 mapping /
  전체 mapping`이었고, 자기 KPI 정의("buyer critical glossary terms 중 매핑된 비율")와 분모가
  달랐습니다. 측정: mapping 12건 중 7건을 지우면 0.917 → **1.0**. 이 값은 `demo_smoke`의
  `ready`와 saleability gate를 0.7 기준으로 통제합니다. 그 분모는 두 가지를 더 가렸습니다 —
  mapping이 전혀 없는 glossary 개념 `이탈 고객`(분모에 없어서 유일한 실제 갭이 보이지 않았음),
  그리고 ontology가 정의하지 않은 개념을 가리키는 mapping 3건(`고객 이탈`·`전환`·`캠페인`;
  이 중 2건이 approved여서 **미정의 개념에 대한 승인 mapping이 ontology coverage의 분자**였습니다).
  세 수치를 각자의 이름으로 게시합니다: glossary 기준 coverage(0.8), 옛 숫자인
  `ontology_mapping_approval_rate`(0.917), 그리고 `unmapped_glossary_concepts` /
  `unregistered_mapping_concept_count`. KPI 정의의 "또는 진행 중인 steward patch 제안" 구절은
  같은 KPI의 guardrail과 모순이었고 구현이 guardrail을 따르고 있었으므로, 숫자를 느슨하게
  맞추는 대신 정의를 엄격한 쪽으로 정정했습니다. **0.8 ≥ 0.7이므로 gate와 `ready`는
  불변입니다** — 결함 수정이고 제품 결정이 아닙니다.
  이 수리에 대한 적대적 리뷰가 두 방향을 더 짚었고 둘 다 처리했습니다. (1) steward가 유일하게
  커버되지 않은 glossary 개념에 mapping을 **제안**하는 것 — 실제 커버리지를 가장 크게 개선하는
  행동 — 이 옛 지표에서는 숫자를 **떨어뜨렸습니다**(측정 0.917 → 0.846; 제안 행이 분모에만
  들어가므로). 지표가 측정 대상과 역상관이었습니다. glossary 기준 coverage는 구조적으로 이를
  해결하며(검증: 제안 시 0.8 → 0.8, 승인하면 상승), 방향을 테스트로 고정했습니다.
  (2) gate의 `evidence`와 KPI의 `source_endpoints`가 `/ontology/patches`를 게시하는데 측정은
  patch 큐를 **읽지 않습니다**. 게시된 증빙을 따라간 diligence 독자는 아무것도 기여하지 않는 큐를
  가져갔습니다. 측정이 실제로 읽는 표면(`/ontology/concepts` = 분모,
  `/catalog/datasets/{dataset_id}` = 분자, `/enterprise/evidence-pack` = 게시 지점)으로
  교체했습니다. patch 큐는 그것을 실제로 읽는 steward-review 표면의 증빙입니다. 보고된 1건만
  보지 않고 일반 경우도 확인했습니다: 전 manifest의 endpoint 형태 증빙 포인터 **34건**이 모두
  실제 라우트이며, 라우트 이름이 바뀌어 404를 가리키지 않도록 기계적으로 고정했습니다.

- 게시된 SHACL shape catalog가 **평가되지 않았습니다**. `required_properties`를 읽은
  사람은 그것이 `conforms`를 만든 제약이라고 받아들이는데, 실제로 돌던 것은 shape id만
  빌려 쓴 손으로 쓴 규칙 세 개였습니다. 측정: `format`과 `endpoint`가 빈 distribution →
  `conforms: true`, violation 0건. `concept`가 빈 mapping → `concept`를 지목하는 violation
  없음. 그리고 `DatasetShape`는 실제로 강제되는 `description`·`sensitivity`·`title`·
  `update_frequency`를 게시 목록에서 빠뜨렸습니다 — 카탈로그가 **양방향으로** 틀렸습니다
  (검사하지 않는 property를 게시하고, 검사하는 property를 게시하지 않음). 이제 게시된 모든
  property가 그것을 선언한 항목에 의해 평가되고, `DatasetShape`는 `REQUIRED_METADATA_FIELDS`에서
  유도되어 다시 어긋날 수 없으며, "승인 mapping 최소 1건"은 property 존재 검사가 아니라
  cardinality로 선언됩니다. `shacl_compatible`은 하드코딩 `true`에서 "게시된 모든 shape가
  평가되는가"로 바뀌었고, SHACL 엔진이 돌지 않는다는 사실(`pyshacl`은 의존성이 아닙니다)을
  `validation_engine`/`shacl_engine_executed`로 함께 게시합니다. **시드는 이미 모든 shape를
  만족하므로 `validation_pass_rate`는 1.0에서 움직이지 않았습니다** — gate가 더 많이 측정하면서
  숫자는 그대로입니다.

- connector probe의 control 판정이 **사전 멤버십 동어반복**이었습니다.
  `implemented = bool(_IMPLEMENTED_PROOF.get(control, []))` — "이 control이 구현되었는가"를
  "이 control 이름이 스무 줄 위 손으로 쓴 dict의 키인가"로 답했습니다. 측정(유효한 5쌍,
  필수 control 11종 전부): dict에 11/11이 있어 `planned`가 **도달 불가능**했고, 전체 행렬에서
  판정을 움직일 수 있는 것은 `credential_vault`의 secret 존재 확인 하나뿐이었습니다. control 11개가
  "implemented"라고 세고 있던 구매자는 **주장 11개**를 세고 있었습니다. 각 control의 효과를 실제로
  검증하는 것은 결함 수정이 아니라 별도 프로젝트이므로, 이번 변경은 주장을 **거짓이 될 수 있게** 만들고
  **강도를 말하게** 합니다: control은 자신이 선언한 proof endpoint를 이 빌드가 전부 서비스할 때
  implemented이고, 행마다 `verification`(`declared_only`/`proof_route_served`/
  `runtime_probe_verified`)과 probe 단위 `control_verification_counts`, 그리고 `verdict_basis`를
  게시합니다. 여기서 나오는 정직한 숫자: 기본 데모 배포에서 runtime 검증 control은 **0개**입니다.
  환경변수 이름이 `proof_endpoints`에 섞여 있던 것도 `config_proof`로 분리했습니다.

### Added — 기계가 읽는 계약

- **거부 계약을 OpenAPI 문서에 게시**합니다. 변경 전: 에러 상태를 하나라도
  문서화한 operation이 60개 중 **0개**. 이제 42개이고, 남은 18개는 실제로 거부가
  없는 열린 읽기입니다. 계약은 표 하나에 있고, 코드가 낼 수 있는 상태는
  `sdp.api`의 AST를 따라 유도해 **양방향**으로 대조합니다.
- **200 응답 계약을 게시**합니다. 변경 전: 쓸 수 있는 200 스키마를 가진 operation이 60개 중
  **0개**(54개가 `{"type":"object","additionalProperties":true}`, 4개 bare array, 1개 빈
  스키마, 1개 타입만). 모든 핸들러가 `-> dict[str, Any]`여서 사실이지만 소비자에게는 무정보였고,
  문서로 클라이언트를 만드는 구매자는 카탈로그·evidence pack·모든 거버닝 읽기에 `Dict[str, Any]`를
  받았습니다. JSON을 반환하는 GET **39개**에 스키마를 게시합니다 — **라우트를 실행해 유도**하고
  (손으로 쓴 응답 스키마는 이 제품이 거부하는 drift 그 자체입니다) 테스트가 실제 응답과 대조합니다.
  그 테스트가 제 유도 코드의 narrowing 버그를 잡았습니다: `{}`("any")가 타입에 흡수되어 `null`로
  관측된 `mappings[].steward`/`approved_at`에 `string`을 게시하고 있었습니다. 유도 규칙은
  `required` 미표시, `integer` 대신 `number`, 관측된 `null`·빈 배열 items·타입 충돌은 `{}`입니다.
  게시하지 않는 22개는 사유와 함께 선언하고 선언의 정확성도 테스트합니다.
- `GET /metrics`가 `application/json` + 빈 스키마로 문서화되어 있었습니다. 실제로는
  `text/plain; version=0.0.4; charset=utf-8`(Prometheus exposition)을 반환하므로, 생성된
  클라이언트는 Prometheus 텍스트를 JSON으로 파싱하려 했을 것입니다. 실제 content type으로
  정정했습니다.
- **요청 본문 계약을 게시**합니다. 네 라우트(`POST /catalog/datasets`,
  `PATCH /catalog/datasets/{id}`, `POST /llm/draft-query`, `POST /browse/query`)는
  이미 pydantic 모델로 검증되고 있었지만 문서에는 `additionalProperties: true`로만
  나타났습니다. 런타임은 그대로이고(400 형태 유지), 게시한 모델이 핸들러가 실제로
  생성하는 모델인지 AST로 확인합니다.
- **profile 수치가 "누가 언제 측정했는지"를 말하게 했습니다(LIN-003).** 수락 기준은
  **metric timestamp와 계산 범위 표시**인데 라우트는 숫자만 공개하고 둘 다 공개하지
  않았습니다 — 그래서 **선언이 측정으로 읽혔습니다**. 시드 카탈로그에서 측정:

      GET /catalog/datasets/crm-customer-master/profile
        -> row_count: 1200000
           schema_profile[1]: {null_ratio: 0.01, distinct_ratio: 0.99}

  이 중 아무것도 이 서비스가 계산하지 않았습니다. `demo_seed.py`의 픽스처 값이거나,
  호출자가 등록 요청 본문에 넣은 값입니다. 프로파일러가 없으므로 소스의 행을 읽는
  코드가 없고, 따라서 null 비율을 셀 수 없습니다. evidence 표면에서 "120만 행, 1% null"을
  읽은 구매자는 **이 제품이 한 적 없는 주장**을 읽고 있었습니다.
  숫자는 그대로 둡니다(소스 자신의 선언이고 그 자체로 유용합니다) — 대신 출처와 함께
  보냅니다: `computed_by_this_service: false`, `measurement_status: declared_by_source`,
  `computation_scope: source_declared_scope_unknown_to_this_service`,
  그리고 `metric_timestamp`는 **선언된 값이거나 `null`**입니다. 읽은 시각을 찍는 것이
  여기서 유일하게 적극적으로 오해를 만드는 선택입니다 — 측정 시점을 모르는 수치에
  매 요청마다 새 timestamp를 붙이면 낡은 선언이 신선하게 보입니다. 값이 문자열이
  아니면 `str()`로 강제하지 않고 없는 것으로 취급합니다.
  `declared_unavailable_metrics`가 LIN-003이 요구하지만 이 제품에 없는 지표를 사유와
  함께 적습니다. `duplicate_ratio`는 행을 훑어야 하므로 계산할 수 없습니다.
  `distinct_count`는 `distinct_ratio * row_count`로 **유도하지 않습니다** — 둘 다
  선언값이고, 곱하면 어느 입력도 뒷받침하지 않는 측정을 만들어냅니다. "없다"와
  "유도하기를 거부한다"는 다른 주장이고 사실인 쪽은 후자이므로, 사유 문구가 그렇게
  말하고 테스트가 그 문구를 고정합니다.
- **품질 임계값을 선언하고 위반을 경고하게 했습니다(LIN-004).** 재료는 전부 있었고
  전부 쓰이지 않았습니다: `quality_score`·`freshness_score`·`metadata_completeness`와
  컬럼별 `nullable_ratio`·`distinct_ratio`·`quality_issues`가 저장되고 공개되고
  있었지만, 임계값을 선언한 코드가 어디에도 없었으므로 위반이 성립할 수 없었고 경고가
  존재할 수 없었습니다. **임계값 없는 숫자는 품질 신호가 아니라 그냥 숫자입니다.**
  규칙 여섯 개를 선언하고 위반마다 수락 기준이 명시한 `rule`·`observed_value`·`threshold`를
  담아 데이터셋 상세와 거버닝 스키마 조회에 공개합니다. 세 가지를 지킵니다.
  (1) **평가할 수 없는 규칙은 통과가 아닙니다** — 입력이 없거나 숫자가 아니거나
  NaN/inf이거나 bool이면(bool은 `int` 서브클래스라 `True`가 `1.0`으로 비교될 수 있습니다)
  `unevaluated`와 사유를 보고하고 셉니다. 없는 데이터를 "임계값 이내"로 처리하면 품질
  표면의 목적이 정확히 뒤집힙니다. (2) **경고는 discovery 경계를 넘지 않습니다** —
  "컬럼 `ssn`이 94% null"은 `discovery_view`가 withhold하는 컬럼별 통계를 quality 필드로
  우회시키는 것입니다. 그래서 규칙에 범위가 있습니다: dataset 범위는 discovery가 이미
  공개하는 필드를 읽고 거기 나타나며, column 범위는 정책 게이트 뒤에만 나타나고 공개
  표면에는 `withheld_quality_warning_count`가 갑니다. (3) **임계값은 한 곳입니다** —
  `metadata_completeness`는 saleability gate가 이미 비교하는 0.90을 재사용합니다(두 벌이
  어긋나면 같은 데이터셋이 pass이면서 gap입니다).
  테스트가 규칙 **여섯 개 전부에 대해 위반 픽스처를 만들어 실제로 발화하는 것을
  확인합니다** — 시드 데모 데이터는 모든 임계값에 대해 깨끗하므로, 시드만 읽는 테스트는
  한 번도 발화하지 않는 규칙 집합을 통과시킵니다. 임계값과 **같은** 값은 발화하지 않고
  (시드의 `semantic-glossary.broader_concept`가 null 비율 0.200으로 정확히 경계에
  있습니다) 0.001 넘으면 발화하는 것도 함께 확인합니다 — 그래야 앞의 단언이 죽은 규칙
  때문에 통과하는 것이 아님이 증명됩니다. 이에 따라 LIN-004는 `not_implemented` →
  `implemented`입니다.
  한 가지를 자체 점검에서 고쳤습니다: 임계값 비교 전의 내부 불변식이 `assert`였는데
  `-O`에서는 제거되므로 threshold가 `None`인 규칙이 `numeric < None`에 도달해 공개된
  읽기 안에서 TypeError를 냈을 수 있습니다. 이제 잘못 선언된 규칙은 예외 대신
  `unevaluated`로 자기 상태를 보고합니다.
- **PRD가 선언한 여섯 개 지연 예산을 측정하게 했습니다 — 단방향으로.**
  `docs/prd-trd.md`는 표면별 p95 예산을 선언합니다(NFR-PERF-001~006: catalog 검색 2초,
  dataset 상세 1.5초, schema browsing 3초, preview 10초, LLM 답변 15초, ontology term
  resolution 500ms). 이 중 **어느 것도** 저장소의 어떤 코드와도 관계가 없었습니다.
  미들웨어는 요청별 `latency_ms`를 처음부터 기록했고 `/enterprise/observability`가 그것을
  공개했지만, 예산을 호명하는 코드가 없었으므로 선언된 여섯 개 목표는 비교 대상이
  없었습니다 — **비교 대상이 없는 목표는 gate가 아닙니다**. CAT-001의 수락 기준도 같은
  2초를 말하면서 같은 상태였습니다.
  `GET /enterprise/latency-budgets`가 각 예산을 그것이 적용되는 라우트에 묶고(라우트
  분류는 앱 자신의 컴파일된 패턴으로 하므로 dispatch와 어긋날 수 없습니다) 성공 응답의
  nearest-rank p95와 비교합니다. **측정은 의도적으로 단방향입니다.** 관측은 이
  프로세스에서 나오고(in-memory store, seed 데이터, 단일 워커, 네트워크 없음) 배포는
  데이터베이스·실제 데이터 규모·동시성·네트워크 홉을 더해 느려지기만 하므로, in-process
  p95는 배포 p95의 **하한**입니다. 예산 초과는 결정적이고 예산 미달은 배포에 대해 아무것도
  증명하지 않습니다. 그래서 필드 이름이 `within_budget`이 아니라 `budget_refuted`이고,
  `budget_confirmation_possible: false`와 그 사유를 함께 게시합니다 — `within_budget: true`는
  "SLO를 충족한다"로 읽히고 이 측정은 정작 중요한 방향으로 그것을 뒷받침할 수 없습니다.
  표본이 20 미만인 표면은 `insufficient_sample`로 보고하고 **어느 방향으로도** 판정하지
  않습니다(표본 몇 개의 p95는 이름만 백분위인 표본 최댓값입니다). 거부 응답은 세지
  않습니다 — 거부는 검색이 아니고, 빠른 4xx를 세면 가장 일을 덜 한 요청들이 모든 p95를
  끌어내립니다. 공개하는 것은 라우트 **템플릿**뿐이어서, 요청별 피드를 withhold하는
  manifest의 공개 경계 안에 머무릅니다.
  `tests/test_latency_budget_measurement.py`가 각 표면에 실제 트래픽을 흘려 여섯 개 전부를
  평가시키고 어느 것도 반증되지 않음을 확인합니다. 그리고 **반증 경로가 실제로 작동하는
  것을 증명합니다** — 예산보다 느린 관측을 넣어 판정이 뒤집히는 것을 봅니다. 이것이 없으면
  모든 `budget_refuted: false`는 한 번도 일어나지 않은 비교일 수 있습니다. 이 gate가 잡을
  종류의 결함이 이미 저장소에 기록되어 있습니다: `src/sdp/catalog.py:468`이 데이터셋
  1005개에 대해 2000-토큰 질의 **5.10초**를 측정하고 있고, 이는 NFR-PERF-001의 2초 예산을
  넘습니다(그래서 질의 길이가 최적화가 아니라 상한으로 막혀 있습니다).
  이에 따라 NFR-PERF-001~006은 `not_implemented` → `partial`로, CAT-001의 비고는 지연
  측면이 측정되었음을 반영해 갱신했습니다.
  라우트 분류에는 bounded cache를 붙였습니다. 한 번의 리포트가 버퍼 용량만큼의 경로를
  전체 라우트에 대조하고 `prometheus_metrics_text`가 observability manifest를 통해 거기
  도달하므로, scrape마다 그 작업이 반복되고 있었습니다. 서로 다른 경로 500개로 채운
  버퍼에서 측정: `/metrics` **37.0 → 5.8 ms**, `/enterprise/latency-budgets`
  **73.6 → 6.2 ms**. `{dataset_id}` 경로는 호출자가 주는 값이므로 캐시는 **상한이 있어야**
  합니다(무한 맵은 외부에서 프로세스 메모리를 키우는 경로입니다) — 테스트가 상한을
  단언합니다. 라우트 테이블은 import 시점에 고정되고 이후 등록되는 라우트가 없으므로
  캐시된 분류가 낡을 수 없습니다.
  표면별로 `sample_window_seconds`도 함께 공개합니다. 관측 버퍼는 **모든** 라우트가
  공유하는 하나의 ring이므로 바쁜 표면이 조용한 표면의 행을 밀어냅니다 — 며칠에 걸친
  요청 20개의 p95와 지난 1분의 요청 20개의 p95가 같은 종류의 숫자처럼 나란히
  놓이는데, 같지 않습니다. 창의 **너비**는 읽는 사람이 필요한 값이고 달리 알 방법이
  없으므로 공개하고, timestamp가 아니라 초 단위 span으로 공개합니다 — 거버닝 읽기가
  **언제** 일어났는지는 필요하지 않고, 그것이 바로 unauthenticated manifest가 요청별
  피드를 withhold하는 이유입니다. stamp가 없거나 문자열이 아니거나 파싱되지 않거나
  aware/naive가 섞여 있어도(섞인 채로 빼면 예외입니다) 공개된 읽기가 터지지 않고 span만
  `null`이 됩니다. `implemented`가 아닌 이유는 위의 단방향성
  그대로입니다 — 요구사항은 배포에 대한 진술이고 이 측정은 그것을 확인할 수 없습니다.
- **그 매트릭스를 적대적 감사에 걸어 38건을 정정했습니다.** 전수 매핑을 만든 직후
  스스로 감사했습니다(요구사항군별 에이전트 11개가 모든 행을 코드에 대고 검증 →
  제기된 발견 45건을 각각 **독립 에이전트가 반증 시도**, 총 56 에이전트). 36~38건이
  확인되고 **7건이 기각**되었습니다.
  **상태 판정 기준이 제 초기 매핑에서 느슨했던 것이 드러났습니다.** 기준은 PRD의
  **수락 기준(ACCEPT 열)** 이어야 합니다 — 기능이 어떤 형태로든 존재하는지가 아니라
  그 요구사항이 명시한 메커니즘이 있는지입니다. 수락 기준이 이 저장소에 없는
  메커니즘을 호명하면 기능이 대체로 동작해도 `implemented`가 아닙니다.
  `implemented` **37건 → 13건**, `partial` 20건 → 45건, P0 `implemented` 21건 → 6건.
  정정의 대표적인 근거(모두 코드 인용과 함께 재현):
  `CAT-002`는 상세 페이지가 표시해야 할 11개 필드 중 `source_system`을 거버넌스
  경계 때문에 의도적으로 withhold합니다(10/11). `CAT-005`의 수락 기준은 변경
  **사유** 기록인데 `_build_dataset_payload`가 모든 카탈로그 쓰기에 `reason="ok"`를
  하드코딩하고, `deprecate`만 호출자 사유를 받습니다(3/4 경로가 사유 없음).
  `CAT-009`의 수락 기준은 business key 또는 ontology mapping 기반 추천인데
  `get_join_candidates`는 `dataset.mappings`를 **읽지 않고** 컬럼 이름 일치를 쓰므로,
  승인된 mapping만 공유하는 두 데이터셋은 `[]`를 돌려받고 `id`/`amount` 같은 일반
  컬럼명만 공유하는 둘은 추천됩니다. `POL-003`의 마스킹은 `col.pii`만 보고 subject·
  purpose·PRD가 호명한 sensitive/confidential 태그를 보지 않습니다. `ONT-002`·`ONT-005`의
  수락 기준은 SHACL/OWL 검증과 reasoner인데 둘 다 없습니다. `NFR-QUAL-004`의 수락
  기준은 **CQ pass rate**이고 그 전제인 CQ 등록(`ONT-008`)이 미구현입니다.
  **반대 방향도 있습니다.** `NFR-SEC-004`를 `external`에서 `partial`로 올렸습니다 —
  수락 기준이 "모든 **내부/외부** 통신 TLS"이고, 이 저장소가 소유한 내부 링크 세 개가
  평문을 허용합니다(JWKS fetch가 http 허용, log sink가 Authorization 헤더를 지고 http
  허용, 배포되는 postgres 프로파일이 `SDP_DATABASE_SSLMODE: disable`). 게다가 제
  비고는 **이 저장소에 존재하지 않는 Traefik 설정**을 책임자로 지목하고 있었습니다
  (`grep -rn traefik` → 제 비고 자신만). 다른 저장소의 모양을 가져다 쓴 것이고,
  근거 없는 책임 전가였습니다.
  `NFR-REL-001`/`002`는 `not_implemented` → `external`입니다. 매트릭스가 **자기
  어휘와 모순**이었습니다 — `external`의 정의가 "배포/호스트 플랫폼의 책임"이고 그
  세 예시 중 하나가 바로 "availability targets"인데, 가용성 요구사항을
  `not_implemented`로 적어 두었습니다. `NFR-SEC-006`은 `implemented` → `external`:
  LLM provider로 데이터를 보내지 않는다는 주장이 **통제가 있어서가 아니라 provider
  경계가 아예 없어서** 성립하고, 인용된 테스트는 카탈로그 DSN redaction을 단언할
  뿐 model egress에 대해 아무것도 말하지 않습니다.
  기각된 7건은 **전부 제가 감사 도중에 이미 고친 것**이었습니다(CAT-001과
  NFR-PERF-001~006 — 검증자가 "제기된 current status가 파일에 존재하지 않는다"로
  기각). 감사를 제 수정과 병행 실행한 비용이고, 검증 단계가 그것을 잡았습니다.
  인용도 세 건 교체했습니다. 감사가 지적한 대로 `CAT-004`/`ONT-003`이 인용한
  concept-graph 테스트는 glossary 개방성만 단언하고 mapping status나 hierarchy
  traversal을 다루지 않으며, `CAT-005`가 인용한 governed-write 테스트는 카탈로그
  라우트를 하나도 건드리지 않습니다.
  생성 문서에 **판정 기준과 이 분포의 의미를 명시**했습니다 — `partial` 45건은
  정보가 없다는 뜻이 아니라 **정보가 상태가 아니라 비고에 있다**는 뜻입니다.
  이 작업에서 제 적용 스크립트의 결함 하나도 저장소 가드레일이 잡았습니다:
  긴 `tests/x.py::test_name` 인용이 wrap 경계에서 쪼개져 식별자 안에 공백이 들어갔고,
  anti-dangling-evidence 테스트가 "존재하지 않는 테스트 3건"으로 실패했습니다.
- **요구사항 대응 매트릭스를 전수로 만들고 기계가 강제하게 했습니다.**
  `CLAUDE.md`가 요구사항 대응 매트릭스로 지목하는 `docs/implementation-compliance.md`를
  PRD에 대고 측정한 결과: PRD의 요구사항 **74건**(기능 52 + NFR 22) 중 문서가 언급하는 것은
  **13건**, P0 34건 중 **25건이 아예 없었습니다**. 빠진 것들이 대부분 실제로는 구현되어
  있다는 점이 문제를 더 나쁘게 만듭니다 — 읽는 사람은 어느 쪽인지 구별할 수 없고, 부재는
  부재로 읽힙니다. 손으로 유지하는 매트릭스가 낡는 방향이 정확히 이쪽입니다.
  `docs/requirements-coverage.md`는 **생성 문서**입니다: 목록을 PRD에서 파싱하므로 원본과
  어긋날 수 없고, 모든 ID가 명시적 상태(`implemented`/`partial`/`not_implemented`/`external`)와
  증빙 포인터를 가져야 합니다. `tests/test_requirements_coverage.py`가 (1) 모든 PRD ID의 매핑
  존재, (2) 반대 방향 — PRD가 더 이상 선언하지 않는 ID의 매핑 금지, (3) 모든 증빙 포인터의
  실제 해석(이 앱이 서비스하는 route / import 가능한 attribute / **pytest가 수집하는** test id),
  (4) `implemented` 주장의 수집되는 test 보유, (5) 약한 상태의 사유 기재, (6) 문서와 생성
  결과의 글자 단위 일치를 강제합니다. 역검증으로 10가지 훼손이 모두 실패를 일으키는 것을
  확인했습니다 — 그중 하나가 **PRD에 요구사항이 추가되면 답할 때까지 스위트가 깨진다**는
  것으로, 이 문서가 다시 낡지 않게 하는 성질입니다.
  이 기계장치가 제 자신의 작업에서 두 가지를 잡았습니다. 첫째, 제가 기억으로 쓴 증빙
  포인터 **102개 중 25개가 해석되지 않았습니다**(존재하지 않는 함수 이름 1개, 수집되지 않는
  test id 24개) — 손으로 쓴 인용은 쓰는 그 순간에도 틀립니다. 둘째, 게시한 상태 어휘는
  `implemented`를 "구현이 답하고 **테스트가 덮는다**"로 정의하는데 게이트는 route 포인터
  하나만으로도 통과시켰습니다(CAT-009가 그 상태였습니다 — 실재하는 route 2개, 실재하는
  테스트 2개, 인용된 테스트 0개). 어휘와 게이트가 같은 말을 하도록 `test:` 포인터를
  요구하게 좁혔습니다.
  **CAT-001은 이 과정에서 `implemented` → `partial`로 내렸습니다.** 수락 기준이
  "2초 이내 95p 응답, facet count 포함"인데 둘 다 성립하지 않습니다: `/catalog/search`
  응답은 `{query, count, items}`로 facet count가 없고(facet은 별도 라우트입니다), p95
  지연을 측정해 2초 예산과 대조하는 코드가 없습니다. 이 저장소가 기록하는 유일한 지연
  수치는 오히려 예산을 넘습니다 — `src/sdp/catalog.py:468`이 데이터셋 1005개에 대해
  2000-토큰 질의 **5.10초**를 측정하고 있고, 그래서 입력이 최적화가 아니라 상한으로
  막혀 있습니다.
- demo smoke의 `ready` 게이트가 12단계 HTTP 표면을 실제로 통과해야 참이 됩니다.
- 테스트 격리를 `tests/conftest.py`의 autouse fixture 하나로 모든 파일에
  적용했습니다. 이전에는 `test_api.py`에만 있어서 파일 순서를 뒤집으면 5건이
  실패했습니다.

### Known limitations (덮지 않고 적어 둡니다)

- `PostgresGraphStore`의 삭제 경로(`edges_for`/`delete_edge`/`delete_node`)는
  라이브 Postgres+AGE+pgvector에서 **실행해 보지 못했습니다**. in-memory 쪽은
  테스트가 덮고, 실제 DB가 필요한 단언은 `tests/test_integration_age.py`에
  있습니다(DSN 없으면 skip).
- 200 응답 스키마는 JSON을 반환하는 GET 38개에 게시했고, 본문이 필요한 non-GET 20개는
  미게시입니다(스키마를 유도하려면 mutation을 구동해야 하고, 그러면 검증 테스트가 그래프 스토어
  상태를 남깁니다 — 요청 본문 쪽은 이미 게시되어 있습니다). `response_model`은 쓰지 않았습니다:
  필드를 필터링하므로 동작 변경 위험이 있어, 런타임을 건드리지 않는 `responses=` 문서화 경로를
  택했습니다.
- 요청 본문 10건은 모델이 없는 라우트입니다(느슨한 키 읽기). 스키마를 손으로
  써 붙이면 핸들러가 읽는 것과 어긋날 수 있고, 모델을 주면 400이 422로 바뀝니다.
- 그래프 스토어 싱글턴은 테스트 격리 대상에서 제외했습니다(snapshot API가 없고,
  테스트를 위해 제품 API를 만드는 것은 범위를 넘습니다).
- alert 조건 평가와 `SDP_ALERT_WEBHOOK_URL` 라우팅은 구현되지 않았습니다(위 참조).
  조건은 게시하지만 계산하지 않습니다.
- http(s) sink의 `Authorization` 분리는 **로컬에서 포착한 요청 객체**로 검증했습니다
  (urllib이 다이얼하는 host, 재구성된 URL, 헤더). 실제 원격 sink에 대한 왕복은
  실행하지 않았습니다.
- `oidc-verify`에서 claim 상한은 **권한 결과를 바꿀 수 있습니다**: 상한을 넘은 group은 role을
  부여하지 않습니다. 부여가 아니라 보류이므로 fail-closed이지만 동작 변경이며, 그래서 verify 응답도
  `declared_group_count`/`withheld_group_count`를 게시해 운영자가 사라진 role의 이유를 볼 수
  있게 했습니다. 256개를 넘는 group을 담은 토큰을 쓰는 배포는 이 상한을 먼저 검토해야 합니다.
- connector control의 `proof_route_served`는 "선언된 proof endpoint가 이 빌드의 라우트로
  존재한다"는 뜻이고, 그 control이 실제로 동작한다는 뜻이 **아닙니다**. 11종 중 runtime 확인이
  있는 것은 `credential_vault` 하나뿐이며, 나머지 10종에 실제 검증을 붙이는 것은 별도 작업입니다
  (그래서 강도를 게시합니다 — 세 단계가 하나의 "implemented"로 합쳐져 있었습니다).
- SHACL 엔진은 돌지 않습니다. 게시된 shape가 SHACL로 표현 가능하고 동등한 in-process
  검사로 강제된다는 것이 이 표면이 할 수 있는 정직한 주장이며, 그 둘을 모두 게시합니다.
  `pyshacl`을 의존성으로 들이는 것은 (RDF 스택을 끌어오고 CI가 hash-pinned 설치를 쓰므로)
  별도 결정입니다.
- `docs/product-technical-gap-baseline.md`의 `ontology_mapping_coverage | 0.917` 표기는
  head `52bc571` 당시의 보존된 스냅샷이라 고치지 않았습니다. 그 문서가 이미 해당 문단을
  "현재 상태로 인용하지 말 것"이라고 표시하고 있습니다.
