"""Two defects on ``POST /enterprise/auth/oidc-preview``, an unauthenticated route.

**It was an enumeration oracle over the operator's group-to-role map.** With
``SDP_OIDC_GROUP_ROLE_MAP={"acme-finance": {"admins": ["platform-admin"]}}`` and
no credential of any kind, measured before the repair::

    POST /enterprise/auth/oidc-preview
      {"claims": {"sub": "attacker@evil.example", "tenant_id": "acme-finance",
                  "groups": ["admins"], "exp": <future>}}
    -> 200 {"actor_context": {"subject": "attacker@evil.example",
                              "tenant_id": "acme-finance",
                              "roles": ["platform-admin"]},
            "group_role_bindings": [{"group_name": "admins",
                                     "tenant_scope": "acme-finance",
                                     "granted_roles": ["platform-admin"]}]}

An unmapped group came back with an empty scope and no roles, so the two were
distinguishable and an outsider could read the deployment's whole group -> role
policy, and its valid tenant scopes, one guessed group name at a time. The trust
anchors are already refused from the request body for a related reason, and the
ledger write on this same route already requires an actor; reading the
configured map back is the same category.

The repair is narrow on purpose. A caller previewing against a role map **they
supplied** learns nothing - that is the route's stated purpose. The **shipped
default** map is not a secret either: it is a constant in ``authz.py``, public
and in the repository, and it is what makes the demo preview work with no
configuration. Only the deployment's own ``SDP_OIDC_GROUP_ROLE_MAP`` is
withheld, and only from a caller with no actor.

**It was an unauthenticated amplifier.** The group claim was unbounded in count
and in per-value length, and each name came back twice - in ``groups`` and in
``group_role_bindings[].group_name``. Measured, one request each::

    groups      10  ->   1,162 bytes      16 ms
    groups   1,000  ->  72,262 bytes       9 ms
    groups  20,000  -> 1.50 MB           135 ms
    groups 100,000  -> 7.58 MB           642 ms
    one 2 MB group name -> 4.00 MB        31 ms   (response larger than request)

Same defect class as the unbounded observation row in ``observability.py``,
reached through a different surface.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
from time import time

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sdp import authz  # noqa: E402
from sdp.api import app  # noqa: E402

client = TestClient(app)

OPERATOR_MAP = {"acme-finance": {"admins": ["platform-admin"]}}


def _preview(**body) -> dict:
    claims = {
        "sub": "probe@example.com",
        "tenant_id": "acme-finance",
        "exp": int(time()) + 3600,
        "groups": [],
    }
    claims.update(body.pop("claims", {}))
    response = client.post("/enterprise/auth/oidc-preview", json={"claims": claims, **body})
    assert response.status_code == 200, response.text
    return response.json()


# --------------------------------------------------------------------------- #
# The oracle
# --------------------------------------------------------------------------- #


def test_an_outsider_cannot_read_the_operator_configured_map(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SDP_OIDC_GROUP_ROLE_MAP", json.dumps(OPERATOR_MAP))
    body = _preview(claims={"groups": ["admins"]})
    assert body["actor_context"]["roles"] == [], body
    assert body["role_map_source"] == "withheld_operator_configured_map_requires_an_actor"
    assert body["group_role_bindings"] == [
        {"group_name": "admins", "tenant_scope": "", "granted_roles": []}
    ], body


def test_a_mapped_group_is_indistinguishable_from_an_unmapped_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The property that makes it an oracle, closed.

    Enumeration needs the two answers to differ. Everything but the echoed name
    must be byte-identical, which is the same rule this product applies to a
    foreign dataset id versus an absent one.
    """
    monkeypatch.setenv("SDP_OIDC_GROUP_ROLE_MAP", json.dumps(OPERATOR_MAP))

    def row(group: str) -> dict:
        binding = _preview(claims={"groups": [group]})["group_role_bindings"][0]
        return {key: value for key, value in binding.items() if key != "group_name"}

    assert row("admins") == row("definitely-not-a-group")


def test_an_operator_still_reads_the_configured_map(monkeypatch: pytest.MonkeyPatch) -> None:
    """The capability is preserved for the role it exists for."""
    monkeypatch.setenv("SDP_OIDC_GROUP_ROLE_MAP", json.dumps(OPERATOR_MAP))
    body = _preview(actor="admin", claims={"groups": ["admins"]})
    assert body["actor_context"]["roles"] == ["platform-admin"]
    assert body["role_map_source"] == "operator_configured"
    assert body["audit_recorded"] is True


