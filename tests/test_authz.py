"""Tests for OIDC JWKS loading, focused on the URL-scheme hardening."""

from __future__ import annotations

import json
import time

import jwt as _jwt
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


@pytest.mark.parametrize(
    ("subject_claims", "expected_subject"),
    [
        ({"preferred_username": "alice"}, "alice"),
        ({"email": "alice@example.com"}, "alice@example.com"),
        ({"sub": "subject-1"}, "subject-1"),
        (
            {"preferred_username": None, "email": "alice@example.com", "sub": "subject-1"},
            "alice@example.com",
        ),
        ({"preferred_username": None, "email": None, "sub": "subject-1"}, "subject-1"),
    ],
)
def test_subject_claim_uses_first_non_empty_string_alias(subject_claims, expected_subject):
    """A missing or JSON-null subject alias may fall through to the next string."""
    context = authz.resolve_oidc_actor_context(
        {
            "org": "cwl-org",
            "exp": int(time.time()) + 3600,
            **subject_claims,
        }
    )

    assert context.subject == expected_subject


@pytest.mark.parametrize(
    "invalid_subject",
    [123, True, ["alice"], {"id": "alice"}, "", "  "],
)
def test_subject_claim_rejects_non_string_or_blank_values(invalid_subject):
    """A present subject alias cannot be coerced into ActorContext.subject."""
    with pytest.raises(ValueError, match=r"(must be a string|must be non-empty)"):
        authz.resolve_oidc_actor_context(
            {
                "preferred_username": invalid_subject,
                "email": "alice@example.com",
                "sub": "subject-1",
                "org": "cwl-org",
                "exp": int(time.time()) + 3600,
            }
        )


def test_numeric_sub_claim_cannot_impersonate_string_subject():
    """A signed numeric sub must not become the string identity '123'."""
    with pytest.raises(ValueError, match=r"sub claim must be a string"):
        authz.resolve_oidc_actor_context(
            {
                "sub": 123,
                "org": "cwl-org",
                "exp": int(time.time()) + 3600,
            }
        )


def test_all_null_subject_aliases_are_missing():
    """JSON-null subject aliases do not invent an anonymous ActorContext."""
    with pytest.raises(ValueError, match=r"missing subject claim"):
        authz.resolve_oidc_actor_context(
            {
                "preferred_username": None,
                "email": None,
                "sub": None,
                "org": "cwl-org",
                "exp": int(time.time()) + 3600,
            }
        )


def test_keyverse_claim_aliases_map_to_tenant_and_bounded_role():
    """Keyverse org/role claims enter the existing tenant and RBAC policy."""
    context = authz.resolve_oidc_actor_context(
        {
            "sub": "keyverse-user-1",
            "org": "cwl-org",
            "workspace": "workspace-cwl",
            "role": "member",
            "exp": int(time.time()) + 3600,
        }
    )

    assert context.subject == "keyverse-user-1"
    assert context.tenant_id == "cwl-org"
    assert context.roles == ["data-analyst"]


@pytest.mark.parametrize(
    ("keyverse_role", "expected_roles"),
    [
        ("member", ["data-analyst"]),
        ("data-analyst", ["data-analyst"]),
        ("data-admin", ["data-admin", "data-analyst"]),
        ("admin", ["admin", "data-analyst"]),
        ("platform-admin", ["platform-admin", "admin", "data-analyst"]),
        ("security", ["security"]),
    ],
)
def test_keyverse_allowed_roles_map_to_bounded_application_roles(
    keyverse_role, expected_roles
):
    """Every admitted Keyverse role maps to its documented bounded roles."""
    context = authz.resolve_oidc_actor_context(
        {
            "sub": "keyverse-user-roles",
            "org": "cwl-org",
            "role": keyverse_role,
            "exp": int(time.time()) + 3600,
        }
    )

    assert context.roles == sorted(expected_roles)


def test_keyverse_role_merges_with_group_derived_roles():
    """A valid singular Keyverse role may combine with an allow-listed group."""
    context = authz.resolve_oidc_actor_context(
        {
            "sub": "keyverse-user-groups",
            "org": "cwl-org",
            "role": "member",
            "groups": ["sdp-security"],
            "exp": int(time.time()) + 3600,
        }
    )

    assert context.roles == ["data-analyst", "security"]


