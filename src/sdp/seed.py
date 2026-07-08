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

from typing import Optional

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

    return store.stats()
