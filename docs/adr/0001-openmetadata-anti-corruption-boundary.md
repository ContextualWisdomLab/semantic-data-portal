# ADR-0001: OpenMetadata interoperability uses an SDP anti-corruption layer

- **Status:** Proposed
- **Date:** 2026-09-03
- **Last updated:** 2026-09-04
- **Decision owner:** Semantic Data Portal
- **Related issue:** #95
- **Implementation PR:** #96

## Context

ContextualWisdomLab products produce physical schema observations, lineage, data quality evidence, ontology labels, data products, contracts, dashboards, model assets, and AI-agent context. Customers may already operate OpenMetadata and expect these products to exchange metadata with it.

Making OpenMetadata the authority for every CWL domain would collapse distinct bounded contexts. Embedding an OpenMetadata SDK in every product would also duplicate mapping, credentials, version handling, retry behavior, privacy controls, and conflict resolution.

The existing Context Fabric architecture assigns Data and AI context to `semantic-data-portal`, enterprise transformation decisions to `enterprise-architecture-core`, cross-product identifiers and event contracts to `context-graph-contracts`, physical schema observations to `pg-erd-cloud`, and inferred relations to LineageWeave. OpenMetadata support must preserve those ownership boundaries.

Three additional interoperability risks require explicit controls.

1. A major-version regular expression can establish that a label looks like OpenMetadata 2.x, but it cannot prove that the payload matches schemas or behavior tested by CWL.
2. OpenMetadata entity UUIDs are scoped to an installation. Different installations inside one tenant may reuse the same UUID.
3. A request body containing a tenant ID is untrusted input. It must not choose the namespace in which a projection is created.

## Decision

`semantic-data-portal` owns the OpenMetadata anti-corruption layer and the admitted Data/AI Context projection.

OpenMetadata remains an external metadata authority. External identity, version, source hash, update time, references, and optional descriptive fields are preserved without promoting the observation to authoritative CWL domain truth. Every result is marked `observed`.

The first implementation slice is read-only and deterministic:

1. Require a verified OIDC bearer actor with `data-analyst`, `admin`, or `platform-admin` role.
2. Require the verified actor tenant to equal the request tenant; reject a mismatch as `404 resource not found`.
3. Require a bounded `source_instance_id` so two installations cannot collide on the same external UUID.
4. Admit an explicitly declared OpenMetadata Table payload and optional EntityLineage payload only through an exact verified release profile.
5. Honor the pinned upstream required-field contract: Table requires `id`, `name`, and `columns`; EntityReference requires `id` and `type`. Optional FQN, name, display name, and href fields remain optional.
6. Normalize table identity, nested columns, owners, domains, data products, data contract, classifications, safe aggregate profile fields, and table/column lineage.
7. Use one snapshot-wide reference registry to reject contradictory type, name, or FQN identities for the same external UUID.
8. Reject malformed UUIDs, unknown lineage endpoints, duplicate column paths, excessive nesting or collections, true cyclic containers, unsafe URLs, embedded URL credentials, and non-finite versions.
9. Treat repeated references to the same acyclic Python container as aliases rather than cycles.
10. Exclude sample rows, DDL, SQL/query text, join samples, column profiles, custom metrics, extension payloads, and transformation functions from the general catalog projection.
11. Record omitted source field classes without copying their values.
12. Limit the HTTP request body to 8 MiB at the router boundary, including direct router embedding and streamed requests without `Content-Length`.
13. Expose the result through `POST /integrations/openmetadata/v1/table-snapshots:normalize`.
14. Return compatibility profile, upstream repository, and exact upstream commit used as the adapter's contract source.

### Projection identity

```text
urn:cwl:{tenant_id}:sdp:openmetadata_table:{source_instance_id}:{openmetadata_uuid}
```

The verified actor supplies the effective tenant. `source_instance_id` is an opaque installation identifier, not a hostname, credential, or provider object ID.

### Exact compatibility profile

The first profile is immutable and has the following identity:

```text
profile_id: openmetadata-table-lineage-2.0.1
canonical_release: 2.0.1
accepted_labels: 2.0.1, 2.0.1-release
upstream_repository: open-metadata/OpenMetadata
upstream_tag: 2.0.1-release
upstream_revision: bf621b166ec12e8c99fcb1c1443442723386fa41
```

It is tested against these upstream schema paths at that revision:

```text
openmetadata-spec/src/main/resources/json/schema/entity/data/table.json
openmetadata-spec/src/main/resources/json/schema/type/entityLineage.json
openmetadata-spec/src/main/resources/json/schema/type/entityReference.json
```

