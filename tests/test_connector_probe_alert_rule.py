"""The third alert rule: connector probe failure, and why it reports zero.

Until this change it did not exist. ``src/sdp_core/production.py``'s
``request_observability_export`` acceptance criterion ended: "A
connector-probe-failure rule is named by this criterion and has never been
published at all", and ``GET /enterprise/observability`` published two rules -
``policy_audit_gap`` (evaluated in process) and ``central_workflow_backlog``
(declared, not evaluated) - and no third. This file pins the condition that rule
evaluates, and above all pins that it reports **zero** on a correct deployment.

The defect this file is written against is not "the rule is missing". It is the
rule that gets written next. The obvious condition - "count probes that did not
reach ``status: ready_for_demo``" - fires on the shipped demo image. Measured,
every (connector, dataset) pair in the seed catalogue, 4 connectors x 5
datasets::

    20 pairs total
    15  raise ValueError  "dataset is not backed by the demo <X> connector"
     4  return status=ready_for_demo   adapter_status=implemented
     1  return status=contract_only    adapter_status=implemented
         (rest_connector, marketing-campaign)

The one ``contract_only`` pair is not broken. Its ``credential_vault`` control
row reports::

    control          credential_vault
    status           implemented
    verification     proof_route_served
    secret_ref       SDP_CONNECTOR_SECRET_REST_CONNECTOR_MARKETING_CAMPAIGN_TOKEN
    secret_present   False
    gap_reason       the configured secret reference is not present in this deployment

``SDP_CONNECTOR_SECRET_*`` is optional - it is in no ``required_environment``
list - and setting that one name flips the pair to ``ready_for_demo`` (measured,
same process: ``status: ready_for_demo``, verification counts
``{runtime_probe_verified: 1, proof_route_served: 2, declared_only: 0}``).
``sdp/demo_smoke.py``'s ``ready`` gate asserts ``rest_probe["adapter_status"] ==
"implemented"`` and deliberately **not** ``status == "ready_for_demo"``, and
reports ``ready: True`` with the pair in that state. So a rule counting "did not
reach ready_for_demo" publishes ``firing: true`` on a correct deployment, and
this repo calls that a defect in its own words -
``tests/test_request_evidence_correlation.py``'s ``policy_audit_gap`` section:
"the count is 0 today and the rule is a regression detector rather than a
standing complaint".

The other 15 pairs are a caller mistake, not a deployment failure: the caller
named a connector whose scheme does not back the dataset. ``connector_id``
reaches ``connector_probe`` from a path segment
(``GET /enterprise/connectors/{connector_id}/probe``) and
``tests/test_api.py::test_enterprise_connector_probe_fails_closed`` drives an
arbitrary caller-supplied id (``admin_shell``) into it. Counting those lets any
authorized caller raise the operator's pager by typing a wrong pair.

What is left is the honest condition: the probe's own ``verdict_basis`` failing
for a reason the **build** owns -

    "adapter_implemented + every required control's declared proof endpoint is
     served by this build + any runtime-verified control passed"

- an adapter the connector registry declares that this build does not implement,
or a required control whose declared proof endpoint this build does not serve.
Neither is caller-controlled and neither is configuration. Measured, both are
zero across all 20 pairs: ``adapter_status`` is ``implemented`` for all four
connectors and ``declared_only`` is 0 in every pair's
``control_verification_counts``, so no control row is missing a served proof
endpoint.

**Why no test here measures alert delivery.** Measured, a fire-and-forget
``asyncio.create_task`` POST raises ``CancelledError`` under ``TestClient`` and
completes only under a real uvicorn server; every test in this repo uses
``TestClient``. Delivery is therefore pinned by
``tests/test_alert_routing_firing_discipline.py``, which measures it through the
module's own ``alert_urlopen`` seam, and this family tests the *evaluation* half
only. The
counter is read back in process through a report function, never asserted
through an outbound request, so no test here can pass vacuously because a POST
was cancelled. ``test_the_route_and_a_direct_call_both_count`` is the one test
that touches HTTP, and it reads the in-process counter afterwards rather than
observing a delivery - which also pins that the chokepoint is synchronous and
usable with no event loop running at all (every other test in this file calls
``connector_probe`` directly, outside any loop).
"""

