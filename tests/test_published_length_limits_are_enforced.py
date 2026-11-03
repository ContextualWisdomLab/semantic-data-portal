"""A published ``maxLength`` must be the rule, not a description of storage.

``sdp.api_request_contract`` publishes ``maxLength: 512`` on five body
properties - ``reason`` on the four catalog mutations and ``comment`` on the
ontology patch review. A client reading that document concludes that a longer
value is refused. Measured, neither was true, and they were untrue in two
different ways::

    POST /catalog/datasets/{id}/publish  {"reason": "x" * 1000}
      -> 200, audit row's details.change_reason length 512

    POST /ontology/patches/{id}/review   {"comment": "y" * 1000}
      -> 200, response's review_comment length 1000

So the reason was accepted and **silently truncated**, and the comment was
accepted and kept whole. The first is the worse of the two: the audit row a
human auditor reads then says something the caller did not write, and the
caller got a 200 that did not say so. ``_change_reason``'s own docstring calls
the value "prose for a human auditor".

Refusing is what makes the published limit true, and it is the only option that
does not either discard a caller's words or retain more than the contract
promises. The limit itself is not changed - it is published, and a published
bound a client has already coded against is not something to widen quietly.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sdp.api import MAX_CHANGE_REASON_CHARS, app  # noqa: E402
from sdp.api_request_contract import REQUEST_BODY_EXTRA_PROPERTIES  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.generate_response_contract import (  # noqa: E402
    non_demo_dataset_body,
)

client = TestClient(app)


def published_limits() -> list[tuple[str, str, str, int]]:
    """Every (method, path, field, maxLength) the request contract publishes."""
    found = []
    for (method, path), properties in REQUEST_BODY_EXTRA_PROPERTIES.items():
        for field, schema in properties.items():
            if "maxLength" in schema:
                found.append((method, path, field, int(schema["maxLength"])))
    return sorted(found)


def test_the_contract_still_publishes_the_limits_this_file_is_about() -> None:
    """The premise, derived from the document rather than restated here."""
    limits = published_limits()
    assert len(limits) == 5, limits
    assert {field for _, _, field, _ in limits} == {"reason", "comment"}
    assert {limit for *_, limit in limits} == {MAX_CHANGE_REASON_CHARS}


def _new_patch() -> str:
    """One proposed ontology patch, created the way the API creates them."""
    created = client.post(
        "/ontology/patches",
        json={"actor": "admin", "concept": "고객", "suggestion": "consumer"},
    )
    assert created.status_code == 200, created.text
    return created.json()["id"]


# One body builder per published surface. The *parametrization* is derived from
# ``published_limits()``, so this mapping can only be incomplete **loudly**: a
# published limit with no builder fails with the message below instead of being
# silently left undriven.
#
# It was a hand-written list of four callers next to a premise that asserted the
# published set has five members. ``POST /catalog/datasets``' ``reason`` was the
# one nobody sent an over-limit value to - so deleting that route's enforcement
# (``change_reason=_change_reason(payload)`` ->
# ``change_reason=(payload.get("reason") or None)``) left this file 10/10 green
# while a 513-character reason answered 200 and was stored whole. Measured.
#
# That is the same "a curated list reports green on what it never visited" shape
# the sibling ``test_refusal_evidence_is_not_an_existence_oracle.py`` was
# repaired for in this round, one file over.
_OTHER_FIELDS: dict[tuple[str, str], object] = {
    ("POST", "/catalog/datasets/{dataset_id}/publish"): lambda: (
        {"path": "/catalog/datasets/crm-customer-master/publish", "body": {"actor": "admin"}}
    ),
    ("POST", "/catalog/datasets/{dataset_id}/deprecate"): lambda: (
        {"path": "/catalog/datasets/sales-order/deprecate", "body": {"actor": "admin"}}
    ),
    ("PATCH", "/catalog/datasets/{dataset_id}"): lambda: (
        {"path": "/catalog/datasets/crm-customer-master", "body": {"actor": "admin", "description": "d"}}
    ),
    ("POST", "/ontology/patches/{patch_id}/review"): lambda: (
        {"path": f"/ontology/patches/{_new_patch()}/review",
         "body": {"actor": "admin", "decision": "approve"}}
    ),
    ("POST", "/catalog/datasets"): lambda: (
        {"path": "/catalog/datasets", "body": _onboarding_body()}
    ),
}

_ONBOARDING_SEQUENCE = [0]


def _onboarding_body() -> dict[str, object]:
    """A valid onboarding body with a fresh id, so repeated calls do not collide."""
    _ONBOARDING_SEQUENCE[0] += 1
    body = non_demo_dataset_body()
    body["id"] = f"length-limit-probe-{_ONBOARDING_SEQUENCE[0]}"
    return body


def _send(method: str, path: str, field: str, value: str):
    """Call one published surface with ``field`` set to ``value``."""
    builder = _OTHER_FIELDS.get((method, path))
    assert builder is not None, (
        f"the contract publishes a maxLength on {method} {path} {field!r} and "
        "this file has no body builder for it, so nothing sends it an "
        "over-limit value. Add one - a published limit nothing drives is a "
        "limit that can be deleted suite-green."
    )
    plan = builder()
    body = dict(plan["body"])
    body[field] = value
    return client.request(method, plan["path"], json=body)


@pytest.mark.parametrize(
    ("method", "path", "field", "limit"),
    published_limits(),
    ids=[f"{method} {path} {field}" for method, path, field, _ in published_limits()],
)
def test_a_value_over_the_published_limit_is_refused(
    method: str, path: str, field: str, limit: int
) -> None:
    """The defect: one was truncated, the other retained whole, both answered 200."""
    response = _send(method, path, field, "x" * (limit + 1))
    assert response.status_code == 400, (method, path, response.status_code, response.text)
    body = response.json()["detail"]
    assert body["error"] == "invalid_request", body
    assert any(entry["field"] == field for entry in body["fields"]), body
    assert str(limit) in str(body), (
        f"{method} {path} {field}: the refusal does not name the limit it "
        f"enforced: {body}"
    )


def test_every_published_limit_has_a_body_builder() -> None:
    """The premise of the derivation, asserted rather than left to a KeyError.

    If a new published limit arrives, the parametrization above drives it and
    fails on the missing builder - but it fails inside a parametrized case,
    which reads like the route being broken. This says plainly which it is.
    """
    undriven = [
        f"{method} {path} {field}"
        for method, path, field, _ in published_limits()
        if (method, path) not in _OTHER_FIELDS
    ]
    assert not undriven, (
        f"published limits with no body builder in this file: {undriven}"
    )


@pytest.mark.parametrize(
    ("label", "call"),
    [
        (
            "publish reason",
            lambda value: client.post(
                "/catalog/datasets/crm-customer-master/publish",
                json={"actor": "admin", "reason": value},
            ),
        ),
        (
            "review comment",
            lambda value: client.post(
                f"/ontology/patches/{_new_patch()}/review",
                json={"actor": "admin", "decision": "approve", "comment": value},
            ),
        ),
    ],
)
def test_a_value_exactly_at_the_limit_is_accepted_whole(label: str, call) -> None:
    """The boundary, both sides. An off-by-one here refuses a legal request."""
    value = "z" * MAX_CHANGE_REASON_CHARS
    response = call(value)
    assert response.status_code == 200, (label, response.text)


def test_an_accepted_reason_is_stored_exactly_as_sent() -> None:
    """Nothing is truncated any more, so the audit row is the caller's words."""
    reason = "r" * MAX_CHANGE_REASON_CHARS
    assert (
        client.post(
            "/catalog/datasets/crm-customer-master/publish",
            json={"actor": "admin", "reason": reason},
        ).status_code
        == 200
    )
    audits = client.get(
        "/catalog/datasets/crm-customer-master/audit",
        params={"user": "admin", "limit": 50},
    ).json()
    stored = [
        event["details"]["change_reason"]
        for event in audits
        if event.get("details", {}).get("change_reason")
    ]
    assert reason in stored, [len(item) for item in stored]


