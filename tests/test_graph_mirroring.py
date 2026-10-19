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
from sdp.seed import seed_dataset


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


@pytest.fixture(autouse=True)
def _remirror_the_seeded_datasets(_restore_catalog):
    """Establish this file's own graph baseline before each test.

    ``tests/conftest.py`` restores ``catalog._DATA`` but deliberately does not
    restore the graph store - it has no snapshot API, and adding one to the
    product for the test suite would be the wrong trade. Its docstring says a
    test that depends on graph-store contents must establish its own baseline,
    and these tests do: once a test removes edges, the catalog is restored while
    the graph keeps the removal, so the next test would find nothing left to
    remove and its precondition would fail. Re-mirroring from the restored
    catalog is idempotent, which is the property that makes this cheap.
    """
    for dataset in catalog.list_datasets():
        seed_dataset(dataset)
    yield


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


# --------------------------------------------------------------------------- #
# The reverse direction: a *removal* must reach the graph too.
#
# Every mirror write was an upsert and the store had no removal primitive at
# all, so the mirror was append-only. Measured after
# ``PATCH /catalog/datasets/crm-customer-master`` dropped the declared-PII
# column ``customer_email``:
#
#     catalog schema                          customer_id, signup_at
#     GET /graph/nodes/...:customer_email     200, properties.pii = true
#     POST /search/semantic "customer_email"  top hit, score 0.673 (analyst)
#
# ``/browse`` masks that column while it is declared, so removing it made the
# column *more* exposed than keeping it. ``/graph/stats`` was monotone: 26 nodes
# / 78 edges before and after stripping a dataset bare.
# --------------------------------------------------------------------------- #


def _declared_column_nodes(dataset_id: str) -> set[str]:
    dataset = catalog._DATA[dataset_id]
    return {f"{dataset_id}:{column.name}" for column in dataset.schema}


def _graph_column_nodes(dataset_id: str) -> set[str]:
    return {
        edge.target_id for edge in get_store().edges_for(dataset_id, "has_column")
    }


def test_a_removed_column_leaves_the_graph_and_semantic_search() -> None:
    """The PII case, because it is the one that matters most."""
    dataset = catalog._DATA["crm-customer-master"]
    pii_columns = [column.name for column in dataset.schema if column.pii]
    assert pii_columns, "fixture must declare a PII column for this to mean anything"

    kept = [column.model_dump() for column in dataset.schema if not column.pii]
    patched = client.patch(
        "/catalog/datasets/crm-customer-master",
        json={"actor": "admin", "schema": kept},
    )
    assert patched.status_code == 200, patched.text

    for column in pii_columns:
        node_id = f"crm-customer-master:{column}"
        assert get_store().get_node(node_id) is None, f"{node_id} survived in the graph"
        found = client.post(
            "/search/semantic",
            json={"actor": "analyst", "query": column, "kind": "column", "limit": 5},
        )
        assert found.status_code == 200, found.text
        hits = [row["node_id"] for row in found.json()["results"]]
        assert node_id not in hits, f"{node_id} still returned by semantic search: {hits}"


def test_the_graph_column_set_equals_the_catalog_after_a_rename() -> None:
    """A rename used to leave both names behind."""
    dataset = catalog._DATA["crm-customer-master"]
    renamed = [column.model_dump() for column in dataset.schema]
    renamed[0]["name"] = f"{renamed[0]['name']}_v2"
    patched = client.patch(
        "/catalog/datasets/crm-customer-master", json={"actor": "admin", "schema": renamed}
    )
    assert patched.status_code == 200, patched.text

    assert _graph_column_nodes("crm-customer-master") == _declared_column_nodes(
        "crm-customer-master"
    )


@pytest.mark.parametrize(
    "field,edge_type,direction",
    [
        ("terms", "mapping", "out"),
        ("mappings", "mapping", "out"),
        ("related_datasets", "related_dataset", "out"),
    ],
)
def test_every_mirrored_facet_is_reconciled_not_only_appended(
    field: str, edge_type: str, direction: str
) -> None:
    """Enumerated by facet, because fixing one of these would have missed the rest.

    Measured before the repair, after a PATCH clearing all five on
    ``crm-event``: mapping 5 edges unchanged, lineage out 4 unchanged, lineage
    in 4 unchanged, related_dataset 2 unchanged, while
    ``GET /catalog/datasets/crm-event/lineage`` reported both lists empty.

    The two ``lineage`` facets moved to
    ``test_a_lineage_edge_is_reconciled_against_both_of_its_declarers`` below.
    They are still covered, and still against the same defect; what changed is
    that clearing one endpoint's list is not sufficient to make a lineage edge
    undeclared. ``crm-event.lineage_outputs`` and
    ``crm-customer-master.lineage_inputs`` name the *same* edge, so reconciling
    it away on the strength of one side alone was itself the bug - it left the
    graph contradicting the catalog, which still declared the edge from the
    other side. The facets kept here (``terms``, ``mappings``,
    ``related_datasets``) have one declarer each, so the original setup remains
    exactly right for them.
    """
    before = get_store().edges_for("crm-event", edge_type, direction=direction)
    assert before, f"fixture must have {edge_type} ({direction}) edges to remove"

    cleared = client.patch(
        "/catalog/datasets/crm-event",
        json={
            "actor": "admin",
            "terms": [],
            "mappings": [],
            "lineage_inputs": [],
            "lineage_outputs": [],
            "related_datasets": [],
        },
    )
    assert cleared.status_code == 200, cleared.text

    after = get_store().edges_for("crm-event", edge_type, direction=direction)
    assert not after, (
        f"{edge_type} ({direction}) survived the removal: "
        f"{[(e.source_id, e.target_id) for e in after]}"
    )


