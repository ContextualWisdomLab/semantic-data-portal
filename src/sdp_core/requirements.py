"""The PRD requirement inventory, and what in this repository answers each one.

``CLAUDE.md`` names ``docs/implementation-compliance.md`` the requirements
correspondence matrix ("요구사항 대응 매트릭스"). Measured against the PRD it is
meant to cover::

    requirement ids in docs/prd-trd.md          74   (52 functional + 22 NFR)
    ids mentioned anywhere in that matrix       13
    P0 ids absent from it                       25 of 34

So the document a diligence reader opens to see which requirements are met
covered 17% of them, and three quarters of the P0 set were not in it at all.
That is not the same as "not implemented" - most of the absent ones are plainly
built - but a reader cannot tell which, and absence reads as absence.

This module closes it without hand-copying anything: the inventory is **parsed
from the PRD**, so it cannot drift from the source, and every requirement must
carry an explicit coverage entry. ``tests/test_requirements_coverage.py``
enforces that each id is mapped, that every evidence pointer resolves (a route
this app serves, a function that imports, a test that exists), and that a
``implemented`` claim carries at least one pointer that resolved.

Status values, chosen so a claim cannot be stronger than its evidence:

``implemented``
    Something in this repository answers the requirement and a test covers it.
``partial``
    Part of it is answered; ``note`` says what is missing.
``not_implemented``
    Nothing answers it. Named rather than omitted.
``external``
    It belongs to the deployment or the host platform, not to this codebase
    (TLS termination, SSO infrastructure, availability targets). Recording it as
    ``implemented`` would be claiming someone else's work.

No status is assigned from the PRD text. Where this file says ``implemented`` it
is because a pointer below resolves and a test exercises it; where it cannot be
established it says ``partial`` or ``not_implemented``, which is the honest
answer and the one a buyer can act on.
"""

from __future__ import annotations

import pathlib
import re

from pydantic import BaseModel, Field

PRD_PATH = pathlib.Path(__file__).resolve().parents[2] / "docs" / "prd-trd.md"

COVERAGE_STATUSES = ("implemented", "partial", "not_implemented", "external")


class PrdRequirement(BaseModel):
    """One row of a PRD requirement table, exactly as the document states it."""

    id: str
    text: str
    priority: str
    acceptance: str
    source_line: int


class RequirementCoverage(BaseModel):
    """What this repository offers for one requirement."""

    status: str = Field(pattern="^(implemented|partial|not_implemented|external)$")
    evidence: list[str] = []
    note: str = ""


class RequirementCoverageEntry(BaseModel):
    """A requirement joined with its coverage, as published."""

    id: str
    text: str
    priority: str
    acceptance: str
    status: str
    evidence: list[str]
    note: str


class RequirementCoverageManifest(BaseModel):
    """The whole matrix, plus the counts a reader would otherwise have to tally."""

    requirement_count: int
    entries: list[RequirementCoverageEntry]
    status_counts: dict[str, int]
    p0_status_counts: dict[str, int]
    unmapped_requirement_ids: list[str]


_FUNCTIONAL_ROW = re.compile(
    r"^\|\s*([A-Z]{3,4}-\d{3})\s*\|(.+?)\|\s*(P\d)\s*\|(.*?)\|\s*$"
)
_NFR_ROW = re.compile(r"^\|\s*(NFR-[A-Z]{3,4}-\d{3})\s*\|(.+?)\|(.*?)\|\s*$")


def parse_prd_requirements() -> list[PrdRequirement]:
    """Read every requirement row out of the PRD.

    Two table shapes: the functional tables carry a priority column, the NFR
    tables carry a target instead. Both are parsed so the inventory is the
    document's own, never a copy of it.
    """
    requirements: list[PrdRequirement] = []
    for number, line in enumerate(PRD_PATH.read_text(encoding="utf-8").splitlines(), 1):
        functional = _FUNCTIONAL_ROW.match(line)
        if functional:
            requirements.append(
                PrdRequirement(
                    id=functional.group(1),
                    text=functional.group(2).strip(),
                    priority=functional.group(3),
                    acceptance=functional.group(4).strip(),
                    source_line=number,
                )
            )
            continue
        nfr = _NFR_ROW.match(line)
        if nfr and "---" not in line:
            requirements.append(
                PrdRequirement(
                    id=nfr.group(1),
                    text=nfr.group(2).strip(),
                    priority="NFR",
                    acceptance=nfr.group(3).strip(),
                    source_line=number,
                )
            )
    return requirements


