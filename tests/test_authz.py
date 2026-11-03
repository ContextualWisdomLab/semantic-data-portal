"""Tests for OIDC JWKS loading, focused on the URL-scheme hardening."""

from __future__ import annotations

import json

import pytest

from sdp import authz


def test_load_jwks_from_url_rejects_non_http_schemes(monkeypatch):
    """A misconfigured non-http(s) JWKS URL must be rejected before any fetch,
    so urllib's ``file://`` support cannot be turned into local file disclosure."""
    unexpected_calls = []

    def _unexpected_urlopen(*args, **kwargs):
        unexpected_calls.append((args, kwargs))
        raise AssertionError("urlopen must not be called for a rejected URL scheme")

    monkeypatch.setattr(authz, "urlopen", _unexpected_urlopen)
    for bad_url in ("file:///etc/passwd", "ftp://host/keys.json", "gopher://x", ""):
        with pytest.raises(ValueError):
            authz._load_jwks_from_url(bad_url)

    assert unexpected_calls == []


def test_load_jwks_from_url_fetches_over_https(monkeypatch):
    """An https JWKS URL passes the scheme allow-list and its JSON body is
    parsed and returned."""
    payload = {"keys": [{"kid": "abc", "kty": "RSA"}]}

    class _FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return json.dumps(payload).encode("utf-8")

    captured = {}

    def _fake_urlopen(url, timeout=None):
        captured["url"] = url
        captured["timeout"] = timeout
        return _FakeResponse()

    monkeypatch.delenv("SDP_OIDC_JWKS_TIMEOUT_SECONDS", raising=False)
    monkeypatch.setattr(authz, "urlopen", _fake_urlopen)
    result = authz._load_jwks_from_url("https://idp.example/.well-known/jwks.json")

    assert result == payload
    assert captured["url"] == "https://idp.example/.well-known/jwks.json"
    assert captured["timeout"] == pytest.approx(2.0)


def test_load_jwks_from_url_honours_timeout_override(monkeypatch):
    """The JWKS fetch timeout is configurable via SDP_OIDC_JWKS_TIMEOUT_SECONDS."""
    monkeypatch.setenv("SDP_OIDC_JWKS_TIMEOUT_SECONDS", "5")

    class _FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return b"{}"

    seen = {}

    def _fake_urlopen(url, timeout=None):
        seen["timeout"] = timeout
        return _FakeResponse()

    monkeypatch.setattr(authz, "urlopen", _fake_urlopen)
    assert authz._load_jwks_from_url("http://localhost:8080/jwks") == {}
    assert seen["timeout"] == pytest.approx(5.0)


# --- OIDC claim/role/JWK guard branches (security-critical error paths) ---

import time

import jwt as _jwt


def test_claim_values_handles_str_list_none_and_scalar():
    assert authz._claim_values(None) == []
    assert authz._claim_values("one") == ["one"]
    assert authz._claim_values(["a", 2]) == ["a", "2"]
    assert authz._claim_values(7) == ["7"]  # non-str, non-list scalar


def test_load_oidc_role_map_default_and_override(monkeypatch):
    monkeypatch.delenv("SDP_OIDC_GROUP_ROLE_MAP", raising=False)
    assert authz.load_oidc_role_map() == authz._DEFAULT_OIDC_GROUP_ROLE_MAP

    monkeypatch.setenv("SDP_OIDC_GROUP_ROLE_MAP", '{"grp": ["data-analyst"]}')
    assert authz.load_oidc_role_map() == {"grp": ["data-analyst"]}

    monkeypatch.setenv("SDP_OIDC_GROUP_ROLE_MAP", "[]")
    with pytest.raises(ValueError):
        authz.load_oidc_role_map()


def _valid_claims(**overrides):
    claims = {
        "preferred_username": "alice",
        "tenant_id": "demo",
        "exp": int(time.time()) + 3600,
    }
    claims.update(overrides)
    return claims


