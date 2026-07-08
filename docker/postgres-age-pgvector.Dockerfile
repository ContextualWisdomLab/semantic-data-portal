# Postgres image with BOTH Apache AGE (property graph / openCypher) and
# pgvector (semantic KNN) -- a single datastore for the graph engine.
#
# Base: Apache AGE ships on top of postgres:16. We add pgvector by building it
# from source against the same server so `CREATE EXTENSION vector` works.
FROM apache/age:release_PG16_1.6.0

USER root

ARG PGVECTOR_VERSION=v0.7.4
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        curl \
        postgresql-server-dev-16 \
    && update-ca-certificates \
    && curl -fsSL "https://github.com/pgvector/pgvector/archive/refs/tags/${PGVECTOR_VERSION}.tar.gz" -o /tmp/pgvector.tar.gz \
    && mkdir -p /tmp/pgvector \
    && tar -xzf /tmp/pgvector.tar.gz -C /tmp/pgvector --strip-components=1 \
    && cd /tmp/pgvector \
    # OPTFLAGS="" disables -march=native, which segfaults when the build host's
    # CPU features differ from the runtime (common in VM/emulated builders).
    && make OPTFLAGS="" \
    && make OPTFLAGS="" install \
    && rm -rf /tmp/pgvector /tmp/pgvector.tar.gz \
    && apt-get purge -y build-essential curl postgresql-server-dev-16 \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

# AGE preloads via shared_preload_libraries; pgvector needs no preload.
USER postgres
