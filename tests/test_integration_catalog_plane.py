"""Live-DSN checks for the 0002 catalog plane (no Apache AGE required).

Skipped unless ``SDP_DATABASE_DSN`` points at a database that already has
``catalog_objects``. This file does not run ``apply_migrations`` because 0001
installs AGE. Paid-pilot images apply 0002 via ``docker/entrypoint.sh``.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, inspect, text

from sdp.catalog_plane_store import RelationalCatalogPlaneStore
from sdp_core.catalog_plane import (
    CatalogObjectRecord,
    ObjectDefinitionRecord,
    ObjectStewardRecord,
)

pytestmark = pytest.mark.integration

DSN = os.environ.get("SDP_DATABASE_DSN")


def _catalog_objects_ready(database_dsn: str) -> bool:
    """Return whether the 0002 parent table already exists on this DSN."""

    engine = create_engine(database_dsn, future=True)
    try:
        return inspect(engine).has_table("catalog_objects")
    finally:
        engine.dispose()


@pytest.fixture(scope="module")
def live_plane_store():
    """Open the 0002 store when the paid-pilot tables are already present."""

    if not DSN:
        pytest.skip("SDP_DATABASE_DSN not set")
    if not _catalog_objects_ready(DSN):
        pytest.skip("catalog_objects is missing; apply 0002 without requiring AGE")
    return RelationalCatalogPlaneStore(DSN)


def test_live_dsn_create_survives_store_reopen(live_plane_store):
    """A paid-pilot DSN keeps glossary rows after the store is reconstructed."""

    tenant_reference = f"plane-persist-{uuid4().hex[:12]}"
    catalog_object_id = CatalogObjectRecord.new_id()
    recorded_at = datetime.now(timezone.utc)
    record = CatalogObjectRecord(
        catalog_object_id=catalog_object_id,
        tenant_reference=tenant_reference,
        object_kind="glossary_term",
        object_slug=f"persist-{uuid4().hex[:8]}",
        display_title="재시작 보존",
        object_status="published",
        created_by_subject="admin",
        created_at=recorded_at,
        updated_at=recorded_at,
        definition=ObjectDefinitionRecord(
            definition_id=str(uuid4()),
            catalog_object_id=catalog_object_id,
            definition_text="DSN 재시작 후에도 남아야 하는 glossary row.",
            preferred_language="ko",
            definition_status="current",
            recorded_at=recorded_at,
        ),
        steward=ObjectStewardRecord(
            steward_record_id=str(uuid4()),
            catalog_object_id=catalog_object_id,
            steward_subject="admin",
            steward_display_name="Mina Park",
            recorded_at=recorded_at,
        ),
    )
    try:
        live_plane_store.insert_catalog_object(record)
        reopened = RelationalCatalogPlaneStore(DSN)
        loaded = reopened.get_catalog_object(
            tenant_reference=tenant_reference,
            catalog_object_id=catalog_object_id,
        )
        assert loaded is not None
        assert loaded.display_title == "재시작 보존"
        assert loaded.steward.steward_display_name == "Mina Park"
    finally:
        engine = create_engine(DSN, future=True)
        try:
            with engine.begin() as connection:
                connection.execute(
                    text("DELETE FROM catalog_objects WHERE catalog_object_id = :object_id"),
                    {"object_id": catalog_object_id},
                )
        finally:
            engine.dispose()
