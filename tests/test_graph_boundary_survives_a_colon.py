"""A colon in a dataset id took its graph nodes outside the tenant boundary.

``policy.graph_node_dataset_id`` resolved a node's owning dataset as the part
before the **first** colon, because a graph node id is ``<dataset>:<column>``.
A dataset whose own id contains a colon therefore resolved to nothing - and both
consumers read "nothing" as *shared vocabulary with no owning tenant*:
``can_see_graph_node`` returns ``True`` and ``graph_node_target_tenant`` returns
``None``, which is the one value ``_authorize_graph_write`` treats as "no tenant
to check".

Measured at ``935e309`` with two tenant-``zeta`` datasets, one id carrying a
colon and one not, read and written by ``data-admin`` (tenant ``demo``, roles
``admin`` + ``data-analyst``)::

    GET  /graph/nodes/zeta-plain-admin-probe:customer_email   -> 404 node not found
    POST /graph/nodes  {... zeta-plain-admin-probe:customer_email}
                                                              -> 403 tenant boundary denied
    GET  /graph/nodes/zeta-colon-admin:probe:customer_email   -> 200 {'pii': True, …}
    POST /graph/nodes  {... zeta-colon-admin:probe:customer_email,
                        properties: {'pii': False, 'probe_marker': True}}
                                                              -> 200 upserted

    read back as admin:
      zeta-plain-admin-probe:customer_email   pii=True   probe_marker=None
      zeta-colon-admin:probe:customer_email   pii=False  probe_marker=True

So a foreign tenant's admin read a column it cannot reach by any other route and
**flipped its ``pii`` classification** - on governed metadata that feeds
``POST /search/semantic`` and ``POST /graph/query``. That is the exact defect
``graph_node_target_tenant``'s own docstring says it was written to close, and it
survived through any dataset id containing the separator.

The reasoning that let it through is in that function's comment: "An id shaped
like a dataset node whose dataset does not exist is not tenant-owned … It cannot
reach another tenant's content, because there is no content there to reach."
True for the case it was written for - an absent dataset - and false for this
one, where the prefix resolves to nothing *because the real id contains the
separator*, so there is content there. A premise wider than the thing it guards.

The repair resolves the **longest** dataset-id prefix instead of the first
segment, which strictly extends the old behaviour (it tries the full id first and
otherwise falls back to exactly what it did before), and reserves the separator
in new dataset ids so the ambiguity cannot grow.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from sdp import policy
from sdp.api import app


client = TestClient(app)

COLON_ID = "zeta-colon-guard:probe"
PLAIN_ID = "zeta-plain-guard-probe"
FOREIGN_ACTOR = "data-admin"  # tenant 'demo', holds the admin role
OWNING_TENANT = "zeta"


def _seed_payload(dataset_id: str, tenant_id: str) -> dict:
    """A create body derived from a seed dataset, so every required field is real."""
    schema = client.get("/browse/crm-customer-master/schema?user=admin").json()["schema"]
    base = client.get("/catalog/datasets/crm-customer-master?user=admin").json()
    return {
        "actor": "admin",
        "id": dataset_id,
        "tenant_id": tenant_id,
        "title": "경계 확인용",
        "description": "그래프 테넌트 경계를 확인하기 위한 데이터셋입니다",
        "domain": base.get("domain", "고객"),
        "owner": "owner@example.com",
        "steward": "steward@example.com",
        "update_frequency": "daily",
        "quality_score": 0.9,
        "freshness_score": 0.9,
        "source_system": "warehouse/boundary_guard",
        "sensitivity": "high",
        "terms": ["고객"],
        "schema": schema,
        "distributions": base.get("distributions") or [],
    }


def _create(dataset_id: str, tenant_id: str = OWNING_TENANT):
    return client.post("/catalog/datasets", json=_seed_payload(dataset_id, tenant_id))


def test_a_colon_bearing_dataset_id_is_accepted_and_still_bounded() -> None:
    """The separator stays legal in a dataset id. The boundary must hold anyway.

    Reserving it at the create boundary was the first repair attempted and it
    was wrong: ``tests/test_catalog_mirror_kind_conflict.py`` creates ``부모셋``
    and ``부모셋:자식셋`` as sibling datasets with a ``has_column`` edge, and
    ``소유자셋:자식:컬럼`` as a column node of ``소유자셋:자식``. Two of its tests
    failed on the attempt, which is how the supported shape was found. So the
    fix belongs entirely in the resolver.
    """
    assert _create(COLON_ID).status_code == 200
    assert policy.graph_node_target_tenant(COLON_ID) == OWNING_TENANT
    assert policy.can_see_graph_node(FOREIGN_ACTOR, COLON_ID) is False


def test_the_plain_sibling_behaves_identically() -> None:
    """Both shapes must land on the same side of the boundary."""
    assert _create(PLAIN_ID).status_code == 200
    assert policy.graph_node_target_tenant(PLAIN_ID) == OWNING_TENANT
    assert policy.can_see_graph_node(FOREIGN_ACTOR, PLAIN_ID) is False


def test_the_most_specific_dataset_owns_a_node_two_levels_down() -> None:
    """``소유자셋:자식:컬럼`` used to resolve to ``소유자셋`` - the wrong owner.

    With sibling datasets ``부모`` (tenant demo) and ``부모:자식`` (tenant zeta),
    the column node ``부모:자식:컬럼`` belongs to ``부모:자식``. Resolving the first
    segment attributed it to ``부모`` and therefore to the wrong tenant, which is
    a mis-attribution in its own right rather than only an open door.
    """
    parent, child = "부모경계", "부모경계:자식"
    assert _create(parent, "demo").status_code == 200
    assert _create(child, OWNING_TENANT).status_code == 200
    assert policy.graph_node_dataset_id(f"{child}:컬럼") == child
    assert policy.graph_node_target_tenant(f"{child}:컬럼") == OWNING_TENANT
    assert policy.graph_node_dataset_id(f"{parent}:컬럼") == parent
    assert policy.graph_node_target_tenant(f"{parent}:컬럼") == "demo"


def test_the_resolver_finds_a_dataset_whose_own_id_holds_the_separator() -> None:
    """Existing colon-bearing data must resolve, not fall outside the boundary.

    Driven through the create route, because that route accepts this id - the
    attempt to forbid it is recorded above.
    """
    assert _create(COLON_ID).status_code == 200

    assert policy.graph_node_dataset_id(COLON_ID) == COLON_ID
    assert policy.graph_node_dataset_id(f"{COLON_ID}:customer_email") == COLON_ID
    assert policy.graph_node_target_tenant(COLON_ID) == OWNING_TENANT
    assert policy.graph_node_target_tenant(f"{COLON_ID}:customer_email") == OWNING_TENANT
    assert policy.can_see_graph_node(FOREIGN_ACTOR, COLON_ID) is False
    assert policy.can_see_graph_node(FOREIGN_ACTOR, f"{COLON_ID}:customer_email") is False


def test_a_concept_name_and_a_column_node_still_resolve_as_before() -> None:
    """The change extends the old answer; it must not narrow the other cases."""
    assert policy.graph_node_dataset_id("crm-customer-master") == "crm-customer-master"
    assert policy.graph_node_dataset_id("crm-customer-master:customer_email") == "crm-customer-master"
    # A concept is shared vocabulary: no dataset, no owning tenant.
    assert policy.graph_node_dataset_id("고객") is None
    assert policy.graph_node_target_tenant("고객") is None
    assert policy.can_see_graph_node(FOREIGN_ACTOR, "고객") is True


def test_the_foreign_reader_is_refused_over_http_on_both_shapes() -> None:
    """The boundary the route publishes, measured end to end."""
    assert _create(COLON_ID).status_code == 200
    assert _create(PLAIN_ID).status_code == 200

    for node in (
        f"{PLAIN_ID}:customer_email",
        f"{COLON_ID}:customer_email",
        PLAIN_ID,
        COLON_ID,
    ):
        read = client.get(f"/graph/nodes/{node}?actor={FOREIGN_ACTOR}")
        assert read.status_code == 404, (node, read.status_code, read.text[:200])
        write = client.post(
            "/graph/nodes",
            json={
                "actor": FOREIGN_ACTOR,
                "node_id": node,
                "kind": "column" if ":customer_email" in node else "dataset",
                "properties": {"pii": False, "probe_marker": True},
            },
        )
        assert write.status_code == 403, (node, write.status_code, write.text[:200])
        assert "tenant" in write.json()["detail"], write.json()
