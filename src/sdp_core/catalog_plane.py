"""Contracts for the ontology/catalog plane above the document knowledge graph.

This module is the library-layer source of truth for buyer-facing catalog
objects. It does not ingest DiskSage batches, store document bodies, or
register GRC policies. Document-KG identifiers are opaque foreign references.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Literal, get_args
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


ObjectKind = Literal["glossary_term", "catalog_dataset", "concept_asset"]
ObjectStatus = Literal["draft", "published", "deprecated"]
BindingRole = Literal["preferred", "related", "broader", "narrower"]
SourceSystem = Literal["naruon", "disksage", "commons"]
SourceObjectKind = Literal[
    "content_node",
    "project_graph_object",
    "catalog_batch_ref",
    "file_candidate",
]
ScoreSystem = Literal["tepp", "commons"]
AccessPurpose = Literal[
    "catalog_browse",
    "glossary_stewardship",
    "ontology_query",
    "document_kg_alignment",
]
OBJECT_KINDS = get_args(ObjectKind)
OBJECT_STATUSES = get_args(ObjectStatus)
BINDING_ROLES = get_args(BindingRole)
SOURCE_SYSTEMS = get_args(SourceSystem)
SOURCE_OBJECT_KINDS = get_args(SourceObjectKind)
SCORE_SYSTEMS = get_args(ScoreSystem)
ACCESS_PURPOSES = get_args(AccessPurpose)
_OPAQUE_ID_RE = r"^[A-Za-z0-9._:-]+$"


def _reject_local_path(value: str, field_name: str) -> str:
    """Reject filesystem or file-URI tokens so the plane never stores a path.

    Parameters
    ----------
    value:
        Caller-supplied identifier or URI fragment.
    field_name:
        Field name used in the validation error.

    Returns
    -------
    str
        The original value when it is path-free.

    Raises
    ------
    ValueError
        If the value looks like a local path or ``file:`` URI.
    """

    if re.fullmatch(_OPAQUE_ID_RE, value) is None:
        raise ValueError(f"{field_name} must be an opaque document-KG id, not a filesystem path")
    return value


class ObjectAliasDraft(BaseModel):
    """One alias row for a catalog object (3NF; not an embedded JSON list)."""

    alias_text: str = Field(min_length=1, max_length=256)
    alias_language: str = Field(min_length=2, max_length=16)


class DocumentKgLinkDraft(BaseModel):
    """Opaque pointer to a naruon/DiskSage/commons object that already exists.

    The plane does not copy document content or run DiskSage ingest/preview.
    """

    source_system: SourceSystem
    source_object_kind: SourceObjectKind
    source_object_id: str = Field(min_length=1, max_length=256)
    provenance_uri: str | None = Field(default=None, max_length=512)

    @field_validator("source_object_id")
    @classmethod
    def source_object_id_is_opaque(cls, value: str) -> str:
        """Keep document-KG identifiers path-free."""

        return _reject_local_path(value, "source_object_id")

    @field_validator("provenance_uri")
    @classmethod
    def provenance_uri_is_http(cls, value: str | None) -> str | None:
        """Allow only http(s) PROV citations, never file URIs."""

        if value is None:
            return value
        if not value.startswith("https://"):
            raise ValueError("provenance_uri must be an https citation")
        return value


class ConceptBindingDraft(BaseModel):
    """Link from a catalog object to an ontology concept key."""

    concept_key: str = Field(min_length=1, max_length=256)
    binding_role: BindingRole = "preferred"


class ScoreReferenceDraft(BaseModel):
    """Pointer to a commons/TEPP score endpoint. SDP does not score items."""

    score_system: ScoreSystem
    score_endpoint: str = Field(min_length=8, max_length=512)

    @field_validator("score_endpoint")
    @classmethod
    def score_endpoint_is_http(cls, value: str) -> str:
        """Scores are consumed over REST; local files are rejected."""

        if not value.startswith("https://"):
            raise ValueError("score_endpoint must be an https TEPP/commons URL")
        return value


class CatalogObjectCreateRequest(BaseModel):
    """Buyer payload that registers one catalog/ontology object in a tenant."""

    object_kind: ObjectKind
    object_slug: str = Field(min_length=2, max_length=128, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    display_title: str = Field(min_length=1, max_length=256)
    definition_text: str = Field(min_length=1, max_length=4000)
    preferred_language: str = Field(default="ko", min_length=2, max_length=16)
    steward_display_name: str = Field(min_length=1, max_length=256)
    aliases: list[ObjectAliasDraft] = Field(default_factory=list, max_length=32)
    document_kg_links: list[DocumentKgLinkDraft] = Field(default_factory=list, max_length=32)
    concept_bindings: list[ConceptBindingDraft] = Field(default_factory=list, max_length=32)
    score_references: list[ScoreReferenceDraft] = Field(default_factory=list, max_length=8)
    object_status: ObjectStatus = "published"


class ObjectAliasRecord(ObjectAliasDraft):
    """Persisted alias row."""

    alias_id: str
    catalog_object_id: str


class ObjectDefinitionRecord(BaseModel):
    """Persisted definition row, separate from catalog-object identity."""

    definition_id: str
    catalog_object_id: str
    definition_text: str
    preferred_language: str
    definition_status: str
    recorded_at: datetime


class DocumentKgLinkRecord(DocumentKgLinkDraft):
    """Persisted document-KG reference row."""

    document_kg_link_id: str
    catalog_object_id: str
    link_status: str
    recorded_at: datetime


class ConceptBindingRecord(ConceptBindingDraft):
    """Persisted concept-binding row."""

    binding_id: str
    catalog_object_id: str
    recorded_at: datetime


class ScoreReferenceRecord(ScoreReferenceDraft):
    """Persisted commons/TEPP score pointer."""

    score_reference_id: str
    catalog_object_id: str
    recorded_at: datetime


class ObjectStewardRecord(BaseModel):
    """Steward identity kept usable (purpose-limited; never masked)."""

    steward_record_id: str
    catalog_object_id: str
    steward_subject: str
    steward_display_name: str
    recorded_at: datetime


class CatalogObjectRecord(BaseModel):
    """Tenant-scoped catalog object plus its 3NF children."""

    catalog_object_id: str
    tenant_reference: str
    object_kind: ObjectKind
    object_slug: str
    display_title: str
    object_status: ObjectStatus
    created_by_subject: str
    created_at: datetime
    updated_at: datetime
    definition: ObjectDefinitionRecord
    steward: ObjectStewardRecord
    aliases: list[ObjectAliasRecord] = Field(default_factory=list)
    document_kg_links: list[DocumentKgLinkRecord] = Field(default_factory=list)
    concept_bindings: list[ConceptBindingRecord] = Field(default_factory=list)
    score_references: list[ScoreReferenceRecord] = Field(default_factory=list)

    @staticmethod
    def new_id() -> str:
        """Return a new catalog-object identifier."""

        return str(uuid4())


class PlaneActor(BaseModel):
    """Keyverse-bound actor that has already passed tenant fail-closed checks."""

    subject: str
    tenant_reference: str
    roles: list[str] = Field(default_factory=list)
    access_purpose: AccessPurpose
    binding_source: str

    def can_mutate(self) -> bool:
        """Return whether the actor may create catalog-plane objects."""

        return bool({"admin", "platform-admin"}.intersection(self.roles))

    def can_read(self) -> bool:
        """Return whether the actor may list or get catalog-plane objects."""

        return bool({"data-analyst", "admin", "platform-admin", "security"}.intersection(self.roles))


class PlaneEnvelope(BaseModel):
    """Buyer-facing envelope with an explicit next action."""

    status: str
    tenant_reference: str
    access_purpose: str
    pii_handling: str = "usable_purpose_limited_no_masking"
    policy_decision_id: str | None = None
    customer_next_action: str
    catalog_object: CatalogObjectRecord | None = None
    catalog_objects: list[CatalogObjectRecord] = Field(default_factory=list)
    count: int = 0
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
