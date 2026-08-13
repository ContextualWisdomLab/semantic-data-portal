"""Connector-secret status: env-vault presence + unsupported-provider guard.

connector_secret_status resolves whether a connector's secret reference is
present (never exposing the value) and rejects any non-env vault provider. These
pin the presence signal and the fail-loud guard.
"""

from __future__ import annotations

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sdp import credentials as cred  # noqa: E402


def test_connector_secret_ref_format_and_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SDP_CONNECTOR_SECRET_REF_PREFIX", raising=False)
    ref = cred.connector_secret_ref("sql_connector", "crm-customer-master")
    assert ref == "SDP_CONNECTOR_SECRET_SQL_CONNECTOR_CRM_CUSTOMER_MASTER_TOKEN"
    monkeypatch.setenv("SDP_CONNECTOR_SECRET_REF_PREFIX", "X_")
    assert cred.connector_secret_ref("a", "b").startswith("X_")


def test_secret_status_reports_presence_without_exposing_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SDP_CONNECTOR_VAULT_PROVIDER", "env")
    ref = cred.connector_secret_ref("sql_connector", "crm-customer-master")
    raw_secret_value = "super-secret-value"

    monkeypatch.delenv(ref, raising=False)
    absent = cred.connector_secret_status("sql_connector", "crm-customer-master")
    absent_public = absent.public_dict()
    assert absent.secret_present is False
    assert raw_secret_value not in str(absent_public)

    monkeypatch.setenv(ref, raw_secret_value)
    present = cred.connector_secret_status("sql_connector", "crm-customer-master")
    assert present.secret_present is True
    # The raw secret value is never surfaced in the public dict.
    assert raw_secret_value not in str(present.public_dict())


def test_unsupported_vault_provider_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SDP_CONNECTOR_VAULT_PROVIDER", "hashicorp")
    with pytest.raises(ValueError):
        cred.connector_secret_status("sql_connector", "crm-customer-master")
