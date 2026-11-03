"""Every build input of every image must name content, not a movable label.

This repository content-addresses almost everything it consumes: base images
carry an ``@sha256:`` digest, Python dependencies install with
``--require-hashes`` from compiled lock files, and GitHub Actions are pinned by
commit SHA. One input was not, and it was found by an audit rather than by a
check: ``docker/postgres-age-pgvector.Dockerfile`` fetched pgvector from
``archive/refs/tags/${PGVECTOR_VERSION}.tar.gz`` and compiled it as root into
the Postgres server that holds the governed graph and the evidence store. A tag
is a movable ref - one force-push re-points it and the same URL serves different
bytes - so that build had no reproducibility and no supply-chain guarantee at
all.

``docs/product-technical-gap-baseline.md`` recorded it as the only unpinned
build input and deliberately left it unrepaired, because the tarball could not
be downloaded from that environment (the egress proxy answered 403) and writing
a hash nobody had computed would have been the appearance of a pin. What it also
recorded was the other way out - pin the commit and fetch it with git - and that
is what the file does now.

The checks here are written over **every** Dockerfile found in the repository
rather than over the one that was wrong, because a second unpinned input added
later is the same defect and naming the file would not catch it. That is the
distinction this repository keeps having to relearn: a guard that enumerates the
known instances is a guard checked against its own list.

Scope and limits, stated rather than implied:

* A git object name is SHA-1, so a commit pin is weaker than a sha256 content
  digest and stronger than a tag. The test accepts either and does not pretend
  they are equivalent.
* ``git fetch <sha>`` is what enforces the pin: git verifies that the object it
  received hashes to the name requested, so a substituted object fails the build.
  A ``git clone --branch <tag>`` would not, which is why a branch or tag
  argument is refused here even though it looks like a pin.
* Nothing here builds an image. These are file-level assertions; they prove the
  recipe names content, not that the build succeeds.
"""

from __future__ import annotations

from pathlib import Path
import re

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]

# Directories that are not this repository's build recipes: the git metadata and
# the scratch worktrees an agent harness leaves behind, which hold copies of
# these same files at older revisions.
_EXCLUDED_PARTS = {".git", ".claude"}

# Hosts that serve source archives at a path containing a movable ref. Matched
# on the ref component rather than the host, so a mirror is covered too.
_MOVABLE_ARCHIVE = re.compile(
    r"https?://\S*?/(?:archive|tarball|zipball)/"
    r"(?:refs/(?:tags|heads)/|v?\d)",
)

_FORTY_HEX = re.compile(r"\b[0-9a-f]{40}\b")


def _outside_this_checkout(path: Path, root: Path) -> bool:
    """Whether ``path`` sits in a nested copy rather than in ``root`` itself.

    Asked of the **relative** parts, deliberately. Asked of the absolute ones -
    as it was - this answered a different question: the agent worktrees the
    exclusion exists for live at ``<repo>/.claude/worktrees/<id>``, so a checkout
    *at* one of those paths carries ``.claude`` in its own ``parts`` and every
    file in the repository was excluded. ``_dockerfiles()`` returned ``[]``, the
    module-level assert fired inside the ``parametrize`` argument below, and
    pytest ended the session with ``Interrupted: 1 error during collection`` -
    zero tests ran, not just this file's.
    """
    return bool(_EXCLUDED_PARTS & set(path.relative_to(root).parts))


def _dockerfiles(root: Path = REPO_ROOT) -> list[Path]:
    """Every Dockerfile this repository owns, found rather than listed."""
    found = [
        path
        for path in root.rglob("*")
        if path.is_file()
        and (path.name == "Dockerfile" or path.name.endswith(".Dockerfile"))
        and not _outside_this_checkout(path, root)
    ]
    assert found, "no Dockerfile was found; re-point this test"
    return sorted(found)


def _logical_lines(text: str) -> list[str]:
    """Join backslash continuations and drop comment lines, as Docker does.

    Docker removes whole comment lines before executing an instruction,
    including inside a continued ``RUN``, so a check that reads raw lines sees
    prose where the shell sees nothing - and would also split one ``RUN`` into
    fragments and miss a flag that sits on a later line than its command.
    """
    joined: list[str] = []
    buffer = ""
    for raw in text.splitlines():
        stripped = raw.strip()
        if stripped.startswith("#"):
            continue
        if stripped.endswith("\\"):
            buffer += stripped[:-1].rstrip() + " "
            continue
        joined.append((buffer + stripped).strip())
        buffer = ""
    if buffer:
        joined.append(buffer.strip())
    return [line for line in joined if line]


