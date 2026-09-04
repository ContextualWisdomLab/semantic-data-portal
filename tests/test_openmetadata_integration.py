"""Contract tests for the OpenMetadata 2.x anti-corruption layer."""

from __future__ import annotations

import json
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from sdp.api import app
from sdp.openmetadata import (
    OpenMetadataContractError,
    normalize_openmetadata_table_snapshot,
)


client = TestClient(app)

_TABLE_ID = "11111111-1111-4111-8111-111111111111"
_UPSTREAM_ID = "22222222-2222-4222-8222-222222222222"
_DOWNSTREAM_ID = "33333333-3333-4333-8333-333333333333"
_PIPELINE_ID = "44444444-4444-4444-8444-444444444444"


def _reference(
    reference_id: str,
    entity_type: str,
    name: str,
    *,
    fully_qualified_name: str | None = None,
) -> dict[str, object]:
    """Build an OpenMetadata entity reference fixture."""

    return {
        "id": reference_id,
        "type": entity_type,
        "name": name,
        "displayName": name.replace("_", " ").title(),
        "fullyQualifiedName": fully_qualified_name or name,
        "href": (
            f"https://metadata.example/api/v1/"
            f"{entity_type}/{reference_id}"
        ),
    }


def _table_payload() -> dict[str, object]:
    """Return a representative OpenMetadata 2.0.1 Table entity."""

    return {
        "id": _TABLE_ID,
        "name": "orders",
        "displayName": "Orders",
        "fullyQualifiedName": "warehouse.sales.public.orders",
        "description": "Governed order facts.",
        "version": 2.3,
        "updatedAt": 1_788_336_000_000,
        "updatedBy": "data_engineer",
        "href": f"https://metadata.example/api/v1/tables/{_TABLE_ID}",
        "tableType": "Regular",
        "columns": [
            {
                "name": "order_id",
                "dataType": "UUID",
                "constraint": "PRIMARY_KEY",
                "ordinalPosition": 1,
                "fullyQualifiedName": (
                    "warehouse.sales.public.orders.order_id"
                ),
                "tags": [
                    {
                        "tagFQN": "Identifier.Primary",
                        "source": "Classification",
                    }
                ],
            },
            {
                "name": "customer",
                "dataType": "STRUCT",
                "ordinalPosition": 2,
                "fullyQualifiedName": (
                    "warehouse.sales.public.orders.customer"
                ),
                "children": [
                    {
                        "name": "email",
                        "dataType": "VARCHAR",
                        "dataTypeDisplay": "varchar(320)",
                        "constraint": "NULL",
                        "description": "Customer contact address.",
                        "fullyQualifiedName": (
                            "warehouse.sales.public.orders.customer.email"
                        ),
                        "tags": [
                            {
                                "tagFQN": "PII.Sensitive",
                                "source": "Classification",
                            }
                        ],
                    }
                ],
            },
        ],
        "owners": [
            _reference(
                "55555555-5555-4555-8555-555555555555",
                "team",
                "data_platform",
            )
        ],
        "databaseSchema": _reference(
            "66666666-6666-4666-8666-666666666666",
            "databaseSchema",
            "warehouse.sales.public",
        ),
        "database": _reference(
            "77777777-7777-4777-8777-777777777777",
            "database",
            "warehouse.sales",
        ),
        "service": _reference(
            "88888888-8888-4888-8888-888888888888",
            "databaseService",
            "warehouse",
        ),
        "serviceType": "Postgres",
        "tags": [
            {
                "tagFQN": "Tier.Tier1",
                "source": "Classification",
            }
        ],
        "domains": [
            _reference(
                "99999999-9999-4999-8999-999999999999",
                "domain",
                "sales",
            )
        ],
        "dataProducts": [
            _reference(
                "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
                "dataProduct",
                "customer_360",
            )
        ],
        "dataContract": _reference(
            "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
            "dataContract",
            "orders_contract",
        ),
        "profile": {
            "timestamp": 1_788_336_000_000,
            "rowCount": 42,
            "columnCount": 2,
            "sizeInByte": 1_024,
        },
        "sourceHash": "0123456789abcdef",
        "sourceUrl": "https://warehouse.example/catalog/orders",
        "entityStatus": "Approved",
        "sampleData": {
            "columns": ["secret"],
            "rows": [["customer-secret-value"]],
        },
        "schemaDefinition": "CREATE TABLE orders (secret text)",
        "queries": ["SELECT * FROM customer_secret"],
        "joins": {
            "directTableJoins": [
                {
                    "fullyQualifiedName": "private.customer",
                    "joinCount": 1,
                }
            ]
        },
    }


