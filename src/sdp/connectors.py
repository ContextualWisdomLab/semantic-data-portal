from __future__ import annotations

from typing import Any

from sdp_core import SourceConnector, buyer_demo_context_for_dataset, connector_registry_manifest

from . import ontology_version
from .catalog import get_dataset, redacted_source_system
from .credentials import connector_secret_status


_IMPLEMENTED_PROOF = {
    "audit_event": ["/audit/events"],
    "credential_vault": ["/enterprise/connectors/{connector_id}/probe"],
    "lineage_capture": ["/catalog/datasets/{dataset_id}/lineage"],
    "ontology_version_pin": [
        "/ontology/version",
        "/ontology/search",
        "/ontology/resolve",
    ],
    "pii_masking": ["/browse/{dataset_id}/preview"],
    "pii_profile": ["/catalog/datasets/{dataset_id}/profile"],
    "policy_before_query": ["/browse/query", "/policy/decision", "/policy/decisions"],
    "purpose_binding": ["/policy/decision", "/policy/decisions"],
    "row_limit": ["/browse/query", "/llm/draft-query"],
    "sample_budget": ["/browse/{dataset_id}/preview"],
    "timeout_ms": ["/browse/query", "/llm/draft-query"],
}

# Non-endpoint proof for a control, kept separate from ``proof_endpoints``.
# ``credential_vault`` listed ``SDP_CONNECTOR_SECRET_REF_PREFIX`` - an
# environment variable name - in a field called "endpoints", so a reader
# following the list found one entry that is not a URL and no field saying what
# it is.
_IMPLEMENTED_CONFIG_PROOF = {
    "credential_vault": ["SDP_CONNECTOR_SECRET_REF_PREFIX"],
}

# Controls with a check that can actually come out false for a given
# (connector, dataset) pair, rather than an authored assertion.
#
# ``implemented`` was ``bool(_IMPLEMENTED_PROOF.get(control, []))``: the question
# "is this control implemented?" was answered by "is this control's name a key
# in the dict above, with a non-empty list?" - a dict hand-written twenty lines
# earlier in this same file. Measured across every valid (connector, dataset)
# pair, all four connectors and all eleven required controls:
#
#     controls required by any connector   11
#     controls present in _IMPLEMENTED_PROOF 11
#     control evidence rows reporting "planned"  0
#
# ``planned`` was unreachable. The one thing that could move a verdict was
# ``credential_vault``'s secret-presence check, which is why
# ``rest_connector``/``marketing-campaign`` is the single ``contract_only`` pair
# in the whole matrix - the only control doing measurement was carrying the only
# information.
def _verify_credential_vault(connector_id: str, dataset_id: str) -> tuple[bool, dict[str, Any], str]:
    """Runtime check for ``credential_vault``: is the secret reference present?"""
    vault = connector_secret_status(connector_id, dataset_id)
    gap = (
        ""
        if vault.secret_present
        else "the configured secret reference is not present in this deployment"
    )
    return vault.secret_present, vault.public_dict(), gap


def _verify_ontology_version_pin(connector_id: str, dataset_id: str) -> tuple[bool, dict[str, Any], str]:
    """Runtime check for ``ontology_version_pin``: does the pin actually refuse?

    This control was the clearest case of ``proof_route_served`` not being
    evidence. It reported ``implemented`` because this build serves
    ``/ontology/search`` and ``/ontology/resolve`` - and neither response
    contained the string "version" anywhere, while ``ONT-004`` was recorded
    ``not_implemented`` for exactly that reason. Serving the named route was a
    true fact about the build and said nothing about the control.

    The predicate is exercised in both directions (``version_pin_is_enforced``),
    so this verdict can come out false: break the comparison and the control
    stops claiming to be implemented.
    """
    del connector_id, dataset_id  # the vocabulary is shared, not per-dataset
    from . import ontology

    verdict = ontology_version.version_pin_is_enforced(
        ontology.concept_vocabulary_snapshot()
    )
    enforced = bool(verdict.pop("enforced"))
    gap = str(verdict.pop("gap_reason", ""))
    return enforced, verdict, gap


