"""Source contract for the operator console's client-side behaviour.

The console is a buyer-handoff artifact. It fetched
``/enterprise/connectors/{id}/probe`` with no actor, and when that route was
tenant-gated the four probes began returning 403. ``json()`` throws on a non-OK
response and the panels were orchestrated with ``Promise.all``, so one 403
rejected the whole chain: the badge read **"evidence load failed"** and the
connector table stayed empty.

Measured in Chromium (uvicorn on 127.0.0.1, ``page.inner_text('#readyBadge')``):

    before   (no query)      badge 'evidence load failed'     connector rows 1
    before   ?user=admin     badge 'evidence load failed'     connector rows 1
    after    (no query)      badge 'signed-out view - add ?user= to load: connectors'
    after    ?user=admin     badge 'ready for pilot review'   connector rows 4

Note the pre-fix badge was wrong for ``?user=admin`` too: the console never
propagated an actor, so no URL could load the panel. Three of the four panels
(evidence, controls, KPIs) rendered correctly throughout - the breakage was the
connector panel plus a badge that blamed the platform.

This is a **source contract**, not a browser test: the repository has no browser
test harness and adding one would mean a new hash-pinned dependency, which is a
maintainer decision. The behavioural check above was run out of band with the
preinstalled Chromium at ``/opt/pw-browsers``. What is pinned here is the three
properties whose absence caused the defect.
"""

from __future__ import annotations

import re

from fastapi.testclient import TestClient

from sdp.api import app
from sdp.console import render_enterprise_console


client = TestClient(app)


def test_the_console_propagates_the_viewers_actor_to_its_fetches() -> None:
    """A panel behind an actor gate cannot load without one."""
    page = render_enterprise_console()
    assert "URLSearchParams(window.location.search).get('user')" in page
    assert "function scoped(path)" in page
    assert "encodeURIComponent(viewer)" in page, "the actor must be URL-encoded"
    assert "fetch(scoped(path))" in page, "every fetch must go through the scoper"
    # The actor is read client-side from the viewer's own URL, so no
    # caller-supplied string is templated into the page.
    assert "fetch(path)" not in page


def test_the_console_does_not_hardcode_an_actor() -> None:
    """A hard-coded actor would hand every viewer that actor's scope."""
    page = render_enterprise_console()
    for actor in ("user=admin", "user=analyst", "user=platform-admin", "user=security"):
        assert actor not in page, f"console hard-codes {actor!r}"


def test_one_failing_panel_does_not_blank_the_others() -> None:
    """``Promise.all`` coupled the panels; one 403 emptied the page."""
    page = render_enterprise_console()
    assert "Promise.allSettled(panels.map" in page
    assert "Promise.all([loadEvidence()" not in page, (
        "the panel orchestration must not couple panel failures again"
    )


def test_the_badge_separates_a_signed_out_view_from_a_real_failure() -> None:
    """"evidence load failed" on an unauthenticated view blames the platform.

    The classifier must **not** key on a status allow-list. It did
    (``status === 401 || status === 403``), and then the connector probe began
    answering 404 - it resolves its query-parameter dataset in the caller's
    tenant scope, and an out-of-scope dataset has to be indistinguishable from
    an absent one. Every signed-out load fell straight through to ``failures``
    and the badge read "evidence load failed: connectors" again.

    What makes this worse than a plain regression: the test below
    (``test_the_probe_route_the_console_calls_is_still_actor_gated``) was
    updated in the same series to accept the new 404 and nobody asked whether
    the consumer of that status still worked. Two assertions in one file
    disagreed and both passed. So the allow-list is now asserted *absent*.

    This test used to pin the exact ternary
    ``(!viewer && !serverError ? needActor : failures)``. That is one
    expression, not the rule, and it blocked a correct change: a refusal **with**
    an actor is not a platform failure either when the panel is tenant-scoped,
    which needed a third branch. The assertions below are about the rule - key
    on actor presence, never on a specific status - so an implementation that
    honours it can take any shape. ``test_a_refusal_for_a_valid_actor_is_not_a
    _platform_failure`` covers the third branch.
    """
    page = render_enterprise_console()
    assert "status === 401 || status === 403" not in page, (
        "classifying by a status allow-list is what broke; key on actor presence"
    )
    # No equality against any individual status anywhere in the classifier.
    assert not re.search(r"status ===\s*\d", page), (
        "classifying by a specific status is the defect; compare ranges"
    )
    assert "!viewer && !serverError" in page, (
        "a refusal with no actor is the signed-out view whatever its status"
    )
    assert "needActor.push(name)" in page, "the signed-out branch must still exist"
    assert "status >= 500" in page, "a 5xx is a real failure no actor would fix"
    assert "signed-out view" in page
    assert "evidence load failed: ${failures.join" in page, (
        "a real failure should name the panels that failed"
    )


def test_a_refusal_for_a_valid_actor_is_not_a_platform_failure() -> None:
    """The console said the platform was broken for a shipped actor.

    Measured with ``?user=external-analyst`` - a valid, documented actor whose
    tenant does not own the dataset the connector panel probes::

        /enterprise/connectors/sql_connector/probe -> 404   (tenant scope)
        /policy/decisions, /audit/events           -> 200
        evidence, controls, KPIs                   -> 200

    Every request was answered correctly and the badge read
    "evidence load failed: connectors". Two buckets were not enough: a 4xx is
    the gate refusing *this* request, and only a 5xx - or a status the client
    could not read at all - is the platform failing.
    """
    page = render_enterprise_console()
    assert "refusedForActor" in page, "the third bucket must exist"
    assert "refused for this actor:" in page, "and must have its own badge text"
    # Worded as a refusal rather than a tenant reason: the console cannot know
    # why the gate refused, and claiming a tenant scope for a 400 would be a
    # different wrong answer.
    assert "outside this actor's tenant scope" not in page
    # The placeholder row is replaced for a refused panel too, for the same
    # reason it is for a signed-out one - but with its own wording. Telling a
    # viewer who *did* supply an actor that the panel "needs an actor" is a
    # second wrong answer; measured in Chromium with ?user=external-analyst, the
    # badge was right and the panel still read "이 패널은 actor가 필요합니다".
    assert "refusedForActor.map((name) => [name, HINTS.refused])" in page
    assert "이 actor에게는 거부된 패널입니다" in page


