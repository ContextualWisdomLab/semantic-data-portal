# CHANGELOG

이 문서는 `claude/semantic-portal-pr-merge-e5a48k` 브랜치(PR
[#102](https://github.com/ContextualWisdomLab/semantic-data-portal/pull/102))가
베이스 대비 더하는 변경을 사람이 읽을 수 있게 묶은 것입니다. **186개** 커밋 중 113개는
gap-baseline 문서 작업이고, 아래는 제품 동작이 바뀐 나머지입니다
(`git rev-list --count origin/docs/product-technical-gap-baseline..HEAD`로 측정;
앞서 적혀 있던 164/112는 그 시점의 값이고 이후 커밋을 반영하지 않은 숫자였습니다 — 자기 문서의
수치도 측정해서 맞춰 둡니다).

형식은 [Keep a Changelog](https://keepachangelog.com/)를 따릅니다.

## [Unreleased]

**릴리즈된 것이 아닙니다.** 이 브랜치는 병합되지 않았고, PR #102는 현재 독립
승인 0건이며 필수 체크는 계정 Actions 과금 잠금으로 디스패치 전에 거부되고
있습니다(저장소 자체 워크플로의 마지막 성공: 2026-10-02T09:03:05Z. 그 이후의
성공은 GitHub 자체 할당량으로 도는 Dependabot 뿐이며, 이는 계정 잠금 해제의
증거가 아닙니다). 태그와 릴리즈는 사람의 승인 없이 만들지 않습니다.

아래 모든 항목의 유일한 실행 증거는 로컬 CI 동형 실행입니다:

    pytest                    994 passed, 11 skipped
    pytest (역방향/난수 순서)  순서 무관 통과 (역순 + seed 11/707/31337)
    pytest tests/fuzz          11 passed
    python -m sdp.demo_smoke   exit 0, "ready": true

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
