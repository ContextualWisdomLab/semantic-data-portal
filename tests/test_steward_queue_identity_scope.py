"""Who may read a vocabulary proposal's actors, and from where.

``GET /ontology/patches`` ran **no** authorization. Measured at HEAD before this
file, after one proposal by ``analyst`` approved by ``admin``::

    GET /ontology/patches                  200  requestor=analyst
                                                reviewed_by=admin
                                                reviewed_at=2026-10-14T18:44:32Z
                                                review_comment='스튜어드 승인 사유'
    GET /ontology/patches?user=anonymous   200  (the same four fields)
    GET /ontology/patches?user=nobody      200  (the same four fields)

at the same moment as, for the same identities::

    GET /ontology/change-log               403
    GET /audit/events                      403
    GET /policy/decisions                  403

Two surfaces carried it, not one. Enumerated across every GET route the app
serves, with the response bodies walked for a mapping key rather than grepped
for a field name::

    /ontology/patches            requestor, reviewed_by, reviewed_at, review_comment
    /enterprise/steward-review   requestor

so gating the first alone would have left the proposer's name reachable from the
second. ``/enterprise/steward-review`` is a published open proof link, pinned to
resolve below 400, so it withholds the field instead of refusing the read.

The first version of the sweep had two holes of its own, both found by running
it against itself rather than by reading it:

* it searched the response **text** for the field name, and matched
  ``"withheld_review_item_fields": ["requestor"]`` - the declaration that the
  field is *absent* - reporting the repaired surface as still leaking. A
  declaration is not a disclosure, so it walks parsed bodies for a mapping key.
* it then skipped every response it could not parse as JSON, which is exactly
  the two routes that answer 200 with HTML and text. A surface that
  server-rendered the queue would have passed. Every 200 body now goes through
  the value search whatever its content type, and
  ``test_the_non_json_surfaces_carry_no_queue_row_at_all`` covers the part a
  value search cannot reach.
* the first attempt at that fix over-fired, treating the planted concept names
  and the patch id as leaks. They appear on five surfaces and every one is
  correct by design - an approved patch publishes its concept into the open
  vocabulary, and the steward summary publishes the queued row's id, concept,
  status and confidence. Asserting those were disclosures would have been a
  false claim in the opposite direction.

Reverse-verified: restoring ``"requestor": patch["requestor"]`` in
``steward_review.patch_items`` fails ``test_no_open_surface_names_a_proposal_actor``
and ``test_the_open_summary_withholds_the_proposer_and_declares_it``; removing
the ``_authorize_evidence_read`` call from ``ontology_patches`` fails five tests
here plus ``tests/test_api_error_contract.py``.
"""

from __future__ import annotations

from typing import Any

from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from sdp import enterprise_evidence, evidence, steward_review
from sdp.api import app


client = TestClient(app)

# The fields that name a person. ``concept``, ``suggestion``, ``status`` and
# ``confidence`` are proposal content, not identity, and are not listed.
IDENTITY_KEYS = frozenset({"requestor", "reviewed_by", "reviewed_at", "review_comment"})

# Every spelling of "no authenticated actor" the route accepts.
UNAUTHENTICATED_PROBES: tuple[dict[str, str], ...] = (
    {},
    {"user": "anonymous"},
    {"user": "nobody"},
    {"user": ""},
)

# Matching the response-contract generator, so this file can drive every GET.
PATH_SUBSTITUTIONS = {
    "{dataset_id}": "crm-customer-master",
    "{node_id}": "crm-customer-master",
    "{connector_id}": "sql_connector",
    "{concept}": "고객",
    "{term}": "고객",
}
REQUIRED_QUERY = {
    "/catalog/search": {"q": "고객"},
    "/ontology/search": {"q": "고객"},
    "/catalog/datasets/{dataset_id}/schema-diff": {
        "from_version": "1.0.0",
        "to_version": "1.0.0",
    },
    "/enterprise/connectors/{connector_id}/probe": {"dataset_id": "crm-customer-master"},
}


