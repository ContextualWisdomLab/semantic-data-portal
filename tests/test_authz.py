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
    jwks = {"keys": [{"kid": "k1", "kty": "RSA"}]}
    assert authz._select_jwk(jwks, "k1")["kid"] == "k1"
    with pytest.raises(ValueError):  # missing kid
        authz._select_jwk(jwks, None)
    with pytest.raises(ValueError):  # keys not a list
        authz._select_jwk({"keys": "nope"}, "k1")
    with pytest.raises(ValueError):  # no matching kid
        authz._select_jwk(jwks, "absent")


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
    )
    assert event.result == "unmapped"
    assert event.action == authz.OIDC_MAPPING_AUDIT_ACTION
    assert event.resource == authz.OIDC_MAPPING_AUDIT_RESOURCE
    assert event.details["ignored_role_claims"] == []
    assert event.details["granted_roles"] == []
