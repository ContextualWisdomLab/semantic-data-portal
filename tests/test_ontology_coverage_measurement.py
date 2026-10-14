"""``ontology_mapping_coverage`` rose when coverage fell.

It was ``approved mappings / all mappings``, while its own published definition
says "share of buyer critical glossary terms mapped". The denominator was the
set of mappings that happen to exist, so the metric is not a coverage metric at
all. Measured against the seed, deleting seven of the twelve mappings and
keeping one approved mapping per dataset::

    mappings 12 -> 5   over the same 16 columns
    published "coverage" 0.917 -> 1.0

It gates ``sdp.demo_smoke``'s ``ready`` flag and a saleability gate at >= 0.7,
and a procurement reader takes it for what its name says.

Two further things the old denominator hid, both measured on the seed:

* the glossary concept ``이탈 고객`` has no mapping at all, and was not in the
  denominator - so the one genuine coverage gap was invisible.
* three mapping concepts (``고객 이탈``, ``전환``, ``캠페인``) resolve to nothing:
  neither canonical concepts nor aliases. Two are approved, so the old numerator
  counted approved mappings to **undefined** concepts as ontology coverage.

Three quantities are now published under names that say which is which. The
headline counts approved mappings only, matching the KPI's own guardrail; the
definition's "or active steward patch proposals" clause contradicted that
guardrail and is corrected rather than implemented (the seed has zero patches,
so it was contributing nothing either way).
"""

from __future__ import annotations

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sdp import catalog, ontology  # noqa: E402
from sdp.enterprise_evidence import (  # noqa: E402
    build_enterprise_evidence_pack,
    ontology_mapping_coverage_detail,
)
from sdp_core import MappingStatus  # noqa: E402


def _keep_one_approved_mapping_per_dataset() -> None:
    """The exact mutation that used to raise the published number."""
    for dataset_id, dataset in list(catalog._DATA.items()):
        keep = [m for m in dataset.mappings if m.status == MappingStatus.APPROVED][:1]
        catalog._DATA[dataset_id] = dataset.model_copy(update={"mappings": keep})


def test_deleting_mappings_lowers_coverage() -> None:
    """The defining property of a coverage metric, and the one it failed."""
    before = ontology_mapping_coverage_detail()["ontology_mapping_coverage"]
    mapping_count = sum(len(d.mappings) for d in catalog.list_datasets())
    _keep_one_approved_mapping_per_dataset()
    after_count = sum(len(d.mappings) for d in catalog.list_datasets())
    assert after_count < mapping_count, "fixture must actually remove mappings"

    after = ontology_mapping_coverage_detail()["ontology_mapping_coverage"]
    assert after < before, (
        f"removing {mapping_count - after_count} mappings moved coverage "
        f"{before} -> {after}; it used to rise to 1.0"
    )


def test_the_approval_rate_is_published_under_its_own_name() -> None:
    """The old number is kept - it is a real number, it was just mislabelled."""
    detail = ontology_mapping_coverage_detail()
    mappings = [m for d in catalog.list_datasets() for m in d.mappings]
    approved = sum(1 for m in mappings if m.status == MappingStatus.APPROVED)
    assert detail["ontology_mapping_approval_rate"] == round(approved / len(mappings), 3)

    # And it is the number that rises when mappings are deleted, which is
    # correct for what *it* measures - now that its name says so.
    before = detail["ontology_mapping_approval_rate"]
    _keep_one_approved_mapping_per_dataset()
    assert ontology_mapping_coverage_detail()["ontology_mapping_approval_rate"] >= before


def test_coverage_is_measured_against_the_glossary() -> None:
    detail = ontology_mapping_coverage_detail()
    assert detail["glossary_concept_count"] == len(ontology.list_concepts())
    assert detail["ontology_mapping_coverage"] == round(
        detail["covered_glossary_concept_count"] / detail["glossary_concept_count"], 3
    )


