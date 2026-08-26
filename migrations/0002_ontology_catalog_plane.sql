-- Ontology/catalog plane above the document KG (3NF, 2+ word snake_case).
--
-- These tables store buyer-visible catalog objects and opaque references to
-- naruon/DiskSage/commons identifiers. They do not store document bodies,
-- DiskSage ingest batches, TEPP scores, or a local GRC policy registry.

SET search_path = public;

CREATE TABLE IF NOT EXISTS catalog_objects (
    catalog_object_id   TEXT PRIMARY KEY,
    tenant_reference    TEXT NOT NULL,
    object_kind         TEXT NOT NULL,
    object_slug         TEXT NOT NULL,
    display_title       TEXT NOT NULL,
    object_status       TEXT NOT NULL,
    created_by_subject  TEXT NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_reference, object_slug)
);
CREATE INDEX IF NOT EXISTS catalog_objects_tenant_idx
    ON catalog_objects (tenant_reference);
CREATE INDEX IF NOT EXISTS catalog_objects_kind_idx
    ON catalog_objects (tenant_reference, object_kind);

CREATE TABLE IF NOT EXISTS object_definitions (
    definition_id       TEXT PRIMARY KEY,
    catalog_object_id   TEXT NOT NULL REFERENCES catalog_objects (catalog_object_id),
    definition_text     TEXT NOT NULL,
    preferred_language  TEXT NOT NULL,
    definition_status   TEXT NOT NULL,
    recorded_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS object_definitions_object_idx
    ON object_definitions (catalog_object_id);

CREATE TABLE IF NOT EXISTS object_aliases (
    alias_id            TEXT PRIMARY KEY,
    catalog_object_id   TEXT NOT NULL REFERENCES catalog_objects (catalog_object_id),
    alias_text          TEXT NOT NULL,
    alias_language      TEXT NOT NULL,
    UNIQUE (catalog_object_id, alias_text, alias_language)
);
CREATE INDEX IF NOT EXISTS object_aliases_object_idx
    ON object_aliases (catalog_object_id);

CREATE TABLE IF NOT EXISTS document_kg_links (
    document_kg_link_id TEXT PRIMARY KEY,
    catalog_object_id   TEXT NOT NULL REFERENCES catalog_objects (catalog_object_id),
    source_system       TEXT NOT NULL,
    source_object_kind  TEXT NOT NULL,
    source_object_id    TEXT NOT NULL,
    provenance_uri      TEXT,
    link_status         TEXT NOT NULL,
    recorded_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (catalog_object_id, source_system, source_object_id)
);
CREATE INDEX IF NOT EXISTS document_kg_links_object_idx
    ON document_kg_links (catalog_object_id);
CREATE INDEX IF NOT EXISTS document_kg_links_source_idx
    ON document_kg_links (source_system, source_object_id);

CREATE TABLE IF NOT EXISTS concept_object_bindings (
    binding_id          TEXT PRIMARY KEY,
    catalog_object_id   TEXT NOT NULL REFERENCES catalog_objects (catalog_object_id),
    concept_key         TEXT NOT NULL,
    binding_role        TEXT NOT NULL,
    recorded_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (catalog_object_id, concept_key, binding_role)
);
CREATE INDEX IF NOT EXISTS concept_object_bindings_object_idx
    ON concept_object_bindings (catalog_object_id);

CREATE TABLE IF NOT EXISTS commons_score_references (
    score_reference_id  TEXT PRIMARY KEY,
    catalog_object_id   TEXT NOT NULL REFERENCES catalog_objects (catalog_object_id),
    score_system        TEXT NOT NULL,
    score_endpoint      TEXT NOT NULL,
    recorded_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS commons_score_references_object_idx
    ON commons_score_references (catalog_object_id);

CREATE TABLE IF NOT EXISTS object_stewards (
    steward_record_id     TEXT PRIMARY KEY,
    catalog_object_id     TEXT NOT NULL REFERENCES catalog_objects (catalog_object_id),
    steward_subject       TEXT NOT NULL,
    steward_display_name  TEXT NOT NULL,
    recorded_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS object_stewards_object_idx
    ON object_stewards (catalog_object_id);

INSERT INTO schema_migrations (migration_id)
VALUES ('0002_ontology_catalog_plane')
ON CONFLICT (migration_id) DO NOTHING;
