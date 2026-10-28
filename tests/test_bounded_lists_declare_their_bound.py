"""Two lists were bounded without saying so, and a row the product accepted
became unreachable.

``GET /catalog/search`` was repaired for exactly this - a page published as the
answer - and ``GET /ontology/change-log`` publishes the same disclosure for an
evicting store. Two surfaces were left behind.

**``GET /catalog/datasets/{dataset_id}/join-candidates``.** Measured against a
tenant holding 124 scoring candidates for ``crm-customer-master``::

    GET .../join-candidates?limit=100   200  rows=100
    body keys                                ['dataset_id', 'join_candidates']
    count / total / withheld / truncated     none of them
    rows reachable over every legal limit    100 of 124
    rows reachable by no request at all      24   (join-filler-0098 ...)

``limit`` is capped at 100 and there is no ``offset``, so candidate 101 is
reachable by no request this API accepts, and the body says nothing about the
other 24 - a buyer reading it sees a complete recommendation list. Worse, the
obvious attempt to page answers 200: ``?offset=100`` is not a declared
parameter, so FastAPI drops it and serves the **first** page again, which is a
silent wrong answer rather than a refusal.

**The ontology proposal queue.** ``propose_patch`` evicts the oldest proposal at
``MAX_ONTOLOGY_PATCHES`` rather than refusing new ones - a deliberate choice,
so the queue cannot be filled to lock out legitimate proposals - but nothing
anywhere declared it. Measured, proposing one patch and then 502 more::

    POST /ontology/patches             200  id=645a69fd-...
    GET  /ontology/patches             200  count=500
    body keys        ['count', 'patches', 'policy_decision_id', 'scope_note']
    first id listed?                        False
    POST /ontology/patches/<that id>/review 404  'patch not found'

So the product accepted a proposal with 200 and an id, then answered 404 to the
only route that can act on it, while the queue reported ``count: 500`` as if
that were the whole queue. Its named sibling store, at the same moment, was
already publishing ``change_log_entry_count``, ``withheld_change_count`` and
``change_log_is_truncated``.

The repair gives both surfaces the vocabulary ``/catalog/search`` and
``/ontology/change-log`` already use: the page length in ``count``, an exact
total, the withheld remainder and a truncation flag - plus ``offset`` on the
join route, because a row no request can reach is not a disclosure problem.
"""

from fastapi.testclient import TestClient

from sdp import catalog, ontology
from sdp.api import app

client = TestClient(app)

_CRM = "crm-customer-master"


def _publish_filler(index: int) -> str:
    """Register and publish one dataset that scores against ``_CRM``."""
    dataset_id = f"join-bound-{index:04d}"
    created = client.post(
        "/catalog/datasets",
        json={
            "actor": "admin",
            "id": dataset_id,
            "title": f"조인 후보 경계 측정 {index}",
            "description": "join-candidates 절단 공표 측정용 데이터셋",
            "owner": "data-platform",
            "steward": "qa",
            "domain": "테스트",
            "source_system": f"postgresql://analytics.dw/bound_{index}",
            "sensitivity": "low",
            "update_frequency": "daily",
            "quality_score": 0.9,
            "freshness_score": 0.9,
            "tags": ["테스트"],
            "terms": ["고객"],
            "related_datasets": [],
            "schema": [
                {
                    "name": "customer_id",
                    "datatype": "string",
                    "nullable_ratio": 0.0,
                    "distinct_ratio": 1.0,
                    "pii": False,
                }
            ],
            "distributions": [
                {
                    "id": f"dist-bound-{index}",
                    "format": "postgresql.table",
                    "endpoint": f"https://example.internal/api/table/bound_{index}",
                }
            ],
            "mappings": [],
            "profile": {},
        },
    )
    assert created.status_code == 200, created.text
    published = client.post(
        f"/catalog/datasets/{dataset_id}/publish", json={"actor": "admin"}
    )
    assert published.status_code == 200, published.text
    return dataset_id


def test_the_join_candidate_page_declares_what_it_left_out() -> None:
    """The page length, the exact total, the remainder and the flag."""
    for index in range(120):
        _publish_filler(index)

    response = client.get(
        f"/catalog/datasets/{_CRM}/join-candidates",
        params={"user": "admin", "limit": 100},
    )
    assert response.status_code == 200, response.text
    body = response.json()

    total = catalog.get_join_candidate_page(
        _CRM, limit=10**6, tenant_ids=None
    ).total_candidate_count
    assert total > 100, "the fixture must exceed one page for this to measure anything"

    assert body["count"] == len(body["join_candidates"]) == 100
    assert body["total_candidate_count"] == total
    assert body["withheld_candidate_count"] == total - 100
    assert body["candidate_list_is_truncated"] is True


