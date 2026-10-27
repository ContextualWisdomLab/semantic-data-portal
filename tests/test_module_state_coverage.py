"""Every module-level mutable store is classified, by enumeration not by memory.

``tests/conftest.py``'s autouse fixture exists because 20-odd test files had no
isolation fixture and two of them leaked - reversed file order turned 529 passed
into 5 failed, 524 passed. Its own guard,
``tests/test_state_isolation.py``, asserts the baseline, but both the fixture's
inventory and that guard are **hand-written lists**, so a new module-level store
is covered only if whoever added it remembered. That is the arrangement whose
failure the fixture exists to prevent, one level up.

Measured when this test was written: two runtime-mutated stores -
``authz._JWKS_CACHE`` and ``observability._SINK_BREAKER`` - were not in the
fixture at all, and the two files that dirty them cleaned up per-test instead
(``test_honest_metrics.py`` pokes ``_SINK_BREAKER["open_until"] = 0.0`` in five
places; ``test_authz.py`` calls ``clear_jwks_cache()`` in three). A per-test
probe over the whole suite found **0** tests leaving either store dirty, so
nothing was failing - but the per-file arrangement is exactly the one that
already failed here once. Both are in the fixture now, and this test is what
stops the next one being silent.

The rule is a classification, not a prohibition: a module-level ``dict``,
``list``, ``set`` or ``deque`` must be declared either restored by the fixture
or not mutated at runtime. Adding one without declaring it fails here, which is
a one-line decision for the author instead of a file-order-dependent failure for
whoever comes next.
"""

from __future__ import annotations

import collections
import importlib
import pathlib
import pkgutil

import sdp
import sdp_core


# Restored by ``tests/conftest.py``'s autouse fixture, because they change at
# runtime and one test's writes would otherwise be another test's input.
RESTORED_BY_FIXTURE = frozenset(
    {
        "sdp.authz._JWKS_CACHE",
        "sdp.catalog._AUDIT_LOG",
        "sdp.catalog._DATA",
        "sdp.catalog._SCHEMA_HISTORY",
        "sdp.evidence._AUDIT_EVENT_LOG",
        "sdp.evidence._POLICY_DECISION_LOG",
        "sdp.observability._ALERT_ERRORS",
        "sdp.observability._ALERT_ROUTING",
        "sdp.observability._CONNECTOR_PROBE_FAILURES",
        "sdp.observability._CONNECTOR_PROBE_VERIFICATIONS",
        "sdp.observability._EXPORT_ERRORS",
        "sdp.observability._GOVERNED_EVIDENCE_GAPS",
        "sdp.observability._REQUEST_OBSERVATIONS",
        "sdp.observability._SINK_BREAKER",
        "sdp.ontology._ALIAS_TO_CANONICAL",
        "sdp.ontology._CONCEPT_DEFINITIONS",
        "sdp.ontology._ONTOLOGY_PATCHES",
        "sdp.ontology_version._CHANGE_LOG",
        "sdp.ontology_version._REVISION_STATE",
    }
)

# Mutable containers that are never written after import: lookup tables,
# published contracts, vocabularies and design tokens. Declared rather than
# inferred from a naming convention, because ``_SINK_BREAKER`` and
# ``_JWKS_CACHE`` look exactly like the entries above and are not constants.
NOT_RUNTIME_MUTATED = frozenset(
    {
        "sdp.api.DOCUMENTED_REFUSALS",
        "sdp.api.JSONLD_CONTEXT",
        "sdp.api._DRAFT_QUERY_ERROR_STATUS",
        "sdp.api_error_contract.DYNAMIC_REFUSALS",
        "sdp.api_error_contract.ERROR_RESPONSE_SCHEMA",
        "sdp.api_error_contract.REFUSAL_DESCRIPTIONS",
        "sdp.api_error_contract.ROUTE_REFUSALS",
        "sdp.api_request_contract.REQUEST_BODY_EXTRA_PROPERTIES",
        "sdp.api_request_contract.REQUEST_BODY_MODELS",
        "sdp.api_response_contract.RESPONSE_SCHEMAS",
        "sdp.policy.REFUSAL_PLANES",
        "sdp.api_response_contract.UNPUBLISHED_RESPONSES",
        "sdp.authz._ALGORITHM_KEY_TYPES",
        "sdp.authz._ALLOWED_JWT_ALGORITHMS",
        "sdp.authz._DEFAULT_OIDC_GROUP_ROLE_MAP",
        "sdp.authz._SUBJECTS",
        "sdp.browse._SAMPLE_COLUMN_VALUES",
        "sdp.browse._SAMPLE_DATATYPE_FAMILIES",
        "sdp.browse._SAMPLE_DATATYPE_VALUES",
        "sdp.catalog._REQUIRED_METADATA_FIELDS",
        "sdp.config._DEFAULT_CONFIG",
        "sdp.connectors._IMPLEMENTED_CONFIG_PROOF",
        "sdp.connectors._IMPLEMENTED_PROOF",
        "sdp.connectors._RUNTIME_CONTROL_CHECKS",
        "sdp.connectors._SOURCE_CONNECTORS",
        "sdp.design_tokens.COMPONENT",
        "sdp.design_tokens.HIGH_CONTRAST",
        "sdp.design_tokens.PRIMITIVE",
        "sdp.design_tokens.SEMANTIC",
        "sdp.enterprise_evidence.ACTOR_SCOPED_PROOF_ENDPOINTS",
        "sdp.enterprise_evidence.OPEN_PROOF_ENDPOINTS",
        "sdp.graph_store._AGE_LABEL_CHARS",
        "sdp.ontology_version.ACTOR_ROLES",
        "sdp.ontology_version.REVIEW_BASES",
        "sdp.ontology_version.VOCABULARY_JSONLD_CONTEXT",
        "sdp.observability._ROUTABLE_ALERT_RULES",
        "sdp.orchestrator._FORBIDDEN_KEYWORDS",
        "sdp.policy.CATALOG_ACTION_ALIASES",
        "sdp.policy._DATA_READ_ACTIONS",
        "sdp.policy._METADATA_READ_ACTIONS",
        "sdp.semantic_validation._SHACL_COMPATIBLE_SHAPES",
        "sdp_core.requirements.REQUIREMENT_COVERAGE",
        "sdp_core.requirements._STATUS_MEANING",
    }
)

