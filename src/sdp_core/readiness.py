from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel, Field

from .contracts import AuditEvent, Dataset, PolicyDecision
from .demo_seed import (
    BuyerDemoDatasetSummary,
    buyer_demo_dataset_summaries,
    get_buyer_demo_domain,
)


class CatalogStore(Protocol):
    """Persistence boundary for catalog metadata."""

    def list_datasets(self) -> list[Dataset]:
        ...

    def get_dataset(self, dataset_id: str) -> Dataset | None:
        ...

    def upsert_dataset(self, dataset: Dataset) -> Dataset:
        ...


class PolicyDecisionStore(Protocol):
    """Persistence boundary for explainable policy decisions."""

    def record_decision(self, decision: PolicyDecision) -> PolicyDecision:
        ...

    def get_decision(self, decision_id: str) -> PolicyDecision | None:
        ...

    def list_decisions(self, *, resource: str | None = None, limit: int = 100) -> list[PolicyDecision]:
        ...


class AuditEventStore(Protocol):
    """Append-only boundary for user-visible compliance evidence."""

    def append_event(self, event: AuditEvent) -> AuditEvent:
        ...

    def list_events(self, *, resource: str | None = None, limit: int = 100) -> list[AuditEvent]:
        ...


class SourceConnector(Protocol):
    """Source-system connector boundary used by browse/query workflows."""

    connector_id: str
    source_type: str

    def inspect_schema(self, dataset_id: str) -> dict[str, Any]:
        ...

    def preview(self, dataset_id: str, *, limit: int, offset: int) -> list[dict[str, Any]]:
        ...


class PackageBoundary(BaseModel):
    id: str
    kind: str
    owns: list[str]
    split_trigger: str
    release_rule: str


class StoreCapability(BaseModel):
    id: str
    responsibility: str
    durability_required: bool = True
    extraction_target: str
    minimum_backend: str
    scale_gate: str


class ConnectorCapability(BaseModel):
    id: str
    source_type: str
    protocol: str
    required_controls: list[str]
    proof: str


class EnterpriseGate(BaseModel):
    id: str
    label: str
    target: str
    evidence: list[str]
    status: str = Field(pattern="^(implemented|planned|external)$")


class DemoWorkflowStep(BaseModel):
    id: str
    day_range: str
    owner: str
    outcome: str
    proof_endpoints: list[str]


class BuyerDemoActivationPlan(BaseModel):
    priority_domain: str
    domain_fixture_id: str | None = None
    activation_days: int
    selected_connectors: list[ConnectorCapability]
    demo_datasets: list[BuyerDemoDatasetSummary] = Field(default_factory=list)
    analyst_questions: list[str] = Field(default_factory=list)
    governance_questions: list[str] = Field(default_factory=list)
    data_requirements: list[str]
    control_requirements: list[str]
    workflow: list[DemoWorkflowStep]
    acceptance_criteria: list[str]
    handoff_artifacts: list[str]


class EnterpriseReadinessManifest(BaseModel):
    product: str
    valuation_target_krw: int
    completion_standard: str
    package_boundary: list[PackageBoundary]
    submodule_decision: dict[str, str]
    storage_capabilities: list[StoreCapability]
    connector_capabilities: list[ConnectorCapability]
    enterprise_gates: list[EnterpriseGate]
    design_artifacts: list[dict[str, str]]
    immediate_next_splits: list[dict[str, str]]


