from __future__ import annotations

from sdp_core import buyer_demo_datasets
from sdp_core.contracts import DatasetDistribution


def test_dataset_distribution_owns_semantic_identifiers() -> None:
    distribution = DatasetDistribution(
        distribution_id="dist-customer-master",
        distribution_format="postgresql.table",
        distribution_endpoint="https://example.internal/api/table/customer_master",
    )

    assert set(DatasetDistribution.model_fields) == {
        "distribution_id",
        "distribution_format",
        "distribution_endpoint",
    }
    assert distribution.distribution_id == "dist-customer-master"
    assert distribution.distribution_format == "postgresql.table"
    assert str(distribution.distribution_endpoint) == "https://example.internal/api/table/customer_master"


def test_dataset_distribution_preserves_legacy_wire_and_python_compatibility() -> None:
    distribution = DatasetDistribution(
        id="dist-customer-master",
        format="postgresql.table",
        endpoint="https://example.internal/api/table/customer_master",
    )

    assert distribution.id == distribution.distribution_id
    assert distribution.format == distribution.distribution_format
    assert distribution.endpoint == distribution.distribution_endpoint

    distribution.id = "dist-customer-master-v2"
    distribution.format = "parquet"
    assert distribution.distribution_id == "dist-customer-master-v2"
    assert distribution.distribution_format == "parquet"

    wire_payload = distribution.model_dump(mode="json", by_alias=True)
    assert wire_payload == {
        "id": "dist-customer-master-v2",
        "format": "parquet",
        "endpoint": "https://example.internal/api/table/customer_master",
    }
    assert "distribution_id" not in wire_payload
    assert "distribution_format" not in wire_payload
    assert "distribution_endpoint" not in wire_payload


def test_dataset_distribution_serializer_honors_field_filters() -> None:
    distribution = DatasetDistribution(
        distribution_id="dist-customer-master",
        distribution_format="postgresql.table",
        distribution_endpoint="https://example.internal/api/table/customer_master",
    )

    assert distribution.model_dump(include={"distribution_id"}, mode="json") == {
        "id": "dist-customer-master",
    }
    assert distribution.model_dump(exclude={"distribution_endpoint"}, mode="json") == {
        "id": "dist-customer-master",
        "format": "postgresql.table",
    }


def test_nested_dataset_dump_keeps_existing_distribution_wire_keys() -> None:
    dataset_payload = buyer_demo_datasets()[0].model_dump(mode="json")
    distribution_payload = dataset_payload["distributions"][0]

    assert set(distribution_payload) == {"id", "format", "endpoint"}
    assert distribution_payload["id"] == "dist-crm-customer"
    assert distribution_payload["format"] == "postgresql.table"
    assert distribution_payload["endpoint"] == "https://example.internal/api/table/crm_customer_master"
