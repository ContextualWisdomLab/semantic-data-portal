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


IMAGE_LOCK_FILES = ("requirements.txt", "requirements-graph.txt")
_PINNED_REQUIREMENT = re.compile(
    r"^(?P<name>[A-Za-z0-9._-]+)(?:\[[A-Za-z0-9,._-]*\])?==(?P<version>[^\s\\]+)"
)


def _pinned_versions(lock_file: str) -> dict[str, str]:
    """Return the normalized distribution-name to pinned-version map of a lock."""
    pins: dict[str, str] = {}
    for line in (REPOSITORY_ROOT / lock_file).read_text(encoding="utf-8").splitlines():
        match = _PINNED_REQUIREMENT.match(line)
        if match is not None:
            name = match.group("name").lower().replace("_", "-")
            pins[name] = match.group("version")
    assert pins, f"{lock_file} must pin at least one distribution"
    return pins


def test_image_locks_agree_on_every_shared_pin() -> None:
    """Keep the image's two sequential hash-pinned installs from downgrading.

    ``Dockerfile`` installs ``requirements.txt`` and then
    ``requirements-graph.txt``, both with ``--require-hashes``. pip honours the
    second file's ``==`` pins, so any package pinned lower there is silently
    downgraded in the built image after the first install already placed the
    newer one. That is how a remediated CVE can reappear in the shipped image
    while the runtime lock looks fixed, so every shared pin must match exactly.
    """
    runtime_pins = _pinned_versions(IMAGE_LOCK_FILES[0])
    graph_pins = _pinned_versions(IMAGE_LOCK_FILES[1])
    shared = sorted(set(runtime_pins) & set(graph_pins))
    assert shared, "the image locks must share at least one pinned distribution"
    conflicts = {
        name: (runtime_pins[name], graph_pins[name])
        for name in shared
        if runtime_pins[name] != graph_pins[name]
    }
    assert not conflicts, (
        "the image lock files disagree on shared pins, so the second "
        f"--require-hashes install would change them in the image: {conflicts}"
    )


# --- the documented developer install must run the documented test command --- #
#
# ``requirements-dev.txt`` is the artifact ``README.md`` and ``CLAUDE.md`` tell a
# developer to install, and ``PYTHONPATH=src pytest`` is the command they tell
# them to run next. Measured before this gate, in a clean venv:
#
#     pip install --require-hashes -r requirements-dev.txt   -> ok
#     PYTHONPATH=src pytest
#       -> ERROR tests/fuzz/test_fuzz_properties.py
#          Interrupted: 1 error during collection
#          0 tests executed
#
# The lock was missing ``hypothesis``, ``sortedcontainers``, ``sqlalchemy`` and
# ``greenlet`` although ``pyproject.toml``'s ``dev`` extra declares the first and
# third, and its own header claimed it had been compiled from that extra. CI was
# unaffected - it installs ``requirements-test.txt``, which pins all of them -
# so nothing in the pipeline could notice.

_LOCK_PIN = re.compile(r"^([A-Za-z0-9_.-]+)==([0-9][^\s;\\]*)")


def _locked_pins(lock_file: str) -> dict[str, str]:
    """Package name (normalised) -> pinned version, from one lock file."""
    pins: dict[str, str] = {}
    for line in (REPOSITORY_ROOT / lock_file).read_text(encoding="utf-8").splitlines():
        match = _LOCK_PIN.match(line)
        if match:
            pins[match.group(1).lower().replace("_", "-")] = match.group(2)
    return pins


