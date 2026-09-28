"""Lockfile floor for advisories the filesystem scan gates on.

cryptography before 50.0.0 is CVE-2026-69247 (GHSA-g6cj-pr64-35w5).
anyio before 4.14.2 is GHSA-3w57-8xmc-8v26, GHSA-5p39-cfhj-2xmp, and
GHSA-82r6-8w77-94w6. The scan reads every requirements lock in the tree,
so each published lock has to clear the same floor.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCKS = (
    "requirements.txt",
    "requirements-dev.txt",
    "requirements-test.txt",
    "requirements-graph.txt",
)
FLOORS = {
    "cryptography": (50, 0, 0),
    "anyio": (4, 14, 2),
}


def _pins(path: Path) -> dict[str, tuple[int, ...]]:
    found: dict[str, tuple[int, ...]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        for name in FLOORS:
            prefix = f"{name}=="
            if line.startswith(prefix):
                raw = line[len(prefix):].split("\\", 1)[0].strip()
                found[name] = tuple(int(part) for part in raw.split("."))
    return found


def test_lockfiles_clear_advisory_floors() -> None:
    missing: list[str] = []
    low: list[str] = []
    for name in LOCKS:
        pins = _pins(ROOT / name)
        for package, floor in FLOORS.items():
            # graph extra does not pull PyJWT, so cryptography is absent there.
            if package == "cryptography" and name == "requirements-graph.txt":
                continue
            got = pins.get(package)
            if got is None:
                missing.append(f"{name}:{package}")
            elif got < floor:
                low.append(f"{name}:{package}=={'.'.join(map(str, got))}")
    assert not missing, missing
    assert not low, low