def test_keyverse_role_array_does_not_combine_privileges():
    """An array role claim must fail closed instead of merging authorities."""
    with pytest.raises(ValueError, match=r"role claim must be a string"):
        authz.resolve_oidc_actor_context(
            {
                "sub": "keyverse-user-array-role",
                "org": "cwl-org",
                "role": ["member", "platform-admin"],
                "exp": int(time.time()) + 3600,
            }
        )


@pytest.mark.parametrize("invalid_org", [["cwl-org"], {"id": "cwl-org"}])
def test_keyverse_org_claim_must_be_a_non_empty_string(invalid_org):
    """Tenant claims with ambiguous JSON shapes must fail closed."""
    with pytest.raises(ValueError, match=r"org claim must be a string"):
        authz.resolve_oidc_actor_context(
            {
                "sub": "keyverse-user-invalid-org",
                "org": invalid_org,
                "exp": int(time.time()) + 3600,
            }
        )


@pytest.mark.parametrize("invalid_org", ["", "  "])
def test_keyverse_org_claim_must_be_non_empty(invalid_org):
    """A standalone Keyverse org alias must reject blank tenant authority."""
    with pytest.raises(ValueError, match=r"org claim must be non-empty"):
        authz.resolve_oidc_actor_context(
            {
                "sub": "keyverse-user-blank-org",
                "org": invalid_org,
                "exp": int(time.time()) + 3600,
            }
        )


@pytest.mark.parametrize("invalid_org", [None, [], {}, "", "  "])
def test_keyverse_org_alias_cannot_hide_behind_tenant_id(invalid_org):
    """Every present tenant alias is validated before alias precedence applies."""
    with pytest.raises(ValueError):
        authz.resolve_oidc_actor_context(
            {
                "sub": "keyverse-user-hidden-org",
                "tenant_id": "cwl-org",
                "org": invalid_org,
                "exp": int(time.time()) + 3600,
            }
        )


def test_keyverse_conflicting_tenant_aliases_fail_closed():
    """Different signed tenant aliases cannot silently select the first value."""
    with pytest.raises(ValueError, match=r"conflicting tenant claims"):
        authz.resolve_oidc_actor_context(
            {
                "sub": "keyverse-user-conflicting-org",
                "tenant_id": "cwl-org",
                "org": "other-org",
                "exp": int(time.time()) + 3600,
            }
        )


def test_keyverse_unknown_role_does_not_grant_access():
    """An unrecognized signed Keyverse role cannot become an application role."""
    context = authz.resolve_oidc_actor_context(
        {
            "sub": "keyverse-user-2",
            "org": "cwl-org",
            "role": "unreviewed-admin",
            "exp": int(time.time()) + 3600,
        }
    )

    assert context.roles == []


def test_decode_unverified_jwt_header_rejects_unusable_segments():
    """Header decoding stays local and never classifies PyJWT exception text."""
    valid = _jwt.encode({"sub": "s"}, "secret", algorithm="HS256")
    header = authz._decode_unverified_jwt_header(valid)
    assert isinstance(header, dict)
    assert header.get("alg") == "HS256"

    assert authz._decode_unverified_jwt_header("not-ascii-\u2603.payload.sig") is None
    assert authz._decode_unverified_jwt_header("@@@.payload.sig") is None
    invalid_utf8 = _jwt.utils.base64url_encode(b"\xff\xfe").decode()
    assert authz._decode_unverified_jwt_header(f"{invalid_utf8}.payload.sig") is None
    array_header = _jwt.utils.base64url_encode(b"[1,2]").decode()
    assert authz._decode_unverified_jwt_header(f"{array_header}.payload.sig") is None


def test_critical_jwt_header_failures_share_one_application_error():
    """Malformed and unsupported crit values map to the same application error."""
    authz._validate_jwt_header({"alg": "RS256"})
    for header in (
        {"alg": "RS256", "crit": ["https://example.com/custom-extension"]},
        {"alg": "RS256", "crit": "not-an-array"},
        {"alg": "RS256", "crit": [1]},
        {"alg": "RS256", "crit": []},
    ):
        with pytest.raises(ValueError, match=r"^unsupported critical JWT header$"):
            authz._validate_jwt_header(header)


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
