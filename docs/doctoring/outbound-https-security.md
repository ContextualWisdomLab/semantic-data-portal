# Outbound HTTPS 보안 경계와 검증 근거

## Decision

Semantic Data Portal의 outbound HTTPS 요청은 단순 설정값이 아니라 외부
trust boundary로 취급한다. JWKS, OpenID Connect, observability 같은 technical
term은 원문 표기를 유지하며, 아래 규칙은 fail-closed 정책이다.

The Semantic Data Portal treats every configuration-driven outbound request as
a security boundary. Remote OpenID Connect JSON Web Key Set (JWKS) retrieval
and remote observability delivery accept only normalized HTTPS URLs that target
a public DNS name or a global IP literal. Explicit local observability files
remain a separate `file` transport and never enter the HTTP client path.

This is a fail-closed policy. OAuth 2.0 authorization-server metadata requires
the `jwks_uri` value to use HTTPS, and OpenID Connect Discovery publishes the
provider signing-key endpoint as an HTTPS resource. Plain HTTP is therefore not
a supported compatibility mode, including for observability callbacks.
Redirect도 compatibility mode가 아니다. 최초 URL이 public HTTPS여도 자동
follow-up은 HTTP downgrade, loopback 또는 metadata endpoint로 이동할 수
있으므로 application client가 모든 3xx redirect를 거부한다.

## Threat model

위협 모델은 운영자 설정이 supply-chain, 관리자 계정 또는 tenant integration
침해를 통해 attacker-controlled input으로 바뀔 수 있다고 가정한다.

An operator-controlled URL can still become attacker-influenced through a
compromised deployment pipeline, configuration store, administrative account,
or tenant-bound integration. Without validation, Python URL handlers can read
local files or connect to loopback, private, link-local, and cloud metadata
addresses. Embedded credentials and fragments also make review and audit
ambiguous.

The centralized validator blocks these classes before a network client is
called:

1. empty or malformed values;
2. every scheme other than HTTPS;
3. URLs with embedded user information or fragments;
4. missing, `localhost`, `.localhost`, and single-label hostnames;
5. non-global IPv4 and IPv6 literals, including loopback, private, link-local,
   and metadata-service addresses;
6. resolver가 loopback으로 해석할 수 있는 `127.1`, `0177.0.0.1`, `0x7f.1`
   같은 legacy numeric IPv4 forms;
7. invalid ports; and
8. every HTTP redirect before a follow-up request is issued.

Internationalized DNS names are normalized with IDNA, host case is normalized,
and an absent path becomes `/`. Query parameters are retained because they can
be part of a provider or collector endpoint contract.

## DNS rebinding and runtime egress

DNS rebinding은 validation 시점의 hostname과 connection 시점의 resolved IP가
달라질 수 있다는 TOCTOU 문제다. 따라서 application validation만으로 runtime
egress 통제를 대체할 수 없다.

The application deliberately does not resolve a DNS name during validation.
Resolving once and connecting later would create a time-of-check/time-of-use
gap. Production deployments must therefore enforce the same destination policy
after DNS resolution with an outbound proxy, firewall, service-mesh egress
gateway, or equivalent network control. That layer must deny private,
loopback, link-local, multicast, reserved, and infrastructure metadata ranges.
The application validator is the first line of defense; post-resolution egress
policy is the required second line.

## Apache AGE query execution

Apache AGE 경로는 dynamic SQL처럼 보이지만, graph name과 Cypher body의
authority를 server-built `Psycopg Literal`에 한정한다.

Apache AGE requires a composed SQL invocation around `cypher()`. The graph name
and complete server-built Cypher body are represented with Psycopg `Literal`
objects, the result declaration is selected from a closed map of constant SQL
objects, and request values remain in the positional JSON parameter. The
rule-specific Semgrep annotation at the driver call records this tested
framework mismatch. It does not suppress another rule, file, or workflow.

## Dependency remediation

