"""Bounds on caller-controlled work and caller-driven memory growth.

Each contract here was measured as unbounded first, at HEAD, with real numbers:

* ``POST /search/semantic`` declared ``min_length=1`` and no ``max_length``;
  ``embed_text`` builds one string and one MD5 per character position, so a
  2 MiB query burned 2.87s of CPU per request.
* ``catalog.search_catalog`` compiled a fresh regex per (dataset x token):
  1005 datasets took 0.03s at 10 tokens, 1.39s at 500 and 5.10s at 2000.
* ``POST /ontology/patches`` ran **no** ``policy.evaluate`` at all (measured:
  5 anonymous proposals, policy-decision delta 0) and appended unbounded caller
  strings to a process-lifetime list (a 50,000-character suggestion was kept).
* ``browse.preview`` wrote an audit event for a dataset that does not exist
  *before* any policy evaluation: 5 anonymous calls gave audit +5, policy +0 —
  an unauthenticated caller growing the ledger, and the documented
  policy-before-access order inverted.
"""

from __future__ import annotations

from pathlib import Path
import sys

from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sdp import catalog, evidence, ontology  # noqa: E402
from sdp.api import app  # noqa: E402
from sdp.graph_models import SemanticSearchRequest  # noqa: E402

client = TestClient(app)


@pytest.fixture(autouse=True)
def _isolate():
    data = {k: v.model_copy(deep=True) for k, v in catalog._DATA.items()}
    audit = list(catalog._AUDIT_LOG)
    decisions = list(evidence._POLICY_DECISION_LOG)
    # The cap test below writes ~2050 events; without restoring this list they
    # stayed in it for every later test in the session.
    recorded_audit = list(evidence._AUDIT_EVENT_LOG)
    patches = [p.model_copy(deep=True) for p in ontology._ONTOLOGY_PATCHES]
    # register_concept mutates these, so a test that publishes a concept
    # would otherwise leak it into every later test.
    concept_definitions = deepcopy(ontology._CONCEPT_DEFINITIONS)
    alias_to_canonical = dict(ontology._ALIAS_TO_CANONICAL)
    try:
        yield
    finally:
        catalog._DATA.clear()
        catalog._DATA.update(data)
        catalog._AUDIT_LOG[:] = audit
        evidence._POLICY_DECISION_LOG[:] = decisions
        evidence._AUDIT_EVENT_LOG[:] = recorded_audit
        ontology._ONTOLOGY_PATCHES[:] = patches
        ontology._CONCEPT_DEFINITIONS.clear()
        ontology._CONCEPT_DEFINITIONS.update(concept_definitions)
        ontology._ALIAS_TO_CANONICAL.clear()
        ontology._ALIAS_TO_CANONICAL.update(alias_to_canonical)


def test_semantic_search_query_is_length_bounded() -> None:
    """The only bound was ``min_length=1``."""
    constraints = repr(SemanticSearchRequest.model_fields["query"].metadata)
    assert "MaxLen" in constraints, constraints

    oversized = client.post(
        "/search/semantic", json={"actor": "analyst", "query": "x" * 100_000, "limit": 3}
    )
    assert oversized.status_code == 422

    normal = client.post(
        "/search/semantic", json={"actor": "analyst", "query": "고객 이탈", "limit": 3}
    )
    assert normal.status_code == 200


def test_catalog_search_query_is_length_bounded() -> None:
    """Note on exploitability: a very long query string is refused client-side by
    httpx (and by any real edge with a request-line limit) before it reaches the
    app, so the measured 5.10s case is reachable in-process rather than over HTTP.
    The server-side bound is still asserted here, just above the cap.
    """
    oversized = client.get("/catalog/search", params={"q": "고객 " * 800, "user": "analyst"})
    assert oversized.status_code == 422, oversized.text
    assert client.get("/catalog/search", params={"q": "고객", "user": "analyst"}).status_code == 200


def test_catalog_search_compiles_each_token_once() -> None:
    """The regex was compiled inside the per-dataset loop, so the cost was
    datasets x tokens rather than tokens."""
    import re

    base = catalog._DATA["crm-customer-master"]
    for n in range(40):
        catalog._DATA[f"bulk-{n}"] = base.model_copy(update={"id": f"bulk-{n}"})

    compiles = 0
    real_compile = re.compile

    def counting_compile(*args, **kwargs):
        nonlocal compiles
        compiles += 1
        return real_compile(*args, **kwargs)

    original = catalog.re.compile
    catalog.re.compile = counting_compile
    try:
        catalog.search_catalog("고객 이탈 전환", limit=5)
    finally:
        catalog.re.compile = original

    # Three tokens over 45 datasets: a per-dataset compile would be ~135.
    assert compiles <= 10, compiles


