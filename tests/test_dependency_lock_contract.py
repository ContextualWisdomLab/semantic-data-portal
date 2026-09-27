"""Dependency source/lock synchronization and artifact-integrity contracts."""

from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_PYPDF_VERSION = "6.16.1"
_PYPDF_HASHES = {
    "63fec31c4092ae50b6729beedcb469055b60d20c834bde1c402df241f371f644",
    "c4d1b43ddae921387321cf63936cd16a7743b91d2da92f165c149a195c972ba9",
}


def test_pypdf_security_floor_is_identical_in_source_and_hash_locks() -> None:
    """The fixed pypdf version and both PyPI artifact hashes stay synchronized."""

    project_source = (_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert project_source.count(f'"pypdf=={_PYPDF_VERSION}",') == 1

    test_input = (_ROOT / "requirements-test.in").read_text(encoding="utf-8")
    assert test_input.count(f"pypdf=={_PYPDF_VERSION}") == 1

    for lock_name in ("requirements.txt", "requirements-dev.txt", "requirements-test.txt"):
        lock = (_ROOT / lock_name).read_text(encoding="utf-8")
        assert lock.count(f"pypdf=={_PYPDF_VERSION}") == 1
        for digest in _PYPDF_HASHES:
            assert f"--hash=sha256:{digest}" in lock
