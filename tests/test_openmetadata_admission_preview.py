"""Contract tests for deterministic OpenMetadata admission previews."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone, tzinfo

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sdp_core import ActorContext

from openmetadata_test_support import table_payload
from sdp import openmetadata_routes
from sdp.openmetadata import (
    DIGEST_PROFILE_ID,
    OpenMetadataAdmissionPreviewRequest,
    OpenMetadataContractError,
    preview_openmetadata_table_admission,
)


OBSERVED_AT = datetime(2026, 9, 4, 0, 0, tzinfo=timezone.utc)


class IndeterminateTimezone(tzinfo):
    """Timezone marker that deliberately has no usable UTC offset."""

    def utcoffset(self, value: datetime | None) -> timedelta | None:
        """Return no offset so ambiguity handling can be verified."""

        return None

    def dst(self, value: datetime | None) -> timedelta | None:
        """Return no daylight-saving offset for the test timezone."""

        return None


def _preview(
    *,
    source_instance_id: str = "metadata_primary",
    source_release: str = "2.0.1",
    table: dict[str, object] | None = None,
):
    """Create one deterministic preview through the public domain boundary."""

    return preview_openmetadata_table_admission(
        tenant_id="tenant_acme",
        source_instance_id=source_instance_id,
        source_release=source_release,
        observed_at=OBSERVED_AT,
        table=table if table is not None else table_payload(),
    )


def test_equivalent_key_order_produces_identical_receipt_identity() -> None:
    """JSON object insertion order cannot change evidence identity."""

    original = table_payload()
    reordered = dict(reversed(list(original.items())))

    first = _preview(table=original)
    second = _preview(table=reordered)

    assert first.digest_profile_id == DIGEST_PROFILE_ID
    assert first.source_snapshot_digest == second.source_snapshot_digest
    assert first.projection_digest == second.projection_digest
    assert first.replay_key == second.replay_key
    assert first.receipt_id == second.receipt_id


def test_release_aliases_produce_one_canonical_receipt() -> None:
    """Equivalent verified labels cannot split one admission candidate."""

    semantic = _preview(source_release="2.0.1")
    tagged = _preview(source_release="2.0.1-release")

    assert semantic == tagged
    assert semantic.source_release == "2.0.1"
    assert semantic.compatibility_profile_id == (
        "openmetadata-table-lineage-2.0.1"
    )


def test_source_instance_changes_projection_and_replay_scope() -> None:
    """Equal source bytes from different installations remain distinct."""

    primary = _preview(source_instance_id="metadata_primary")
    recovery = _preview(source_instance_id="metadata_recovery")

    assert primary.source_snapshot_digest == recovery.source_snapshot_digest
    assert primary.projection_digest != recovery.projection_digest
    assert primary.projection.projection_id != recovery.projection.projection_id
    assert primary.replay_key != recovery.replay_key
    assert primary.receipt_id != recovery.receipt_id


def test_omitted_secret_changes_source_digest_without_receipt_leak() -> None:
    """Source identity includes omitted values while the safe projection does not."""

    first_table = table_payload()
    first_table["sampleData"] = {
        "columns": ["secret"],
        "rows": [["customer-secret-alpha"]],
    }
    second_table = deepcopy(first_table)
    second_sample_data = second_table["sampleData"]
    assert isinstance(second_sample_data, dict)
    second_sample_data["rows"] = [["customer-secret-beta"]]

    first = _preview(table=first_table)
    second = _preview(table=second_table)

    assert first.source_snapshot_digest != second.source_snapshot_digest
    assert first.projection_digest == second.projection_digest
    assert first.replay_key != second.replay_key
    assert "table.sampleData" in first.omitted_fields

    serialized = first.model_dump_json()
    assert "customer-secret-alpha" not in serialized
    assert "customer-secret-beta" not in serialized
    assert first.raw_payload_persisted is False
    assert first.catalog_mutation_performed is False
    assert first.omitted_source_values_copied is False


def test_non_deterministic_json_values_fail_before_receipt_creation() -> None:
    """Values without a language-neutral digest representation fail closed."""

    non_finite = table_payload()
    non_finite["version"] = float("nan")
    with pytest.raises(
        OpenMetadataContractError,
        match="table.version must be finite",
    ):
        _preview(table=non_finite)

    non_string_key = table_payload()
    non_string_key["extension"] = {1: "value"}  # type: ignore[dict-item]
    with pytest.raises(
        OpenMetadataContractError,
        match="JSON object keys must be strings",
    ):
        _preview(table=non_string_key)

    foreign_container = table_payload()
    foreign_container["extension"] = ("value",)
    with pytest.raises(
        OpenMetadataContractError,
        match="source snapshot is not deterministic JSON data",
    ):
        _preview(table=foreign_container)


def test_source_instance_and_observation_time_fail_closed() -> None:
    """Replay scope and event time reject ambiguous direct-call values."""

    with pytest.raises(
        OpenMetadataContractError,
        match="source_instance_id contains unsupported characters",
    ):
        _preview(source_instance_id="metadata:prod")

    with pytest.raises(
        OpenMetadataContractError,
        match="observed_at must be a datetime",
    ):
        preview_openmetadata_table_admission(
            tenant_id="tenant_acme",
            source_instance_id="metadata_primary",
            source_release="2.0.1",
            observed_at="2026-09-04T00:00:00Z",  # type: ignore[arg-type]
            table=table_payload(),
        )

    with pytest.raises(
        OpenMetadataContractError,
        match="observed_at must include a timezone",
    ):
        preview_openmetadata_table_admission(
            tenant_id="tenant_acme",
            source_instance_id="metadata_primary",
            source_release="2.0.1",
            observed_at=datetime(2026, 9, 4, 0, 0),
            table=table_payload(),
        )


def test_request_model_rejects_timezone_without_offset() -> None:
    """A timezone marker without an offset is invalid at the typed HTTP seam."""

    with pytest.raises(ValidationError, match="observed_at must include a timezone"):
        OpenMetadataAdmissionPreviewRequest(
            tenant_id="tenant_acme",
            source_instance_id="metadata_primary",
            source_release="2.0.1",
            observed_at=datetime(
                2026,
                9,
                4,
                0,
                0,
                tzinfo=IndeterminateTimezone(),
            ),
            table=table_payload(),
        )


def test_http_endpoint_returns_non_mutating_admission_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The HTTP surface returns receipt evidence without source persistence."""

    def verify_actor(_token: str) -> tuple[ActorContext, dict[str, object]]:
        return (
            ActorContext(
                subject="user_001",
                tenant_id="tenant_acme",
                roles=["data-analyst"],
            ),
            {"sub": "user_001", "tenant_id": "tenant_acme"},
        )

    monkeypatch.setattr(
        openmetadata_routes,
        "verify_oidc_jwks_token",
        verify_actor,
    )
    app = FastAPI()
    app.include_router(openmetadata_routes.router)
    response = TestClient(app).post(
        "/integrations/openmetadata/v1/table-snapshots:admission-preview",
        headers={"Authorization": "Bearer valid"},
        json={
            "tenant_id": "tenant_acme",
            "source_instance_id": "metadata_primary",
            "source_release": "2.0.1-release",
            "observed_at": OBSERVED_AT.isoformat(),
            "table": table_payload(),
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["admission_status"] == "accepted_for_review"
    assert body["receipt_contract_version"] == "1.0.0"
    assert body["digest_profile_id"] == DIGEST_PROFILE_ID
    assert body["external_entity_id"] == table_payload()["id"]
    assert body["receipt_id"].startswith(
        "urn:cwl:tenant_acme:sdp:openmetadata_admission_preview:"
    )
    for field_name in (
        "source_snapshot_digest",
        "projection_digest",
        "replay_key",
    ):
        assert body[field_name].startswith("sha256:")
        assert len(body[field_name]) == 71
    assert body["raw_payload_persisted"] is False
    assert body["catalog_mutation_performed"] is False
    assert body["omitted_source_values_copied"] is False
    assert body["projection"]["source_instance_id"] == "metadata_primary"
    assert json.dumps(body).find("customer-secret") == -1
