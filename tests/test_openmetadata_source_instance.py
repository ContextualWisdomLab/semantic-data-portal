"""Contract tests for OpenMetadata installation-scoped identities."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from openmetadata_test_support import table_payload
from sdp.openmetadata import (
    OpenMetadataContractError,
    OpenMetadataNormalizationRequest,
    normalize_openmetadata_table_snapshot,
)


def test_source_instance_scopes_projection_identity() -> None:
    """Equal upstream UUIDs from distinct installations never collide."""

    primary = normalize_openmetadata_table_snapshot(
        tenant_id="tenant_acme",
        source_instance_id="metadata_primary",
        source_release="2.0.1",
        table=table_payload(),
    )
    recovery = normalize_openmetadata_table_snapshot(
        tenant_id="tenant_acme",
        source_instance_id="metadata_recovery",
        source_release="2.0.1",
        table=table_payload(),
    )

    assert primary.source_instance_id == "metadata_primary"
    assert recovery.source_instance_id == "metadata_recovery"
    assert primary.external_entity_id == recovery.external_entity_id
    assert primary.projection_id != recovery.projection_id
    assert ":metadata_primary:" in primary.projection_id
    assert ":metadata_recovery:" in recovery.projection_id


def test_invalid_source_instance_fails_closed() -> None:
    """A source installation identifier cannot inject URI structure."""

    with pytest.raises(
        OpenMetadataContractError,
        match="source_instance_id contains unsupported characters",
    ):
        normalize_openmetadata_table_snapshot(
            tenant_id="tenant_acme",
            source_instance_id="metadata:primary",
            source_release="2.0.1",
            table=table_payload(),
        )


def test_http_request_requires_source_instance() -> None:
    """The wire contract never falls back to a collision-prone default source."""

    with pytest.raises(ValidationError):
        OpenMetadataNormalizationRequest.model_validate(
            {
                "tenant_id": "tenant_acme",
                "source_release": "2.0.1",
                "table": table_payload(),
            }
        )