# The reviewer's comment is the one identity value that can be made distinctive:
# it is caller-supplied, and it is the reviewer speaking, so any surface carrying
# it is carrying review identity. ``requestor`` and ``reviewed_by`` cannot be -
# they are the authorized actors, and only a resolvable actor passes the
# proposal and review gates - so those two are covered by the key walk over JSON
# bodies and, for the two routes that answer 200 with something other than JSON,
# by proving they carry no queue row at all.
#
# The concept names and the patch id are deliberately **not** markers. Measured,
# they appear on five surfaces and each is correct: an approved patch publishes
# its concept into the shared, open vocabulary (/ontology/concepts,
# /ontology/vocabulary/jsonld, /enterprise/evidence-pack), and
# /enterprise/steward-review publishes the queued row's id, concept, status and
# confidence, which is the queue depth and topic the summary exists to answer.
# An earlier version of this file treated them as leaks and failed on all five -
# a false claim in the opposite direction from the one being fixed.
PLANTED_REVIEW_COMMENT = "스튜어드승인사유표지2026"
PLANTED_APPROVED_CONCEPT = "승인된개념표지"
PLANTED_PENDING_CONCEPT = "대기개념표지"


def _queue_one_approved_and_one_proposed() -> tuple[str, str]:
    """Put one approved and one still-proposed patch in the queue.

    Both states matter: the approved row is the one carrying ``reviewed_by``,
    ``reviewed_at`` and ``review_comment``, and the proposed row is the one
    ``/enterprise/steward-review`` republishes.
    """
    approved = client.post(
        "/ontology/patches",
        json={
            "actor": "analyst",
            "concept": PLANTED_APPROVED_CONCEPT,
            "suggestion": "승인된 개념의 정의",
        },
    )
    assert approved.status_code == 200, approved.text
    reviewed = client.post(
        f"/ontology/patches/{approved.json()['id']}/review",
        json={"actor": "admin", "decision": "approve", "comment": PLANTED_REVIEW_COMMENT},
    )
    assert reviewed.status_code == 200, reviewed.text
    pending = client.post(
        "/ontology/patches",
        json={
            "actor": "analyst",
            "concept": PLANTED_PENDING_CONCEPT,
            "suggestion": "아직 심사 전인 정의",
        },
    )
    assert pending.status_code == 200, pending.text
    return approved.json()["id"], pending.json()["id"]


def _identity_keys(node: Any, trail: tuple[str, ...] = ()) -> list[tuple[str, Any]]:
    """Every identity-bearing mapping key in ``node`` that carries a value.

    A *key* walk, not a text search. The first instrument written for this was a
    text search, and it matched ``"withheld_review_item_fields": ["requestor"]``
    - the declaration that the field is **absent** - and reported the repaired
    surface as still disclosing. A declaration is not a disclosure, and
    ``test_the_declaration_is_not_itself_a_disclosure`` pins that distinction so
    the instrument cannot be "fixed" by deleting the declaration.
    """
    found: list[tuple[str, Any]] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key in IDENTITY_KEYS and value is not None:
                found.append((".".join(trail + (key,)), value))
            found.extend(_identity_keys(value, trail + (key,)))
    elif isinstance(node, list):
        for index, item in enumerate(node):
            found.extend(_identity_keys(item, trail + (f"[{index}]",)))
    return found


def _get_routes() -> list[str]:
    """Every GET path the app serves, from the router rather than a list."""
    return sorted(
        route.path
        for route in app.routes
        if isinstance(route, APIRoute) and "GET" in route.methods
    )


def _fetch(path: str, probe: dict[str, str]) -> Any:
    """Fetch one GET route with the placeholders and required parameters filled."""
    url = path
    for placeholder, value in PATH_SUBSTITUTIONS.items():
        url = url.replace(placeholder, value)
    params = dict(REQUIRED_QUERY.get(path, {}))
    params.update(probe)
    return client.get(url, params=params)


