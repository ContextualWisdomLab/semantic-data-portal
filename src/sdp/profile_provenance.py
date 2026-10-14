"""Where a published profile metric came from, and when it was measured.

LIN-003 (P0) requires the quality profile to carry null ratio, distinct count,
freshness and duplicate ratio, and its acceptance criterion requires the
**metric timestamp and the computation scope** to be shown. The profile route
published the numbers and neither of those, which made a declaration read as a
measurement. Measured on the seeded catalog before this module::

    GET /catalog/datasets/crm-customer-master/profile
      -> row_count: 1200000
         schema_profile[1]: {null_ratio: 0.01, distinct_ratio: 0.99}

Nothing in this service computed any of those figures. They are fixture values
(``demo_seed.py``: ``profile={"row_count": 1200000, ...}``) or, for a
caller-registered dataset, whatever the caller put in the request body. There is
no profiler here: no code reads a source system's rows, so no null ratio can be
counted. A buyer reading "1,200,000 rows, 1% null" on an evidence surface was
reading a claim about their data that this product never made.

So the numbers stay - they are the source's own declaration and that is useful -
and they now travel with the provenance that says what they are:

``computed_by_this_service: false``
    No profiler exists in this codebase. This is the field that turns the rest
    of the block from decoration into a disclosure.
``measurement_status: "declared_by_source"``
    The same vocabulary ``orchestrator`` already uses for its own un-executed
    figures (``mock_execution_no_real_data``).
``computation_scope``
    What the figure covers. For a declared value the honest answer is that the
    scope is the source's, unknown here - not "full table", which would be a
    scope this service cannot vouch for.
``metric_timestamp`` / ``metric_timestamp_available``
    The declared measurement time when the profile carries one, and ``null``
    with the availability flag ``false`` when it does not. **Never** ``now()``:
    stamping a read time onto a figure measured at an unknown time is the one
    move here that would actively mislead, since it would make a stale
    declaration look fresh on every request.

``declared_unavailable_metrics`` names the metrics LIN-003 requires that this
product does not have, with the reason, rather than omitting them. Two are
listed. ``duplicate_ratio`` is not computed anywhere and cannot be without a
profiler. ``distinct_count`` is deliberately *not* derived from
``distinct_ratio * row_count``: multiplying two declared values would
manufacture a measurement that neither input supports, which is exactly the
drift this product exists to refuse.
"""

from __future__ import annotations

from typing import Any

# No code in this repository reads a source system's rows, so no profile metric
# is computed here. A profiler landing later flips this one constant and the
# tests that pin the published block will say so.
PROFILE_COMPUTED_BY_THIS_SERVICE = False

MEASUREMENT_STATUS_DECLARED = "declared_by_source"

COMPUTATION_SCOPE_DECLARED = "source_declared_scope_unknown_to_this_service"

PROVENANCE_NOTE = (
    "Profile figures are declared by the source system or by the caller that "
    "registered the dataset; this service runs no profiler and recomputes "
    "nothing. Treat them as the source's claim, not as a measurement taken "
    "here."
)

# Metrics LIN-003 names that this product does not carry, named rather than
# omitted so a short profile cannot read as a complete one.
DECLARED_UNAVAILABLE_METRICS: tuple[dict[str, str], ...] = (
    {
        "metric": "duplicate_ratio",
        "required_by": "LIN-003",
        "reason": (
            "nothing computes it; a duplicate ratio needs a pass over the "
            "source's rows and this service never reads them"
        ),
    },
    {
        "metric": "distinct_count",
        "required_by": "LIN-003",
        "reason": (
            "distinct_ratio is published instead. A count is not derived from "
            "distinct_ratio * row_count: both inputs are declarations, and "
            "multiplying them would manufacture a measurement neither supports"
        ),
    },
)


def _declared_timestamp(profile: dict[str, Any]) -> str | None:
    """The profile's own declared measurement time, when it carries a usable one.

    A non-string value is treated as absent rather than coerced: ``profile`` is
    a free-form dict a caller can put anything in, and ``str()`` of an
    arbitrary object published as a timestamp is worse than saying there is
    none.
    """
    declared = profile.get("updated_at")
    if isinstance(declared, str) and declared.strip():
        return declared
    return None


def profile_metric_provenance(profile: dict[str, Any]) -> dict[str, Any]:
    """The provenance block published beside a dataset's profile figures."""
    declared = _declared_timestamp(profile)
    return {
        "computed_by_this_service": PROFILE_COMPUTED_BY_THIS_SERVICE,
        "measurement_status": MEASUREMENT_STATUS_DECLARED,
        "computation_scope": COMPUTATION_SCOPE_DECLARED,
        # Never ``now()``: see this module's docstring.
        "metric_timestamp": declared,
        "metric_timestamp_available": declared is not None,
        "note": PROVENANCE_NOTE,
    }


def declared_unavailable_metrics() -> list[dict[str, str]]:
    """The LIN-003 metrics this product does not have, with reasons."""
    return [dict(entry) for entry in DECLARED_UNAVAILABLE_METRICS]
