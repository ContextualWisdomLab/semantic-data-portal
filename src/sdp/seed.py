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

from typing import Any, Iterable, Optional

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


def assert_dataset_mirror_kinds_are_available(
    dataset_id: str, column_names: Iterable[str], store: Optional[GraphStore] = None
) -> None:
    """Refuse a catalog write whose graph mirror would reclassify a node.

    ``seed_dataset`` writes exactly two kinds of node - ``dataset_id`` as a
    ``dataset`` and ``f"{dataset_id}:{column}"`` as a ``column`` - and
    ``assert_node_kind_is_stable`` refuses either if that id already exists as
    something else. Both catalog routes mirrored **after** writing the catalog
    row, so that refusal arrived too late. Measured before this check, each one
    authorized request:

        POST /catalog/datasets {"id": "고객", ...}        (고객 is a seeded concept)
            -> 500, the catalog row created and served 200 by
               GET /catalog/datasets/고객, no graph node, and every later
               ``seed_store`` in the process raising on that row - so one
               request permanently broke seeding.

        PATCH /catalog/datasets/{id} adding a column whose node id a concept
        holds
            -> 400 "request body is not valid", with the title *and* the schema
               change kept by the catalog and the graph half-mirrored. The
               caller is told the request was rejected while it was applied.

    So the question is asked here, before the catalog row is touched, and the
    routes map the refusal to 409 - the same status the structurally identical
    conflict already answers on ``POST /graph/nodes`` and
    ``POST /ontology/concepts``. The 500 and the mislabelled 400 were both
    introduced with the kind rule itself; this closes the two paths that rule
    left unguarded.

    Kept next to ``seed_dataset`` on purpose: it enumerates the same node ids
    that function writes, so a change to one is visible beside the other.
    """
    store = store or get_store()
    store.assert_node_kind_is_stable(dataset_id, "dataset")
    for column_name in column_names:
        store.assert_node_kind_is_stable(f"{dataset_id}:{column_name}", "column")


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

    Every write here is an upsert, which made the mirror **append-only**: a
    column, term, mapping or lineage edge removed from the catalog stayed in the
    graph forever. Measured after ``PATCH /catalog/datasets/crm-customer-master``
    dropped the declared-PII column ``customer_email``:

        catalog schema                        customer_id, signup_at
        GET /graph/nodes/...:customer_email   200, properties.pii = true
        POST /search/semantic "customer_email"  top hit, score 0.673 (analyst)

    ``/browse`` masks that column while it is declared, so removing it made the
    column *more* exposed than keeping it. The same held for terms, business
    mappings, lineage in both directions and related datasets, and a rename left
    both names in the graph. ``/graph/stats`` was monotone: 26 nodes / 78 edges
    before and after stripping a dataset bare.

    So this is now a reconcile: the declared sets are upserted and anything the
    graph still holds for this dataset that the catalog no longer declares is
    removed. Only the dataset's own column nodes are deleted - concepts and
    other datasets are not owned by this one, so for those only the edge goes.
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

    declared_columns = set()
    for column in dataset.schema:
        column_id = f"{dataset.id}:{column.name}"
        declared_columns.add(column_id)
        store.upsert_node(
            column_id,
            "column",
            label=column.name,
            properties={"datatype": column.datatype, "pii": column.pii},
            text=f"{column.name} {column.datatype}",
        )
        store.upsert_edge("has_column", dataset.id, column_id)

    # dataset -> concept mappings (both explicit terms and business mappings)
    declared_mappings = set()
    for term in dataset.terms:
        declared_mappings.add(term)
        store.upsert_edge("mapping", dataset.id, term, properties={"origin": "term"})
    for mapping in dataset.mappings:
        declared_mappings.add(mapping.concept)
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

    _reconcile_removed(
        dataset,
        store,
        declared_columns=declared_columns,
        declared_mappings=declared_mappings,
    )


def _declaring_record(dataset: Any, dataset_id: str) -> Any:
    """The catalog record for ``dataset_id``, preferring the one being seeded.

    The dataset under reconciliation is passed in rather than re-read, so its
    declaration is the one the caller is applying.
    """
    if dataset_id == dataset.id:
        return dataset
    return catalog.get_dataset(dataset_id)


