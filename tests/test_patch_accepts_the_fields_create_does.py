"""A field create accepts and patch does not is a 200 that stores nothing.

``license`` was the first instance, and ``DatasetCreateRequest``'s own comment
records it: "a supplied value was silently dropped: ``POST /catalog/datasets``
with ``license: "CC-BY-4.0"`` answered 200 and stored ``None``". It was fixed by
adding the field to both request models. ``distributions`` was the same omission
one field later, and the worse one, because it is the field a refusal tells a
steward to add. Measured at ``dba2403``::

    POST  /catalog/datasets      distributions: [csv]         -> 200, stored
    PATCH /catalog/datasets/{id} distributions: [pg.table]    -> 200
    stored distributions                                      -> [csv]   (unchanged)
    source_relation_name(dataset)                             -> None
    POST  /llm/draft-query                                    -> 400 (still)

Three fields stay deliberately unpatchable, and this file is where that decision
is declared rather than inferred from an omission: ``id`` and ``tenant_id`` are
identity (a patch that moves a dataset between tenants is a different operation
with a different decision), and ``owner`` is an ownership transfer, which this
product has no reviewed path for. Any *other* divergence fails here, so the next
new create field is an explicit publish-or-withhold decision instead of a silent
200.
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from sdp import catalog, orchestrator
from sdp.api import app
from sdp_core.contracts import DatasetCreateRequest, DatasetPatchRequest


client = TestClient(app)

# Create-only on purpose, each with the reason it is not a patch.
UNPATCHABLE_BY_DESIGN = {
    "id": "identity: a new id is a new dataset",
    "tenant_id": "identity: moving tenants is a different, separately decided operation",
    "owner": "ownership transfer: no reviewed path exists for it",
}

DATASET_ID = "patch-parity-probe"


def _register(**overrides: Any) -> None:
    """Register one probe dataset with a non-relational distribution."""
    body: dict[str, Any] = {
        "id": DATASET_ID,
        "tenant_id": "demo",
        "title": "패치 패리티 프로브",
        "description": "create/patch 계약 패리티 측정용",
        "owner": "data-admin",
        "steward": "data-admin",
        "domain": "고객",
        "source_system": "s3://analytics/events/orders",
        "sensitivity": "low",
        "update_frequency": "daily",
        "quality_score": 0.9,
        "freshness_score": 0.9,
        # Non-empty on purpose: with no tags, "cleared" and "never set" are the
        # same observation, and the mutation that stopped clearing came back
        # green against an empty fixture.
        "tags": ["고객", "프로브"],
        "schema": [
            {"name": "customer_id", "datatype": "string", "nullable_ratio": 0.0, "distinct_ratio": 1.0}
        ],
        "distributions": [
            {"id": "d-csv", "format": "csv", "endpoint": "https://files.example.internal/x.csv"}
        ],
        "actor": "data-admin",
        "reason": "probe",
    }
    body.update(overrides)
    created = client.post("/catalog/datasets", json=body)
    assert created.status_code == 200, created.text


def test_the_two_request_models_diverge_only_where_declared() -> None:
    """Structural: the omission that caused this was invisible at the surface."""
    create_fields = set(DatasetCreateRequest.model_fields)
    patch_fields = set(DatasetPatchRequest.model_fields)
    create_only = create_fields - patch_fields
    assert create_only == set(UNPATCHABLE_BY_DESIGN), (
        "a field `POST /catalog/datasets` accepts cannot be patched, and a patch "
        "carrying it answers 200 and stores nothing. Add it to "
        f"DatasetPatchRequest, or declare it here with its reason: {sorted(create_only)}"
    )


def test_a_patched_distribution_is_stored() -> None:
    """The write the refusal's remedy depends on."""
    _register()
    patched = client.patch(
        f"/catalog/datasets/{DATASET_ID}",
        json={
            "actor": "data-admin",
            "reason": "relation 선언",
            "distributions": [
                {
                    "id": "d-table",
                    "format": f"{orchestrator.DRAFT_SQL_DIALECT}.table",
                    "endpoint": "https://warehouse.example.internal/api/table/events_orders",
                }
            ],
        },
    )
    assert patched.status_code == 200, patched.text
    stored = catalog.get_dataset(DATASET_ID)
    assert [str(distribution.format) for distribution in stored.distributions] == [
        f"{orchestrator.DRAFT_SQL_DIALECT}.table"
    ], stored.distributions
    assert orchestrator.source_relation_name(stored) == "events_orders"


def test_a_patch_that_omits_distributions_leaves_them_alone() -> None:
    """Absent is not empty: the other collections behave this way already."""
    _register()
    before = [d.id for d in catalog.get_dataset(DATASET_ID).distributions]
    patched = client.patch(
        f"/catalog/datasets/{DATASET_ID}",
        json={"actor": "data-admin", "reason": "제목만 수정", "title": "프로브 v2"},
    )
    assert patched.status_code == 200, patched.text
    assert [d.id for d in catalog.get_dataset(DATASET_ID).distributions] == before


def test_an_explicit_null_leaves_any_field_alone_and_an_empty_list_clears_it() -> None:
    """``None`` is "not supplied" for every field; ``[]`` is how a caller clears.

    Driven over a field that was in the old skip list (``tags``), one that never
    was (``title``), and ``distributions``, because the list was dead code: both
    branches skipped a ``None`` identically, so membership asserted a rule it did
    not enforce. Removing it is safe only if this holds for all three.
    """
    _register()
    before = catalog.get_dataset(DATASET_ID)
    # One real change travels with the nulls, so the expected answer is 200 and
    # not "it errored, therefore nothing changed" - which is what the first
    # version of this guard accepted, and why the mutation that wrote nulls
    # straight into the model came back green.
    nulled = client.patch(
        f"/catalog/datasets/{DATASET_ID}",
        json={
            "actor": "data-admin",
            "reason": "null 전송",
            "distributions": None,
            "tags": None,
            "title": None,
            "steward": "data-steward",
        },
    )
    assert nulled.status_code == 200, nulled.text
    after = catalog.get_dataset(DATASET_ID)
    assert after.steward == "data-steward", after.steward
    assert [d.id for d in after.distributions] == [d.id for d in before.distributions]
    assert after.tags == before.tags != [], after.tags
    assert after.title == before.title

    cleared = client.patch(
        f"/catalog/datasets/{DATASET_ID}",
        json={"actor": "data-admin", "reason": "태그 비우기", "tags": []},
    )
    assert cleared.status_code == 200, cleared.text
    assert before.tags != [], "the fixture must start with tags for this to measure clearing"
    assert catalog.get_dataset(DATASET_ID).tags == []


def test_the_patch_is_recorded_as_a_change() -> None:
    """A stored change the ledger does not show is the other half of this bug."""
    _register()
    client.patch(
        f"/catalog/datasets/{DATASET_ID}",
        json={
            "actor": "data-admin",
            "reason": "relation 선언",
            "distributions": [
                {
                    "id": "d-table",
                    "format": f"{orchestrator.DRAFT_SQL_DIALECT}.table",
                    "endpoint": "https://warehouse.example.internal/api/table/events_orders",
                }
            ],
        },
    )
    audit = client.get(f"/catalog/datasets/{DATASET_ID}/audit?user=data-admin").json()
    events = audit if isinstance(audit, list) else audit.get("events", audit.get("items", []))
    assert events, audit
    details = (events[0].get("details") or {})
    changes = details.get("changes") or {}
    assert "distributions" in changes, details
    assert details.get("before", {}).get("distributions") != details.get("after", {}).get(
        "distributions"
    ), details