def _lineage_pairs(dataset_id: str, direction: str) -> set[tuple[str, str]]:
    """The graph's lineage edges at one end of a dataset."""
    return {
        (edge.source_id, edge.target_id)
        for edge in get_store().edges_for(dataset_id, "lineage", direction=direction)
    }


def _clear_lineage(dataset_id: str) -> None:
    """Clear one dataset's own lineage declarations through the product route."""
    cleared = client.patch(
        f"/catalog/datasets/{dataset_id}",
        json={"actor": "admin", "lineage_inputs": [], "lineage_outputs": []},
    )
    assert cleared.status_code == 200, cleared.text


def test_a_lineage_edge_is_reconciled_against_both_of_its_declarers() -> None:
    """A lineage edge survives until *neither* endpoint declares it.

    ``A -> B`` exists because A lists B in ``lineage_outputs`` or because B
    lists A in ``lineage_inputs``; the mirror creates it from either side. The
    reconcile consulted only the mutated dataset's own half, so seeding or
    mutating the non-declaring endpoint deleted an edge the catalog still
    declared - and the startup bootstrap seeds every dataset in turn, so
    whichever was seeded second wiped the other's declaration. Measured before
    the repair, on a pair where only the upstream declares the link::

        PATCH lin-up {"lineage_outputs": ["lin-down"]} ; seed lin-up
          -> incoming edges of lin-down: [("lin-up", "lin-down")]
        seed lin-down
          -> incoming edges of lin-down: []
          -> catalog still declares lin-up.lineage_outputs == ["lin-down"]
    """
    # The seeded pair declares one edge from both sides at once.
    assert "crm-customer-master" in catalog._DATA["crm-event"].lineage_outputs
    assert "crm-event" in catalog._DATA["crm-customer-master"].lineage_inputs
    shared = ("crm-event", "crm-customer-master")
    assert shared in _lineage_pairs("crm-event", "out")

    # Clearing one declarer is not enough: the other still declares it.
    _clear_lineage("crm-event")
    assert shared in _lineage_pairs("crm-event", "out"), (
        "the edge was removed although crm-customer-master.lineage_inputs "
        "still declares it"
    )
    # An edge whose only declarer was the cleared list is gone, so this is not
    # passing by way of a reconcile that removes nothing.
    assert ("app-event-raw", "crm-event") not in _lineage_pairs("crm-event", "in")

    # Clearing the second declarer removes it.
    _clear_lineage("crm-customer-master")
    assert shared not in _lineage_pairs("crm-event", "out"), (
        "no declarer remains, so the edge should have been reconciled away"
    )


def test_mutating_a_dataset_keeps_edges_its_partners_declare() -> None:
    """An unrelated mutation must not disturb a partner's declared lineage."""
    incoming_before = _lineage_pairs("crm-event", "in")
    declared_by_partners = {
        pair
        for pair in incoming_before
        if pair[0] in catalog._DATA
        and "crm-event" in catalog._DATA[pair[0]].lineage_outputs
    }
    assert declared_by_partners, "fixture must have partner-declared incoming edges"

    renamed = client.patch(
        "/catalog/datasets/crm-event", json={"actor": "admin", "title": "제목 변경"}
    )
    assert renamed.status_code == 200, renamed.text
    assert declared_by_partners <= _lineage_pairs("crm-event", "in"), (
        "a title change deleted lineage edges other datasets declare"
    )


def test_graph_stats_can_decrease() -> None:
    """It was monotone, which is how the append-only mirror stayed invisible."""
    store = get_store()
    before = store.stats()["edges"]
    cleared = client.patch(
        "/catalog/datasets/crm-event",
        json={
            "actor": "admin",
            "terms": [],
            "mappings": [],
            "lineage_inputs": [],
            "lineage_outputs": [],
            "related_datasets": [],
        },
    )
    assert cleared.status_code == 200, cleared.text
    assert store.stats()["edges"] < before, (
        f"edges did not decrease: {before} -> {store.stats()['edges']}"
    )


def test_reconciling_does_not_remove_nodes_this_dataset_does_not_own() -> None:
    """A mapping edge goes; the concept it pointed at stays.

    The dataset owns its ``{id}:{column}`` nodes and nothing else. Deleting a
    concept or another dataset because one mapping was dropped would turn a
    metadata edit into data loss for every other consumer of that concept.
    """
    store = get_store()
    concepts_before = store.stats()["concepts"]
    mapped = {edge.target_id for edge in store.edges_for("crm-event", "mapping")}
    assert mapped, "fixture must have mapping edges"

    cleared = client.patch(
        "/catalog/datasets/crm-event",
        json={"actor": "admin", "terms": [], "mappings": []},
    )
    assert cleared.status_code == 200, cleared.text

    assert store.stats()["concepts"] == concepts_before
    for concept in mapped:
        if concept in catalog._DATA:  # another dataset, not a concept node
            assert store.get_node(concept) is not None, f"{concept} was deleted"
