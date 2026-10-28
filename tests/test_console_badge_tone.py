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
    """The chip's class is written with ``className``, not an HTML sink."""
    page = _console()
    assert "className" in page or "classList" in page
    assert "document.write" not in page
    assert "outerHTML" not in page
    assert "insertAdjacentHTML" not in page


def _html_template_literals(script: str) -> list[str]:
    """Every backtick template literal in ``script`` that builds HTML."""
    literals: list[str] = []
    index = 0
    while True:
        start = script.find("`", index)
        if start == -1:
            return [literal for literal in literals if "<" in literal]
        end = start + 1
        while end < len(script):
            if script[end] == "\\":
                end += 2
                continue
            if script[end] == "`":
                break
            end += 1
        literals.append(script[start + 1 : end])
        index = end + 1


def _interpolations(literal: str) -> list[str]:
    """The expression inside each ``${...}`` of one template literal."""
    found: list[str] = []
    index = 0
    while True:
        start = literal.find("${", index)
        if start == -1:
            return found
        depth, cursor = 1, start + 2
        while cursor < len(literal) and depth:
            if literal[cursor] == "{":
                depth += 1
            elif literal[cursor] == "}":
                depth -= 1
            cursor += 1
        found.append(literal[start + 2 : cursor - 1].strip())
        index = cursor


def test_the_console_uses_innerhtml_and_escapes_everything_it_interpolates() -> None:
    """The real property, in place of an assertion that could not fail.

    This check used to read::

        assert "innerHTML = " not in script.replace("panelHtml", "") or True

    which is vacuous by construction, and the thing it was hedging around was
    true: the controls, KPI and connector panels each assign ``innerHTML``, and
    a comment a few lines above them said "the console stays free of
    innerHTML". The hedge is why that comment survived.

    So the property asserted is the one that actually holds. Every value
    interpolated into an HTML-bearing template literal must be either an
    ``esc(...)`` call or a ternary over string literals - a CSS class chosen
    between ``'ok'`` and ``'warn'`` cannot carry caller data. Anything else is
    an unescaped interpolation into an HTML sink.
    """
    script = _console().split("<script>", 1)[-1]
    assert "innerHTML" in script, (
        "if the console no longer uses an HTML sink this guard is measuring "
        "nothing - delete it rather than leave it green"
    )
    literals = _html_template_literals(script)
    assert literals, "no HTML-bearing template literal found; the parse is wrong"

    # A ternary is accepted only when **both** branches are quoted string
    # literals. The first predicate here was "contains ? and ' and no . after
    # the ?", which would have accepted ``flag ? someIdentifier : 'warn'`` - a
    # bare identifier carries data just as a property access does.
    literal_branches = re.compile(r"^[^?]+\?\s*'[\w -]*'\s*:\s*'[\w -]*'$")
    offenders = []
    for literal in literals:
        for expression in _interpolations(literal):
            if _is_one_esc_call(expression) or literal_branches.match(expression):
                continue
            offenders.append(expression)
    assert not offenders, (
        "these values reach an HTML template literal without esc(): " f"{offenders}"
    )


def _is_one_esc_call(expression: str) -> bool:
    """Whether ``expression`` is exactly one ``esc(...)`` call and nothing else.

    ``expression.startswith("esc(")`` was the predicate, and it accepts
    ``esc(row.a) + row.raw_value`` - raw data concatenated into an
    ``innerHTML`` template literal, past a guard whose whole purpose is to stop
    that. Measured: injecting that interpolation left this file green.

    So the matching parenthesis has to be the **last** character. A nested call
    (``esc(fmt(x))``) still passes, which is why the depth is counted rather
    than the string merely ending in ``)``.
    """
    if not expression.startswith("esc("):
        return False
    depth = 0
    for index, char in enumerate(expression):
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return index == len(expression) - 1
    return False


def test_the_escaper_covers_every_html_metacharacter() -> None:
    r"""``esc`` is the whole defence above, so both of its halves are asserted.

    The first version of this checked only that the five entity strings appear
    somewhere in the escaper's source. The entities live in a lookup object; the
    characters that get replaced are decided by a **separate** regex character
    class. So narrowing ``/[&<>"']/g`` to ``/[&]/g`` leaves every entity string
    in place, stops escaping ``<``, ``>``, ``"`` and ``'``, and this test stayed
    green - measured. A guard that reads the table while the regex decides is
    not guarding the decision.

    Both halves are read here: the class must contain the character, and the
    table must map it to its entity. Either one missing is an unescaped
    metacharacter reaching ``innerHTML``.
    """
    script = _console().split("<script>", 1)[-1]
    escaper = script.split("const esc =", 1)[1].split("const pct", 1)[0]

    character_class = re.search(r"\.replace\(\s*/\[([^\]]*)\]/[a-z]*", escaper)
    assert character_class is not None, (
        "the escaper no longer replaces on a regex character class; this guard "
        f"reads that class and must be updated with it: {escaper}"
    )
    replaced = character_class.group(1)

    for character, entity in (
        ("&", "&amp;"),
        ("<", "&lt;"),
        (">", "&gt;"),
        ('"', "&quot;"),
        ("'", "&#39;"),
    ):
        assert character in replaced, (
            f"{character!r} is not in the escaper's character class {replaced!r}, "
            "so it is never replaced however complete the entity table is"
        )
        assert entity in escaper, (character, entity, escaper)
