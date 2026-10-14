"""A connector probe's control verdicts were a dictionary-membership tautology.

``implemented`` was ``bool(_IMPLEMENTED_PROOF.get(control, []))``, so the
question "is this control implemented?" was answered by "is this control's name
a key in a hand-written dict twenty lines earlier in the same file?". Measured
before the repair, enumerated over every valid (connector, dataset) pair - all
four connectors, all eleven required controls::

    controls required by any connector        11
    controls present in _IMPLEMENTED_PROOF    11
    control evidence rows reporting "planned"  0

``planned`` was unreachable. The single thing in the matrix that could move a
verdict was ``credential_vault``'s secret-presence check, which is why
``rest_connector``/``marketing-campaign`` was the only ``contract_only`` pair:
the one control doing measurement was carrying all the information, and the
other ten rows said "implemented" on the strength of having been typed into a
dict. A procurement reader counting eleven implemented controls was counting
eleven assertions.

The repair does not pretend to verify each control's effect - that is a real
project, not a defect fix. It makes the claim falsifiable and says how strong it
is: a control is implemented when this build actually serves every proof
endpoint the control names, and each row publishes its ``verification`` level
(``declared_only`` / ``proof_route_served`` / ``runtime_probe_verified``) with
the counts summarised on the probe. The honest headline that falls out is that
**zero** controls in the demo matrix are runtime-verified, because the only
control with a runtime check is required by one connector whose secret is not
configured.
"""

from __future__ import annotations

import os
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sdp import connectors  # noqa: E402
from sdp.api import app  # noqa: E402
from sdp.connectors import connector_probe  # noqa: E402
from sdp.credentials import connector_secret_ref  # noqa: E402
from sdp_core import connector_registry_manifest  # noqa: E402


# The pairs that exist: each demo adapter is backed by the seeded datasets whose
# source system it owns and raises for the rest, so the matrix is five pairs, not
# twenty. ``test_the_valid_pairs_are_the_whole_matrix`` derives the list from the
# code and compares - it caught this being written as four, which is the point of
# pinning it rather than trusting a hand-copied list.
VALID_PAIRS = [
    ("sql_connector", "crm-customer-master"),
    ("sql_connector", "sales-order"),
    ("rdf_connector", "semantic-glossary"),
    ("file_lake_connector", "crm-event"),
    ("rest_connector", "marketing-campaign"),
]


def test_the_valid_pairs_are_the_whole_matrix() -> None:
    """Pinned, so the enumeration below cannot silently cover less than it claims."""
    from sdp import catalog

    found = []
    for connector in connector_registry_manifest():
        for dataset in catalog.list_datasets():
            try:
                connector_probe(connector.id, dataset.id)
            except ValueError:
                continue
            found.append((connector.id, dataset.id))
    assert sorted(found) == sorted(VALID_PAIRS), found


@pytest.mark.parametrize("connector_id,dataset_id", VALID_PAIRS)
def test_every_control_row_declares_how_strong_its_evidence_is(
    connector_id: str, dataset_id: str
) -> None:
    probe = connector_probe(connector_id, dataset_id)
    levels = {
        connectors.VERIFICATION_DECLARED,
        connectors.VERIFICATION_PROOF_ROUTE,
        connectors.VERIFICATION_RUNTIME,
    }
    assert probe["control_evidence"], probe
    for row in probe["control_evidence"]:
        assert row["verification"] in levels, row
        # A row that is not implemented must say why, or the gap is invisible.
        if row["status"] != "implemented":
            assert row.get("gap_reason"), row

    counts = probe["control_verification_counts"]
    assert set(counts) == levels
    assert sum(counts.values()) == len(probe["control_evidence"])


def test_a_control_verdict_can_be_false() -> None:
    """The property the tautology denied: ``planned`` must be reachable.

    Pointing a control's proof at a route this build does not serve is the
    cheapest way to exercise it, and it is also the real failure mode - a route
    renamed or removed while the proof list keeps naming the old path.
    """
    saved = dict(connectors._IMPLEMENTED_PROOF)
    connectors._IMPLEMENTED_PROOF["audit_event"] = ["/this/route/does/not/exist"]
    try:
        probe = connector_probe("sql_connector", "crm-customer-master")
        row = next(
            item for item in probe["control_evidence"] if item["control"] == "audit_event"
        )
        assert row["status"] == "planned", row
        assert row["verification"] == connectors.VERIFICATION_DECLARED
        assert "/this/route/does/not/exist" in row["gap_reason"]
        # And the probe verdict follows, rather than staying ready_for_demo.
        assert probe["status"] == "contract_only"
    finally:
        connectors._IMPLEMENTED_PROOF.clear()
        connectors._IMPLEMENTED_PROOF.update(saved)

    assert connector_probe("sql_connector", "crm-customer-master")["status"] == "ready_for_demo"


