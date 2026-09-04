"""RED contracts for exact OpenMetadata 2.0.1 compatibility.

These tests intentionally exercise the normalization sink as well as the public
verified wrapper. They are grounded in the immutable upstream 2.0.1 schemas:
Table requires only ``id``, ``name`` and ``columns``; EntityReference requires
only ``id`` and ``type``. Optional upstream identity fields must therefore not
be invented as CWL admission requirements.
"""

from __future__ import annotations

from copy import deepcopy
from math import inf, nan

import pytest

from openmetadata_test_support import TABLE_ID, table_payload
from sdp.openmetadata import (
    OpenMetadataContractError,
    normalize_openmetadata_table_snapshot,
)
from sdp.openmetadata import normalizer

_SOURCE_INSTANCE_ID = "metadata_primary"


def test_core_normalizer_admits_schema_valid_table_without_fqn() -> None:
    """Do not require an optional Table fullyQualifiedName."""

    projection = normalizer.normalize_openmetadata_table_snapshot(
        tenant_id="tenant_acme",
        source_instance_id=_SOURCE_INSTANCE_ID,
        source_release="2.0.1",
        table={"id": TABLE_ID, "name": "orders", "columns": []},
    )

    assert projection.name == "orders"
    assert projection.fully_qualified_name is None


def test_reference_requires_only_upstream_id_and_type() -> None:
    """Do not reject a schema-valid EntityReference that omits its name."""

    projection = normalizer._reference(
        {"id": TABLE_ID, "type": "table"},
        "reference",
    )

    assert projection.external_entity_id == TABLE_ID
    assert projection.entity_type == "table"
    assert projection.name is None
    assert projection.display_name is None
    assert projection.label is None


def test_core_normalizer_cannot_bypass_verified_release_profile() -> None:
    """The actual normalization sink must reject an unverified 2.x release."""

    with pytest.raises(
        OpenMetadataContractError,
        match="no verified OpenMetadata compatibility profile",
    ):
        normalizer.normalize_openmetadata_table_snapshot(
            tenant_id="tenant_acme",
            source_instance_id=_SOURCE_INSTANCE_ID,
            source_release="2.1.0-release",
            table=table_payload(),
        )


@pytest.mark.parametrize("version", [nan, inf, -inf])
def test_non_finite_table_versions_fail_closed(version: float) -> None:
    """NaN and infinities are not portable entity-version values."""

    table = table_payload()
    table["version"] = version

    with pytest.raises(OpenMetadataContractError, match="version must be finite"):
        normalize_openmetadata_table_snapshot(
            tenant_id="tenant_acme",
            source_instance_id=_SOURCE_INSTANCE_ID,
            source_release="2.0.1",
            table=table,
        )


def test_reference_identity_conflicts_are_snapshot_wide() -> None:
    """One external UUID cannot acquire contradictory identities by field."""

    table = table_payload()
    owner = deepcopy(table["owners"][0])
    table["domains"] = [
        {
            **owner,
            "type": "domain",
            "name": "sales",
            "displayName": "Sales",
            "fullyQualifiedName": "sales",
        }
    ]

    with pytest.raises(OpenMetadataContractError, match="conflict"):
        normalize_openmetadata_table_snapshot(
            tenant_id="tenant_acme",
            source_instance_id=_SOURCE_INSTANCE_ID,
            source_release="2.0.1",
            table=table,
        )
