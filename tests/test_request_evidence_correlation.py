"""A request log's ``evidence_ids`` must name the evidence the server recorded.

``GET /enterprise/observability`` publishes ``structured_logs.fields`` including
``evidence_ids``, and the readiness manifest's acceptance criterion for
``request_observability_export`` reads "Request logs include request id, tenant,
actor, route, status, latency, and evidence ids without request bodies" - with
that integration marked ``implemented`` and only ``SDP_ALERT_WEBHOOK_URL``
declared unimplemented. Measured before this change, the field was read from a
**caller-supplied request header**, ``X-SDP-Evidence-Ids``::

    POST /browse/crm-customer-master/preview
      headers: X-SDP-Evidence-Ids: 00000000-dead-beef-0000-000000000000,
                                   another-forged-id
      -> 200
         the decision the server actually recorded: 4ff4d6c7-52a3-...-cb585180a27d
         the exported log line's evidence_ids:       ['00000000-dead-beef-...',
                                                      'another-forged-id']
         does the log carry the real decision id?:   False

So the one field whose purpose is to tie a log line to the governance ledger was
controlled by the caller the line is about, and the id the server recorded never
appeared. An auditor correlating logs to ``/policy/decisions`` was reading
caller-asserted data; a caller could point its line at another request's
evidence, or send nothing and have the line say no evidence existed. Sending
nothing was the ordinary case: no route sets that header, so in practice every
governed request exported ``evidence_ids: []``.

This is the defect ``tenant_id`` already carries a comment about in
``tests/test_observability.py`` ("self-asserted by the very caller whose rows
would be filtered") - the difference is that ``tenant_id`` is declared as
caller-asserted and withheld from the unauthenticated manifest, while
``evidence_ids`` was published as the correlation key.

The ids now come from the two chokepoints every evidence row flows through,
``evidence.record_policy_decision`` and ``evidence.append_audit_event``,
collected per request. The header is no longer read.
"""

from __future__ import annotations

import json

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from sdp_core.contracts import PolicyDecision

from sdp import api, evidence, observability as obs
from sdp.api import app
from sdp.api_error_contract import policy_gated_route_methods


client = TestClient(app, raise_server_exceptions=False)

PREVIEW_HEADERS = {"X-SDP-Actor": "analyst@example.com", "X-SDP-Tenant": "demo"}
PREVIEW_BODY = {"user": "analyst", "purpose": "analysis", "limit": 1}
FORGED = "00000000-dead-beef-0000-000000000000"


def _last_observation(route: str) -> dict:
    """The newest buffered observation for ``route``."""
    for observation in reversed(obs.list_request_observations(limit=100)):
        if observation.get("route") == route:
            return observation
    raise AssertionError(f"no observation recorded for {route}")


def test_the_exported_log_carries_the_decision_the_server_recorded() -> None:
    """The correlation key, measured end to end on an authorized governed read."""
    response = client.post(
        "/browse/crm-customer-master/preview", headers=PREVIEW_HEADERS, json=PREVIEW_BODY
    )
    assert response.status_code == 200
    decision_id = response.json()["policy_decision_id"]
    observation = _last_observation("/browse/crm-customer-master/preview")
    assert decision_id in observation["evidence_ids"]


def test_a_caller_cannot_assert_its_own_evidence_ids() -> None:
    """The header is not a source; the recorded decision is."""
    response = client.post(
        "/browse/crm-customer-master/preview",
        headers={**PREVIEW_HEADERS, "X-SDP-Evidence-Ids": f"{FORGED}, another-forged-id"},
        json=PREVIEW_BODY,
    )
    assert response.status_code == 200
    observation = _last_observation("/browse/crm-customer-master/preview")
    assert FORGED not in observation["evidence_ids"]
    assert "another-forged-id" not in observation["evidence_ids"]
    assert response.json()["policy_decision_id"] in observation["evidence_ids"]


