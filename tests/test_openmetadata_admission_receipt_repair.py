"""RED contract for the repaired OpenMetadata admission-receipt successor."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sdp_core import ActorContext

from openmetadata_test_support import table_payload
from sdp import openmetadata_routes
import sdp.openmetadata.admission_preview as admission_preview_module
from sdp.openmetadata import (
    OpenMetadataAdmissionReceipt,
    OpenMetadataContractError,
    preview_openmetadata_table_admission,
)


OBSERVED_AT = datetime(2026, 9, 4, 0, 0, tzinfo=timezone.utc)


def _verified_actor(
    monkeypatch: pytest.MonkeyPatch,
    *,
    tenant_id: str = "tenant_acme",
) -> None:
    """Install a typed actor fixture at the existing bearer-verification seam."""

    def verify_actor(_token: str) -> tuple[ActorContext, dict[str, object]]:
        return (
            ActorContext(
                subject="user_001",
                tenant_id=tenant_id,
                roles=["data-analyst"],
            ),
            {"sub": "user_001", "tenant_id": tenant_id},
        )

    monkeypatch.setattr(
        openmetadata_routes,
        "verify_oidc_jwks_token",
        verify_actor,
    )


def _preview(
    *,
    observed_at: datetime = OBSERVED_AT,
    source_instance_id: str = "metadata_primary",
    table: dict[str, object] | None = None,
):
    """Build one deterministic receipt through the public domain boundary."""

    return preview_openmetadata_table_admission(
        tenant_id="tenant_acme",
        source_instance_id=source_instance_id,
        source_release="2.0.1-release",
        observed_at=observed_at,
        table=table if table is not None else table_payload(),
    )


def test_receipt_projection_keeps_source_instance_scope() -> None:
    """The receipt must not collapse equal UUIDs from distinct installations."""

    primary = _preview(source_instance_id="metadata_primary")
    recovery = _preview(source_instance_id="metadata_recovery")

    assert primary.projection.source_instance_id == "metadata_primary"
    assert recovery.projection.source_instance_id == "metadata_recovery"
    assert primary.projection.projection_id != recovery.projection.projection_id
    assert primary.replay_key != recovery.replay_key


def test_receipt_rejects_nested_projection_tampering() -> None:
    """Transport validation must recompute the safe-projection digest."""

    payload = _preview().model_dump(mode="json")
    projection = payload["projection"]
    assert isinstance(projection, dict)
    projection["title"] = "Tampered title"

    with pytest.raises(
        ValidationError,
        match="projection_digest does not match projection",
    ):
        OpenMetadataAdmissionReceipt.model_validate(payload)


def test_source_snapshot_digest_sees_omitted_values_without_copying_them() -> None:
    """Sensitive omitted values affect source identity but never receipt content."""

    first_table = table_payload()
    first_table["sampleData"] = {
        "columns": ["secret"],
        "rows": [["alpha-secret"]],
    }
    second_table = deepcopy(first_table)
    second_sample = second_table["sampleData"]
    assert isinstance(second_sample, dict)
    second_sample["rows"] = [["beta-secret"]]

    first = _preview(table=first_table)
    second = _preview(table=second_table)

    assert first.source_snapshot_digest != second.source_snapshot_digest
    assert first.projection_digest == second.projection_digest
    assert first.omitted_source_values_copied is False
    serialized = first.model_dump_json()
    assert "alpha-secret" not in serialized
    assert "beta-secret" not in serialized


def test_reobservation_reuses_candidate_but_not_event_receipt() -> None:
    """Retry identity and a later observation are not conflated."""

    first = _preview()
    retry = _preview()
    later = _preview(observed_at=OBSERVED_AT + timedelta(minutes=5))

    assert first.admission_candidate_id == retry.admission_candidate_id
    assert first.receipt_id == retry.receipt_id
    assert first.admission_candidate_id == later.admission_candidate_id
    assert first.receipt_id != later.receipt_id


def test_invalid_tenant_fails_before_source_hashing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cheap identity admission precedes work proportional to source size."""

    def hashing_must_not_run(_value: object, _field_name: str) -> str:
        raise AssertionError("source hashing ran before tenant validation")

    monkeypatch.setattr(
        admission_preview_module,
        "structural_sha256",
        hashing_must_not_run,
    )
    with pytest.raises(
        OpenMetadataContractError,
        match="tenant_id contains unsupported characters",
    ):
        preview_openmetadata_table_admission(
            tenant_id="tenant:other",
            source_instance_id="metadata_primary",
            source_release="2.0.1",
            observed_at=OBSERVED_AT,
            table=table_payload(),
        )


def test_admission_route_reuses_bearer_and_tenant_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The successor route must not reintroduce caller-selected tenant authority."""

    app = FastAPI()
    app.include_router(openmetadata_routes.router)
    client = TestClient(app)
    path = "/integrations/openmetadata/v1/table-snapshots:admission-preview"
    payload = {
        "tenant_id": "tenant_acme",
        "source_instance_id": "metadata_primary",
        "source_release": "2.0.1",
        "observed_at": OBSERVED_AT.isoformat(),
        "table": table_payload(),
    }

    unauthenticated = client.post(path, json=payload)
    assert unauthenticated.status_code == 401
    assert unauthenticated.json() == {
        "detail": "Bearer authentication required"
    }

    _verified_actor(monkeypatch, tenant_id="tenant_acme")
    cross_tenant = client.post(
        path,
        headers={"Authorization": "Bearer valid"},
        json={**payload, "tenant_id": "tenant_other"},
    )
    assert cross_tenant.status_code == 404
    assert cross_tenant.json() == {"detail": "resource not found"}

    accepted = client.post(
        path,
        headers={"Authorization": "Bearer valid"},
        json=payload,
    )
    assert accepted.status_code == 200
    assert accepted.json()["projection"]["source_instance_id"] == (
        "metadata_primary"
    )
