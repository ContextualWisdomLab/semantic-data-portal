# OIDC JWKS transport security and SAST evidence

## Decision

`SDP_OIDC_JWKS_URL` is an operator-supplied URL for the public JSON Web Key Set
used to verify OpenID Connect tokens. Production code accepts only an
unambiguous HTTPS URL with a host. It rejects local-file URLs, plaintext HTTP,
embedded user information, and fragments before opening any resource.

This is a fail-closed boundary. OAuth 2.0 Authorization Server Metadata requires
`jwks_uri` to use HTTPS. OpenID Connect Discovery likewise defines the JWKS
location as the provider's public signing-key endpoint. The verifier therefore
does not provide a compatibility escape hatch for insecure development URLs;
tests that need deterministic keys pass a JWKS document directly to the
verification function.

## Runtime invariants

1. The URL scheme is exactly `https`, compared case-insensitively.
2. The parsed URL has a hostname.
3. User information is absent, so credentials cannot be hidden in the
   authority component.
4. The URL has no fragment, because fragments are client-side components and
   do not identify the fetched HTTP resource.
5. The configured timeout remains bounded by
   `SDP_OIDC_JWKS_TIMEOUT_SECONDS`.
6. Token algorithms remain restricted to the explicit asymmetric allowlist,
   and issuer, audience, expiration, and key identifier checks remain enabled.

Regression coverage lives in `tests/test_oidc_transport_security.py`. It proves
that insecure and ambiguous values are rejected before `urlopen` can execute,
and that a valid HTTPS endpoint receives the configured timeout.

## Reviewed SAST findings

### OIDC JWKS loader

The original dynamic-URL finding was valid: Python's URL opener supports
schemes beyond HTTP, including local files. The implementation now validates
the complete transport boundary before the call. The adjacent `nosemgrep`
annotation documents that post-validation state and is scoped to the exact
rule and call site.

### Observability sink

`SDP_LOG_SINK_URL` intentionally supports two explicit transports. The `file`
branch writes append-only JSON Lines with `Path.open`; only the separate
`http`/`https` branch constructs an HTTP request and calls `urlopen`. The
adjacent rule-specific annotation records this already-enforced scheme split.
It does not suppress other rules or other call sites.

### Apache AGE query execution

Apache AGE requires a composed SQL call around `cypher()`. The graph name and
the complete server-built Cypher body are represented with Psycopg `Literal`
objects, the result declaration comes from a closed map of constant SQL
objects, and every request value remains in the positional JSON parameter.
`tests/test_graph_security.py` proves that stacked-SQL payloads never enter the
statement text, graph names and Cypher bodies are quoted by Psycopg, and unknown
result declarations fail before database execution. The rule-specific
annotation therefore records a tested framework mismatch rather than accepting
an unbounded raw-query risk.

## Verification requirements

A change to any of these boundaries is incomplete unless all of the following
hold on the same pull-request head:

- the API test suite passes, including transport and graph injection regressions;
- SAST reports no unsuppressed finding;
- the security dependency scan passes against the hash-pinned lock files; and
- the test environment resolves the same cryptography release as the runtime
  and development locks.

## References

Jones, M., Sakimura, N., & Bradley, J. (2018). *OAuth 2.0 authorization server
metadata* (RFC 8414). RFC Editor. https://doi.org/10.17487/RFC8414

OpenID Foundation. (2014). *OpenID Connect Discovery 1.0*. https://openid.net/specs/openid-connect-discovery-1_0.html

Psycopg Team. (2026). *SQL string composition*. Psycopg documentation.
https://www.psycopg.org/docs/sql.html

Semgrep, Inc. (2026). *Resolve findings using Semgrep AppSec Platform*.
https://semgrep.dev/docs/for-developers/resolve-findings-through-app
