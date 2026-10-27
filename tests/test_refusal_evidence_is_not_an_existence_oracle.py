"""A prober's own decision ledger must not answer what the 404 refuses.

Five routes collapse "this dataset is not yours" and "this dataset does not
exist" into one byte-identical ``404 dataset not found`` - deliberately, and
already pinned by the browse, catalog and graph refusal families. But the
policy-decision ledger is readable *by the prober*, scoped to its own tenant,
and filterable by resource::

    GET /policy/decisions?user=<prober>&resource=<id>

Measured as ``external-analyst`` (tenant ``external``), with the HTTP bodies
already identical, counting only rows that caller can see::

    GET  /graph/nodes/{id}              404/404   rows: foreign 0   absent 1
    POST /graph/query  (start_id)       404/404   rows: foreign 0   absent 1
    POST /catalog/datasets/{id}/publish 404/404   rows: foreign 0   absent 1
    POST .../{id}/deprecate             404/404   rows: foreign 0   absent 1
    PATCH /catalog/datasets/{id}        404/404   rows: foreign 0   absent 1

    GET  /browse/{id}/schema            404/404   rows: foreign 0   absent 0
    POST /browse/{id}/preview           404/404   rows: foreign 0   absent 0
    GET  /catalog/datasets/{id}         404/404   rows: foreign 0   absent 0

A row appearing exactly when the id is **free** answers the question the 404
exists to refuse, and the row does not merely leak by its presence - it states
the answer::

    {"action": "publish", "effect": "deny",
     "reason": "존재하지 않는 데이터셋입니다.",     <- "the dataset does not exist"
     "obligations": {"tenant_id": "external"}}    <- the prober's own tenant

    {"action": "search", "effect": "allow",
     "reason": "카탈로그 발견 정책 통과",            <- an allow row behind a 404
     "obligations": {"tenant_id": "external"}}

The mechanism is the same on both sets of routes and it is not the refusal
recording, which was repaired earlier and files to the owning tenant or the
reserved ``unresolved`` scope. It is the evaluation that runs **before** the
reachability check:

* the graph routes authenticate with ``evaluate(..., resource=node_id,
  action="search")``, whose own docstring says it "establishes authentication
  only" - so it files a per-id row for a question that is not about that id,
  and for an absent id the catalog-discovery branch returns ``allow`` in the
  prober's own tenant;
* the three catalog mutations call ``evaluate(..., resource=dataset_id)`` first
  and reach ``_catalog_mutation_refusal`` after the row is already filed, so
  the "does not exist" reason lands in the prober's scope.

``policy.evaluate_dataset_scope_refusal`` is the helper built for this, and
``browse.py`` shows the working order: resolve reachability **first**, file the
refusal outside the prober's scope, and only then evaluate. The three clean
rows above are that order; the five leaking ones are the other one.

The HTTP channel is unchanged. What changes is which scope the evidence lands
in - the owning tenant's auditor still sees attempts on its own assets.

One sentence above was overstated until later measurement. ``browse``'s three
rows read ``0/0`` here, and this file credited that to "the working order".
``schema`` was clean for a different reason: it filed **nothing** for an absent
id, which keeps this ledger quiet and leaves a louder channel open. The
unauthenticated global gauges on ``GET /metrics`` moved ``+1/+1`` for a foreign
id and ``+0/+0`` for an absent one, so a caller with no credential at all could
read the answer off the counters - see
``test_counter_surfaces_are_not_an_existence_oracle.py``. ``schema`` now files
through ``evaluate_dataset_scope_refusal`` like its siblings, and the claim
above is earned rather than coincidental.

The two guards are not redundant, and each catches what the other misses:
filing nothing reddens only the counter sweep, while filing through the generic
``evaluate`` - into the prober's own scope - reddens only this file. Closing one
channel by opening the other would pass either guard alone.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sdp.api import app  # noqa: E402
from sdp.policy import accessible_tenant_ids  # noqa: E402

client = TestClient(app)

# tenant ``external`` - an authenticated reader that owns none of the seeded
# datasets, which is what makes every seeded id "foreign" to it.
PROBER = "external-analyst"
FOREIGN = "crm-customer-master"
ABSENT = "no-such-dataset-xyz-0b1c"

# Words a row visible to the prober must never carry about an id it cannot
# reach. Both languages, because the reasons in this product are Korean and the
# obligations are English.
EXISTENCE_WORDS = ("존재하지", "not found", "absent", "unknown dataset")

# The surface list is **derived from the application**, not curated. The first
# draft was a hand-written list of eight and the coverage check below reported
# eleven dataset-scoped routes it had never measured - audit, join-candidates,
# jsonld, lineage, profile, related, schema-diff, schema-history,
# schema-versions, semantic-validation, validate. All eleven turned out clean,
# which is exactly the result a curated list cannot be trusted to produce,
# because it would have reported the same green without visiting any of them.
_SKIPPED_PREFIX = "/api/v1"  # aliases delegating to the same handlers


def _dataset_scoped_routes() -> list[tuple[str, str]]:
    """Every (method, path) taking a dataset or node id in its path."""
    found: set[tuple[str, str]] = set()
    for route in app.routes:
        path = getattr(route, "path", "")
        if path.startswith(_SKIPPED_PREFIX):
            continue
        if not any(token in path for token in ("{dataset_id}", "{node_id}")):
            continue
        for method in getattr(route, "methods", set()) or set():
            if method in {"HEAD", "OPTIONS"}:
                continue
            found.add((method, path))
    return sorted(found)


def _path_caller(method: str, path: str) -> Callable[[str], object]:
    """Drive one route against a dataset id, carrying the actor both ways.

    Routes in this product disagree about whether the caller travels in
    ``?user=``, ``?actor=`` or the body, so all three are supplied; an
    unauthenticated default would make every surface refuse for the wrong
    reason and the family would prove nothing.
    """

    def call(dataset_id: str) -> object:
        url = path.replace("{dataset_id}", dataset_id).replace("{node_id}", dataset_id)
        if method == "GET":
            return client.get(url, params={"user": PROBER, "actor": PROBER})
        return client.request(
            method,
            url,
            params={"user": PROBER, "actor": PROBER},
            json={"actor": PROBER, "user": PROBER, "description": "oracle probe"},
        )

    return call


# ``POST /graph/query`` takes the id in its **body**, so no path scan finds it -
# and it carries the same defect as ``GET /graph/nodes/{id}`` because both call
# ``_authorize_graph_node_read``. Listed explicitly, and the coverage check
# below asserts it stays listed.
BODY_SCOPED_SURFACES: list[tuple[str, Callable[[str], object]]] = [
    (
        "POST /graph/query",
        lambda i: client.post(
            "/graph/query", json={"actor": PROBER, "start_id": i, "max_depth": 1}
        ),
    ),
]

SURFACES: list[tuple[str, Callable[[str], object]]] = [
    (f"{method} {path}", _path_caller(method, path))
    for method, path in _dataset_scoped_routes()
] + BODY_SCOPED_SURFACES

SURFACE_IDS = [label for label, _ in SURFACES]


def _visible_rows(resource: str) -> list[dict]:
    """The decision rows the prober itself can read about one resource."""
    response = client.get(
        "/policy/decisions", params={"user": PROBER, "resource": resource, "limit": 500}
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_the_prober_is_an_authenticated_reader_owning_none_of_this() -> None:
    """The premise. An unauthenticated caller is refused earlier and differently."""
    tenants = accessible_tenant_ids(PROBER)
    assert tenants, f"{PROBER!r} must be authenticated for this family to mean anything"
    assert client.get("/catalog/datasets", params={"user": PROBER}).json() == [], (
        "the prober must own none of the seeded datasets, or FOREIGN is not foreign"
    )


@pytest.mark.parametrize(("label", "call"), SURFACES, ids=SURFACE_IDS)
def test_the_http_answer_is_already_identical(label: str, call: Callable[[str], object]) -> None:
    """The premise that makes the ledger the whole channel.

    If a surface ever distinguished the two over HTTP, the ledger assertion
    below would be guarding a door that is already open, and this file would
    still be green.
    """
    foreign, absent = call(FOREIGN), call(ABSENT)
    # Identical, not specifically 404: ``schema-diff`` answers 422 for want of
    # its query parameters, and 422/422 with one body is just as closed.
    assert foreign.status_code == absent.status_code, (  # type: ignore[attr-defined]
        label,
        foreign.status_code,  # type: ignore[attr-defined]
        absent.status_code,  # type: ignore[attr-defined]
    )
    assert foreign.status_code >= 400, (label, foreign.status_code)  # type: ignore[attr-defined]
    assert foreign.text == absent.text, (label, foreign.text, absent.text)  # type: ignore[attr-defined]


@pytest.mark.parametrize(("label", "call"), SURFACES, ids=SURFACE_IDS)
def test_the_visible_ledger_does_not_distinguish_the_two(
    label: str, call: Callable[[str], object]
) -> None:
    """The defect: a row appeared exactly when the id was free."""
    before_foreign, before_absent = len(_visible_rows(FOREIGN)), len(_visible_rows(ABSENT))
    call(FOREIGN)
    call(ABSENT)
    added_foreign = len(_visible_rows(FOREIGN)) - before_foreign
    added_absent = len(_visible_rows(ABSENT)) - before_absent
    assert added_foreign == added_absent, (
        f"{label} files {added_foreign} prober-visible decision row(s) for a "
        f"foreign id and {added_absent} for an absent one, so the prober's own "
        "/policy/decisions answers what the 404 refuses"
    )


@pytest.mark.parametrize(("label", "call"), SURFACES, ids=SURFACE_IDS)
def test_no_visible_row_states_the_answer(label: str, call: Callable[[str], object]) -> None:
    """Counting is not enough: the row must not *say* the id is free either.

    Equal counts with one row reading "존재하지 않는 데이터셋입니다." and the other
    "tenant boundary denied" would pass the count assertion and leak the same
    bit in plain text.
    """
    call(FOREIGN)
    call(ABSENT)
    for resource in (FOREIGN, ABSENT):
        for row in _visible_rows(resource):
            blob = f"{row.get('reason', '')} {row.get('obligations', {})}".lower()
            leaked = [word for word in EXISTENCE_WORDS if word.lower() in blob]
            assert not leaked, (
                f"{label}: a row the prober can read about {resource!r} carries "
                f"{leaked} - {row}"
            )


@pytest.mark.parametrize(("label", "call"), SURFACES, ids=SURFACE_IDS)
def test_no_visible_row_behind_a_404_claims_the_access_was_allowed(
    label: str, call: Callable[[str], object]
) -> None:
    """An ``allow`` row behind a 404 describes something that did not happen."""
    call(FOREIGN)
    call(ABSENT)
    for resource in (FOREIGN, ABSENT):
        effects = [row.get("effect") for row in _visible_rows(resource)]
        assert "allow" not in effects, (
            f"{label}: the prober can read an allow row about {resource!r}, which "
            f"it was refused: {effects}"
        )


def test_every_dataset_scoped_route_is_measured() -> None:
    """Derived from the app, so a new route cannot quietly join the leaking set.

    A curated list is the kind of guard that reports success because it was
    never extended - this one did exactly that, listing eight surfaces while
    the app had nineteen.
    """
    measured = set(SURFACE_IDS)
    for method, path in _dataset_scoped_routes():
        assert f"{method} {path}" in measured, (method, path)
    assert len(SURFACES) == len(_dataset_scoped_routes()) + len(BODY_SCOPED_SURFACES)
    assert len(SURFACES) >= 17, len(SURFACES)


def test_the_body_scoped_traversal_route_stays_listed() -> None:
    """No path scan finds it, so only this assertion keeps it in the family."""
    assert "POST /graph/query" in SURFACE_IDS
    assert any(
        getattr(route, "path", "") == "/graph/query" for route in app.routes
    ), "the route this entry stands in for no longer exists"


# --------------------------------------------------------------------------
# Closing the prober's channel must not delete the evidence. The owning
# tenant's auditor is the reader this evidence is for, and the refusal is now
# filed in its scope rather than the prober's.
#
# Deleting the refusal filing entirely leaves every assertion above green -
# measured - because none of them look at the owner's side. The full suite does
# catch it (``tests/test_refused_mutation_evidence.py``), but a family that can
# be satisfied by removing the thing it is about is not self-contained, so the
# other half is asserted here too.
# --------------------------------------------------------------------------

OWNER_AUDITOR = "admin"


@pytest.mark.parametrize(
    ("event_type", "call"),
    [
        ("dataset.publish", lambda i: client.post(f"/catalog/datasets/{i}/publish", json={"actor": PROBER})),
        ("dataset.deprecate", lambda i: client.post(f"/catalog/datasets/{i}/deprecate", json={"actor": PROBER})),
        ("dataset.patch", lambda i: client.patch(f"/catalog/datasets/{i}", json={"actor": PROBER, "description": "x"})),
    ],
    ids=["publish", "deprecate", "patch"],
)
def test_the_refusal_is_still_recorded_where_the_owner_can_read_it(
    event_type: str, call: Callable[[str], object]
) -> None:
    """Both halves of the governance invariant, outside the prober's scope."""
    before = len(
        client.get(
            "/policy/decisions",
            params={"user": OWNER_AUDITOR, "resource": FOREIGN, "limit": 500},
        ).json()
    )
    call(FOREIGN)
    rows = client.get(
        "/policy/decisions", params={"user": OWNER_AUDITOR, "resource": FOREIGN, "limit": 500}
    ).json()
    assert len(rows) > before, (
        f"{event_type} on a foreign dataset recorded no decision the owner can "
        "read, so closing the prober's channel deleted the evidence instead of "
        "moving it"
    )
    assert any(row.get("effect") == "deny" for row in rows), [r.get("effect") for r in rows]

    audit_response = client.get(
        f"/catalog/datasets/{FOREIGN}/audit", params={"user": OWNER_AUDITOR, "limit": 200}  # this route caps at 200
    )
    assert audit_response.status_code == 200, audit_response.text
    audits = audit_response.json()
    assert isinstance(audits, list) and all(isinstance(event, dict) for event in audits), audits
    # ``result``, not ``decision``: the audit event's field is spelled ``result``
    # on this route, and asking for the wrong key raised rather than failing -
    # a guard that errors is not a guard that measures.
    refused = [event for event in audits if event.get("result") in {"denied", "refused"}]
    assert refused, (
        f"{event_type}: the owner's audit trail holds no refused attempt: "
        f"{[(event.get('action'), event.get('result')) for event in audits[:5]]}"
    )
    assert any(event.get("actor") == PROBER for event in refused), (
        f"{event_type}: the owner cannot see who attempted it: "
        f"{[event.get('actor') for event in refused[:5]]}"
    )
