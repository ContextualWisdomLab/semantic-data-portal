"""A published KPI definition must be computable, and compute the published number.

``metadata_completeness`` is gated at 0.90 by ``/enterprise/evidence-pack``, and
its definition told a diligence reader to count a different set of fields than
the gate counts. Measured on the published definition against
``REQUIRED_METADATA_FIELDS``::

    named by the definition : owner steward schema lineage quality freshness
                              license sensitivity          (8)
    counted by the number   : owner steward title description domain sensitivity
                              update_frequency source_system schema
                              distributions                 (10)
    named AND counted       : owner steward schema sensitivity          (4)
    named but NOT counted   : lineage quality freshness license         (4)
    counted but NOT named   : title description domain update_frequency
                              source_system distributions              (6)

Both directions matter. The four it named and did not count invite a reader to
mark a dataset incomplete over a field the gate ignores; the six it counted and
did not name let a dataset pass the gate on fields the definition never
mentioned. A reader following the definition arrives at a number the product
does not publish, and the product publishes a number no reader can reproduce.

What this file guards is that all three of the definition's clauses stay true:
the counted clause **is** the tally (derived from it, so the only failure left is
a formatting one), the uncounted names are genuinely absent from it, and - the
part that is a measurement rather than a string comparison - each uncounted name
is scored where the sentence says it is scored. That last clause is where the
first draft of this repair was itself wrong: it said all four were "scored by
recommended_score instead", and two of them are scored by nothing.
"""

from __future__ import annotations

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sdp_core import enterprise_kpi_framework  # noqa: E402
from sdp_core.contracts import REQUIRED_METADATA_FIELDS, Dataset  # noqa: E402
from sdp_core.kpis import (  # noqa: E402
    RECOMMENDATION_SCORED_FIELDS,
    UNSCORED_DISPLAY_FIELDS,
    metadata_completeness_definition,
    policy_audit_coverage_definition,
)

# This guard existed for exactly the ``policy_audit_coverage`` defect and could
# not see it, because every assertion below was reached through
# ``if item.id == "metadata_completeness"``. A curated list wearing a
# derivation's clothes - the same shape as the oracle sweep that derived its
# surfaces from path templates and so could not see a body-named one.
#
# The registry replaces the pin. An id in it must publish its derived sentence.
DERIVED_DEFINITIONS = {
    "metadata_completeness": metadata_completeness_definition,
    "policy_audit_coverage": policy_audit_coverage_definition,
}

# A ``measured=True`` KPI whose sentence is a hand-written literal is where this
# defect class lives, so none may sit outside both sets silently. These two are
# exempt on MEASUREMENT, not on judgement: the round-32 sweep ran each one's
# definition against its published figure and both reproduced it, so deriving
# them would add churn without adding honesty. If that stops being true the
# exemption is wrong and the entry has to move into DERIVED_DEFINITIONS.
MEASURED_WITH_A_LITERAL_DEFINITION = {
    "ontology_mapping_coverage": (
        "swept and verified MATCHES with the measurement run, not read: the "
        "sentence's excluded-mapping clause is the one the figure applies."
    ),
    "validation_pass_rate": (
        "swept and verified MATCHES with the measurement run, not read."
    ),
}

# A complete dataset, so a probe can drop exactly one field at a time.
COMPLETE_DATASET: dict[str, object] = {
    "id": "definition-probe",
    "tenant_id": "demo",
    "title": "T",
    "description": "d",
    "owner": "a",
    "steward": "a",
    "domain": "s",
    "source_system": "postgresql://a.dw/t",
    "sensitivity": "low",
    "update_frequency": "daily",
    "quality_score": 0.9,
    "freshness_score": 0.9,
    "schema": [
        {"name": "c", "datatype": "string", "nullable_ratio": 0.0, "distinct_ratio": 1.0}
    ],
    "distributions": [{"id": "d1", "format": "table", "endpoint": "https://x/y"}],
}

# How to set each uncounted field low and high, since "absent" differs by type
# and two of these fields have no absent state at all.
PROBE_RANGE: dict[str, tuple[object, object]] = {
    "license": ("", "CC-BY-4.0"),
    "lineage_inputs": ([], ["crm-event"]),
    "quality_score": (0.0, 1.0),
    "freshness_score": (0.0, 1.0),
}


def _counted_clause() -> list[str]:
    """The field names the published definition presents as counted."""
    definition = metadata_completeness_definition()
    head = definition.split("required fields: ", 1)
    assert len(head) == 2, definition
    clause = head[1].split(". Not counted here: ", 1)
    assert len(clause) == 2, definition
    return clause[0].split(", ")


