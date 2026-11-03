"""The published count of runtime-verified controls, computed rather than counted.

``README.md`` and ``docs/implementation-compliance.md`` both stated that the
default demo deployment runtime-verifies **zero** controls and that
``credential_vault`` is the only control carrying a runtime check. Both were
true when written and both were false for twelve days::

    c74ba8e  2026-10-14 12:27  wrote the README paragraph (credential_vault only)
    1a62855  2026-10-14 17:25  added ontology_version_pin - five hours later
    measured at 2026-10-26     2 controls carry a runtime check
                               1 is runtime-verified in the default deployment
                               2 once the REST connector's secret is set

Nobody mis-reasoned; the numbers were maintained by hand in two documents and
the code that produces them moved. So this guard does not match the prose. It
**computes** the three figures from the product and asserts the documents state
those figures, which is the same device used for ``alert_webhook_routing``'s
published status: a hand-written list is what failed five times this cycle, and
a product-derived comparison is what did not.

The first version of this guard searched for the numerals inside the paragraph
that mentions ``runtime``. Measured, that was nearly vacuous: restoring the
stale README sentence left the count check **green**, because the surrounding
paragraph supplies a "1" and a "2" of its own, and only the control-name check
fired. Searching prose for a number cannot distinguish the number from its
neighbours.

So the numbers live in one machine-read block in ``README.md`` and are compared
**exactly** - the shape ``fast-mlsirm`` already uses for its runtime contract -
and ``docs/implementation-compliance.md`` deliberately states no count at all,
because two documents holding the same hand-maintained number is what produced
the twelve days.
"""

from __future__ import annotations

from pathlib import Path
import re

import pytest

from sdp import connectors as conn
from sdp.catalog import list_datasets


REPO_ROOT = Path(__file__).resolve().parents[1]
DOCUMENTS = (
    REPO_ROOT / "README.md",
    REPO_ROOT / "docs" / "implementation-compliance.md",
)


def runtime_check_counts() -> dict[str, int]:
    """The three figures the documents state, measured from the product.

    ``controls_with_a_runtime_check`` is the size of the one collection that
    decides it. ``verified_in_the_default_deployment`` walks every probeable
    connector/dataset pair exactly as the demo does and sums the published
    ``runtime_probe_verified`` counts, so it is the number a buyer running the
    demo would see rather than a number about the source.
    """
    verified = 0
    for connector_id in sorted(conn._SOURCE_CONNECTORS):
        for dataset in list_datasets():
            try:
                probe = conn.connector_probe(connector_id, dataset.id)
            except (KeyError, ValueError):
                continue
            verified += probe["control_verification_counts"]["runtime_probe_verified"]
    return {
        "controls_with_a_runtime_check": len(conn._RUNTIME_CONTROL_CHECKS),
        "verified_in_the_default_deployment": verified,
    }


def _paragraphs_mentioning_runtime(text: str) -> list[str]:
    """The blank-line-separated paragraphs that talk about runtime verification."""
    return [
        block
        for block in re.split(r"\n\s*\n", text)
        if "runtime" in block and ("control" in block or "검증" in block)
    ]


def published_counts(text: str) -> dict[str, int]:
    """The ``key = integer`` pairs from the one machine-read block, if present.

    Looked for by key rather than by position, so the block can move. A missing
    block is an empty mapping and the caller reports that as the defect.
    """
    found: dict[str, int] = {}
    for key in ("controls_with_a_runtime_check", "runtime_verified_in_the_default_demo"):
        match = re.search(rf"^{key} = (\d+)$", text, re.MULTILINE)
        if match:
            found[key] = int(match.group(1))
    return found


