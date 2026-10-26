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
            leaked 277 nodes (121 dataset, 129 column, 25 concept), 233 edges

    and with it enabled, 0 and 0.

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
