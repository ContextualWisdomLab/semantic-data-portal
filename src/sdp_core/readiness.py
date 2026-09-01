from __future__ import annotations

from typing import Any, ClassVar, Protocol

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    model_serializer,
)

from .contracts import AuditEvent, Dataset, PolicyDecision
from .demo_seed import (
    BuyerDemoDatasetSummary,
    buyer_demo_dataset_summaries,
    get_buyer_demo_domain,
)


class CatalogStore(Protocol):
    """Persistence boundary for catalog metadata."""

    def list_datasets(self) -> list[Dataset]:
        pass

    def get_dataset(self, dataset_id: str) -> Dataset | None:
        pass

    def upsert_dataset(self, dataset: Dataset) -> Dataset:
        pass


class PolicyDecisionStore(Protocol):
    """Persistence boundary for explainable policy decisions."""

    def record_decision(self, decision: PolicyDecision) -> PolicyDecision:
        pass

    def get_decision(self, decision_id: str) -> PolicyDecision | None:
        pass

    def list_decisions(self, *, resource: str | None = None, limit: int = 100) -> list[PolicyDecision]:
        pass


class AuditEventStore(Protocol):
    """Append-only boundary for user-visible compliance evidence."""

    def append_event(self, event: AuditEvent) -> AuditEvent:
        pass

    def list_events(self, *, resource: str | None = None, limit: int = 100) -> list[AuditEvent]:
        pass


class SourceConnector(Protocol):
    """Source-system connector boundary used by browse/query workflows."""

    connector_id: str
    source_type: str

    def inspect_schema(self, dataset_id: str) -> dict[str, Any]:
        pass

    def preview(self, dataset_id: str, *, limit: int, offset: int) -> list[dict[str, Any]]:
        pass


class SemanticReadinessModel(BaseModel):
    """Readiness contract with semantic Python names and stable legacy wire keys."""

    model_config = ConfigDict(populate_by_name=True)
    legacy_attribute_map: ClassVar[dict[str, str]] = {}

    @model_serializer(mode="wrap")
    def serialize_wire_contract(
        self,
        serializer: SerializerFunctionWrapHandler,
    ) -> dict[str, Any]:
        """Emit established public keys while keeping semantic internal fields."""

        serialized_contract = serializer(self)
        wire_payload: dict[str, Any] = {}
        for semantic_field_name, model_field in self.__class__.model_fields.items():
            wire_field_name = model_field.alias or semantic_field_name
            if semantic_field_name in serialized_contract:
                wire_payload[wire_field_name] = serialized_contract[semantic_field_name]
            elif wire_field_name in serialized_contract:
                wire_payload[wire_field_name] = serialized_contract[wire_field_name]
        return wire_payload

    def __getattr__(self, attribute_name: str) -> Any:
        semantic_field_name = self.legacy_attribute_map.get(attribute_name)
        if semantic_field_name is not None:
            return super().__getattribute__(semantic_field_name)
        return super().__getattr__(attribute_name)

    def __setattr__(self, attribute_name: str, attribute_value: Any) -> None:
        semantic_field_name = self.legacy_attribute_map.get(attribute_name, attribute_name)
        super().__setattr__(semantic_field_name, attribute_value)


class PackageBoundary(SemanticReadinessModel):
    legacy_attribute_map = {
        "id": "package_boundary_id",
        "kind": "package_kind",
        "owns": "owned_responsibilities",
    }

    package_boundary_id: str = Field(alias="id")
    package_kind: str = Field(alias="kind")
    owned_responsibilities: list[str] = Field(alias="owns")
    split_trigger: str
    release_rule: str


class StoreCapability(SemanticReadinessModel):
    legacy_attribute_map = {
        "id": "store_capability_id",
        "responsibility": "store_responsibility",
    }

    store_capability_id: str = Field(alias="id")
    store_responsibility: str = Field(alias="responsibility")
    durability_required: bool = True
    extraction_target: str
    minimum_backend: str
    scale_gate: str


