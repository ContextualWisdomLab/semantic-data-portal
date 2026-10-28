"""No route may answer 5xx to a body a client can trivially send.

``POST /browse/{dataset_id}/preview`` is annotated ``dict[str, Any]`` - it has to
be, because ``limit`` and ``offset`` are integers - and it read ``user`` and
``purpose`` straight out of that dict with no type check. A non-string value
reached the policy and masking code and raised there:

    {"user": 123}  {"user": null}  {"user": ["a"]}  {"user": {"x": 1}}  {"user": true}
      -> 500 Internal Server Error   (same for every value of "purpose")

Sibling routes annotated ``dict[str, str]`` are validated by FastAPI and already
answered 422. The routes are enumerated here rather than spot-checked, so the
next raw-``Any`` body that reads a field without checking it fails here.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from sdp.api import app


client = TestClient(app, raise_server_exceptions=False)

NON_STRING_VALUES = (123, None, ["a"], {"x": 1}, True)

# (path, a body that works, the string fields to perturb)
RAW_PAYLOAD_ROUTES = (
    ("/browse/crm-customer-master/preview", {"user": "analyst", "purpose": "analysis"}, ("user", "purpose")),
    ("/llm/search", {"user": "analyst", "question": "고객"}, ("user", "question", "purpose")),
    (
        "/llm/draft-query",
        {"user": "admin", "dataset_id": "crm-customer-master", "question": "추이", "purpose": "analysis"},
        ("user", "dataset_id", "question", "purpose"),
    ),
    (
        "/policy/decision",
        {"subject": "analyst", "resource": "crm-customer-master", "action": "preview", "purpose": "analysis"},
        ("subject", "resource", "action", "purpose"),
    ),
    ("/ontology/resolve", {"text": "고객"}, ("text",)),
    ("/ontology/patches", {"actor": "analyst", "concept": "고객", "suggestion": "s"}, ("actor", "concept", "suggestion")),
    ("/ontology/concepts", {"actor": "admin", "concept": "새개념", "definition": "d"}, ("actor", "concept", "definition")),
    ("/catalog/datasets/crm-event/deprecate", {"actor": "admin", "reason": "r"}, ("actor", "reason")),
    (
        "/browse/query",
        {
            "user": "analyst",
            "dataset_ids": ["crm-customer-master"],
            "language": "SQL",
            "query": "select customer_id from crm_customer_master",
            "purpose": "analysis",
        },
        ("user", "language", "query", "purpose"),
    ),
)


@pytest.mark.parametrize("path,body,fields", RAW_PAYLOAD_ROUTES, ids=[row[0] for row in RAW_PAYLOAD_ROUTES])
def test_a_non_string_field_is_a_client_error_not_a_server_error(
    path: str, body: dict, fields: tuple[str, ...]
) -> None:
    """Any 4xx is a defensible answer here; a 5xx is a defect."""
    server_errors = []
    for field in fields:
        for value in NON_STRING_VALUES:
            payload = dict(body)
            payload[field] = value
            response = client.post(path, json=payload)
            if response.status_code >= 500:
                server_errors.append((field, value, response.status_code))
    assert not server_errors, f"{path} answered 5xx to a client-sendable body: {server_errors}"


def test_the_preview_route_names_the_offending_field() -> None:
    """An unactionable 400 is only half a fix."""
    for field in ("user", "purpose"):
        payload = {"user": "analyst", "purpose": "analysis", field: 123}
        response = client.post("/browse/crm-customer-master/preview", json=payload)
        assert response.status_code == 400, response.text
        assert field in response.text, response.text


def test_an_explicit_null_falls_back_to_the_documented_default() -> None:
    """``null`` is absence, not a bad type - matching _pagination_int's handling."""
    response = client.post(
        "/browse/crm-customer-master/preview",
        json={"user": "analyst", "purpose": None, "limit": None, "offset": None},
    )
    assert response.status_code == 200, response.text


def test_the_control_bodies_actually_work() -> None:
    """Otherwise the parametrized test above would pass on 4xx for every body."""
    for path, body, _ in RAW_PAYLOAD_ROUTES:
        response = client.post(path, json=body)
        assert response.status_code < 400, f"{path} control body failed: {response.text}"


