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
        status="implemented",
        evidence=[
            "route:GET /catalog/datasets/{dataset_id}",
            "test:tests/test_api.py::test_catalog_dataset_detail_exposes_recommendation_score",
        ],
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
        status="implemented",
        evidence=[
            "route:GET /ontology/concept/{concept}",
            "func:sdp.ontology.concept_assets",
            "test:tests/test_concept_graph_scope.py::test_the_shared_vocabulary_itself_stays_open",
        ],
    ),
    "CAT-005": RequirementCoverage(
        status="implemented",
        evidence=[
            "route:GET /catalog/datasets/{dataset_id}/audit",
            "func:sdp.catalog.ingest_event",
            "test:tests/test_governed_write_evidence.py::test_a_governed_write_records_a_decision_and_an_audit_event",
        ],
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
        ],
    ),
    "CAT-009": RequirementCoverage(
        status="implemented",
        evidence=[
            "route:GET /catalog/datasets/{dataset_id}/join-candidates",
            "route:GET /catalog/datasets/{dataset_id}/related",
            "test:tests/test_api.py::test_join_candidate_endpoint",
            "test:tests/test_catalog.py::test_join_candidates_skips_zero_overlap",
        ],
        note=(
            "Recommendation is scored on shared business terms (the concept "
            "mapping the acceptance criterion names) weighted above shared "
            "column names. There is no business-key notion - no primary or "
            "foreign key is declared anywhere - so column overlap stands in "
            "for it."
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
        status="implemented",
        evidence=[
            "func:sdp.graph_store.GraphNode",
            "test:tests/test_graph_engine.py::test_semantic_search_kind_filter_only_returns_datasets",
        ],
        note="Concept and dataset/column nodes are distinct kinds in the graph store.",
    ),
    "ONT-003": RequirementCoverage(
        status="partial",
        evidence=[
            "route:GET /ontology/term/{term}/graph",
            "test:tests/test_concept_graph_scope.py::test_the_shared_vocabulary_itself_stays_open",
        ],
        note=(
            "broader/narrower/related are carried per concept, which is the SKOS "
            "shape, but no SKOS serialization is emitted and no hierarchy "
            "traversal endpoint exists."
        ),
    ),
    "ONT-004": RequirementCoverage(
        status="not_implemented",
        note=(
            "There is no OWL/RDFS artifact and no ontology version. The concept "
            "vocabulary is a Python dict with no release identity."
        ),
    ),
    "ONT-005": RequirementCoverage(
        status="implemented",
        evidence=[
            "route:POST /ontology/patches",
            "route:POST /ontology/patches/{patch_id}/review",
            "test:tests/test_ontology_publication_loop.py::test_approving_a_patch_publishes_the_term_to_every_read_surface",
        ],
    ),
    "ONT-006": RequirementCoverage(
        status="implemented",
        evidence=[
            "func:sdp.enterprise_evidence.ontology_mapping_coverage_detail",
            "test:tests/test_ontology_coverage_measurement.py::test_coverage_is_measured_against_the_glossary",
        ],
    ),
    "ONT-007": RequirementCoverage(
        status="not_implemented",
        note="No reasoner is integrated and no consistency check runs.",
    ),
    "ONT-008": RequirementCoverage(
        status="not_implemented",
        note="Competency questions are not registrable; no such contract exists.",
    ),
    # --- Browse / query ----------------------------------------------------- #
    "BRW-001": RequirementCoverage(
        status="implemented",
        evidence=[
            "route:GET /browse/{dataset_id}/schema",
            "test:tests/test_api.py::test_browse_schema_requires_purpose",
        ],
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
            "null ratio, distinct ratio and freshness are carried per column and "
            "published with provenance labels; min/max is in the profile contract "
            "but nothing computes it from data."
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
            "row_limit and timeout_ms are validated and echoed, and the sample "
            "budget is hard-capped. Memory and cost limits are not implemented, "
            "and nothing enforces a timeout because nothing executes."
        ),
    ),
    "BRW-007": RequirementCoverage(
        status="implemented",
        evidence=[
            "func:sdp.browse.preview",
            "test:tests/test_payload_type_robustness.py::test_the_decision_and_audit_halves_stay_paired",
        ],
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
        status="implemented",
        evidence=[
            "route:POST /graph/query",
            "route:GET /graph/nodes/{node_id}",
            "test:tests/test_graph_tenant_scope.py::test_graph_traversal_withholds_other_tenants_nodes",
        ],
    ),
    # --- LLM ---------------------------------------------------------------- #
    "LLM-001": RequirementCoverage(
        status="implemented",
        evidence=[
            "route:POST /llm/search",
            "test:tests/test_api.py::test_llm_search_uses_catalog_discovery_policy_scope",
        ],
    ),
    "LLM-002": RequirementCoverage(
        status="implemented",
        evidence=[
            "func:sdp.ontology.resolve_terms",
            "test:tests/test_api.py::test_ontology_resolve",
        ],
    ),
    "LLM-003": RequirementCoverage(
        status="implemented",
        evidence=[
            "func:sdp.orchestrator.draft_sql",
            "test:tests/test_orchestrator.py::test_a_rewritten_column_is_reported_rather_than_contradicted",
        ],
        note=(
            "The drafter uses only declared columns and the catalog-derived table "
            "name, and refuses a column the dataset does not declare."
        ),
    ),
    "LLM-004": RequirementCoverage(
        status="implemented",
        evidence=[
            "func:sdp.orchestrator.draft_sql",
            "test:tests/test_orchestrator.py::test_every_seeded_dataset_drafts_a_statement_its_validator_accepts",
        ],
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
            "The question is screened for forbidden keywords and the generated "
            "statement must pass the safety gate, which bounds what an injected "
            "instruction could produce. There is no prompt-injection classifier, "
            "because no model is called."
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
            "Dataset-level control is enforced per tenant and per role, and "
            "column-level control is enforced as masking. There is no per-table "
            "level, because a dataset is the table here."
        ),
    ),
    "POL-003": RequirementCoverage(
        status="implemented",
        evidence=[
            "func:sdp.browse.preview",
            "test:tests/test_browse.py::test_preview_masks_every_declared_pii_column",
        ],
    ),
    "POL-004": RequirementCoverage(
        status="implemented",
        evidence=[
            "func:sdp.policy.evaluate",
            "test:tests/test_governance_boundary.py::test_no_purpose_spelling_bypasses_the_export_denial",
        ],
    ),
    "POL-005": RequirementCoverage(
        status="implemented",
        evidence=[
            "route:GET /policy/decisions",
            "test:tests/test_governed_write_evidence.py::test_a_governed_write_records_a_decision_and_an_audit_event",
        ],
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
        status="implemented",
        evidence=[
            "route:GET /catalog/datasets/{dataset_id}/lineage",
            "test:tests/test_graph_mirroring.py::test_every_mirrored_facet_is_reconciled_not_only_appended",
        ],
    ),
    "LIN-002": RequirementCoverage(
        status="not_implemented",
        note="Column-level lineage is Phase 2 in the PRD and is not built.",
    ),
    "LIN-003": RequirementCoverage(
        status="partial",
        evidence=["route:GET /catalog/datasets/{dataset_id}/profile"],
        note=(
            "null ratio, distinct ratio and freshness are present; duplicate "
            "ratio is not computed anywhere."
        ),
    ),
    "LIN-004": RequirementCoverage(
        status="not_implemented",
        note=(
            "Quality scores are carried and published, but no threshold is "
            "configured and no warning is derived from one."
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
        status="implemented",
        evidence=[
            "route:GET /enterprise/shacl-validation",
            "test:tests/test_semantic_validation.py::test_every_published_required_property_is_evaluated",
        ],
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
            "Audit events are searchable by resource and tenant-scoped. There is "
            "no export format and no date-range filter."
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
            "OIDC token verification against operator-configured JWKS is built. "
            "SAML is not, and there is no session or login flow - the service "
            "verifies a token a host obtained."
        ),
    ),
    "NFR-SEC-002": RequirementCoverage(
        status="implemented",
        evidence=[
            "func:sdp_core.rbac.enterprise_rbac_matrix",
            "func:sdp.policy.evaluate",
            "test:tests/test_published_claim_honesty.py::test_every_published_grant_is_one_the_engine_actually_allows",
        ],
        note="Roles plus tenant/sensitivity/purpose attributes, i.e. RBAC + ABAC.",
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
        status="external",
        note=(
            "TLS terminates at the deployment's edge. This service speaks HTTP "
            "and the compose/Traefik configuration owns transport security."
        ),
    ),
    "NFR-SEC-005": RequirementCoverage(
        status="implemented",
        evidence=[
            "func:sdp.catalog.ingest_event",
            "test:tests/test_governed_write_evidence.py::test_a_governed_write_records_a_decision_and_an_audit_event",
        ],
    ),
    "NFR-SEC-006": RequirementCoverage(
        status="implemented",
        evidence=[
            "test:tests/test_source_system_redaction.py::test_no_connection_string_form_survives_with_its_secret",
        ],
        note="No model is called, so no data leaves for one; redaction is asserted.",
    ),
    "NFR-SEC-007": RequirementCoverage(
        status="implemented",
        evidence=[
            "func:sdp.orchestrator.validate_sql_query",
            "test:tests/test_orchestrator.py::test_a_function_outside_the_allowlist_is_refused",
        ],
    ),
    # --- NFR: reliability --------------------------------------------------- #
    "NFR-REL-001": RequirementCoverage(
        status="not_implemented",
        note="No availability target is measured or published.",
    ),
    "NFR-REL-002": RequirementCoverage(
        status="not_implemented",
        note="No availability target is measured or published.",
    ),
    "NFR-REL-003": RequirementCoverage(
        status="not_implemented",
        note=(
            "There is no backup path for the metadata graph. The evidence store "
            "has durability (a SQLite file or Postgres) but no backup or restore "
            "procedure in this repository."
        ),
    ),
    "NFR-REL-004": RequirementCoverage(
        status="not_implemented",
        note=(
            "Search is an in-process scan with no index, so there is nothing to "
            "rebuild and no rebuild path."
        ),
    ),
    "NFR-REL-005": RequirementCoverage(
        status="not_implemented",
        note="There is no ingestion pipeline and therefore no retry.",
    ),
    # --- NFR: quality ------------------------------------------------------- #
    "NFR-QUAL-001": RequirementCoverage(
        status="implemented",
        evidence=[
            "route:GET /catalog/datasets/{dataset_id}/validate",
            "test:tests/test_published_claim_honesty.py::test_completeness_and_validation_score_the_same_fields",
        ],
    ),
    "NFR-QUAL-002": RequirementCoverage(
        status="not_implemented",
        note=(
            "There is no ontology release, so no release validation. ONT-004 is "
            "the prerequisite and is also unbuilt."
        ),
    ),
    "NFR-QUAL-003": RequirementCoverage(
        status="implemented",
        evidence=[
            "func:sdp.orchestrator.validate_sql_query",
            "test:tests/test_orchestrator.py::test_the_drafter_self_check_is_a_live_guard",
        ],
        note="A generated statement is validated by the same gate before it is returned.",
    ),
    "NFR-QUAL-004": RequirementCoverage(
        status="implemented",
        evidence=["test:tests/test_state_isolation.py::test_every_test_starts_from_the_seeded_baseline"],
        note="The suite is the regression gate; order independence is asserted.",
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