class ConnectorCapability(SemanticReadinessModel):
    legacy_attribute_map = {
        "id": "connector_capability_id",
        "protocol": "connector_protocol",
        "proof": "connector_proof",
    }

    connector_capability_id: str = Field(alias="id")
    source_type: str
    connector_protocol: str = Field(alias="protocol")
    required_controls: list[str]
    connector_proof: str = Field(alias="proof")


class EnterpriseGate(SemanticReadinessModel):
    legacy_attribute_map = {
        "id": "enterprise_gate_id",
        "label": "gate_label",
        "target": "gate_target",
        "evidence": "gate_evidence",
        "status": "gate_status",
    }

    enterprise_gate_id: str = Field(alias="id")
    gate_label: str = Field(alias="label")
    gate_target: str = Field(alias="target")
    gate_evidence: list[str] = Field(alias="evidence")
    gate_status: str = Field(alias="status", pattern="^(implemented|planned|external)$")


class DemoWorkflowStep(SemanticReadinessModel):
    legacy_attribute_map = {
        "id": "workflow_step_id",
        "owner": "step_owner",
        "outcome": "step_outcome",
    }

    workflow_step_id: str = Field(alias="id")
    day_range: str
    step_owner: str = Field(alias="owner")
    step_outcome: str = Field(alias="outcome")
    proof_endpoints: list[str]


class BuyerDemoActivationPlan(SemanticReadinessModel):
    legacy_attribute_map = {"workflow": "demo_workflow_steps"}

    priority_domain: str
    domain_fixture_id: str | None = None
    activation_days: int
    selected_connectors: list[ConnectorCapability]
    demo_datasets: list[BuyerDemoDatasetSummary] = Field(default_factory=list)
    analyst_questions: list[str] = Field(default_factory=list)
    governance_questions: list[str] = Field(default_factory=list)
    data_requirements: list[str]
    control_requirements: list[str]
    demo_workflow_steps: list[DemoWorkflowStep] = Field(alias="workflow")
    acceptance_criteria: list[str]
    handoff_artifacts: list[str]


class SubmoduleDecision(SemanticReadinessModel):
    legacy_attribute_map = {
        "decision": "submodule_strategy",
        "reason": "decision_reason",
    }

    submodule_strategy: str = Field(alias="decision")
    decision_reason: str = Field(alias="reason")
    promotion_rule: str


class DesignArtifact(SemanticReadinessModel):
    legacy_attribute_map = {
        "id": "design_artifact_id",
        "type": "artifact_type",
        "url": "artifact_url",
    }

    design_artifact_id: str = Field(alias="id")
    artifact_type: str = Field(alias="type")
    artifact_url: str = Field(alias="url")
    code_connect: str


class PlannedPackageSplit(SemanticReadinessModel):
    legacy_attribute_map = {
        "package": "package_name",
        "action": "split_action",
    }

    package_name: str = Field(alias="package")
    split_action: str = Field(alias="action")


class EnterpriseReadinessManifest(SemanticReadinessModel):
    legacy_attribute_map = {
        "product": "product_name",
        "package_boundary": "package_boundaries",
    }

    product_name: str = Field(alias="product")
    valuation_target_krw: int
    completion_standard: str
    package_boundaries: list[PackageBoundary] = Field(alias="package_boundary")
    submodule_decision: SubmoduleDecision
    storage_capabilities: list[StoreCapability]
    connector_capabilities: list[ConnectorCapability]
    enterprise_gates: list[EnterpriseGate]
    design_artifacts: list[DesignArtifact]
    immediate_next_splits: list[PlannedPackageSplit]


