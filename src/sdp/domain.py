from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

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


class Dataset(BaseModel):
    id: str
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
    version: str = "1.0.0"
    schema_version: str = "1.0.0"
    created_at: datetime = Field(default_factory=datetime.utcnow)
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


class PolicyDecision(BaseModel):
    subject: str
    resource: str
    action: str
    effect: str
    obligations: Dict[str, Any] = Field(default_factory=dict)
    reason: str = ""


class QueryDraftRequest(BaseModel):
    question: str
    user: str
    purpose: str
    dataset_id: str
    group_by: Optional[str] = None
    date_window_days: int = 90

