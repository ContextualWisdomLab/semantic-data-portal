from __future__ import annotations

import os
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

from sdp_core import AuditEvent, PolicyDecision, PostgresEvidenceStore, SQLiteEvidenceStore
from sdp_core.stores import _audit_tenant_id, _policy_tenant_id

EvidenceStore = SQLiteEvidenceStore | PostgresEvidenceStore | None


def _build_configured_evidence_store(environ: Mapping[str, str]) -> EvidenceStore:
    if environ.get("SDP_DATABASE_URL"):
        return PostgresEvidenceStore(
            environ["SDP_DATABASE_URL"],
            sslmode=environ.get("SDP_DATABASE_SSLMODE"),
        )
    if environ.get("SDP_SQLITE_PATH"):
        return SQLiteEvidenceStore(environ["SDP_SQLITE_PATH"])
    return None


_STORE: EvidenceStore = _build_configured_evidence_store(os.environ)
# Every gated route evaluates policy before refusing, so an unauthenticated
# caller can add one row per request to whichever in-memory list is unbounded.
# Both fallback lists are therefore capped, and ``catalog`` imports
# ``MAX_IN_MEMORY_AUDIT_EVENTS`` from here rather than declaring its own number:
# the previous round capped ``catalog._AUDIT_LOG`` at a local 2000 while
# ``append_audit_event`` kept appending the *same* event to the unbounded list
# below, so the cap did not bound memory at all. Measured over 2600 refused
# ``POST /browse/crm-customer-master/preview`` calls with no store configured:
#
#     catalog._AUDIT_LOG        = 2000   (capped)
#     evidence._AUDIT_EVENT_LOG = 2600   (grew with the request count)
#
# One number, imported, is what makes the two windows unable to drift again.
MAX_IN_MEMORY_POLICY_DECISIONS = 2000
MAX_IN_MEMORY_AUDIT_EVENTS = 2000

_POLICY_DECISION_LOG: list[PolicyDecision] = []
# Audit events recorded while no store is configured. Without this the event was
# returned to the caller and written nowhere, so the OIDC group-to-role mapping
# records - who was granted admin or platform-admin - were lost in the documented
# `uvicorn sdp.api:app` configuration while the API still handed back an
# `audit_event_id`. Policy decisions already had this fallback.
_AUDIT_EVENT_LOG: list[AuditEvent] = []

# Trimming a window makes "did this get recorded?" unanswerable from the window
# alone: once the cap is reached ``len()`` is constant, so a length comparison
# reads as "nothing was recorded" for every subsequent write. These counters are
# monotonic over the process except for a rolled-back write, which
# ``forget_refused_audit_write`` un-counts because it did not happen, so the
# question stays answerable, and a count
# reported to a buyer does not silently stop rising at the cap.
_RECORDED_POLICY_DECISION_COUNT = 0
_RECORDED_AUDIT_EVENT_COUNT = 0

# Rows a configured store refused to take. The counters above count *attempts*:
# the increment happens before the write and regardless of destination, so a
# store whose write raises leaves the attempt counted and the row nowhere -
# neither in the store nor in the in-memory window, which takes no new row
# while a store is configured. Not "stays empty": it keeps whatever it already
# held, measured at 3 rows before and 3 rows after a store was selected. The
# distinction is what ``observability._withheld_series`` rests its ``gauge``
# declaration on - a store selected after a trim returns the published loss to
# 0 - and the two sentences contradicted each other until this one was fixed. Measured with a store whose writes raise (the store
# ``tests/test_request_evidence_correlation.py`` models, whose docstring says
# "a write that raises - the deployed Postgres/SQLite configuration can"): five
# attempts, five raises, counter 5, both windows 0, and the published loss said
# 0. "A store does not trim, therefore nothing was lost" holds only while every
# write succeeds, so the exception is counted where it happens rather than
# inferred later from a cap.
_STORE_AUDIT_WRITE_FAILURES = 0
_STORE_DECISION_WRITE_FAILURES = 0


def configure_evidence_store(store: EvidenceStore) -> EvidenceStore:
    global _STORE
    previous = _STORE
    _STORE = store
    return previous


def has_configured_evidence_store() -> bool:
    return _STORE is not None