def test_validate_oidc_claim_shape_guard_branches():
    authz.validate_oidc_claim_shape(_valid_claims())  # happy path
    with pytest.raises(ValueError):  # missing subject
        authz.validate_oidc_claim_shape({"tenant_id": "d", "exp": int(time.time()) + 60})
    with pytest.raises(ValueError):  # missing tenant
        authz.validate_oidc_claim_shape({"sub": "s", "exp": int(time.time()) + 60})
    with pytest.raises(ValueError):  # missing exp
        authz.validate_oidc_claim_shape({"sub": "s", "tenant_id": "d"})
    with pytest.raises(ValueError):  # invalid exp type
        authz.validate_oidc_claim_shape({"sub": "s", "tenant_id": "d", "exp": "soon"})
    with pytest.raises(ValueError):  # expired
        authz.validate_oidc_claim_shape({"sub": "s", "tenant_id": "d", "exp": 1})


def test_select_jwk_guard_branches():
    """``_select_jwk`` now takes the token's algorithm as well as its kid.

    Matching on ``kid`` alone let an outsider pair any allow-listed algorithm
    with any configured key. The allow-list already refuses ``none`` and the
    HMAC families so this was never a signature bypass, but PyJWT raises
    ``InvalidKeyError`` (a ``PyJWTError``, *not* an ``InvalidTokenError``) or a
    plain ``TypeError`` for the mismatch, and neither was caught - so the
    refusal escaped as an unauthenticated 500 while the published contract for
    the route is ``(400,)``.
    """
    jwks = {"keys": [{"kid": "k1", "kty": "RSA"}]}
    assert authz._select_jwk(jwks, "k1", "RS256")["kid"] == "k1"
    with pytest.raises(ValueError):  # missing kid
        authz._select_jwk(jwks, None, "RS256")
    with pytest.raises(ValueError):  # keys not a list
        authz._select_jwk({"keys": "nope"}, "k1", "RS256")
    with pytest.raises(ValueError):  # no matching kid
        authz._select_jwk(jwks, "absent", "RS256")
    with pytest.raises(ValueError):  # an RSA key cannot verify ES256
        authz._select_jwk(jwks, "k1", "ES256")
    published = {"keys": [{"kid": "k2", "kty": "RSA", "alg": "RS256"}]}
    with pytest.raises(ValueError):  # published for a different algorithm
        authz._select_jwk(published, "k2", "RS512")


def test_verify_oidc_jwks_token_config_and_alg_guards(monkeypatch):
    monkeypatch.delenv("SDP_OIDC_ISSUER", raising=False)
    monkeypatch.delenv("SDP_OIDC_AUDIENCE", raising=False)
    monkeypatch.delenv("SDP_OIDC_JWKS_URL", raising=False)
    with pytest.raises(ValueError):  # missing issuer
        authz.verify_oidc_jwks_token("t", jwks={"keys": []})
    with pytest.raises(ValueError):  # missing audience
        authz.verify_oidc_jwks_token("t", issuer="iss", jwks={"keys": []})
    with pytest.raises(ValueError):  # jwks is None and no JWKS URL configured
        authz.verify_oidc_jwks_token("t", issuer="iss", audience="aud")

    # Unsupported algorithm is rejected before signature verification.
    hs_token = _jwt.encode({"sub": "s"}, "secret", algorithm="HS256")
    with pytest.raises(ValueError):
        authz.verify_oidc_jwks_token(hs_token, issuer="iss", audience="aud", jwks={"keys": []})


def test_verify_oidc_jwks_token_loads_jwks_from_env_url(monkeypatch):
    monkeypatch.setenv("SDP_OIDC_JWKS_URL", "https://idp.example/jwks")

    def _fake_load(url):
        assert url == "https://idp.example/jwks"
        return {"keys": []}

    monkeypatch.setattr(authz, "_load_jwks_from_url", _fake_load)
    # Unsupported alg is rejected after the env JWKS is loaded -> wrapped ValueError,
    # which exercises the `jwks = _load_jwks_from_url(jwks_url)` branch.
    hs_token = _jwt.encode({"sub": "s"}, "secret", algorithm="HS256")
    with pytest.raises(ValueError):
        authz.verify_oidc_jwks_token(hs_token, issuer="iss", audience="aud")


