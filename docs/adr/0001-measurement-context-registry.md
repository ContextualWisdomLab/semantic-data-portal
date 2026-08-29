# ADR-0001: Measurement Context Registry as an Open Host Service

Status: **Proposed**  
Date: 2026-08-29

## Context

The governed-rater program needs stable references for constructs, criteria,
rubrics, tasks, exact rater configurations, validation studies, rights, and
provenance. Several bounded contexts consume those references:

- `contextual-orchestrator` creates criterion observations;
- `fast-mlsirm` owns the published observation language and numerical
  calibration;
- Psychometrics Commons owns panel, request, adjudication, and result lifecycle;
- TEPP owns temporal monitoring artifacts.

None of those products should copy or privately redefine reference metadata.
Conversely, Semantic Data Portal must not become a measurement data warehouse or
an assessment system of record. Storing raw responses, observations, parameters,
scores, adjudication state, or decisions here would duplicate authority and make
graph projections indistinguishable from domain truth.

Domain-Driven Design calls for a bounded context with its own ubiquitous
language and an explicit service relationship. Semantic Data Portal already
owns ontology, semantic catalog, provenance, rights, version metadata, and
policy-filtered context delivery, so it is the natural home for reference
metadata.

## Decision

Create a `Measurement Context Registry` bounded context exposed as a
policy-filterable Open Host Service.

### Aggregate root

`MeasurementDefinition` owns one exact revision of a governed measurement
definition:

- stable definition reference;
- exact definition and construct revision references;
- mandatory rights and provenance references;
- criterion entities with exact criterion and rubric revisions;
- task entities with exact task revisions and covered criterion references;
- exact reusable rater-configuration entities;
- immutable validation-study references;
- `Draft -> Published -> Superseded` lifecycle;
- explicit successor revision after supersession.

### Entity identities

`CriterionRegistration` contains:

- `criterion_ref`
- `criterion_revision_ref`
- `rubric_revision_ref`

`TaskRegistration` contains:

- `task_ref`
- `task_revision_ref`
- a non-empty unique set of `criterion_refs`

`RaterConfigurationRegistration` contains:

- `configuration_ref`
- `rater_family_ref`
- `provider_authority_ref`
- exact implementation revision
- exact instruction revision
- exact response-schema revision
- workflow mode
- modality channel

The configuration identity matches the published governed-rater language but is
stored here as contextual reference metadata. Invocation instances remain in the
observation/operations contexts.

## Publication invariants

A definition may be published only when:

- at least one criterion is registered;
- at least one task is registered;
- at least one exact rater configuration is registered;
- every task criterion reference resolves inside the aggregate revision;
- criterion identities and revisions are unique;
- task identities and revisions are unique;
- rater-configuration identities are unique;
- mandatory rights and provenance references are present.

Publication freezes all members. A published revision can only be superseded by
an explicit successor revision; it cannot be edited in place.

## Authority exclusions

The Anti-Corruption Layer rejects the following categories rather than storing
them:

- raw response content;
- criterion observations or provider payloads;
- parameter snapshots;
- scores or latent traits;
- placement, pass/fail, certification, or employment decisions;
- hosted adjudication state.

Graph projections may reference those external artifacts by opaque identifier,
but they do not become registry-owned facts.

## Context map

```text
semantic-data-portal
  Measurement Context Registry / Open Host Service
        | immutable reference bundles
        +---------------------+-----------------------+
        v                     v                       v
contextual-orchestrator   fast-mlsirm      psychometrics-commons / TEPP
Observation Context       Calibration      Operations / Monitoring
```

Every consumer pins a released contract version and digest and translates the
context bundle through its own Anti-Corruption Layer. Direct database access and
shared internal Python/Rust entities are prohibited.

## Consequences

### Benefits

- one authoritative revision lineage for constructs, criteria, rubrics, tasks,
  models, procedures, rights, and validation evidence;
- no CEFR or other domain profile becomes the generic framework owner;
- graph and search consumers receive contextual metadata without copying
  operational or numerical truth;
- published definitions are reproducible and rights-aware;
- provider/model/prompt changes produce a new configuration identity rather than
  silently changing an existing rater.

### Costs

- PostgreSQL 3NF persistence and API authorization are follow-up work;
- consumers must resolve opaque references instead of embedding display text;
- domain profiles require explicit adapters and separate rights review;
- registry availability becomes important for authoring and validation, while
  runtime execution must still be able to use pinned immutable bundles.

## Alternatives considered

1. **Store reference metadata in `fast-mlsirm`.** Rejected because numerical
   contracts and reference catalog governance have different lifecycles and
   buyers.
2. **Store all assessment data in Semantic Data Portal.** Rejected because raw
   responses, observations, parameters, and decisions belong to other bounded
   contexts and often have stricter purpose and retention controls.
3. **Create a new shared-kernel repository.** Rejected because released context
   bundles and schemas provide sufficient decoupling without coordinated source
   changes.
4. **Use free-form graph nodes and JSONB as the system of record.** Rejected
   because publication, uniqueness, rights, and referential-closure invariants
   require typed aggregates and normalized persistence.

## Follow-up implementation

1. normalized PostgreSQL tables and temporal revision constraints;
2. tenant and purpose authorization;
3. transactional outbox events for publication and supersession;
4. policy-filtered OpenAPI context-bundle endpoint;
5. graph and vector projections as rebuildable read models;
6. consumer-driven contract tests with the four dependent repositories;
7. domain-profile adapters, with CEFR considered only after the generic core is
   stable.

## Verification

The initial aggregate tests exact and unsafe references, unknown and authority-
leaking fields, entity round trips, collection bounds, duplicate identities,
referential closure, publication immutability, supersession, rehydration, and
caller-mutation isolation. Persistence work must additionally test 3NF,
transactional uniqueness, clean install, upgrade rehearsal, RLS, outbox
atomicity, and graph-projection replay.

## References

Evans, E. (2003). *Domain-driven design: Tackling complexity in the heart of
software*. Addison-Wesley.

Vernon, V. (2013). *Implementing domain-driven design*. Addison-Wesley.