# How many evidence ids one request may collect for its log line. The same
# number as ``observability.MAX_OBSERVATION_EVIDENCE_IDS``, but not imported from
# there: ``observability`` imports this module, so the dependency only runs one
# way. A request that records more than this many rows keeps the first ones and
# counts the rest, so the log line's ``withheld_evidence_id_count`` is the true
# total withheld rather than only what the observation builder trimmed.
MAX_REQUEST_EVIDENCE_IDS = 32


@dataclass
class CollectedRequestEvidenceIds:
    """The evidence ids one request recorded, and how many did not fit."""

    ids: list[str] = field(default_factory=list)
    # The *distinct* ids that did not fit, not the number of times one was
    # offered. ``withheld`` was an ``int`` incremented per call, so 32 distinct
    # ids plus one further id noted five times published
    # ``withheld_evidence_id_count: 5`` for one withheld id - a field named for a
    # count of ids reporting a count of attempts. Not reachable over HTTP today
    # (no route writes more than two ledger rows for one request), which is why
    # it is a set rather than a redesign.
    withheld_ids: set[str] = field(default_factory=set)

    @property
    def withheld(self) -> int:
        """How many distinct evidence ids did not fit."""
        return len(self.withheld_ids)


# Set per request by the observability middleware. The value is the *same list
# object* the request's handler appends to, which is what makes this work for
# this app's ``def`` handlers: FastAPI runs those in a threadpool with a **copy**
# of the context, so rebinding a ContextVar inside the handler would not reach
# the middleware - mutating the object it already holds does.
_REQUEST_EVIDENCE_IDS: ContextVar[CollectedRequestEvidenceIds | None] = ContextVar(
    "sdp_request_evidence_ids", default=None
)


@contextmanager
def collect_request_evidence_ids() -> Iterator[CollectedRequestEvidenceIds]:
    """Collect the evidence ids recorded while one request is served.

    The request log's ``evidence_ids`` is the key that ties a log line to
    ``/policy/decisions`` and ``/audit/events``. It used to be read from the
    caller-supplied ``X-SDP-Evidence-Ids`` header, so the field was asserted by
    the very caller the line is about and the id the server recorded never
    appeared - measured, a governed preview exported two forged ids while its
    real decision ``4ff4d6c7-...`` was nowhere in the log. No route set that
    header, so the ordinary case was an empty list under a published field name
    that claimed correlation.

    Collected here instead, at the two functions every evidence row already
    flows through, so a new route cannot forget to report its evidence and
    cannot report evidence it did not record.
    """
    collected = CollectedRequestEvidenceIds()
    token = _REQUEST_EVIDENCE_IDS.set(collected)
    try:
        yield collected
    finally:
        _REQUEST_EVIDENCE_IDS.reset(token)


def note_request_evidence_id(evidence_id: str) -> None:
    """Record one evidence id against the request in flight, if there is one.

    A no-op outside a request - startup seeding records evidence with nothing in
    flight - and idempotent: two rows naming one decision id are one correlation
    key, not two.
    """
    collected = _REQUEST_EVIDENCE_IDS.get()
    if collected is None or not evidence_id:
        return
    if evidence_id in collected.ids:
        return
    if len(collected.ids) >= MAX_REQUEST_EVIDENCE_IDS:
        collected.withheld_ids.add(evidence_id)
        return
    collected.ids.append(evidence_id)


def record_policy_decision(decision: PolicyDecision) -> PolicyDecision:
    global _RECORDED_POLICY_DECISION_COUNT
    global _STORE_DECISION_WRITE_FAILURES
    _RECORDED_POLICY_DECISION_COUNT += 1
    if _STORE:
        try:
            _STORE.record_decision(decision)
        except Exception:
            # Counted, then re-raised: the request must still fail. Swallowing
            # it here would turn a lost row into a silent one, which is the
            # opposite of what this counter exists for.
            _STORE_DECISION_WRITE_FAILURES += 1
            raise
    else:
        _POLICY_DECISION_LOG.append(decision)
        if len(_POLICY_DECISION_LOG) > MAX_IN_MEMORY_POLICY_DECISIONS:
            del _POLICY_DECISION_LOG[:-MAX_IN_MEMORY_POLICY_DECISIONS]
    # After the write, not before. The log row's ``evidence_ids`` is published as
    # the key that finds this decision in the ledger, and
    # ``evidence_id_source: server_recorded`` says the server recorded it - so on
    # a store write that raises (the deployed Postgres/SQLite configuration can),
    # noting the id first published a key naming a row that does not exist. The
    # request fails in that case, but its log row had already been built.
    note_request_evidence_id(decision.decision_id)
    return decision


