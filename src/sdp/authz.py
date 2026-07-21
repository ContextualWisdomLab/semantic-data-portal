from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit
from urllib.request import urlopen

import jwt
from jwt import InvalidTokenError, PyJWK
from sdp_core import ActorContext


_SUBJECTS = {
    "admin": ActorContext(subject="admin", tenant_id="demo", roles=["admin", "data-analyst", "platform-admin"]),
    "security": ActorContext(subject="security", tenant_id="demo", roles=["security", "platform-admin"]),
    "data-admin": ActorContext(subject="data-admin", tenant_id="demo", roles=["admin", "data-analyst"]),
    "analyst": ActorContext(subject="analyst", tenant_id="demo", roles=["data-analyst"]),
    "data-analyst": ActorContext(subject="data-analyst", tenant_id="demo", roles=["data-analyst"]),
    "external-analyst": ActorContext(subject="external-analyst", tenant_id="external", roles=["data-analyst"]),
}

_DEFAULT_OIDC_GROUP_ROLE_MAP = {
    "sdp-admins": ["admin", "data-analyst"],
    "sdp-analysts": ["data-analyst"],
    "sdp-platform-admins": ["platform-admin", "admin", "data-analyst"],
    "sdp-security": ["security"],
}

_SUBJECT_CLAIMS = ("preferred_username", "email", "sub")
_ALLOWED_JWT_ALGORITHMS = {"RS256", "RS384", "RS512", "ES256", "ES384", "ES512"}


def resolve_actor_context(subject: str) -> ActorContext:
    key = subject.strip().lower()
    return _SUBJECTS.get(key, ActorContext(subject=subject, tenant_id="", roles=[]))


def has_role(subject: str, *roles: str) -> bool:
    context = resolve_actor_context(subject)
    return bool(set(roles).intersection(context.roles))


def can_access_tenant(subject: str, tenant_id: str) -> bool:
    context = resolve_actor_context(subject)
    return "platform-admin" in context.roles or context.tenant_id == tenant_id


def _claim_values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


def oidc_role_claims(claims: dict[str, Any]) -> list[str]:
    return _claim_values(claims.get("roles"))


def load_oidc_role_map() -> dict[str, list[str]]:
    raw = os.getenv("SDP_OIDC_GROUP_ROLE_MAP")
    if not raw:
        return _DEFAULT_OIDC_GROUP_ROLE_MAP

    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("SDP_OIDC_GROUP_ROLE_MAP must be a JSON object")
    return {str(group): _claim_values(roles) for group, roles in parsed.items()}


def validate_oidc_claim_shape(claims: dict[str, Any]) -> None:
    if not any(claims.get(key) for key in _SUBJECT_CLAIMS):
        raise ValueError("missing subject claim")
    if not (claims.get("tenant_id") or claims.get("tid") or claims.get("organization")):
        raise ValueError("missing tenant claim")
    if "exp" not in claims:
        raise ValueError("missing exp claim")

    try:
        expires_at = int(claims["exp"])
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid exp claim") from exc

    if expires_at <= int(datetime.now(timezone.utc).timestamp()):
        raise ValueError("expired token claims")


def resolve_oidc_actor_context(
    claims: dict[str, Any],
    *,
    role_map: dict[str, list[str]] | None = None,
) -> ActorContext:
    validate_oidc_claim_shape(claims)
    mapping = role_map or load_oidc_role_map()
    subject = (
        claims.get("preferred_username")
        or claims.get("email")
        or claims.get("sub")
        or "anonymous"
    )
    tenant_id = str(claims.get("tenant_id") or claims.get("tid") or claims.get("organization") or "")
    groups = _claim_values(claims.get("groups"))

    roles: set[str] = set()
    for group in groups:
        roles.update(mapping.get(group, []))

    return ActorContext(subject=str(subject), tenant_id=tenant_id, roles=sorted(roles))


def _load_jwks_from_url(jwks_url: str) -> dict[str, Any]:
    parsed = urlsplit(jwks_url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("OIDC JWKS URL must be absolute HTTPS")
    timeout = float(os.getenv("SDP_OIDC_JWKS_TIMEOUT_SECONDS", "2"))
    # The HTTPS-only check above excludes urllib's local file handlers.
    with urlopen(jwks_url, timeout=timeout) as response:  # nosemgrep: python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected
        return json.loads(response.read().decode("utf-8"))


def _select_jwk(jwks: dict[str, Any], kid: str | None) -> dict[str, Any]:
    if not kid:
        raise ValueError("missing token kid")
    keys = jwks.get("keys")
    if not isinstance(keys, list):
        raise ValueError("jwks must contain keys")
    for key in keys:
        if isinstance(key, dict) and key.get("kid") == kid:
            return key
    raise ValueError("no matching jwks key")


def verify_oidc_jwks_token(
    token: str,
    *,
    issuer: str | None = None,
    audience: str | None = None,
    jwks: dict[str, Any] | None = None,
    role_map: dict[str, list[str]] | None = None,
) -> tuple[ActorContext, dict[str, Any]]:
    expected_issuer = issuer or os.getenv("SDP_OIDC_ISSUER")
    expected_audience = audience or os.getenv("SDP_OIDC_AUDIENCE")
    jwks_url = os.getenv("SDP_OIDC_JWKS_URL")

    if not expected_issuer:
        raise ValueError("missing OIDC issuer")
    if not expected_audience:
        raise ValueError("missing OIDC audience")
    if jwks is None:
        if not jwks_url:
            raise ValueError("missing OIDC JWKS")
        jwks = _load_jwks_from_url(jwks_url)

    try:
        header = jwt.get_unverified_header(token)
        alg = header.get("alg")
        if alg not in _ALLOWED_JWT_ALGORITHMS:
            raise ValueError("unsupported token algorithm")
        jwk = _select_jwk(jwks, header.get("kid"))
        signing_key = PyJWK.from_dict(jwk).key
        claims = jwt.decode(
            token,
            signing_key,
            algorithms=[alg],
            audience=expected_audience,
            issuer=expected_issuer,
            options={"require": ["exp", "iss", "aud"]},
        )
    except (InvalidTokenError, ValueError) as exc:
        raise ValueError(f"invalid token: {exc}") from exc

    context = resolve_oidc_actor_context(claims, role_map=role_map)
    return context, claims