def test_the_proposal_queue_refuses_an_unauthenticated_read() -> None:
    """Every spelling of "no actor" is refused, not just the empty one."""
    _queue_one_approved_and_one_proposed()
    statuses = {
        tuple(sorted(probe.items())): client.get("/ontology/patches", params=probe).status_code
        for probe in UNAUTHENTICATED_PROBES
    }
    assert set(statuses.values()) == {403}, statuses


def test_an_authorized_actor_reads_the_whole_queue_including_identity() -> None:
    """The gate scopes the read; it does not remove the capability.

    A steward has to know who proposed a change to judge it. That is why this is
    a gate rather than an unconditional redaction of the queue.
    """
    approved_id, pending_id = _queue_one_approved_and_one_proposed()
    response = client.get("/ontology/patches", params={"user": "analyst"})
    assert response.status_code == 200
    body = response.json()
    rows = {row["id"]: row for row in body["patches"]}
    assert set(rows) >= {approved_id, pending_id}
    assert rows[approved_id]["requestor"] == "analyst"
    assert rows[approved_id]["reviewed_by"] == "admin"
    assert rows[approved_id]["reviewed_at"]
    assert rows[approved_id]["review_comment"] == PLANTED_REVIEW_COMMENT
    assert rows[pending_id]["requestor"] == "analyst"
    # The governed read names the decision that let it through, like the other
    # governed reads, and states the scope that applies.
    assert body["policy_decision_id"]
    assert body["scope_note"]


def test_the_queue_and_the_change_log_agree_on_who_may_read_identity() -> None:
    """The defect was a disagreement between two surfaces, so pin the agreement.

    Both carry ``{actor_id, reviewer_id, recorded_at}`` for the same approval.
    One answered 403 and the other 200 to the same anonymous caller.
    """
    _queue_one_approved_and_one_proposed()
    for path in ("/ontology/patches", "/ontology/change-log"):
        assert client.get(path).status_code == 403, path
        assert client.get(path, params={"user": "admin"}).status_code == 200, path


def test_authorization_runs_before_the_status_filter_rules() -> None:
    """An unauthorized caller must not learn the payload rules.

    ``ontology_patch_review`` states that rule; this route now follows it. The
    400 body publishes ``known_statuses``, so ordering the checks the other way
    would answer a question the caller is not authorized to ask.
    """
    unauthorized = client.get("/ontology/patches", params={"status": "nope"})
    assert unauthorized.status_code == 403
    assert "known_statuses" not in unauthorized.text

    authorized = client.get("/ontology/patches", params={"status": "nope", "user": "admin"})
    assert authorized.status_code == 400
    detail = authorized.json()["detail"]
    assert detail["error"] == "unknown_status_filter"
    assert detail["known_statuses"] == ["approved", "proposed", "rejected"]


def test_the_refusal_and_the_success_each_record_exactly_one_decision() -> None:
    """One governed read, one decision row - the shape every other read has."""
    before = (len(evidence._POLICY_DECISION_LOG), len(evidence._AUDIT_EVENT_LOG))
    assert client.get("/ontology/patches").status_code == 403
    after_refusal = (len(evidence._POLICY_DECISION_LOG), len(evidence._AUDIT_EVENT_LOG))
    assert after_refusal == (before[0] + 1, before[1])
    assert client.get("/ontology/patches", params={"user": "admin"}).status_code == 200
    after_success = (len(evidence._POLICY_DECISION_LOG), len(evidence._AUDIT_EVENT_LOG))
    assert after_success == (before[0] + 2, before[1])


