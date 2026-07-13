-- Semantic Data Portal :: graph + vector schema (Postgres + Apache AGE + pgvector)
--
-- All NEW objects use 2+ word snake_case names, per org rules. Existing
-- Camel/Pascal identifiers elsewhere in the codebase are left untouched.
--
-- Requires a Postgres image with the Apache AGE and pgvector extensions
-- available (see docker-compose.yml -> apache/age image + pgvector build).

-- Extensions -----------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS age;
CREATE EXTENSION IF NOT EXISTS vector;

LOAD 'age';
SET search_path = ag_catalog, "$user", public;

-- Property graph (openCypher via AGE). create_graph is not idempotent, so guard.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM ag_catalog.ag_graph WHERE name = 'semantic_graph') THEN
        PERFORM ag_catalog.create_graph('semantic_graph');
    END IF;
END
$$;

-- Application tables live in the public schema (the AGE graph lives in
-- ag_catalog). Reset the search_path so the tables below are NOT created inside
-- ag_catalog, and so plain (non-AGE) connections resolve them by default.
SET search_path = public;

-- Relational mirror of the graph (fast lookups, joins, edge filtering) -------
CREATE TABLE IF NOT EXISTS graph_nodes (
    node_id          TEXT PRIMARY KEY,
    node_kind        TEXT NOT NULL,
    node_label       TEXT NOT NULL,
    node_properties  JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS graph_nodes_kind_idx ON graph_nodes (node_kind);

CREATE TABLE IF NOT EXISTS graph_edges (
    edge_type        TEXT NOT NULL,
    source_id        TEXT NOT NULL,
    target_id        TEXT NOT NULL,
    edge_properties  JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (edge_type, source_id, target_id)
);
CREATE INDEX IF NOT EXISTS graph_edges_source_idx ON graph_edges (source_id);
CREATE INDEX IF NOT EXISTS graph_edges_target_idx ON graph_edges (target_id);

-- Ontology concepts (broader/narrower/related/aliases/multilingual) ----------
CREATE TABLE IF NOT EXISTS ontology_concepts (
    concept_key           TEXT PRIMARY KEY,
    concept_definition    TEXT NOT NULL DEFAULT '',
    concept_aliases       JSONB NOT NULL DEFAULT '[]'::jsonb,
    concept_broader       TEXT,
    concept_narrower      JSONB NOT NULL DEFAULT '[]'::jsonb,
    concept_related       JSONB NOT NULL DEFAULT '[]'::jsonb,
    concept_multilingual  JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Dataset nodes (catalog datasets projected into the graph) ------------------
CREATE TABLE IF NOT EXISTS dataset_nodes (
    dataset_id       TEXT PRIMARY KEY,
    dataset_title    TEXT NOT NULL,
    dataset_domain   TEXT,
    dataset_owner    TEXT,
    dataset_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Semantic embeddings for pgvector KNN ---------------------------------------
-- Dimension must match config embedding_dimension (default 128).
CREATE TABLE IF NOT EXISTS embedding_vectors (
    node_id     TEXT PRIMARY KEY,
    node_kind   TEXT NOT NULL,
    embedding   vector(128) NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Cosine-distance ANN index (ivfflat). Safe to create after some rows exist;
-- IF NOT EXISTS keeps the migration idempotent.
CREATE INDEX IF NOT EXISTS embedding_vectors_cosine_idx
    ON embedding_vectors USING ivfflat (embedding vector_cosine_ops) WITH (lists = 10);

-- Application config KV (no runtime os.getenv for app config/secrets) --------
CREATE TABLE IF NOT EXISTS config_entries (
    config_namespace  TEXT NOT NULL DEFAULT 'default',
    config_key        TEXT NOT NULL,
    config_value      JSONB NOT NULL,
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (config_namespace, config_key)
);

-- Migration bookkeeping ------------------------------------------------------
CREATE TABLE IF NOT EXISTS schema_migrations (
    migration_id  TEXT PRIMARY KEY,
    applied_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
INSERT INTO schema_migrations (migration_id)
VALUES ('0001_init_graph_vector')
ON CONFLICT (migration_id) DO NOTHING;
