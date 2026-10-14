"""A dataset onboarded through the API must reach the graph.

``seed_store()`` mirrors every dataset - its node, columns, mappings and lineage -
into the graph store, and it ran **only at startup**. So a dataset created through
``POST /catalog/datasets`` never reached the graph at all. Measured before the
repair, immediately after a successful create::

    POST /catalog/datasets          -> 200
    GET  /graph/stats               -> nodes 26 -> 26, embeddings 26 -> 26
    GET  /graph/nodes/<new dataset> -> 404

README names graph traversal and semantic search as headline capabilities, so a
buyer's own data being invisible to both is a product gap rather than a seeding
detail. A status change had the same problem in reverse: the graph kept a stale
node after publish or deprecate.

Every write in that path is an upsert, which is why one function serves both the
startup bootstrap and each later mutation - no second mirror was written.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from sdp import catalog
from sdp.api import app
from sdp.graph_store import get_store


client = TestClient(app, raise_server_exceptions=False)


def _create_payload(dataset_id: str, **overrides) -> dict:
    payload = json.loads(catalog._DATA["crm-customer-master"].model_dump_json())
    payload.update(
        {
            "id": dataset_id,
            "title": f"{dataset_id} 제목",
            "description": "설명",
            "actor": "admin",
        }
    )
    payload.update(overrides)
    return payload


@pytest.fixture(autouse=True)
def _restore_catalog():
    data = {key: value.model_copy(deep=True) for key, value in catalog._DATA.items()}
    yield
    catalog._DATA.clear()
    catalog._DATA.update(data)


def test_a_created_dataset_and_its_columns_reach_the_graph() -> None:
    before = client.get("/graph/stats").json()["stats"]
    created = client.post("/catalog/datasets", json=_create_payload("mirror-new-ds"))
    assert created.status_code == 200, created.text
    after = client.get("/graph/stats").json()["stats"]

    assert after["nodes"] > before["nodes"], "the dataset node was not written"
    assert after["embeddings"] > before["embeddings"], "no embedding was indexed"

    node = client.get("/graph/nodes/mirror-new-ds", params={"actor": "admin"})
    assert node.status_code == 200, node.text
    assert node.json()["kind"] == "dataset"

    # Columns too, so semantic search over column names reaches onboarded data.
    column_count = len(catalog._DATA["mirror-new-ds"].schema)
    assert column_count >= 1
    for column in catalog._DATA["mirror-new-ds"].schema:
        column_node = client.get(
            f"/graph/nodes/mirror-new-ds:{column.name}", params={"actor": "admin"}
        )
        assert column_node.status_code == 200, column_node.text
        assert column_node.json()["kind"] == "column"


def test_a_status_change_updates_the_node_instead_of_leaving_it_stale() -> None:
    client.post("/catalog/datasets", json=_create_payload("mirror-status-ds"))

    def node_status() -> str:
        body = client.get("/graph/nodes/mirror-status-ds", params={"actor": "admin"}).json()
        return body["properties"]["status"]

    created_status = node_status()
    assert client.post(
        "/catalog/datasets/mirror-status-ds/deprecate",
        json={"actor": "admin", "reason": "테스트"},
    ).status_code == 200
    assert node_status() == "deprecated", "the graph kept a stale status"
    assert created_status != "deprecated", "fixture no longer demonstrates the change"


def test_mirroring_does_not_widen_who_can_see_the_dataset() -> None:
    """The per-node boundary must still apply to an onboarded dataset."""
    client.post(
        "/catalog/datasets",
        json=_create_payload("mirror-foreign-ds", tenant_id="unreachable-tenant"),
    )

    for node_id in ("mirror-foreign-ds", "mirror-foreign-ds:customer_id"):
        refused = client.get(f"/graph/nodes/{node_id}", params={"actor": "analyst"})
        # 404, matching a node that does not exist: node ids are derived from
        # dataset ids, so a 403/404 split would tell an outsider which datasets
        # exist. The boundary holds either way; only the status is uniform.
        assert refused.status_code == 404, refused.text
        assert "tenant" not in refused.text

    allowed = client.get("/graph/nodes/mirror-foreign-ds", params={"actor": "admin"})
    assert allowed.status_code == 200, allowed.text


def test_a_foreign_node_is_indistinguishable_from_a_missing_one() -> None:
    client.post(
        "/catalog/datasets",
        json=_create_payload("mirror-oracle-ds", tenant_id="unreachable-tenant"),
    )
    foreign = client.get("/graph/nodes/mirror-oracle-ds", params={"actor": "analyst"})
    missing = client.get("/graph/nodes/definitely-not-a-node", params={"actor": "analyst"})
    assert (foreign.status_code, foreign.text) == (missing.status_code, missing.text)


def test_the_startup_bootstrap_is_still_idempotent() -> None:
    """One function now serves both paths; re-running it must change nothing."""
    from sdp.seed import seed_store

    first = seed_store()
    second = seed_store()
    assert first == second, "re-seeding changed the store, so a write is not an upsert"
    assert get_store().stats() == second
