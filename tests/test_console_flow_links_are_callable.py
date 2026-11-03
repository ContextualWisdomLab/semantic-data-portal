"""The console's Pilot Flow printed two links a reader cannot follow.

``/enterprise/console``'s "Pilot Flow" section is five ``<a class="node">``
links, each printing its own path in ``<code>`` - the walk a buyer is handed.
Fetching every path the console prints, exactly as printed, at ``3eb1e83``::

    200 /enterprise/readiness
    200 /enterprise/evidence-pack
    200 /enterprise/production-readiness
    200 /enterprise/demo-plan
    200 /docs
    200 /enterprise/steward-review
    405 /browse/query                                {'detail': 'Method Not Allowed'}
    422 /enterprise/connectors/sql_connector/probe   {'loc': ['query', 'dataset_id']}

Two of eight. ``/browse/query`` is a **POST**, so no ``href`` can ever reach it,
and the probe needs a ``dataset_id`` the console already knows - it prints
``crm-customer-master`` in the Connectors table immediately below.

A third defect in the same section, found while measuring the first two: the
links do not go through ``scoped()``. The console reads the viewer's actor from
its own query string and appends it to every **fetch**; a reader who opened
``/enterprise/console?user=admin`` and clicked a flow node dropped it, which is
why the probe answers 404 rather than 200 on the walk the section exists to
support. ``test_the_console_propagates_the_viewers_actor_to_its_fetches`` pins
that property for fetches only, and the Pilot Flow section is asserted by no
test at all.
"""

from __future__ import annotations

import re

from fastapi.testclient import TestClient

from sdp.api import app
from sdp.console import render_enterprise_console


client = TestClient(app)

# Routes the console names that are not GETs, so no link can reach them.
NON_GET_STEPS = {"/browse/query"}


def _printed_paths() -> list[str]:
    """Every path the console prints, in document order, de-duplicated."""
    page = render_enterprise_console()
    found: list[str] = []
    for match in re.finditer(r"(?:href=\"|<code>)(/[A-Za-z0-9_\-/{}?=&.:%]+)", page):
        path = match.group(1)
        if path not in found:
            found.append(path)
    assert found, "the console printed no paths at all"
    return found


def _linked_paths() -> list[str]:
    """Only the paths the console makes clickable."""
    page = render_enterprise_console()
    return sorted({match.group(1) for match in re.finditer(r'href="(/[^"]+)"', page)})


def test_no_printed_path_is_uncallable_regardless_of_who_asks() -> None:
    """405 and 422 are not refusals - they say the request cannot be made.

    Separated from the authorized walk below on purpose. A 403 or 404 from a
    governed route is the gate working and depends on the caller; a 405 (wrong
    method) and a 422 (a required parameter the printed path omits) depend on
    nobody and cannot be fixed by signing in.
    """
    uncallable = []
    for path in _printed_paths():
        for actor in ("", "?user=admin" if "?" not in path else "&user=admin"):
            status = client.get(path + actor).status_code
            if status in {405, 422}:
                uncallable.append((path + actor, status))
    assert not uncallable, f"printed paths no caller can use: {uncallable}"


def test_every_printed_path_completes_the_walk_for_an_authorized_viewer() -> None:
    """The Pilot Flow is a walk; an authorized reader must be able to take it.

    The anonymous view is deliberately not asserted: the probe is actor-gated
    and answers 404 without one, which is the control working and what the
    console's own badge explains ("signed-out view - add ?user= to load").
    """
    failures = []
    for path in _printed_paths():
        separator = "&" if "?" in path else "?"
        response = client.get(f"{path}{separator}user=admin")
        if response.status_code >= 400:
            failures.append((path, response.status_code))
    assert not failures, f"printed paths an authorized viewer cannot follow: {failures}"


def test_a_route_that_is_not_a_get_is_not_printed_as_a_link() -> None:
    """``/browse/query`` is a POST; an ``href`` to it can only ever be 405."""
    linked = _linked_paths()
    wrong = sorted(
        path.split("?")[0] for path in linked if path.split("?")[0] in NON_GET_STEPS
    )
    assert not wrong, f"these are POST routes published as links: {wrong}"


def test_the_non_get_step_still_names_its_method() -> None:
    """Dropping the step would lose it; the fix is to say what it is.

    The step is part of the pilot walk, so it stays on the page - as a step that
    states the method, not as a link that cannot work.
    """
    page = render_enterprise_console()
    for path in NON_GET_STEPS:
        assert path in page, f"{path} was removed from the flow rather than labelled"
        assert f"POST {path}" in page, f"{path} does not say it is a POST"


def test_the_flow_links_carry_the_viewers_actor_like_the_fetches_do() -> None:
    """One actor-propagation rule for the page, not one per element kind."""
    page = render_enterprise_console()
    assert "function scoped(path)" in page
    assert "data-path" in page, "a flow link must declare the path it scopes"
    assert re.search(r"scoped\(\s*(?:node|link|element)\.dataset\.path\s*\)", page), (
        "the flow links must be rewritten through the same scoper as the fetches"
    )


def test_the_links_the_script_builds_are_scoped_too() -> None:
    """The Connectors table had the same defect, one element kind over.

    ``loadConnectors`` already builds a probe path with its ``dataset_id`` - the
    console knew the parameter all along - and rendered it as
    ``href="${esc(path)}"``, dropping the viewer. So the table's four links sent
    an authorized reader to a 404 for the same reason the flow node did. One
    rule for the page: anything that becomes a URL a viewer follows goes through
    ``scoped``.
    """
    page = render_enterprise_console()
    assert 'href="${esc(scoped(path))}"' in page, (
        "a link the script builds must carry the viewer's actor"
    )
    assert 'href="${esc(path)}"' not in page, (
        "an unscoped href is back in the script"
    )


def test_the_probe_link_carries_the_dataset_the_console_already_knows() -> None:
    """The console prints ``crm-customer-master`` one section below."""
    probe = [path for path in _linked_paths() if "/probe" in path]
    assert probe, _linked_paths()
    for path in probe:
        assert "dataset_id=" in path, path
