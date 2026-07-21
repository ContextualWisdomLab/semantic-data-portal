"""Persistence + graph + vector engine for the Semantic Data Portal.

Two interchangeable backends implement :class:`GraphStore`:

* :class:`InMemoryGraphStore` -- zero-dependency default. Keeps the service
  runnable standalone, in CI, and as an embedded submodule with no database.
  Graph traversal is a BFS; semantic search is exact cosine KNN.

* :class:`PostgresGraphStore` -- production backend on a single Postgres
  instance running **Apache AGE** (property graph, openCypher) for traversal
  and **pgvector** for semantic KNN. Selected automatically when a database DSN
  is provided at bootstrap and the extensions are reachable.

Both back the ingestion, traversal and semantic-search endpoints identically so
the same tests exercise the contract regardless of backend.
"""

from __future__ import annotations

import json
import logging
import re
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from .config import AppConfig, get_app_config, load_bootstrap
from .embeddings import cosine_similarity, embed_text


# --- Shared value objects -----------------------------------------------------


@dataclass
class GraphNode:
    node_id: str
    kind: str
    label: str
    properties: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "kind": self.kind,
            "label": self.label,
            "properties": self.properties,
        }


@dataclass
class GraphEdge:
    edge_type: str
    source_id: str
    target_id: str
    properties: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "edge_type": self.edge_type,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "properties": self.properties,
        }


def _normalize(value: str) -> str:
    return value.strip().replace("_", " ").lower()


def _is_governed_file_identifier(value: Any) -> bool:
    text = str(value or "")
    return text.startswith("urn:sha256:") or text.startswith("urn:cwl:distribution:")


def _validate_concept_file_boundaries(payload: Dict[str, Any]) -> None:
    values = [
        payload.get("concept"),
        payload.get("broader"),
        *list(payload.get("narrower", [])),
        *list(payload.get("related", [])),
        *list(payload.get("aliases", [])),
        *list(payload.get("multilingual", [])),
    ]
    if any(_is_governed_file_identifier(value) for value in values if value is not None):
        raise ValueError("ontology concepts cannot use governed file identifiers")


_logger = logging.getLogger(__name__)

