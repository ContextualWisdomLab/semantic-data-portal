"""GRC evidence-export redaction contract tests.

The catalog plane returns original PII to authorized stewards; the GRC
evidence export is where response minimization must happen. These tests pin
the obligation-based redaction gate in
``sdp.enterprise_evidence.redact_grc_obligated_payload`` and the redacted
``grc_audit_tail`` embedded by ``build_enterprise_evidence_pack``: obligated
columns are replaced, non-obligated fields survive, and raw steward PII never
leaves through the export.
"""

from __future__ import annotations

from pathlib import Path
import json
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sdp import browse, catalog  # noqa: E402
from sdp.enterprise_evidence import (  # noqa: E402
    GRC_OBLIGATION_KEY,
    GRC_REDACTED_VALUE,
    build_enterprise_evidence_pack,
    redact_grc_obligated_payload,
)


@pytest.fixture()
def _isolate_state():
    """Snapshot/restore module-level catalog data and audit log."""
    data = {k: v.model_copy(deep=True) for k, v in catalog._DATA.items()}
    audit = list(catalog._AUDIT_LOG)
    try:
        yield
    finally:
        catalog._DATA.clear()
        catalog._DATA.update(data)
        catalog._AUDIT_LOG[:] = audit


def _mark_customer_email_pii() -> None:
    """Flag customer_email as PII so preview records the GRC obligation."""
    base = catalog._DATA["crm-customer-master"]
    schema = [c.model_copy(update={"pii": (c.name == "customer_email")}) for c in base.schema]
    catalog._DATA["crm-customer-master"] = base.model_copy(update={"schema": schema})


def test_redacts_obligated_columns_and_preserves_rest() -> None:
    """Obligated scalar columns become GRC_REDACTED_VALUE; others pass through."""
    payload = {
        "actor": "steward-1",
        "customer_email": "alice@example.com",
        "customer_id": "C-1001",
        "details": {"purpose": "analysis", "customer_phone": "+82-10-0000-0000"},
        GRC_OBLIGATION_KEY: ["customer_email", "customer_phone"],
    }
    redacted, applied = redact_grc_obligated_payload(payload)
    assert applied == ["customer_email", "customer_phone"]
    assert redacted["customer_email"] == GRC_REDACTED_VALUE
    assert redacted["details"]["customer_phone"] == GRC_REDACTED_VALUE
    assert redacted["actor"] == "steward-1"
    assert redacted["customer_id"] == "C-1001"
    assert redacted["details"]["purpose"] == "analysis"


def test_no_obligations_returns_payload_unchanged() -> None:
    """A payload without obligations is exported verbatim (copy semantics)."""
    payload = {"actor": "steward-2", "details": {"note": "no pii here"}}
    redacted, applied = redact_grc_obligated_payload(payload)
    assert applied == []
    assert redacted == payload
    assert redacted is not payload


def test_declared_but_absent_columns_report_empty_application() -> None:
    """Declared obligations that never appear as keys are not counted applied."""
    payload = {GRC_OBLIGATION_KEY: ["ghost_column"], "actor": "steward-3"}
    redacted, applied = redact_grc_obligated_payload(payload)
    assert applied == []
    assert "ghost_column" not in redacted
    assert redacted["actor"] == "steward-3"


@pytest.mark.usefixtures("_isolate_state")
def test_export_tail_redacts_steward_pii_from_preview_events() -> None:
    """browse.preview PII never appears in the exported audit tail."""
    _mark_customer_email_pii()
    result = browse.preview("crm-customer-master", user="admin", purpose="analysis", limit=2)
    assert any("alice@example.com" in row["customer_email"] for row in result["rows"])

    # Simulate a future event type that embeds obligated row values: the export
    # gate must scrub the value wherever it appears, not only today's shapes.
    catalog.ingest_event(
        event_type="browse.row_snapshot",
        actor="admin",
        dataset_id="crm-customer-master",
        decision="allowed",
        details={
            "customer_email": "alice@example.com",
            GRC_OBLIGATION_KEY: ["customer_email"],
        },
    )

    pack = build_enterprise_evidence_pack()

    serialized = json.dumps(pack)
    assert "alice@example.com" not in serialized
    assert "bob@example.com" not in serialized
    assert GRC_REDACTED_VALUE in serialized

    preview_tail = [
        event
        for event in pack["grc_audit_tail"]
        if event["action"] == "browse.preview" and event["result"] == "allowed"
    ]
    assert preview_tail, "preview events must be embedded in the audited export tail"
    latest = preview_tail[-1]
    assert latest["details"]["masking_applied"] is False
    assert latest["details"]["grc_redaction_obligated_columns"] == ["customer_email"]

    redaction_meta = pack["grc_redaction"]
    assert redaction_meta["obligation_key"] == GRC_OBLIGATION_KEY
    assert redaction_meta["obligation_declared_event_count"] >= 2
    assert redaction_meta["redacted_event_count"] >= 1
    assert redaction_meta["redacted_column_count"] >= 1


@pytest.mark.usefixtures("_isolate_state")
def test_export_without_activity_reports_zero_redactions() -> None:
    """An idle portal exports an empty tail and zero redaction counters."""
    catalog._AUDIT_LOG.clear()
    pack = build_enterprise_evidence_pack()
    assert pack["grc_audit_tail"] == []
    assert pack["grc_redaction"]["obligation_declared_event_count"] == 0
    assert pack["grc_redaction"]["redacted_event_count"] == 0
    assert pack["grc_redaction"]["redacted_column_count"] == 0