# Who owns a runtime check's outcome. ``build`` means the predicate either holds
# or does not hold in this source tree, whatever the deployment does;
# ``deployment`` means an operator's configuration decides it. The distinction
# is what makes one of these two safe to page on and the other not.
OWNER_BUILD = "build"
OWNER_DEPLOYMENT = "deployment"

# control -> (its runtime check, who owns the outcome). One collection, because
# two hand-written collections of the same set drift and the one that decides
# the published verdict would win silently. ``_RUNTIME_VERIFIED_CONTROLS`` and
# ``BUILD_OWNED_RUNTIME_CONTROLS`` are both derived from it.
_RUNTIME_CONTROL_CHECKS = {
    "credential_vault": (_verify_credential_vault, OWNER_DEPLOYMENT),
    "ontology_version_pin": (_verify_ontology_version_pin, OWNER_BUILD),
}
_RUNTIME_VERIFIED_CONTROLS = frozenset(_RUNTIME_CONTROL_CHECKS)
BUILD_OWNED_RUNTIME_CONTROLS = frozenset(
    control
    for control, (_check, owner) in _RUNTIME_CONTROL_CHECKS.items()
    if owner == OWNER_BUILD
)

# How strong the evidence behind one control row is. Published, because
# "implemented" alone cannot distinguish these and a diligence reader assumes
# the strongest.
VERIFICATION_DECLARED = "declared_only"
VERIFICATION_PROOF_ROUTE = "proof_route_served"
VERIFICATION_RUNTIME = "runtime_probe_verified"


def _served_route_paths() -> frozenset[str]:
    """Route paths this application actually serves.

    Imported inside the function on purpose: ``api`` imports this module, so a
    module-level import would be a cycle. ``connector_probe`` is only ever
    reached from a request handler or ``sdp.demo_smoke``, both long after
    ``api`` has finished importing.

    Asking the app is the point. A control's proof endpoint being a real route
    is a fact about this build that can be false - rename or drop a route and
    the control stops claiming to be implemented - where membership in a
    hand-written dict cannot be.
    """
    from .api import app

    return frozenset(
        route.path for route in app.routes if isinstance(getattr(route, "path", None), str)
    )


def _named_graph(source_system: str) -> str:
    """The SPARQL named graph, derived from the **redacted** locator.

    ``dataset.source_system.removeprefix("sparql://")`` kept whatever the DSN
    carried, so a dataset registered as
    ``sparql://graphuser:RDFPASS999@semantic.graph/ci`` put the cleartext
    credential into the audit event's ``details`` - which
    ``GET /catalog/datasets/{id}/audit?user=analyst`` and
    ``GET /audit/events?user=analyst`` return, to the roles for which the
    governed read routes withhold ``source_system`` entirely.
    ``connector_probe`` redacted; the adapter methods the probe advertises as
    the product's contract (``contract_methods: ["inspect_schema", "preview"]``)
    did not. Eight values across the four adapters were derived from the raw DSN.
    """
    return redacted_source_system(source_system).removeprefix("sparql://")


def _manifest_path(source_system: str) -> str:
    """The object-store manifest path, derived from the **redacted** locator.

    Same defect as :func:`_named_graph`: an ``s3://`` DSN can carry an access
    key id and its secret in the userinfo component.
    """
    return f"{redacted_source_system(source_system).rstrip('/')}/_manifest.json"


class DemoSQLConnector(SourceConnector):
    connector_id = "sql_connector"
    source_type = "warehouse_or_rdbms"

    def inspect_schema(self, dataset_id: str) -> dict[str, Any]:
        dataset = get_dataset(dataset_id)
        if not dataset:
            raise KeyError(dataset_id)
        if not dataset.source_system.startswith("postgresql://"):
            raise ValueError("dataset is not backed by the demo SQL connector")
        return {
            "dataset_id": dataset.id,
            "source_system": redacted_source_system(dataset.source_system),
            "columns": [column.model_dump() for column in dataset.schema],
        }

    def preview(self, dataset_id: str, *, limit: int, offset: int) -> list[dict[str, Any]]:
        from .browse import preview

        result = preview(dataset_id, user="analyst", purpose="analysis", limit=limit, offset=offset)
        return result["rows"]


