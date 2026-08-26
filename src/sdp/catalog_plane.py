"""Ontology/catalog plane sitting above the document knowledge graph.

Buyers create, list, get, and query catalog objects that *reference* naruon
content-graph / project-graph identifiers (and optional DiskSage or commons
pointers). Persistence is in-memory when ``SDP_DATABASE_DSN`` is unset (CI
default) and the 0002 3NF tables when the DSN is set. This module does not
ingest files, preview bytes, compute TEPP scores, or keep a local GRC policy
registry.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sdp_core.catalog_plane import (
    CatalogObjectCreateRequest,
    CatalogObjectRecord,
    ConceptBindingDraft,
    ConceptBindingRecord,
    DocumentKgLinkDraft,
    DocumentKgLinkRecord,
    ObjectAliasRecord,
    ObjectDefinitionRecord,
    ObjectStewardRecord,
    PlaneActor,
    PlaneEnvelope,
    ScoreReferenceRecord,
)

from .catalog_plane_store import (
    get_catalog_plane_store,
    reset_memory_catalog_plane,
    restore_memory_catalog_plane,
    snapshot_memory_catalog_plane,
)
from .policy import evaluate


def reset_catalog_plane() -> None:
    """Clear in-memory plane state so tests do not leak across cases."""

    reset_memory_catalog_plane()


def snapshot_catalog_plane() -> dict[str, CatalogObjectRecord]:
    """Copy current in-memory plane rows for test isolation."""

    return snapshot_memory_catalog_plane()


def restore_catalog_plane(snapshot: dict[str, CatalogObjectRecord]) -> None:
    """Replace in-memory plane rows with a previously captured snapshot."""

    restore_memory_catalog_plane(snapshot)


def _now() -> datetime:
    """Return an aware UTC timestamp."""

    return datetime.now(timezone.utc)


def _child_id() -> str:
    """Allocate a child-row identifier."""

    return str(uuid4())


def _next_action_for_object(record: CatalogObjectRecord) -> str:
    """Tell the buyer the useful next call after seeing one object."""

    if not record.document_kg_links:
        return (
            f"다음으로 POST /plane/catalog-objects/{record.catalog_object_id}/document-kg-links "
            "에 naruon content_node 또는 project_graph_object id를 보내 "
            "이 glossary/catalog 객체가 document KG identity를 해석하게 하세요. "
            "문서는 여기에 올리지 마세요 — naruon이 이미 보유합니다."
        )
    if not record.concept_bindings:
        return (
            f"다음으로 POST /plane/catalog-objects/{record.catalog_object_id}/concept-bindings "
            "로 ontology concept key를 붙인 뒤 GET /plane/query?q="
            f"{record.object_slug} 로 용어 검색이 되는지 확인하세요."
        )
    return (
        f"같은 X-CWL-Tenant-Reference로 GET /plane/catalog-objects/{record.catalog_object_id} "
        "를 분석가와 공유하거나, "
        f"GET /plane/query?q={record.object_slug} 로 alias와 document-KG link를 "
        "이 tenant에서 검색하세요."
    )


def _envelope(
    *,
    actor: PlaneActor,
    status: str,
    record: CatalogObjectRecord | None = None,
    records: list[CatalogObjectRecord] | None = None,
    customer_next_action: str | None = None,
) -> PlaneEnvelope:
    """Build a buyer envelope that always includes the next action."""

    items = records if records is not None else ([record] if record is not None else [])
    action = customer_next_action
    if action is None and record is not None:
        action = _next_action_for_object(record)
    if action is None:
        action = (
            "같은 X-CWL-Tenant-Reference로 POST /plane/catalog-objects 를 호출해 "
            "document KG 위의 glossary term 또는 catalog dataset을 등록하세요."
        )
    return PlaneEnvelope(
        status=status,
        tenant_reference=actor.tenant_reference,
        access_purpose=actor.access_purpose,
        customer_next_action=action,
        catalog_object=record,
        catalog_objects=items,
        count=len(items),
    )


def _govern(actor: PlaneActor, *, mutate: bool) -> str:
    """Reuse the existing policy helper without adding a GRC registry or masking.

    Create uses ``action=create`` (admin). List/get/query use ``action=search``
    with resource ``catalog`` so ``evaluate`` never looks up a Dataset id.
    Steward names stay in the envelope unmasked.
    """

    decision = evaluate(
        subject=actor.subject,
        resource="plane" if mutate else "catalog",
        action="create" if mutate else "search",
        purpose=actor.access_purpose,
    )
    if decision.effect != "allow":
        raise PermissionError(decision.reason)
    return decision.decision_id


def _assert_unique_children(request: CatalogObjectCreateRequest) -> None:
    """Reject duplicate alias/link/binding keys that SQL UNIQUE would refuse."""

    alias_keys = [(row.alias_text, row.alias_language) for row in request.aliases]
    if len(alias_keys) != len(set(alias_keys)):
        raise ValueError("duplicate object alias in this catalog object")
    link_keys = [(row.source_system, row.source_object_id) for row in request.document_kg_links]
    if len(link_keys) != len(set(link_keys)):
        raise ValueError("duplicate document-KG link in this catalog object")
    binding_keys = [(row.concept_key, row.binding_role) for row in request.concept_bindings]
    if len(binding_keys) != len(set(binding_keys)):
        raise ValueError("duplicate concept binding in this catalog object")


def _new_record(actor: PlaneActor, request: CatalogObjectCreateRequest) -> CatalogObjectRecord:
    """Build a catalog object and 3NF children from a buyer create payload."""

    catalog_object_id = CatalogObjectRecord.new_id()
    recorded_at = _now()
    return CatalogObjectRecord(
        catalog_object_id=catalog_object_id,
        tenant_reference=actor.tenant_reference,
        object_kind=request.object_kind,
        object_slug=request.object_slug,
        display_title=request.display_title,
        object_status=request.object_status,
        created_by_subject=actor.subject,
        created_at=recorded_at,
        updated_at=recorded_at,
        definition=ObjectDefinitionRecord(
            definition_id=_child_id(),
            catalog_object_id=catalog_object_id,
            definition_text=request.definition_text,
            preferred_language=request.preferred_language,
            definition_status="current",
            recorded_at=recorded_at,
        ),
        steward=ObjectStewardRecord(
            steward_record_id=_child_id(),
            catalog_object_id=catalog_object_id,
            steward_subject=actor.subject,
            steward_display_name=request.steward_display_name,
            recorded_at=recorded_at,
        ),
        aliases=[
            ObjectAliasRecord(
                alias_id=_child_id(),
                catalog_object_id=catalog_object_id,
                alias_text=alias.alias_text,
                alias_language=alias.alias_language,
            )
            for alias in request.aliases
        ],
        document_kg_links=[
            DocumentKgLinkRecord(
                document_kg_link_id=_child_id(),
                catalog_object_id=catalog_object_id,
                source_system=link.source_system,
                source_object_kind=link.source_object_kind,
                source_object_id=link.source_object_id,
                provenance_uri=link.provenance_uri,
                link_status="active",
                recorded_at=recorded_at,
            )
            for link in request.document_kg_links
        ],
        concept_bindings=[
            ConceptBindingRecord(
                binding_id=_child_id(),
                catalog_object_id=catalog_object_id,
                concept_key=binding.concept_key,
                binding_role=binding.binding_role,
                recorded_at=recorded_at,
            )
            for binding in request.concept_bindings
        ],
        score_references=[
            ScoreReferenceRecord(
                score_reference_id=_child_id(),
                catalog_object_id=catalog_object_id,
                score_system=reference.score_system,
                score_endpoint=reference.score_endpoint,
                recorded_at=recorded_at,
            )
            for reference in request.score_references
        ],
    )


def create_catalog_object(actor: PlaneActor, request: CatalogObjectCreateRequest) -> PlaneEnvelope:
    """Persist a tenant-scoped catalog object and its 3NF children.

    Parameters
    ----------
    actor:
        Fail-closed Keyverse binding for this request.
    request:
        Buyer create payload.

    Returns
    -------
    PlaneEnvelope
        Created object plus the buyer's next action.

    Raises
    ------
    PermissionError
        When the actor cannot mutate the plane.
    ValueError
        When the slug already exists in the tenant.
    """

    decision_id = _govern(actor, mutate=True)
    _assert_unique_children(request)
    record = _new_record(actor, request)
    get_catalog_plane_store().insert_catalog_object(record)
    envelope = _envelope(actor=actor, status="created", record=record)
    envelope.policy_decision_id = decision_id
    return envelope


def list_catalog_objects(
    actor: PlaneActor,
    *,
    object_kind: str | None = None,
) -> PlaneEnvelope:
    """List catalog objects visible to the bound tenant only."""

    decision_id = _govern(actor, mutate=False)
    items = get_catalog_plane_store().list_catalog_objects(
        tenant_reference=actor.tenant_reference,
        object_kind=object_kind,
    )
    items.sort(key=lambda row: row.display_title)
    next_action = (
        "다음으로 GET /plane/catalog-objects/{catalog_object_id} 로 steward가 "
        "다룰 객체를 열거나, POST /plane/catalog-objects 로 document KG 위의 "
        "glossary term을 등록하세요."
        if items
        else (
            "이 tenant에는 catalog object가 없습니다. admin으로 "
            "POST /plane/catalog-objects 를 호출해 첫 glossary term 또는 "
            "catalog dataset을 등록하세요."
        )
    )
    envelope = _envelope(
        actor=actor,
        status="listed",
        records=items,
        customer_next_action=next_action,
    )
    envelope.policy_decision_id = decision_id
    return envelope


def get_catalog_object(actor: PlaneActor, catalog_object_id: str) -> PlaneEnvelope:
    """Return one catalog object if it belongs to the bound tenant."""

    decision_id = _govern(actor, mutate=False)
    record = get_catalog_plane_store().get_catalog_object(
        tenant_reference=actor.tenant_reference,
        catalog_object_id=catalog_object_id,
    )
    if record is None:
        raise KeyError("catalog object not found in this tenant")
    envelope = _envelope(actor=actor, status="retrieved", record=record)
    envelope.policy_decision_id = decision_id
    return envelope


def attach_document_kg_link(
    actor: PlaneActor,
    catalog_object_id: str,
    source_system: str,
    source_object_kind: str,
    source_object_id: str,
    provenance_uri: str | None = None,
) -> PlaneEnvelope:
    """Attach an opaque document-KG reference to an existing catalog object."""

    decision_id = _govern(actor, mutate=True)
    draft = DocumentKgLinkDraft(
        source_system=source_system,  # type: ignore[arg-type]
        source_object_kind=source_object_kind,  # type: ignore[arg-type]
        source_object_id=source_object_id,
        provenance_uri=provenance_uri,
    )
    recorded_at = _now()
    snapshot = get_catalog_plane_store().attach_document_kg_link(
        tenant_reference=actor.tenant_reference,
        catalog_object_id=catalog_object_id,
        link=DocumentKgLinkRecord(
            document_kg_link_id=_child_id(),
            catalog_object_id=catalog_object_id,
            source_system=draft.source_system,
            source_object_kind=draft.source_object_kind,
            source_object_id=draft.source_object_id,
            provenance_uri=draft.provenance_uri,
            link_status="active",
            recorded_at=recorded_at,
        ),
    )
    if snapshot is None:
        raise KeyError("catalog object not found in this tenant")
    envelope = _envelope(actor=actor, status="linked", record=snapshot)
    envelope.policy_decision_id = decision_id
    return envelope


def attach_concept_binding(
    actor: PlaneActor,
    catalog_object_id: str,
    concept_key: str,
    binding_role: str = "preferred",
) -> PlaneEnvelope:
    """Attach an ontology concept key to an existing catalog object."""

    decision_id = _govern(actor, mutate=True)
    draft = ConceptBindingDraft(concept_key=concept_key, binding_role=binding_role)  # type: ignore[arg-type]
    recorded_at = _now()
    snapshot = get_catalog_plane_store().attach_concept_binding(
        tenant_reference=actor.tenant_reference,
        catalog_object_id=catalog_object_id,
        binding=ConceptBindingRecord(
            binding_id=_child_id(),
            catalog_object_id=catalog_object_id,
            concept_key=draft.concept_key,
            binding_role=draft.binding_role,
            recorded_at=recorded_at,
        ),
    )
    if snapshot is None:
        raise KeyError("catalog object not found in this tenant")
    envelope = _envelope(actor=actor, status="bound", record=snapshot)
    envelope.policy_decision_id = decision_id
    return envelope


def query_catalog_objects(actor: PlaneActor, query: str) -> PlaneEnvelope:
    """Search title, slug, aliases, concept keys, and document-KG ids in-tenant."""

    decision_id = _govern(actor, mutate=False)
    needle = query.strip().lower()
    if not needle:
        raise ValueError("query text is required")

    matches = get_catalog_plane_store().query_catalog_objects(
        tenant_reference=actor.tenant_reference,
        query_text=needle,
    )
    matches.sort(key=lambda row: row.display_title)
    next_action = (
        "다음으로 GET /plane/catalog-objects/{catalog_object_id} 로 매칭된 객체를 "
        "열고, naruon content_node가 없으면 document-KG link를 추가하세요."
        if matches
        else (
            "이 tenant에서 일치하는 객체가 없습니다. X-CWL-Tenant-Reference를 "
            "확인한 뒤 POST /plane/catalog-objects 로 glossary term을 등록하세요."
        )
    )
    envelope = _envelope(
        actor=actor,
        status="queried",
        records=matches,
        customer_next_action=next_action,
    )
    envelope.policy_decision_id = decision_id
    return envelope
