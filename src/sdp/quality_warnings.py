"""Quality thresholds, and the warnings a dataset's own numbers produce.

LIN-004 (P1) requires a warning on a dataset's detail when a quality threshold
is violated, and names what the warning must carry: **rule, observed value,
threshold**. Before this module the ingredients were all present and unused -
``quality_score``, ``freshness_score``, ``metadata_completeness``, per-column
``nullable_ratio``/``distinct_ratio``/``quality_issues`` were carried, stored and
published - but no threshold was declared anywhere, so nothing could be
violated. A number with no threshold is not a quality signal; it is a number.

Three properties this implementation holds to.

**A rule that cannot be evaluated does not pass.** If the input a rule reads is
absent or not a number, the rule reports ``unevaluated`` with the reason, and is
counted. Silently treating an absent input as "within threshold" would turn
missing data into a clean bill of health, which is the opposite of what a
quality surface is for.

**A warning never crosses the discovery boundary.** ``catalog.discovery_view``
withholds the per-column schema and the ``profile`` from the actor-less
discovery surface, publishing ``schema_field_count`` in their place - so a
warning saying "column ``ssn`` is 94% null" would route exactly that withheld
per-column statistic through the quality field instead. Rules are therefore
scoped: ``dataset`` rules read fields discovery already publishes and appear
there; ``column`` rules read withheld fields and appear only behind the policy
gate, with the discovery surface reporting
``withheld_quality_warning_count`` so a short list cannot read as a clean one.

**Thresholds are one list.** ``metadata_completeness`` reuses the 0.90 figure
the saleability gate already compares against rather than restating it, for the
same reason ``REQUIRED_METADATA_FIELDS`` is single-sourced: two copies of a
threshold drift, and then a dataset is simultaneously a pass and a gap.

The thresholds are product-wide defaults, not per-tenant or per-domain
configuration. LIN-004 does not ask for configurability and nothing here
pretends to offer it; ``threshold_source`` says so on every warning.
"""

from __future__ import annotations

from typing import Any

from sdp_core.contracts import Dataset

# The share of required metadata the saleability gate in ``enterprise_evidence``
# already compares against. Imported there rather than restated, so the catalog
# warning and the gate cannot disagree about what "complete" means.
METADATA_COMPLETENESS_THRESHOLD = 0.90

# Below this, the dataset's own declared quality score is low enough that a
# consumer should see it next to the number rather than have to compare it to a
# figure published nowhere.
QUALITY_SCORE_THRESHOLD = 0.80

# Freshness is scored on the same 0..1 scale and tolerated lower: a monthly
# dataset is legitimately less fresh than a streaming one, and nothing here
# knows the update cadence well enough to grade per cadence.
FRESHNESS_SCORE_THRESHOLD = 0.70

# A column this empty is a join hazard and a masking hazard.
COLUMN_NULL_RATIO_THRESHOLD = 0.20

# A column with almost no distinct values carries almost no information; it is
# usually a dead default or a broken ingest.
COLUMN_DISTINCT_RATIO_THRESHOLD = 0.01

THRESHOLD_SOURCE = "product_default"

DATASET_SCOPE = "dataset"
COLUMN_SCOPE = "column"


class QualityRule:
    """One threshold rule: what it reads, how it compares, and against what."""

    def __init__(
        self,
        *,
        rule_id: str,
        scope: str,
        field: str,
        comparison: str,
        threshold: float | None,
        severity: str,
        message: str,
    ) -> None:
        """Declare a rule; ``threshold`` is ``None`` for a presence comparison."""
        self.rule_id = rule_id
        self.scope = scope
        self.field = field
        self.comparison = comparison
        self.threshold = threshold
        self.severity = severity
        self.message = message


QUALITY_RULES: tuple[QualityRule, ...] = (
    QualityRule(
        rule_id="quality_score_below_threshold",
        scope=DATASET_SCOPE,
        field="quality_score",
        comparison="below",
        threshold=QUALITY_SCORE_THRESHOLD,
        severity="warning",
        message="declared quality score is below the product threshold",
    ),
    QualityRule(
        rule_id="freshness_score_below_threshold",
        scope=DATASET_SCOPE,
        field="freshness_score",
        comparison="below",
        threshold=FRESHNESS_SCORE_THRESHOLD,
        severity="warning",
        message="declared freshness score is below the product threshold",
    ),
    QualityRule(
        rule_id="metadata_completeness_below_threshold",
        scope=DATASET_SCOPE,
        field="metadata_completeness",
        comparison="below",
        threshold=METADATA_COMPLETENESS_THRESHOLD,
        severity="warning",
        message="required metadata is incomplete",
    ),
    QualityRule(
        rule_id="column_null_ratio_above_threshold",
        scope=COLUMN_SCOPE,
        field="nullable_ratio",
        comparison="above",
        threshold=COLUMN_NULL_RATIO_THRESHOLD,
        severity="warning",
        message="column is null more often than the product threshold allows",
    ),
    QualityRule(
        rule_id="column_distinct_ratio_below_threshold",
        scope=COLUMN_SCOPE,
        field="distinct_ratio",
        comparison="below",
        threshold=COLUMN_DISTINCT_RATIO_THRESHOLD,
        severity="warning",
        message="column carries almost no distinct values",
    ),
    QualityRule(
        rule_id="column_declares_quality_issue",
        scope=COLUMN_SCOPE,
        field="quality_issues",
        comparison="non_empty",
        threshold=None,
        severity="warning",
        message="column declares a quality issue",
    ),
)