def test_normalize_group_role_map_wraps_flat_entries_in_wildcard_scope():
    """A flat map must apply to every tenant through the wildcard scope, and
    scalar role values must be coerced into role name lists."""
    assert authz.normalize_group_role_map({"sdp-analysts": "data-analyst"}) == {
        authz.TENANT_SCOPE_WILDCARD: {"sdp-analysts": ["data-analyst"]}
    }


def test_normalize_group_role_map_returns_empty_scope_set_for_empty_map():
    """An empty configured map must normalize to no scopes rather than to a
    wildcard scope that would grant every group nothing in a hidden way."""
    assert authz.normalize_group_role_map({}) == {}


def test_normalize_group_role_map_keeps_tenant_scoped_entries():
    """A tenant-scoped map must be preserved per tenant, with role coercion
    applied inside each scope."""
    assert authz.normalize_group_role_map(
        {"demo": {"sdp-analysts": ["data-analyst"]}, "external": {"sdp-analysts": []}}
    ) == {"demo": {"sdp-analysts": ["data-analyst"]}, "external": {"sdp-analysts": []}}


def test_normalize_group_role_map_rejects_mixed_shapes():
    """Mixing flat and tenant-scoped entries is an operator typo that would
    silently read a tenant identifier as a group name, so it must be refused."""
    with pytest.raises(ValueError, match="must not mix flat and tenant-scoped"):
        authz.normalize_group_role_map({"demo": {"sdp-analysts": []}, "sdp-admins": ["admin"]})


def test_normalize_group_role_map_rejects_blank_tenant_scope():
    """A blank tenant scope cannot be matched against any token tenant claim,
    so it must be refused instead of becoming dead configuration."""
    with pytest.raises(ValueError, match="tenant scope must not be empty"):
        authz.normalize_group_role_map({"   ": {"sdp-analysts": ["data-analyst"]}})


def test_tenant_scope_overrides_wildcard_group_entry():
    """A tenant scope must be able to both widen and revoke a wildcard grant
    for the same group name."""
    role_map = {
        authz.TENANT_SCOPE_WILDCARD: {"sdp-analysts": ["data-analyst"]},
        "external": {"sdp-analysts": []},
        "demo": {"sdp-admins": ["admin"]},
    }
    assert authz.tenant_scoped_group_roles(role_map, "external") == {"sdp-analysts": []}
    assert authz.tenant_scoped_group_roles(role_map, "demo") == {
        "sdp-analysts": ["data-analyst"],
        "sdp-admins": ["admin"],
    }
    assert authz.tenant_scoped_group_roles(role_map, "") == {"sdp-analysts": ["data-analyst"]}


def test_oidc_tenant_claim_prefers_first_populated_claim():
    """The tenant claim must be read from tenant_id, tid, then organization,
    and must be empty rather than guessed when none is populated."""
    assert authz.oidc_tenant_claim({"tenant_id": "demo", "tid": "other"}) == "demo"
    assert authz.oidc_tenant_claim({"tid": "demo"}) == "demo"
    assert authz.oidc_tenant_claim({"organization": "demo"}) == "demo"
    assert authz.oidc_tenant_claim({}) == ""


def test_oidc_group_role_bindings_report_unmapped_and_deduplicated_groups():
    """Bindings must list each distinct group once in claim order, including
    groups no scope maps, so a reviewer can read refusals as well as grants."""
    bindings = authz.oidc_group_role_bindings(
        {"groups": ["sdp-analysts", "sdp-analysts", "unknown-group"], "tenant_id": "demo"},
        role_map={"demo": {"sdp-analysts": ["data-analyst"]}},
    )
    assert bindings == [
        {"group_name": "sdp-analysts", "tenant_scope": "demo", "granted_roles": ["data-analyst"]},
        {"group_name": "unknown-group", "tenant_scope": "", "granted_roles": []},
    ]


