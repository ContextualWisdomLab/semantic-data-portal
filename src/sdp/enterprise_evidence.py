from __future__ import annotations

from typing import Any

from sdp_core import (
    MappingStatus,
    buyer_demo_activation_plan,
    enterprise_controls_manifest,
    enterprise_kpi_framework,
    enterprise_production_readiness_manifest,
    enterprise_readiness_manifest,
)

from .catalog import count_audit_events, list_audit_events, list_datasets, validate_metadata
from .evidence import count_policy_decisions, list_policy_decisions
from .ontology import canonical_concept_or_none, list_concepts, ontology_version_identity
from .semantic_validation import enterprise_shacl_validation_summary
from .steward_review import build_steward_review_summary


def _ratio(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return round(numerator / denominator, 3)


def _mean_metadata_completeness() -> float:
    """The number behind the ``metadata_completeness`` KPI's own target.

    That KPI published ``target: ">=90 percent display coverage"`` with
    ``status: implemented`` while nothing in the code compared anything to 0.90.
    The two thresholds that existed were 0.95 on
    ``metadata_validation_pass_rate`` - the share of datasets with *no* missing
    field, which is a different and stricter measure - and 0.7 on ontology
    coverage. A target nothing compares to is not a gate.
    """
    datasets = list_datasets()
    if not datasets:
        return 0.0
    return round(
        sum(dataset.metadata_completeness for dataset in datasets) / len(datasets), 3
    )


def _metadata_validation_pass_rate() -> float:
    datasets = list_datasets()
    valid = sum(1 for dataset in datasets if validate_metadata(dataset)["is_valid"])
    return _ratio(valid, len(datasets))


def ontology_mapping_coverage_detail() -> dict[str, Any]:
    """Coverage of the glossary, and the two numbers it was conflated with.

    ``ontology_mapping_coverage`` was ``approved mappings / all mappings``. Its
    own published definition says something else - "share of buyer critical
    glossary terms mapped" - and the difference is not cosmetic: the denominator
    was the set of mappings that happen to exist, so the metric *rose when
    coverage fell*. Measured against the seed, deleting seven of the twelve
    mappings and keeping one approved mapping per dataset::

        mappings 12 -> 5   over the same 16 columns
        published "coverage" 0.917 -> 1.0

    A coverage number that improves when you delete coverage is measuring
    something else, and it gates ``sdp.demo_smoke``'s ``ready`` flag and a
    saleability gate at >= 0.7.

    Two further things the old denominator hid, both measured on the seed:

    * the glossary concept ``이탈 고객`` has no mapping at all. It was not in the
      denominator, so the one genuine coverage gap was invisible.
    * three mapping concepts - ``고객 이탈``, ``전환``, ``캠페인`` - resolve to
      nothing: neither canonical concepts nor aliases. Two of the three are
      approved, so the old numerator counted approved mappings to **undefined**
      concepts as evidence of ontology coverage.

    So three distinct quantities are published under names that say which is
    which, rather than one number standing in for all of them. The headline
    counts approved mappings only, matching the KPI's own guardrail
    ("Proposed mappings are not treated as approved mappings") - the published
    definition's "or active steward patch proposals" clause contradicted that
    guardrail, and is corrected rather than implemented.
    """
    mappings = [mapping for dataset in list_datasets() for mapping in dataset.mappings]
    glossary = list_concepts()

    approved_concepts: set[str] = set()
    mapped_concepts: set[str] = set()
    unregistered: set[str] = set()
    for mapping in mappings:
        canonical = canonical_concept_or_none(mapping.concept)
        if canonical is None:
            unregistered.add(mapping.concept)
            continue
        mapped_concepts.add(canonical)
        if mapping.status == MappingStatus.APPROVED:
            approved_concepts.add(canonical)

    covered = sorted(approved_concepts)
    return {
        # Coverage *of the glossary*: what the published definition describes.
        "ontology_mapping_coverage": _ratio(len(covered), len(glossary)),
        # The old number, under a name that says what it measures.
        "ontology_mapping_approval_rate": _ratio(
            sum(1 for mapping in mappings if mapping.status == MappingStatus.APPROVED),
            len(mappings),
        ),
        "glossary_concept_count": len(glossary),
        "covered_glossary_concept_count": len(covered),
        # Declared, not hidden: the concepts a buyer would ask about next.
        "unmapped_glossary_concepts": sorted(set(glossary) - approved_concepts),
        # Mappings pointing at concepts the ontology does not define. These are
        # excluded from coverage and counted here instead of credited to it.
        "unregistered_mapping_concept_count": len(unregistered),
        "unregistered_mapping_concepts": sorted(unregistered),
    }


def ontology_version_summary() -> dict[str, Any]:
    """The ontology version, trimmed to what belongs in a diligence pack.

    The full identity surface publishes seventeen fields including the digest
    basis and the change vocabularies; a pack needs the identity and the one
    limitation that changes how a reader may use it.
    """
    identity = ontology_version_identity()
    return {
        "revision": identity["ontology_revision"],
        "content_digest": identity["content_digest"],
        "revision_is_durable": identity["revision_is_durable"],
        "concept_count": identity["concept_count"],
        "change_log_entry_count": identity["change_log_entry_count"],
        "digest_matches_recorded_revision": identity["digest_matches_recorded_revision"],
    }


def _ontology_mapping_coverage() -> float:
    """The glossary-coverage headline, for the gate and the evidence pack."""
    return float(ontology_mapping_coverage_detail()["ontology_mapping_coverage"])


# Published diligence links, split by whether they are governed reads.
#
# An unauthenticated fetch of a governed read answers 403, which is the access
# control working - but the evidence pack listed those links beside the open ones
# with no distinction, so a reader following the list saw three dead links and
# had no way to tell a refusal from a missing capability.
OPEN_PROOF_ENDPOINTS = [
    "/enterprise/readiness",
    "/enterprise/demo-plan",
    "/enterprise/kpis",
    "/enterprise/controls",
    "/enterprise/rbac-matrix",
    "/enterprise/observability",
    "/enterprise/production-readiness",
    "/enterprise/shacl-validation",
    "/enterprise/steward-review",
    # ONT-004's two open halves: the live ontology version, and the versioned
    # SKOS/RDFS artifact the revision names. Both carry counts and content, no
    # identity - the identity-bearing change log is actor-scoped below.
    "/ontology/version",
    "/ontology/vocabulary/jsonld",
    "/metrics",
]

ACTOR_SCOPED_PROOF_ENDPOINTS = [
    "/enterprise/connectors/sql_connector/probe?dataset_id=crm-customer-master&user=<actor>",
    "/policy/decisions?user=<actor>",
    "/audit/events?user=<actor>",
    # Every entry names an actor and, on an approval, a reviewer, so this is
    # gated like the other two ledgers rather than published open beside the
    # version. ONT-004's reviewer-record evidence lives here.
    "/ontology/change-log?user=<actor>",
]


def build_enterprise_evidence_pack() -> dict[str, Any]:
    readiness = enterprise_readiness_manifest()
    demo_plan = buyer_demo_activation_plan()
    controls = enterprise_controls_manifest()
    kpis = enterprise_kpi_framework()
    production = enterprise_production_readiness_manifest()
    shacl_validation = enterprise_shacl_validation_summary()
    steward_review = build_steward_review_summary()
    datasets = list_datasets()
    audit_events = list_audit_events(limit=500)
    policy_decisions = list_policy_decisions(limit=500)
    # Real counts, not the size of the page above. See
    # ``catalog.count_audit_events``.
    audit_event_count, audit_count_is_lower_bound = count_audit_events()
    policy_decision_count, policy_count_is_lower_bound = count_policy_decisions()

    return {
        "product": readiness.product,
        "valuation_target_krw": readiness.valuation_target_krw,
        "demo_domain": demo_plan.priority_domain,
        "dataset_count": len(datasets),
        "demo_seed_datasets": [dataset.id for dataset in demo_plan.demo_datasets],
        # ONT-004: the version a diligence reader is comparing against, in the
        # pack rather than only behind a link. Process-local, and labelled so.
        **{
            f"ontology_{key}": value
            for key, value in ontology_version_summary().items()
        },
        "metadata_validation_pass_rate": _metadata_validation_pass_rate(),
        "mean_metadata_completeness": _mean_metadata_completeness(),
        "shacl_validation_pass_rate": shacl_validation["validation_pass_rate"],
        "steward_review_queue_count": steward_review["review_queue_count"],
        "steward_buyer_handoff_ready": steward_review["buyer_handoff_ready"],
        **{
            key: value
            for key, value in ontology_mapping_coverage_detail().items()
            if key != "unregistered_mapping_concepts"
        },
        "policy_decision_count": policy_decision_count,
        "audit_event_count": audit_event_count,
        # Declared rather than silently wrong, if the ceiling is ever reached.
        "policy_decision_count_is_lower_bound": policy_count_is_lower_bound,
        "audit_event_count_is_lower_bound": audit_count_is_lower_bound,
        "production_demo_release_ready": production.demo_release_ready,
        "production_paid_pilot_ready": production.paid_pilot_ready,
        "production_paid_pilot_blockers": len(production.paid_pilot_blockers),
        "implemented_enterprise_controls": controls.implemented_controls,
        "planned_enterprise_controls": controls.planned_controls,
        "primary_kpis": [kpi.id for kpi in kpis.primary_kpis],
        "guardrail_kpis": [kpi.id for kpi in kpis.guardrail_kpis],
        "proof_endpoints": OPEN_PROOF_ENDPOINTS + ACTOR_SCOPED_PROOF_ENDPOINTS,
        # Three of the thirteen published links are governed reads and answer 403
        # without an actor. Measured: fetched exactly as published, the connector
        # probe, /policy/decisions and /audit/events all refused - so a diligence
        # reader following the list concluded the proof did not exist, when in
        # fact it is the governance working. The list is now split and the
        # parameter is named, rather than leaving the reader to guess.
        "open_proof_endpoints": OPEN_PROOF_ENDPOINTS,
        "actor_scoped_proof_endpoints": ACTOR_SCOPED_PROOF_ENDPOINTS,
        "actor_scoped_proof_note": (
            "이 경로들은 거버닝 읽기이므로 actor가 필요합니다. "
            "`?user=<actor>`를 붙이지 않으면 403으로 거부되며, 그 거부 자체가 "
            "접근 통제가 동작한다는 증거입니다."
        ),
        "saleability_gates": {
            "metadata_validation_pass_rate": "pass" if _metadata_validation_pass_rate() >= 0.95 else "gap",
            # The KPI of this id publishes ">=90 percent"; this is the
            # comparison that was missing.
            "metadata_completeness": "pass" if _mean_metadata_completeness() >= 0.90 else "gap",
            "shacl_validation_pass_rate": "pass" if shacl_validation["validation_pass_rate"] >= 0.95 else "gap",
            "steward_review_queue": "pass" if steward_review["buyer_handoff_ready"] else "needs_review",
            "ontology_mapping_coverage": "pass" if _ontology_mapping_coverage() >= 0.7 else "gap",
            "policy_decisions_inspectable": "pass" if policy_decisions else "needs_activity",
            "audit_events_inspectable": "pass" if audit_events else "needs_activity",
            "enterprise_controls_visible": "pass" if controls.implemented_controls >= 2 else "gap",
            "production_demo_release": "pass" if production.demo_release_ready else "gap",
            "production_paid_pilot": "pass" if production.paid_pilot_ready else "needs_integration",
        },
    }
