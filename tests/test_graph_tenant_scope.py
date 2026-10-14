"""Tenant scoping of the graph read surface.

The graph carries the same dataset and column nodes the catalog does — column
nodes include the per-column ``pii`` classification that ``discovery_view``,
``discovery_column_view`` and the ``/browse/{id}/schema`` gate all withhold. Three
graph read paths bypassed that boundary:

* ``GET /graph/nodes/{node_id}`` had no authorization at all.
* ``_authorize_graph_read`` evaluated ``action="search"``, which the policy engine
  short-circuits on the reader-role check *before* its tenant check, so
  ``/graph/query`` and ``/search/semantic`` enforced authentication but no tenant
  boundary.
* Traversal walks through shared business-concept nodes, so a start node in one
  tenant reaches datasets in another at depth 2 — entry gating alone cannot fix it.
"""

from __future__ import annotations

from pathlib import Path
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sdp import catalog, evidence, policy  # noqa: E402
from sdp.api import app  # noqa: E402
from sdp.graph_store import get_store  # noqa: E402
from sdp.seed import seed_store  # noqa: E402

client = TestClient(app)

ACME_DATASET = "acme-secret-ds"
ACME_COLUMN = f"{ACME_DATASET}:customer_email"


@pytest.fixture(autouse=True)
def _seed_foreign_tenant_dataset():
    """Seed a dataset owned by tenant ``acme-bank`` into the catalog and graph."""
    data = {k: v.model_copy(deep=True) for k, v in catalog._DATA.items()}
    audit = list(catalog._AUDIT_LOG)
    decisions = list(evidence._POLICY_DECISION_LOG)
    base = catalog._DATA["crm-customer-master"]
    catalog._DATA[ACME_DATASET] = base.model_copy(
        update={"id": ACME_DATASET, "tenant_id": "acme-bank", "title": "ACME secret master"}
    )
    seed_store(get_store())
    try:
        yield
    finally:
        catalog._DATA.clear()
        catalog._DATA.update(data)
        catalog._AUDIT_LOG.clear()
        catalog._AUDIT_LOG.extend(audit)
        evidence._POLICY_DECISION_LOG.clear()
        evidence._POLICY_DECISION_LOG.extend(decisions)
        seed_store(get_store())


def test_graph_node_read_requires_an_authorized_reader():
    """It had no gate at all: an anonymous caller read a column node's pii flag."""
    anonymous = client.get(f"/graph/nodes/{ACME_COLUMN}")
    assert anonymous.status_code == 403, anonymous.text


def test_graph_node_read_enforces_the_tenant_boundary():
    """A reader in another tenant is refused, exactly as /browse/{id}/schema refuses."""
    refused = client.get(f"/graph/nodes/{ACME_COLUMN}", params={"actor": "analyst"})
    # 404, not 403: node ids are derived from dataset ids, so answering 403
    # for a foreign node and 404 for a missing one tells an outsider which
    # datasets exist - the same oracle the browse/catalog/llm families were
    # repaired to close. The boundary still holds; only the status changed.
    assert refused.status_code == 404
    assert refused.json()["detail"] == "node not found"
    assert "tenant" not in refused.text, "the refusal must not explain itself"

    # The owning tenant's reader still gets the node.
    allowed = client.get(f"/graph/nodes/{ACME_COLUMN}", params={"actor": "admin"})
    assert allowed.status_code == 200
    assert allowed.json()["properties"]["pii"] is True


def test_graph_node_read_still_serves_non_dataset_nodes():
    """Business concepts belong to no dataset and stay readable by any reader."""
    concept = client.get("/graph/nodes/고객", params={"actor": "analyst"})
    assert concept.status_code == 200
    assert concept.json()["kind"] == "concept"


def test_graph_traversal_withholds_other_tenants_nodes():
    """Measured before this contract: depth 2 from ``crm-customer-master`` (tenant
    demo) reached ``acme-secret-ds`` (tenant acme-bank) through shared concepts."""
    response = client.post(
        "/graph/query",
        json={"actor": "analyst", "start_id": "crm-customer-master", "max_depth": 3},
    )
    assert response.status_code == 200
    body = response.json()
    reached = {node["node_id"].split(":")[0] for node in body["nodes"]}
    assert ACME_DATASET not in reached, sorted(reached)

    # Edges must not reference a node that was withheld.
    visible = {node["node_id"] for node in body["nodes"]}
    for edge in body["edges"]:
        assert edge["source_id"] in visible and edge["target_id"] in visible, edge

    # Withholding is reported, not silent.
    assert body["withheld_node_count"] >= 1


def test_graph_traversal_refuses_a_start_node_in_another_tenant():
    response = client.post(
        "/graph/query", json={"actor": "analyst", "start_id": ACME_DATASET, "max_depth": 1}
    )
    # 404, not 403: node ids are derived from dataset ids, so answering 403
    # for a foreign node and 404 for a missing one tells an outsider which
    # datasets exist - the same oracle the browse/catalog/llm families were
    # repaired to close. The boundary still holds; only the status changed.
    assert response.status_code == 404
    assert response.json()["detail"] == "node not found"
    assert "tenant" not in response.text, "the refusal must not explain itself"


def test_semantic_search_withholds_other_tenants_nodes():
    """The acme dataset was the top hit for a tenant-demo reader."""
    response = client.post(
        "/search/semantic", json={"actor": "analyst", "query": "ACME secret", "limit": 10}
    )
    assert response.status_code == 200
    body = response.json()
    assert all(not r["node_id"].startswith(ACME_DATASET) for r in body["results"]), body["results"]
    assert body["count"] == len(body["results"])
    assert "withheld_result_count" in body


def test_platform_admin_still_crosses_the_graph_boundary():
    """The explicit platform-admin crossing is preserved on the graph surface too."""
    response = client.post(
        "/search/semantic", json={"actor": "admin", "query": "ACME secret", "limit": 10}
    )
    assert response.status_code == 200
    assert any(r["node_id"].startswith(ACME_DATASET) for r in response.json()["results"])


def test_can_see_graph_node_decides_by_the_owning_dataset():
    """Unit-level contract for the visibility rule."""
    assert policy.can_see_graph_node("admin", ACME_COLUMN) is True          # platform-admin
    assert policy.can_see_graph_node("analyst", ACME_COLUMN) is False       # other tenant
    assert policy.can_see_graph_node("analyst", "crm-customer-master:customer_email") is True
    assert policy.can_see_graph_node("analyst", "고객") is True              # not dataset-owned
