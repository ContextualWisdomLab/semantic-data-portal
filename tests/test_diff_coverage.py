"""Mutation-sensitive contracts for the changed-production coverage gate."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "check_diff_coverage",
    REPO_ROOT / "tools" / "check_diff_coverage.py",
)
assert SPEC is not None and SPEC.loader is not None
check_diff_coverage = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(check_diff_coverage)

_BASE_SHA = "a" * 40
_HEAD_SHA = "b" * 40


def test_changed_exclusion_cannot_claim_complete_coverage() -> None:
    """A changed ``pragma: no cover`` line must fail rather than disappear."""

    path = "src/sdp/network_security.py"
    payload = {
        "files": {
            path: {
                "executed_lines": [],
                "missing_lines": [],
                "missing_branches": [],
                "excluded_lines": [1],
            }
        }
    }

    failures = check_diff_coverage.coverage_failures(payload, {path: {1}})

    assert failures == [f"{path}: excluded changed lines [1]"]


def test_changed_sdp_core_file_without_evidence_fails(monkeypatch) -> None:
    """The default ``src`` diff actually discovers sdp_core production code."""

    class Completed:
        stdout = """diff --git a/src/sdp_core/contracts.py b/src/sdp_core/contracts.py
+++ b/src/sdp_core/contracts.py
@@ -45,0 +46 @@
+changed_line = True
"""

    observed: dict[str, object] = {}

    def fake_run(*args, **kwargs):
        observed["args"] = args[0] if args else kwargs.get("args")
        observed["shell"] = kwargs.get("shell")
        return Completed()

    monkeypatch.setattr(check_diff_coverage.subprocess, "run", fake_run)
    path = "src/sdp_core/contracts.py"
    changes = check_diff_coverage.changed_lines(_BASE_SHA, _HEAD_SHA, "src")

    assert observed["shell"] is False
    assert observed["args"][:4] == ["git", "diff", "--unified=0", "--no-ext-diff"]
    assert observed["args"][4] == f"{_BASE_SHA}...{_HEAD_SHA}"
    assert observed["args"][5:] == ["--", "src"]

    assert changes == {path: {46}}
    assert check_diff_coverage.coverage_failures({"files": {}}, changes) == [
        f"{path}: no coverage evidence"
    ]


def test_changed_lines_rejects_non_sha_git_arguments() -> None:
    """Option-like git arguments must fail closed before subprocess starts."""

    with pytest.raises(ValueError, match="40-character lowercase git SHA"):
        check_diff_coverage.changed_lines("--output=/tmp/evil", _HEAD_SHA, "src")


@pytest.mark.parametrize(
    "source_root",
    ["../etc", ":(top)", ":(exclude)src"],
)
def test_changed_lines_rejects_unsafe_source_root(source_root: str) -> None:
    """A source root must stay a relative in-repo path, not a git pathspec."""

    with pytest.raises(ValueError, match="relative repository path"):
        check_diff_coverage.changed_lines(_BASE_SHA, _HEAD_SHA, source_root)


def test_changed_lines_treats_malicious_filenames_as_text_only(monkeypatch) -> None:
    """Diff path text is never interpolated into a shell command."""

    class Completed:
        stdout = """diff --git a/; touch /tmp/exploit ;.py b/; touch /tmp/exploit ;.py
+++ b/; touch /tmp/exploit ;.py
@@ -1,0 +2 @@
+payload
"""

    observed: dict[str, object] = {}

    def fake_run(*args, **kwargs):
        observed["args"] = args[0] if args else kwargs.get("args")
        observed["shell"] = kwargs.get("shell")
        return Completed()

    monkeypatch.setattr(check_diff_coverage.subprocess, "run", fake_run)
    changes = check_diff_coverage.changed_lines(_BASE_SHA, _HEAD_SHA, "src")

    assert observed["shell"] is False
    assert all(isinstance(item, str) for item in observed["args"])
    assert "; touch /tmp/exploit ;.py" in changes
    assert changes["; touch /tmp/exploit ;.py"] == {2}