def append_audit_event(event: AuditEvent) -> AuditEvent:
    global _RECORDED_AUDIT_EVENT_COUNT
    global _STORE_AUDIT_WRITE_FAILURES
    _RECORDED_AUDIT_EVENT_COUNT += 1
    if _STORE:
        try:
            _STORE.append_event(event)
        except Exception:
            # Counted, then re-raised; see ``record_policy_decision``.
            _STORE_AUDIT_WRITE_FAILURES += 1
            raise
    else:
        _AUDIT_EVENT_LOG.append(event)
        if len(_AUDIT_EVENT_LOG) > MAX_IN_MEMORY_AUDIT_EVENTS:
            del _AUDIT_EVENT_LOG[:-MAX_IN_MEMORY_AUDIT_EVENTS]
    # After the write; see ``record_policy_decision``.
    note_request_evidence_id(event.id)
    return event


def recorded_policy_decision_count() -> int:
    """How many policy decisions this process has recorded, ignoring trimming.

    ``len(_POLICY_DECISION_LOG)`` stops rising at the cap, so it cannot answer
    "was this decision recorded?" once a long-lived process has passed it.
    """
    return _RECORDED_POLICY_DECISION_COUNT


def recorded_audit_event_count() -> int:
    """How many audit events this process has recorded, ignoring trimming."""
    return _RECORDED_AUDIT_EVENT_COUNT


WITHHELD_COUNT_SCOPE = "this_process"


def forget_refused_audit_write() -> int:
    """Undo one counted refusal, for a caller that rolled its write back.

    :func:`append_audit_event` counts a refused store write where the loss
    happens, because that is the only place the exception is seen. But a caller
    can *undo* the mutation the row would have evidenced, and
    ``catalog._commit_dataset_with_evidence`` does exactly that: on a failed
    audit write it restores the previous dataset, pops the schema snapshot this
    mutation appended, and re-raises. Nothing was destroyed in that case - the
    write never happened - so leaving it counted publishes a **fabricated**
    loss, which is the defect this whole repair exists to remove, arriving from
    the other side. Review measured it: one rolled-back catalog mutation
    published one destroyed audit row.

    Floored at 0 rather than asserted: a caller that calls this without a
    counted refusal is wrong, but answering a published governance number with
    a crash would be worse than answering it with the truth.

    It undoes **both** counts, and an earlier draft of this round undid only the
    refusal on the argument that ``_RECORDED_AUDIT_EVENT_COUNT`` counts
    *attempts* and the rolled-back mutation genuinely attempted one. That draft
    added: "Nothing compares that counter with the store's row count any more",
    which was true when it was written and false later in the same round, when
    the store branch of :func:`unreachable_audit_event_count` began deriving
    this process's store successes as ``recorded - refusals``. With the refusal
    forgotten and the attempt kept, that difference counted the rolled-back row
    as a success the store had lost, and the rolled-back mutation published one
    destroyed audit row again - the same fabricated number, arriving through the
    repair for a different one. The test for it went red, which is what it is
    for.

    So the attempt is undone too, and the counter reads "recorded audit events
    this process has **not** rolled back". That is the number every consumer
    wants: a write whose evidence row does not exist and whose mutation was
    undone recorded nothing. It costs the counter strict monotonicity on this
    one path, which is why no caller may treat it as a progress marker that only
    rises.
    """
    global _STORE_AUDIT_WRITE_FAILURES
    global _RECORDED_AUDIT_EVENT_COUNT
    if _STORE_AUDIT_WRITE_FAILURES > 0:
        _STORE_AUDIT_WRITE_FAILURES -= 1
        # Only alongside a counted refusal: a caller with no refusal to forget
        # has nothing to undo, and silently lowering the recording count for it
        # would hide a row that does exist.
        if _RECORDED_AUDIT_EVENT_COUNT > 0:
            _RECORDED_AUDIT_EVENT_COUNT -= 1
    return _STORE_AUDIT_WRITE_FAILURES


