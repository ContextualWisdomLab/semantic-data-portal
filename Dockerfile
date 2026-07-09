# Semantic Data Portal -- application image
# Runs standalone (docker compose up) and is embeddable as a submodule.
FROM python:3.12-slim@sha256:423ed6ab25b1921a477529254bfeeabf5855151dc2c3141699a1bfc852199fbf AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/src

WORKDIR /app

# Install the graph runtime dependencies from a hash-pinned lock file.
COPY requirements-graph.txt ./
COPY src ./src
COPY migrations ./migrations
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh

RUN python -m pip install --require-hashes -r requirements-graph.txt \
    && chmod +x /usr/local/bin/entrypoint.sh \
    # non-root runtime user
    && useradd --create-home --uid 10001 sdp \
    && chown -R sdp:sdp /app

USER sdp

EXPOSE 8000

# Container-level liveness; readiness is served by GET /healthz.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=5 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health').status==200 else 1)" || exit 1

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["uvicorn", "sdp.api:app", "--host", "0.0.0.0", "--port", "8000"]
