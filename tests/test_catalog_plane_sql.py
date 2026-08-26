"""Unit tests for the 0002-backed catalog plane store (SQLite mapping)."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text

from sdp.catalog_plane import create_catalog_object, reset_catalog_plane
from sdp.catalog_plane_store import (
    InMemoryCatalogPlaneStore,
    RelationalCatalogPlaneStore,
    apply_catalog_plane_sqlite_schema,
    build_catalog_plane_store,
    get_catalog_plane_store,
    set_catalog_plane_store,
)
from sdp.config import reset_config_cache
from sdp_core.catalog_plane import (
    CatalogObjectCreateRequest,
    CatalogObjectRecord,
    ConceptBindingRecord,
    DocumentKgLinkRecord,
    ObjectAliasRecord,
    ObjectDefinitionRecord,
    ObjectStewardRecord,
    PlaneActor,
    ScoreReferenceRecord,
)


def _now() -> datetime:
    """Return an aware UTC timestamp for test fixtures."""

    return datetime.now(timezone.utc)


def _child_id() -> str:
    """Allocate a child-row identifier for test fixtures."""

    return str(uuid4())


def _sample_record(
    *,
    tenant_reference: str = "demo",
    object_slug: str = "active-customer",
    display_title: str = "활성 고객",
    source_object_id: str = "cn_buyer_active_customer_2026",
) -> CatalogObjectRecord:
    """Build one 0002-shaped catalog object with children."""

    catalog_object_id = CatalogObjectRecord.new_id()
    recorded_at = _now()
    return CatalogObjectRecord(
        catalog_object_id=catalog_object_id,
        tenant_reference=tenant_reference,
        object_kind="glossary_term",
        object_slug=object_slug,
        display_title=display_title,
        object_status="published",
        created_by_subject="admin",
        created_at=recorded_at,
        updated_at=recorded_at,
        definition=ObjectDefinitionRecord(
            definition_id=_child_id(),
            catalog_object_id=catalog_object_id,
            definition_text="최근 활성이 확인된 고객 집합.",
            preferred_language="ko",
            definition_status="current",
            recorded_at=recorded_at,
        ),
        steward=ObjectStewardRecord(
            steward_record_id=_child_id(),
            catalog_object_id=catalog_object_id,
            steward_subject="admin",
            steward_display_name="Mina Park",
            recorded_at=recorded_at,
        ),
        aliases=[
            ObjectAliasRecord(
                alias_id=_child_id(),
                catalog_object_id=catalog_object_id,
                alias_text="active customer",
                alias_language="en",
            )
        ],
        document_kg_links=[
            DocumentKgLinkRecord(
                document_kg_link_id=_child_id(),
                catalog_object_id=catalog_object_id,
                source_system="naruon",
                source_object_kind="content_node",
                source_object_id=source_object_id,
                provenance_uri="https://www.w3.org/TR/prov-o/",
                link_status="active",
                recorded_at=recorded_at,
            )
        ],
        concept_bindings=[
            ConceptBindingRecord(
                binding_id=_child_id(),
                catalog_object_id=catalog_object_id,
                concept_key="활성 고객",
                binding_role="preferred",
                recorded_at=recorded_at,
            )
        ],
        score_references=[
            ScoreReferenceRecord(
                score_reference_id=_child_id(),
                catalog_object_id=catalog_object_id,
                score_system="tepp",
                score_endpoint="https://commons.example.test/tepp/items/active-customer",
                recorded_at=recorded_at,
            )
        ],
    )


def _sqlite_dsn(tmp_path) -> str:
    """Return a file-backed SQLite DSN and apply the rewritten 0002 DDL."""

    database_path = tmp_path / "catalog-plane.sqlite"
    dsn = f"sqlite:///{database_path}"
    engine = create_engine(dsn, future=True)
    apply_catalog_plane_sqlite_schema(engine)
    engine.dispose()
    return dsn


def _admin_actor(tenant_reference: str = "demo") -> PlaneActor:
    """Return a Keyverse admin actor for service-layer persist tests."""

    return PlaneActor(
        subject="admin",
        tenant_reference=tenant_reference,
        roles=["admin"],
        access_purpose="glossary_stewardship",
        binding_source="test",
    )


def test_get_catalog_plane_store_defaults_to_memory(monkeypatch):
    """CI / pytest without SDP_DATABASE_DSN keeps the in-memory store."""

    monkeypatch.delenv("SDP_DATABASE_DSN", raising=False)
    set_catalog_plane_store(None)
    reset_config_cache()
    store = get_catalog_plane_store()
    assert isinstance(store, InMemoryCatalogPlaneStore)
    set_catalog_plane_store(None)


def test_relational_query_treats_like_metacharacters_literally(tmp_path):
    """Percent, underscore, and backslash search text are literal substrings."""

    store = RelationalCatalogPlaneStore(_sqlite_dsn(tmp_path))
    literal = _sample_record(object_slug=r"rate_100%\\complete")
    ordinary = _sample_record(object_slug="rate-100-complete")
    store.insert_catalog_object(literal)
    store.insert_catalog_object(ordinary)

    assert [
        row.catalog_object_id
        for row in store.query_catalog_objects(
            tenant_reference="demo", query_text=r"_100%\\"
        )
    ] == [literal.catalog_object_id]


def test_in_memory_insert_detaches_the_callers_record():
    """Mutating an input model after insertion cannot alter persisted state."""

    reset_catalog_plane()
    store = InMemoryCatalogPlaneStore()
    record = _sample_record()
    store.insert_catalog_object(record)
    record.display_title = "changed outside the store"

    loaded = store.get_catalog_object(
        tenant_reference="demo", catalog_object_id=record.catalog_object_id
    )
    assert loaded is not None
    assert loaded.display_title == "활성 고객"


def test_build_store_uses_relational_when_dsn_is_set(tmp_path, monkeypatch):
    """A configured DSN selects the 0002 relational store, not memory."""

    dsn = _sqlite_dsn(tmp_path)
    monkeypatch.setenv("SDP_DATABASE_DSN", dsn)
    reset_config_cache()
    set_catalog_plane_store(None)
    try:
        store = build_catalog_plane_store()
        assert isinstance(store, RelationalCatalogPlaneStore)
    finally:
        monkeypatch.delenv("SDP_DATABASE_DSN", raising=False)
        reset_config_cache()
        set_catalog_plane_store(None)


def test_relational_store_survives_new_engine(tmp_path):
    """Create/list/get/query/attach remain after the process reopens the DSN."""

    dsn = _sqlite_dsn(tmp_path)
    first = RelationalCatalogPlaneStore(dsn)
    record = _sample_record()
    first.insert_catalog_object(record)

    restarted = RelationalCatalogPlaneStore(dsn)
    loaded = restarted.get_catalog_object(
        tenant_reference="demo",
        catalog_object_id=record.catalog_object_id,
    )
    assert loaded is not None
    assert loaded.object_slug == "active-customer"
    assert loaded.steward.steward_display_name == "Mina Park"
    assert "***" not in loaded.steward.steward_display_name
    assert loaded.document_kg_links[0].source_object_id == "cn_buyer_active_customer_2026"
    listed = restarted.list_catalog_objects(tenant_reference="demo")
    assert [row.catalog_object_id for row in listed] == [record.catalog_object_id]
    queried = restarted.query_catalog_objects(
        tenant_reference="demo",
        query_text="cn_buyer_active_customer_2026",
    )
    assert len(queried) == 1

    attached = restarted.attach_document_kg_link(
        tenant_reference="demo",
        catalog_object_id=record.catalog_object_id,
        link=DocumentKgLinkRecord(
            document_kg_link_id=_child_id(),
            catalog_object_id=record.catalog_object_id,
            source_system="disksage",
            source_object_kind="catalog_batch_ref",
            source_object_id="disksage:batch:preview-ref-not-ingest",
            provenance_uri="https://www.w3.org/TR/prov-o/",
            link_status="active",
            recorded_at=_now(),
        ),
    )
    assert attached is not None
    assert len(attached.document_kg_links) == 2

    third = RelationalCatalogPlaneStore(dsn)
    after_attach = third.get_catalog_object(
        tenant_reference="demo",
        catalog_object_id=record.catalog_object_id,
    )
    assert after_attach is not None
    assert len(after_attach.document_kg_links) == 2


def test_relational_store_enforces_tenant_and_unique_keys(tmp_path):
    """UNIQUE (tenant, slug) and child keys match the 0002 constraints."""

    dsn = _sqlite_dsn(tmp_path)
    store = RelationalCatalogPlaneStore(dsn)
    demo = _sample_record(tenant_reference="demo", object_slug="active-customer")
    store.insert_catalog_object(demo)
    with pytest.raises(ValueError, match="object_slug already exists"):
        store.insert_catalog_object(
            _sample_record(tenant_reference="demo", object_slug="active-customer")
        )

    other = _sample_record(
        tenant_reference="external",
        object_slug="active-customer",
        source_object_id="cn_external_only",
    )
    store.insert_catalog_object(other)
    assert store.list_catalog_objects(tenant_reference="demo")[0].catalog_object_id == demo.catalog_object_id
    assert store.get_catalog_object(
        tenant_reference="external",
        catalog_object_id=demo.catalog_object_id,
    ) is None

    duplicate_link = DocumentKgLinkRecord(
        document_kg_link_id=_child_id(),
        catalog_object_id=demo.catalog_object_id,
        source_system="naruon",
        source_object_kind="content_node",
        source_object_id="cn_buyer_active_customer_2026",
        provenance_uri="https://www.w3.org/TR/prov-o/",
        link_status="active",
        recorded_at=_now(),
    )
    with pytest.raises(ValueError, match="duplicate document-KG link"):
        store.attach_document_kg_link(
            tenant_reference="demo",
            catalog_object_id=demo.catalog_object_id,
            link=duplicate_link,
        )

    duplicate_binding = ConceptBindingRecord(
        binding_id=_child_id(),
        catalog_object_id=demo.catalog_object_id,
        concept_key="활성 고객",
        binding_role="preferred",
        recorded_at=_now(),
    )
    with pytest.raises(ValueError, match="duplicate concept binding"):
        store.attach_concept_binding(
            tenant_reference="demo",
            catalog_object_id=demo.catalog_object_id,
            binding=duplicate_binding,
        )


def test_service_create_survives_store_reopen(tmp_path):
    """The buyer create path writes 0002 rows that a new store instance can read."""

    dsn = _sqlite_dsn(tmp_path)
    set_catalog_plane_store(RelationalCatalogPlaneStore(dsn))
    try:
        envelope = create_catalog_object(
            _admin_actor(),
            CatalogObjectCreateRequest(
                object_kind="glossary_term",
                object_slug="renewal-risk",
                display_title="갱신 위험",
                definition_text="계약 갱신 위험이 높은 고객.",
                preferred_language="ko",
                steward_display_name="Mina Park",
                aliases=[],
                document_kg_links=[],
                concept_bindings=[],
                score_references=[],
            ),
        )
        catalog_object_id = envelope.catalog_object.catalog_object_id
        set_catalog_plane_store(RelationalCatalogPlaneStore(dsn))
        reopened = get_catalog_plane_store().get_catalog_object(
            tenant_reference="demo",
            catalog_object_id=catalog_object_id,
        )
        assert reopened is not None
        assert reopened.display_title == "갱신 위험"
        assert reopened.steward.steward_display_name == "Mina Park"
    finally:
        set_catalog_plane_store(None)
        reset_catalog_plane()


def test_sqlite_schema_keeps_0002_table_and_unique_names(tmp_path):
    """The SQLite rewrite still creates the production 0002 table names."""

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
        "catalog_objects",
        "object_definitions",
        "object_aliases",
        "document_kg_links",
        "concept_object_bindings",
        "commons_score_references",
        "object_stewards",
    }.issubset(tables)
