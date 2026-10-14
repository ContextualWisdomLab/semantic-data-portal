"""``dataset_ids`` is dataset identity, and this payload leaked it three times.

The concept vocabulary is shared and open; which datasets map to a concept is
not. ``ontology.concept_assets`` was given a tenant scope to close the first two
callers (``POST /llm/search`` and ``GET /ontology/concept/{concept}``). The
third, ``GET /ontology/term/{term}/graph``, reads the **graph store's** own
``concept_graph`` instead and took no actor at all. Measured with a tenant-``zeta``
dataset present and no credential of any kind::

    anon GET /ontology/concept/고객     -> dataset_ids [], withheld_dataset_count 4
    anon POST /llm/search              -> 403
    anon GET /ontology/term/고객/graph  -> 200, dataset_ids
        ['crm-customer-master', 'marketing-campaign', 'sales-order',
         'semantic-glossary', 'zeta-secret']
    ledger delta for that call: decisions +0  audits +0

So the one fact two sibling routes refuse was handed over in full - including a
foreign tenant's dataset id - with no policy decision and no audit event. That
contradicts the product's own published guardrail ("No unauthorized dataset
existence disclosure", ``sdp_core.kpis``) and the governance invariant that a
governed read evaluates policy and records evidence.

Fixing one caller at a time is the pattern that produced three instances, so the
enumeration below derives the routes that return this field from the live
OpenAPI document rather than naming them.
"""

from __future__ import annotations

from pathlib import Path
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sdp import catalog, evidence  # noqa: E402
from sdp.api import app  # noqa: E402
from sdp.api_response_contract import RESPONSE_SCHEMAS  # noqa: E402

client = TestClient(app, raise_server_exceptions=False)

FOREIGN = {
    "actor": "admin",
    "id": "zeta-secret",
    "tenant_id": "zeta",
    "title": "Z",
    "description": "d",
    "owner": "o",
    "steward": "s",
    "domain": "z",
    "source_system": "pg://zeta/secret",
    "sensitivity": "medium",
    "update_frequency": "daily",
    "quality_score": 0.9,
    "freshness_score": 0.9,
    "schema": [
        {
            "name": "customer_email",
            "datatype": "string",
            "nullable_ratio": 0.0,
            "distinct_ratio": 1.0,
            "pii": True,
        }
    ],
    "distributions": [{"id": "d1", "format": "table", "endpoint": "https://x/y"}],
    "mappings": [{"concept": "고객", "status": "approved"}],
}


@pytest.fixture
def foreign_dataset() -> str:
    created = client.post("/catalog/datasets", json=FOREIGN)
    assert created.status_code == 200, created.text
    return FOREIGN["id"]


def test_an_anonymous_caller_reads_no_dataset_ids(foreign_dataset: str) -> None:
    body = client.get("/ontology/term/고객/graph").json()
    assert body["dataset_ids"] == [], body
    assert body["withheld_dataset_count"] >= 1, body
    assert foreign_dataset not in str(body)


def test_the_three_sibling_routes_now_agree(foreign_dataset: str) -> None:
    """The property that was violated: one fact, three routes, one answer."""
    concept = client.get("/ontology/concept/고객").json()
    graph = client.get("/ontology/term/고객/graph").json()
    assert concept["dataset_ids"] == graph["dataset_ids"] == []
    assert client.post("/llm/search", json={"question": "고객"}).status_code == 403


def test_a_tenant_scoped_caller_sees_its_own_and_is_told_what_is_withheld(
    foreign_dataset: str,
) -> None:
    """The withheld count is derived, not hardcoded.

    ``tests/conftest.py`` deliberately does not restore the graph store - it has
    no snapshot API - so mapping edges written by earlier tests persist and the
    absolute number of mapped datasets varies with file order. An earlier
    version asserted ``== 1`` and passed alone while failing in the full run.
    The invariant is the relationship between the two views, which holds at any
    baseline.
    """
    crossing = client.get("/ontology/term/고객/graph", params={"user": "admin"}).json()
    scoped = client.get("/ontology/term/고객/graph", params={"user": "analyst"}).json()

    assert scoped["dataset_ids"], scoped
    assert foreign_dataset in crossing["dataset_ids"], crossing
    assert foreign_dataset not in scoped["dataset_ids"], scoped
    # Declared, so a short list does not read as the whole mapping.
    assert scoped["withheld_dataset_count"] == len(crossing["dataset_ids"]) - len(
        scoped["dataset_ids"]
    ), (crossing, scoped)
    assert scoped["withheld_dataset_count"] >= 1, scoped


def test_a_platform_admin_still_crosses_tenants(foreign_dataset: str) -> None:
    body = client.get("/ontology/term/고객/graph", params={"user": "admin"}).json()
    assert foreign_dataset in body["dataset_ids"], body
    assert body["withheld_dataset_count"] == 0, body


def test_the_shared_vocabulary_itself_stays_open() -> None:
    """Scoping dataset identity must not have closed the glossary.

    The concept, its definition and its aliases are shared across tenants by
    design; it is only the mapping to datasets that is tenant data.
    """
    body = client.get("/ontology/term/고객/graph").json()
    assert body["definition"], body
    assert body["aliases"], body
    assert body["canonical"] == "고객"


def test_an_unknown_term_is_unchanged() -> None:
    body = client.get("/ontology/term/no-such-term/graph").json()
    assert body["not_found"] is True
    assert body["canonical"] == "no-such-term"


def test_every_route_returning_dataset_ids_is_scoped(foreign_dataset: str) -> None:
    """Derived from the published response contract, not hand-listed.

    This payload has leaked through three different callers, each fixed in turn.
    The enumeration is the thing that catches the fourth: any GET whose published
    200 schema declares ``dataset_ids`` must withhold a foreign tenant's id from
    an anonymous caller.
    """
    paths = [
        path
        for (method, path), schema in RESPONSE_SCHEMAS.items()
        if method == "GET" and "dataset_ids" in (schema.get("properties") or {})
    ]
    assert paths, "the contract must publish at least one dataset_ids route"

    leaking = []
    for path in paths:
        url = path.replace("{term}", "고객").replace("{concept}", "고객")
        url = url.replace("{dataset_id}", "crm-customer-master")
        response = client.get(url)
        if response.status_code != 200:
            continue
        if foreign_dataset in str(response.json()):
            leaking.append(path)
    assert not leaking, (
        "these routes serve a foreign tenant's dataset id to an anonymous "
        f"caller: {leaking}"
    )


def test_the_scoped_route_is_not_a_new_ledger_write_surface(foreign_dataset: str) -> None:
    """Scoping must not have turned an open read into an unauthenticated write.

    ``POST /enterprise/auth/oidc-preview`` was recording on every anonymous call
    before that was closed; a scoping change that starts writing a decision row
    per anonymous read would reintroduce the same unbounded-growth surface.
    """
    before = (len(evidence._POLICY_DECISION_LOG), len(evidence._AUDIT_EVENT_LOG))
    for _ in range(5):
        client.get("/ontology/term/고객/graph")
    assert (len(evidence._POLICY_DECISION_LOG), len(evidence._AUDIT_EVENT_LOG)) == before
