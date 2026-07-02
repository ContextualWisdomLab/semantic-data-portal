from __future__ import annotations

from typing import Any

from sdp_core import ActorContext


_SUBJECTS = {
    "admin": ActorContext(subject="admin", tenant_id="demo", roles=["admin", "data-analyst", "platform-admin"]),
    "security": ActorContext(subject="security", tenant_id="demo", roles=["security", "platform-admin"]),
    "data-admin": ActorContext(subject="data-admin", tenant_id="demo", roles=["admin", "data-analyst"]),
    "analyst": ActorContext(subject="analyst", tenant_id="demo", roles=["data-analyst"]),
    "data-analyst": ActorContext(subject="data-analyst", tenant_id="demo", roles=["data-analyst"]),
    "external-analyst": ActorContext(subject="external-analyst", tenant_id="external", roles=["data-analyst"]),
}

_OIDC_ROLE_MAP = {
    "sdp-admins": ["admin", "data-analyst"],
    "sdp-analysts": ["data-analyst"],
    "sdp-platform-admins": ["platform-admin", "admin", "data-analyst"],
    "sdp-security": ["security"],
}


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


def resolve_oidc_actor_context(
    claims: dict[str, Any],
    *,
    role_map: dict[str, list[str]] | None = None,
) -> ActorContext:
    mapping = role_map or _OIDC_ROLE_MAP
    subject = (
        claims.get("preferred_username")
        or claims.get("email")
        or claims.get("sub")
        or "anonymous"
    )
    tenant_id = str(claims.get("tenant_id") or claims.get("tid") or claims.get("organization") or "")
    groups = _claim_values(claims.get("groups")) + _claim_values(claims.get("roles"))

    roles: set[str] = set()
    for group in groups:
        roles.update(mapping.get(group, []))

    return ActorContext(subject=str(subject), tenant_id=tenant_id, roles=sorted(roles))