def test_oidc_group_role_bindings_treat_explicit_empty_map_as_no_grant(monkeypatch):
    """An explicitly empty role map must grant nothing rather than fall back to
    the configured default map."""
    monkeypatch.delenv("SDP_OIDC_GROUP_ROLE_MAP", raising=False)
    bindings = authz.oidc_group_role_bindings({"groups": ["sdp-admins"], "tenant_id": "demo"}, role_map={})
    assert bindings == [{"group_name": "sdp-admins", "tenant_scope": "", "granted_roles": []}]


def test_oidc_group_role_bindings_fall_back_to_configured_map(monkeypatch):
    """Omitting the role map entirely must read the configured map, which keeps
    the wildcard default available to deployments that do not scope groups."""
    monkeypatch.setenv("SDP_OIDC_GROUP_ROLE_MAP", json.dumps({"sdp-analysts": ["data-analyst"]}))
    bindings = authz.oidc_group_role_bindings({"groups": ["sdp-analysts"], "tenant_id": "demo"})
    assert bindings == [
        {
            "group_name": "sdp-analysts",
            "tenant_scope": authz.TENANT_SCOPE_WILDCARD,
            "granted_roles": ["data-analyst"],
        }
    ]


def test_load_oidc_role_map_returns_tenant_scoped_configuration(monkeypatch):
    """The reader must pass a tenant-scoped configuration through unchanged so
    that shape validation stays in one place."""
    scoped = {"demo": {"sdp-analysts": ["data-analyst"]}}
    monkeypatch.setenv("SDP_OIDC_GROUP_ROLE_MAP", json.dumps(scoped))
    assert authz.load_oidc_role_map() == scoped


def test_record_oidc_mapping_audit_event_marks_unmapped_contexts():
    """A mapping that grants no role must still be auditable, and must be
    labelled unmapped so a reviewer can find refused sign-ins."""
    context = authz.ActorContext(subject="analyst@example.com", tenant_id="demo", roles=[])
    event = authz.record_oidc_mapping_audit_event(
        context,
        [{"group_name": "unknown-group", "tenant_scope": "", "granted_roles": []}],
        mapping_mode="claim_mapping_preview",
        # No default: the answer decides whose ledger the row lands in, so every
        # call site states it. A verified mapping keeps mapped/unmapped.
        tenant_verified=True,
    )
    assert event.result == "unmapped"
    assert event.action == authz.OIDC_MAPPING_AUDIT_ACTION
    assert event.resource == authz.OIDC_MAPPING_AUDIT_RESOURCE
    assert event.details["ignored_role_claims"] == []
    assert event.details["granted_roles"] == []



def test_an_unverified_mapping_is_not_attributed_to_the_claimed_tenant():
    """``tenant_verified=False`` files the row outside any real tenant.

    The evidence stores file an audit row by ``details['tenant_id']``, and this
    recorder wrote ``actor_context.tenant_id`` verbatim - which on the preview
    path comes from unverified caller claims. An outsider could therefore plant
    a row in any tenant's ledger.
    """
    context = authz.ActorContext(
        subject="mallory@evil.example", tenant_id="external", roles=["admin"]
    )
    event = authz.record_oidc_mapping_audit_event(
        context,
        [{"group_name": "sdp-platform-admins", "tenant_scope": "*", "granted_roles": ["admin"]}],
        mapping_mode="claim_mapping_preview",
        tenant_verified=False,
    )
    assert event.details["tenant_id"] == authz.UNRESOLVED_TENANT_ID
    assert event.details["claimed_tenant_id"] == "external"
    assert event.details["tenant_verified"] is False
    # "mapped" would read as a real grant.
    assert event.result == "previewed"


