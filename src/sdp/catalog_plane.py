"""In-memory ontology/catalog plane sitting above the document knowledge graph.

Buyers create, list, get, and query catalog objects that *reference* naruon
content-graph / project-graph identifiers (and optional DiskSage or commons
pointers). This module does not ingest files, preview bytes, compute TEPP
scores, or keep a local GRC policy registry.
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


_CATALOG_OBJECTS: dict[str, CatalogObjectRecord] = {}


def reset_catalog_plane() -> None:
    """Clear in-memory plane state so tests do not leak across cases."""

    _CATALOG_OBJECTS.clear()


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
            f"POST /plane/catalog-objects/{record.catalog_object_id}/document-kg-links "
            "with a naruon content_node or project_graph_object id so this "
            "glossary/catalog object can resolve document-KG identity. Do not "
            "upload the document here — naruon already holds it."
        )
    if not record.concept_bindings:
        return (
            f"POST /plane/catalog-objects/{record.catalog_object_id}/concept-bindings "
            "to attach an ontology concept key, then GET /plane/query?q="
            f"{record.object_slug} to confirm buyers can find it by term."
        )
    return (
        f"Share GET /plane/catalog-objects/{record.catalog_object_id} with the "
        "same X-CWL-Tenant-Reference so analysts can browse this object, or "
        f"GET /plane/query?q={record.object_slug} to search aliases and "
        "document-KG links in this tenant."
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
            "POST /plane/catalog-objects to register a glossary term or catalog "
            "dataset above the document KG, using the same X-CWL-Tenant-Reference."
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


def _require_mutate(actor: PlaneActor) -> None:
    """Refuse writes unless the bound actor has an admin role."""

    if not actor.can_mutate():
        raise PermissionError("catalog-plane writes require an admin Keyverse role")


def _require_read(actor: PlaneActor) -> None:
    """Refuse reads unless the bound actor has a reader role."""

    if not actor.can_read():
        raise PermissionError("catalog-plane reads require a Keyverse reader role")


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

    _require_mutate(actor)
    for existing in _CATALOG_OBJECTS.values():
        if (
            existing.tenant_reference == actor.tenant_reference
            and existing.object_slug == request.object_slug
        ):
            raise ValueError("object_slug already exists in this tenant")

    catalog_object_id = CatalogObjectRecord.new_id()
    recorded_at = _now()
    record = CatalogObjectRecord(
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
    _CATALOG_OBJECTS[catalog_object_id] = record
    return _envelope(actor=actor, status="created", record=record)


def list_catalog_objects(
    actor: PlaneActor,
    *,
    object_kind: str | None = None,
) -> PlaneEnvelope:
    """List catalog objects visible to the bound tenant only."""

    _require_read(actor)
    items = [
        record
        for record in _CATALOG_OBJECTS.values()
        if record.tenant_reference == actor.tenant_reference
        and (object_kind is None or record.object_kind == object_kind)
    ]
    items.sort(key=lambda row: row.display_title)
    next_action = (
        "Open GET /plane/catalog-objects/{catalog_object_id} for the object a "
        "steward should govern, or POST /plane/catalog-objects to register a "
        "new glossary term above the document KG."
        if items
        else (
            "No catalog objects exist for this tenant yet. POST "
            "/plane/catalog-objects as an admin to register the first glossary "
            "term or catalog dataset above the document KG."
        )
    )
    return _envelope(
        actor=actor,
        status="listed",
        records=items,
        customer_next_action=next_action,
    )


def get_catalog_object(actor: PlaneActor, catalog_object_id: str) -> PlaneEnvelope:
    """Return one catalog object if it belongs to the bound tenant."""

    _require_read(actor)
    record = _CATALOG_OBJECTS.get(catalog_object_id)
    if record is None or record.tenant_reference != actor.tenant_reference:
        raise KeyError("catalog object not found in this tenant")
    return _envelope(actor=actor, status="retrieved", record=record)


def attach_document_kg_link(
    actor: PlaneActor,
    catalog_object_id: str,
    source_system: str,
    source_object_kind: str,
    source_object_id: str,
    provenance_uri: str | None = None,
) -> PlaneEnvelope:
    """Attach an opaque document-KG reference to an existing catalog object."""

    _require_mutate(actor)
    envelope = get_catalog_object(actor, catalog_object_id)
    record = envelope.catalog_object
    if record is None:  # pragma: no cover - get_catalog_object always sets it
        raise KeyError("catalog object not found in this tenant")

    draft = DocumentKgLinkDraft(
        source_system=source_system,  # type: ignore[arg-type]
        source_object_kind=source_object_kind,  # type: ignore[arg-type]
        source_object_id=source_object_id,
        provenance_uri=provenance_uri,
    )
    recorded_at = _now()
    record.document_kg_links.append(
        DocumentKgLinkRecord(
            document_kg_link_id=_child_id(),
            catalog_object_id=record.catalog_object_id,
            source_system=draft.source_system,
            source_object_kind=draft.source_object_kind,
            source_object_id=draft.source_object_id,
            provenance_uri=draft.provenance_uri,
            link_status="active",
            recorded_at=recorded_at,
        )
    )
    record.updated_at = recorded_at
    return _envelope(actor=actor, status="linked", record=record)


def attach_concept_binding(
    actor: PlaneActor,
    catalog_object_id: str,
    concept_key: str,
    binding_role: str = "preferred",
) -> PlaneEnvelope:
    """Attach an ontology concept key to an existing catalog object."""

    _require_mutate(actor)
    envelope = get_catalog_object(actor, catalog_object_id)
    record = envelope.catalog_object
    if record is None:  # pragma: no cover
        raise KeyError("catalog object not found in this tenant")

    draft = ConceptBindingDraft(concept_key=concept_key, binding_role=binding_role)  # type: ignore[arg-type]
    recorded_at = _now()
    record.concept_bindings.append(
        ConceptBindingRecord(
            binding_id=_child_id(),
            catalog_object_id=record.catalog_object_id,
            concept_key=draft.concept_key,
            binding_role=draft.binding_role,
            recorded_at=recorded_at,
        )
    )
    record.updated_at = recorded_at
    return _envelope(actor=actor, status="bound", record=record)


def query_catalog_objects(actor: PlaneActor, query: str) -> PlaneEnvelope:
    """Search title, slug, aliases, concept keys, and document-KG ids in-tenant."""

    _require_read(actor)
    needle = query.strip().lower()
    if not needle:
        raise ValueError("query text is required")

    matches: list[CatalogObjectRecord] = []
    for record in _CATALOG_OBJECTS.values():
        if record.tenant_reference != actor.tenant_reference:
            continue
        haystacks = [
            record.display_title,
            record.object_slug,
            record.definition.definition_text,
            record.steward.steward_display_name,
            *[alias.alias_text for alias in record.aliases],
            *[binding.concept_key for binding in record.concept_bindings],
            *[link.source_object_id for link in record.document_kg_links],
        ]
        if any(needle in value.lower() for value in haystacks):
            matches.append(record)
    matches.sort(key=lambda row: row.display_title)
    next_action = (
        "Open GET /plane/catalog-objects/{catalog_object_id} for the match a "
        "buyer should govern, then attach a missing document-KG link if the "
        "term still has no naruon content_node."
        if matches
        else (
            "No tenant-local match. Confirm the Keyverse tenant header, then "
            "POST /plane/catalog-objects to register the missing glossary term."
        )
    )
    return _envelope(
        actor=actor,
        status="queried",
        records=matches,
        customer_next_action=next_action,
    )