def _unpinned_from_lines(text: str) -> list[str]:
    """The ``FROM`` lines that fetch an image without naming its content.

    A target that an **earlier** ``AS`` in the same file already declared is a
    stage of this build, not a fetched input, so it is exempt. The order matters
    and is the repair: the exemption was previously granted to any line
    containing ``AS``, which exempted ``FROM <registry image> AS <stage>`` - a
    fetch of exactly as much as a bare ``FROM`` - and left the ``named_stages``
    set it then intersected with as dead code. No Dockerfile here is multi-stage
    today, so the hole had no live subject; the first multi-stage build would
    have inherited it silently.
    """
    declared: set[str] = set()
    unpinned: list[str] = []
    for line in _logical_lines(text):
        if not line.upper().startswith("FROM "):
            continue
        target = line.split()[1]
        if target.lower() not in declared and "@sha256:" not in line:
            unpinned.append(line)
        stage = re.search(r"\bAS\s+(\S+)\s*$", line, re.IGNORECASE)
        if stage:
            declared.add(stage.group(1).lower())
    return unpinned


@pytest.mark.parametrize("dockerfile", _dockerfiles(), ids=lambda p: p.name)
def test_every_base_image_is_pinned_by_digest(dockerfile: Path) -> None:
    """``FROM`` must carry an ``@sha256:`` digest, not only a tag.

    A tag on a registry is as movable as a tag on a repository. Both images here
    already carried a digest; this holds that, over whatever ``FROM`` lines
    exist rather than the two that exist today.
    """
    unpinned = _unpinned_from_lines(dockerfile.read_text(encoding="utf-8"))
    assert unpinned == [], (
        f"{dockerfile.relative_to(REPO_ROOT)} builds on an image named by tag "
        f"alone, which the registry can re-point: {unpinned}"
    )


@pytest.mark.parametrize("dockerfile", _dockerfiles(), ids=lambda p: p.name)
def test_no_source_archive_is_fetched_from_a_movable_ref(dockerfile: Path) -> None:
    """No ``curl``/``wget`` of an ``archive/refs/tags/...`` URL.

    This is the shape that was wrong. The URL looks specific because it contains
    a version, and it is not: the bytes behind it are whatever the tag points at
    when the build runs.
    """
    offenders = [
        line
        for line in _logical_lines(dockerfile.read_text(encoding="utf-8"))
        if _MOVABLE_ARCHIVE.search(line)
    ]
    assert offenders == [], (
        f"{dockerfile.relative_to(REPO_ROOT)} downloads a source archive from a "
        f"movable ref: {offenders}. Pin the commit and fetch it with git, which "
        "verifies the object against the name requested, or pin a sha256 you "
        "have actually computed."
    )


@pytest.mark.parametrize("dockerfile", _dockerfiles(), ids=lambda p: p.name)
def test_every_git_fetch_names_an_object_not_a_ref(dockerfile: Path) -> None:
    """A ``git fetch``/``clone`` in a build must name a 40-hex object.

    ``git clone --branch v0.7.4`` is the same defect wearing git's clothes: git
    cannot verify a ref against anything, so the server chooses the content.
    Fetching an object name is verified by git itself.
    """
    lines = _logical_lines(dockerfile.read_text(encoding="utf-8"))
    unverified = [
        line
        for line in lines
        if re.search(r"\bgit\b[^&|;]*\b(fetch|clone)\b", line)
        and not _FORTY_HEX.search(line)
        # A fetch may name the object through a build argument; the argument's
        # own default is checked below.
        and not re.search(r"\$\{?[A-Z_]*COMMIT", line)
    ]
    assert unverified == [], (
        f"{dockerfile.relative_to(REPO_ROOT)} fetches git history without naming "
        f"an object: {unverified}"
    )

    for line in lines:
        if not re.match(r"ARG\s+[A-Z_]*COMMIT=", line):
            continue
        _, _, value = line.partition("=")
        assert _FORTY_HEX.fullmatch(value.strip().strip('"')), (
            f"{dockerfile.relative_to(REPO_ROOT)} declares a *_COMMIT build "
            f"argument that is not a full object name: {line}"
        )


