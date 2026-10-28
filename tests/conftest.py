"""One autouse fixture restoring every module-level mutable store, for all tests.

The app keeps its MVP state in module-level dicts and lists, so a test that
registers a dataset, publishes a concept or writes an audit row changes what
every later test sees. ``tests/test_api.py`` carried a thorough snapshot/restore
fixture and several other files carried partial copies, but **20-odd files had
none**, and the leakage was not theoretical. Measured by running the suite with
the files in reverse order::

    5 failed, 524 passed      (forward order: 529 passed)

    tests/test_api.py::test_draft_query                  assert 403 == 200
    tests/test_api.py::test_join_candidate_endpoint      assert False
    tests/test_api.py::test_enterprise_demo_smoke_summary_is_ready
    tests/test_api.py::test_enterprise_evidence_pack_summarizes_buyer_diligence
    tests/test_demo_smoke_http_walkthrough.py::test_the_ready_gate_fails_when_the_walkthrough_fails

Bisected, two files leaked: ``test_payload_type_robustness.py`` and
``test_governed_write_evidence.py`` - both added in this series, both with no
fixture at all. Fixing them one at a time is the pattern that has already failed
repeatedly here, so the restore lives in one autouse fixture every file gets
instead of being something each new file has to remember.

The per-file fixtures that already exist are now redundant rather than wrong:
they nest inside this one and restore to the same values.

The state covered here was enumerated from the modules, not listed from memory::

    sdp.catalog          _DATA, _AUDIT_LOG, _SCHEMA_HISTORY
    sdp.evidence         _POLICY_DECISION_LOG, _AUDIT_EVENT_LOG
    sdp.ontology         _CONCEPT_DEFINITIONS, _ALIAS_TO_CANONICAL, _ONTOLOGY_PATCHES,
                         _PATCH_QUEUE_STATE
                         (the concept-to-dataset map was here too, as ``_INDEX``;
                         it is derived from the catalog on read now, so there is
                         no snapshot left to restore)
    sdp.ontology_version _CHANGE_LOG, _REVISION_STATE
    sdp.observability    request-observation ring buffer, export-error buffer,
                         governed-evidence gap counter,
                         connector-probe failure and verification counters,
                         alert-routing latch and counters, alert-error ring,
                         _SINK_BREAKER
    sdp.authz            _JWKS_CACHE

The last three were added after the enumeration was mechanised. ``_CHANGE_LOG``
and ``_REVISION_STATE`` must be restored **together with**
``_CONCEPT_DEFINITIONS``: the revision names a content digest, so restoring the
vocabulary without the revision leaves ``ontology_version_identity`` reporting
``digest_matches_recorded_revision: false`` for the rest of the session.

``_SINK_BREAKER`` and ``_JWKS_CACHE`` are runtime-mutated and were covered only
by per-test cleanup inside the two files that dirty them
(``test_honest_metrics.py`` pokes ``_SINK_BREAKER["open_until"] = 0.0`` in five
places; ``test_authz.py`` calls ``clear_jwks_cache()`` in three). Measured over
the whole suite with a per-test probe, neither leaked - 0 tests left either
store dirty - so this is latent fragility rather than a live defect, and the
honest reason to move them here is that per-file cleanup is the arrangement
whose failure this fixture exists to prevent.

**The graph store singleton is covered too**, as of the round that measured
what it was accumulating. It was excluded on the grounds that it exposes no
snapshot API and that inventing one would be a product change made for the test
suite - true of a product API, but this fixture already reaches into
``catalog._DATA`` and the store's backing collections are the same kind of
module-level state, so the copy lives here instead. Measured against the
26-node seeded baseline with the restore disabled::

    tests/test_catalog_mirror_kind_conflict.py alone
        leaked 31 nodes (18 dataset, 8 column, 5 concept), 26 edges
    the whole suite
        leaked 277 nodes (121 dataset, 129 column, 25 concept, 2 service), 233 edges

and with it enabled, 0 and 0. No pre-existing test failed on the leak in any
order measured either way - forward, reverse and shuffled seed 11 with the
restore disabled, all five with it - so this closed a latent leak, not a live
one. The reason not to leave it latent: this cycle added refusals keyed on a
node's existing kind, so a leaked ``concept`` node at an id a later test
registers as a dataset now turns that 200 into a 409, and a leaked ``dataset``
node does the same to a later ``POST /ontology/concepts``.
``tests/test_state_isolation.py`` pins the restored baseline by deriving it from
the catalog and the vocabulary rather than counting nodes.

The ``PostgresGraphStore`` backend has no such collections and no test runs
against it, so the snapshot is skipped rather than guessed when they are absent.
"""

