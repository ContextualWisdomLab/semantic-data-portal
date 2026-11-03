"""LIN-003: a profile figure must say when it was measured and over what scope.

The profile route published the numbers and neither of those, which made a
declaration read as a measurement. Measured on the seeded catalog before
``sdp.profile_provenance``::

    GET /catalog/datasets/crm-customer-master/profile
      -> row_count: 1200000
         schema_profile[1]: {null_ratio: 0.01, distinct_ratio: 0.99}

Nothing in this service computed any of it. Those are fixture values in
``demo_seed.py`` or, for a caller-registered dataset, whatever the caller put in
the request body; there is no profiler here, so no null ratio can be counted. A
buyer reading "1,200,000 rows, 1% null" on an evidence surface was reading a
claim about their data that this product never made.

The tests below hold the three things that keep the fix honest: the figures are
labelled as declarations rather than removed, the metric timestamp is never
fabricated from the read time, and the two LIN-003 metrics this product lacks
are named with reasons instead of omitted - including the one that could be
faked by arithmetic.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from sdp import profile_provenance as pp
from sdp.api import app
from sdp.catalog import get_dataset_profile

client = TestClient(app)

_DATASET = "crm-customer-master"


def test_the_profile_declares_it_computed_nothing() -> None:
    """The field that turns the block from decoration into a disclosure."""
    provenance = get_dataset_profile(_DATASET)["metric_provenance"]
    assert provenance["computed_by_this_service"] is False
    assert provenance["measurement_status"] == "declared_by_source"
    assert provenance["computation_scope"] == (
        "source_declared_scope_unknown_to_this_service"
    )
    assert "runs no profiler" in provenance["note"]


def test_no_profiler_exists_so_the_claim_is_true() -> None:
    """Guard the constant against becoming a lie if a profiler is added.

    ``PROFILE_COMPUTED_BY_THIS_SERVICE`` is the single place that claim lives.
    If someone writes a profiler and forgets this flag, the published block
    would under-claim; if someone flips the flag without writing one, it would
    over-claim. This test pins the flag to the fact that no profile metric is
    computed from source rows anywhere in the package.
    """
    assert pp.PROFILE_COMPUTED_BY_THIS_SERVICE is False, (
        "a profiler was added: update the provenance vocabulary and this test "
        "together, and say what scope it actually covers"
    )


def test_the_metric_timestamp_is_the_declared_one_not_the_read_time() -> None:
    """Stamping ``now()`` would make a stale declaration look fresh per request."""
    provenance = get_dataset_profile(_DATASET)["metric_provenance"]
    # The seeded declaration, verbatim.
    assert provenance["metric_timestamp"] == "2026-06-29T00:00:00Z"
    assert provenance["metric_timestamp_available"] is True
    # Twice in a row, unchanged: a read-time stamp would move.
    again = get_dataset_profile(_DATASET)["metric_provenance"]
    assert again["metric_timestamp"] == provenance["metric_timestamp"]


def test_an_absent_declaration_is_reported_absent_not_invented() -> None:
    """No timestamp means no timestamp."""
    provenance = pp.profile_metric_provenance({})
    assert provenance["metric_timestamp"] is None
    assert provenance["metric_timestamp_available"] is False


def test_an_unusable_declaration_is_treated_as_absent_not_coerced() -> None:
    """``profile`` is a free-form dict; ``str()`` of anything is not a timestamp."""
    for unusable in ({"updated_at": None}, {"updated_at": 1_750_000_000},
                     {"updated_at": ""}, {"updated_at": "   "},
                     {"updated_at": {"nested": "object"}},
                     {"updated_at": ["2026-06-29"]}):
        provenance = pp.profile_metric_provenance(unusable)
        assert provenance["metric_timestamp"] is None, unusable
        assert provenance["metric_timestamp_available"] is False, unusable


def test_the_metrics_lin_003_requires_but_this_product_lacks_are_named() -> None:
    """A short profile must not read as a complete one."""
    declared = get_dataset_profile(_DATASET)["declared_unavailable_metrics"]
    named = {entry["metric"] for entry in declared}
    assert named == {"duplicate_ratio", "distinct_count"}
    for entry in declared:
        assert entry["required_by"] == "LIN-003"
        assert entry["reason"], entry


def test_distinct_count_is_declared_unavailable_rather_than_multiplied() -> None:
    """The one metric here that could be faked by arithmetic.

    ``distinct_ratio * row_count`` would produce a plausible count from two
    declarations, supported by neither. The reason text has to say so, because
    "we don't have it" and "we refuse to derive it" are different claims and
    only the second is true.
    """
    declared = get_dataset_profile(_DATASET)["declared_unavailable_metrics"]
    reason = next(
        entry["reason"] for entry in declared if entry["metric"] == "distinct_count"
    )
    assert "distinct_ratio * row_count" in reason
    assert "manufacture" in reason
    # And no published field carries such a product.
    profile = get_dataset_profile(_DATASET)
    assert "distinct_count" not in profile
    for column in profile["schema_profile"]:
        assert "distinct_count" not in column


def test_the_declared_figures_are_kept_not_removed() -> None:
    """Labelling a declaration is the fix; deleting it would lose real signal."""
    profile = get_dataset_profile(_DATASET)
    assert profile["row_count"] == 1_200_000
    assert profile["profile_updated_at"] == "2026-06-29T00:00:00Z"
    assert [column["null_ratio"] for column in profile["schema_profile"]] == [
        0.0,
        0.01,
        0.0,
    ]
    assert [column["distinct_ratio"] for column in profile["schema_profile"]] == [
        1.0,
        0.99,
        0.88,
    ]


def test_the_unavailable_list_cannot_be_mutated_through_the_published_copy() -> None:
    """A caller editing the returned list must not change the declaration."""
    first = pp.declared_unavailable_metrics()
    first[0]["reason"] = "tampered"
    first.append({"metric": "injected", "required_by": "", "reason": ""})
    second = pp.declared_unavailable_metrics()
    assert "tampered" not in [entry["reason"] for entry in second]
    assert {entry["metric"] for entry in second} == {
        "duplicate_ratio",
        "distinct_count",
    }


def test_the_gated_profile_route_publishes_the_provenance() -> None:
    """The route a buyer actually reads, behind its policy gate."""
    response = client.get(
        f"/catalog/datasets/{_DATASET}/profile",
        params={"user": "analyst", "purpose": "analysis"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["metric_provenance"]["computed_by_this_service"] is False
    assert body["metric_provenance"]["metric_timestamp"] == "2026-06-29T00:00:00Z"
    assert {
        entry["metric"] for entry in body["declared_unavailable_metrics"]
    } == {"duplicate_ratio", "distinct_count"}


def test_the_provenance_does_not_reach_the_ungated_discovery_surface() -> None:
    """``profile`` is a governed field; its provenance block travels with it.

    Not a disclosure concern in itself - the block names no dataset content -
    but publishing it on discovery would imply a profile is readable there,
    which ``discovery_view`` deliberately withholds.
    """
    detail = client.get(
        f"/catalog/datasets/{_DATASET}", params={"user": "analyst"}
    ).json()
    assert "metric_provenance" not in detail
    assert "declared_unavailable_metrics" not in detail
    assert "profile" not in detail
