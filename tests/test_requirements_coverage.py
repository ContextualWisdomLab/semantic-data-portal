"""The requirements matrix must stay true to the PRD and to the code it cites.

``docs/implementation-compliance.md`` is the document ``CLAUDE.md`` names the
requirements correspondence matrix. Measured before ``sdp_core.requirements``
existed::

    requirement ids in docs/prd-trd.md          74
    ids mentioned anywhere in that matrix       13
    P0 ids absent from it                       25 of 34

A hand-maintained matrix drifts in exactly that direction, and absence reads as
absence to a diligence reader. These tests make drift mechanically impossible in
four ways:

1. the inventory is parsed from the PRD, so a new requirement row appears here
   and fails until it is answered;
2. every evidence pointer must resolve against the running app, the importable
   package, or the collected test ids - a renamed test breaks the suite instead
   of quietly becoming a dead citation;
3. an ``implemented`` claim must carry at least one pointer that resolved, so
   the strongest status cannot be asserted without evidence;
4. the committed document must equal the generated one byte for byte.

(3) is the one that matters most: the honest-measurement discipline this
repository applies to its published numbers applies to its published *claims*
too, and "implemented" is a claim.
"""

from __future__ import annotations

import importlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

from sdp.api import app
from sdp_core.requirements import (
    COVERAGE_DOC_PATH,
    COVERAGE_STATUSES,
    PRD_PATH,
    REQUIREMENT_COVERAGE,
    parse_prd_requirements,
    render_requirements_coverage_markdown,
    requirement_group,
    requirements_coverage_manifest,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _served_routes() -> set[str]:
    """``"<METHOD> <path>"`` for every route this app serves."""
    served: set[str] = set()
    for route in app.routes:
        for method in getattr(route, "methods", set()) or set():
            served.add(f"{method} {route.path}")
    return served


def _collected_test_ids() -> set[str]:
    """Every test id pytest collects, with parametrisation suffixes stripped.

    Collected rather than grepped: a pointer naming a function that exists but
    is not collected (wrong file, skipped module, collection error) is a dead
    citation too, and only pytest itself knows the difference.
    """
    # ``PYTHONPATH=src`` is how this repository is importable (the package is
    # not installed), and CI sets it relative to the repo root. Resolving it to
    # an absolute path here means the child collects the same tree no matter
    # what cwd or PYTHONPATH the parent was launched with.
    environment = dict(os.environ)
    source_root = str(REPOSITORY_ROOT / "src")
    existing = environment.get("PYTHONPATH", "")
    environment["PYTHONPATH"] = (
        source_root if not existing else f"{source_root}{os.pathsep}{existing}"
    )
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "-p",
            "no:warnings",
            "-o",
            "addopts=",
            "tests",
        ],
        capture_output=True,
        text=True,
        cwd=REPOSITORY_ROOT,
        env=environment,
        check=False,
    )
    ids = {
        line.strip().split("[")[0]
        for line in completed.stdout.splitlines()
        if line.strip().startswith("tests/") and "::" in line
    }
    assert ids, (
        "pytest collected no test ids; evidence pointers cannot be verified\n"
        f"{completed.stdout[-2000:]}\n{completed.stderr[-2000:]}"
    )
    return ids


@pytest.fixture(scope="module")
def resolvers() -> dict[str, object]:
    """The three resolution sources, collected once for the whole module."""
    return {"routes": _served_routes(), "tests": _collected_test_ids()}


def _resolution_failure(pointer: str, resolvers: dict[str, object]) -> str:
    """Why this evidence pointer does not resolve, or ``""`` if it does."""
    kind, separator, target = pointer.partition(":")
    if not separator:
        return "pointer has no 'kind:target' shape"
    if kind == "route":
        if target not in resolvers["routes"]:
            return "no such route is served"
        return ""
    if kind == "func":
        # Walks the dotted path from the longest importable prefix, so a method
        # on a class is as citable as a module-level function. Resolving only
        # ``module.attribute`` rejected
        # ``sdp.graph_store.GraphStore.assert_node_kind_is_stable`` with "is not
        # a package" - a pointer the resolver could not express rather than one
        # that did not exist, which is the wrong kind of failure for a test
        # whose job is to catch dangling evidence.
        parts = target.split(".")
        module = None
        remainder: list[str] = []
        for split in range(len(parts) - 1, 0, -1):
            try:
                module = importlib.import_module(".".join(parts[:split]))
            except ImportError:
                continue
            remainder = parts[split:]
            break
        if module is None:
            return f"no importable module prefix in {target!r}"
        if not remainder:
            return "func pointer needs an attribute after the module path"
        current: object = module
        walked = ".".join(parts[: len(parts) - len(remainder)])
        for attribute in remainder:
            if not hasattr(current, attribute):
                return f"{walked} has no attribute {attribute!r}"
            current = getattr(current, attribute)
            walked = f"{walked}.{attribute}"
        return ""
    if kind == "test":
        if target not in resolvers["tests"]:
            return "pytest does not collect this test id"
        return ""
    return f"unknown pointer kind {kind!r}"