from __future__ import annotations

from copy import deepcopy

import pytest

from sdp import authz, catalog, evidence, graph_store, observability, ontology, ontology_version


# The graph store's five collections, snapshotted and put back the same way the
# module-level dicts above are. Enumerated from the backend rather than listed:
# these are exactly the attributes ``InMemoryGraphStore`` assigns outside
# ``__init__`` plus the dicts it mutates in place. ``_config`` and ``_lock`` are
# set once at construction and are deliberately not restored.
_GRAPH_COLLECTIONS = ("_nodes", "_edges", "_embeddings", "_concepts", "_alias_to_concept")

# ``deepcopy``, not a one-level copy, because one write path mutates a *contained*
# object: ``InMemoryGraphStore.upsert_edge`` finds an existing edge and does
# ``existing.properties.update(...)`` rather than replacing it, so a
# ``list(self._edges)`` snapshot would hold the same ``GraphEdge`` objects and
# restore the mutated properties. ``GraphNode.as_dict`` likewise returns the live
# ``properties`` dict by reference. Nodes, embeddings and concept records are
# replaced wholesale, so only edges need it today - the whole snapshot is deep
# anyway, because the next in-place mutation someone adds should not need this
# comment re-derived. Measured, 200 round trips against the seeded baseline
# (26 nodes, 78 edges, 26 embeddings of dimension 128):
#
#     deepcopy   4.53 ms/test   ~5.8 s over the suite
#     one-level  0.005 ms/test  ~0.01 s over the suite
#
# ~6% of the suite's wall clock, paid for a snapshot that cannot be defeated by
# a mutation inside a stored object.


def _graph_snapshot():
    """Copy the graph store's collections, or ``None`` for a backend without them."""
    store = graph_store.get_store()
    if not all(hasattr(store, name) for name in _GRAPH_COLLECTIONS):
        return None
    return {name: deepcopy(getattr(store, name)) for name in _GRAPH_COLLECTIONS}


def _graph_restore(snapshot) -> None:
    """Put the graph store's collections back."""
    if snapshot is None:
        return
    store = graph_store.get_store()
    for name, value in snapshot.items():
        setattr(store, name, deepcopy(value))


