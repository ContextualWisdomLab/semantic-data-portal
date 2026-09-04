"""Identity invariants for OpenMetadata admission candidates and observations."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from openmetadata_test_support import table_payload
from sdp.openmetadata import preview_openmetadata_table_admission


BASE_TIME = datetime(2026, 9, 4, 0, 0, tzinfo=timezone.utc)


def _preview(observed_at: datetime):
    """Create one admission preview for identity comparison."""

    return preview_openmetadata_table_admission(
        tenant_id="tenant_acme",
        source_instance_id="metadata_primary",
        source_release="2.0.1-release",
        observed_at=observed_at,
        table=table_payload(),
    )


def test_reobservation_keeps_candidate_but_creates_new_receipt() -> None:
    """One candidate may be observed repeatedly without reusing event identity."""

    first = _preview(BASE_TIME)
    later = _preview(BASE_TIME + timedelta(minutes=5))

    assert first.replay_key == later.replay_key
    assert first.admission_candidate_id == later.admission_candidate_id
    assert first.receipt_id != later.receipt_id
    assert first.observed_at != later.observed_at


def test_same_candidate_and_observation_time_is_retry_idempotent() -> None:
    """An exact delivery retry produces the same receipt and candidate identity."""

    first = _preview(BASE_TIME)
    retry = _preview(BASE_TIME)

    assert first.replay_key == retry.replay_key
    assert first.admission_candidate_id == retry.admission_candidate_id
    assert first.receipt_id == retry.receipt_id


def test_equivalent_timezones_produce_one_observation_receipt() -> None:
    """Equivalent instants cannot split identity because of offset spelling."""

    utc = _preview(BASE_TIME)
    korea = _preview(BASE_TIME.astimezone(timezone(timedelta(hours=9))))

    assert utc.observed_at == korea.observed_at
    assert utc.receipt_id == korea.receipt_id
    assert utc.admission_candidate_id == korea.admission_candidate_id
