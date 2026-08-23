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
