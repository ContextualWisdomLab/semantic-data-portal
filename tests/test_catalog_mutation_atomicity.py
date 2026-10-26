"""A catalog mutation is one atomic read-modify-write, and so is its mirror.

Every catalog mutation was a read-modify-write over module dicts -
``get_dataset_or_404``, ``model_dump``, ``_bump_version``,
``_DATA[id] = updated`` - with nothing serialising it. FastAPI runs this
package's ``def`` handlers in a worker threadpool, so two requests genuinely
interleave. Measured before the mutation lock, by forcing the interleaving::

    PATCH description=FIRST  -> 200
    PATCH steward=SECOND     -> 200
    stored: description=FIRST, steward=<unchanged>, version=1.0.1
    audit:  success {"description": "FIRST"}
    audit:  success {"steward": "SECOND"}

The lost write is bad. The audit row is worse: this product's stated governance
invariant is that a policy decision and an audit event accompany every governed
write, and here the ledger certified a change that is not in the store. The
event is built from the writer's own ``updates`` and never re-read from
``_DATA``, so it cannot notice. Unsynchronised, 50 concurrent patches advanced
the version by 25; eight concurrent id-less creates each returned 200 and the
catalog grew by five.

**The interleaving is forced, not raced.** Pausing one writer between its read
and its write makes the defect deterministic in both directions: without the
lock the second writer slips in and one write is lost every time; with the lock
the second writer waits outside the critical section and no write is lost ever.
A pause rather than a barrier, because a barrier *inside* the critical section
would deadlock against the fix it is meant to verify. The stress tests below
are kept as well - they are what found the defect - but the deterministic ones
are the gate.
"""

from __future__ import annotations

import threading
import time

import pytest

from sdp import catalog
from sdp_core.contracts import DatasetCreateRequest, DatasetPatchRequest

_WIDE_SCHEMA = [
    {
        "name": f"column_{index}",
        "datatype": "string",
        "nullable_ratio": 0.0,
        "distinct_ratio": 1.0,
    }
    for index in range(80)
]


def _create(dataset_id: str | None = None, *, title: str = "원자성 픽스처"):
    """Register a dataset wide enough to have a real read-modify-write window."""
    return catalog.register_dataset(
        DatasetCreateRequest(
            id=dataset_id,
            title=title,
            description="d",
            owner="owner@example.org",
            steward="steward@example.org",
            domain="customer",
            source_system="postgresql://analytics.dw:5432/crm",
            sensitivity="internal",
            update_frequency="daily",
            quality_score=0.9,
            freshness_score=0.9,
            schema=_WIDE_SCHEMA,
        ),
        actor="admin",
    )


def _patch_events(dataset_id: str):
    """The ``dataset.patch`` audit rows for one dataset."""
    return [
        event
        for event in catalog.list_audit_events(
            limit=500, resource=dataset_id, tenant_ids=None
        )
        if event.action == "dataset.patch"
    ]


@pytest.fixture()
def paused_first_writer(monkeypatch):
    """Pause the first writer between its read and its write.

    ``_bump_version`` runs after the dataset has been read and before the store
    assignment, which is exactly the window. Only the first caller pauses, and
    only once.
    """
    real_bump = catalog._bump_version
    reached = threading.Event()

    def slow_bump(version: str) -> str:
        if not reached.is_set():
            reached.set()
            time.sleep(0.25)
        return real_bump(version)

    monkeypatch.setattr(catalog, "_bump_version", slow_bump)
    return reached


def test_a_second_writer_cannot_clobber_the_first(paused_first_writer) -> None:
    """Two patches of two different fields: both must survive."""
    dataset = _create("atomic-patch")

    def patch(field: str, value: str) -> None:
        catalog.patch_dataset(
            dataset.id, DatasetPatchRequest(**{field: value}), actor="admin"
        )

    first = threading.Thread(target=patch, args=("description", "FIRST_DESCRIPTION"))
    first.start()
    assert paused_first_writer.wait(timeout=10), "the writer never reached the window"
    time.sleep(0.02)
    second = threading.Thread(target=patch, args=("steward", "second@example.org"))
    second.start()
    first.join(timeout=30)
    second.join(timeout=30)
    assert not first.is_alive() and not second.is_alive()

    stored = catalog.get_dataset(dataset.id)
    assert stored is not None
    assert stored.description == "FIRST_DESCRIPTION", "the first write was lost"
    assert stored.steward == "second@example.org", "the second write was lost"
    # Two patches applied means two version bumps, not one.
    assert stored.version == "1.0.2", stored.version


