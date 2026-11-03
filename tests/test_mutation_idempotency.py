"""A replayed or empty mutation must not invent governance evidence.

Three defects from the same adversarial sweep, all reproduced through the
product's own routes. They share a shape: a request that changes nothing was
recorded as though it had changed something, so the ledger, the version
sequence and ``updated_at`` all described work that did not happen.

``publish_dataset`` already modelled the answer - it guards its
already-published case and records the attempt as a no-op - and the other two
paths did not.

Measured before the repair, on ``crm-customer-master``::

    POST .../deprecate x3   -> 200, 200, 200
                               version 1.0.1 -> 1.0.2 -> 1.0.3
                               3 "dataset.deprecate / success" ledger rows
                               3 schema snapshots appended
    PATCH {"actor": "admin"} -> 200
                               version bumped, updated_at moved,
                               a snapshot appended, nothing changed
    GET  .../schema-versions -> ["1.0.0", "1.0.0", "1.0.0", "1.0.0"]

The audit rows are kept in every case: a replayed request is a real event and
hiding it would be the opposite defect. What changes is that the row says
``noop: true`` and the dataset is returned untouched.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from sdp import catalog
from sdp.api import app

client = TestClient(app)

_DATASET = "crm-customer-master"


def _rows(action: str, dataset_id: str = _DATASET):
    """The audit rows for one action on one dataset."""
    return [
        event
        for event in catalog.list_audit_events(
            limit=500, resource=dataset_id, tenant_ids=None
        )
        if event.action == action
    ]


def _snapshot_count(dataset_id: str = _DATASET) -> int:
    """How many state snapshots the dataset has accumulated."""
    return len(catalog._SCHEMA_HISTORY.get(dataset_id, []))


def test_a_replayed_deprecate_changes_nothing_and_says_so() -> None:
    """``publish`` guarded this case; ``deprecate`` did not."""
    first = client.post(
        f"/catalog/datasets/{_DATASET}/deprecate",
        json={"actor": "admin", "reason": "sunset"},
    )
    assert first.status_code == 200, first.text
    after_first = catalog.get_dataset(_DATASET)
    assert after_first is not None
    assert after_first.status == "deprecated"
    version = after_first.version
    snapshots = _snapshot_count()
    updated_at = after_first.updated_at

    for replay in range(2):
        again = client.post(
            f"/catalog/datasets/{_DATASET}/deprecate",
            json={"actor": "admin", "reason": "sunset"},
        )
        assert again.status_code == 200, again.text
        current = catalog.get_dataset(_DATASET)
        assert current is not None
        assert current.version == version, f"replay {replay} bumped the version"
        assert current.updated_at == updated_at, f"replay {replay} moved updated_at"
        assert _snapshot_count() == snapshots, f"replay {replay} appended a snapshot"

    # The attempts are still audited - a replay is a real event - but marked.
    # Asserted on content, not position: ``list_audit_events`` returns the feed
    # newest-first, so an order-dependent assertion here would encode the feed's
    # direction rather than the behaviour under test.
    rows = _rows("dataset.deprecate")
    assert len(rows) == 3, rows
    marked = [bool(row.details.get("noop")) for row in rows]
    assert marked.count(True) == 2, marked
    assert marked.count(False) == 1, marked
    for row in rows:
        assert row.result == "success"


def test_a_patch_that_changes_nothing_leaves_the_dataset_untouched() -> None:
    """``{"actor": "admin"}`` names no patchable field."""
    before = catalog.get_dataset(_DATASET)
    assert before is not None
    snapshots = _snapshot_count()

    response = client.patch(
        f"/catalog/datasets/{_DATASET}", json={"actor": "admin"}
    )
    assert response.status_code == 200, response.text

    after = catalog.get_dataset(_DATASET)
    assert after is not None
    assert after.version == before.version
    assert after.updated_at == before.updated_at
    assert _snapshot_count() == snapshots
    row = _rows("dataset.patch")[-1]
    assert row.details.get("noop") is True
    assert row.details.get("changes") == {}


def test_a_patch_whose_values_are_all_skipped_is_also_a_no_op() -> None:
    """The effective change set is what counts, not the requested one.

    A body of ``None`` values passes validation and is then skipped field by
    field, so ``updates`` is non-empty while nothing is applied. Keying the
    no-op on the requested set would have missed this.
    """
    before = catalog.get_dataset(_DATASET)
    assert before is not None
    snapshots = _snapshot_count()

    response = client.patch(
        f"/catalog/datasets/{_DATASET}",
        json={"actor": "admin", "title": None, "tags": None, "profile": None},
    )
    assert response.status_code == 200, response.text

    after = catalog.get_dataset(_DATASET)
    assert after is not None
    assert after.version == before.version
    assert after.updated_at == before.updated_at
    assert _snapshot_count() == snapshots
    assert _rows("dataset.patch")[-1].details.get("noop") is True


def test_a_patch_that_does_change_something_still_bumps() -> None:
    """The guard must not swallow a real change."""
    before = catalog.get_dataset(_DATASET)
    assert before is not None
    snapshots = _snapshot_count()

    response = client.patch(
        f"/catalog/datasets/{_DATASET}", json={"actor": "admin", "title": "새 제목"}
    )
    assert response.status_code == 200, response.text

    after = catalog.get_dataset(_DATASET)
    assert after is not None
    assert after.title == "새 제목"
    assert after.version != before.version
    assert after.updated_at != before.updated_at
    assert _snapshot_count() == snapshots + 1
    row = _rows("dataset.patch")[-1]
    assert "noop" not in row.details
    assert row.details["changes"] == {"title": "새 제목"}
    assert row.details["after"] == {"title": "새 제목"}


def test_the_ledger_records_the_effective_change_set_not_the_requested_one() -> None:
    """A skipped field must not appear as a change that was applied."""
    response = client.patch(
        f"/catalog/datasets/{_DATASET}",
        json={"actor": "admin", "title": "확정 제목", "tags": None},
    )
    assert response.status_code == 200, response.text
    row = _rows("dataset.patch")[-1]
    assert row.details["changes"] == {"title": "확정 제목"}
    assert "tags" not in row.details["changes"], (
        "the ledger recorded a field the patch skipped"
    )
    assert "tags" not in row.details["before"]
    assert "tags" not in row.details["after"]


def test_every_listed_schema_version_is_addressable_by_the_diff() -> None:
    """The listing advertised four ``1.0.0`` and the diff served one.

    A state snapshot is recorded on every mutation - it captures lineage,
    mappings, tags, status and scores as well as the columns, which is what
    drift detection reads - so a non-schema patch added a snapshot carrying an
    unchanged ``schema_version``. The listing is one entry per *version* now,
    and every entry resolves.
    """
    for index in range(3):
        patched = client.patch(
            f"/catalog/datasets/{_DATASET}",
            json={"actor": "admin", "title": f"반복 {index}"},
        )
        assert patched.status_code == 200, patched.text

    listed = client.get(
        f"/catalog/datasets/{_DATASET}/schema-versions", params={"user": "analyst"}
    )
    assert listed.status_code == 200, listed.text
    versions = listed.json()["versions"]
    assert versions == sorted(set(versions), key=versions.index)
    assert len(versions) == len(set(versions)), f"duplicated versions: {versions}"
    # Snapshots still accumulate; the listing just stops repeating itself.
    assert _snapshot_count() > len(versions)

    for version in versions:
        diff = client.get(
            f"/catalog/datasets/{_DATASET}/schema-diff",
            params={
                "user": "analyst",
                "from_version": version,
                "to_version": version,
            },
        )
        assert diff.status_code == 200, (version, diff.text)


def test_a_real_schema_change_adds_a_new_listed_version() -> None:
    """De-duplicating must not collapse two genuinely different versions."""
    before = client.get(
        f"/catalog/datasets/{_DATASET}/schema-versions", params={"user": "analyst"}
    ).json()["versions"]

    dataset = catalog.get_dataset(_DATASET)
    assert dataset is not None
    columns = [column.model_dump() for column in dataset.schema]
    columns[0]["name"] = f"{columns[0]['name']}_renamed"
    patched = client.patch(
        f"/catalog/datasets/{_DATASET}", json={"actor": "admin", "schema": columns}
    )
    assert patched.status_code == 200, patched.text

    after = client.get(
        f"/catalog/datasets/{_DATASET}/schema-versions", params={"user": "analyst"}
    ).json()["versions"]
    assert len(after) == len(before) + 1, (before, after)
    assert after[: len(before)] == before
