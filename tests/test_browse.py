"""Browse-path security tests: input validation, policy-deny propagation, and
PII masking.

``browse.preview``/``browse.schema`` are the policy-gated data-access surface;
these pin the deny/validation branches (bad pagination, missing dataset, policy
denial) and assert that PII columns obligated by policy are masked to ``***``.
Every call records an audit event and a policy decision, so the in-memory
catalog/audit/evidence stores are snapshot/restored for isolation.
"""

from __future__ import annotations

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sdp import browse, catalog, evidence  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate_state():
    """Snapshot/restore module-level catalog data, audit log, and policy decisions."""
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


@pytest.mark.parametrize(
    "limit,offset",
    [(0, 0), (101, 0), (1, -1)],
)
def test_preview_rejects_out_of_range_pagination(limit: int, offset: int) -> None:
    """preview enforces 1<=limit<=100 and offset>=0 before any data access."""
    with pytest.raises(ValueError):
        browse.preview("crm-customer-master", user="admin", purpose="analysis", limit=limit, offset=offset)


def test_preview_denied_raises_permission_error() -> None:
    """A cross-tenant subject is denied preview (policy deny -> PermissionError)."""
    with pytest.raises(PermissionError):
        browse.preview("crm-customer-master", user="external-analyst", purpose="analysis")


def test_schema_missing_dataset_raises_keyerror() -> None:
    """schema on an unknown dataset raises KeyError (mapped to 404 at the route)."""
    with pytest.raises(KeyError):
        browse.schema("__no_such_dataset__", user="admin")


def test_schema_denied_raises_permission_error() -> None:
    """schema denial (cross-tenant) records an audit event and raises PermissionError."""
    before = len(catalog._AUDIT_LOG)
    with pytest.raises(PermissionError):
        browse.schema("crm-customer-master", user="external-analyst", purpose="analysis")
    assert len(catalog._AUDIT_LOG) == before + 1  # the denial is audited


def test_preview_masks_pii_columns() -> None:
    """Any column policy obligates as masked is redacted to '***' in returned rows."""
    # Mark an email-bearing column PII so policy obligates masking for the preview rows.
    base = catalog._DATA["crm-customer-master"]
    schema = [c.model_copy(update={"pii": (c.name == "customer_email")}) for c in base.schema]
    assert any(c.name == "customer_email" for c in schema), (
        "fixture must include customer_email to exercise the preview masking integration"
    )
    catalog._DATA["crm-customer-master"] = base.model_copy(update={"schema": schema})
    result = browse.preview("crm-customer-master", user="admin", purpose="analysis", limit=2)
    assert "customer_email" in result["masking_summary"]["masked_columns"]
    assert all(row["customer_email"] == "***" for row in result["rows"])


def test_apply_mask_noop_without_masked_columns() -> None:
    """apply_mask returns the row unchanged when nothing is obligated masked."""
    row = {"a": "1", "b": "2"}
    assert browse.apply_mask(row, []) == {"a": "1", "b": "2"}
