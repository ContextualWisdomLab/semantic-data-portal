from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class SaleabilityKPI(BaseModel):
    """Buyer-saleability KPI with semantic internal vocabulary and stable wire keys."""

    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    kpi_id: str = Field(alias="id")
    kpi_label: str = Field(alias="label")
    decision_question: str
    kpi_definition: str = Field(alias="definition")
    kpi_target: str = Field(alias="target")
    review_cadence: str = Field(alias="cadence")
    source_endpoints: list[str]
    kpi_owner: str = Field(alias="owner")
    kpi_guardrails: list[str] = Field(default_factory=list, alias="guardrails")
    implementation_status: str = Field(alias="status", pattern="^(implemented|planned|external)$")

    @property
    def id(self) -> str:  # noqa: A003 - legacy Python compatibility attribute
        """Return the historical KPI identifier compatibility attribute."""

        return self.kpi_id

    @id.setter
    def id(self, legacy_kpi_id: str) -> None:  # noqa: A003
        self.kpi_id = legacy_kpi_id

    @property
    def label(self) -> str:
        """Return the historical KPI label compatibility attribute."""

        return self.kpi_label

    @label.setter
    def label(self, legacy_kpi_label: str) -> None:
        self.kpi_label = legacy_kpi_label

    @property
    def definition(self) -> str:
        """Return the historical KPI definition compatibility attribute."""

        return self.kpi_definition

    @definition.setter
    def definition(self, legacy_kpi_definition: str) -> None:
        self.kpi_definition = legacy_kpi_definition

    @property
    def target(self) -> str:
        """Return the historical KPI target compatibility attribute."""

        return self.kpi_target

    @target.setter
    def target(self, legacy_kpi_target: str) -> None:
        self.kpi_target = legacy_kpi_target

    @property
    def cadence(self) -> str:
        """Return the historical KPI cadence compatibility attribute."""

        return self.review_cadence

    @cadence.setter
    def cadence(self, legacy_review_cadence: str) -> None:
        self.review_cadence = legacy_review_cadence

    @property
    def owner(self) -> str:
        """Return the historical KPI owner compatibility attribute."""

        return self.kpi_owner

    @owner.setter
    def owner(self, legacy_kpi_owner: str) -> None:
        self.kpi_owner = legacy_kpi_owner

    @property
    def guardrails(self) -> list[str]:
        """Return the historical KPI guardrails compatibility attribute."""

        return self.kpi_guardrails

    @guardrails.setter
    def guardrails(self, legacy_kpi_guardrails: list[str]) -> None:
        self.kpi_guardrails = legacy_kpi_guardrails

    @property
    def status(self) -> str:
        """Return the historical KPI implementation-status compatibility attribute."""

        return self.implementation_status

    @status.setter
    def status(self, legacy_implementation_status: str) -> None:
        self.implementation_status = legacy_implementation_status


class KPIFramework(BaseModel):
    """Enterprise KPI framework with a semantic internal product name."""

    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    product_name: str = Field(alias="product")
    valuation_target_krw: int
    operating_cadence: str
    primary_kpis: list[SaleabilityKPI]
    guardrail_kpis: list[SaleabilityKPI]

    @property
    def product(self) -> str:
        """Return the historical product compatibility attribute."""

        return self.product_name

    @product.setter
    def product(self, legacy_product_name: str) -> None:
        self.product_name = legacy_product_name


