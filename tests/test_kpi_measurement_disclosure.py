"""A published target nobody compares is not a gate — checked over every KPI.

``nl_catalog_search_success`` shipped ``status="implemented"`` with
``target=">=80 percent"`` and ``cadence="golden set review"``. Measured at
``0bbb58b``, its identifier occurred exactly once in all of ``src/`` - its own
declaration. No curated question set, no eval harness, no value on any
endpoint, and no comparison to 80 anywhere in the tree. The product points the
diligence reader straight at it: ``/enterprise/evidence-pack`` lists
``/enterprise/kpis`` in ``open_proof_endpoints`` and names this KPI among its
``guardrail_kpis``, and the endpoint answers 200 unauthenticated.

This repository had already adjudicated the class in writing - README's bullet
on ``metadata_completeness`` ("비교하지 않는 target은 게이트가 아닙니다") and
``tests/test_catalog_field_forwarding.py::test_the_metadata_completeness_target_is_compared``.
**That guard is keyed to one id**, ``item.id == "metadata_completeness"``, and
was never generalized, which is exactly how the next instance escaped. So this
file is the generalization: every KPI, derived from the framework rather than
enumerated here.

Two things it deliberately does **not** do. It does not demand that
``nl_catalog_search_success`` become ``planned``: its surfaces are shipped and
answer 200, and this repository already wrote that "a stale 'this is not
implemented' misleads the same buyer as a premature 'this is'" - so a stale
denial is the same defect from the other side. And it does not demand the eval
harness be built (PRD epic ``E5-S4``, unbuilt, genuinely large). It demands the
two statuses be **separate and both honest**: the feature ships, the number is
not computed, and the KPI says so.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sdp.api import app  # noqa: E402
from sdp_core import enterprise_kpi_framework  # noqa: E402


client = TestClient(app)

# A target that promises a number. ``0 blocking PRs`` counts: it is a threshold.
_NUMERIC_TARGET = re.compile(r"\d")


def _all_kpis():
    """Every published KPI, from both lists, derived rather than listed."""
    framework = enterprise_kpi_framework()
    published = list(framework.primary_kpis) + list(framework.guardrail_kpis)
    assert len(published) >= 5, [kpi.id for kpi in published]
    return published


def _resolve(surface: str):
    """Fetch the value a ``endpoint#dotted.key`` pointer names."""
    endpoint, _, pointer = surface.partition("#")
    response = client.get(endpoint, params={"user": "admin"})
    assert response.status_code == 200, (
        f"{surface}: {endpoint} answered {response.status_code}"
    )
    value = response.json()
    for part in pointer.split("."):
        assert isinstance(value, dict) and part in value, (
            f"{surface}: {part!r} is not in {sorted(value) if isinstance(value, dict) else type(value)}"
        )
        value = value[part]
    return value


@pytest.mark.parametrize("kpi", _all_kpis(), ids=lambda k: k.id)
def test_an_implemented_numeric_target_is_measured_or_discloses_why_not(kpi) -> None:
    """The generalization of the single-id guard that let this through.

    A KPI may be unmeasured. It may not be unmeasured *silently* while
    publishing a number as its target and ``implemented`` as its status.
    """
    if kpi.status != "implemented" or not _NUMERIC_TARGET.search(kpi.target):
        pytest.skip(f"{kpi.id}: status={kpi.status}, target={kpi.target!r}")
    assert kpi.measured or kpi.measurement_gap, (
        f"{kpi.id} publishes status=implemented against target "
        f"{kpi.target!r} with measured=False and no measurement_gap, so a "
        "reader cannot tell an authored intent from a measured result"
    )


@pytest.mark.parametrize("kpi", _all_kpis(), ids=lambda k: k.id)
def test_a_measured_kpi_points_at_a_surface_that_resolves(kpi) -> None:
    """A pointer that does not resolve is worse than no pointer."""
    if not kpi.measured:
        pytest.skip(f"{kpi.id} is not measured")
    assert kpi.measurement_surface, f"{kpi.id} claims measured with no surface"
    value = _resolve(kpi.measurement_surface)
    assert value is not None, (
        f"{kpi.id} points at {kpi.measurement_surface}, which resolves to None"
    )


@pytest.mark.parametrize("kpi", _all_kpis(), ids=lambda k: k.id)
def test_a_measured_kpi_points_at_a_number_not_a_gate_verdict(kpi) -> None:
    """Resolving is the weaker property. The field says *figure*.

    ``measurement_surface``'s own contract is "where this KPI's own figure is
    published", and the guard above checks only that the pointer resolves to
    something other than ``None``. Measured at ``c27958f``, three of the four
    ``measured`` pointers resolved to the string ``'pass'`` - the
    ``saleability_gates`` verdict, next to the number rather than the number::

        metadata_completeness      -> saleability_gates.metadata_completeness      'pass'
        ontology_mapping_coverage  -> saleability_gates.ontology_mapping_coverage  'pass'
        validation_pass_rate       -> saleability_gates.metadata_validation_pass_rate 'pass'

    Every target here carries a number (``>=90 percent``, ``>=70 percent``,
    ``>=95 percent``), so a buyer following the pointer to check the claim got
    a verdict and could not see the value, the threshold it was compared
    against, or the margin. The verdict is the product's own opinion of the
    measurement; publishing it in the measurement's place is the same
    substitution this round repaired on the drafter and on ``/graph/stats``.

    A number is the checkable property: a reader can compare it to the target
    themselves. ``bool`` is excluded explicitly because it is an ``int``
    subclass in Python, and a boolean is a verdict too.
    """
    if not kpi.measured:
        pytest.skip(f"{kpi.id} is not measured")
    value = _resolve(kpi.measurement_surface)
    assert isinstance(value, (int, float)) and not isinstance(value, bool), (
        f"{kpi.id} publishes measured=True and points at "
        f"{kpi.measurement_surface}, which resolves to {value!r} - a verdict, "
        f"not the figure its target {kpi.target!r} is compared against"
    )


