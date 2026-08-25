"""Actionable data-management evidence services above the catalog plane."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sdp_core.catalog_plane import CatalogObjectRecord, PlaneActor
from sdp_core.data_management_evidence import (
    CriticalDataElementDraft,
    CriticalDataElementRecord,
    DataManagementMutationEnvelope,
    DataManagementProfile,
    DataOwnerAssignmentDraft,
    DataOwnerAssignmentRecord,
    DataQualityObservationDraft,
    DataQualityObservationRecord,
    DataQualityRuleDraft,
    DataQualityRuleRecord,
)

from .catalog_plane_store import get_catalog_plane_store
from .data_management_store import get_data_management_store
from .policy import evaluate


def _now() -> datetime:
    """Return an aware UTC timestamp."""

    return datetime.now(timezone.utc)


def _record_id() -> str:
    """Allocate an opaque record identifier."""

    return str(uuid4())


def _govern(actor: PlaneActor, *, mutate: bool) -> str:
    """Authorize the evidence-plane operation and record policy evidence."""

    if mutate and not actor.can_mutate():
        raise PermissionError("data-management writes require an admin Keyverse role")
    if not mutate and not actor.can_read():
        raise PermissionError("data-management reads require a Keyverse reader role")
    decision = evaluate(
        subject=actor.subject,
        resource="plane" if mutate else "catalog",
        action="create" if mutate else "search",
        purpose=actor.access_purpose,
    )
    if decision.effect != "allow":
        raise PermissionError(decision.reason)
    return decision.decision_id


def _catalog_object(actor: PlaneActor, catalog_object_id: str) -> CatalogObjectRecord:
    """Load one tenant-owned catalog object or fail without leaking existence."""

    record = get_catalog_plane_store().get_catalog_object(
        tenant_reference=actor.tenant_reference,
        catalog_object_id=catalog_object_id,
    )
    if record is None:
        raise KeyError("catalog object not found in this tenant")
    return record


def _catalog_dataset(actor: PlaneActor, catalog_object_id: str) -> CatalogObjectRecord:
    """Require a tenant-owned catalog dataset for CDE evidence."""

    record = _catalog_object(actor, catalog_object_id)
    if record.object_kind != "catalog_dataset":
        raise ValueError("critical data elements require a catalog_dataset parent")
    return record


def assign_data_owner(
    actor: PlaneActor,
    catalog_object_id: str,
    draft: DataOwnerAssignmentDraft,
) -> DataManagementMutationEnvelope:
    """Attach an effective-dated owner decision to one catalog object."""

    decision_id = _govern(actor, mutate=True)
    _catalog_object(actor, catalog_object_id)
    record = DataOwnerAssignmentRecord(
        data_owner_assignment_id=_record_id(),
        catalog_object_id=catalog_object_id,
        tenant_reference=actor.tenant_reference,
        recorded_at=_now(),
        **draft.model_dump(),
    )
    get_data_management_store().insert_owner_assignment(record)
    return DataManagementMutationEnvelope(
        status="data_owner_assigned",
        tenant_reference=actor.tenant_reference,
        catalog_object_id=catalog_object_id,
        policy_decision_id=decision_id,
        customer_next_action=(
            f"다음으로 POST /plane/catalog-objects/{catalog_object_id}/critical-data-elements "
            "에서 업무 의사결정에 중요한 Critical Data Element를 등록하세요."
        ),
        data_owner_assignment=record,
    )


def register_critical_data_element(
    actor: PlaneActor,
    catalog_object_id: str,
    draft: CriticalDataElementDraft,
) -> DataManagementMutationEnvelope:
    """Register one evidence-backed CDE under a catalog dataset."""

    decision_id = _govern(actor, mutate=True)
    _catalog_dataset(actor, catalog_object_id)
    record = CriticalDataElementRecord(
        critical_data_element_id=_record_id(),
        catalog_object_id=catalog_object_id,
        tenant_reference=actor.tenant_reference,
        recorded_at=_now(),
        **draft.model_dump(),
    )
    get_data_management_store().insert_critical_data_element(record)
    return DataManagementMutationEnvelope(
        status="critical_data_element_registered",
        tenant_reference=actor.tenant_reference,
        catalog_object_id=catalog_object_id,
        policy_decision_id=decision_id,
        customer_next_action=(
            f"다음으로 POST /plane/critical-data-elements/{record.critical_data_element_id}/"
            "quality-rules 에 측정 가능한 Data Quality rule과 기준값을 등록하세요."
        ),
        critical_data_element=record,
    )


def define_data_quality_rule(
    actor: PlaneActor,
    critical_data_element_id: str,
    draft: DataQualityRuleDraft,
) -> DataManagementMutationEnvelope:
    """Define one evidence-backed rule for a tenant-owned CDE."""

    decision_id = _govern(actor, mutate=True)
    store = get_data_management_store()
    element = store.get_critical_data_element(
        tenant_reference=actor.tenant_reference,
        critical_data_element_id=critical_data_element_id,
    )
    if element is None:
        raise KeyError("critical data element not found in this tenant")
    record = DataQualityRuleRecord(
        data_quality_rule_id=_record_id(),
        critical_data_element_id=critical_data_element_id,
        catalog_object_id=element.catalog_object_id,
        tenant_reference=actor.tenant_reference,
        recorded_at=_now(),
        **draft.model_dump(),
    )
    store.insert_data_quality_rule(record)
    return DataManagementMutationEnvelope(
        status="data_quality_rule_defined",
        tenant_reference=actor.tenant_reference,
        catalog_object_id=element.catalog_object_id,
        policy_decision_id=decision_id,
        customer_next_action=(
            f"다음으로 POST /plane/quality-rules/{record.data_quality_rule_id}/observations "
            "에서 실제 control run 또는 measurement evidence를 기록하세요."
        ),
        data_quality_rule=record,
    )


def record_data_quality_observation(
    actor: PlaneActor,
    data_quality_rule_id: str,
    draft: DataQualityObservationDraft,
) -> DataManagementMutationEnvelope:
    """Append one immutable observation for a tenant-owned quality rule."""

    decision_id = _govern(actor, mutate=True)
    store = get_data_management_store()
    rule = store.get_data_quality_rule(
        tenant_reference=actor.tenant_reference,
        data_quality_rule_id=data_quality_rule_id,
    )
    if rule is None:
        raise KeyError("data-quality rule not found in this tenant")
    record = DataQualityObservationRecord(
        data_quality_observation_id=_record_id(),
        data_quality_rule_id=data_quality_rule_id,
        critical_data_element_id=rule.critical_data_element_id,
        catalog_object_id=rule.catalog_object_id,
        tenant_reference=actor.tenant_reference,
        recorded_at=_now(),
        **draft.model_dump(),
    )
    store.insert_data_quality_observation(record)
    return DataManagementMutationEnvelope(
        status="data_quality_observation_recorded",
        tenant_reference=actor.tenant_reference,
        catalog_object_id=rule.catalog_object_id,
        policy_decision_id=decision_id,
        customer_next_action=(
            f"GET /plane/catalog-objects/{rule.catalog_object_id}/data-management-profile "
            "에서 owner, CDE, rule, observation evidence가 완결되었는지 확인하세요."
        ),
        data_quality_observation=record,
    )


def _profile_next_action(
    catalog_object_id: str,
    *,
    owner_present: bool,
    element_present: bool,
    rule_present: bool,
    observation_present: bool,
    elements: list[CriticalDataElementRecord],
    rules: list[DataQualityRuleRecord],
) -> str:
    """Return the first precise buyer action needed to complete the profile."""

    if not owner_present:
        return (
            f"POST /plane/catalog-objects/{catalog_object_id}/data-owner-assignments 로 "
            "책임 있는 Data Owner와 승인 evidence를 먼저 지정하세요."
        )
    if not element_present:
        return (
            f"POST /plane/catalog-objects/{catalog_object_id}/critical-data-elements 로 "
            "업무 의사결정에 중요한 Critical Data Element를 등록하세요."
        )
    if not rule_present:
        return (
            f"POST /plane/critical-data-elements/{elements[0].critical_data_element_id}/"
            "quality-rules 로 첫 Data Quality rule을 정의하세요."
        )
    if not observation_present:
        return (
            f"POST /plane/quality-rules/{rules[0].data_quality_rule_id}/observations 로 "
            "실제 measurement 또는 control-run evidence를 기록하세요."
        )
    return (
        "Evidence profile이 완결되었습니다. 최신 observation의 provenance와 status를 "
        "검토하고, 새로운 control run이 발생하면 append-only evidence를 추가하세요."
    )


def build_data_management_profile(
    actor: PlaneActor,
    catalog_object_id: str,
) -> DataManagementProfile:
    """Build an explainable evidence-completeness profile for one dataset."""

    decision_id = _govern(actor, mutate=False)
    _catalog_object(actor, catalog_object_id)
    owners, elements, rules, observations = get_data_management_store().profile_rows(
        tenant_reference=actor.tenant_reference,
        catalog_object_id=catalog_object_id,
    )
    current_time = _now()
    # Factor asymmetry is contractual, not accidental:
    # - data_owner_present requires an *authoritative* assignment whose
    #   effective-time window covers `current_time`, because authority lapses
    #   when the window closes.
    # - CDE/rule presence requires authoritative truth; these are definitions,
    #   not measurements, so "observed" does not make a definition exist.
    # - observation presence accepts authoritative or observed truth because an
    #   observation row IS a measurement record — its native truth status is
    #   "observed" by construction.
    owner_present = any(
        row.truth_status == "authoritative"
        and row.valid_from <= current_time
        and (row.valid_to is None or current_time < row.valid_to)
        for row in owners
    )
    element_present = any(row.truth_status == "authoritative" for row in elements)
    rule_present = any(row.truth_status == "authoritative" for row in rules)
    observation_present = any(
        row.truth_status in {"authoritative", "observed"} for row in observations
    )
    factors = {
        "data_owner_present": owner_present,
        "critical_data_element_present": element_present,
        "quality_rule_present": rule_present,
        "quality_observation_present": observation_present,
    }
    counts = {
        "data_owner_assignments": len(owners),
        "critical_data_elements": len(elements),
        "data_quality_rules": len(rules),
        "data_quality_observations": len(observations),
    }
    return DataManagementProfile(
        tenant_reference=actor.tenant_reference,
        catalog_object_id=catalog_object_id,
        policy_decision_id=decision_id,
        evidence_complete=all(factors.values()),
        factors=factors,
        counts=counts,
        customer_next_action=_profile_next_action(
            catalog_object_id,
            owner_present=owner_present,
            element_present=element_present,
            rule_present=rule_present,
            observation_present=observation_present,
            elements=elements,
            rules=rules,
        ),
        data_owner_assignments=owners,
        critical_data_elements=elements,
        data_quality_rules=rules,
        data_quality_observations=observations,
    )
