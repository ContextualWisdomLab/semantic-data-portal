# Outbound HTTPS security boundary and verification evidence

## Decision

The Semantic Data Portal treats every configuration-driven outbound request as
a security boundary. Remote OpenID Connect JSON Web Key Set (JWKS) retrieval
and remote observability delivery accept only normalized HTTPS URLs that target
a public DNS name or a global IP literal. Explicit local observability files
remain a separate `file` transport and never enter the HTTP client path.

This is a fail-closed policy. OAuth 2.0 authorization-server metadata requires
the `jwks_uri` value to use HTTPS, and OpenID Connect Discovery publishes the
provider signing-key endpoint as an HTTPS resource. Plain HTTP is therefore not
a supported compatibility mode, including for observability callbacks.

## Threat model

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
   and metadata-service addresses; and
6. invalid ports.

Internationalized DNS names are normalized with IDNA, host case is normalized,
and an absent path becomes `/`. Query parameters are retained because they can
be part of a provider or collector endpoint contract.

## DNS rebinding and runtime egress

The application deliberately does not resolve a DNS name during validation.
Resolving once and connecting later would create a time-of-check/time-of-use
gap. Production deployments must therefore enforce the same destination policy
after DNS resolution with an outbound proxy, firewall, service-mesh egress
gateway, or equivalent network control. That layer must deny private,
loopback, link-local, multicast, reserved, and infrastructure metadata ranges.
The application validator is the first line of defense; post-resolution egress
policy is the required second line.

## Apache AGE query execution

Apache AGE requires a composed SQL invocation around `cypher()`. The graph name
and complete server-built Cypher body are represented with Psycopg `Literal`
objects, the result declaration is selected from a closed map of constant SQL
objects, and request values remain in the positional JSON parameter. The
rule-specific Semgrep annotation at the driver call records this tested
framework mismatch. It does not suppress another rule, file, or workflow.

## Dependency remediation

The three hash-pinned requirements files resolve `cryptography` 50.0.0. That
release fixes CVE-2026-69247, in which distinguishable PKCS#7 encrypted-key
unwrap failures could expose a Bleichenbacher oracle. Keeping runtime,
development, and test lock files aligned prevents a clean test environment from
masking a vulnerable production resolution.

## Required verification

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

Jones, M., Sakimura, N., & Bradley, J. (2018). *OAuth 2.0 authorization server
metadata* (RFC 8414). RFC Editor. https://doi.org/10.17487/RFC8414

Python Cryptographic Authority. (2026). *Cryptography 50.0.0 changelog*.
https://cryptography.io/en/latest/changelog/

Python Software Foundation. (2026). *urllib.parse—Parse URLs into components*.
Python documentation. https://docs.python.org/3/library/urllib.parse.html

Psycopg Project. (2026). *SQL string composition*. Psycopg documentation.
https://www.psycopg.org/psycopg3/docs/api/sql.html

Sakimura, N., Bradley, J., Jones, M., de Medeiros, B., & Mortimore, C. (2014).
*OpenID Connect Discovery 1.0*. OpenID Foundation.
https://openid.net/specs/openid-connect-discovery-1_0.html

Semgrep, Inc. (2026). *Ignoring findings in files*. Semgrep documentation.
https://semgrep.dev/docs/ignoring-files-folders-code