@pytest.mark.parametrize("kpi", _all_kpis(), ids=lambda k: k.id)
def test_a_measured_pointer_does_not_name_the_gate_block(kpi) -> None:
    """The structural half, so the repair cannot be undone by renaming a key.

    A number could be published *inside* ``saleability_gates`` later, which
    would satisfy the check above while putting the figure back in the block
    whose job is verdicts. The two blocks have different jobs and the pointer
    has to name the one that carries measurements.
    """
    if not kpi.measured:
        pytest.skip(f"{kpi.id} is not measured")
    assert "saleability_gates" not in kpi.measurement_surface, (
        f"{kpi.id} points into the gate-verdict block: "
        f"{kpi.measurement_surface}"
    )


@pytest.mark.parametrize("kpi", _all_kpis(), ids=lambda k: k.id)
def test_an_unmeasured_kpi_publishes_no_pointer_and_no_both_ways(kpi) -> None:
    """The two fields cannot both be set, in either direction."""
    if kpi.measured:
        assert not kpi.measurement_gap, (
            f"{kpi.id} is measured and also declares a measurement gap"
        )
    else:
        assert not kpi.measurement_surface, (
            f"{kpi.id} is not measured and still points at "
            f"{kpi.measurement_surface}"
        )


def test_at_least_one_kpi_exercises_each_branch() -> None:
    """Keeps the three parametrized checks above from passing by skipping.

    Measured at the time of writing: four KPIs measured, one implemented with a
    numeric target and a declared gap, three neither implemented nor numeric.
    Asserted as "at least one of each" rather than as those counts, so adding a
    KPI does not fail this for the wrong reason.
    """
    kpis = _all_kpis()
    measured = [kpi.id for kpi in kpis if kpi.measured]
    disclosed = [
        kpi.id
        for kpi in kpis
        if not kpi.measured
        and kpi.status == "implemented"
        and _NUMERIC_TARGET.search(kpi.target)
    ]
    assert measured, "no KPI is measured, so the pointer check never runs"
    assert disclosed, (
        "no KPI discloses a measurement gap, so the disclosure check never "
        "runs - if every KPI became measured this file should be re-read "
        "rather than silently skipped"
    )


def test_the_published_kpi_response_carries_both_statuses() -> None:
    """A field that exists only in the model tells a buyer nothing.

    The defect is on the published surface, so the repair has to be too.
    """
    body = client.get("/enterprise/kpis").json()
    items = [
        item
        for group in ("primary_kpis", "guardrail_kpis")
        for item in body.get(group, [])
    ]
    assert items, sorted(body)
    gap_kpi = [item for item in items if item["id"] == "nl_catalog_search_success"]
    assert gap_kpi, [item["id"] for item in items]
    published = gap_kpi[0]
    assert published["status"] == "implemented", published["status"]
    assert published["measured"] is False, published
    assert published["measurement_gap"], (
        "the published KPI does not carry its own measurement gap, so the "
        "disclosure exists only in the source"
    )


def test_the_disclosure_names_what_is_not_measured_rather_than_a_guess() -> None:
    """The gap text was corrected once already; this pins the correction.

    The first write-up called this "the KPI that bounds hallucinated dataset
    results". It bounds nothing of the kind: ``/llm/search`` is a deterministic
    alias lookup whose ``dataset_ids`` come from the catalog index, so a
    non-existent dataset cannot be emitted by construction - measured, an
    unresolvable question answers ``{"error": "No resolvable ontology term."}``
    rather than inventing assets. The unmeasured quantity is **recall**.
    """
    gap = next(
        kpi.measurement_gap
        for kpi in _all_kpis()
        if kpi.id == "nl_catalog_search_success"
    )
    assert "recall" in gap, gap
    # No word-absence check here. The first version asserted
    # ``"hallucination" not in gap``, and the disclosure says recall "and *not*
    # hallucination rate" - so the assertion failed on the text's own denial.
    # A substring cannot distinguish a claim from its negation, which is the
    # same mistake as searching prose for a number, so the premise is checked
    # by behaviour below instead of by vocabulary.

    unresolvable = client.post(
        "/llm/search", json={"question": "zzz nonexistent unicorn table"}
    )
    assert unresolvable.status_code == 200, unresolvable.text
    assert "error" in unresolvable.json(), (
        "the premise of the correction is that an unresolvable question is "
        f"refused rather than answered with invented assets: {unresolvable.json()}"
    )