def _lineage_payload() -> dict[str, object]:
    """Return lineage with both table- and column-level mappings."""

    upstream = _reference(
        _UPSTREAM_ID,
        "table",
        "warehouse.raw.orders",
    )
    downstream = _reference(
        _DOWNSTREAM_ID,
        "dashboard",
        "sales.order_dashboard",
    )
    primary = _reference(
        _TABLE_ID,
        "table",
        "orders",
        fully_qualified_name="warehouse.sales.public.orders",
    )
    return {
        "entity": primary,
        "nodes": [upstream, downstream],
        "upstreamEdges": [
            {
                "fromEntity": _UPSTREAM_ID,
                "toEntity": _TABLE_ID,
                "lineageDetails": {
                    "source": "OpenLineage",
                    "pipeline": _reference(
                        _PIPELINE_ID,
                        "pipeline",
                        "load_orders",
                    ),
                    "sqlQuery": "SELECT secret FROM raw_orders",
                    "columnsLineage": [
                        {
                            "fromColumns": [
                                "warehouse.raw.orders.order_id"
                            ],
                            "toColumn": (
                                "warehouse.sales.public.orders.order_id"
                            ),
                            "function": "hash(secret)",
                        }
                    ],
                },
            }
        ],
        "downstreamEdges": [
            {
                "fromEntity": _TABLE_ID,
                "toEntity": _DOWNSTREAM_ID,
                "lineageDetails": {
                    "source": "DashboardLineage"
                },
            }
        ],
    }


def test_normalizer_preserves_identity_semantics_and_safe_lineage() -> None:
    """The adapter keeps governed context without leaking samples or SQL text."""

    result = normalize_openmetadata_table_snapshot(
        tenant_id="tenant_acme",
        source_release="2.0.1",
        table=_table_payload(),
        lineage=_lineage_payload(),
    )

    assert result.projection_id == (
        f"urn:cwl:tenant_acme:sdp:openmetadata_table:{_TABLE_ID}"
    )
    assert result.source_authority == "openmetadata"
    assert result.source_release == "2.0.1"
    assert result.truth_status == "observed"
    assert result.external_entity_type == "table"
    assert result.external_entity_id == _TABLE_ID
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
    assert upstream.from_reference.external_entity_id == _UPSTREAM_ID
    assert upstream.to_reference.external_entity_id == _TABLE_ID
    assert upstream.source == "OpenLineage"
    assert upstream.pipeline_reference is not None
    assert upstream.pipeline_reference.external_entity_id == _PIPELINE_ID
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

    lineage = _lineage_payload()
    lineage["entity"] = _reference(
        _UPSTREAM_ID,
        "table",
        "warehouse.raw.orders",
    )

    with pytest.raises(
        OpenMetadataContractError,
        match="lineage entity does not match table id",
    ):
        normalize_openmetadata_table_snapshot(
            tenant_id="tenant_acme",
            source_release="2.0.1",
            table=_table_payload(),
            lineage=lineage,
        )


def test_normalizer_rejects_lineage_edges_with_unknown_endpoints() -> None:
    """Every lineage endpoint must resolve to the primary entity or a node."""

    lineage = _lineage_payload()
    lineage["upstreamEdges"][0]["fromEntity"] = (
        "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
    )

    with pytest.raises(
        OpenMetadataContractError,
        match="unknown lineage endpoint",
    ):
        normalize_openmetadata_table_snapshot(
            tenant_id="tenant_acme",
            source_release="2.0.1",
            table=_table_payload(),
            lineage=lineage,
        )


def test_normalizer_rejects_duplicate_column_paths() -> None:
    """Ambiguous column identities fail closed instead of being overwritten."""

    table = _table_payload()
    table["columns"].append(deepcopy(table["columns"][0]))

    with pytest.raises(
        OpenMetadataContractError,
        match="duplicate column path: order_id",
    ):
        normalize_openmetadata_table_snapshot(
            tenant_id="tenant_acme",
            source_release="2.0.1",
            table=table,
        )


def test_normalizer_rejects_excessive_column_nesting() -> None:
    """Hostile recursive schemas are bounded before exhausting the process."""

    table = _table_payload()
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
        normalize_openmetadata_table_snapshot(
            tenant_id="tenant_acme",
            source_release="2.0.1",
            table=table,
        )


def test_openmetadata_normalization_endpoint_returns_typed_projection() -> None:
    """The HTTP surface exposes the same deterministic ACL contract."""

    response = client.post(
        "/integrations/openmetadata/v1/table-snapshots:normalize",
        json={
            "tenant_id": "tenant_acme",
            "source_release": "2.0.1",
            "table": _table_payload(),
            "lineage": _lineage_payload(),
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["projection_id"].endswith(_TABLE_ID)
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
        json={
            "tenant_id": "tenant_acme",
            "source_release": "1.12.8",
            "table": _table_payload(),
        },
    )

    assert response.status_code == 422


def test_openmetadata_endpoint_returns_bounded_contract_error() -> None:
    """Malformed references produce a stable 400 without echoing source data."""

    table = _table_payload()
    table["id"] = "not-a-uuid"
    response = client.post(
        "/integrations/openmetadata/v1/table-snapshots:normalize",
        json={
            "tenant_id": "tenant_acme",
            "source_release": "2.0.1",
            "table": table,
        },
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "table.id must be a UUID"}
    assert "Governed order facts" not in json.dumps(response.json())
