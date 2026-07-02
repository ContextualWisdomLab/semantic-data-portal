from __future__ import annotations

from sdp_core import ActorContext


_SUBJECTS = {
    "admin": ActorContext(subject="admin", tenant_id="demo", roles=["admin", "data-analyst", "platform-admin"]),
    "security": ActorContext(subject="security", tenant_id="demo", roles=["security", "platform-admin"]),
    "data-admin": ActorContext(subject="data-admin", tenant_id="demo", roles=["admin", "data-analyst"]),
    "analyst": ActorContext(subject="analyst", tenant_id="demo", roles=["data-analyst"]),
    "data-analyst": ActorContext(subject="data-analyst", tenant_id="demo", roles=["data-analyst"]),
    "external-analyst": ActorContext(subject="external-analyst", tenant_id="external", roles=["data-analyst"]),
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