def _numeric(value: Any) -> float | None:
    """``value`` as a float when it is a real number, else ``None``.

    ``bool`` is rejected explicitly: it is an ``int`` subclass, so ``True``
    would otherwise compare as ``1.0`` and a boolean field would silently
    satisfy a numeric threshold.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    numeric = float(value)
    if numeric != numeric or numeric in (float("inf"), float("-inf")):
        return None
    return numeric


def _violation(rule: QualityRule, observed: Any) -> dict[str, Any] | None:
    """The warning this rule produces for an observed value, or ``None``.

    Returns an ``unevaluated`` row rather than ``None`` when the input cannot be
    compared, so an absent input is visible instead of reading as a pass.
    """
    base = {
        "rule": rule.rule_id,
        "scope": rule.scope,
        "field": rule.field,
        "comparison": rule.comparison,
        "threshold": rule.threshold,
        "threshold_source": THRESHOLD_SOURCE,
        "severity": rule.severity,
    }
    if rule.comparison == "non_empty":
        if observed is None:
            return {**base, "evaluated": False, "unevaluated_reason": "field is absent"}
        if not isinstance(observed, (list, tuple)):
            return {
                **base,
                "evaluated": False,
                "unevaluated_reason": "field is not a list",
            }
        if not observed:
            return None
        return {
            **base,
            "evaluated": True,
            "observed_value": list(observed),
            "message": rule.message,
        }

    numeric = _numeric(observed)
    if numeric is None:
        return {
            **base,
            "evaluated": False,
            "unevaluated_reason": (
                "field is absent" if observed is None else "field is not a number"
            ),
        }
    if rule.threshold is None:
        # Every comparison but ``non_empty`` declares a threshold, so this is an
        # internal invariant - but it is checked rather than asserted: ``assert``
        # is stripped under ``-O``, and a ``None`` threshold would then reach
        # ``numeric < None`` and raise TypeError inside a published read. A
        # misdeclared rule reports itself instead.
        return {
            **base,
            "evaluated": False,
            "unevaluated_reason": "rule declares no threshold to compare against",
        }
    violated = (
        numeric < rule.threshold
        if rule.comparison == "below"
        else numeric > rule.threshold
    )
    if not violated:
        return None
    return {
        **base,
        "evaluated": True,
        "observed_value": round(numeric, 6),
        "message": rule.message,
    }


def dataset_quality_warnings(dataset: Dataset) -> list[dict[str, Any]]:
    """Warnings from the dataset-level fields discovery already publishes."""
    observed = {
        "quality_score": dataset.quality_score,
        "freshness_score": dataset.freshness_score,
        "metadata_completeness": dataset.metadata_completeness,
    }
    warnings: list[dict[str, Any]] = []
    for rule in QUALITY_RULES:
        if rule.scope != DATASET_SCOPE:
            continue
        row = _violation(rule, observed.get(rule.field))
        if row is not None:
            warnings.append(row)
    return warnings


def column_quality_warnings(dataset: Dataset) -> list[dict[str, Any]]:
    """Warnings from per-column statistics the discovery surface withholds.

    Published only behind the policy gate. Each row names its column, which is
    the point of a column rule and also why it may not appear on an actor-less
    surface.
    """
    warnings: list[dict[str, Any]] = []
    for column in dataset.schema or []:
        values = column.model_dump()
        for rule in QUALITY_RULES:
            if rule.scope != COLUMN_SCOPE:
                continue
            row = _violation(rule, values.get(rule.field))
            if row is not None:
                warnings.append({**row, "column": column.name})
    return warnings


def quality_warning_summary(
    dataset: Dataset, *, include_column_scope: bool
) -> dict[str, Any]:
    """Every warning this caller may see, plus what was withheld from them.

    ``include_column_scope`` is the policy decision, taken by the caller: the
    governed schema route passes ``True`` because it is already publishing the
    per-column statistics these rules read; ``discovery_view`` passes ``False``
    and gets the count instead, so an empty list cannot be mistaken for a clean
    dataset.
    """
    dataset_scope = dataset_quality_warnings(dataset)
    column_scope = column_quality_warnings(dataset)
    warnings = (
        dataset_scope + column_scope if include_column_scope else dataset_scope
    )
    scopes = (
        {DATASET_SCOPE, COLUMN_SCOPE} if include_column_scope else {DATASET_SCOPE}
    )
    summary: dict[str, Any] = {
        "warnings": warnings,
        "warning_count": len(warnings),
        "unevaluated_rule_count": sum(
            1 for row in warnings if not row.get("evaluated", True)
        ),
        # The rules evaluated *for this caller*. Listing all six on the
        # discovery surface would claim the column rules ran there, which is
        # exactly what ``include_column_scope=False`` prevented.
        "rules_evaluated": [
            rule.rule_id for rule in QUALITY_RULES if rule.scope in scopes
        ],
        "threshold_source": THRESHOLD_SOURCE,
    }
    if not include_column_scope:
        # Declared, not dropped: the same pattern as ``schema_field_count`` and
        # ``withheld_report_count`` elsewhere in this product.
        summary["withheld_quality_warning_count"] = len(column_scope)
        summary["withheld_scope"] = COLUMN_SCOPE
        summary["withheld_reason"] = (
            "column-scope warnings name a column and read per-column statistics "
            "the discovery surface withholds; read them through "
            "GET /browse/{dataset_id}/schema"
        )
    return summary
