"""Mutation-sensitive contracts for the changed-production coverage gate."""

from __future__ import annotations

import importlib.util
import subprocess
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
    assert observed["args"][:6] == [
        "git",
        "--literal-pathspecs",
        "diff",
        "--default-prefix",
        "--unified=0",
        "--no-ext-diff",
    ]
    assert observed["args"][6] == f"{_BASE_SHA}...{_HEAD_SHA}"
    assert observed["args"][7:] == ["--", "src"]

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
    ["../etc", ":(top)", ":(exclude)src", "*", "?", "src/*.py", "", " "],
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


def _commit_probe_repo(repo: Path, contents: str, message: str) -> str:
    """Write the probe file, commit it, and return the resulting lowercase SHA."""

    target = repo / "src" / "sdp" / "coverage_probe.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(contents, encoding="utf-8")
    subprocess.run(["git", "add", "src/sdp/coverage_probe.py"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", message], cwd=repo, check=True)
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()


def test_changed_lines_collects_files_when_git_prefixes_are_customized(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Hostile ``diff.noprefix`` / prefix config must not hide changed files.

    The parser only accepts ``+++ b/`` paths. Without ``--default-prefix``, a
    repository that sets ``diff.noprefix`` or custom prefixes would collect no
    changed lines and the 100% coverage gate would pass vacuously.
    """

    repo = tmp_path / "probe-repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "ci@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "coverage-gate"], cwd=repo, check=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=repo, check=True)
    base = _commit_probe_repo(repo, "value = 1\n", "base")
    head = _commit_probe_repo(repo, "value = 2\nchanged = True\n", "head")
    subprocess.run(["git", "config", "diff.noprefix", "true"], cwd=repo, check=True)
    subprocess.run(["git", "config", "diff.srcPrefix", "old/"], cwd=repo, check=True)
    subprocess.run(["git", "config", "diff.dstPrefix", "new/"], cwd=repo, check=True)

    monkeypatch.chdir(repo)
    changes = check_diff_coverage.changed_lines(base, head, "src")

    assert changes["src/sdp/coverage_probe.py"] == {1, 2}
