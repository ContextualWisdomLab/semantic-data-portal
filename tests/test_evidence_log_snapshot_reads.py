"""A page of evidence must not duplicate a row while the log trims behind it.

``list_policy_decisions`` and ``list_persisted_audit_events`` built their page
from ``reversed(_POLICY_DECISION_LOG)`` - a lazy iterator over the list itself -
while ``record_policy_decision`` trims the front of that same list with
``del _POLICY_DECISION_LOG[:-MAX_IN_MEMORY_POLICY_DECISIONS]``. A reverse
iterator whose list loses its front mid-iteration re-visits shifted elements and
skips others, so a page could carry the same ``decision_id`` twice and silently
omit that many real rows. Measured with two readers and two writers against a
log already at its cap::

    pages read 14303, pages containing a duplicated decision_id 142

The repair is a snapshot, not a lock: ``list(...)`` of a list is one C-level
copy, so it is taken either side of a trim and never mid-trim, and the read path
stays uncontended. ``catalog.list_audit_events`` already read this way, which is
why only the ``evidence`` pages tore.

A caveat these tests state rather than hide: a page is a point-in-time view, so
a row appended after the snapshot is legitimately absent. What they assert is
that no row appears **twice** and that the window stays within its declared
bound - not that a page is a consistent transactional read, which an in-memory
fallback log does not offer.
"""

from __future__ import annotations

import threading
import time

import pytest

from sdp import evidence
from sdp_core.contracts import AuditEvent, PolicyDecision


@pytest.fixture()
def saturated_decision_log():
    """A decision log already at its cap, so the next append trims."""
    evidence._POLICY_DECISION_LOG.clear()
    for index in range(evidence.MAX_IN_MEMORY_POLICY_DECISIONS):
        evidence._POLICY_DECISION_LOG.append(
            PolicyDecision(
                subject="subject", resource=f"resource-{index}",
                action="read", effect="allow",
            )
        )
    return evidence._POLICY_DECISION_LOG


@pytest.fixture()
def saturated_audit_log():
    """An audit log already at its cap, so the next append trims."""
    evidence._AUDIT_EVENT_LOG.clear()
    for index in range(evidence.MAX_IN_MEMORY_AUDIT_EVENTS):
        evidence._AUDIT_EVENT_LOG.append(
            AuditEvent(
                id=f"event-{index}", actor="actor", action="read",
                resource=f"resource-{index}", result="success",
            )
        )
    return evidence._AUDIT_EVENT_LOG


def _hammer(read, write, *, seconds: float = 2.0) -> tuple[int, int]:
    """Read pages while writers trim; return (pages read, pages with a duplicate)."""
    stop = threading.Event()
    counters = {"pages": 0, "duplicated": 0}
    failures: list[BaseException] = []

    def writer(tag: int) -> None:
        # The tag makes each writer's ids unique. Without it both writers mint
        # ``written-0``, ``written-1``, ... and the duplicates the reader counts
        # are the test's own, not the log's.
        index = 0
        try:
            while not stop.is_set():
                write(f"{tag}-{index}")
                index += 1
        except BaseException as exc:  # noqa: BLE001
            failures.append(exc)

    def reader() -> None:
        try:
            while not stop.is_set():
                identifiers = read()
                counters["pages"] += 1
                if len(identifiers) != len(set(identifiers)):
                    counters["duplicated"] += 1
        except BaseException as exc:  # noqa: BLE001
            failures.append(exc)

    threads = [threading.Thread(target=writer, args=(tag,)) for tag in range(2)]
    threads += [threading.Thread(target=reader) for _ in range(2)]
    for thread in threads:
        thread.start()
    time.sleep(seconds)
    stop.set()
    for thread in threads:
        thread.join(timeout=30)
    assert all(not thread.is_alive() for thread in threads)
    assert not failures, f"a log read or write raised: {failures[0]!r}"
    return counters["pages"], counters["duplicated"]


def test_a_decision_page_never_repeats_a_row_while_the_log_trims(
    saturated_decision_log,
) -> None:
    """The reported defect, on the route's own read function."""
    pages, duplicated = _hammer(
        read=lambda: [
            decision.decision_id
            for decision in evidence.list_policy_decisions(limit=500, tenant_ids=None)
        ],
        write=lambda tag: evidence.record_policy_decision(
            PolicyDecision(
                subject="subject", resource=f"written-{tag}",
                action="read", effect="allow",
            )
        ),
    )
    assert pages > 100, f"only {pages} pages read; the probe did not exercise much"
    assert duplicated == 0, (
        f"{duplicated} of {pages} pages contained a duplicated decision_id"
    )


def test_an_audit_page_never_repeats_a_row_while_the_log_trims(
    saturated_audit_log,
) -> None:
    """The same lazy-reverse read, on the other log - fixed together."""
    pages, duplicated = _hammer(
        read=lambda: [
            event.id
            for event in evidence.list_persisted_audit_events(
                limit=500, tenant_ids=None
            )
        ],
        write=lambda tag: evidence.append_audit_event(
            AuditEvent(
                id=f"written-{tag}", actor="actor", action="read",
                resource=f"written-{tag}", result="success",
            )
        ),
    )
    assert pages > 100, f"only {pages} pages read; the probe did not exercise much"
    assert duplicated == 0, (
        f"{duplicated} of {pages} pages contained a duplicated event id"
    )


def test_the_window_stays_within_its_declared_bound(saturated_decision_log) -> None:
    """Append-then-trim is two steps, so one row past the cap is possible.

    Stated as a bound rather than an equality: a reader landing between the
    append and the trim legitimately sees one extra row. What may not happen is
    the log growing without limit.
    """
    for index in range(50):
        evidence.record_policy_decision(
            PolicyDecision(
                subject="subject", resource=f"overflow-{index}",
                action="read", effect="allow",
            )
        )

    assert len(evidence._POLICY_DECISION_LOG) <= (
        evidence.MAX_IN_MEMORY_POLICY_DECISIONS + 1
    )


def test_both_read_paths_snapshot_rather_than_iterate_the_live_log() -> None:
    """Enumerated from the functions, so a third reader cannot reintroduce this.

    Scoped to the two function bodies rather than the whole module: the module
    comment documenting this defect quotes the forbidden expression, and a
    module-wide grep flagged the explanation instead of the code.
    """
    import inspect

    for reader in (evidence.list_policy_decisions, evidence.list_persisted_audit_events):
        source = inspect.getsource(reader)
        for log in ("_POLICY_DECISION_LOG", "_AUDIT_EVENT_LOG"):
            assert f"reversed({log})" not in source, (
                f"{reader.__name__} iterates {log} live, which tears while the "
                "log trims; wrap it in _log_snapshot(...)"
            )
        assert "_log_snapshot(" in source, (
            f"{reader.__name__} does not read through the snapshot helper"
        )


def test_the_snapshot_is_a_copy_and_not_the_log_itself() -> None:
    """A 'snapshot' that aliases the list would fix nothing."""
    snapshot = evidence._log_snapshot(evidence._POLICY_DECISION_LOG)
    assert snapshot is not evidence._POLICY_DECISION_LOG
    before = len(snapshot)
    evidence._POLICY_DECISION_LOG.append(
        PolicyDecision(
            subject="subject", resource="after-snapshot", action="read", effect="allow"
        )
    )
    assert len(snapshot) == before, "the snapshot tracked a later append"
