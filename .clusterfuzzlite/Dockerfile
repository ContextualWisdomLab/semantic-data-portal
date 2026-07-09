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

CMD ["python", "fuzz/fuzz_query_safety.py", "-runs=1000"]
