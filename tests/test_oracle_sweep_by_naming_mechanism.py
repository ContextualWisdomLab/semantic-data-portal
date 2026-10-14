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

from fastapi.testclient import TestClient

from sdp import catalog, ontology
from sdp.api import app


client = TestClient(app, raise_server_exceptions=False)
FOREIGN = "sweep-foreign-ds"
ABSENT = "sweep-definitely-absent-ds"


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
