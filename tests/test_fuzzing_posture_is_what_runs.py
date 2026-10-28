"""Three documents said ClusterFuzzLite runs a harness. Nothing runs it.

``fuzz/fuzz_query_safety.py`` is the Atheris target for ``validate_sql_query``.
Three places state its venue as fact:

* ``CLAUDE.md``: "``.clusterfuzzlite/Dockerfile`` 이미지에서
  ``python fuzz/fuzz_query_safety.py -runs=1000``으로 실행된다"
* the harness's own module docstring: "ClusterFuzzLite runs this file as
  ``python fuzz/fuzz_query_safety.py`` from ``/src`` …"
* ``tests/test_fuzz_harness_imports.py``: "the image is the **only place**
  either one shows"

Measured at ``80ac7b6``::

    $ grep -rln 'clusterfuzzlite\\|cflite' .github/
    (no output)
    $ ls .github/workflows/
    fuzz.yml  scorecard-analysis.yml  tests.yml
    $ git log --all --diff-filter=A --name-only -- '.github/workflows/*cflite*'
    (no such file was ever committed)
    $ grep -rln 'clusterfuzzlite' ../.github/.github/workflows/   # the central repo
    fast-mlsirm-cflite_pr.yml      <- on: workflow_call, and nothing here calls it

So the image is built and run by **no pipeline**: not by this repository's three
workflows, and not by the organization's central required workflows, whose only
ClusterFuzzLite entry is a reusable workflow with no caller here. The harness has
never been executed by anything.

The third sentence is the one that cost something. ``tests/test_fuzz_harness_imports.py``
exists because an import repair to that harness was invisible in a checkout, and
its docstring sends the next reader to the image to see the breakage. There is
nothing to see there, ever. That same docstring already contains the true
statement - "This file is the only thing standing between the ClusterFuzzLite
entrypoint and silence" - and it is *more* true than written: silence is the only
other outcome, because the entrypoint is never reached.

What is **not** wrong, and is asserted below so the correction does not overstate
in the other direction: the invariant that harness checks is exercised by venues
that do run. ``.github/workflows/fuzz.yml``'s Hypothesis job runs
``tests/fuzz/test_fuzz_properties.py``, which calls the same shared oracle, and
its Atheris job runs the four harnesses under ``tests/fuzz/atheris``. The gap is
the published venue, not the coverage.

Pinned symmetrically: these assertions read whether a workflow references
ClusterFuzzLite and require the documents to match **in either direction**, so
wiring the pipeline up later reddens them just as removing the correction does.
"""

from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"

# The exact claims that were false, kept verbatim so a revert is caught rather
# than paraphrased past.
EXECUTION_CLAIMS = {
    "CLAUDE.md": "이미지에서 `python fuzz/fuzz_query_safety.py -runs=1000`으로 실행된다",
    "fuzz/fuzz_query_safety.py": "ClusterFuzzLite runs this file as ``python fuzz/fuzz_query_safety.py``",
    "tests/test_fuzz_harness_imports.py": "the image is the only place either one shows",
}

# What each must say instead while nothing runs the image.
NEVER_RUN_STATEMENTS = {
    "CLAUDE.md": "어떤 워크플로도 이 이미지를 빌드하거나 실행하지 않는다",
    "fuzz/fuzz_query_safety.py": "no workflow in this repository builds or runs that image",
    "tests/test_fuzz_harness_imports.py": "no pipeline ever builds that image",
    ".clusterfuzzlite/Dockerfile": "no workflow in this repository builds or runs this image",
}


def _workflows_referencing_clusterfuzzlite() -> list[str]:
    """Local workflows that name ClusterFuzzLite in any spelling."""
    pattern = re.compile(r"clusterfuzzlite|cflite", re.IGNORECASE)
    return sorted(
        path.name
        for path in WORKFLOW_DIR.glob("*.y*ml")
        if pattern.search(path.read_text(encoding="utf-8"))
    )


