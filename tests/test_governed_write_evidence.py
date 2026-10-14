"""Every governed write records both halves of the evidence, and no route is an oracle.

Two defect classes, each checked by enumeration rather than by the one case that
was reported.

**Missing audit half.** The graph and ontology mutation routes evaluated policy
and recorded the decision, but no audit event - on denial *or* success::

    POST /ontology/concepts  -> 200  decisions +1  audits +0
    POST /ontology/patches   -> 200  decisions +1  audits +0
    POST /graph/edges        -> 200  decisions +1  audits +0
    POST /catalog/.../publish-> 200  decisions +1  audits +1   (correct, for contrast)

So a concept or edge overwrite was unattributable in the ledger an auditor reads,
while the structurally identical catalog mutation wrote both halves.

**Dataset named in the body.** ``POST /browse/query`` answered 403 ``tenant
boundary denied`` for a dataset in another tenant and 400 ``dataset_not_found``
for one that does not exist, so the error still told an outsider which ids exist.
The earlier repair of this oracle enumerated ``/browse/{id}/...`` and
``/catalog/datasets/{id}/...`` **by URL shape**, which is exactly why it did not
reach this route: the dataset arrives in the request body. Enumerating by URL
shape is not enumerating the routes that resolve a dataset.

**Pre-policy audit rows.** Rows written by the input-validation branches had a
null ``decision_id``, which reads as "policy was skipped". They now carry
``policy_stage``, so a reader can tell "policy not reached" from "policy not
applied".
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from sdp import catalog, evidence
from sdp.api import app


client = TestClient(app, raise_server_exceptions=False)

# (label, path, an authorized body, an unauthorized body)
GOVERNED_WRITES = (
    (
        "ontology.concept_upsert",
        "/ontology/concepts",
        {"actor": "admin", "concept": "증거검증개념", "definition": "d"},
        {"actor": "nobody", "concept": "증거검증개념", "definition": "d"},
    ),
    (
        "ontology.patch_propose",
        "/ontology/patches",
        {"actor": "analyst", "concept": "고객", "suggestion": "evidence check"},
        {"actor": "nobody", "concept": "고객", "suggestion": "evidence check"},
    ),
    (
        "graph.edge_upsert",
        "/graph/edges",
        {"actor": "admin", "source_id": "ev-a", "target_id": "ev-b", "edge_type": "rel"},
        {"actor": "nobody", "source_id": "ev-a", "target_id": "ev-b", "edge_type": "rel"},
    ),
)


@pytest.mark.parametrize(
    "event_type,path,authorized,denied", GOVERNED_WRITES, ids=[row[0] for row in GOVERNED_WRITES]
)
def test_a_governed_write_records_a_decision_and_an_audit_event(
    event_type: str, path: str, authorized: dict, denied: dict
) -> None:
    """Both halves, on both outcomes."""
    for label, body, expected_result in (
        ("allowed", authorized, "allowed"),
        ("denied", denied, "denied"),
    ):
        before_decisions = len(evidence._POLICY_DECISION_LOG)
        before_audit = len(catalog._AUDIT_LOG)
        client.post(path, json=body)
        decisions = evidence._POLICY_DECISION_LOG[before_decisions:]
        audited = catalog._AUDIT_LOG[before_audit:]

        assert decisions, f"{path} ({label}) recorded no policy decision"
        assert audited, f"{path} ({label}) recorded a decision but no audit event"
        assert any(event.action == event_type for event in audited), (
            f"{path} ({label}) audited under {[e.action for e in audited]}, not {event_type}"
        )
        matching = next(event for event in audited if event.action == event_type)
        assert matching.result == expected_result
        assert matching.decision_id, "the audit row must point at a real decision"


def test_the_browse_query_route_is_not_an_existence_oracle() -> None:
    """The route whose dataset is in the body, not the path."""
    base = catalog._DATA["crm-customer-master"]
    catalog._DATA["body-named-foreign"] = base.model_copy(
        update={"id": "body-named-foreign", "tenant_id": "unreachable-tenant"}
    )

    def query(dataset_id: str):
        return client.post(
            "/browse/query",
            json={
                "user": "analyst",
                "dataset_ids": [dataset_id],
                "language": "SQL",
                "query": "select customer_id from customer",
                "purpose": "analysis",
            },
        )

    foreign = query("body-named-foreign")
    missing = query("definitely-not-a-dataset")
    assert (foreign.status_code, foreign.text) == (missing.status_code, missing.text), (
        f"foreign -> {foreign.status_code} {foreign.text} | "
        f"missing -> {missing.status_code} {missing.text}"
    )
    assert "tenant" not in foreign.text


def test_the_body_named_refusal_is_still_recorded_with_its_real_reason() -> None:
    base = catalog._DATA["crm-customer-master"]
    catalog._DATA["body-named-foreign"] = base.model_copy(
        update={"id": "body-named-foreign", "tenant_id": "unreachable-tenant"}
    )
    before = len(catalog._AUDIT_LOG)
    client.post(
        "/browse/query",
        json={
            "user": "analyst",
            "dataset_ids": ["body-named-foreign"],
            "language": "SQL",
            "query": "select customer_id from customer",
            "purpose": "analysis",
        },
    )
    audited = catalog._AUDIT_LOG[before:]
    assert [event.reason for event in audited] == ["tenant boundary denied"]
    assert audited[0].details["policy_stage"] == "evaluated"


def test_a_pre_policy_refusal_says_so_instead_of_leaving_a_null_decision() -> None:
    """A null decision_id must not be the only signal."""
    before = len(catalog._AUDIT_LOG)
    refused = client.post(
        "/browse/query",
        json={
            "user": "analyst",
            "dataset_ids": ["crm-customer-master"],
            "language": "python",
            "query": "select 1",
            "purpose": "analysis",
        },
    )
    assert refused.status_code == 400
    audited = catalog._AUDIT_LOG[before:]
    assert len(audited) == 1
    assert audited[0].details["policy_stage"] == "pre_policy_validation"
    assert not audited[0].decision_id

    before = len(catalog._AUDIT_LOG)
    allowed = client.post(
        "/browse/query",
        json={
            "user": "analyst",
            "dataset_ids": ["crm-customer-master"],
            "language": "SQL",
            "query": "select customer_id from customer",
            "purpose": "analysis",
        },
    )
    assert allowed.status_code == 200
    audited = catalog._AUDIT_LOG[before:]
    assert audited[0].details["policy_stage"] == "evaluated"
    assert audited[0].decision_id


def test_every_published_proof_link_resolves_as_published() -> None:
    """A diligence link that 404s or 403s reads as a missing capability.

    ``/enterprise/evidence-pack`` published thirteen ``proof_endpoints`` with no
    distinction between open reads and governed ones. Measured before the repair,
    fetching each exactly as printed:

        403  /enterprise/connectors/sql_connector/probe?dataset_id=crm-customer-master
        403  /policy/decisions
        403  /audit/events

    Those refusals are the access control working - but a reader following the
    published list sees three dead links and cannot tell a refusal from an absent
    capability. The list is split so each link resolves when used as documented.
    """
    pack = client.get("/enterprise/evidence-pack").json()

    assert pack["proof_endpoints"] == (
        pack["open_proof_endpoints"] + pack["actor_scoped_proof_endpoints"]
    ), "the combined list must stay the union of the two, with nothing dropped"
    assert pack["actor_scoped_proof_note"]

    open_failures = [
        (endpoint, client.get(endpoint).status_code)
        for endpoint in pack["open_proof_endpoints"]
        if client.get(endpoint).status_code >= 400
    ]
    assert not open_failures, f"open proof links failed as published: {open_failures}"

    scoped_failures = []
    for endpoint in pack["actor_scoped_proof_endpoints"]:
        assert "<actor>" in endpoint, (
            f"an actor-scoped link must name the parameter: {endpoint}"
        )
        resolved = endpoint.replace("<actor>", "admin")
        status = client.get(resolved).status_code
        if status >= 400:
            scoped_failures.append((resolved, status))
    assert not scoped_failures, (
        f"actor-scoped proof links failed with an actor supplied: {scoped_failures}"
    )


def test_an_actor_scoped_proof_link_still_refuses_without_an_actor() -> None:
    """The split documents the gate; it must not have removed it."""
    pack = client.get("/enterprise/evidence-pack").json()
    for endpoint in pack["actor_scoped_proof_endpoints"]:
        without_actor = endpoint.replace("&user=<actor>", "").replace("?user=<actor>", "")
        status = client.get(without_actor).status_code
        # The status differs by route and that is deliberate: the connector probe
        # names a dataset in a query parameter, so an actor-less caller gets the
        # same 404 a foreign or absent dataset gets, while the two ledger reads
        # have no dataset to scope and answer 403. What this test guards is that
        # every one of them still refuses.
        assert status in (403, 404), (
            f"{without_actor} should still refuse an actor-less read, got {status}"
        )
