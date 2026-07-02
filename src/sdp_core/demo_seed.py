from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from .contracts import (
    BusinessMapping,
    ColumnMetadata,
    Dataset,
    DatasetDistribution,
    MappingStatus,
)


class BuyerDemoDomain(BaseModel):
    id: str
    label: str
    description: str
    default_connectors: list[str]
    analyst_questions: list[str]
    governance_questions: list[str]
    acceptance_questions: list[str]
    dataset_ids: list[str]
    glossary_terms: list[str]


class BuyerDemoDatasetSummary(BaseModel):
    id: str
    title: str
    domain: str
    source_type: str
    source_system: str
    sensitivity: str
    steward: str
    acceptance_role: str


def _approved_mapping(concept: str, *, steward: str) -> BusinessMapping:
    return BusinessMapping(
        concept=concept,
        status=MappingStatus.APPROVED,
        source=f"steward:{steward}",
        steward=steward,
        approved_at=datetime.now(timezone.utc),
    )


def _proposed_mapping(concept: str) -> BusinessMapping:
    return BusinessMapping(concept=concept, status=MappingStatus.PROPOSED, source="llm:suggestion")


def _customer_intelligence_domain() -> BuyerDemoDomain:
    return BuyerDemoDomain(
        id="customer_intelligence",
        label="customer intelligence",
        description="고객 마스터, 행동 이벤트, 세일즈 전환 데이터를 연결해 고객 탐색과 이탈 분석을 시연하는 buyer demo domain.",
        default_connectors=["sql_connector", "rdf_connector"],
        analyst_questions=[
            "최근 90일 활성 고객과 이탈 위험 고객을 찾고 근거 데이터셋을 추천한다.",
            "고객 마스터와 행동 이벤트를 조인할 때 사용할 business key와 품질 리스크를 확인한다.",
        ],
        governance_questions=[
            "PII 컬럼이 preview/query에서 마스킹되고 policy decision id가 남는지 확인한다.",
            "핵심 glossary term이 승인된 ontology concept 또는 steward patch로 추적되는지 확인한다.",
        ],
        acceptance_questions=[
            "자연어 질문이 catalog search, ontology resolve, governed query path로 이어진다.",
            "모든 preview/query 증빙이 audit event와 policy decision에 연결된다.",
        ],
        dataset_ids=["crm-customer-master", "crm-event", "sales-order"],
        glossary_terms=["고객", "활성 고객", "이탈", "고객 활동", "전환"],
    )


def buyer_demo_domains() -> list[BuyerDemoDomain]:
    return [_customer_intelligence_domain()]


def get_buyer_demo_domain(priority_domain: str) -> BuyerDemoDomain | None:
    normalized = priority_domain.strip().lower().replace("-", "_").replace(" ", "_")
    for domain in buyer_demo_domains():
        labels = {domain.id, domain.label.lower(), domain.label.lower().replace(" ", "_")}
        if normalized in labels or priority_domain.strip() in domain.glossary_terms:
            return domain
    return None


def _customer_intelligence_datasets() -> list[Dataset]:
    approved_at = datetime.now(timezone.utc)
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
                    pii=False,
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
                BusinessMapping(
                    concept="고객",
                    status=MappingStatus.APPROVED,
                    source="steward:biz-admin",
                    steward="biz-admin",
                    approved_at=approved_at,
                ),
                _proposed_mapping("활성 고객"),
            ],
            profile={"row_count": 1200000, "updated_at": "2026-06-29T00:00:00Z"},
            lineage_inputs=["crm-event"],
            lineage_outputs=["churn-report"],
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
                    pii=False,
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
                _approved_mapping("활성 고객", steward="data-engineering"),
                _proposed_mapping("고객 이탈"),
            ],
            profile={"row_count": 54000000, "updated_at": "2026-06-29T00:00:00Z"},
            lineage_inputs=["app-event-raw", "auth-service"],
            lineage_outputs=["crm-customer-master"],
        ),
        Dataset(
            id="sales-order",
            title="주문 전환 내역",
            description="고객별 주문, 매출, 전환 상태를 분석하는 세일즈 데이터셋",
            owner="revenue-ops",
            steward="sales-ops",
            domain="매출",
            source_system="postgresql://analytics.dw/sales",
            sensitivity="medium",
            update_frequency="daily",
            quality_score=0.9,
            freshness_score=0.96,
            tags=["주문", "매출", "전환"],
            terms=["전환", "고객", "매출"],
            related_datasets=["crm-customer-master"],
            schema=[
                ColumnMetadata(
                    name="order_id",
                    datatype="string",
                    nullable_ratio=0.0,
                    distinct_ratio=1.0,
                    pii=False,
                ),
                ColumnMetadata(
                    name="customer_id",
                    datatype="string",
                    nullable_ratio=0.0,
                    distinct_ratio=0.91,
                    pii=False,
                ),
                ColumnMetadata(
                    name="order_amount",
                    datatype="decimal",
                    nullable_ratio=0.0,
                    distinct_ratio=0.72,
                    pii=False,
                ),
            ],
            distributions=[
                DatasetDistribution(
                    id="dist-sales-order",
                    format="postgresql.table",
                    endpoint="https://example.internal/api/table/sales_order",
                )
            ],
            mappings=[
                _approved_mapping("전환", steward="sales-ops"),
                _proposed_mapping("매출"),
            ],
            profile={"row_count": 8700000, "updated_at": "2026-06-29T00:00:00Z"},
            lineage_inputs=["commerce-order"],
            lineage_outputs=["revenue-dashboard"],
        ),
    ]


def buyer_demo_datasets(domain_id: str = "customer_intelligence") -> list[Dataset]:
    if domain_id != "customer_intelligence":
        raise ValueError(f"unsupported buyer demo domain: {domain_id}")
    return _customer_intelligence_datasets()


def buyer_demo_dataset_summaries(domain_id: str = "customer_intelligence") -> list[BuyerDemoDatasetSummary]:
    summaries = []
    for dataset in buyer_demo_datasets(domain_id):
        source_type = "sql" if dataset.source_system.startswith("postgresql://") else "file_lake"
        summaries.append(
            BuyerDemoDatasetSummary(
                id=dataset.id,
                title=dataset.title,
                domain=dataset.domain,
                source_type=source_type,
                source_system=dataset.source_system,
                sensitivity=dataset.sensitivity,
                steward=dataset.steward,
                acceptance_role="priority_dataset",
            )
        )
    return summaries


def buyer_demo_context_for_dataset(dataset_id: str) -> dict[str, Any] | None:
    for domain in buyer_demo_domains():
        if dataset_id not in domain.dataset_ids:
            continue
        return {
            "domain_id": domain.id,
            "domain_label": domain.label,
            "analyst_questions": domain.analyst_questions,
            "governance_questions": domain.governance_questions,
            "acceptance_questions": domain.acceptance_questions,
        }
    return None
