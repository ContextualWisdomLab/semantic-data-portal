"""Dependency source/lock synchronization and artifact-integrity contracts."""

from __future__ import annotations

from pathlib import Path
import tomllib

_ROOT = Path(__file__).resolve().parents[1]
_PYPDF_VERSION = "6.15.0"
_PYPDF_HASHES = {
    "14e001d6504822cb1ca9c7ed9a69bccb320f59b320730f55af804361abe4d5ee",
    "d39c4d955a76409284a905e2d65b40076d77ab76129e0faaeeb6612403ecfc79",
}


def test_pypdf_security_floor_is_identical_in_source_and_hash_locks() -> None:
    """The fixed pypdf version and both PyPI artifact hashes stay synchronized."""

    project = tomllib.loads((_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    dependencies = project["project"]["dependencies"]
    assert f"pypdf=={_PYPDF_VERSION}" in dependencies

    test_input = (_ROOT / "requirements-test.in").read_text(encoding="utf-8")
    assert test_input.count(f"pypdf=={_PYPDF_VERSION}") == 1

    for lock_name in ("requirements.txt", "requirements-dev.txt", "requirements-test.txt"):
        lock = (_ROOT / lock_name).read_text(encoding="utf-8")
        assert lock.count(f"pypdf=={_PYPDF_VERSION}") == 1
        for digest in _PYPDF_HASHES:
            assert f"--hash=sha256:{digest}" in lock