def test_a_refused_governed_request_still_carries_its_decision() -> None:
    """A denial is a decision, and the ledger row for it is what an auditor
    looking for refused attempts reads - so the log line must name it.

    The refusal here answers **404**, not 403: an out-of-scope caller gets the
    same status and body as a missing dataset on purpose, so the response is not
    an existence oracle (see the route's own comment). The real reason lives in
    the ledger the refused caller cannot read - which is exactly why the log line
    has to carry the id that finds it.
    """
    response = client.post(
        "/browse/crm-customer-master/preview",
        headers={"X-SDP-Actor": "nobody@example.com", "X-SDP-Tenant": "demo"},
        json={"user": "nobody", "purpose": "analysis", "limit": 1},
    )
    assert response.status_code == 404
    observation = _last_observation("/browse/crm-customer-master/preview")
    assert observation["status_code"] == 404
    assert observation["evidence_ids"], "a refused governed read recorded no correlatable evidence"


def test_a_request_that_records_no_evidence_exports_an_empty_list() -> None:
    """Honest emptiness: ``/health`` evaluates no policy and writes no audit row."""
    assert client.get("/health").status_code == 200
    assert _last_observation("/health")["evidence_ids"] == []


def test_one_request_does_not_carry_another_request_s_evidence() -> None:
    """The collector is per request, not per process."""
    first = client.post(
        "/browse/crm-customer-master/preview", headers=PREVIEW_HEADERS, json=PREVIEW_BODY
    )
    first_ids = set(_last_observation("/browse/crm-customer-master/preview")["evidence_ids"])
    second = client.post(
        "/browse/crm-customer-master/preview", headers=PREVIEW_HEADERS, json=PREVIEW_BODY
    )
    second_ids = set(_last_observation("/browse/crm-customer-master/preview")["evidence_ids"])
    assert first.status_code == second.status_code == 200
    assert first_ids and second_ids
    assert first_ids.isdisjoint(second_ids)
    assert first.json()["policy_decision_id"] not in second_ids


def test_the_exported_bytes_carry_it_too(tmp_path, monkeypatch) -> None:
    """The ring buffer is the local read; the sink is the buyer-visible artifact."""
    log_path = tmp_path / "requests.jsonl"
    monkeypatch.setenv("SDP_LOG_SINK_URL", f"file://{log_path}")
    response = client.post(
        "/browse/crm-customer-master/preview", headers=PREVIEW_HEADERS, json=PREVIEW_BODY
    )
    assert response.status_code == 200
    records = [json.loads(line) for line in log_path.read_text().splitlines() if line.strip()]
    assert len(records) == 1
    assert response.json()["policy_decision_id"] in records[0]["evidence_ids"]
    # The criterion's other half: no request body in the row.
    assert "analysis" not in json.dumps(records[0])


def test_the_collected_list_is_bounded_and_declares_what_it_withheld() -> None:
    """A route recording many rows must not grow the observation without bound,
    and the row must say how many ids it is not showing."""
    overflow = obs.MAX_OBSERVATION_EVIDENCE_IDS * 2
    with evidence.collect_request_evidence_ids() as collected:
        for index in range(overflow):
            evidence.note_request_evidence_id(f"decision-{index:04d}")
        observation = obs.build_request_observation(
            method="GET",
            route="/health",
            status_code=200,
            latency_ms=1.0,
            headers={},
            request_id="sdp-bound",
            evidence_ids=collected.ids,
            withheld_evidence_id_count=collected.withheld,
        )
    assert len(observation["evidence_ids"]) == obs.MAX_OBSERVATION_EVIDENCE_IDS
    assert observation["withheld_evidence_id_count"] == overflow - obs.MAX_OBSERVATION_EVIDENCE_IDS


