"""An invalid-pagination refusal must still be a governed, recorded refusal.

``4d9e3d3`` stopped ``POST /browse/{id}/preview`` clamping ``limit``/``offset``,
because the clamp silently rewrote the caller's request: ``limit: 500``
answered 200 with a hundred rows and said nothing. That reasoning stands. What
it did not measure is the consequence: the clamp had made ``browse.preview``'s
own bound checks unreachable over HTTP, and those checks sit **above** the
dataset lookup and the policy call. Passing the values through made them
reachable, so a refusal path appeared that returns before any policy evaluation
and files no evidence.

Measured on the branch before this file:

    caller                     limit   status   audit   decisions
    admin (authorised)         9999      400      +0        +0
    anonymous (denied)         9999      400      +0        +0
    anonymous, absent dataset  9999      400      +0        +0

An unauthenticated caller made the portal answer and left no trace, on the
policy-gated data-access surface, in a product whose claim is the evidence
trail. CLAUDE.md states the invariant directly: a change that omits policy
evaluation and evidence recording on the browse/query path is a regression.

The repair is not the clamp. It is the order: resolve the dataset, evaluate
policy, and only then check the bounds - with the refusal recorded like every
other refusal. A caller who may not read the dataset is told so, and never
learns what this route thinks of its pagination.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from sdp import browse, catalog, evidence
from sdp.api import app

client = TestClient(app)

_DATASET = "crm-customer-master"
OUT_OF_RANGE = [
    {"limit": browse.MAX_PREVIEW_ROWS + 1},
    {"limit": browse.MIN_PREVIEW_ROWS - 1},
    {"offset": -5},
]


# No warm-up fixture, and no count deltas. The first version had both: the
# first request through ``TestClient(app)`` runs the startup hook, whose own
# ingest satisfied a count-delta assertion the request under test had not
# earned - the authorised ``limit: 101`` case passed while its two siblings
# failed, for that reason alone. A module-scoped warm-up fixed that and broke
# something worse: it runs *outside* conftest's per-test
# ``restore_in_memory_app_state`` window, so its rows survived into the next
# test and ``tests/test_state_isolation.py`` caught the leak. Matching the row
# this request produced needs neither.


def _decision_rows_for(subject: str, resource: str) -> list[object]:
    """Policy decisions this subject's preview of ``resource`` produced."""
    return [
        decision
        for decision in evidence._POLICY_DECISION_LOG
        if decision.subject == subject
        and decision.resource == resource
        and decision.action == "preview"
    ]


def _refusal_rows_for(actor: str, dataset_id: str) -> list[object]:
    """Audit rows this actor's refused preview of ``dataset_id`` produced."""
    return [
        event
        for event in catalog._AUDIT_LOG
        if event.action == "browse.preview"
        and event.actor == actor
        # ``AuditEvent`` names the subject ``resource``, not ``dataset_id``.
        # The first version of this helper used the latter and every assertion
        # died with ``AttributeError`` - which is not a measurement, it is a
        # guard that never ran.
        and event.resource == dataset_id
        and event.result == "denied"
    ]


@pytest.mark.parametrize("pagination", OUT_OF_RANGE)
def test_an_authorised_caller_s_bad_pagination_is_refused_and_recorded(pagination) -> None:
    """Still a 400 - and now a row."""
    rows_before = len(_refusal_rows_for("admin", _DATASET))
    decisions_before = len(_decision_rows_for("admin", _DATASET))
    response = client.post(
        f"/browse/{_DATASET}/preview",
        json={"user": "admin", "purpose": "analysis", **pagination},
    )
    assert response.status_code == 400, response.text
    assert len(_refusal_rows_for("admin", _DATASET)) > rows_before, (
        "the refusal filed no browse.preview denial row"
    )
    assert len(_decision_rows_for("admin", _DATASET)) > decisions_before, (
        "the refusal filed no policy decision"
    )


@pytest.mark.parametrize("pagination", OUT_OF_RANGE)
def test_an_unauthorised_caller_never_reaches_the_bound_check(pagination) -> None:
    """Deny first: the answer is the authorisation answer, not the shape answer.

    The same caller with valid pagination is answered 404 (an unreadable
    dataset is hidden), so answering 400 for invalid pagination would tell them
    the route processed their input and would hand them a distinguisher the 404
    collapse exists to deny.
    """
    body = {"user": "anonymous", "purpose": "external-export"}
    control = client.post(f"/browse/{_DATASET}/preview", json={**body, "limit": 2})
    assert control.status_code in {403, 404}, control.text

    rows_before = len(_refusal_rows_for("anonymous", _DATASET))
    decisions_before = len(_decision_rows_for("anonymous", _DATASET))
    measured = client.post(f"/browse/{_DATASET}/preview", json={**body, **pagination})
    assert measured.status_code == control.status_code, (
        f"pagination changed the refusal for a caller who may not read this "
        f"dataset: {measured.status_code} vs {control.status_code}"
    )
    assert len(_refusal_rows_for("anonymous", _DATASET)) > rows_before, (
        "the refusal filed no browse.preview denial row"
    )
    assert len(_decision_rows_for("anonymous", _DATASET)) > decisions_before, (
        "the refusal filed no policy decision"
    )


@pytest.mark.parametrize("pagination", OUT_OF_RANGE)
def test_an_absent_dataset_answers_as_absent_whatever_the_pagination(pagination) -> None:
    """The absent-id refusal keeps its own shape and its own evidence row."""
    rows_before = len(_refusal_rows_for("anonymous", "no-such-dataset-xyz"))
    response = client.post(
        "/browse/no-such-dataset-xyz/preview",
        json={"user": "anonymous", "purpose": "external-export", **pagination},
    )
    assert response.status_code == 404, response.text
    assert len(_refusal_rows_for("anonymous", "no-such-dataset-xyz")) > rows_before, (
        "the absent-id refusal filed no browse.preview denial row"
    )


def test_the_bounds_still_refuse_rather_than_rewrite() -> None:
    """The reason the clamp was removed must survive the repair.

    ``browse.preview`` is still called directly by tests and by the module
    layer, and out-of-range values must raise there too - the governance is in
    the route's ordering, not in a looser contract.
    """
    for pagination in OUT_OF_RANGE:
        with pytest.raises(ValueError):
            browse.preview(_DATASET, user="admin", purpose="analysis", **pagination)
