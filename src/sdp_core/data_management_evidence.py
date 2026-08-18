"""Framework-neutral contracts for actionable data-management evidence.

The contracts describe CWL-owned ownership, critical-element, quality-rule, and
observation facts. They do not reproduce DAMA-DMBOK or DCAM licensed prose,
challenge questions, official scoring criteria, or evidence lists.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


TruthStatus = Literal["authoritative", "observed", "inferred", "proposed"]
DataClassification = Literal[
    "public",
    "internal",
    "confidential",
    "restricted_pii",
    "restricted_financial",
]
ThresholdOperator = Literal[
    "equal_to",
    "not_equal_to",
    "greater_than",
    "greater_than_or_equal_to",
    "less_than",
    "less_than_or_equal_to",
]
QualityStatus = Literal["passed", "failed", "warning", "unknown"]
_OPAQUE_REFERENCE_RE = re.compile(r"^[A-Za-z0-9._:@-]+$")


def _require_aware_utc(value: datetime, field_name: str) -> datetime:
    """Require an aware timestamp and normalize it to UTC."""

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must include a timezone offset")
    return value.astimezone(timezone.utc)


def _require_https(value: str, field_name: str) -> str:
    """Require an HTTPS evidence reference rather than a local path or URI."""

    if not value.startswith("https://"):
        raise ValueError(f"{field_name} must be an https evidence reference")
    return value


def _require_opaque_reference(value: str, field_name: str) -> str:
    """Reject path-bearing or whitespace-bearing external identities."""

    if _OPAQUE_REFERENCE_RE.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be an opaque identifier")
    return value


class DataOwnerAssignmentDraft(BaseModel):
    """Effective-dated data-owner assignment backed by explicit evidence."""

    owner_subject: str = Field(min_length=1, max_length=256)
    owner_display_name: str = Field(min_length=1, max_length=256)
    valid_from: datetime
    valid_to: datetime | None = None
    evidence_reference: str = Field(min_length=9, max_length=1024)
    truth_status: TruthStatus

    @field_validator("owner_subject")
    @classmethod
    def owner_subject_is_opaque(cls, value: str) -> str:
        """Keep the external identity path-free and bounded."""

        return _require_opaque_reference(value, "owner_subject")

    @field_validator("valid_from", "valid_to")
    @classmethod
    def timestamps_are_aware(cls, value: datetime | None, info) -> datetime | None:
        """Normalize assignment business times to aware UTC."""

        if value is None:
            return value
        return _require_aware_utc(value, info.field_name)

    @field_validator("evidence_reference")
    @classmethod
    def evidence_reference_is_https(cls, value: str) -> str:
        """Require transport-protected owner-decision evidence."""

        return _require_https(value, "evidence_reference")

    @model_validator(mode="after")
    def valid_interval_is_ordered(self) -> "DataOwnerAssignmentDraft":
        """Reject empty or reversed effective intervals."""

        if self.valid_to is not None and self.valid_to <= self.valid_from:
            raise ValueError("valid_to must be later than valid_from")
        return self


class CriticalDataElementDraft(BaseModel):
    """One critical data element defined within a catalog dataset."""

    element_key: str = Field(
        min_length=2,
        max_length=128,
        pattern=r"^[a-z][a-z0-9_]+$",
    )
    display_name: str = Field(min_length=1, max_length=256)
    definition_text: str = Field(min_length=10, max_length=4000)
    data_classification: DataClassification
    evidence_reference: str = Field(min_length=9, max_length=1024)
    truth_status: TruthStatus

    @field_validator("evidence_reference")
    @classmethod
    def evidence_reference_is_https(cls, value: str) -> str:
        """Require an HTTPS glossary, policy, or decision citation."""

        return _require_https(value, "evidence_reference")


class DataQualityRuleDraft(BaseModel):
    """Versioned quality expectation for one critical data element."""

    rule_code: str = Field(
        min_length=2,
        max_length=128,
        pattern=r"^[a-z][a-z0-9_]+$",
    )
    rule_description: str = Field(min_length=10, max_length=4000)
    metric_code: str = Field(
        min_length=2,
        max_length=128,
        pattern=r"^[a-z][a-z0-9_]+$",
    )
    threshold_operator: ThresholdOperator
    threshold_value: Decimal
    unit_code: str = Field(min_length=1, max_length=32, pattern=r"^[A-Za-z0-9._%-]+$")
    evidence_reference: str = Field(min_length=9, max_length=1024)
    truth_status: TruthStatus

    @field_validator("threshold_value")
    @classmethod
    def threshold_is_finite(cls, value: Decimal) -> Decimal:
        """Reject NaN and infinite thresholds from financial or quality logic."""

        if not value.is_finite():
            raise ValueError("threshold_value must be finite")
        return value

    @field_validator("evidence_reference")
    @classmethod
    def evidence_reference_is_https(cls, value: str) -> str:
        """Require an HTTPS control-definition citation."""

        return _require_https(value, "evidence_reference")


class DataQualityObservationDraft(BaseModel):
    """Immutable observed result for one quality rule."""

    source_observation_id: str = Field(min_length=2, max_length=256)
    observed_value: Decimal
    observed_at: datetime
    quality_status: QualityStatus
    evidence_reference: str = Field(min_length=9, max_length=1024)
    truth_status: TruthStatus

    @field_validator("source_observation_id")
    @classmethod
    def observation_identity_is_opaque(cls, value: str) -> str:
        """Keep the producer's replay identity path-free."""

        return _require_opaque_reference(value, "source_observation_id")

    @field_validator("observed_value")
    @classmethod
    def observed_value_is_finite(cls, value: Decimal) -> Decimal:
        """Reject NaN and infinite observed values."""

        if not value.is_finite():
            raise ValueError("observed_value must be finite")
        return value

    @field_validator("observed_at")
    @classmethod
    def observed_at_is_aware(cls, value: datetime) -> datetime:
        """Normalize observation time to aware UTC."""

        return _require_aware_utc(value, "observed_at")

    @field_validator("evidence_reference")
    @classmethod
    def evidence_reference_is_https(cls, value: str) -> str:
        """Require an HTTPS run, receipt, or measurement citation."""

        return _require_https(value, "evidence_reference")