def test_the_pgvector_pin_and_the_version_it_claims_are_checked_against_each_other() -> None:
    """The one build that compiles from source states both, and verifies them.

    Two names have to agree: the commit that fixes the content, and the version
    string the image is labelled with. The commit alone is the pin - but a
    ``PGVECTOR_VERSION`` left behind after the commit moves would label the image
    with a version it does not contain, which is the same class of defect as a
    stale published claim anywhere else in this repository. The build checks the
    pinned tree's own ``vector.control`` rather than trusting the pair.
    """
    dockerfile = REPO_ROOT / "docker" / "postgres-age-pgvector.Dockerfile"
    lines = _logical_lines(dockerfile.read_text(encoding="utf-8"))
    text = "\n".join(lines)

    assert any(re.match(r"ARG PGVECTOR_COMMIT=[0-9a-f]{40}$", line) for line in lines), lines
    assert any(re.match(r"ARG PGVECTOR_VERSION=v\d+\.\d+\.\d+$", line) for line in lines), lines
    assert "git -C /tmp/pgvector fetch -q --depth 1 origin \"${PGVECTOR_COMMIT}\"" in text
    assert (
        "grep -qx \"default_version = '${PGVECTOR_VERSION#v}'\" /tmp/pgvector/vector.control"
        in text
    ), (
        "the build must check the pinned commit's own declared version against "
        "the version this image claims, or the two can drift apart silently"
    )
    assert "curl" not in text, (
        "curl is no longer needed and installing it leaves a fetch tool in a "
        "layer that compiles as root"
    )


# --------------------------------------------------------------------------- #
# The exclusion that excluded the repository.
#
# ``_EXCLUDED_PARTS`` exists to skip the stale copies an agent harness leaves
# under ``.claude/worktrees/``. Applied to each candidate's absolute path it
# also skipped the checkout itself whenever the checkout *was* one of those
# worktrees, which is where every review of this branch ran. Reproduced before
# the repair, in a tree holding a copy of this file and two Dockerfiles::
#
#     $ cd .../.claude/checkout && pytest tests/test_build_input_pinning.py
#     tests/test_build_input_pinning.py:74: in <module>
#         @pytest.mark.parametrize("dockerfile", _dockerfiles(), ...)
#     E   AssertionError: no Dockerfile was found; re-point this test
#     !!!! Interrupted: 1 error during collection !!!!
#     no tests collected, 1 error
#
# The whole session, not this file: the assert runs while pytest evaluates the
# parametrize argument, so collection ends there.
# --------------------------------------------------------------------------- #


def test_the_nested_copy_exclusion_is_measured_against_this_checkout(
    tmp_path: Path,
) -> None:
    """Discovery must find a checkout's own recipes, wherever the checkout is.

    Driven over a real tree rather than over the predicate alone, because the
    defect was in which path the predicate was handed, not in the predicate.
    The nested stale copy stays excluded - that is what the exclusion is for.
    """
    root = tmp_path / ".claude" / "worktrees" / "wf-1"
    (root / "docker").mkdir(parents=True)
    (root / "Dockerfile").write_text("FROM x@sha256:abc\n", encoding="utf-8")
    (root / "docker" / "p.Dockerfile").write_text(
        "FROM y@sha256:def\n", encoding="utf-8"
    )
    stale = root / ".claude" / "worktrees" / "older"
    stale.mkdir(parents=True)
    (stale / "Dockerfile").write_text("FROM tag-only\n", encoding="utf-8")
    (root / ".git").mkdir()
    (root / ".git" / "Dockerfile").write_text("FROM tag-only\n", encoding="utf-8")

    found = [path.relative_to(root).as_posix() for path in _dockerfiles(root)]
    assert found == ["Dockerfile", "docker/p.Dockerfile"], found


def test_the_predicate_names_the_parts_of_the_relative_path() -> None:
    """``.claude`` above the checkout is not ``.claude`` inside it."""
    root = Path("/srv/agent/.claude/worktrees/wf-1")
    assert not _outside_this_checkout(root / "Dockerfile", root)
    assert not _outside_this_checkout(root / "docker" / "a.Dockerfile", root)
    assert _outside_this_checkout(
        root / ".claude" / "worktrees" / "older" / "Dockerfile", root
    )
    assert _outside_this_checkout(root / ".git" / "modules" / "Dockerfile", root)


def test_a_registry_image_named_as_a_stage_is_still_a_fetched_input() -> None:
    """``FROM <image> AS <stage>`` must be pinned; ``FROM <stage> AS ...`` need not.

    The exemption is for a target an earlier ``AS`` declared. Granting it to any
    line containing ``AS`` exempted the first half of every multi-stage build,
    which is the half that fetches.
    """
    text = (
        "FROM python:3.12-slim AS builder\n"
        "RUN true\n"
        "FROM builder AS final\n"
        "FROM debian:bookworm\n"
        "FROM alpine@sha256:beef AS trailer\n"
    )
    assert _unpinned_from_lines(text) == [
        "FROM python:3.12-slim AS builder",
        "FROM debian:bookworm",
    ]
