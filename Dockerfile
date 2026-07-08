FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/src
ENV SDP_SQLITE_PATH=/data/sdp-evidence.sqlite3

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --no-cache-dir .

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

CMD ["uvicorn", "sdp.api:app", "--host", "0.0.0.0", "--port", "8000"]