def test_an_accepted_comment_is_returned_exactly_as_sent() -> None:
    """The review path's mirror of the same property."""
    comment = "c" * MAX_CHANGE_REASON_CHARS
    reviewed = client.post(
        f"/ontology/patches/{_new_patch()}/review",
        json={"actor": "admin", "decision": "approve", "comment": comment},
    )
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["review_comment"] == comment


def test_nothing_truncates_a_caller_string_to_the_limit() -> None:
    """Structural, because a behavioural guard cannot see a truncation that is
    reachable only on a path this file does not drive.

    The repair is "refuse", not "refuse here and truncate there", so the slice
    that used to do it must not come back anywhere in the module.

    Read over the syntax tree, not the text. The first version matched the
    string ``"[:MAX_CHANGE_REASON_CHARS]"`` and failed on the docstring that
    records the removal - prose quoting the old code is not the old code, and a
    guard that cannot tell them apart would push the next author into not
    writing the explanation down.
    """
    import ast

    module = ast.parse(
        (Path(__file__).resolve().parents[1] / "src" / "sdp" / "api.py").read_text()
    )
    slices = [
        node
        for node in ast.walk(module)
        if isinstance(node, ast.Subscript)
        and isinstance(node.slice, ast.Slice)
        and isinstance(node.slice.upper, ast.Name)
        and node.slice.upper.id == "MAX_CHANGE_REASON_CHARS"
    ]
    assert not slices, (
        "a caller-supplied string is being truncated to the published limit "
        f"instead of refused, at line(s) {[node.lineno for node in slices]}"
    )
