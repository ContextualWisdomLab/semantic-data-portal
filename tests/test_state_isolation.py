"""The guard for ``tests/conftest.py``'s restore, not for the app.

pytest does not collect tests from ``conftest.py``, so this assertion lives in a
real test module. Without it, a restore that stops covering a store shows up as
an unrelated test failing in one file order and passing in another - which is
exactly how the leakage was found::

    forward order   529 passed
    reversed order    5 failed, 524 passed

Bisected to two files with no isolation fixture at all. The fixture is now in
``conftest.py`` so every file gets it; this pins that it still works.
"""

from __future__ import annotations

import pytest

from sdp import catalog, evidence, graph_store, ontology, ontology_version

# Imported for its side effect, not its contents: the graph store is seeded when
# ``sdp.api`` is imported (and again on ASGI startup), while ``catalog._DATA``
# and the vocabulary are seeded by their own modules. Without this import the
# graph-store baseline assertion below sees an empty store when this file runs
# on its own and a seeded one when it runs after any file that builds a client -
# which is the file-order dependence this module exists to catch, in the guard
# itself.
from sdp import api as _app_module_imported_to_seed_the_graph_store  # noqa: F401


SEEDED_BASELINE_SIZES = {
    "catalog._DATA": 5,
    "ontology._CONCEPT_DEFINITIONS": 5,
}


def test_every_test_starts_from_the_seeded_baseline() -> None:
    """The guard for the fixture above, not for the app.

    If the restore ever stops covering a store, this fails rather than some
    unrelated test failing in one file order and passing in another - which is
    how the leakage showed up in the first place.
    """
    assert len(catalog._DATA) == SEEDED_BASELINE_SIZES["catalog._DATA"], sorted(catalog._DATA)
    assert len(ontology._CONCEPT_DEFINITIONS) == SEEDED_BASELINE_SIZES[
        "ontology._CONCEPT_DEFINITIONS"
    ], sorted(ontology._CONCEPT_DEFINITIONS)
    assert sorted(ontology._CONCEPT_DEFINITIONS) == sorted(ontology.SEEDED_CONCEPTS)
    assert not ontology._ONTOLOGY_PATCHES
    # Every alias points at a concept the vocabulary actually holds.
    for term, owner in ontology._ALIAS_TO_CANONICAL.items():
        assert owner in ontology._CONCEPT_DEFINITIONS, f"{term!r} -> missing {owner!r}"


def test_the_evidence_ledgers_start_empty_for_each_test() -> None:
    """A test that counts ledger rows must not inherit another test's."""
    assert not catalog._AUDIT_LOG
    assert not evidence._POLICY_DECISION_LOG
    assert not evidence._AUDIT_EVENT_LOG


def _seeded_edge_set() -> set[tuple[str, str, str]]:
    """The edges the seed writes, derived by seeding a throwaway store.

    Not a written-down list: ``seed_store`` is the function whose output the
    restore has to reproduce, so asking it - against a store nobody else holds -
    is the only baseline that cannot drift from the seed. It reads
    ``catalog._DATA`` and ``ontology._CONCEPT_DEFINITIONS``, which the autouse
    fixture has already restored when this runs, so the derivation sees the same
    inputs the real store was seeded from.

    ``InMemoryGraphStore()`` and not ``set_store``: the throwaway is never
    installed, so seeding it cannot touch the singleton this test is about. That
    distinction is the one a previous round got wrong in the other direction -
    a line reading ``seed_store(InMemoryGraphStore())`` was positioned as
    cleanup, and seeded a store it then discarded.
    """
    from sdp.graph_store import InMemoryGraphStore
    from sdp.seed import seed_store

    throwaway = InMemoryGraphStore()
    seed_store(throwaway)
    return {
        (edge.edge_type, edge.source_id, edge.target_id) for edge in throwaway._edges
    }