_MUTABLE_TYPES = (dict, list, set, bytearray, collections.deque)


def _module_level_mutables() -> dict[str, object]:
    """Every module-level mutable container in both packages, by import."""
    found: dict[str, object] = {}
    for package in (sdp, sdp_core):
        for info in pkgutil.iter_modules(package.__path__, package.__name__ + "."):
            module = importlib.import_module(info.name)
            for name, value in vars(module).items():
                if name.startswith("__"):
                    continue
                if isinstance(value, _MUTABLE_TYPES):
                    found[f"{info.name}.{name}"] = value
    return found


def test_every_module_level_mutable_is_classified() -> None:
    """A new store must be declared restored or declared constant.

    This is the check that was missing: the fixture and its guard both carry
    hand-written lists, so a store nobody remembered was simply absent from
    both and failed later, in one file order only.
    """
    found = set(_module_level_mutables())
    classified = RESTORED_BY_FIXTURE | NOT_RUNTIME_MUTATED
    unclassified = sorted(found - classified)
    assert not unclassified, (
        "these module-level mutable stores are neither restored by "
        "tests/conftest.py's fixture nor declared constant - add them to one of "
        f"the two sets in this file, and to the fixture if they change at "
        f"runtime: {unclassified}"
    )


def test_no_classification_names_a_store_that_no_longer_exists() -> None:
    """Otherwise a stale entry silently excuses a store with the same name."""
    found = set(_module_level_mutables())
    classified = RESTORED_BY_FIXTURE | NOT_RUNTIME_MUTATED
    assert not sorted(classified - found), sorted(classified - found)


def test_the_two_classifications_do_not_overlap() -> None:
    """A store cannot be both restored and never written."""
    assert not RESTORED_BY_FIXTURE & NOT_RUNTIME_MUTATED


def test_the_fixture_actually_restores_everything_it_claims() -> None:
    """The claim in ``RESTORED_BY_FIXTURE`` is checked against the restore block.

    A name could sit in that set while the fixture never puts it back, which
    would turn this file into documentation of an intention rather than a guard.

    The check is scoped to the text **after** ``finally:`` on purpose. Written
    against the whole file it passed while the restore was deleted and only the
    snapshot line remained - measured: removing
    ``authz._JWKS_CACHE.clear()``/``.update(...)`` from the fixture left
    ``jwks_cache = dict(authz._JWKS_CACHE)`` behind, the substring still
    matched, and this test stayed green. Capturing a store and never restoring
    it is exactly the half-done state the set is supposed to rule out.
    """
    text = pathlib.Path(__file__).with_name("conftest.py").read_text(encoding="utf-8")
    marker = "    finally:"
    assert marker in text, "the fixture no longer has a finally: restore block"
    restore_block = text.split(marker, 1)[1]
    for dotted in sorted(RESTORED_BY_FIXTURE):
        module, _, attribute = dotted.rpartition(".")
        short = module.rsplit(".", 1)[-1]
        if attribute in {"_REQUEST_OBSERVATIONS", "_EXPORT_ERRORS"}:
            # Restored through the module's own reset/replay API rather than by
            # name, because the ring buffers are not rebindable in place.
            assert "reset_request_observability()" in restore_block, dotted
            assert "record_request_observation(" in restore_block, dotted
            continue
        assert f"{short}.{attribute}" in restore_block, dotted
