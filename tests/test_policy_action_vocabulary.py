"""The policy engine must not answer "allow" to an action it cannot evaluate.

``evaluate`` ran a chain of branches and fell through to ``allow`` at the end, so
any action it did not recognize was permitted. Measured before the repair:

    evaluate(subject="analyst", action="administer_tenants", ...) -> allow
    evaluate(subject="analyst", action="totally_made_up",    ...) -> allow

``POST /policy/decision`` takes ``action`` verbatim from an unauthenticated
request body, so the published decision API answered ``allow`` for anything and
recorded that answer in the evidence ledger.

A second defect compounded it: the RBAC matrix's ``action_catalog`` is spelled
``verb_noun`` (``patch_dataset``) while the engine matched bare verbs
(``patch``), so **all ten** published action names were unrecognized - including
the four the matrix publishes as denied to ``data-analyst``, and
``administer_tenants``. Every published cell therefore resolved to ``allow`` for
every role with any read grant.

Both halves are checked here by enumerating the published matrix against the
engine, cell by cell, rather than by spot-checking the one action that was
reported.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from sdp.api import app
from sdp.authz import resolve_actor_context
from sdp.policy import (
    CATALOG_ACTION_ALIASES,
    KNOWN_ACTIONS,
    UNMAPPED_CATALOG_ACTIONS,
    evaluate,
)
from sdp_core.rbac import enterprise_rbac_matrix


client = TestClient(app)
DATASET = "crm-customer-master"

# Subjects whose seeded role bundle is exactly the matrix row, so a disagreement
# is attributable to the engine rather than to the seed. `security` and
# `platform-admin` have no such subject - see
# test_the_seed_has_no_clean_subject_for_two_published_rows.
CLEAN_ROW_SUBJECTS = {"data-analyst": "analyst", "admin": "data-admin"}


def _effect(subject: str, action: str) -> str:
    return evaluate(
        subject=subject, resource=DATASET, action=action, purpose="analysis"
    ).effect


def test_an_unrecognized_action_is_denied() -> None:
    """Fail closed, and say what is evaluable."""
    decision = evaluate(
        subject="admin", resource=DATASET, action="totally_made_up", purpose="analysis"
    )
    assert decision.effect == "deny"
    assert decision.obligations["known_actions"] == sorted(KNOWN_ACTIONS)

    # Including through the published HTTP decision API, unauthenticated.
    response = client.post(
        "/policy/decision",
        json={
            "subject": "analyst",
            "resource": DATASET,
            "action": "totally_made_up",
            "purpose": "analysis",
        },
    )
    assert response.status_code == 200
    assert response.json()["effect"] == "deny", response.text


def test_the_published_matrix_is_evaluable_and_agrees_for_every_clean_row() -> None:
    """Every (role, action) cell the seed can represent cleanly."""
    matrix = enterprise_rbac_matrix()
    disagreements = []
    for role in matrix.roles:
        subject = CLEAN_ROW_SUBJECTS.get(role.role)
        if subject is None:
            continue
        for action in matrix.action_catalog:
            if action in UNMAPPED_CATALOG_ACTIONS:
                continue
            expected = (
                "allow"
                if action in role.allowed_actions
                else "deny"
                if action in role.denied_actions
                else None
            )
            if expected is None:
                continue
            actual = _effect(subject, action)
            if actual != expected:
                disagreements.append(
                    f"{role.role}/{action}: matrix says {expected}, engine says {actual}"
                )
    assert not disagreements, (
        "the published RBAC matrix disagrees with the engine that is supposed to "
        "implement it:\n  " + "\n  ".join(disagreements)
    )


def _published_action_enum() -> list[str]:
    """The ``action`` enum as the live OpenAPI document publishes it."""
    spec = client.get("/openapi.json").json()
    schema = (
        spec["paths"]["/policy/decision"]["post"]["requestBody"]["content"][
            "application/json"
        ]["schema"]
    )
    enum = schema["properties"]["action"].get("enum")
    assert enum, f"the action enum is no longer published: {schema['properties']['action']}"
    return list(enum)


def test_every_value_the_document_publishes_is_one_the_route_can_evaluate() -> None:
    """Document against behaviour, which is a different pair from the guard above.

    The guard above compares the **matrix** to the engine's own sets, and the
    enum is *derived* from those sets rather than restated - so neither of them
    asks the question a client asks: does the value this document advertises
    actually work when posted?

    "Derived from the engine's vocabulary" answers that only if the engine's
    sets are what the route accepts, which is an assumption. A handler that
    narrowed its acceptance, or a set that stopped matching the handler, would
    leave the document advertising a value that answers ``평가할 수 없는
    action입니다.`` - and nothing would notice, because the enum and the sets
    would still agree with each other.

    Measured when this was added: all 19 published values evaluate, none
    refused. And it cannot fail while the derivation stands - removing an alias
    from the engine removes it from the enum too, so the document and the route
    narrow together and this guard has nothing left to catch. That is why the
    next test asserts the derivation itself: this one is the protection that
    activates the moment the enum becomes a literal, and that one is what
    notices the moment it does. Stated rather than left implied, because a
    guard that cannot fail today reads like a guard that works.
    """
    refused = []
    for action in _published_action_enum():
        response = client.post(
            "/policy/decision",
            json={
                "subject": "admin",
                "resource": "crm-customer-master",
                "action": action,
                "purpose": "analysis",
            },
        )
        if response.status_code != 200:
            refused.append(f"{action}: HTTP {response.status_code}")
            continue
        body = response.json()
        if "평가할 수 없는 action" in str(body.get("reason", "")):
            refused.append(f"{action}: {body.get('reason')}")
    assert not refused, (
        "the document publishes these as acceptable ``action`` values and the "
        f"route cannot evaluate them: {refused}"
    )


def test_the_published_enum_is_not_narrower_than_the_vocabulary_it_derives_from() -> None:
    """The reverse direction, as far as it can honestly be checked.

    The enum derives from ``KNOWN_ACTIONS | CATALOG_ACTION_ALIASES``, so
    comparing it to those sets is comparing a value with its own source - it
    cannot fail while the derivation stands, and that is exactly what this
    asserts: that the derivation still stands. If someone replaces the derived
    expression with a hand-written list, this reddens, and the test above then
    becomes the one that matters.
    """
    assert set(_published_action_enum()) == set(KNOWN_ACTIONS) | set(
        CATALOG_ACTION_ALIASES
    ), (
        "the published enum is no longer the engine's vocabulary; if it was "
        "replaced with a literal list, every value now needs the end-to-end "
        "check above rather than a derivation to lean on"
    )


def test_every_published_action_resolves_to_a_known_action_or_a_declared_gap() -> None:
    """No published name may be silently unrecognized.

    This is the structural guard: an action added to the matrix without a mapping
    fails here instead of resolving to "unknown action" at runtime, which is how
    all ten names came to be unrecognized in the first place.
    """
    unresolved = [
        action
        for action in enterprise_rbac_matrix().action_catalog
        if action not in KNOWN_ACTIONS
        and action not in CATALOG_ACTION_ALIASES
        and action not in UNMAPPED_CATALOG_ACTIONS
    ]
    assert not unresolved, (
        "published action names the engine cannot evaluate and that are not "
        f"declared as gaps: {unresolved}"
    )


def test_the_two_unmapped_actions_refuse_with_their_own_reason() -> None:
    """A declared gap must read as a gap, not as a typo."""
    assert UNMAPPED_CATALOG_ACTIONS == {"administer_tenants", "review_security_evidence"}
    for action in sorted(UNMAPPED_CATALOG_ACTIONS):
        for subject in ("analyst", "admin", "security"):
            decision = evaluate(
                subject=subject, resource=DATASET, action=action, purpose="analysis"
            )
            assert decision.effect == "deny", f"{subject}/{action}"
            assert decision.obligations["unmapped_published_action"] == action
            assert "known_actions" not in decision.obligations, (
                "a declared gap must not be reported as an unknown action"
            )


def test_an_alias_decides_identically_to_the_action_it_names() -> None:
    """Two spellings of one action must not become two policies."""
    for alias, internal in sorted(CATALOG_ACTION_ALIASES.items()):
        assert internal in KNOWN_ACTIONS, f"{alias} aliases unknown action {internal}"
        for subject in ("analyst", "data-admin", "security", "nobody"):
            assert _effect(subject, alias) == _effect(subject, internal), (
                f"{subject}: {alias} and {internal} disagree"
            )


def test_the_seed_has_no_clean_subject_for_two_published_rows() -> None:
    """Recorded, not worked around: why two matrix rows are untested above.

    No seeded subject holds exactly the ``security`` or ``platform-admin`` role
    bundle - ``security`` also carries ``platform-admin``, and the only
    ``platform-admin`` subject also carries ``admin`` and ``data-analyst``. So a
    disagreement on those rows cannot be attributed to the engine rather than to
    the seed, and whether ``security`` should hold ``platform-admin`` at all is an
    open product question rather than an engine defect.
    """
    security = resolve_actor_context("security")
    assert "security" in security.roles
    assert "platform-admin" in security.roles, (
        "if this bundle is ever narrowed, add 'security' to CLEAN_ROW_SUBJECTS "
        "and let the matrix comparison cover its row"
    )

    admin = resolve_actor_context("admin")
    assert {"admin", "data-analyst", "platform-admin"} <= set(admin.roles)

    clean = resolve_actor_context("data-admin")
    assert "platform-admin" not in clean.roles, (
        "data-admin must stay free of platform-admin to represent the admin row"
    )
