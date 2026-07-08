"""Request/response models for the graph + semantic-search API surface."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class GraphNodeRequest(BaseModel):
    node_id: str = Field(min_length=1)
    kind: str = Field(min_length=1, description="node label, e.g. concept/dataset/column")
    label: Optional[str] = None
    properties: Dict[str, Any] = Field(default_factory=dict)
    text: Optional[str] = Field(
        default=None,
        description="text to embed for semantic search; falls back to label/node_id",
    )
    actor: str = Field(default="anonymous", description="authenticated subject for authz")


class GraphEdgeRequest(BaseModel):
    edge_type: str = Field(min_length=1, description="relationship, e.g. broader/related/mapping/lineage")
    source_id: str = Field(min_length=1)
    target_id: str = Field(min_length=1)
    properties: Dict[str, Any] = Field(default_factory=dict)
    actor: str = Field(default="anonymous", description="authenticated subject for authz")


class OntologyConceptRequest(BaseModel):
    concept: str = Field(min_length=1)
    definition: str = ""
    aliases: List[str] = Field(default_factory=list)
    broader: Optional[str] = None
    narrower: List[str] = Field(default_factory=list)
    related: List[str] = Field(default_factory=list)
    multilingual: List[str] = Field(default_factory=list)
    actor: str = Field(default="anonymous", description="authenticated subject for authz")


class GraphTraversalRequest(BaseModel):
    """Safe, parameterized traversal request.

    Raw openCypher is intentionally NOT accepted: the traversal is expressed as a
    start node id + relationship-type allowlist + direction + bounded depth, and
    the cypher is built server-side with bound parameters.
    """

    start_id: str = Field(min_length=1)
    edge_types: Optional[List[str]] = Field(
        default=None, description="filter to these relationship types; null = all"
    )
    direction: str = Field(default="both", pattern="^(out|in|both)$")
    max_depth: int = Field(default=2, ge=1, le=6)
    actor: str = Field(default="anonymous", description="authenticated subject for authz")


class SemanticSearchRequest(BaseModel):
    query: str = Field(min_length=1)
    kind: Optional[str] = Field(default=None, description="restrict to a node kind")
    limit: int = Field(default=5, ge=1, le=50)
    actor: str = Field(default="anonymous", description="authenticated subject for authz")
