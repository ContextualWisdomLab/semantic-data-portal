"""``POST /policy/decision`` answered more than the routes this series closed.

It was open, and with **no authentication at all** it answered both of the
questions four earlier commits spent their time hiding. Measured before the
repair::

    {"resource": "zeta-secret",     ...} -> 200  reason "tenant boundary denied"
                                                 obligations.tenant_id "zeta-bank"
    {"resource": "no-such-dataset", ...} -> 200  reason "존재하지 않는 데이터셋입니다."
                                                 obligations.tenant_id "unresolved"

So an unauthenticated caller could enumerate dataset ids, learn which exist from
the differing reason, **and read the owning tenant out of the obligations**.
Closing the catalog, browse, llm and graph families left this as an open side
channel exposing the same facts plus tenant ownership, because that sweep
enumerated routes that *resolve* a dataset and this one merely answers questions
*about* one.

It also wrote to the ledger: ``evaluate()`` records every decision, so 50
unauthenticated calls produced 50 rows in the evidence log an auditor reads,
while the sibling ``GET /policy/decisions`` already refused an actor-less *read*
with 403. You could not read the ledger without an actor but could write to it
without one.

The route is pre-existing - unchanged since the original MVP merge and identical
on ``main`` - so this is a hole the sweep left behind rather than one it opened.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from sdp import catalog, evidence
from sdp.api import NON_DATASET_POLICY_RESOURCES, app


client = TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _planted_foreign_dataset():
    """Plant the foreign dataset, and put everything this file touches back.

    The planted dataset and the ledger rows these probes write used to outlive
    the file (one test here deliberately fills the decision ledger to its cap),
    so every later test in the session saw them. Leaking shared state was one of
    the findings this self-review raised against this very file.
    """
    data = {key: value.model_copy(deep=True) for key, value in catalog._DATA.items()}
    audit = list(catalog._AUDIT_LOG)
    decisions = list(evidence._POLICY_DECISION_LOG)
    recorded_audit = list(evidence._AUDIT_EVENT_LOG)
    base = catalog._DATA["crm-customer-master"]
    catalog._DATA["policy-foreign-ds"] = base.model_copy(
        update={"id": "policy-foreign-ds", "tenant_id": "zeta-bank"}
    )
    try:
        yield
    finally:
        catalog._DATA.clear()
        catalog._DATA.update(data)
        catalog._AUDIT_LOG[:] = audit
        evidence._POLICY_DECISION_LOG[:] = decisions
        evidence._AUDIT_EVENT_LOG[:] = recorded_audit


def _ask(**body) -> object:
    payload = {"resource": "crm-customer-master", "action": "preview", "purpose": "analysis"}
    payload.update(body)
    return client.post("/policy/decision", json=payload)


def test_an_actor_less_caller_is_refused() -> None:
    refused = _ask(subject="nobody", resource="policy-foreign-ds")
    assert refused.status_code == 403, refused.text
    assert "zeta-bank" not in refused.text
    assert "tenant boundary" not in refused.text


def test_the_owning_tenant_is_never_disclosed() -> None:
    for actor in ("nobody", "analyst", "external-analyst"):
        response = _ask(user=actor, resource="policy-foreign-ds")
        assert "zeta-bank" not in response.text, f"{actor}: {response.text}"


def test_a_foreign_dataset_and_a_nonexistent_id_answer_alike() -> None:
    """The reason string was the oracle even once the tenant was hidden."""
    foreign = _ask(user="analyst", resource="policy-foreign-ds")
    missing = _ask(user="analyst", resource="definitely-not-a-dataset")
    assert (foreign.status_code, foreign.text) == (missing.status_code, missing.text), (
        f"foreign -> {foreign.status_code} {foreign.text} | "
        f"missing -> {missing.status_code} {missing.text}"
    )
    assert foreign.status_code == 404


def test_a_platform_admin_still_gets_a_real_answer() -> None:
    allowed = _ask(user="admin", resource="policy-foreign-ds")
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["resource"] == "policy-foreign-ds"


def test_the_route_still_answers_its_own_non_dataset_resources() -> None:
    """The scope check must not break the question the route exists to answer."""
    assert NON_DATASET_POLICY_RESOURCES == {"catalog", "evidence", "graph"}
    for resource in sorted(NON_DATASET_POLICY_RESOURCES):
        response = _ask(user="analyst", resource=resource, action="search")
        assert response.status_code == 200, f"{resource}: {response.text}"
        assert response.json()["resource"] == resource

    ontology_scoped = _ask(user="analyst", resource="ontology/patches", action="search")
    assert ontology_scoped.status_code == 200, ontology_scoped.text


def test_an_in_scope_question_still_gets_its_real_reason() -> None:
    """Only out-of-scope resources collapse; a genuine denial stays diagnosable."""
    base = catalog._DATA["crm-customer-master"]
    catalog._DATA["policy-critical-ds"] = base.model_copy(
        update={"id": "policy-critical-ds", "sensitivity": "critical"}
    )
    response = _ask(user="analyst", resource="policy-critical-ds")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["effect"] == "deny"
    assert "critical" in body["reason"]


def test_the_decision_ledger_is_bounded() -> None:
    """Every gated route evaluates policy before refusing, so an actor-less
    caller could grow this list one row per request without limit."""
    from sdp.policy import evaluate

    for _ in range(evidence.MAX_IN_MEMORY_POLICY_DECISIONS + 200):
        evaluate(subject="analyst", resource="catalog", action="search", purpose="analysis")
    assert len(evidence._POLICY_DECISION_LOG) <= evidence.MAX_IN_MEMORY_POLICY_DECISIONS
