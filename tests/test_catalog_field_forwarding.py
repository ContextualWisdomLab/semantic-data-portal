"""A field on the request contract must reach the stored dataset.

``Dataset`` has carried a ``license`` since the first commit, and neither
``DatasetCreateRequest`` nor ``DatasetPatchRequest`` exposed it, so a supplied
value was silently dropped. Measured before the repair::

    POST /catalog/datasets   {"license": "CC-BY-4.0"}  -> 200, stored "internal"
    PATCH /catalog/datasets/{id} {"license": "MIT"}    -> 200, stored "internal"
    every seeded dataset's license                     -> ["internal"]

A data catalog whose licence cannot be set is missing the field a diligence
reader checks first, and the ``metadata_completeness`` KPI's own definition
names ``license`` among the fields it counts - so the number was computed over a
field no caller could populate.

Exposing it was not enough: ``register_dataset`` built the ``Dataset`` from a
hand-written list of ``payload.<field>`` arguments and ignored the new one, so
the create path still stored the default. That constructor now spreads the
request's own fields, and the check below is mechanical rather than one test per
field - which is what let a field sit unreachable in the first place.
"""

from __future__ import annotations

from pathlib import Path
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sdp.api import app  # noqa: E402
from sdp_core.contracts import Dataset, DatasetCreateRequest, DatasetPatchRequest  # noqa: E402

client = TestClient(app, raise_server_exceptions=False)

# A value the field can take that differs from its default, per field name.
PROBE_VALUES: dict[str, object] = {
    "title": "제목 프로브",
    "description": "설명 프로브",
    "owner": "owner-probe",
    "steward": "steward-probe",
    "domain": "domain-probe",
    "source_system": "postgresql://probe.dw/probe_table",
    "sensitivity": "high",
    "update_frequency": "hourly",
    "license": "CC-BY-4.0",
    "quality_score": 0.42,
    "freshness_score": 0.43,
    "tags": ["tag-probe"],
    "terms": ["term-probe"],
    "related_datasets": ["crm-event"],
    "tenant_id": "demo",
    "lineage_inputs": ["crm-event"],
    "lineage_outputs": ["sales-order"],
}


def test_the_request_contracts_are_subsets_of_the_stored_model() -> None:
    """What makes spreading the payload into ``Dataset`` exact rather than lenient."""
    dataset_fields = set(Dataset.model_fields)
    assert set(DatasetCreateRequest.model_fields) <= dataset_fields, sorted(
        set(DatasetCreateRequest.model_fields) - dataset_fields
    )
    assert set(DatasetPatchRequest.model_fields) <= dataset_fields, sorted(
        set(DatasetPatchRequest.model_fields) - dataset_fields
    )


def test_register_dataset_forwards_every_request_field() -> None:
    """Mechanical, so a field added to the request cannot be ignored again."""
    import inspect

    from sdp import catalog

    # ``register_dataset`` is the locking wrapper; the constructor lives in the
    # ``_locked`` helper it delegates to, so both are read. Inspecting only the
    # public name silently passed the moment the mutation lock was introduced -
    # the wrapper names no payload field, so "no field is named" read as
    # "every field is spread".
    source = inspect.getsource(catalog.register_dataset) + inspect.getsource(
        catalog._register_dataset_locked
    )
    # The constructor spreads the payload, so no field needs naming - and if a
    # future edit goes back to naming them, this catches the one left out.
    if "payload.model_dump()" not in source:
        ignored = [
            field
            for field in DatasetCreateRequest.model_fields
            if field != "id" and f"payload.{field}" not in source
        ]
        assert not ignored, f"register_dataset ignores these request fields: {ignored}"