def test_the_graph_store_starts_from_the_catalog_and_the_vocabulary() -> None:
    """The guard for the graph-store half of the restore.

    The graph store was deliberately excluded from the restore, on the stated
    grounds that it exposes no snapshot API and inventing one would be a product
    change made for the test suite. That reason held for a product API; it did
    not hold for the fixture reading the same backend collections it already
    reads ``catalog._DATA`` from, so the exclusion is gone and this is what
    holds it closed.

    Measured with the restore disabled, against the 26-node seeded baseline::

        tests/test_catalog_mirror_kind_conflict.py alone
            leaked 31 nodes (18 dataset, 8 column, 5 concept), 26 edges
        the whole suite
            leaked 277 nodes (121 dataset, 129 column, 25 concept, 2 service), 233 edges

    and with it enabled, 0 and 0. The parenthetical summed to 275 against its
    own headline of 277 for one round: two ``service`` nodes (``authz-node``,
    ``svc-A``) were left out, and a breakdown that does not add up is the same
    defect as a count that does not match - caught by a reviewer re-measuring
    rather than by anything mechanical, because no test reads these figures.

    No **pre-existing** test failed on the leak in any order measured either
    way - forward, reverse and shuffled seed 11 with the restore disabled, all
    five with it - so it was latent rather than live. This guard is not latent:
    with the restore disabled it fails in forward order and in shuffled seed 11
    and **passes in reverse**, because reverse order happens to run this file
    before any file that dirties the store. Passing in one order and failing in
    another is the exact shape the isolation fixture exists to eliminate, which
    is why the fix is the restore and not this assertion on its own.

    What made the latent leak worth closing is the shape of the latency: a
    leaked ``concept`` node at an id a later test registers as a dataset turns
    that test's 200 into a 409, and a leaked ``dataset`` node does the same to a
    later ``POST /ontology/concepts``. Both are refusals the suite added this
    cycle, so the number of ways a leak could become a failure grew with the
    kind rule itself.

    The baseline is derived, not counted, so changing the demo seed does not
    come back here: every node is a dataset the catalog holds, a column one of
    them declares, or a concept the vocabulary holds.

    **Edges are asserted too**, because the first version of this test checked
    nodes only while the restore's own justification is largely about edges.
    Measured, with ``_edges`` dropped from ``_GRAPH_COLLECTIONS`` and the other
    four kept::

        leaked nodes 0   leaked edges 233   whole suite: 1265 passed, 15 skipped

    so the half this test was written to hold could be removed with every test
    green - a guard reporting success for the half it did not look at. The edge
    set is derived the same way: every edge is one the seed writes, so the
    assertion is that no test added or removed one.
    """
    store = graph_store.get_store()
    nodes = {node_id: node.kind for node_id, node in store._nodes.items()}
    expected = {dataset_id: "dataset" for dataset_id in catalog._DATA}
    expected.update(
        {
            f"{dataset_id}:{column.name}": "column"
            for dataset_id, dataset in catalog._DATA.items()
            for column in dataset.schema or []
        }
    )
    expected.update({concept: "concept" for concept in ontology._CONCEPT_DEFINITIONS})
    # The message names both failure shapes. ``set(nodes) ^ set(expected)`` alone
    # is empty when the ids match and a *kind* differs - which is the reclassified
    # node this cycle's rules exist to refuse, so it is the shape most worth
    # naming.
    assert nodes == expected, {
        "unexpected": {node_id: nodes[node_id] for node_id in sorted(set(nodes) - set(expected))},
        "missing": {node_id: expected[node_id] for node_id in sorted(set(expected) - set(nodes))},
        "wrong_kind": {
            node_id: (nodes[node_id], expected[node_id])
            for node_id in sorted(set(nodes) & set(expected))
            if nodes[node_id] != expected[node_id]
        },
    }

    # The edges the seed writes, taken as the baseline the same way. Compared as
    # a multiset-free set because the store holds at most one edge per
    # (type, source, target) - ``upsert_edge`` merges properties into an
    # existing match rather than appending a second.
    edges = {(edge.edge_type, edge.source_id, edge.target_id) for edge in store._edges}
    baseline_edges = _seeded_edge_set()
    assert edges == baseline_edges, {
        "added": sorted(edges - baseline_edges),
        "removed": sorted(baseline_edges - edges),
    }


# The retracted claim, in both languages it was published in. Two reasons for
# the shape of this:
#
# * **Normalised search** - comment markers stripped, whitespace collapsed -
#   because three of the four sites wrapped the claim across lines and one was
#   an inline ``#`` comment, so a plain substring matched none of them.
# * **Assembled from fragments**, so the banned string never appears as a
#   literal in this file. Written out whole, the guard failed on its own
#   definition. The equivalent guard in ``tests/test_honest_metrics.py`` hit
#   this the other way round: it caught a README retraction that *quoted* the
#   sentence it was retracting, and the fix there was to reword the quote. Here
#   the phrases are data, so splitting them is the fix that does not weaken the
#   search.
_RETRACTED_EXCLUSION_CLAIMS = (
    "graph store singleton is " + "deliberately outside",
    "graph store is " + "deliberately outside",
    "그래프 스토어 싱글턴은 " + "의도적으로 제외",
    # The fourth wording, added after the first three missed five live sites.
    # Present tense only: the retractions deliberately keep the history in the
    # past tense ("did not restore ... when this was written"), which is true
    # and is how a reader learns why these tests clean up after themselves.
    "does not " + "restore the graph",
    "deliberately does not " + "restore the",
    # The consequence, which the five wordings above do not reach. An
    # adversarial review of c50eae7 reported five files still stating the
    # exclusion; re-measured after dd0c3f3 added the two fragments above, those
    # wordings are gone and three files had moved one step downstream - still
    # presenting the instruction a reader derives from the exclusion (that a
    # test touching graph counts must seed a graph baseline for itself) as the
    # current rule, one of them citing a sentence of tests/conftest.py that
    # 56259e0 deleted. A guard that catches the claim and not the instruction
    # derived from it leaves readers doing the thing the claim was wrong about.
    # The banned phrasings are deliberately not written out in this comment:
    # five guards this cycle were checked against a list that contained their
    # own explanation, so each searched for a string it had just introduced.
    "takes its " + "own baseline",
    "establish its " + "own baseline",
    "must take its " + "own baseline",
)