def test_no_get_route_answers_200_to_an_anonymous_caller_while_billing_the_ledger() -> None:
    """The platform-wide invariant that made this a gate rather than a redaction.

    ``test_the_scoped_route_is_not_a_new_ledger_write_surface`` states it for one
    route; measured across every GET the app serves, it holds everywhere - 19
    routes evaluate policy and every one of them answers 403 without an actor,
    and no route answers 200 while writing a row. Serving a redacted 200 from a
    policy evaluation would have made ``/ontology/patches`` the only read in the
    product that bills the ledger for an anonymous success, which is an
    unbounded-growth surface an unauthenticated caller controls.
    """
    offenders = []
    for path in _get_routes():
        before = (len(evidence._POLICY_DECISION_LOG), len(evidence._AUDIT_EVENT_LOG))
        response = _fetch(path, {})
        written = (
            len(evidence._POLICY_DECISION_LOG) - before[0],
            len(evidence._AUDIT_EVENT_LOG) - before[1],
        )
        if response.status_code == 200 and any(written):
            offenders.append((path, written))
    assert not offenders, f"open 200 reads that write ledger rows: {offenders}"


def test_no_open_surface_names_a_proposal_actor() -> None:
    """Enumerated over every GET route, because a third surface is one edit away.

    Two surfaces carried the identity and a spot check on one would have passed
    while the other still served the name. This drives every GET the router
    exposes under each unauthenticated spelling and walks the parsed body, so a
    future surface that republishes a patch row fails here rather than shipping.
    """
    approved_id, _pending_id = _queue_one_approved_and_one_proposed()
    # The approved row's timestamp, read from the governed route, is the second
    # distinctive identity value: it is ``reviewed_at`` and nothing else in the
    # product produces that exact string. Its reach is narrower than the
    # comment's and measured as such: planting a server-rendered leak in the
    # HTML console, the comment matched and the timestamp did not, because that
    # surface stringified the datetime as ``2026-10-14 19:02:31+00:00`` rather
    # than the route's ISO ``...T...Z``. A value search is format-sensitive, so
    # it is one detector of three rather than the one being relied on.
    approved_row = next(
        row
        for row in client.get("/ontology/patches", params={"user": "admin"}).json()["patches"]
        if row["id"] == approved_id
    )
    identity_values = (PLANTED_REVIEW_COMMENT, approved_row["reviewed_at"])

    # A non-JSON 200 is not a free pass. The first version of this sweep called
    # ``response.json()`` and ``continue``d on the two routes that answer 200
    # with HTML (``/enterprise/console``) and text (``/metrics``) - so a surface
    # that server-rendered the queue would have passed the very test written to
    # catch it. Both now go through the value search like every other body.
    disclosures = []
    for probe in UNAUTHENTICATED_PROBES:
        for path in _get_routes():
            response = _fetch(path, probe)
            if response.status_code != 200:
                continue
            for value in identity_values:
                if value and value in response.text:
                    disclosures.append((path, probe, "text", value))
            try:
                body = response.json()
            except ValueError:
                continue
            for field_path, value in _identity_keys(body):
                disclosures.append((path, probe, field_path, value))
    assert not disclosures, f"identity served to an unauthenticated caller: {disclosures}"


def test_the_non_json_surfaces_carry_no_queue_row_at_all() -> None:
    """How the two non-JSON responses are covered, since a bare actor name is not
    a searchable marker.

    ``requestor`` is ``analyst`` and ``reviewed_by`` is ``admin``: real actors,
    because only a resolvable actor passes the proposal and review gates, so
    neither can be planted as a distinctive string and a substring search for
    them would match unrelated content (``/enterprise/rbac-matrix`` publishes the
    role ``data-analyst``). What is checkable is the precondition: to render a
    row's proposer a surface must first hold the row. Measured,
    ``/enterprise/console`` is a static shell that fetches over JS and
    ``/metrics`` carries counters, so neither holds one - and this fails if
    either starts to.
    """
    approved_id, pending_id = _queue_one_approved_and_one_proposed()
    non_json = []
    for path in _get_routes():
        response = _fetch(path, {})
        if response.status_code != 200:
            continue
        try:
            response.json()
        except ValueError:
            non_json.append((path, response.text))
    # Enumerated, not assumed: if a third non-JSON surface appears it is checked
    # here too, and the names are asserted so a surface silently turning into
    # JSON (or away from it) is visible.
    assert sorted(path for path, _ in non_json) == ["/enterprise/console", "/metrics"]
    for path, text in non_json:
        for marker in (approved_id, pending_id, PLANTED_APPROVED_CONCEPT, PLANTED_PENDING_CONCEPT):
            assert marker not in text, f"{path} renders a queue row: {marker}"


