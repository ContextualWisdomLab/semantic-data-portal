"""A quality gate that does not run on a stacked PR is not a gate.

Measured at ``33293cc`` on PR #102, whose base is the ``#79`` branch rather than
``main`` — the repository's own merge order stacks PRs deliberately::

    GET /repos/.../pulls/102/check-runs  ->  total_count: 2
      Hypothesis property tests          (fuzz.yml)
      Atheris coverage-guided (bounded)  (fuzz.yml)

``Tests / API integration suite`` is absent entirely. The cause is one line:
``fuzz.yml`` declares ``pull_request:`` with no filter, while ``tests.yml``
declared ``pull_request: branches: [main]``, and that filter matches the PR's
**base** branch. So the primary suite — the gate that would catch a real
regression — ran on no stacked PR at all.

Nobody noticed for 24 days because the account's Actions billing lock refused
every job before dispatch, so no check ran either way. The consequence lands the
moment that lock lifts: the PR would show the fuzz lane's results and **no**
``Tests`` result, and a reviewer reading "checks passed" would be reading one
lane of two. This is the defect a sibling repository already recorded
(``contextual-orchestrator``'s "Stacked quality checks: zero check runs can
result from the former ``pull_request.branches: [main]`` filter excluding the PR
base. Keep the quality trigger unfiltered.") — the same filter, in a second
repository, found by reading the check list rather than the workflow.

The check here is **derived**: it reads every workflow this repository owns and
refuses a ``branches`` filter on any ``pull_request`` trigger, rather than naming
``tests.yml``. A workflow added later with the same filter is caught without an
edit here. ``scorecard-analysis.yml`` has no ``pull_request`` trigger at all and
is therefore unaffected rather than exempted.

No PyYAML in this repository's locked dependency set, and adding one for a guard
would be the wrong trade, so the trigger block is read as text — the same way
``tests/test_container_entrypoint.py`` and ``tests/test_api.py`` already read
``docker-compose.yml`` and ``fuzz.yml``. The parser is driven by its own tests
below against synthetic text, because a guard whose parser nobody measured is a
guard checked against its own assumption.
"""

from __future__ import annotations

from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"

# Filters that narrow which pull requests a trigger fires on by base branch.
# ``types``, ``paths`` and ``paths-ignore`` are not in scope: they narrow by
# event kind or by changed file, not by which PR gets a result at all.
_BASE_BRANCH_FILTERS = ("branches", "branches-ignore")


def _indent(line: str) -> int:
    """How far this line is indented, in spaces."""
    return len(line) - len(line.lstrip(" "))


def _trigger_lines(text: str) -> list[str]:
    """The lines inside the workflow's top-level ``on:`` mapping.

    Stops at the next top-level key, so a ``branches`` under ``jobs:`` or under a
    ``concurrency:`` block cannot be mistaken for a trigger filter.
    """
    lines = text.splitlines()
    collected: list[str] = []
    inside = False
    for line in lines:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not inside:
            if line.startswith("on:"):
                inside = True
            continue
        if _indent(line) == 0:
            break
        collected.append(line)
    return collected


def pull_request_base_filters(text: str) -> list[str]:
    """The base-branch filter keys under this workflow's ``pull_request`` trigger.

    Empty when the trigger is unfiltered, and empty when there is no
    ``pull_request`` trigger at all - the caller distinguishes those with
    :func:`has_pull_request_trigger`.
    """
    block = _trigger_lines(text)
    found: list[str] = []
    depth: int | None = None
    for line in block:
        stripped = line.strip()
        if depth is None:
            if stripped.rstrip(":") == "pull_request" and stripped.endswith(":"):
                depth = _indent(line)
            continue
        if _indent(line) <= depth:
            break
        key = stripped.split(":", 1)[0].strip("- ")
        if key in _BASE_BRANCH_FILTERS:
            found.append(key)
    return found


def has_pull_request_trigger(text: str) -> bool:
    """Whether this workflow runs on pull requests at all."""
    return any(
        line.strip().rstrip(":") == "pull_request" for line in _trigger_lines(text)
    )


def _workflows() -> list[Path]:
    """Every workflow this repository owns, found rather than listed."""
    found = sorted(
        path
        for path in WORKFLOW_DIR.glob("*.y*ml")
        if path.is_file()
    )
    assert found, f"no workflow was found under {WORKFLOW_DIR}; re-point this test"
    return found


@pytest.mark.parametrize("workflow", _workflows(), ids=lambda p: p.name)
def test_no_pull_request_trigger_filters_by_base_branch(workflow: Path) -> None:
    """A PR gate must fire whatever branch the PR targets.

    The filter matches the PR's base, and this repository stacks PRs, so a
    ``branches: [main]`` filter silently excludes exactly the PRs that carry the
    most change.
    """
    text = workflow.read_text(encoding="utf-8")
    if not has_pull_request_trigger(text):
        pytest.skip(f"{workflow.name} does not run on pull requests")
    filters = pull_request_base_filters(text)
    assert filters == [], (
        f"{workflow.name} filters its pull_request trigger by base branch "
        f"({filters}), so it produces no check run on a PR whose base is not "
        "listed - and this repository's merge order stacks PRs on each other"
    )


def test_at_least_two_workflows_run_on_pull_requests() -> None:
    """Keeps the parametrized check above from passing by skipping everything."""
    running = [
        path.name
        for path in _workflows()
        if has_pull_request_trigger(path.read_text(encoding="utf-8"))
    ]
    assert len(running) >= 2, running
    assert "tests.yml" in running, (
        "the API integration suite no longer runs on pull requests at all, "
        f"which is a larger version of the defect this file is about: {running}"
    )


def test_the_trigger_parser_reads_what_it_claims_to_read() -> None:
    """Driven against synthetic text, both shapes plus the near misses."""
    filtered = (
        "name: Tests\n"
        "on:\n"
        "  push:\n"
        "    branches: [main]\n"
        "  pull_request:\n"
        "    branches: [main]\n"
        "jobs:\n"
        "  pytest:\n"
        "    branches: ignored-here\n"
    )
    assert has_pull_request_trigger(filtered)
    assert pull_request_base_filters(filtered) == ["branches"]

    unfiltered = (
        "on:\n"
        "  push:\n"
        "    branches: [main]\n"
        "  pull_request:\n"
        "  schedule:\n"
        "    - cron: \"0 3 * * *\"\n"
    )
    assert has_pull_request_trigger(unfiltered)
    assert pull_request_base_filters(unfiltered) == []

    # ``types`` narrows the event, not which PRs get a result, and must not be
    # reported as a base-branch filter.
    typed = "on:\n  pull_request:\n    types: [opened, synchronize]\n"
    assert pull_request_base_filters(typed) == []

    # A push-only workflow has no pull_request trigger, and its push filter is
    # not a pull_request filter.
    push_only = "on:\n  push:\n    branches: [\"main\"]\n  schedule:\n    - cron: \"30 1 * * 6\"\n"
    assert not has_pull_request_trigger(push_only)
    assert pull_request_base_filters(push_only) == []

    # ``branches-ignore`` is the same defect spelled the other way.
    ignored = "on:\n  pull_request:\n    branches-ignore: [experimental]\n"
    assert pull_request_base_filters(ignored) == ["branches-ignore"]