@pytest.fixture(autouse=True)
def restore_in_memory_app_state():
    """Snapshot every module-level store before a test and put it back after."""
    datasets = {
        dataset_id: dataset.model_copy(deep=True)
        for dataset_id, dataset in catalog._DATA.items()
    }
    audit_log = list(catalog._AUDIT_LOG)
    schema_history = deepcopy(catalog._SCHEMA_HISTORY)
    policy_log = list(evidence._POLICY_DECISION_LOG)
    audit_event_log = list(evidence._AUDIT_EVENT_LOG)
    patches = [patch.model_copy(deep=True) for patch in ontology._ONTOLOGY_PATCHES]
    # Restored together with the queue, for the reason ``_REVISION_STATE`` is
    # restored together with ``_CHANGE_LOG``: the counter describes that list,
    # and restoring one without the other leaves the pair disagreeing about
    # how many proposals the cap dropped.
    patch_queue_state = dict(ontology._PATCH_QUEUE_STATE)
    concept_definitions = deepcopy(ontology._CONCEPT_DEFINITIONS)
    alias_to_canonical = dict(ontology._ALIAS_TO_CANONICAL)
    change_log = [dict(entry) for entry in ontology_version._CHANGE_LOG]
    revision_state = dict(ontology_version._REVISION_STATE)
    jwks_cache = dict(authz._JWKS_CACHE)
    sink_breaker = dict(observability._SINK_BREAKER)
    governed_evidence_gaps = dict(observability._GOVERNED_EVIDENCE_GAPS)
    connector_probe_failures = dict(observability._CONNECTOR_PROBE_FAILURES)
    connector_probe_verifications = dict(observability._CONNECTOR_PROBE_VERIFICATIONS)
    alert_routing = {
        key: deepcopy(value)
        for key, value in observability._ALERT_ROUTING.items()
        if key != "generation"
    }
    alert_errors = list(observability._ALERT_ERRORS)
    graph = _graph_snapshot()
    request_observations = observability.list_request_observations()
    export_errors = observability.list_observability_export_errors()
    try:
        yield
    finally:
        catalog._DATA.clear()
        catalog._DATA.update(datasets)
        catalog._AUDIT_LOG[:] = audit_log
        catalog._SCHEMA_HISTORY.clear()
        catalog._SCHEMA_HISTORY.update(schema_history)
        evidence._POLICY_DECISION_LOG[:] = policy_log
        evidence._AUDIT_EVENT_LOG[:] = audit_event_log
        ontology._ONTOLOGY_PATCHES[:] = patches
        ontology._PATCH_QUEUE_STATE.clear()
        ontology._PATCH_QUEUE_STATE.update(patch_queue_state)
        ontology._CONCEPT_DEFINITIONS.clear()
        ontology._CONCEPT_DEFINITIONS.update(concept_definitions)
        ontology._ALIAS_TO_CANONICAL.clear()
        ontology._ALIAS_TO_CANONICAL.update(alias_to_canonical)
        ontology_version._CHANGE_LOG[:] = change_log
        ontology_version._REVISION_STATE.clear()
        ontology_version._REVISION_STATE.update(revision_state)
        authz._JWKS_CACHE.clear()
        authz._JWKS_CACHE.update(jwks_cache)
        observability._SINK_BREAKER.clear()
        observability._SINK_BREAKER.update(sink_breaker)
        observability.reset_request_observability()
        for observation in request_observations:
            observability.record_request_observation(observation, export=False)
        for error in export_errors:
            observability.record_observability_export_error(error)
        # After the reset above, which clears it: the governed-evidence gap
        # counter is published by GET /enterprise/observability and /metrics, so
        # one test's deliberate gap must not be another test's reading.
        observability._GOVERNED_EVIDENCE_GAPS.clear()
        observability._GOVERNED_EVIDENCE_GAPS.update(governed_evidence_gaps)
        # Same position and the same reason: the reset above clears all four of
        # these too, and every one of them is published by
        # GET /enterprise/observability and /metrics, so one test's deliberate
        # probe failure or firing episode must not be another test's reading.
        observability._CONNECTOR_PROBE_FAILURES.clear()
        observability._CONNECTOR_PROBE_FAILURES.update(connector_probe_failures)
        observability._CONNECTOR_PROBE_VERIFICATIONS.clear()
        observability._CONNECTOR_PROBE_VERIFICATIONS.update(connector_probe_verifications)
        # ``generation`` is deliberately not restored. It is a monotonic marker
        # that lets a delivery thread still waiting on a wedged webhook discard
        # its outcome instead of writing it into a later episode's counters;
        # rolling it back to the snapshot value would hand that thread a
        # matching generation and let the write land after all.
        observability._ALERT_ROUTING.update(deepcopy(alert_routing))
        observability._ALERT_ERRORS.clear()
        observability._ALERT_ERRORS.extend(alert_errors)
        _graph_restore(graph)

