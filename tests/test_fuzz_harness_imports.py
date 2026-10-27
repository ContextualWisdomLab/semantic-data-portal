"""The coverage-guided harness must import the way ClusterFuzzLite runs it.

``fuzz/fuzz_query_safety.py`` is the Atheris target for ``validate_sql_query``.
When that function gained a ``declared_relation`` parameter, the harness was put
on the same shared oracle as the Hypothesis mirror so the two engines cannot
disagree about what counts as a violation. The import that achieved it broke the
harness in **two independent ways**, and the image is the only place either one
shows:

1. ``.clusterfuzzlite/Dockerfile`` sets ``WORKDIR /src`` and
   ``PYTHONPATH=/src/src`` and runs ``CMD ["python", "fuzz/fuzz_query_safety.py"]``.
   Python puts *the script's own directory* on ``sys.path[0]``, so the path is
   ``/src/fuzz`` plus ``/src/src`` - and ``/src`` is on it nowhere.
2. That image did **not contain** ``tests``. It copied ``src`` and ``fuzz`` and
   two requirements files, nothing else. So the oracle was not merely
   unaddressable, it was absent, and no amount of ``sys.path`` repair reaches a
   file that was never copied. Moving the oracle into ``fuzz/`` is not the fix
   either: ``tests/`` has no ``__init__.py``, so ``tests/fuzz`` is itself
   imported as top-level ``fuzz`` and would shadow it. The image copies
   ``tests/fuzz`` instead.

``import tests.fuzz.invariants`` therefore raised ``ModuleNotFoundError: No
module named 'tests'`` before a single input was fuzzed. Nothing caught it: the
repository's own ``.github/workflows/fuzz.yml`` Atheris job runs
``tests/fuzz/run_atheris.sh``, which never runs *this* harness, and the
Hypothesis job imports the oracle directly. This file is the only thing standing
between the ClusterFuzzLite entrypoint and silence.

The first version of this guard reproduced the path *order* only, and passed
while the image stayed broken - ``tests/`` exists in a checkout. A guard whose
premise is wider than the thing it guards is the defect it exists to catch, one
layer up. So the file set is now read **out of the Dockerfile** and materialised
in a sandbox: add a ``COPY`` and the sandbox follows, drop one and the guard
reddens.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = REPO_ROOT / ".clusterfuzzlite" / "Dockerfile"
HARNESS = REPO_ROOT / "fuzz" / "fuzz_query_safety.py"

# ``exec_module`` runs the module body - the imports under test - without
# running ``main()``, so this never starts a fuzz run even where Atheris is
# installed. ``atheris`` is stubbed rather than required: the harness imports it
# *before* the shared oracle, so where Atheris is absent an unstubbed probe dies
# on that and never reaches the import under test.
_PROBE = (
    "import contextlib, importlib.util, os, sys, types;"
    "stub = types.ModuleType('atheris');"
    "stub.instrument_imports = contextlib.nullcontext;"
    "sys.modules['atheris'] = stub;"
    "script = {script!r};"
    "sys.path[0] = os.path.dirname(os.path.abspath(script));"
    "spec = importlib.util.spec_from_file_location('harness_under_test', script);"
    "module = importlib.util.module_from_spec(spec);"
    "spec.loader.exec_module(module);"
    "print('ORACLE_BOUND', hasattr(module, 'check_validate_sql_query'))"
)


def image_spec() -> dict[str, object]:
    """Read the image's workdir, PYTHONPATH, COPY set and CMD off the Dockerfile.

    Deriving these means the simulation cannot drift from the image the way a
    hand-copied path shape did.
    """
    text = DOCKERFILE.read_text()
    workdir = re.search(r"^WORKDIR\s+(\S+)", text, re.M)
    pythonpath = re.search(r"^\s*PYTHONPATH=(\S+)", text, re.M)
    cmd = re.search(r"^CMD\s+(\[[^\]]*\])", text, re.M)
    assert workdir and pythonpath and cmd, "Dockerfile shape changed; update this guard"
    return {
        "workdir": PurePosixPath(workdir.group(1)),
        "pythonpath": [PurePosixPath(p) for p in pythonpath.group(1).split(":") if p],
        "copies": re.findall(r"^COPY\s+(\S+)\s+(\S+)", text, re.M),
        "cmd": json.loads(cmd.group(1)),
    }


def _materialise(sandbox: Path, spec: dict[str, object]) -> None:
    """Build the image's file tree in ``sandbox`` by copying each COPY source.

    Copies, not symlinks. The first version symlinked - and the probe stayed
    green with the oracle's ``COPY`` deleted, because the harness computes its
    bootstrap from ``Path(__file__).resolve()``, which **follows symlinks**: the
    sandbox's ``fuzz`` link resolved back to the real checkout and put the real
    repository root on ``sys.path``, ``tests/`` and all. A sandbox that can
    reach outside itself is not the image; two of the three mutations below came
    back green against it.
    """
    workdir = spec["workdir"]
    for source, destination in spec["copies"]:  # type: ignore[misc]
        origin = REPO_ROOT / source
        assert origin.exists(), f"Dockerfile copies {source!r}, which does not exist"
        target = PurePosixPath(destination)
        if target.is_absolute():
            target = target.relative_to(workdir)
        landing = sandbox / target
        landing.parent.mkdir(parents=True, exist_ok=True)
        if origin.is_dir():
            shutil.copytree(
                origin,
                landing,
                symlinks=False,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
                dirs_exist_ok=True,
            )
        else:
            shutil.copy2(origin, landing)


def _in_image(spec: dict[str, object]) -> subprocess.CompletedProcess[str]:
    """Import the harness inside a tree holding exactly what the image holds."""
    workdir = spec["workdir"]
    script = next(arg for arg in spec["cmd"] if str(arg).endswith(".py"))  # type: ignore[union-attr]
    with tempfile.TemporaryDirectory() as raw:
        sandbox = Path(raw)
        _materialise(sandbox, spec)
        path_entries = [
            str(sandbox / entry.relative_to(workdir)) if entry.is_absolute() else str(sandbox / entry)
            for entry in spec["pythonpath"]  # type: ignore[union-attr]
        ]
        return subprocess.run(
            [sys.executable, "-c", _PROBE.format(script=script)],
            cwd=sandbox,
            capture_output=True,
            text=True,
            env={"PATH": "/usr/bin:/bin", "PYTHONPATH": ":".join(path_entries)},
            timeout=120,
        )


def oracle_module() -> str:
    """Read the oracle's module path out of the harness, not out of this file.

    The harness is free to move its oracle; what must hold is that whatever it
    imports is inside the image. Parsing the import keeps that invariant true
    without this guard naming a path that can go stale.
    """
    source = HARNESS.read_text()
    match = re.search(r"^\s*from\s+([\w.]+)\s+import\s+check_validate_sql_query", source, re.M)
    assert match, "the harness no longer imports the shared query-safety oracle"
    return match.group(1)


def test_the_image_contains_the_oracle_the_harness_imports() -> None:
    """The premise, asserted rather than assumed: the import must be in the image.

    This is the check that was missing. The first version of this guard
    reproduced the image's ``sys.path`` order and nothing else, so it passed
    against a checkout - where ``tests/`` exists - while the image it claimed to
    simulate had no ``tests/`` directory at all.
    """
    spec = image_spec()
    assert HARNESS.is_file(), HARNESS
    copied = {source for source, _ in spec["copies"]}  # type: ignore[misc]
    assert "src" in copied, copied
    assert "fuzz" in copied, copied
    assert any(str(arg).endswith("fuzz/fuzz_query_safety.py") for arg in spec["cmd"])  # type: ignore[union-attr]

    # Every directory on the way to the oracle has to be copied by something.
    oracle = Path(oracle_module().replace(".", "/") + ".py")
    assert (REPO_ROOT / oracle).is_file(), oracle
    assert any(
        oracle == Path(source) or Path(source) in oracle.parents
        for source in copied
    ), (
        f"the harness imports {oracle_module()}, but no COPY in the image brings "
        f"{oracle} into it: {sorted(copied)}"
    )


def test_the_harness_imports_inside_the_image_file_set() -> None:
    """The defect: the oracle was absent from the image, so nothing was fuzzed."""
    result = _in_image(image_spec())
    assert "ModuleNotFoundError" not in result.stderr, (
        "the harness cannot import its shared oracle inside the ClusterFuzzLite "
        f"image's own file set:\n{result.stderr[-2000:]}"
    )


def test_the_harness_binds_the_shared_oracle() -> None:
    """The whole module body must execute, with the oracle actually bound.

    Checking only that one error string is absent would pass on a run that
    failed for some other reason - which is how a guard comes to report success
    because it never got far enough to fail.
    """
    result = _in_image(image_spec())
    assert result.returncode == 0, result.stderr[-2000:]
    assert "ORACLE_BOUND True" in result.stdout, (result.stdout, result.stderr[-800:])