class DemoRDFConnector(SourceConnector):
    connector_id = "rdf_connector"
    source_type = "semantic_store"

    def inspect_schema(self, dataset_id: str) -> dict[str, Any]:
        dataset = get_dataset(dataset_id)
        if not dataset:
            raise KeyError(dataset_id)
        if not dataset.source_system.startswith("sparql://"):
            raise ValueError("dataset is not backed by the demo RDF connector")
        return {
            "dataset_id": dataset.id,
            "source_system": redacted_source_system(dataset.source_system),
            "named_graph": _named_graph(dataset.source_system),
            "columns": [column.model_dump() for column in dataset.schema],
        }

    def preview(self, dataset_id: str, *, limit: int, offset: int) -> list[dict[str, Any]]:
        from .catalog import ingest_event
        from .policy import evaluate

        dataset = get_dataset(dataset_id)
        if not dataset:
            raise KeyError(dataset_id)
        if not dataset.source_system.startswith("sparql://"):
            raise ValueError("dataset is not backed by the demo RDF connector")

        decision = evaluate(subject="analyst", resource=dataset_id, action="preview", purpose="analysis")
        if decision.effect != "allow":
            ingest_event(
                event_type="connector.rdf.preview",
                actor="analyst",
                dataset_id=dataset_id,
                decision="denied",
                decision_id=decision.decision_id,
                reason=decision.reason,
                details={"policy_decision_id": decision.decision_id},
            )
            raise PermissionError(decision.reason)

        rows = [
            {
                "concept_uri": "https://semantic-data-portal.local/concepts/customer",
                "preferred_label": "고객",
                "broader_concept": "https://semantic-data-portal.local/concepts/party",
            },
            {
                "concept_uri": "https://semantic-data-portal.local/concepts/active-customer",
                "preferred_label": "활성 고객",
                "broader_concept": "https://semantic-data-portal.local/concepts/customer",
            },
            {
                "concept_uri": "https://semantic-data-portal.local/concepts/churn",
                "preferred_label": "이탈",
                "broader_concept": "https://semantic-data-portal.local/concepts/customer",
            },
        ]
        selected = rows[offset : offset + limit]
        ingest_event(
            event_type="connector.rdf.preview",
            actor="analyst",
            dataset_id=dataset_id,
            decision="allowed",
            decision_id=decision.decision_id,
            reason="ok",
            details={
                "policy_decision_id": decision.decision_id,
                "requested_offset": offset,
                "requested_limit": limit,
                "returned_rows": len(selected),
                "named_graph": _named_graph(dataset.source_system),
            },
        )
        return selected


class DemoFileLakeConnector(SourceConnector):
    connector_id = "file_lake_connector"
    source_type = "object_storage_or_lakehouse"

    def inspect_schema(self, dataset_id: str) -> dict[str, Any]:
        dataset = get_dataset(dataset_id)
        if not dataset:
            raise KeyError(dataset_id)
        if not dataset.source_system.startswith("s3://"):
            raise ValueError("dataset is not backed by the demo file lake connector")
        return {
            "dataset_id": dataset.id,
            "source_system": redacted_source_system(dataset.source_system),
            "manifest_path": _manifest_path(dataset.source_system),
            "columns": [column.model_dump() for column in dataset.schema],
        }

    def preview(self, dataset_id: str, *, limit: int, offset: int) -> list[dict[str, Any]]:
        from .catalog import ingest_event
        from .policy import evaluate

        dataset = get_dataset(dataset_id)
        if not dataset:
            raise KeyError(dataset_id)
        if not dataset.source_system.startswith("s3://"):
            raise ValueError("dataset is not backed by the demo file lake connector")

        decision = evaluate(subject="analyst", resource=dataset_id, action="preview", purpose="analysis")
        if decision.effect != "allow":
            ingest_event(
                event_type="connector.file_lake.preview",
                actor="analyst",
                dataset_id=dataset_id,
                decision="denied",
                decision_id=decision.decision_id,
                reason=decision.reason,
                details={"policy_decision_id": decision.decision_id},
            )
            raise PermissionError(decision.reason)

        rows = [
            {
                "event_id": "evt-1001",
                "customer_id": "C-1001",
                "event_timestamp": "2026-06-20T12:10:00Z",
                "device_id": "dev-88",
            },
            {
                "event_id": "evt-1002",
                "customer_id": "C-1002",
                "event_timestamp": "2026-06-21T09:11:00Z",
                "device_id": "dev-01",
            },
        ]
        selected = rows[offset : offset + limit]
        ingest_event(
            event_type="connector.file_lake.preview",
            actor="analyst",
            dataset_id=dataset_id,
            decision="allowed",
            decision_id=decision.decision_id,
            reason="ok",
            details={
                "policy_decision_id": decision.decision_id,
                "requested_offset": offset,
                "requested_limit": limit,
                "returned_rows": len(selected),
                "sample_budget": limit,
                "manifest_path": _manifest_path(dataset.source_system),
            },
        )
        return selected


