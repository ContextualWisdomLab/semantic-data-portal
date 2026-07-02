from __future__ import annotations

import json
import os
from datetime import datetime, timezone
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

_DEFAULT_OIDC_GROUP_ROLE_MAP = {
    "sdp-admins": ["admin", "data-analyst"],
    "sdp-analysts": ["data-analyst"],
    "sdp-platform-admins": ["platform-admin", "admin", "data-analyst"],
    "sdp-security": ["security"],
}

_SUBJECT_CLAIMS = ("preferred_username", "email", "sub")


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