def test_the_withheld_count_counts_distinct_ids_not_attempts() -> None:
    """The field is named for a count of ids, so it must count ids.

    ``withheld`` was an ``int`` incremented per call, and the dedupe that
    collapses a repeat only looks at the ids that fit - so one withheld id
    offered five times published 5. Not reachable over HTTP today (no route
    writes more than two ledger rows for one request), which is why this is a
    set rather than a redesign, and why the test says so.
    """
    with evidence.collect_request_evidence_ids() as collected:
        for index in range(evidence.MAX_REQUEST_EVIDENCE_IDS):
            evidence.note_request_evidence_id(f"kept-{index:04d}")
        for _ in range(5):
            evidence.note_request_evidence_id("overflowing-but-one-id")
        evidence.note_request_evidence_id("a-second-overflowing-id")
    assert len(collected.ids) == evidence.MAX_REQUEST_EVIDENCE_IDS
    assert collected.withheld == 2
    assert collected.withheld_ids == {"overflowing-but-one-id", "a-second-overflowing-id"}


def test_the_collector_records_each_id_once() -> None:
    """Two rows naming one decision id are one correlation key, not two."""
    with evidence.collect_request_evidence_ids() as collected:
        evidence.note_request_evidence_id("decision-1")
        evidence.note_request_evidence_id("decision-1")
        evidence.note_request_evidence_id("event-1")
        evidence.note_request_evidence_id("")
    assert collected.ids == ["decision-1", "event-1"]
    assert collected.withheld == 0


def test_noting_an_id_outside_a_request_is_a_no_op() -> None:
    """Startup seeding records evidence with no request in flight."""
    evidence.note_request_evidence_id("decision-outside-any-request")
    with evidence.collect_request_evidence_ids() as collected:
        pass
    assert collected.ids == []


# ---------------------------------------------------------------------------- #
# The ``policy_audit_gap`` alert, which this key made evaluable.
#
# ``GET /enterprise/observability`` published two alert rules with
# ``evaluated: false`` and ``alert_evaluation: declared_not_evaluated`` - honest,
# but the critical one is a self-check on the product's central claim: a
# governed path records a policy decision *and* an audit row. It could not be
# evaluated while ``evidence_ids`` came from a request header, because "did this
# request record evidence" had no answer the server owned.
#
# Measured across the 18 policy-gated GET routes that could be probed with seed
# data, every 2xx carries at least one evidence id, so the count is 0 today and
# the rule is a regression detector rather than a standing complaint.
# ---------------------------------------------------------------------------- #


def test_the_gap_condition_is_zero_on_ordinary_governed_traffic() -> None:
    """The measured state, asserted so a regression has somewhere to show up."""
    assert (
        client.post(
            "/browse/crm-customer-master/preview", headers=PREVIEW_HEADERS, json=PREVIEW_BODY
        ).status_code
        == 200
    )
    report = obs.governed_evidence_gap_report()
    assert report["observed_total"] == 0, report
    assert report["firing"] is False
    assert report["routes"] == {}


def test_a_governed_two_hundred_without_evidence_is_counted(monkeypatch) -> None:
    """The alert firing, driven through the real middleware.

    ``/health`` evaluates no policy and writes no audit row, so widening the
    governed surface to include it is the smallest honest way to produce the
    condition: a route the refusal contract would call governed answering 200
    with nothing to correlate.
    """
    monkeypatch.setattr(api, "_POLICY_GATED_ROUTES", frozenset({("GET", "/health")}))
    assert client.get("/health").status_code == 200
    report = obs.governed_evidence_gap_report()
    assert report["observed_total"] == 1, report
    assert report["firing"] is True
    assert report["routes"] == {"GET /health": 1}
    # And the manifest says it, rather than only the helper.
    gap = next(
        alert
        for alert in obs.build_observability_manifest()["alerts"]
        if alert["id"] == "policy_audit_gap"
    )
    assert gap["evaluated"] is True and gap["firing"] is True
    assert gap["observed_total"] == 1


def test_a_route_outside_the_governed_surface_is_not_counted() -> None:
    """``/health`` is not policy-gated, so its empty evidence list is not a gap."""
    assert client.get("/health").status_code == 200
    assert obs.governed_evidence_gap_report()["observed_total"] == 0


