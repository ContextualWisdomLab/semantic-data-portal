# ClusterFuzzLite image for Semantic Data Portal Python fuzz targets.
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

RUN groupadd --system --gid 10001 sdp-fuzz \
    && useradd --system --uid 10001 --gid sdp-fuzz --home-dir /src --no-create-home sdp-fuzz \
    && chown -R sdp-fuzz:sdp-fuzz /src

USER 10001:10001

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import pathlib; raise SystemExit(0 if pathlib.Path('/src/fuzz/fuzz_query_safety.py').is_file() else 1)"

CMD ["python", "fuzz/fuzz_query_safety.py", "-runs=1000"]