def test_no_published_text_still_says_the_graph_store_is_excluded() -> None:
    """The recurrence guard for the claim this round retracted.

    The exclusion was published in four places: ``tests/conftest.py``'s
    docstring, ``CLAUDE.md``'s conventions section, a justification in
    production code (``sdp/api_response_contract.py``, where it was one of two
    reasons for not publishing response schemas for the 20 non-GET operations)
    and two test comments that cited it as the reason they clean up after
    themselves. Retracting it in the fixture alone would leave production code
    and the agent-facing conventions file telling the next reader to work around
    a limit that is gone - and a reader who believes
    ``api_response_contract.py`` concludes the published-schema gap has a cause
    it no longer has.

    This is the same recurrence shape as the alert-evaluation sentence in
    ``tests/test_honest_metrics.py``, which went stale in three places found a
    round apart, so it gets the same mechanism. It is conditioned on the restore
    actually being in place: if the graph store is ever deliberately excluded
    again, the condition goes false and the claim is publishable once more.

    **Two limits, stated rather than left to be discovered.**

    *The enumeration is not the class.* The first version banned three wordings
    and the retraction it protected had missed **five** live sites that used a
    fourth - ``tests/test_catalog_mirror_kind_conflict.py``,
    ``tests/test_concept_graph_scope.py``,
    ``tests/test_graph_hierarchy_class_separation.py``,
    ``tests/test_graph_hierarchy_consistency.py`` and
    ``tests/test_graph_mirroring.py``, all five asserting in the present tense
    that the autouse fixture leaves the graph-store singleton alone - one of
    them 70 lines from the retraction in its own file. The wording is described
    rather than quoted here: written out, it matched this very list, which is
    the third time in this cycle a mechanical guard has flagged the text
    explaining it. A phrase list catches recurrence
    of the wordings it knows, which is worth having and is not the same as
    closing the class. This is the 409 enumeration's defect in another costume:
    a list compared against itself.

    *The skip is a hole.* The condition looks for ``_graph_restore(`` in the
    restore block, so renaming that helper while keeping the restore working
    makes this test **skip** - with a reason that reads as "the claim is true
    again" when it is not - and every protected site becomes republishable. A
    behavioural condition would need the fixture's effect rather than its
    source, and ``test_the_graph_store_starts_from_the_catalog_and_the_vocabulary``
    is that test; this one is about the prose.
    """
    import pathlib
    import re

    repo_root = pathlib.Path(__file__).resolve().parents[1]
    fixture = (repo_root / "tests" / "conftest.py").read_text(encoding="utf-8")
    marker = "    finally:"
    assert marker in fixture, "the fixture no longer has a finally: restore block"
    if "_graph_restore(" not in fixture.split(marker, 1)[1]:
        pytest.skip("the graph store is excluded again; the claim is true")

    searched = [repo_root / "README.md", repo_root / "CLAUDE.md"]
    searched += sorted((repo_root / "docs").rglob("*.md"))
    searched += sorted((repo_root / "src").rglob("*.py"))
    searched += sorted((repo_root / "tests").rglob("*.py"))
    offenders = []
    for candidate in searched:
        if not candidate.is_file():
            continue
        # Strip comment markers and collapse whitespace so a claim wrapped
        # across lines, or written as an inline comment, is still one string.
        flat = re.sub(r"\s+", " ", candidate.read_text(encoding="utf-8").replace("#", " "))
        for claim in _RETRACTED_EXCLUSION_CLAIMS:
            if claim in flat:
                offenders.append(f"{candidate.relative_to(repo_root).as_posix()}: {claim!r}")
    assert offenders == [], (
        "these texts say the graph store is outside tests/conftest.py's restore, "
        f"while the fixture restores it: {offenders}"
    )


def test_the_ontology_revision_and_the_vocabulary_are_restored_together() -> None:
    """Restoring one without the other breaks the version for the whole session.

    The revision names a content digest, so a fixture that put the vocabulary
    back but left the revision where a previous test moved it would leave
    ``digest_matches_recorded_revision`` false in every later test - and that
    field exists precisely to report a vocabulary mutated outside the versioned
    path, so it would stop meaning anything.
    """
    identity = ontology.ontology_version_identity()
    assert identity["ontology_revision"] == ontology_version.BASELINE_REVISION
    assert identity["digest_matches_recorded_revision"] is True
    assert identity["change_log_entry_count"] == 1
    assert identity["withheld_change_count"] == 0
    baseline = ontology.vocabulary_change_log(limit=1)["changes"][0]
    assert baseline["change_kind"] == "baseline"