def catalog_store_capabilities() -> list[StoreCapability]:
    return [
        StoreCapability(
            id="catalog_metadata",
            responsibility="Versioned dataset metadata, schema history, lineage, DCAT/JSON-LD export, and business-term mappings.",
            extraction_target="sdp_core.catalog",
            minimum_backend="PostgreSQL or document store with optimistic versioning and full-text/search-index sync.",
            scale_gate="10,000 datasets, 1,000,000 searchable columns, p95 search API under 500 ms.",
        ),
        StoreCapability(
            id="policy_decisions",
            responsibility="Explainable allow/deny decisions with obligations, purpose, subject, resource, and decision id traceability.",
            extraction_target="sdp_core.policy",
            minimum_backend="Append-friendly relational table keyed by decision_id with immutable payload snapshots.",
            scale_gate="100 percent of preview/query/catalog mutations linked to a policy_decision_id.",
        ),
        StoreCapability(
            id="audit_events",
            responsibility="Append-only audit trail for catalog mutation, preview, query, ontology patch, and admin actions.",
            extraction_target="sdp_core.audit",
            minimum_backend="Write-once log sink plus queryable hot store; retention and export policy must be tenant configurable.",
            scale_gate="365-day searchable retention with tamper-evidence for enterprise buyer diligence.",
        ),
        StoreCapability(
            id="ontology_registry",
            responsibility="Concept graph, synonyms, SKOS/SHACL compatibility, and steward-reviewed ontology patch lifecycle.",
            extraction_target="sdp_core.ontology",
            minimum_backend="RDF store or graph database with deterministic JSON export for CI validation.",
            scale_gate="70 percent or higher mapping coverage for buyer-selected critical business glossary terms.",
        ),
    ]


def connector_registry_manifest() -> list[ConnectorCapability]:
    return [
        ConnectorCapability(
            id="sql_connector",
            source_type="warehouse_or_rdbms",
            protocol="SQL with read-only credentials and statement timeout",
            required_controls=["policy_before_query", "row_limit", "timeout_ms", "audit_event", "pii_masking"],
            proof="/browse/query and /llm/draft-query",
        ),
        ConnectorCapability(
            id="rdf_connector",
            source_type="semantic_store",
            protocol="SPARQL/Graph query with named graph allow-list",
            required_controls=["ontology_version_pin", "policy_before_query", "audit_event"],
            proof="/ontology/search and /catalog/datasets/{dataset_id}/jsonld",
        ),
        ConnectorCapability(
            id="rest_connector",
            source_type="governed_api",
            protocol="HTTP API with signed service account and schema inspection adapter",
            required_controls=["credential_vault", "purpose_binding", "audit_event"],
            proof="planned connector contract in sdp_core.SourceConnector",
        ),
        ConnectorCapability(
            id="file_lake_connector",
            source_type="object_storage_or_lakehouse",
            protocol="Manifest-based file scan with partition and profile sampling",
            required_controls=["sample_budget", "pii_profile", "lineage_capture", "audit_event"],
            proof="planned connector contract in sdp_core.SourceConnector",
        ),
    ]