def test_an_unmapped_glossary_concept_is_named_rather_than_excluded() -> None:
    """The gap the old denominator could not express.

    A concept with no mapping was simply absent from the calculation, so adding
    an unmapped concept to the glossary did not move the number at all.
    """
    detail = ontology_mapping_coverage_detail()
    assert detail["unmapped_glossary_concepts"], (
        "the seed has a glossary concept with no approved mapping; it must be named"
    )
    for concept in detail["unmapped_glossary_concepts"]:
        assert concept in ontology.list_concepts()
        approved = [
            mapping
            for dataset in catalog.list_datasets()
            for mapping in dataset.mappings
            if ontology.canonical_concept_or_none(mapping.concept) == concept
            and mapping.status == MappingStatus.APPROVED
        ]
        assert not approved, f"{concept} has an approved mapping and is named as unmapped"


def test_registering_an_unmapped_concept_lowers_coverage() -> None:
    """The denominator must respond to the glossary growing."""
    before = ontology_mapping_coverage_detail()
    ontology.register_concept(
        "거래 금액", change_source="concept_upsert", definition="테스트용 미매핑 개념"
    )
    after = ontology_mapping_coverage_detail()
    assert after["glossary_concept_count"] == before["glossary_concept_count"] + 1
    assert after["ontology_mapping_coverage"] < before["ontology_mapping_coverage"]
    assert "거래 금액" in after["unmapped_glossary_concepts"]


def test_a_mapping_to_an_undefined_concept_is_not_counted_as_coverage() -> None:
    """It was counted in the numerator, as approved evidence of ontology coverage."""
    detail = ontology_mapping_coverage_detail()
    assert detail["unregistered_mapping_concept_count"] >= 1, (
        "the seed has approved mappings naming concepts the ontology never defined"
    )
    for concept in detail["unregistered_mapping_concepts"]:
        assert ontology.canonical_concept_or_none(concept) is None, concept
        assert concept not in ontology.list_concepts()

    # Adding more of them must not raise coverage.
    base = catalog._DATA["crm-customer-master"]
    extra = base.mappings[0].model_copy(
        update={"concept": "존재하지 않는 개념", "status": MappingStatus.APPROVED}
    )
    catalog._DATA["crm-customer-master"] = base.model_copy(
        update={"mappings": list(base.mappings) + [extra]}
    )
    after = ontology_mapping_coverage_detail()
    assert after["ontology_mapping_coverage"] == detail["ontology_mapping_coverage"]
    assert (
        after["unregistered_mapping_concept_count"]
        == detail["unregistered_mapping_concept_count"] + 1
    )


def test_an_alias_mapping_still_counts_toward_its_canonical_concept() -> None:
    """Coverage is of concepts, not of spellings.

    ``canonical_concept_or_none`` exists for exactly this: a mapping naming an
    alias covers the canonical concept, while a mapping naming an unregistered
    term covers nothing. ``_canonicalize_concept`` alone cannot tell those apart
    because it returns its input unchanged for both.
    """
    alias, canonical = next(iter(ontology._ALIAS_TO_CANONICAL.items()))
    assert ontology.canonical_concept_or_none(alias) == canonical
    assert ontology.canonical_concept_or_none("확실히 없는 개념 이름") is None

    # Strip every mapping of the canonical concept from the whole catalog, so the
    # alias mapping is the only thing that can cover it. Coverage is computed
    # across all datasets, which is why mutating one dataset proves nothing here.
    for dataset_id, dataset in list(catalog._DATA.items()):
        catalog._DATA[dataset_id] = dataset.model_copy(
            update={
                "mappings": [
                    mapping
                    for mapping in dataset.mappings
                    if ontology.canonical_concept_or_none(mapping.concept) != canonical
                ]
            }
        )
    assert canonical in ontology_mapping_coverage_detail()["unmapped_glossary_concepts"]

    base = catalog._DATA["crm-customer-master"]
    template = next(
        mapping for d in catalog.list_datasets() for mapping in d.mappings
    )
    aliased = template.model_copy(
        update={"concept": alias, "status": MappingStatus.APPROVED}
    )
    catalog._DATA["crm-customer-master"] = base.model_copy(
        update={"mappings": list(base.mappings) + [aliased]}
    )
    detail = ontology_mapping_coverage_detail()
    assert canonical not in detail["unmapped_glossary_concepts"], detail
    # The alias was resolved, so it is not counted as an unregistered concept.
    assert alias not in detail["unregistered_mapping_concepts"], detail


