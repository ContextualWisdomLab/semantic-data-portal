"""The one place that enumerates published route references across the manifests.

Shared because the alternative is two implementations of the same property, and
this round exists because the single implementation there was reached four
manifests and four field names while eleven fields across five manifests publish
route references. A second, weaker copy is the drift this module prevents.

Imported as ``from tests import manifest_pointers`` the way
``tests/fuzz/invariants.py`` is shared by the Hypothesis suite and the Atheris
harnesses.
"""

from __future__ import annotations

import re
from typing import Iterator

from fastapi.routing import APIRoute
from pydantic import BaseModel

# A path token counts as a route reference only where it begins the string or
# follows whitespace. Without that anchor, the prose "The policy/audit gap
# condition IS evaluated" in ``production.acceptance_criteria`` reads as a
# reference to ``/audit``, which is not a served route - a finding the heuristic
# would have manufactured rather than found. Measured: the unanchored form
# reported exactly that one false positive and nothing else.
PATH_TOKEN = re.compile(r"(?:(?<=^)|(?<=\s))(/[A-Za-z0-9_{][A-Za-z0-9_{}/.\-]*)")

# ``"GET /policy/decisions"`` - the spelling the controls and the production
# integrations use. Case-sensitive on purpose: a lowercase method is not a
# spelling this product publishes, and accepting one would let a typo pass as a
# verified pointer.
METHOD_AND_PATH = re.compile(r"^(GET|POST|PATCH|PUT|DELETE|HEAD) (/\S*)$")


def manifest_roots() -> dict[str, object]:
    """Every published manifest, by the name a reader would use for it.

    Five, not four. ``buyer_demo_activation_plan()`` publishes route pointers and
    no guard enumerated it - and the field it publishes them in is literally
    named ``proof_endpoints``, which is where the controls loop's
    ``getattr(item, "proof_endpoints", None)`` almost certainly came from: that
    name was copied onto a model whose field is ``evidence``.
    """
    from sdp_core import (
        enterprise_controls_manifest,
        enterprise_kpi_framework,
        enterprise_production_readiness_manifest,
        enterprise_readiness_manifest,
    )
    from sdp_core.readiness import buyer_demo_activation_plan

    return {
        "readiness": enterprise_readiness_manifest(),
        "kpis": enterprise_kpi_framework(),
        "controls": enterprise_controls_manifest(),
        "production": enterprise_production_readiness_manifest(),
        "demo_plan": buyer_demo_activation_plan(),
    }


def walk_strings(node: object, trail: tuple[str, ...] = ()) -> Iterator[tuple[tuple[str, ...], str]]:
    """Every string reachable from a manifest, with the field trail holding it.

    Structural rather than hand-listed, which is the whole point: a walk cannot
    miss a field that exists, so a new manifest or a renamed field is covered
    without anyone remembering to add it.
    """
    if isinstance(node, BaseModel):
        for name in type(node).model_fields:
            yield from walk_strings(getattr(node, name), trail + (name,))
    elif isinstance(node, (list, tuple)):
        for item in node:
            yield from walk_strings(item, trail)
    elif isinstance(node, str):
        yield trail, node


def served_paths(app: object) -> set[str]:
    """The route paths this build serves."""
    return {route.path for route in app.routes if isinstance(route, APIRoute)}


def served_pairs(app: object) -> set[tuple[str, str]]:
    """The ``(method, path)`` pairs this build serves."""
    return {
        (method, route.path)
        for route in app.routes
        if isinstance(route, APIRoute)
        for method in route.methods
    }


def route_references(app: object) -> list[tuple[str, str, str, str]]:
    """Every published reference to a route this app serves.

    ``(manifest, field, path, whole_string)``. A token is a route reference when
    its first segment is one the app actually serves - derived from the route
    table, so it needs no allow-list and cannot go stale against it.
    """
    served = served_paths(app)
    segments = {path.split("/")[1] for path in served if len(path.split("/")) > 1}
    references: list[tuple[str, str, str, str]] = []
    for manifest, root in manifest_roots().items():
        for trail, text in walk_strings(root):
            for token in PATH_TOKEN.findall(text):
                token = token.rstrip(".,;")
                head = token.split("/")[1] if len(token.split("/")) > 1 else ""
                if head in segments:
                    references.append((manifest, trail[-1], token, text))
    return references


def unserved_method_references(
    references: list[tuple[str, str, str, str]], pairs: set[tuple[str, str]]
) -> list[tuple[str, str, str]]:
    """The method-prefixed references this build does not serve for that method.

    One predicate with two callers, because the first version of this check was
    written inline in the guard *and* re-implemented in the near-miss test - so a
    mutation that dropped the method from the comparison left both green: the
    guard had no wrong-method pointer in the real data to catch, and the
    near-miss test was checking its own copy rather than the guard's. A test
    that re-implements the predicate it is meant to pin proves nothing about the
    predicate.
    """
    unserved: list[tuple[str, str, str]] = []
    for manifest, field, _path, text in references:
        match = METHOD_AND_PATH.match(text)
        if match is None:
            continue
        if (match.group(1), match.group(2)) not in pairs:
            unserved.append((manifest, field, text))
    return unserved