def catalog_store_capabilities() -> list[StoreCapability]:
    return [
        StoreCapability(
            store_capability_id="catalog_metadata",
            store_responsibility="Versioned dataset metadata, schema history, lineage, DCAT/JSON-LD export, and business-term mappings.",
            extraction_target="sdp_core.catalog",
            minimum_backend="PostgreSQL or document store with optimistic versioning and full-text/search-index sync.",
            scale_gate="10,000 datasets, 1,000,000 searchable columns, p95 search API under 500 ms.",
        ),
        StoreCapability(
            store_capability_id="policy_decisions",
            store_responsibility="Explainable allow/deny decisions with obligations, purpose, subject, resource, and decision id traceability.",
            extraction_target="sdp_core.policy",
            minimum_backend="Append-friendly relational table keyed by decision_id with immutable payload snapshots.",
            scale_gate="100 percent of preview/query/catalog mutations linked to a policy_decision_id.",
        ),
        StoreCapability(
            store_capability_id="audit_events",
            store_responsibility="Append-only audit trail for catalog mutation, preview, query, ontology patch, and admin actions.",
            extraction_target="sdp_core.audit",
            minimum_backend="Write-once log sink plus queryable hot store; retention and export policy must be tenant configurable.",
            scale_gate="365-day searchable retention with tamper-evidence for enterprise buyer diligence.",
        ),
        StoreCapability(
            store_capability_id="ontology_registry",
            store_responsibility="Concept graph, synonyms, SKOS/SHACL compatibility, and steward-reviewed ontology patch lifecycle.",
            extraction_target="sdp_core.ontology",
            minimum_backend="RDF store or graph database with deterministic JSON export for CI validation.",
            scale_gate="70 percent or higher mapping coverage for buyer-selected critical business glossary terms.",
        ),
    ]


def connector_registry_manifest() -> list[ConnectorCapability]:
    return [
        ConnectorCapability(
            connector_capability_id="sql_connector",
            source_type="warehouse_or_rdbms",
            connector_protocol="SQL with read-only credentials and statement timeout",
            required_controls=["policy_before_query", "row_limit", "timeout_ms", "audit_event", "pii_masking"],
            connector_proof="/browse/query and /llm/draft-query",
        ),
        ConnectorCapability(
            connector_capability_id="rdf_connector",
            source_type="semantic_store",
            connector_protocol="SPARQL/Graph query with named graph allow-list",
            required_controls=["ontology_version_pin", "policy_before_query", "audit_event"],
            connector_proof="/ontology/search and /catalog/datasets/{dataset_id}/jsonld",
        ),
        ConnectorCapability(
            connector_capability_id="rest_connector",
            source_type="governed_api",
            connector_protocol="HTTP API with signed service account and schema inspection adapter",
            required_controls=["credential_vault", "purpose_binding", "audit_event"],
            connector_proof="planned connector contract in sdp_core.SourceConnector",
        ),
        ConnectorCapability(
            connector_capability_id="file_lake_connector",
            source_type="object_storage_or_lakehouse",
            connector_protocol="Manifest-based file scan with partition and profile sampling",
            required_controls=["sample_budget", "pii_profile", "lineage_capture", "audit_event"],
            connector_proof="planned connector contract in sdp_core.SourceConnector",
        ),
    ]