def test_the_gate_and_the_demo_ready_flag_are_unchanged_by_the_repair() -> None:
    """Why this is a defect fix and not a product decision.

    Measured: the honest number is 0.8 (4 of 5 glossary concepts carry an
    approved mapping) against a 0.7 gate, so the gate still passes and
    ``sdp.demo_smoke``'s ``ready`` flag is unaffected. If a future seed drops
    below 0.7 this fails, and whoever changed it decides deliberately rather
    than discovering it through a red ``ready``.
    """
    pack = build_enterprise_evidence_pack()
    assert pack["ontology_mapping_coverage"] >= 0.7, pack["ontology_mapping_coverage"]
    assert pack["saleability_gates"]["ontology_mapping_coverage"] == "pass"


def test_the_published_definition_matches_what_is_computed() -> None:
    """Two published statements about one number used to disagree.

    The KPI definition said "approved concepts **or active steward patch
    proposals**" while its own guardrail said proposals are not treated as
    approved. The implementation honoured the guardrail, so the definition was
    the wrong one of the two and is corrected.
    """
    from sdp_core import enterprise_kpi_framework

    kpi = next(
        item
        for item in enterprise_kpi_framework().primary_kpis
        + enterprise_kpi_framework().guardrail_kpis
        if item.id == "ontology_mapping_coverage"
    )
    assert "registered glossary concepts" in kpi.definition
    assert "at least one approved business mapping" in kpi.definition
    assert "steward patch proposals" not in kpi.definition, (
        "the definition contradicted this KPI's own guardrail"
    )
    assert any("Proposed mappings are not treated" in g for g in kpi.guardrails)


def test_a_proposed_mapping_does_not_count_as_coverage() -> None:
    """The guardrail, exercised."""
    base = catalog._DATA["crm-customer-master"]
    concept = ontology.canonical_concept_or_none(base.mappings[0].concept)
    assert concept, "fixture must map a registered concept"
    assert concept not in ontology_mapping_coverage_detail()["unmapped_glossary_concepts"]

    # Demote it in *every* dataset: more than one dataset maps the same concept,
    # and coverage is a property of the catalog, not of one dataset. Demoting
    # only one left it covered - which is the metric behaving correctly.
    for dataset_id, dataset in list(catalog._DATA.items()):
        catalog._DATA[dataset_id] = dataset.model_copy(
            update={
                "mappings": [
                    mapping.model_copy(update={"status": MappingStatus.PROPOSED})
                    if ontology.canonical_concept_or_none(mapping.concept) == concept
                    else mapping
                    for mapping in dataset.mappings
                ]
            }
        )
    detail = ontology_mapping_coverage_detail()
    assert concept in detail["unmapped_glossary_concepts"], detail


def test_the_raw_unregistered_concept_names_stay_off_the_evidence_pack() -> None:
    """The pack is an unauthenticated read.

    The count is published so the gap is visible; the concept strings come from
    tenant dataset mappings, so they are not. The detail function returns them
    for operators and tests.
    """
    pack = build_enterprise_evidence_pack()
    assert "unregistered_mapping_concept_count" in pack
    assert "unregistered_mapping_concepts" not in pack
    assert ontology_mapping_coverage_detail()["unregistered_mapping_concepts"]


# --------------------------------------------------------------------------- #
# Two more directions the old metric failed, surfaced by an adversarial review
# of the first repair.
# --------------------------------------------------------------------------- #


