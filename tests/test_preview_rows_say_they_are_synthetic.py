"""The preview served fabricated rows with no machine-readable provenance.

``POST /browse/{id}/preview`` is a buyer's first look at their own dataset. Its
rows are a fixed two-row synthetic sample projected onto the declared schema, and
the only disclosure was one Korean sentence (``sampling_note``). The sibling
data-bearing route labels its mock in full - ``/browse/query`` publishes
``execution.measurement_status: "mock_execution_no_real_data"`` beside
``rows_source: "fixed_mock_sample"`` and
``row_count_source: "mock_row_cap_below_catalog_profile_estimate"`` - so an
integrator who correctly learned there that simulated figures are labelled had
every reason to read these rows as real. Measured at ``57ba6e3``::

    crm-customer-master  has_more False  row_count 2  profile row_count 1,200,000
    crm-event            has_more False  row_count 2  profile row_count 54,000,000
    sales-order          has_more False  row_count 2  profile row_count 8,700,000
    provenance keys in the response: ['sampling_note']

``has_more: false`` with two rows says the preview showed everything, while the
same product's profile route says otherwise for the same dataset.

And the fallback contradicts the schema it is projected onto. ``_SAMPLE_DATATYPE_VALUES``
covers boolean/date/decimal/integer/iri/timestamp; a column declared ``double``
or ``bigint`` falls through to ``f"{column.name}-sample-{n}"``, so a dataset
declaring ``touch_revenue_krw: double`` was served the string
``"touch_revenue_krw-sample-1"`` - a value that is not merely synthetic but
unparseable as its own declared type.
"""

from __future__ import annotations

from typing import Any

import pytest

from fastapi.testclient import TestClient

from sdp import browse
from sdp.api import app


client = TestClient(app)

SEEDED = ("crm-customer-master", "crm-event", "sales-order")

# Declared types the fallback must shape its value like, with the family each
# belongs to. These are the spellings a warehouse actually declares.
TYPED_COLUMNS = (
    ("touch_revenue_krw", "double"),
    ("touch_count", "bigint"),
    ("ratio_value", "float"),
    ("row_total", "numeric"),
    ("is_active", "bool"),
    ("seen_at", "datetime"),
)


def _register_typed_dataset(dataset_id: str) -> None:
    """Register one dataset declaring the numeric and temporal types above."""
    body: dict[str, Any] = {
        "id": dataset_id,
        "tenant_id": "demo",
        "title": "타입 프로브",
        "description": "선언 타입과 샘플 값의 모양을 비교하는 프로브",
        "owner": "data-admin",
        "steward": "data-admin",
        "domain": "마케팅",
        "source_system": "s3://analytics/events/touchpoints",
        "sensitivity": "low",
        "update_frequency": "daily",
        "quality_score": 0.9,
        "freshness_score": 0.9,
        "schema": [
            {"name": name, "datatype": datatype, "nullable_ratio": 0.0, "distinct_ratio": 0.9}
            for name, datatype in TYPED_COLUMNS
        ],
        "distributions": [
            {"id": f"{dataset_id}-csv", "format": "csv", "endpoint": "https://files.example.internal/t.csv"}
        ],
        "profile": {"row_count": 125000},
        "actor": "data-admin",
        "reason": "probe",
    }
    created = client.post("/catalog/datasets", json=body)
    assert created.status_code == 200, created.text
    published = client.post(
        f"/catalog/datasets/{dataset_id}/publish", json={"actor": "data-admin", "reason": "probe"}
    )
    assert published.status_code == 200, published.text


