#!/usr/bin/env sh
# Bootstrap transport: if a database DSN is provided, wait for it, then apply
# migrations + seed. Otherwise the service starts on the in-memory backend.
set -e

if [ -n "${SDP_DATABASE_DSN}" ]; then
    echo "[entrypoint] SDP_DATABASE_DSN set -- applying migrations + seed"
    attempt=0
    until python -m migrations.run_migrations; do
        attempt=$((attempt + 1))
        if [ "${attempt}" -ge 30 ]; then
            echo "[entrypoint] migrations failed after ${attempt} attempts" >&2
            break
        fi
        echo "[entrypoint] database not ready yet (attempt ${attempt}); retrying in 2s"
        sleep 2
    done
else
    echo "[entrypoint] no SDP_DATABASE_DSN -- starting on in-memory backend"
fi

exec "$@"
