"""The documented readiness command must diagnose a misconfiguration, not raise on it.

``PYTHONPATH=src python -m sdp.demo_smoke`` is how ``README.md`` and
``sdp_core.enterprise`` tell an operator to ask whether a deployment is ready, and its contract is
an exit code plus a JSON report. ``smoke_summary`` probes four connectors directly, and
``connector_probe`` reaches ``credentials.connector_secret_status``, which refuses a vault provider
it does not implement and a timeout that is not a positive integer. Measured on the head before
this change:

    SDP_CONNECTOR_TIMEOUT_MS=2s         exit 1, NO JSON, ValueError traceback
    SDP_CONNECTOR_VAULT_PROVIDER=vault  exit 1, NO JSON, ValueError traceback
    SDP_CONNECTOR_TIMEOUT_MS=0          exit 0, JSON, "ready": true

The exit code was right for the first two and the report - the half that tells an operator *what*
to fix - was missing. The third was worse: it answered ready while the rest connector's control
evidence published ``timeout_ms: 0``, and it is refused at the point of use now, which is what
brought all three to the same place.

So the two halves are asserted separately here. A report must exist, and it must name the variable;
and the exit code must still be 1, because a readiness command that diagnoses a problem and exits 0
is worse than one that crashes.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sdp import demo_smoke  # noqa: E402


# The three misconfigurations, with the text each must put in front of an operator. Only the rest
# connector declares ``credential_vault`` in its required controls, so it is the pair that reports -
# the other three probe the vault not at all, which ``docs/product-technical-gap-baseline.md``
# records as a deliberate boundary rather than an oversight.
# The expected fragment is the remedy, not the rejected value. Written against the message as it
# first came back, this parametrisation asserted that each entry names its variable - and the
# provider refusal did not: it read "unsupported connector vault provider: vault" and left the
# operator to work out which setting held it. The message names the variable now, and since this
# report is the whole of what an operator sees, the assertion is kept as the thing that required it.
MISCONFIGURATIONS = (
    ("SDP_CONNECTOR_TIMEOUT_MS", "2s", "must be an integer number of milliseconds"),
    ("SDP_CONNECTOR_TIMEOUT_MS", "0", "must be at least 1 millisecond"),
    ("SDP_CONNECTOR_VAULT_PROVIDER", "vault", "only 'env' is implemented"),
)


@pytest.mark.parametrize("variable,value,expected", MISCONFIGURATIONS)
def test_a_misconfigured_connector_is_reported_rather_than_raised(
    variable: str, value: str, expected: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A report must come back, and it must name the variable and the problem."""
    monkeypatch.setenv(variable, value)

    summary = demo_smoke.smoke_summary()

    assert summary["ready"] is False
    errors = summary["connector_configuration_errors"]
    assert errors, "the misconfiguration produced no diagnosis"
    assert any(variable in entry for entry in errors), errors
    assert any(expected in entry for entry in errors), errors
    # The probe fields degrade to null rather than disappearing, so a reader parsing the report
    # does not have to branch on whether a key exists.
    assert "rest_connector_probe_status" in summary
    assert summary["rest_connector_probe_status"] is None


def test_the_command_still_exits_one_and_still_prints_the_report(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Both halves of the contract, through ``main`` rather than the helper.

    ``main`` is what the documented command runs. Asserting on ``smoke_summary`` alone would leave
    the exit code and the printing unmeasured, and the exit code is the half the previous behaviour
    got right - losing it while fixing the report would be a trade, not a repair.
    """
    monkeypatch.setenv("SDP_CONNECTOR_VAULT_PROVIDER", "hashicorp")

    code = demo_smoke.main()

    assert code == 1
    printed = json.loads(capsys.readouterr().out)
    assert printed["ready"] is False
    assert any(
        "unsupported SDP_CONNECTOR_VAULT_PROVIDER" in entry
        for entry in printed["connector_configuration_errors"]
    ), printed["connector_configuration_errors"]


def test_a_correct_deployment_reports_no_configuration_error() -> None:
    """The anti-vacuity half: the list is empty and the gate still passes.

    Without this, every assertion above could be satisfied by a report that always carries an
    error, and the ready gate would be permanently false - the standing-complaint shape this
    repository treats as a defect in its own words.
    """
    summary = demo_smoke.smoke_summary()

    assert summary["connector_configuration_errors"] == []
    assert summary["ready"] is True
    assert summary["rest_connector_adapter_status"] == "implemented"


def test_a_missing_seed_dataset_is_not_reported_as_a_configuration_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``KeyError`` is deliberately not caught, and that boundary is worth pinning.

    A dataset this function names being absent from the seed catalogue means the build is broken,
    not that the operator's environment is wrong. Reporting it as "not ready, check your
    configuration" would send someone to their environment file over a defect in the image, so it
    is left to raise.
    """
    from sdp import catalog

    monkeypatch.delitem(catalog._DATA, "crm-customer-master")

    with pytest.raises(KeyError):
        demo_smoke.smoke_summary()


def test_the_ready_gate_requires_an_empty_error_list_independently_of_the_probe_fields() -> None:
    """The gate's own clause, asserted in source because behaviour cannot reach it.

    Reverse-verification found this, and it is the third instance of the shape this round: deleting
    ``and not configuration_errors`` from the ``ready`` expression left every test in this file
    green (6 passed). The reason is that the helper returns ``None`` exactly when it records an
    error, and all four probes have a field in the gate, so a failing probe already fails its own
    clause:

        and (sql_probe or {}).get("status") == "ready_for_demo"      -> None fails it
        and (rdf_probe or {}).get("status") == "ready_for_demo"      -> None fails it
        and (file_probe or {}).get("status") == "ready_for_demo"     -> None fails it
        and (rest_probe or {}).get("adapter_status") == "implemented" -> None fails it

    Measured, only one of the four can produce a configuration error today - ``credential_vault``
    is in ``required_controls`` for ``rest_connector`` only, so the other three never reach
    ``connector_secret_status``:

        sql_connector        returns (never reaches the vault)
        rdf_connector        returns (never reaches the vault)
        file_lake_connector  returns (never reaches the vault)
        rest_connector       raises

    So the clause is **currently redundant**, and saying so is the point: it is kept because the two
    things are different concerns that happen to coincide. The probe-field checks ask whether the
    deployment is demo-ready; this clause asks whether its configuration was usable at all. Remove
    ``rest_probe``'s field from the gate later - or extend the vault to a connector whose fields are
    not checked - and the coincidence ends with nothing reporting it.

    A behavioural test cannot distinguish a redundant clause from an absent one, which is what made
    the first version of this file pass against its removal. Reading the source is the device that
    can, and it is the same one
    ``tests/test_alert_routing_request_path.py::test_the_middleware_awaits_the_alert_instead_of_calling_it_inline``
    uses for a call site a timing test cannot see.
    """
    source = Path(demo_smoke.__file__).read_text(encoding="utf-8")
    ready_clause = source[source.index('"ready": ('):]
    ready_clause = ready_clause[: ready_clause.index("\n        ),")]
    assert "not configuration_errors" in ready_clause, (
        "the ready gate no longer requires an empty configuration-error list. It is redundant "
        "while every probe that can fail also has a field in the gate, and that coincidence is "
        "not the invariant - a usable configuration is."
    )