def unreachable_audit_event_count(
    *, recorded_count: int, reachable_count: int | None
) -> int | None:
    """How many recorded audit events can no longer be read.

    ``recorded_count`` is passed in rather than read here, and the caller
    must sample it **before** it builds the page. The first version read it
    inside this function, after the page, so every row recorded between the
    two samples became a published loss. Measured over HTTP with four writer
    threads and 1400 rows against a 2000-row cap - nothing trimmed, true loss
    0 at every instant - 34 of 233 reads of ``/enterprise/observability``
    published a nonzero withheld count with the lower-bound flag set, and a
    function-level probe over a 1500-row union fabricated up to 655. The
    counter itself is exact (8 threads x 20000 appends gave 160000 with no
    lost increment); the defect was purely the two samples' separation, and
    it was a regression - the cap comparison this replaced could not exceed
    0 below the cap.

    Sampled first, the page can only be **larger** than the set the counter
    describes, so the subtraction can only come out low: a concurrent loss is
    understated for one read instead of invented. That is the direction this
    whole repair argues for - a flag that should be set and is not
    understates, while a fabricated quantity is a number a reader acts on.

    Measured against what is **actually reachable**, never against a cap. The
    first draft of this function computed
    ``recorded - MAX_IN_MEMORY_AUDIT_EVENTS``: one counter minus **one** cap,
    while the reachable set is the id-deduped union of **two** windows each
    capped at that number - ``catalog._AUDIT_LOG`` and ``_AUDIT_EVENT_LOG``
    here. Rows that enter only this module's window raise the counter without
    shrinking the union, and every OIDC mapping row does exactly that
    (``authz`` imports :func:`append_audit_event` from here and never touches
    the catalog log). Measured over HTTP: 2000 anonymous schema refusals plus
    300 OIDC previews left 2300 recorded, 2300 still reachable and nothing
    destroyed, while the product published a 300-row loss of governance
    evidence that had not happened.

    That is a worse failure than the missing flag it replaced. A flag that
    should be set and is not understates; a fabricated quantity in this
    vocabulary is a number a reader acts on, and it named destroyed audit
    evidence that still existed.

    Takes the **unscoped** reachable count and answers only the question it can
    answer. Whether the loss is knowable at all is the caller's decision, and
    it is made in one place: a scoped read and a saturated page both publish no
    number, because a trimmed row's scope cannot be recovered and a truncated
    page has not seen what it left out.

    ``reachable_count=None`` says the page truncated at the read ceiling, so
    there is no reachable total to subtract from.

    The measured defect this round repaired is the **store** case, and the fix
    for it is the branch above this one, not this one: with a store configured
    the read ceiling *is* reachable - the store has no 2000-row window and the
    shipped image sets ``SDP_SQLITE_PATH`` - and in that state the loss is still
    exactly knowable, so returning ``None`` published ``null`` for a quantity
    sitting in a module global one call away, against a response contract that
    declares ``number``. That branch is first, so a configured store never
    reaches the ``None`` test at all.

    Which leaves this branch reached only with **no** store and a page saturated
    at the ceiling, and that pair cannot occur: the no-store reachable set is
    bounded by two 2000-row windows against a ceiling of 100,000
    (``test_the_no_store_path_cannot_saturate_the_read_page_ceiling`` asserts
    that inequality on the constants). So it is unreachable from the product
    today, exactly as it was when an earlier draft of this round deleted it over
    a surviving ``return 0`` mutation. It is back because deleting it moved the
    decision into the callers, where the store case was then got wrong; it stays
    because the honest answer to "subtract from what?" is "I cannot know", and a
    caller that passes ``None`` must not be handed a fabricated ``0``. Only
    ``test_the_read_page_ceiling_publishes_no_number_it_cannot_know``, which
    lowers the ceiling to 5, reaches it - a test, not a deployment, and said
    here so the next reader does not have to measure it again.
    """
    if has_configured_evidence_store():
        # A store does not trim, so the retention window destroys nothing - but
        # a write it refused destroys the row just as surely, and the first
        # draft returned a flat 0 here on the strength of the trimming half
        # alone. The writes that raised are counted exactly, where they happen.
        #
        # They are not the only way a store loses a row this process wrote, and
        # a draft of this branch returned the refusal counter **alone** while
        # discarding both arguments - which made its own opening sentence
        # ("Measured against what is actually reachable, never against a cap")
        # false of the code under it. Measured: 10 rows written through a store
        # that keeps and serves them, 6 then removed from the store by
        # something outside the app - an operator prune, a restore from an
        # older snapshot, a retention job - and the product published
        # ``visible 4, withheld 0, is_lower_bound false`` on all three
        # surfaces. Six recorded rows unreadable, answered with 0.
        #
        # ``recorded - reachable`` is still not usable, for the reason the
        # earlier comment gave: ``reachable`` counts rows from every process,
        # so predating rows make that difference meaningless. What **is** exact
        # is this process's own writes against the whole reachable set:
        # ``successes`` rows went in from here, and if fewer than that many are
        # readable in total then at least the difference of this process's rows
        # is gone. Another process's rows can only *mask* that, never inflate
        # it, so it understates - the direction this whole repair argues for.
        successes = recorded_count - _STORE_AUDIT_WRITE_FAILURES
        if reachable_count is None:
            # A truncated read says nothing about either quantity, so only the
            # exactly-counted half stands at the ceiling.
            return _STORE_AUDIT_WRITE_FAILURES
        return _STORE_AUDIT_WRITE_FAILURES + max(successes - reachable_count, 0)
    if reachable_count is None:
        # No store, and the page truncated: the only reachable total available
        # is the truncated one, and subtracting from it would overstate by
        # however much it hid. Not knowable here, and not published as 0.
        return None
    return max(recorded_count - reachable_count, 0)


