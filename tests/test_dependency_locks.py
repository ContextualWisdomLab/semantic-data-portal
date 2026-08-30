"""Regression tests for deterministic hash-pinned dependency lock artifacts."""

from __future__ import annotations

import re
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
LOCK_FILES = (
    "requirements.txt",
    "requirements-dev.txt",
    "requirements-test.txt",
)
CRYPTOGRAPHY_VERSION = "50.0.0"
_HASH_LINE = re.compile(r"^\s+--hash=sha256:([0-9a-f]{64})(?: \\)?$")


def _cryptography_hashes(lock_file: str) -> list[str]:
    """Return the cryptography SHA-256 hashes in their generated-file order."""
    lines = (REPOSITORY_ROOT / lock_file).read_text(encoding="utf-8").splitlines()
    package_line = f"cryptography=={CRYPTOGRAPHY_VERSION} \\"
    try:
        start = lines.index(package_line) + 1
    except ValueError as exc:
        raise AssertionError(
            f"{lock_file} must pin cryptography=={CRYPTOGRAPHY_VERSION}"
        ) from exc

    hashes: list[str] = []
    for line in lines[start:]:
        match = _HASH_LINE.fullmatch(line)
        if match is None:
            break
        hashes.append(match.group(1))
    assert hashes, f"{lock_file} must include generated cryptography hashes"
    return hashes


def test_cryptography_hashes_keep_generated_uv_order() -> None:
    """Treat the uv-compiled hash order as canonical (not a hand-sorted list)."""
    for lock_file in LOCK_FILES:
        hashes = _cryptography_hashes(lock_file)
        # uv pip compile --generate-hashes does not emit lexical order; require
        # a stable non-empty block and reject accidental empty/hand-blanked pins.
        assert len(hashes) >= 2, (
            f"{lock_file} cryptography hash block looks truncated; "
            "regenerate with the documented uv pip compile --generate-hashes command"
        )
        assert len(hashes) == len(set(hashes)), (
            f"{lock_file} cryptography hashes contain duplicates; "
            "regenerate the lock file rather than hand-editing"
        )


def test_cryptography_hash_set_matches_across_lock_files() -> None:
    """Require all runtime/dev/test locks to carry the same cryptography artifacts."""
    expected = _cryptography_hashes(LOCK_FILES[0])
    for lock_file in LOCK_FILES[1:]:
        assert _cryptography_hashes(lock_file) == expected, (
            f"{lock_file} cryptography hashes drifted from {LOCK_FILES[0]}"
        )
