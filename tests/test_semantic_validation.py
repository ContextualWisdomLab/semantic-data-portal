"""SHACL-compatible dataset semantic validation.

validate_dataset_semantics reports metadata/mapping/term violations that gate a
dataset's readiness. These pin the violation branches (missing required
metadata, no approved business mapping, no searchable terms) and the
missing-dataset guard.
"""

from __future__ import annotations

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sdp import catalog, evidence  # noqa: E402
from sdp.semantic_validation import validate_dataset_semantics  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate_state():
    data = {k: v.model_copy(deep=True) for k, v in catalog._DATA.items()}
    audit = list(catalog._AUDIT_LOG)
    decisions = list(evidence._POLICY_DECISION_LOG)
    try:
        yield
    finally:
        catalog._DATA.clear()
        catalog._DATA.update(data)
        catalog._AUDIT_LOG.clear()
        catalog._AUDIT_LOG.extend(audit)
        evidence._POLICY_DECISION_LOG.clear()
        evidence._POLICY_DECISION_LOG.extend(decisions)


def test_missing_dataset_raises_keyerror() -> None:
    with pytest.raises(KeyError):
        validate_dataset_semantics("__no_such_dataset__")


def test_incomplete_dataset_reports_all_violation_classes() -> None:
    """A dataset with cleared metadata, no approved mapping, and no terms trips
    every violation branch and does not conform."""
    base = catalog._DATA["crm-customer-master"]
    catalog._DATA["incomplete-ds"] = base.model_copy(
        update={"id": "incomplete-ds", "owner": "", "steward": "", "mappings": [], "terms": []}
    )
    report = validate_dataset_semantics("incomplete-ds")
    assert report["conforms"] is False
    shapes = {v["shape"] for v in report["violations"]}
    assert "DatasetShape" in shapes  # missing required metadata (owner/steward)
    assert "BusinessMappingShape" in shapes  # no approved mapping + no terms
    assert report["approved_mapping_count"] == 0
    # The terms shortfall is recorded as a warning, not a hard violation.
    assert any(v["path"] == "terms" and v["severity"] == "warning" for v in report["violations"])
