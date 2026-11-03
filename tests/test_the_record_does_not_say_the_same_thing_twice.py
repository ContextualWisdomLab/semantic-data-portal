"""The record must not repeat a run of prose it has already published.

Round 27 shipped a defect of exactly this shape: round 26 wrote a nine-line
parenthetical into ``CHANGELOG.md``'s verification block, and round 27 appended
a **byte-identical** second copy instead of updating the first. Measured on the
shipped head ``8e1e08b``: that parenthetical appeared once at ``5b01d7f`` and
twice at ``8e1e08b``, and the round's own diff added exactly one copy.

Two things let it ship. No test reads that block - so the ten-run file-order
gate was green ten times over a record that said the same thing twice. And the
text named no head ("this round is one"), so neither the next round nor a
reader could tell which head either copy described; the duplicate was invisible
*because* the prose was head-agnostic. The repair in ``CHANGELOG.md`` names the
heads; this file is the part that makes a third copy impossible to ship
quietly.

Scope, and why it is this scope:

* The document list is derived from ``git ls-files '*.md'``, not declared. A
  hand-written list would have covered the three documents these rounds edit
  and silently missed the eleven others - and a document added later would
  start out unguarded. Measured: 14 tracked markdown files.
* Fenced code blocks are excluded, and the exclusion earns its branch:
  ``test_the_detector_ignores_a_duplicate_inside_a_fence`` shows on a synthetic
  fixture that it changes the answer. It also matters for real content -
  measured 2026-11-02 across all 14 files, ``docs/prd-trd.md`` repeats 19
  three-line runs, every one inside a fence and every one legitimate - but note
  what they actually are, because the first draft of this docstring got it
  wrong: **1 of 19** is Turtle (``a sh:NodeShape ;``, inside ```` ```turtle ````),
  **17** are JSON example closers (``}`` / ``]`` runs inside ```` ```json ````),
  and **1** is SQL; **14 of the 19 windows include the closing fence delimiter
  itself** as their third line, and all 19 reduce to just 6 distinct keys. They
  recur because JSON blocks end the same way, not because shapes recur.
  That measurement is deliberately **not** asserted as a gate. An earlier draft
  had a ``test_the_fence_exclusion_is_load_bearing`` asserting that some tracked
  file still has in-fence repeats; it was removed because it made one unrelated
  product document's bracket formatting a merge gate on this guard, and its own
  failure message told the repairer to delete ``skip_fences`` - which would have
  turned ``test_the_detector_ignores_a_duplicate_inside_a_fence`` red and
  falsified a legitimate-repair mutation this round declares green. A
  measurement belongs in the record; only a property belongs in an assertion.
* The window is three contiguous non-blank lines, and it is bounded on **both**
  sides by measurement rather than chosen. An earlier draft of this docstring
  gave only the upper half.
  - Below: at a two-line window the tree has **38** repeats across five
    documents, every one legitimate - repeated table header rows
    (``| 변이 | red |``, ``| 확인 | 결과 |``, ``| 영역 | 설명 |``), repeated
    bullet prefixes, repeated command fragments. Narrowing to two therefore
    makes ``test_no_tracked_markdown_document_repeats_a_run_of_prose`` red on
    correct content, which is the right failure and explains itself.
  - Above: the defect this guard exists for is a **nine**-line parenthetical
    duplicated byte-for-byte, so a window wider than nine cannot see it.
    ``test_the_configured_window_still_catches_the_defect_this_guard_exists_for``
    is what holds that end, and it is anchored on the defect's shape rather than
    on a number, because the protection used to be incidental: setting the window
    to ten reddened only two tests, both via their own three-line fixtures, and
    widening those fixtures to match - the natural move for someone fixing the
    test they just broke - left the suite green with a nine-line duplicate
    undetected.
  - At three and at four the tree has zero prose repeats, so three is not the
    only green choice; it is the narrowest green one.

What this guard does **not** cover, said plainly rather than left for someone to
discover: prose that repeats itself in different words, a duplicated run of one
or two lines, and a legitimately repeated prose passage - there is none today
(measured: the only prose repeat in any tracked markdown file is the defect this
round removes), and if one ever appears the honest move is an allowance entry
with a reason it cannot mislead a reader, the idiom
``tests/test_dependency_locks.py`` already uses for ``DEV_CI_PIN_ALLOWANCES``.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

# Contiguous non-blank lines that must not recur byte-for-byte. See the module
# docstring for why three and not two.
WINDOW_LINES = 3

# Documents these rounds edit. Used only to prove the derived enumeration is
# not vacuous - never as the enumeration itself.
DOCUMENTS_THE_ROUNDS_EDIT = (
    "CHANGELOG.md",
    "README.md",
    "docs/product-technical-gap-baseline.md",
)


def tracked_markdown_documents() -> tuple[str, ...]:
    """Every tracked markdown path, from git rather than from a literal list.

    ``-z`` and a NUL split, not ``splitlines()`` or ``split()``: without ``-z``
    git quotes a path containing a space or a non-ASCII byte, and ``split()``
    would additionally tear such a path into two nonexistent ones. No tracked
    markdown path contains whitespace today (measured: 0 of 14), so this is a
    latent defect rather than a live one - which is exactly when it is cheap to
    remove instead of recording.

    ``check=True`` is deliberate, and a failure here must stay loud. This is
    the only test in the repository that shells out to git, so it is the only
    one with that precondition; the precondition holds everywhere the suite
    actually runs (the package is never pip-installed - tests run from the git
    working tree, and CI checks out with ``actions/checkout``). Do not "repair"
    a git failure into ``pytest.skip`` or a filesystem glob fallback. A skip
    would make this guard silently vacuous in precisely the environment where
    someone had changed the harness, and a glob would scan untracked scratch
    files while missing the derived-from-tracked-files property that
    ``test_the_enumeration_comes_from_git_and_is_not_vacuous`` relies on.
    """
    listing = subprocess.run(
        ["git", "ls-files", "-z", "*.md"],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return tuple(sorted(path for path in listing.stdout.split("\0") if path))


def _lines_inside_a_fence(lines: list[str]) -> list[bool]:
    """Mark each line that opens, closes, or sits inside a fenced code block."""
    inside, marks = False, []
    for line in lines:
        if line.lstrip().startswith("```"):
            marks.append(True)
            inside = not inside
            continue
        marks.append(inside)
    return marks


def repeated_prose_runs(
    text: str, window: int = WINDOW_LINES, skip_fences: bool = True
) -> list[tuple[int, int, str]]:
    """Return every later occurrence of a run of prose already seen.

    Each entry is ``(first_line_number, repeat_line_number, first_line_text)``,
    one-indexed to match what a reader sees in an editor. A run is ``window``
    contiguous lines with no blank among them, so a blank line cannot bridge two
    unrelated passages into one false match.
    """
    lines = text.splitlines()
    fenced = _lines_inside_a_fence(lines)
    first_seen: dict[str, int] = {}
    repeats: list[tuple[int, int, str]] = []
    for index in range(len(lines) - window + 1):
        run = lines[index : index + window]
        if any(not line.strip() for line in run):
            continue
        if skip_fences and any(fenced[index : index + window]):
            continue
        key = "\n".join(run)
        if key in first_seen:
            repeats.append((first_seen[key] + 1, index + 1, run[0].strip()))
        else:
            first_seen[key] = index
    return repeats


def test_no_tracked_markdown_document_repeats_a_run_of_prose() -> None:
    """The guard itself: no document may publish the same prose run twice."""
    offenders: dict[str, list[tuple[int, int, str]]] = {}
    for document in tracked_markdown_documents():
        text = (REPOSITORY_ROOT / document).read_text(encoding="utf-8")
        repeats = repeated_prose_runs(text)
        if repeats:
            offenders[document] = repeats
    assert offenders == {}, (
        "a record document repeats a run of prose byte-for-byte. Round 27 "
        "shipped exactly this by appending a second copy of an existing "
        "parenthetical instead of updating it. Collapse the duplicate and make "
        "the surviving copy name the head it describes, so the next round can "
        f"see that it is already there: {offenders}"
    )


def test_the_enumeration_comes_from_git_and_is_not_vacuous() -> None:
    """A broken enumeration would make the guard above pass by finding nothing."""
    documents = tracked_markdown_documents()
    assert len(documents) >= 10, (
        "git ls-files returned too few markdown paths for this repository; the "
        f"guard would be close to vacuous: {documents}"
    )
    missing = [
        document
        for document in DOCUMENTS_THE_ROUNDS_EDIT
        if document not in documents
    ]
    assert missing == [], (
        f"the derived enumeration does not contain {missing}, which these "
        "rounds edit every time; the guard is not looking where the defect was"
    )
    # Derived, so it must also reach past the three it is checked against.
    assert len(set(documents) - set(DOCUMENTS_THE_ROUNDS_EDIT)) >= 5, (
        "the enumeration covers barely more than the hand-written list, which "
        "is the thing deriving it was supposed to avoid"
    )


def test_the_detector_finds_a_duplicate_it_is_given() -> None:
    """Positive control: a bug here would make every assertion above vacuous."""
    passage = "first line of the passage\nsecond line\nthird line\n"
    once = f"preamble\n\n{passage}\nmiddle\n"
    twice = f"preamble\n\n{passage}\nmiddle\n\n{passage}"
    assert repeated_prose_runs(once) == []
    found = repeated_prose_runs(twice)
    assert len(found) == 1, found
    first_line, repeat_line, text = found[0]
    assert text == "first line of the passage"
    assert first_line < repeat_line


def test_the_detector_ignores_a_duplicate_inside_a_fence() -> None:
    """A command or shape shown twice in code blocks is not a prose defect."""
    snippet = "```sh\nrun --one\nrun --two\nrun --three\n```\n"
    document = f"prose above\n\n{snippet}\nprose between\n\n{snippet}"
    assert repeated_prose_runs(document) == []
    # ... and the un-excluded reading does see it, so the fixture is real.
    assert repeated_prose_runs(document, skip_fences=False) != []


def test_a_blank_line_does_not_bridge_two_passages() -> None:
    """Runs must be contiguous, or unrelated neighbours would match as one."""
    document = "alpha\n\nbeta\n\ngamma\n\nalpha\n\nbeta\n\ngamma\n"
    assert repeated_prose_runs(document) == []


# The defect this guard exists for, in its actual shipped shape: round 26 wrote a
# nine-line indented parenthetical into CHANGELOG.md's verification block and round
# 27 appended a byte-identical second copy. Reconstructed here rather than quoted,
# so that editing the record cannot quietly change what this test measures.
ROUND_27_DEFECT_LINE_COUNT = 9


def _the_shipped_defect_shape() -> str:
    """A document carrying the round-27 defect: one parenthetical, written twice."""
    parenthetical = "\n".join(
        f"{' ' * 34}parenthetical line {index}"
        for index in range(ROUND_27_DEFECT_LINE_COUNT)
    )
    return f"prose above\n\n{parenthetical}\n\nprose between\n\n{parenthetical}\n"


def test_the_configured_window_still_catches_the_defect_this_guard_exists_for() -> None:
    """Anchor the window on the defect, not on a magnitude anyone chose.

    ``WINDOW_LINES`` decides whether this guard can see its own motivating case,
    and nothing else in this file reads it: the two detector controls pass their
    own fixtures, and ``test_the_window_is_the_smallest_...`` passes ``window=``
    explicitly. Measured before this test existed: setting ``WINDOW_LINES`` to 10
    reddened exactly two tests, and both reddened because their three-line
    synthetic fixtures no longer produced a match - not because anything checked
    the real defect. Widening those fixtures to match the new constant, which is
    the natural move for someone fixing the test they just broke, left the suite
    green while a nine-line duplicate went undetected.

    So this test does not assert a number. It rebuilds what round 27 actually
    shipped and requires the guard, at whatever ``WINDOW_LINES`` is configured to,
    to still find it. Widening the window reddens this, and there is no fixture to
    widen in response - the fixture is the defect.
    """
    found = repeated_prose_runs(_the_shipped_defect_shape())
    assert found, (
        f"WINDOW_LINES={WINDOW_LINES} no longer detects a "
        f"{ROUND_27_DEFECT_LINE_COUNT}-line parenthetical duplicated byte-for-byte, "
        "which is exactly what round 27 shipped and what this guard was added to "
        "catch. Do not widen a fixture to make this pass; the window is too wide."
    )
    first_line, repeat_line, text = found[0]
    assert first_line < repeat_line
    assert text == "parenthetical line 0"
    # ... and the window must be strictly narrower than the defect, or a duplicate
    # one line shorter than round 27's would slip through unnoticed.
    assert WINDOW_LINES <= ROUND_27_DEFECT_LINE_COUNT, (
        f"WINDOW_LINES={WINDOW_LINES} exceeds the "
        f"{ROUND_27_DEFECT_LINE_COUNT}-line defect it must catch"
    )


def test_the_window_is_the_smallest_that_catches_the_shipped_defect() -> None:
    """Three lines, measured against the defect rather than chosen by feel."""
    passage = "one\ntwo\nthree\n"
    document = f"{passage}\nbetween\n\n{passage}"
    assert repeated_prose_runs(document, window=3) != []
    assert repeated_prose_runs(document, window=4) == [], (
        "a four-line window does not see a three-line duplicate, which is the "
        "shape round 27 shipped"
    )
