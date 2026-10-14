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

    sdp.catalog      _DATA, _AUDIT_LOG, _SCHEMA_HISTORY
    sdp.evidence     _POLICY_DECISION_LOG, _AUDIT_EVENT_LOG
    sdp.ontology     _CONCEPT_DEFINITIONS, _ALIAS_TO_CANONICAL, _ONTOLOGY_PATCHES
    sdp.observability  request-observation ring buffer, export-error buffer

**Deliberately not covered: the graph store singleton.** Catalog mutations now
mirror into it, so it does accumulate across tests, but it exposes no snapshot
API and inventing one here would be a product change made for the test suite.
A test that depends on graph-store counts must establish its own baseline; the
limit is stated rather than papered over.
"""

from __future__ import annotations

from copy import deepcopy

import pytest

from sdp import catalog, evidence, observability, ontology


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
    concept_definitions = deepcopy(ontology._CONCEPT_DEFINITIONS)
    alias_to_canonical = dict(ontology._ALIAS_TO_CANONICAL)
    concept_index = deepcopy(ontology._INDEX)
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
        ontology._CONCEPT_DEFINITIONS.clear()
        ontology._CONCEPT_DEFINITIONS.update(concept_definitions)
        ontology._ALIAS_TO_CANONICAL.clear()
        ontology._ALIAS_TO_CANONICAL.update(alias_to_canonical)
        ontology._INDEX.clear()
        ontology._INDEX.update(concept_index)
        observability.reset_request_observability()
        for observation in request_observations:
            observability.record_request_observation(observation, export=False)
        for error in export_errors:
            observability.record_observability_export_error(error)

