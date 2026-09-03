"""Boundary and hostile-input tests for the OpenMetadata adapter."""

from __future__ import annotations

from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

import sdp.openmetadata as om
from sdp.api import app


client = TestClient(app)

_TABLE_ID = "11111111-1111-4111-8111-111111111111"
_UPSTREAM_ID = "22222222-2222-4222-8222-222222222222"
_DOWNSTREAM_ID = "33333333-3333-4333-8333-333333333333"
_PIPELINE_ID = "44444444-4444-4444-8444-444444444444"


def _reference(
    reference_id: str = _TABLE_ID,
    entity_type: str = "table",
    name: str = "warehouse.sales.public.orders",
) -> dict[str, object]:
    """Build a minimal bounded OpenMetadata entity reference."""

    return {
        "id": reference_id,
        "type": entity_type,
        "name": name,
        "displayName": name.replace("_", " ").title(),
        "fullyQualifiedName": name,
        "href": f"https://metadata.example/api/v1/{entity_type}/{reference_id}",
    }


def _table_payload() -> dict[str, object]:
    """Build a table fixture containing both admitted and omitted metadata."""

    return {
        "id": _TABLE_ID,
        "name": "orders",
        "displayName": "Orders",
        "fullyQualifiedName": "warehouse.sales.public.orders",
        "description": "Governed order facts.",
        "version": 2.3,
        "updatedAt": 1_788_336_000_000,
        "updatedBy": "data_engineer",
        "tableType": "Regular",
        "serviceType": "Postgres",
        "columns": [
            {
                "name": "order_id",
                "dataType": "UUID",
                "constraint": "PRIMARY_KEY",
                "ordinalPosition": 1,
                "fullyQualifiedName": "warehouse.sales.public.orders.order_id",
                "tags": [{"tagFQN": "Identifier.Primary"}],
            },
            {
                "name": "customer",
                "dataType": "STRUCT",
                "ordinalPosition": 2,
                "children": [
                    {
                        "name": "email",
                        "dataType": "VARCHAR",
                        "constraint": "NULL",
                        "fullyQualifiedName": "warehouse.sales.public.orders.customer.email",
                    }
                ],
            },
        ],
        "owners": [_reference("55555555-5555-4555-8555-555555555555", "team", "data_platform")],
        "databaseSchema": _reference(
            "66666666-6666-4666-8666-666666666666",
            "databaseSchema",
            "warehouse.sales.public",
        ),
        "database": _reference("77777777-7777-4777-8777-777777777777", "database", "warehouse.sales"),
        "service": _reference("88888888-8888-4888-8888-888888888888", "databaseService", "warehouse"),
        "domains": [_reference("99999999-9999-4999-8999-999999999999", "domain", "sales")],
        "dataProducts": [
            _reference("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "dataProduct", "customer_360")
        ],
        "dataContract": _reference(
            "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
            "dataContract",
            "orders_contract",
        ),
        "tags": [{"tagFQN": "Tier.Tier1"}],
        "profile": {
            "timestamp": 1_788_336_000_000,
            "rowCount": 42,
            "columnCount": 2,
            "sizeInByte": 1_024,
        },
        "sourceHash": "0123456789abcdef",
        "sourceUrl": "https://warehouse.example/catalog/orders",
        "entityStatus": "Approved",
        "sampleData": {"columns": ["secret"], "rows": [["customer-secret-value"]]},
        "schemaDefinition": "CREATE TABLE orders (secret text)",
        "queries": ["SELECT * FROM customer_secret"],
        "joins": {"directTableJoins": [{"fullyQualifiedName": "private.customer"}]},
    }


def _lineage_payload() -> dict[str, object]:
    """Build a table and column lineage fixture."""

    return {
        "entity": _reference(),
        "nodes": [
            _reference(_UPSTREAM_ID, "table", "warehouse.raw.orders"),
            _reference(_DOWNSTREAM_ID, "dashboard", "sales.order_dashboard"),
        ],
        "upstreamEdges": [
            {
                "fromEntity": _UPSTREAM_ID,
                "toEntity": _TABLE_ID,
                "lineageDetails": {
                    "source": "OpenLineage",
                    "pipeline": _reference(_PIPELINE_ID, "pipeline", "load_orders"),
                    "sqlQuery": "SELECT secret FROM raw_orders",
                    "columnsLineage": [
                        {
                            "fromColumns": ["warehouse.raw.orders.order_id"],
                            "toColumn": "warehouse.sales.public.orders.order_id",
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
                "lineageDetails": {"source": "DashboardLineage"},
            }
        ],
    }


def _normalize(
    table: object | None = None,
    lineage: object | None = None,
    *,
    tenant_id: str = "tenant_acme",
    source_release: str = "2.0.1",
):
    """Normalize a fixture while allowing one field group to be replaced."""

    return om.normalize_openmetadata_table_snapshot(
        tenant_id=tenant_id,
        source_release=source_release,
        table=_table_payload() if table is None else table,
        lineage=lineage,
    )


def _assert_contract(message: str, function, *args, **kwargs) -> None:
    """Assert that a direct adapter call fails with the stable contract error."""

    with pytest.raises(om.OpenMetadataContractError, match=message):
        function(*args, **kwargs)


def test_scalar_container_and_url_guards() -> None:
    """Scalar coercion, active URLs, and embedded credentials fail closed."""

    _assert_contract("must be an object", om._require_mapping, [], "value")
    assert om._optional_mapping(None, "value") is None
    _assert_contract("must be an array", om._require_list, {}, "value", maximum=1)
    _assert_contract("exceeds 1 items", om._require_list, [1, 2], "value", maximum=1)
    assert om._optional_list(None, "value", maximum=1) == []

    _assert_contract("is required", om._text, None, "value", required=True)
    _assert_contract("must be a string", om._text, 1, "value")
    _assert_contract("is required", om._text, "", "value", required=True)
    _assert_contract("exceeds 1 characters", om._text, "xx", "value", maximum=1)
    _assert_contract("control characters", om._text, "x\x00", "value")
    assert om._text("x\n", "value") == "x\n"

    assert om._safe_url(None, "url") is None
    _assert_contract(r"HTTP\(S\)", om._safe_url, "file:///tmp/x", "url")
    _assert_contract(
        "must not contain credentials",
        om._safe_url,
        "https://user:pass@example.com/x",
        "url",
    )
    assert om._safe_url("http://example.com/x", "url") == "http://example.com/x"


def test_numeric_time_release_and_tenant_guards() -> None:
    """Counts, timestamps, releases, and tenant-scoped IDs are not coerced."""

    assert om._optional_non_negative_int(None, "count") is None
    for value in (True, -1, 1.2, "1"):
        _assert_contract("non-negative integer", om._optional_non_negative_int, value, "count")
    assert om._epoch_milliseconds(None, "when") is None
    _assert_contract("outside the supported", om._epoch_milliseconds, 10**30, "when")

    assert om._validate_source_release("2.0-release") == "2.0-release"
    _assert_contract("OpenMetadata 2.x", om._validate_source_release, "3.0.0")
    assert om._validate_tenant_id("tenant-1") == "tenant-1"
    _assert_contract("unsupported characters", om._validate_tenant_id, "tenant:1")


def test_payload_budget_guards(monkeypatch: pytest.MonkeyPatch) -> None:
    """Recursive, cyclic, text-heavy, and container-heavy payloads are bounded."""

    too_deep = current = []
    for _ in range(65):
        child: list[object] = []
        current.append(child)
        current = child
    _assert_contract("nesting exceeds 64", om._validate_payload_budget, too_deep)

    monkeypatch.setattr(om, "_MAX_PAYLOAD_TEXT_BYTES", 1)
    _assert_contract("payload text exceeds", om._validate_payload_budget, {"a": "xx"})

    list_cycle: list[object] = []
    list_cycle.append(list_cycle)
    _assert_contract("cyclic container", om._validate_payload_budget, list_cycle)

    mapping_cycle: dict[str, object] = {}
    mapping_cycle["self"] = mapping_cycle
    _assert_contract("cyclic container", om._validate_payload_budget, mapping_cycle)

    monkeypatch.setattr(om, "_MAX_PAYLOAD_CONTAINERS", 1)
    _assert_contract("exceeds 100000 containers", om._validate_payload_budget, {"a": {}})
    _assert_contract("exceeds 100000 containers", om._validate_payload_budget, [[]])


def test_reference_tag_and_profile_variants() -> None:
    """Optional references and safe profile aggregates retain unknown states."""

    basic = {"id": _TABLE_ID, "type": "table", "name": "orders"}
    normalized = om._reference(basic, "ref")
    assert normalized.label == "orders"
    assert normalized.href is None
    assert normalized.fully_qualified_name is None
    assert om._optional_reference(None, "ref") is None

    assert len(om._reference_list([deepcopy(basic), deepcopy(basic)], "refs")) == 1
    conflicting = [deepcopy(basic), {**basic, "name": "other"}]
    _assert_contract("conflicting reference id", om._reference_list, conflicting, "refs")

    assert om._tags([{"tagFQN": "A"}, {"tagFQN": "A"}], "tags") == ["A"]
    _assert_contract("must be an object", om._tags, ["A"], "tags")
    _assert_contract("is required", om._tags, [{}], "tags")

    assert om._profile_summary(None).row_count is None
    for field_name, value in (
        ("rowCount", -1),
        ("columnCount", True),
        ("sizeInByte", 1.5),
        ("timestamp", -1),
    ):
        _assert_contract("non-negative integer", om._profile_summary, {field_name: value})


def test_column_omissions_and_total_column_bound(monkeypatch: pytest.MonkeyPatch) -> None:
    """Column observations exclude profiles and bound aggregate nesting size."""

    table = _table_payload()
    table["columns"][0].update(
        {
            "profile": {"min": "secret"},
            "customMetrics": [{"name": "x"}],
            "extension": {"secret": "x"},
        }
    )
    result = _normalize(table)
    assert {
        "table.columns[].profile",
        "table.columns[].customMetrics",
        "table.columns[].extension",
    } <= set(result.omitted_fields)

    monkeypatch.setattr(om, "_MAX_COLUMNS", 2)
    bounded = _table_payload()
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
    _assert_contract("table.columns exceeds 2 items", _normalize, bounded)


def test_minimal_table_preserves_unknowns_and_rejects_bad_versions() -> None:
    """Missing optional facts remain unknown, while false version types fail."""

    minimal = {
        "id": _TABLE_ID,
        "name": "orders",
        "fullyQualifiedName": "svc.db.schema.orders",
        "columns": [],
    }
    result = _normalize(minimal, source_release="2.1.0-release")
    assert result.title == "orders"
    assert result.entity_version is None
    assert result.updated_at is None
    assert result.lineage_schema_uri is None
    assert result.lineage_edges == []
    assert result.profile_summary.row_count is None
    assert result.owner_references == []

    for value in (True, "2.3"):
        invalid = deepcopy(minimal)
        invalid["version"] = value
        _assert_contract("version must be numeric", _normalize, invalid)


def test_table_and_lineage_shape_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """Malformed tables, references, edges, and column mappings fail closed."""

    _assert_contract(
        "table must be an object",
        om.normalize_openmetadata_table_snapshot,
        tenant_id="tenant_acme",
        source_release="2.0.1",
        table=[],
    )

    table = _table_payload()
    table["columns"] = {}
    _assert_contract("table.columns must be an array", _normalize, table)

    table = _table_payload()
    table["columns"] = [{}]
    _assert_contract("name is required", _normalize, table)

    table = _table_payload()
    table["columns"] = [{"name": "x"}]
    _assert_contract("dataType is required", _normalize, table)

    lineage = _lineage_payload()
    lineage["nodes"] = [
        _reference(_UPSTREAM_ID, "table", "one"),
        _reference(_UPSTREAM_ID, "table", "two"),
    ]
    _assert_contract("conflicts with reference id", _normalize, _table_payload(), lineage)

    lineage = _lineage_payload()
    lineage["upstreamEdges"][0]["lineageDetails"] = "x"
    _assert_contract("must be an object", _normalize, _table_payload(), lineage)

    lineage = _lineage_payload()
    lineage["upstreamEdges"][0]["lineageDetails"]["columnsLineage"] = [{}]
    _assert_contract("fromColumns must be an array", _normalize, _table_payload(), lineage)

    lineage = _lineage_payload()
    lineage["upstreamEdges"][0]["lineageDetails"]["columnsLineage"][0]["fromColumns"] = [1]
    _assert_contract("must be a string", _normalize, _table_payload(), lineage)

    lineage = _lineage_payload()
    del lineage["upstreamEdges"][0]["lineageDetails"]["columnsLineage"][0]["toColumn"]
    _assert_contract("toColumn is required", _normalize, _table_payload(), lineage)

    monkeypatch.setattr(om, "_MAX_LINEAGE_EDGES", 1)
    _assert_contract("lineage edges exceed 1 items", _normalize, _table_payload(), _lineage_payload())


def test_lineage_defaults_and_column_deduplication() -> None:
    """Absent details retain manual provenance and duplicate columns collapse."""

    lineage = {
        "entity": _reference(),
        "nodes": [_reference(_UPSTREAM_ID, "table", "up")],
        "upstreamEdges": [{"fromEntity": _UPSTREAM_ID, "toEntity": _TABLE_ID}],
    }
    result = _normalize(lineage=lineage)
    edge = result.lineage_edges[0]
    assert edge.source == "Manual"
    assert edge.pipeline_reference is None
    assert edge.column_mappings == []
    assert edge.transformation_text_omitted is False

    lineage = _lineage_payload()
    details = lineage["upstreamEdges"][0]["lineageDetails"]
    details.pop("sqlQuery")
    details["columnsLineage"][0].pop("function")
    details["columnsLineage"][0]["fromColumns"].append("warehouse.raw.orders.order_id")
    edge = _normalize(lineage=lineage).lineage_edges[0]
    assert edge.column_mappings[0].from_columns == ["warehouse.raw.orders.order_id"]
    assert edge.transformation_text_omitted is False


def test_data_model_omissions_and_source_url_rules() -> None:
    """Free-form SQL and unsafe external links never enter the projection."""

    table = _table_payload()
    table["dataModel"] = {"rawSql": "secret", "sql": "secret"}
    table["extension"] = {"secret": "value"}
    result = _normalize(table)
    assert {
        "table.dataModel.rawSql",
        "table.dataModel.sql",
        "table.extension",
    } <= set(result.omitted_fields)

    partial = _table_payload()
    partial["dataModel"] = {"rawSql": "secret"}
    result = _normalize(partial)
    assert "table.dataModel.rawSql" in result.omitted_fields
    assert "table.dataModel.sql" not in result.omitted_fields

    invalid_url = _table_payload()
    invalid_url["sourceUrl"] = "file:///etc/passwd"
    _assert_contract(r"HTTP\(S\)", _normalize, invalid_url)

    credential_url = _table_payload()
    credential_url["owners"][0]["href"] = "https://user:pass@example.com/x"
    _assert_contract("must not contain credentials", _normalize, credential_url)


def test_endpoint_rejects_an_extra_request_field() -> None:
    """The HTTP contract rejects silent expansion of its trust boundary."""

    response = client.post(
        "/integrations/openmetadata/v1/table-snapshots:normalize",
        json={
            "tenant_id": "tenant_acme",
            "source_release": "2.0.1",
            "table": _table_payload(),
            "unexpected": True,
        },
    )

    assert response.status_code == 422
