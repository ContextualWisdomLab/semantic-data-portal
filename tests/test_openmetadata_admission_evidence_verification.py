"""Evidence-bound verification tests for OpenMetadata admission receipts."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone

import pytest

from openmetadata_test_support import table_payload
from sdp.openmetadata import (
    OpenMetadataContractError,
    preview_openmetadata_table_admission,
    verify_openmetadata_admission_receipt,
)


OBSERVED_AT = datetime(2026, 9, 3, 12, 0, tzinfo=timezone.utc)


def _receipt(table: dict[str, object]):
    """Build a deterministic admission preview for evidence verification."""

    return preview_openmetadata_table_admission(
        tenant_id="tenant_acme",
        source_instance_id="metadata_prod",
        source_release="2.0.1",
        observed_at=OBSERVED_AT,
        table=table,
    )


def test_receipt_verification_recomputes_source_and_projection_evidence() -> None:
    """Matching source bytes and safe projection satisfy the strong verifier."""

    table = table_payload()
    receipt = _receipt(table)

    result = verify_openmetadata_admission_receipt(
        receipt,
        source_table=table,
        source_lineage=None,
        projection=receipt.projection,
    )

    assert result.valid is True


def test_receipt_verification_rejects_another_source_snapshot() -> None:
    """A receipt cannot verify against different source evidence."""

    table = table_payload()
    receipt = _receipt(table)
    different = deepcopy(table)
    different["sampleData"] = {
        "columns": ["secret"],
        "rows": [["different-source-value"]],
    }

    with pytest.raises(
        OpenMetadataContractError,
        match="source snapshot digest does not match receipt",
    ):
        verify_openmetadata_admission_receipt(
            receipt,
            source_table=different,
            source_lineage=None,
            projection=receipt.projection,
        )


def test_receipt_verification_rejects_another_safe_projection() -> None:
    """The supplied projection must equal the projection bound to source."""

    table = table_payload()
    receipt = _receipt(table)
    different_projection = receipt.projection.model_copy(
        update={"title": "Forged title"}
    )

    with pytest.raises(
        OpenMetadataContractError,
        match="projection digest does not match receipt",
    ):
        verify_openmetadata_admission_receipt(
            receipt,
            source_table=table,
            source_lineage=None,
            projection=different_projection,
        )
