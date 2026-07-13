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
  echo "::group::fuzz ${target} (${SECONDS_PER_TARGET}s)"
  # -max_total_time bounds the run; -close_fd_mask keeps libFuzzer output tidy.
  python "${harness}" \
    -max_total_time="${SECONDS_PER_TARGET}" \
    -close_fd_mask=3 \
    "${corpus}"
  rc=$?
  echo "::endgroup::"
  if [ "${rc}" -ne 0 ]; then
    echo "FUZZ FAILURE: ${target} exited with ${rc} (see crash artifact above)"
    status=1
  fi
done

exit "${status}"