def buyer_demo_activation_plan(
    priority_domain: str = "customer intelligence",
    connector_ids: list[str] | None = None,
) -> BuyerDemoActivationPlan:
    domain_fixture = get_buyer_demo_domain(priority_domain)
    connectors = {connector.id: connector for connector in connector_registry_manifest()}
    selected_ids = connector_ids or (
        domain_fixture.default_connectors if domain_fixture else ["sql_connector", "rdf_connector"]
    )
    unknown = sorted(set(selected_ids) - set(connectors))
    if unknown:
        raise ValueError(f"unsupported connector ids: {', '.join(unknown)}")

    selected = [connectors[connector_id] for connector_id in selected_ids]
    demo_datasets = buyer_demo_dataset_summaries(domain_fixture.id) if domain_fixture else []
    analyst_questions = domain_fixture.analyst_questions if domain_fixture else []
    governance_questions = domain_fixture.governance_questions if domain_fixture else []
    fixture_acceptance = domain_fixture.acceptance_questions if domain_fixture else []
    return BuyerDemoActivationPlan(
        priority_domain=priority_domain,
        domain_fixture_id=domain_fixture.id if domain_fixture else None,
        activation_days=10,
        selected_connectors=selected,
        demo_datasets=demo_datasets,
        analyst_questions=analyst_questions,
        governance_questions=governance_questions,
        data_requirements=[
            "3 to 5 priority datasets with owner, steward, schema, sensitivity, freshness, and source system.",
            "20 to 50 buyer glossary terms with approved definitions and synonyms.",
            "Read-only service account or representative fixture for every selected connector.",
            "One analyst question and one governance question that must be demonstrated end to end.",
        ],
        control_requirements=[
            "Policy decision before preview or query.",
            "Audit event for catalog mutation, preview, query, and ontology patch workflow.",
            "PII masking or explicit denial for sensitive data.",
            "Central workflow, security scan, and coverage evidence before pilot handoff.",
        ],
        workflow=[
            DemoWorkflowStep(
                id="domain_intake",
                day_range="D1-D2",
                owner="product + data steward",
                outcome="Buyer domain, glossary scope, datasets, and acceptance questions are locked.",
                proof_endpoints=["/enterprise/readiness"],
            ),
            DemoWorkflowStep(
                id="metadata_onboarding",
                day_range="D3-D4",
                owner="data platform engineer",
                outcome="Datasets expose searchable metadata, schema history, lineage, validation, and quality signals.",
                proof_endpoints=[
                    "/catalog/datasets",
                    "/catalog/datasets/{dataset_id}/validate",
                    "/catalog/datasets/{dataset_id}/lineage",
                ],
            ),
            DemoWorkflowStep(
                id="semantic_mapping",
                day_range="D5-D6",
                owner="ontology engineer",
                outcome="Critical buyer terms resolve to approved concepts or steward-reviewed patch proposals.",
                proof_endpoints=["/ontology/search", "/ontology/resolve", "/ontology/patches"],
            ),
            DemoWorkflowStep(
                id="governed_browse_query",
                day_range="D7-D8",
                owner="backend engineer + security reviewer",
                outcome="Preview and query paths run through policy, audit, row limits, timeout, and connector controls.",
                proof_endpoints=["/browse/{dataset_id}/preview", "/browse/query", "/audit/events"],
            ),
            DemoWorkflowStep(
                id="buyer_readout",
                day_range="D9-D10",
                owner="product + solution architect",
                outcome="Buyer receives a reproducible demo script, evidence packet, risk register, and next integration backlog.",
                proof_endpoints=["/enterprise/demo-plan", "docs/enterprise-readiness.md"],
            ),
        ],
        acceptance_criteria=fixture_acceptance + [
            "At least one buyer analyst question resolves from natural language to dataset recommendation and governed query path.",
            "All preview/query paths produce policy_decision_id and audit evidence.",
            "Critical glossary mapping coverage is at least 70 percent or every gap has a steward patch proposal.",
            "Metadata validation pass rate is at least 95 percent across priority datasets.",
            "Unsupported connector requests fail closed before any source credential is used.",
        ],
        handoff_artifacts=[
            "Figma/FigJam journey and IA board with Code Connect disabled.",
            "docs/enterprise-readiness.md",
            "GET /enterprise/readiness output",
            "GET /enterprise/demo-plan output",
            "GET /enterprise/console operator surface",
            "Local pytest and central workflow evidence",
        ],
    )


