"""An ownerless graph node's ownership is resolved per call, not fixed for its life.

RECORDED, NOT FIXED — in the sense of ``#71``. Every assertion here pins
*measured current behavior*, and three of the four are behavior this repository
would not choose. They are pinned rather than repaired because the obvious
repair is not available: see :func:`test_the_two_cases_are_indistinguishable_by_construction`.

``policy.graph_node_dataset_id`` resolves the longest prefix that names an
**existing** dataset. So an id's owner is a function of what the catalog holds
*at the moment of the call*, not of the id. Three consequences follow, all
measured:

1. A write under a dataset-shaped id whose dataset does not exist is accepted
   for any admin, and the node it creates is ownerless.
2. Ownerless means ``can_see_graph_node`` is True for **every** subject — the
   tenant boundary does not apply to it at all.
3. If that dataset is later created, the *same* node silently becomes the new
   owner's, still carrying the properties and kind written by whoever planted
   it, and the planter loses access to what it wrote.

And a fourth, which is the buyer-visible one: because
``assert_dataset_mirror_kinds_are_available`` refuses a create whose mirror
would reclassify a node, one planted node under one column id is enough to
**block that dataset from ever being created**, with a 409 that reads as though
the requester's own schema conflicts with itself.

The planter does not need to be in the victim's tenant. That step is *composed*
from two measurements rather than measured end to end — the plant succeeds for
any absent dataset id regardless of who will own it, and the create refusal is a
property of the mirror guard independent of who creates — because the seeded
subject table (``authz._SUBJECTS``) contains no admin outside tenant ``demo``,
so a cross-tenant admin cannot be produced without patching it.
"""

import json

from fastapi.testclient import TestClient

from sdp import catalog, policy
from sdp.api import app
from sdp.graph_store import get_store

client = TestClient(app)

PLANTER = "data-admin"
"""Tenant ``demo``, roles ``admin`` + ``data-analyst`` (``authz._SUBJECTS``)."""

EVERY_SEEDED_READER = ("data-admin", "analyst", "data-analyst", "external-analyst", "anonymous")
"""Every seeded subject plus one unknown, spanning three tenant values."""


def _template() -> dict[str, object]:
    """A seeded dataset's payload, as JSON-safe fields to copy for a new id."""
    base = catalog._DATA["crm-customer-master"]
    return json.loads(base.model_dump_json())


def _plant(node_id: str, *, kind: str = "concept") -> int:
    """Write one graph node under ``node_id`` as the planter; return the status."""
    response = client.post(
        "/graph/nodes",
        json={
            "actor": PLANTER,
            "node_id": node_id,
            "kind": kind,
            "label": "planted-outside-the-owning-tenant",
            "properties": {"pii": False, "planted": True},
        },
    )
    return response.status_code


def _create_dataset(dataset_id: str, *, tenant_id: str = "demo") -> tuple[int, str]:
    """Create a dataset through the product mutation path; return status and body."""
    body = _template()
    body["id"] = dataset_id
    body["tenant_id"] = tenant_id
    body["actor"] = PLANTER
    response = client.post("/catalog/datasets", json=body)
    return response.status_code, response.text


def test_a_write_under_an_absent_datasets_id_is_accepted_and_is_ownerless() -> None:
    """Consequence 1: the id looks dataset-scoped, and nothing owns the result."""
    node_id = "absent-dataset-one:customer_email"
    assert "absent-dataset-one" not in catalog._DATA
    assert _plant(node_id) == 200
    assert policy.graph_node_target_tenant(node_id) is None
    assert policy.graph_node_dataset_id(node_id) is None


def test_an_ownerless_node_is_visible_to_every_subject_in_every_tenant() -> None:
    """Consequence 2: the tenant boundary does not apply to an ownerless node.

    Asserted against every seeded subject rather than a chosen one, because a
    single-subject check would read as "visible to that tenant" when the
    measured property is "visible to all of them".
    """
    node_id = "absent-dataset-two:customer_email"
    assert _plant(node_id) == 200
    assert all(policy.can_see_graph_node(who, node_id) for who in EVERY_SEEDED_READER)

    # The contrast that makes the point: an id whose dataset *does* exist in
    # another tenant is hidden from the same subjects.
    catalog._DATA["foreign-owned"] = catalog._DATA["crm-customer-master"].model_copy(
        update={"id": "foreign-owned", "tenant_id": "zeta"}
    )
    assert not policy.can_see_graph_node("data-admin", "foreign-owned:customer_email")


def test_creating_the_dataset_later_transfers_the_planted_node_to_its_new_owner() -> None:
    """Consequence 3: the node is unchanged, and the owner changes under it."""
    dataset_id = "absent-dataset-three"
    node_id = f"{dataset_id}:customer_email"
    assert _plant(node_id) == 200
    assert policy.can_see_graph_node("data-admin", node_id)

    catalog._DATA[dataset_id] = catalog._DATA["crm-customer-master"].model_copy(
        update={"id": dataset_id, "tenant_id": "zeta"}
    )

    assert policy.graph_node_target_tenant(node_id) == "zeta"
    assert not policy.can_see_graph_node("data-admin", node_id)
    stored = get_store().get_node(node_id)
    assert stored is not None
    # Still the planter's content, now inside the new owner's graph. ``pii`` is
    # governed metadata that drives masking, so a planted ``False`` is not inert.
    assert stored.kind == "concept"
    assert stored.label == "planted-outside-the-owning-tenant"
    assert stored.properties["pii"] is False
    assert stored.properties["planted"] is True


def test_one_planted_node_blocks_that_dataset_from_being_created_at_all() -> None:
    """Consequence 4, the buyer-visible one: onboarding is refused, with no row.

    The control matters: the same create succeeds when nothing is planted, so
    the refusal is attributable to the planted node and not to the payload.
    """
    assert _create_dataset("control-with-nothing-planted")[0] == 200

    victim = "absent-dataset-four"
    assert _plant(f"{victim}:customer_id") == 200
    status, body = _create_dataset(victim)
    assert status == 409
    assert "kind cannot be changed" in body
    assert victim not in catalog._DATA, "refused, and nothing was written"


def test_the_two_cases_are_indistinguishable_by_construction() -> None:
    """Why this is pinned and not repaired.

    The repair that suggests itself — refuse a write under a dataset-shaped id
    whose dataset does not exist — is not expressible. ``graph_node_dataset_id``
    returns ``None`` for *both* an absent dataset's column id and an ordinary
    business concept, because it resolves the longest prefix that names an
    existing dataset and neither has one. A rule keyed on that answer would
    refuse every legitimate concept write too, and a rule keyed on the presence
    of a separator would refuse the glossary terms this product is built to
    hold, while still accepting a planted bare dataset id.

    So the finding is a property of the ownership model, not of one call site,
    and anything that closes it is a model change rather than a guard.
    """
    assert policy.graph_node_dataset_id("absent-dataset-five:customer_email") is None
    assert policy.graph_node_dataset_id("customer_lifetime_value") is None
    assert policy.graph_node_dataset_id("absent-dataset-five") is None
