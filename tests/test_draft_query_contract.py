"""``POST /llm/draft-query`` answered 200 for every failure, and audited nothing.

Three defects in one route:

* **Status.** Authorization denial, an unknown dataset, and malformed input all
  came back as HTTP 200 with the cause buried in an ``error`` key, so a client
  checking ``response.ok`` read a denial as success::

      authz denied -> 200 error=policy_denied
      unknown ds   -> 200 error=dataset_not_found
      bad window   -> 200 error=invalid_date_window

* **Existence oracle.** ``dataset_not_found`` for a dataset that does not exist
  and ``policy_denied`` for one in another tenant let an outside caller read
  which ids exist out of the error code.

* **No evidence.** The route recorded a policy decision and no audit event, on
  denial *or* success. Measured: ``decisions +1  audits +0``. The repository's
  stated invariant is that these paths evaluate policy *and* record evidence.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from sdp import catalog, evidence
from sdp.api import app


client = TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _planted_datasets() -> None:
    base = catalog._DATA["crm-customer-master"]
    catalog._DATA["draft-foreign-ds"] = base.model_copy(
        update={"id": "draft-foreign-ds", "tenant_id": "unreachable-tenant"}
    )
    catalog._DATA["draft-unpublished-ds"] = base.model_copy(
        update={"id": "draft-unpublished-ds", "status": "draft"}
    )


def _draft(**overrides) -> object:
    body = {
        "user": "analyst",
        "dataset_id": "crm-customer-master",
        "question": "월별 추이를 보여줘",
        "purpose": "analysis",
    }
    body.update(overrides)
    return client.post("/llm/draft-query", json=body)


def test_each_failure_carries_the_status_an_integrator_can_act_on() -> None:
    assert _draft().status_code == 200
    assert _draft(dataset_id="definitely-not-a-dataset").status_code == 404
    assert _draft(dataset_id="draft-unpublished-ds").status_code == 403
    assert _draft(date_window_days=9999).status_code == 400
    assert _draft(group_by="not-a-column").status_code == 400
    assert _draft(user="nobody").status_code == 404


def test_a_foreign_dataset_is_indistinguishable_from_a_missing_one() -> None:
    """The error code was the oracle, so the codes must match too."""
    foreign = _draft(dataset_id="draft-foreign-ds")
    missing = _draft(dataset_id="definitely-not-a-dataset")
    assert (foreign.status_code, foreign.text) == (missing.status_code, missing.text), (
        f"foreign -> {foreign.status_code} {foreign.text} | "
        f"missing -> {missing.status_code} {missing.text}"
    )
    assert foreign.status_code == 404
    assert "tenant" not in foreign.text


def test_the_refusal_is_recorded_even_though_the_client_is_told_nothing() -> None:
    """The reason moved from the response to the ledger, not out of existence."""
    before_decisions = len(evidence._POLICY_DECISION_LOG)
    before_audit = len(catalog._AUDIT_LOG)
    assert _draft(dataset_id="draft-foreign-ds").status_code == 404

    decisions = evidence._POLICY_DECISION_LOG[before_decisions:]
    assert [decision.effect for decision in decisions] == ["deny"]
    assert decisions[0].reason == "tenant boundary denied"

    audited = catalog._AUDIT_LOG[before_audit:]
    assert [event.action for event in audited] == ["llm.draft_query"]
    assert audited[0].result == "denied"
    assert audited[0].reason == "tenant boundary denied"
    assert audited[0].decision_id


def test_a_successful_draft_is_audited_too() -> None:
    """A governed SQL draft left no trace in the audit feed at all."""
    before = len(catalog._AUDIT_LOG)
    assert _draft(user="admin").status_code == 200
    audited = catalog._AUDIT_LOG[before:]
    assert [event.action for event in audited] == ["llm.draft_query"]
    assert audited[0].result == "allowed"
    assert audited[0].decision_id

    feed = client.get("/audit/events", params={"user": "admin", "limit": 20}).json()
    rows = feed if isinstance(feed, list) else feed.get("events", [])
    assert any(row["action"] == "llm.draft_query" for row in rows), (
        "the draft must be visible in the audit feed an auditor actually reads"
    )


def test_a_successful_draft_still_returns_the_whole_payload() -> None:
    """The status mapping must not change what a working call returns."""
    body = _draft(user="admin").json()
    assert body["query"].startswith("SELECT ")
    assert body["policy_decision_id"]
    assert body["dialect"] == "postgresql"
    assert "error" not in body
