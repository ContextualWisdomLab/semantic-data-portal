"""Assurance-label tests for unsigned OpenMetadata admission receipts."""

from __future__ import annotations

from datetime import datetime, timezone

from openmetadata_test_support import table_payload
from sdp.openmetadata import preview_openmetadata_table_admission


def test_receipt_does_not_claim_signature_or_source_origin_attestation() -> None:
    """Digest self-consistency must not be represented as authenticated origin."""

    receipt = preview_openmetadata_table_admission(
        tenant_id="tenant_acme",
        source_instance_id="metadata_primary",
        source_release="2.0.1",
        observed_at=datetime(2026, 9, 4, tzinfo=timezone.utc),
        table=table_payload(),
    )

    assert receipt.integrity_assurance == "unsigned_self_consistency"
    assert receipt.source_origin_attested is False
    assert receipt.catalog_admission_performed is False