class DemoRESTConnector(SourceConnector):
    connector_id = "rest_connector"
    source_type = "governed_api"

    def inspect_schema(self, dataset_id: str) -> dict[str, Any]:
        dataset = get_dataset(dataset_id)
        if not dataset:
            raise KeyError(dataset_id)
        if not dataset.source_system.startswith(("https://", "http://")):
            raise ValueError("dataset is not backed by the demo REST connector")
        return {
            "dataset_id": dataset.id,
            "source_system": redacted_source_system(dataset.source_system),
            "auth_mode": "service_account_reference",
            "columns": [column.model_dump() for column in dataset.schema],
        }

    def preview(self, dataset_id: str, *, limit: int, offset: int) -> list[dict[str, Any]]:
        from .catalog import ingest_event
        from .policy import evaluate

        dataset = get_dataset(dataset_id)
        if not dataset:
            raise KeyError(dataset_id)
        if not dataset.source_system.startswith(("https://", "http://")):
            raise ValueError("dataset is not backed by the demo REST connector")

        decision = evaluate(subject="analyst", resource=dataset_id, action="preview", purpose="analysis")
        if decision.effect != "allow":
            ingest_event(
                event_type="connector.rest.preview",
                actor="analyst",
                dataset_id=dataset_id,
                decision="denied",
                decision_id=decision.decision_id,
                reason=decision.reason,
                details={"policy_decision_id": decision.decision_id},
            )
            raise PermissionError(decision.reason)

        rows = [
            {"campaign_id": "cmp-1001", "target_segment": "active_customers", "channel": "email"},
            {"campaign_id": "cmp-1002", "target_segment": "churn_risk", "channel": "push"},
        ]
        selected = rows[offset : offset + limit]
        ingest_event(
            event_type="connector.rest.preview",
            actor="analyst",
            dataset_id=dataset_id,
            decision="allowed",
            decision_id=decision.decision_id,
            reason="ok",
            details={
                "policy_decision_id": decision.decision_id,
                "requested_offset": offset,
                "requested_limit": limit,
                "returned_rows": len(selected),
                "auth_mode": "service_account_reference",
            },
        )
        return selected


_SOURCE_CONNECTORS: dict[str, SourceConnector] = {
    "sql_connector": DemoSQLConnector(),
    "rdf_connector": DemoRDFConnector(),
    "file_lake_connector": DemoFileLakeConnector(),
    "rest_connector": DemoRESTConnector(),
}


def get_source_connector(connector_id: str) -> SourceConnector:
    connector = _SOURCE_CONNECTORS.get(connector_id)
    if not connector:
        raise ValueError(f"unsupported connector id: {connector_id}")
    return connector


