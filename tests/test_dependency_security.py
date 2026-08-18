"""Regression contracts for production dependency security floors."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOCK_FILES = (
    ROOT / "requirements.txt",
    ROOT / "requirements-dev.txt",
    ROOT / "requirements-test.txt",
)
CRYPTOGRAPHY_PIN = "cryptography==50.0.0"
# GHSA-g6cj-pr64-35w5: cryptography>=44.0.0,<50.0.0
_AFFECTED_CRYPTOGRAPHY_PIN = re.compile(r"^cryptography\s*==\s*(?:4[4-9])\.", re.IGNORECASE)


def _cryptography_requirement_lines(path: Path) -> list[str]:
    """Return non-comment cryptography requirement lines from a text file."""

    lines: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        candidate = stripped.strip(",").strip('"').strip("'")
        if candidate.lower().startswith("cryptography"):
            lines.append(candidate)
    return lines


def test_runtime_metadata_pins_patched_cryptography_release() -> None:
    """Project metadata keeps CVE-2026-69247 outside the resolver graph."""

    with (ROOT / "pyproject.toml").open("rb") as handle:
        dependencies = tomllib.load(handle).get("project", {}).get("dependencies", [])

    runtime_pins = [
        item.split(";", 1)[0].strip()
        for item in dependencies
        if item.split(";", 1)[0].strip().lower().startswith("cryptography")
    ]
    assert runtime_pins == [CRYPTOGRAPHY_PIN]
    assert not any(_AFFECTED_CRYPTOGRAPHY_PIN.match(item) for item in runtime_pins)

    pyproject_pins = _cryptography_requirement_lines(ROOT / "pyproject.toml")
    assert CRYPTOGRAPHY_PIN in pyproject_pins
    assert not any(_AFFECTED_CRYPTOGRAPHY_PIN.match(item) for item in pyproject_pins)

    test_input_pins = _cryptography_requirement_lines(ROOT / "requirements-test.in")
    assert test_input_pins == [CRYPTOGRAPHY_PIN]
    assert not any(_AFFECTED_CRYPTOGRAPHY_PIN.match(item) for item in test_input_pins)


def test_every_installable_lock_uses_patched_cryptography_release() -> None:
    """Every hash-locked installation surface resolves cryptography 50.0.0."""

    for lock_file in LOCK_FILES:
        lock_text = lock_file.read_text(encoding="utf-8")
        pinned_versions = re.findall(r"(?m)^cryptography==([^ ]+) \\$", lock_text)
        assert pinned_versions == ["50.0.0"], (
            f"{lock_file.name} must contain exactly one cryptography 50.0.0 pin; "
            f"found {pinned_versions!r}"
        )
