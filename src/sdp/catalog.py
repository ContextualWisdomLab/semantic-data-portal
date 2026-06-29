from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional

from .domain import BusinessMapping, ColumnMetadata, Dataset, DatasetDistribution, MappingStatus


def _seed_datasets() -> List[Dataset]:
    return [
        Dataset(
            id="crm-customer-master",
            title="고객 마스터",
            description="고객의 상태와 핵심 상태 지표를 통합 관리하는 기본 데이터셋",
            owner="data-platform",
            steward="biz-admin",
            domain="고객",
            source_system="postgresql://analytics.dw/customer",
            sensitivity="medium",
            update_frequency="daily",
            quality_score=0.92,
            freshness_score=0.98,
            tags=["고객", "프로필", "이탈"],
            terms=["고객", "활성 고객", "이탈"],
            related_datasets=["crm-event", "sales-order"],
            schema=[
                ColumnMetadata(
                    name="customer_id",
                    datatype="string",
                    nullable_ratio=0.0,
                    distinct_ratio=1.0,
                    pii=False,
                ),
                ColumnMetadata(
                    name="customer_email",
                    datatype="string",
                    nullable_ratio=0.01,
                    distinct_ratio=0.99,
                    pii=True,
                ),
                ColumnMetadata(
                    name="signup_at",
                    datatype="timestamp",
                    nullable_ratio=0.0,
                    distinct_ratio=0.88,
                ),
            ],
            distributions=[
                DatasetDistribution(
                    id="dist-crm-customer",
                    format="postgresql.table",
                    endpoint="https://example.internal/api/table/crm_customer_master",
                )
            ],
            mappings=[
                BusinessMapping(concept="고객", status=MappingStatus.APPROVED),
                BusinessMapping(concept="활성 고객", status=MappingStatus.PROPOSED),
            ],
            profile={"row_count": 1200000, "updated_at": "2026-06-29T00:00:00Z"},
        ),
        Dataset(
            id="crm-event",
            title="행동 이벤트 로그",
            description="고객 행태, 접속 이벤트, 전환 로그를 저장한 시계열 데이터셋",
            owner="data-platform",
            steward="data-engineering",
            domain="고객행동",
            source_system="s3://analytics/events/crm",
            sensitivity="high",
            update_frequency="hourly",
            quality_score=0.88,
            freshness_score=0.95,
            tags=["이벤트", "행동", "로그"],
            terms=["고객 활동", "행동", "이벤트"],
            related_datasets=["crm-customer-master", "marketing-campaign"],
            schema=[
                ColumnMetadata(
                    name="event_id",
                    datatype="string",
                    nullable_ratio=0.0,
                    distinct_ratio=1.0,
                    pii=False,
                ),
                ColumnMetadata(
                    name="customer_id",
                    datatype="string",
                    nullable_ratio=0.0,
                    distinct_ratio=0.98,
                    pii=False,
                ),
                ColumnMetadata(
                    name="event_timestamp",
                    datatype="timestamp",
                    nullable_ratio=0.0,
                    distinct_ratio=0.97,
                ),
                ColumnMetadata(
                    name="device_id",
                    datatype="string",
                    nullable_ratio=0.05,
                    distinct_ratio=0.85,
                    pii=False,
                ),
            ],
            distributions=[
                DatasetDistribution(
                    id="dist-crm-event",
                    format="parquet",
                    endpoint="https://example.internal/api/file/crm_event",
                )
            ],
            mappings=[
                BusinessMapping(concept="활성 고객", status=MappingStatus.APPROVED),
                BusinessMapping(concept="고객 이탈", status=MappingStatus.PROPOSED),
            ],
            profile={"row_count": 54000000, "updated_at": "2026-06-29T00:00:00Z"},
        ),
    ]


_DATA = {dataset.id: dataset for dataset in _seed_datasets()}


@dataclass(frozen=True)
class SearchResult:
    dataset: Dataset
    score: float


def _term_score(dataset: Dataset, tokens: list[str], query: str) -> float:
    score = 0.0
    for token in tokens:
        if token == "":
            continue
        token_re = re.compile(re.escape(token), re.IGNORECASE)
        if token_re.search(dataset.title):
            score += 1.0
        if token_re.search(dataset.description):
            score += 0.8
        for tag in dataset.tags:
            if token_re.search(tag):
                score += 0.5
        for term in dataset.terms:
            if token_re.search(term):
                score += 0.7
    if dataset.sensitivity == "low":
        score += 0.1
    if query in {"활성", "활성 고객", "customer"}:
        for m in dataset.mappings:
            if m.concept == "활성 고객":
                score += 0.4
    return score


def search_catalog(query: str, *, tags: Optional[list[str]] = None, limit: int = 20, include_inactive: bool = False) -> list[SearchResult]:
    tokens = [t.strip() for t in query.split() if t.strip()]
    if not tokens:
        return []

    by_token: list[SearchResult] = []
    for dataset in _DATA.values():
        if tags and not set(tags).intersection(set(dataset.tags)):
            continue
        if not include_inactive and dataset.metadata_completeness < 0.8:
            continue
        score = _term_score(dataset, tokens, query)
        if score > 0:
            by_token.append(SearchResult(dataset=dataset, score=score))

    by_token.sort(key=lambda row: row.score, reverse=True)
    return by_token[:limit]


def get_dataset(dataset_id: str) -> Dataset | None:
    return _DATA.get(dataset_id)


def list_datasets() -> list[Dataset]:
    return list(_DATA.values())


def validate_metadata(dataset: Dataset) -> Dict[str, object]:
    required = ["owner", "steward", "title", "description", "sensitivity", "update_frequency", "source_system"]
    missing = [field for field in required if not getattr(dataset, field, None)]
    return {
        "required_fields": required,
        "missing": missing,
        "is_valid": len(missing) == 0,
        "critical": bool(missing),
    }


def mapping_candidates(dataset: Dataset, concept: str) -> list[str]:
    aliases = {"고객": ["고객", "구매자"], "이탈": ["탈퇴", "이탈"], "활성 고객": ["유효 고객", "액티브 고객"]}
    normalized = concept.strip()
    candidates = set([normalized])
    for base, extra in aliases.items():
        if normalized == base:
            candidates.update(extra)
    return [candidate for candidate in dataset.terms if candidate in candidates]