from __future__ import annotations

from pathlib import Path
import sys

from fastapi.testclient import TestClient
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sdp import connectors as conn  # noqa: E402
from sdp import observability as obs  # noqa: E402
from sdp.api import app  # noqa: E402
from sdp.credentials import connector_secret_ref  # noqa: E402
from sdp_core import connector_registry_manifest  # noqa: E402
from sdp import catalog  # noqa: E402


client = TestClient(app)

# The rule id this file pins, as it must appear in the published ``alerts`` list.
RULE_ID = "connector_probe_failure"


def _every_pair() -> list[tuple[str, str]]:
    """Every (connector_id, dataset_id) pair the seed catalogue allows.

    Derived from the registry and the catalogue rather than written out, so a
    new seed dataset or connector widens the enumeration instead of silently
    leaving a pair unmeasured.
    """
    return [
        (connector.id, dataset_id)
        for connector in connector_registry_manifest()
        for dataset_id in sorted(catalog._DATA)
    ]


def _probe_outcomes() -> dict[str, list[tuple[str, str]]]:
    """Classify every pair into the four outcomes measured on seed data.

    Keys are ``ready_for_demo``, ``contract_only``, ``scheme_mismatch`` and
    ``other_refusal``; values are the pairs that produced them.
    """
    outcomes: dict[str, list[tuple[str, str]]] = {
        "ready_for_demo": [],
        "contract_only": [],
        "scheme_mismatch": [],
        "other_refusal": [],
    }
    for connector_id, dataset_id in _every_pair():
        try:
            probe = conn.connector_probe(connector_id, dataset_id)
        except ValueError as exc:
            key = "scheme_mismatch" if "is not backed by" in str(exc) else "other_refusal"
            outcomes[key].append((connector_id, dataset_id))
        except KeyError:
            outcomes["other_refusal"].append((connector_id, dataset_id))
        else:
            outcomes[probe["status"]].append((connector_id, dataset_id))
    return outcomes


def _published_rule() -> dict:
    """The ``connector_probe_failure`` entry of the published ``alerts`` list.

    Read through the route, because the manifest is what a buyer reads. Fails
    the calling test with the ids that *are* published when the rule is absent,
    rather than raising ``StopIteration`` from a generator expression.
    """
    alerts = client.get("/enterprise/observability").json()["alerts"]
    matching = [entry for entry in alerts if entry.get("id") == RULE_ID]
    assert matching, f"no {RULE_ID} rule is published; ids = {[r.get('id') for r in alerts]}"
    return matching[0]


@pytest.fixture
def broken_proof_endpoint(monkeypatch):
    """Make this build stop serving a declared proof endpoint, for one test.

    ``audit_event`` is required by all four registry connectors and its declared
    proof endpoint is ``/audit/events``. Pointing it at a path the app does not
    serve reproduces the build defect the rule is for - a route renamed or
    dropped while the control still claims it - without editing the route table.
    Measured effect on a probe: ``control_evidence`` gains ``gap_reason`` "this
    build does not serve every declared proof endpoint: /audit/events-renamed"
    and the row's ``verification`` becomes ``declared_only``.
    """
    monkeypatch.setitem(conn._IMPLEMENTED_PROOF, "audit_event", ["/audit/events-renamed"])
    return "/audit/events-renamed"


# ---------------------------------------------------------------------------- #
# 1. The condition that is honest.
# ---------------------------------------------------------------------------- #


