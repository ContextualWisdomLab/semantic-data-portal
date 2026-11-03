"""The in-memory graph store is shared process state, so its reads are guarded.

FastAPI runs this package's ``def`` handlers in a worker threadpool, so a reader
genuinely interleaves with a writer. ``semantic_search`` iterated
``_embeddings`` live, which is a hard error rather than a stale read::

    POST /search/semantic, while datasets are being onboarded
      -> 500 RuntimeError: dictionary changed size during iteration
    measured at 17 of 42 searches (40%) with two readers and two writers

The repair is a lock in the store rather than a snapshot at the one iteration
that was reported: ``_edges`` is rebuilt wholesale by ``delete_edge`` and
``delete_node`` while ``edges_for`` and ``traverse`` iterate it, and
``delete_node`` mutates three collections in sequence - so a reader could see a
node whose embedding was already gone. Fixing only the reported line would have
left the rest.

The interleaving here is forced rather than raced: the reader is slowed per
node so a writer is certain to arrive mid-iteration. A pause, not a barrier -
a barrier inside the critical section would deadlock against the lock it is
meant to verify.
"""

from __future__ import annotations

import threading
import time

import pytest

from sdp import graph_store as gs
from sdp.graph_store import InMemoryGraphStore


@pytest.fixture()
def populated_store() -> InMemoryGraphStore:
    """A store with enough nodes that an iteration takes measurable time."""
    store = InMemoryGraphStore()
    store.upsert_node("seed-dataset", "dataset", label="seed dataset")
    for index in range(60):
        store.upsert_node(f"seed:{index}", "column", label=f"column_{index}")
        store.upsert_edge("has_column", "seed-dataset", f"seed:{index}")
    return store


def _run_concurrently(reader, writer, *, reader_delay_hook):
    """Start the reader, let it enter its loop, then run the writer."""
    entered = threading.Event()
    failures: list[BaseException] = []

    def slow_hook(*args, **kwargs):
        entered.set()
        time.sleep(0.004)
        return reader_delay_hook(*args, **kwargs)

    results: list[object] = []

    def read() -> None:
        try:
            results.append(reader())
        except BaseException as exc:  # noqa: BLE001 - the defect is the exception
            failures.append(exc)

    thread = threading.Thread(target=read)
    return entered, failures, results, thread, slow_hook


def test_a_search_survives_nodes_arriving_mid_iteration(
    populated_store: InMemoryGraphStore, monkeypatch
) -> None:
    """The reported 500: a dict changing size while being iterated."""
    real_similarity = gs.cosine_similarity
    entered, failures, results, thread, slow_hook = _run_concurrently(
        lambda: populated_store.semantic_search("column", limit=5),
        None,
        reader_delay_hook=real_similarity,
    )
    monkeypatch.setattr(gs, "cosine_similarity", slow_hook)
    thread.start()
    assert entered.wait(timeout=10), "the reader never entered its loop"

    for index in range(200):
        populated_store.upsert_node(f"late:{index}", "column", label=f"late_{index}")
    thread.join(timeout=60)
    assert not thread.is_alive()

    assert not failures, f"the search raised while nodes arrived: {failures[0]!r}"
    assert results and len(results[0]) == 5


def test_an_edge_read_survives_edges_being_rebuilt(
    populated_store: InMemoryGraphStore,
) -> None:
    """``delete_edge``/``delete_node`` replace ``_edges`` wholesale.

    The reported defect was the embeddings dict, but the edge list is rebuilt
    by assignment under readers that iterate it, and ``delete_node`` mutates
    three collections in sequence - so a reader could observe a node whose
    embedding was already gone.

    Honest about its own strength: this one **passes without the lock too**
    (verified by replacing the lock with a no-op). Rebuilding a list by
    assignment does not raise in CPython, because an iterator already holding
    the old list keeps iterating it; the torn read it can produce is a wrong
    answer rather than an exception, and a wrong answer is not something this
    test can distinguish from a legitimate concurrent one. It is kept as
    hardening against a future edit that makes these collections raise the way
    ``_embeddings`` did, not as a reproduction. The reproduction is
    ``test_a_search_survives_nodes_arriving_mid_iteration``, which does fail
    without the lock.
    """
    failures: list[BaseException] = []
    stop = threading.Event()

    def reader() -> None:
        try:
            while not stop.is_set():
                populated_store.edges_for("seed-dataset", "has_column")
                populated_store.traverse("seed-dataset", max_depth=1)
        except BaseException as exc:  # noqa: BLE001
            failures.append(exc)

    threads = [threading.Thread(target=reader) for _ in range(2)]
    for thread in threads:
        thread.start()
    for index in range(60):
        populated_store.delete_node(f"seed:{index}")
    stop.set()
    for thread in threads:
        thread.join(timeout=60)
    assert all(not thread.is_alive() for thread in threads)
    assert not failures, f"a graph read raised while edges were rebuilt: {failures[0]!r}"


def test_every_method_touching_shared_state_takes_the_lock() -> None:
    """Enumerated from the class, so a new method cannot be left unguarded.

    ``readiness`` is the one exemption and is asserted to touch no shared
    collection, rather than being listed by name and trusted.
    """
    import inspect

    exempt = {"__init__", "readiness"}
    shared = ("self._nodes", "self._edges", "self._embeddings",
              "self._concepts", "self._alias_to_concept")
    unguarded = []
    for name, member in vars(InMemoryGraphStore).items():
        if not callable(member) or name in exempt:
            continue
        source = inspect.getsource(member)
        if any(collection in source for collection in shared):
            if "with self._lock" not in source:
                unguarded.append(name)
    assert unguarded == [], (
        f"these store methods read or write shared state unguarded: {unguarded}"
    )

    readiness_source = inspect.getsource(InMemoryGraphStore.readiness)
    assert not any(collection in readiness_source for collection in shared), (
        "readiness now touches shared state and must take the lock"
    )


def test_the_store_lock_is_reentrant() -> None:
    """``concept_graph`` and ``traverse`` call siblings that also take it."""
    store = InMemoryGraphStore()
    assert isinstance(store._lock, type(threading.RLock()))
    store.upsert_concept({"concept": "고객", "aliases": ["customer"]})
    # Exercises the nested path: concept_graph -> _canonical_concept.
    assert store.concept_graph("customer")["canonical"] == "고객"
    with store._lock:
        with store._lock:
            assert store.stats()["concepts"] == 1