# --------------------------------------------------------------------------- #
# The same class reached through stored catalog metadata rather than the request.
#
# ``profile`` is a free-form ``Dict[str, Any]`` on both POST /catalog/datasets
# and PATCH, so ``profile.row_count`` is stored verbatim. ``_row_count_estimate``
# compared it to an int, which raised ``TypeError`` - uncaught - so the governed
# query route was permanently dead for that dataset. Measured with
# ``profile: {"row_count": "1200000"}``, which is what a metadata harvester
# emitting counts as text produces:
#
#     POST /catalog/datasets    -> 200
#     POST /catalog/.../publish -> 200
#     POST /browse/query        -> 500 Internal Server Error
#     ledger delta: decisions +1  audits +0
#
# The 500 is the lesser half: the crash lands between the policy decision and
# the audit write, so it produced a decision with no matching audit event - the
# one pairing CLAUDE.md calls non-negotiable.
#
# This is the request-body defect class one surface over: the untrusted value is
# a *stored* one, so no amount of request validation on /browse/query would have
# caught it.
# --------------------------------------------------------------------------- #

ROW_COUNT_VALUES = (
    "1200000",          # a JSON string - the reported case
    "",
    [1, 2],
    {"a": 1},
    True,               # bool is an int in Python; not a measurement
    False,
    -5,                 # a negative count is not a count
    1200.5,             # fractional: would have to be silently truncated
    1200.0,             # a legitimate JSON spelling of 1200
    150,
    99999999,           # above the mock cap
    10**30,             # a float round-trip of this is not equal to it
    0,
)


def _publish_with_row_count(dataset_id: str, row_count) -> None:
    payload = {
        "actor": "admin",
        "id": dataset_id,
        "tenant_id": "demo",
        "title": "T",
        "description": "d",
        "owner": "admin",
        "steward": "admin",
        "domain": "sales",
        "source_system": "postgresql://analytics.dw/customer",
        "sensitivity": "internal",
        "update_frequency": "daily",
        "quality_score": 0.9,
        "freshness_score": 0.9,
        "schema": [
            {
                "name": "customer_id",
                "datatype": "string",
                "nullable_ratio": 0.0,
                "distinct_ratio": 1.0,
            }
        ],
        "distributions": [{"id": "d1", "format": "table", "endpoint": "https://dw/c"}],
        "profile": {"row_count": row_count},
    }
    assert client.post("/catalog/datasets", json=payload).status_code == 200
    assert (
        client.post(f"/catalog/datasets/{dataset_id}/publish", json={"actor": "admin"}).status_code
        == 200
    )


@pytest.mark.parametrize("row_count", ROW_COUNT_VALUES, ids=lambda v: repr(v)[:18])
def test_a_stored_row_count_of_any_type_does_not_5xx(row_count) -> None:
    dataset_id = f"rowcount-{abs(hash(repr(row_count))) % 10**8}"
    _publish_with_row_count(dataset_id, row_count)
    response = client.post(
        "/browse/query",
        json={
            "user": "admin",
            "purpose": "analysis",
            "dataset_ids": [dataset_id],
            "query": "SELECT count(*) FROM customer",
            "language": "sql",
        },
    )
    assert response.status_code < 500, (row_count, response.status_code, response.text[:200])


@pytest.mark.parametrize("row_count", ROW_COUNT_VALUES, ids=lambda v: repr(v)[:18])
def test_the_decision_and_audit_halves_stay_paired(row_count) -> None:
    """The invariant the crash broke, checked per value rather than once.

    A policy decision with no matching audit event is the pairing CLAUDE.md
    declares non-negotiable, and an exception between the two is how it breaks.
    """
    from sdp import catalog as catalog_module
    from sdp import evidence as evidence_module

    dataset_id = f"rowpair-{abs(hash(repr(row_count))) % 10**8}"
    _publish_with_row_count(dataset_id, row_count)
    decisions = len(evidence_module._POLICY_DECISION_LOG)
    audits = len(catalog_module._AUDIT_LOG)
    client.post(
        "/browse/query",
        json={
            "user": "admin",
            "purpose": "analysis",
            "dataset_ids": [dataset_id],
            "query": "SELECT count(*) FROM customer",
            "language": "sql",
        },
    )
    assert len(evidence_module._POLICY_DECISION_LOG) > decisions, row_count
    assert len(catalog_module._AUDIT_LOG) > audits, (
        f"row_count={row_count!r} produced a policy decision with no audit event"
    )


