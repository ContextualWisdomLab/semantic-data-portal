from __future__ import annotations

from pydantic import BaseModel, Field

from .contracts import REQUIRED_METADATA_FIELDS


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
    #
    # *Resolving is not the property.* The first three pointers written here
    # all resolved, to the string ``'pass'``: they named the
    # ``saleability_gates`` verdict that sits next to each number instead of
    # the number. A verdict is the product's own opinion of the measurement,
    # so publishing it in the measurement's place leaves the reader unable to
    # compare anything to the target themselves. The pointer must name a
    # figure, and ``tests/test_kpi_measurement_disclosure.py`` now checks that
    # it resolves to a number and does not name the gate block.
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


# ``metadata_completeness``'s definition named eight fields while the number
# counts ten, and only four of them are the same four. Measured on the
# published definition against ``REQUIRED_METADATA_FIELDS``::
#
#     named by the definition : owner steward schema lineage quality freshness
#                               license sensitivity
#     counted by the number   : owner steward title description domain
#                               sensitivity update_frequency source_system
#                               schema distributions
#     named AND counted       : owner steward schema sensitivity
#     named but NOT counted   : lineage quality freshness license
#     counted but NOT named   : title description domain update_frequency
#                               source_system distributions
#
# A diligence reader who computes the definition's own ratio gets a different
# number from the one gated at 0.90, in both directions. The counted clause is
# built from ``REQUIRED_METADATA_FIELDS`` below rather than written out, so the
# sentence cannot drift from the tally again - the same remedy the tally itself
# needed when three hand-written copies of it disagreed.
#
# The four it named and did not count do not all land in the same place, and
# saying they did would have been the next unverified claim. Measured per field
# on a dataset that differs only in that field::
#
#     license          -> completeness 1.0->1.0   recommended 0.7059->0.7647
#     lineage_inputs   -> completeness 1.0->1.0   recommended 0.7647->0.8235
#     quality_score    -> completeness 1.0->1.0   recommended 0.7647->0.7647
#     freshness_score  -> completeness 1.0->1.0   recommended 0.7647->0.7647
#
# So two of them are scored somewhere and two are scored nowhere.

# Absent from ``REQUIRED_METADATA_FIELDS`` and read by
# ``Dataset.metadata_recommendation_score``, which is published per dataset as
# ``recommended_score``.
RECOMMENDATION_SCORED_FIELDS = ("license", "lineage_inputs")

# Absent from ``REQUIRED_METADATA_FIELDS`` and read by neither score. Their two
# entries in ``metadata_recommendation_score`` are ``quality_score is not None``
# and ``freshness_score is not None``, and both are **non-optional floats** on
# ``Dataset`` - constructing one without either is refused - so the two tests
# are tautologies. A dataset reporting ``quality_score: 0.0`` scores the same
# recommendation point as one reporting ``1.0``. That is a second defect, in the
# measure rather than in this sentence, and whether a measured ``0.0`` counts as
# present is a product decision rather than a wording fix; it is filed
# separately. This sentence only stops the definition claiming these two are
# scored.
UNSCORED_DISPLAY_FIELDS = ("quality_score", "freshness_score")


def metadata_completeness_definition() -> str:
    """The definition sentence, with its counted clause derived from the tally.

    Public because the guard in
    ``tests/test_the_definition_names_what_the_number_counts.py`` pins each of
    its three clauses to a measurement rather than to a copy of this string.
    ``tests/test_catalog_field_forwarding.py`` owns a different half - that a
    field this sentence names is settable through the API at all.
    """
    counted = ", ".join(REQUIRED_METADATA_FIELDS)
    return (
        f"Share of priority datasets carrying all {len(REQUIRED_METADATA_FIELDS)} "
        f"required fields: {counted}. Not counted here: "
        f"{' and '.join(RECOMMENDATION_SCORED_FIELDS)}, which recommended_score "
        f"scores instead; {' and '.join(UNSCORED_DISPLAY_FIELDS)}, whose values "
        "neither score reads."
    )


# ``policy_audit_coverage``'s definition said "Share of preview, query, and
# catalog mutation requests **with** policy decision or audit evidence", target
# "100 percent", ``measured=True``, and pointed at
# ``governed_requests_without_evidence_total``. Measured, the sentence and the
# figure diverged on three axes at once::
#
#     the sentence says   the figure is
#     ------------------  ----------------------------------------------
#     a share             an absolute count
#     requests WITH       the complement - requests WITHOUT
#     3 request classes   the whole set the refusal contract declares;
#     (7 routes strictly) 40 pairs, so 33 outside the named classes,
#                         including 23 GET reads in none of them
#
# ``metadata_completeness`` was one axis (a field list); this was three, and the
# KPI published ``measurement_gap=''`` beside it, so a buyer reading
# ``GET /enterprise/kpis`` saw all three with no disclosure attached. Partial
# disclosure existed only in the Korean gap document, and the third axis nowhere.
#
# Filling ``measurement_gap`` is not available as a repair:
# ``tests/test_kpi_measurement_disclosure.py`` forbids a gap when ``measured``
# is true, and rightly - a measured figure should not need an excuse. So the
# sentence is corrected to say what the figure is.
#
# **The population is named by its authority, not by a count.** Embedding
# ``len(policy_gated_route_methods())`` is not possible here and would be worse
# if it were: that function lives in ``sdp.api_error_contract`` and ``sdp_core``
# imports nothing from ``sdp`` (measured: zero such imports), so inlining the
# number would invert the layering. A literal would also drift the moment a
# route is added, which is the defect class this whole block exists to close.
# Naming the authority cannot drift; the correspondence is enforced instead by
# ``tests/test_the_definition_names_what_the_number_counts.py``.
def policy_audit_coverage_definition() -> str:
    """The definition sentence, saying what the published figure actually is.

    A count of the complement over the refusal contract's declared surface -
    not a share, not the with-evidence side, and not the three request classes
    the previous sentence named. The population is named rather than counted,
    so this string cannot go stale when a route is added; the guard in
    ``tests/test_the_definition_names_what_the_number_counts.py`` pins it to the
    live set.
    """
    return (
        "Count of policy-gated 2xx responses that recorded neither a policy "
        "decision nor an audit event, over every (method, path) pair the "
        "refusal contract declares as policy-gated - which is broader than "
        "preview, query, and catalog mutation alone and includes governed "
        "reads. Lower is better; the with-evidence share is not published."
    )


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
                definition=metadata_completeness_definition(),
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
                # The published figure is ``mean_metadata_completeness`` - the
                # key differs from the gate's name, which is part of why the
                # gate was pointed at by mistake.
                measurement_surface=(
                    "/enterprise/evidence-pack#mean_metadata_completeness"
                ),
            ),
            SaleabilityKPI(
                id="policy_audit_coverage",
                label="Policy and audit coverage",
                decision_question="Can every governed data action be explained and audited?",
                definition=policy_audit_coverage_definition(),
                # "100 percent" was a share's unit against a figure that is a
                # count, so the target could not be compared with the number it
                # targeted. A count's target is a count.
                target="0 governed requests without evidence",
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
                    "/enterprise/evidence-pack#ontology_mapping_coverage"
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
                # The earlier note here said the raw rate "is not" published.
                # That was wrong: ``/enterprise/evidence-pack`` publishes
                # ``metadata_validation_pass_rate`` at its top level, and this
                # pointer named the same-named *gate verdict* one level down.
                # The defect was the pointer, not a missing measurement - and
                # deferring it on a false premise is how it survived a commit.
                measurement_surface=(
                    "/enterprise/evidence-pack#metadata_validation_pass_rate"
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
