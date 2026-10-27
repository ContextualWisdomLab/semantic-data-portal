"""The SHACL evidence route's own comment says it carries no dataset identity.

``GET /enterprise/shacl-validation``'s route comment reads "The aggregate stays
open - it carries no dataset identity. The per-dataset report array does, so it
is scoped", and ``enterprise_shacl_validation_summary`` exempts the
``hierarchy_class_separation`` block on the matching ground: "the edge
identifiers it reports are concept names, which the ontology surface already
serves to any caller".

That premise is false in the one branch the block exists for. ``ConceptHierarchyShape``
reports a violation precisely when a hierarchy endpoint **is a dataset node
rather than a concept**, so the identifier in that message is a dataset id by
construction, and the message prints it.

Reproduced at ``09ee1ad``, with no credential of any kind at the final read::

    0) anonymous GET /enterprise/shacl-validation
         withheld_report_count 5 · reports 0 · hierarchy violations 2 (both warnings)

    1) data-admin (tenant demo) plants a hierarchy edge to an id that is not a node
         POST /graph/edges {broader, 고객 -> zeta-leak-probe}        -> 200

    2) tenant zeta onboards that id
         POST /catalog/datasets {id: zeta-leak-probe, tenant_id: zeta} -> 200

    3) anonymous GET /enterprise/shacl-validation
         withheld_report_count 6 · reports 0
         + {"severity": "violation", "message": "hierarchy target is a 'dataset'
            node rather than a 'concept', … : broader: 고객 -> zeta-leak-probe
            (target=zeta-leak-probe)"}

    control, same anonymous caller:
         GET /catalog/datasets/zeta-leak-probe   -> 403
         GET /browse/zeta-leak-probe/schema      -> 404
         GET /graph/nodes/zeta-leak-probe        -> 403
         GET /catalog/search?q=제타               -> 403

``withheld_report_count`` rising to 6 in the same body is the route stating that
it is withholding six per-dataset reports while handing over a seventh tenant's
dataset id one key over. The write in step 1 needs only a reader of another
tenant: an edge to an unknown endpoint is permitted by design (the seed's load
order needs it), and the endpoint becoming a dataset afterwards is the case the
report exists to catch.

The exemption's *true* half is kept: a hierarchy endpoint that is a concept name
is shared vocabulary and stays visible, which is why the two seeded warnings
about ``매출 성장`` and ``매출 채널별 집계`` are asserted to survive below.
"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from sdp.api import app
from sdp.catalog import list_datasets


client = TestClient(app)

FOREIGN_TENANT = "zeta"
PLANTED_ID = "zeta-hierarchy-leak-probe"


def _seed_foreign_dataset_reachable_only_through_the_hierarchy() -> None:
    """Plant the edge first, then let the foreign tenant onboard the id."""
    edge = client.post(
        "/graph/edges",
        json={
            "actor": "data-admin",
            "edge_type": "broader",
            "source_id": "고객",
            "target_id": PLANTED_ID,
        },
    )
    assert edge.status_code == 200, edge.text[:200]

    schema = client.get("/browse/crm-customer-master/schema?user=admin").json()["schema"]
    base = client.get("/catalog/datasets/crm-customer-master?user=admin").json()
    created = client.post(
        "/catalog/datasets",
        json={
            "actor": "admin",
            "id": PLANTED_ID,
            "tenant_id": FOREIGN_TENANT,
            "title": "제타 비공개 데이터셋",
            "description": "다른 테넌트만 볼 수 있어야 하는 데이터셋입니다",
            "domain": base.get("domain", "고객"),
            "owner": "owner@example.com",
            "steward": "steward@example.com",
            "update_frequency": "daily",
            "quality_score": 0.9,
            "freshness_score": 0.9,
            "source_system": "warehouse/zeta_private",
            "sensitivity": "high",
            "terms": ["고객"],
            "schema": schema,
            "distributions": base.get("distributions") or [],
        },
    )
    assert created.status_code == 200, created.text[:200]


def _summary(query: str = "") -> dict:
    response = client.get(f"/enterprise/shacl-validation{query}")
    assert response.status_code == 200, response.text[:200]
    return response.json()


def test_the_anonymous_payload_names_no_dataset_the_caller_cannot_reach() -> None:
    """The general property, derived from the catalog rather than from one id.

    Every dataset id in the catalog is checked against the whole serialized
    anonymous payload. A second leak through a different key fails here too.
    """
    _seed_foreign_dataset_reachable_only_through_the_hierarchy()
    rendered = json.dumps(_summary(), ensure_ascii=False)
    leaked = sorted(
        dataset.id for dataset in list_datasets() if dataset.id in rendered
    )
    assert not leaked, f"anonymous payload names dataset ids: {leaked}"


def test_the_owning_tenant_still_sees_the_identifier() -> None:
    """The redaction is scope-based, not a blanket removal."""
    _seed_foreign_dataset_reachable_only_through_the_hierarchy()
    # ``admin`` holds platform-admin, which is the explicit unscoped crossing.
    rendered = json.dumps(_summary("?user=admin"), ensure_ascii=False)
    assert PLANTED_ID in rendered, "a scoped caller lost the identifier it may see"


def test_a_concept_endpoint_stays_visible_to_anyone() -> None:
    """The exemption's true half: shared vocabulary is not tenant-owned."""
    hierarchy = _summary()["hierarchy_class_separation"]
    rendered = json.dumps(hierarchy, ensure_ascii=False)
    assert "매출 성장" in rendered, rendered[:400]
    assert "매출 채널별 집계" in rendered, rendered[:400]


def test_the_violation_is_still_reported_and_its_withholding_declared() -> None:
    """A redacted identifier must not turn into a vanished finding."""
    before = _summary()["hierarchy_class_separation"]
    _seed_foreign_dataset_reachable_only_through_the_hierarchy()
    after = _summary()["hierarchy_class_separation"]

    violations_before = [v for v in before["violations"] if v["severity"] == "violation"]
    violations_after = [v for v in after["violations"] if v["severity"] == "violation"]
    assert len(violations_after) == len(violations_before) + 1, (
        violations_before,
        violations_after,
    )
    assert after["conforms"] is False, after
    assert after.get("withheld_identifier_count", 0) >= 1, after


def test_the_counts_are_the_same_for_every_caller() -> None:
    """Procurement's number must not depend on who asked."""
    _seed_foreign_dataset_reachable_only_through_the_hierarchy()
    anonymous = _summary()["hierarchy_class_separation"]
    scoped = _summary("?user=admin")["hierarchy_class_separation"]
    for key in ("conforms", "unknown_endpoint_count"):
        assert anonymous[key] == scoped[key], (key, anonymous[key], scoped[key])
    assert len(anonymous["violations"]) == len(scoped["violations"])
    assert scoped.get("withheld_identifier_count", 0) == 0, scoped
