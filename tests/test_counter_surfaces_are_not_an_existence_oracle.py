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


def _dataset_scoped_surfaces() -> list[tuple[str, str]]:
    """``(method, path)`` for every route taking a single dataset/node id.

    Derived, not listed. A curated table cannot report a route it does not
    contain, and that failure mode has already happened in this repository.
    """
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


def _call(method: str, path: str, dataset_id: str):
    """Issue one probe at ``path`` for ``dataset_id`` as the anonymous prober."""
    url = path.replace("{dataset_id}", dataset_id).replace("{node_id}", dataset_id)
    if method == "GET":
        return client.get(url, params=PROBE)
    return client.request(method, url, json=PROBE)


def _probe(method: str, path: str, dataset_id: str) -> tuple[int, tuple[float, ...]]:
    """Status plus the counter delta the one call produced."""
    before = _counters()
    response = _call(method, path, dataset_id)
    after = _counters()
    return response.status_code, tuple(after[g] - before[g] for g in GAUGES)


def test_the_sweep_actually_covers_the_dataset_scoped_surfaces() -> None:
    """The premise: a sweep that exercises nothing reports green.

    Pinned as a floor rather than an exact count so adding a route does not
    fail this, while deriving nothing does.
    """
    surfaces = _dataset_scoped_surfaces()
    assert len(surfaces) >= 15, surfaces
    assert ("GET", "/browse/{dataset_id}/schema") in surfaces
    assert ("POST", "/browse/{dataset_id}/preview") in surfaces


@pytest.mark.parametrize("method,path", _dataset_scoped_surfaces())
def test_the_global_counters_do_not_reveal_whether_an_id_is_free(method: str, path: str) -> None:
    """Identical HTTP answer must mean an identical counter answer."""
    foreign_status, foreign_delta = _probe(method, path, FOREIGN)
    absent_status, absent_delta = _probe(method, path, ABSENT)

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
