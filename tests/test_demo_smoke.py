"""Readiness smoke entrypoint tests.

``demo_smoke.main`` aggregates the readiness/demo-plan/validation/connector-probe
summary, prints it as JSON, and returns a process exit code (0 when the ``ready``
gate holds, 1 otherwise). This pins the ``main()`` body so a regression in the exit
contract is caught.
"""

from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sdp import demo_smoke  # noqa: E402


def test_main_returns_int_exit_code(capsys) -> None:
    """main() prints the summary JSON and returns 0 (ready) or 1 (not ready)."""
    code = demo_smoke.main()
    assert code in (0, 1)
    captured = capsys.readouterr()
    assert '"ready"' in captured.out
    assert code == (0 if demo_smoke.smoke_summary()["ready"] else 1)