def test_every_join_candidate_is_reachable_by_some_request() -> None:
    """``offset`` exists because a row no request can reach is not a disclosure
    problem. Before it, 24 of 124 candidates were reachable by nothing."""
    for index in range(120):
        _publish_filler(index)

    total = catalog.get_join_candidate_page(
        _CRM, limit=10**6, tenant_ids=None
    ).total_candidate_count
    assert total > 100

    reached: set[str] = set()
    offset = 0
    while offset < total:
        page = client.get(
            f"/catalog/datasets/{_CRM}/join-candidates",
            params={"user": "admin", "limit": 100, "offset": offset},
        )
        assert page.status_code == 200, page.text
        rows = page.json()["join_candidates"]
        assert rows, f"offset={offset} returned nothing while {total} candidates exist"
        reached.update(row["dataset_id"] for row in rows)
        offset += 100

    assert len(reached) == total


def test_the_published_numbers_agree_on_every_reachable_page() -> None:
    """The four numbers mean one thing together, so assert the thing.

    An adversarial review of the first version of this file found the gap this
    test closes. Every published-number assertion here was taken either at
    ``offset=0`` or at ``offset=10_000`` against the **seeded** fixture - and the
    seeded total is 4, so ``total - limit`` clamps to zero and the exhausted-page
    test was vacuous against the mutation that matters. Measured: replacing

        withheld = max(page.total_candidate_count - offset - len(page.items), 0)
    with
        withheld = max(page.total_candidate_count - limit, 0)

    left 444 tests across 18 files green, because at ``offset=0`` the two are
    algebraically identical. The mutant then published, over 124 candidates at
    ``limit=100``: ``offset=50 -> count=74 withheld=24 truncated=True``, so
    ``offset + count + withheld = 148`` against its own ``total`` of 124, and
    ``offset=150 -> count=0 withheld=24 truncated=True`` - an empty page claiming
    24 recommendations were held back after every one had been delivered.

    So the assertion is the identity, not the sample: of the candidates the
    caller has skipped past, received, and not yet received, the three must
    account for the whole match exactly once. ``min(offset, total)`` is what
    makes it hold past the end, where a caller can skip past rows that do not
    exist.
    """
    for index in range(120):
        _publish_filler(index)

    total = catalog.get_join_candidate_page(
        _CRM, limit=10**6, tenant_ids=None
    ).total_candidate_count
    assert total > 100, "the fixture must exceed one page for this to measure anything"

    seen_a_truncated_page = False
    seen_an_untruncated_page = False
    for offset in (0, 50, 100, total, total + 26):
        page = client.get(
            f"/catalog/datasets/{_CRM}/join-candidates",
            params={"user": "admin", "limit": 100, "offset": offset},
        )
        assert page.status_code == 200, page.text
        body = page.json()
        assert body["count"] == len(body["join_candidates"]), offset
        assert body["total_candidate_count"] == total, offset
        assert (
            min(offset, total) + body["count"] + body["withheld_candidate_count"] == total
        ), (offset, body["count"], body["withheld_candidate_count"], total)
        assert body["candidate_list_is_truncated"] is (
            body["withheld_candidate_count"] > 0
        ), offset
        seen_a_truncated_page |= body["candidate_list_is_truncated"]
        seen_an_untruncated_page |= not body["candidate_list_is_truncated"]

    # Both sides of the flag were exercised, so neither constant passes this.
    assert seen_a_truncated_page and seen_an_untruncated_page


def test_a_negative_join_candidate_offset_is_refused() -> None:
    """The bound its two named siblings already carry.

    ``tests/test_evidence_rows_stay_reachable.py`` and
    ``tests/test_catalog_search_declares_its_truncation.py`` each assert this for
    their own ``offset``; nothing asserted it here. Before the parameter existed
    ``?offset=-1`` answered **200 with the whole first page**, because an
    undeclared parameter is dropped rather than refused - the same silent wrong
    answer ``?offset=100`` gave, which is why the parameter was added.
    """
    refused = client.get(
        f"/catalog/datasets/{_CRM}/join-candidates",
        params={"user": "admin", "offset": -1},
    )
    assert refused.status_code == 422, refused.text


