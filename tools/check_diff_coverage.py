#!/usr/bin/env python3
"""Enforce complete statement and branch coverage on changed production lines.

The repository contains legacy modules that predate the current coverage
contract. This gate prevents that historical debt from being extended: every
executable Python line changed by a pull request must run, and every branch
whose source line changed must exercise all destinations. The full test suite
still runs under branch coverage so the JSON evidence is authoritative.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any

_HUNK_PATTERN = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
_GIT_OBJECT_SHA = re.compile(r"^[0-9a-f]{40}$")

# Exclusions are exceptional governance decisions, not a per-file escape hatch.
# Keep the allowlist explicit and line-scoped; it is intentionally empty until
# a reviewed, unreachable production boundary requires an entry.
_APPROVED_CHANGED_EXCLUSIONS: dict[str, frozenset[int]] = {}


def _validated_git_object(value: str, *, argument: str) -> str:
    """Accept only a complete lowercase SHA so git never sees option text."""

    if _GIT_OBJECT_SHA.fullmatch(value) is None:
        raise ValueError(f"{argument} must be a 40-character lowercase git SHA")
    return value


def _validated_source_root(value: str) -> str:
    """Accept only a relative in-repo path that cannot be parsed as an option.

    Empty values, Git pathspec magic, and glob characters are rejected so a
    caller cannot shrink or expand the coverage scope through ``git diff``.
    """

    path = Path(value)
    if (
        not value.strip()
        or path.is_absolute()
        or value.startswith("-")
        or value.startswith(":")
        or ".." in path.parts
        or any(character in value for character in "*?[]\\")
    ):
        raise ValueError("source_root must be a relative repository path")
    return value


def changed_lines(base_sha: str, head_sha: str, source_root: str) -> dict[str, set[int]]:
    """Return added or modified line numbers grouped by production file.

    Git is invoked with an argument vector and ``shell=False``. ``--literal-pathspecs``
    and ``--default-prefix`` keep the pathspec and ``a/`` ``b/`` prefixes stable
    even when repository Git config would otherwise hide changed files. File
    names from the diff are parsed as text only; they are never interpolated
    into a shell.
    """

    base = _validated_git_object(base_sha, argument="base_sha")
    head = _validated_git_object(head_sha, argument="head_sha")
    completed = subprocess.run(
        [
            "git",
            "--literal-pathspecs",
            "diff",
            "--default-prefix",
            "--unified=0",
            "--no-ext-diff",
            f"{base}...{head}",
            "--",
            _validated_source_root(source_root),
        ],
        check=True,
        capture_output=True,
        text=True,
        shell=False,
    )
    result: dict[str, set[int]] = {}
    current_path: str | None = None

    for raw_line in completed.stdout.splitlines():
        if raw_line.startswith("+++ "):
            marker = raw_line[4:]
            current_path = marker[2:] if marker.startswith("b/") else None
            continue
        match = _HUNK_PATTERN.match(raw_line)
        if match is None or current_path is None:
            continue
        start = int(match.group(1))
        count = int(match.group(2) or "1")
        if count:
            result.setdefault(current_path, set()).update(range(start, start + count))

    return result


def coverage_failures(
    coverage_payload: dict[str, Any],
    changes: dict[str, set[int]],
) -> list[str]:
    """Describe uncovered changed statements and branch destinations."""

    failures: list[str] = []
    files = coverage_payload.get("files", {})

    for path, lines in sorted(changes.items()):
        if not path.endswith(".py"):
            continue
        evidence = files.get(path)
        if evidence is None:
            failures.append(f"{path}: no coverage evidence")
            continue

        executed_lines = set(evidence.get("executed_lines", []))
        missing_lines = set(evidence.get("missing_lines", []))
        executable_lines = executed_lines | missing_lines
        uncovered_statements = sorted(lines & missing_lines)
        if uncovered_statements:
            failures.append(
                f"{path}: uncovered changed statements {uncovered_statements}"
            )

        missing_branches = {
            (int(branch[0]), int(branch[1]))
            for branch in evidence.get("missing_branches", [])
        }
        uncovered_branches = sorted(
            branch for branch in missing_branches if branch[0] in lines
        )
        if uncovered_branches:
            failures.append(
                f"{path}: uncovered changed branches {uncovered_branches}"
            )

        excluded_lines = set(evidence.get("excluded_lines", []))
        approved_exclusions = _APPROVED_CHANGED_EXCLUSIONS.get(path, frozenset())
        unapproved_exclusions = sorted(lines & excluded_lines - approved_exclusions)
        if unapproved_exclusions:
            failures.append(f"{path}: excluded changed lines {unapproved_exclusions}")

        changed_executable_lines = lines & executable_lines
        if not changed_executable_lines and any(
            line.strip() and not line.lstrip().startswith("#")
            for line in Path(path).read_text(encoding="utf-8").splitlines()
        ):
            # This is informational only: documentation-only hunks are valid.
            continue

    return failures


def main() -> int:
    """Run the differential coverage gate and return a process exit code."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--coverage-json", default="coverage.json")
    parser.add_argument("--base-sha", required=True)
    parser.add_argument("--head-sha", required=True)
    parser.add_argument("--source-root", default="src")
    args = parser.parse_args()

    payload = json.loads(Path(args.coverage_json).read_text(encoding="utf-8"))
    changes = changed_lines(args.base_sha, args.head_sha, args.source_root)
    failures = coverage_failures(payload, changes)
    if failures:
        print("Changed-production coverage is below 100%:")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print("Changed-production statement and branch coverage: 100%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