def test_an_authorized_identity_read_is_served_only_by_the_governed_queue() -> None:
    """The other half: with an actor, exactly one route serves identity.

    If a second route starts serving it to an authorized caller, that route needs
    its own gate and its own decision row; this fails until one of the two is
    true.
    """
    _queue_one_approved_and_one_proposed()
    serving = set()
    for probe in ({"user": "admin"}, {"user": "analyst"}):
        for path in _get_routes():
            response = _fetch(path, probe)
            if response.status_code != 200:
                continue
            try:
                body = response.json()
            except ValueError:
                continue
            if _identity_keys(body):
                serving.add(path)
    assert serving == {"/ontology/patches"}, serving


def test_the_open_summary_withholds_the_proposer_and_declares_it() -> None:
    """A short row must not read as a row with no proposer.

    The summary keeps the queue visible - a buyer's question is how deep it is -
    and drops the name, for every caller including an authorized one.
    """
    _, pending_id = _queue_one_approved_and_one_proposed()
    for probe in ({}, {"user": "admin"}, {"user": "analyst"}):
        response = client.get("/enterprise/steward-review", params=probe)
        assert response.status_code == 200, probe
        body = response.json()
        rows = [item for item in body["review_items"] if item["type"] == "ontology_patch"]
        assert [row["id"] for row in rows] == [pending_id], (probe, rows)
        assert "requestor" not in rows[0], (probe, rows[0])
        # The queue is still legible: topic, state and confidence stay.
        assert rows[0]["concept"] == PLANTED_PENDING_CONCEPT
        assert rows[0]["status"] == "proposed"
        # All four, derived: the summary carries none of the identity fields,
        # and the declaration is computed from the items so it cannot keep
        # claiming a field is withheld after someone puts it back.
        assert body["withheld_review_item_fields"] == list(
            steward_review.REVIEW_ITEM_IDENTITY_FIELDS
        )
        for field in steward_review.REVIEW_ITEM_IDENTITY_FIELDS:
            assert field not in rows[0], (probe, field)
        note = body["withheld_review_item_field_note"]
        assert "/ontology/patches" in note and "/ontology/change-log" in note


def test_the_declaration_is_not_itself_a_disclosure() -> None:
    """The instrument distinction, pinned.

    The response text *does* contain the string ``requestor`` - in the
    declaration naming the withheld field - while no mapping key carries a
    proposer. A text-search detector reports this surface as leaking; a key walk
    does not. Pinned so the next person to write the detector does not "fix" the
    false positive by deleting the declaration.
    """
    _queue_one_approved_and_one_proposed()
    response = client.get("/enterprise/steward-review")
    assert "requestor" in response.text
    assert not _identity_keys(response.json())


def test_the_summary_stays_a_resolvable_open_proof_link() -> None:
    """Withheld, not gated, and this is why.

    The summary is published in ``OPEN_PROOF_ENDPOINTS`` and
    ``test_every_published_proof_link_resolves_as_published`` fetches each entry
    exactly as printed. Gating it would turn a published proof link into a
    refusal; this fails first, naming the reason, if someone tries.
    """
    assert "/enterprise/steward-review" in enterprise_evidence.OPEN_PROOF_ENDPOINTS
    assert client.get("/enterprise/steward-review").status_code == 200
    # The governed queue is not published as an open link, and must not become
    # one now that it refuses an anonymous read.
    assert "/ontology/patches" not in enterprise_evidence.OPEN_PROOF_ENDPOINTS
