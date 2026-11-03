"""A hypothetical policy answer was recorded as an ordinary decision.

``POST /policy/decision`` answers "what would policy say for this subject", and
``subject`` is caller-supplied by design. The row it writes lands in the
**subject's** tenant ledger, so the ``provenance`` labels exist precisely to stop
an auditor reading a question as an event: ``evaluation_mode: hypothetical``,
``asked_by`` (who really asked) and ``subject_is_caller``. ``CHANGELOG.md``
records adding them.

Three branches of ``policy.evaluate`` never received them. Measured at
``c4ac6b5`` as ``user=analyst`` asking about ``subject=external-analyst`` — the
labels present on the hypothetical row::

    discover_catalog  allow  labels: []                                        <- unlabelled
    register_dataset  deny   labels: []                                        <- unlabelled
    search            allow  labels: []                                        <- unlabelled
    preview           deny   labels: ['asked_by', 'evaluation_mode', 'subject_is_caller']

So the external tenant's steward reads an ``allow`` on catalog discovery and a
``deny`` on dataset registration, both naming their own user as the subject, with
nothing anywhere recording that a different tenant's analyst asked the question.
The branches were ``create``'s two denials (``policy.py:321``, ``:333``) and the
``search``/``search_catalog``/``discover`` **allow** (``:352``).

The parametrize is derived from the engine's own ``KNOWN_ACTIONS`` and
``CATALOG_ACTION_ALIASES`` rather than from a list of the three branches found,
because a list of known branches is how the next one goes unlabelled.
"""

from __future__ import annotations

import ast
import pathlib

from typing import Any

import pytest

from fastapi.testclient import TestClient

from sdp import evidence, policy
from sdp.api import app


client = TestClient(app)

PROVENANCE_KEYS = {"evaluation_mode", "asked_by", "subject_is_caller"}
CALLER = "analyst"
OTHER_TENANT_SUBJECT = "external-analyst"

# Every spelling the engine accepts, from the engine.
EVERY_ACTION = sorted(policy.KNOWN_ACTIONS | set(policy.CATALOG_ACTION_ALIASES))


def _hypothetical_rows(action: str, *, resource: str) -> list[dict[str, Any]]:
    """Ask about another subject and return the rows that answer about them."""
    before = len(evidence._POLICY_DECISION_LOG)
    response = client.post(
        "/policy/decision",
        json={
            "user": CALLER,
            "subject": OTHER_TENANT_SUBJECT,
            "resource": resource,
            "action": action,
            "purpose": "analysis",
        },
    )
    assert response.status_code == 200, (action, response.text)
    rows = [
        row if isinstance(row, dict) else row.model_dump()
        for row in evidence._POLICY_DECISION_LOG[before:]
    ]
    # The caller's own authorization to use the route is also recorded and is not
    # hypothetical; the answer is the row about the named subject.
    return [row for row in rows if row.get("subject") == OTHER_TENANT_SUBJECT]


@pytest.mark.parametrize("action", EVERY_ACTION)
# An unknown dataset id is refused with 404 before any answer exists - the
# existence-oracle contract - so it is not a resource this guard can drive. The
# first version parametrized it and read 19 failures that were all that refusal;
# it is asserted on its own below instead.
@pytest.mark.parametrize("resource", ("catalog", "crm-customer-master"))
def test_every_action_records_its_hypothetical_answer_as_hypothetical(
    action: str, resource: str
) -> None:
    """One label set, on every branch, for every action the engine knows."""
    rows = _hypothetical_rows(action, resource=resource)
    assert rows, (action, resource, "no row was recorded about the named subject")
    for row in rows:
        obligations = row.get("obligations") or {}
        missing = sorted(PROVENANCE_KEYS - set(obligations))
        assert not missing, (
            f"action={action!r} resource={resource!r} effect={row.get('effect')!r} "
            f"recorded an answer about {OTHER_TENANT_SUBJECT!r} with no record that "
            f"{CALLER!r} asked it: missing {missing}"
        )
        assert obligations["evaluation_mode"] == "hypothetical", obligations
        assert obligations["asked_by"] == CALLER, obligations
        assert obligations["subject_is_caller"] is False, obligations


