"""An existence oracle is a property of the *question*, not of the URL shape.

The earlier sweeps enumerated routes that name a dataset in the **path**, then
the one that names it in the **request body**. Both enumerations missed the other
mechanisms, and the self-review found four more holes:

    GET  /enterprise/connectors/{id}/probe?dataset_id=  query parameter
                                        403 foreign / 404 absent
    POST /graph/query  {"start_id": ...}  both 404, but the detail string echoed
                                        the requested id for the absent case
    POST /catalog/datasets/{id}/publish  both 403, but with different *reasons*
         ...  /patch,  /deprecate        ("tenant boundary denied" vs
                                         "존재하지 않는 데이터셋입니다.")
    GET  /ontology/concept/{concept}     the other caller of the helper that was
                                        scoped for /llm/search - unscoped, so it
                                        listed every tenant's dataset ids to no
                                        actor at all

Two lessons are encoded here. A response is only indistinguishable if the
**status and the body** match - a shared status with different reasons is still
an oracle. And scoping a helper fixes only the callers that pass the scope.
"""

from __future__ import annotations

import json
import re
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from sdp import catalog, evidence, ontology
from sdp.api import app


client = TestClient(app, raise_server_exceptions=False)
FOREIGN = "sweep-foreign-ds"
ABSENT = "sweep-definitely-absent-ds"
PROBER = "analyst"


@pytest.fixture(autouse=True)
def _isolate_shared_state():
    """These tests plant datasets and read the ledger back, so both must reset.

    Without this the file was order-dependent, and the dependence was not
    theoretical: ``test_the_evidence_surfaces_do_not_answer_what_the_route_refused``
    passed on its own and failed in the file, because an earlier test had already
    left rows naming the same two ids in the ledger it inspects. Leaving shared
    state behind was one of the findings this self-review raised against these
    very test files.
    """
    data = {key: value.model_copy(deep=True) for key, value in catalog._DATA.items()}
    audit = list(catalog._AUDIT_LOG)
    decisions = list(evidence._POLICY_DECISION_LOG)
    recorded_audit = list(evidence._AUDIT_EVENT_LOG)
    definitions = deepcopy(ontology._CONCEPT_DEFINITIONS)
    aliases = dict(ontology._ALIAS_TO_CANONICAL)
    try:
        yield
    finally:
        catalog._DATA.clear()
        catalog._DATA.update(data)
        catalog._AUDIT_LOG[:] = audit
        evidence._POLICY_DECISION_LOG[:] = decisions
        evidence._AUDIT_EVENT_LOG[:] = recorded_audit
        ontology._CONCEPT_DEFINITIONS.clear()
        ontology._CONCEPT_DEFINITIONS.update(definitions)
        ontology._ALIAS_TO_CANONICAL.clear()
        ontology._ALIAS_TO_CANONICAL.update(aliases)


def _plant() -> None:
    base = catalog._DATA["crm-customer-master"]
    catalog._DATA[FOREIGN] = base.model_copy(
        update={"id": FOREIGN, "tenant_id": "unreachable-tenant", "terms": ["고객"]}
    )
    ontology._INDEX = ontology._build_index()


def _probes() -> list[tuple[str, object]]:
    """Every mechanism by which a caller can name a dataset to this API."""
    return [
        (
            "query parameter: connector probe",
            lambda d: client.get(
                "/enterprise/connectors/sql_connector/probe",
                params={"dataset_id": d, "user": "analyst"},
            ),
        ),
        (
            "request body: graph traversal start_id",
            lambda d: client.post(
                "/graph/query", json={"actor": "analyst", "start_id": d, "max_depth": 2}
            ),
        ),
        (
            "request body: governed query dataset_ids",
            lambda d: client.post(
                "/browse/query",
                json={
                    "user": "analyst",
                    "dataset_ids": [d],
                    "language": "SQL",
                    "query": "select customer_id from customer",
                    "purpose": "analysis",
                },
            ),
        ),
        (
            "path parameter: catalog detail",
            lambda d: client.get(f"/catalog/datasets/{d}", params={"user": "analyst"}),
        ),
        (
            "path parameter: governed schema",
            lambda d: client.get(
                f"/browse/{d}/schema", params={"user": "analyst", "purpose": "analysis"}
            ),
        ),
        (
            "mutation: publish",
            lambda d: client.post(f"/catalog/datasets/{d}/publish", json={"actor": "data-admin"}),
        ),
        (
            "mutation: patch",
            lambda d: client.patch(
                f"/catalog/datasets/{d}", json={"actor": "data-admin", "title": "x"}
            ),
        ),
        (
            "mutation: deprecate",
            lambda d: client.post(
                f"/catalog/datasets/{d}/deprecate", json={"actor": "data-admin", "reason": "r"}
            ),
        ),
        (
            "what-if: policy decision resource",
            lambda d: client.post(
                "/policy/decision",
                json={"user": "analyst", "resource": d, "action": "preview", "purpose": "analysis"},
            ),
        ),
    ]


def test_no_naming_mechanism_distinguishes_foreign_from_absent() -> None:
    """Status *and* body, for every way a dataset can be named."""
    _plant()
    oracles = []
    for label, probe in _probes():
        foreign = probe(FOREIGN)
        absent = probe(ABSENT)
        if (foreign.status_code, foreign.text) != (absent.status_code, absent.text):
            oracles.append(
                f"{label}: foreign -> {foreign.status_code} {foreign.text[:70]} | "
                f"absent -> {absent.status_code} {absent.text[:70]}"
            )
    assert not oracles, "these tell an outsider which dataset ids exist:\n  " + "\n  ".join(oracles)