def test_an_attacker_chosen_alg_kid_pairing_is_a_400_not_a_500(monkeypatch):
    """The published contract for ``/enterprise/auth/oidc-verify`` is ``(400,)``.

    ``_select_jwk`` matched on ``kid`` alone and the token's own header ``alg``
    was then handed to ``jwt.decode``. For a key-type mismatch PyJWT raises
    ``InvalidKeyError`` - which descends from ``PyJWTError``, **not** from
    ``InvalidTokenError`` - or a plain ``TypeError``, and the handler caught
    neither. Measured against an operator JWKS holding one RSA key::

        header {"alg": "ES256", "kid": "op-key-1"} -> 500 Internal Server Error
        header {"alg": "ES384", "kid": "op-key-1"} -> 500 Internal Server Error
        header {"alg": "RS512", "kid": "op-key-1"} -> 400 invalid token
        header {"alg": "HS256", "kid": "op-key-1"} -> 400 unsupported algorithm
        header {"alg": "none",  "kid": "op-key-1"} -> 400 unsupported algorithm

    The allow-list already refused ``none`` and the HMAC families, so this was
    never a signature bypass - but an unauthenticated 500 with a traceback
    contradicted the document this repository publishes.
    """
    import json

    import jwt
    from cryptography.hazmat.primitives.asymmetric import rsa
    from fastapi.testclient import TestClient
    from jwt.utils import to_base64url_uint

    from sdp.api import app

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    numbers = key.public_key().public_numbers()
    jwks = {
        "keys": [
            {
                "kty": "RSA",
                "kid": "op-key-1",
                "use": "sig",
                "alg": "RS256",
                "n": to_base64url_uint(numbers.n).decode(),
                "e": to_base64url_uint(numbers.e).decode(),
            }
        ]
    }
    monkeypatch.setenv("SDP_OIDC_JWKS", json.dumps(jwks))
    monkeypatch.setenv("SDP_OIDC_ISSUER", "https://idp.example")
    monkeypatch.setenv("SDP_OIDC_AUDIENCE", "sdp")
    authz.clear_jwks_cache()

    client = TestClient(app, raise_server_exceptions=False)
    for alg in sorted(authz._ALLOWED_JWT_ALGORITHMS | {"HS256", "none"}):
        header = jwt.utils.base64url_encode(
            json.dumps({"alg": alg, "kid": "op-key-1"}).encode()
        ).decode()
        body = jwt.utils.base64url_encode(json.dumps({"sub": "x"}).encode()).decode()
        response = client.post(
            "/enterprise/auth/oidc-verify", json={"token": f"{header}.{body}.AAAA"}
        )
        assert response.status_code == 400, f"{alg}: {response.status_code} {response.text}"


def test_a_malformed_token_does_not_reach_the_identity_provider(monkeypatch, tmp_path):
    """The JWKS was fetched before the token was parsed, and on every call.

    ``_load_configured_jwks`` ran unconditionally with no cache, so a token
    that cannot even be base64-decoded triggered a round trip to the operator's
    IdP: 25 unauthenticated posts of the literal ``"a.b.c"`` produced 25 GETs
    on the JWKS endpoint, from the portal's own address. A repeated *valid*
    verification did the same.
    """
    import json
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    from fastapi.testclient import TestClient

    from sdp.api import app

    hits: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 - http.server's interface
            hits.append(self.path)
            payload = json.dumps({"keys": []}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):  # noqa: D102 - silence the test server
            return

    server = HTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        monkeypatch.delenv("SDP_OIDC_JWKS", raising=False)
        monkeypatch.setenv("SDP_OIDC_JWKS_URL", f"http://127.0.0.1:{port}/jwks")
        monkeypatch.setenv("SDP_OIDC_ISSUER", "https://idp.example")
        monkeypatch.setenv("SDP_OIDC_AUDIENCE", "sdp")
        authz.clear_jwks_cache()

        client = TestClient(app, raise_server_exceptions=False)
        for _ in range(25):
            refused = client.post("/enterprise/auth/oidc-verify", json={"token": "a.b.c"})
            assert refused.status_code == 400, refused.text
        assert hits == [], f"a malformed token fetched the JWKS {len(hits)} time(s)"
    finally:
        server.shutdown()
        server.server_close()
        authz.clear_jwks_cache()