def test_ontology_patch_proposal_is_policy_evaluated_and_bounded() -> None:
    # The monotonic counter, not ``len(_POLICY_DECISION_LOG)``: the window is
    # capped, so once a process has passed the cap its length never rises again
    # and a length comparison reads as "nothing was recorded" for every write
    # after that. This assertion failed in the full suite for exactly that
    # reason while passing in isolation.
    before = evidence.recorded_policy_decision_count()
    anonymous = client.post("/ontology/patches", json={"concept": "고객", "suggestion": "s"})
    assert anonymous.status_code == 403, anonymous.text
    assert evidence.recorded_policy_decision_count() > before, "the denial must be recorded"

    oversized = client.post(
        "/ontology/patches",
        json={"actor": "analyst", "concept": "고객", "suggestion": "s" * 50_000},
    )
    assert oversized.status_code == 400

    accepted = client.post(
        "/ontology/patches",
        json={"actor": "analyst", "concept": "고객", "suggestion": "정상 제안"},
    )
    assert accepted.status_code == 200


def test_ontology_patch_queue_is_capped() -> None:
    for index in range(ontology.MAX_ONTOLOGY_PATCHES + 5):
        ontology.propose_patch(concept="고객", suggestion=f"s{index}", requestor="analyst")
    assert len(ontology._ONTOLOGY_PATCHES) <= ontology.MAX_ONTOLOGY_PATCHES


def test_preview_of_a_missing_dataset_evaluates_policy_before_writing_evidence() -> None:
    """The documented invariant is policy-before-access; the missing-dataset
    branch wrote the audit event first and evaluated nothing."""
    before_audit = evidence.recorded_audit_event_count()
    before_policy = evidence.recorded_policy_decision_count()
    response = client.post(
        "/browse/no-such-dataset/preview", json={"user": "anonymous", "purpose": "analysis"}
    )
    assert response.status_code == 404
    assert evidence.recorded_policy_decision_count() > before_policy, "policy must be evaluated"
    assert evidence.recorded_audit_event_count() - before_audit == 1


def test_in_memory_audit_log_is_capped() -> None:
    """The in-memory fallback logs were unbounded lists, so a caller that can
    reach any audited route could grow process memory without limit.

    This test used to assert the cap on ``catalog._AUDIT_LOG`` alone, and that
    is why capping one of the two lists shipped as a memory bound.
    ``catalog._record_audit_event`` writes each event to *both* lists, and
    ``evidence._AUDIT_EVENT_LOG`` had no cap at all. Measured over 2600 refused
    ``POST /browse/crm-customer-master/preview`` calls with no store configured:
    ``catalog._AUDIT_LOG`` 2000, ``evidence._AUDIT_EVENT_LOG`` 2600. Both are
    asserted below, and both read the same imported constant.
    """
    assert catalog.MAX_IN_MEMORY_AUDIT_EVENTS is evidence.MAX_IN_MEMORY_AUDIT_EVENTS

    for index in range(evidence.MAX_IN_MEMORY_AUDIT_EVENTS + 50):
        catalog.ingest_event(
            event_type="probe.growth",
            actor="analyst",
            dataset_id="crm-customer-master",
            decision="allowed",
            reason="probe",
        )
    assert len(catalog._AUDIT_LOG) <= evidence.MAX_IN_MEMORY_AUDIT_EVENTS
    assert len(evidence._AUDIT_EVENT_LOG) <= evidence.MAX_IN_MEMORY_AUDIT_EVENTS


def test_a_trimmed_ledger_can_still_answer_whether_a_write_happened() -> None:
    """Trimming must not make the evidence ledger unfalsifiable.

    A bounded window reports a constant length once it is full, so "was this
    decision recorded?" has no answer from the window alone - and the answer it
    implies is the wrong one, "no". The monotonic counters keep the question
    answerable, which is what the two assertions above now rely on.
    """
    evidence._POLICY_DECISION_LOG[:] = []
    evidence._AUDIT_EVENT_LOG[:] = []

    for index in range(evidence.MAX_IN_MEMORY_POLICY_DECISIONS + 25):
        catalog.ingest_event(
            event_type="probe.counter",
            actor="analyst",
            dataset_id="crm-customer-master",
            decision="allowed",
            reason="probe",
        )

    saturated = len(evidence._AUDIT_EVENT_LOG)
    assert saturated == evidence.MAX_IN_MEMORY_AUDIT_EVENTS

    before_window = len(evidence._AUDIT_EVENT_LOG)
    before_count = evidence.recorded_audit_event_count()
    catalog.ingest_event(
        event_type="probe.counter",
        actor="analyst",
        dataset_id="crm-customer-master",
        decision="allowed",
        reason="one more",
    )
    # The window cannot see the write; the counter can.
    assert len(evidence._AUDIT_EVENT_LOG) == before_window
    assert evidence.recorded_audit_event_count() == before_count + 1