# One entry per requirement the PRD states. Evidence pointers take three forms,
# each resolved mechanically by the test:
#
#   "route:GET /catalog/search"              a route this app serves
#   "func:sdp.catalog.search_catalog"       an importable attribute
#   "test:tests/test_api.py::test_health"    a test that exists
#
# A pointer that no longer resolves fails the suite, so this matrix cannot rot
# into the shape the document it replaces was in.
REQUIREMENT_COVERAGE: dict[str, RequirementCoverage] = {
    # --- Catalog ----------------------------------------------------------- #
    "CAT-001": RequirementCoverage(
        status="partial",
        evidence=[
            "route:GET /catalog/search",
            "route:GET /catalog/facets",
            "func:sdp.catalog.search_catalog",
            "test:tests/test_api.py::test_catalog_search_and_detail",
            "test:tests/test_api.py::test_catalog_search_filter_by_quality",
        ],
        note=(
            "Every search dimension the requirement names is filterable. The "
            "acceptance criterion is a different matter. Its facet half does "
            "not hold: the search response is {query, count, items} and carries "
            "no facet counts, which come from a separate route "
            "(GET /catalog/facets). Its latency half - the same 2-second p95 "
            "NFR-PERF-001 declares - is now measured, under the same one-sided "
            "limitation recorded there: GET /enterprise/latency-budgets reports "
            "a measured p95 for this surface and refutes the budget when it is "
            "exceeded in-process, but an under-budget result does not establish "
            "the deployed p95. The one latency figure this repository records "
            "is what such a refutation looks like: src/sdp/catalog.py:468 "
            "measures 5.10s for a 2000-token query over 1005 datasets, which is "
            "why the query length is bounded rather than optimised."
        ),
    ),
    "CAT-002": RequirementCoverage(
        status="partial",
        evidence=[
            "route:GET /catalog/datasets/{dataset_id}",
            "test:tests/test_api.py::test_catalog_dataset_detail_exposes_recommendation_score",
        ],
        note=(
            "Ten of the eleven enumerated fields are published by GET "
            "/catalog/datasets/{dataset_id} (freshness and quality as "
            "freshness_score/quality_score), and the \"metadata incomplete\" badge "
            "is served as completeness_badge (good/partial/invalid), graded no "
            "higher than validate_metadata. The eleventh, source_system, is not "
            "displayed: discovery_view drops it as a governed field "
            "(src/sdp/catalog.py:49, 287) and the detail payload's pinned key set "
            "excludes it (tests/test_api.py:2152). Where it does surface it is "
            "not the detail page and not the full value: GET "
            "/enterprise/connectors/{id}/probe returns a credential-redacted "
            "locator, and GET /enterprise/demo-plan returns the seed value for "
            "the five fixture datasets only."
        ),
    ),
    "CAT-003": RequirementCoverage(
        status="partial",
        evidence=[
            "route:GET /catalog/datasets/{dataset_id}/jsonld",
            "test:tests/test_jsonld_export.py::test_a_distribution_is_a_real_dcat_node_with_an_access_url",
        ],
        note=(
            "Dataset and Distribution are expressed as DCAT nodes. DataService is "
            "not modelled - no route or contract emits dcat:DataService."
        ),
    ),
    "CAT-004": RequirementCoverage(
        status="partial",
        evidence=[
            "route:GET /ontology/concept/{concept}",
            "func:sdp.ontology.concept_assets",
            "test:tests/test_semantic_validation.py::test_the_cardinality_rule_is_declared_as_one",
            "test:tests/test_ontology_coverage_measurement.py::test_coverage_is_measured_against_the_glossary",
        ],
        note=(
            "Datasets carry business-concept mappings and GET "
            "/ontology/concept/{concept} resolves the datasets per concept "
            "(tenant-scoped). The proposed/approved distinction is real and "
            "enforced: BusinessMappingShape requires at least one approved "
            "mapping on GET /catalog/datasets/{dataset_id}/semantic-validation "
            "(src/sdp/semantic_validation.py:145, "
            "tests/test_semantic_validation.py::test_the_cardinality_rule_is_declared_as_one) "
            "and ontology_mapping_coverage counts approved mappings only "
            "(src/sdp/enterprise_evidence.py:96). The three-state status is not a "
            "lifecycle, however: status is an unvalidated free string (a PATCH "
            "with status \"totally-made-up\" returns 200 and persists), "
            "\"deprecated\" is a declared constant nothing sets or reads - a "
            "mapping written \"deprecated\" is treated identically to an arbitrary "
            "string - and no route transitions a mapping's status, which can only "
            "be rewritten wholesale by POST/PATCH. The status is visible on GET "
            "/catalog/datasets/{dataset_id} and .../jsonld, not on the concept "
            "route."
        ),
    ),
    "CAT-005": RequirementCoverage(
        status="partial",
        evidence=[
            "route:GET /catalog/datasets/{dataset_id}/audit",
            "func:sdp.catalog.ingest_event",
            "func:sdp.catalog.change_reason_details",
            "test:tests/test_catalog.py::test_patch_audit_still_names_which_withheld_field_changed",
            "test:tests/test_catalog_mutation_atomicity.py::test_the_ledger_never_certifies_a_change_that_is_not_stored",
            "test:tests/test_refused_mutation_evidence.py::test_a_refused_catalog_mutation_records_both_halves",
            "test:tests/test_change_reason_evidence.py::test_every_catalog_write_records_a_supplied_reason",
        ],
        note=(
            "Three of the acceptance criterion's four items are met on all four "
            "write paths: actor, timestamp and - now - the change reason, which "
            "`details.change_reason` carries from the request payload on "
            "register, patch, publish and deprecate alike. Before this, the "
            "row's `reason` field was the constant \"ok\" (that is the row's "
            "outcome, not the caller's reason) and only deprecate accepted one, "
            "under its own `details.reason` key; a reason sent to POST "
            "/catalog/datasets or PATCH /catalog/datasets/{id} answered 200 and "
            "was dropped, because the request models declare no such field. "
            "Deprecate also used to default an absent reason to the literal "
            "string \"deprecated\", recording a reason the caller never gave; "
            "all four now report `None`. The row is also guaranteed to describe "
            "the store - concurrent patches used to record result=success for a "
            "change that was not applied - and a refused write is recorded too. "
            "What remains partial is the diff: `details.before`/`after` carry "
            "only the fields the request named, so a field changed by a "
            "different concurrent writer does not appear, a register row has no "
            "prior state to diff against, and governed values (the source DSN, "
            "per-column PII flags) are projected rather than recorded verbatim."
        ),
    ),
    "CAT-006": RequirementCoverage(
        status="implemented",
        evidence=[
            "func:sdp_core.contracts.REQUIRED_METADATA_FIELDS",
            "test:tests/test_catalog_field_forwarding.py::test_the_metadata_completeness_target_is_compared",
        ],
    ),
    "CAT-007": RequirementCoverage(
        status="implemented",
        evidence=[
            "route:GET /catalog/datasets/{dataset_id}/jsonld",
            "test:tests/test_jsonld_export.py::test_every_published_term_is_mapped_by_the_context",
        ],
    ),
    "CAT-008": RequirementCoverage(
        status="implemented",
        evidence=[
            "route:GET /catalog/datasets/{dataset_id}/schema-versions",
            "route:GET /catalog/datasets/{dataset_id}/schema-diff",
            "test:tests/test_api.py::test_catalog_schema_history_and_diff",
            "test:tests/test_mutation_idempotency.py::test_every_listed_schema_version_is_addressable_by_the_diff",
            "test:tests/test_mutation_idempotency.py::test_a_real_schema_change_adds_a_new_listed_version",
        ],
        note=(
            "`version` and `schema_version` advance independently and a drift "
            "produces a diff against the previous schema version. The version "
            "listing used to repeat a version once per non-schema mutation - a "
            "state snapshot is recorded on every mutation, because it captures "
            "lineage, mappings, tags, status and scores too - so it advertised "
            "four `1.0.0` where the diff could resolve only one. Every listed "
            "version is now addressable."
        ),
    ),
    "CAT-009": RequirementCoverage(
        status="partial",
        evidence=[
            "route:GET /catalog/datasets/{dataset_id}/join-candidates",
            "route:GET /catalog/datasets/{dataset_id}/related",
            "test:tests/test_api.py::test_join_candidate_endpoint",
            "test:tests/test_catalog.py::test_join_candidates_skips_zero_overlap",
        ],
        note=(
            "Join candidates are derived and tenant-scoped: get_join_candidates "
            "scores shared Dataset.terms (weight 2) above shared column names "
            "(weight 1) and returns the overlap as its evidence. Three gaps "
            "against the acceptance criterion. (1) There is no business key to "
            "match on - ColumnMetadata declares no primary, foreign or join key, "
            "and none exists anywhere in the codebase - so bare column-name "
            "equality stands in for it, and two datasets sharing only generic "
            "names such as id/amount are recommended to each other. (2) The term "
            "signal is the free-text Dataset.terms tag list, which is never "
            "validated against the ontology; the approved BusinessMapping "
            "concepts - the repo's own concept-mapping construct - are not read "
            "at all, so two datasets sharing only an approved concept yield no "
            "candidates. (3) GET /catalog/datasets/{dataset_id}/related returns "
            "the operator-supplied related_datasets field verbatim (de-duplicated "
            "through a set, so unordered, and ids that resolve to nothing pass "
            "through), not a derived recommendation."
        ),
    ),
    # --- Ontology ---------------------------------------------------------- #
    "ONT-001": RequirementCoverage(
        status="implemented",
        evidence=[
            "route:GET /ontology/search",
            "route:POST /ontology/resolve",
            "test:tests/test_api.py::test_ontology_resolve",
        ],
    ),
    "ONT-002": RequirementCoverage(
        status="partial",
        evidence=[
            "func:sdp.graph_store.GraphNode",
            "func:sdp.graph_store.GraphStore.assert_node_kind_is_stable",
            "func:sdp.graph_store.GraphStore.assert_hierarchy_respects_class_separation",
            "func:sdp.semantic_validation.hierarchy_class_separation",
            "func:sdp.ontology.hierarchy_class_separation_report",
            "route:POST /graph/edges",
            "route:GET /enterprise/shacl-validation",
            "test:tests/test_graph_engine.py::test_semantic_search_kind_filter_only_returns_datasets",
            "test:tests/test_graph_node_kind_stability.py::test_a_concept_named_after_an_existing_dataset_is_refused",
            "test:tests/test_graph_node_kind_stability.py::test_a_column_node_cannot_be_reclassified_either",
            "test:tests/test_graph_hierarchy_class_separation.py::test_a_hierarchy_edge_across_the_class_boundary_is_refused",
            "test:tests/test_graph_hierarchy_class_separation.py::test_the_rule_refuses_nothing_legitimate",
            "test:tests/test_graph_hierarchy_class_separation.py::test_a_concept_cannot_declare_a_data_asset_as_its_parent_or_child",
            "test:tests/test_graph_hierarchy_class_separation.py::test_the_refused_publication_leaves_neither_store_written",
            "test:tests/test_graph_hierarchy_class_separation.py::test_the_shipped_graph_conforms_and_its_warnings_are_counted_separately",
            "test:tests/test_graph_hierarchy_class_separation.py::test_the_report_catches_the_ordering_the_gate_cannot",
        ],
        note=(
            "Concept, dataset and column are distinct node kinds "
            "(graph_store.py:304-343) and a dataset relates to a concept through "
            "a `mapping` edge rather than subclassing, so the separation is "
            "modelled. Nothing verifies it: semantic_validation.py publishes only "
            "property-presence/cardinality shapes and reports "
            "shacl_engine_executed = false, and no shape, axiom or reasoner "
            "expresses a class hierarchy anywhere in the repo — the SHACL/OWL "
            "check the acceptance criterion names is absent. "
            "One half of the separation is now enforced, and it was the half "
            "that was destroying data. A node's **kind is immutable**: "
            "`GraphStore.assert_node_kind_is_stable` refuses a write that would "
            "reclassify an existing id, and `ontology.validate_concept_registration` "
            "asks it before either store is written - so all three publication "
            "paths answer 409 where they answered 200: "
            "`POST /ontology/concepts`, `POST /graph/nodes {kind: concept}` and "
            "`POST /ontology/patches/{id}/review` on an approval. The approval "
            "path is why the check cannot live in the store alone: it writes "
            "only the vocabulary, so a store-side guard missed it entirely and "
            "approving a patch named `crm-customer-master` answered 200 and put "
            "a dataset id into the vocabulary and the open SKOS export "
            "(measured). `ConceptKindConflict` is a `ValueError` subclass, so "
            "every existing handler still catches it while the routes that want "
            "the precise status answer 409 rather than 400. This note previously recorded that 200 as a modelling "
            "violation; measured, it was worse — `upsert_node` built a fresh node "
            "and stored it over the old one, so the seeded dataset node became "
            "kind=concept with label crm-customer-master and its governed "
            "properties (owner, steward, sensitivity: medium, status: published, "
            "domain, tags, terms) were **destroyed** by one authorized ontology "
            "write. The tenant half of that boundary had already been closed "
            "(`_authorize_graph_write` resolves the target tenant); this was the "
            "kind half. The rule is deliberately not a kind allow-list — `kind` "
            "stays free-form, so a new kind is still introducible and the "
            "injection-regression tests that pass a hostile string as a kind "
            "still hold — what is refused is reclassifying an id that already "
            "exists as something else. "
            "The edge half is now closed too, in both of the halves the "
            "acceptance criterion names. **Refused**: `broader` and `narrower` "
            "are the only relations in this graph that assert one thing is a "
            "*kind of* another, and an endpoint that is a known data asset is "
            "refused with 409 on both publication paths - `POST /graph/edges` "
            "through `GraphStore.assert_hierarchy_respects_class_separation`, "
            "and `POST /ontology/concepts` through the pre-write validator, "
            "where it has to be: with the store's gate alone the same request "
            "answered 500 with the vocabulary record published and the graph "
            "node served, because the route's mirror write is inside neither "
            "try block. Measured before the gate, each one authorized request "
            "on the shipped seed: `broader` dataset->concept 200, "
            "`broader` concept->dataset 200, `narrower` dataset->concept 200, "
            "`POST /ontology/concepts {broader: crm-customer-master}` 200, and "
            "the same with a *column* id as `narrower` 200. `related` and "
            "`mapping` stay open by design - `related` is associative in SKOS "
            "rather than subsumption, and `mapping` is how a dataset and a "
            "concept are modelled as linked - so the rule refuses exactly the "
            "subsumption claim and nothing a caller needs. **Verified**: "
            "`ConceptHierarchyShape` is the first shape in this repository that "
            "expresses a class hierarchy; it is a sh:class-shaped constraint on "
            "both endpoints of a subsumption relation, published in the shape "
            "catalog and evaluated over the graph the product actually holds on "
            "`/enterprise/shacl-validation`. Both halves exist because neither "
            "suffices: the gate can only read the kinds known at write time, "
            "and an edge whose endpoints are both unknown must be permitted - "
            "the shipped seed declares `narrower: 매출 -> 매출 성장` for a "
            "concept the vocabulary never defines, and `upsert_concept` writes "
            "a concept's hierarchy edges before its targets are registered, so "
            "treating an unknown endpoint as a violation makes `seed_store` on "
            "a fresh store raise outright (reverse-verified; 27 of the seed's "
            "78 edges name a node that does not exist, 2 of them hierarchy "
            "edges). So an edge written to an unknown target whose target is "
            "*then* created as a dataset passes the gate twice, and the report "
            "is what catches it: measured, `conforms` false and "
            "`hierarchy_pass_rate` 0.875. The shipped graph conforms - all 7 "
            "hierarchy edges touching the vocabulary run concept -> concept, "
            "and the 2 that name a missing target are counted separately as "
            "`unknown_endpoint_count`, which is why this constraint can be a "
            "violation where ConceptShape's resolvable-target constraint has to "
            "stay a warning. Still absent, and declared rather than implied: no "
            "SHACL processor and no reasoner runs "
            "(`shacl_engine_executed = false`, `validation_engine = "
            "builtin_shape_checks`), `kind` remains a free-form string, and the "
            "report's `conformance_scope` names its own blind spot - a "
            "kind=\"concept\" node written straight through POST /graph/nodes "
            "is not in the vocabulary, so a hierarchy edge between it and a "
            "node that later becomes a dataset is counted by nothing "
            "(measured)."
        ),
    ),
    "ONT-003": RequirementCoverage(
        status="partial",
        evidence=[
            "route:GET /ontology/term/{term}/graph",
            "route:POST /graph/query",
            "test:tests/test_graph_engine.py::test_graph_query_traverses_concept_hierarchy",
            "test:tests/test_api.py::test_ontology_concept_graph",
            "test:tests/test_graph_hierarchy_consistency.py::test_the_edge_that_closes_a_two_concept_cycle_is_refused",
            "test:tests/test_graph_hierarchy_consistency.py::test_the_two_spellings_of_one_assertion_are_one_pair",
        ],
        note=(
            "broader/narrower/related are carried per concept, are readable "
            "(GET /ontology/term/{term}/graph returns all three), traversable "
            "(POST /graph/query, with an edge_types filter), and — since "
            "ONT-004 — serialized as real SKOS: GET /ontology/vocabulary/jsonld "
            "emits skos:broader/narrower/related between skos:Concept nodes in "
            "one skos:ConceptScheme (this note previously said no skos: "
            "vocabulary or RDF/SKOS serialization was emitted anywhere, which "
            "that route falsified). What is still missing is in the **graph** "
            "path, not the serialization: measured, 10 of the 19 "
            "broader/narrower/related edges in the seed name a target the "
            "vocabulary never defines, over 9 distinct names, and graph "
            "traversal materializes them as kind=\"unknown\" placeholders with "
            "no definition — including 휴면 고객, which duplicates the existing "
            "concept 이탈 고객 because **edge targets are not resolved through "
            "the alias index**. The export does resolve them (휴면 고객 → "
            "이탈 고객) and declares the 10 undefined edges rather than minting "
            "an IRI for a concept that does not exist, so the defect is now "
            "visible to a reader; it is not fixed in the graph. the currently "
            "cited test_the_shared_vocabulary_itself_stays_open asserts only "
            "definition/aliases/canonical and proves nothing about the hierarchy. "
            "A second defect in the same read path is now closed: the hierarchy "
            "could be made **cyclic**, so \"broader/narrower 관계 조회\" answered "
            "200 with a hierarchy that has no top. Measured: `broader 고객 -> "
            "주문` then `broader 주문 -> 고객`, both 200, after which "
            "`GET /ontology/term/고객/graph`, `GET /ontology/concept/고객`, "
            "`GET /ontology/search` and `POST /graph/query` all still answered "
            "200 - traversal is depth-bounded, so nothing crashed and the "
            "glossary was simply wrong. The closing edge is now refused with 409 "
            "on both publication paths and the cycle count is published; see "
            "ONT-007 for the gate, the report, and what remains absent."
        ),
    ),
    "ONT-004": RequirementCoverage(
        status="partial",
        evidence=[
            "route:GET /ontology/version",
            "route:GET /ontology/change-log",
            "route:GET /ontology/vocabulary/jsonld",
            "func:sdp.ontology_version.record_vocabulary_change",
            "test:tests/test_ontology_version_identity.py::test_publishing_a_concept_advances_the_revision_and_logs_it",
            "test:tests/test_ontology_version_identity.py::test_an_approved_patch_records_both_the_proposer_and_the_reviewer",
            "test:tests/test_ontology_version_identity.py::test_an_eviction_is_recorded_as_its_own_revision",
            "test:tests/test_ontology_vocabulary_export.py::test_the_scheme_carries_the_version_it_serialized",
        ],
        note=(
            "All three acceptance items are implemented and tested. **version**: "
            "a monotonic `ontology_revision` from a recorded baseline plus a "
            "sha256 `content_digest` recomputed from live content, published on "
            "GET /ontology/version. **change log**: a bounded, newest-first log "
            "with one entry per effective change — a no-op re-publication "
            "records nothing, and an eviction at the vocabulary cap is its own "
            "revision, which is the first time that silent deletion left any "
            "trace. **reviewer 기록**: an approved patch records the proposer "
            "(`actor_role: proposer`) and the approving reviewer; a direct "
            "upsert records `reviewer_id: null` with `review_basis: "
            "direct_admin_upsert`, and the recorder refuses a reviewer on any "
            "source that carries no review. The artifact the revision names is "
            "a SKOS/RDFS JSON-LD serialization of the vocabulary carrying "
            "`owl:versionInfo`. "
            "Not implemented, which is why this is partial rather than "
            "implemented: (1) the requirement says **OWL**/RDFS and there is no "
            "OWL axiom anywhere — no owl:Class, no rdfs:subClassOf, no "
            "restriction — and no reasoner validates the release (ONT-007 is "
            "not_implemented, so NFR-QUAL-002 stays unmet); (2) the version is "
            "not durable. The revision, the change log and every reviewer "
            "record live in process memory and reset on restart, while "
            "`sdp.evidence` already selects a Postgres or SQLite store for the "
            "policy/audit ledgers — the asymmetry is declared "
            "(`revision_is_durable: false`, `revision_scope: "
            "process_lifetime`) but a declared limitation is what makes this "
            "partial, not what closes it; (3) the version covers the concept "
            "vocabulary and its alias index only — `ontology._INDEX`, the "
            "concept-to-dataset map, is built once at import and no "
            "registration updates it, so dataset mapping is outside the "
            "versioned scope and the export says so "
            "(`sdp:datasetMappingIsVersioned false`). "
            "One published claim this closed: the `rdf_connector` control "
            "`ontology_version_pin` reported `status: implemented` / "
            "`verification: proof_route_served` with proof endpoints "
            "/ontology/search and /ontology/resolve while neither response "
            "contained the string \"version\" anywhere — two published claims "
            "about one capability contradicting each other. Both routes now "
            "stamp the version they answered from and accept a digest pin "
            "(409 on a mismatch, 400 on a malformed digest), and the control is "
            "graded `runtime_probe_verified` by exercising the pin predicate in "
            "both directions."
        ),
    ),
    "ONT-005": RequirementCoverage(
        status="partial",
        evidence=[
            "route:POST /ontology/patches",
            "route:POST /ontology/patches/{patch_id}/review",
            "route:GET /ontology/patches",
            "func:sdp.semantic_validation.validate_concept_semantics",
            "test:tests/test_ontology_publication_loop.py::test_approving_a_patch_publishes_the_term_to_every_read_surface",
            "test:tests/test_concept_shape_gate.py::test_a_concept_with_no_definition_is_refused_at_both_publication_paths",
            "test:tests/test_concept_shape_gate.py::test_the_approval_gate_is_still_a_backstop_behind_intake",
            "test:tests/test_semantic_validation.py::test_every_published_required_property_is_evaluated",
            "test:tests/test_steward_queue_identity_scope.py::test_no_open_surface_names_a_proposal_actor",
            "test:tests/test_steward_queue_identity_scope.py::test_the_queue_and_the_change_log_agree_on_who_may_read_identity",
        ],
        note=(
            "The requirement half is implemented and tested: a patch is stored "
            "`proposed`, and a proposal alone publishes nothing "
            "(test_approving_a_patch_publishes_the_term_to_every_read_surface "
            "asserts the term is absent from every read surface before the "
            "approval, and test_rejecting_a_patch_publishes_nothing covers the "
            "other decision). Two of the "
            "acceptance criterion's three gate items are now met and one is not. "
            "**reviewer 승인**: the sole gate before, and still required. "
            "**SHACL**: a ConceptShape is published and evaluated on the shared "
            "pre-write validator, so both publication paths — the direct upsert "
            "and an approval — are gated by one check a third caller cannot "
            "bypass. This note previously said no concept shape existed and "
            "nothing ran on the review path; both were true and both are now "
            "false. The gate closed a measured defect: "
            "`POST /ontology/concepts {\"actor\": \"admin\", \"concept\": "
            "\"정의누락개념\"}` answered 200 and published a concept with "
            "`definition: ''` into the glossary every read surface consults, "
            "and /ontology/search and /ontology/concept then served it. The "
            "shape's strength is bounded and published as such: the engine is "
            "`builtin_shape_checks` and `shacl_engine_executed` stays false — "
            "the shapes are SHACL-expressible and enforced by equivalent "
            "in-process checks, which is the strongest honest claim without an "
            "RDF stack (pyshacl and rdflib are not dependencies and CI installs "
            "from hash-pinned requirements). `definition` is the only property "
            "that can honestly be required — a top concept has no `broader` and "
            "a leaf no `narrower` — and the `sh:class`-shaped constraint that a "
            "hierarchy target must itself be a Concept is declared at **warning** "
            "severity, because the shipped vocabulary violates it 10 times over "
            "9 distinct undefined names: raised to a violation it makes all five "
            "seeded concepts non-conforming (measured), and a constraint that "
            "refuses the product's own seed cannot gate publication. "
            "**reasoner**: still absent (ONT-007 is not_implemented), nothing "
            "checks consistency, and the export carries no OWL axiom for a "
            "reasoner to act on — so this stays partial and NFR-QUAL-002 stays "
            "unmet. "
            "The disclosure this note recorded as deliberately deferred is "
            "closed. It read: GET /ontology/patches runs no authorization at all "
            "and serves requestor, reviewed_by, reviewed_at and review_comment "
            "in the clear to an anonymous caller — measured, at the same "
            "moment /ontology/change-log, /audit/events and /policy/decisions "
            "all answered 403 for the same identities. The queue read now runs "
            "`_authorize_evidence_read`, the same helper and the same reasoning "
            "as the change log (the vocabulary is shared, so no tenant "
            "predicate applies and the scope that does is authorization), and "
            "authorization precedes the status-filter validation so an "
            "unauthorized caller does not learn the payload rules. "
            "It was two surfaces, not one: enumerated across every GET route "
            "with the bodies walked for a mapping key rather than grepped for a "
            "field name, /enterprise/steward-review also republished "
            "`requestor`. Gating only the queue would have left the name "
            "reachable, so the summary withholds the field — withheld "
            "rather than gated, because it is a published open proof link "
            "pinned to resolve below 400, and the procurement question it "
            "answers does not need the proposer. The withholding is declared "
            "(`withheld_review_item_fields`), and the field is dropped for "
            "every caller including an authorized one: an actor-dependent "
            "field there would need a predicate that writes no decision row, "
            "and no GET in this product answers 200 while billing the ledger. "
            "That invariant is now pinned platform-wide rather than per route."
        ),
    ),
    "ONT-006": RequirementCoverage(
        status="partial",
        evidence=[
            "func:sdp.enterprise_evidence.ontology_mapping_coverage_detail",
            "test:tests/test_ontology_coverage_measurement.py::test_coverage_is_measured_against_the_glossary",
        ],
        note=(
            "Mappings are dataset-level, not column-level. BusinessMapping "
            "(contracts.py:31-36) carries "
            "concept/status/source/steward/approved_at, so source (:34) and "
            "approval state (:33, approved_at) are present but mapping type and "
            "confidence are absent — the only confidence field in the codebase is "
            "OntologyPatch.confidence (contracts.py:197), a concept-definition "
            "proposal, not a mapping. No term is bound to a physical column "
            "anywhere: ColumnMetadata has no term field (contracts.py:10-16) and "
            "the graph writes only dataset->concept \"mapping\" and dataset->column "
            "\"has_column\" edges (seed.py:120-133); the mapping edge's `origin` "
            "property (term vs business_mapping) is provenance, not a mapping "
            "type. The cited coverage function (enterprise_evidence.py:51) "
            "measures glossary-coverage arithmetic over concept and status only "
            "and does not establish the mapping record's fields."
        ),
    ),
    "ONT-007": RequirementCoverage(
        status="partial",
        evidence=[
            "func:sdp.graph_store.GraphStore.assert_hierarchy_stays_acyclic",
            "func:sdp.semantic_validation.hierarchy_consistency",
            "func:sdp.ontology.hierarchy_consistency_report",
            "route:GET /enterprise/shacl-validation",
            "test:tests/test_graph_hierarchy_consistency.py::test_the_edge_that_closes_a_two_concept_cycle_is_refused",
            "test:tests/test_graph_hierarchy_consistency.py::test_a_self_loop_is_the_same_rule",
            "test:tests/test_graph_hierarchy_consistency.py::test_a_concept_cannot_be_published_under_its_own_descendant",
            "test:tests/test_graph_hierarchy_consistency.py::test_a_cycle_the_gate_never_saw_is_reported_with_its_members",
            "test:tests/test_graph_hierarchy_consistency.py::test_the_report_is_honest_about_what_ran",
        ],
        note=(
            "One consistency condition is now checked, and the number a release "
            "gate would read is published - but **no reasoner is integrated**, "
            "and this note previously said no check ran at all. What runs is an "
            "acyclicity check over the subsumption relation `broader`/`narrower` "
            "assert: the edge that would close a cycle is refused with 409 on "
            "both publication paths (`POST /graph/edges` and "
            "`POST /ontology/concepts`), and "
            "`/enterprise/shacl-validation` publishes "
            "`hierarchy_consistency` with `cycle_count`, the cycles' members, "
            "`consistency_engine: builtin_graph_checks` and "
            "`reasoner_executed: false`. Measured before the gate, each one "
            "authorized request on the shipped seed: `broader 고객 -> 주문` 200 "
            "then `broader 주문 -> 고객` 200 (each term a kind of the other), a "
            "self-loop `broader 고객 -> 고객` 200, and the same cycle through "
            "`POST /ontology/concepts` 200/200. No read surface crashed on it - "
            "traversal is depth-bounded - so a glossary with no top answered 200 "
            "everywhere, which is ONT-003's read path as much as this "
            "requirement's. Direction is normalized once in "
            "`graph_store.subsumption_pair`, because `narrower: A -> B` and "
            "`broader: B -> A` are the same assertion and the seed states two of "
            "its five subsumptions from both ends; reading them as opposed would "
            "have made the seed itself cyclic. "
            "The criterion asks for `unsatisfiable class 0개` as a release gate, "
            "and the published number is deliberately **not** called that: a "
            "cycle makes concepts mutually subsuming, and unsatisfiability needs "
            "a disjointness axiom this repository does not have, so the number is "
            "`cycle_count` - what is computed. Still absent: any reasoner, any "
            "OWL axiom, SKOS S27 (`skos:related` disjoint from "
            "`skos:broaderTransitive`, measured clean on the seed but ungated), "
            "and any wiring of this number into a release gate - nothing blocks a "
            "release on it, because this repository has no release gate to wire "
            "it into. Acyclicity is a graph property rather than a shape, so it "
            "is deliberately outside `_SHACL_COMPATIBLE_SHAPES`: putting it there "
            "would make `shacl_compatible` cover a constraint that is not "
            "shape-shaped. The gate reads edges rather than node kinds, so no "
            "single write through `upsert_edge` closes a cycle unseen; what the "
            "report is for is edges the gate never saw - a hierarchy written "
            "before it existed, a bulk path that bypasses `upsert_edge`, and on "
            "the Postgres backend two concurrent writers each adding one edge, "
            "because there the reachability walk runs outside the write "
            "transaction."
        ),
    ),
    "ONT-008": RequirementCoverage(
        status="not_implemented",
        note="Competency questions are not registrable; no such contract exists.",
    ),
    # --- Browse / query ----------------------------------------------------- #
    "BRW-001": RequirementCoverage(
        status="partial",
        evidence=[
            "route:GET /browse/{dataset_id}/schema",
            "test:tests/test_api.py::test_browse_schema_requires_purpose",
        ],
        note=(
            "The policy-gated schema route publishes only name, datatype, "
            "nullable_ratio, distinct_ratio, quality_issues and pii per column. "
            "The ACCEPT's key (PK/FK) and column comment have no field on "
            "ColumnMetadata at all, and because the create/patch requests reuse "
            "that same model without accepting extra keys, a submitted key or "
            "comment is silently dropped rather than stored; nullable is "
            "published only as the profiling figure nullable_ratio, not a "
            "declared constraint. The cited test asserts only the 200 and the "
            "policy decision id, not the column field set."
        ),
    ),
    "BRW-002": RequirementCoverage(
        status="partial",
        evidence=[
            "route:POST /browse/{dataset_id}/preview",
            "test:tests/test_api.py::test_preview_pagination_and_decision_traceability",
        ],
        note=(
            "limit/offset are accepted and bounded at 100, not the PRD's 1,000, "
            "and the demo engine returns a fixed two-row sample, so pagination is "
            "a contract rather than a traversal of real rows."
        ),
    ),
    "BRW-003": RequirementCoverage(
        status="implemented",
        evidence=[
            "func:sdp.browse.preview",
            "test:tests/test_browse.py::test_preview_masks_every_declared_pii_column",
        ],
    ),
    "BRW-004": RequirementCoverage(
        status="partial",
        evidence=["route:GET /catalog/datasets/{dataset_id}/profile"],
        note=(
            "The policy-gated route publishes row_count, profile_updated_at, "
            "quality_issues and per-column "
            "null_ratio/distinct_ratio/quality_issues, each labelled by a "
            "metric_provenance block (computed_by_this_service=false, "
            "measurement_status=declared_by_source, declared metric_timestamp "
            "rather than read time): this service runs no profiler, so every "
            "figure is the source's or the registering caller's declaration, not "
            "a measurement taken here. Against the ACCEPT and the requirement "
            "text: no sample-vs-full indicator is published — computation_scope "
            "reports the scope as unknown to this service; min/max is absent from "
            "the payload entirely (DatasetProfile.minmax is declared in contracts "
            "but constructed nowhere); freshness exists only as the dataset-level "
            "profile_updated_at, not per column; and distinct is served as a "
            "ratio, with distinct_count listed in declared_unavailable_metrics "
            "rather than derived."
        ),
    ),
    "BRW-005": RequirementCoverage(
        status="implemented",
        evidence=[
            "func:sdp.orchestrator.validate_sql_query",
            "test:tests/test_orchestrator.py::test_the_allowlist_is_an_allowlist_not_a_denylist",
        ],
        note=(
            "SELECT-only, single statement, forbidden keywords, source-table "
            "allow-list and a function allow-list. No engine executes the "
            "statement, so this is a certification gate, not enforcement."
        ),
    ),
    "BRW-006": RequirementCoverage(
        status="partial",
        evidence=["func:sdp.orchestrator.execute_query"],
        note=(
            "Only the draft path (POST /llm/draft-query) applies a limit: "
            "draft_sql clamps row_limit to 2000 and emits it as a LIMIT clause in "
            "the generated SQL. The clamp is silent — a request for 5000 returns "
            "row_limit 2000 with no warning — and _audit_draft records no limit "
            "field, so the ACCEPT's \"abort safely and record an audit log on "
            "exceed\" is unmet. timeout_ms is only a request-contract range bound "
            "(ge=500, le=120000); draft_sql's own range check is unreachable over "
            "HTTP, and nothing enforces a timeout because nothing executes. The "
            "execution path carries no limit at all: QueryExecutionRequest and "
            "execute_query declare no row, timeout, memory or cost parameter, and "
            "the 2000 cap there bounds a mock row-count estimate rather than a "
            "result set. estimated_cost is computed and echoed but no threshold "
            "consumes it; memory limits are absent. The connector control "
            "matrix's claim that row_limit and timeout_ms are proven by "
            "/browse/query is wrong — that route has neither parameter."
        ),
    ),
    "BRW-007": RequirementCoverage(
        status="partial",
        evidence=[
            "func:sdp.browse.preview",
            "test:tests/test_payload_type_robustness.py::test_the_decision_and_audit_halves_stay_paired",
        ],
        note=(
            "Every preview, query, schema, profile and draft request writes an "
            "audit row carrying actor, dataset id and purpose, and a decision id "
            "wherever a policy decision was reached (pre-policy query rejections "
            "record `policy_stage: pre_policy_validation` with no decision id). "
            "The ACCEPT's columns field is not recorded on any path: `AuditEvent` "
            "has no columns field, preview logs only `masked_columns` — the "
            "masked subset, which is empty for a dataset with no PII column even "
            "though every column was returned — and the browse.query and draft "
            "rows log no column list at all, not even the caller's own requested "
            "columns."
        ),
    ),
    "BRW-008": RequirementCoverage(
        status="implemented",
        evidence=[
            "route:GET /browse/{dataset_id}/schema",
            "test:tests/test_browse.py::test_preview_rows_never_leave_the_named_dataset_schema",
        ],
    ),
    "BRW-009": RequirementCoverage(
        status="partial",
        evidence=[
            "route:GET /enterprise/connectors/{connector_id}/probe",
            "test:tests/test_connector_verdict_evidence.py::test_every_control_row_declares_how_strong_its_evidence_is",
        ],
        note=(
            "Four connector contracts (sql, rdf, file_lake, rest) with demo "
            "adapters that inspect fixture schemas. No connector reaches a real "
            "source system."
        ),
    ),
    "BRW-010": RequirementCoverage(
        status="partial",
        evidence=[
            "route:POST /graph/query",
            "route:GET /graph/nodes/{node_id}",
            "route:POST /search/semantic",
            "test:tests/test_graph_tenant_scope.py::test_graph_traversal_withholds_other_tenants_nodes",
            "test:tests/test_graph_store_concurrency.py::test_a_search_survives_nodes_arriving_mid_iteration",
        ],
        note=(
            "Traversal returns a bounded, tenant-scoped neighbourhood from one "
            "start node (nodes + edges, depth <= 6, direction and edge-type "
            "filters); covered by "
            "tests/test_graph_engine.py::test_graph_query_traverses_concept_hierarchy. "
            "The ACCEPT's path lookup is missing: the request carries no target "
            "node (an extra target_id is silently ignored) and neither backend "
            "implements a path or shortest-path query — the AGE backend binds a "
            "path variable and discards it, returning only the reached nodes. The "
            "traversed graph is also a mirror of the in-process catalog and "
            "ontology (src/sdp/seed.py), not an ingest from an external RDF "
            "store; the Apache AGE graph-DB backend exists but is exercised only "
            "by integration tests that skip without a live SDP_DATABASE_DSN, so "
            "the backend the normal suite covers is in_memory. Semantic search "
            "used to return 500 while datasets were being onboarded (a dict "
            "iterated while it grew); the store is now internally locked."
        ),
    ),
    # --- LLM ---------------------------------------------------------------- #
    "LLM-001": RequirementCoverage(
        status="partial",
        evidence=[
            "route:POST /llm/search",
            "test:tests/test_api.py::test_llm_search_uses_catalog_discovery_policy_scope",
        ],
        note=(
            "POST /llm/search returns the ontology term it used (mapped_term, "
            "src/sdp/api.py:1835) beside the tenant-scoped candidate datasets "
            "(recommendations.dataset_ids, :1840), so both halves of the "
            "acceptance criterion sit in one response. Three limits keep it short "
            "of the requirement. There is no conversion into a catalog search "
            "query: the route substring-matches the question against the dataset "
            "terms indexed in ontology._INDEX (src/sdp/ontology.py:56, :68) and "
            "never calls catalog.search_catalog, whose only caller is GET "
            "/catalog/search (src/sdp/api.py:552) — so a question naming no "
            "indexed term returns 200 with error \"No resolvable ontology term.\" "
            "and no candidates at all (src/sdp/api.py:1810-1816); measured, '주문 "
            "금액이 큰 데이터셋' yields zero candidates here and five ranked items from "
            "/catalog/search. Only the single top-scoring term is reported "
            "(:1817), and ties resolve by vocabulary order (stable sort at "
            "src/sdp/ontology.py:398 over the _INDEX insertion order): '활성 고객 "
            "데이터를 찾아줘' — the cited test's own question — scores 고객, 활성 고객, 이탈 and "
            "비즈니스 용어 all at 1.0 and reports 고객 with that broader concept's four "
            "datasets, so the term shown can be the parent of the one asked for, "
            "or a term the question never names (이탈 and 비즈니스 용어 score 1.0 only "
            "because a sibling dataset carries them). Coverage is one-sided: the "
            "tenant-scoped candidate list is covered by "
            "tests/test_llm_search_policy_enforcement.py, while mapped_term is "
            "asserted by no test in the suite — the full suite passes with that "
            "key renamed."
        ),
    ),
    "LLM-002": RequirementCoverage(
        status="partial",
        evidence=[
            "func:sdp.ontology.resolve_terms",
            "test:tests/test_api.py::test_ontology_resolve",
        ],
        note=(
            "Term resolution does run through the Ontology Service: "
            "sdp.ontology.resolve_terms is called by POST /llm/search "
            "(src/sdp/api.py:1809) and POST /ontology/resolve. The acceptance "
            "criterion is not met — no surface reports an unresolved term, and "
            "nothing is presented to the user as an assumption. /llm/search "
            "publishes only the single top-scoring resolution as mapped_term "
            "(src/sdp/api.py:1817, 1835) and drops the remaining resolved terms; "
            "/ontology/resolve returns the resolved list only, with no unresolved "
            "field; a question that resolves nothing returns a flat HTTP 200 "
            "error body rather than an assumption (src/sdp/api.py:1810-1816). The "
            "only assumptions list in the product (orchestrator.draft_sql) covers "
            "columns, date windows, PII and row filters and never consults the "
            "ontology. The cited test asserts only that some resolution came "
            "back."
        ),
    ),
    "LLM-003": RequirementCoverage(
        status="partial",
        evidence=[
            "func:sdp.orchestrator.draft_sql",
            "test:tests/test_orchestrator.py::test_a_rewritten_column_is_reported_rather_than_contradicted",
        ],
        note=(
            "Requested columns are checked against the dataset's declared columns "
            "and an unknown one is refused (invalid_columns, "
            "src/sdp/orchestrator.py:396-404); a rewrite colliding with another "
            "declared column is refused (ambiguous_identifier); and the table "
            "allowlist blocks any other table, including qualified names and "
            "extra comma-separated tables (src/sdp/orchestrator.py:293-302). Two "
            "gaps remain against the acceptance criterion. (1) A declared column "
            "that is not a bare SQL identifier is rewritten into the emitted "
            "statement rather than refused ('order amount' -> order_amount, "
            "src/sdp/orchestrator.py:504-506 and :513), so the draft names a "
            "column the catalog does not declare. The allowlist runs on the "
            "request before the rewrite and validate_sql_query applies no column "
            "allowlist, so nothing re-checks the emitted identifiers; "
            "/browse/query answers 200 SUCCEEDED on such a statement. The rewrite "
            "is reported in emitted_identifiers and an assumption, but the same "
            "assumptions list still asserts that only catalog-validated "
            "tables/columns were used. Pinned by "
            "tests/test_orchestrator.py:386-387. (2) There is no table entity or "
            "asset registry in this codebase — Dataset has no table field "
            "(src/sdp_core/contracts.py:65-94) — so the FROM name is derived from "
            "the dataset's source locator (src/sdp/orchestrator.py:183-184): FROM "
            "crm for s3://analytics/events/crm, FROM customer_intelligence for "
            "sparql://semantic.graph/customer-intelligence, FROM campaigns for "
            "https://api.example.internal/marketing/campaigns. The allowlist "
            "compares the draft against that same derivation, so it can prove "
            "only that no other table is named, not that the table exists."
        ),
    ),
    "LLM-004": RequirementCoverage(
        status="partial",
        evidence=[
            "func:sdp.orchestrator.draft_sql",
            "test:tests/test_orchestrator.py::test_every_seeded_dataset_drafts_a_statement_its_validator_accepts",
        ],
        note=(
            "SQL drafting is schema-grounded: requested columns and group_by are "
            "refused unless declared in the dataset schema, the date-window "
            "column must be a declared temporal column, the table name is derived "
            "from the catalog's source_system, and the draft is self-checked "
            "against validate_sql_query before it is returned. Not met: there is "
            "no SPARQL generation path. The drafter hard-codes dialect "
            "\"postgresql\" and emits relational SQL for the seeded sparql:// "
            "dataset, reducing the named graph to a table name (semantic-glossary "
            "-> \"... FROM customer_intelligence\") while the same response asserts "
            "that only catalog-validated tables/columns were used. Secondarily, "
            "the self-check validator enforces the table allow-list with no "
            "column check, so column grounding rests on the upstream request "
            "validation rather than being re-proved on the statement; "
            "/browse/query accepts an undeclared column on caller-supplied SQL."
        ),
    ),
    "LLM-005": RequirementCoverage(
        status="partial",
        evidence=["func:sdp.orchestrator.draft_sql"],
        note=(
            "assumptions, requested_columns, emitted_identifiers and the "
            "policy decision id are returned. There is no timestamp on the draft "
            "and no quality warning derived from the dataset's quality score."
        ),
    ),
    "LLM-006": RequirementCoverage(
        status="implemented",
        evidence=[
            "func:sdp.credentials.connector_secret_status",
            "test:tests/test_api.py::test_enterprise_rest_connector_probe_uses_vault_reference_without_secret_leak",
        ],
        note="No LLM runs in-process; connector secrets are referenced, never returned.",
    ),
    "LLM-007": RequirementCoverage(
        status="partial",
        evidence=[
            "func:sdp.orchestrator.draft_sql",
            "test:tests/test_orchestrator.py::test_validate_sql_query_flags_unsafe_input",
        ],
        note=(
            "No model is called anywhere in this service, so there is no "
            "prompt-injection defence in the sense the acceptance criterion "
            "names: document and metadata text (dataset/column descriptions, "
            "ontology definitions) is returned verbatim with no instruction/data "
            "separation, because nothing interprets it. What exists on the only "
            "natural-language input path is a forbidden-keyword screen on the "
            "question (src/sdp/orchestrator.py:384-394, covered by "
            "tests/test_orchestrator.py::test_draft_sql_rejects_forbidden_keyword_in_question), "
            "and the question's content never reaches the generated statement, "
            "which is built only from the dataset's source_system plus "
            "columns/group_by/row_limit/date_window_days and must pass "
            "validate_sql_query."
        ),
    ),
    "LLM-008": RequirementCoverage(
        status="implemented",
        evidence=[
            "route:POST /ontology/patches",
            "test:tests/test_api.py::test_ontology_patch_workflow",
        ],
    ),
    "LLM-009": RequirementCoverage(
        status="external",
        note=(
            "No conversation history is stored by this service - there is no "
            "chat transcript surface - so there is nothing here to redact. A host "
            "that adds one owns this requirement."
        ),
    ),
    # --- Policy ------------------------------------------------------------- #
    "POL-001": RequirementCoverage(
        status="implemented",
        evidence=[
            "func:sdp.policy.evaluate",
            "test:tests/test_policy.py::test_security_role_may_read_metadata_but_not_data",
        ],
    ),
    "POL-002": RequirementCoverage(
        status="partial",
        evidence=[
            "func:sdp.policy.evaluate",
            "test:tests/test_governance_boundary.py::test_a_foreign_tenant_admin_cannot_overwrite_a_node_it_cannot_read",
        ],
        note=(
            "Dataset level is genuine subject-dependent access control: tenant "
            "boundary, metadata-reader vs data-reader role, critical sensitivity "
            "(admin only) and external-export purpose each change the decision "
            "(policy.py:348-395). There is no per-table level, because a dataset "
            "is the table here. Column level is classification-driven redaction, "
            "not access control: the `masking` obligation is `[col.name for col "
            "in dataset.schema if col.pii]` (policy.py:408), so the masked set is "
            "identical for admin, data-admin, analyst and security; no role, "
            "purpose or configuration releases a PII value, and no per-role "
            "column grant exists. The ACCEPT's \"숨김 또는 마스킹\" is met for preview "
            "rows (`***`, "
            "tests/test_browse.py::test_preview_masks_every_declared_pii_column) "
            "and the ungated catalog detail withholds the column schema entirely; "
            "what is missing is any notion of a column a given subject is or is "
            "not authorized for. Also unredacted: `orchestrator.draft_sql` names "
            "a requested PII column in the drafted SELECT, carrying only an "
            "advisory assumption (orchestrator.py:569)."
        ),
    ),
    "POL-003": RequirementCoverage(
        status="implemented",
        evidence=[
            "func:sdp_core.contracts.column_masking_bases",
            "func:sdp_core.contracts.masked_column_rules",
            "func:sdp.browse.preview",
            "test:tests/test_classification_masking.py::test_every_declared_basis_masks",
            "test:tests/test_classification_masking.py::test_a_rule_carries_the_column_the_bases_and_the_action",
            "test:tests/test_classification_masking.py::test_a_classified_non_pii_column_is_actually_masked_in_a_preview",
        ],
        note=(
            "All three bases the requirement names now mask, and the decision "
            "carries the rule the acceptance criterion asks for: "
            "`obligations.masking_rules` gives each masked column its bases and "
            "its action, beside the `masking` name list that `apply_mask` and "
            "the published response read. Before this the policy consulted only "
            "the `pii` bool - a column classified sensitive or confidential was "
            "released, and there was nowhere on ColumnMetadata to classify one. "
            "An unrecognised label masks as well, reported as "
            "`unrecognized_classification`: masking is a withholding control, "
            "so releasing a column because its label was misspelled is the "
            "failure that matters. `pii: true` and `classification: [\"pii\"]` "
            "are one statement. `classification` is governed exactly like `pii` "
            "- withheld from the discovery surface, reported as drift in the "
            "schema diff without publishing the value. What this does not do is "
            "suppress rather than mask (the obligation's action is always "
            "`mask`), and nothing classifies a column automatically: the label "
            "is operator-supplied, like `pii`."
        ),
    ),
    "POL-004": RequirementCoverage(
        status="implemented",
        evidence=[
            "func:sdp.policy.evaluate",
            "test:tests/test_governance_boundary.py::test_no_purpose_spelling_bypasses_the_export_denial",
        ],
    ),
    "POL-005": RequirementCoverage(
        status="partial",
        evidence=[
            "route:GET /policy/decisions",
            "test:tests/test_governed_write_evidence.py::test_a_governed_write_records_a_decision_and_an_audit_event",
            "test:tests/test_evidence_log_snapshot_reads.py::test_a_decision_page_never_repeats_a_row_while_the_log_trims",
        ],
        note=(
            "Every `evaluate` branch records a row with a `decision_id`, but "
            "`PolicyDecision` carries no `purpose` and no timestamp and `GET "
            "/policy/decisions` returns it verbatim, so the deciding input is "
            "absent: two `preview` allows on `crm-event` differing only in "
            "purpose are identical in subject/resource/action/effect and reason, "
            "differing only by an unexplained `row_filter` obligation. "
            "Reproduction therefore requires a `decision_id` join to the audit "
            "event, which carries `details.purpose` and `created_at` on the "
            "browse/schema/query and catalog-mutation paths; `POST "
            "/policy/decision` and `POST /llm/search` evaluate a caller-supplied "
            "purpose and write no audit event, so those rows are not reproducible "
            "at all. The SQLite/Postgres stores keep a server-side "
            "`recorded_at`/`created_at` used only for ordering and never exposed "
            "by the API, and with no evidence store configured (the documented "
            "`uvicorn sdp.api:app` run) the decision log is a 2000-row window "
            "that drops older rows, so \"모든 policy decision\" does not hold there. "
            "A page used to be able to repeat a row and omit that many real ones "
            "while the bounded in-memory log trimmed behind the reader; pages are "
            "now built from a snapshot."
        ),
    ),
    "POL-006": RequirementCoverage(
        status="not_implemented",
        note=(
            "Usage conditions are not expressed in ODRL or any policy ontology; "
            "obligations are a fixed dict shape."
        ),
    ),
    # --- Lineage and quality ------------------------------------------------ #
    "LIN-001": RequirementCoverage(
        status="partial",
        evidence=[
            "route:GET /catalog/datasets/{dataset_id}/lineage",
            "route:POST /graph/query",
            "test:tests/test_graph_mirroring.py::test_a_lineage_edge_is_reconciled_against_both_of_its_declarers",
            "test:tests/test_graph_mirroring.py::test_mutating_a_dataset_keeps_edges_its_partners_declare",
        ],
        note=(
            "Dataset-level upstream/downstream lineage is exposed, but only as "
            "two flat lists of dataset ids (GET /catalog/datasets/{id}/lineage), "
            "mirrored into the graph as dataset->dataset `lineage` edges carrying "
            "a `kind=input|output` property. The ACCEPT column's "
            "source/job/target triple is not met: there is no "
            "job/process/activity entity in the model and no transformation "
            "metadata - consistent with ADM-002 (\"There is no ingestion job\") and "
            "LIN-005 (\"No PROV activity/entity/agent representation exists\"). "
            "Coverage boundary: the lineage lists are asserted to round-trip "
            "through create and patch (tests/test_catalog_field_forwarding.py), "
            "and the graph edges are asserted to reconcile against both declarers "
            "(tests/test_graph_mirroring.py::test_a_lineage_edge_is_reconciled_against_both_of_its_declarers), "
            "but no test asserts the /lineage route's own payload contents - the "
            "route test checks status 200 and dataset_id only. The previously "
            "cited test "
            "`test_every_mirrored_facet_is_reconciled_not_only_appended` is "
            "parametrized over terms/mappings/related_datasets only and covers no "
            "lineage facet; The graph mirror now agrees with the catalog under "
            "concurrent and sequential mutation alike; seeding or mutating one "
            "endpoint used to delete lineage edges the other endpoint declared."
        ),
    ),
    "LIN-002": RequirementCoverage(
        status="not_implemented",
        note="Column-level lineage is Phase 2 in the PRD and is not built.",
    ),
    "LIN-003": RequirementCoverage(
        status="partial",
        evidence=[
            "route:GET /catalog/datasets/{dataset_id}/profile",
            "func:sdp.profile_provenance.profile_metric_provenance",
            "test:tests/test_profile_metric_provenance.py::test_the_profile_declares_it_computed_nothing",
            "test:tests/test_profile_metric_provenance.py::test_distinct_count_is_declared_unavailable_rather_than_multiplied",
        ],
        note=(
            "The gated profile route publishes row_count, profile_updated_at and "
            "per-column null_ratio/distinct_ratio, plus a `metric_provenance` "
            "block (`computed_by_this_service: false`, `measurement_status: "
            "declared_by_source`, `computation_scope`, `metric_timestamp`) and a "
            "`declared_unavailable_metrics` list; "
            "`tests/test_profile_metric_provenance.py` pins all of it. Missing "
            "against the PRD's metric list: `duplicate_ratio` is absent entirely, "
            "and distinct *count* is deliberately not carried - only "
            "`distinct_ratio`, because deriving a count from `distinct_ratio * "
            "row_count` would manufacture a measurement neither declaration "
            "supports. Freshness is not a profile metric here: `freshness_score` "
            "is a separate dataset-level 0..1 score on the catalog summary and "
            "the browse schema quality block, and `DatasetProfile.freshness_ts` "
            "is declared in the contracts but never populated or surfaced. On the "
            "acceptance criterion, the metric-timestamp half is met by the "
            "source's declared `updated_at` (never fabricated from the read time, "
            "and reported absent when the declaration is missing or unusable); "
            "the computation-scope half is disclosed rather than satisfied - "
            "`computation_scope` reports "
            "`source_declared_scope_unknown_to_this_service`, so no window, "
            "sample size or partition is ever stated. No figure here is computed: "
            "this service runs no profiler, every seeded profile value is a "
            "static literal, and per-column `quality_issues` is empty for all "
            "five seeded datasets."
        ),
    ),
    "LIN-004": RequirementCoverage(
        status="implemented",
        evidence=[
            "route:GET /catalog/datasets/{dataset_id}",
            "route:GET /browse/{dataset_id}/schema",
            "func:sdp.quality_warnings.quality_warning_summary",
            "test:tests/test_quality_threshold_warnings.py::test_every_declared_rule_fires_on_a_violating_dataset",
            "test:tests/test_quality_threshold_warnings.py::test_every_warning_carries_rule_observed_value_and_threshold",
        ],
        note=(
            "Six rules over the dataset's declared scores, its required-metadata "
            "completeness and its per-column null/distinct ratios and declared "
            "issues. Each warning carries the rule, the observed value and the "
            "threshold, which is what the acceptance criterion names. Two "
            "boundaries are deliberate: a rule whose input cannot be compared "
            "reports `unevaluated` rather than passing, and column-scope "
            "warnings appear only behind the policy gate because they name a "
            "column and read statistics the discovery surface withholds - the "
            "open surface publishes `withheld_quality_warning_count` instead. "
            "The thresholds are product-wide defaults, not per-tenant or "
            "per-domain configuration; `threshold_source` says so on every "
            "warning."
        ),
    ),
    "LIN-005": RequirementCoverage(
        status="not_implemented",
        note="No PROV activity/entity/agent representation exists.",
    ),
    # --- Admin -------------------------------------------------------------- #
    "ADM-001": RequirementCoverage(
        status="not_implemented",
        note=(
            "Connectors are a fixed registry in code. There is no registration, "
            "edit or deactivation path, and the console is read-only."
        ),
    ),
    "ADM-002": RequirementCoverage(
        status="not_implemented",
        note="There is no ingestion job and therefore no manual run.",
    ),
    "ADM-003": RequirementCoverage(
        status="partial",
        evidence=[
            "route:GET /enterprise/shacl-validation",
            "test:tests/test_semantic_validation.py::test_every_published_required_property_is_evaluated",
        ],
        note=(
            "No SHACL processor runs: pyshacl and rdflib are not dependencies "
            "(`import pyshacl` raises ImportError), and both surfaces publish "
            "`validation_engine: builtin_shape_checks` with "
            "`shacl_engine_executed: false`. The acceptance criterion's fields "
            "are met and tested - every violation carries path, severity and "
            "message, and paths are index-qualified (`distributions[0].format`) "
            "so a report names which member failed. What runs is three "
            "hand-written checks over this repo's own 3-shape catalog: "
            "required-property presence (by truthiness), one `min_approved_count` "
            "cardinality rule and one recommended-terms warning. The PRD's "
            "section 15 shapes are not the ones evaluated: `sh:maxCount`, "
            "`sh:datatype`, `sh:minLength`, `sh:nodeKind` and `sh:in` are "
            "evaluated nowhere, and `NoDatasetAsBusinessClassShape` (15.2) and "
            "`SensitiveColumnPolicyShape` (15.3, an `sh:sparql` constraint) are "
            "absent from the catalog entirely. `shacl_compatible` asserts only "
            "that every published shape id is in the evaluated set; no shapes "
            "graph is emitted, so it is not evidence of a SHACL translation. This "
            "is an equivalent in-process check, not a SHACL conformance report."
        ),
    ),
    "ADM-004": RequirementCoverage(
        status="not_implemented",
        note="There is no feature-flag surface, per domain or per group.",
    ),
    "ADM-005": RequirementCoverage(
        status="partial",
        evidence=[
            "route:GET /audit/events",
            "test:tests/test_evidence_tenant_read_scope.py::test_audit_events_are_scoped_to_the_reader_tenant",
        ],
        note=(
            "Audit events are listable with an asset (`resource`) filter and are "
            "tenant-scoped; the `user` parameter is the reader's own identity for "
            "authorization, not an actor filter - a reader sees other actors' "
            "rows within scope. Of the four ACCEPT filters only asset exists: "
            "there is no actor, action or time-range filter at any layer, "
            "in-memory or store-backed, although AuditEvent carries actor and "
            "action and returns both. Unrecognized filter parameters such as "
            "`?actor=` or `?since=` are accepted with 200 and silently ignored, "
            "so an integrator gets unfiltered rows rather than an error. There is "
            "also no export format - the evidence pack publishes an audit event "
            "count only."
        ),
    ),
    # --- NFR: performance --------------------------------------------------- #
    # Each budget is declared in ``sdp.latency_budgets`` against the routes it
    # governs and compared to a measured p95, which is why these are no longer
    # ``not_implemented``. They are not ``implemented`` either: the measurement
    # is one-sided. An in-process p95 is a lower bound on the deployed p95, so
    # it can refute a budget and cannot confirm one - and the requirement is a
    # statement about the deployment.
    **{
        f"NFR-PERF-{index:03d}": RequirementCoverage(
            status="partial",
            evidence=[
                "route:GET /enterprise/latency-budgets",
                "func:sdp.latency_budgets.latency_budget_report",
                "test:tests/test_latency_budget_measurement.py::test_no_declared_budget_is_refuted_in_process",
                "test:tests/test_latency_budget_measurement.py::test_the_refutation_path_actually_fires",
            ],
            note=(
                "The budget is declared against the routes it governs and "
                "compared to a measured nearest-rank p95 over successful "
                "responses, with a minimum sample below which no verdict is "
                "produced in either direction. What it cannot establish is the "
                "requirement as stated: the observations come from one "
                "in-process worker over in-memory stores and seed data, so the "
                "measured p95 is a lower bound on a deployment's. The published "
                "field is therefore `budget_refuted`, not `within_budget` - an "
                "over-budget result is conclusive, an under-budget one is not. "
                "Confirming a deployed p95 needs a load test against a deployed "
                "instance, which is outside this repository."
            ),
        )
        for index in range(1, 7)
    },
    # --- NFR: security ------------------------------------------------------ #
    "NFR-SEC-001": RequirementCoverage(
        status="partial",
        evidence=[
            "route:POST /enterprise/auth/oidc-verify",
            "test:tests/test_api.py::test_oidc_jwks_verification_maps_verified_token_without_token_leak",
        ],
        note=(
            "OIDC token verification against operator-configured JWKS (signature, "
            "issuer, audience, required exp/iss/aud) is built and tested; SAML is "
            "not. Nothing consumes the verified identity: "
            "`verify_oidc_jwks_token` has one call site, `POST "
            "/enterprise/auth/oidc-verify`, which returns the actor context to "
            "the caller and binds it to no request. There is no session or login "
            "flow and no route requires a credential - every other route takes "
            "its subject from an unauthenticated `user` query parameter or "
            "`actor` body field, resolved against a seeded demo subject table. A "
            "verified OIDC subject resolves there to no tenant and no roles, so "
            "it cannot even be used as that input. SSO is therefore not enforced "
            "anywhere in this service."
        ),
    ),
    "NFR-SEC-002": RequirementCoverage(
        status="partial",
        evidence=[
            "func:sdp_core.rbac.enterprise_rbac_matrix",
            "func:sdp.policy.evaluate",
            "test:tests/test_published_claim_honesty.py::test_every_published_grant_is_one_the_engine_actually_allows",
        ],
        note=(
            "The decision engine is a genuine RBAC + ABAC hybrid - roles plus "
            "tenant, sensitivity and purpose attributes - and every published "
            "grant is enumerated against the engine itself. What is not built is "
            "the identity and role model behind it. Role and tenant assignment is "
            "a six-subject demo table in sdp.authz with no role store and no "
            "assignment route, and an unrecognized subject resolves to no roles. "
            "The subject is unauthenticated request input: no route requires a "
            "credential, so a caller may name any seeded subject, and the roles "
            "carried by a verified OIDC token are returned to the caller but "
            "never reach the engine. Two of the ten published actions "
            "(review_security_evidence, administer_tenants) are declared "
            "unenforced and are denied before any role is consulted. The seeded "
            "subject-to-role bundling is itself published at GET "
            "/enterprise/rbac-matrix. The enumeration skips the `admin` row, "
            "whose subject key is absent, though that row's grants are identical "
            "to the platform-admin row's and are exercised through a subject "
            "holding the admin role."
        ),
    ),
    "NFR-SEC-003": RequirementCoverage(
        status="partial",
        evidence=[
            "func:sdp.credentials.connector_secret_status",
            "test:tests/test_source_system_redaction.py::test_no_connection_string_form_survives_with_its_secret",
        ],
        note=(
            "Secrets are read as environment references, never stored or "
            "published, and credential-bearing locators are redacted on every "
            "surface. No Secret Manager or Vault integration exists; the "
            "reference resolver reads the process environment."
        ),
    ),
    "NFR-SEC-004": RequirementCoverage(
        status="partial",
        note=(
            "Inbound TLS termination belongs to the deployment edge, and none "
            "ships here: the image and every compose service serve plain HTTP "
            "(uvicorn on :8000, http healthchecks), and no reverse proxy or TLS "
            "terminator exists in this repository. The internal links this "
            "codebase does own are TLS-capable but not TLS-only: "
            "SDP_DATABASE_SSLMODE is forwarded to the driver and sslmode=require "
            "is test-covered, yet the shipped postgres profile sets it to "
            "disable; the JWKS fetch that anchors token verification and the log "
            "sink both accept a plain http URL, and their scheme allow-lists "
            "exist to block file://, not to require TLS. Nothing rejects an http "
            "target and no test asserts TLS, so \"all internal/external "
            "communication TLS\" is not met."
        ),
    ),
    "NFR-SEC-005": RequirementCoverage(
        status="implemented",
        evidence=[
            "func:sdp.catalog.ingest_event",
            "test:tests/test_governed_write_evidence.py::test_a_governed_write_records_a_decision_and_an_audit_event",
            "test:tests/test_catalog_mutation_atomicity.py::test_the_ledger_never_certifies_a_change_that_is_not_stored",
            "test:tests/test_refused_mutation_evidence.py::test_a_refused_catalog_mutation_records_both_halves",
            "test:tests/test_refused_mutation_evidence.py::test_every_catalog_mutation_route_is_covered_here",
        ],
        note=(
            "Every preview, query, policy evaluation and catalog change records "
            "a decision and an audit event, on refusal as well as on success. "
            "Two holes in that 100% were found and closed rather than assumed "
            "absent. Concurrent patches used to record result=success for a "
            "change that was not stored, so the ledger was complete and partly "
            "false. And a *refused* catalog mutation recorded the decision and "
            "no audit row at all - measured on all four verbs: 403, decisions "
            "+1, audits +0 - while the browse paths audited their denials; the "
            "pairing test's governed-write list covered only the three routes "
            "sharing the auditing gate, which is how four inline-authorizing "
            "routes stayed uncovered. The new coverage is derived from the "
            "route table. What this row does not claim is the *content* of a "
            "record: see CAT-005 for the reason field and the before/after diff."
        ),
    ),
    "NFR-SEC-006": RequirementCoverage(
        status="external",
        evidence=[
            "test:tests/test_source_system_redaction.py::test_no_connection_string_form_survives_with_its_secret",
        ],
        note=(
            "No LLM provider is integrated anywhere in this service, so no "
            "preview text is sent to one: the acceptance criterion holds by "
            "absence of that boundary, not by a control. Both /llm/* surfaces are "
            "deterministic - /llm/search resolves ontology terms and "
            "/llm/draft-query assembles template SQL - and there is no "
            "redaction-before-send path and no test asserting the absence of "
            "model egress. The preview masking in sdp.browse redacts the user "
            "response, not a provider payload, so it is not evidence here. A host "
            "that adds a provider owns this requirement."
        ),
    ),
    "NFR-SEC-007": RequirementCoverage(
        status="partial",
        evidence=[
            "func:sdp.orchestrator.validate_sql_query",
            "test:tests/test_orchestrator.py::test_a_function_outside_the_allowlist_is_refused",
        ],
        note=(
            "SELECT-only, single statement, forbidden keywords, a function "
            "allow-list and a source-table allow-list are enforced on every "
            "submitted statement, so read-only and allowlist are met. Timeout, "
            "row limit and cost limit are not: QueryExecutionRequest carries no "
            "timeout, row-limit or cost field, the gate does not require a LIMIT "
            "clause (`select customer_id from customer` is accepted and answered "
            "SUCCEEDED), and nothing executes, so a timeout has nothing to "
            "interrupt. row_limit and timeout_ms are validated on the draft route "
            "only — row_limit is emitted as a LIMIT clause in the drafted SQL, "
            "timeout_ms and estimated_cost are echoed, and no budget is compared "
            "against estimated_cost — while a caller may submit any SELECT "
            "straight to the execution gate. Same boundary as BRW-005 and "
            "BRW-006."
        ),
    ),
    # --- NFR: reliability --------------------------------------------------- #
    "NFR-REL-001": RequirementCoverage(
        status="external",
        note=(
            "Availability is a property of the deployment - replica count, "
            "restart policy, the load balancer in front - and this codebase "
            "cannot establish a monthly figure for it. What it ships is what a "
            "platform gates on: `GET /health`, and the `GET /healthz` readiness "
            "probe, which reports the active store's readiness and answers 503 "
            "when the backend is unreachable; the compose healthcheck polls it "
            "every 30s. Nothing here measures or publishes availability: "
            "`/metrics` exports seven gauges and no request-outcome counters, so "
            "no SLI can be computed from it; per-request status codes exist only "
            "in a bounded in-process ring buffer that is withheld from the "
            "published manifest and empties on restart; and there is no SLO or "
            "error-budget surface."
        ),
    ),
    "NFR-REL-002": RequirementCoverage(
        status="external",
        note=(
            "A monthly availability percentage is a property of the deployment, "
            "not of this codebase: nothing here measures or publishes "
            "availability. What this service provides is the probe a host needs — "
            "`GET /health` (a constant) and `GET /healthz`, which reports "
            "graph-backend readiness and answers 503 when the backend is "
            "unreachable. Same ownership as NFR-REL-001 and NFR-SEC-004. The "
            "target's `source dependency 제외` carve-out has no counterpart here, "
            "because no browse route reads a source system: preview rows are "
            "deterministic sample values projected onto the named dataset's "
            "declared schema (`sdp.browse._sample_rows`), the demo "
            "SQL/RDF/file-lake/REST connectors return hardcoded rows "
            "(`sdp.connectors`), and `/browse/query` reports `source: mock-trino` "
            "rather than executing against anything. So browse availability does "
            "not yet depend on a source at all, and the carve-out cannot be "
            "exercised."
        ),
    ),
    "NFR-REL-003": RequirementCoverage(
        status="not_implemented",
        note=(
            "No backup or restore path exists for the metadata graph: no "
            "daily-full / hourly-incremental schedule, no dump or restore "
            "tooling, no retention path and no restore test. Two distinct gaps "
            "sit behind that. In the default configuration (no database DSN) the "
            "graph is `InMemoryGraphStore` and the catalog's dataset records are "
            "a process-level dict re-seeded from demo data at startup and never "
            "hydrated back from any store, so a restart loses the metadata and "
            "there is no durable artifact to back up. With the Postgres + AGE + "
            "pgvector backend the graph nodes, edges, concepts and embeddings are "
            "persisted in tables - catalog mutations mirror into the active store "
            "in the same critical section as the write - and backing that "
            "database up is the operator's responsibility; this repository still "
            "ships none of the schedule, restore procedure or restore evidence "
            "the target names."
        ),
    ),
    "NFR-REL-004": RequirementCoverage(
        status="partial",
        note=(
            "An index exists and so does a repeatable, operator-runnable rebuild "
            "of its contents, which is why this is not `not_implemented`. The "
            "semantic-search index is the `embedding_vectors` table with an "
            "ivfflat cosine ANN index, which `PostgresGraphStore.semantic_search` "
            "orders against; `python -m migrations.run_migrations` re-applies "
            "that index DDL and then re-seeds every concept, dataset and column "
            "node with its embedding from the catalog and ontology via "
            "`sdp.seed.seed_store()`, which is idempotent, also runs at startup "
            "and at import, is tested against a fresh empty store, and is "
            "exercised end to end (migrate, seed, vector search) by the "
            "live-Postgres integration test. What is missing is the acceptance "
            "criterion itself. Nothing detects index corruption: the readiness "
            "probe checks only backend reachability and `age`/`vector` extension "
            "presence. Nothing repairs a corrupt index object either - the "
            "migration's `CREATE INDEX IF NOT EXISTS` is a no-op against an "
            "existing index and there is no `REINDEX` or drop-and-recreate path - "
            "so the rebuild covers index *contents*, not a damaged index. No "
            "rebuild duration is measured or asserted against the four-hour "
            "target. The rebuild's source is process memory (`catalog._DATA`, "
            "seeded from the buyer demo datasets), so it restores seed and "
            "live-process content, not metadata lost with the process. The index "
            "is confined to the Postgres backend: the default in-memory backend "
            "has no index and scans every embedding, `/catalog/search` is an "
            "unindexed linear scan, and the Postgres path's tests skip unless a "
            "reachable `SDP_DATABASE_DSN` is supplied, so CI never runs them."
        ),
    ),
    "NFR-REL-005": RequirementCoverage(
        status="not_implemented",
        note="There is no ingestion pipeline and therefore no retry.",
    ),
    # --- NFR: quality ------------------------------------------------------- #
    "NFR-QUAL-001": RequirementCoverage(
        status="partial",
        evidence=[
            "route:GET /catalog/datasets/{dataset_id}/validate",
            "test:tests/test_published_claim_honesty.py::test_completeness_and_validation_score_the_same_fields",
        ],
        note=(
            "Publish is gated, but only on required-field presence: "
            "`validate_metadata` (src/sdp/catalog.py:730-738, over the ten "
            "`REQUIRED_METADATA_FIELDS` in src/sdp_core/contracts.py:51-62) "
            "enforced at src/sdp/catalog.py:954-956 and covered by "
            "tests/test_api.py::test_publish_requires_schema_and_distribution_metadata. "
            "The ACCEPT's SHACL step is missing in two ways. (1) No SHACL "
            "processor runs: `SHACL_ENGINE_EXECUTED = False` and "
            "`VALIDATION_ENGINE = \"builtin_shape_checks\"` "
            "(src/sdp/semantic_validation.py:73-74); pyshacl is not a dependency. "
            "(2) The equivalent in-process shape check, "
            "`validate_dataset_semantics` (src/sdp/semantic_validation.py:107), "
            "is not a publish precondition — it is read only by `GET "
            "/catalog/datasets/{id}/semantic-validation`, the "
            "`/enterprise/shacl-validation` aggregate, and the steward worklist. "
            "Measured: a dataset with no approved business mapping reports "
            "`conforms: false` (BusinessMappingShape `min_approved_count`, "
            "src/sdp/semantic_validation.py:52,145-157) and still publishes 200, "
            "because `mappings` is outside the field list the publish gate "
            "checks."
        ),
    ),
    "NFR-QUAL-002": RequirementCoverage(
        status="not_implemented",
        note=(
            "The prerequisite is now built: ONT-004 gives the vocabulary a "
            "release identity (revision + content digest) and a versioned "
            "SKOS/RDFS artifact, so there is something to validate — this note "
            "previously said there was no ontology release at all. The "
            "requirement itself is still unmet, and for the reason it names: "
            "**reasoner consistency 통과**. ONT-007 is not_implemented and "
            "nothing checks consistency. The publication path does now apply a "
            "shape before a concept reaches the read surfaces — this note "
            "previously said it applied neither a reasoner nor a SHACL shape, "
            "and the shape half is ONT-005's ConceptShape gate — but a "
            "property-presence shape is not a consistency check, the engine is "
            "`builtin_shape_checks` with `shacl_engine_executed: false`, and the "
            "export carries no OWL axiom for a reasoner to act on. Release "
            "validation in this requirement's sense would need an RDF/OWL stack "
            "this repository deliberately does not depend on."
        ),
    ),
    "NFR-QUAL-003": RequirementCoverage(
        status="partial",
        evidence=[
            "func:sdp.orchestrator.validate_sql_query",
            "test:tests/test_orchestrator.py::test_the_drafter_self_check_is_a_live_guard",
        ],
        note=(
            "Permission and SQL-safety/syntax validation run on both the drafter "
            "(src/sdp/orchestrator.py:379, plus the self-check at :542 before the "
            "draft is returned) and the execution gate (orchestrator.py:812, "
            "829); the source-table allow-list is enforced in validate_sql_query. "
            "Column-vs-schema validation runs on the drafter only "
            "(orchestrator.py:396-404, tests/test_orchestrator.py:138). Two of "
            "the four ACCEPT checks are missing at the execution gate. There is "
            "no cost validation anywhere: `estimated_cost` (orchestrator.py:520) "
            "is reported at :605 but never compared to a budget, and "
            "validate_sql_query imposes no LIMIT requirement, so `/browse/query` "
            "accepts `LIMIT 999999999` or no LIMIT at all. And the execution gate "
            "never re-checks columns against the dataset schema, so a statement "
            "naming an undeclared column (`SELECT totally_bogus_column FROM "
            "customer LIMIT 10`) returns SUCCEEDED. The PRD's own Query Validator "
            "design (docs/prd-trd.md:288) names table/column allowlist, syntax, "
            "cost and limit; BRW-006 already records cost limits as not "
            "implemented. Execution is mocked (`mock_execution_no_real_data`), so "
            "no cost is measured either."
        ),
    ),
    "NFR-QUAL-004": RequirementCoverage(
        status="partial",
        evidence=["test:tests/test_state_isolation.py::test_every_test_starts_from_the_seeded_baseline"],
        note=(
            "A pytest regression suite and its CI workflow exist, and "
            "tests/test_state_isolation.py pins order-independence of the shared "
            "in-memory state. The ACCEPT is not met: there is no "
            "competency-question registry or CQ test type (ONT-008 is "
            "not_implemented for exactly that) and no CQ pass-rate measurement "
            "anywhere, so a \"핵심 CQ test pass rate 100%\" figure cannot be "
            "produced."
        ),
    ),
}


