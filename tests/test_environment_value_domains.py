"""A readiness gate may only be satisfied by a value the code will accept.

``production._is_set`` asks whether a non-blank string is present and nothing more. For most
required variables that is the honest limit - this module cannot reach a database to find out
whether a DSN is real. For two of them it was not the limit, and the gap was reachable with the
value an operator would naturally choose. Measured on the head before this change, with everything
else configured:

    SDP_CONNECTOR_VAULT_PROVIDER='vault'       gate satisfied,
      GET /enterprise/connectors/rest_connector/probe?dataset_id=marketing-campaign&user=admin
      -> 400 {"detail": "unsupported connector vault provider: vault"}
    SDP_CONNECTOR_TIMEOUT_MS='2s'              gate satisfied,
      same route -> 400 {"detail": "invalid literal for int() with base 10: '2s'"}

``vault`` and ``hashicorp`` are the products an operator has; ``2s`` is how a person writes a
timeout. So ``GET /enterprise/production-readiness`` reported progress toward
``paid_pilot_ready`` while the connector probe - a buyer-demo surface - answered 400 for every
connector. That is worse than the defect this registry was built around:
``SDP_EVIDENCE_RETENTION_DAYS`` cleared a gate while doing nothing, and these cleared a gate while
**breaking** the capability the gate claims to measure.

WHAT THIS FILE GUARDS, AND WHY IT DRIVES THE FUNCTION. The repair declares the two domains in
``ProductionIntegration.environment_value_rules``, which duplicates knowledge that already lives in
``sdp.credentials.connector_secret_status``. A duplicated domain drifts, and a test that read both
and compared them would be comparing one list against another - the shape this repository keeps
finding at fault. So this file **executes the enforcing function** for every value it probes and
asserts the declaration agrees with what actually happened. The direction that matters most is the
one that is easy to forget: a gate must not *reject* a value the code accepts either, or the gate
has invented a requirement. That direction caught a real over-reach while this was being written -
``minimum=1`` was declared while ``int()`` happily accepted ``0``, so the fix moved into
``connector_secret_status``, which now validates the bound it publishes.
"""

from __future__ import annotations

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sdp.credentials import connector_secret_status  # noqa: E402
from sdp_core.production import (  # noqa: E402
    EnvironmentValueRule,
    enterprise_production_readiness_manifest,
    production_integration_registry,
)


def _drive_connector_secret_status(
    monkeypatch: pytest.MonkeyPatch, variable: str, value: str
) -> str | None:
    """Call the function that enforces this variable; return the refusal, or ``None``.

    The vault provider and the timeout are both read by this one function, which is why one
    enforcer covers both. It is called for its side effect of raising, with the rest of the
    environment left at its defaults so the only variable under test is the one being probed.
    """
    monkeypatch.setenv(variable, value)
    try:
        connector_secret_status("rest_connector", "marketing-campaign")
    except ValueError as exc:
        return str(exc)
    return None


# Which function enforces each declared domain. Declared here rather than in the registry because
# it is a fact about the test, not about the published contract - and because
# ``test_every_declared_domain_is_tied_to_an_enforcer`` makes a new rule without an entry here a
# failure, so the map cannot fall behind the registry.
ENFORCERS = {
    "SDP_CONNECTOR_VAULT_PROVIDER": _drive_connector_secret_status,
    "SDP_CONNECTOR_TIMEOUT_MS": _drive_connector_secret_status,
}

# Values probed against every rule: the ones an operator plausibly types, plus the shapes that
# separate "parses" from "is accepted". Deliberately not derived from the rule alone - a probe set
# generated from the declaration would only ever confirm the declaration.
PROBE_VALUES = (
    "env",
    "vault",
    "hashicorp",
    "aws-secrets-manager",
    "1000",
    "1",
    "0",
    "-5",
    "2s",
    "1000ms",
    " 1000 ",
    "true",
)


def _declared_rules() -> dict[str, tuple[str, EnvironmentValueRule]]:
    """Every value rule the registry declares, keyed by variable."""
    rules: dict[str, tuple[str, EnvironmentValueRule]] = {}
    for item in production_integration_registry():
        for variable, rule in item.environment_value_rules.items():
            rules[variable] = (item.id, rule)
    assert rules, "no environment_value_rules are declared; re-point this test"
    return rules


def test_every_declared_domain_is_tied_to_an_enforcer() -> None:
    """A rule with no enforcer in this file is a declaration nothing checks."""
    unmapped = sorted(set(_declared_rules()) - set(ENFORCERS))
    assert unmapped == [], (
        f"these variables declare a value domain that no test drives: {unmapped}. Add the function "
        "that enforces the domain to ENFORCERS, so the declaration is checked against behaviour "
        "rather than against itself."
    )
    # And the reverse, so a rule removed from the registry does not leave a probe behind that
    # silently tests nothing.
    stale = sorted(set(ENFORCERS) - set(_declared_rules()))
    assert stale == [], f"ENFORCERS names variables the registry no longer constrains: {stale}"


