"""Behavioural tests for ``docker/entrypoint.sh``.

The entrypoint is the only thing that applies graph migrations before the API
serves traffic (README: "기동 시 마이그레이션 + 시드를 멱등하게 적용합니다"), so
*whether it starts the app when migrations never succeeded* is a correctness
property, not a style question. These run the real script under ``sh`` with
stubbed ``python``/``sleep`` on ``PATH``; no database and no container needed.
"""

from __future__ import annotations

from pathlib import Path
import subprocess

ENTRYPOINT = Path(__file__).resolve().parents[1] / "docker" / "entrypoint.sh"


def _stub_bin(tmp_path: Path, *, python_exit: int) -> Path:
    """Build a PATH directory where ``python`` exits with the given code and
    ``sleep`` returns immediately (so the retry loop runs without real delay)."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    python_stub = bin_dir / "python"
    python_stub.write_text(f"#!/bin/sh\necho \"stub python $*\"\nexit {python_exit}\n")
    python_stub.chmod(0o755)
    sleep_stub = bin_dir / "sleep"
    sleep_stub.write_text("#!/bin/sh\nexit 0\n")
    sleep_stub.chmod(0o755)
    return bin_dir


def _run(tmp_path: Path, *, python_exit: int, dsn: str | None) -> tuple[subprocess.CompletedProcess[str], Path]:
    bin_dir = _stub_bin(tmp_path, python_exit=python_exit)
    marker = tmp_path / "app_started"
    env = {
        "PATH": f"{bin_dir}:/usr/bin:/bin",
        "HOME": str(tmp_path),
    }
    if dsn is not None:
        env["SDP_DATABASE_DSN"] = dsn
    else:
        env["SDP_DATABASE_DSN"] = ""
    completed = subprocess.run(
        ["sh", str(ENTRYPOINT), "/bin/sh", "-c", f"echo started > {marker}"],
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )
    return completed, marker


def test_entrypoint_refuses_to_start_the_app_when_migrations_never_succeed(tmp_path: Path) -> None:
    """A non-transient migration failure was retried 30 times and then ignored:
    the loop ``break``-ed and fell through to ``exec "$@"``, so the service began
    serving against a database whose schema was never established. Evidence and
    graph writes then fail request-by-request behind a container that looks up.
    Refusing to start surfaces the real failure instead.
    """
    completed, marker = _run(tmp_path, python_exit=1, dsn="postgresql+psycopg://stub/db")
    assert not marker.exists(), "the app must not start when migrations never succeeded"
    assert completed.returncode != 0, "a failed bootstrap must be a failed container start"
    assert "migrations failed" in completed.stderr


def test_entrypoint_starts_the_app_once_migrations_succeed(tmp_path: Path) -> None:
    completed, marker = _run(tmp_path, python_exit=0, dsn="postgresql+psycopg://stub/db")
    assert completed.returncode == 0, completed.stderr
    assert marker.read_text().strip() == "started"


def test_entrypoint_starts_on_the_in_memory_backend_without_a_dsn(tmp_path: Path) -> None:
    """With no DSN the service is documented to run on the in-memory backend, so
    migrations are skipped and the app still starts."""
    completed, marker = _run(tmp_path, python_exit=1, dsn=None)
    assert completed.returncode == 0, completed.stderr
    assert marker.read_text().strip() == "started"
    assert "in-memory backend" in completed.stdout