def buyer_demo_activation_plan(
    priority_domain: str = "customer intelligence",
    connector_ids: list[str] | None = None,
) -> BuyerDemoActivationPlan:
    domain_fixture = get_buyer_demo_domain(priority_domain)
    connectors = {
        connector.connector_capability_id: connector
        for connector in connector_registry_manifest()
    }
    selected_ids = connector_ids or (
        domain_fixture.default_connectors if domain_fixture else ["sql_connector", "rdf_connector"]
    )
    unknown = sorted(set(selected_ids) - set(connectors))
    if unknown:
        raise ValueError(f"unsupported connector ids: {', '.join(unknown)}")

    selected = [connectors[connector_id] for connector_id in selected_ids]
    demo_datasets = (
        buyer_demo_dataset_summaries(domain_fixture.demo_domain_id)
        if domain_fixture
        else []
    )
    analyst_questions = domain_fixture.analyst_questions if domain_fixture else []
    governance_questions = domain_fixture.governance_questions if domain_fixture else []
    fixture_acceptance = domain_fixture.acceptance_questions if domain_fixture else []
    return BuyerDemoActivationPlan(
        priority_domain=priority_domain,
        domain_fixture_id=domain_fixture.demo_domain_id if domain_fixture else None,
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
        demo_workflow_steps=[
            DemoWorkflowStep(
                workflow_step_id="domain_intake",
                day_range="D1-D2",
                step_owner="product + data steward",
                step_outcome="Buyer domain, glossary scope, datasets, and acceptance questions are locked.",
                proof_endpoints=["/enterprise/readiness"],
            ),
            DemoWorkflowStep(
                workflow_step_id="metadata_onboarding",
                day_range="D3-D4",
                step_owner="data platform engineer",
                step_outcome="Datasets expose searchable metadata, schema history, lineage, validation, and quality signals.",
                proof_endpoints=[
                    "/catalog/datasets",
                    "/catalog/datasets/{dataset_id}/validate",
                    "/catalog/datasets/{dataset_id}/lineage",
                ],
            ),
            DemoWorkflowStep(
                workflow_step_id="semantic_mapping",
                day_range="D5-D6",
                step_owner="ontology engineer",
                step_outcome="Critical buyer terms resolve to approved concepts or steward-reviewed patch proposals.",
                proof_endpoints=["/ontology/search", "/ontology/resolve", "/ontology/patches"],
            ),
            DemoWorkflowStep(
                workflow_step_id="governed_browse_query",
                day_range="D7-D8",
                step_owner="backend engineer + security reviewer",
                step_outcome="Preview and query paths run through policy, audit, row limits, timeout, and connector controls.",
                proof_endpoints=["/browse/{dataset_id}/preview", "/browse/query", "/audit/events"],
            ),
            DemoWorkflowStep(
                workflow_step_id="buyer_readout",
                day_range="D9-D10",
                step_owner="product + solution architect",
                step_outcome="Buyer receives a reproducible demo script, evidence packet, risk register, and next integration backlog.",
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
        product_name="Semantic Data Portal",
        valuation_target_krw=2_000_000_000,
        completion_standard=(
            "A buyer can run a governed catalog, ontology, policy, audit, and query demonstration "
            "against their own priority domain without code changes, with measurable governance evidence."
        ),
        package_boundaries=[
            PackageBoundary(
                package_boundary_id="sdp_core",
                package_kind="library",
                owned_responsibilities=["domain contracts", "store protocols", "connector protocols", "readiness manifest"],
                split_trigger="When a second application or external connector package consumes the same contracts.",
                release_rule="Semantic versioning, no FastAPI dependency, and backward-compatible schema changes only in minor releases.",
            ),
            PackageBoundary(
                package_boundary_id="sdp_app",
                package_kind="application",
                owned_responsibilities=["FastAPI routes", "local demo data", "policy orchestration", "buyer demo endpoints"],
                split_trigger="Remains in this repository unless deployment/runtime ownership diverges from core contracts.",
                release_rule="Application releases may move faster than sdp_core but must pass core contract tests.",
            ),
            PackageBoundary(
                package_boundary_id="sdp_design_system",
                package_kind="design_artifact",
                owned_responsibilities=["Figma/FigJam flows", "information architecture", "component states", "manual token handoff"],
                split_trigger="Extract only after UI implementation starts and token governance has at least one consumer.",
                release_rule="No Figma Code Connect; design tokens are reviewed manually before implementation.",
            ),
        ],
        submodule_decision=SubmoduleDecision(
            submodule_strategy="monorepo_package_split_first",
            decision_reason="No independently versioned external dependency exists yet; submodules would add release friction before connector ownership is real.",
            promotion_rule="Promote a connector to a submodule or separate repository only after it has its own CI, release cadence, secrets policy, and buyer-specific integration backlog.",
        ),
        storage_capabilities=catalog_store_capabilities(),
        connector_capabilities=connector_registry_manifest(),
        enterprise_gates=[
            EnterpriseGate(
                enterprise_gate_id="policy_audit_coverage",
                gate_label="Policy and audit coverage",
                gate_target="100 percent of preview, query, and catalog mutation requests expose policy_decision_id or audit evidence.",
                gate_evidence=[
                    "/browse/{dataset_id}/preview",
                    "/browse/query",
                    "/audit/events",
                    "tests/test_api.py",
                    "tests/test_api.py::test_browse_query_rejects_literal_tautology_injection",
                ],
                gate_status="implemented",
            ),
            EnterpriseGate(
                enterprise_gate_id="metadata_completeness",
                gate_label="Metadata quality",
                gate_target="95 percent validation pass rate on buyer-selected priority datasets; each dataset exposes owner, steward, lineage, quality, freshness, schema, and license.",
                gate_evidence=["/catalog/datasets/{dataset_id}/validate", "/catalog/datasets/{dataset_id}/lineage", "/catalog/datasets/{dataset_id}/schema-history"],
                gate_status="implemented",
            ),
            EnterpriseGate(
                enterprise_gate_id="ontology_mapping_coverage",
                gate_label="Semantic coverage",
                gate_target="70 percent or higher mapping coverage for critical business glossary terms before paid pilot conversion.",
                gate_evidence=["/ontology/search", "/ontology/resolve", "/ontology/patches"],
                gate_status="implemented",
            ),
            EnterpriseGate(
                enterprise_gate_id="buyer_demo_activation",
                gate_label="Buyer demo activation",
                gate_target="A buyer priority domain can be onboarded in two weeks with SQL, RDF, REST, or file connector path selected.",
                gate_evidence=["connector_capabilities", "docs/enterprise-readiness.md"],
                gate_status="planned",
            ),
            EnterpriseGate(
                enterprise_gate_id="tenant_authz_model",
                gate_label="Tenant authorization model",
                gate_target="Dataset access is scoped by actor tenant context before preview, query, or schema access.",
                gate_evidence=[
                    "sdp_core.ActorContext",
                    "sdp.authz",
                    "/enterprise/controls",
                    "tests/test_api.py::test_tenant_boundary_denies_cross_tenant_preview",
                    "tests/test_api.py::test_oidc_preview_rejects_unverified_claim_shape",
                ],
                gate_status="implemented",
            ),
            EnterpriseGate(
                enterprise_gate_id="operational_due_diligence",
                gate_label="Operational diligence",
                gate_target="Central required workflows, security scan, coverage evidence, and OSSF baseline pass before production pilot.",
                gate_evidence=["ContextualWisdomLab central required workflows", "PR #2", "PR #4"],
                gate_status="external",
            ),
        ],
        design_artifacts=[
            DesignArtifact(
                design_artifact_id="figjam_product_map",
                artifact_type="figjam",
                artifact_url="https://www.figma.com/board/UptVQaUlwbLVYv20ot4ZDm",
                code_connect="disabled",
            ),
            DesignArtifact(
                design_artifact_id="operator_console_design_capture",
                artifact_type="figma_design",
                artifact_url="https://www.figma.com/design/JjYSqr6nWxpARUjaVKhG16?node-id=3-2",
                code_connect="disabled",
            ),
            DesignArtifact(
                design_artifact_id="product_design_review",
                artifact_type="information_architecture",
                artifact_url="docs/enterprise-readiness.md",
                code_connect="disabled",
            ),
        ],
        immediate_next_splits=[
            PlannedPackageSplit(
                package_name="sdp_core",
                split_action="Keep stable contracts and SQLite evidence-store fallback in the internal package until a second consumer needs a versioned library.",
            ),
            PlannedPackageSplit(
                package_name="sdp_connectors",
                split_action="Create optional connector package after a second real SQL/RDF/file adapter is added with separate CI and secrets policy.",
            ),
            PlannedPackageSplit(
                package_name="sdp_enterprise",
                split_action="Expose SSO, RBAC, retention, deployment, and org workflow controls behind the /enterprise/controls feature-gate manifest.",
            ),
        ],
    )