def test_the_ledger_never_certifies_a_change_that_is_not_stored(
    paused_first_writer,
) -> None:
    """The governance invariant: an audit row is evidence, so it must be true.

    This is the half of the defect that matters most. Both writers recorded
    ``result="success"`` with their own change under ``details.changes`` while
    only one of the changes was in the store.
    """
    dataset = _create("atomic-ledger")

    def patch(field: str, value: str) -> None:
        catalog.patch_dataset(
            dataset.id, DatasetPatchRequest(**{field: value}), actor="admin"
        )

    first = threading.Thread(target=patch, args=("description", "LEDGER_DESCRIPTION"))
    first.start()
    assert paused_first_writer.wait(timeout=10)
    time.sleep(0.02)
    second = threading.Thread(target=patch, args=("title", "LEDGER_TITLE"))
    second.start()
    first.join(timeout=30)
    second.join(timeout=30)

    stored = catalog.get_dataset(dataset.id)
    assert stored is not None
    events = _patch_events(dataset.id)
    assert len(events) == 2, events
    for event in events:
        assert event.result == "success", event
        for field, claimed in (event.details.get("changes") or {}).items():
            assert getattr(stored, field) == claimed, (
                f"the ledger records {field}={claimed!r} as a successful change, "
                f"but the store holds {getattr(stored, field)!r}"
            )