def _preview(dataset_id: str) -> dict[str, Any]:
    response = client.post(
        f"/browse/{dataset_id}/preview",
        json={"user": "admin", "purpose": "analysis", "limit": 10},
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize("dataset_id", SEEDED)
def test_the_preview_says_its_rows_are_not_source_rows(dataset_id: str) -> None:
    """One vocabulary across both data-bearing routes."""
    body = _preview(dataset_id)
    provenance = body.get("sample_provenance")
    assert provenance, f"the preview publishes no provenance block: {sorted(body)}"
    assert provenance["rows_source"] == "fixed_mock_sample", provenance
    assert "no_real_data" in provenance["measurement_status"], provenance
    assert provenance["row_count_source"], provenance


@pytest.mark.parametrize("dataset_id", SEEDED)
def test_has_more_cannot_be_read_as_having_seen_the_dataset(dataset_id: str) -> None:
    """The declared source size travels with the claim that there is no more."""
    body = _preview(dataset_id)
    provenance = body["sample_provenance"]
    profile = client.get(f"/catalog/datasets/{dataset_id}/profile?user=admin").json()
    declared = profile.get("row_count")
    assert declared and declared > body["row_count"], (declared, body["row_count"])
    assert provenance["declared_source_row_count"] == declared, provenance
    assert provenance["sample_row_count"] == len(body["rows"]), provenance
    # And the note is still there, in a language a person reads.
    assert body["sampling_note"], body


def test_the_sibling_query_route_keeps_its_own_labels() -> None:
    """The preview borrows that vocabulary; it must not take it away."""
    response = client.post(
        "/browse/query",
        json={
            "user": "analyst",
            "dataset_ids": ["crm-customer-master"],
            "language": "SQL",
            "query": "select customer_id from crm_customer_master",
            "purpose": "analysis",
        },
    )
    assert response.status_code == 200, response.text
    execution = response.json()["execution"]
    assert execution["measurement_status"] == "mock_execution_no_real_data", execution
    assert execution["rows_source"] == "fixed_mock_sample", execution


def test_a_declared_numeric_column_is_not_served_its_own_name() -> None:
    """The fallback must at least be shaped like the type it is projected onto."""
    _register_typed_dataset("type-probe-shaped")
    rows = _preview("type-probe-shaped")["rows"]
    assert rows, "the probe returned no rows"
    row = rows[0]
    for name, datatype in TYPED_COLUMNS:
        value = row[name]
        assert name not in str(value), (
            f"{name} is declared {datatype} and was served its own column name: {value!r}"
        )
    # Numeric families parse as numbers; the temporal one parses as a timestamp.
    assert float(row["touch_revenue_krw"]) == float(row["touch_revenue_krw"])
    assert int(row["touch_count"]) == int(row["touch_count"])
    assert float(row["ratio_value"]) == float(row["ratio_value"])
    assert float(row["row_total"]) == float(row["row_total"])
    assert str(row["is_active"]).lower() in {"true", "false"}
    assert str(row["seen_at"]).startswith("20")


def test_a_column_whose_type_the_sample_cannot_match_is_named() -> None:
    """Honest about the residue rather than silently shipping a mismatch."""
    body_id = "type-probe-unknown"
    body: dict[str, Any] = {
        "id": body_id,
        "tenant_id": "demo",
        "title": "미지 타입 프로브",
        "description": "샘플이 모양을 맞출 수 없는 선언 타입",
        "owner": "data-admin",
        "steward": "data-admin",
        "domain": "마케팅",
        "source_system": "s3://analytics/events/touchpoints",
        "sensitivity": "low",
        "update_frequency": "daily",
        "quality_score": 0.9,
        "freshness_score": 0.9,
        "schema": [
            {"name": "geo_shape", "datatype": "geography", "nullable_ratio": 0.0, "distinct_ratio": 0.9},
            {"name": "customer_id", "datatype": "string", "nullable_ratio": 0.0, "distinct_ratio": 1.0},
        ],
        "distributions": [
            {"id": f"{body_id}-csv", "format": "csv", "endpoint": "https://files.example.internal/t.csv"}
        ],
        "actor": "data-admin",
        "reason": "probe",
    }
    assert client.post("/catalog/datasets", json=body).status_code == 200
    assert (
        client.post(f"/catalog/datasets/{body_id}/publish", json={"actor": "data-admin", "reason": "p"}).status_code
        == 200
    )
    provenance = _preview(body_id)["sample_provenance"]
    assert provenance["untyped_sample_columns"] == ["geo_shape"], provenance


def test_a_dataset_with_no_declared_row_count_publishes_null_not_zero() -> None:
    """Absent is not empty.

    ``0`` would claim the source holds no rows, which is a statement about the
    data rather than about the catalog's metadata. The mutation that returned
    ``0`` for an absent or unparseable profile went uncaught until this case
    existed, because every other probe here declares a row count.
    """
    for dataset_id, profile in (
        ("rowcount-absent", {}),
        ("rowcount-unparseable", {"row_count": "not a number"}),
        ("rowcount-boolean", {"row_count": True}),
    ):
        body: dict[str, Any] = {
            "id": dataset_id,
            "tenant_id": "demo",
            "title": "행 수 프로브",
            "description": "선언된 행 수가 없거나 해석할 수 없는 경우",
            "owner": "data-admin",
            "steward": "data-admin",
            "domain": "마케팅",
            "source_system": "s3://analytics/events/touchpoints",
            "sensitivity": "low",
            "update_frequency": "daily",
            "quality_score": 0.9,
            "freshness_score": 0.9,
            "schema": [
                {"name": "customer_id", "datatype": "string", "nullable_ratio": 0.0, "distinct_ratio": 1.0}
            ],
            "distributions": [
                {
                    "id": f"{dataset_id}-csv",
                    "format": "csv",
                    "endpoint": "https://files.example.internal/t.csv",
                }
            ],
            "profile": profile,
            "actor": "data-admin",
            "reason": "probe",
        }
        assert client.post("/catalog/datasets", json=body).status_code == 200, dataset_id
        assert (
            client.post(
                f"/catalog/datasets/{dataset_id}/publish",
                json={"actor": "data-admin", "reason": "p"},
            ).status_code
            == 200
        ), dataset_id
        provenance = _preview(dataset_id)["sample_provenance"]
        assert provenance["declared_source_row_count"] is None, (dataset_id, provenance)


def test_the_family_table_is_the_one_the_value_picker_reads() -> None:
    """Structural: a second spelling table is how the two drift apart."""
    import inspect

    code = "\n".join(
        line
        for line in inspect.getsource(browse._sample_value).splitlines()
        if not line.lstrip().startswith("#")
    )
    assert "_sample_datatype_family" in code, code
    assert browse._sample_datatype_family("DOUBLE PRECISION") == "decimal", "case and modifiers"
    assert browse._sample_datatype_family("bigint") == "integer"
    assert browse._sample_datatype_family("geography") is None
