from __future__ import annotations

from uuid import uuid4

from .authz import can_access_tenant, has_role, resolve_actor_context
from .catalog import get_dataset
from .domain import PolicyDecision
from .evidence import record_policy_decision


def _decision(**kwargs: object) -> PolicyDecision:
    return record_policy_decision(PolicyDecision(**kwargs))


def _is_admin(subject: str) -> bool:
    return has_role(subject, "admin", "platform-admin")


def _can_mutate(subject: str, action: str) -> bool:
    return _is_admin(subject) and action.lower() in {"create", "publish", "patch", "deprecate"}


def _has_reader_role(subject: str) -> bool:
    return has_role(subject, "data-analyst", "admin", "platform-admin", "security")


def evaluate_file_asset_access(
    actor_context: object,
    resource: str,
    action: str,
    resource_tenant_id: str,
) -> PolicyDecision:
    """Evaluate and record resource-scoped policy for one governed file asset."""

    subject = str(getattr(actor_context, "subject", "anonymous"))
    actor_tenant_id = str(getattr(actor_context, "tenant_id", ""))
    roles = set(getattr(actor_context, "roles", []))
    action_key = action.lower()
    decision_base = {
        "subject": subject,
        "resource": resource,
        "action": action,
        "decision_id": str(uuid4()),
    }
    obligations = {
        "tenant_id": resource_tenant_id,
        "actor_tenant_id": actor_tenant_id,
    }
    if "platform-admin" not in roles and actor_tenant_id != resource_tenant_id:
        return _decision(
            **decision_base,
            effect="deny",
            reason="tenant boundary denied",
            obligations=obligations,
        )
    if action_key == "create_file_asset":
        allowed = bool({"admin", "platform-admin"}.intersection(roles))
        required_role = "admin"
    elif action_key == "read_file_locations":
        allowed = bool({"admin", "platform-admin"}.intersection(roles))
        required_role = "admin"
    else:
        allowed = bool(
            {"data-analyst", "admin", "platform-admin", "security"}.intersection(roles)
        )
        required_role = "data-analyst"
    if not allowed:
        return _decision(
            **decision_base,
            effect="deny",
            reason="file asset policy denied",
            obligations={**obligations, "required_role": required_role},
        )
    return _decision(
        **decision_base,
        effect="allow",
        reason="file asset tenant and role policy satisfied",
        obligations=obligations,
    )


def evaluate_graph_access(
    actor_context: object,
    resource: str,
    action: str,
) -> PolicyDecision:
    """Evaluate and record OIDC-derived access to the generic graph surface."""

    subject = str(getattr(actor_context, "subject", "anonymous"))
    roles = set(getattr(actor_context, "roles", []))
    write = action.lower() == "write_graph"
    allowed = bool(
        ({"admin", "platform-admin"} if write else {"data-analyst", "admin", "platform-admin", "security"})
        .intersection(roles)
    )
    return _decision(
        subject=subject,
        resource=resource,
        action=action,
        decision_id=str(uuid4()),
        effect="allow" if allowed else "deny",
        reason="graph role policy satisfied" if allowed else "graph role policy denied",
        obligations={"required_role": "admin" if write else "data-analyst"},
    )


def evaluate(subject: str, resource: str, action: str, purpose: str) -> PolicyDecision:
    action_key = action.lower()
    decision_id = str(uuid4())
    decision_base = {
        "subject": subject,
        "resource": resource,
        "action": action,
        "decision_id": decision_id,
    }

    if action_key == "create":
        if _is_admin(subject):
            return _decision(
                **decision_base,
                effect="allow",
                reason="관리자 권한으로 catalog mutation 권한 통과",
                obligations={"required_role": "admin"},
            )
        return _decision(
            **decision_base,
            effect="deny",
            reason="create 작업은 admin 권한만 가능",
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
