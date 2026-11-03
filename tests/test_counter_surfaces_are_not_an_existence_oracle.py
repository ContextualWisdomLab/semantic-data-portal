"""The unauthenticated counters must not distinguish a free id from a taken one.

The dataset-scoped routes collapse "not yours" and "does not exist" into one
byte-identical ``404 dataset not found``. An earlier guard
(``test_refusal_evidence_is_not_an_existence_oracle.py``) pinned that the
*prober's own* decision ledger does not answer what the 404 refuses - and that
guard's premise is the tenant-scoped ledger, which needs a credential:
``GET /policy/decisions`` answers ``403`` to an anonymous caller.

There is a second channel with no credential at all. ``GET /metrics`` is
unauthenticated and publishes two **global** gauges,
``sdp_audit_events_observed_total`` and
``sdp_policy_decisions_observed_total`` (``/enterprise/observability`` and
``/enterprise/evidence-pack`` publish the same totals). Read them, call a
dataset-scoped route with a candidate id, read them again: the delta is the
answer. Measured on ``ef46174``, both calls answering ``404``::

    GET /browse/{id}/schema    foreign +1/+1    absent +0/+0   <- asymmetric
    POST /browse/{id}/preview  foreign +1/+1    absent +1/+1

So any caller, with no credential, could decide whether an id exists in any
tenant. ``schema`` was the one route with the asymmetry: it raised ``KeyError``
for an absent id before evaluating anything, while every sibling - ``preview``
among them - files the absent-id refusal through
``policy.evaluate_dataset_scope_refusal``, which lands outside the prober's
scope and keeps the two paths indistinguishable from outside.

This file sweeps the surfaces **derived from ``app.routes``** rather than a
curated list, because a curated list is how the previous sweep came to miss
eleven routes while reporting green.
"""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from sdp.api import app
from sdp.api_request_contract import REQUEST_BODY_MODELS

client = TestClient(app)

GAUGES = ("sdp_audit_events_observed_total", "sdp_policy_decisions_observed_total")

FOREIGN = "crm-customer-master"          # exists; not readable by the prober
ABSENT = "definitely-not-a-dataset-9f3a"  # free id
PROBE = {"user": "anonymous", "purpose": "external-export"}


def _counters() -> dict[str, float]:
    """The two global gauges, read off the unauthenticated metrics surface."""
    text = client.get("/metrics").text
    out: dict[str, float] = {}
    for gauge in GAUGES:
        match = re.search(rf"^{gauge}\s+([0-9.]+)$", text, re.M)
        assert match is not None, f"{gauge} is no longer published; update this guard"
        out[gauge] = float(match.group(1))
    return out


def _path_named_surfaces() -> list[tuple[str, str]]:
    """``(method, path)`` for every route naming a dataset/node id in the PATH."""
    surfaces: list[tuple[str, str]] = []
    for route in app.routes:
        path = getattr(route, "path", "")
        if "{dataset_id}" not in path and "{node_id}" not in path:
            continue
        for method in sorted(getattr(route, "methods", []) or []):
            if method in {"HEAD", "OPTIONS"}:
                continue
            surfaces.append((method, path))
    return surfaces


# Fields through which a request body names a dataset. Not a route list - a
# field-name set, applied to every model in the request contract, so a new route
# reusing one of these models is swept the moment it is registered.
BODY_DATASET_FIELDS = ("dataset_id", "dataset_ids", "related_datasets", "start_id", "node_id")


def _body_named_surfaces() -> list[tuple[str, str, str]]:
    """``(method, path, field)`` for every route naming a dataset in its BODY.

    Round 30 added this half, and the reason is the point. The path-shaped
    derivation above was introduced *because* "a curated table cannot report a
    route it does not contain" - but it derived from the wrong property. Filtering
    on ``"{dataset_id}" not in path`` is itself a curated rule: it encodes the
    assumption that naming a dataset means putting it in the URL. Three routes
    named one in the body instead, and all three were live existence oracles on
    the gauges this file reads while all three committed oracle guards reported
    green. Measured before the repair, as the anonymous prober, deltas
    ``(audit, policy)``:

        POST /browse/query          foreign (1,1)   absent (1,0)
        POST /api/v1/browse/query   foreign (1,1)   absent (1,0)
        POST /llm/draft-query       foreign (1,1)   absent (0,0)

    with status and body byte-identical in every case, which is exactly why the
    sibling sweep over status-and-body could not see them. The repository had
    written the governing rule down twice already -
    ``tests/test_oracle_sweep_by_naming_mechanism.py``'s "an existence oracle is
    a property of the *question*, not of the URL shape", and
    ``orchestrator.py``'s "this route names its dataset in the request *body*,
    which is why the path-shaped enumeration did not reach it" - and this file
    still derived from the shape.

    All five matching routes are swept, including the two whose field is
    ``related_datasets`` on a mutation. Those two are green, and measurement says
    why rather than judgment: both refuse on authorization *before* the field is
    examined (403 for an anonymous caller), so a prober never reaches it.
    Excluding them because they look like "a different question" would be the
    curated exclusion this docstring is about; if that authorization order ever
    changes, they are already in the sweep.
    """
    surfaces: list[tuple[str, str, str]] = []
    for (method, path), model in REQUEST_BODY_MODELS.items():
        for field in getattr(model, "model_fields", {}):
            if field in BODY_DATASET_FIELDS:
                surfaces.append((method, path, field))
    return sorted(surfaces)