def test_a_refusal_that_recorded_nothing_is_still_not_counted_as_a_gap() -> None:
    """The status guard, exercised by the only refusal that needs it.

    This test used to drive a 404 - which records a policy decision, so
    ``not collected.ids`` was already false and the ``200 <= status_code < 300``
    clause never decided the outcome. Deleting that clause left the whole suite
    green (measured: 1241 passed), and the clause is load-bearing: a governed
    route that refuses *before* reaching ``policy.evaluate`` records nothing at
    all. A malformed body is exactly that - pydantic rejects it and the handler
    never runs - so without the guard an ordinary 400 would make the critical
    rule fire.
    """
    response = client.post(
        "/browse/crm-customer-master/preview",
        headers=PREVIEW_HEADERS,
        json={"user": "analyst", "purpose": "analysis", "limit": "not-an-int"},
    )
    assert response.status_code == 400
    observation = _last_observation("/browse/crm-customer-master/preview")
    assert observation["status_code"] == 400
    # The precondition that makes this test about the status guard: nothing was
    # recorded, so only the status can be the reason it is not counted.
    assert observation["evidence_ids"] == []
    report = obs.governed_evidence_gap_report()
    assert report["observed_total"] == 0, report
    assert report["firing"] is False


def test_a_refused_governed_request_that_did_record_evidence_is_not_counted() -> None:
    """The other refusal shape: it recorded its decision, so it is correlatable
    and is not a gap either."""
    response = client.post(
        "/browse/crm-customer-master/preview",
        headers={"X-SDP-Actor": "nobody@example.com", "X-SDP-Tenant": "demo"},
        json={"user": "nobody", "purpose": "analysis", "limit": 1},
    )
    assert response.status_code == 404
    assert _last_observation("/browse/crm-customer-master/preview")["evidence_ids"]
    assert obs.governed_evidence_gap_report()["observed_total"] == 0


def test_the_counted_routes_are_bounded_without_losing_the_total() -> None:
    """A caller that can reach many templates must not grow the manifest."""
    overflow = obs.MAX_TRACKED_EVIDENCE_GAP_ROUTES + 5
    for index in range(overflow):
        obs.note_governed_request_without_evidence(f"/route-{index:03d}")
    report = obs.governed_evidence_gap_report()
    assert len(report["routes"]) == obs.MAX_TRACKED_EVIDENCE_GAP_ROUTES + 1
    assert report["routes"][obs._OTHER_GAP_ROUTES] == 5
    assert report["observed_total"] == overflow


def test_the_governed_surface_is_derived_from_the_published_refusal_contract() -> None:
    """One source of truth, and no stale entries in it.

    The set is derived from the routes the refusal contract says can answer 403 -
    a route that can be refused is a route that asked ``policy.evaluate`` - so a
    new governed route joins the self-check by declaring its own 403 rather than
    by being added to a second list. The second assertion is the drift guard the
    derivation still needs: a path removed from the app but left in the contract
    would silently never be counted.
    """
    gated = policy_gated_route_methods()
    assert ("POST", "/browse/{dataset_id}/preview") in gated
    assert ("GET", "/health") not in gated
    # The method is part of the answer. ``POST /ontology/concepts`` is governed
    # and ``GET /ontology/concepts`` is deliberately open; a set of bare paths
    # cannot say that, and when it could not, one anonymous GET made the
    # critical rule fire (measured).
    assert ("POST", "/ontology/concepts") in gated
    assert ("GET", "/ontology/concepts") not in gated
    served = set()
    for route in app.routes:
        if isinstance(route, APIRoute):
            for method in route.methods:
                served.add((method, route.path))
    assert gated <= served, f"declared governed routes the app does not serve: {gated - served}"


