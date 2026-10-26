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

from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from sdp import api, evidence, observability as obs
from sdp.api import app
from sdp.api_error_contract import policy_gated_route_paths


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
    monkeypatch.setattr(api, "_POLICY_GATED_ROUTES", frozenset({"/health"}))
    assert client.get("/health").status_code == 200
    report = obs.governed_evidence_gap_report()
    assert report["observed_total"] == 1, report
    assert report["firing"] is True
    assert report["routes"] == {"/health": 1}
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


def test_a_refusal_is_not_counted_as_a_gap() -> None:
    """Only a 2xx can be a gap: a refusal recorded its decision and said no."""
    response = client.post(
        "/browse/crm-customer-master/preview",
        headers={"X-SDP-Actor": "nobody@example.com", "X-SDP-Tenant": "demo"},
        json={"user": "nobody", "purpose": "analysis", "limit": 1},
    )
    assert response.status_code == 404
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
    gated = policy_gated_route_paths()
    assert "/browse/{dataset_id}/preview" in gated
    assert "/health" not in gated
    templates = {route.path for route in app.routes if isinstance(route, APIRoute)}
    assert gated <= templates, f"declared governed routes the app does not serve: {gated - templates}"