def connector_probe(connector_id: str, dataset_id: str) -> dict[str, Any]:
    connectors = {connector.id: connector for connector in connector_registry_manifest()}
    connector = connectors.get(connector_id)
    if not connector:
        raise ValueError(f"unsupported connector id: {connector_id}")

    dataset = get_dataset(dataset_id)
    if not dataset:
        raise KeyError(dataset_id)

    source_adapter = _SOURCE_CONNECTORS.get(connector_id)
    inspected_schema = None
    adapter_status = "planned"
    if source_adapter:
        inspected_schema = source_adapter.inspect_schema(dataset_id)
        adapter_status = "implemented"

    served = _served_route_paths()
    control_evidence = []
    satisfied_controls = 0
    for control in connector.required_controls:
        proof_endpoints = _IMPLEMENTED_PROOF.get(control, [])
        config_proof = _IMPLEMENTED_CONFIG_PROOF.get(control, [])
        missing_routes = [path for path in proof_endpoints if path not in served]
        # A control is implemented when it names at least one proof endpoint and
        # this build serves every endpoint it names. Both halves can be false.
        implemented = bool(proof_endpoints) and not missing_routes
        satisfied = implemented
        verification = (
            VERIFICATION_PROOF_ROUTE if implemented else VERIFICATION_DECLARED
        )
        evidence_payload: dict[str, Any] = {
            "control": control,
            "status": "implemented" if implemented else "planned",
            "proof_endpoints": proof_endpoints,
            "config_proof": config_proof,
            "verification": verification,
        }
        if not proof_endpoints:
            evidence_payload["gap_reason"] = "no proof endpoint is declared for this control"
        elif missing_routes:
            evidence_payload["gap_reason"] = (
                "this build does not serve every declared proof endpoint: "
                + ", ".join(missing_routes)
            )
        runtime_entry = _RUNTIME_CONTROL_CHECKS.get(control)
        if runtime_entry is not None:
            runtime_check, owner = runtime_entry
            evidence_payload["runtime_check_owner"] = owner
            observed, observation, gap_reason = runtime_check(connector_id, dataset_id)
            evidence_payload.update(observation)
            satisfied = implemented and observed
            # These controls' verdicts are backed by a runtime observation of
            # the control's own effect; the rest rest on the route existing.
            evidence_payload["verification"] = (
                VERIFICATION_RUNTIME if satisfied else evidence_payload["verification"]
            )
            if gap_reason:
                evidence_payload["gap_reason"] = gap_reason
        satisfied_controls += int(satisfied)
        control_evidence.append(evidence_payload)

    # The honest shape of the evidence, published rather than left to be inferred
    # from eleven rows that all said "implemented".
    control_verification_counts = {
        level: sum(1 for row in control_evidence if row["verification"] == level)
        for level in (
            VERIFICATION_RUNTIME,
            VERIFICATION_PROOF_ROUTE,
            VERIFICATION_DECLARED,
        )
    }

    ready_for_demo = adapter_status == "implemented" and satisfied_controls == len(connector.required_controls)
    probe = {
        "connector_id": connector.id,
        "dataset_id": dataset.id,
        "source_type": connector.source_type,
        "source_system": redacted_source_system(dataset.source_system),
        "status": "ready_for_demo" if ready_for_demo else "contract_only",
        "contract_methods": ["inspect_schema", "preview"],
        "adapter_status": adapter_status,
        "data_contract": {
            "schema_fields": len(inspected_schema["columns"]) if inspected_schema else len(dataset.schema),
            "sensitivity": dataset.sensitivity,
            "quality_score": dataset.quality_score,
            "freshness_score": dataset.freshness_score,
        },
        "demo_context": buyer_demo_context_for_dataset(dataset.id),
        "control_evidence": control_evidence,
        "control_verification_counts": control_verification_counts,
        # What ``status: ready_for_demo`` does and does not assert. A probe
        # verdict is evidence that the declared controls are wired, not that each
        # one was exercised against this dataset.
        "verdict_basis": (
            "adapter_implemented + every required control's declared proof endpoint "
            "is served by this build + any runtime-verified control passed"
        ),
        "proof": connector.proof,
    }
    # The one chokepoint, placed after the result is built and before it is
    # returned. ``demo_smoke`` calls this function directly four times and
    # twenty-odd tests call it directly too, so a counter hooked at the route
    # would miss every one of them; a counter in the middleware would miss those
    # and also count nothing for a probe that raised. Being here, after the two
    # caller-caused refusals above have already raised, is also what excludes
    # them for free: an unsupported connector id, an unknown dataset id and the
    # 15 of 20 seed pairs whose scheme does not back the dataset never reach it.
    #
    # Imported inside the function on purpose. ``observability`` imports
    # ``sdp.api`` at call time for the latency-budget report and ``sdp.api``
    # imports this module, so a module-level import here is a cycle - the same
    # pattern the served-route check above already uses.
    from .observability import note_connector_probe

    note_connector_probe(
        connector.id,
        connector_probe_failure_reason(probe),
        probe["control_verification_counts"],
    )
    return probe


