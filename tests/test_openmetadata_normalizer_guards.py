"""Edge-case tests for OpenMetadata table and lineage normalization."""

from __future__ import annotations

from copy import deepcopy
from typing import Callable

import pytest

from sdp.openmetadata import OpenMetadataContractError
from sdp.openmetadata import normalizer

from openmetadata_test_support import (
    TABLE_ID,
    UPSTREAM_ID,
    lineage_payload,
    normalize_fixture,
    reference_payload,
    table_payload,
)


def _assert_contract(
    message: str,
    function: Callable[..., object],
    *args: object,
    **kwargs: object,
) -> None:
    """Assert a normalizer call fails with the bounded error type."""

    with pytest.raises(OpenMetadataContractError, match=message):
        function(*args, **kwargs)


def test_reference_tag_and_profile_variants() -> None:
    """Unknown optional metadata stays unknown and duplicate labels are stable."""

    basic = {
        "id": TABLE_ID,
        "type": "table",
        "name": "orders",
    }
    normalized = normalizer._reference(basic, "ref")
    assert normalized.label == "orders"
    assert normalized.href is None
    assert normalized.fully_qualified_name is None
    assert normalizer._optional_reference(None, "ref") is None

    same = [deepcopy(basic), deepcopy(basic)]
    assert len(normalizer._reference_list(same, "refs")) == 1
    conflicting = [deepcopy(basic), {**basic, "name": "other"}]
    _assert_contract(
        "conflicts with reference id",
        normalizer._reference_list,
        conflicting,
        "refs",
    )

    assert normalizer._tags(
        [{"tagFQN": "A"}, {"tagFQN": "A"}],
        "tags",
    ) == ["A"]
    _assert_contract(
        "must be an object",
        normalizer._tags,
        ["A"],
        "tags",
    )
    _assert_contract(
        "is required",
        normalizer._tags,
        [{}],
        "tags",
    )

    assert normalizer._profile_summary(None).row_count is None
    for field_name, value in (
        ("rowCount", -1),
        ("columnCount", True),
        ("sizeInByte", 1.5),
        ("timestamp", -1),
    ):
        _assert_contract(
            "non-negative integer",
            normalizer._profile_summary,
            {field_name: value},
        )


def test_column_omissions_and_total_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Column detail leakage and deeply expanded schemas are bounded."""

    table = table_payload()
    table["columns"][0].update(
        {
            "profile": {"min": "secret"},
            "customMetrics": [{"name": "x"}],
            "extension": {"secret": "x"},
        }
    )
    result = normalize_fixture(table)
    assert {
        "table.columns[].profile",
        "table.columns[].customMetrics",
        "table.columns[].extension",
    } <= set(result.omitted_fields)

    monkeypatch.setattr(normalizer, "_MAX_COLUMNS", 2)
    bounded = table_payload()
    bounded["columns"] = [
        {
            "name": "root",
            "dataType": "STRUCT",
            "children": [
                {"name": "a", "dataType": "STRING"},
                {"name": "b", "dataType": "STRING"},
            ],
        }
    ]
    _assert_contract(
        "table.columns exceeds 2 items",
        normalize_fixture,
        bounded,
    )


def test_minimal_table_and_version_guards() -> None:
    """A sparse valid table keeps unknowns while invalid versions fail."""

    minimal = {
        "id": TABLE_ID,
        "name": "orders",
        "fullyQualifiedName": "svc.db.schema.orders",
        "columns": [],
    }
    result = normalize_fixture(minimal, source_release="2.0.1-release")
    assert result.source_release == "2.0.1"
    assert result.title == "orders"
    assert result.entity_version is None
    assert result.updated_at is None
    assert result.lineage_schema_uri is None
    assert result.lineage_edges == []
    assert result.profile_summary.row_count is None
    assert result.owner_references == []
    assert result.tag_fqns == []

    for value in (True, "2.3"):
        invalid = deepcopy(minimal)
        invalid["version"] = value
        _assert_contract(
            "version must be numeric",
            normalize_fixture,
            invalid,
        )


def test_table_and_column_shape_errors() -> None:
    """Malformed table and column containers fail before projection."""

    _assert_contract(
        "table must be an object",
        normalizer.normalize_openmetadata_table_snapshot,
        tenant_id="tenant_acme",
        source_release="2.0.1",
        table=[],
    )

    table = table_payload()
    table["columns"] = {}
    _assert_contract(
        "table.columns must be an array",
        normalize_fixture,
        table,
    )

    table = table_payload()
    table["columns"] = [{}]
    _assert_contract(
        "name is required",
        normalize_fixture,
        table,
    )

    table = table_payload()
    table["columns"] = [{"name": "x"}]
    _assert_contract(
        "dataType is required",
        normalize_fixture,
        table,
    )


def test_reference_and_lineage_shape_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Conflicting nodes and malformed lineage detail fail closed."""

    lineage = lineage_payload()
    lineage["nodes"] = [
        reference_payload(UPSTREAM_ID, "table", "one"),
        reference_payload(UPSTREAM_ID, "table", "two"),
    ]
    _assert_contract(
        "conflicts with reference id",
        normalize_fixture,
        table_payload(),
        lineage,
    )

    lineage = lineage_payload()
    lineage["upstreamEdges"][0]["lineageDetails"] = "x"
    _assert_contract(
        "must be an object",
        normalize_fixture,
        table_payload(),
        lineage,
    )

    lineage = lineage_payload()
    lineage["upstreamEdges"][0]["lineageDetails"][
        "columnsLineage"
    ] = [{}]
    _assert_contract(
        "fromColumns must be an array",
        normalize_fixture,
        table_payload(),
        lineage,
    )

    lineage = lineage_payload()
    lineage["upstreamEdges"][0]["lineageDetails"][
        "columnsLineage"
    ][0]["fromColumns"] = [1]
    _assert_contract(
        "must be a string",
        normalize_fixture,
        table_payload(),
        lineage,
    )

    lineage = lineage_payload()
    del lineage["upstreamEdges"][0]["lineageDetails"][
        "columnsLineage"
    ][0]["toColumn"]
    _assert_contract(
        "toColumn is required",
        normalize_fixture,
        table_payload(),
        lineage,
    )

    monkeypatch.setattr(normalizer, "_MAX_LINEAGE_EDGES", 1)
    _assert_contract(
        "lineage edges exceed 1 items",
        normalize_fixture,
        table_payload(),
        lineage_payload(),
    )


