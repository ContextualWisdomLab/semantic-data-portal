# Postgres image with BOTH Apache AGE (property graph / openCypher) and
# pgvector (semantic KNN) -- a single datastore for the graph engine.
#
# Base: Apache AGE ships on top of postgres:16. We add pgvector by building it
# from source against the same server so `CREATE EXTENSION vector` works.
FROM apache/age:release_PG16_1.6.0@sha256:16aa423d20a31aed36a3313244bf7aa00731325862f20ed584510e381f2feaed

USER root

# pgvector is pinned by COMMIT, not by the release tag it was pinned by before.
# A tag is a mutable ref - one force-push re-points it, and
# archive/refs/tags/v0.7.4.tar.gz then serves different bytes at the same URL -
# and this was the only build input in the repository that was not
# content-addressed. Everything else already is: the base image above carries a
# digest, Python dependencies install with --require-hashes, GitHub Actions are
# pinned by commit SHA.
#
# The pin is enforced by git itself, which is why this is a fetch and not a
# download. ``git fetch <sha>`` verifies that the object it received hashes to
# the name that was asked for, so a server that serves different content under
# this name fails the build rather than compiling it into the extension that
# holds the governed graph and the evidence store.
#
# Measured before pinning: ``git ls-remote https://github.com/pgvector/pgvector
# refs/tags/v0.7.4`` advertises no peeled ``^{}`` ref, so v0.7.4 is a
# lightweight tag and the name below is the commit itself. Verified by fetching
# it - object type ``commit``, subject "Version bump to 0.7.4 [skip ci]", tree
# 97af667455d30dba56b092ce3b9241b991f7f888, carrying Makefile, src/, sql/ and
# vector.control with default_version '0.7.4'.
#
# Why a commit and not a tarball sha256, which would be stronger: the tarball
# cannot be downloaded from the environment this repair was made in (the egress
# proxy answers 403), so its digest could not be computed, and writing an
# unverified hash would be the appearance of a pin rather than a pin - worse
# than none, because nobody re-checks it afterwards. The honest limit of what is
# here: git object names are SHA-1, so this is weaker than a sha256 content
# digest and stronger than a mutable tag. Replacing it with a verified tarball
# digest, computed where the tarball is reachable, is a straight improvement.
ARG PGVECTOR_COMMIT=103ac50f1a90b47a72003e8e8628a55ec372f202
ARG PGVECTOR_VERSION=v0.7.4
WORKDIR /tmp/pgvector
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        git \
        postgresql-server-dev-16 \
    && update-ca-certificates \
    && git init -q /tmp/pgvector \
    && git -C /tmp/pgvector remote add origin https://github.com/pgvector/pgvector \
    && git -C /tmp/pgvector fetch -q --depth 1 origin "${PGVECTOR_COMMIT}" \
    && git -C /tmp/pgvector checkout -q "${PGVECTOR_COMMIT}" \
    # The version this image claims to ship, checked against what the pinned
    # commit actually declares. The commit name already fixes the content, so
    # this does not strengthen the pin - it stops PGVECTOR_VERSION and
    # PGVECTOR_COMMIT drifting apart and labelling the image with a version it
    # does not contain.
    && grep -qx "default_version = '${PGVECTOR_VERSION#v}'" /tmp/pgvector/vector.control \
    # OPTFLAGS="" disables -march=native, which segfaults when the build host's
    # CPU features differ from the runtime (common in VM/emulated builders).
    && make OPTFLAGS="" \
    && make OPTFLAGS="" install \
    && rm -rf /tmp/pgvector \
    && apt-get purge -y build-essential git postgresql-server-dev-16 \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

# AGE preloads via shared_preload_libraries; pgvector needs no preload.
WORKDIR /var/lib/postgresql
USER postgres

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=5 \
    CMD pg_isready -U "${POSTGRES_USER:-postgres}" || exit 1
