from __future__ import annotations

from .catalog import get_dataset
from .domain import PolicyDecision


def _is_admin(subject: str) -> bool:
    return subject in {"admin", "security", "data-admin"}


def _can_mutate(subject: str, action: str) -> bool:
    return _is_admin(subject) and action.lower() in {"create", "publish", "patch", "deprecate"}


def evaluate(subject: str, resource: str, action: str, purpose: str) -> PolicyDecision:
    action_key = action.lower()

    if action_key == "create":
        if _is_admin(subject):
            return PolicyDecision(
                subject=subject,
                resource=resource,
                action=action,
                effect="allow",
                reason="관리자 권한으로 catalog mutation 권한 통과",
                obligations={"required_role": "admin"},
            )
        return PolicyDecision(
            subject=subject,
            resource=resource,
            action=action,
            effect="deny",
            reason="create 작업은 admin 권한만 가능",
            obligations={"required_role": "admin"},
        )

    dataset = get_dataset(resource)
    if not dataset:
        return PolicyDecision(
            subject=subject,
            resource=resource,
            action=action,
            effect="deny",
            reason="존재하지 않는 데이터셋입니다.",
        )

    if dataset.sensitivity == "critical":
        return PolicyDecision(
            subject=subject,
            resource=resource,
            action=action,
            effect="deny",
            reason="critical 민감도 자산은 별도 심사 필요",
            obligations={"redact": True, "masking": True},
        )

    if purpose.lower() == "external-export" and subject not in {"admin", "security", "data-admin"}:
        return PolicyDecision(
            subject=subject,
            resource=resource,
            action=action,
            effect="deny",
            reason="외부 반출 목적은 데이터 운영자 승인 필요",
            obligations={"required_role": "data-admin"},
        )

    if action_key in {"publish", "patch", "deprecate"} and not _can_mutate(subject, action_key):
        return PolicyDecision(
            subject=subject,
            resource=resource,
            action=action,
            effect="deny",
            reason="catalog mutation 작업은 admin 권한만 가능",
            obligations={"required_role": "admin"},
        )

    if action_key in {"query", "preview", "schema", "search"} and subject not in {
        "admin",
        "analyst",
        "data-analyst",
        "data-admin",
    }:
        return PolicyDecision(
            subject=subject,
            resource=resource,
            action=action,
            effect="deny",
            reason="조회 권한이 없습니다.",
            obligations={"required_role": "data-analyst"},
        )

    return PolicyDecision(
        subject=subject,
        resource=resource,
        action=action,
        effect="allow",
        reason="거버넌스 정책 조건 충족",
        obligations={"masking": [col.name for col in dataset.schema if col.pii]},
    )


def is_mutable(subject: str, action: str, resource: str) -> bool:
    decision = evaluate(subject=subject, resource=resource, action=action, purpose="analysis")
    return decision.effect == "allow"
