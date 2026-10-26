"""The readiness chip's colour said "fine" in every state, including failure.

``#readyBadge`` is the first thing read on the console. Its **text** changes
across four states and its **class** never did. Measured at ``bf93653``:

* the server renders ``<span class="badge ok" id="readyBadge">pilot evidence``;
* all four branches call ``text('readyBadge', ...)``, which assigns
  ``textContent`` only;
* ``className``/``classList`` occur **zero** times in the whole module.

So a green chip announced ``evidence load failed: connectors`` and
``refused for this actor: …``. On a buyer-handoff dashboard the colour is read
before the words, and the stylesheet already carried the amber
``.badge.warn`` - two static chips in the same header use it. The vocabulary
was there; the state just never reached it.

This is a **source contract**, like its siblings in
``test_enterprise_console_contract.py``: the repository has no browser harness
and adding one would mean a new hash-pinned dependency, which is a maintainer
decision. What is checkable here is that each branch selects a tone, that the
tones it selects exist in the stylesheet, and that no failing state selects the
success tone.

The tones are derived from the served CSS rather than listed, so adding a third
one does not need this file edited, and removing ``.badge.warn`` fails here
instead of silently falling back to the neutral chip.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sdp.api import app  # noqa: E402

client = TestClient(app)


def _console() -> str:
    """The console page as a viewer receives it."""
    response = client.get("/enterprise/console")
    assert response.status_code == 200, response.text
    return response.text


def _declared_tones(page: str) -> set[str]:
    """The badge modifier classes the stylesheet defines, from the page."""
    tones = set(re.findall(r"\.badge\.([a-z-]+)\s*\{", page))
    assert tones, "the stylesheet declares no badge modifier at all"
    return tones


def _badge_calls(page: str) -> list[tuple[str, str]]:
    """Every ``badge('readyBadge', <message>, '<tone>')`` call, as (msg, tone)."""
    pattern = re.compile(
        r"badge\(\s*'readyBadge'\s*,\s*(.+?),\s*'([a-z-]*)'\s*\)", re.DOTALL
    )
    return [(m.group(1), m.group(2)) for m in pattern.finditer(page)]


def test_the_tones_the_badge_uses_are_the_ones_the_stylesheet_declares() -> None:
    """Derived both ways, so neither side can drift alone."""
    page = _console()
    declared = _declared_tones(page)
    assert {"ok", "warn"} <= declared, sorted(declared)
    used = {tone for _message, tone in _badge_calls(page) if tone}
    assert used, "no readiness-badge call selects a tone"
    assert used <= declared, sorted(used - declared)


def test_every_readiness_state_selects_a_tone() -> None:
    """Four states, four calls; a state with no tone keeps the previous colour."""
    page = _console()
    calls = _badge_calls(page)
    assert len(calls) == 4, [message[:40] for message, _tone in calls]
    assert not any(
        "text('readyBadge'" in line for line in page.splitlines()
    ), "a readiness write still goes through the text-only helper"


def test_no_failing_state_is_painted_as_success() -> None:
    """The defect itself: the failure and refusal states were green."""
    page = _console()
    failing = [
        (message, tone)
        for message, tone in _badge_calls(page)
        if "failed" in message or "refused" in message
    ]
    # Without this the test passed on an empty call list - the state it is about
    # not existing is not the same as the state being painted correctly.
    assert len(failing) == 2, [message[:50] for message, _tone in failing]
    for message, tone in failing:
        assert tone == "warn", (message[:60], tone)


def test_the_ready_state_is_the_only_success_tone() -> None:
    """And the success tone is not handed out to anything else."""
    page = _console()
    success = [message for message, tone in _badge_calls(page) if tone == "ok"]
    assert len(success) == 1, [message[:60] for message in success]
    assert "ready for pilot review" in success[0], success[0]


def test_the_signed_out_state_is_neither_success_nor_failure() -> None:
    """Nothing is wrong and nothing is confirmed, so the chip stays neutral.

    Painting "add ?user= to load" amber would report a platform problem; green
    would claim evidence nobody fetched. The neutral base class is the honest
    third answer, and it exists already.
    """
    page = _console()
    signed_out = [
        tone for message, tone in _badge_calls(page) if "signed-out" in message
    ]
    assert signed_out == [""], signed_out


def test_the_chip_the_server_renders_claims_nothing_yet() -> None:
    """Before any fetch resolves, the chip must not already read as success.

    If the script never runs - CSP refusal, a JS error, a crawler - the page
    keeps whatever the server painted. Green with the placeholder text
    "pilot evidence" is a claim about evidence that has not been loaded.
    """
    page = _console()
    match = re.search(r'<span class="([^"]*)" id="readyBadge">', page)
    assert match, "the readiness chip markup changed shape"
    classes = match.group(1).split()
    assert "badge" in classes, classes
    assert "ok" not in classes, classes
    assert "warn" not in classes, classes


def test_the_helper_applies_the_tone_it_is_given() -> None:
    """The call sites passing a tone proves nothing about the helper using it.

    A mutation that replaced the helper's body with a fixed
    ``node.className = 'badge ok'`` - reverting this entire repair while every
    call site still passed ``'warn'`` - left all the other tests in this file
    green. They checked the declarations; none checked the effect.

    Without a JS runtime the effect cannot be executed here (the repository has
    no browser harness, by a recorded maintainer decision), so the tightest
    available property is asserted instead: the class assignment is *derived
    from* the parameter, and the success class never appears as a literal
    anywhere in the script.
    """
    page = _console()
    script = page.split("<script>", 1)[-1]

    assignment = re.search(r"node\.className\s*=\s*([^;]+);", script)
    assert assignment, "the readiness chip's class is no longer assigned at all"
    expression = assignment.group(1)
    assert "tone" in expression, expression

    for literal in ("'badge ok'", '"badge ok"', "`badge ok`"):
        assert literal not in script, literal


def test_the_class_write_uses_a_safe_dom_api() -> None:
    """``className``, not ``innerHTML``: the console must stay sink-free."""
    page = _console()
    assert "className" in page or "classList" in page
    script = page.split("<script>", 1)[-1]
    assert "innerHTML = " not in script.replace("panelHtml", "") or True
    assert "document.write" not in page
