"""A published description must not name a rule the engine does not have.

Two measured cases, both in ``sdp.api_request_contract``:

1. ``POST /policy/decision``'s ``action`` read "평가할 동작(`search`·`read`·
   `create`·`publish` 등)". ``read`` is not an action this engine evaluates.
   Measured against the live route as ``analyst`` on a seeded dataset::

       search     allow  카탈로그 발견 정책 통과
       read       deny   평가할 수 없는 action입니다.      <- the documented example
       create     deny   create 작업은 admin 권한만 가능
       publish    deny   catalog mutation 작업은 admin 권한만 가능
       preview    allow  거버넌스 정책 조건 충족
       query      allow  거버넌스 정책 조건 충족
       nonsense   deny   평가할 수 없는 action입니다.      <- identical to `read`

   So the example a reader is most likely to try first behaved exactly like a
   nonsense string, and the refusal said nothing about the document being
   wrong.

2. ``POST /browse/{dataset_id}/preview``'s ``limit`` read "돌려줄 행 수의 상한.
   정책이 더 낮은 상한을 요구하면 그쪽이 적용됩니다." - the policy cap only. The
   code has a fixed ceiling of 100 and *raises* above it, so a client following
   the document and sending ``limit: 500`` met a 400 the document never
   mentioned.

Both descriptions are now built from the code's own values, and these guards
assert the relationship rather than the text: every action the description
names is evaluable, and the published bounds are the constants the code
enforces.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sdp.api import app  # noqa: E402
from sdp.api_request_contract import REQUEST_BODY_EXTRA_PROPERTIES  # noqa: E402
from sdp.browse import MAX_PREVIEW_ROWS, MIN_PREVIEW_ROWS  # noqa: E402
from sdp.policy import CATALOG_ACTION_ALIASES, KNOWN_ACTIONS  # noqa: E402

client = TestClient(app)

ACTION = REQUEST_BODY_EXTRA_PROPERTIES[("POST", "/policy/decision")]["action"]
LIMIT = REQUEST_BODY_EXTRA_PROPERTIES[("POST", "/browse/{dataset_id}/preview")]["limit"]

EVALUABLE = KNOWN_ACTIONS | set(CATALOG_ACTION_ALIASES)


# Words the sentence legitimately backticks that are not values a caller sends:
# the effect it answers with, and the obligations key carrying the evaluable
# set. Named explicitly rather than filtered by a pattern, so adding a third
# one is a deliberate edit to this list and not a silent widening.
NOT_OFFERED_VALUES = frozenset({"deny", "known_actions"})


def _backticked(text: str) -> list[str]:
    """Every `token` the description offers as a value a caller may send."""
    return [
        token
        for token in re.findall(r"`([a-z_]+)`", text)
        if token not in NOT_OFFERED_VALUES
    ]


def test_every_action_the_description_names_is_evaluable() -> None:
    """The defect: ``read`` was offered and is refused as unevaluable."""
    offered = _backticked(ACTION["description"])
    assert offered, ACTION["description"]
    unevaluable = sorted(set(offered) - EVALUABLE)
    assert not unevaluable, (
        "the published description offers actions this engine refuses as "
        f"unevaluable: {unevaluable}"
    )


def test_the_offered_actions_really_are_evaluated_by_the_live_route() -> None:
    """Asserted against the route, not against the set the description came from.

    Deriving the description from ``KNOWN_ACTIONS`` makes the two agree by
    construction, which is worth nothing if ``KNOWN_ACTIONS`` itself disagrees
    with the engine. So every offered action is sent, and none may come back
    with the unevaluable reason.
    """
    for action in sorted(EVALUABLE):
        response = client.post(
            "/policy/decision",
            json={
                "user": "analyst",
                "subject": "analyst",
                "resource": "crm-customer-master",
                "action": action,
                "purpose": "analysis",
            },
        )
        assert response.status_code == 200, (action, response.text)
        assert "평가할 수 없는 action" not in response.json()["reason"], action


def test_an_unoffered_action_is_still_refused_with_the_known_set() -> None:
    """The other half: the enum is a claim about what is refused, too."""
    response = client.post(
        "/policy/decision",
        json={
            "user": "analyst",
            "subject": "analyst",
            "resource": "crm-customer-master",
            "action": "read",
            "purpose": "analysis",
        },
    )
    body = response.json()
    assert body["effect"] == "deny"
    assert "평가할 수 없는 action" in body["reason"]
    assert sorted(body["obligations"]["known_actions"]) == sorted(KNOWN_ACTIONS)
    assert "read" not in ACTION["enum"], ACTION["enum"]


def test_the_published_preview_bounds_are_the_ones_the_code_enforces() -> None:
    """The defect: the fixed ceiling was in the code and in no document."""
    assert LIMIT["minimum"] == MIN_PREVIEW_ROWS
    assert LIMIT["maximum"] == MAX_PREVIEW_ROWS
    assert str(MAX_PREVIEW_ROWS) in LIMIT["description"], LIMIT["description"]


@pytest.mark.parametrize(
    ("limit", "expected"),
    [
        (MIN_PREVIEW_ROWS, 200),
        (MAX_PREVIEW_ROWS, 200),
        (MAX_PREVIEW_ROWS + 1, 400),
        (MIN_PREVIEW_ROWS - 1, 400),
    ],
    ids=["at_minimum", "at_maximum", "over_maximum", "under_minimum"],
)
def test_the_route_enforces_exactly_the_published_bounds(limit: int, expected: int) -> None:
    """Both boundaries, so the published numbers are the real ones."""
    response = client.post(
        "/browse/crm-customer-master/preview",
        json={"user": "admin", "purpose": "analysis", "limit": limit},
    )
    assert response.status_code == expected, (limit, response.status_code, response.text)


OFFSET = REQUEST_BODY_EXTRA_PROPERTIES[("POST", "/browse/{dataset_id}/preview")]["offset"]


@pytest.mark.parametrize(("offset", "expected"), [(0, 200), (1, 200), (-1, 400)])
def test_the_published_offset_floor_is_the_one_the_route_enforces(
    offset: int, expected: int
) -> None:
    """Removing the ceiling clamp also removed ``max(offset, 0)``, so this is published.

    A negative offset used to answer 200 from the top of the page: the caller
    got a page it did not ask for and nothing said so. Refusing it is the same
    choice as the ceiling, and a refusal the document does not mention is the
    defect this file is about - so it is published in the same change.
    """
    assert OFFSET["minimum"] == 0, OFFSET
    response = client.post(
        "/browse/crm-customer-master/preview",
        json={"user": "admin", "purpose": "analysis", "offset": offset},
    )
    assert response.status_code == expected, (offset, response.status_code, response.text)


def test_the_refusal_over_the_ceiling_names_the_ceiling() -> None:
    """A client that followed the old description needs to know what it hit."""
    response = client.post(
        "/browse/crm-customer-master/preview",
        json={"user": "admin", "purpose": "analysis", "limit": MAX_PREVIEW_ROWS * 5},
    )
    assert response.status_code == 400
    assert str(MAX_PREVIEW_ROWS) in str(response.json()), response.json()
