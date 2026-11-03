"""One route spelled the caller only as ``?actor=``, which no document uses.

``GET /graph/nodes/{node_id}`` was repaired for exactly this, and its comment
claims "This was the **only** route in the catalog/browse/ontology/graph surface
spelling the caller ``actor`` as a *query* parameter; 21 others spell it
``user``." Measured at ``94aa785`` from the published ``/openapi.json`` rather
than by hand::

    operations taking only ``actor``: [('GET', '/graph/stats')]
    operations taking only ``user`` : 25
    operations taking both          : [('GET', '/graph/nodes/{node_id}')]

    GET /graph/stats               -> 403 지식 그래프 접근은 인증된 사용자만 가능합니다.
    GET /graph/stats?user=admin    -> 403 지식 그래프 접근은 인증된 사용자만 가능합니다.
    GET /graph/stats?actor=admin   -> 200 {'backend': 'in_memory', 'stats': {...}}

So the prior repair's census missed one route and its prose asserted a
completeness it had not checked - an authenticated caller using the spelling
every document uses is refused as anonymous, with a message about
authentication that names nothing it could fix. ``?actor=`` appears zero times
in ``README.md``, ``docs/enterprise-readiness.md`` and
``docs/implementation-compliance.md``; ``?user=`` appears five times, and
README writes it as ``?user=<actor>``.

Pinned by derivation, so "the only route" cannot be asserted again without
being true: the census comes from the served OpenAPI document, and any
operation accepting ``actor`` must accept ``user`` too.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from sdp.api import app


client = TestClient(app)


def _caller_parameter_census() -> dict[str, list[tuple[str, str]]]:
    """Which spelling each published operation accepts, read off /openapi.json."""
    spec = client.get("/openapi.json").json()
    census: dict[str, list[tuple[str, str]]] = {"actor_only": [], "user_only": [], "both": []}
    for path, operations in spec["paths"].items():
        for method, operation in operations.items():
            names = {
                parameter.get("name")
                for parameter in (operation.get("parameters") or [])
            }
            if "actor" in names and "user" in names:
                census["both"].append((method.upper(), path))
            elif "actor" in names:
                census["actor_only"].append((method.upper(), path))
            elif "user" in names:
                census["user_only"].append((method.upper(), path))
    return census


def test_no_published_operation_accepts_only_the_undocumented_spelling() -> None:
    """``?user=`` is what every document writes, so every route must take it."""
    census = _caller_parameter_census()
    assert not census["actor_only"], (
        "these operations accept the caller only as ?actor=, a spelling no "
        f"document uses: {census['actor_only']}"
    )
    assert census["user_only"], "the census found no ?user= route at all"


def test_graph_stats_answers_both_spellings_identically() -> None:
    """The repaired sibling's contract, applied to the route it missed."""
    by_actor = client.get("/graph/stats?actor=admin")
    by_user = client.get("/graph/stats?user=admin")
    assert by_actor.status_code == 200, by_actor.text[:200]
    assert by_user.status_code == 200, by_user.text[:200]
    assert by_user.json() == by_actor.json()


def test_the_route_still_refuses_an_unauthenticated_caller() -> None:
    """Accepting a second spelling must not open the gate."""
    for query in ("", "?user=", "?actor=", "?user=nobody-at-all"):
        response = client.get(f"/graph/stats{query}")
        assert response.status_code == 403, (query, response.status_code)


def test_the_sibling_route_keeps_accepting_both() -> None:
    """The precedent this repair follows must not regress."""
    for query in ("?actor=admin", "?user=admin"):
        response = client.get(f"/graph/nodes/crm-customer-master{query}")
        assert response.status_code == 200, (query, response.status_code)
