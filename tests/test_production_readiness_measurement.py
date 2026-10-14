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

import pathlib

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


# --------------------------------------------------------------------------- #
# A gate may only measure capabilities that exist.
#
# Making ``paid_pilot_ready`` falsifiable was not enough: the gate still turned
# on the presence of a non-blank string, and one declared variable had no
# consumer anywhere in ``src/``. Measured with everything else configured, the
# last variable between false and true was ``SDP_EVIDENCE_RETENTION_DAYS``, and
# it was satisfied by every one of ``'banana'``, ``'0'``, ``'-1'`` and
# ``'   x'`` - while neither evidence store has any prune, purge or expiry path
# at all. The gate could be cleared by setting a variable that does nothing.
# --------------------------------------------------------------------------- #

SOURCE_ROOT = pathlib.Path(__file__).resolve().parents[1] / "src"
DECLARATION_FILE = "production.py"


def _consumers(variable: str) -> list[str]:
    """Source files that mention this variable, excluding its declaration site.

    The limit is worth stating: a name appearing in a source file is not proof
    that behaviour depends on it. It is a far better check than none, and it
    catches this defect class exactly - a variable that appears *only* where it
    is declared as required cannot be changing anything.
    """
    return sorted(
        path.relative_to(SOURCE_ROOT).as_posix()
        for path in SOURCE_ROOT.rglob("*.py")
        if path.name != DECLARATION_FILE and variable in path.read_text()
    )


def test_every_required_variable_has_a_consumer() -> None:
    """Enumerated over the whole registry, not just the one that was reported."""
    unread = {}
    for integration in production_integration_registry():
        for variable in integration.required_environment:
            if not _consumers(variable):
                unread.setdefault(integration.id, []).append(variable)
    assert not unread, (
        "these variables gate paid-pilot readiness while nothing reads them, so "
        f"the gate can be cleared without the capability existing: {unread}"
    )


def test_an_unimplemented_variable_is_declared_rather_than_dropped() -> None:
    """The gap stays visible to a buyer.

    Deleting the variable would have removed the false claim and the
    information with it. An operator who sets it should be able to find out,
    from the readiness document itself, that nothing honours it.
    """
    manifest = enterprise_production_readiness_manifest({})
    declared = manifest.unimplemented_environment
    assert declared.get("postgres_evidence_store") == ["SDP_EVIDENCE_RETENTION_DAYS"], declared

    evidence_store = next(
        item for item in manifest.integrations if item.id == "postgres_evidence_store"
    )
    assert "SDP_EVIDENCE_RETENTION_DAYS" not in evidence_store.required_environment
    # The prose must not claim the capability either.
    assert "retention is NOT implemented" in evidence_store.buyer_risk


def test_a_declared_unimplemented_variable_cannot_clear_the_gate() -> None:
    """Setting it must change nothing about readiness."""
    base = {
        "SDP_DATABASE_URL": "postgresql://user:pass@host/db",
        "SDP_DATABASE_SSLMODE": "require",
    }
    without = enterprise_production_readiness_manifest(base)
    for value in ("banana", "0", "-1", "   x", "30"):
        with_variable = enterprise_production_readiness_manifest(
            {**base, "SDP_EVIDENCE_RETENTION_DAYS": value}
        )
        assert with_variable.paid_pilot_ready == without.paid_pilot_ready
        assert with_variable.paid_pilot_blockers == without.paid_pilot_blockers
        assert with_variable.missing_environment == without.missing_environment


def test_no_evidence_store_claims_a_retention_path_it_does_not_have() -> None:
    """The reason the variable is unimplemented, pinned.

    If a prune/purge path is ever added, this fails and whoever added it moves
    the variable back into ``required_environment`` deliberately.
    """
    from sdp_core import PostgresEvidenceStore, SQLiteEvidenceStore

    for store in (SQLiteEvidenceStore, PostgresEvidenceStore):
        retention_methods = [
            name
            for name in dir(store)
            if not name.startswith("__")
            and any(word in name.lower() for word in ("prune", "purge", "retent", "expire"))
        ]
        assert not retention_methods, (
            f"{store.__name__} gained {retention_methods}; move "
            "SDP_EVIDENCE_RETENTION_DAYS back into required_environment and gate on it"
        )


def test_no_enterprise_control_claims_retention_it_does_not_implement() -> None:
    """The control named "retention" provides durability, and now says so.

    ``local_evidence_retention`` was labelled "Local evidence retention" with
    ``status: implemented``, so a buyer reading the controls manifest concluded
    a retention policy was in place. Its own ``risk_reduced`` described
    surviving a restart - durability - and no store has a prune, purge or
    expiry path. The id is kept (docs and tests reference it); the claim is
    corrected.
    """
    from sdp_core.enterprise import enterprise_controls_manifest

    controls = {item.id: item for item in enterprise_controls_manifest().controls}
    durability = controls["local_evidence_retention"]
    assert durability.status == "implemented"
    assert "no age-based retention" in durability.label
    assert "not a retention policy" in durability.risk_reduced