def requirements_coverage_manifest() -> RequirementCoverageManifest:
    """Join the parsed PRD inventory with the coverage mapping."""
    requirements = parse_prd_requirements()
    entries: list[RequirementCoverageEntry] = []
    unmapped: list[str] = []
    for requirement in requirements:
        coverage = REQUIREMENT_COVERAGE.get(requirement.id)
        if coverage is None:
            unmapped.append(requirement.id)
            continue
        entries.append(
            RequirementCoverageEntry(
                id=requirement.id,
                text=requirement.text,
                priority=requirement.priority,
                acceptance=requirement.acceptance,
                status=coverage.status,
                evidence=list(coverage.evidence),
                note=coverage.note,
            )
        )
    status_counts = {
        status: sum(1 for entry in entries if entry.status == status)
        for status in COVERAGE_STATUSES
    }
    p0_status_counts = {
        status: sum(
            1 for entry in entries if entry.status == status and entry.priority == "P0"
        )
        for status in COVERAGE_STATUSES
    }
    return RequirementCoverageManifest(
        requirement_count=len(requirements),
        entries=entries,
        status_counts=status_counts,
        p0_status_counts=p0_status_counts,
        unmapped_requirement_ids=unmapped,
    )


COVERAGE_DOC_PATH = PRD_PATH.parent / "requirements-coverage.md"