def test_the_prd_parser_finds_both_table_shapes() -> None:
    """Guard the parser itself: the inventory is only as good as its reader."""
    requirements = parse_prd_requirements()
    ids = [requirement.id for requirement in requirements]
    assert len(ids) == len(set(ids)), "the PRD states a requirement id twice"
    # Both shapes present: functional rows carry a priority, NFR rows do not.
    assert any(r.priority.startswith("P") for r in requirements)
    assert any(r.priority == "NFR" for r in requirements)
    # Known anchors, so a regex that silently stops matching is caught.
    assert "CAT-001" in ids
    assert "NFR-SEC-001" in ids
    for requirement in requirements:
        assert requirement.text, f"{requirement.id} parsed with empty text"
        assert requirement.source_line > 0


def test_every_prd_requirement_carries_a_coverage_entry() -> None:
    """A requirement the PRD states may not be absent from the matrix."""
    manifest = requirements_coverage_manifest()
    assert manifest.unmapped_requirement_ids == [], (
        "these PRD requirements have no entry in REQUIREMENT_COVERAGE: "
        f"{manifest.unmapped_requirement_ids}. Add one - including "
        "'not_implemented', which is an answer; silence is not."
    )
    assert manifest.requirement_count == len(manifest.entries)


def test_the_matrix_does_not_cover_requirements_the_prd_dropped() -> None:
    """The other direction: a mapping for an id the PRD no longer states is dead weight."""
    stated = {requirement.id for requirement in parse_prd_requirements()}
    stale = sorted(set(REQUIREMENT_COVERAGE) - stated)
    assert stale == [], (
        f"REQUIREMENT_COVERAGE maps ids the PRD does not state: {stale}"
    )


def test_every_evidence_pointer_resolves(resolvers: dict[str, object]) -> None:
    """A citation that no longer resolves is the failure mode this replaces."""
    failures = [
        f"{requirement_id}: {pointer} ({reason})"
        for requirement_id, coverage in sorted(REQUIREMENT_COVERAGE.items())
        for pointer in coverage.evidence
        if (reason := _resolution_failure(pointer, resolvers))
    ]
    assert failures == [], "unresolvable evidence pointers:\n" + "\n".join(failures)


def test_an_implemented_claim_carries_resolving_evidence(
    resolvers: dict[str, object],
) -> None:
    """``implemented`` is the strongest status; it may not be asserted bare."""
    unsupported = sorted(
        requirement_id
        for requirement_id, coverage in REQUIREMENT_COVERAGE.items()
        if coverage.status == "implemented"
        and not any(
            not _resolution_failure(pointer, resolvers)
            for pointer in coverage.evidence
        )
    )
    assert unsupported == [], (
        "these requirements claim 'implemented' with no resolving evidence "
        f"pointer: {unsupported}. Either cite the code/test that answers them, "
        "or state 'partial'/'not_implemented'."
    )


def test_an_implemented_claim_is_covered_by_a_test(
    resolvers: dict[str, object],
) -> None:
    """The published vocabulary says ``implemented`` means a test covers it.

    The weaker rule above - "any resolving pointer" - let a route pointer alone
    carry the strongest status, which is not what the document promises a
    reader. CAT-009 was in exactly that state: two real routes, two real tests,
    and neither test cited. Requiring the ``test:`` pointer makes the word and
    the gate say the same thing.
    """
    untested = sorted(
        requirement_id
        for requirement_id, coverage in REQUIREMENT_COVERAGE.items()
        if coverage.status == "implemented"
        and not any(
            pointer.startswith("test:")
            and not _resolution_failure(pointer, resolvers)
            for pointer in coverage.evidence
        )
    )
    assert untested == [], (
        "these requirements claim 'implemented' but cite no collected test: "
        f"{untested}. The status vocabulary published in "
        "docs/requirements-coverage.md defines 'implemented' as answered *and* "
        "covered by a test, so cite the test or weaken the status."
    )


