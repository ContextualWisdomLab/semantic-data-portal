"""A published evidence count must declare the window that bounds it.

The counts had a lower-bound flag already, but its premise was narrower than
the thing it guarded: the flag asked whether the *read page* had saturated
``EVIDENCE_COUNT_CEILING`` (100_000) and was blind to the *retention window*
(``MAX_IN_MEMORY_AUDIT_EVENTS``, 2000) that actually binds in the documented
``uvicorn sdp.api:app`` configuration - 50x smaller, and the only one a buyer
reaches. Measured over 2200 anonymous ``GET /browse/{id}/schema`` calls at head
317732a:

    evidence.recorded_audit_event_count()          2200
    published audit_event_count                    2000
    published audit_event_count_is_lower_bound    False

So the product recorded 2200, published 2000, and said that 2000 was not a
lower bound. The cap-independent counters that exist to answer this exact
question - their docstring says a count "does not silently stop rising at the
cap" - were
read by twelve call sites in two test files and by **no published surface**.
Every one of those twelve reads a delta rather than an absolute value, which is
why none of them noticed that the counters were never restored between tests.

**The first repair of that defect was worse than the defect.** It derived the
loss as ``recorded - MAX_IN_MEMORY_AUDIT_EVENTS``: one counter minus **one**
cap, while the reachable set is the id-deduped union of **two** windows each
capped at that number. Rows reaching only ``evidence._AUDIT_EVENT_LOG`` - every
OIDC mapping row, since ``authz`` imports ``append_audit_event`` from there and
never touches ``catalog._AUDIT_LOG`` - raised the counter without shrinking the
union. Measured over HTTP: 2000 schema refusals plus 300 OIDC previews left
2300 recorded, 2300 still reachable, **nothing destroyed**, and the product
published ``withheld_audit_event_count: 300`` with the flag true on all three
surfaces. A missing flag understates; a fabricated quantity in this vocabulary
is a number a reader acts on, naming destroyed governance evidence that still
existed.

``test_the_sum_invariant_holds_when_one_window_is_fed_alone`` is the test that
was missing. The first draft's invariant test drove only
``/browse/{id}/schema``, which writes the same ids into both windows, so the
de-duplication in ``catalog.list_audit_events`` hid the union and the invariant
held by accident. A test that can only confirm its author is not a test.
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from sdp import catalog, evidence
from sdp_core.contracts import AuditEvent, DatasetPatchRequest, PolicyDecision
from sdp.api import app
from sdp.enterprise_evidence import build_enterprise_evidence_pack
from sdp.observability import (
    _bound_series as prometheus_bound_series,
    _withheld_series as prometheus_withheld_series,
    build_observability_manifest,
    prometheus_metrics_text,
)

client = TestClient(app)


def _record_over_the_window(extra: int) -> int:
    """Record ``window + extra`` audit events and policy decisions over HTTP.

    Anonymous, through the gated route, because that is the reachable path: the
    caller cannot read a row but every attempt is still recorded, which is what
    makes an unauthenticated caller able to push the window past its cap.
    """
    target = evidence.MAX_IN_MEMORY_AUDIT_EVENTS + extra
    while evidence.recorded_audit_event_count() < target:
        client.get("/browse/crm-customer-master/schema")
    return evidence.recorded_audit_event_count()


def _record_into_the_evidence_window_only(count: int) -> int:
    """Record ``count`` audit events that reach one window and not the other.

    ``POST /enterprise/auth/oidc-preview`` with an actor files its row through
    ``authz.record_oidc_mapping_audit_event`` -> ``evidence.append_audit_event``
    (api.py), which never touches ``catalog._AUDIT_LOG``. That asymmetry is the
    whole point: it raises the recorded counter without shrinking the reachable
    union, so a loss derived from a single cap reports rows destroyed that are
    still readable.
    """
    body = {
        "claims": {
            "sub": "window-probe",
            "groups": ["admins"],
            "tenant_id": "acme-finance",
            "exp": int(time.time()) + 3600,
        },
        "actor": "admin",
    }
    accepted = 0
    for _ in range(count):
        if client.post("/enterprise/auth/oidc-preview", json=body).status_code == 200:
            accepted += 1
    assert accepted == count, f"only {accepted} of {count} previews recorded"
    return accepted


def _reachable_audit_ids() -> set[str]:
    """Every audit id a reader can still reach, across both windows."""
    return {event.id for event in catalog._AUDIT_LOG} | {
        event.id for event in evidence._AUDIT_EVENT_LOG
    }


def test_a_trimmed_window_declares_the_published_count_a_lower_bound() -> None:
    """The reproduction, on every surface that publishes the pair."""
    recorded = _record_over_the_window(200)
    assert recorded > evidence.MAX_IN_MEMORY_AUDIT_EVENTS, recorded

    pack = build_enterprise_evidence_pack()
    assert pack["audit_event_count_is_lower_bound"] is True
    assert pack["policy_decision_count_is_lower_bound"] is True

    metrics = build_observability_manifest()["metrics"]
    assert metrics["audit_events_observed_total_is_lower_bound"] is True
    assert metrics["policy_decisions_observed_total_is_lower_bound"] is True


def test_the_withheld_count_closes_the_gap_to_what_was_recorded() -> None:
    """A flag says "more exist"; the withheld count says how many more.

    The same sum invariant the bounded lists carry: what is visible plus what
    was withheld is what there was.
    """
    recorded = _record_over_the_window(200)

    pack = build_enterprise_evidence_pack()
    assert pack["audit_event_count"] + pack["withheld_audit_event_count"] == recorded
    assert (
        pack["policy_decision_count"] + pack["withheld_policy_decision_count"]
        == evidence.recorded_policy_decision_count()
    )

    metrics = build_observability_manifest()["metrics"]
    assert (
        metrics["audit_events_observed_total"] + metrics["audit_events_withheld_total"]
        == recorded
    )
    assert (
        metrics["policy_decisions_observed_total"]
        + metrics["policy_decisions_withheld_total"]
        == evidence.recorded_policy_decision_count()
    )


def test_every_published_lower_bound_flag_has_a_withheld_sibling() -> None:
    """The structural half: enumerated from the payloads, not listed by hand.

    A flag alone only says the number is wrong, so a surface that publishes one
    must publish how much it left out.

    **The reach of this guard is exactly "flags that exist", not "counts from a
    bounded window".** Its loop body skips every key that does not end in
    ``_is_lower_bound``, so a bounded count that carries no flag at all is
    invisible to it - which is how the defect being repaired here originally
    shipped. The first draft of this docstring claimed the wider property
    ("including a surface that does not exist yet") and was false when written:
    measured at the time, ``request_observations_total`` is ``len()`` of a
    ``deque(maxlen=500)``, read 500 after 650 requests, is published in the very
    dict this walk iterates, carries neither a flag nor a withheld sibling, and
    this guard was green. A planted ``"audit_events_page_total":
    len(audit_events)`` in the same dict also passed.

    Closing that needs a premise of "counts published from a bounded window",
    derived structurally - the AST technique in
    ``test_no_published_count_is_the_length_of_a_paged_read`` extended to
    module-level containers bounded by a ``maxlen`` or a ``del x[:-CAP]`` trim.
    That is a larger piece of work than this round, and claiming it here rather
    than building it is the defect shape this round exists to remove, so the
    claim is narrowed instead and the gap is recorded.
    """
    _record_over_the_window(200)
    payloads = {
        "enterprise_evidence_pack": build_enterprise_evidence_pack(),
        "observability_metrics": build_observability_manifest()["metrics"],
    }

    missing: list[str] = []
    checked = 0
    for surface, payload in payloads.items():
        for key in payload:
            if not key.endswith("_is_lower_bound"):
                continue
            checked += 1
            subject = key[: -len("_is_lower_bound")]
            # "A withheld number about the same thing", not a guessed spelling.
            # The first draft of this walk listed name transforms, and
            # ``"audit_event_count".replace("_total", ...)`` matched nothing and
            # handed back the subject key - which is always in the payload, so
            # the walk passed while reading no withheld number at all. The
            # premise here is the one that survives a rename: a key that says
            # ``withheld`` and whose other words are the subject's.
            subject_words = set(subject.split("_"))
            if not any(
                "withheld" in sibling.split("_")
                and set(sibling.split("_")) - {"withheld"} <= subject_words
                for sibling in payload
            ):
                missing.append(f"{surface}.{key}")

    assert not missing, missing
    # Not a floor on how many flags exist - a floor goes stale upward in
    # silence. The payloads are the two the product publishes, and each one
    # must contribute at least one flag, so an empty walk cannot pass.
    for surface, payload in payloads.items():
        assert any(key.endswith("_is_lower_bound") for key in payload), surface
    assert checked >= len(payloads)


def test_the_scrape_surface_exposes_every_withheld_number_it_has() -> None:
    """Prometheus is the surface with the fewest words and had no marker at all.

    Derived from the metrics payload rather than listed: a withheld number that
    never reaches the scrape text leaves an operator alerting on a series that
    cannot move. A ``None`` is omitted instead of rendered, because a scrape has
    no way to say "unknown" and ``0`` there would assert that nothing was lost.

    Declared ``gauge``, not ``counter``. The first draft declared these series
    counters and told the operator in the HELP text to build ``rate()`` on them,
    while the value can step backwards - it is derived from a process counter
    against the reachable set, not accumulated at trim time.
    """
    _record_over_the_window(200)
    metrics = build_observability_manifest()["metrics"]
    text = prometheus_metrics_text()

    withheld_keys = [key for key in metrics if key.endswith("_withheld_total")]
    assert withheld_keys, sorted(metrics)
    for key in withheld_keys:
        value = metrics[key]
        # Not ``if value is None: ...`` here. This walk's setup is unscoped and
        # unsaturated, so the value is always a number and that arm never ran -
        # measured: mutating the helper's ``None`` handling to render ``0``
        # survived the suite. The unknown case is pinned against the helper
        # itself, below, where it can actually be reached.
        assert isinstance(value, int), (key, value)
        assert f"sdp_{key} {value}" in text, key
        assert f"# TYPE sdp_{key} gauge" in text, key
        assert f"# TYPE sdp_{key} counter" not in text, key


def test_the_scrape_helper_omits_a_number_it_does_not_have() -> None:
    """The unknown case, pinned against the helper rather than through a route.

    ``withheld_count`` is ``None`` only for a scoped read or a saturated page,
    and neither publication site can produce one - both call unscoped, and the
    read-page ceiling cannot saturate against two 2000-row windows. So the
    branch is unreachable from the product today and a payload-driven test
    cannot exercise it.

    It is kept rather than deleted, which is the opposite of what a different
    surviving mutation in this round called for: without it a scoped or
    saturated publication would render the literal ``None`` into a scrape as a
    metric value. A branch that guards a future hazard gets pinned; a branch
    that duplicates a decision gets deleted.
    """
    assert prometheus_withheld_series("sdp_probe_withheld_total", "probe", None) == []

    rendered = prometheus_withheld_series("sdp_probe_withheld_total", "probe help", 7)
    assert rendered == [
        "# HELP sdp_probe_withheld_total probe help",
        "# TYPE sdp_probe_withheld_total gauge",
        "sdp_probe_withheld_total 7",
    ], rendered


def test_a_store_that_refuses_a_write_reports_the_rows_it_lost() -> None:
    """A store does not trim, but a write it refused destroys the row anyway.

    The first draft returned a flat 0 for the whole store path, on the strength
    of the trimming half of the premise alone. Measured against the store this
    repository already models in
    ``tests/test_request_evidence_correlation.py`` - whose docstring says "a
    write that raises - the deployed Postgres/SQLite configuration can" - five
    attempts raised, the counter stood at five, both windows were empty, and
    the published loss said 0.

    The exception is counted where it happens rather than inferred later from a
    cap, so the number on this path is exact.
    """

    class _RefusingStore:
        """An evidence store whose every write raises."""

        def append_event(self, event: object) -> None:
            """Refuse one audit event."""
            raise RuntimeError("store down")

        def record_decision(self, decision: object) -> None:
            """Refuse one policy decision."""
            raise RuntimeError("store down")

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(evidence, "_STORE", _RefusingStore())
        refused = 0
        for index in range(5):
            try:
                catalog.ingest_event(
                    event_type="probe.event",
                    actor="admin",
                    dataset_id="crm-event",
                    decision="allowed",
                    reason="probe",
                    decision_id=f"refused-{index}",
                    details={},
                )
            except RuntimeError:
                refused += 1
        assert refused == 5, refused
        assert len(evidence._AUDIT_EVENT_LOG) == 0
        assert (
            evidence.unreachable_audit_event_count(
                recorded_count=evidence.recorded_audit_event_count(),
                reachable_count=0,
            )
            == 5
        ), "a store that refused five writes reports no loss"


class _KeepingStore:
    """An evidence store that keeps what it is given and can serve it back.

    Serving it back matters for the ceiling tests: with a store configured
    ``list_persisted_audit_events`` asks the store, so a store that only
    swallows rows cannot produce a saturated read page.
    """

    def __init__(self, *, refuse_appends: bool = False) -> None:
        self.events: list[object] = []
        self.decisions: list[object] = []
        self.refuse_appends = refuse_appends

    def append_event(self, event: object) -> object:
        """Keep one audit event, or refuse it the way a real backend can."""
        if self.refuse_appends:
            raise RuntimeError("audit_events is unavailable")
        self.events.append(event)
        return event

    def record_decision(self, decision: object) -> object:
        """Keep one policy decision, or refuse it."""
        if self.refuse_appends:
            raise RuntimeError("policy_decisions is unavailable")
        self.decisions.append(decision)
        return decision

    def list_events(self, **_kwargs: object) -> list[object]:
        """Serve the kept audit events, newest last, unfiltered."""
        return list(self.events)

    def list_decisions(self, **_kwargs: object) -> list[object]:
        """Serve the kept policy decisions, unfiltered."""
        return list(self.decisions)


def test_a_store_that_keeps_every_row_withholds_nothing() -> None:
    """The flag must not fire where no window trims: a store keeps every row.

    Without this the fix would trade a false "complete" for a false
    "truncated": nothing is appended to the in-memory lists while a store is
    configured, so a process counter compared against them would read every
    recorded row as dropped.

    The first version of this test flooded the window **first** and then
    attached the store, while its docstring said "the in-memory lists stay
    empty with a store configured" - false in the state it had just built,
    where both windows held 2000 rows and 200 rows really had been destroyed.
    It asserted 0, which is what the code returns, so it passed while pinning
    the answer for a state it was not describing. That state is the test below.
    """
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(evidence, "_STORE", _KeepingStore())
        assert evidence.has_configured_evidence_store() is True
        recorded = evidence.recorded_audit_event_count()
        assert (
            evidence.unreachable_audit_event_count(
                recorded_count=recorded, reachable_count=0
            )
            == 0
        )
        assert (
            evidence.unreachable_policy_decision_count(
                recorded_count=evidence.recorded_policy_decision_count(),
                reachable_count=0,
            )
            == 0
        )


def test_a_store_selected_after_a_trim_still_reports_the_rows_already_lost() -> None:
    """Attaching a store does not amnesty the rows the window already dropped.

    This test pinned the opposite until this round's seventh pass. Its earlier
    form recorded a *measured limitation*: 2200 recorded against 2000 reachable
    published ``withheld 200`` with the flag set, and attaching a store with
    nothing else changed published ``withheld 0`` with the flag clear, because
    the store branch returned the refusal counter alone and discarded both of
    its arguments. The repair that derives the store-path loss from this
    process's own successful writes against the whole reachable set closed this
    case as a side effect, and the pinned limitation then read as a gate
    forbidding its own repair - a test asserting that a defect is intended
    behaviour. Re-measured on the repaired tree, both halves report:

    * audit: ``visible 2000, withheld 200, lower bound`` with a store attached,
      identical to the no-store reading. ``list_audit_events`` merges
      ``catalog._AUDIT_LOG`` with the store, so the 2000 survivors stay
      readable and the 200 the window dropped are still named.
    * policy: ``visible 0, withheld 2200, lower bound``.
      ``list_policy_decisions`` returns store rows **exclusively** once a store
      is set, so attaching an empty store takes the policy reachable set from
      2000 to 0 - and the published loss now follows it to 2200 instead of
      understating a total blackout as 0.

    The asymmetry in the two magnitudes is a real property of the two readers,
    and is asserted as one. What is symmetric is the honesty condition, so that
    is what drives both halves here: ``visible + withheld == recorded`` on each
    side, before and after. This stays the round's **third** application of
    "where the behaviour is symmetric across the two counts, one test feeds
    both" - the same application the earlier form reached, re-expressed through
    one shared predicate instead of two parallel assertions. It is not a fourth:
    an earlier draft of this very docstring said "fourth", which would have
    added one more unverifiable ordinal to the pile this pass exists to clear.
    The fourth is the read-ceiling test.

    Reachability, unchanged from the earlier form: ``configure_evidence_store``
    has no caller under ``src/`` (``_STORE`` is bound once at import), so a
    served deployment either has a store for its whole life or never gets one.
    The mid-life transition driven here is in-process only, which is why the
    audit half is the half that matters to a deployment - and it is the half
    that now moves not at all.
    """
    _record_over_the_window(200)
    recorded_audit = evidence.recorded_audit_event_count()
    recorded_policy = evidence.recorded_policy_decision_count()
    before_audit = catalog.count_audit_events()
    before_policy = evidence.count_policy_decisions()
    for before, recorded in (
        (before_audit, recorded_audit),
        (before_policy, recorded_policy),
    ):
        assert before.withheld_count is not None and before.withheld_count > 0, before
        assert before.is_lower_bound is True, before
        assert before.visible_count + before.withheld_count == recorded, before

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(evidence, "_STORE", _KeepingStore())
        after_audit = catalog.count_audit_events()
        after_policy = evidence.count_policy_decisions()
    for after, recorded in (
        (after_audit, recorded_audit),
        (after_policy, recorded_policy),
    ):
        assert after.withheld_count is not None and after.withheld_count > 0, after
        assert after.is_lower_bound is True, after
        assert after.visible_count + after.withheld_count == recorded, after

    # The measured asymmetry, pinned: the audit reading does not move at all,
    # because its rows stay readable through the merged window; the policy
    # reader loses the whole window to the empty store and publishes the whole
    # loss. A future change that made ``list_policy_decisions`` merge its
    # window would move the second pair, and that is a change worth seeing
    # rather than one to absorb silently.
    assert after_audit == before_audit, (after_audit, before_audit)
    assert after_policy.visible_count == 0, (after_policy, before_policy)
    assert after_policy.withheld_count == recorded_policy, (
        after_policy,
        recorded_policy,
    )


def test_the_read_page_ceiling_still_declares_a_lower_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The bound that was already covered stays covered.

    Three things can put a recorded row out of reach - the read ceiling, the
    retention window, and a store that refuses or drops a write - and the
    repair adds the later two without discarding the first.
    """
    for index in range(20):
        catalog.ingest_event(
            event_type="probe.event",
            actor="admin",
            dataset_id="crm-event",
            decision="allowed",
            reason="probe",
            decision_id=f"window-probe-{index}",
            details={},
        )
    monkeypatch.setattr(catalog, "EVIDENCE_COUNT_CEILING", 5)
    counted = catalog.count_audit_events()
    assert counted.visible_count == 5
    assert counted.is_lower_bound is True