The actual normalization sink resolves the release profile. A caller cannot bypass compatibility admission by importing an internal normalizer directly. `2.0.1-release` is normalized to `2.0.1`; a label such as `2.1.0` fails closed until a distinct verified profile is added.

`OpenMetadataReleaseProfile` validates its own construction: canonical release membership, unique accepted labels, exact lowercase 40-character upstream commit identity, and non-empty schema paths. Profile data is therefore not accepted merely because a module constant was instantiated.

The upstream revision is contract-source provenance. It does not, by itself, prove that a submitted payload was fetched from that Git commit. A successor admission receipt must bind the submitted payload digest, normalized projection digest, installation identity, observation time, and profile identity.

### HTTP application boundary

OpenMetadata routes remain in `src/sdp/openmetadata_routes.py` and are registered by `src/sdp/api.py`.

This preserves a narrow application boundary around authentication, body admission, tenant enforcement, HTTP status mapping, and OpenMetadata-specific DTOs. Moving all route decorators and error translation into the already broad composition root would couple the integration lifecycle to unrelated catalog, graph, enterprise, and browse endpoints. Domain normalization remains in `src/sdp/openmetadata/`.

Durable admission, signed change-event ingestion, outbound synchronization, and additional asset types are successor slices. They must not be hidden inside this read-only normalization PR.

## Context map

```text
Keyverse-compatible OIDC authority
    │ verified actor, tenant, role
    ▼
semantic-data-portal application boundary
    │ bounded OpenMetadata request
    ▼
OpenMetadata anti-corruption layer
    │ safe governed observed projection
    ├──────────────► Contextual Orchestrator / MCP context
    ├──────────────► enterprise-architecture-core impact consumer
    └──────────────► future steward admission ledger
                         ▲
                         │ external metadata authority
                    OpenMetadata installation
```

Rules:

- CWL products do not query another product database.
- `enterprise-architecture-core` consumes released SDP context; it does not call OpenMetadata directly.
- `context-graph-contracts` owns cross-product envelope schemas, not the OpenMetadata client runtime.
- OpenMetadata webhook, API input, descriptions, and tags are untrusted and cannot change CWL policy, tool definitions, or truth status.
- LLM/inferred proposals require steward approval before any future outbound write.
- A release label is not compatibility evidence without a profile bound to exact upstream source and executable fixtures.
- Existing compatibility profiles are not rewritten when a later release changes schema or behavior.
- Request tenant values never override a verified actor tenant.
- External UUID identity is interpreted within tenant and source installation scope.

## Alternatives considered

### Use OpenMetadata as the organization-wide system of record

Rejected. It would move product-domain truth into an external catalog model and weaken the existing federated ownership model. HR, billing, learning, psychometrics, security, and enterprise-architecture facts have different invariants and approval lifecycles.

### Add an OpenMetadata SDK to each CWL product

Rejected. This creates incompatible mappings and distributes credentials, retry behavior, version drift, and conflict logic across repositories.

### Accept every syntactically valid OpenMetadata 2.x release

Rejected. Semantic-version syntax and a shared major version do not establish field-level compatibility. New required properties, enum members, reference shapes, lineage semantics, or sensitive payload classes could be silently misinterpreted. Compatibility must be established by a new immutable profile, schema-drift review, and exact fixtures.

### Use tenant and UUID without a source-installation dimension

Rejected. UUID uniqueness is not guaranteed across independently operated OpenMetadata installations. The resulting projection identifier could merge unrelated external entities.

### Trust the request tenant without bearer verification

Rejected. A caller-controlled tenant would allow namespace spoofing and cross-tenant projection creation.

### Require every optional upstream descriptive field

Rejected. It would make the adapter stricter than the pinned upstream schema and reject valid OpenMetadata snapshots.

### Put the routes directly in `api.py`

Rejected. `api.py` is the composition root for multiple bounded contexts. Keeping OpenMetadata HTTP policy in a focused application module reduces coupling while `api.py` still owns router registration.

### Create a new `openmetadata-gateway` repository immediately

Rejected for the current maturity level. The first capability is a narrow SDP-owned anti-corruption layer without an independent database, release lifecycle, or buyer surface. A separate service is justified later only if throughput, network isolation, or independent deployment establishes a real bounded context.

### Copy all OpenMetadata entities into generic graph tables

Rejected. Generic graph nodes are useful read projections, not a business-rule system of record. Durable ingestion requires normalized external-source, snapshot, receipt, relation, and provenance records before graph projection.

