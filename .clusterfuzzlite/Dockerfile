# ClusterFuzzLite image for Semantic Data Portal Python fuzz targets.
#
# Scorecard discovery marker:
# **no workflow in this repository builds or runs this image**.
# The three workflows here (tests.yml, fuzz.yml,
# scorecard-analysis.yml) do not reference ClusterFuzzLite and never have, and
# the organization's only central ClusterFuzzLite workflow is a reusable
# `workflow_call` with no caller here. The CMD below is therefore the shape the
# entrypoint would take, not a pipeline that has ever run. The fuzzing that does
# run is in .github/workflows/fuzz.yml; tests/test_fuzzing_posture_is_what_runs.py
# keeps this comment and that fact in step.
FROM python:3.12-slim@sha256:423ed6ab25b1921a477529254bfeeabf5855151dc2c3141699a1bfc852199fbf

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/src/src

WORKDIR /src

COPY requirements.txt ./requirements.txt
COPY fuzz-requirements.txt ./fuzz-requirements.txt

RUN python -m pip install --no-cache-dir --require-hashes -r requirements.txt \
    && python -m pip install --no-cache-dir --require-hashes -r fuzz-requirements.txt

COPY src ./src
COPY fuzz ./fuzz
# fuzz/fuzz_query_safety.py imports its crash-oracle from
# tests/fuzz/invariants.py so the coverage-guided harness and the Hypothesis
# mirror cannot disagree about what counts as a violation. Without this the
# harness dies on `ModuleNotFoundError: No module named 'tests'` before the
# first input - and nothing in this repository's own CI runs it, so the
# breakage is visible only here. tests/test_fuzz_harness_imports.py reads this
# COPY set and reddens if the oracle's directory stops being copied. Narrowed
# to tests/fuzz on purpose: the rest of the suite is not an image dependency.
COPY tests/fuzz ./tests/fuzz

RUN groupadd --system --gid 10001 sdp-fuzz \
    && useradd --system --uid 10001 --gid sdp-fuzz --home-dir /src --no-create-home sdp-fuzz \
    && chown -R sdp-fuzz:sdp-fuzz /src

USER 10001:10001

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import pathlib; raise SystemExit(0 if pathlib.Path('/src/fuzz/fuzz_query_safety.py').is_file() else 1)"

CMD ["python", "fuzz/fuzz_query_safety.py", "-runs=1000"]
