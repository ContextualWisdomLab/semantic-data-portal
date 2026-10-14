"""CAT-005 names four things a catalog-write audit row must carry; one was absent.

The acceptance criterion is "변경 전후 diff, actor, timestamp, reason 기록". The
diff, the actor and the timestamp were recorded. The reason was not:
``_build_dataset_payload`` hardcodes ``reason="ok"`` - which is the row's
*outcome*, not the caller's reason for the change - and only
``POST .../deprecate`` accepted one. Measured before this::

    PATCH /catalog/datasets/{id} {"reason": "buyer audit reason"}
      -> 200, details keys: after, before, changes, tenant_id  (no reason)

A caller's reason was accepted with 200 and dropped, because the request models
declare no such field and pydantic ignores an extra one.

Two design choices these tests hold in place.

The reason is read from the raw payload rather than added to
``DatasetCreateRequest``/``DatasetPatchRequest``: it is metadata *about* the
change, not dataset state, and those models' fields are a strict subset of
``Dataset``'s - an invariant ``tests/test_catalog_field_forwarding.py`` asserts
and a ``reason`` field would break. Because the key is then read outside the
model, it has to be declared in ``REQUEST_BODY_EXTRA_PROPERTIES`` or a client
generated from the document could not send it; the request-contract test caught
exactly that omission.

And the key is published even when no reason was given, as ``None``. Omitting it
would leave a reader unable to tell "the caller gave no reason" from "this
surface does not record one", which is the distinction the row exists to make.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from sdp import catalog
from sdp.api import MAX_CHANGE_REASON_CHARS, _change_reason
from sdp.api import app

client = TestClient(app)

_DATASET = "crm-customer-master"

_VALID_CREATE = {
    "title": "사유 증빙 픽스처",
    "description": "d",
    "owner": "owner@example.org",
    "steward": "steward@example.org",
    "domain": "customer",
    "source_system": "postgresql://analytics.dw:5432/crm",
    "sensitivity": "internal",
    "update_frequency": "daily",
    "quality_score": 0.9,
    "freshness_score": 0.9,
}


def _latest(action: str):
    """The most recent audit row for one action."""
    rows = [
        event
        for event in catalog.list_audit_events(limit=500, tenant_ids=None)
        if event.action == action
    ]
    assert rows, f"no {action} row was recorded"
    return rows[0]


# (label, the call, the action its audit row carries)
WRITES = (
    (
        "register",
        lambda reason: client.post(
            "/catalog/datasets",
            json={**_VALID_CREATE, "actor": "admin", **({"reason": reason} if reason is not None else {})},
        ),
        "dataset.register",
    ),
    (
        "patch",
        lambda reason: client.patch(
            f"/catalog/datasets/{_DATASET}",
            json={"actor": "admin", "title": f"제목 {reason!r}", **({"reason": reason} if reason is not None else {})},
        ),
        "dataset.patch",
    ),
    (
        "publish",
        lambda reason: client.post(
            f"/catalog/datasets/{_DATASET}/publish",
            json={"actor": "admin", **({"reason": reason} if reason is not None else {})},
        ),
        "dataset.publish",
    ),
    (
        "deprecate",
        lambda reason: client.post(
            f"/catalog/datasets/{_DATASET}/deprecate",
            json={"actor": "admin", **({"reason": reason} if reason is not None else {})},
        ),
        "dataset.deprecate",
    ),
)


@pytest.mark.parametrize("label,call,action", WRITES, ids=[row[0] for row in WRITES])
def test_every_catalog_write_records_a_supplied_reason(
    label: str, call, action: str
) -> None:
    """All four verbs, because three of the four recorded none."""
    response = call("감사 추적용 변경 사유")
    assert response.status_code == 200, response.text
    row = _latest(action)
    assert row.details.get("change_reason") == "감사 추적용 변경 사유", row.details


@pytest.mark.parametrize("label,call,action", WRITES, ids=[row[0] for row in WRITES])
def test_the_key_is_published_even_with_no_reason(
    label: str, call, action: str
) -> None:
    """``None`` is a different fact from "this surface does not record one"."""
    response = call(None)
    assert response.status_code == 200, response.text
    row = _latest(action)
    assert "change_reason" in row.details, row.details
    assert row.details["change_reason"] is None, row.details


def test_a_blank_reason_is_the_same_fact_as_no_reason() -> None:
    """An empty string in a prose field is worse than an honest absence."""
    for blank in ("", "   ", "\n\t "):
        assert _change_reason({"reason": blank}) is None, repr(blank)
    assert _change_reason({}) is None
    assert _change_reason(None) is None
    # A non-string is not a reason; it must not be coerced into one.
    for wrong in (42, True, ["a"], {"nested": "x"}):
        assert _change_reason({"reason": wrong}) is None, repr(wrong)


def test_a_reason_is_bounded_like_every_other_retained_caller_string() -> None:
    """The payload is caller-supplied and the row is retained."""
    long = "가" * (MAX_CHANGE_REASON_CHARS + 500)
    assert len(_change_reason({"reason": long})) == MAX_CHANGE_REASON_CHARS
    response = client.patch(
        f"/catalog/datasets/{_DATASET}",
        json={"actor": "admin", "title": "상한 확인", "reason": long},
    )
    assert response.status_code == 200, response.text
    recorded = _latest("dataset.patch").details["change_reason"]
    assert len(recorded) == MAX_CHANGE_REASON_CHARS


def test_the_reason_is_stripped_not_echoed_verbatim() -> None:
    """Surrounding whitespace is not part of a reason."""
    response = client.patch(
        f"/catalog/datasets/{_DATASET}",
        json={"actor": "admin", "title": "공백 확인", "reason": "  사유  "},
    )
    assert response.status_code == 200, response.text
    assert _latest("dataset.patch").details["change_reason"] == "사유"


def test_a_no_op_write_still_records_the_reason_it_was_given() -> None:
    """A refused-as-unnecessary change is still a documented attempt."""
    client.post(
        f"/catalog/datasets/{_DATASET}/deprecate",
        json={"actor": "admin", "reason": "first"},
    )
    client.post(
        f"/catalog/datasets/{_DATASET}/deprecate",
        json={"actor": "admin", "reason": "replayed with a different reason"},
    )
    row = _latest("dataset.deprecate")
    assert row.details.get("noop") is True, row.details
    assert row.details["change_reason"] == "replayed with a different reason"


def test_one_key_carries_the_reason_on_every_path() -> None:
    """``deprecate`` used its own ``details["reason"]``; two keys, one meaning.

    The rename is the point: a ledger reader filtering on one key would have
    found three of the four paths and missed the fourth, or found the fourth
    and missed the three.
    """
    assert catalog.CHANGE_REASON_DETAIL_KEY == "change_reason"
    for label, call, action in WRITES:
        call("키 통일 확인")
        row = _latest(action)
        assert "reason" not in row.details, (
            f"{label} still carries a separate details['reason'] key: {row.details}"
        )
        assert row.details["change_reason"] == "키 통일 확인"


def test_the_published_request_schema_declares_the_reason_key() -> None:
    """A key read outside the model must be documented or no client can send it."""
    from sdp.api_request_contract import REQUEST_BODY_EXTRA_PROPERTIES

    for route in (("POST", "/catalog/datasets"), ("PATCH", "/catalog/datasets/{dataset_id}")):
        extras = REQUEST_BODY_EXTRA_PROPERTIES[route]
        assert "reason" in extras, route
        assert extras["reason"]["type"] == "string"
        assert extras["reason"]["maxLength"] == MAX_CHANGE_REASON_CHARS
        assert extras["reason"]["description"]

    document = client.get("/openapi.json").json()
    for method, path in (("post", "/catalog/datasets"), ("patch", "/catalog/datasets/{dataset_id}")):
        body = document["paths"][path][method]["requestBody"]["content"][
            "application/json"
        ]["schema"]
        component = body["$ref"].rsplit("/", 1)[-1]
        properties = document["components"]["schemas"][component]["properties"]
        assert "reason" in properties, (method, path, sorted(properties))