# openCypher / AGE relationship types occupy an *identifier* position in the
# graph mutation/traversal statements and therefore CANNOT be bound as a query
# parameter. They are strict-allowlisted against ``^[A-Za-z_][A-Za-z0-9_]*$`` and
# rejected outright otherwise, so an arbitrary string (e.g. one carrying cypher
# or SQL breakout characters) can never reach the statement text. Both backends
# enforce this identically for behaviour parity.
_AGE_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# Fixed identifier alphabet used to rebuild validated labels character by
# character. Every returned label is provably composed of these constant
# strings only, so callers may splice it into server-built cypher text; this
# also makes the sanitization structural (visible to SAST taint tracking)
# instead of relying on the regex guard alone.
_AGE_LABEL_CHARS = {c: c for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_"}


def _relationship_label(edge_type: str) -> str:
    """Validate ``edge_type`` as a safe identifier and return its AGE label.

    Raises :class:`ValueError` when ``edge_type`` is not a bare identifier. The
    returned label is upper-cased to match the AGE relationship-type convention
    used across the seed data (``BROADER``/``NARROWER``/``HAS_COLUMN``/...) and
    rebuilt from the fixed ``_AGE_LABEL_CHARS`` alphabet.
    """

    if not _AGE_IDENTIFIER_RE.match(edge_type):
        raise ValueError(f"invalid relationship type: {edge_type!r}")
    return "".join(_AGE_LABEL_CHARS[ch] for ch in edge_type.upper())


# --- Backend contract ---------------------------------------------------------


class GraphStore(ABC):
    """Backend contract shared by the in-memory and Postgres implementations."""

    dimension: int

    @abstractmethod
    def readiness(self) -> Dict[str, Any]:  # pragma: no cover - overridden
        """Return whether the backend and its required capabilities are ready."""

        raise NotImplementedError

    @abstractmethod
    def upsert_node(
        self,
        node_id: str,
        kind: str,
        *,
        label: Optional[str] = None,
        properties: Optional[Dict[str, Any]] = None,
        text: Optional[str] = None,
    ) -> GraphNode:
        """Create or update one graph node and return its persisted value."""

        raise NotImplementedError

    @abstractmethod
    def upsert_edge(
        self,
        edge_type: str,
        source_id: str,
        target_id: str,
        *,
        properties: Optional[Dict[str, Any]] = None,
    ) -> GraphEdge:
        """Create or update one directed graph edge."""

        raise NotImplementedError

    @abstractmethod
    def upsert_concept(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Create or update an ontology concept and its graph relationships."""

        raise NotImplementedError

    @abstractmethod
    def get_node(self, node_id: str) -> Optional[GraphNode]:
        """Return a node by identifier, or ``None`` when it does not exist."""

        raise NotImplementedError

    @abstractmethod
    def concept_graph(self, term: str) -> Dict[str, Any]:
        """Return the concept-centered graph for ``term``."""

        raise NotImplementedError

    @abstractmethod
    def traverse(
        self,
        start_id: str,
        *,
        edge_types: Optional[List[str]] = None,
        direction: str = "both",
        max_depth: int = 2,
    ) -> Dict[str, Any]:
        """Traverse from ``start_id`` through a bounded relationship set."""

        raise NotImplementedError

    @abstractmethod
    def semantic_search(
        self,
        query: str,
        *,
        kind: Optional[str] = None,
        limit: int = 5,
        tenant_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return the nearest graph nodes for a semantic query."""

        raise NotImplementedError

    @abstractmethod
    def stats(self) -> Dict[str, int]:
        """Return backend object counts suitable for readiness diagnostics."""

        raise NotImplementedError


# --- In-memory backend --------------------------------------------------------


class InMemoryGraphStore(GraphStore):
    def __init__(
        self,
        config: Optional[AppConfig] = None,
        *,
        embedder: Optional[Callable[[str], List[float]]] = None,
    ) -> None:
        self._config = config or get_app_config()
        self.dimension = self._config.embedding_dimension
        self._embedder = embedder or (
            lambda text: embed_text(text, self.dimension)
        )
        self._external_embedder = embedder is not None
        self._nodes: Dict[str, GraphNode] = {}
        self._edges: List[GraphEdge] = []
        self._embeddings: Dict[str, List[float]] = {}
        self._concepts: Dict[str, Dict[str, Any]] = {}
        self._alias_to_concept: Dict[str, str] = {}

    # ingestion ---------------------------------------------------------------

    def upsert_node(
        self,
        node_id: str,
        kind: str,
        *,
        label: Optional[str] = None,
        properties: Optional[Dict[str, Any]] = None,
        text: Optional[str] = None,
    ) -> GraphNode:
        node = GraphNode(
            node_id=node_id,
            kind=kind,
            label=label or node_id,
            properties=dict(properties or {}),
        )
        self._nodes[node_id] = node
        embed_source = text or label or node_id
        vector = [float(component) for component in self._embedder(embed_source)]
        if not vector:
            raise ValueError("embedding vector must not be empty")
        if self._external_embedder and not self._embeddings:
            self.dimension = len(vector)
        if len(vector) != self.dimension:
            raise ValueError(f"embedding dimension must be {self.dimension}")
        self._embeddings[node_id] = vector
        return node

    def upsert_edge(
        self,
        edge_type: str,
        source_id: str,
        target_id: str,
        *,
        properties: Optional[Dict[str, Any]] = None,
    ) -> GraphEdge:
        # Reject non-identifier relationship types for parity with the AGE
        # backend (where the type occupies a cypher identifier position).
        _relationship_label(edge_type)
        for existing in self._edges:
            if (
                existing.edge_type == edge_type
                and existing.source_id == source_id
                and existing.target_id == target_id
            ):
                existing.properties.update(properties or {})
                return existing
        edge = GraphEdge(edge_type, source_id, target_id, dict(properties or {}))
        self._edges.append(edge)
        return edge

    def upsert_concept(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        _validate_concept_file_boundaries(payload)
        concept = payload["concept"].strip()
        record = {
            "concept": concept,
            "definition": payload.get("definition", ""),
            "aliases": list(payload.get("aliases", [])),
            "broader": payload.get("broader"),
            "narrower": list(payload.get("narrower", [])),
            "related": list(payload.get("related", [])),
            "multilingual": list(payload.get("multilingual", [])),
        }
        self._concepts[concept] = record

        # alias index for canonicalisation
        self._alias_to_concept[_normalize(concept)] = concept
        for alias in record["aliases"] + record["multilingual"]:
            self._alias_to_concept[_normalize(alias)] = concept

        # mirror as a graph node with an embedding over concept + definition + aliases
        embed_source = " ".join(
            [concept, record["definition"]] + record["aliases"] + record["multilingual"]
        )
        self.upsert_node(
            concept,
            "concept",
            label=concept,
            properties={
                "definition": record["definition"],
                "aliases": record["aliases"],
                "multilingual": record["multilingual"],
            },
            text=embed_source,
        )
        # edges to related/broader/narrower concepts
        if record["broader"]:
            self.upsert_edge("broader", concept, record["broader"])
        for narrow in record["narrower"]:
            self.upsert_edge("narrower", concept, narrow)
        for related in record["related"]:
            self.upsert_edge("related", concept, related)
        return record

    # reads -------------------------------------------------------------------

    def get_node(self, node_id: str) -> Optional[GraphNode]:
        return self._nodes.get(node_id)

    def _canonical_concept(self, term: str) -> str:
        return self._alias_to_concept.get(_normalize(term), term)

    def concept_graph(self, term: str) -> Dict[str, Any]:
        canonical = self._canonical_concept(term)
        record = self._concepts.get(canonical)
        if not record:
            return {"canonical": term, "not_found": True, "aliases": []}
        dataset_ids = sorted(
            {
                edge.source_id
                for edge in self._edges
                if edge.edge_type == "mapping" and edge.target_id == canonical
            }
        )
        return {
            "canonical": canonical,
            "concept": canonical,
            "definition": record["definition"],
            "aliases": [canonical] + record["aliases"],
            "broader": record["broader"],
            "narrower": record["narrower"],
            "related": record["related"],
            "multilingual": record["multilingual"],
            "dataset_ids": dataset_ids,
        }

    def traverse(
        self,
        start_id: str,
        *,
        edge_types: Optional[List[str]] = None,
        direction: str = "both",
        max_depth: int = 2,
    ) -> Dict[str, Any]:
        if start_id not in self._nodes:
            raise KeyError(f"node not found: {start_id}")
        if edge_types:
            for etype in edge_types:
                _relationship_label(etype)  # reject bad labels (AGE parity)
        allowed = set(edge_types) if edge_types else None
        visited_nodes: Dict[str, GraphNode] = {start_id: self._nodes[start_id]}
        visited_edges: List[GraphEdge] = []
        seen_edge_keys: set[Tuple[str, str, str]] = set()
        frontier: deque[Tuple[str, int]] = deque([(start_id, 0)])

        while frontier:
            current, depth = frontier.popleft()
            if depth >= max_depth:
                continue
            for edge in self._edges:
                if allowed and edge.edge_type not in allowed:
                    continue
                neighbor: Optional[str] = None
                if direction in {"out", "both"} and edge.source_id == current:
                    neighbor = edge.target_id
                elif direction in {"in", "both"} and edge.target_id == current:
                    neighbor = edge.source_id
                if neighbor is None:
                    continue
                key = (edge.edge_type, edge.source_id, edge.target_id)
                if key not in seen_edge_keys:
                    seen_edge_keys.add(key)
                    visited_edges.append(edge)
                if neighbor not in visited_nodes:
                    node = self._nodes.get(neighbor)
                    if node is None:
                        node = GraphNode(neighbor, "unknown", neighbor)
                    visited_nodes[neighbor] = node
                    frontier.append((neighbor, depth + 1))

        return {
            "start_id": start_id,
            "backend": "in_memory",
            "nodes": [node.as_dict() for node in visited_nodes.values()],
            "edges": [edge.as_dict() for edge in visited_edges],
        }

    def semantic_search(
        self,
        query: str,
        *,
        kind: Optional[str] = None,
        limit: int = 5,
        tenant_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        query_vec = [float(component) for component in self._embedder(query)]
        if len(query_vec) != self.dimension:
            raise ValueError(f"embedding dimension must be {self.dimension}")
        scored: List[Dict[str, Any]] = []
        for node_id, vector in self._embeddings.items():
            node = self._nodes[node_id]
            if kind and node.kind != kind:
                continue
            node_tenant = str(
                node.properties.get("tenant_id")
                or (node.properties.get("file_asset") or {}).get("tenant_id")
                or ""
            )
            if (
                tenant_id is not None
                and node.kind in {"file_asset", "distribution"}
                and node_tenant != tenant_id
            ):
                continue
            score = cosine_similarity(query_vec, vector)
            scored.append(
                {
                    "node_id": node_id,
                    "kind": node.kind,
                    "label": node.label,
                    "score": round(score, 6),
                }
            )
        scored.sort(key=lambda row: row["score"], reverse=True)
        return scored[:limit]

    def readiness(self) -> Dict[str, Any]:
        return {
            "ready": True,
            "backend": "in_memory",
            "database": False,
            "age": False,
            "pgvector": False,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

    def stats(self) -> Dict[str, int]:
        return {
            "nodes": len(self._nodes),
            "edges": len(self._edges),
            "concepts": len(self._concepts),
            "embeddings": len(self._embeddings),
        }


# --- Postgres + Apache AGE + pgvector backend --------------------------------


def _vector_literal(vector: List[float]) -> str:
    return "[" + ",".join(f"{component:.8f}" for component in vector) + "]"


class PostgresGraphStore(GraphStore):
    """Backend on Postgres with Apache AGE (openCypher) and pgvector (KNN)."""

    def __init__(
        self,
        dsn: str,
        config: Optional[AppConfig] = None,
        *,
        embedder: Optional[Callable[[str], List[float]]] = None,
    ) -> None:
        from sqlalchemy import create_engine

        self._config = config or get_app_config()
        self.dimension = self._config.embedding_dimension
        self._embedder = embedder or (
            lambda text: embed_text(text, self.dimension)
        )
        self.graph_name = self._config.graph_name
        self._engine = create_engine(dsn, pool_pre_ping=True, future=True)

    # Every AGE statement needs the ag_catalog search path loaded on the
    # connection first. Called inside an already-open transaction/connection so
    # it does not trigger a conflicting begin().
    def _prepare(self, conn) -> None:
        from sqlalchemy import text

        conn.execute(text("LOAD 'age'"))
        conn.execute(text('SET search_path = ag_catalog, "$user", public'))

    def _cypher(
        self,
        conn,
        query: str,
        columns: str,
        params: Dict[str, Any],
    ) -> List[Tuple]:
        """Execute an openCypher statement via Apache AGE, injection-safe.

        User values are NEVER interpolated into ``query``. They are passed as an
        agtype **parameter map** bound to a real positional SQL parameter, so the
        ``cypher()`` body references them as ``$name`` and they never touch the
        SQL/cypher text. Psycopg's SQL composition quotes the graph name and the
        complete server-built Cypher body as literals. Result declarations are
        selected from a closed map because AGE requires them in SQL syntax and
        they cannot be bound. The agtype parameter map remains a real positional
        driver parameter.
        """

        from psycopg import sql as pg_sql

        result_columns = {
            "v agtype": pg_sql.SQL("v agtype"),
            "node_id agtype, kind agtype, label agtype": pg_sql.SQL(
                "node_id agtype, kind agtype, label agtype"
            ),
        }.get(columns)
        if result_columns is None:
            raise ValueError(f"unsupported AGE result declaration: {columns!r}")

        statement = pg_sql.SQL("SELECT * FROM cypher({}, {}, %s) AS ({})").format(
            pg_sql.Literal(self.graph_name),
            pg_sql.Literal(query),
            result_columns,
        )
        driver_connection = conn.connection.driver_connection
        with driver_connection.cursor() as cursor:
            cursor.execute(statement, (json.dumps(params),))
            return cursor.fetchall()

    def upsert_node(
        self,
        node_id: str,
        kind: str,
        *,
        label: Optional[str] = None,
        properties: Optional[Dict[str, Any]] = None,
        text: Optional[str] = None,
    ) -> GraphNode:
        from sqlalchemy import text as sql

        label = label or node_id
        props = dict(properties or {})
        embed_source = text or label or node_id
        vector = [float(component) for component in self._embedder(embed_source)]
        if len(vector) != self.dimension:
            raise ValueError(f"embedding dimension must be {self.dimension}")
        with self._engine.begin() as conn:
            self._prepare(conn)
            self._cypher(
                conn,
                "MERGE (n:GraphNode {node_id: $node_id}) "
                "SET n.kind = $kind, n.label = $label",
                "v agtype",
                params={"node_id": node_id, "kind": kind, "label": label},
            )
            conn.execute(
                sql(
                    "INSERT INTO graph_nodes (node_id, node_kind, node_label, node_properties) "
                    "VALUES (:id, :kind, :label, CAST(:props AS jsonb)) "
                    "ON CONFLICT (node_id) DO UPDATE SET node_kind = EXCLUDED.node_kind, "
                    "node_label = EXCLUDED.node_label, node_properties = EXCLUDED.node_properties"
                ),
                {"id": node_id, "kind": kind, "label": label, "props": json.dumps(props)},
            )
            conn.execute(
                sql(
                    "INSERT INTO embedding_vectors (node_id, node_kind, embedding) "
                    "VALUES (:id, :kind, CAST(:vec AS vector)) "
                    "ON CONFLICT (node_id) DO UPDATE SET node_kind = EXCLUDED.node_kind, "
                    "embedding = EXCLUDED.embedding"
                ),
                {"id": node_id, "kind": kind, "vec": _vector_literal(vector)},
            )
        return GraphNode(node_id, kind, label, props)

    def upsert_edge(
        self,
        edge_type: str,
        source_id: str,
        target_id: str,
        *,
        properties: Optional[Dict[str, Any]] = None,
    ) -> GraphEdge:
        from sqlalchemy import text as sql

        props = dict(properties or {})
        rel = _relationship_label(edge_type)
        with self._engine.begin() as conn:
            self._prepare(conn)
            self._cypher(
                conn,
                "MERGE (a:GraphNode {node_id: $source_id}) "
                "MERGE (b:GraphNode {node_id: $target_id}) "
                f"MERGE (a)-[r:{rel}]->(b)",
                "v agtype",
                params={"source_id": source_id, "target_id": target_id},
            )
            conn.execute(
                sql(
                    "INSERT INTO graph_edges (edge_type, source_id, target_id, edge_properties) "
                    "VALUES (:etype, :src, :tgt, CAST(:props AS jsonb)) "
                    "ON CONFLICT (edge_type, source_id, target_id) "
                    "DO UPDATE SET edge_properties = EXCLUDED.edge_properties"
                ),
                {
                    "etype": edge_type,
                    "src": source_id,
                    "tgt": target_id,
                    "props": json.dumps(props),
                },
            )
        return GraphEdge(edge_type, source_id, target_id, props)

    def upsert_concept(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        from sqlalchemy import text as sql

        _validate_concept_file_boundaries(payload)
        concept = payload["concept"].strip()
        record = {
            "concept": concept,
            "definition": payload.get("definition", ""),
            "aliases": list(payload.get("aliases", [])),
            "broader": payload.get("broader"),
            "narrower": list(payload.get("narrower", [])),
            "related": list(payload.get("related", [])),
            "multilingual": list(payload.get("multilingual", [])),
        }
        with self._engine.begin() as conn:
            conn.execute(
                sql(
                    "INSERT INTO ontology_concepts "
                    "(concept_key, concept_definition, concept_aliases, concept_broader, "
                    "concept_narrower, concept_related, concept_multilingual) "
                    "VALUES (:key, :definition, CAST(:aliases AS jsonb), :broader, "
                    "CAST(:narrower AS jsonb), CAST(:related AS jsonb), CAST(:multilingual AS jsonb)) "
                    "ON CONFLICT (concept_key) DO UPDATE SET "
                    "concept_definition = EXCLUDED.concept_definition, "
                    "concept_aliases = EXCLUDED.concept_aliases, "
                    "concept_broader = EXCLUDED.concept_broader, "
                    "concept_narrower = EXCLUDED.concept_narrower, "
                    "concept_related = EXCLUDED.concept_related, "
                    "concept_multilingual = EXCLUDED.concept_multilingual"
                ),
                {
                    "key": concept,
                    "definition": record["definition"],
                    "aliases": json.dumps(record["aliases"]),
                    "broader": record["broader"],
                    "narrower": json.dumps(record["narrower"]),
                    "related": json.dumps(record["related"]),
                    "multilingual": json.dumps(record["multilingual"]),
                },
            )
        embed_source = " ".join(
            [concept, record["definition"]] + record["aliases"] + record["multilingual"]
        )
        self.upsert_node(
            concept,
            "concept",
            label=concept,
            properties={"definition": record["definition"], "aliases": record["aliases"]},
            text=embed_source,
        )
        if record["broader"]:
            self.upsert_edge("broader", concept, record["broader"])
        for narrow in record["narrower"]:
            self.upsert_edge("narrower", concept, narrow)
        for related in record["related"]:
            self.upsert_edge("related", concept, related)
        return record

    def get_node(self, node_id: str) -> Optional[GraphNode]:
        from sqlalchemy import text as sql

        with self._engine.connect() as conn:
            row = conn.execute(
                sql(
                    "SELECT node_id, node_kind, node_label, node_properties "
                    "FROM graph_nodes WHERE node_id = :id"
                ),
                {"id": node_id},
            ).fetchone()
        if not row:
            return None
        props = row[3] if isinstance(row[3], dict) else json.loads(row[3] or "{}")
        return GraphNode(row[0], row[1], row[2], props)

    def concept_graph(self, term: str) -> Dict[str, Any]:
        from sqlalchemy import text as sql

        with self._engine.connect() as conn:
            row = conn.execute(
                sql(
                    "SELECT concept_key, concept_definition, concept_aliases, concept_broader, "
                    "concept_narrower, concept_related, concept_multilingual FROM ontology_concepts "
                    "WHERE concept_key = :key OR concept_aliases ? :key OR concept_multilingual ? :key "
                    "LIMIT 1"
                ),
                {"key": term},
            ).fetchone()
            if not row:
                return {"canonical": term, "not_found": True, "aliases": []}

            def _as_list(value: Any) -> List[str]:
                if isinstance(value, list):
                    return value
                return json.loads(value or "[]")

            canonical = row[0]
            dataset_rows = conn.execute(
                sql(
                    "SELECT source_id FROM graph_edges "
                    "WHERE edge_type = 'mapping' AND target_id = :key"
                ),
                {"key": canonical},
            ).fetchall()
        return {
            "canonical": canonical,
            "concept": canonical,
            "definition": row[1],
            "aliases": [canonical] + _as_list(row[2]),
            "broader": row[3],
            "narrower": _as_list(row[4]),
            "related": _as_list(row[5]),
            "multilingual": _as_list(row[6]),
            "dataset_ids": sorted({r[0] for r in dataset_rows}),
        }

    def traverse(
        self,
        start_id: str,
        *,
        edge_types: Optional[List[str]] = None,
        direction: str = "both",
        max_depth: int = 2,
    ) -> Dict[str, Any]:
        # Parity with the in-memory backend: an unknown start node is a 404.
        if self.get_node(start_id) is None:
            raise KeyError(f"node not found: {start_id}")
        # Depth is clamped server-side (never interpolated from a raw value); the
        # API layer also validates it, but bound the identifier-position integer
        # here so the cypher text is always well-formed.
        depth = max(1, min(int(max_depth), self._config.traversal_max_depth))
        with self._engine.connect() as conn:
            self._prepare(conn)
            rel_filter = ""
            if edge_types:
                rels = "|".join(_relationship_label(etype) for etype in edge_types)
                rel_filter = f":{rels}"
            left = "<-" if direction == "in" else "-"
            right = "->" if direction == "out" else "-"
            # start_id is bound as an agtype parameter ($start_id); only the
            # allowlisted relationship filter and the clamped integer depth are
            # interpolated into the (server-built) pattern.
            pattern = (
                "(a:GraphNode {node_id: $start_id})"
                f"{left}[{rel_filter}*1..{depth}]{right}(b:GraphNode)"
            )
            rows = self._cypher(
                conn,
                f"MATCH p = {pattern} RETURN DISTINCT b.node_id, b.kind, b.label",
                "node_id agtype, kind agtype, label agtype",
                params={"start_id": start_id},
            )

        def _clean(value: Any) -> str:
            return str(value).strip('"') if value is not None else ""

        nodes = [{"node_id": _clean(r[0]), "kind": _clean(r[1]), "label": _clean(r[2])} for r in rows]
        node_ids = {n["node_id"] for n in nodes} | {start_id}
        start_node = self.get_node(start_id)
        if start_node and start_node.node_id not in {n["node_id"] for n in nodes}:
            nodes.insert(0, {"node_id": start_node.node_id, "kind": start_node.kind, "label": start_node.label})
        edges = self._edges_within(node_ids, edge_types)
        return {"start_id": start_id, "backend": "postgres_age", "nodes": nodes, "edges": edges}

    def _edges_within(self, node_ids: Iterable[str], edge_types: Optional[List[str]]) -> List[Dict[str, Any]]:
        from sqlalchemy import text as sql

        ids = list(node_ids)
        if not ids:
            return []
        query = (
            "SELECT edge_type, source_id, target_id, edge_properties FROM graph_edges "
            "WHERE source_id = ANY(:ids) AND target_id = ANY(:ids)"
        )
        params: Dict[str, Any] = {"ids": ids}
        if edge_types:
            query += " AND edge_type = ANY(:etypes)"
            params["etypes"] = edge_types
        with self._engine.connect() as conn:
            rows = conn.execute(sql(query), params).fetchall()
        result = []
        for etype, src, tgt, props in rows:
            props_dict = props if isinstance(props, dict) else json.loads(props or "{}")
            result.append(
                {"edge_type": etype, "source_id": src, "target_id": tgt, "properties": props_dict}
            )
        return result

    def semantic_search(
        self,
        query: str,
        *,
        kind: Optional[str] = None,
        limit: int = 5,
        tenant_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        from sqlalchemy import text as sql

        query_vector = [float(component) for component in self._embedder(query)]
        if len(query_vector) != self.dimension:
            raise ValueError(f"embedding dimension must be {self.dimension}")
        vector = _vector_literal(query_vector)
        stmt = (
            "SELECT e.node_id, e.node_kind, n.node_label, "
            "1 - (e.embedding <=> CAST(:vec AS vector)) AS score "
            "FROM embedding_vectors e "
            "LEFT JOIN graph_nodes n ON n.node_id = e.node_id "
        )
        params: Dict[str, Any] = {"vec": vector, "limit": limit}
        conditions: List[str] = []
        if kind:
            conditions.append("e.node_kind = :kind")
            params["kind"] = kind
        if tenant_id is not None:
            conditions.append(
                "(e.node_kind NOT IN ('file_asset', 'distribution') OR "
                "COALESCE(n.node_properties ->> 'tenant_id', "
                "n.node_properties -> 'file_asset' ->> 'tenant_id') = :tenant_id)"
            )
            params["tenant_id"] = tenant_id
        if conditions:
            stmt += "WHERE " + " AND ".join(conditions) + " "
        stmt += "ORDER BY e.embedding <=> CAST(:vec AS vector) LIMIT :limit"
        with self._engine.connect() as conn:
            rows = conn.execute(sql(stmt), params).fetchall()
        return [
            {
                "node_id": row[0],
                "kind": row[1],
                "label": row[2] or row[0],
                "score": round(float(row[3]), 6),
            }
            for row in rows
        ]

    def readiness(self) -> Dict[str, Any]:
        from sqlalchemy import text as sql

        status = {
            "ready": False,
            "backend": "postgres_age",
            "database": False,
            "age": False,
            "pgvector": False,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            with self._engine.connect() as conn:
                conn.execute(sql("SELECT 1"))
                status["database"] = True
                ext = conn.execute(
                    sql("SELECT extname FROM pg_extension WHERE extname IN ('age', 'vector')")
                ).fetchall()
                present = {row[0] for row in ext}
                status["age"] = "age" in present
                status["pgvector"] = "vector" in present
            status["ready"] = status["database"] and status["age"] and status["pgvector"]
        except Exception:  # pragma: no cover - exercised only on outage
            # Log the details server-side only: exception text can carry DSN
            # hosts or SQL fragments and /healthz is an unauthenticated surface.
            _logger.exception("graph readiness probe failed")
            status["error"] = "backend unreachable"
        return status

    def stats(self) -> Dict[str, int]:
        from sqlalchemy import text as sql

        with self._engine.connect() as conn:
            nodes = conn.execute(sql("SELECT count(*) FROM graph_nodes")).scalar() or 0
            edges = conn.execute(sql("SELECT count(*) FROM graph_edges")).scalar() or 0
            concepts = conn.execute(sql("SELECT count(*) FROM ontology_concepts")).scalar() or 0
            embeddings = conn.execute(sql("SELECT count(*) FROM embedding_vectors")).scalar() or 0
        return {
            "nodes": int(nodes),
            "edges": int(edges),
            "concepts": int(concepts),
            "embeddings": int(embeddings),
        }


# --- Backend selection --------------------------------------------------------

_STORE: Optional[GraphStore] = None


def _configured_embedder(config: AppConfig) -> Optional[Callable[[str], List[float]]]:
    if not config.orchestrator_base_url:
        return None
    # Lazy import avoids the file-ontology -> graph-store dependency cycle.
    from .document_semantics import build_orchestrator_client

    return build_orchestrator_client(config).embed_one


def build_store() -> GraphStore:
    """Construct the configured backend for the current bootstrap config.

    Fails LOUD on a misconfigured/unreachable database instead of silently
    downgrading to the in-memory backend (which would drop every write). The
    in-memory backend is used ONLY when it is the explicit choice:

    * ``graph_backend = "memory"`` -- always in-memory.
    * ``graph_backend = "auto"`` (default) with **no** database DSN configured
      -- standalone / submodule / CI mode.

    When a database DSN *is* configured (or ``graph_backend = "postgres"``), the
    Postgres+AGE+pgvector backend must construct and report ready, otherwise a
    :class:`RuntimeError` is raised so the misconfiguration surfaces immediately.
    """

    bootstrap = load_bootstrap()
    config = get_app_config()
    backend = config.graph_backend
    embedder = _configured_embedder(config)

    if backend == "memory":
        return InMemoryGraphStore(config=config, embedder=embedder)

    if bootstrap.has_database:
        store_kwargs = {"embedder": embedder} if embedder is not None else {}
        store = PostgresGraphStore(
            bootstrap.database_dsn,
            config=config,
            **store_kwargs,
        )
        readiness = store.readiness()
        if not readiness.get("ready"):
            raise RuntimeError(
                "configured database backend is not ready (AGE/pgvector/DB "
                f"unreachable or misconfigured): {readiness}. Set graph_backend="
                "'memory' to run without a database."
            )
        return store

    if backend == "postgres":
        raise RuntimeError(
            "graph_backend='postgres' but no database DSN was configured "
            "(bootstrap transport SDP_DATABASE_DSN is unset)."
        )

    return InMemoryGraphStore(config=config, embedder=embedder)


def get_store() -> GraphStore:
    """Build and seed the active store lazily after runtime credentials exist."""

    global _STORE
    if _STORE is None:
        _STORE = build_store()
        # Lazy import avoids the seed -> graph_store dependency cycle. Passing
        # the concrete store prevents seed_store from recursively calling us.
        from .seed import seed_store

        seed_store(_STORE)
    return _STORE


def set_store(store: Optional[GraphStore]) -> None:
    """Swap the active store (used by seeding and tests)."""

    global _STORE
    _STORE = store
