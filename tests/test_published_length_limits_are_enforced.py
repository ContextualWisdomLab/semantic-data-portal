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
            "deprecate reason",
            lambda value: client.post(
                "/catalog/datasets/sales-order/deprecate",
                json={"actor": "admin", "reason": value},
            ),
        ),
        (
            "patch reason",
            lambda value: client.patch(
                "/catalog/datasets/crm-customer-master",
                json={"actor": "admin", "description": "d", "reason": value},
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
def test_a_value_over_the_published_limit_is_refused(label: str, call) -> None:
    """The defect: one was truncated, the other retained whole, both answered 200."""
    response = call("x" * (MAX_CHANGE_REASON_CHARS + 1))
    assert response.status_code == 400, (label, response.status_code, response.text)
    body = response.json()["detail"]
    assert body["error"] == "invalid_request", body
    assert any(
        entry["field"] in {"reason", "comment"} for entry in body["fields"]
    ), body
    assert str(MAX_CHANGE_REASON_CHARS) in str(body), (
        f"{label}: the refusal does not name the limit it enforced: {body}"
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
