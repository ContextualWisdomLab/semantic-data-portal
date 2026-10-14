"""Idempotent seed/bootstrap of the graph engine.

Ports the previously hard-coded MVP data -- the catalog datasets and the five
ontology concepts -- into whichever :class:`GraphStore` backend is active. Safe
to run repeatedly (all writes are upserts), so it works for both the in-memory
default and the Postgres+AGE+pgvector backend.

Nodes:  concepts, datasets, columns.
Edges:  broader / narrower / related (ontology), mapping (dataset->concept),
        lineage (dataset->dataset), has_column (dataset->column).
"""

from __future__ import annotations

from typing import Any, Optional

from . import catalog, ontology
from .graph_store import GraphStore, get_store


def seed_store(store: Optional[GraphStore] = None) -> dict:
    """Load catalog + ontology seed data into ``store`` (idempotent)."""

    store = store or get_store()

    # --- ontology concepts -------------------------------------------------
    for concept, meta in ontology._CONCEPT_DEFINITIONS.items():
        store.upsert_concept(
            {
                "concept": concept,
                "definition": meta.get("definition", ""),
                "aliases": list(meta.get("aliases", [])),
                "broader": meta.get("broader"),
                "narrower": list(meta.get("narrower", [])),
                "related": list(meta.get("related", [])),
                "multilingual": list(meta.get("multilingual", [])),
            }
        )

    # --- datasets, columns, mappings, lineage ------------------------------
    for dataset in catalog.list_datasets():
        seed_dataset(dataset, store=store)

    return store.stats()


def seed_dataset(dataset: Any, store: Optional[GraphStore] = None) -> None:
    """Mirror one dataset - its node, columns, mappings and lineage - into the graph.

    This was the body of ``seed_store``'s loop and ran **only at startup**, so a
    dataset onboarded through ``POST /catalog/datasets`` never reached the graph
    at all. Measured before this change, immediately after a successful create:

        POST /catalog/datasets            -> 200
        GET  /graph/stats                 -> nodes 26 -> 26, embeddings 26 -> 26
        GET  /graph/nodes/<new dataset>   -> 404

    README names graph traversal and semantic search as headline capabilities, so
    a buyer's own data being invisible to both is a gap in the product rather than
    in the seed. Every write here is an upsert, which is why the same function can
    serve the startup bootstrap and each later mutation.

    Tenant scope is unaffected: ``policy.can_see_graph_node`` resolves each node's
    owning dataset and applies the same boundary the catalog does, so mirroring a
    dataset does not widen who can see it.
    """
    store = store or get_store()
    text_blob = " ".join(
        [dataset.title, dataset.description, dataset.domain]
        + list(dataset.tags)
        + list(dataset.terms)
    )
    store.upsert_node(
        dataset.id,
        "dataset",
        label=dataset.title,
        properties={
            "domain": dataset.domain,
            "owner": dataset.owner,
            "steward": dataset.steward,
            "tags": list(dataset.tags),
            "terms": list(dataset.terms),
            "sensitivity": dataset.sensitivity,
            "status": dataset.status,
        },
        text=text_blob,
    )

    for column in dataset.schema:
        column_id = f"{dataset.id}:{column.name}"
        store.upsert_node(
            column_id,
            "column",
            label=column.name,
            properties={"datatype": column.datatype, "pii": column.pii},
            text=f"{column.name} {column.datatype}",
        )
        store.upsert_edge("has_column", dataset.id, column_id)

    # dataset -> concept mappings (both explicit terms and business mappings)
    for term in dataset.terms:
        store.upsert_edge("mapping", dataset.id, term, properties={"origin": "term"})
    for mapping in dataset.mappings:
        store.upsert_edge(
            "mapping",
            dataset.id,
            mapping.concept,
            properties={"origin": "business_mapping", "status": mapping.status},
        )

    # lineage edges
    for upstream in dataset.lineage_inputs:
        store.upsert_edge("lineage", upstream, dataset.id, properties={"kind": "input"})
    for downstream in dataset.lineage_outputs:
        store.upsert_edge("lineage", dataset.id, downstream, properties={"kind": "output"})
    for related in dataset.related_datasets:
        store.upsert_edge("related_dataset", dataset.id, related)
