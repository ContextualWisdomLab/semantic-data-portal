-- DiskSage post-copy catalog lineage.
--
-- These tables are a normalized read-model over file_asset/distribution graph
-- nodes. They intentionally do not add foreign keys to graph_edges: graph seed
-- data may create an edge before both relational mirror nodes exist. Post-copy
-- lineage is stricter and can only reference already-persisted graph nodes.

CREATE TABLE IF NOT EXISTS file_asset_records (
    graph_node_id   TEXT PRIMARY KEY
                    REFERENCES graph_nodes (node_id) ON DELETE RESTRICT,
    tenant_id       TEXT NOT NULL,
    content_sha256  CHAR(64) NOT NULL UNIQUE,
    byte_size       BIGINT NOT NULL CHECK (byte_size >= 0),
    media_type      TEXT NOT NULL,
    asset_title     TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT file_asset_records_digest_check CHECK (
        content_sha256 ~ '^[0-9a-f]{64}$'
        AND graph_node_id = 'urn:sha256:' || content_sha256
    )
);
CREATE INDEX IF NOT EXISTS file_asset_records_tenant_idx
    ON file_asset_records (tenant_id);

CREATE TABLE IF NOT EXISTS file_distribution_records (
    graph_node_id   TEXT PRIMARY KEY
                    REFERENCES graph_nodes (node_id) ON DELETE RESTRICT,
    asset_node_id   TEXT NOT NULL
                    REFERENCES file_asset_records (graph_node_id) ON DELETE RESTRICT,
    provider        TEXT NOT NULL CHECK (
        provider IN (
            'filesystem', 's3', 's3_compatible', 'azure_blob',
            'icloud', 'onedrive', 'google-drive'
        )
    ),
    account_scope   TEXT CHECK (
        account_scope IS NULL
        OR account_scope IN ('personal', 'organization', 'shared', 'unknown')
    ),
    endpoint_id     TEXT NOT NULL,
    available       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS file_distribution_records_asset_idx
    ON file_distribution_records (asset_node_id);

CREATE TABLE IF NOT EXISTS cloud_copy_receipts (
    receipt_id                       CHAR(64) PRIMARY KEY,
    asset_node_id                    TEXT NOT NULL
                                     REFERENCES file_asset_records (graph_node_id)
                                     ON DELETE RESTRICT,
    destination_distribution_node_id TEXT NOT NULL
                                     REFERENCES file_distribution_records (graph_node_id)
                                     ON DELETE RESTRICT,
    candidate_fingerprint            CHAR(64) NOT NULL,
    review_fingerprint               CHAR(64) NOT NULL,
    lineage_fingerprint              CHAR(64) NOT NULL,
    source_locator_sha256            CHAR(64) NOT NULL,
    content_blake3                   CHAR(64) NOT NULL,
    copied_bytes                     BIGINT NOT NULL CHECK (copied_bytes >= 0),
    source_modified_ms               BIGINT NOT NULL CHECK (source_modified_ms >= 0),
    copied_at_ms                     BIGINT NOT NULL CHECK (copied_at_ms > 0),
    production_time_ms               BIGINT NOT NULL CHECK (production_time_ms > 0),
    production_time_source           TEXT NOT NULL,
    production_time_confidence       TEXT NOT NULL CHECK (
        production_time_confidence IN ('high', 'medium', 'low', 'unknown')
    ),
    filesystem_created_ms            BIGINT NOT NULL CHECK (filesystem_created_ms >= 0),
    filesystem_modified_ms           BIGINT NOT NULL CHECK (filesystem_modified_ms > 0),
    copy_verification_method         TEXT NOT NULL,
    local_copy_verified              BOOLEAN NOT NULL CHECK (local_copy_verified),
    provider_write_executed          BOOLEAN NOT NULL DEFAULT FALSE,
    provider_sync_confirmed          BOOLEAN NOT NULL DEFAULT FALSE,
    requires_review                  BOOLEAN NOT NULL,
    review_reason_codes              JSONB NOT NULL DEFAULT '[]'::jsonb CHECK (
        jsonb_typeof(review_reason_codes) = 'array'
    ),
    review_decision_id               TEXT,
    review_disposition               TEXT CHECK (
        review_disposition IS NULL
        OR review_disposition IN ('approved', 'held')
    ),
    reviewed_at_ms                   BIGINT CHECK (reviewed_at_ms > 0),
    reviewed_by                      TEXT,
    review_rationale                 TEXT,
    created_at                       TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT cloud_copy_receipts_digest_check CHECK (
        receipt_id ~ '^[0-9a-f]{64}$'
        AND candidate_fingerprint ~ '^[0-9a-f]{64}$'
        AND review_fingerprint ~ '^[0-9a-f]{64}$'
        AND lineage_fingerprint ~ '^[0-9a-f]{64}$'
        AND source_locator_sha256 ~ '^[0-9a-f]{64}$'
        AND content_blake3 ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT cloud_copy_receipts_review_check CHECK (
        (
            requires_review
            AND jsonb_array_length(review_reason_codes) > 0
            AND review_decision_id IS NOT NULL
            AND review_disposition = 'approved'
            AND reviewed_at_ms IS NOT NULL
            AND reviewed_by IS NOT NULL
            AND review_rationale IS NOT NULL
        )
        OR (
            NOT requires_review
            AND jsonb_array_length(review_reason_codes) = 0
            AND review_decision_id IS NULL
            AND review_disposition IS NULL
            AND reviewed_at_ms IS NULL
            AND reviewed_by IS NULL
            AND review_rationale IS NULL
        )
    )
);
CREATE INDEX IF NOT EXISTS cloud_copy_receipts_asset_idx
    ON cloud_copy_receipts (asset_node_id);
CREATE INDEX IF NOT EXISTS cloud_copy_receipts_distribution_idx
    ON cloud_copy_receipts (destination_distribution_node_id);

CREATE TABLE IF NOT EXISTS file_metadata_evidence_records (
    receipt_id       CHAR(64) NOT NULL
                     REFERENCES cloud_copy_receipts (receipt_id) ON DELETE RESTRICT,
    evidence_order   INTEGER NOT NULL CHECK (evidence_order >= 0),
    evidence_field   TEXT NOT NULL,
    evidence_value   TEXT NOT NULL,
    evidence_source  TEXT NOT NULL,
    confidence       TEXT NOT NULL CHECK (confidence IN ('high', 'medium', 'low', 'unknown')),
    selected         BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (receipt_id, evidence_order)
);
CREATE UNIQUE INDEX IF NOT EXISTS file_metadata_evidence_selected_idx
    ON file_metadata_evidence_records (receipt_id)
    WHERE selected;

CREATE TABLE IF NOT EXISTS cloud_sync_evidence_records (
    evidence_record_id     TEXT PRIMARY KEY,
    receipt_id             CHAR(64) NOT NULL
                           REFERENCES cloud_copy_receipts (receipt_id) ON DELETE RESTRICT,
    evidence_kind          TEXT NOT NULL,
    provider_evidence_id   TEXT NOT NULL,
    confirmed_at_ms        BIGINT NOT NULL CHECK (confirmed_at_ms > 0),
    observed_bytes         BIGINT NOT NULL CHECK (observed_bytes >= 0),
    destination_blake3     CHAR(64) NOT NULL CHECK (
        destination_blake3 ~ '^[0-9a-f]{64}$'
    ),
    sync_complete          BOOLEAN NOT NULL,
    remote_object_id       TEXT,
    remote_revision        TEXT,
    remote_location_bound  BOOLEAN,
    sync_reason_codes      JSONB NOT NULL DEFAULT '[]'::jsonb CHECK (
        jsonb_typeof(sync_reason_codes) = 'array'
    ),
    created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (receipt_id, provider_evidence_id)
);
CREATE INDEX IF NOT EXISTS cloud_sync_evidence_records_receipt_idx
    ON cloud_sync_evidence_records (receipt_id, confirmed_at_ms DESC);

INSERT INTO schema_migrations (migration_id)
VALUES ('0002_file_copy_lineage')
ON CONFLICT (migration_id) DO NOTHING;
