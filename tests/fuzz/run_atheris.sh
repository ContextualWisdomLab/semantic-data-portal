#!/usr/bin/env bash
# Bounded Atheris coverage-guided fuzz runner.
#
# Runs every harness in tests/fuzz/atheris for a short, fixed wall-clock budget
# so it is safe to call on PRs without blowing CI cost. Any crash (non-zero
# exit from a harness) fails the whole run.
#
# Usage:
#   tests/fuzz/run_atheris.sh                # 60s per target (PR default)
#   FUZZ_SECONDS=300 tests/fuzz/run_atheris.sh   # longer nightly run
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HARNESS_DIR="${REPO_ROOT}/tests/fuzz/atheris"
CORPUS_DIR="${REPO_ROOT}/tests/fuzz/corpus"
SECONDS_PER_TARGET="${FUZZ_SECONDS:-60}"

# Make `sdp` and `tests` importable for the harnesses.
export PYTHONPATH="${REPO_ROOT}:${REPO_ROOT}/src:${PYTHONPATH:-}"

status=0
for harness in "${HARNESS_DIR}"/fuzz_*.py; do
  name="$(basename "${harness}" .py)"
  target="${name#fuzz_}"
  corpus="${CORPUS_DIR}/${target}"
  # Snapshot pre-existing reproducer files so a crash can be attributed to the
  # target that just produced it (libFuzzer writes crash-/oom-/timeout- files
  # into the CWD, which persist across targets within one run).
  shopt -s nullglob
  before=(crash-* oom-* timeout-*)
  shopt -u nullglob
  echo "::group::fuzz ${target} (${SECONDS_PER_TARGET}s)"
  # -max_total_time bounds the run; -close_fd_mask keeps libFuzzer output tidy.
  python "${harness}" \
    -max_total_time="${SECONDS_PER_TARGET}" \
    -close_fd_mask=3 \
    "${corpus}"
  rc=$?
  echo "::endgroup::"
  if [ "${rc}" -ne 0 ]; then
    echo "FUZZ FAILURE: ${target} exited with ${rc}"
    # Surface the reproducer in the log so the failure cause is diagnosable
    # directly from the run (the crash-* artifact is also uploaded, but log
    # visibility means no artifact download is needed to reproduce).
    shopt -s nullglob
    after=(crash-* oom-* timeout-*)
    shopt -u nullglob
    for repro in "${after[@]}"; do
      is_new=1
      for old in "${before[@]}"; do
        [ "${repro}" = "${old}" ] && is_new=0 && break
      done
      [ "${is_new}" -eq 0 ] && continue
      echo "::group::crash reproducer ${repro} (target ${target})"
      echo "target=${target} file=${repro} bytes=$(wc -c <"${repro}") sha256=$(sha256sum "${repro}" | cut -d' ' -f1)"
      echo "reproduce locally: base64 -d > repro.bin <<'B64' && PYTHONPATH=src:. python ${harness} repro.bin"
      base64 "${repro}"
      echo "B64"
      echo "::endgroup::"
    done
    status=1
  fi
done

exit "${status}"