def test_no_seed_probe_outcome_is_a_pageable_failure() -> None:
    """The taxonomy, and the condition predicate applied to all of it.

    The enumeration is asserted here rather than in a test of its own: on its
    own it only measures the seed data and would pass against today's code,
    pinning nothing. Together with the predicate it is the justification -
    exact counts from running all 20 pairs in one process::

        20 pairs   4 ready_for_demo   1 contract_only   15 scheme_mismatch   0 other

    ``connector_probe_failure_reason`` is the rule's condition as a function of
    one probe result: "" when the outcome is not something an operator should be
    paged about, otherwise the reason. Every pair that returns on seed data -
    the 4 ``ready_for_demo`` and the 1 ``contract_only`` - must produce "".
    """
    outcomes = _probe_outcomes()
    assert len(_every_pair()) == 20
    assert len(outcomes["ready_for_demo"]) == 4
    assert outcomes["contract_only"] == [("rest_connector", "marketing-campaign")]
    assert len(outcomes["scheme_mismatch"]) == 15
    assert outcomes["other_refusal"] == []

    reasons = {}
    for connector_id, dataset_id in _every_pair():
        try:
            probe = conn.connector_probe(connector_id, dataset_id)
        except (ValueError, KeyError):
            continue
        reasons[(connector_id, dataset_id)] = conn.connector_probe_failure_reason(probe)
    assert len(reasons) == 5, reasons
    assert set(reasons.values()) == {""}, reasons


def test_the_declared_configuration_gap_is_not_a_probe_failure() -> None:
    """The crux: the one ``contract_only`` pair must not fire the rule.

    ``rest_connector``/``marketing-campaign`` probes ``contract_only`` because
    the optional ``SDP_CONNECTOR_SECRET_REST_CONNECTOR_MARKETING_CAMPAIGN_TOKEN``
    is unset - ``credential_vault`` fails closed and says so in ``gap_reason``.
    ``demo_smoke`` asserts that state and still reports ``ready: True``, so a
    rule that counts it fires on the shipped demo image. Asserted on the probe
    whose control row carries the gap, so this cannot pass because the pair
    stopped being ``contract_only``.
    """
    probe = conn.connector_probe("rest_connector", "marketing-campaign")
    vault = [row for row in probe["control_evidence"] if row["control"] == "credential_vault"]
    assert probe["status"] == "contract_only"
    assert vault[0]["secret_present"] is False
    assert vault[0]["secret_ref"] == connector_secret_ref("rest_connector", "marketing-campaign")

    assert conn.connector_probe_failure_reason(probe) == ""
    report = obs.connector_probe_failure_report()
    assert report["observed_total"] == 0, report
    assert report["firing"] is False


def test_a_scheme_mismatch_is_a_caller_mistake_and_is_not_counted() -> None:
    """15 of 20 pairs raise for a scheme mismatch; none of them may count.

    The connector id is a caller-supplied path segment and
    ``tests/test_api.py::test_enterprise_connector_probe_fails_closed`` drives an
    arbitrary one (``admin_shell``) into this function, so an operator's pager
    must not be reachable by naming a wrong pair. Unsupported connector id and
    unknown dataset id are driven here too: both are refusals the caller caused.
    """
    for connector_id, dataset_id in _probe_outcomes()["scheme_mismatch"]:
        with pytest.raises(ValueError, match="is not backed by"):
            conn.connector_probe(connector_id, dataset_id)
    with pytest.raises(ValueError, match="unsupported connector id"):
        conn.connector_probe("admin_shell", "crm-event")
    with pytest.raises(KeyError):
        conn.connector_probe("sql_connector", "no-such-dataset")

    report = obs.connector_probe_failure_report()
    assert report["observed_total"] == 0, report
    assert report["firing"] is False


# ---------------------------------------------------------------------------- #
# 2. The baseline, and the condition being reachable at all.
# ---------------------------------------------------------------------------- #


def test_the_condition_is_zero_after_probing_every_connector() -> None:
    """The baseline the rule is published against: 0 on seed data.

    Probes every connector at the dataset ``demo_smoke`` uses for it - the four
    pairs the ready gate exercises - and asserts the published rule reports
    nothing. A rule firing here would be the standing complaint this repo treats
    as a defect.
    """
    for connector_id, dataset_id in (
        ("sql_connector", "crm-customer-master"),
        ("rdf_connector", "semantic-glossary"),
        ("file_lake_connector", "crm-event"),
        ("rest_connector", "marketing-campaign"),
    ):
        conn.connector_probe(connector_id, dataset_id)

    report = obs.connector_probe_failure_report()
    assert report["observed_total"] == 0, report
    assert report["firing"] is False
    assert report["connectors"] == {}