def test_the_middleware_consumes_the_derived_surface_unchanged() -> None:
    """The wiring, which no test checked while it was wrong.

    ``test_a_governed_two_hundred_without_evidence_is_counted`` replaces
    ``api._POLICY_GATED_ROUTES`` to drive the counter, so it proves the counting
    mechanism and says nothing about the value the middleware really uses - and
    the value really used was method-blind. Every other gap test asserts zero,
    which a detector wired to nothing also satisfies. This is the assertion that
    fails if the two ever diverge again.
    """
    assert api._POLICY_GATED_ROUTES == policy_gated_route_methods()


def test_an_open_method_on_a_governed_path_is_not_counted() -> None:
    """The shipped defect, pinned.

    ``POST /ontology/concepts`` declares 403, so the *path* was governed and the
    membership test took ``GET /ontology/concepts`` with it: an actor-less,
    policy-free vocabulary read that records nothing. Measured against the first
    version, one anonymous GET published
    ``policy_audit_gap: {firing: true, observed_total: 1,
    routes: {'/ontology/concepts': 1}}`` on a rule whose severity is critical -
    while the CHANGELOG, production.py and both docs published "measured 0, a
    regression detector rather than a standing complaint".
    """
    response = client.get("/ontology/concepts")
    assert response.status_code == 200
    observation = _last_observation("/ontology/concepts")
    assert observation["evidence_ids"] == [], "this route is open; it records nothing"
    report = obs.governed_evidence_gap_report()
    assert report["observed_total"] == 0, report
    assert report["firing"] is False


def test_no_governed_get_route_reports_a_gap_on_seed_data() -> None:
    """The measurement that justified publishing "0", as a standing test.

    It was taken once, by hand, over the 403-capable GET templates - the
    method-aware view - while the middleware matched paths. The two disagreed and
    the hand measurement was the one that looked right, so the published "0"
    survived a rule that fires on the first anonymous request. Run as a test over
    the surface the middleware itself uses, that cannot happen twice.
    """
    substitutions = {
        "{dataset_id}": "crm-customer-master",
        "{term}": "고객",
        "{concept}": "고객",
    }
    probed = 0
    for method, template in sorted(api._POLICY_GATED_ROUTES):
        if method != "GET":
            continue
        url = template
        for token, value in substitutions.items():
            url = url.replace(token, value)
        if "{" in url:
            continue
        response = client.get(url, params={"user": "admin", "actor": "admin"})
        if not (200 <= response.status_code < 300):
            continue
        probed += 1
    report = obs.governed_evidence_gap_report()
    assert probed >= 15, f"only {probed} governed GET routes were probed"
    assert report["observed_total"] == 0, report
    assert report["routes"] == {}


def test_an_id_is_published_only_after_the_store_accepted_the_row() -> None:
    """The log row's correlation key must name a row that exists.

    ``note_request_evidence_id`` ran *before* the configured store's write, so a
    write that raises - the deployed Postgres/SQLite configuration can - still
    published the id in the request log while the ledger never got the row.
    ``GET /enterprise/observability`` publishes ``evidence_id_source:
    server_recorded`` beside it, and the readiness manifest's criterion says the
    ids name what the server recorded, so the row became the one thing an
    auditor cannot check: a key with nothing behind it.
    """

    class _RefusingStore:
        """An evidence store whose writes fail, like an outage."""

        def record_decision(self, decision) -> None:
            """Fail the way a store outage fails."""
            raise RuntimeError("evidence store unavailable")

        def append_event(self, event) -> None:
            """Fail the way a store outage fails."""
            raise RuntimeError("evidence store unavailable")

    previous = evidence._STORE
    evidence.configure_evidence_store(_RefusingStore())
    try:
        with evidence.collect_request_evidence_ids() as collected:
            with pytest.raises(RuntimeError):
                evidence.record_policy_decision(
                    PolicyDecision(
                        decision_id="never-persisted",
                        subject="analyst",
                        resource="x",
                        action="read",
                        purpose="analysis",
                        effect="allow",
                        reason="r",
                    )
                )
        assert collected.ids == [], collected.ids
    finally:
        evidence.configure_evidence_store(previous)