def test_the_sum_invariant_holds_when_one_window_is_fed_alone() -> None:
    """The test the first draft was missing, and the reason it was missing.

    The first draft's invariant test drove only ``/browse/{id}/schema``, which
    writes the same ids into both windows; the de-duplication in
    ``catalog.list_audit_events`` then hid the union and the invariant held by
    accident. Feeding one window alone is what separates "measured against the
    reachable set" from "derived from a cap".

    Measured against the first draft: 2000 schema refusals plus 300 OIDC
    previews gave 2300 recorded, 2300 reachable, 0 destroyed - and a published
    ``withheld_audit_event_count`` of 300.
    """
    while evidence.recorded_audit_event_count() < evidence.MAX_IN_MEMORY_AUDIT_EVENTS:
        client.get("/browse/crm-customer-master/schema")
    _record_into_the_evidence_window_only(300)

    recorded = evidence.recorded_audit_event_count()
    reachable = _reachable_audit_ids()
    assert len(reachable) == recorded, (
        f"{recorded - len(reachable)} rows unreachable; the premise of this test is "
        "that none are"
    )

    pack = build_enterprise_evidence_pack()
    assert pack["withheld_audit_event_count"] == 0, (
        "a loss was published for rows that are still readable"
    )
    assert pack["audit_event_count_is_lower_bound"] is False
    assert pack["audit_event_count"] + pack["withheld_audit_event_count"] == recorded

    metrics = build_observability_manifest()["metrics"]
    assert metrics["audit_events_withheld_total"] == 0
    assert metrics["audit_events_observed_total_is_lower_bound"] is False


