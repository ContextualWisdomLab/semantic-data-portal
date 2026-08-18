# 의존성 보안 결정

## Cryptography 50.0.0 security floor

### Decision

설치 가능한 모든 Python 의존성 표면은 `cryptography==50.0.0` 또는 이후에 명시적으로 검토한 대체 버전으로 resolve되어야 한다. runtime metadata, test resolver input, hash-locked 생성 파일을 맞춰 두어 local development, CI, production installation이 영향받는 release를 조용히 다시 끌어오지 못하게 한다.

### Security rationale

GitHub Advisory Database 항목 GHSA-g6cj-pr64-35w5는 PKCS#7 EnvelopedData decryption에서 구분 가능한 오류와 timing으로 인한 Bleichenbacher-style oracle을 설명한다. 영향 범위는 `cryptography>=44.0.0,<50.0.0`이며, 50.0.0이 첫 patched release이다. 이 저장소는 이전에 `PyJWT[crypto]` dependency graph를 통해 49.0.0을 resolve했으므로, transitive resolver 선택에 의존하지 않고 직접 security floor를 두는 것이 의도된 결정이다.

### Verification contract

`tests/test_dependency_security.py`는 다음을 검증한다:

1. `pyproject.toml`의 `[project].dependencies`와 `requirements-test.in`이 patched floor를 선언한다.
2. 설치 가능한 각 hash-locked 의존성 파일에 `cryptography==50.0.0` 항목이 정확히 하나 있다.
3. 해당 installation surface에 stale affected pin이 남아 있지 않다.

저장소의 pin된 `uv` compiler로 lock을 재생성하고, merge 전에 결과 graph를 검토한다:

```bash
uv pip compile pyproject.toml --generate-hashes -o requirements.txt
uv pip compile pyproject.toml --extra dev --generate-hashes -o requirements-dev.txt
uv pip compile --generate-hashes --universal --python-version 3.12 \
  requirements-test.in -o requirements-test.txt
```

Lock regeneration 이후에도 security scanning, tests, exact-current-head review가 필요하다. 이전 head의 성공한 scan은 재생성된 graph의 증빙이 되지 않는다.

## Reference

GitHub. (2026, August 3). *Cryptography: PKCS#7 EnvelopedData decryption exposes a Bleichenbacher oracle through distinguishable errors and timing (GHSA-g6cj-pr64-35w5).* GitHub Advisory Database. https://github.com/advisories/GHSA-g6cj-pr64-35w5
