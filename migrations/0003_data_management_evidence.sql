-- Framework-neutral data-management evidence profile (3NF, 2+ word snake_case).
--
-- This migration stores CWL-owned ownership, critical-element, quality-rule,
-- and observation facts. It deliberately does not reproduce licensed
-- DAMA-DMBOK or DCAM framework prose, questions, scoring, or evidence lists.

SET search_path = public;

CREATE TABLE IF NOT EXISTS data_owner_assignments (
    data_owner_assignment_id TEXT PRIMARY KEY,
    catalog_object_id        TEXT NOT NULL REFERENCES catalog_objects (catalog_object_id),
    tenant_reference         TEXT NOT NULL,
    owner_subject            TEXT NOT NULL,
    owner_display_name       TEXT NOT NULL,
    valid_from               TIMESTAMPTZ NOT NULL,
    valid_to                 TIMESTAMPTZ,
    evidence_reference       TEXT NOT NULL CHECK (evidence_reference LIKE 'https://%'),
    truth_status             TEXT NOT NULL
        CHECK (truth_status IN ('authoritative', 'observed', 'inferred', 'proposed')),
    recorded_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (catalog_object_id, owner_subject, valid_from),
    CHECK (valid_to IS NULL OR valid_to > valid_from)
);
CREATE INDEX IF NOT EXISTS data_owner_assignments_object_idx
    ON data_owner_assignments (tenant_reference, catalog_object_id);
CREATE INDEX IF NOT EXISTS data_owner_assignments_active_idx
    ON data_owner_assignments (tenant_reference, catalog_object_id, valid_to);

CREATE TABLE IF NOT EXISTS critical_data_elements (
    critical_data_element_id TEXT PRIMARY KEY,
    catalog_object_id        TEXT NOT NULL REFERENCES catalog_objects (catalog_object_id),
    tenant_reference         TEXT NOT NULL,
    element_key              TEXT NOT NULL,
    display_name             TEXT NOT NULL,
    definition_text          TEXT NOT NULL,
    data_classification      TEXT NOT NULL
        CHECK (data_classification IN (
            'public', 'internal', 'confidential', 'restricted_pii', 'restricted_financial'
        )),
    evidence_reference       TEXT NOT NULL CHECK (evidence_reference LIKE 'https://%'),
    truth_status             TEXT NOT NULL
        CHECK (truth_status IN ('authoritative', 'observed', 'inferred', 'proposed')),
    recorded_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (catalog_object_id, element_key)
);
CREATE INDEX IF NOT EXISTS critical_data_elements_object_idx
    ON critical_data_elements (tenant_reference, catalog_object_id);

CREATE TABLE IF NOT EXISTS data_quality_rules (
    data_quality_rule_id     TEXT PRIMARY KEY,
    critical_data_element_id TEXT NOT NULL
        REFERENCES critical_data_elements (critical_data_element_id),
    catalog_object_id        TEXT NOT NULL REFERENCES catalog_objects (catalog_object_id),
    tenant_reference         TEXT NOT NULL,
    rule_code                TEXT NOT NULL,
    rule_description         TEXT NOT NULL,
    metric_code              TEXT NOT NULL,
    threshold_operator       TEXT NOT NULL,
    threshold_value          NUMERIC NOT NULL,
    unit_code                TEXT NOT NULL,
    evidence_reference       TEXT NOT NULL CHECK (evidence_reference LIKE 'https://%'),
    truth_status             TEXT NOT NULL
        CHECK (truth_status IN ('authoritative', 'observed', 'inferred', 'proposed')),
    recorded_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (critical_data_element_id, rule_code)
);
CREATE INDEX IF NOT EXISTS data_quality_rules_element_idx
    ON data_quality_rules (tenant_reference, critical_data_element_id);
CREATE INDEX IF NOT EXISTS data_quality_rules_object_idx
    ON data_quality_rules (tenant_reference, catalog_object_id);

CREATE TABLE IF NOT EXISTS data_quality_observations (
    data_quality_observation_id TEXT PRIMARY KEY,
    data_quality_rule_id        TEXT NOT NULL REFERENCES data_quality_rules (data_quality_rule_id),
    critical_data_element_id    TEXT NOT NULL
        REFERENCES critical_data_elements (critical_data_element_id),
    catalog_object_id           TEXT NOT NULL REFERENCES catalog_objects (catalog_object_id),
    tenant_reference            TEXT NOT NULL,
    source_observation_id       TEXT NOT NULL,
    observed_value              NUMERIC NOT NULL,
    observed_at                 TIMESTAMPTZ NOT NULL,
    quality_status              TEXT NOT NULL,
    evidence_reference          TEXT NOT NULL CHECK (evidence_reference LIKE 'https://%'),
    truth_status                TEXT NOT NULL
        CHECK (truth_status IN ('authoritative', 'observed', 'inferred', 'proposed')),
    recorded_at                 TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (data_quality_rule_id, source_observation_id)
);
CREATE INDEX IF NOT EXISTS data_quality_observations_rule_idx
    ON data_quality_observations (tenant_reference, data_quality_rule_id, observed_at);
CREATE INDEX IF NOT EXISTS data_quality_observations_object_idx
    ON data_quality_observations (tenant_reference, catalog_object_id, observed_at);

INSERT INTO schema_migrations (migration_id)
VALUES ('0003_data_management_evidence')
ON CONFLICT (migration_id) DO NOTHING;