def test_a_build_that_lost_a_declared_proof_endpoint_is_counted(broken_proof_endpoint) -> None:
    """The condition must be reachable, or zero at baseline proves nothing.

    With ``audit_event``'s declared proof endpoint pointed at a path this build
    does not serve, the control row loses its proof and the probe's verdict basis
    fails for a reason the build owns. This is the direction that makes the rule
    a regression detector rather than a constant.
    """
    probe = conn.connector_probe("sql_connector", "crm-customer-master")
    assert any(
        broken_proof_endpoint in row.get("gap_reason", "")
        for row in probe["control_evidence"]
    ), probe["control_evidence"]

    assert conn.connector_probe_failure_reason(probe) != ""
    report = obs.connector_probe_failure_report()
    assert report["observed_total"] == 1, report
    assert report["firing"] is True
    assert report["connectors"] == {"sql_connector": 1}


def test_an_adapter_the_registry_declares_but_this_build_lacks_is_counted(monkeypatch) -> None:
    """The second build-owned reason: a declared connector with no adapter.

    ``connector_probe`` reports ``adapter_status: planned`` when
    ``_SOURCE_CONNECTORS`` has no entry for a connector the registry manifest
    declares. Measured on seed data this is unreachable - all four registry ids
    have adapters - so it is driven here by removing one.
    """
    monkeypatch.delitem(conn._SOURCE_CONNECTORS, "sql_connector")
    probe = conn.connector_probe("sql_connector", "crm-customer-master")
    assert probe["adapter_status"] == "planned"
    assert probe["status"] == "contract_only"

    assert conn.connector_probe_failure_reason(probe) != ""
    report = obs.connector_probe_failure_report()
    assert report["observed_total"] == 1, report
    assert report["connectors"] == {"sql_connector": 1}


def test_the_counter_is_keyed_by_connector_id_not_dataset_id(broken_proof_endpoint) -> None:
    """Bounded by the registry, not by caller-supplied ids.

    ``connector_registry_manifest()`` declares 4 connectors, so a map keyed by
    connector id cannot exceed 4 entries. Dataset ids are caller-controlled and
    unbounded - a caller that can register datasets could grow the published
    manifest without limit. Driven with two datasets on one connector: one key,
    count 2.
    """
    conn.connector_probe("sql_connector", "crm-customer-master")
    conn.connector_probe("sql_connector", "sales-order")

    report = obs.connector_probe_failure_report()
    assert report["observed_total"] == 2, report
    assert report["connectors"] == {"sql_connector": 2}
    assert len(report["connectors"]) <= len(connector_registry_manifest())


# ---------------------------------------------------------------------------- #
# 3. What the rule publishes, and what it refuses to claim.
# ---------------------------------------------------------------------------- #


def test_the_rule_publishes_its_declared_condition_and_what_it_does_not_cover() -> None:
    """Published the way ``policy_audit_gap`` is, not as a bare id and severity.

    ``policy_audit_gap`` publishes ``condition``, ``declared_condition``,
    ``not_covered``, ``severity``, ``evaluated``, ``evaluation`` and its report
    fields. The third rule must carry the same shape, because the gap between
    the condition as named by the acceptance criterion ("connector probe
    failure") and the condition actually computed (a build-owned verdict-basis
    failure) is exactly the gap a diligence reader would otherwise assume away.
    """
    rule = _published_rule()
    required_fields = {
        "condition",
        "declared_condition",
        "not_covered",
        "severity",
        "evaluated",
        "evaluation",
    }
    assert required_fields - set(rule) == set(), sorted(required_fields - set(rule))
    assert rule["evaluated"] is True
    assert rule["evaluation"] == "measured_in_process"
    assert rule["observed_total"] == 0
    assert rule["firing"] is False
    # Not softened: the condition is zero at baseline and only a build defect
    # moves it, so there is nothing to down-rank it for.
    assert rule["severity"] == "critical"


def test_the_rule_names_the_two_outcomes_it_deliberately_ignores() -> None:
    """``not_covered`` must name the config gap and the caller mistake by name.

    Both are outcomes a reader would expect "connector probe failure" to include:
    the 1 ``contract_only`` pair on the demo image and the 15 scheme-mismatch
    pairs. A rule that silently excludes them reads as broader coverage than it
    has.
    """
    not_covered = _published_rule()["not_covered"]
    assert "credential_vault" in not_covered
    assert "SDP_CONNECTOR_SECRET" in not_covered
    assert "contract_only" in not_covered
    assert "caller" in not_covered


