"""Contract tests for the OpenMetadata 2.x anti-corruption layer."""

from __future__ import annotations

import json
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient
from sdp_core import ActorContext

from openmetadata_test_support import (
    DOWNSTREAM_ID,
    PIPELINE_ID,
    TABLE_ID,
    UPSTREAM_ID,
    lineage_payload,
    reference_payload,
    table_payload,
)
from sdp import openmetadata_routes
from sdp.api import app
from sdp.openmetadata import (
    OpenMetadataContractError,
    normalize_openmetadata_table_snapshot,
)

_SOURCE_INSTANCE_ID = "metadata_primary"
_AUTH_HEADERS = {"Authorization": "Bearer test-token"}
client = TestClient(app)


@pytest.fixture(autouse=True)
def _authorize_http_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bind HTTP integration checks to one verified tenant actor."""

    monkeypatch.setattr(
        openmetadata_routes,
        "verify_oidc_jwks_token",
        lambda _token: (
            ActorContext(
                subject="user_001",
                tenant_id="tenant_acme",
                roles=["data-analyst"],
            ),
            {},
        ),
    )


def _normalize(
    *,
    table: dict[str, object] | None = None,
    lineage: dict[str, object] | None = None,
):
    """Normalize a fixture through the public installation-scoped boundary."""

    return normalize_openmetadata_table_snapshot(
        tenant_id="tenant_acme",
        source_instance_id=_SOURCE_INSTANCE_ID,
        source_release="2.0.1",
        table=table or table_payload(),
        lineage=lineage,
    )


def test_normalizer_preserves_identity_semantics_and_safe_lineage() -> None:
    """The adapter keeps governed context without leaking samples or SQL text."""

    result = _normalize(lineage=lineage_payload())

    assert result.projection_id == (
        f"urn:cwl:tenant_acme:sdp:openmetadata_table:"
        f"{_SOURCE_INSTANCE_ID}:{TABLE_ID}"
    )
    assert result.source_authority == "openmetadata"
    assert result.source_instance_id == _SOURCE_INSTANCE_ID
    assert result.source_release == "2.0.1"
    assert result.truth_status == "observed"
    assert result.external_entity_type == "table"
    assert result.external_entity_id == TABLE_ID
    assert result.title == "Orders"
    assert result.fully_qualified_name == (
        "warehouse.sales.public.orders"
    )
    assert result.entity_version == "2.3"
    assert result.owner_references[0].label == "Data Platform"
    assert result.domain_references[0].fully_qualified_name == "sales"
    assert result.data_product_references[0].label == "Customer 360"
    assert result.data_contract_reference is not None
    assert result.tag_fqns == ["Tier.Tier1"]
    assert result.profile_summary.row_count == 42
    assert result.profile_summary.column_count == 2
    assert result.profile_summary.size_in_bytes == 1_024

    columns = {column.column_path: column for column in result.columns}
    assert set(columns) == {"order_id", "customer", "customer.email"}
    assert columns["order_id"].nullable is False
    assert columns["customer"].nullable is None
    assert columns["customer.email"].nullable is True
    assert columns["customer.email"].data_type_display == "varchar(320)"
    assert columns["customer.email"].tag_fqns == ["PII.Sensitive"]

    assert len(result.lineage_edges) == 2
    upstream = result.lineage_edges[0]
    assert upstream.from_reference.external_entity_id == UPSTREAM_ID
    assert upstream.to_reference.external_entity_id == TABLE_ID
    assert upstream.source == "OpenLineage"
    assert upstream.pipeline_reference is not None
    assert upstream.pipeline_reference.external_entity_id == PIPELINE_ID
    assert upstream.column_mappings[0].from_columns == [
        "warehouse.raw.orders.order_id"
    ]
    assert upstream.column_mappings[0].to_column == (
        "warehouse.sales.public.orders.order_id"
    )
    assert upstream.transformation_text_omitted is True

    serialized = result.model_dump_json()
    assert "customer-secret-value" not in serialized
    assert "CREATE TABLE" not in serialized
    assert "SELECT secret" not in serialized
    assert "hash(secret)" not in serialized
    assert set(result.omitted_fields) >= {
        "table.joins",
        "table.queries",
        "table.sampleData",
        "table.schemaDefinition",
        "lineage.lineageDetails.sqlQuery",
        "lineage.lineageDetails.columnsLineage.function",
    }


def test_normalizer_rejects_lineage_for_another_primary_entity() -> None:
    """A lineage response cannot be attached to a different table snapshot."""

    lineage = lineage_payload()
    lineage["entity"] = reference_payload(
        UPSTREAM_ID,
        "table",
        "warehouse.raw.orders",
    )

    with pytest.raises(
        OpenMetadataContractError,
        match="lineage entity does not match table id",
    ):
        _normalize(lineage=lineage)


def test_normalizer_rejects_lineage_edges_with_unknown_endpoints() -> None:
    """Every lineage endpoint must resolve to the primary entity or a node."""

    lineage = lineage_payload()
    lineage["upstreamEdges"][0]["fromEntity"] = (
        "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
    )

    with pytest.raises(
        OpenMetadataContractError,
        match="unknown lineage endpoint",
    ):
        _normalize(lineage=lineage)


def test_normalizer_rejects_duplicate_column_paths() -> None:
    """Ambiguous column identities fail closed instead of being overwritten."""

    table = table_payload()
    table["columns"].append(deepcopy(table["columns"][0]))

    with pytest.raises(
        OpenMetadataContractError,
        match="duplicate column path: order_id",
    ):
        _normalize(table=table)


def test_normalizer_rejects_excessive_column_nesting() -> None:
    """Hostile recursive schemas are bounded before exhausting the process."""

    table = table_payload()
    nested = {
        "name": "level_00",
        "dataType": "STRUCT",
        "children": [],
    }
    table["columns"] = [nested]
    cursor = nested
    for index in range(1, 18):
        child = {
            "name": f"level_{index:02d}",
            "dataType": "STRUCT",
            "children": [],
        }
        cursor["children"] = [child]
        cursor = child

    with pytest.raises(
        OpenMetadataContractError,
        match="column nesting exceeds 16",
    ):
        _normalize(table=table)


def test_openmetadata_normalization_endpoint_returns_typed_projection() -> None:
    """The HTTP surface exposes the same deterministic ACL contract."""

    response = client.post(
        "/integrations/openmetadata/v1/table-snapshots:normalize",
        headers=_AUTH_HEADERS,
        json={
            "tenant_id": "tenant_acme",
            "source_instance_id": _SOURCE_INSTANCE_ID,
            "source_release": "2.0.1",
            "table": table_payload(),
            "lineage": lineage_payload(),
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["projection_id"].endswith(
        f"{_SOURCE_INSTANCE_ID}:{TABLE_ID}"
    )
    assert body["source_instance_id"] == _SOURCE_INSTANCE_ID
    assert body["source_schema_uri"] == (
        "https://open-metadata.org/schema/entity/data/table.json"
    )
    assert body["lineage_schema_uri"] == (
        "https://open-metadata.org/schema/type/entityLineage.json"
    )
    assert body["columns"][2]["column_path"] == "customer.email"


def test_openmetadata_endpoint_rejects_pre_2_x_payload_contracts() -> None:
    """The first adapter slice does not reinterpret pre-2.x payloads."""

    response = client.post(
        "/integrations/openmetadata/v1/table-snapshots:normalize",
        headers=_AUTH_HEADERS,
        json={
            "tenant_id": "tenant_acme",
            "source_instance_id": _SOURCE_INSTANCE_ID,
            "source_release": "1.12.8",
            "table": table_payload(),
        },
    )

    assert response.status_code == 422


def test_openmetadata_endpoint_returns_bounded_contract_error() -> None:
    """Malformed references produce a stable 400 without echoing source data."""

    table = table_payload()
    table["id"] = "not-a-uuid"
    response = client.post(
        "/integrations/openmetadata/v1/table-snapshots:normalize",
        headers=_AUTH_HEADERS,
        json={
            "tenant_id": "tenant_acme",
            "source_instance_id": _SOURCE_INSTANCE_ID,
            "source_release": "2.0.1",
            "table": table,
        },
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "table.id must be a UUID"}
    assert "Governed order facts" not in json.dumps(response.json())


def test_projection_serialization_is_bounded_and_deterministic() -> None:
    """Equivalent payload copies produce identical serialized projections."""

    first = _normalize(lineage=lineage_payload())
    second = normalize_openmetadata_table_snapshot(
        tenant_id="tenant_acme",
        source_instance_id=_SOURCE_INSTANCE_ID,
        source_release="2.0.1-release",
        table=deepcopy(table_payload()),
        lineage=deepcopy(lineage_payload()),
    )

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert json.loads(first.model_dump_json()) == first.model_dump(mode="json")


def test_malformed_external_reference_does_not_echo_payload_data() -> None:
    """A stable contract error never contains unrelated source description."""

    table = table_payload()
    table["id"] = "not-a-uuid"

    with pytest.raises(OpenMetadataContractError) as error:
        _normalize(table=table)

    assert str(error.value) == "table.id must be a UUID"
    assert "Governed order facts" not in str(error.value)
