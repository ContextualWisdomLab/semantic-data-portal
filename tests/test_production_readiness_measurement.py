"""``paid_pilot_ready`` must be falsifiable by something a buyer can change.

It was derived from each integration's authored ``status`` literal, and every one
of the four is ``"implemented"``, so no real change could make it false. Measured
before the repair, in a process with no ``SDP_*`` configuration at all and with
three of the manifest's own named proof endpoints returning 403::

    paid_pilot_ready    = True
    paid_pilot_blockers = []
    the manifest function read no runtime state whatsoever

A flag that cannot be falsified is not evidence, and a procurement reader takes
it as one.

Two different claims were being conflated, and both are kept:

* ``status`` is about the **codebase** - this integration is built - and is
  unchanged, because it is true.
* ``configured_integrations`` / ``missing_environment`` are measured from the
  **deployment**, using the variables each integration already declares in
  ``required_environment``.

A paid pilot needs a configured deployment, not only shipped code, so the flag
now requires both. ``demo_release_ready`` is deliberately untouched: the demo path
runs on in-memory defaults by design, which is why ``sdp.demo_smoke`` does not
gate on this flag.
"""

from __future__ import annotations

from sdp_core.production import (
    enterprise_production_readiness_manifest,
    production_integration_registry,
)


def _fully_configured_environment() -> dict[str, str]:
    return {
        name: "configured"
        for integration in production_integration_registry()
        for name in integration.required_environment
    }


def test_an_unconfigured_deployment_is_not_paid_pilot_ready() -> None:
    manifest = enterprise_production_readiness_manifest({})
    assert manifest.paid_pilot_ready is False
    assert manifest.paid_pilot_blockers, "the refusal must name what blocks it"
    assert manifest.configured_integrations == []
    assert sorted(manifest.unconfigured_integrations) == sorted(
        item.id for item in production_integration_registry()
    )


def test_a_fully_configured_deployment_is_paid_pilot_ready() -> None:
    manifest = enterprise_production_readiness_manifest(_fully_configured_environment())
    assert manifest.paid_pilot_ready is True
    assert manifest.paid_pilot_blockers == []
    assert manifest.unconfigured_integrations == []
    assert manifest.missing_environment == {}


def test_removing_one_variable_flips_the_flag_and_names_it() -> None:
    """The falsifiability property, exercised one variable at a time."""
    for integration in production_integration_registry():
        for name in integration.required_environment:
            environment = _fully_configured_environment()
            del environment[name]
            manifest = enterprise_production_readiness_manifest(environment)
            assert manifest.paid_pilot_ready is False, (
                f"dropping {name} must make paid_pilot_ready false"
            )
            assert integration.id in manifest.unconfigured_integrations
            assert name in manifest.missing_environment[integration.id], (
                f"the manifest must name {name} as the missing variable"
            )


def test_a_blank_variable_counts_as_unset() -> None:
    """An empty string is not configuration."""
    environment = _fully_configured_environment()
    first = next(iter(environment))
    environment[first] = "   "
    manifest = enterprise_production_readiness_manifest(environment)
    assert manifest.paid_pilot_ready is False
    assert any(first in missing for missing in manifest.missing_environment.values())


def test_the_status_literals_still_describe_the_codebase() -> None:
    """The authored claim is kept; it was the *derivation* that was wrong.

    If an integration is ever genuinely unbuilt, it must block regardless of
    configuration, so both causes are checked here.
    """
    for integration in production_integration_registry():
        assert integration.status == "implemented", integration.id

    manifest = enterprise_production_readiness_manifest(_fully_configured_environment())
    assert manifest.paid_pilot_ready is True
    # Configuration alone must not be able to vouch for an unbuilt integration.
    import sdp_core.production as production

    original = production.production_integration_registry

    def one_unbuilt() -> list:
        items = original()
        items[0] = items[0].model_copy(update={"status": "planned"})
        return items

    production.production_integration_registry = one_unbuilt
    try:
        degraded = production.enterprise_production_readiness_manifest(
            _fully_configured_environment()
        )
        assert degraded.paid_pilot_ready is False
        assert degraded.paid_pilot_blockers == [one_unbuilt()[0].id]
        assert degraded.unconfigured_integrations == []
    finally:
        production.production_integration_registry = original


def test_demo_readiness_is_not_coupled_to_pilot_configuration() -> None:
    """The demo path runs on in-memory defaults; that claim must not regress."""
    assert enterprise_production_readiness_manifest({}).demo_release_ready is True
    assert (
        enterprise_production_readiness_manifest(
            _fully_configured_environment()
        ).demo_release_ready
        is True
    )
