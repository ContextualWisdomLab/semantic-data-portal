"""Source-connector contract guards.

Each demo connector must reject an unknown dataset (KeyError), a dataset backed
by the wrong source scheme (ValueError), and — on the preview path — a policy
denial (PermissionError, audited). These pin those guards so a connector cannot
silently inspect/preview data it should refuse. Preview records policy + audit
evidence, so the in-memory stores are snapshot/restored.
"""

from __future__ import annotations

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sdp import catalog, connectors, evidence  # noqa: E402

# connector id -> a source_system scheme it accepts
_ACCEPTS = {
    "sql_connector": "postgresql://analytics.dw/customer",
    "rdf_connector": "sparql://graph/customer",
    "file_lake_connector": "s3://bucket/customer/",
    "rest_connector": "https://api.example/customer",
}
# a scheme every connector rejects (mismatch)
_WRONG = "ftp://elsewhere/x"


@pytest.fixture(autouse=True)
def _isolate_state():
    data = {k: v.model_copy(deep=True) for k, v in catalog._DATA.items()}
    audit = list(catalog._AUDIT_LOG)
    decisions = list(evidence._POLICY_DECISION_LOG)
    try:
        yield
    finally:
        catalog._DATA.clear()
        catalog._DATA.update(data)
        catalog._AUDIT_LOG.clear()
        catalog._AUDIT_LOG.extend(audit)
        evidence._POLICY_DECISION_LOG.clear()
        evidence._POLICY_DECISION_LOG.extend(decisions)


def _seed(ds_id: str, *, source_system: str, sensitivity: str = "medium"):
    base = catalog._DATA["crm-customer-master"]
    catalog._DATA[ds_id] = base.model_copy(
        update={"id": ds_id, "source_system": source_system, "sensitivity": sensitivity}
    )


def test_get_source_connector_rejects_unknown_id() -> None:
    with pytest.raises(ValueError):
        connectors.get_source_connector("no_such_connector")


@pytest.mark.parametrize("connector_id", list(_ACCEPTS))
def test_inspect_schema_missing_dataset_raises_keyerror(connector_id: str) -> None:
    conn = connectors.get_source_connector(connector_id)
    with pytest.raises(KeyError):
        conn.inspect_schema("__no_such_dataset__")


@pytest.mark.parametrize("connector_id", list(_ACCEPTS))
def test_inspect_schema_wrong_scheme_raises_valueerror(connector_id: str) -> None:
    _seed("wrong-scheme-ds", source_system=_WRONG)
    conn = connectors.get_source_connector(connector_id)
    with pytest.raises(ValueError):
        conn.inspect_schema("wrong-scheme-ds")


@pytest.mark.parametrize("connector_id", list(_ACCEPTS))
def test_inspect_schema_accepts_matching_scheme(connector_id: str) -> None:
    _seed("ok-ds", source_system=_ACCEPTS[connector_id])
    conn = connectors.get_source_connector(connector_id)
    result = conn.inspect_schema("ok-ds")
    assert result["dataset_id"] == "ok-ds"


@pytest.mark.parametrize("connector_id", ["rdf_connector", "file_lake_connector", "rest_connector"])
def test_preview_policy_denied_raises_permission_error(connector_id: str) -> None:
    """A critical-sensitivity dataset denies the connector's hardcoded 'analyst'
    subject, so preview raises PermissionError and audits the denial."""
    _seed("deny-ds", source_system=_ACCEPTS[connector_id], sensitivity="critical")
    conn = connectors.get_source_connector(connector_id)
    before = len(catalog._AUDIT_LOG)
    with pytest.raises(PermissionError):
        conn.preview("deny-ds", limit=10, offset=0)
    assert len(catalog._AUDIT_LOG) == before + 1  # the denial is audited


@pytest.mark.parametrize("connector_id", ["rdf_connector", "file_lake_connector", "rest_connector"])
def test_preview_missing_dataset_raises_keyerror(connector_id: str) -> None:
    conn = connectors.get_source_connector(connector_id)
    with pytest.raises(KeyError):
        conn.preview("__no_such_dataset__", limit=10, offset=0)


@pytest.mark.parametrize("connector_id", ["rdf_connector", "file_lake_connector", "rest_connector"])
def test_preview_wrong_scheme_raises_valueerror(connector_id: str) -> None:
    """preview refuses a dataset backed by the wrong source scheme."""
    _seed("wrong-scheme-preview", source_system=_WRONG)
    conn = connectors.get_source_connector(connector_id)
    with pytest.raises(ValueError):
        conn.preview("wrong-scheme-preview", limit=10, offset=0)