## Consequences

### Benefits

- One compatibility boundary for all CWL products.
- OpenMetadata upgrades are isolated from domain models.
- External and internal authority remain distinguishable.
- Sensitive source content is excluded by construction.
- Two installations cannot collide solely because they reuse a UUID.
- Request bodies cannot choose a tenant independently of verified identity.
- Schema-valid sparse OpenMetadata payloads remain admissible.
- Downstream consumers can identify the exact compatibility profile and upstream contract source.
- Future release support requires an auditable change rather than an implicit regular-expression expansion.
- The pure normalization layer can be tested without network credentials or a live OpenMetadata server.

### Costs

- Only explicitly profiled OpenMetadata releases are admitted.
- HTTP use requires OIDC/JWKS configuration.
- The route buffers a bounded body before parsing so it can enforce the same limit for chunked direct-router embedding.
- Bidirectional synchronization is not available in the first slice.
- Additional entity types require explicit mappings and contract tests.
- Durable replay, conflict resolution, and write receipts need a later persistence model.
- OpenMetadata release drift must be monitored and tested rather than assumed compatible.

## Required successor decisions

1. Deterministic payload, source-identity, and normalized-projection digests plus admission-preview receipt.
2. 3NF external metadata source, snapshot, admission receipt, and projection history.
3. Raw payload retention classification and restricted immutable evidence storage.
4. Signed webhook/change-event verification, inbox deduplication, ordering, replay, and dead-letter evidence.
5. Canonical egress and credential-bound outbound synchronization.
6. Steward approval and optimistic concurrency for ownership, glossary, classification, quality, and lineage writes.
7. Contract ownership split between `semantic-data-portal` and `context-graph-contracts` once multiple independent consumers exist and an immutable released contract is available.

## Verification

The implementation must retain RED-before-GREEN history and prove:

- production statement coverage 100%;
- production branch coverage 100%;
- public API docstrings 100%;
- exact OpenMetadata 2.0.1 fixtures;
- equivalence of the `2.0.1` and `2.0.1-release` aliases;
- rejection of a well-formed but unverified release such as `2.1.0` at every normalization entry point;
- exact profile, upstream repository, upstream revision, and source instance in every projection;
- schema-valid Table without FQN and EntityReference without name;
- snapshot-wide reference consistency;
- acyclic alias acceptance and true cycle rejection;
- non-finite version rejection;
- authenticated same-tenant use and fail-closed 401/403/404 responses;
- streamed request-body rejection above 8 MiB;
- absence of sample, SQL, DDL, and transformation text in serialized projections;
- no outbound network calls, credentials, persistence, catalog mutation, or cross-service SQL in this slice.

## Research traceability

Wiederhold's mediator architecture motivates placing encoded integration knowledge between autonomous data sources and higher-level consumers rather than forcing either side to adopt the other's representation. In this ADR, the OpenMetadata anti-corruption layer is that mediator, while both OpenMetadata and CWL domain owners retain their autonomy.

Bernstein, Madhavan, and Rahm treat schema matching as an independent integration problem with explicit technique selection and evaluation. This supports release-specific compatibility profiles and executable fixtures instead of assuming compatibility from a shared major version.

No paper PDF is redistributed in this repository. Citations link to publisher or bibliographic records only.

## References

Bernstein, P. A., Madhavan, J., & Rahm, E. (2011). Generic schema matching, ten years later. *Proceedings of the VLDB Endowment, 4*(11), 695–701. https://doi.org/10.14778/3402707.3402710

OpenMetadata. (2026). *OpenMetadata 2.0.1 release*. GitHub tag `2.0.1-release`, commit `bf621b166ec12e8c99fcb1c1443442723386fa41`.

OpenMetadata. (2026). *Table JSON schema*. `openmetadata-spec/src/main/resources/json/schema/entity/data/table.json`, commit `bf621b166ec12e8c99fcb1c1443442723386fa41`.

OpenMetadata. (2026). *EntityLineage JSON schema*. `openmetadata-spec/src/main/resources/json/schema/type/entityLineage.json`, commit `bf621b166ec12e8c99fcb1c1443442723386fa41`.

OpenMetadata. (2026). *EntityReference JSON schema*. `openmetadata-spec/src/main/resources/json/schema/type/entityReference.json`, commit `bf621b166ec12e8c99fcb1c1443442723386fa41`.

Wiederhold, G. (1992). Mediators in the architecture of future information systems. *Computer, 25*(3), 38–49. https://doi.org/10.1109/2.121508