def _dataset_scoped_surfaces() -> list[tuple[str, str, str | None]]:
    """Every route naming a dataset, by either mechanism. Derived, not listed.

    The third element is the body field carrying the id, or ``None`` when the
    path carries it. It exists because adding the body-named routes to this
    sweep without it made the sweep **vacuous on exactly those routes**: ``_call``
    substituted only into the path, so for a body-named surface the foreign and
    absent probes were byte-identical requests with no dataset id anywhere, and
    the sweep reported green over five surfaces it was not probing. Caught by
    reading ``_call`` after the parametrization already passed - a guard that
    grows its surface list and stays green has not necessarily grown its reach.
    """
    return [(method, path, None) for method, path in _path_named_surfaces()] + [
        (method, path, field) for method, path, field in _body_named_surfaces()
    ]


def _minimal_body(method: str, path: str, field: str, dataset_id: str) -> dict:
    """A body this route's model accepts, with ``field`` set to ``dataset_id``.

    Filled from the model's own required fields by type rather than hand-written
    per route, so a model gaining a required field does not silently reduce this
    probe to a 422 that is identical for both ids and therefore proves nothing.
    """
    model = REQUEST_BODY_MODELS[(method, path)]
    body: dict[str, object] = {}
    for name, info in model.model_fields.items():
        if name == field:
            body[name] = [dataset_id] if name.endswith("s") else dataset_id
            continue
        if not info.is_required():
            continue
        annotation = repr(info.annotation)
        if "list" in annotation or "List" in annotation:
            body[name] = []
        elif "float" in annotation:
            body[name] = 0.5
        elif "int" in annotation:
            body[name] = 1
        elif "bool" in annotation:
            body[name] = False
        else:
            body[name] = "probe"
    body.update(PROBE)
    body[field] = [dataset_id] if field.endswith("s") else dataset_id
    return body


def _call(method: str, path: str, dataset_id: str, field: str | None = None):
    """Issue one probe for ``dataset_id`` as the anonymous prober.

    ``field`` names the body key carrying the id for a body-named route; when it
    is ``None`` the id goes into the path, as before.
    """
    if field is not None:
        return client.request(method, path, json=_minimal_body(method, path, field, dataset_id))
    url = path.replace("{dataset_id}", dataset_id).replace("{node_id}", dataset_id)
    if method == "GET":
        return client.get(url, params=PROBE)
    return client.request(method, url, json=PROBE)


def _probe(
    method: str, path: str, dataset_id: str, field: str | None = None
) -> tuple[int, tuple[float, ...]]:
    """Status plus the counter delta the one call produced."""
    before = _counters()
    response = _call(method, path, dataset_id, field)
    after = _counters()
    return response.status_code, tuple(after[g] - before[g] for g in GAUGES)


def test_the_sweep_actually_covers_the_dataset_scoped_surfaces() -> None:
    """The premise: a sweep that exercises nothing reports green.

    Pinned as a floor rather than an exact count so adding a route does not
    fail this, while deriving nothing does.
    """
    surfaces = _dataset_scoped_surfaces()
    assert len(surfaces) >= 15, surfaces
    assert ("GET", "/browse/{dataset_id}/schema", None) in surfaces
    assert ("POST", "/browse/{dataset_id}/preview", None) in surfaces
    # Both mechanisms, or the sweep is back to deriving from the URL shape. The
    # body half is named by field, not by route, so this does not become a
    # curated list of the routes that happen to exist today.
    body_named = [surface for surface in surfaces if surface[2] is not None]
    assert body_named, "no body-named surface is swept; the path filter is back"
    assert ("POST", "/browse/query", "dataset_ids") in surfaces, surfaces
    assert ("POST", "/llm/draft-query", "dataset_id") in surfaces, surfaces


def test_a_body_named_probe_actually_carries_the_id() -> None:
    """The anti-vacuity control for the half this file gained in round 30.

    Adding the body-named routes to the parametrization was not enough: ``_call``
    substituted only into the path, so the two probes were byte-identical
    requests carrying no dataset id, and the sweep reported green over five
    surfaces it never exercised.

    This asserts on **what ``_call`` actually put on the wire**, not on what
    ``_minimal_body`` could produce. The first version of this control called
    ``_minimal_body`` directly, and a mutation that made ``_call`` send a bare
    probe body - reintroducing the exact vacuity - left it green, because the
    helper it inspected was untouched. A control that does not exercise the path
    under test proves nothing about that path.
    """
    for method, path, field in _body_named_surfaces():
        for dataset_id in (FOREIGN, ABSENT):
            sent = _call(method, path, dataset_id, field).request.content.decode()
            assert dataset_id in sent, (
                f"{method} {path} probe did not carry {dataset_id} in its body; "
                f"the sweep over this surface is vacuous. sent={sent[:200]}"
            )


@pytest.mark.parametrize("method,path,field", _dataset_scoped_surfaces())
def test_the_global_counters_do_not_reveal_whether_an_id_is_free(
    method: str, path: str, field: str | None
) -> None:
    """Identical HTTP answer must mean an identical counter answer."""
    foreign_status, foreign_delta = _probe(method, path, FOREIGN, field)
    absent_status, absent_delta = _probe(method, path, ABSENT, field)

    if foreign_status != absent_status:
        pytest.skip(
            f"{method} {path} answers {foreign_status}/{absent_status}; the HTTP "
            "channel already distinguishes these, which is a separate question"
        )
    assert foreign_delta == absent_delta, (
        f"{method} {path} answers {foreign_status} for both, but the "
        f"unauthenticated counters move differently: foreign {foreign_delta} vs "
        f"absent {absent_delta}. A caller with no credential reads /metrics, "
        "calls this route, reads /metrics again, and learns whether the id is free."
    )