Dependency remediation은 runtime, development, test lock을 동일한 fixed
version으로 유지해 환경별 security drift를 막는다.

The three hash-pinned requirements files resolve `cryptography` 50.0.0. That
release fixes CVE-2026-69247, in which distinguishable PKCS#7 encrypted-key
unwrap failures could expose a Bleichenbacher oracle. Keeping runtime,
development, and test lock files aligned prevents a clean test environment from
masking a vulnerable production resolution.

## Required verification

필수 검증은 동일한 exact PR head에서 수행되어야 하며 predecessor evidence를
재사용하지 않는다.

A change to these boundaries is incomplete unless the same pull-request head
satisfies all of the following:

- the exact checked-out commit equals the pull request's current head;
- production statement and branch coverage remain 100%;
- domain-valid regression tests prove unsafe URLs are rejected before network
  access and valid destinations preserve their timeout and payload contract;
- Semgrep reports no unsuppressed warning or error;
- Trivy and OSV report no blocking dependency finding; and
- repository policy and an independent non-author approval cover the current
  head before merge.

## References

학술 논문 PDF의 repository redistribution permission은 확인되지 않았으므로
PDF를 포함하지 않고 APA 7 citation, DOI link, 관련성 요약을 제공한다.

Jackson, C., Barth, A., Bortz, A., Shao, W., & Boneh, D. (2007). Protecting
browsers from DNS rebinding attacks. In *Proceedings of the 14th ACM Conference
on Computer and Communications Security* (pp. 421–431). Association for
Computing Machinery. https://doi.org/10.1145/1315245.1315298

이 연구는 DNS pinning만으로 rebinding을 막을 수 없음을 실증하고, firewall
circumvention을 차단하는 policy-based defense와 `dnswall`을 제안한다. 본
경계에서 application-side URL validation과 post-DNS network egress control을
서로 독립된 두 계층으로 요구하는 근거다.

Jones, M., Sakimura, N., & Bradley, J. (2018). *OAuth 2.0 authorization server
metadata* (RFC 8414). RFC Editor. https://doi.org/10.17487/RFC8414

RFC 8414는 authorization-server metadata의 `jwks_uri`가 HTTPS URL이어야
한다는 interoperability contract를 정의하며, plain HTTP fallback을 제공하지
않는 결정의 표준 근거다.

Python Cryptographic Authority. (2026). *Cryptography 50.0.0 changelog*.
https://cryptography.io/en/latest/changelog/

이 changelog는 pinned dependency remediation의 fixed release와 security
impact를 추적하기 위한 authoritative release evidence다.

Python Software Foundation. (2026). *urllib.parse—Parse URLs into components*.
Python documentation. https://docs.python.org/3/library/urllib.parse.html

이 문서는 URL parsing과 normalization 동작의 authoritative implementation
reference이며, parsing 자체가 destination authorization은 아님을 구분한다.

Psycopg Project. (2026). *SQL string composition*. Psycopg documentation.
https://www.psycopg.org/psycopg3/docs/api/sql.html

이 문서는 `SQL`, `Identifier`, `Literal` composition contract를 정의해 AGE
driver call의 authority boundary를 검토하는 근거다.

Sakimura, N., Bradley, J., Jones, M., de Medeiros, B., & Mortimore, C. (2014).
*OpenID Connect Discovery 1.0*. OpenID Foundation.
https://openid.net/specs/openid-connect-discovery-1_0.html

OpenID Connect Discovery는 provider signing-key endpoint discovery contract를
정의하며, JWKS retrieval을 public HTTPS 경계 안에 두는 표준 근거다.

Semgrep, Inc. (2026). *Ignoring findings in files*. Semgrep documentation.
https://semgrep.dev/docs/ignoring-files-folders-code

이 문서는 rule-scoped annotation semantics를 확인하는 도구 근거다. Workflow
파일 전체 제외나 broad suppression을 허용하는 근거로 사용하지 않는다.
