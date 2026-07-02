from __future__ import annotations

from pydantic import BaseModel, Field


class SaleabilityKPI(BaseModel):
    id: str
    label: str
    decision_question: str
    definition: str
    target: str
    cadence: str
    source_endpoints: list[str]
    owner: str
    guardrails: list[str] = Field(default_factory=list)
    status: str = Field(pattern="^(implemented|planned|external)$")


class KPIFramework(BaseModel):
    product: str
    valuation_target_krw: int
    operating_cadence: str
    primary_kpis: list[SaleabilityKPI]
    guardrail_kpis: list[SaleabilityKPI]


def enterprise_kpi_framework() -> KPIFramework:
    return KPIFramework(
        product="Semantic Data Portal",
        valuation_target_krw=2_000_000_000,
        operating_cadence="Review every buyer demo and before every pilot handoff.",
        primary_kpis=[
            SaleabilityKPI(
                id="discovery_time_reduction",
                label="Discovery time reduction",
                decision_question="Can a buyer find governed datasets materially faster than their current workflow?",
                definition="Median time from natural language intent to a qualified dataset shortlist compared with the buyer baseline.",
                target=">=50 percent reduction",
                cadence="buyer demo and pilot weekly review",
                source_endpoints=["/catalog/search", "/llm/search", "/enterprise/demo-plan"],
                owner="product",
                guardrails=["No unauthorized dataset existence disclosure.", "Search result explanations must include source evidence."],
                status="planned",
            ),
            SaleabilityKPI(
                id="metadata_completeness",
                label="Metadata completeness",
                decision_question="Are buyer priority datasets complete enough for diligence and analyst use?",
                definition="Share of priority datasets with owner, steward, schema, lineage, quality, freshness, license, and sensitivity present.",
                target=">=90 percent display coverage",
                cadence="dataset onboarding review",
                source_endpoints=["/catalog/datasets/{dataset_id}/validate", "/catalog/datasets/{dataset_id}/lineage"],
                owner="data steward",
                guardrails=["Completeness must not hide failed validation.", "Deprecated datasets stay visible with status."],
                status="implemented",
            ),
            SaleabilityKPI(
                id="policy_audit_coverage",
                label="Policy and audit coverage",
                decision_question="Can every governed data action be explained and audited?",
                definition="Share of preview, query, and catalog mutation requests with policy decision or audit evidence.",
                target="100 percent",
                cadence="release gate and buyer demo",
                source_endpoints=["/browse/{dataset_id}/preview", "/browse/query", "/audit/events", "/policy/decision"],
                owner="security",
                guardrails=["No preview or query path may bypass policy.", "Audit payloads must not contain secrets."],
                status="implemented",
            ),
            SaleabilityKPI(
                id="demo_setup_minutes",
                label="Demo setup time",
                decision_question="Can a buyer evaluator run the core demo quickly enough for sales diligence?",
                definition="Elapsed time from clean checkout to health check, readiness manifest, demo plan, and one governed query proof.",
                target="<=15 minutes",
                cadence="release candidate",
                source_endpoints=["/health", "/enterprise/readiness", "/enterprise/demo-plan", "/enterprise/connectors/{connector_id}/probe"],
                owner="solution architect",
                guardrails=["Demo setup must not require production credentials.", "Failure modes must be explicit."],
                status="planned",
            ),
        ],
        guardrail_kpis=[
            SaleabilityKPI(
                id="nl_catalog_search_success",
                label="Natural language catalog success",
                decision_question="Does natural language intent reliably resolve to grounded catalog actions?",
                definition="Share of curated buyer questions that resolve to approved ontology terms and existing datasets without hallucinated assets.",
                target=">=80 percent",
                cadence="golden set review",
                source_endpoints=["/ontology/resolve", "/ontology/search", "/llm/search"],
                owner="ontology engineer",
                guardrails=["Hallucinated table or column count must be zero in demo scripts."],
                status="implemented",
            ),
            SaleabilityKPI(
                id="ontology_mapping_coverage",
                label="Ontology mapping coverage",
                decision_question="Are enough critical buyer terms mapped for a credible pilot?",
                definition="Share of buyer critical glossary terms mapped to approved concepts or active steward patch proposals.",
                target=">=70 percent",
                cadence="domain onboarding review",
                source_endpoints=["/ontology/search", "/ontology/resolve", "/ontology/patches"],
                owner="ontology engineer",
                guardrails=["Proposed mappings are not treated as approved mappings."],
                status="implemented",
            ),
            SaleabilityKPI(
                id="validation_pass_rate",
                label="Metadata validation pass rate",
                decision_question="Can priority datasets pass the required governance quality bar?",
                definition="Share of priority datasets passing metadata validation before pilot handoff.",
                target=">=95 percent",
                cadence="pilot handoff",
                source_endpoints=["/catalog/datasets/{dataset_id}/validate"],
                owner="data steward",
                guardrails=["Critical validation failures block publish."],
                status="implemented",
            ),
            SaleabilityKPI(
                id="clean_pr_queue",
                label="Clean PR queue",
                decision_question="Can the buyer trust engineering hygiene and release discipline?",
                definition="Open pull requests without current-head required workflow completion, unresolved review threads, or merge conflicts.",
                target="0 blocking PRs",
                cadence="release gate",
                source_endpoints=["ContextualWisdomLab central required workflows", "GitHub PR status rollup"],
                owner="engineering",
                guardrails=["Review process itself is not a blocker; current-head failed checks are."],
                status="external",
            ),
        ],
    )
