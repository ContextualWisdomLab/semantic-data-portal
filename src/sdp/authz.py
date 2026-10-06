"""Actor resolution, OIDC claim mapping, and JWKS token verification.

Role grants are tenant scoped: a group claim only grants the roles that the
token's tenant scope authorizes, and every mapping is recorded as an audit
event carrying group names, granting scopes, and resolved roles only.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit
from urllib.request import urlopen
from uuid import uuid4

import jwt
from jwt import InvalidTokenError, PyJWK
from sdp_core import ActorContext, AuditEvent

from .evidence import append_audit_event


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
_TENANT_CLAIMS = ("tenant_id", "tid", "organization")
_ALLOWED_JWT_ALGORITHMS = {"RS256", "RS384", "RS512", "ES256", "ES384", "ES512"}

TENANT_SCOPE_WILDCARD = "*"
OIDC_MAPPING_AUDIT_RESOURCE = "enterprise/auth/oidc"
OIDC_MAPPING_AUDIT_ACTION = "oidc_group_role_mapping"


def resolve_actor_context(subject: str) -> ActorContext:
    """Resolve a demo subject name to its seeded actor context.

    An unknown subject resolves to an empty tenant with no roles so that an
    unrecognized caller is denied rather than defaulted into a tenant.
    """
    key = subject.strip().lower()
    return _SUBJECTS.get(key, ActorContext(subject=subject, tenant_id="", roles=[]))


def has_role(subject: str, *roles: str) -> bool:
    """Report whether the subject holds at least one of the given roles."""
    context = resolve_actor_context(subject)
    return bool(set(roles).intersection(context.roles))


def can_access_tenant(subject: str, tenant_id: str) -> bool:
    """Report whether the subject may act inside the given tenant.

    Only the explicit platform-admin role crosses a tenant boundary.
    """
    context = resolve_actor_context(subject)
    return "platform-admin" in context.roles or context.tenant_id == tenant_id


def _claim_values(value: Any) -> list[str]:
    """Coerce a scalar, list, or absent claim value into a string list."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


def oidc_role_claims(claims: dict[str, Any]) -> list[str]:
    """Read the direct role claims that mapping deliberately ignores.

    Roles are granted only through group bindings, so these values are
    reported for audit rather than honoured as grants.
    """
    return _claim_values(claims.get("roles"))


def load_oidc_role_map() -> dict[str, Any]:
    """Read the configured group-to-role map without normalizing its shape.

    The configured map may be written flat or tenant scoped, so shape
    validation is deferred to :func:`normalize_group_role_map` and this reader
    only guarantees that the configured value is a JSON object.
    """
    raw = os.getenv("SDP_OIDC_GROUP_ROLE_MAP")
    if not raw:
        return dict(_DEFAULT_OIDC_GROUP_ROLE_MAP)

    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("SDP_OIDC_GROUP_ROLE_MAP must be a JSON object")
    return parsed


def _normalize_group_roles(group_roles: Mapping[str, Any]) -> dict[str, list[str]]:
    """Coerce one tenant scope's group-to-role entries into role name lists."""
    return {str(group): _claim_values(roles) for group, roles in group_roles.items()}


def normalize_group_role_map(role_map: Mapping[str, Any]) -> dict[str, dict[str, list[str]]]:
    """Normalize a flat or tenant-scoped group-to-role map into tenant scopes.

    A flat ``{"group_name": ["role_name"]}`` map applies to every tenant and is
    returned under the :data:`TENANT_SCOPE_WILDCARD` scope. A tenant-scoped
    ``{"tenant_id": {"group_name": ["role_name"]}}`` map is kept as written.
    Mixing the two forms in one map is refused so that an operator typo cannot
    silently apply a tenant identifier as a group name, or the reverse.
    """
    if not role_map:
        return {}

    scoped_keys = [key for key, value in role_map.items() if isinstance(value, Mapping)]
    if not scoped_keys:
        return {TENANT_SCOPE_WILDCARD: _normalize_group_roles(role_map)}
    if len(scoped_keys) != len(role_map):
        raise ValueError("group role map must not mix flat and tenant-scoped entries")

    normalized_scopes: dict[str, dict[str, list[str]]] = {}
    for tenant_scope, group_roles in role_map.items():
        scope_name = str(tenant_scope).strip()
        if not scope_name:
            raise ValueError("group role map tenant scope must not be empty")
        normalized_scopes[scope_name] = _normalize_group_roles(group_roles)
    return normalized_scopes


def tenant_scoped_group_roles(role_map: Mapping[str, Any], tenant_id: str) -> dict[str, list[str]]:
    """Resolve the group-to-role entries that apply to one tenant.

    Wildcard entries apply first and an entry in the tenant's own scope
    replaces the wildcard entry for the same group, so a tenant scope can both
    widen and revoke a wildcard grant.
    """
    normalized_scopes = normalize_group_role_map(role_map)
    effective_roles = dict(normalized_scopes.get(TENANT_SCOPE_WILDCARD, {}))
    if tenant_id:
        effective_roles.update(normalized_scopes.get(tenant_id, {}))
    return effective_roles