class DataOwnerAssignmentRecord(DataOwnerAssignmentDraft):
    """Persisted owner assignment."""

    data_owner_assignment_id: str
    catalog_object_id: str
    tenant_reference: str
    recorded_at: datetime


class CriticalDataElementRecord(CriticalDataElementDraft):
    """Persisted critical data element."""

    critical_data_element_id: str
    catalog_object_id: str
    tenant_reference: str
    recorded_at: datetime


class DataQualityRuleRecord(DataQualityRuleDraft):
    """Persisted quality rule."""

    data_quality_rule_id: str
    critical_data_element_id: str
    catalog_object_id: str
    tenant_reference: str
    recorded_at: datetime


class DataQualityObservationRecord(DataQualityObservationDraft):
    """Persisted immutable quality observation."""

    data_quality_observation_id: str
    data_quality_rule_id: str
    critical_data_element_id: str
    catalog_object_id: str
    tenant_reference: str
    recorded_at: datetime


class DataManagementMutationEnvelope(BaseModel):
    """Buyer-facing mutation result with policy evidence and next action."""

    status: str
    tenant_reference: str
    catalog_object_id: str
    policy_decision_id: str
    pii_handling: str = "usable_purpose_limited_no_masking"
    customer_next_action: str
    data_owner_assignment: DataOwnerAssignmentRecord | None = None
    critical_data_element: CriticalDataElementRecord | None = None
    data_quality_rule: DataQualityRuleRecord | None = None
    data_quality_observation: DataQualityObservationRecord | None = None
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DataManagementProfile(BaseModel):
    """Explainable evidence-completeness profile for one catalog dataset."""

    status: str = "data_management_profile"
    tenant_reference: str
    catalog_object_id: str
    policy_decision_id: str
    pii_handling: str = "usable_purpose_limited_no_masking"
    evidence_complete: bool
    factors: dict[str, bool]
    counts: dict[str, int]
    customer_next_action: str
    data_owner_assignments: list[DataOwnerAssignmentRecord] = Field(default_factory=list)
    critical_data_elements: list[CriticalDataElementRecord] = Field(default_factory=list)
    data_quality_rules: list[DataQualityRuleRecord] = Field(default_factory=list)
    data_quality_observations: list[DataQualityObservationRecord] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