def unreachable_policy_decision_count(
    *, recorded_count: int, reachable_count: int | None
) -> int | None:
    """How many recorded policy decisions can no longer be read.

    See :func:`unreachable_audit_event_count` for the sampling rule, the
    saturated case and why both are written this way. This side has one window
    rather than two, so the union argument does not apply - but the measurement
    is written the same way on purpose, because deriving the loss from a cap is
    what produced a published number that was never true.
    """
    if has_configured_evidence_store():
        # The same two halves as the audit side, for the same reason: see
        # :func:`unreachable_audit_event_count` for the measurement that put
        # the second one here.
        successes = recorded_count - _STORE_DECISION_WRITE_FAILURES
        if reachable_count is None:
            return _STORE_DECISION_WRITE_FAILURES
        return _STORE_DECISION_WRITE_FAILURES + max(successes - reachable_count, 0)
    if reachable_count is None:
        return None
    return max(recorded_count - reachable_count, 0)


@dataclass(frozen=True)
class EvidenceCount:
    """One evidence count beside what bounded it.

    Three things can put a recorded row out of reach, and a published count has
    to answer for all of them: the read page's ``EVIDENCE_COUNT_CEILING``, the
    in-memory retention window, and - with a store configured - the store
    itself, either refusing a write or no longer holding one it accepted. The
    flag asked only about the first, which is 50x larger than the second and
    therefore never the one a buyer reaches, so the product recorded 2200
    events, published 2000, and declared 2000 complete.

    The count was **two** for most of this round and the third arrived last,
    which is why it is spelled out here: a store that drops rows it took is not
    a truncated read and not a trimmed window, and an enumeration that stops at
    two sends the next reader looking for the wrong mechanism.

    The fields travel together on purpose: a surface cannot publish the count
    without the number it dropped being in its hand.

    ``withheld_count`` is ``None`` rather than a number when the loss is not
    recoverable: a scoped read, or - with no store configured - a page that
    saturated the ceiling. It is deliberately not 0 there: 0 is a claim that
    nothing was lost, and the first draft of this round published exactly that
    kind of unearned number in the other direction.

    The flag is **not** implied by a withheld ``None``, and an earlier version
    of this docstring said it was. A saturated page is always a lower bound
    because it has seen that more exist. A scoped read is a lower bound only
    when the process lost something, which is a fact about the process and not
    about the scope - so a scoped read of a ledger that has lost nothing
    publishes ``withheld_count=None`` beside ``is_lower_bound=False``, and that
    pair reads "this count is exact, and no loss is attributable to this
    scope". Measured with 5 rows recorded and all 5 reachable:
    ``resource="no-such-dataset"`` gives ``(0, None, False)``.
    """

    visible_count: int
    withheld_count: int | None
    is_lower_bound: bool


