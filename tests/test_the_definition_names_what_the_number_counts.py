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
)

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


def test_the_published_definition_is_the_derived_one() -> None:
    """The framework must publish this sentence, not a second copy of it."""
    framework = enterprise_kpi_framework()
    kpi = next(
        item
        for item in framework.primary_kpis + framework.guardrail_kpis
        if item.id == "metadata_completeness"
    )
    assert kpi.definition == metadata_completeness_definition()


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