def _lineage_edge_is_declared(dataset: Any, source_id: str, target_id: str) -> bool:
    """Whether either endpoint's catalog record declares this lineage edge.

    A dataset that no longer exists declares nothing, so a dangling endpoint
    does not keep an edge alive.
    """
    upstream = _declaring_record(dataset, source_id)
    if upstream is not None and target_id in upstream.lineage_outputs:
        return True
    downstream = _declaring_record(dataset, target_id)
    if downstream is not None and source_id in downstream.lineage_inputs:
        return True
    return False


def _owns_column_node(dataset_id: str, node_id: str) -> bool:
    """Whether ``node_id`` is a column node this dataset generated.

    ``seed_dataset`` writes column nodes under exactly one shape -
    ``f"{dataset_id}:{column.name}"`` - so anything else reached through a
    ``has_column`` edge was put there by some other writer (``POST
    /graph/edges`` accepts a ``has_column`` edge to any node) and is not this
    reconciliation's to destroy. Before this guard, an undeclared
    ``has_column`` edge took its target node with it: pointing one at the
    seeded ``고객`` concept and then patching the dataset's schema deleted
    ``고객`` itself, together with every edge touching it, and the ontology
    routes that resolve that term answered as if the concept had never been
    defined. The edge is still removed in that case - it is this dataset's
    edge - only the node someone else owns survives.
    """
    return node_id.startswith(f"{dataset_id}:") and len(node_id) > len(dataset_id) + 1


def _reconcile_removed(
    dataset: Any,
    store: GraphStore,
    *,
    declared_columns: set[str],
    declared_mappings: set[str],
) -> None:
    """Remove what the graph still holds for this dataset and the catalog does not.

    Separated from the upsert half so the two directions are readable on their
    own. Scoped strictly to edges this dataset owns: a ``mapping`` edge from the
    dataset to a concept is removed, the concept node is not; a ``lineage`` edge
    is removed, the other dataset is not. Only the dataset's own
    ``{dataset.id}:{column}`` nodes are deleted, and only once their
    ``has_column`` edge is gone.
    """
    for edge in store.edges_for(dataset.id, "has_column"):
        if edge.target_id in declared_columns:
            continue
        store.delete_edge("has_column", dataset.id, edge.target_id)
        if _owns_column_node(dataset.id, edge.target_id):
            store.delete_node(edge.target_id)

    for edge in store.edges_for(dataset.id, "mapping"):
        if edge.target_id not in declared_mappings:
            store.delete_edge("mapping", dataset.id, edge.target_id)

    # A lineage edge has **two** possible declarers: ``A -> B`` exists because A
    # lists B in ``lineage_outputs`` *or* because B lists A in
    # ``lineage_inputs``. The upsert half above creates it from either side.
    # Reconciling against only the mutated dataset's own half therefore deleted
    # edges it does not own. Measured on two datasets where the upstream alone
    # declares the link:
    #
    #     PATCH lin-up {"lineage_outputs": ["lin-down"]} ; seed lin-up
    #       -> graph incoming edges of lin-down: [("lin-up", "lin-down")]
    #     seed lin-down            (any mutation on it, or startup bootstrap)
    #       -> graph incoming edges of lin-down: []
    #       -> catalog still declares lin-up.lineage_outputs == ["lin-down"]
    #
    # The graph then contradicted the catalog permanently - nothing restored the
    # edge short of re-seeding the upstream - and the startup bootstrap seeds
    # every dataset in turn, so whichever was seeded second wiped the other's
    # declaration. An edge is removed only when *neither* endpoint declares it.
    for edge in store.edges_for(dataset.id, "lineage", direction="out"):
        if not _lineage_edge_is_declared(dataset, dataset.id, edge.target_id):
            store.delete_edge("lineage", dataset.id, edge.target_id)
    for edge in store.edges_for(dataset.id, "lineage", direction="in"):
        if not _lineage_edge_is_declared(dataset, edge.source_id, dataset.id):
            store.delete_edge("lineage", edge.source_id, dataset.id)

    for edge in store.edges_for(dataset.id, "related_dataset"):
        if edge.target_id not in set(dataset.related_datasets):
            store.delete_edge("related_dataset", dataset.id, edge.target_id)