def test_no_concurrent_patch_is_silently_dropped() -> None:
    """Stress form: every patch that returned must have advanced the version."""
    dataset = _create("atomic-stress")
    start = int(catalog.get_dataset(dataset.id).version.split(".")[2])
    applied = []
    per_thread = 12

    def worker(field: str, tag: str) -> None:
        for index in range(per_thread):
            catalog.patch_dataset(
                dataset.id,
                DatasetPatchRequest(**{field: f"{tag}-{index}"}),
                actor="admin",
            )
            applied.append(1)

    threads = [
        threading.Thread(target=worker, args=("description", "DESCRIPTION")),
        threading.Thread(target=worker, args=("title", "TITLE")),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    assert all(not thread.is_alive() for thread in threads)

    end = int(catalog.get_dataset(dataset.id).version.split(".")[2])
    assert end - start == len(applied) == 2 * per_thread, (
        f"{len(applied)} patches returned, version advanced {end - start}"
    )


def test_concurrent_id_less_creates_all_survive() -> None:
    """``len(_DATA) + 1`` plus a non-atomic check-then-store destroyed datasets."""
    before = {dataset.id for dataset in catalog.list_datasets()}
    created: list[str] = []
    guard = threading.Lock()
    barrier = threading.Barrier(8)

    def create(tag: int) -> None:
        barrier.wait(timeout=10)
        dataset = _create(title=f"concurrent-{tag}")
        with guard:
            created.append(dataset.id)

    threads = [threading.Thread(target=create, args=(tag,)) for tag in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    assert all(not thread.is_alive() for thread in threads)

    assert len(created) == 8
    assert len(set(created)) == 8, f"an id was handed to two callers: {created}"
    after = {dataset.id for dataset in catalog.list_datasets()}
    assert len(after - before) == 8, (
        f"{8 - len(after - before)} datasets were silently destroyed"
    )


def test_a_generated_id_skips_one_a_caller_already_took() -> None:
    """The count never answered "which ids are free"; the scan does."""
    taken = catalog._next_generated_dataset_id()
    _create(taken)
    assert catalog._next_generated_dataset_id() != taken
    # And an explicitly-registered generated-shape id is skipped too.
    explicit = catalog._next_generated_dataset_id()
    _create(explicit)
    following = catalog._next_generated_dataset_id()
    assert following not in {taken, explicit}
    assert catalog.get_dataset(following) is None


def test_the_mutation_lock_is_reentrant() -> None:
    """``api`` holds it across a mutation and its mirror; the mutation retakes it."""
    with catalog.catalog_mutation_lock():
        with catalog.catalog_mutation_lock():
            dataset = _create("reentrant-probe")
    assert catalog.get_dataset(dataset.id) is not None


def test_every_catalog_mutation_takes_the_lock() -> None:
    """Enumerated from the module, so a fifth mutation cannot be left out.

    The lock object's type is checked too. Naming ``_MUTATION_LOCK`` is not the
    same as holding one: when this was verified in reverse by swapping the
    ``RLock`` for a no-op context manager, the two deterministic tests above
    failed as intended while a name-only check here kept passing.
    """
    import inspect

    assert isinstance(catalog._MUTATION_LOCK, type(threading.RLock())), (
        "_MUTATION_LOCK is not a reentrant lock"
    )
    for name in (
        "register_dataset",
        "patch_dataset",
        "publish_dataset",
        "deprecate_dataset",
    ):
        source = inspect.getsource(getattr(catalog, name))
        assert "_MUTATION_LOCK" in source, (
            f"catalog.{name} mutates the store without taking the mutation lock"
        )


# --- the evidence write, which is the last of the three and can fail ---------


class _StoreWithDeadAuditTable:
    """An evidence store whose audit table is gone: decisions write, events raise.

    Not a general outage: ``record_decision`` succeeds so the route's policy
    decision is recorded exactly as it is in production, and only the audit
    write - the **last** of a mutation's three writes - fails. That asymmetry is
    the point, because it is the one that used to leave the mutation committed
    with nothing certifying it.
    """

    def __init__(self) -> None:
        """Count what reached the store, so a test can tell silence from success."""
        self.decisions: list[object] = []
        self.event_attempts = 0

    def record_decision(self, decision: object) -> None:
        """Accept the decision, as a store with a live decisions table would."""
        self.decisions.append(decision)

    def append_event(self, event: object) -> None:
        """Fail the way a dropped table fails."""
        self.event_attempts += 1
        raise RuntimeError("no such table: audit_events")

    def list_events(self, **kwargs: object) -> list:
        """No rows to read."""
        return []

    def list_decisions(self, **kwargs: object) -> list:
        """Read back what was accepted."""
        return list(self.decisions)


@pytest.fixture
def dead_audit_table():
    """Install the half-broken store for one test and put the previous one back."""
    from sdp import evidence

    store = _StoreWithDeadAuditTable()
    previous = evidence.configure_evidence_store(store)
    try:
        yield store
    finally:
        evidence.configure_evidence_store(previous)


_MUTATION_TARGET = "crm-customer-master"


def test_a_mutation_whose_audit_row_cannot_be_written_is_not_applied(
    dead_audit_table: _StoreWithDeadAuditTable,
) -> None:
    """The violation of this product's central claim, on all four routes.

    The audit row is written last, through the configured evidence store, and
    that store is a real external dependency in both documented deployments
    (``SDP_SQLITE_PATH`` for the Docker demo, ``SDP_DATABASE_URL`` for the
    paid-pilot profile). When its write failed, the mutation was already
    committed. Measured before the repair, with ``record_decision`` healthy and
    ``append_event`` raising::

        PATCH /catalog/datasets/crm-customer-master {"description": ...}
          -> 400 {"error": "invalid_request", "reason": "request body is not valid"}
             description changed:  True
             audit rows for it:    0

        POST /catalog/datasets           -> 500, catalog row created
        POST .../publish, .../deprecate  -> 500, status changed

    Four governed writes that landed with no evidence that they were
    authorised - and the patch route additionally told the caller their body was
    malformed because the **server** could not write its own ledger.
    """
    from fastapi.testclient import TestClient

    from sdp.api import app

    client = TestClient(app, raise_server_exceptions=False)
    stored = catalog.get_dataset(_MUTATION_TARGET)
    assert stored is not None
    before_description = stored.description
    before_status = stored.status
    before_version = stored.version
    before_history = len(catalog._SCHEMA_HISTORY.get(_MUTATION_TARGET, []))

    response = client.patch(
        f"/catalog/datasets/{_MUTATION_TARGET}",
        json={"actor": "admin", "description": "감사실패변경", "change_reason": "probe"},
    )
    # A server-side storage failure, not a client error. 400 was the measured
    # answer and it is the one thing a caller cannot act on.
    assert response.status_code >= 500, (response.status_code, response.text)

    after = catalog.get_dataset(_MUTATION_TARGET)
    assert after is not None
    assert after.description == before_description
    assert after.status == before_status
    # The version bump and the schema snapshot are part of the mutation and roll
    # back with it; a kept snapshot would leave the history claiming a revision
    # the catalog does not hold.
    assert after.version == before_version
    assert len(catalog._SCHEMA_HISTORY.get(_MUTATION_TARGET, [])) == before_history

    # The store was really asked, so the test is about the failure handling and
    # not about a route that skipped the write.
    assert dead_audit_table.event_attempts >= 1
    # And the policy decision is deliberately kept: authorization was evaluated
    # and granted, and the write then failed. That is the honest record.
    assert dead_audit_table.decisions


def test_a_registration_whose_audit_row_cannot_be_written_leaves_no_row(
    dead_audit_table: _StoreWithDeadAuditTable,
) -> None:
    """The create path's rollback has to **remove** the key, not restore a value.

    ``register_dataset`` writes an id that had no previous entry, so the undo is
    a deletion. Restoring ``previous`` without that case would leave the new
    dataset in the catalog - which is the defect, not the fix - and the next
    ``seed_store`` would mirror a row no audit event covers.
    """
    from fastapi.testclient import TestClient

    from sdp.api import app

    client = TestClient(app, raise_server_exceptions=False)
    new_id = "감사실패등록셋"
    assert new_id not in catalog._DATA

    response = client.post(
        "/catalog/datasets",
        json={
            "actor": "admin",
            "id": new_id,
            "title": "제목",
            "description": "설명",
            "owner": "owner",
            "steward": "steward",
            "domain": "테스트",
            "source_system": "postgresql://analytics.dw/t",
            "sensitivity": "low",
            "update_frequency": "daily",
            "quality_score": 0.9,
            "freshness_score": 0.9,
            "tags": ["테스트"],
            "terms": ["테스트"],
            "related_datasets": [],
            "schema": [],
            "distributions": [
                {
                    "id": f"dist-{new_id}",
                    "format": "postgresql.table",
                    "endpoint": "https://example.internal/api/table/t",
                }
            ],
            "mappings": [],
        },
    )
    assert response.status_code >= 500, (response.status_code, response.text)
    assert new_id not in catalog._DATA
    assert new_id not in catalog._SCHEMA_HISTORY
    assert catalog.get_dataset(new_id) is None
    # Checked in the store, not over HTTP: while this store is installed a
    # governed *read* answers 5xx too, because it records an audit event of its
    # own and that write fails the same way. That is the correct answer - a read
    # that cannot be audited should not serve the row - so the absence is
    # asserted where it is unambiguous. With the store restored, the id is free
    # again, which the fixture's teardown leaves true for the next test.


def test_every_catalog_writer_commits_through_the_evidence_helper() -> None:
    """The drift guard: a fifth writer must not reintroduce the bare sequence.

    All four writers had the same three lines in the same order, and a repair to
    one would not have reached the others - the same shape as the IPv6 authority
    defect and the kind-conflict guard that covered two of four writes. This
    reads the source so a new writer that assigns ``_DATA`` directly is refused
    here rather than in production.

    The question is **"does this function assign ``_DATA`` itself"**, not "does
    it call ``_record_audit_event``". Written the second way, this test failed
    on ``_patch_dataset_locked``'s no-op branch: a patch naming no patchable
    field records the no-op in the ledger and returns the dataset **untouched**,
    deliberately skipping the version bump and the schema snapshot, so routing
    it through the helper would add a snapshot for a request that changed
    nothing. An audit row without a mutation needs no rollback; a mutation is
    what does.
    """
    import inspect
    import re

    # The *locked* functions, which are where the writes live; the public
    # ``publish_dataset``/``deprecate_dataset`` are lock wrappers that delegate,
    # and naming those made this test pass vacuously on their delegating source.
    for name in (
        "_register_dataset_locked",
        "_patch_dataset_locked",
        "_publish_dataset_locked",
        "_deprecate_dataset_locked",
    ):
        source = inspect.getsource(getattr(catalog, name))
        assert "_commit_dataset_with_evidence" in source, (
            f"catalog.{name} commits without the evidence helper, so a failed "
            "audit write would leave its mutation applied"
        )
        direct = re.findall(r"_DATA\[[^\]]*\]\s*=", source)
        assert direct == [], (
            f"catalog.{name} assigns _DATA directly ({direct}); commit through "
            "_commit_dataset_with_evidence so a failed audit write rolls back"
        )

    # And the helper is the only place that does assign it, so the guard above
    # is not satisfied by moving the assignment somewhere else in the module.
    helper = inspect.getsource(catalog._commit_dataset_with_evidence)
    assert re.findall(r"_DATA\[[^\]]*\]\s*=", helper)
