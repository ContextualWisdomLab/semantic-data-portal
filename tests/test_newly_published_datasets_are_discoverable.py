"""A published dataset was invisible to two discovery routes that claimed none was.

``ontology._INDEX`` was built once at import, so a dataset registered and
published afterwards never entered the concept-to-dataset map. Measured at
``dba2403`` after onboarding ``mkt_campaign_touchpoint`` (terms ``["고객",
"캠페인"]``, one approved mapping to 고객) as ``user=data-admin``::

    GET  /catalog/search?q=고객      -> 6 ids, including the new one
    GET  /ontology/term/고객/graph   -> 5 ids, including the new one
    GET  /ontology/concept/고객      -> 4 ids, WITHOUT it, withheld_dataset_count: 0
    POST /llm/search {고객}          -> 4 ids, WITHOUT it, withheld_dataset_count: 0

``withheld_dataset_count`` is the field ``README.md`` introduces so that "a short
list does not read as the whole mapping", and here the short list read as the
whole mapping: the owner has no signal to retry, escalate or distrust the answer,
and two routes the README calls siblings serving the same fact disagree.

The root cause was recorded as a *scope* note - ONT-004 says the map "is built
once at import and no registration updates it", and the vocabulary export
publishes ``sdp:datasetMappingIsVersioned false``. That the map is outside the
**versioned** scope stays true after this repair; what was never recorded is that
a response therefore asserted full coverage while a mapped dataset was missing.

The repair is to derive the map where it is read instead of snapshotting it at
import. Measured cost: rebuilding is 3.7 ms per 2000 calls against
``resolve_terms``'s own 148.9 ms for the same 2000 - 2.5%, on a map of 10 keys
over 5 datasets - so there is no cache to keep coherent and no new module state
for ``tests/conftest.py`` to restore.
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from sdp import ontology
from sdp.api import app


client = TestClient(app)

DATASET_ID = "discovery-probe-touchpoint"
CONCEPT = "고객"


def _onboard() -> None:
    """Register and publish one dataset declaring an existing concept as a term."""
    body: dict[str, Any] = {
        "id": DATASET_ID,
        "tenant_id": "demo",
        "title": "캠페인 접점 프로브",
        "description": "온보딩 후 발견 가능성을 측정하는 프로브 데이터셋",
        "owner": "data-admin",
        "steward": "data-admin",
        "domain": "마케팅",
        "source_system": "s3://analytics/events/touchpoints",
        "sensitivity": "low",
        "update_frequency": "daily",
        "quality_score": 0.9,
        "freshness_score": 0.9,
        "tags": ["마케팅"],
        "terms": [CONCEPT, "캠페인"],
        "schema": [
            {"name": "customer_id", "datatype": "string", "nullable_ratio": 0.0, "distinct_ratio": 1.0}
        ],
        "distributions": [
            {"id": f"{DATASET_ID}-csv", "format": "csv", "endpoint": "https://files.example.internal/t.csv"}
        ],
        "actor": "data-admin",
        "reason": "probe",
    }
    created = client.post("/catalog/datasets", json=body)
    assert created.status_code == 200, created.text
    published = client.post(
        f"/catalog/datasets/{DATASET_ID}/publish", json={"actor": "data-admin", "reason": "probe"}
    )
    assert published.status_code == 200, published.text


def _concept_ids() -> tuple[list[str], int]:
    body = client.get(f"/ontology/concept/{CONCEPT}?user=data-admin").json()
    return body["dataset_ids"], body["withheld_dataset_count"]


def _llm_search_ids() -> tuple[list[str], int]:
    body = client.post(
        "/llm/search",
        json={"user": "data-admin", "question": f"{CONCEPT} 데이터셋을 찾아줘", "purpose": "analysis"},
    ).json()
    return (
        body["recommendations"]["dataset_ids"],
        body["recommendations"]["withheld_dataset_count"],
    )


def test_the_catalog_sees_it_immediately() -> None:
    """The premise: the dataset is registered, published and visible somewhere."""
    _onboard()
    found = client.get(f"/catalog/search?q={CONCEPT}&user=data-admin").json()
    ids = [row["dataset"]["id"] if "dataset" in row else row["id"] for row in found["items"]]
    assert DATASET_ID in ids, ids


def test_the_concept_route_sees_a_dataset_that_declares_the_term() -> None:
    """The owner's documented "which datasets carry this term" entry point."""
    _onboard()
    ids, withheld = _concept_ids()
    assert DATASET_ID in ids, (ids, withheld)


def test_the_natural_language_route_sees_it_too() -> None:
    """The second entry point, which shared the same frozen map."""
    _onboard()
    ids, withheld = _llm_search_ids()
    assert DATASET_ID in ids, (ids, withheld)


def test_the_two_sibling_routes_agree_about_the_same_concept() -> None:
    """README calls them siblings serving the same fact; they returned 4 and 5."""
    _onboard()
    graph = client.get(f"/ontology/term/{CONCEPT}/graph?user=data-admin").json()
    graph_ids = set(graph["dataset_ids"])
    concept_ids = set(_concept_ids()[0])
    assert concept_ids == graph_ids, (sorted(concept_ids), sorted(graph_ids))


def test_a_zero_withheld_count_means_nothing_was_withheld() -> None:
    """The honesty half, which has to hold whatever the map does.

    If a mapped dataset is ever missing from the answer again, the count must not
    read zero - that is what made the first defect unreportable by its own
    surface.
    """
    _onboard()
    for ids, withheld in (_concept_ids(), _llm_search_ids()):
        if DATASET_ID not in ids:
            assert withheld > 0, (
                "a dataset that declares this term is missing from the answer while "
                f"the response claims nothing was withheld: {ids} withheld={withheld}"
            )


def test_the_concept_to_dataset_map_is_derived_not_snapshotted() -> None:
    """Structural: an import-time snapshot is the defect, not an implementation detail."""
    assert not hasattr(ontology, "_INDEX"), (
        "the concept-to-dataset map is a module-level snapshot again; it goes stale "
        "the moment a dataset is registered, and `tests/conftest.py` then has to "
        "restore it as state"
    )
    # Not only that one name: both readers must call the deriving function. A
    # mutation that reintroduced the snapshot under a *different* name passed the
    # attribute check above and was caught only by the repository's generic
    # module-state guard, which is luck rather than this file doing its job.
    import inspect

    for reader in (ontology.resolve_terms, ontology.concept_assets):
        body = inspect.getsource(reader).split('"""')[-1]
        assert "concept_dataset_index()" in body, (reader.__name__, body[:400])
    index = ontology.concept_dataset_index()
    assert isinstance(index, dict) and index, index
    # Derived means a new dataset shows up without anything being told.
    before = set(ontology.concept_dataset_index().get(CONCEPT, []))
    _onboard()
    after = set(ontology.concept_dataset_index().get(CONCEPT, []))
    assert after - before == {DATASET_ID}, (sorted(before), sorted(after))
