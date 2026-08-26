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
                reason="관리자 권한으로 데이터셋 등록 정책 통과",
                obligations={"required_role": "admin"},
            )
        return _decision(
            **decision_base,
            effect="deny",
            reason=(
                "데이터셋 등록(create)은 admin 권한이 있는 계정만 수행할 수 있습니다. "
                "admin 역할로 다시 요청하거나 데이터 운영 담당자에게 등록을 요청하세요."
            ),
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
            reason=(
                "목록 조회는 인증된 사용자만 가능합니다. "
                "data-analyst 역할을 부여받은 계정으로 다시 시도하거나 관리자에게 역할 부여를 요청하세요."
            ),
            obligations={"required_role": "data-analyst"},
        )

    dataset = get_dataset(resource)
    if not dataset:
        return _decision(
            **decision_base,
            effect="deny",
            reason=(
                "존재하지 않는 데이터셋입니다. dataset_id를 확인하고 카탈로그 검색"
                "(GET /catalog/search?q=<용어>)으로 유효한 데이터셋을 찾은 뒤 다시 요청하세요."
            ),
        )

    actor_context = resolve_actor_context(subject)
    if not can_access_tenant(subject, dataset.tenant_id):
        return _decision(
            **decision_base,
            effect="deny",
            reason=(
                "tenant boundary denied. 이 데이터셋은 접근 권한이 없는 테넌트에 속해 있습니다. "
                "올바른 테넌트 참조(X-CWL-Tenant-Reference 헤더)로 요청하거나 "
                "데이터 거버넌스 담당자에게 해당 테넌트 접근을 요청하세요."
            ),
            obligations={"tenant_id": dataset.tenant_id, "actor_tenant_id": actor_context.tenant_id},
        )

    if dataset.sensitivity == "critical" and not _is_admin(subject):
        return _decision(
            **decision_base,
            effect="deny",
            reason=(
                "critical 민감도 자산은 admin 권한이 있는 계정만 조회할 수 있습니다. "
                "admin 또는 platform-admin 역할로 다시 요청하거나 관리자에게 승인을 요청하세요."
            ),
            obligations={"required_role": "admin", "redact": True, "masking": True},
        )

    if purpose.lower() == "external-export" and not _is_admin(subject):
        return _decision(
            **decision_base,
            effect="deny",
            reason=(
                "외부 반출 목적(external-export)은 admin 권한이 필요합니다. "
                "분석 목적(purpose=analysis 등)으로 다시 요청하거나 "
                "admin/platform-admin 역할로 재요청하세요."
            ),
            obligations={"required_role": "admin"},
        )

    if action_key in {"publish", "patch", "deprecate"} and not _can_mutate(subject, action_key):
        return _decision(
            **decision_base,
            effect="deny",
            reason=(
                f"{action_key} 변경 작업은 admin 권한이 있는 계정만 수행할 수 있습니다. "
                "admin 역할로 다시 요청하거나 관리자에게 승인을 요청하세요."
            ),
            obligations={"required_role": "admin"},
        )

    if action_key in {"query", "preview", "schema", "search", "list"} and not _has_reader_role(subject):
        return _decision(
            **decision_base,
            effect="deny",
            reason=(
                "조회 권한이 없습니다. data-analyst, admin, platform-admin, security 중 "
                "하나의 역할이 필요합니다. 해당 역할을 부여받은 계정으로 다시 시도하거나 "
                "관리자에게 역할 부여를 요청하세요."
            ),
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
