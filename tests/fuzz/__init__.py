"""Fuzzing / property-based test package for semantic-data-portal.

Two layers live here:

* ``test_fuzz_properties.py`` — Hypothesis (MPL-2.0) property tests that run as
  part of the normal ``pytest`` suite on every platform. Fast and deterministic.
* ``atheris/`` — Atheris (Apache-2.0) coverage-guided harnesses that run in a
  bounded CI job (Linux). They reuse the invariants defined here.

The targets were chosen from the highest-value untrusted-input surfaces that
CodeGraph surfaced: the NL->SQL drafter and query executor
(``sdp.orchestrator``), the free-text ontology resolver (``sdp.ontology``), and
the token/regex catalog search (``sdp.catalog``), plus the Pydantic request DTOs.
"""