def test_no_refusal_explains_itself_to_an_outsider() -> None:
    """The reason string carried the oracle even where the status matched."""
    _plant()
    leaks = []
    for label, probe in _probes():
        body = probe(FOREIGN).text
        for marker in ("tenant", "unreachable-tenant", "존재하지 않는"):
            if marker in body:
                leaks.append(f"{label}: body contains {marker!r}")
    assert not leaks, "an out-of-scope refusal must not name its cause:\n  " + "\n  ".join(leaks)


def test_the_concept_payload_is_scoped_for_both_of_its_callers() -> None:
    """Scoping ``concept_assets`` fixed /llm/search and left this caller open."""
    _plant()
    detail = client.get("/ontology/concept/고객", params={"user": "analyst"}).json()
    search = client.post("/llm/search", json={"user": "analyst", "question": "고객"}).json()

    assert FOREIGN not in detail["dataset_ids"], detail["dataset_ids"]
    assert detail["dataset_ids"] == search["recommendations"]["dataset_ids"], (
        "the two callers of concept_assets must agree"
    )
    assert detail["withheld_dataset_count"] >= 1

    # With no actor at all, nothing is published.
    anonymous = client.get("/ontology/concept/고객").json()
    assert anonymous["dataset_ids"] == []
    assert anonymous["withheld_dataset_count"] >= 1

    # A platform admin still sees the whole mapping.
    admin = client.get("/ontology/concept/고객", params={"user": "admin"}).json()
    assert FOREIGN in admin["dataset_ids"]
    assert admin["withheld_dataset_count"] == 0


# --------------------------------------------------------------------------- #
# The oracle through the *evidence* surface, not the route.
#
# Closing the oracle in the response made the refusal owe the ledger an entry.
# The first attempt at that entry reopened the oracle one surface over: the
# refusal decision was produced by ``evaluate(subject, dataset_id, ...)``, which
# answers deny-filed-to-the-owner for a foreign id and allow-filed-to-the-caller
# for a free one. Measured as the probing analyst, behind two identical 404s:
#
#     foreign id -> GET /policy/decisions  ->  0 rows
#     absent  id -> GET /policy/decisions  ->  1 row, effect "allow"
#
# A prober that can read its own tenant's ledger could therefore ask the ledger
# what the route refused to say. The check below is by *surface*: whatever the
# caller can read back must look the same either way.
# --------------------------------------------------------------------------- #

LEDGER_READS = (
    ("/audit/events", "events"),
    ("/policy/decisions", "decisions"),
)


def _ledger_shape(endpoint: str, container: str, probed_id: str) -> list[str]:
    """Everything the prober can read back that mentions the id it probed.

    Ids and timestamps are masked out (they differ on every run and disclose
    nothing), and the probed id is masked to ``<probed-id>`` because it is the
    caller's own input - its presence is not a disclosure, only a difference
    between the two cases would be.
    """
    response = client.get(endpoint, params={"user": PROBER, "limit": 200})
    if response.status_code != 200:
        return [f"{endpoint}:{response.status_code}"]
    payload = response.json()
    rows = payload if isinstance(payload, list) else payload.get(container, [])
    shapes = []
    for row in rows:
        blob = json.dumps(row, sort_keys=True, ensure_ascii=False)
        if probed_id not in blob:
            continue
        blob = re.sub(r"[0-9a-f]{8}-[0-9a-f-]{27}", "<id>", blob)
        blob = re.sub(r"\d{4}-\d\d-\d\dT[\d:.+]+", "<ts>", blob)
        shapes.append(blob.replace(probed_id, "<probed-id>"))
    return sorted(shapes)


def test_the_evidence_surfaces_do_not_answer_what_the_route_refused() -> None:
    _plant()
    oracles = []
    for endpoint, container in LEDGER_READS:
        foreign_route = client.get(
            f"/catalog/datasets/{FOREIGN}/lineage", params={"user": PROBER}
        )
        foreign_ledger = _ledger_shape(endpoint, container, FOREIGN)
        absent_route = client.get(
            f"/catalog/datasets/{ABSENT}/lineage", params={"user": PROBER}
        )
        absent_ledger = _ledger_shape(endpoint, container, ABSENT)

        assert (foreign_route.status_code, foreign_route.text) == (
            absent_route.status_code,
            absent_route.text,
        ), "the route itself must already be identical"

        if foreign_ledger != absent_ledger:
            oracles.append(
                f"{endpoint}: foreign -> {foreign_ledger} | absent -> {absent_ledger}"
            )
    assert not oracles, (
        "the prober can read back which ids exist:\n  " + "\n  ".join(oracles)
    )


def test_a_scope_refusal_is_still_recorded_for_the_tenant_that_owns_the_dataset() -> None:
    """Uniform to the prober, not absent from the ledger.

    This is the other half: hiding the refusal from the prober must not hide it
    from the auditor whose assets were probed. Before the refusal-evidence
    repair the catalog family wrote a discovery ``allow`` on resource
    ``catalog`` and no audit row at all, so nobody could see the attempt.
    """
    _plant()
    client.get(f"/catalog/datasets/{FOREIGN}/lineage", params={"user": PROBER})

    decisions = client.get("/policy/decisions", params={"user": "admin", "limit": 200})
    assert decisions.status_code == 200, decisions.text
    payload = decisions.json()
    rows = payload if isinstance(payload, list) else payload.get("decisions", [])
    owned = [row for row in rows if row.get("resource") == FOREIGN]
    assert owned, "the owning tenant's auditor must see the attempt"
    assert owned[0]["effect"] == "deny"
    assert owned[0]["reason"] == "tenant boundary denied"
    assert owned[0]["obligations"]["tenant_id"] == catalog._DATA[FOREIGN].tenant_id
    assert owned[0]["obligations"]["refusal_cause"] == "tenant_scope"
