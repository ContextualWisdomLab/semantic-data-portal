# Semantic Data Portal -- application image
# Runs standalone (docker compose up) and is embeddable as a submodule.
FROM python:3.12-slim@sha256:423ed6ab25b1921a477529254bfeeabf5855151dc2c3141699a1bfc852199fbf

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1
ENV PYTHONPATH=/app/src
ENV SDP_SQLITE_PATH=/data/sdp-evidence.sqlite3

WORKDIR /app

# Install the app + graph runtime dependencies from hash-pinned lock files.
COPY requirements.txt requirements-graph.txt ./
COPY src ./src
COPY migrations ./migrations
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh

RUN python -m pip install --require-hashes -r requirements.txt \
  && python -m pip install --require-hashes -r requirements-graph.txt \
  && chmod +x /usr/local/bin/entrypoint.sh

# Run as a non-root user to avoid container-escape risk (Trivy DS-0002 / CIS Docker 4.1).
# Create an unprivileged user and give it ownership of the app and writable data dir.
RUN groupadd --system --gid 10001 sdp \
  && useradd --system --uid 10001 --gid sdp --home-dir /app --no-create-home sdp \
  && mkdir -p /data \
  && chown -R sdp:sdp /app /data

EXPOSE 8000

USER 10001:10001

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).read()"

# Applies graph migrations + seed when SDP_DATABASE_DSN is set, then execs CMD.
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["uvicorn", "sdp.api:app", "--host", "0.0.0.0", "--port", "8000"]