def test_a_status_without_evidence_explains_itself() -> None:
    """``partial``/``not_implemented``/``external`` must say what is missing."""
    silent = sorted(
        requirement_id
        for requirement_id, coverage in REQUIREMENT_COVERAGE.items()
        if coverage.status != "implemented" and not coverage.note
    )
    assert silent == [], (
        "a status weaker than 'implemented' needs a note saying what is "
        f"missing; these have none: {silent}"
    )


def test_every_status_is_one_of_the_published_vocabulary() -> None:
    """The document publishes the vocabulary; nothing may use a word outside it."""
    for requirement_id, coverage in REQUIREMENT_COVERAGE.items():
        assert coverage.status in COVERAGE_STATUSES, (
            f"{requirement_id} uses status {coverage.status!r}, which the "
            "published vocabulary does not define"
        )


def test_the_committed_document_is_the_generated_one() -> None:
    """The doc is a generated artifact; a hand edit must fail rather than ship."""
    assert COVERAGE_DOC_PATH.exists(), (
        f"{COVERAGE_DOC_PATH} is missing; regenerate with "
        "`PYTHONPATH=src python -m sdp_core.requirements`"
    )
    assert COVERAGE_DOC_PATH.read_text(encoding="utf-8") == (
        render_requirements_coverage_markdown()
    ), (
        f"{COVERAGE_DOC_PATH} is stale or hand-edited; regenerate with "
        "`PYTHONPATH=src python -m sdp_core.requirements`"
    )


def test_the_generated_document_states_every_requirement_and_status() -> None:
    """Every id and its status must be readable in the document, not only tallied."""
    rendered = render_requirements_coverage_markdown()
    manifest = requirements_coverage_manifest()
    for entry in manifest.entries:
        assert f"#### {entry.id} · {entry.priority} · `{entry.status}`" in rendered, (
            f"{entry.id} has no detail block in the generated document"
        )
        assert f"| {entry.id} | {entry.priority} | `{entry.status}` |" in rendered, (
            f"{entry.id} is missing from the generated index table"
        )
    for status in COVERAGE_STATUSES:
        assert (
            f"| `{status}` | {manifest.status_counts[status]} "
            f"| {manifest.p0_status_counts[status]} |"
        ) in rendered, f"the {status} tally is not published"


def test_the_published_counts_are_the_measured_counts() -> None:
    """The summary table may not disagree with the entries it summarises."""
    manifest = requirements_coverage_manifest()
    assert sum(manifest.status_counts.values()) == len(manifest.entries)
    for status in COVERAGE_STATUSES:
        assert manifest.status_counts[status] == sum(
            1 for entry in manifest.entries if entry.status == status
        )
        assert manifest.p0_status_counts[status] == sum(
            1
            for entry in manifest.entries
            if entry.status == status and entry.priority == "P0"
        )
        assert manifest.p0_status_counts[status] <= manifest.status_counts[status]


def test_requirement_group_derives_the_family_prefix() -> None:
    """Grouping is derived from the id, so a new family needs no code change."""
    assert requirement_group("CAT-001") == "CAT"
    assert requirement_group("NFR-SEC-001") == "NFR-SEC"
    # An id that does not end in -NNN groups under itself rather than raising:
    # the document must still render if the PRD adopts a new id shape.
    assert requirement_group("ODD") == "ODD"


def test_the_prd_is_where_the_inventory_comes_from() -> None:
    """Pin the source path, so the inventory cannot be pointed at a copy."""
    assert PRD_PATH == REPOSITORY_ROOT / "docs" / "prd-trd.md"
    assert PRD_PATH.exists()
    assert COVERAGE_DOC_PATH == REPOSITORY_ROOT / "docs" / "requirements-coverage.md"


def test_the_matrix_covers_the_whole_p0_set() -> None:
    """The gap that motivated this: 25 of 34 P0 ids were absent from the old doc."""
    manifest = requirements_coverage_manifest()
    p0_entries = [entry for entry in manifest.entries if entry.priority == "P0"]
    stated_p0 = [r for r in parse_prd_requirements() if r.priority == "P0"]
    assert len(p0_entries) == len(stated_p0)
    assert p0_entries, "the PRD states P0 requirements; none reached the matrix"
