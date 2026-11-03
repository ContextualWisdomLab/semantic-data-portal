"""Two manifests told an operator something the product does not do.

**1. ``configured_integrations`` contradicted its own payload.**
``src/sdp_core/production.py`` builds it from ``missing_environment`` alone,
while two lines above it computes ``unconfigured = missing | rejected`` under the
comment "An integration configured with a value the code refuses is not
configured. Counting it as ready because the name is present is the defect this
split exists to close." Measured at ``2f64f55`` with the vault's two
rule-bearing variables set to values the code refuses::

    SDP_CONNECTOR_SECRET_REF_PREFIX = SDP_CONNECTOR_SECRET_
    SDP_CONNECTOR_VAULT_PROVIDER    = hashicorp     (allowed: env)
    SDP_CONNECTOR_TIMEOUT_MS        = 0            (required: integer >= 1)

    rejected_environment      {'connector_credential_vault': {
                                 'SDP_CONNECTOR_VAULT_PROVIDER': 'must be one of: env',
                                 'SDP_CONNECTOR_TIMEOUT_MS': 'must be an integer >= 1'}}
    missing_environment       {}
    configured_integrations   ['connector_credential_vault']      <- published as configured
    unconfigured_integrations ['connector_credential_vault', …]   <- and as unconfigured
    paid_pilot_blockers       includes connector_credential_vault

One response says the vault is configured and, twice over, that it is not.

**2. ``/enterprise/observability`` points monitoring at a probe that cannot see
the evidence store.** ``probe_semantics["/healthz"]`` reads "readiness; reports
**the active store** and answers 503 when the backend is unreachable. Wire
monitoring here." ``/healthz``'s own docstring is narrower and honest -
"Readiness probe verifying **graph-engine** backend availability" - and it
consults ``get_store()`` only. Measured with ``SDP_SQLITE_PATH`` set, so the
evidence ledger is on SQLite::

    GET /healthz -> {"ready": true, "backend": "in_memory", "database": false, …}
    the word "evidence" appears nowhere in the payload

So an operator reading "reports the active store" sees ``in_memory`` while the
ledger that carries this product's auditability claim is on SQLite, and the 503
promise covers one of the two stores that matter.
"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from sdp.api import app
from sdp_core.production import enterprise_production_readiness_manifest


client = TestClient(app)

REFUSED_VAULT_ENVIRONMENT = {
    "SDP_CONNECTOR_SECRET_REF_PREFIX": "SDP_CONNECTOR_SECRET_",
    "SDP_CONNECTOR_VAULT_PROVIDER": "hashicorp",
    "SDP_CONNECTOR_TIMEOUT_MS": "0",
}


def test_an_integration_is_never_both_configured_and_unconfigured() -> None:
    """The two lists partition; the payload cannot assert both of one id."""
    manifest = enterprise_production_readiness_manifest(REFUSED_VAULT_ENVIRONMENT)
    overlap = sorted(
        set(manifest.configured_integrations) & set(manifest.unconfigured_integrations)
    )
    assert not overlap, f"published as configured and unconfigured at once: {overlap}"


def test_a_refused_value_leaves_the_integration_unconfigured() -> None:
    """The rule the comment states, applied to the field beside it."""
    manifest = enterprise_production_readiness_manifest(REFUSED_VAULT_ENVIRONMENT)
    assert "connector_credential_vault" in manifest.rejected_environment, manifest
    assert "connector_credential_vault" not in manifest.configured_integrations, (
        manifest.configured_integrations
    )
    assert "connector_credential_vault" in manifest.paid_pilot_blockers, manifest


def test_a_fully_accepted_value_is_still_configured() -> None:
    """The repair must not call everything unconfigured."""
    accepted = {
        **REFUSED_VAULT_ENVIRONMENT,
        "SDP_CONNECTOR_VAULT_PROVIDER": "env",
        "SDP_CONNECTOR_TIMEOUT_MS": "500",
    }
    manifest = enterprise_production_readiness_manifest(accepted)
    assert manifest.rejected_environment == {}, manifest.rejected_environment
    assert "connector_credential_vault" in manifest.configured_integrations, manifest


def test_no_integration_is_configured_while_any_of_its_values_is_refused() -> None:
    """Derived over every integration, not only the one with rules today."""
    manifest = enterprise_production_readiness_manifest(REFUSED_VAULT_ENVIRONMENT)
    for integration_id in manifest.rejected_environment:
        assert integration_id not in manifest.configured_integrations, integration_id


def test_the_readiness_probe_claim_names_the_store_it_actually_reads() -> None:
    """``the active store`` read as *the* store; the product has two that matter."""
    semantics = client.get("/enterprise/observability").json()["probe_semantics"]
    healthz_claim = semantics["/healthz"]
    assert "the active store" not in healthz_claim, healthz_claim
    assert "graph" in healthz_claim, healthz_claim
    assert "evidence" in healthz_claim, healthz_claim


def test_the_probe_payload_really_carries_only_the_graph_store() -> None:
    """The measurement behind the correction, so it cannot drift silently."""
    payload = client.get("/healthz").json()
    assert "store" in payload, sorted(payload)
    assert "backend" in payload["store"], payload["store"]
    assert "evidence" not in json.dumps(payload, ensure_ascii=False).lower(), payload


def test_the_identity_names_each_backend_the_selector_can_choose() -> None:
    """All three branches, driven through the module's own swap seam.

    The first version of this file asserted only that ``selected_by`` was one of
    the three, and the test environment configures none - so a mutation that
    collapsed the Postgres branch came back **green**. The branch a test cannot
    reach is the branch that breaks in the deployment that uses it.
    """
    from sdp import evidence
    from sdp.observability import _evidence_store_identity
    from sdp_core import PostgresEvidenceStore, SQLiteEvidenceStore

    cases = [
        (None, "process_memory_fallback", "in_memory_bounded_lists"),
        (
            SQLiteEvidenceStore(str(tmp_sqlite_path())),
            "SDP_SQLITE_PATH",
            "sqlite",
        ),
        (
            PostgresEvidenceStore.__new__(PostgresEvidenceStore),
            "SDP_DATABASE_URL",
            "postgres",
        ),
    ]
    previous = evidence.configure_evidence_store(None)
    try:
        for store, selected_by, backend in cases:
            evidence.configure_evidence_store(store)
            identity = _evidence_store_identity()
            assert identity["selected_by"] == selected_by, identity
            assert identity["backend"] == backend, identity
            assert identity["readiness_probe_covers_it"] is False, identity
    finally:
        evidence.configure_evidence_store(previous)


def tmp_sqlite_path():
    """A throwaway path for the SQLite branch of the identity test."""
    import tempfile
    from pathlib import Path

    return Path(tempfile.mkdtemp(prefix="sdp-evidence-identity-")) / "ev.sqlite3"


def test_the_manifest_publishes_which_evidence_store_is_active() -> None:
    """What the operator needed and the probe cannot give them."""
    observability = client.get("/enterprise/observability").json()
    store = observability["evidence_store"]
    assert store["selected_by"] in {
        "SDP_DATABASE_URL",
        "SDP_SQLITE_PATH",
        "process_memory_fallback",
    }, store
    assert "readiness_probe_covers_it" in store, store
    assert store["readiness_probe_covers_it"] is False, store
