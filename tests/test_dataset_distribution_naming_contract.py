from __future__ import annotations

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

    wire_payload = distribution.model_dump(mode="json", by_alias=True)
    assert wire_payload == {
        "id": "dist-customer-master",
        "format": "postgresql.table",
        "endpoint": "https://example.internal/api/table/customer_master",
    }
    assert "distribution_id" not in wire_payload
    assert "distribution_format" not in wire_payload
    assert "distribution_endpoint" not in wire_payload
