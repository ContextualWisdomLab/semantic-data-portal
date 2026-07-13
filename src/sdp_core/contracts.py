from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, HttpUrl


class ColumnMetadata(BaseModel):
    name: str
    datatype: str
    nullable_ratio: float = Field(ge=0, le=1)
    distinct_ratio: float = Field(ge=0, le=1)
    quality_issues: list[str] = Field(default_factory=list)
    pii: bool = False


class DatasetDistribution(BaseModel):
    id: str
    format: str
    endpoint: HttpUrl


class MappingStatus:
    APPROVED = "approved"
    PROPOSED = "proposed"
    DEPRECATED = "deprecated"


class BusinessMapping(BaseModel):
    concept: str
    status: str = MappingStatus.PROPOSED
    source: str | None = None
    steward: str | None = None
    approved_at: datetime | None = None


class DatasetProfile(BaseModel):
    row_count: int | None = None
    freshness_ts: str | None = None
    minmax: Dict[str, Dict[str, float | int | str]] = Field(default_factory=dict)
    quality_issues: list[str] = Field(default_factory=list)


class Dataset(BaseModel):
    id: str
    tenant_id: str = "demo"
    title: str
    description: str
    owner: str
    steward: str
    domain: str
    source_system: str
    sensitivity: str
    update_frequency: str
    quality_score: float = Field(ge=0, le=1)
    freshness_score: float = Field(ge=0, le=1)
    tags: list[str] = Field(default_factory=list)
    terms: list[str] = Field(default_factory=list)
    license: str = "internal"
    related_datasets: list[str] = Field(default_factory=list)
    schema: list[ColumnMetadata] = Field(default_factory=list)
    distributions: list[DatasetDistribution] = Field(default_factory=list)
    mappings: list[BusinessMapping] = Field(default_factory=list)
    lineage_inputs: list[str] = Field(default_factory=list)
    lineage_outputs: list[str] = Field(default_factory=list)
    completeness_score: float = 0.0
    recommended_score: float = 0.0
    version: str = "1.0.0"
    schema_version: str = "1.0.0"
    status: str = "published"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    profile: Dict[str, Any] = Field(default_factory=dict)

    @property
    def metadata_completeness(self) -> float:
        required_fields = [
            self.owner,
            self.steward,
            self.title,
            self.description,
            self.sensitivity,
            self.update_frequency,
            self.source_system,
        ]
        covered = sum(1 for value in required_fields if value)
        return covered / len(required_fields)

    @property
    def metadata_recommendation_score(self) -> float:
        recommended_fields = [
            self.owner,
            self.steward,
            self.title,
            self.description,
            self.sensitivity,
            self.update_frequency,
            self.source_system,
            self.domain,
            self.license,
            self.tags,
            self.terms,
            bool(self.schema),
            bool(self.distributions),
            bool(self.lineage_inputs),
            bool(self.profile),
            self.quality_score is not None,
            self.freshness_score is not None,
        ]
        covered = sum(1 for value in recommended_fields if bool(value))
        return covered / len(recommended_fields)

    def recompute_scores(self) -> None:
        required_total = 11
        scored = 0
        if self.owner:
            scored += 1
        if self.steward:
            scored += 1
        if self.title:
            scored += 1
        if self.description:
            scored += 1
        if self.sensitivity:
            scored += 1
        if self.source_system:
            scored += 1
        if self.update_frequency:
            scored += 1
        if self.domain:
            scored += 1
        if self.tags:
            scored += 1
        if self.schema:
            scored += 1
        if self.distributions:
            scored += 1
        self.completeness_score = round(scored / required_total, 3)
        self.recommended_score = round(self.metadata_recommendation_score, 3)


class PolicyDecision(BaseModel):
    subject: str
    resource: str
    action: str
    effect: str
    decision_id: str = Field(default_factory=lambda: str(uuid4()))
    obligations: Dict[str, Any] = Field(default_factory=dict)
    reason: str = ""


class ActorContext(BaseModel):
    subject: str
    tenant_id: str
    roles: list[str] = Field(default_factory=list)


class OntologyPatch(BaseModel):
    id: str
    concept: str
    requestor: str = "anonymous"
    suggestion: str
    confidence: float = Field(default=0.0, ge=0, le=1)
    status: str = "proposed"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    review_comment: str | None = None


class QueryDraftRequest(BaseModel):
    question: str
    user: str
    purpose: str
    dataset_id: str
    group_by: Optional[str] = None
    date_window_days: int = 90
    columns: Optional[list[str]] = None
    row_limit: int = Field(default=1000, ge=1, le=5000)
    timeout_ms: int = Field(default=30000, ge=500, le=120000)


class QueryExecutionRequest(BaseModel):
    language: str = Field(default="SQL", min_length=1)
    user: str = Field(default="anonymous")
    purpose: str = Field(default="analysis")
    dataset_ids: list[str] = Field(default_factory=list, min_length=1)
    query: str = Field(min_length=1)
    dry_run: bool = False


class QueryExecutionResponse(BaseModel):
    request_id: str
    dataset_id: str
    query_id: str
    policy_decision_id: str
    status: str
    row_count: int
    columns: list[str]
    rows: list[dict[str, str | int | float | bool | None]]
    execution: dict[str, Any]
    warnings: list[str] = Field(default_factory=list)


class AuditEvent(BaseModel):
    id: str
    actor: str
    action: str
    resource: str
    result: str
    decision_id: str | None = None
    reason: str = ""
    details: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DatasetCreateRequest(BaseModel):
    id: Optional[str] = None
    tenant_id: str = "demo"
    title: str
    description: str
    owner: str
    steward: str
    domain: str
    source_system: str
    sensitivity: str
    update_frequency: str
    quality_score: float = Field(ge=0, le=1)
    freshness_score: float = Field(ge=0, le=1)
    tags: list[str] = Field(default_factory=list)
    terms: list[str] = Field(default_factory=list)
    related_datasets: list[str] = Field(default_factory=list)
    schema: list[ColumnMetadata] = Field(default_factory=list)
    distributions: list[DatasetDistribution] = Field(default_factory=list)
    mappings: list[BusinessMapping] = Field(default_factory=list)
    profile: Dict[str, Any] = Field(default_factory=dict)


class DatasetPatchRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    steward: Optional[str] = None
    domain: Optional[str] = None
    source_system: Optional[str] = None
    sensitivity: Optional[str] = None
    update_frequency: Optional[str] = None
    quality_score: Optional[float] = None
    freshness_score: Optional[float] = None
    tags: Optional[list[str]] = None
    terms: Optional[list[str]] = None
    related_datasets: Optional[list[str]] = None
    lineage_inputs: Optional[list[str]] = None
    lineage_outputs: Optional[list[str]] = None
    mappings: Optional[list[BusinessMapping]] = None
    profile: Optional[Dict[str, Any]] = None