def decision_tenant_id(decision: PolicyDecision) -> str:
    """Return the tenant a policy decision belongs to, as the store files it."""
    return _policy_tenant_id(decision)


def audit_tenant_id(event: AuditEvent) -> str:
    """Return the tenant an audit event belongs to, as the store files it."""
    return _audit_tenant_id(event)


def tenant_is_in_scope(tenant_id: str, tenant_ids: list[str] | None) -> bool:
    """Match one row's tenant against a read scope (``None`` means every tenant)."""
    if tenant_ids is None:
        return True
    return tenant_id in tenant_ids


# Read the bounded in-memory logs through a snapshot, never the live list.
#
# ``reversed(_POLICY_DECISION_LOG)`` is a lazy iterator over the list itself,
# and ``record_policy_decision`` trims the front with
# ``del _POLICY_DECISION_LOG[:-MAX_IN_MEMORY_POLICY_DECISIONS]``. A reverse
# iterator whose list has its front removed mid-iteration re-visits shifted
# elements and skips others, so a page could contain the same ``decision_id``
# twice and silently omit that many real rows. Measured with two readers and two
# writers against a log already at its cap:
#
#     pages read 14303, pages containing a duplicated decision_id 142
#
# ``list(...)`` of a list is one C-level copy, so the snapshot is taken either
# side of a trim and never mid-trim; a lock is not needed on this read path. The
# append-then-trim pair is two steps, so a reader can briefly see one row past
# the cap - an extra row, not a torn page.
def _log_snapshot(log: list[Any]) -> list[Any]:
    """A point-in-time copy of a bounded log, safe to iterate."""
    return list(log)


def list_persisted_audit_events(
    *,
    resource: str | None = None,
    limit: int = 100,
    tenant_ids: list[str] | None = None,
    decision_id: str | None = None,
) -> list[AuditEvent]:
    """Audit events from the configured store, or this module's fallback log.

    ``decision_id`` is pushed to the store rather than filtered after the page,
    because filtering a newest-first page cannot reach a row the page does not
    contain - which is the defect ``catalog.list_audit_events`` documents. Both
    SQL stores carry it as a first-class column.
    """
    if _STORE:
        return _STORE.list_events(
            resource=resource, limit=limit, tenant_ids=tenant_ids, decision_id=decision_id
        )

    events = [
        event
        for event in reversed(_log_snapshot(_AUDIT_EVENT_LOG))
        if (not resource or event.resource == resource)
        and (not decision_id or event.decision_id == decision_id)
        and tenant_is_in_scope(_audit_tenant_id(event), tenant_ids)
    ]
    return events[:limit]


def list_policy_decisions(
    *,
    resource: str | None = None,
    limit: int = 100,
    tenant_ids: list[str] | None = None,
    decision_id: str | None = None,
    offset: int = 0,
) -> list[PolicyDecision]:
    """Decisions newest-first, optionally by decision id, starting at ``offset``.

    A caller could not reach the rows its own ``200`` named. Every store orders
    newest-first and then truncates - ``decisions[:limit]`` here, ``ORDER BY ...
    DESC LIMIT ?`` in SQLite and Postgres - so the caller's own row is the first
    to fall out. Measured: a ``policy_decision_id`` handed back by ``POST
    /browse/{id}/preview`` was reachable immediately and unreachable after 600
    further requests, while ``offset``, ``cursor`` and ``decision_id`` were
    accepted and silently ignored. These are the two selectors a caller actually
    holds.
    """
    if _STORE:
        return _STORE.list_decisions(
            resource=resource,
            limit=limit,
            tenant_ids=tenant_ids,
            decision_id=decision_id,
            offset=offset,
        )

    decisions = [
        decision
        for decision in reversed(_log_snapshot(_POLICY_DECISION_LOG))
        if (not resource or decision.resource == resource)
        and (not decision_id or decision.decision_id == decision_id)
        and tenant_is_in_scope(_policy_tenant_id(decision), tenant_ids)
    ]
    return decisions[offset : offset + limit]


