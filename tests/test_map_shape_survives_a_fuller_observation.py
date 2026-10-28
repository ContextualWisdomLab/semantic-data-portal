"""A more complete observation must not narrow a published claim.

``as_map_where_keys_are_data`` fires on one signal: the second catalog state
holds a key the first state's ``properties`` lacks. That makes the published
shape a function of **which sample saw more**, not of whether the node's keys
vary. ``scripts/generate_response_contract.py`` already recorded two attempts
reverted for exactly that reason ("Each destroys the map rule ... ``details``
reverted from a map to a closed struct").

The third arrived from production code. When the connector probe's 404 refusal
began recording its policy decision, the first state's observed obligation keys
went from none to five, nothing was left to differ, and
``/policy/decisions[].obligations`` was republished as a closed five-key struct::

    -  'obligations': {'type': 'object', 'additionalProperties': {}}
    +  'obligations': {'type': 'object',
    +                  'properties': {'masking': ..., 'tenant_id': ...,
    +                                 'required_role': ..., 'masking_rules': ...,
    +                                 'actor_tenant_id': ...}}

``sdp.policy`` fills that node from eleven keys, so five published as a field
list is the narrowing ``test_the_obligations_node_is_a_map_because_its_keys_vary``
exists to refuse - and the node had not become less variadic. Only the accident
the rule depended on had gone.

So the node is now declared and checked against the vocabulary the product's own
source names. This file pins the three properties that makes it safe: the
derivation reads every spelling ``policy.py`` uses, the comparison runs in the
direction that cannot invent a map, and the rule stops firing once a node really
has been observed completely.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import generate_response_contract as generator  # noqa: E402

from sdp.api_response_contract import RESPONSE_SCHEMAS  # noqa: E402


def _published_obligations() -> dict:
    return RESPONSE_SCHEMAS[("GET", "/policy/decisions")]["items"]["properties"][
        "obligations"
    ]


def test_the_derivation_reads_every_spelling_policy_uses() -> None:
    """Four spellings, one key each that appears in no other.

    A derivation that silently handled three of the four would undercount, and
    an undercount is safe only because of the comparison's direction - it is
    still worth refusing, because the gap it leaves is invisible.
    """
    declared = generator.declared_obligation_keys()
    # ``obligations={...}`` keyword at a ``_decision`` call
    assert "required_role" in declared, sorted(declared)
    # local ``obligations = {...}`` literal
    assert "masking_rules" in declared, sorted(declared)
    # ``obligations["key"] = ...``
    assert "row_filter" in declared, sorted(declared)
    # ``obligations.setdefault("key", ...)``
    assert "tenant_id" in declared, sorted(declared)


def test_the_product_can_still_emit_keys_the_contract_never_observed() -> None:
    """The rule's premise, measured rather than assumed."""
    declared = generator.declared_obligation_keys()
    published = _published_obligations()
    assert "additionalProperties" in published, published
    # The node is a map, so it publishes no field list at all - which is the
    # whole point: every one of the declared keys is unobserved by it.
    assert declared, "the derivation found nothing, so the rule can never fire"


def test_the_rule_cannot_claim_a_map_the_product_denies() -> None:
    """``declared - observed``, not ``observed ⊆ declared``.

    Fed a node whose properties already cover every declared key, the rule must
    leave it a struct. Were the comparison the other way round, an incomplete
    derivation would collapse a genuine field list into a map.
    """
    declared = generator.declared_obligation_keys()
    complete = {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "obligations": {
                    "type": "object",
                    "properties": {key: {"type": "string"} for key in declared},
                }
            },
        },
    }
    result = generator.as_map_where_the_product_declares_more_keys(
        complete, ("GET", "/policy/decisions"), declared
    )
    node = result["items"]["properties"]["obligations"]
    assert "properties" in node, node
    assert "additionalProperties" not in node, node


def test_an_undeclared_route_is_left_alone() -> None:
    """The declaration is one node, not a blanket."""
    schema = {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "obligations": {"type": "object", "properties": {"a_single_key": {}}}
            },
        },
    }
    untouched = generator.as_map_where_the_product_declares_more_keys(
        schema, ("GET", "/audit/events"), {"a_single_key", "another_key"}
    )
    assert untouched["items"]["properties"]["obligations"]["properties"], untouched
