"""Regression contracts for production dependency security floors."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOCK_FILES = (
    ROOT / "requirements.txt",
    ROOT / "requirements-dev.txt",
    ROOT / "requirements-test.txt",
)
CRYPTOGRAPHY_PIN = "cryptography==50.0.0"


def test_runtime_metadata_pins_patched_cryptography_release() -> None:
    """Project metadata keeps CVE-2026-69247 outside the resolver graph."""

    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    test_input = (ROOT / "requirements-test.in").read_text(encoding="utf-8")

    assert f'"{CRYPTOGRAPHY_PIN}"' in pyproject
    assert re.search(rf"(?m)^{re.escape(CRYPTOGRAPHY_PIN)}$", test_input)


def test_every_installable_lock_uses_patched_cryptography_release() -> None:
    """Every hash-locked installation surface resolves cryptography 50.0.0."""

    for lock_file in LOCK_FILES:
        lock_text = lock_file.read_text(encoding="utf-8")
        pinned_versions = re.findall(r"(?m)^cryptography==([^ ]+) \\$", lock_text)
        assert pinned_versions == ["50.0.0"], (
            f"{lock_file.name} must contain exactly one cryptography 50.0.0 pin; "
            f"found {pinned_versions!r}"
        )
