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


def test_changed_sdp_core_file_without_evidence_fails() -> None:
    """The common ``src`` root includes both sdp and sdp_core production code."""

    path = "src/sdp_core/contracts.py"
    failures = check_diff_coverage.coverage_failures({"files": {}}, {path: {46}})

    assert failures == [f"{path}: no coverage evidence"]