def connector_probe_failure_reason(probe: dict[str, Any]) -> str:
    """The ``connector_probe_failure`` alert condition, as a function of one probe.

    Returns the reason an operator should be paged, or ``""`` when this outcome
    is not one. The three reasons are the parts of the probe's own
    ``verdict_basis`` that the **build** owns, and none is caller-controlled or
    configuration:

    * the connector registry declares an adapter this build does not implement
      (``adapter_status`` is not ``implemented``);
    * a required control's declared proof endpoint is not served by this build,
      which is what leaves its row at ``VERIFICATION_DECLARED``;
    * a **build-owned** runtime-verified control's own effect stopped holding,
      which leaves its row short of ``VERIFICATION_RUNTIME``.

    The third was missing, and it was the one that matters most: it is the only
    conjunct of ``verdict_basis`` whose *effect* is measured rather than
    inferred from a route existing. ``verdict_basis`` has three conjuncts and
    this function keyed on two. Measured with the pin comparison broken at
    source - which ``_verify_ontology_version_pin``'s own docstring says stops
    the control claiming to be implemented - the ``rdf_connector`` probe
    degraded to ``contract_only`` and carried a ``gap_reason``, while the row's
    ``verification`` stayed ``proof_route_served`` (the route *is* served), so
    this function returned ``""``, the critical rule reported
    ``observed_total: 0, firing: False`` and ``sdp_connector_probe_failures_total``
    stayed 0 on a genuine build defect. Three published surfaces asserted the
    opposite coverage. ``python -m sdp.demo_smoke`` did fail, because its ready
    gate asserts ``status == "ready_for_demo"`` for that pair - so the blast
    radius was reduced, not removed, and the runtime alert and the gauge were
    still wrong.

    ``credential_vault`` is the other runtime-verified control and stays
    excluded: its outcome is an operator's ``SDP_CONNECTOR_SECRET_*``
    configuration, so paging on it would page on the demo image as shipped. The
    ownership is declared once, in ``_RUNTIME_CONTROL_CHECKS``, and both the
    exclusion and this clause are derived from it.

    Deliberately **not** keyed on ``probe["status"]`` or on the presence of a
    ``gap_reason``. Measured over the seed catalogue, the one ``contract_only``
    pair - ``rest_connector``/``marketing-campaign`` - carries a ``gap_reason``
    on its ``credential_vault`` row because the optional
    ``SDP_CONNECTOR_SECRET_REST_CONNECTOR_MARKETING_CAMPAIGN_TOKEN`` is unset,
    while that row's ``verification`` stays ``proof_route_served``. Setting the
    one variable flips the pair to ``ready_for_demo``, and ``demo_smoke`` asserts
    ``adapter_status == "implemented"`` rather than ``status == "ready_for_demo"``
    and reports ``ready: True`` with the pair exactly as shipped. So a condition
    reading either of those fields fires on the demo image, which is the
    standing complaint this repository treats as a defect in its own words.

    Measured, both reasons are zero across all 20 seed pairs: ``adapter_status``
    is ``implemented`` for all four connectors and ``declared_only`` is 0 in
    every pair's ``control_verification_counts``.
    """
    if probe["adapter_status"] != "implemented":
        return (
            "the connector registry declares "
            f"{probe['connector_id']} but this build implements no adapter for it"
        )
    unserved = [
        row["control"]
        for row in probe["control_evidence"]
        if row["verification"] == VERIFICATION_DECLARED
    ]
    if unserved:
        return (
            "this build does not serve the declared proof endpoint of: "
            + ", ".join(sorted(unserved))
        )
    unverified = [
        row["control"]
        for row in probe["control_evidence"]
        if row["control"] in BUILD_OWNED_RUNTIME_CONTROLS
        and row["verification"] != VERIFICATION_RUNTIME
    ]
    if unverified:
        return (
            "a build-owned control's own effect did not hold at runtime: "
            + ", ".join(sorted(unverified))
        )
    return ""
