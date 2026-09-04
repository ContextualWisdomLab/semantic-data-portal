"""Regression tests for verified OpenMetadata review findings."""

from __future__ import annotations

from copy import deepcopy

import pytest

from openmetadata_test_support import TABLE_ID
from sdp.openmetadata import (
    OpenMetadataContractError,
    normalize_openmetadata_table_snapshot,
)
from sdp.openmetadata.normalizer import (
    normalize_openmetadata_table_snapshot as normalize_at_sink,
)
from sdp.openmetadata.validation import _validate_payload_budget

_SOURCE_INSTANCE_ID = "metadata_primary"


def _minimal_table() -> dict[str, object]:
    """Return the smallest Table admitted by the pinned 2.0.1 schema."""

    return {
        "id": TABLE_ID,
        "name": "orders",
        "columns": [{"name": "order_id", "dataType": "UUID"}],
    }


def _reference(
    reference_id: str,
    entity_type: str,
    *,
    name: str | None = None,
    fully_qualified_name: str | None = None,
) -> dict[str, object]:
    """Build a schema-valid reference with optional descriptive fields."""

    value: dict[str, object] = {
        "id": reference_id,
        "type": entity_type,
    }
    if name is not None:
        value["name"] = name
    if fully_qualified_name is not None:
        value["fullyQualifiedName"] = fully_qualified_name
    return value


def test_minimal_schema_valid_table_does_not_require_fully_qualified_name() -> None:
    """The ACL admits the exact required Table fields without inventing an FQN."""

    projection = normalize_openmetadata_table_snapshot(
        tenant_id="tenant_acme",
        source_instance_id=_SOURCE_INSTANCE_ID,
        source_release="2.0.1",
        table=_minimal_table(),
    )

    assert projection.name == "orders"
    assert projection.fully_qualified_name is None


def test_schema_valid_unnamed_references_remain_unlabelled() -> None:
    """EntityReference requires only id and type across every supported location."""

    owner_id = "55555555-5555-4555-8555-555555555555"
    schema_id = "66666666-6666-4666-8666-666666666666"
    upstream_id = "22222222-2222-4222-8222-222222222222"
    pipeline_id = "44444444-4444-4444-8444-444444444444"
    table = _minimal_table()
    table["owners"] = [_reference(owner_id, "team")]
    table["databaseSchema"] = _reference(schema_id, "databaseSchema")
    lineage = {
        "entity": _reference(TABLE_ID, "table"),
        "nodes": [_reference(upstream_id, "table")],
        "upstreamEdges": [
            {
                "fromEntity": upstream_id,
                "toEntity": TABLE_ID,
                "lineageDetails": {
                    "pipeline": _reference(pipeline_id, "pipeline")
                },
            }
        ],
        "downstreamEdges": [],
    }

    projection = normalize_openmetadata_table_snapshot(
        tenant_id="tenant_acme",
        source_instance_id=_SOURCE_INSTANCE_ID,
        source_release="2.0.1",
        table=table,
        lineage=lineage,
    )

    assert projection.owner_references[0].label is None
    assert projection.database_schema_reference is not None
    assert projection.database_schema_reference.label is None
    edge = projection.lineage_edges[0]
    assert edge.from_reference.label is None
    assert edge.pipeline_reference is not None
    assert edge.pipeline_reference.label is None
    assert edge.to_reference.label == "orders"


def test_acyclic_shared_container_is_not_misclassified_as_cycle() -> None:
    """A Python alias is allowed after its first traversal path is complete."""

    shared = {"id": "value"}
    _validate_payload_budget({"left": shared, "right": shared})


def test_true_container_back_edge_remains_rejected() -> None:
    """The active traversal path still detects actual cyclic input."""

    cyclic: dict[str, object] = {}
    cyclic["self"] = cyclic

    with pytest.raises(OpenMetadataContractError, match="cyclic container"):
        _validate_payload_budget(cyclic)


def test_conflicting_uuid_across_table_reference_fields_fails_closed() -> None:
    """One snapshot cannot assign contradictory identities to one UUID."""

    shared_id = "55555555-5555-4555-8555-555555555555"
    table = _minimal_table()
    table["owners"] = [
        _reference(shared_id, "team", name="data_platform")
    ]
    table["domains"] = [
        _reference(shared_id, "domain", name="sales")
    ]

    with pytest.raises(OpenMetadataContractError, match="conflicts with reference id"):
        normalize_openmetadata_table_snapshot(
            tenant_id="tenant_acme",
            source_instance_id=_SOURCE_INSTANCE_ID,
            source_release="2.0.1",
            table=table,
        )


def test_table_and_lineage_primary_identity_must_be_consistent() -> None:
    """The lineage primary cannot contradict the Table identity sharing its UUID."""

    table = _minimal_table()
    table["fullyQualifiedName"] = "warehouse.sales.orders"
    lineage = {
        "entity": _reference(
            TABLE_ID,
            "table",
            name="orders",
            fully_qualified_name="warehouse.other.orders",
        ),
        "nodes": [],
        "upstreamEdges": [],
        "downstreamEdges": [],
    }

    with pytest.raises(OpenMetadataContractError, match="conflicts with reference id"):
        normalize_openmetadata_table_snapshot(
            tenant_id="tenant_acme",
            source_instance_id=_SOURCE_INSTANCE_ID,
            source_release="2.0.1",
            table=table,
            lineage=lineage,
        )


def test_direct_normalization_sink_rejects_unverified_release() -> None:
    """Importing the internal sink cannot bypass exact compatibility admission."""

    with pytest.raises(
        OpenMetadataContractError,
        match="no verified OpenMetadata compatibility profile",
    ):
        normalize_at_sink(
            tenant_id="tenant_acme",
            source_instance_id=_SOURCE_INSTANCE_ID,
            source_release="2.1.0",
            table=_minimal_table(),
        )


@pytest.mark.parametrize("version", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_table_version_is_rejected(version: float) -> None:
    """Non-JSON floating-point sentinels never enter projection provenance."""

    table = deepcopy(_minimal_table())
    table["version"] = version

    with pytest.raises(OpenMetadataContractError, match="table.version must be finite"):
        normalize_openmetadata_table_snapshot(
            tenant_id="tenant_acme",
            source_instance_id=_SOURCE_INSTANCE_ID,
            source_release="2.0.1",
            table=table,
        )