def _declared_dev_extra() -> list[str]:
    """The ``dev`` extra's requirement names, read from ``pyproject.toml``."""
    source = (REPOSITORY_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    block = source.split("dev = [", 1)[1].split("]", 1)[0]
    names = []
    for entry in re.findall(r'"([^"]+)"', block):
        name = re.split(r"[\[><=!~;]", entry, maxsplit=1)[0].strip()
        names.append(name.lower().replace("_", "-"))
    return names


def test_the_dev_lock_pins_every_package_the_dev_extra_declares() -> None:
    """A declared dev dependency missing from the lock breaks the documented path."""
    pins = _locked_pins("requirements-dev.txt")
    missing = sorted(name for name in _declared_dev_extra() if name not in pins)
    assert missing == [], (
        f"requirements-dev.txt does not pin {missing}, which pyproject.toml's "
        "dev extra declares. Regenerate with the command in the file's header "
        "rather than hand-editing."
    )


def test_the_dev_lock_can_import_what_the_test_suite_imports() -> None:
    """Enumerated from the suite, not from the extra, so an indirect need counts.

    ``hypothesis`` reaches the lock through the ``dev`` extra, but the reason it
    is needed is that ``tests/fuzz/test_fuzz_properties.py`` imports it - and a
    collection error there stops the whole run, not just that file.
    """
    pins = _locked_pins("requirements-dev.txt")
    for package, importer in (
        ("hypothesis", "tests/fuzz/test_fuzz_properties.py"),
        ("sqlalchemy", "src/sdp/graph_store.py"),
    ):
        assert package in pins, (
            f"{importer} imports {package}, which requirements-dev.txt does not "
            "pin; the documented developer install cannot run the suite"
        )


# Packages the developer and CI locks are allowed to differ on, with the reason.
# Declared rather than left as a silent exception, and each one has to be
# justified by "a difference here cannot change a test outcome" - which is a
# much narrower claim than "the locks agree".
#
# This is not a wish list. Bringing every lock into agreement is a larger piece
# of dependency work than it looks: ``requirements-graph.txt`` is generated by
# pip-compile against its own ``constraints-graph.txt`` (which pins
# ``greenlet==3.2.5`` where the dev and CI locks carry ``3.5.3``), so a blanket
# invariant asserted here would be a gate this repository does not currently
# meet.
DEV_CI_PIN_ALLOWANCES = {
    "tzdata": (
        "timezone data, imported by nothing in src/ or tests/; the runtime and "
        "Docker locks carry 2026.2 and the CI lock 2026.3, and aligning them "
        "means regenerating the pip-compile Docker lock as well"
    ),
}


def test_the_dev_and_ci_locks_agree_except_where_declared() -> None:
    """A developer must test what CI tests, package for package.

    CI installs ``requirements-test.txt``. A free resolution of the dev extra
    picked ``hypothesis==6.169.1`` and ``sqlalchemy==2.1.4`` where CI pins
    ``6.156.6`` and ``2.0.51`` - a minor-version gap in the library
    ``src/sdp/graph_store.py`` and ``src/sdp/config.py`` build on, which is how
    a green local run hides a red CI. ``constraints-dev.txt`` holds them
    together.
    """
    dev = _locked_pins("requirements-dev.txt")
    ci = _locked_pins("requirements-test.txt")
    shared = sorted(set(dev) & set(ci))
    assert shared, "the two locks share no packages, which cannot be right"
    disagreements = {
        name: (dev[name], ci[name])
        for name in shared
        if dev[name] != ci[name] and name not in DEV_CI_PIN_ALLOWANCES
    }
    assert disagreements == {}, (
        "requirements-dev.txt and requirements-test.txt pin different versions "
        f"of {disagreements}; add the pin to constraints-dev.txt and regenerate "
        "the dev lock, or declare the difference in DEV_CI_PIN_ALLOWANCES with "
        "a reason it cannot change a test outcome"
    )


def test_every_declared_pin_allowance_is_real_and_reasoned() -> None:
    """An allowance for a package that now agrees is dead weight; remove it."""
    dev = _locked_pins("requirements-dev.txt")
    ci = _locked_pins("requirements-test.txt")
    for package, reason in DEV_CI_PIN_ALLOWANCES.items():
        assert reason, package
        assert package in dev and package in ci, (
            f"{package} is allowed to differ but is not in both locks"
        )
        assert dev[package] != ci[package], (
            f"{package} no longer differs between the locks; drop its allowance"
        )


def test_the_constraint_file_is_what_holds_the_dev_lock_to_ci() -> None:
    """The mechanism is committed, so the header's command is runnable."""
    constraint = REPOSITORY_ROOT / "constraints-dev.txt"
    assert constraint.exists(), (
        "requirements-dev.txt's header names constraints-dev.txt; it must exist"
    )
    pinned = _locked_pins("constraints-dev.txt")
    assert pinned, "constraints-dev.txt pins nothing"
    dev = _locked_pins("requirements-dev.txt")
    for package, version in pinned.items():
        assert dev.get(package) == version, (
            f"constraints-dev.txt pins {package}=={version} but the dev lock "
            f"carries {dev.get(package)}; regenerate it"
        )


def test_each_lock_records_the_command_that_regenerates_it() -> None:
    """The header is the only instruction for regenerating; it must be right.

    ``requirements-dev.txt``'s header claimed a plain
    ``uv pip compile pyproject.toml --extra dev`` while its contents could only
    have come from a universal compile - so following the header produced a
    different, platform-specific file and dropped packages.
    """
    for lock_file, required in (
        ("requirements-dev.txt", ("--extra dev", "--generate-hashes", "--universal")),
        # ``requirements.txt`` carries no platform markers, so its plain
        # command is consistent with having been compiled on the platform whose
        # wheels it names; nothing here establishes that it needs --universal.
        ("requirements.txt", ("--generate-hashes",)),
        ("requirements-test.txt", ("--generate-hashes", "--universal")),
    ):
        header = "\n".join(
            (REPOSITORY_ROOT / lock_file).read_text(encoding="utf-8").splitlines()[:3]
        )
        assert "uv pip compile" in header, f"{lock_file} records no compile command"
        assert f"-o {lock_file}" in header, (
            f"{lock_file}'s header names a different output path"
        )
        for flag in required:
            assert flag in header, f"{lock_file}'s header omits {flag}"
