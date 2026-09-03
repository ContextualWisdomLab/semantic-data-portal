"""Integrity tests for transported OpenMetadata admission receipts."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from openmetadata_test_support import table_payload
from sdp.openmetadata import (
    OpenMetadataAdmissionReceipt,
    preview_openmetadata_table_admission,
)


OBSERVED_AT = datetime(2026, 9, 3, 12, 0, tzinfo=timezone.utc)


def _receipt_payload() -> dict[str, object]:
    """Return a detached valid receipt payload for tamper tests."""

    receipt = preview_openmetadata_table_admission(
        tenant_id="tenant_acme",
        source_instance_id="metadata_prod",
        source_release="2.0.1",
        observed_at=OBSERVED_AT,
        table=table_payload(),
    )
    return receipt.model_dump(mode="json")


def test_generated_receipt_round_trips_through_integrity_validation() -> None:
    """A valid generated receipt remains transportable as ordinary JSON data."""

    payload = _receipt_payload()

    restored = OpenMetadataAdmissionReceipt.model_validate(payload)

    assert restored.model_dump(mode="json") == payload


@pytest.mark.parametrize(
    ("field_name", "tampered_value", "message"),
    [
        (
            "projection_digest",
            "sha256:" + ("0" * 64),
            "projection_digest does not match projection",
        ),
        (
            "replay_key",
            "sha256:" + ("1" * 64),
            "replay_key does not match receipt fields",
        ),
        (
            "admission_candidate_id",
            "urn:cwl:tenant_acme:sdp:openmetadata_admission_candidate:"
            + ("2" * 64),
            "admission_candidate_id does not match replay_key",
        ),
        (
            "receipt_id",
            "urn:cwl:tenant_acme:sdp:openmetadata_admission_preview:"
            + ("3" * 64),
            "receipt_id does not match candidate and observation time",
        ),
        (
            "external_entity_id",
            "22222222-2222-4222-8222-222222222222",
            "external_entity_id does not match projection",
        ),
    ],
)
def test_receipt_rejects_tampered_top_level_identity(
    field_name: str,
    tampered_value: str,
    message: str,
) -> None:
    """Top-level receipt identity cannot diverge from its nested evidence."""

    payload = _receipt_payload()
    payload[field_name] = tampered_value

    with pytest.raises(ValidationError, match=message):
        OpenMetadataAdmissionReceipt.model_validate(payload)


def test_receipt_rejects_tampered_projection_content() -> None:
    """Changing projected metadata without its digest invalidates the receipt."""

    payload = _receipt_payload()
    projection = payload["projection"]
    assert isinstance(projection, dict)
    projection["title"] = "Tampered title"

    with pytest.raises(
        ValidationError,
        match="projection_digest does not match projection",
    ):
        OpenMetadataAdmissionReceipt.model_validate(payload)


def test_receipt_rejects_projection_and_receipt_metadata_disagreement() -> None:
    """Authority, release, profile, revision, and omission metadata stay aligned."""

    mutations: list[tuple[str, object, str]] = [
        ("source_release", "2.0.0", "source_release does not match projection"),
        (
            "compatibility_profile_id",
            "other-profile",
            "compatibility_profile_id does not match projection",
        ),
        (
            "upstream_repository",
            "example/other",
            "upstream_repository does not match projection",
        ),
        (
            "upstream_revision",
            "0" * 40,
            "upstream_revision does not match projection",
        ),
        (
            "omitted_fields",
            ["table.extension"],
            "omitted_fields do not match projection",
        ),
    ]

    for field_name, value, message in mutations:
        payload = deepcopy(_receipt_payload())
        payload[field_name] = value
        with pytest.raises(ValidationError, match=message):
            OpenMetadataAdmissionReceipt.model_validate(payload)


def test_receipt_rejects_tenant_source_or_time_tampering() -> None:
    """Candidate and observation identities bind tenant, source, and time."""

    tenant_payload = _receipt_payload()
    tenant_payload["tenant_id"] = "tenant_other"
    with pytest.raises(
        ValidationError,
        match="replay_key does not match receipt fields",
    ):
        OpenMetadataAdmissionReceipt.model_validate(tenant_payload)

    source_payload = _receipt_payload()
    source_payload["source_instance_id"] = "metadata_recovery"
    with pytest.raises(
        ValidationError,
        match="replay_key does not match receipt fields",
    ):
        OpenMetadataAdmissionReceipt.model_validate(source_payload)

    time_payload = _receipt_payload()
    time_payload["observed_at"] = "2026-09-03T12:05:00Z"
    with pytest.raises(
        ValidationError,
        match="receipt_id does not match candidate and observation time",
    ):
        OpenMetadataAdmissionReceipt.model_validate(time_payload)
