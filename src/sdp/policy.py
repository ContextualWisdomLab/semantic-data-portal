from __future__ import annotations

from typing import Iterable

from .catalog import get_dataset
from .domain import PolicyDecision


def evaluate(subject: str, resource: str, action: str, purpose: str) -> PolicyDecision:
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

    if purpose.lower() in {"debug", "test", "analysis"} and subject != "admin":
        return PolicyDecision(
            subject=subject,
            resource=resource,
            action=action,
            effect="deny",
            reason="권한이 없습니다.",
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

