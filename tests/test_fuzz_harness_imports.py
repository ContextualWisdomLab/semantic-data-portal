"""The coverage-guided harness must import the way ClusterFuzzLite runs it.

``fuzz/fuzz_query_safety.py`` is the Atheris target for ``validate_sql_query``.
When that function gained a ``declared_relation`` parameter, the harness was put
on the same shared oracle as the Hypothesis mirror so the two engines cannot
disagree about what counts as a violation. The import that achieved it broke the
harness in **two independent ways**, and a checkout shows neither:

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
Hypothesis job imports the oracle directly.

And **no pipeline ever builds that image** - not this repository's three
workflows, and not the organization's central required workflows, whose only
ClusterFuzzLite entry is a reusable ``workflow_call`` with no caller here. So the
sentence this docstring used to carry - that the image is where the breakage
shows - named a venue that is never reached. This file is the only thing standing
between the ClusterFuzzLite entrypoint and silence, and that is the whole of it
rather than the first of several.
``tests/test_fuzzing_posture_is_what_runs.py`` ties these paragraphs to the
derived pipeline state in both directions.

The first version of this guard reproduced the path *order* only, and passed
while the image stayed broken - ``tests/`` exists in a checkout. A guard whose
premise is wider than the thing it guards is the defect it exists to catch, one
layer up. So the file set is now read **out of the Dockerfile** and materialised
in a sandbox: add a ``COPY`` and the sandbox follows, drop one and the guard
reddens.
"""

from __future__ import annotations

import ast
import json
import re
import shutil
import subprocess
import sys
import tempfile
from importlib.metadata import packages_distributions
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
    tree = ast.parse(HARNESS.read_text())
    modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and node.module
        and any(alias.name == "check_validate_sql_query" for alias in node.names)
    }
    assert len(modules) == 1, (
        "the harness no longer imports the shared query-safety oracle from "
        f"exactly one module: {sorted(modules)}"
    )
    # Parsed, not matched with a line regex. The first version used one, and it
    # failed the moment the harness grew a second name and the import wrapped
    # across lines - reporting "no longer imports the oracle" about an import
    # that was right there.
    return modules.pop()


def _third_party_top_level_imports(path: Path) -> set[str]:
    """Top-level module names a file imports that are neither local nor stdlib."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    local = {"sdp", "sdp_core", "tests", "fuzz", "scripts"}
    return {
        name
        for name in names
        if name not in local and name not in sys.stdlib_module_names
    }


def _image_installed_distributions() -> set[str]:
    """Distribution names the image installs, read off the Dockerfile's own files."""
    installed: set[str] = set()
    for source, _ in image_spec()["copies"]:  # type: ignore[misc]
        if not source.endswith(".txt"):
            continue
        text = (REPO_ROOT / source).read_text(encoding="utf-8")
        installed |= {
            match.group(1).lower().replace("_", "-")
            for match in re.finditer(r"^([A-Za-z0-9_.\-]+)==", text, re.M)
        }
    return installed


def test_the_harness_imports_nothing_the_image_does_not_install() -> None:
    """The other half of the sandbox's premise: the file set *and* the packages.

    The sandbox below reproduces the image's ``COPY`` set faithfully, and runs
    the probe with **this** interpreter - whose site-packages are the
    development environment's, not the image's. The image installs exactly
    ``requirements.txt`` and ``fuzz-requirements.txt``. So a new third-party
    import in the harness or its oracle would pass the sandbox and kill the
    image at import, which is the failure this file exists to catch, one layer
    up again.

    Scoped to the harness and its oracle on purpose. ``sdp``'s own imports are
    covered by ``requirements.txt`` being the application's lock - an undeclared
    import there breaks installing the app at all, not just fuzzing - whereas
    these two files are the only ones the image needs *in addition*.

    Today the answer is ``atheris`` and nothing else; the point is that the next
    import is checked rather than assumed.
    """
    harness_imports = _third_party_top_level_imports(HARNESS)
    oracle_imports = _third_party_top_level_imports(
        REPO_ROOT / (oracle_module().replace(".", "/") + ".py")
    )
    required = harness_imports | oracle_imports
    installed = _image_installed_distributions()
    assert installed, "no pinned distributions were read off the image's requirement files"

    mapping = packages_distributions()
    unresolved: list[str] = []
    missing: list[str] = []
    for module in sorted(required):
        # The module name as a distribution name, **first**. Consulting
        # ``packages_distributions()`` first made this guard's verdict depend on
        # the *local* environment rather than on the repository: ``atheris`` has
        # no wheel for this repo's 3.11 venv, so the mapping came back empty and
        # the guard failed its fail-closed branch there while passing on 3.12.
        # A guard that answers differently per interpreter is not measuring the
        # image. The direct match covers the ordinary case (``atheris`` ships as
        # ``atheris``) without needing the package present at all.
        if module.lower().replace("_", "-") in installed:
            continue
        distributions = mapping.get(module)
        if not distributions:
            unresolved.append(module)
            continue
        normalised = {name.lower().replace("_", "-") for name in distributions}
        if not normalised & installed:
            missing.append(f"{module} (from {sorted(distributions)})")

    assert not unresolved, (
        f"these imports are not pinned under their own name and this "
        f"environment cannot map them to a distribution either: {unresolved}. "
        "Either the image does not install them - add the pin to "
        "requirements.txt or fuzz-requirements.txt - or the distribution is "
        "named differently from the module, in which case install it here or "
        "record the mapping in this guard."
    )
    assert not missing, (
        "the harness or its oracle imports packages the ClusterFuzzLite image "
        f"does not install: {missing}. The image installs only "
        f"{sorted(installed)}; add the pin to requirements.txt or "
        "fuzz-requirements.txt, or the harness dies at import with nothing "
        "fuzzed - exactly the breakage this file exists to catch."
    )


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