def _published_kpis() -> list:
    """Every published KPI, primary and guardrail together."""
    framework = enterprise_kpi_framework()
    return list(framework.primary_kpis) + list(framework.guardrail_kpis)


@pytest.mark.parametrize("kpi_id", sorted(DERIVED_DEFINITIONS))
def test_the_published_definition_is_the_derived_one(kpi_id: str) -> None:
    """The framework must publish the derived sentence, not a copy of it."""
    kpi = next(item for item in _published_kpis() if item.id == kpi_id)
    assert kpi.definition == DERIVED_DEFINITIONS[kpi_id]()


def test_no_measured_kpi_sits_outside_both_sets() -> None:
    """A new measured KPI cannot arrive with an unexamined literal sentence.

    This is the half that was missing. The guard above only ever looked at ids
    it was told about, so ``policy_audit_coverage`` published a three-axis
    mismatch for as long as nobody added it by hand. Deriving the population
    from the framework itself means the omission fails instead of hiding.
    """
    measured = {item.id for item in _published_kpis() if item.measured}
    accounted = set(DERIVED_DEFINITIONS) | set(MEASURED_WITH_A_LITERAL_DEFINITION)
    unaccounted = measured - accounted
    assert not unaccounted, (
        f"measured KPIs with an unexamined definition: {sorted(unaccounted)}. "
        "Either derive the sentence and register it in DERIVED_DEFINITIONS, or "
        "measure the literal against the published figure and record that "
        "measurement in MEASURED_WITH_A_LITERAL_DEFINITION."
    )
    assert not (accounted - measured) - set(DERIVED_DEFINITIONS), (
        "an exemption names a KPI that is not measured: "
        f"{sorted((accounted - measured) - set(DERIVED_DEFINITIONS))}"
    )


def test_the_coverage_sentence_names_its_population_authority() -> None:
    """The sentence must name the refusal contract, not a snapshot count.

    A literal ``N (method, path) pairs`` would drift the moment a route is
    added, and cannot be computed here anyway: the live set lives in
    ``sdp.api_error_contract`` and ``sdp_core`` imports nothing from ``sdp``.
    So the sentence names the authority and this test pins the correspondence.
    """
    sentence = policy_audit_coverage_definition()
    assert "refusal contract declares" in sentence, sentence
    # The three axes the old sentence got wrong, each now stated correctly.
    assert sentence.startswith("Count of"), "the figure is a count, not a share"
    assert "neither a policy decision nor an audit event" in sentence, (
        "the figure counts the complement, not the with-evidence side"
    )
    assert "broader than" in sentence and "includes governed reads" in sentence, (
        "the population is wider than the three request classes"
    )
    assert "share is not published" in sentence, (
        "a reader must not be left expecting a share"
    )


def test_the_published_target_is_a_count_not_a_share() -> None:
    """The unit has to match the figure, or the target cannot be compared.

    ``100 percent`` was a share's unit against a counter. Measured: the
    pointed-at metric resolves to an ``int``.
    """
    kpi = next(item for item in _published_kpis() if item.id == "policy_audit_coverage")
    assert "percent" not in kpi.target, kpi.target
    assert kpi.target.startswith("0 "), kpi.target
    assert "without evidence" in kpi.target, kpi.target


def test_the_named_population_is_the_live_policy_gated_set() -> None:
    """The correspondence a named authority buys, actually checked.

    Imported here rather than in ``sdp_core`` on purpose - tests may cross the
    layer the product code may not.
    """
    from sdp.api_error_contract import policy_gated_route_methods

    live = policy_gated_route_methods()
    assert live, "the refusal contract declares no policy-gated route"
    # The sentence claims the set is broader than the three request classes it
    # used to name. Measure that rather than asserting it in prose alone.
    named_classes = tuple(
        pair
        for pair in live
        if pair[1].endswith("/preview")
        or pair[1].endswith("/browse/query")
        or (pair[0] in {"POST", "PATCH"} and "/catalog/datasets" in pair[1])
    )
    assert len(named_classes) < len(live), (
        "the old sentence's three classes would cover the whole set, so "
        "'broader than' would be false"
    )
    assert any(method == "GET" for method, _ in live), (
        "the sentence says the population includes governed reads"
    )


