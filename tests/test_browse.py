"""Browse-path security tests: input validation, policy-deny, and usable PII.

``browse.preview``/``browse.schema`` are the policy-gated data-access surface.
These pin deny/validation branches (bad pagination, missing dataset, policy
denial) and assert that an authorized steward still sees original PII values.
Masking is not applied here; Keyverse fail-closed authorization plus GRC audit
are the controls. Every call records an audit event and a policy decision, so
the in-memory catalog/audit/evidence stores are snapshot/restored for isolation.
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
        browse.preview(
            "crm-customer-master", user="admin", purpose="analysis", limit=limit, offset=offset
        )


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


def test_preview_keeps_pii_for_authorized_steward() -> None:
    """Authorized preview keeps original emails; catalog plane does not mask."""
    base = catalog._DATA["crm-customer-master"]
    schema = [c.model_copy(update={"pii": (c.name == "customer_email")}) for c in base.schema]
    assert any(c.name == "customer_email" for c in schema), (
        "fixture must include customer_email to exercise authorized preview PII"
    )
    catalog._DATA["crm-customer-master"] = base.model_copy(update={"schema": schema})
    result = browse.preview("crm-customer-master", user="admin", purpose="analysis", limit=2)
    assert result["masking_summary"]["masking_applied"] is False
    assert result["masking_summary"]["masked_columns"] == []
    assert result["masking_summary"]["grc_redaction_obligated_columns"] == ["customer_email"]
    emails = {row["customer_email"] for row in result["rows"]}
    assert emails == {"alice@example.com", "bob@example.com"}
    assert "***" not in emails
    schema_result = browse.schema("crm-customer-master", user="admin", purpose="analysis")
    assert schema_result["masked_columns"] == []
    assert schema_result["grc_redaction_obligated_columns"] == ["customer_email"]

    preview_event = next(
        event
        for event in reversed(catalog._AUDIT_LOG)
        if event.action == "browse.preview" and event.result == "allowed"
    )
    assert preview_event.details["masking_applied"] is False
    assert preview_event.details["grc_redaction_obligated_columns"] == ["customer_email"]
    assert preview_event.details["policy_decision_id"] == result["policy_decision_id"]


def test_apply_mask_never_redacts() -> None:
    """apply_mask is a compatibility no-op and must not replace steward PII."""
    row = {"customer_email": "alice@example.com", "customer_id": "C-1001"}
    assert browse.apply_mask(row, ["customer_email"]) == {
        "customer_email": "alice@example.com",
        "customer_id": "C-1001",
    }