# What each status promises a reader, published in the document itself so the
# table cannot be read as a stronger claim than it is.
_STATUS_MEANING = {
    "implemented": "이 저장소의 구현이 요구사항에 답하고, 테스트가 이를 덮는다",
    "partial": "일부만 답한다. `비고`가 무엇이 빠졌는지 명시한다",
    "not_implemented": "아무것도 답하지 않는다. 생략하지 않고 그대로 적는다",
    "external": "배포/호스트 플랫폼의 책임이며 이 코드베이스의 것이 아니다",
}

_GROUP_SUFFIX = re.compile(r"^(?P<group>.+)-\d{3}$")


def requirement_group(requirement_id: str) -> str:
    """The id's family prefix (``CAT-001`` → ``CAT``, ``NFR-SEC-001`` → ``NFR-SEC``)."""
    match = _GROUP_SUFFIX.match(requirement_id)
    if match is None:
        return requirement_id
    return match.group("group")


def render_requirements_coverage_markdown() -> str:
    """Render the coverage matrix as the document committed at ``COVERAGE_DOC_PATH``.

    The group order is the PRD's own (first appearance), not a list kept here, so
    reordering the source document reorders this one instead of desynchronising it.
    """
    manifest = requirements_coverage_manifest()
    groups: dict[str, list[RequirementCoverageEntry]] = {}
    for entry in manifest.entries:
        groups.setdefault(requirement_group(entry.id), []).append(entry)

    nfr_count = sum(1 for entry in manifest.entries if entry.priority == "NFR")
    functional_count = len(manifest.entries) - nfr_count

    lines = [
        "# 요구사항 대응 매트릭스 (PRD/TRD, 생성 문서)",
        "",
        "이 문서는 **생성물**이다. `docs/prd-trd.md`의 요구사항 표를 파싱해",
        "`src/sdp_core/requirements.py`의 `REQUIREMENT_COVERAGE`와 조인한 결과이며,",
        "손으로 수정하지 말고 아래 명령으로 재생성한다:",
        "",
        "```bash",
        "PYTHONPATH=src python -m sdp_core.requirements",
        "```",
        "",
        "`tests/test_requirements_coverage.py`가 네 가지를 강제한다: (1) PRD의 모든",
        "요구사항 ID가 매핑되어 있는지, (2) 모든 증빙 포인터가 실제로 해석되는지",
        "(이 앱이 서비스하는 route / import 가능한 attribute / 수집되는 test),",
        "(3) `implemented` 주장이 해석되는 증빙을 최소 하나 가지는지, (4) 이 파일이",
        "생성 결과와 글자 단위로 일치하는지. 따라서 PRD가 바뀌거나 증빙이 사라지면",
        "문서가 조용히 낡는 대신 테스트가 깨진다.",
        "",
        "## 상태 어휘",
        "",
        "| 상태 | 의미 |",
        "| --- | --- |",
    ]
    for status in COVERAGE_STATUSES:
        lines.append(f"| `{status}` | {_STATUS_MEANING[status]} |")

    lines += [
        "",
        "## 집계",
        "",
        f"요구사항 총 {len(manifest.entries)}건 "
        f"(기능 {functional_count}건 + NFR {nfr_count}건).",
        "",
        "| 상태 | 전체 | P0 |",
        "| --- | --- | --- |",
    ]
    for status in COVERAGE_STATUSES:
        lines.append(
            f"| `{status}` | {manifest.status_counts[status]} "
            f"| {manifest.p0_status_counts[status]} |"
        )

    lines += ["", "## 전체 색인", "", "| ID | 우선순위 | 상태 |", "| --- | --- | --- |"]
    for entry in manifest.entries:
        lines.append(f"| {entry.id} | {entry.priority} | `{entry.status}` |")

    lines += ["", "## 요구사항별 대응"]
    for group, entries in groups.items():
        lines += ["", f"### {group}"]
        for entry in entries:
            lines += [
                "",
                f"#### {entry.id} · {entry.priority} · `{entry.status}`",
                "",
                f"- **요구사항**: {entry.text}",
                f"- **수락 기준**: {entry.acceptance}",
            ]
            if entry.evidence:
                pointers = ", ".join(f"`{pointer}`" for pointer in entry.evidence)
                lines.append(f"- **증빙**: {pointers}")
            if entry.note:
                lines.append(f"- **비고**: {entry.note}")

    lines.append("")
    return "\n".join(lines)


def main() -> int:
    """Write the generated coverage document and report whether it changed."""
    rendered = render_requirements_coverage_markdown()
    previous = (
        COVERAGE_DOC_PATH.read_text(encoding="utf-8")
        if COVERAGE_DOC_PATH.exists()
        else None
    )
    COVERAGE_DOC_PATH.write_text(rendered, encoding="utf-8")
    print(
        f"{COVERAGE_DOC_PATH}: "
        + ("unchanged" if previous == rendered else "regenerated")
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry, exercised only on direct execution
    raise SystemExit(main())