def enterprise_readiness_manifest() -> EnterpriseReadinessManifest:
    return EnterpriseReadinessManifest(
        product="Semantic Data Portal",
        valuation_target_krw=2_000_000_000,
        completion_standard=(
            "A buyer can run a governed catalog, ontology, policy, audit, and query demonstration "
            "against their own priority domain without code changes, with measurable governance evidence."
        ),
        package_boundary=[
            PackageBoundary(
                id="sdp_core",
                kind="library",
                owns=["domain contracts", "store protocols", "connector protocols", "readiness manifest"],
                split_trigger="When a second application or external connector package consumes the same contracts.",
                release_rule="Semantic versioning, no FastAPI dependency, and backward-compatible schema changes only in minor releases.",
            ),
            PackageBoundary(
                id="sdp_app",
                kind="application",
                owns=["FastAPI routes", "local demo data", "policy orchestration", "buyer demo endpoints"],
                split_trigger="Remains in this repository unless deployment/runtime ownership diverges from core contracts.",
                release_rule="Application releases may move faster than sdp_core but must pass core contract tests.",
            ),
            PackageBoundary(
                id="sdp_design_system",
                kind="design_artifact",
                owns=["Figma/FigJam flows", "information architecture", "component states", "manual token handoff"],
                split_trigger="Extract only after UI implementation starts and token governance has at least one consumer.",
                release_rule="No Figma Code Connect; design tokens are reviewed manually before implementation.",
            ),
        ],
        submodule_decision={
            "decision": "monorepo_package_split_first",
            "reason": "No independently versioned external dependency exists yet; submodules would add release friction before connector ownership is real.",
            "promotion_rule": "Promote a connector to a submodule or separate repository only after it has its own CI, release cadence, secrets policy, and buyer-specific integration backlog.",
        },
        storage_capabilities=catalog_store_capabilities(),
        connector_capabilities=connector_registry_manifest(),
        enterprise_gates=[
            EnterpriseGate(
                id="policy_audit_coverage",
                label="Policy and audit coverage",
                target="100 percent of preview, query, and catalog mutation requests expose policy_decision_id or audit evidence.",
                evidence=[
                    "/browse/{dataset_id}/preview",
                    "/browse/query",
                    "/audit/events",
                    "tests/test_api.py",
                    "tests/test_api.py::test_browse_query_rejects_literal_tautology_injection",
                ],
                status="implemented",
            ),
            EnterpriseGate(
                id="metadata_completeness",
                label="Metadata quality",
                target="95 percent validation pass rate on buyer-selected priority datasets; each dataset exposes owner, steward, lineage, quality, freshness, schema, and license.",
                evidence=["/catalog/datasets/{dataset_id}/validate", "/catalog/datasets/{dataset_id}/lineage", "/catalog/datasets/{dataset_id}/schema-history"],
                status="implemented",
            ),
            EnterpriseGate(
                id="ontology_mapping_coverage",
                label="Semantic coverage",
                target="70 percent or higher mapping coverage for critical business glossary terms before paid pilot conversion.",
                evidence=["/ontology/search", "/ontology/resolve", "/ontology/patches"],
                status="implemented",
            ),
            EnterpriseGate(
                id="buyer_demo_activation",
                label="Buyer demo activation",
                target="A buyer priority domain can be onboarded in two weeks with SQL, RDF, REST, or file connector path selected.",
                evidence=["connector_capabilities", "docs/enterprise-readiness.md"],
                status="planned",
            ),
            EnterpriseGate(
                id="tenant_authz_model",
                label="Tenant authorization model",
                target="Dataset access is scoped by actor tenant context before preview, query, or schema access.",
                evidence=[
                    "sdp_core.ActorContext",
                    "sdp.authz",
                    "/enterprise/controls",
                    "tests/test_api.py::test_tenant_boundary_denies_cross_tenant_preview",
                    "tests/test_api.py::test_oidc_preview_rejects_unverified_claim_shape",
                ],
                status="implemented",
            ),
            EnterpriseGate(
                id="operational_due_diligence",
                label="Operational diligence",
                target="Central required workflows, security scan, coverage evidence, and OSSF baseline pass before production pilot.",
                evidence=["ContextualWisdomLab central required workflows", "PR #2", "PR #4"],
                status="external",
            ),
        ],
        design_artifacts=[
            {
                "id": "figjam_product_map",
                "type": "figjam",
                "url": "https://www.figma.com/board/UptVQaUlwbLVYv20ot4ZDm",
                "code_connect": "disabled",
            },
            {
                "id": "product_design_review",
                "type": "information_architecture",
                "url": "docs/enterprise-readiness.md",
                "code_connect": "disabled",
            },
        ],
        immediate_next_splits=[
            {
                "package": "sdp_core",
                "action": "Keep stable contracts and SQLite evidence-store fallback in the internal package until a second consumer needs a versioned library.",
            },
            {
                "package": "sdp_connectors",
                "action": "Create optional connector package after a second real SQL/RDF/file adapter is added with separate CI and secrets policy.",
            },
            {
                "package": "sdp_enterprise",
                "action": "Expose SSO, RBAC, retention, deployment, and org workflow controls behind the /enterprise/controls feature-gate manifest.",
            },
        ],
    )
