# CHANGELOG

이 문서는 `claude/semantic-portal-pr-merge-e5a48k` 브랜치(PR
[#102](https://github.com/ContextualWisdomLab/semantic-data-portal/pull/102))가
베이스 대비 더하는 변경을 사람이 읽을 수 있게 묶은 것입니다. 164개 커밋 중 112개는
gap-baseline 문서 작업이고, 아래는 제품 동작이 바뀐 나머지입니다.

형식은 [Keep a Changelog](https://keepachangelog.com/)를 따릅니다.

## [Unreleased]

**릴리즈된 것이 아닙니다.** 이 브랜치는 병합되지 않았고, PR #102는 현재 독립
승인 0건이며 필수 체크는 계정 Actions 과금 잠금으로 디스패치 전에 거부되고
있습니다(저장소 자체 워크플로의 마지막 성공: 2026-10-02T09:03:05Z. 그 이후의
성공은 GitHub 자체 할당량으로 도는 Dependabot 뿐이며, 이는 계정 잠금 해제의
증거가 아닙니다). 태그와 릴리즈는 사람의 승인 없이 만들지 않습니다.

아래 모든 항목의 유일한 실행 증거는 로컬 CI 동형 실행입니다:

    pytest                    894 passed, 11 skipped
    pytest (역방향/난수 순서)  순서 무관 통과 (역순 + seed 11/29/77)
    pytest tests/fuzz          11 passed
    python -m sdp.demo_smoke   exit 0, "ready": true

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
  받았습니다. JSON을 반환하는 GET **38개**에 스키마를 게시합니다 — **라우트를 실행해 유도**하고
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
