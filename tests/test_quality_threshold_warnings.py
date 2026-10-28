"""LIN-004: a quality threshold violation must warn, with rule/observed/threshold.

Before ``sdp.quality_warnings`` the ingredients were all present and unused.
``quality_score``, ``freshness_score``, ``metadata_completeness`` and per-column
``nullable_ratio``/``distinct_ratio``/``quality_issues`` were carried, stored and
published - but no threshold was declared anywhere, so nothing could be
violated and no warning could exist. A number with no threshold is not a quality
signal.

What these tests hold in place:

* each rule actually fires - the seeded demo data is clean against every
  threshold, so a test that only reads the seed would pass against a rule set
  that never triggers;
* a boundary value does not fire, so a threshold means what it says;
* an input that cannot be compared reports ``unevaluated`` rather than passing -
  missing data must not read as a clean bill of health;
* every warning carries the three fields the acceptance criterion names;
* the discovery surface never publishes a column name or a per-column statistic
  through the quality field, which is the same boundary
  ``catalog.discovery_view`` enforces by withholding the schema and profile;
* the withheld count equals what the governed route actually shows, so a short
  list on the open surface cannot be mistaken for a clean dataset.
"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from sdp import quality_warnings as qw
from sdp.api import app
from sdp.catalog import discovery_view, get_dataset
from sdp_core.contracts import ColumnMetadata, Dataset

client = TestClient(app)

_DATASET = "crm-customer-master"


def _dataset(**overrides) -> Dataset:
    """A valid dataset with every quality input at a passing value by default."""
    base = dict(
        id="quality-fixture",
        tenant_id="demo",
        title="품질 픽스처",
        description="threshold 검증용",
        owner="owner@example.org",
        steward="steward@example.org",
        domain="customer",
        source_system="postgresql://analytics.dw:5432/crm",
        sensitivity="internal",
        update_frequency="daily",
        quality_score=0.95,
        freshness_score=0.95,
        tags=["fixture"],
        terms=["고객"],
        schema=[
            ColumnMetadata(
                name="customer_id",
                datatype="string",
                nullable_ratio=0.0,
                distinct_ratio=1.0,
            )
        ],
        distributions=[],
    )
    base.update(overrides)
    return Dataset(**base)


def _column(**overrides) -> ColumnMetadata:
    """A column at passing values by default."""
    base = dict(
        name="probe_column", datatype="string", nullable_ratio=0.0, distinct_ratio=1.0
    )
    base.update(overrides)
    return ColumnMetadata(**base)


def _rules_by_id() -> dict[str, qw.QualityRule]:
    """The declared rules, keyed by id."""
    return {rule.rule_id: rule for rule in qw.QUALITY_RULES}


def test_the_seeded_demo_data_is_clean_against_every_threshold() -> None:
    """States the baseline the tests below depend on being non-trivial."""
    for dataset_id in ("crm-customer-master", "crm-event", "sales-order"):
        dataset = get_dataset(dataset_id)
        assert dataset is not None
        summary = qw.quality_warning_summary(dataset, include_column_scope=True)
        assert summary["warning_count"] == 0, (dataset_id, summary["warnings"])


def test_every_declared_rule_fires_on_a_violating_dataset() -> None:
    """A rule that never triggers is not a rule. One fixture per rule."""
    violations = {
        "quality_score_below_threshold": _dataset(quality_score=0.10),
        "freshness_score_below_threshold": _dataset(freshness_score=0.10),
        # Dropping a required field drives metadata_completeness below 0.90.
        "metadata_completeness_below_threshold": _dataset(owner="", steward=""),
        "column_null_ratio_above_threshold": _dataset(
            schema=[_column(nullable_ratio=0.94)]
        ),
        "column_distinct_ratio_below_threshold": _dataset(
            schema=[_column(distinct_ratio=0.0)]
        ),
        "column_declares_quality_issue": _dataset(
            schema=[_column(quality_issues=["stale ingest"])]
        ),
    }
    assert set(violations) == set(_rules_by_id()), (
        "a declared rule has no fixture proving it fires: "
        f"{sorted(set(_rules_by_id()) - set(violations))}"
    )
    for rule_id, dataset in violations.items():
        summary = qw.quality_warning_summary(dataset, include_column_scope=True)
        fired = [row["rule"] for row in summary["warnings"]]
        assert rule_id in fired, (rule_id, summary["warnings"])


def test_every_warning_carries_rule_observed_value_and_threshold() -> None:
    """The acceptance criterion names exactly these three."""
    dataset = _dataset(
        quality_score=0.10,
        freshness_score=0.10,
        owner="",
        schema=[_column(nullable_ratio=0.94, quality_issues=["stale ingest"])],
    )
    summary = qw.quality_warning_summary(dataset, include_column_scope=True)
    assert summary["warning_count"] >= 4
    for row in summary["warnings"]:
        assert row["rule"]
        assert row["evaluated"] is True, row
        assert "observed_value" in row, row
        assert "threshold" in row, row
        assert row["message"], row
        # A column rule must name its column; a dataset rule must not.
        if row["scope"] == qw.COLUMN_SCOPE:
            assert row["column"], row
        else:
            assert "column" not in row, row


def test_a_value_exactly_at_the_threshold_does_not_warn() -> None:
    """A threshold that fires at its own value is a different threshold.

    ``semantic-glossary.broader_concept`` sits at exactly the null-ratio
    threshold in the seed, so this boundary is live data, not a hypothetical.
    """
    at_ceiling = _dataset(
        schema=[_column(nullable_ratio=qw.COLUMN_NULL_RATIO_THRESHOLD)]
    )
    fired = [
        row["rule"]
        for row in qw.quality_warning_summary(at_ceiling, include_column_scope=True)[
            "warnings"
        ]
    ]
    assert "column_null_ratio_above_threshold" not in fired

    at_floor = _dataset(quality_score=qw.QUALITY_SCORE_THRESHOLD)
    fired = [
        row["rule"]
        for row in qw.quality_warning_summary(at_floor, include_column_scope=True)[
            "warnings"
        ]
    ]
    assert "quality_score_below_threshold" not in fired

    # Just past it, in each direction, does fire - so the test above is not
    # passing because the rule is dead.
    just_over = _dataset(
        schema=[_column(nullable_ratio=qw.COLUMN_NULL_RATIO_THRESHOLD + 0.001)]
    )
    fired = [
        row["rule"]
        for row in qw.quality_warning_summary(just_over, include_column_scope=True)[
            "warnings"
        ]
    ]
    assert "column_null_ratio_above_threshold" in fired


def test_an_input_that_cannot_be_compared_is_unevaluated_not_passing() -> None:
    """Missing data may not read as a clean bill of health."""
    rule = _rules_by_id()["quality_score_below_threshold"]
    for observed, reason in (
        (None, "field is absent"),
        ("0.1", "field is not a number"),
        # bool is an int subclass: True must not compare as 1.0.
        (True, "field is not a number"),
        (float("nan"), "field is not a number"),
        (float("inf"), "field is not a number"),
    ):
        row = qw._violation(rule, observed)
        assert row is not None, observed
        assert row["evaluated"] is False, (observed, row)
        assert row["unevaluated_reason"] == reason, (observed, row)
        assert "observed_value" not in row, row

    issue_rule = _rules_by_id()["column_declares_quality_issue"]
    assert qw._violation(issue_rule, None)["unevaluated_reason"] == "field is absent"
    assert (
        qw._violation(issue_rule, "stale")["unevaluated_reason"]
        == "field is not a list"
    )
    # An empty list is a real pass, not an unevaluated rule.
    assert qw._violation(issue_rule, []) is None


def test_a_rule_with_no_threshold_reports_itself_instead_of_raising() -> None:
    """``assert`` is stripped under ``-O``; a misdeclared rule must not 500.

    Every comparison but ``non_empty`` declares a threshold, so this is an
    internal invariant - but it was an ``assert``, and with assertions stripped
    a ``None`` threshold would have reached ``numeric < None`` and raised
    TypeError inside a published read.
    """
    misdeclared = qw.QualityRule(
        rule_id="misdeclared_rule",
        scope=qw.DATASET_SCOPE,
        field="quality_score",
        comparison="below",
        threshold=None,
        severity="warning",
        message="should never be reached",
    )
    row = qw._violation(misdeclared, 0.5)
    assert row is not None
    assert row["evaluated"] is False
    assert row["unevaluated_reason"] == (
        "rule declares no threshold to compare against"
    )
    assert "observed_value" not in row
    # And no shipped rule is in that state.
    for rule in qw.QUALITY_RULES:
        if rule.comparison == "non_empty":
            assert rule.threshold is None, rule.rule_id
        else:
            assert rule.threshold is not None, rule.rule_id


def test_an_unevaluated_rule_is_counted_rather_than_hidden() -> None:
    """``unevaluated_rule_count`` must reflect the rows it describes."""
    rule = _rules_by_id()["quality_score_below_threshold"]
    unevaluated = qw._violation(rule, None)
    summary = {
        "warnings": [unevaluated],
        "unevaluated_rule_count": sum(
            1 for row in [unevaluated] if not row.get("evaluated", True)
        ),
    }
    assert summary["unevaluated_rule_count"] == 1
    # And on the real path, where every seeded input is comparable, it is zero.
    dataset = get_dataset(_DATASET)
    assert dataset is not None
    assert (
        qw.quality_warning_summary(dataset, include_column_scope=True)[
            "unevaluated_rule_count"
        ]
        == 0
    )


def test_the_discovery_surface_withholds_column_scope_warnings() -> None:
    """A column warning names a column; the open surface may not publish one."""
    dataset = _dataset(
        schema=[
            _column(name="customer_ssn", nullable_ratio=0.94),
            _column(name="dead_default", distinct_ratio=0.0),
        ]
    )
    open_summary = qw.quality_warning_summary(dataset, include_column_scope=False)
    governed = qw.quality_warning_summary(dataset, include_column_scope=True)

    assert all(row["scope"] == qw.DATASET_SCOPE for row in open_summary["warnings"])
    serialized = json.dumps(open_summary, ensure_ascii=False)
    for leaked in ("customer_ssn", "dead_default", "nullable_ratio", "distinct_ratio"):
        assert leaked not in serialized, f"{leaked!r} crossed the discovery boundary"

    # The count is declared, and it is the real one.
    column_warnings = [
        row for row in governed["warnings"] if row["scope"] == qw.COLUMN_SCOPE
    ]
    assert column_warnings, "the fixture must produce column warnings to compare"
    assert open_summary["withheld_quality_warning_count"] == len(column_warnings)
    assert open_summary["withheld_scope"] == qw.COLUMN_SCOPE
    assert open_summary["withheld_reason"]


def test_rules_evaluated_names_only_what_ran_for_this_caller() -> None:
    """Listing the column rules on the open surface would claim they ran."""
    dataset = get_dataset(_DATASET)
    assert dataset is not None
    open_ids = qw.quality_warning_summary(dataset, include_column_scope=False)[
        "rules_evaluated"
    ]
    governed_ids = qw.quality_warning_summary(dataset, include_column_scope=True)[
        "rules_evaluated"
    ]
    dataset_scope = [
        rule.rule_id for rule in qw.QUALITY_RULES if rule.scope == qw.DATASET_SCOPE
    ]
    assert open_ids == dataset_scope
    assert governed_ids == [rule.rule_id for rule in qw.QUALITY_RULES]
    assert set(open_ids) < set(governed_ids)


def test_the_metadata_completeness_threshold_is_single_sourced() -> None:
    """Two copies of a threshold drift, and then a dataset is a pass and a gap.

    ``enterprise_evidence`` compares the mean completeness to 0.90 for the
    saleability gate; this rule must use the same figure.
    """
    source = (
        __import__("pathlib")
        .Path("src/sdp/enterprise_evidence.py")
        .read_text(encoding="utf-8")
    )
    assert (
        f'_mean_metadata_completeness() >= {qw.METADATA_COMPLETENESS_THRESHOLD}'
        in source
    ), (
        "the saleability gate no longer compares against "
        f"{qw.METADATA_COMPLETENESS_THRESHOLD}; the warning threshold and the "
        "gate must not disagree about what 'complete' means"
    )


def test_the_dataset_detail_route_publishes_the_warning_block() -> None:
    """LIN-004 asks for the warning on the dataset detail."""
    response = client.get(f"/catalog/datasets/{_DATASET}", params={"user": "analyst"})
    assert response.status_code == 200
    block = response.json()["quality_warnings"]
    assert block["warning_count"] == 0
    assert block["threshold_source"] == "product_default"
    assert "withheld_quality_warning_count" in block
    assert block["rules_evaluated"] == [
        rule.rule_id for rule in qw.QUALITY_RULES if rule.scope == qw.DATASET_SCOPE
    ]


def test_the_governed_schema_route_publishes_the_full_set() -> None:
    """Behind the policy gate, column-scope warnings are released."""
    response = client.get(
        f"/browse/{_DATASET}/schema", params={"user": "analyst", "purpose": "analysis"}
    )
    assert response.status_code == 200
    block = response.json()["quality_warnings"]
    assert block["rules_evaluated"] == [rule.rule_id for rule in qw.QUALITY_RULES]
    # The governed route releases content, so it declares no withholding.
    assert "withheld_quality_warning_count" not in block


def test_the_warning_block_travels_with_every_discovery_projection() -> None:
    """``discovery_view`` is the one projection; list and detail both use it."""
    dataset = get_dataset(_DATASET)
    assert dataset is not None
    projected = discovery_view(dataset)
    assert "quality_warnings" in projected
    listed = client.get("/catalog/datasets", params={"user": "analyst"})
    assert listed.status_code == 200
    assert all("quality_warnings" in item for item in listed.json())


def test_a_governed_dataset_field_did_not_arrive_through_the_quality_block() -> None:
    """The quality field must not become a bypass for the withheld fields."""
    dataset = get_dataset(_DATASET)
    assert dataset is not None
    # ``default=str`` because a distribution's endpoint is an ``HttpUrl``; it is
    # a published field, so rendering it is correct here.
    serialized = json.dumps(discovery_view(dataset), ensure_ascii=False, default=str)
    # ``source_system`` carries the connection string; ``profile`` the row count.
    assert "analytics.dw" not in serialized
    assert "row_count" not in serialized