def test_the_probe_status_the_console_classifies_is_the_one_it_receives() -> None:
    """The two halves that disagreed, asserted together.

    The earlier regression happened because one test accepted the probe's new
    404 while another pinned a classifier that treated 404 as a failure. Both
    passed. Measuring the status here, in the file that classifies it, is what
    keeps them from drifting again.
    """
    from fastapi.testclient import TestClient

    from sdp.api import app

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get(
        "/enterprise/connectors/sql_connector/probe",
        params={"actor": "external-analyst", "dataset_id": "crm-customer-master"},
    )
    assert response.status_code == 404, response.text
    page = render_enterprise_console()
    # 404 must fall in the refused range, not the failure range.
    assert "status >= 400 && status < 500" in page, (
        "the refused bucket must cover every 4xx, including the probe's 404"
    )


def test_the_actor_hint_replaces_the_placeholder_rather_than_waiting_for_an_empty_panel() -> None:
    """The hint was dead code for every panel.

    It was appended only ``if (target && !target.innerHTML)``, and all three
    tables ship a static placeholder row from the server - ``Loading | --``, and
    for connectors ``SQL connector | crm-customer-master | --``. So the guard
    was never true. Measured in Chromium before the repair, signed out: badge
    correct but the connector panel still showed
    ``'SQL connector\tcrm-customer-master\t--'``, which reads as a real row
    whose status is unknown rather than as a panel needing an actor.
    """
    page = render_enterprise_console()
    assert "!target.innerHTML" not in page, (
        "the panels ship placeholder rows, so this guard is never true"
    )
    assert "body.replaceChildren(row)" in page
    assert "이 패널은 actor가 필요합니다 (?user=)" in page
    # The placeholder the hint has to replace is really there, so the test above
    # is about a live condition rather than a hypothetical one.
    assert '<tr><td>SQL connector</td><td class="mono">crm-customer-master</td><td>--</td></tr>' in page


def _console_panel_urls(page: str) -> list[str]:
    """The paths the shipped console actually fetches, read out of the page.

    Extracted rather than hardcoded: a hardcoded list would keep passing after
    the console started fetching something else, which is the shape of defect
    this file exists to catch.
    """
    literals = re.findall(r"json\('(/[^']+)'\)", page)
    probes = re.findall(
        r"\['[^']+', '([a-z_]+)', '([a-z0-9-]+)'\]", page
    )
    return literals + [
        f"/enterprise/connectors/{connector}/probe?dataset_id={dataset}"
        for connector, dataset in probes
    ]


def test_every_panel_the_console_fetches_behaves_as_the_classifier_assumes() -> None:
    """The server-side half of the contract, measured.

    With no actor every panel must either answer 200 or refuse with a 4xx -
    never a 5xx, which the classifier reports as a real failure. With an actor
    every panel must answer 200, or the badge would say the platform is broken
    while it is not.
    """
    page = render_enterprise_console()
    urls = _console_panel_urls(page)
    assert len(urls) >= 7, urls  # 3 literal panels + 4 connector probes

    signed_out = {}
    signed_in = {}
    for url in urls:
        joiner = "&" if "?" in url else "?"
        signed_out[url] = client.get(url).status_code
        signed_in[url] = client.get(f"{url}{joiner}user=admin").status_code

    server_errors = {url: code for url, code in signed_out.items() if code >= 500}
    assert not server_errors, f"signed-out panels must not 5xx: {server_errors}"
    not_ok_with_actor = {url: code for url, code in signed_in.items() if code != 200}
    assert not not_ok_with_actor, (
        f"with an actor every panel must load: {not_ok_with_actor}"
    )
    # At least one panel really is gated, so the signed-out branch is live.
    assert any(code >= 400 for code in signed_out.values()), signed_out


def test_the_console_still_renders_and_is_reachable() -> None:
    """The route itself, so a template error cannot pass the checks above."""
    response = client.get("/enterprise/console")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    body = response.text
    for element_id in ("readyBadge", "metadataRate", "controlsRows", "kpiRows", "connectorRows"):
        assert f'id="{element_id}"' in body, element_id


def test_the_probe_route_the_console_calls_is_still_actor_gated() -> None:
    """The gate is correct; the console was what had to change.

    If this ever returns 200 without an actor, the console's workaround is
    masking a reopened hole rather than compensating for a real gate.
    """
    refused = client.get(
        "/enterprise/connectors/sql_connector/probe",
        params={"dataset_id": "crm-customer-master"},
    )
    # 404 since the route began resolving its query-parameter dataset in the
    # caller's tenant scope. The property this test guards is that the route is
    # still refused without an actor - which it is - not the particular 4xx.
    assert refused.status_code == 404, refused.text

    allowed = client.get(
        "/enterprise/connectors/sql_connector/probe",
        params={"dataset_id": "crm-customer-master", "user": "admin"},
    )
    assert allowed.status_code == 200, allowed.text