def test_an_exhausted_join_candidate_page_is_empty_and_says_so() -> None:
    """Past the end the page is empty, the total still stands, and nothing is
    withheld - the two numbers cannot disagree about the same request."""
    response = client.get(
        f"/catalog/datasets/{_CRM}/join-candidates",
        params={"user": "admin", "limit": 100, "offset": 10_000},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["count"] == 0
    assert body["join_candidates"] == []
    assert body["withheld_candidate_count"] == 0
    assert body["candidate_list_is_truncated"] is False
    assert body["total_candidate_count"] == catalog.get_join_candidate_page(
        _CRM, limit=10**6, tenant_ids=None
    ).total_candidate_count


def test_an_untruncated_join_candidate_page_says_nothing_was_withheld() -> None:
    """The flag is derived, not a constant: the seeded catalog fits in one page."""
    response = client.get(
        f"/catalog/datasets/{_CRM}/join-candidates",
        params={"user": "admin", "limit": 100},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["withheld_candidate_count"] == 0
    assert body["candidate_list_is_truncated"] is False
    assert body["count"] == body["total_candidate_count"]


def test_the_proposal_queue_declares_the_proposals_it_evicted() -> None:
    """The queue's own disclosure, in the vocabulary its named sibling uses."""
    first = client.post(
        "/ontology/patches",
        json={
            "actor": "admin",
            "concept": "경계 공표 최초 제안",
            "suggestion": "가장 먼저 대기열에 들어간 제안입니다.",
        },
    )
    assert first.status_code == 200, first.text
    first_id = first.json()["id"]

    empty = client.get("/ontology/patches", params={"user": "admin"})
    assert empty.status_code == 200, empty.text
    assert empty.json()["withheld_patch_count"] == 0
    assert empty.json()["patch_queue_is_truncated"] is False

    for index in range(ontology.MAX_ONTOLOGY_PATCHES + 2):
        queued = client.post(
            "/ontology/patches",
            json={
                "actor": "admin",
                "concept": f"경계 공표 제안 {index}",
                "suggestion": f"대기열 포화 측정 {index}",
            },
        )
        assert queued.status_code == 200, queued.text

    listed = client.get("/ontology/patches", params={"user": "admin"})
    assert listed.status_code == 200, listed.text
    body = listed.json()
    assert body["patch_queue_entry_count"] == ontology.MAX_ONTOLOGY_PATCHES
    assert body["withheld_patch_count"] == 3
    assert body["patch_queue_is_truncated"] is True

    # The accepted id is gone, and that is now a declared fact rather than a
    # silent one: the caller reads the withheld count beside the queue.
    assert not any(patch["id"] == first_id for patch in body["patches"])
    review = client.post(
        f"/ontology/patches/{first_id}/review",
        json={"actor": "admin", "decision": "approve", "comment": "승인"},
    )
    assert review.status_code == 404


def test_the_proposal_that_causes_the_eviction_is_told() -> None:
    """An accept that arrives at a full queue displaced an older proposal, and
    that is a fact about this write which no later read attributes to it - so
    the accept response carries the same three numbers.

    This docstring used to say the proposer "is the one party that cannot read
    the queue later and tell whether their own row survived", and the product
    refutes it: every identity that may propose gets 200 from
    ``GET /ontology/patches``, which returns the whole queue with every row's
    ``id``. The fields report aggregate loss, never own-row survival - a freshly
    appended row always survives the eviction of the oldest.
    """
    for index in range(ontology.MAX_ONTOLOGY_PATCHES - 1):
        ontology.propose_patch(
            concept=f"포화 직전 {index}", suggestion=f"s{index}", requestor="admin"
        )

    last_fitting = client.post(
        "/ontology/patches",
        json={"actor": "admin", "concept": "정확히 채우는 제안", "suggestion": "마지막 자리"},
    )
    assert last_fitting.status_code == 200, last_fitting.text
    assert last_fitting.json()["patch_queue_entry_count"] == ontology.MAX_ONTOLOGY_PATCHES
    assert last_fitting.json()["withheld_patch_count"] == 0
    assert last_fitting.json()["patch_queue_is_truncated"] is False

    overflowing = client.post(
        "/ontology/patches",
        json={"actor": "admin", "concept": "한 칸 넘기는 제안", "suggestion": "가장 오래된 것을 밀어냅니다"},
    )
    assert overflowing.status_code == 200, overflowing.text
    assert overflowing.json()["withheld_patch_count"] == 1
    assert overflowing.json()["patch_queue_is_truncated"] is True
    # The patch's own fields survive alongside the queue's.
    assert overflowing.json()["concept"] == "한 칸 넘기는 제안"
    assert overflowing.json()["status"] == "proposed"


def test_the_queue_disclosure_counts_the_queue_not_the_filtered_page() -> None:
    """``count`` is the page the filter produced; ``patch_queue_entry_count`` is
    the queue. A status filter must not make the queue look smaller than it is."""
    proposed = client.post(
        "/ontology/patches",
        json={"actor": "admin", "concept": "필터 측정 제안", "suggestion": "승인될 제안"},
    )
    assert proposed.status_code == 200, proposed.text
    approved = client.post(
        f"/ontology/patches/{proposed.json()['id']}/review",
        json={"actor": "admin", "decision": "approve", "comment": "승인"},
    )
    assert approved.status_code == 200, approved.text

    whole = client.get("/ontology/patches", params={"user": "admin"})
    only_proposed = client.get(
        "/ontology/patches", params={"user": "admin", "status": "proposed"}
    )
    assert whole.status_code == only_proposed.status_code == 200

    assert only_proposed.json()["count"] < whole.json()["count"]
    assert (
        only_proposed.json()["patch_queue_entry_count"]
        == whole.json()["patch_queue_entry_count"]
        == whole.json()["count"]
    )
