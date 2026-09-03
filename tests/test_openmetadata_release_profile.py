"""Compatibility-profile tests for the OpenMetadata boundary."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from openmetadata_test_support import table_payload
from sdp.openmetadata import (
    OpenMetadataContractError,
    normalize_openmetadata_table_snapshot,
    resolve_openmetadata_release_profile,
)
from sdp.openmetadata_routes import router


def test_verified_release_aliases_resolve_to_one_exact_profile() -> None:
    """Tag and semantic-version spellings identify one immutable upstream revision."""

    semantic = resolve_openmetadata_release_profile("2.0.1")
    tagged = resolve_openmetadata_release_profile("2.0.1-release")

    assert semantic == tagged
    assert semantic.profile_id == "openmetadata-table-lineage-2.0.1"
    assert semantic.canonical_release == "2.0.1"
    assert semantic.upstream_repository == "open-metadata/OpenMetadata"
    assert semantic.upstream_revision == "bf621b166ec12e8c99fcb1c1443442723386fa41"


def test_unverified_2_x_release_fails_closed() -> None:
    """A syntactically valid 2.x label is not treated as verified compatibility."""

    with pytest.raises(
        OpenMetadataContractError,
        match="no verified OpenMetadata compatibility profile",
    ):
        resolve_openmetadata_release_profile("2.1.0")


def test_projection_records_exact_compatibility_provenance() -> None:
    """Every normalized projection identifies the tested contract and source commit."""

    projection = normalize_openmetadata_table_snapshot(
        tenant_id="tenant_acme",
        source_release="2.0.1-release",
        table=table_payload(),
    )

    assert projection.source_release == "2.0.1"
    assert projection.compatibility_profile_id == "openmetadata-table-lineage-2.0.1"
    assert projection.upstream_repository == "open-metadata/OpenMetadata"
    assert projection.upstream_revision == "bf621b166ec12e8c99fcb1c1443442723386fa41"


def test_http_boundary_rejects_unverified_2_x_release() -> None:
    """The API does not silently reinterpret a future OpenMetadata contract."""

    app = FastAPI()
    app.include_router(router)
    response = TestClient(app).post(
        "/integrations/openmetadata/v1/table-snapshots:normalize",
        json={
            "tenant_id": "tenant_acme",
            "source_release": "2.1.0",
            "table": table_payload(),
        },
    )

    assert response.status_code == 400
    assert response.json() == {
        "detail": "source_release has no verified OpenMetadata compatibility profile"
    }