def test_a_control_with_no_declared_proof_is_planned() -> None:
    """The other half of the condition."""
    saved = dict(connectors._IMPLEMENTED_PROOF)
    connectors._IMPLEMENTED_PROOF["audit_event"] = []
    try:
        row = next(
            item
            for item in connector_probe("sql_connector", "crm-customer-master")[
                "control_evidence"
            ]
            if item["control"] == "audit_event"
        )
        assert row["status"] == "planned"
        assert "no proof endpoint is declared" in row["gap_reason"]
    finally:
        connectors._IMPLEMENTED_PROOF.clear()
        connectors._IMPLEMENTED_PROOF.update(saved)


def test_every_declared_proof_endpoint_is_a_route_this_build_serves() -> None:
    """Enumerated over the whole proof map, not one control.

    This is the check the verdict now rests on, asserted directly so a stale
    proof path is a test failure rather than a quietly downgraded control.
    """
    served = {
        route.path for route in app.routes if isinstance(getattr(route, "path", None), str)
    }
    missing = {
        control: [path for path in paths if path not in served]
        for control, paths in connectors._IMPLEMENTED_PROOF.items()
        if any(path not in served for path in paths)
    }
    assert not missing, f"these controls name proof endpoints this build does not serve: {missing}"


def test_no_proof_endpoint_entry_is_something_other_than_an_endpoint() -> None:
    """``credential_vault`` listed an environment variable name among "endpoints".

    A reader following the list found one entry that is not a URL and no field
    saying what it was. Configuration proof is a real kind of proof; it now has
    its own field.
    """
    for control, paths in connectors._IMPLEMENTED_PROOF.items():
        for path in paths:
            assert path.startswith("/"), (control, path)

    row = next(
        item
        for item in connector_probe("rest_connector", "marketing-campaign")[
            "control_evidence"
        ]
        if item["control"] == "credential_vault"
    )
    assert row["config_proof"] == ["SDP_CONNECTOR_SECRET_REF_PREFIX"]
    assert "SDP_CONNECTOR_SECRET_REF_PREFIX" not in row["proof_endpoints"]


def test_only_a_control_with_a_runtime_check_claims_runtime_verification() -> None:
    """And the honest headline: zero of them do, in the default demo deployment.

    ``credential_vault`` is the only control whose effect is observed at probe
    time, and it is required by one connector whose secret reference is not
    configured - so no control in the whole matrix reaches
    ``runtime_probe_verified`` without an operator action. Published rather than
    left to be inferred from rows that all said "implemented".
    """
    for connector_id, dataset_id in VALID_PAIRS:
        probe = connector_probe(connector_id, dataset_id)
        assert probe["control_verification_counts"][connectors.VERIFICATION_RUNTIME] == 0
        for row in probe["control_evidence"]:
            if row["verification"] == connectors.VERIFICATION_RUNTIME:
                assert row["control"] in connectors._RUNTIME_VERIFIED_CONTROLS, row


def test_configuring_the_secret_reaches_runtime_verification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The level is reachable, so its absence above is a measurement not a dead branch."""
    reference = connector_secret_ref("rest_connector", "marketing-campaign")
    monkeypatch.setenv(reference, "configured-for-this-probe")
    probe = connector_probe("rest_connector", "marketing-campaign")
    assert probe["status"] == "ready_for_demo"
    assert probe["control_verification_counts"][connectors.VERIFICATION_RUNTIME] == 1
    row = next(
        item for item in probe["control_evidence"] if item["control"] == "credential_vault"
    )
    assert row["verification"] == connectors.VERIFICATION_RUNTIME
    assert "gap_reason" not in row


def test_the_probe_says_what_its_verdict_asserts() -> None:
    """``ready_for_demo`` reads as "every control was exercised". It is not that."""
    probe = connector_probe("sql_connector", "crm-customer-master")
    basis = probe["verdict_basis"]
    assert "declared proof endpoint" in basis
    assert "is served by this build" in basis
    assert "runtime-verified control" in basis


def test_no_secret_value_reaches_the_probe_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    """The pre-existing contract, re-asserted against the new fields."""
    reference = connector_secret_ref("rest_connector", "marketing-campaign")
    monkeypatch.setenv(reference, "super-secret-token-value")
    probe = connector_probe("rest_connector", "marketing-campaign")
    assert "super-secret-token-value" not in str(probe)
    assert os.environ[reference] == "super-secret-token-value"
