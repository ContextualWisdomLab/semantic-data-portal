"""The evidence pack says its own refusals are evidence. One of them left none.

``/enterprise/evidence-pack`` splits ``proof_endpoints`` into open reads and
``actor_scoped_proof_endpoints``, and publishes ``actor_scoped_proof_note`` as
the explanation a diligence reader is meant to follow::

    이 경로들은 거버닝 읽기이므로 actor가 필요합니다. `?user=<actor>`를 붙이지
    않으면 403으로 거부되며, 그 거부 자체가 접근 통제가 동작한다는 증거입니다.

Both halves of that sentence were false for the first of the four links. Measured
at ``be501c5``, each fetched exactly as published with the actor parameter
removed::

    404 {'detail': 'dataset not found'}   /enterprise/connectors/sql_connector/probe?dataset_id=crm-customer-master
    403 {'detail': '카탈로그 접근은 ...'}  /policy/decisions
    403 {'detail': '카탈로그 접근은 ...'}  /audit/events
    403 {'detail': '카탈로그 접근은 ...'}  /ontology/change-log

and what each exit of the probe route files::

    404 anonymous, dataset exists  -> audit+0 decision+0
    404 anonymous, dataset absent  -> audit+0 decision+0
    200 allowed actor              -> audit+1 decision+1

The 404 is deliberate and must stay: the route resolves the dataset in the
caller's scope first so a foreign dataset and an absent one answer identically,
and that is a *stronger* control than a 403 - it is also nowhere published, so a
reader following the note sees 'dataset not found' and concludes the demo
dataset is missing. The second half is the defect this file is named for: the
refusal an unauthorized caller actually reaches was the one exit of three that
filed neither a policy decision nor an audit event, so 'the refusal itself is
the evidence' described a refusal that left none.

The existing guard
(``test_governed_write_evidence::test_every_published_proof_link_resolves_as_published``)
asserts ``pack["actor_scoped_proof_note"]`` - that the string is non-empty, never
that it is true.
"""

from __future__ import annotations

import re

from fastapi.testclient import TestClient

from sdp import catalog, evidence
from sdp.api import app


client = TestClient(app)

ABSENT_DATASET_ID = "proof-refusal-probe-absent-dataset"


def _without_actor(endpoint: str) -> str:
    return endpoint.replace("&user=<actor>", "").replace("?user=<actor>", "")


def _scoped_endpoints() -> list[str]:
    pack = client.get("/enterprise/evidence-pack").json()
    endpoints = pack["actor_scoped_proof_endpoints"]
    assert endpoints, pack
    return endpoints


def _ledger_sizes() -> tuple[int, int]:
    return (
        len(catalog.list_audit_events(limit=500)),
        len(evidence.list_policy_decisions(limit=500)),
    )


def test_every_actor_scoped_link_refuses_without_its_actor() -> None:
    """The premise of the note: these are governed reads, not open ones."""
    for endpoint in _scoped_endpoints():
        status = client.get(_without_actor(endpoint)).status_code
        assert status in {401, 403, 404}, (endpoint, status)


def test_the_note_names_every_refusal_status_its_links_actually_return() -> None:
    """The note said 403 for all four; one answers 404 by design.

    Asserted structurally rather than by pinning prose: whatever statuses the
    four links actually refuse with, the published explanation has to name them.
    A route that later changes its refusal status fails here until the note
    catches up.
    """
    pack = client.get("/enterprise/evidence-pack").json()
    note = pack["actor_scoped_proof_note"]
    observed = sorted(
        {client.get(_without_actor(endpoint)).status_code for endpoint in pack["actor_scoped_proof_endpoints"]}
    )
    # No ``\b`` on either side: the note writes ``403으로`` and a Korean
    # syllable is a word character, so a word-boundary pattern finds nothing
    # there - which made this guard report an empty set rather than a wrong one.
    named = {int(token) for token in re.findall(r"(?<!\d)([45]0[0-9])(?!\d)", note)}
    assert set(observed) == named, (
        f"the note names {sorted(named)} but the links refuse with {observed}"
    )


def test_each_refusal_files_at_least_one_evidence_row() -> None:
    """``그 거부 자체가 ... 증거입니다`` - so each refusal must leave a row.

    Deliberately **not** "both ledgers grow". The dataset audit ledger is keyed
    on a dataset (``catalog.ingest_event(resource=dataset_id)``) and three of the
    four links are plane-level reads of the ledgers themselves, which carry no
    dataset; their refusal correctly files one policy decision tagged
    ``resource: "evidence"`` and no audit event, and README documents that shape.
    Measured at ``be501c5``, demanding both would have failed all four and named
    three of them wrongly - a guard whose premise is wider than the thing it
    guards. The per-dataset link is checked against its own allow path below.
    """
    for endpoint in _scoped_endpoints():
        before = _ledger_sizes()
        response = client.get(_without_actor(endpoint))
        after = _ledger_sizes()
        assert response.status_code >= 400, (endpoint, response.status_code)
        assert sum(after) > sum(before), (
            f"refusal of {endpoint} filed no evidence at all: {before} -> {after}"
        )


def test_the_probes_refusal_files_what_its_own_allow_path_files() -> None:
    """The route says it is "gated and audited like the other governed reads".

    The expectation is read off the route's own allow exit rather than written
    here, so this stays true if the route's recording shape changes.
    """
    probe = "/enterprise/connectors/sql_connector/probe?dataset_id=crm-customer-master"

    before = _ledger_sizes()
    assert client.get(probe + "&user=admin").status_code == 200
    allowed = tuple(a - b for a, b in zip(_ledger_sizes(), before))

    before = _ledger_sizes()
    assert client.get(probe).status_code == 404
    refused = tuple(a - b for a, b in zip(_ledger_sizes(), before))

    assert allowed == (1, 1), f"the allow path changed shape: {allowed}"
    assert refused == allowed, (
        f"allow files {allowed} rows, the refusal files {refused}"
    )


def test_the_404_still_hides_which_of_the_two_causes_it_was() -> None:
    """The response must not start distinguishing absent from out-of-scope.

    The recording is what changes; the answer does not. If this ever diverges,
    an unauthorized caller can enumerate dataset existence through the probe.
    """
    probe = "/enterprise/connectors/sql_connector/probe?dataset_id="
    exists = client.get(probe + "crm-customer-master")
    absent = client.get(probe + ABSENT_DATASET_ID)
    assert exists.status_code == absent.status_code == 404, (
        exists.status_code,
        absent.status_code,
    )
    assert exists.json() == absent.json(), (exists.json(), absent.json())


def test_the_ledger_keeps_the_cause_the_response_withholds() -> None:
    """One indistinguishable answer to the caller, the true reason in the row."""
    probe = "/enterprise/connectors/sql_connector/probe?dataset_id="
    reasons = {}
    for label, dataset_id in (("exists", "crm-customer-master"), ("absent", ABSENT_DATASET_ID)):
        before = len(catalog.list_audit_events(limit=500))
        client.get(probe + dataset_id)
        rows = catalog.list_audit_events(limit=500)
        assert len(rows) > before
        row = next(row for row in rows if row.resource == dataset_id)
        assert row.result == "denied", row
        assert row.details.get("response_status") == 404, row.details
        reasons[label] = row.reason
    assert reasons["exists"] != reasons["absent"], (
        "the ledger merged the two causes the response is allowed to merge: "
        f"{reasons}"
    )