def test_the_counted_clause_is_the_tally() -> None:
    """Named-but-not-counted and counted-but-not-named were 4 and 6."""
    named = _counted_clause()
    assert named == list(REQUIRED_METADATA_FIELDS), (
        f"named but not counted: {[f for f in named if f not in REQUIRED_METADATA_FIELDS]}; "
        f"counted but not named: {[f for f in REQUIRED_METADATA_FIELDS if f not in named]}"
    )
    assert f"all {len(REQUIRED_METADATA_FIELDS)} required fields" in (
        metadata_completeness_definition()
    )


@pytest.mark.parametrize(
    "field", sorted(RECOMMENDATION_SCORED_FIELDS + UNSCORED_DISPLAY_FIELDS)
)
def test_an_uncounted_field_is_absent_from_the_tally(field: str) -> None:
    """A field in both clauses would make the sentence contradict itself."""
    assert field not in REQUIRED_METADATA_FIELDS
    assert field in metadata_completeness_definition()


@pytest.mark.parametrize("field", sorted(RECOMMENDATION_SCORED_FIELDS))
def test_a_recommendation_scored_field_moves_that_score_and_not_this_one(
    field: str,
) -> None:
    """"...which recommended_score scores instead" is a measurement, not a hope."""
    low, high = PROBE_RANGE[field]
    without = Dataset(**{**COMPLETE_DATASET, field: low})
    with_it = Dataset(**{**COMPLETE_DATASET, field: high})
    assert without.metadata_completeness == with_it.metadata_completeness
    assert without.metadata_recommendation_score < with_it.metadata_recommendation_score


@pytest.mark.parametrize("field", sorted(UNSCORED_DISPLAY_FIELDS))
def test_an_unscored_field_moves_neither_score(field: str) -> None:
    """"...whose values neither score reads" - the half the first draft got wrong.

    These two are non-optional floats on ``Dataset``, so the
    ``<field> is not None`` tests in ``metadata_recommendation_score`` are
    tautologies: a dataset reporting the worst possible value scores the same
    point as one reporting the best. The repair for *that* is a product decision
    about whether a measured ``0.0`` is present, and is filed separately; what
    this pins is that the definition does not claim these are scored while they
    are not.
    """
    low, high = PROBE_RANGE[field]
    worst = Dataset(**{**COMPLETE_DATASET, field: low})
    best = Dataset(**{**COMPLETE_DATASET, field: high})
    assert worst.metadata_completeness == best.metadata_completeness
    assert worst.metadata_recommendation_score == best.metadata_recommendation_score
    assert Dataset.model_fields[field].is_required(), (
        f"{field} gained an absent state, so its recommendation entry is no "
        "longer a tautology - re-measure before trusting this classification"
    )


# Required fields this probe leaves empty, so the ratio is not 1.0 and the test
# cannot pass on a dataset where every denominator agrees trivially.
BLANKED_REQUIRED_FIELDS = {"domain": "", "schema": []}


def test_a_reader_following_the_definition_reproduces_the_published_number() -> None:
    """The property the whole sentence exists for, on a dataset that is not 1.0.

    Both sides are **derived**: the reader's ratio from the sentence's own
    counted clause, the expected ratio from ``REQUIRED_METADATA_FIELDS``, and
    the third value from the implementation. Nothing here is a transcribed
    number, which is what this test needed two passes to get right.

    The first version pinned ``0.8``. The second derived it as
    ``(len(tally) - len(blanked)) / len(tally)`` and **was still a gate against
    its own repair**: adding an eleventh required field that
    ``COMPLETE_DATASET`` does not set (measured with ``tags``) leaves three
    required fields empty rather than two, so the formula expected 9/11 while
    every real measure said 8/11, and a legitimate addition to the tally turned
    this guard red. Deriving the expectation by counting the probe's own fields
    is what removes the trap - the shape round 22 recorded when a pinned
    "measured limitation" blocked the repair it was measuring.

    Found by mutating in the legitimate repair rather than only the defects: a
    guard that claims not to block a fix has to be shown the fix.
    """
    incomplete = Dataset(**{**COMPLETE_DATASET, **BLANKED_REQUIRED_FIELDS})
    counted = _counted_clause()
    by_hand = sum(1 for field in counted if getattr(incomplete, field, None)) / len(
        counted
    )
    expected = sum(
        1 for field in REQUIRED_METADATA_FIELDS if getattr(incomplete, field, None)
    ) / len(REQUIRED_METADATA_FIELDS)
    assert expected < 1.0, "the probe must leave at least one required field empty"
    assert by_hand == incomplete.metadata_completeness
    assert by_hand == pytest.approx(expected), (by_hand, expected)