def test_a_non_numeric_row_count_is_labelled_unusable_not_estimated() -> None:
    """Provenance, not a silent substitute.

    This module's sibling defect was a figure labelled
    ``catalog_profile_estimate`` that was the cap, off by a factor of 600 from
    the thing it claimed. Falling back to the default is fine; calling it an
    estimate of the catalog profile is not.
    """
    _publish_with_row_count("rowcount-label", "1200000")
    body = client.post(
        "/browse/query",
        json={
            "user": "admin",
            "purpose": "analysis",
            "dataset_ids": ["rowcount-label"],
            "query": "SELECT count(*) FROM customer",
            "language": "sql",
        },
    ).json()
    assert body["execution"]["row_count_source"] == "unusable_catalog_profile_row_count"


def test_a_float_spelling_of_an_integer_is_still_an_estimate() -> None:
    """``1200.0`` is 1200; ``1200.5`` is not a row count."""
    from sdp import catalog as catalog_module
    from sdp.orchestrator import _row_count_estimate

    base = catalog_module._DATA["crm-customer-master"]
    integral = base.model_copy(update={"profile": {**base.profile, "row_count": 1200.0}})
    assert _row_count_estimate(integral, dry_run=False) == (1200, "catalog_profile_estimate")
    fractional = base.model_copy(update={"profile": {**base.profile, "row_count": 1200.5}})
    assert _row_count_estimate(fractional, dry_run=False)[1] == "unusable_catalog_profile_row_count"


def test_non_finite_row_counts_do_not_raise() -> None:
    """``NaN`` and ``Infinity`` are reachable: Python's ``json`` accepts them.

    My first version of the type guard used ``float(v) != int(v)``, which raises
    ``ValueError`` on ``NaN`` and ``OverflowError`` on ``Infinity`` - a second
    uncaught 500 in the same function - and also misclassified ``10**30``,
    because ``float(10**30)`` is not exactly ``10**30``.
    """
    from sdp import catalog as catalog_module
    from sdp.orchestrator import MOCK_ROW_COUNT_CAP, _row_count_estimate

    base = catalog_module._DATA["crm-customer-master"]
    for value in (float("nan"), float("inf"), float("-inf")):
        probe = base.model_copy(update={"profile": {**base.profile, "row_count": value}})
        assert _row_count_estimate(probe, dry_run=False)[1] == "unusable_catalog_profile_row_count"

    huge = base.model_copy(update={"profile": {**base.profile, "row_count": 10**30}})
    assert _row_count_estimate(huge, dry_run=False) == (
        MOCK_ROW_COUNT_CAP,
        "mock_row_cap_below_catalog_profile_estimate",
    )

    # And reachable end to end, not only through the helper.
    created = client.post(
        "/catalog/datasets",
        content=(
            b'{"actor":"admin","id":"rowcount-nan","tenant_id":"demo","title":"T",'
            b'"description":"d","owner":"admin","steward":"admin","domain":"s",'
            b'"source_system":"postgresql://a.dw/customer","sensitivity":"internal",'
            b'"update_frequency":"daily","quality_score":0.9,"freshness_score":0.9,'
            b'"schema":[{"name":"c","datatype":"string","nullable_ratio":0.0,'
            b'"distinct_ratio":1.0}],"distributions":[{"id":"d1","format":"table",'
            b'"endpoint":"https://x/y"}],"profile":{"row_count":NaN}}'
        ),
        headers={"content-type": "application/json"},
    )
    assert created.status_code == 200, created.text
    client.post("/catalog/datasets/rowcount-nan/publish", json={"actor": "admin"})
    response = client.post(
        "/browse/query",
        json={
            "user": "admin",
            "purpose": "analysis",
            "dataset_ids": ["rowcount-nan"],
            "query": "SELECT count(*) FROM customer",
            "language": "sql",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["execution"]["row_count_source"] == "unusable_catalog_profile_row_count"
