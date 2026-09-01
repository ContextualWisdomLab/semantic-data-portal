from __future__ import annotations

from sdp_core import buyer_demo_datasets
from sdp_core.contracts import ColumnMetadata


def test_column_metadata_owns_semantic_column_name() -> None:
    column = ColumnMetadata(
        column_name="customer_id",
        datatype="string",
        nullable_ratio=0.0,
        distinct_ratio=1.0,
    )

    assert "column_name" in ColumnMetadata.model_fields
    assert "name" not in ColumnMetadata.model_fields
    assert column.column_name == "customer_id"


def test_column_metadata_preserves_legacy_name_wire_compatibility() -> None:
    column = ColumnMetadata(
        name="customer_email",
        datatype="string",
        nullable_ratio=0.1,
        distinct_ratio=0.9,
    )

    assert column.column_name == "customer_email"
    assert column.name == "customer_email"

    column.name = "customer_email_hash"
    assert column.column_name == "customer_email_hash"

    wire_payload = column.model_dump(mode="json", by_alias=True)
    assert wire_payload["name"] == "customer_email_hash"
    assert "column_name" not in wire_payload


def test_column_metadata_serializer_honors_field_filters() -> None:
    column = ColumnMetadata(
        column_name="customer_id",
        datatype="string",
        nullable_ratio=0.0,
        distinct_ratio=1.0,
    )

    assert column.model_dump(include={"column_name"}, mode="json") == {
        "name": "customer_id",
    }
    filtered_payload = column.model_dump(exclude={"column_name"}, mode="json")
    assert "name" not in filtered_payload
    assert "column_name" not in filtered_payload
    assert filtered_payload["datatype"] == "string"


def test_nested_dataset_dump_keeps_existing_column_name_wire_key() -> None:
    dataset_payload = buyer_demo_datasets()[0].model_dump(mode="json")
    column_payload = dataset_payload["schema"][0]

    assert "name" in column_payload
    assert "column_name" not in column_payload
