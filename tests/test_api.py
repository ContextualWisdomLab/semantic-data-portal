import json
from copy import deepcopy
from pathlib import Path
from time import time

import jwt
import pytest
from fastapi.testclient import TestClient
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

import sdp.catalog as app_catalog
import sdp.domain as app_domain
import sdp.evidence as app_evidence
import sdp.observability as app_observability
import sdp_core
from sdp.api import app
from sdp.connectors import get_source_connector
from sdp.demo_smoke import smoke_summary
from sdp.policy import evaluate


client = TestClient(app)


@pytest.fixture(autouse=True)
def isolate_in_memory_app_state():
    data = {dataset_id: dataset.model_copy(deep=True) for dataset_id, dataset in app_catalog._DATA.items()}
    audit_log = list(app_catalog._AUDIT_LOG)
    schema_history = deepcopy(app_catalog._SCHEMA_HISTORY)
    policy_log = list(app_evidence._POLICY_DECISION_LOG)
    request_observations = app_observability.list_request_observations()
    export_errors = app_observability.list_observability_export_errors()
    yield
    app_catalog._DATA.clear()
    app_catalog._DATA.update(data)
    app_catalog._AUDIT_LOG[:] = audit_log
    app_catalog._SCHEMA_HISTORY.clear()
    app_catalog._SCHEMA_HISTORY.update(schema_history)
    app_evidence._POLICY_DECISION_LOG[:] = policy_log
    app_observability.reset_request_observability()
    for observation in request_observations:
        app_observability.record_request_observation(observation, export=False)
    for error in export_errors:
        app_observability.record_observability_export_error(error)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_enterprise_readiness_manifest_exposes_saleable_gates():
    response = client.get("/enterprise/readiness")
    assert response.status_code == 200

    body = response.json()
    assert body["valuation_target_krw"] == 2_000_000_000
    assert body["submodule_decision"]["decision"] == "monorepo_package_split_first"

    packages = {package["id"]: package for package in body["package_boundary"]}
    assert packages["sdp_core"]["kind"] == "library"
    assert "store protocols" in packages["sdp_core"]["owns"]
    assert packages["sdp_app"]["kind"] == "application"

    stores = {store["id"]: store for store in body["storage_capabilities"]}
    assert stores["audit_events"]["durability_required"] is True
    assert stores["policy_decisions"]["scale_gate"].startswith("100 percent")

    connectors = {connector["id"]: connector for connector in body["connector_capabilities"]}
    assert {"sql_connector", "rdf_connector", "rest_connector", "file_lake_connector"} <= set(connectors)
    assert "policy_before_query" in connectors["sql_connector"]["required_controls"]

    gates = {gate["id"]: gate for gate in body["enterprise_gates"]}
    assert gates["policy_audit_coverage"]["status"] == "implemented"
    assert gates["operational_due_diligence"]["status"] == "external"
    assert any(artifact["code_connect"] == "disabled" for artifact in body["design_artifacts"])
    artifacts = {artifact["id"]: artifact for artifact in body["design_artifacts"]}
    assert artifacts["operator_console_design_capture"]["url"].startswith("https://www.figma.com/design/")
    assert "node-id=3-2" in artifacts["operator_console_design_capture"]["url"]
    assert artifacts["operator_console_design_capture"]["code_connect"] == "disabled"


def test_enterprise_demo_plan_supports_buyer_activation_path():
    response = client.get(
        "/enterprise/demo-plan",
        params={"domain": "insurance claims", "connector": ["sql_connector", "rest_connector"]},
    )
    assert response.status_code == 200

    body = response.json()
    assert body["priority_domain"] == "insurance claims"
    assert body["activation_days"] == 10
    assert [connector["id"] for connector in body["selected_connectors"]] == ["sql_connector", "rest_connector"]
    assert any(step["id"] == "governed_browse_query" for step in body["workflow"])
    assert any("/enterprise/demo-plan" in artifact for artifact in body["handoff_artifacts"])
    assert any("policy_decision_id" in criterion for criterion in body["acceptance_criteria"])