def count_policy_decisions(
    *, resource: str | None = None, tenant_ids: list[str] | None = None
) -> EvidenceCount:
    """How many policy decisions exist in scope, and whether that is a lower bound.

    See ``catalog.count_audit_events`` for the measurement that made the
    published gauges wrong: both were ``len()`` of a 500-row page, and for why
    the scoped branch here reads twice and which callers can reach it (none of
    them a route).
    """
    from .catalog import EVIDENCE_COUNT_CEILING

    # Sampled before the page. That order is the whole fix for a measured
    # fabrication; see :func:`unreachable_audit_event_count`.
    recorded = recorded_policy_decision_count()
    decisions = list_policy_decisions(
        resource=resource, limit=EVIDENCE_COUNT_CEILING, tenant_ids=tenant_ids
    )
    # ``bool(resource)``, not ``resource is not None``: the page filters with
    # ``if resource``, so ``resource=""`` is an unscoped page (measured: same
    # length as the unscoped one) and suppressing a knowable number for it
    # would be two readings of one argument. ``tenant_ids`` is different -
    # ``None`` means every tenant and an empty list yields no rows, so presence
    # is the scope there.
    scoped = bool(resource) or tenant_ids is not None
    if len(decisions) >= EVIDENCE_COUNT_CEILING:
        # The page stopped before the rows did, so it has not seen what it left
        # out: always a lower bound. The loss can still be knowable - with a
        # store configured it is the writes that raised, and the ceiling is
        # reachable in exactly that configuration - so it is asked for rather
        # than assumed away. Returning ``None`` here published ``null`` for a
        # field the response contract declares ``number``, measured at exactly
        # 100,000 store rows on both surfaces.
        truncated_loss = unreachable_policy_decision_count(
            recorded_count=recorded, reachable_count=None
        )
        return EvidenceCount(
            visible_count=len(decisions),
            withheld_count=None if scoped else truncated_loss,
            is_lower_bound=True,
        )
    reachable = (
        len(list_policy_decisions(limit=EVIDENCE_COUNT_CEILING))
        if scoped
        else len(decisions)
    )
    # Answered unscoped even when the published number is withheld: a trimmed
    # row's scope is unrecoverable, so a scope showing nothing may still be
    # missing something, and its count is a lower bound.
    loss = unreachable_policy_decision_count(
        recorded_count=recorded, reachable_count=reachable
    )
    # No ``or predates_this_process`` here, and that clause is withdrawn rather
    # than never written: this round added it so a restart would stop
    # republishing a permanent store-path loss as "complete", and review
    # measured the cost. With a store configured ``reachable`` counts rows from
    # every process while the counter counts this one's attempts, so the clause
    # fired after **any** restart - permanently, for a count that is exact and
    # untruncated, beside ``withheld 0`` - and all three surfaces then called a
    # complete count a lower bound. That is a false incompleteness traded for a
    # false completeness, and the flag's published meaning ("more rows exist
    # than the gauge can show") is false in that state.
    #
    # What the restart case actually needs is for the *withheld number* to say
    # what it covers, which is what ``WITHHELD_COUNT_SCOPE`` publishes beside
    # it: ``withheld 0`` means no row **this process recorded** is unreachable,
    # and makes no claim about earlier processes. The flag keeps its own
    # meaning.
    return EvidenceCount(
        visible_count=len(decisions),
        withheld_count=None if scoped else loss,
        # ``reachable`` is a number here, so the loss is too - the ``None``
        # answer belongs to the truncated branch above.
        is_lower_bound=bool(loss),
    )


def list_persisted_policy_decisions(
    *,
    resource: str | None = None,
    limit: int = 100,
    tenant_ids: list[str] | None = None,
    decision_id: str | None = None,
) -> list[PolicyDecision]:
    """Decisions from the configured store only, or nothing when none is configured."""
    if not _STORE:
        return []
    return _STORE.list_decisions(
        resource=resource, limit=limit, tenant_ids=tenant_ids, decision_id=decision_id
    )