@pytest.mark.parametrize("variable", sorted(_declared_rules()))
def test_the_declared_domain_agrees_with_the_code_that_enforces_it(
    variable: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both directions, for every probe value: the gate and the function must agree.

    A value the function refuses must not satisfy the gate - that is the defect. A value the
    function accepts must not be refused by the gate - that is the over-reach, and it is the half a
    one-directional check misses.
    """
    _, rule = _declared_rules()[variable]
    enforcer = ENFORCERS[variable]

    disagreements = []
    for value in PROBE_VALUES:
        with monkeypatch.context() as patched:
            refusal = enforcer(patched, variable, value)
        declared = rule.rejection_reason(value)
        if (refusal is None) != (declared is None):
            disagreements.append(
                {
                    "value": value,
                    "code": refusal or "accepted",
                    "gate": declared or "accepted",
                }
            )
    assert disagreements == [], (
        f"the declared domain for {variable} disagrees with the code that enforces it: "
        f"{disagreements}. Either the gate admits a value that breaks the capability, or it "
        "invents a requirement the code does not have."
    )


def test_a_value_the_code_refuses_does_not_clear_the_paid_pilot_gate() -> None:
    """The end-to-end statement, through the published manifest.

    Measured before the repair: every row below reported the integration as configured. The
    assertion is on the manifest an operator actually reads, not on the helper, because the helper
    being right is not the claim - the published readiness is.
    """
    configured = {
        "SDP_CONNECTOR_SECRET_REF_PREFIX": "SDP_CONNECTOR_SECRET_",
        "SDP_CONNECTOR_VAULT_PROVIDER": "env",
        "SDP_CONNECTOR_TIMEOUT_MS": "1000",
    }
    clean = enterprise_production_readiness_manifest(configured)
    assert "connector_credential_vault" not in clean.unconfigured_integrations
    assert clean.rejected_environment == {}

    for variable, value, expected in (
        ("SDP_CONNECTOR_VAULT_PROVIDER", "vault", "must be one of: env"),
        ("SDP_CONNECTOR_VAULT_PROVIDER", "hashicorp", "must be one of: env"),
        ("SDP_CONNECTOR_TIMEOUT_MS", "2s", "must be an integer"),
        ("SDP_CONNECTOR_TIMEOUT_MS", "0", "must be an integer >= 1"),
    ):
        manifest = enterprise_production_readiness_manifest(
            {**configured, variable: value}
        )
        assert "connector_credential_vault" in manifest.unconfigured_integrations, (
            f"{variable}={value!r} cleared the gate; the code refuses it"
        )
        assert "connector_credential_vault" in manifest.paid_pilot_blockers
        rejected = manifest.rejected_environment["connector_credential_vault"]
        assert rejected[variable] == expected, rejected


def test_a_rejected_value_is_reported_separately_from_an_unset_one() -> None:
    """An operator who set a variable must not be told it is missing.

    The two states need different remedies - a missing name is a name to add, a rejected value is a
    domain to read - and folding them into one list sends an operator who just set the variable
    looking for a typo in its name. A variable that is unset appears in ``missing_environment``
    only, never in both.
    """
    rejected_only = enterprise_production_readiness_manifest(
        {
            "SDP_CONNECTOR_SECRET_REF_PREFIX": "SDP_CONNECTOR_SECRET_",
            "SDP_CONNECTOR_VAULT_PROVIDER": "vault",
            "SDP_CONNECTOR_TIMEOUT_MS": "1000",
        }
    )
    assert rejected_only.rejected_environment["connector_credential_vault"] == {
        "SDP_CONNECTOR_VAULT_PROVIDER": "must be one of: env"
    }
    assert "SDP_CONNECTOR_VAULT_PROVIDER" not in rejected_only.missing_environment.get(
        "connector_credential_vault", []
    )

    unset = enterprise_production_readiness_manifest(
        {"SDP_CONNECTOR_SECRET_REF_PREFIX": "SDP_CONNECTOR_SECRET_"}
    )
    missing = unset.missing_environment["connector_credential_vault"]
    assert "SDP_CONNECTOR_VAULT_PROVIDER" in missing
    assert "SDP_CONNECTOR_TIMEOUT_MS" in missing
    assert "connector_credential_vault" not in unset.rejected_environment, (
        "an unset variable must not also be reported as rejected; one problem, one entry"
    )