def test_lineage_defaults_and_column_deduplication() -> None:
    """Missing lineage details retain manual provenance and stable columns."""

    lineage = {
        "entity": reference_payload(),
        "nodes": [
            reference_payload(
                UPSTREAM_ID,
                "table",
                "upstream",
            )
        ],
        "upstreamEdges": [
            {
                "fromEntity": UPSTREAM_ID,
                "toEntity": TABLE_ID,
            }
        ],
    }
    edge = normalize_fixture(lineage=lineage).lineage_edges[0]
    assert edge.source == "Manual"
    assert edge.pipeline_reference is None
    assert edge.column_mappings == []
    assert edge.transformation_text_omitted is False

    lineage = lineage_payload()
    details = lineage["upstreamEdges"][0]["lineageDetails"]
    details.pop("sqlQuery")
    details["columnsLineage"][0].pop("function")
    details["columnsLineage"][0]["fromColumns"].append(
        "warehouse.raw.orders.order_id"
    )
    edge = normalize_fixture(lineage=lineage).lineage_edges[0]
    assert edge.column_mappings[0].from_columns == [
        "warehouse.raw.orders.order_id"
    ]
    assert edge.transformation_text_omitted is False


def test_data_model_omissions_and_source_url_rules() -> None:
    """Free-form SQL and unsafe external links never enter the projection."""

    table = table_payload()
    table["dataModel"] = {
        "rawSql": "secret",
        "sql": "secret",
    }
    table["extension"] = {"secret": "value"}
    result = normalize_fixture(table)
    assert {
        "table.dataModel.rawSql",
        "table.dataModel.sql",
        "table.extension",
    } <= set(result.omitted_fields)

    partial = table_payload()
    partial["dataModel"] = {"rawSql": "secret"}
    result = normalize_fixture(partial)
    assert "table.dataModel.rawSql" in result.omitted_fields
    assert "table.dataModel.sql" not in result.omitted_fields

    invalid_url = table_payload()
    invalid_url["sourceUrl"] = "file:///etc/passwd"
    _assert_contract(
        r"HTTP\(S\)",
        normalize_fixture,
        invalid_url,
    )

    credential_url = table_payload()
    credential_url["owners"][0]["href"] = (
        "https://user:pass@example.com/x"
    )
    _assert_contract(
        "must not contain credentials",
        normalize_fixture,
        credential_url,
    )