def test_an_unknown_dataset_id_is_refused_before_any_answer_is_recorded() -> None:
    """And the refusal does not leave an unlabelled row behind either."""
    before = len(evidence._POLICY_DECISION_LOG)
    response = client.post(
        "/policy/decision",
        json={
            "user": CALLER,
            "subject": OTHER_TENANT_SUBJECT,
            "resource": "no-such-dataset-anywhere",
            "action": "preview",
            "purpose": "analysis",
        },
    )
    assert response.status_code == 404, response.text
    rows = [
        row if isinstance(row, dict) else row.model_dump()
        for row in evidence._POLICY_DECISION_LOG[before:]
    ]
    for row in rows:
        if row.get("subject") != OTHER_TENANT_SUBJECT:
            continue
        obligations = row.get("obligations") or {}
        assert PROVENANCE_KEYS.issubset(obligations), (
            f"the refusal recorded an unlabelled answer about {OTHER_TENANT_SUBJECT!r}: {obligations}"
        )


def test_a_caller_asking_about_itself_is_still_labelled_as_a_question() -> None:
    """The distinction is question-versus-event, not whose question it is."""
    before = len(evidence._POLICY_DECISION_LOG)
    response = client.post(
        "/policy/decision",
        json={"user": CALLER, "resource": "catalog", "action": "search", "purpose": "analysis"},
    )
    assert response.status_code == 200, response.text
    rows = [
        row if isinstance(row, dict) else row.model_dump()
        for row in evidence._POLICY_DECISION_LOG[before:]
    ]
    answers = [row for row in rows if (row.get("obligations") or {}).get("evaluation_mode")]
    assert answers, rows
    for row in answers:
        obligations = row["obligations"]
        assert obligations["subject_is_caller"] is True, obligations
        assert obligations["asked_by"] == CALLER, obligations


def test_an_ordinary_governed_read_is_not_labelled_hypothetical() -> None:
    """The labels must mark questions only, or they mean nothing.

    A guard that only demanded "more labels" would pass an implementation that
    stamped every decision in the ledger as hypothetical, which would make every
    real access look like a question.
    """
    before = len(evidence._POLICY_DECISION_LOG)
    read = client.post(
        "/browse/crm-customer-master/preview",
        json={"user": "analyst", "purpose": "analysis", "limit": 2},
    )
    assert read.status_code == 200, read.text
    rows = [
        row if isinstance(row, dict) else row.model_dump()
        for row in evidence._POLICY_DECISION_LOG[before:]
    ]
    assert rows, "the read must still be recorded"
    for row in rows:
        obligations = row.get("obligations") or {}
        assert not PROVENANCE_KEYS.intersection(obligations), (
            f"a real governed read was labelled as a hypothetical question: {obligations}"
        )


def test_no_branch_of_evaluate_can_omit_the_provenance_argument() -> None:
    """Structural, because the behavioural guard can only reach live branches.

    Three of fifteen ``_decision`` calls omitted it. Walking the AST is what makes
    a sixteenth branch unable to.
    """
    tree = ast.parse(pathlib.Path(policy.__file__).read_text(encoding="utf-8"))
    function = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "evaluate"
    )
    offenders = [
        node.lineno
        for node in ast.walk(function)
        if isinstance(node, ast.Call)
        and getattr(node.func, "id", "") == "_decision"
        and "provenance" not in [keyword.arg for keyword in node.keywords]
    ]
    assert not offenders, (
        "these decision branches drop the caller's provenance, so the row they "
        f"write cannot be told from a real event: lines {offenders}"
    )
    # And the guard must be measuring something: the calls exist.
    calls = [
        node
        for node in ast.walk(function)
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "_decision"
    ]
    assert len(calls) >= 10, len(calls)