def test_proposing_a_mapping_for_the_uncovered_concept_does_not_lower_coverage() -> None:
    """The old metric moved the wrong way for the single most useful action.

    A steward proposing a mapping for the one genuinely uncovered glossary
    concept is the action that most improves real coverage. Under
    ``approved / all mappings`` the new proposed row landed in the denominator
    only, so the published figure **fell**: measured 0.917 -> 0.846. The metric
    was anti-correlated with the thing it claimed to measure.

    Glossary-based coverage holds steady instead - the concept is not covered
    until the mapping is approved, which is what the guardrail says - and
    approving it then raises coverage.
    """
    before = ontology_mapping_coverage_detail()
    target = before["unmapped_glossary_concepts"][0]
    base = catalog._DATA["crm-customer-master"]
    proposed = base.mappings[0].model_copy(
        update={"concept": target, "status": MappingStatus.PROPOSED}
    )
    catalog._DATA["crm-customer-master"] = base.model_copy(
        update={"mappings": list(base.mappings) + [proposed]}
    )
    after = ontology_mapping_coverage_detail()
    assert after["ontology_mapping_coverage"] >= before["ontology_mapping_coverage"], (
        f"proposing a mapping for {target!r} lowered coverage: "
        f"{before['ontology_mapping_coverage']} -> {after['ontology_mapping_coverage']}"
    )
    assert target in after["unmapped_glossary_concepts"], "proposed is not approved"

    # Approving it is what moves the number.
    approved = proposed.model_copy(update={"status": MappingStatus.APPROVED})
    catalog._DATA["crm-customer-master"] = base.model_copy(
        update={"mappings": list(base.mappings) + [approved]}
    )
    final = ontology_mapping_coverage_detail()
    assert final["ontology_mapping_coverage"] > before["ontology_mapping_coverage"]
    assert target not in final["unmapped_glossary_concepts"]


def test_the_published_evidence_names_the_surfaces_the_measurement_reads() -> None:
    """``/ontology/patches`` was published as evidence and is never consulted.

    The KPI's definition also promised "or active steward patch proposals",
    which no code implemented - that clause was corrected to the stricter
    reading the guardrail already stated, but the endpoint stayed in both the
    gate's ``evidence`` and the KPI's ``source_endpoints``. A diligence reader
    following the published evidence fetched a queue contributing nothing to the
    number.

    The queue is genuine evidence for the steward-review surface, which does
    read it; it is not evidence for this measurement.
    """
    from sdp_core import enterprise_kpi_framework, enterprise_readiness_manifest

    framework = enterprise_kpi_framework()
    kpi = next(
        item
        for item in framework.primary_kpis + framework.guardrail_kpis
        if item.id == "ontology_mapping_coverage"
    )
    gate = next(
        item
        for item in enterprise_readiness_manifest().enterprise_gates
        if item.id == "ontology_mapping_coverage"
    )

    for published in (kpi.source_endpoints, gate.evidence):
        assert "/ontology/patches" not in published, published
        # The denominator, the numerator, and where the figure is published.
        assert "/ontology/concepts" in published, published
        assert "/catalog/datasets/{dataset_id}" in published, published
        assert "/enterprise/evidence-pack" in published, published


def test_every_published_evidence_endpoint_is_a_real_route() -> None:
    """Enumerated across every manifest, because one dangling pointer is enough.

    Measured: 34 endpoint-shaped evidence pointers across the readiness gates,
    KPIs, controls and production integrations, all of which currently resolve.
    Pinned so a renamed route cannot leave a diligence reader following a 404.
    """
    from fastapi.routing import APIRoute

    from sdp.api import app
    from sdp_core import (
        enterprise_controls_manifest,
        enterprise_kpi_framework,
        enterprise_production_readiness_manifest,
        enterprise_readiness_manifest,
    )

    routes = {route.path for route in app.routes if isinstance(route, APIRoute)}
    pointers: list[tuple[str, str, str]] = []
    for item in enterprise_readiness_manifest().enterprise_gates:
        pointers.extend(("gate", item.id, ref) for ref in item.evidence)
    framework = enterprise_kpi_framework()
    for item in framework.primary_kpis + framework.guardrail_kpis:
        pointers.extend(("kpi", item.id, ref) for ref in item.source_endpoints)
    for item in enterprise_controls_manifest().controls:
        pointers.extend(
            ("control", item.id, ref) for ref in (getattr(item, "proof_endpoints", None) or [])
        )
    for item in enterprise_production_readiness_manifest().integrations:
        pointers.extend(("integration", item.id, ref) for ref in item.current_evidence)

    endpoint_like = [row for row in pointers if row[2].startswith("/")]
    assert len(endpoint_like) >= 34, len(endpoint_like)
    dangling = [row for row in endpoint_like if row[2] not in routes]
    assert not dangling, f"published evidence pointing at routes that do not exist: {dangling}"
