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
    # ``status`` is about the **feature**: are the surfaces this KPI names
    # shipped. It is not about whether anyone computes the number.
    status: str = Field(pattern="^(implemented|planned|external)$")
    # ``measured`` is the other half, and it was missing. A KPI published
    # ``implemented`` with a numeric target reads as a measured result, and
    # ``nl_catalog_search_success`` shipped that way with ``>=80 percent``
    # while its identifier occurred exactly once in all of ``src/`` - its own
    # declaration. No golden set, no eval harness, no value on any endpoint.
    #
    # Flipping that KPI to ``planned`` would have been the same defect from the
    # other side: its surfaces are shipped and answer 200, and this repository
    # already wrote down that "a stale 'this is not implemented' misleads the
    # same buyer as a premature 'this is'". So feature status and measurement
    # status are separate fields now.
    measured: bool = False
    # Where this KPI's own figure is published, as ``endpoint#key``. Empty when
    # ``measured`` is false, and checked against the live response - a pointer
    # that does not resolve is worse than none.
    measurement_surface: str = ""
    # Required when the feature is ``implemented``, the target carries a number
    # and nothing computes it. This is the disclosure that was absent.
    measurement_gap: str = ""


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
                # This target was published with ``status: implemented`` while
                # nothing in the code compared anything to 0.90 - the only
                # thresholds in the evidence path were 0.95 on
                # ``metadata_validation_pass_rate`` (a different, stricter
                # measure: the share of datasets with *no* missing field) and
                # 0.7 on ontology coverage. A target nothing compares to is not
                # a gate. ``/enterprise/evidence-pack`` now measures and gates
                # this one, so the number and the target meet.
                target=">=90 percent mean metadata_completeness across datasets",
                cadence="dataset onboarding review",
                source_endpoints=[
                    "/catalog/datasets/{dataset_id}/validate",
                    "/catalog/datasets/{dataset_id}",
                    "/enterprise/evidence-pack",
                ],
                owner="data steward",
                guardrails=["Completeness must not hide failed validation.", "Deprecated datasets stay visible with status."],
                status="implemented",
                measured=True,
                measurement_surface=(
                    "/enterprise/evidence-pack#saleability_gates.metadata_completeness"
                ),
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
                measured=True,
                measurement_surface=(
                    "/enterprise/observability#metrics."
                    "governed_requests_without_evidence_total"
                ),
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
                measured=False,
                measurement_gap=(
                    "이 KPI의 값은 어디에서도 계산되지 않습니다. 선언된 target "
                    ">=80 percent와 비교되는 코드가 없고, curated question set도 "
                    "eval harness도 트리에 없습니다(PRD epic E5-S4, 미구현). "
                    "feature는 동작합니다 — /llm/search는 결정적 alias 조회이고 "
                    "해결되지 않는 질문에는 자산을 지어내지 않습니다. 측정되지 "
                    "않는 것은 recall(실제 구매자 질문이 얼마나 해결되는가)이며 "
                    "hallucination rate가 아닙니다."
                ),
            ),
            SaleabilityKPI(
                id="ontology_mapping_coverage",
                label="Ontology mapping coverage",
                decision_question="Are enough critical buyer terms mapped for a credible pilot?",
                # The "or active steward patch proposals" clause contradicted
                # this KPI's own guardrail below, and the implementation
                # honoured the guardrail. The definition is corrected to the
                # stricter reading rather than the number loosened to match the
                # looser one. The denominator is the glossary, which is what
                # "share of ... terms" means; it used to be "mappings that
                # happen to exist", so the metric rose when mappings were
                # deleted.
                definition="Share of registered glossary concepts with at least one approved business mapping. Mappings naming a concept the ontology does not define are excluded from both numerator and denominator and reported as unregistered_mapping_concept_count.",
                target=">=70 percent",
                cadence="domain onboarding review",
                # The endpoints that actually produce this number, not the ones
                # a reader might associate with the topic. ``/ontology/patches``
                # was listed and the measurement never reads the patch queue -
                # a diligence reader following the published evidence fetched a
                # queue that contributes nothing. The inputs are the glossary
                # (the denominator) and each dataset's mappings (the numerator);
                # the evidence pack is where the computed figure is published.
                source_endpoints=[
                    "/ontology/concepts",
                    "/catalog/datasets/{dataset_id}",
                    "/enterprise/evidence-pack",
                ],
                owner="ontology engineer",
                guardrails=["Proposed mappings are not treated as approved mappings."],
                status="implemented",
                measured=True,
                measurement_surface=(
                    "/enterprise/evidence-pack#saleability_gates.ontology_mapping_coverage"
                ),
            ),
            SaleabilityKPI(
                id="validation_pass_rate",
                label="Metadata validation pass rate",
                decision_question="Can priority datasets pass the required governance quality bar?",
                definition="Share of priority datasets passing metadata validation before pilot handoff.",
                target=">=95 percent",
                cadence="pilot handoff",
                source_endpoints=[
                    "/catalog/datasets/{dataset_id}/validate",
                    "/catalog/datasets/{dataset_id}/semantic-validation",
                    "/enterprise/shacl-validation",
                ],
                owner="data steward",
                guardrails=["Critical validation failures block publish."],
                status="implemented",
                measured=True,
                # The comparison runs and its verdict is published; the raw
                # rate behind it is not, which is a smaller honesty gap
                # recorded in the gap baseline rather than closed here.
                measurement_surface=(
                    "/enterprise/evidence-pack#saleability_gates."
                    "metadata_validation_pass_rate"
                ),
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
