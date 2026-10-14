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
            "query": "select customer_id from customer",
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
