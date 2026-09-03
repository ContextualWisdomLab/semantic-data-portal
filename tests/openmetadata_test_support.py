"""CWL-authored fixtures for OpenMetadata adapter tests."""

from __future__ import annotations

from typing import Any

from sdp.openmetadata import normalize_openmetadata_table_snapshot

TABLE_ID = "11111111-1111-4111-8111-111111111111"
UPSTREAM_ID = "22222222-2222-4222-8222-222222222222"
DOWNSTREAM_ID = "33333333-3333-4333-8333-333333333333"
PIPELINE_ID = "44444444-4444-4444-8444-444444444444"


def reference_payload(
    reference_id: str = TABLE_ID,
    entity_type: str = "table",
    name: str = "warehouse.sales.public.orders",
) -> dict[str, Any]:
    """Build a representative OpenMetadata entity reference."""

    return {
        "id": reference_id,
        "type": entity_type,
        "name": name,
        "displayName": name.replace("_", " ").title(),
        "fullyQualifiedName": name,
        "href": (
            f"https://metadata.example/api/v1/"
            f"{entity_type}/{reference_id}"
        ),
    }


def table_payload() -> dict[str, Any]:
    """Build a table carrying both admitted and deliberately omitted fields."""

    return {
        "id": TABLE_ID,
        "name": "orders",
        "displayName": "Orders",
        "fullyQualifiedName": "warehouse.sales.public.orders",
        "description": "Governed order facts.",
        "version": 2.3,
        "updatedAt": 1_788_336_000_000,
        "updatedBy": "data_engineer",
        "href": f"https://metadata.example/api/v1/tables/{TABLE_ID}",
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
            reference_payload(
                "55555555-5555-4555-8555-555555555555",
                "team",
                "data_platform",
            )
        ],
        "databaseSchema": reference_payload(
            "66666666-6666-4666-8666-666666666666",
            "databaseSchema",
            "warehouse.sales.public",
        ),
        "database": reference_payload(
            "77777777-7777-4777-8777-777777777777",
            "database",
            "warehouse.sales",
        ),
        "service": reference_payload(
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
            reference_payload(
                "99999999-9999-4999-8999-999999999999",
                "domain",
                "sales",
            )
        ],
        "dataProducts": [
            reference_payload(
                "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
                "dataProduct",
                "customer_360",
            )
        ],
        "dataContract": reference_payload(
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


def lineage_payload() -> dict[str, Any]:
    """Build table and column lineage with sensitive transformation text."""

    return {
        "entity": reference_payload(),
        "nodes": [
            reference_payload(
                UPSTREAM_ID,
                "table",
                "warehouse.raw.orders",
            ),
            reference_payload(
                DOWNSTREAM_ID,
                "dashboard",
                "sales.order_dashboard",
            ),
        ],
        "upstreamEdges": [
            {
                "fromEntity": UPSTREAM_ID,
                "toEntity": TABLE_ID,
                "lineageDetails": {
                    "source": "OpenLineage",
                    "pipeline": reference_payload(
                        PIPELINE_ID,
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
                "fromEntity": TABLE_ID,
                "toEntity": DOWNSTREAM_ID,
                "lineageDetails": {
                    "source": "DashboardLineage"
                },
            }
        ],
    }


def normalize_fixture(
    table: object | None = None,
    lineage: object | None = None,
    *,
    tenant_id: str = "tenant_acme",
    source_release: str = "2.0.1",
):
    """Normalize fixtures while allowing a caller to replace either payload."""

    return normalize_openmetadata_table_snapshot(
        tenant_id=tenant_id,
        source_release=source_release,
        table=table_payload() if table is None else table,
        lineage=lineage,
    )