@pytest.mark.parametrize(
    "field",
    sorted(set(DatasetCreateRequest.model_fields) & set(PROBE_VALUES)),
)
def test_a_created_dataset_keeps_every_field_the_caller_sent(field: str) -> None:
    base = {
        "actor": "admin",
        "id": f"forward-create-{field}",
        "tenant_id": "demo",
        "title": "T",
        "description": "d",
        "owner": "a",
        "steward": "a",
        "domain": "s",
        "source_system": "postgresql://a.dw/t",
        "sensitivity": "low",
        "update_frequency": "daily",
        "quality_score": 0.9,
        "freshness_score": 0.9,
        "schema": [
            {"name": "c", "datatype": "string", "nullable_ratio": 0.0, "distinct_ratio": 1.0}
        ],
        "distributions": [{"id": "d1", "format": "table", "endpoint": "https://x/y"}],
    }
    base[field] = PROBE_VALUES[field]
    created = client.post("/catalog/datasets", json=base)
    assert created.status_code == 200, created.text
    stored = created.json()["dataset"]
    expected = PROBE_VALUES[field]
    if field == "source_system":
        # Redacted on every response by design; the stored value is checked via
        # the behaviour that depends on it rather than by reading it back.
        assert stored[field]
        return
    assert stored[field] == expected, (field, stored[field], expected)


@pytest.mark.parametrize(
    "field",
    sorted(set(DatasetPatchRequest.model_fields) & set(PROBE_VALUES)),
)
def test_a_patched_dataset_keeps_every_field_the_caller_sent(field: str) -> None:
    dataset_id = f"forward-patch-{field}"
    client.post(
        "/catalog/datasets",
        json={
            "actor": "admin",
            "id": dataset_id,
            "tenant_id": "demo",
            "title": "T",
            "description": "d",
            "owner": "a",
            "steward": "a",
            "domain": "s",
            "source_system": "postgresql://a.dw/t",
            "sensitivity": "low",
            "update_frequency": "daily",
            "quality_score": 0.9,
            "freshness_score": 0.9,
            "schema": [
                {"name": "c", "datatype": "string", "nullable_ratio": 0.0, "distinct_ratio": 1.0}
            ],
            "distributions": [{"id": "d1", "format": "table", "endpoint": "https://x/y"}],
        },
    )
    patched = client.patch(
        f"/catalog/datasets/{dataset_id}", json={"actor": "admin", field: PROBE_VALUES[field]}
    )
    assert patched.status_code == 200, patched.text
    stored = patched.json()["dataset"]
    if field == "source_system":
        assert stored[field]
        return
    assert stored[field] == PROBE_VALUES[field], (field, stored[field])


def test_the_license_is_what_the_kpi_definition_counts() -> None:
    """The field and the measurement that names it must agree.

    ``metadata_completeness``'s definition lists ``license`` among the fields it
    counts, which was being computed over a field no caller could set.
    """
    from sdp_core import enterprise_kpi_framework
    from sdp_core.contracts import REQUIRED_METADATA_FIELDS

    framework = enterprise_kpi_framework()
    kpi = next(
        item
        for item in framework.primary_kpis + framework.guardrail_kpis
        if item.id == "metadata_completeness"
    )
    assert "license" in kpi.definition
    assert "license" in DatasetCreateRequest.model_fields
    assert "license" in DatasetPatchRequest.model_fields
    # It is not in the required-field list, so it does not change the score; the
    # point is that a caller can now set what the definition advertises.
    assert "license" not in REQUIRED_METADATA_FIELDS


def test_the_metadata_completeness_target_is_compared() -> None:
    """The target was published with ``status: implemented`` and never compared.

    The only thresholds in the evidence path were 0.95 on
    ``metadata_validation_pass_rate`` - a different, stricter measure - and 0.7
    on ontology coverage.
    """
    from sdp_core import enterprise_kpi_framework

    framework = enterprise_kpi_framework()
    kpi = next(
        item
        for item in framework.primary_kpis + framework.guardrail_kpis
        if item.id == "metadata_completeness"
    )
    assert kpi.target == ">=90 percent mean metadata_completeness across datasets"
    assert kpi.status == "implemented"

    pack = client.get("/enterprise/evidence-pack").json()
    assert "mean_metadata_completeness" in pack
    assert pack["saleability_gates"]["metadata_completeness"] in {"pass", "gap"}
    expected = "pass" if pack["mean_metadata_completeness"] >= 0.90 else "gap"
    assert pack["saleability_gates"]["metadata_completeness"] == expected
