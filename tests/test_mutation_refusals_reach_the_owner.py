"""A refused mutation on a real dataset must stay visible to its owner.

The governance invariant has two halves - a policy decision and an audit event.
``_refuse_mutation_on_unreachable_dataset`` audits only its 404 branch; the 403
branch (a caller with no accessible tenant scope) raises after filing a decision
against the resource ``catalog`` and files no audit event. That was harmless
while the three verbs audited *after* evaluating, which they no longer do: they
call this helper first, so the post-evaluation audit never runs.

The helper's own docstring states the 403 reasoning - "has already filed its row
against the resource ``catalog``, which carries no information about the id" -
and that is true about **the caller's** side. It does not cover the owner's: a
decision row against ``catalog`` tells the owning tenant's auditor nothing about
an attempt on *its* dataset.

Measured at the head before this file, as ``anonymous`` against a real dataset::

    publish    -> 403  total audit +0  decision +2
    patch      -> 403  total audit +0  decision +2
    deprecate  -> 403  total audit +0  decision +2
    GET /catalog/datasets/{id}/audit as admin, rows naming 'anonymous': 0 -> 0

``POST /catalog/datasets`` - the one mutation verb that was not reordered -
still records both halves for the same caller, which is what makes this an
asymmetry introduced by the reordering rather than a standing design.

The repair files the same pair the 404 branch files, through
``evaluate_dataset_scope_refusal``, which lands in the owning tenant's scope or
the reserved ``unresolved`` scope. So the owner sees the attempt and the caller
still cannot tell a taken id from a free one - the 403 fires before existence is
known, and both cases file one row.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from sdp import catalog, evidence
from sdp.api import app

client = TestClient(app)

_DATASET = "crm-customer-master"
_ABSENT = "no-such-dataset-for-mutation-probe"
_SCOPELESS = "anonymous"

VERBS = [
    ("publish", lambda ds, actor: client.post(f"/catalog/datasets/{ds}/publish", json={"actor": actor})),
    ("patch", lambda ds, actor: client.patch(f"/catalog/datasets/{ds}", json={"actor": actor, "title": "t"})),
    ("deprecate", lambda ds, actor: client.post(f"/catalog/datasets/{ds}/deprecate", json={"actor": actor})),
]


def _owner_visible_rows(dataset_id: str, actor: str) -> int:
    """Rows naming ``actor`` that the dataset's owner can read."""
    response = client.get(f"/catalog/datasets/{dataset_id}/audit", params={"user": "admin"})
    if response.status_code != 200:
        return -1
    body = response.json()
    rows = body if isinstance(body, list) else body.get("items", body.get("events", []))
    return sum(1 for row in rows if row.get("actor") == actor)


@pytest.mark.parametrize("verb,call", VERBS, ids=[v for v, _ in VERBS])
def test_a_scopeless_mutation_attempt_is_audited(verb: str, call) -> None:
    """Both halves, not just the decision."""
    audit_before = len(catalog._AUDIT_LOG)
    decisions_before = len(evidence._POLICY_DECISION_LOG)
    response = call(_DATASET, _SCOPELESS)
    assert response.status_code == 403, response.text
    assert len(evidence._POLICY_DECISION_LOG) > decisions_before, "no policy decision filed"
    assert len(catalog._AUDIT_LOG) > audit_before, (
        f"{verb} on a real dataset by a scopeless caller filed no audit event"
    )


@pytest.mark.parametrize("verb,call", VERBS, ids=[v for v, _ in VERBS])
def test_the_owning_tenant_sees_the_refused_attempt(verb: str, call) -> None:
    """The half that matters to the owner, read through the owner's own route."""
    before = _owner_visible_rows(_DATASET, _SCOPELESS)
    assert before >= 0, "the owner's audit route is unreadable; the premise is gone"
    response = call(_DATASET, _SCOPELESS)
    assert response.status_code == 403, response.text
    after = _owner_visible_rows(_DATASET, _SCOPELESS)
    assert after > before, (
        f"the owner cannot see the refused {verb} attempt on its own dataset: "
        f"{before} -> {after}"
    )


@pytest.mark.parametrize("verb,call", VERBS, ids=[v for v, _ in VERBS])
def test_auditing_the_refusal_does_not_tell_the_caller_whether_the_id_is_free(
    verb: str, call
) -> None:
    """Filing a row must not become the leak it prevents.

    The 403 fires before existence is known, so both ids must produce the same
    HTTP answer and the same number of rows.
    """
    audit_before = len(catalog._AUDIT_LOG)
    taken = call(_DATASET, _SCOPELESS)
    taken_rows = len(catalog._AUDIT_LOG) - audit_before

    audit_before = len(catalog._AUDIT_LOG)
    free = call(_ABSENT, _SCOPELESS)
    free_rows = len(catalog._AUDIT_LOG) - audit_before

    assert taken.status_code == free.status_code, (taken.status_code, free.status_code)
    assert taken_rows == free_rows, (
        f"{verb} files {taken_rows} rows for a taken id and {free_rows} for a free "
        "one, so the row count answers what the status code refuses"
    )
