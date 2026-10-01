"""Regression guard for the dependency findings in the required filesystem scan."""

from pathlib import Path

import pytest
from packaging.requirements import Requirement

ROOT = Path(__file__).resolve().parents[1]
FLOORS = {"anyio": (4, 14, 2), "cryptography": (50, 0, 0), "pyjwt": (2, 15, 0)}
LOCKS = ("requirements.txt", "requirements-dev.txt", "requirements-test.txt", "requirements-graph.txt")


def test_lockfiles_clear_advisory_floors() -> None:
    failures = []
    for lock in LOCKS:
        lines = (ROOT / lock).read_text(encoding="utf-8").splitlines()
        for package, floor in FLOORS.items():
            pins = [line.split("==", 1)[1].split("\\", 1)[0].strip()
                    for line in lines if line.startswith(package + "==")]
            assert len(pins) == 1, (lock, package, pins)
            if tuple(map(int, pins[0].split("."))) < floor:
                failures.append(f"{lock}: {package}=={pins[0]}")
    assert not failures, failures


@pytest.mark.parametrize("python_version", ["3.10", "3.12"])
@pytest.mark.parametrize(
    ("lock", "package", "version", "platform", "machine"),
    [
        ("requirements-graph.txt", "greenlet", "3.2.5", "linux", "x86_64"),
        *[
            ("requirements-dev.txt", "greenlet", "3.2.5", platform, machine)
            for platform, machine in (
                ("linux", "x86_64"), ("win32", "AMD64"),
                ("darwin", "x86_64"), ("darwin", "aarch64"),
            )
        ],
        *[
            (lock, package, version, "win32", "AMD64")
            for lock in ("requirements.txt", "requirements-dev.txt", "requirements-graph.txt")
            for package, version in (("colorama", "0.4.6"), ("tzdata", "2026.2"))
        ],
    ],
)
def test_platform_dependencies_are_hash_pinned(
    lock, package, version, platform, machine, python_version
) -> None:
    blocks = (ROOT / lock).read_text(encoding="utf-8").split("\n")
    indexes = [i for i, line in enumerate(blocks) if line.startswith(package + "==")]
    assert len(indexes) == 1, (lock, package, indexes)
    index = indexes[0]
    requirement = Requirement(blocks[index].rstrip("\\").strip())
    assert str(requirement.specifier) == "==" + version
    assert requirement.marker is not None, (lock, package, "missing platform marker")
    assert requirement.marker.evaluate({
        "sys_platform": platform, "platform_machine": machine,
        "python_version": python_version, "python_full_version": python_version + ".13",
        "implementation_name": "cpython", "platform_python_implementation": "CPython",
    })
    hashes = []
    for line in blocks[index + 1:]:
        if not line.startswith("    --hash="):
            break
        hashes.append(line)
    assert hashes, (lock, package, "missing distribution hashes")
    if package in ("colorama", "tzdata"):
        assert not requirement.marker.evaluate({"sys_platform": "darwin"})
    if package == "greenlet":
        assert not requirement.marker.evaluate({"platform_machine": "s390x"})


@pytest.mark.parametrize(
    "lock,package",
    [(lock, "exceptiongroup") for lock in LOCKS]
    + [(lock, "tomli") for lock in ("requirements-dev.txt", "requirements-test.txt")],
)
def test_python310_backports_are_hash_pinned(lock, package) -> None:
    lines = (ROOT / lock).read_text(encoding="utf-8").splitlines()
    indexes = [i for i, line in enumerate(lines) if line.startswith(package + "==")]
    assert len(indexes) == 1, (package, indexes)
    index = indexes[0]
    requirement = Requirement(lines[index].rstrip("\\").strip())
    assert requirement.marker is not None
    assert requirement.marker.evaluate({"python_full_version": "3.10.13"})
    assert not requirement.marker.evaluate({"python_full_version": "3.12.13"})
    assert lines[index + 1].startswith("    --hash=sha256:")


def test_dev_sqlalchemy_preserves_python310_support() -> None:
    # SQLAlchemy 2.1 requires Python >=3.11; keep the dev lock on the
    # Python 3.10-compatible release already used by the graph/test locks.
    for lock in ("requirements-dev.txt", "requirements-graph.txt", "requirements-test.txt"):
        lines = (ROOT / lock).read_text(encoding="utf-8").splitlines()
        pins = [Requirement(line.rstrip("\\").strip()).specifier
                for line in lines if line.startswith("sqlalchemy==")]
        assert [str(pin) for pin in pins] == ["==2.0.51"], (lock, pins)


def test_graph_cryptography_downgrade_is_rejected(tmp_path, monkeypatch) -> None:
    for lock in LOCKS:
        text = (ROOT / lock).read_text(encoding="utf-8")
        if lock == "requirements-graph.txt":
            line = next(line for line in text.splitlines() if line.startswith("cryptography=="))
            text = text.replace(line, "cryptography==49.0.0 \\")
        (tmp_path / lock).write_text(text, encoding="utf-8")
    monkeypatch.setitem(test_lockfiles_clear_advisory_floors.__globals__, "ROOT", tmp_path)
    with pytest.raises(AssertionError, match=r"requirements-graph\.txt: cryptography==49\.0\.0"):
        test_lockfiles_clear_advisory_floors()
