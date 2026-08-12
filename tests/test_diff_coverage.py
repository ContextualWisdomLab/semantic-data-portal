"""Mutation-sensitive contracts for the changed-production coverage gate."""

from __future__ import annotations

import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "check_diff_coverage",
    REPO_ROOT / "tools" / "check_diff_coverage.py",
)
assert SPEC is not None and SPEC.loader is not None
check_diff_coverage = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(check_diff_coverage)


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

    monkeypatch.setattr(
        check_diff_coverage.subprocess,
        "run",
        lambda *args, **kwargs: Completed(),
    )
    path = "src/sdp_core/contracts.py"
    changes = check_diff_coverage.changed_lines("base", "head", "src")

    assert changes == {path: {46}}
    assert check_diff_coverage.coverage_failures({"files": {}}, changes) == [
        f"{path}: no coverage evidence"
    ]
