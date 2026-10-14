from __future__ import annotations

from typing import Any
from uuid import uuid4

from sdp_core.stores import UNRESOLVED_TENANT_ID

from .authz import can_access_tenant, has_role, resolve_actor_context
from .catalog import get_dataset
from .domain import PolicyDecision
from .evidence import record_policy_decision


def _effective_tenant_id(subject: str, resource: str, target_tenant_id: str | None = None) -> str:
    """Resolve which tenant an evidence row for this decision belongs to.

    A decision about an existing dataset belongs to the tenant that owns the
    dataset - that is the scope a tenant-scoped auditor queries for its own
    assets' access history. A decision that names no existing dataset (a
    ``create``, a discovery query, an unknown resource) has no owning tenant, so
    it belongs to the actor's. When neither resolves, the row is marked
    unresolved rather than attributed to a real tenant.
    """
    if target_tenant_id:
        # A create names a tenant the catalog cannot yet confirm; the caller supplies it.
        return target_tenant_id
    dataset = get_dataset(resource)
    if dataset and dataset.tenant_id:
        return dataset.tenant_id
    return resolve_actor_context(subject).tenant_id or UNRESOLVED_TENANT_ID


def _decision(*, tenant_id: str, **kwargs: Any) -> PolicyDecision:
    """Record one policy decision, stamped with the tenant it belongs to.

    The evidence store scopes rows by ``obligations['tenant_id']``, so the stamp
    is applied on every branch rather than only the ones whose obligations
    happen to mention a tenant. A branch that sets the key explicitly keeps its
    own value.
    """
    obligations = dict(kwargs.pop("obligations", None) or {})
    obligations.setdefault("tenant_id", tenant_id)
    return record_policy_decision(PolicyDecision(obligations=obligations, **kwargs))


def _is_admin(subject: str) -> bool:
    return has_role(subject, "admin", "platform-admin")


def _can_mutate(subject: str, action: str) -> bool:
    return _is_admin(subject) and action.lower() in {"create", "publish", "patch", "deprecate"}


def _has_reader_role(subject: str) -> bool:
    return has_role(subject, "data-analyst", "admin", "platform-admin", "security")


def evaluate(
    subject: str,
    resource: str,
    action: str,
    purpose: str,
    *,
    target_tenant_id: str | None = None,
) -> PolicyDecision:
    action_key = action.lower()
    decision_id = str(uuid4())
    decision_base = {
        "subject": subject,
        "resource": resource,
        "action": action,
        "decision_id": decision_id,
        "tenant_id": _effective_tenant_id(subject, resource, target_tenant_id),
    }

    if action_key == "create":
        if not _is_admin(subject):
            return _decision(
                **decision_base,
                effect="deny",
                reason="create 작업은 admin 권한만 가능",
                obligations={"required_role": "admin"},
            )
        # Every other action resolves the owning tenant from the catalog and checks
        # it below. A create cannot: the dataset does not exist yet, so the target
        # tenant arrives in the request. Without this check an admin in one tenant
        # writes into another tenant's catalog namespace - and is then correctly
        # refused on the asset it just planted, which is the tell.
        if target_tenant_id and not can_access_tenant(subject, target_tenant_id):
            return _decision(
                **decision_base,
                effect="deny",
                reason="tenant boundary denied",
                obligations={
                    "tenant_id": target_tenant_id,
                    "actor_tenant_id": resolve_actor_context(subject).tenant_id,
                },
            )
        return _decision(
            **decision_base,
            effect="allow",
            reason="관리자 권한으로 catalog mutation 권한 통과",
            obligations={"required_role": "admin"},
        )

    if action_key in {"search", "search_catalog", "discover"}:
        if _has_reader_role(subject):
            return _decision(
                **decision_base,
                effect="allow",
                reason="카탈로그 발견 정책 통과",
                obligations={"masking": []},
            )
        return _decision(
            **decision_base,
            effect="deny",
            reason="목록 조회는 인증된 사용자만 가능합니다.",
            obligations={"required_role": "data-analyst"},
        )

    dataset = get_dataset(resource)
    if not dataset:
        return _decision(
            **decision_base,
            effect="deny",
            reason="존재하지 않는 데이터셋입니다.",
        )

    actor_context = resolve_actor_context(subject)
    if not can_access_tenant(subject, dataset.tenant_id):
        return _decision(
            **decision_base,
            effect="deny",
            reason="tenant boundary denied",
            obligations={"tenant_id": dataset.tenant_id, "actor_tenant_id": actor_context.tenant_id},
        )

    if dataset.sensitivity == "critical" and not _is_admin(subject):
        return _decision(
            **decision_base,
            effect="deny",
            reason="critical 민감도 자산은 별도 심사 필요",
            obligations={"redact": True, "masking": True},
        )

    if purpose.lower() == "external-export" and not _is_admin(subject):
        return _decision(
            **decision_base,
            effect="deny",
            reason="외부 반출 목적은 데이터 운영자 승인 필요",
            obligations={"required_role": "data-admin"},
        )

    if action_key in {"publish", "patch", "deprecate"} and not _can_mutate(subject, action_key):
        return _decision(
            **decision_base,
            effect="deny",
            reason="catalog mutation 작업은 admin 권한만 가능",
            obligations={"required_role": "admin"},
        )

    if action_key in {"query", "preview", "schema", "search", "list"} and not _has_reader_role(subject):
        return _decision(
            **decision_base,
            effect="deny",
            reason="조회 권한이 없습니다.",
            obligations={"required_role": "data-analyst"},
        )

    row_filter = []
    if action_key in {"query", "preview"} and purpose == "analysis" and dataset.sensitivity == "high":
        row_filter.append("business_unit = current_user_unit")

    obligations = {
        "tenant_id": dataset.tenant_id,
        "masking": [col.name for col in dataset.schema if col.pii],
    }
    if row_filter:
        obligations["row_filter"] = row_filter

    return _decision(
        **decision_base,
        effect="allow",
        reason="거버넌스 정책 조건 충족",
        obligations=obligations,
    )


def is_mutable(subject: str, action: str, resource: str) -> bool:
    decision = evaluate(subject=subject, resource=resource, action=action, purpose="analysis")
    return decision.effect == "allow"