def test_a_request_supplied_map_still_works_without_an_actor() -> None:
    """Previewing against a candidate map discloses nothing the caller lacks."""
    body = _preview(
        claims={"tenant_id": "demo", "groups": ["g"]},
        role_map={"demo": {"g": ["data-analyst"]}},
    )
    assert body["actor_context"]["roles"] == ["data-analyst"]
    assert body["role_map_source"] == "request"


def test_the_shipped_default_map_is_not_withheld(monkeypatch: pytest.MonkeyPatch) -> None:
    """It is a public constant, and withholding it would break the demo path.

    Deliberately narrow: the fix withholds the deployment's secret, not the
    repository's documented default.
    """
    monkeypatch.delenv("SDP_OIDC_GROUP_ROLE_MAP", raising=False)
    assert authz.oidc_role_map_is_operator_configured() is False
    body = _preview(claims={"tenant_id": "demo", "groups": ["sdp-analysts"]})
    assert body["role_map_source"] == "shipped_default"
    assert body["actor_context"]["roles"] == ["data-analyst"]


def test_an_anonymous_actor_name_does_not_pass_for_an_actor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One predicate gates both the map and the ledger write on this route."""
    monkeypatch.setenv("SDP_OIDC_GROUP_ROLE_MAP", json.dumps(OPERATOR_MAP))
    for actor in ("anonymous", "no-such-user"):
        body = _preview(actor=actor, claims={"groups": ["admins"]})
        assert body["actor_context"]["roles"] == [], (actor, body)
        assert body["audit_recorded"] is False, actor
        assert body["role_map_source"].startswith("withheld"), actor


def test_the_previewed_context_says_it_is_not_a_resolved_one() -> None:
    """It is shaped exactly like a resolved ``ActorContext``.

    No signature is checked here, so the subject, tenant and roles are what a
    token carrying these claims *would* map to.
    """
    body = _preview()
    assert body["actor_context_verified"] is False
    assert body["token_verification"] == "external_signature_required_claim_shape_validated"


# --------------------------------------------------------------------------- #
# The amplifier
# --------------------------------------------------------------------------- #


def test_the_group_claim_is_bounded_in_count_and_the_truncation_declared() -> None:
    body = _preview(claims={"groups": [f"g-{index}" for index in range(50_000)]})
    assert len(body["group_role_bindings"]) == authz.MAX_CLAIM_VALUES
    assert len(body["groups"]) == authz.MAX_CLAIM_VALUES
    assert body["declared_group_count"] == 50_000
    assert body["withheld_group_count"] == 50_000 - authz.MAX_CLAIM_VALUES


def test_one_group_name_is_bounded_in_length_with_a_marker() -> None:
    """A silently shortened name reads as the whole name."""
    body = _preview(claims={"groups": ["g" * 2_000_000]})
    echoed = body["group_role_bindings"][0]["group_name"]
    assert len(echoed) == authz.MAX_CLAIM_VALUE_CHARS
    assert echoed.endswith("...[truncated]")


def test_the_length_cap_does_not_change_an_authorization_outcome() -> None:
    """The cap belongs at the emit site, and the first version of it did not.

    Capping inside ``_claim_values`` also capped the value feeding the group ->
    role lookup, while the map's **keys** are not capped - so a legitimately long
    group name stopped matching its own entry. Measured with that version, a
    300-character group name present in both the token and the role map::

        granted roles  []            (was ["data-analyst"])

    Fail-closed, so not a privilege grant, but silent: the group was inside the
    count cap, so ``withheld_group_count`` was 0 and nothing said why the role
    had vanished. Matching now uses the real value; only the echo is capped,
    which is all the amplifier fix needed.
    """
    long_group = "g" * (authz.MAX_CLAIM_VALUE_CHARS + 44)
    body = _preview(
        claims={"tenant_id": "demo", "groups": [long_group]},
        role_map={"demo": {long_group: ["data-analyst"]}},
    )
    assert body["actor_context"]["roles"] == ["data-analyst"], body
    assert body["withheld_group_count"] == 0
    row = body["group_role_bindings"][0]
    assert row["granted_roles"] == ["data-analyst"]
    # Still capped on the way out, with the marker.
    assert len(row["group_name"]) == authz.MAX_CLAIM_VALUE_CHARS
    assert row["group_name"].endswith("...[truncated]")


def test_two_long_group_names_stay_distinct_for_matching() -> None:
    """They collapsed to one string and the duplicate guard dropped the second.

    The echoed names are still identical - both truncate to the same prefix, and
    disambiguating a 300-character group name in the output would be
    over-engineering - but the rows are distinguishable by their granted roles,
    and the marker says the name was cut.
    """
    first = "x" * 250 + "A" * 80
    second = "x" * 250 + "B" * 80
    body = _preview(
        claims={"tenant_id": "demo", "groups": [first, second]},
        role_map={"demo": {first: ["data-analyst"], second: ["security"]}},
    )
    assert sorted(body["actor_context"]["roles"]) == ["data-analyst", "security"], body
    assert len(body["group_role_bindings"]) == 2
    assert {tuple(row["granted_roles"]) for row in body["group_role_bindings"]} == {
        ("data-analyst",),
        ("security",),
    }


def test_the_response_is_not_larger_than_the_request() -> None:
    """The amplification property, directly.

    Before: a 2 MB group name produced a 4 MB response, because the name came
    back in both ``groups`` and ``group_role_bindings``.
    """
    claims = {
        "sub": "probe",
        "tenant_id": "acme",
        "exp": int(time()) + 3600,
        "groups": ["g" * 2_000_000],
    }
    request_body = json.dumps({"claims": claims})
    response = client.post("/enterprise/auth/oidc-preview", json={"claims": claims})
    assert response.status_code == 200
    assert len(response.text.encode()) < len(request_body.encode()) / 1000


def test_a_hundred_thousand_groups_no_longer_cost_megabytes() -> None:
    claims = {
        "sub": "probe",
        "tenant_id": "acme",
        "exp": int(time()) + 3600,
        "groups": [f"g-{index}" for index in range(100_000)],
    }
    response = client.post("/enterprise/auth/oidc-preview", json={"claims": claims})
    assert response.status_code == 200
    # Was 7,578,262 bytes.
    assert len(response.text.encode()) < 100_000, len(response.text.encode())


def test_the_role_claim_is_bounded_too() -> None:
    """``ignored_role_claims`` echoes a caller claim through the same helper."""
    body = _preview(claims={"roles": [f"r-{index}" for index in range(5_000)]})
    assert len(body["ignored_role_claims"]) == authz.MAX_CLAIM_VALUES


def test_the_verified_path_declares_the_same_truncation() -> None:
    """On the verified route the cap can change an authorization outcome.

    Groups past the cap grant no roles - fail-closed, since it withholds rather
    than grants - but an operator debugging a missing role must be able to see
    that it happened. The route publishes the counts rather than truncating
    silently; this test asserts the fields exist on the published contract.
    """
    import inspect

    from sdp import api

    source = inspect.getsource(api.enterprise_oidc_verify)
    assert '"declared_group_count": declared_group_count' in source
    assert '"withheld_group_count": withheld_group_count' in source


def test_the_count_cap_can_only_withhold_a_role_never_grant_one() -> None:
    """A security property I had asserted only in prose, now measured.

    The group-count cap applies to matching, including on the verified route,
    so it can change an authorization outcome. The commit that added it called
    that fail-closed; this is the measurement behind the word. Enumerated over
    the position of the privileged group in the claim, because a cap that
    truncates a list is exactly where ordering could matter::

        admins first   uncapped 401 roles | capped 256 | gained none
        admins last    uncapped 401 roles | capped 256 | gained none
        admins at 300  uncapped 401 roles | capped 256 | gained none

    The ``admins last`` and ``admins at 300`` cases lose ``platform-admin`` -
    withheld, which is the safe direction - and no case gains a role the
    uncapped evaluation did not grant.
    """
    role_map = {"demo": {f"g-{index}": [f"role-{index}"] for index in range(400)}}
    role_map["demo"]["admins"] = ["platform-admin"]

    def granted(groups: list[str], cap: int) -> set[str]:
        saved = authz.MAX_CLAIM_VALUES
        authz.MAX_CLAIM_VALUES = cap
        try:
            context = authz.resolve_oidc_actor_context(
                {
                    "sub": "a",
                    "tenant_id": "demo",
                    "exp": int(time()) + 3600,
                    "groups": groups,
                },
                role_map=role_map,
            )
            return set(context.roles)
        finally:
            authz.MAX_CLAIM_VALUES = saved

    others = [f"g-{index}" for index in range(400)]
    for label, groups in (
        ("admins first", ["admins"] + others),
        ("admins last", others + ["admins"]),
        ("admins at 300", others[:300] + ["admins"] + others[300:]),
    ):
        uncapped = granted(groups, 10**6)
        capped = granted(groups, authz.MAX_CLAIM_VALUES)
        assert not (capped - uncapped), (label, sorted(capped - uncapped))
        assert len(capped) <= len(uncapped), label
