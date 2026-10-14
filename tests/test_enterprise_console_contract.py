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
    """"evidence load failed" on an unauthenticated view blames the platform."""
    page = render_enterprise_console()
    assert "status === 401 || status === 403" in page, (
        "an auth status must be classified apart from a genuine error"
    )
    assert "signed-out view" in page
    assert "evidence load failed: ${failures.join" in page, (
        "a real failure should name the panels that failed"
    )


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
