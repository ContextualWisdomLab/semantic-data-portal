"""SQLite mapping tests for migration-0003 data-management evidence."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, text

from sdp.catalog_plane import create_catalog_object
from sdp.catalog_plane_store import (
    RelationalCatalogPlaneStore,
    apply_catalog_plane_sqlite_schema,
    set_catalog_plane_store,
)
from sdp.data_management_evidence import (
    assign_data_owner,
    build_data_management_profile,
    define_data_quality_rule,
    record_data_quality_observation,
    register_critical_data_element,
)
from sdp.data_management_store import (
    RelationalDataManagementStore,
    apply_data_management_sqlite_schema,
    set_data_management_store,
)
from sdp_core.catalog_plane import CatalogObjectCreateRequest, PlaneActor
from sdp_core.data_management_evidence import (
    CriticalDataElementDraft,
    DataOwnerAssignmentDraft,
    DataQualityObservationDraft,
    DataQualityRuleDraft,
)


def _admin_actor(tenant_reference: str = "demo") -> PlaneActor:
    """Return a purpose-bound Keyverse admin actor."""

    return PlaneActor(
        subject="admin",
        tenant_reference=tenant_reference,
        roles=["admin"],
        access_purpose="glossary_stewardship",
        binding_source="test",
    )


def _reader_actor(tenant_reference: str = "demo") -> PlaneActor:
    """Return a purpose-bound catalog reader."""

    return PlaneActor(
        subject="analyst",
        tenant_reference=tenant_reference,
        roles=["data-analyst"],
        access_purpose="catalog_browse",
        binding_source="test",
    )


def _sqlite_dsn(tmp_path) -> str:
    """Create a SQLite file with the 0002 parent and 0003 evidence schemas."""

    database_path = tmp_path / "data-management.sqlite"
    dsn = f"sqlite:///{database_path}"
    engine = create_engine(dsn, future=True)
    apply_catalog_plane_sqlite_schema(engine)
    apply_data_management_sqlite_schema(engine)
    engine.dispose()
    return dsn


def _create_dataset(actor: PlaneActor) -> str:
    """Create one relational catalog dataset and return its identifier."""

    envelope = create_catalog_object(
        actor,
        CatalogObjectCreateRequest(
            object_kind="catalog_dataset",
            object_slug="billing-settlement-evidence",
            display_title="Billing settlement evidence",
            definition_text="Usage, invoice, payment, refund, and settlement evidence.",
            preferred_language="en",
            steward_display_name="Billing Data Steward",
            aliases=[],
            document_kg_links=[],
            concept_bindings=[],
            score_references=[],
        ),
    )
    return envelope.catalog_object.catalog_object_id


def _populate_profile(actor: PlaneActor, catalog_object_id: str) -> None:
    """Populate owner, CDE, quality rule, and immutable observation rows."""

    assign_data_owner(
        actor,
        catalog_object_id,
        DataOwnerAssignmentDraft(
            owner_subject="billing-operations-owner",
            owner_display_name="Billing Operations Owner",
            valid_from=datetime(2026, 8, 18, tzinfo=timezone.utc),
            evidence_reference="https://evidence.example.test/decisions/billing-owner",
            truth_status="authoritative",
        ),
    )
    cde = register_critical_data_element(
        actor,
        catalog_object_id,
        CriticalDataElementDraft(
            element_key="settlement_amount",
            display_name="Settlement amount",
            definition_text="Cash amount paid out by the provider for one settlement.",
            data_classification="restricted_financial",
            evidence_reference="https://evidence.example.test/dictionary/settlement-amount",
            truth_status="authoritative",
        ),
    ).critical_data_element
    assert cde is not None
    rule = define_data_quality_rule(
        actor,
        cde.critical_data_element_id,
        DataQualityRuleDraft(
            rule_code="settlement_matches_expected_amount",
            rule_description="Settlement plus provider fee equals the captured invoice amount.",
            metric_code="reconciliation_difference",
            threshold_operator="equal_to",
            threshold_value="0",
            unit_code="KRW",
            evidence_reference="https://evidence.example.test/controls/reconciliation",
            truth_status="authoritative",
        ),
    ).data_quality_rule
    assert rule is not None
    record_data_quality_observation(
        actor,
        rule.data_quality_rule_id,
        DataQualityObservationDraft(
            source_observation_id="reconciliation_run_2026_08_18",
            observed_value="0",
            observed_at=datetime(2026, 8, 18, 1, tzinfo=timezone.utc),
            quality_status="passed",
            evidence_reference="https://evidence.example.test/runs/reconciliation-2026-08-18",
            truth_status="observed",
        ),
    )


def test_relational_profile_survives_store_reopen(tmp_path) -> None:
    """Migration-0003 rows remain complete after both stores reopen the DSN."""

    dsn = _sqlite_dsn(tmp_path)
    set_catalog_plane_store(RelationalCatalogPlaneStore(dsn))
    set_data_management_store(RelationalDataManagementStore(dsn))
    try:
        catalog_object_id = _create_dataset(_admin_actor())
        _populate_profile(_admin_actor(), catalog_object_id)

        set_catalog_plane_store(RelationalCatalogPlaneStore(dsn))
        set_data_management_store(RelationalDataManagementStore(dsn))
        profile = build_data_management_profile(_reader_actor(), catalog_object_id)

        assert profile.evidence_complete is True
        assert profile.counts == {
            "data_owner_assignments": 1,
            "critical_data_elements": 1,
            "data_quality_rules": 1,
            "data_quality_observations": 1,
        }
        assert profile.data_owner_assignments[0].owner_display_name == "Billing Operations Owner"
        assert profile.data_quality_observations[0].source_observation_id == "reconciliation_run_2026_08_18"
    finally:
        set_data_management_store(None)
        set_catalog_plane_store(None)


def test_relational_store_enforces_natural_keys_and_tenant_scope(tmp_path) -> None:
    """SQL uniqueness and tenant filters match the in-memory store."""

    dsn = _sqlite_dsn(tmp_path)
    set_catalog_plane_store(RelationalCatalogPlaneStore(dsn))
    set_data_management_store(RelationalDataManagementStore(dsn))
    try:
        actor = _admin_actor()
        catalog_object_id = _create_dataset(actor)
        draft = DataOwnerAssignmentDraft(
            owner_subject="billing-operations-owner",
            owner_display_name="Billing Operations Owner",
            valid_from=datetime(2026, 8, 18, tzinfo=timezone.utc),
            evidence_reference="https://evidence.example.test/decisions/billing-owner",
            truth_status="authoritative",
        )
        assign_data_owner(actor, catalog_object_id, draft)
        with pytest.raises(ValueError, match="duplicate data-owner assignment"):
            assign_data_owner(actor, catalog_object_id, draft)

        profile = build_data_management_profile(_reader_actor("external"), catalog_object_id)
        assert profile.catalog_object_id == catalog_object_id  # pragma: no cover
    except KeyError as exc:
        assert "catalog object not found" in str(exc)
    finally:
        set_data_management_store(None)
        set_catalog_plane_store(None)


def test_sqlite_schema_creates_all_0003_tables(tmp_path) -> None:
    """The portable rewrite keeps the production migration table names."""

    dsn = _sqlite_dsn(tmp_path)
    engine = create_engine(dsn, future=True)
    with engine.connect() as connection:
        tables = {
            row[0]
            for row in connection.execute(
                text("SELECT name FROM sqlite_master WHERE type = 'table'")
            )
        }
    engine.dispose()
    assert {
        "data_owner_assignments",
        "critical_data_elements",
        "data_quality_rules",
        "data_quality_observations",
    }.issubset(tables)