def _text(relative: str) -> str:
    return (REPO_ROOT / relative).read_text(encoding="utf-8")


def test_the_documents_agree_with_whether_a_pipeline_runs_it() -> None:
    """Symmetric on purpose: the prose tracks the pipeline in both directions."""
    wired = bool(_workflows_referencing_clusterfuzzlite())
    for relative, claim in EXECUTION_CLAIMS.items():
        present = claim in _text(relative)
        assert present == wired, (
            f"{relative} {'claims' if present else 'does not claim'} the image runs "
            f"the harness, while workflows referencing ClusterFuzzLite are "
            f"{_workflows_referencing_clusterfuzzlite() or 'none'}"
        )


def test_each_document_says_so_where_a_reader_would_look() -> None:
    """A missing claim is not the same as a stated absence."""
    if _workflows_referencing_clusterfuzzlite():
        return
    for relative, statement in NEVER_RUN_STATEMENTS.items():
        assert statement in _text(relative), (
            f"{relative} does not state that nothing runs the image"
        )


def test_nothing_here_calls_the_central_reusable_cflite_workflow() -> None:
    """The one central ClusterFuzzLite workflow is ``on: workflow_call``.

    It can only run where a caller invokes it, so the derivation above is
    complete only while no local workflow has such a ``uses:``.
    """
    callers = [
        path.name
        for path in WORKFLOW_DIR.glob("*.y*ml")
        if re.search(r"uses:.*cflite", path.read_text(encoding="utf-8"), re.IGNORECASE)
    ]
    assert not callers, f"these workflows call a ClusterFuzzLite reusable workflow: {callers}"


def _calls_named(source: str, name: str) -> int:
    """How many times ``source`` **calls** ``name`` - parsed, not matched.

    The first version of the assertion below tested
    ``"check_validate_sql_query" in mirror``, and a mutation that renamed the
    call to ``check_validate_sql_query_DISABLED`` came back **green**: a prefix
    still satisfies a substring. The premise was "the oracle is called"; the
    code checked "these characters appear". That is the same defect this file
    repairs one layer up, so it is parsed now.
    """
    import ast

    found = 0
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        called = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
        if called == name:
            found += 1
    return found


def test_the_shared_oracle_is_exercised_where_something_does_run() -> None:
    """The correction must not read as "the invariant is unchecked"."""
    mirror = _text("tests/fuzz/test_fuzz_properties.py")
    calls = _calls_named(mirror, "check_validate_sql_query")
    assert calls >= 1, (
        "the Hypothesis mirror no longer calls the oracle the unrun harness "
        f"shares (calls found: {calls})"
    )
    workflow = _text(".github/workflows/fuzz.yml")
    assert "tests/fuzz/test_fuzz_properties.py" in workflow, workflow[:400]
    assert "tests/fuzz/run_atheris.sh" in workflow, workflow[:400]


def test_the_runner_still_does_not_reach_the_query_safety_harness() -> None:
    """The premise of the whole record: that harness is outside the runner."""
    runner = _text("tests/fuzz/run_atheris.sh")
    assert 'HARNESS_DIR="${REPO_ROOT}/tests/fuzz/atheris"' in runner, runner[:400]
    harnesses = sorted(p.name for p in (REPO_ROOT / "tests/fuzz/atheris").glob("fuzz_*.py"))
    assert harnesses, "the runner's harness directory is empty"
    assert "fuzz_query_safety.py" not in harnesses, harnesses


def test_the_guard_the_prose_names_is_the_guard_that_exists() -> None:
    """"The only thing standing between the entrypoint and silence" must be real."""
    guard = _text("tests/test_fuzz_harness_imports.py")
    assert ".clusterfuzzlite/Dockerfile" in guard, "the guard no longer reads the image"
    assert "COPY" in guard, "the guard no longer reads the image's COPY set"