def test_a_scoped_count_publishes_no_number_it_cannot_know() -> None:
    """A trimmed row's scope is unrecoverable, so a scope reports no quantity.

    The first draft bound a scoped ``visible_count`` to the process-wide loss,
    so ``resource="no-such-dataset"`` stated that a dataset which never held an
    audit row had lost 300 of them. ``None`` is the honest value and is not 0:
    0 would claim nothing was lost.
    """
    _record_over_the_window(200)

    for scope in ({"resource": "no-such-dataset"}, {"tenant_ids": []}):
        counted = catalog.count_audit_events(**scope)
        assert counted.withheld_count is None, (scope, counted)
        # Still a lower bound: a trimmed row might have matched this scope.
        assert counted.is_lower_bound is True, (scope, counted)
        decided = evidence.count_policy_decisions(**scope)
        assert decided.withheld_count is None, (scope, decided)


def test_the_read_page_ceiling_publishes_no_number_it_cannot_know(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The other bound gets the same treatment, for the same reason.

    The first draft reported ``withheld_count == 0`` when the ceiling truncated
    the page, so the published pair read "5 visible, 0 withheld" while 2000 rows
    were reachable - the pair denied 1995 of them. The ceiling's loss is not
    measured here, so it is not a number here.
    """
    _record_over_the_window(200)
    monkeypatch.setattr(catalog, "EVIDENCE_COUNT_CEILING", 5)

    # Both sides. The first draft asserted only the audit side, and a mutation
    # that flipped the *policy* saturated branch's flag to ``False`` survived
    # the suite - the branch is reachable through ``count_policy_decisions``
    # and nothing read it. The two sibling tests here were two-sided already;
    # this one was not, which is the whole difference between a guard and a
    # guard that happens to be pointed at the half that works.
    #
    # The policy side reads ``EVIDENCE_COUNT_CEILING`` from ``catalog`` inside
    # the function, so the one monkeypatch above reaches both.
    for counted in (catalog.count_audit_events(), evidence.count_policy_decisions()):
        assert counted.visible_count == 5, counted
        assert counted.is_lower_bound is True, counted
        assert counted.withheld_count is None, counted

def test_the_published_withheld_number_is_never_null_on_a_served_response() -> None:
    """What makes the generated contract's ``number`` honest, stated as a test.

    ``withheld_count`` is ``int | None``, and
    ``src/sdp/api_response_contract.py`` publishes the two fields as
    ``{'type': 'number'}`` - which is correct only because no route reaches a
    ``None``. Both publication sites call the count functions unscoped, and the
    read-page ceiling cannot saturate on the in-memory path (two windows of
    2000 against a ceiling of 100,000). The generator derives types from
    executed responses, so it has never seen the other branch.

    This pins the premise rather than the consequence. Publish a scoped count
    from either surface and this fails, which is the signal to regenerate the
    contract - the generator spells a nullable field ``{}`` - instead of
    shipping a response that contradicts its own published schema.
    """
    _record_over_the_window(200)

    pack = build_enterprise_evidence_pack()
    metrics = build_observability_manifest()["metrics"]
    for payload, key in (
        (pack, "withheld_audit_event_count"),
        (pack, "withheld_policy_decision_count"),
        (metrics, "audit_events_withheld_total"),
        (metrics, "policy_decisions_withheld_total"),
    ):
        assert isinstance(payload[key], int), (key, payload[key])


def test_a_row_recorded_while_the_page_is_read_is_not_published_as_destroyed() -> None:
    """The two samples the loss is made of must be taken in the safe order.

    The first version of this repair read the reachable page first and the
    monotonic counter afterwards, so a row recorded between the two samples
    came out as a row that could no longer be read. Measured over HTTP with
    four writer threads and 1400 rows against a 2000-row cap - nothing trimmed,
    true loss 0 at every instant - 34 of 233 reads of
    ``/enterprise/observability`` published a nonzero withheld count with the
    lower-bound flag set, and the same state at ``317732a`` published 0 because
    the comparison was against a constant cap. So it was a regression, and it
    was the withdrawn first draft's defect through a different mechanism: a
    fabricated quantity of destroyed governance evidence.

    This reproduces it without threads, which is why it belongs in the suite: a
    single writer landing inside the page read is the whole mechanism. With the
    counter sampled first the page can only be larger than the set the counter
    describes, so the subtraction can only come out low - a concurrent loss is
    understated for one read instead of invented.
    """
    real_page = catalog.list_audit_events
    seen = {"calls": 0}

    def recording_page(**kwargs: object) -> list[object]:
        """Return the real page, recording one row while it is built."""
        page = real_page(**kwargs)  # type: ignore[arg-type]
        seen["calls"] += 1
        if seen["calls"] == 1:
            catalog.ingest_event(
                event_type="probe.event",
                actor="admin",
                dataset_id="crm-event",
                decision="allowed",
                reason="probe",
                decision_id="sampling-order-1",
                details={},
            )
        return page

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(catalog, "list_audit_events", recording_page)
        during = catalog.count_audit_events()
    assert seen["calls"] >= 1, "the page was never read, so nothing was overlapped"

    recorded = evidence.recorded_audit_event_count()
    reachable = len(real_page(limit=catalog.EVIDENCE_COUNT_CEILING))
    assert recorded == reachable, (recorded, reachable)
    assert during.withheld_count == 0, during
    assert during.is_lower_bound is False, during


def test_a_decision_recorded_while_the_page_is_read_is_not_published_as_destroyed() -> None:
    """The policy half of the sampling order, because one half is not a guard.

    The audit-side test above was written first and alone, and a mutation that
    moved the policy counter back after its page **survived the suite** - the
    same one-sided-guard shape this round already hit on the read-page ceiling,
    hit twice. The two count functions are separate code with separate globals,
    so a repair applied to both needs a guard that reaches both.
    """
    real_page = evidence.list_policy_decisions
    seen = {"calls": 0}

    def recording_page(**kwargs: object) -> list[object]:
        """Return the real page, recording one decision while it is built."""
        page = real_page(**kwargs)  # type: ignore[arg-type]
        seen["calls"] += 1
        if seen["calls"] == 1:
            evidence.record_policy_decision(
                PolicyDecision(
                    subject="admin",
                    resource="crm-event",
                    action="browse",
                    effect="allow",
                    decision_id="sampling-order-policy-1",
                )
            )
        return page

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(evidence, "list_policy_decisions", recording_page)
        during = evidence.count_policy_decisions()
    assert seen["calls"] >= 1, "the page was never read, so nothing was overlapped"

    recorded = evidence.recorded_policy_decision_count()
    reachable = len(real_page(limit=catalog.EVIDENCE_COUNT_CEILING))
    assert recorded == reachable, (recorded, reachable)
    assert during.withheld_count == 0, during
    assert during.is_lower_bound is False, during


def test_the_no_store_path_cannot_saturate_the_read_page_ceiling() -> None:
    """Why the published ``withheld`` is a number on every served response.

    ``withheld_count`` is ``int | None``, and ``api_response_contract.py``
    publishes the four fields as ``{'type': 'number'}``. That is true of served
    responses for two reasons, and only one of them used to be written down:
    no route passes a scope, and - with no store configured - the reachable set
    is bounded by the two retention windows, which cannot reach the read-page
    ceiling. The second reason is an inequality between three constants, so it
    is asserted rather than asserted *about*: raising a window cap above half
    the ceiling makes this red instead of making a route publish ``null``.

    With a store configured the ceiling **is** reachable, which is the state
    the next test covers; the answer there is a number for a different reason.
    """
    assert (
        evidence.MAX_IN_MEMORY_AUDIT_EVENTS + evidence.MAX_IN_MEMORY_AUDIT_EVENTS
        < catalog.EVIDENCE_COUNT_CEILING
    ), (evidence.MAX_IN_MEMORY_AUDIT_EVENTS, catalog.EVIDENCE_COUNT_CEILING)
    assert (
        evidence.MAX_IN_MEMORY_POLICY_DECISIONS < catalog.EVIDENCE_COUNT_CEILING
    ), (evidence.MAX_IN_MEMORY_POLICY_DECISIONS, catalog.EVIDENCE_COUNT_CEILING)


def test_a_store_past_the_read_ceiling_publishes_the_number_it_knows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A truncated read says nothing about refused writes, and must not hide them.

    The saturated branch used to return ``withheld_count=None`` unconditionally.
    Measured at exactly ``EVIDENCE_COUNT_CEILING`` store rows: both
    ``/enterprise/evidence-pack`` and ``/enterprise/observability`` served
    ``null`` for a field the generated contract declares ``number``, the audit
    series vanished from ``/metrics`` entirely, and one refused append sat in
    ``_STORE_AUDIT_WRITE_FAILURES`` one call away. The shipped image sets
    ``SDP_SQLITE_PATH`` (``Dockerfile``) and neither store prunes, so this is
    the default deployment at scale, reachable by anonymous traffic one audit
    row per request.
    """
    store = _KeepingStore()
    monkeypatch.setattr(evidence, "_STORE", store)
    monkeypatch.setattr(catalog, "EVIDENCE_COUNT_CEILING", 3)
    for index in range(4):
        catalog.ingest_event(
            event_type="probe.event",
            actor="admin",
            dataset_id="crm-event",
            decision="allowed",
            reason="probe",
            decision_id=f"ceiling-{index}",
            details={},
        )
        # Fed explicitly, because ``ingest_event`` writes an audit row and no
        # decision. An earlier draft of this test added the policy assertion
        # below without this: with a store configured
        # ``list_policy_decisions`` returns store rows **exclusively**, so the
        # policy page held nothing, never saturated, and the assertion read
        # ``EvidenceCount(visible_count=0, withheld_count=0,
        # is_lower_bound=False)``. The round's rule is that one test drives
        # both counts - driving them means feeding both, not asserting twice.
        evidence.record_policy_decision(
            PolicyDecision(
                subject="admin",
                resource="crm-event",
                action="browse",
                effect="allow",
                decision_id=f"ceiling-decision-{index}",
            )
        )

    for counted in (catalog.count_audit_events(), evidence.count_policy_decisions()):
        assert counted.is_lower_bound is True, counted
        assert counted.withheld_count == 0, counted
    assert catalog.count_audit_events().visible_count >= 3
    assert evidence.count_policy_decisions().visible_count >= 3

    pack = build_enterprise_evidence_pack()
    assert pack["withheld_audit_event_count"] == 0, pack["withheld_audit_event_count"]
    manifest = build_observability_manifest()
    assert manifest["metrics"]["audit_events_withheld_total"] == 0

    store.refuse_appends = True
    with pytest.raises(RuntimeError):
        catalog.ingest_event(
            event_type="probe.event",
            actor="admin",
            dataset_id="crm-event",
            decision="allowed",
            reason="probe",
            decision_id="ceiling-refused",
            details={},
        )
    with pytest.raises(RuntimeError):
        evidence.record_policy_decision(
            PolicyDecision(
                subject="admin",
                resource="crm-event",
                action="browse",
                effect="allow",
                decision_id="ceiling-refused-decision",
            )
        )
    store.refuse_appends = False
    refused = catalog.count_audit_events()
    assert refused.is_lower_bound is True, refused
    assert refused.withheld_count == 1, refused
    refused_policy = evidence.count_policy_decisions()
    assert refused_policy.is_lower_bound is True, refused_policy
    assert refused_policy.withheld_count == 1, refused_policy


def test_a_scoped_count_with_nothing_lost_does_not_claim_a_lower_bound() -> None:
    """The pair's two null-withheld cases do not share one flag.

    ``EvidenceCount``'s docstring used to finish "The flag stays true in those
    cases", which is true of a saturated page - it has seen that more exist -
    and false of a scope. A scoped read is a lower bound only when the
    *process* lost something, so a scoped read of a ledger that has lost
    nothing publishes ``withheld_count=None`` beside ``is_lower_bound=False``.
    The test that covers the scoped branch floods the window first, so it only
    ever sees ``True``; this is the other half.
    """
    client.get("/browse/crm-customer-master/schema")
    assert catalog.count_audit_events().withheld_count == 0

    scoped = catalog.count_audit_events(resource="no-such-dataset")
    assert scoped.visible_count == 0, scoped
    assert scoped.withheld_count is None, scoped
    assert scoped.is_lower_bound is False, scoped

    tenant_scoped = evidence.count_policy_decisions(tenant_ids=["demo"])
    assert tenant_scoped.withheld_count is None, tenant_scoped
    assert tenant_scoped.is_lower_bound is False, tenant_scoped


def test_an_empty_resource_is_not_a_scope() -> None:
    """The count and its page must read one argument one way.

    ``list_audit_events`` filters with ``if resource``, so ``resource=""``
    returns the unscoped page; the count's predicate was
    ``resource is not None``, so it called that page scoped and suppressed a
    withheld number it could compute. ``tenant_ids`` is deliberately the other
    way - ``None`` means every tenant and an empty list yields no rows, so
    presence is the scope there.
    """
    client.get("/browse/crm-customer-master/schema")
    unscoped = catalog.count_audit_events()
    empty = catalog.count_audit_events(resource="")
    assert empty.visible_count == unscoped.visible_count, (empty, unscoped)
    assert empty.withheld_count == unscoped.withheld_count, (empty, unscoped)

    policy_unscoped = evidence.count_policy_decisions()
    policy_empty = evidence.count_policy_decisions(resource="")
    assert policy_empty.visible_count == policy_unscoped.visible_count
    assert policy_empty.withheld_count == policy_unscoped.withheld_count

    assert catalog.count_audit_events(tenant_ids=[]).withheld_count is None


def test_the_scrape_publishes_the_lower_bound_as_its_own_series() -> None:
    """The flag has to be on the surface that can lose the withheld series.

    ``_withheld_series`` omits a series it cannot quantify and justified that
    with "the paired ``*_is_lower_bound`` field on the JSON surface still says
    more rows exist" - a control on a different surface. Measured: no series
    name emitted by ``prometheus_metrics_text`` contained ``lower_bound``, so
    the scrape published ``sdp_audit_events_observed_total 100000`` as a bare
    number with nothing to say the true total was larger.
    """
    text = prometheus_metrics_text()
    for name in (
        "sdp_audit_events_observed_total_is_lower_bound",
        "sdp_policy_decisions_observed_total_is_lower_bound",
    ):
        assert f"# TYPE {name} gauge" in text, name
        assert f"{name} 0" in text, name

    _record_over_the_window(200)
    flooded = prometheus_metrics_text()
    assert "sdp_audit_events_observed_total_is_lower_bound 1" in flooded
    assert "sdp_policy_decisions_observed_total_is_lower_bound 1" in flooded

    assert prometheus_bound_series("sdp_probe_bound", "probe help", True) == [
        "# HELP sdp_probe_bound probe help",
        "# TYPE sdp_probe_bound gauge",
        "sdp_probe_bound 1",
    ]


def test_a_store_that_predates_this_process_publishes_an_exact_count_and_its_scope() -> None:
    """A restart publishes the count it can read, and says what the 0 covers.

    This test asserted the opposite for one draft, and the draft is withdrawn.
    The argument for it was: the published loss on the store path *was, at that
    point in the round,* this process's refusal counter alone, which starts at 0
    while a loss can be permanent in the ledger, so after a restart the pair
    reads ``withheld 0`` beside ``is_lower_bound false`` - seemingly a positive
    claim that nothing was lost. (The branch is no longer that counter alone;
    the restart reading it describes is unchanged, because a store holding more
    rows than this process recorded still subtracts to nothing.)
    The draft made ``reachable > recorded`` set the flag to carry that case.

    Two measurements killed it.

    **It priced an exact count as a lower bound, permanently, in the shipped
    deployment.** ``docker-compose.yml`` sets ``SDP_SQLITE_PATH`` on a named
    volume, so rows survive every restart and ``reachable > recorded`` holds for
    the whole life of every process after the first. Measured: 5 rows written,
    restart, 10 more written - 15 reachable, 15 published, nothing truncated
    anywhere - and all three surfaces flagged 15 as a lower bound beside
    ``withheld 0``. The flag's own published HELP says "1 when more audit events
    exist than the observed gauge can show"; 15 existed and the gauge showed 15.

    **And it did not cover the case it was added for.** With
    ``reachable = prior_rows + this_process_successes`` and
    ``recorded = this_process_successes + this_process_refusals``, the predicate
    reduces to ``prior_rows > this_process_refusals`` - so it is False exactly
    when the earlier process persisted *nothing*, which is what a store that
    refused every write produces. The draft's own guard seeded 7 prior rows,
    i.e. it was pointed at the half that worked. The second half is asserted
    below, so this cannot be re-added without a test saying it misses its case.

    What is published instead: the count that *is* readable, the loss this
    process observed, and ``withheld_count_scope`` naming what that number
    covers - on both JSON surfaces and in both ``/metrics`` HELP lines. The
    restart's ``withheld 0`` is then true as published: this process lost none.
    The rows an earlier process recorded and lost are not knowable from here at
    all - the fact lived in that process's memory, and persisting it would have
    needed a write to the store that was refusing writes.
    """
    store = _KeepingStore()
    store.events.extend(
        AuditEvent(
            id=f"earlier-process-{index}",
            actor="admin",
            action="dataset.publish",
            resource="crm-event",
            result="allowed",
            decision_id=f"earlier-decision-{index}",
        )
        for index in range(7)
    )
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(evidence, "_STORE", store)
        assert evidence.recorded_audit_event_count() == 0, "this process wrote none"
        counted = catalog.count_audit_events()

    assert counted.visible_count == 7, counted
    assert counted.withheld_count == 0, counted
    # Exact, untruncated, and said so. The withdrawn clause set this True.
    assert counted.is_lower_bound is False, counted

    # The policy side, from the same state: its window is separate code with a
    # separate global, and a one-sided guard is what let the sampling-order
    # mutation survive on this very repair.
    store.decisions.extend(
        PolicyDecision(
            subject="admin",
            resource="crm-event",
            action="browse",
            effect="allow",
            decision_id=f"earlier-policy-{index}",
        )
        for index in range(4)
    )
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(evidence, "_STORE", store)
        policy_counted = evidence.count_policy_decisions()
    assert policy_counted.visible_count == 4, policy_counted
    assert policy_counted.withheld_count == 0, policy_counted
    assert policy_counted.is_lower_bound is False, policy_counted

    # The scope is what carries the restart boundary now, so it is asserted
    # where the condition exists rather than only in its own test.
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(evidence, "_STORE", store)
        pack = build_enterprise_evidence_pack()
    assert pack["withheld_count_scope"] == evidence.WITHHELD_COUNT_SCOPE, pack
    assert pack["audit_event_count_is_lower_bound"] is False, pack
    assert pack["policy_decision_count_is_lower_bound"] is False, pack

    # The second half of the reduction: the state the withdrawn clause was for.
    # A store that refused every write holds nothing, so ``reachable`` is 0 and
    # ``recorded`` is the refusal count - the predicate the draft used is False
    # here, for the one failure mode it was added to carry.
    refusing = _KeepingStore(refuse_appends=True)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(evidence, "_STORE", refusing)
        for index in range(3):
            with pytest.raises(RuntimeError):
                evidence.append_audit_event(
                    AuditEvent(
                        id=f"refused-{index}",
                        actor="admin",
                        action="dataset.publish",
                        resource="crm-event",
                        result="allowed",
                        decision_id=f"refused-decision-{index}",
                    )
                )
        lost = catalog.count_audit_events()
        recorded_here = evidence.recorded_audit_event_count()
    assert recorded_here == 3, recorded_here
    assert lost.visible_count == 0, lost
    # This process saw the loss, so it publishes it exactly.
    assert lost.withheld_count == 3, lost
    assert lost.is_lower_bound is True, lost
    # And the withdrawn predicate, evaluated on this state: reachable 0 is not
    # greater than recorded 3, so the clause would not have fired.
    assert not (lost.visible_count > recorded_here), (lost, recorded_here)


def test_a_store_that_loses_rows_this_process_wrote_publishes_them_as_withheld() -> None:
    """A store can lose a row it accepted, and the loss must not read as 0.

    A draft of the store branch returned the refusal counter **alone** and
    discarded both of its arguments, which made its own opening sentence -
    "Measured against what is actually reachable, never against a cap" - false
    of the code under it. Measured by review: 10 rows written through a store
    that keeps and serves them, 6 then removed from the store by something
    outside the app - an operator prune, a restore from an older snapshot, a
    retention job - and the product published ``visible 4, withheld 0,
    is_lower_bound false`` on all three surfaces. Six recorded rows unreadable,
    answered with 0, by the same vocabulary that says "``null`` says the number
    is not recoverable, which is not the same as 0 and must not be published
    as 0".

    Reachable in the shipped configuration, not only under a fake: with a store
    configured ``append_audit_event`` takes the ``if _STORE`` arm and the
    in-memory window never holds the row, so nothing else can serve it back.

    What is published instead is a lower bound that cannot be inflated.
    ``successes = recorded - refusals`` is what this process put in the store;
    ``reachable`` counts rows from **every** process, so ``successes >
    reachable`` means at least the difference of *this process's own* rows is
    gone. Another process's rows can only mask that, never inflate it.

    Both counts, from one test, because the two sides are separate code with
    separate globals - the rule this round learned three times.
    """
    store = _KeepingStore()
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(evidence, "_STORE", store)
        # A process that has only this store: the windows are what a restart
        # starts with, and the counters likewise.
        patch.setattr(evidence, "_AUDIT_EVENT_LOG", [])
        patch.setattr(evidence, "_POLICY_DECISION_LOG", [])
        patch.setattr(catalog, "_AUDIT_LOG", [])
        patch.setattr(evidence, "_RECORDED_AUDIT_EVENT_COUNT", 0)
        patch.setattr(evidence, "_RECORDED_POLICY_DECISION_COUNT", 0)
        patch.setattr(evidence, "_STORE_AUDIT_WRITE_FAILURES", 0)
        patch.setattr(evidence, "_STORE_DECISION_WRITE_FAILURES", 0)
        for index in range(10):
            evidence.append_audit_event(
                AuditEvent(
                    id=f"vanishing-{index}",
                    actor="admin",
                    action="dataset.publish",
                    resource="crm-event",
                    result="allowed",
                    decision_id=f"vanishing-decision-{index}",
                )
            )
            evidence.record_policy_decision(
                PolicyDecision(
                    subject="admin",
                    resource="crm-event",
                    action="browse",
                    effect="allow",
                    decision_id=f"vanishing-policy-{index}",
                )
            )

        healthy_audit = catalog.count_audit_events()
        healthy_policy = evidence.count_policy_decisions()

        # Nothing in the app did this; that is the point.
        del store.events[:6]
        del store.decisions[:6]

        lost_audit = catalog.count_audit_events()
        lost_policy = evidence.count_policy_decisions()

    for healthy in (healthy_audit, healthy_policy):
        assert healthy.visible_count == 10, healthy
        assert healthy.withheld_count == 0, healthy
        assert healthy.is_lower_bound is False, healthy

    for lost in (lost_audit, lost_policy):
        assert lost.visible_count == 4, lost
        # The number the draft published as 0.
        assert lost.withheld_count == 6, lost
        assert lost.is_lower_bound is True, lost


def test_a_store_holding_rows_from_an_earlier_process_does_not_read_as_a_loss() -> None:
    """The other direction of the same comparison, so the fix cannot overshoot.

    ``successes > reachable`` is the signal; ``reachable > successes`` is the
    ordinary state of any restart over a persistent volume and must publish
    nothing. Without this, the repair for the vanished-row case would reinvent
    the withdrawn ``predates`` clause from the other side.
    """
    store = _KeepingStore()
    store.events.extend(
        AuditEvent(
            id=f"earlier-boot-{index}",
            actor="admin",
            action="dataset.publish",
            resource="crm-event",
            result="allowed",
            decision_id=f"earlier-boot-decision-{index}",
        )
        for index in range(5)
    )
    store.decisions.extend(
        PolicyDecision(
            subject="admin",
            resource="crm-event",
            action="browse",
            effect="allow",
            decision_id=f"earlier-boot-policy-{index}",
        )
        for index in range(5)
    )
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(evidence, "_STORE", store)
        patch.setattr(evidence, "_AUDIT_EVENT_LOG", [])
        patch.setattr(evidence, "_POLICY_DECISION_LOG", [])
        patch.setattr(catalog, "_AUDIT_LOG", [])
        patch.setattr(evidence, "_RECORDED_AUDIT_EVENT_COUNT", 0)
        patch.setattr(evidence, "_RECORDED_POLICY_DECISION_COUNT", 0)
        patch.setattr(evidence, "_STORE_AUDIT_WRITE_FAILURES", 0)
        patch.setattr(evidence, "_STORE_DECISION_WRITE_FAILURES", 0)
        for index in range(10):
            evidence.append_audit_event(
                AuditEvent(
                    id=f"this-boot-{index}",
                    actor="admin",
                    action="dataset.publish",
                    resource="crm-event",
                    result="allowed",
                    decision_id=f"this-boot-decision-{index}",
                )
            )
            evidence.record_policy_decision(
                PolicyDecision(
                    subject="admin",
                    resource="crm-event",
                    action="browse",
                    effect="allow",
                    decision_id=f"this-boot-policy-{index}",
                )
            )
        counted_audit = catalog.count_audit_events()
        counted_policy = evidence.count_policy_decisions()

    for counted in (counted_audit, counted_policy):
        assert counted.visible_count == 15, counted
        assert counted.withheld_count == 0, counted
        assert counted.is_lower_bound is False, counted


def test_a_rolled_back_mutation_does_not_publish_a_destroyed_row() -> None:
    """The refusal that a rollback undid destroyed nothing, so it is not a loss.

    ``append_audit_event`` counts a refused store write where the loss happens,
    which is the only place the exception is visible. But
    ``catalog._commit_dataset_with_evidence`` catches exactly that exception and
    undoes the mutation the row would have evidenced - restoring the previous
    dataset and popping the schema snapshot - so nothing was destroyed and
    counting it publishes a fabricated loss. Measured before the repair: one
    rolled-back patch published one destroyed audit row.

    The no-op branches are deliberately not hooked: they call
    ``_record_audit_event`` directly with nothing to roll back, so a refusal
    there really is a lost row and stays counted.
    """
    before = catalog.get_dataset("crm-customer-master").description
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(evidence, "_STORE", _KeepingStore(refuse_appends=True))
        with pytest.raises(RuntimeError):
            catalog.patch_dataset(
                "crm-customer-master",
                DatasetPatchRequest(description="a changed description for the guard"),
                actor="admin",
                decision_id="rolled-back-decision",
                change_reason="guard",
            )
        counted = catalog.count_audit_events()

    assert catalog.get_dataset("crm-customer-master").description == before
    assert evidence._STORE_AUDIT_WRITE_FAILURES == 0
    assert counted.withheld_count == 0, counted
    assert counted.is_lower_bound is False, counted


def test_a_rollback_with_no_refusal_to_forget_steals_no_recording() -> None:
    """``forget_refused_audit_write`` un-counts the attempt only beside a refusal.

    The pass that made the rollback un-count the recording attempt as well left
    this half unpinned, and the mutation that moves the recording decrement
    *outside* the refusal guard survived the whole suite. It survived because
    the one existing rollback test drives the function with a counted refusal,
    where the mutant and the original behave identically - both drop both
    counts by one. They differ only when the function is called with no refusal
    counted, and nothing reached that state.

    It is reachable from the product, not just from here: the rollback in
    ``catalog._commit_dataset_with_evidence`` sits under a bare
    ``except Exception:``, so anything ``_record_audit_event`` raises before a
    store refusal is counted - a validation error, a window append failure -
    arrives here with ``_STORE_AUDIT_WRITE_FAILURES == 0``. The mutant then
    lowers the recording count for a row that *does* exist, stealing the count
    of some earlier, unrelated write. Measured: one recorded row, no counted
    refusal, mutant publishes ``recorded 0`` against a reachable row.

    Both halves are driven here, and the third assertion pins a deliberate
    **asymmetry** rather than a symmetry: there is no policy-side equivalent of
    this function (``_RECORDED_POLICY_DECISION_COUNT`` is only ever
    incremented), so the policy counter stays strictly monotonic while the
    audit one does not. A future change that "fixed" that into symmetry would
    move this assertion, which is the point of writing it down.
    """
    client.get("/browse/crm-customer-master/schema")
    recorded_before = evidence.recorded_audit_event_count()
    policy_before = evidence.recorded_policy_decision_count()
    assert recorded_before > 0, recorded_before
    assert evidence._STORE_AUDIT_WRITE_FAILURES == 0

    # No refusal to forget: neither counter may move, and the return is the
    # untouched refusal count.
    assert evidence.forget_refused_audit_write() == 0
    assert evidence.recorded_audit_event_count() == recorded_before
    assert evidence.recorded_policy_decision_count() == policy_before

    # Beside a counted refusal: both counts drop by exactly one, and the
    # return is the refusal count after the decrement.
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(evidence, "_STORE_AUDIT_WRITE_FAILURES", 2)
        assert evidence.forget_refused_audit_write() == 1
        assert evidence._STORE_AUDIT_WRITE_FAILURES == 1
    assert evidence.recorded_audit_event_count() == recorded_before - 1
    assert evidence.recorded_policy_decision_count() == policy_before


def test_both_surfaces_publish_what_the_withheld_numbers_are_scoped_to() -> None:
    """A number whose scope a reader has to guess is the defect one level up.

    Both withheld counts come from this process's own recording counters, so a
    row an earlier process recorded and lost is not in them and is not knowable
    from here. That boundary is published rather than left to the field name.
    (Not "monotonic counters", which an earlier form of this docstring said:
    the audit counter gives up strict monotonicity on the rollback path, where
    ``forget_refused_audit_write`` un-counts a write that did not happen. The
    policy counter has no such path and is still strictly monotonic - the
    asymmetry is deliberate and is pinned by
    ``test_a_rollback_with_no_refusal_to_forget_steals_no_recording``.)
    """
    assert build_enterprise_evidence_pack()["withheld_count_scope"] == "this_process"
    assert (
        build_observability_manifest()["metrics"]["withheld_count_scope"]
        == "this_process"
    )