def oidc_tenant_claim(identity_claims: Mapping[str, Any]) -> str:
    """Read the tenant identifier from the first populated tenant claim."""
    for claim_name in _TENANT_CLAIMS:
        claim_value = identity_claims.get(claim_name)
        if claim_value:
            return str(claim_value)
    return ""


def oidc_group_role_bindings(
    identity_claims: Mapping[str, Any],
    *,
    role_map: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Explain which tenant scope granted which roles for the token's groups.

    One row is returned per distinct group claim, in claim order, including
    groups that no scope maps, so a security reviewer can read refusals as well
    as grants. An explicitly empty ``role_map`` grants nothing rather than
    falling back to the configured map.
    """
    configured_map = load_oidc_role_map() if role_map is None else role_map
    normalized_scopes = normalize_group_role_map(configured_map)
    tenant_id = oidc_tenant_claim(identity_claims)
    tenant_scope_roles = normalized_scopes.get(tenant_id, {}) if tenant_id else {}
    wildcard_scope_roles = normalized_scopes.get(TENANT_SCOPE_WILDCARD, {})

    group_bindings: list[dict[str, Any]] = []
    seen_group_names: set[str] = set()
    for group_name in _claim_values(identity_claims.get("groups")):
        if group_name in seen_group_names:
            continue
        seen_group_names.add(group_name)
        if group_name in tenant_scope_roles:
            granting_scope = tenant_id
            granted_roles = tenant_scope_roles[group_name]
        elif group_name in wildcard_scope_roles:
            granting_scope = TENANT_SCOPE_WILDCARD
            granted_roles = wildcard_scope_roles[group_name]
        else:
            granting_scope = ""
            granted_roles = []
        group_bindings.append(
            {
                "group_name": group_name,
                "tenant_scope": granting_scope,
                "granted_roles": sorted(set(granted_roles)),
            }
        )
    return group_bindings


def record_oidc_mapping_audit_event(
    actor_context: ActorContext,
    group_bindings: list[dict[str, Any]],
    *,
    mapping_mode: str,
    ignored_role_claims: list[str] | None = None,
) -> AuditEvent:
    """Append one audit event explaining an OIDC group-to-role mapping.

    The event carries group names, granting tenant scopes, and resolved role
    names only. Tokens, signatures, and raw claim payloads never reach the
    evidence store through this path.
    """
    audit_event = AuditEvent(
        id=str(uuid4()),
        actor=actor_context.subject,
        action=OIDC_MAPPING_AUDIT_ACTION,
        resource=OIDC_MAPPING_AUDIT_RESOURCE,
        result="mapped" if actor_context.roles else "unmapped",
        reason=f"oidc group mapping resolved {len(actor_context.roles)} role(s)",
        details={
            "mapping_mode": mapping_mode,
            "tenant_id": actor_context.tenant_id,
            "granted_roles": list(actor_context.roles),
            "group_bindings": group_bindings,
            "ignored_role_claims": list(ignored_role_claims or []),
        },
    )
    return append_audit_event(audit_event)


def validate_oidc_claim_shape(claims: dict[str, Any]) -> None:
    """Reject claims missing a subject, tenant, or usable expiry.

    Raises:
        ValueError: If a required claim is absent, unparsable, or expired.
    """
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
    role_map: Mapping[str, Any] | None = None,
) -> ActorContext:
    """Map validated identity claims onto a tenant-scoped actor context.

    Roles come only from the group bindings that the token's tenant scope
    authorizes, so a group that grants roles under one tenant cannot grant them
    under another.
    """
    validate_oidc_claim_shape(claims)
    group_bindings = oidc_group_role_bindings(claims, role_map=role_map)
    subject_name = (
        claims.get("preferred_username")
        or claims.get("email")
        or claims.get("sub")
        or "anonymous"
    )

    granted_roles: set[str] = set()
    for group_binding in group_bindings:
        granted_roles.update(group_binding["granted_roles"])

    return ActorContext(
        subject=str(subject_name),
        tenant_id=oidc_tenant_claim(claims),
        roles=sorted(granted_roles),
    )


_ALLOWED_JWKS_SCHEMES = frozenset({"https", "http"})


def _load_jwks_from_url(jwks_url: str) -> dict[str, Any]:
    """Fetch a JWKS document over an allow-listed http(s) URL."""
    # Restrict the JWKS fetch to HTTP(S). urllib honours file:// (and other
    # schemes), so without this guard a misconfigured SDP_OIDC_JWKS_URL such as
    # "file:///etc/passwd" would turn an operator misconfiguration into local
    # file disclosure.
    scheme = urlsplit(jwks_url).scheme.lower()
    if scheme not in _ALLOWED_JWKS_SCHEMES:
        raise ValueError("OIDC JWKS URL must use the http or https scheme")
    timeout = float(os.getenv("SDP_OIDC_JWKS_TIMEOUT_SECONDS", "2"))
    # nosemgrep: python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected -- scheme is allow-listed to http(s) above; JWKS URL is operator config, not request input
    with urlopen(jwks_url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _select_jwk(jwks: dict[str, Any], kid: str | None) -> dict[str, Any]:
    """Select the JWKS key matching the token's key identifier."""
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
    role_map: Mapping[str, Any] | None = None,
) -> tuple[ActorContext, dict[str, Any]]:
    """Verify a token against JWKS and map its claims to an actor context."""
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
