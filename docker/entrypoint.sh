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
            # Do not fall through to the app. The retry loop cannot tell "the
            # database is not up yet" from a permanent failure (bad DSN, failed
            # migration), and starting anyway would serve traffic against a
            # database whose schema was never established: graph and evidence
            # writes then fail request-by-request behind a container that looks
            # healthy. Exiting non-zero lets the orchestrator's restart policy
            # surface the real failure.
            echo "[entrypoint] migrations failed after ${attempt} attempts; refusing to start" >&2
            exit 1
        fi
        echo "[entrypoint] database not ready yet (attempt ${attempt}); retrying in 2s"
        sleep 2
    done
else
    echo "[entrypoint] no SDP_DATABASE_DSN -- starting on in-memory backend"
fi

exec "$@"