def test_the_published_block_equals_the_measured_counts() -> None:
    """Exact equality against the product, from the one block that holds them."""
    counts = runtime_check_counts()
    assert counts["controls_with_a_runtime_check"] >= 1, counts
    assert counts["verified_in_the_default_deployment"] >= 1, (
        "no control is runtime-verified in the default deployment any more, so "
        "the published numbers are not the ones this guard was built for: "
        f"{counts}"
    )

    published = published_counts((REPO_ROOT / "README.md").read_text(encoding="utf-8"))
    assert published, (
        "README.md no longer carries the machine-read runtime-verification "
        "block; the numbers were moved out of prose on purpose, because a "
        "search for a numeral in a paragraph is satisfied by its neighbours"
    )
    assert published == {
        "controls_with_a_runtime_check": counts["controls_with_a_runtime_check"],
        "runtime_verified_in_the_default_demo": counts[
            "verified_in_the_default_deployment"
        ],
    }, f"published {published}, measured {counts}"


def test_the_second_document_states_no_count_to_drift() -> None:
    """One number, one place. Two copies is what produced the twelve days."""
    text = (REPO_ROOT / "docs" / "implementation-compliance.md").read_text(
        encoding="utf-8"
    )
    assert published_counts(text) == {}, (
        "the compliance document carries its own copy of the counts again"
    )
    blocks = _paragraphs_mentioning_runtime(text)
    assert blocks, "that document no longer discusses runtime verification"
    stale = [
        block
        for block in blocks
        if re.search(r"runtime[^.\n]{0,40}(검증|확인)[^.\n]{0,20}\d+개", block)
    ]
    assert stale == [], (
        f"a hand-counted runtime-verification figure is back: {stale}"
    )


def test_the_named_controls_are_the_ones_that_carry_a_check() -> None:
    """The documents name the controls; the names must be the real ones.

    A count alone would pass while the paragraph named the wrong control, which
    is exactly what happened: the sentence said ``credential_vault`` was the
    only one for twelve days after a second one existed.
    """
    named = sorted(conn._RUNTIME_CONTROL_CHECKS)
    for document in DOCUMENTS:
        joined = "\n".join(
            _paragraphs_mentioning_runtime(document.read_text(encoding="utf-8"))
        )
        absent = [control for control in named if control not in joined]
        assert absent == [], (
            f"{document.relative_to(REPO_ROOT).as_posix()} discusses runtime "
            f"verification without naming {absent}; the controls that carry a "
            f"check are {named}"
        )


def test_the_paragraph_selector_does_not_match_the_whole_file() -> None:
    """The narrow scope is the point, so it is measured rather than asserted.

    A guard that searched the whole document would be satisfied by a numeral
    anywhere in a 3000-line file.
    """
    for document in DOCUMENTS:
        text = document.read_text(encoding="utf-8")
        blocks = _paragraphs_mentioning_runtime(text)
        selected = sum(len(block) for block in blocks)
        assert 0 < selected < len(text) * 0.5, (
            f"{document.name}: the selector picked {selected} of {len(text)} "
            "characters, which is not a paragraph-scoped match"
        )


@pytest.mark.parametrize(
    "fake",
    [
        "runtime 검증 control은 0개입니다",
        "runtime 확인이 있는 control은 credential_vault 하나입니다",
    ],
)
def test_the_guard_rejects_the_sentences_it_was_built_for(fake: str) -> None:
    """Driven against the two sentences that were live, so the guard is measured.

    Both are checked against the real measured counts, so this stays honest if
    the product's own numbers change.
    """
    blocks = _paragraphs_mentioning_runtime(fake)
    assert blocks, "the selector must pick these sentences up at all"
    # Neither historical sentence carries the machine-read block, so neither
    # can satisfy the exact comparison - which is the whole reason the numbers
    # were moved there. Stated as a measurement rather than as a claim.
    assert published_counts(fake) == {}, fake
    stale = re.search(r"runtime[^.\n]{0,40}(검증|확인)[^.\n]{0,20}\d+개", fake)
    hand_named = "credential_vault" in fake and "ontology_version_pin" not in fake
    assert stale or hand_named, (
        "this historical sentence is caught by neither the stale-count pattern "
        f"nor the named-controls check, so the guard cannot reject it: {fake!r}"
    )
