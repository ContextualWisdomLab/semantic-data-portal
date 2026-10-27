from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, HttpUrl


# POL-003 (P0) names three classification bases for masking: "PII, sensitive,
# confidential tag 기반 masking". Only ``pii`` existed, as a bool, so a column
# classified sensitive or confidential had nowhere to say so and nothing masked
# it - the policy obligation was literally
# ``[col.name for col in dataset.schema if col.pii]``.
MASKING_CLASSIFICATIONS = ("pii", "sensitive", "confidential")

# A classification outside that vocabulary still masks. Masking is a withholding
# control, so the fail-closed direction is to mask what is not understood: an
# unrecognised label is a configuration error, and the alternative - releasing a
# column because its label was misspelled - is the failure that matters. The rule
# reports the basis as ``unrecognized_classification`` so the decision says why
# rather than silently widening.
UNRECOGNIZED_CLASSIFICATION_BASIS = "unrecognized_classification"


class ColumnMetadata(BaseModel):
    name: str
    datatype: str
    nullable_ratio: float = Field(ge=0, le=1)
    distinct_ratio: float = Field(ge=0, le=1)
    quality_issues: list[str] = Field(default_factory=list)
    pii: bool = False
    # Declared classifications for this column. ``pii: true`` and
    # ``classification: ["pii"]`` are the same statement; either one masks, so
    # the two cannot disagree about the outcome.
    classification: list[str] = Field(default_factory=list)


def column_masking_bases(column: "ColumnMetadata") -> list[str]:
    """Why this column must be masked, or ``[]`` when nothing requires it.

    The bases are what POL-003's acceptance criterion needs the decision to
    carry: "policy decision 결과에 masking rule 포함". A bare list of column
    names says *which* columns and not *on what grounds*, so an auditor reading
    a decision could not tell a PII mask from a confidentiality mask - or
    notice that only one of the three declared bases was ever consulted.
    """
    bases: list[str] = []
    if column.pii and "pii" not in column.classification:
        bases.append("pii")
    for label in column.classification:
        normalized = label.strip().lower()
        if not normalized:
            continue
        if normalized in MASKING_CLASSIFICATIONS:
            if normalized not in bases:
                bases.append(normalized)
        elif UNRECOGNIZED_CLASSIFICATION_BASIS not in bases:
            bases.append(UNRECOGNIZED_CLASSIFICATION_BASIS)
    return bases


def masked_column_rules(columns: list["ColumnMetadata"]) -> list[dict[str, Any]]:
    """One masking rule per column that must be masked, in schema order."""
    return [
        {"column": column.name, "bases": bases, "action": "mask"}
        for column in columns
        if (bases := column_masking_bases(column))
    ]


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


# The metadata a dataset must carry to be considered complete. This is the one
# list: ``Dataset.metadata_completeness`` scores it and ``catalog.validate_metadata``
# requires it. They were two lists of different lengths, so the published
# completeness number could read 1.0 for a dataset the validator calls critically
# invalid.
REQUIRED_METADATA_FIELDS = (
    "owner",
    "steward",
    "title",
    "description",
    "domain",
    "sensitivity",
    "update_frequency",
    "source_system",
    "schema",
    "distributions",
)


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
        """Share of the **required** metadata fields this dataset carries.

        This scored seven fields while ``catalog.validate_metadata`` requires
        ten (adding ``domain``, ``schema`` and ``distributions``), so a dataset
        that fails validation critically still published ``1.0``. Measured on a
        dataset registered with ``schema: []`` and ``distributions: []``::

            GET /catalog/datasets/{id}/validate
              -> is_valid: false, critical: true,
                 missing: ["schema", "distributions"]
            the same catalog payload
              -> metadata_completeness: 1.0

        The KPI named after this measure states its own guardrail as
        "Completeness must not hide failed validation." - which is exactly what
        the seven-field score did. One list, in
        ``REQUIRED_METADATA_FIELDS`` below, is what keeps the number and the
        validator from drifting again; ``catalog`` imports it rather than
        keeping its own copy.
        """
        covered = sum(
            1 for field in REQUIRED_METADATA_FIELDS if getattr(self, field, None)
        )
        return covered / len(REQUIRED_METADATA_FIELDS)

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
    # Required, not defaulted. `default_factory=list` with `min_length=1`
    # contradicted itself: pydantic does not validate a default, so omitting the
    # field produced `[]`, passed validation, and then `req.dataset_ids[0]` raised
    # IndexError - a 500 on a body any client can send. Supplying `[]` explicitly
    # was correctly refused with 400, which is the tell.
    dataset_ids: list[str] = Field(min_length=1)
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
    # ``Dataset`` has carried a ``license`` all along and neither request model
    # exposed it, so a supplied value was silently dropped:
    # ``POST /catalog/datasets`` with ``license: "CC-BY-4.0"`` answered 200 and
    # stored ``None``; ``PATCH`` with ``license: "MIT"`` answered 200 and left
    # ``internal``; every seeded dataset reads ``internal``. A data catalog whose
    # licence cannot be set is missing the field a diligence reader checks
    # first - and the ``metadata_completeness`` KPI's own definition names
    # ``license`` among the fields it counts.
    license: str = "internal"
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
    license: Optional[str] = None
    quality_score: Optional[float] = None
    freshness_score: Optional[float] = None
    tags: Optional[list[str]] = None
    terms: Optional[list[str]] = None
    related_datasets: Optional[list[str]] = None
    schema: Optional[list[ColumnMetadata]] = None
    # ``license`` was already absent once and silently dropped a supplied value;
    # ``distributions`` was the same omission one field later, and it is the one
    # field a refusal tells a steward to add. Measured before this: PATCH with a
    # ``postgresql.table`` distribution answered 200, stored nothing, and
    # ``/llm/draft-query`` kept refusing the dataset whose remedy had just been
    # "applied". Every other collection ``DatasetCreateRequest`` accepts is
    # patchable; ``tests/test_patch_accepts_the_fields_create_does.py`` holds the
    # two request models to that parity with a declared exemption list.
    distributions: Optional[list[DatasetDistribution]] = None
    lineage_inputs: Optional[list[str]] = None
    lineage_outputs: Optional[list[str]] = None
    mappings: Optional[list[BusinessMapping]] = None
    profile: Optional[Dict[str, Any]] = None