def enterprise_kpi_framework() -> KPIFramework:
    return KPIFramework(
        product_name="Semantic Data Portal",
        valuation_target_krw=2_000_000_000,
        operating_cadence="Review every buyer demo and before every pilot handoff.",
        primary_kpis=[
            SaleabilityKPI(
                kpi_id="discovery_time_reduction",
                kpi_label="Discovery time reduction",
                decision_question="Can a buyer find governed datasets materially faster than their current workflow?",
                kpi_definition="Median time from natural language intent to a qualified dataset shortlist compared with the buyer baseline.",
                kpi_target=">=50 percent reduction",
                review_cadence="buyer demo and pilot weekly review",
                source_endpoints=["/catalog/search", "/llm/search", "/enterprise/demo-plan"],
                kpi_owner="product",
                kpi_guardrails=["No unauthorized dataset existence disclosure.", "Search result explanations must include source evidence."],
                implementation_status="planned",
            ),
            SaleabilityKPI(
                kpi_id="metadata_completeness",
                kpi_label="Metadata completeness",
                decision_question="Are buyer priority datasets complete enough for diligence and analyst use?",
                kpi_definition="Share of priority datasets with owner, steward, schema, lineage, quality, freshness, license, and sensitivity present.",
                kpi_target=">=90 percent display coverage",
                review_cadence="dataset onboarding review",
                source_endpoints=["/catalog/datasets/{dataset_id}/validate", "/catalog/datasets/{dataset_id}/lineage"],
                kpi_owner="data steward",
                kpi_guardrails=["Completeness must not hide failed validation.", "Deprecated datasets stay visible with status."],
                implementation_status="implemented",
            ),
            SaleabilityKPI(
                kpi_id="policy_audit_coverage",
                kpi_label="Policy and audit coverage",
                decision_question="Can every governed data action be explained and audited?",
                kpi_definition="Share of preview, query, and catalog mutation requests with policy decision or audit evidence.",
                kpi_target="100 percent",
                review_cadence="release gate and buyer demo",
                source_endpoints=["/browse/{dataset_id}/preview", "/browse/query", "/audit/events", "/policy/decision"],
                kpi_owner="security",
                kpi_guardrails=["No preview or query path may bypass policy.", "Audit payloads must not contain secrets."],
                implementation_status="implemented",
            ),
            SaleabilityKPI(
                kpi_id="demo_setup_minutes",
                kpi_label="Demo setup time",
                decision_question="Can a buyer evaluator run the core demo quickly enough for sales diligence?",
                kpi_definition="Elapsed time from clean checkout to health check, readiness manifest, demo plan, and one governed query proof.",
                kpi_target="<=15 minutes",
                review_cadence="release candidate",
                source_endpoints=["/health", "/enterprise/readiness", "/enterprise/demo-plan", "/enterprise/connectors/{connector_id}/probe"],
                kpi_owner="solution architect",
                kpi_guardrails=["Demo setup must not require production credentials.", "Failure modes must be explicit."],
                implementation_status="planned",
            ),
        ],
        guardrail_kpis=[
            SaleabilityKPI(
                kpi_id="nl_catalog_search_success",
                kpi_label="Natural language catalog success",
                decision_question="Does natural language intent reliably resolve to grounded catalog actions?",
                kpi_definition="Share of curated buyer questions that resolve to approved ontology terms and existing datasets without hallucinated assets.",
                kpi_target=">=80 percent",
                review_cadence="golden set review",
                source_endpoints=["/ontology/resolve", "/ontology/search", "/llm/search"],
                kpi_owner="ontology engineer",
                kpi_guardrails=["Hallucinated table or column count must be zero in demo scripts."],
                implementation_status="implemented",
            ),
            SaleabilityKPI(
                kpi_id="ontology_mapping_coverage",
                kpi_label="Ontology mapping coverage",
                decision_question="Are enough critical buyer terms mapped for a credible pilot?",
                kpi_definition="Share of buyer critical glossary terms mapped to approved concepts or active steward patch proposals.",
                kpi_target=">=70 percent",
                review_cadence="domain onboarding review",
                source_endpoints=["/ontology/search", "/ontology/resolve", "/ontology/patches"],
                kpi_owner="ontology engineer",
                kpi_guardrails=["Proposed mappings are not treated as approved mappings."],
                implementation_status="implemented",
            ),
            SaleabilityKPI(
                kpi_id="validation_pass_rate",
                kpi_label="Metadata validation pass rate",
                decision_question="Can priority datasets pass the required governance quality bar?",
                kpi_definition="Share of priority datasets passing metadata validation before pilot handoff.",
                kpi_target=">=95 percent",
                review_cadence="pilot handoff",
                source_endpoints=[
                    "/catalog/datasets/{dataset_id}/validate",
                    "/catalog/datasets/{dataset_id}/semantic-validation",
                    "/enterprise/shacl-validation",
                ],
                kpi_owner="data steward",
                kpi_guardrails=["Critical validation failures block publish."],
                implementation_status="implemented",
            ),
            SaleabilityKPI(
                kpi_id="clean_pr_queue",
                kpi_label="Clean PR queue",
                decision_question="Can the buyer trust engineering hygiene and release discipline?",
                kpi_definition="Open pull requests without current-head required workflow completion, unresolved review threads, or merge conflicts.",
                kpi_target="0 blocking PRs",
                review_cadence="release gate",
                source_endpoints=["ContextualWisdomLab central required workflows", "GitHub PR status rollup"],
                kpi_owner="engineering",
                kpi_guardrails=["Review process itself is not a blocker; current-head failed checks are."],
                implementation_status="external",
            ),
        ],
    )
