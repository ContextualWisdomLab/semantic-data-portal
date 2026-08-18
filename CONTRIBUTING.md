# Contributing to semantic-data-portal

구매자·운영자 안내는 [README.md](README.md)에 있습니다. 이 문서는 이 저장소에서
코드를 고치거나 문서를 쓰는 기여자용입니다.

## 범위

- 이 저장소는 CWL **ontology / catalog leaf**입니다. 단독 기동과 HTTP 호출이
  모두 가능해야 합니다.
- 형제 저장소 checkout, path dependency, 다른 CWL home의 git submodule을
  부팅 조건으로 넣지 마십시오.
- LineageWeave weekly-report KG UI, `fast-mlsirm` score kernel, TEPP
  measurement import는 **여기서 구현하지 않습니다**. 경계는
  [docs/msa.md](docs/msa.md)와 [docs/adr/0001-product-authority-boundary.md](docs/adr/0001-product-authority-boundary.md)를
  보세요.

## 로컬 개발

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install --require-hashes -r requirements-dev.txt
PYTHONPATH=src uvicorn sdp.api:app --reload
PYTHONPATH=src pytest
```

패키지를 editable install 하지 않습니다. `PYTHONPATH=src`가 import 경로입니다.
pytest 기본 옵션은 `pyproject.toml`의 `addopts = "-q"`입니다.

의존성을 바꾸면 `pyproject.toml`이 원천입니다. hash-pinned 산출물을 다시
컴파일하십시오.

```bash
uv pip compile pyproject.toml --generate-hashes -o requirements.txt
uv pip compile pyproject.toml --extra dev --generate-hashes -o requirements-dev.txt
```

## 문서와 ADR

- 운영 사실·HTTP 계약은 README에 둡니다. 구현 매핑 표는
  [docs/implementation-compliance.md](docs/implementation-compliance.md)에
  둡니다.
- 새 아키텍처 결정은 [docs/adr/](docs/adr/)에 Context / Decision /
  Consequences / APA 7th References로 작성합니다. Draft ADR은 최종이
  아닙니다.
- 서지 원천은 [docs/REFERENCES.md](docs/REFERENCES.md) 하나입니다. 확인하지
  않은 DOI·논문을 만들지 마십시오.
- 개인정보: 마스킹을 처방하지 마십시오. 인가된 데이터는 목적 바운드 접근
  제어·암호화·감사 아래에서 사용 가능해야 합니다.

에이전트 거버넌스(보안 게이트, 탐색 규칙)는 [AGENTS.md](AGENTS.md)에
있습니다. README에 PR 스택·exact-head CI·do-not-merge 런북을 넣지 마십시오.

## 설계 메모

- 도메인 계층은 `KeyError` → 404, `ValueError` → 400, `PermissionError` →
  403을 올리고, `src/sdp/api.py`가 HTTP로 변환합니다.
- 카탈로그 mutation과 browse/query 경로에서 `policy.evaluate()`와 evidence
  기록을 빼는 변경은 회귀입니다.
- `/enterprise/console` CSS는 `src/sdp/design_tokens.py`의 `var(--sdp-*)`만
  참조합니다.
- 모듈 레벨 mutable 상태를 추가하면
  `tests/test_api.py`의 `isolate_in_memory_app_state` fixture에도 반영하십시오.
