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

from sdp import catalog, evidence, ontology, ontology_version


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
