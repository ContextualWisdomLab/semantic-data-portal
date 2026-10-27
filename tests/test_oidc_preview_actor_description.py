"""The published ``actor`` description must name every key the actor changes.

``POST /enterprise/auth/oidc-preview`` accepts a claim set with or without an
``actor`` and answers 200 either way - that part of the description is right,
and it was written to correct a worse sentence copied from five sibling mutation
routes ("없으면 anonymous로 취급되어 거부됩니다", false here).

What it then claims is that the only thing an actor changes is
``audit_recorded``. Measured, that is false in **both** configurations:

    SDP_OIDC_GROUP_ROLE_MAP set (the operator/production case), 5 keys:
        actor_context, audit_event_id, audit_recorded,
        group_role_bindings, role_map_source

        no actor  -> role_map_source 'withheld_operator_configured_map_requires_an_actor'
                     group_role_bindings [{'group_name': 'admins',
                                           'tenant_scope': '', 'granted_roles': []}]
        actor     -> role_map_source 'operator_configured'
                     group_role_bindings [{'group_name': 'admins',
                                           'tenant_scope': 'acme-finance',
                                           'granted_roles': ['platform-admin']}]

    no operator map (the shipped default), 2 keys:
        audit_event_id, audit_recorded

So an operator debugging "why does the preview show no roles" is pointed away
from the one input that caused it, and a reader auditing the
enumeration-oracle fix is told the fix has no observable effect. Even the
default case is not "only ``audit_recorded``" - the audit row's id appears with
it.

This guard reads the keys **out of the published description** and compares them
to the keys a measured A/B actually changes. The description is prose, so the
comparison is on the backticked identifiers it names; naming a key it does not
change is allowed (the prose may mention more), omitting one that changes is
not.
"""

from __future__ import annotations

import json
import os
import re
import time

import pytest
from fastapi.testclient import TestClient

from sdp.api import app
from sdp.api_request_contract import REQUEST_BODY_EXTRA_PROPERTIES

client = TestClient(app)

_ROUTE = ("POST", "/enterprise/auth/oidc-preview")
_OPERATOR_MAP = {"acme-finance": {"admins": ["platform-admin"]}}


def _claims() -> dict[str, object]:
    """A complete, unexpired claim set the route can map."""
    return {
        "sub": "u1",
        "tenant_id": "acme-finance",
        "groups": ["admins"],
        "exp": int(time.time()) + 3600,
    }


def _actor_sensitive_keys() -> set[str]:
    """Response keys whose value depends on whether an ``actor`` was sent."""
    answers = {}
    for label, actor in (("without", None), ("with", "external-analyst")):
        payload: dict[str, object] = {"claims": _claims()}
        if actor is not None:
            payload["actor"] = actor
        response = client.post("/enterprise/auth/oidc-preview", json=payload)
        assert response.status_code == 200, response.text
        answers[label] = response.json()
    return {
        key
        for key in set(answers["without"]) | set(answers["with"])
        if answers["without"].get(key) != answers["with"].get(key)
    }


def _described_keys() -> set[str]:
    """Backticked identifiers the published ``actor`` description names."""
    description = REQUEST_BODY_EXTRA_PROPERTIES[_ROUTE]["actor"]["description"]
    return set(re.findall(r"`([A-Za-z_][A-Za-z0-9_]*)`", description))


def test_the_default_configuration_changes_more_than_one_key() -> None:
    """The premise, measured, so the comparison below is not vacuous."""
    changed = _actor_sensitive_keys()
    assert "audit_recorded" in changed, changed
    assert changed == {"audit_event_id", "audit_recorded"}, (
        "the shipped default's actor-sensitive key set moved; this guard's "
        f"description of it needs updating: {sorted(changed)}"
    )


def test_the_description_names_every_key_the_actor_changes_by_default() -> None:
    """Document against behaviour, in the configuration the tests run in."""
    missing = sorted(_actor_sensitive_keys() - _described_keys())
    assert not missing, (
        "the published actor description does not name these keys, which an "
        f"actor does change: {missing}. Named: {sorted(_described_keys())}"
    )


def test_the_description_names_every_key_the_actor_changes_under_an_operator_map(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The production case, which is what the route's security comment is for."""
    monkeypatch.setenv("SDP_OIDC_GROUP_ROLE_MAP", json.dumps(_OPERATOR_MAP))
    changed = _actor_sensitive_keys()
    # The premise again: the operator map must actually be in effect, or this
    # measures the default a second time and agrees with itself.
    assert "role_map_source" in changed, (
        "the operator map is not in effect, so this guard is measuring the "
        f"default configuration twice: {sorted(changed)}"
    )
    missing = sorted(changed - _described_keys())
    assert not missing, (
        "under an operator-configured role map the actor changes these keys and "
        f"the published description names none of them: {missing}. "
        f"Named: {sorted(_described_keys())}"
    )