def test_the_absence_of_firing_is_not_a_claim_that_the_controls_passed() -> None:
    """19 of 20 control rows rest on a served route, so 0 is not "all controls pass".

    Measured across the 5 pairs that return on seed data: 20 control-evidence
    rows in total, of which exactly 1 is ``runtime_probe_verified``
    (``rdf_connector``'s ``ontology_version_pin``) and 19 are
    ``proof_route_served`` - "this build serves the declared proof endpoint",
    which is a fact about the route table and not about the control's effect. The
    rule's own text must say so, and must publish the mix rather than leave it to
    be inferred from a zero.
    """
    rows = runtime = 0
    for connector_id, dataset_id in _every_pair():
        try:
            probe = conn.connector_probe(connector_id, dataset_id)
        except (ValueError, KeyError):
            continue
        rows += len(probe["control_evidence"])
        runtime += probe["control_verification_counts"]["runtime_probe_verified"]
    assert (rows, runtime) == (20, 1)

    rule = _published_rule()
    assert "proof_route_served" in rule["not_covered"]
    assert rule["control_verification_counts_observed"] == {
        "runtime_probe_verified": 1,
        "proof_route_served": 19,
        "declared_only": 0,
    }


# ---------------------------------------------------------------------------- #
# 4. The one chokepoint every probe flows through.
# ---------------------------------------------------------------------------- #


def test_the_route_and_a_direct_call_both_count(broken_proof_endpoint) -> None:
    """Counting belongs in ``connector_probe``, not in the route or middleware.

    ``sdp/demo_smoke.py`` calls ``connector_probe`` directly four times and
    20-odd tests call it directly too, so a counter hooked at the route would
    miss every one of them; a counter in the middleware would miss them and
    also count nothing for a probe that raised. Both paths are driven here
    against the same broken build and each must add one.

    This is also the only test in this file that goes through HTTP, deliberately:
    it reads the in-process counter afterwards instead of observing a delivery,
    so the ``asyncio.create_task``/``CancelledError`` hazard under ``TestClient``
    cannot make it vacuous. Together with the direct call - made with no event
    loop running - it pins that the chokepoint is synchronous.
    """
    conn.connector_probe("sql_connector", "crm-customer-master")
    assert obs.connector_probe_failure_report()["observed_total"] == 1

    response = client.get(
        "/enterprise/connectors/sql_connector/probe",
        params={"dataset_id": "crm-customer-master", "user": "admin"},
    )
    assert response.status_code == 200
    assert obs.connector_probe_failure_report()["observed_total"] == 2


def test_the_read_path_never_evaluates_the_condition() -> None:
    """Building the manifest must not probe, so an anonymous GET cannot fire it.

    ``GET /enterprise/observability`` and ``GET /metrics`` are both
    unauthenticated. If the rule were evaluated from the read path, any
    anonymous GET would run four connector probes and - once routing exists -
    make an outbound POST to the operator's webhook. The rule reports what probes
    already observed; it does not go and measure.
    """
    before = obs.connector_probe_failure_report()["observed_total"]
    assert client.get("/enterprise/observability").status_code == 200
    assert client.get("/metrics").status_code == 200
    assert obs.connector_probe_failure_report()["observed_total"] == before


def test_the_counter_is_restored_between_tests() -> None:
    """New module-level mutable state must be in the autouse restore fixture.

    Every test above probes, and several deliberately drive the condition. The
    counter is published by ``GET /enterprise/observability`` and ``/metrics``,
    so one test's deliberate failure must not be another's reading. The restore
    line must sit **after** ``reset_request_observability()`` in
    ``tests/conftest.py``, which clears it, and the name must be declared in
    ``RESTORED_BY_FIXTURE`` in ``tests/test_module_state_coverage.py``.
    """
    assert obs.connector_probe_failure_report()["observed_total"] == 0
    assert obs._CONNECTOR_PROBE_FAILURES == {}
    assert obs._CONNECTOR_PROBE_VERIFICATIONS == {}
