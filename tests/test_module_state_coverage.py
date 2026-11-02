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

import ast
import collections
import contextvars
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
        "sdp.evidence._RECORDED_AUDIT_EVENT_COUNT",
        "sdp.evidence._RECORDED_POLICY_DECISION_COUNT",
        "sdp.evidence._STORE_AUDIT_WRITE_FAILURES",
        "sdp.evidence._STORE_DECISION_WRITE_FAILURES",
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
        "sdp.ontology._PATCH_QUEUE_STATE",
        "sdp.ontology._VOCABULARY_STATE",
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

# Module-level names that hold *which backend is active*, rebound only by an
# explicit configuration call or a lazy first construction - never by request
# handling. What accumulates inside them is restored separately: the graph
# store's five collections are snapshotted by the fixture, and evidence rows
# live in the two logs above or in the configured store itself. Rebinding these
# per test is what the fixture must *not* do, since a test that selects a
# backend does so through ``monkeypatch``, whose own teardown puts it back.
REBOUND_BY_BACKEND_SELECTION = frozenset(
    {
        "sdp.evidence._STORE",
        "sdp.graph_store._STORE",
    }
)

# Module-level objects whose *value* is rebound through their own API rather
# than by assignment, so neither enumeration below can see them: a ``global``
# statement is not involved and the object is not one of ``_MUTABLE_TYPES``.
#
# This is a third way module state changes at runtime, and the round that added
# the ``global`` enumeration claimed the two together were "every way". They are
# not. ``_REQUEST_EVIDENCE_IDS`` was already in the tree, in none of the three
# sets, with this file green - found by review, not by this file.
#
# A ``ContextVar`` needs no restore because the request path sets it and resets
# it by token, so a test cannot inherit another test's value. That is a
# classification, which is what this file asks for; it is not an exemption from
# being listed.
#
# The paragraph above defines a wider class than this set can hold, and saying
# so is the point. The only enumeration feeding it is ``ContextVar`` by
# ``isinstance``, so a name in this set that is *not* a ``ContextVar`` is
# rejected by ``test_no_classification_names_a_store_that_no_longer_exists`` - the set
# cannot currently hold the other members of its own definition. Two are known
# and recorded as open rather than classified here: an ``lru_cache`` on a
# module-level function (three live in ``src/``) and an attribute of a
# module-level object or class. Widening the enumeration needs a premise for
# "rebound through its own API" that is decidable by import, and there is none
# yet - which is a different change from this round.
REBOUND_THROUGH_THEIR_OWN_API = frozenset(
    {
        "sdp.evidence._REQUEST_EVIDENCE_IDS",
    }
)

_MUTABLE_TYPES = (dict, list, set, bytearray, collections.deque)


def _modules_to_scan() -> list[tuple[str, object]]:
    """Both packages and every submodule, as ``(dotted_name, module)`` pairs.

    ``pkgutil.iter_modules`` yields a package's submodules and never the
    package itself, so all three enumerations here had a whole file per package
    they did not read. Latent when review measured it - ``sdp/__init__.py`` is
    a docstring and ``sdp_core/__init__.py`` is re-exports plus ``__all__``,
    which the ``__`` filter skips anyway - and a silent blind spot the moment
    anyone puts a counter or a cache in a package ``__init__``. A guard whose
    stated premise is "enumerated from the modules, not listed from memory"
    does not get to skip two of them.
    """
    scanned: list[tuple[str, object]] = []
    for package in (sdp, sdp_core):
        scanned.append((package.__name__, package))
        for info in pkgutil.iter_modules(package.__path__, package.__name__ + "."):
            scanned.append((info.name, importlib.import_module(info.name)))
    return scanned


def _module_level_mutables() -> dict[str, object]:
    """Every module-level mutable container in both packages, by import."""
    found: dict[str, object] = {}
    for dotted, module in _modules_to_scan():
        for name, value in vars(module).items():
            if name.startswith("__"):
                continue
            if isinstance(value, _MUTABLE_TYPES):
                found[f"{dotted}.{name}"] = value
    return found


def _module_level_context_vars() -> set[str]:
    """Module-level ``ContextVar`` objects, whose values are rebound at runtime.

    By import rather than by AST: a ``ContextVar``'s value changes through
    ``.set()``/``.reset()``, which no ``global`` statement accompanies and no
    container type reveals.
    """
    found: set[str] = set()
    for dotted, module in _modules_to_scan():
        for name, value in vars(module).items():
            if name.startswith("__"):
                continue
            if isinstance(value, contextvars.ContextVar):
                found.add(f"{dotted}.{name}")
    return found


def _global_declarations(tree: ast.Module) -> set[str]:
    """Names some function in this module rebinds with ``global``.

    Separate from its caller so the predicate can be fed a source directly.
    The caller walks real packages, so a test driving it can only assert
    properties of today's ``src/`` - and the property that matters here is that
    nothing is filtered out, which today's ``src/`` cannot demonstrate because
    every ``global`` name is also bound at import.
    """
    return {
        name
        for node in ast.walk(tree)
        if isinstance(node, ast.Global)
        for name in node.names
    }


def _module_level_rebound_names() -> set[str]:
    """Module-level names some function rebinds with ``global``, by AST.

    The enumeration above asks about a value's *type*, so it sees a container
    mutated in place and misses a scalar rebound in place of one. That is not a
    hypothetical gap: ``evidence._RECORDED_AUDIT_EVENT_COUNT`` and its policy
    sibling are plain ``int`` counters that rise on every recording attempt,
    were in neither classification, and were not restored by the fixture.

    They leaked silently, but **not** because nothing read them - that claim
    was wrong. Measured at the base commit, twelve call sites in two files
    (``test_governed_write_evidence.py``, ``test_resource_bounds.py``) already
    read them, and every one reads a *delta*
    (``before = count(); ... assert count() > before``), which is exactly why
    none of them could observe an absolute-value leak.
    ``tests/test_state_isolation.py`` already draws this distinction for the
    patch-queue counter. The leak became observable the moment a *published*
    number was derived from an absolute value: a test that floods the retention
    window then hands every later test "0 visible, 200 withheld", in whichever
    file order runs it first.

    ``global`` is the premise rather than a type guess: rebinding a
    module-level name from inside a function requires it. It is **not** the
    whole of "every way module state changes at runtime" - an earlier version
    of this docstring said that, and this round retracted it beside
    ``REBOUND_THROUGH_THEIR_OWN_API`` above while leaving the sentence standing
    here, which is two contradictory claims about one file's coverage.

    The set is the ``global`` declarations themselves. It used to be their
    intersection with an AST walk of module-scope assignments, and the walk is
    gone: this is the round's clearest case of a measurement answering a design
    question instead of asking for another test. Review planted a live
    module-level counter into a real production module six more ways that walk
    could not see - a ``match`` case body, a walrus, a ``for`` target, a
    ``with ... as`` target, an ``import ... as``, and a name created only by
    ``global`` inside a function - after an earlier round had already repaired
    three. A second draft of the walk, written to see all sixteen binding
    forms, did see them, and was deleted anyway, because the walk was never
    load-bearing: every name bound at module scope is in ``vars(module)`` after
    import, where the type enumeration above judges its value directly, and the
    one form that is not there until a function runs is the ``global``-only
    counter, which ``global`` is exactly what names. Measured: ``src/`` holds
    six ``global`` declarations and **none** is absent from ``vars(module)``,
    so the intersection was filtering nothing while the walk carried a premise
    falsifiable nine ways.

    Two forms are outside every enumeration in this file and are recorded
    rather than caught: an ``lru_cache`` on a module-level function (three live
    in ``src/`` today, and ``config.reset_config_cache()`` is the repo's own
    acknowledgement that it is cross-test state) and an attribute of a
    module-level object or class.
    """
    found: set[str] = set()
    for dotted, module in _modules_to_scan():
        source = pathlib.Path(getattr(module, "__file__", "") or "")
        if not source.is_file():
            continue
        tree = ast.parse(source.read_text(encoding="utf-8"))
        for name in _global_declarations(tree):
            found.add(f"{dotted}.{name}")
    return found


def test_every_module_level_mutable_is_classified() -> None:
    """A new store must be declared restored or declared constant.

    This is the check that was missing: the fixture and its guard both carry
    hand-written lists, so a store nobody remembered was simply absent from
    both and failed later, in one file order only.
    """
    found = (
        set(_module_level_mutables())
        | _module_level_rebound_names()
        | _module_level_context_vars()
    )
    classified = (
        RESTORED_BY_FIXTURE
        | NOT_RUNTIME_MUTATED
        | REBOUND_BY_BACKEND_SELECTION
        | REBOUND_THROUGH_THEIR_OWN_API
    )
    unclassified = sorted(found - classified)
    # The set names are listed rather than counted: the message said "one of the
    # two sets" while ``classified`` had grown to four, so a reader who tripped
    # the guard with a ``ContextVar`` or a backend handle was pointed at two
    # sets that do not fit it. Deriving the names means the next set cannot
    # leave this sentence behind.
    choices = ", ".join(
        [
            "RESTORED_BY_FIXTURE",
            "NOT_RUNTIME_MUTATED",
            "REBOUND_BY_BACKEND_SELECTION",
            "REBOUND_THROUGH_THEIR_OWN_API",
        ]
    )
    assert not unclassified, (
        "these module-level mutable stores are neither restored by "
        "tests/conftest.py's fixture nor declared constant - add them to one of "
        f"these sets in this file ({choices}), and to the fixture if they "
        f"change at runtime: {unclassified}"
    )


def test_no_classification_names_a_store_that_no_longer_exists() -> None:
    """Otherwise a stale entry silently excuses a store with the same name."""
    found = (
        set(_module_level_mutables())
        | _module_level_rebound_names()
        | _module_level_context_vars()
    )
    classified = (
        RESTORED_BY_FIXTURE
        | NOT_RUNTIME_MUTATED
        | REBOUND_BY_BACKEND_SELECTION
        | REBOUND_THROUGH_THEIR_OWN_API
    )
    assert not sorted(classified - found), sorted(classified - found)


def test_the_classifications_do_not_overlap() -> None:
    """A store gets exactly one classification, so none of them can excuse it twice."""
    sets = {
        "RESTORED_BY_FIXTURE": RESTORED_BY_FIXTURE,
        "NOT_RUNTIME_MUTATED": NOT_RUNTIME_MUTATED,
        "REBOUND_BY_BACKEND_SELECTION": REBOUND_BY_BACKEND_SELECTION,
        "REBOUND_THROUGH_THEIR_OWN_API": REBOUND_THROUGH_THEIR_OWN_API,
    }
    for left, left_set in sets.items():
        for right, right_set in sets.items():
            if left < right:
                assert not left_set & right_set, (left, right, left_set & right_set)


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



def test_a_counter_created_only_inside_a_function_is_still_named() -> None:
    """The enumeration must not filter by "also assigned at module scope".

    It used to, by intersecting with an AST walk of module-scope assignments,
    and the gap that hid was measured: a counter whose only binding is
    ``global`` plus an assignment inside a function has no module-scope
    assignment and is absent from ``vars(module)`` until that function runs, so
    it was outside the walk, outside the type enumeration and outside this one
    - the one form with no spelling of the name anywhere a reader could grep.

    Today's ``src/`` cannot show this: all six of its ``global`` names are also
    bound at import, so the intersection filtered nothing and a mutation
    re-adding it would survive the suite. The form is fed in directly instead.
    """
    created_only_in_a_function = (
        "def bump_the_counter() -> None:\n"
        "    global _ONLY_IN_A_FUNCTION_COUNT\n"
        "    _ONLY_IN_A_FUNCTION_COUNT = 1\n"
    )
    assert _global_declarations(ast.parse(created_only_in_a_function)) == {
        "_ONLY_IN_A_FUNCTION_COUNT"
    }

    also_bound_at_import = (
        "_BOUND_AT_IMPORT_COUNT = 0\n"
        "def bump_the_counter() -> None:\n"
        "    global _BOUND_AT_IMPORT_COUNT\n"
        "    _BOUND_AT_IMPORT_COUNT += 1\n"
    )
    assert _global_declarations(ast.parse(also_bound_at_import)) == {
        "_BOUND_AT_IMPORT_COUNT"
    }

    assert _global_declarations(ast.parse("_PLAIN = 0\n")) == set()


def test_the_scan_includes_the_packages_themselves() -> None:
    """``iter_modules`` yields submodules only, so the packages were unread.

    Latent when review measured it - both ``__init__`` files hold nothing this
    file would classify - so nothing in the suite could have caught the gap.
    This is the cheapest thing that can: the two package names, derived from
    the same tuple the scan walks.
    """
    scanned = {dotted for dotted, _ in _modules_to_scan()}
    assert {sdp.__name__, sdp_core.__name__} <= scanned, sorted(scanned)[:5]
    assert f"{sdp.__name__}.api" in scanned, "submodules are still scanned"




def test_a_module_scope_loop_does_not_leave_its_target_bound() -> None:
    """A loop variable that outlives its loop is state no enumeration here sees.

    ``catalog`` had one: ``for _dataset in _DATA.values():`` with no ``del``, so
    after import the module held the *same object* as a live catalog row
    (measured: ``catalog._dataset is catalog._DATA[...]`` was True). The type
    enumeration cannot judge it - a ``Dataset`` is not in ``_MUTABLE_TYPES`` -
    and no ``global`` names it, so it sat outside every set with this file
    green. ``ontology`` already deleted its equivalent, so the two modules
    differed and nothing could see the difference.

    The first draft of this guard asserted identity against the rows in
    ``catalog._DATA`` and **did not catch the planted defect**: the autouse
    fixture restores ``_DATA`` from ``model_copy(deep=True)`` snapshots, so
    after the first test's teardown the live rows are copies and the stale
    alias is identical to none of them. A guard that is green from the second
    test onward is the order-dependent shape this file exists to refuse, so it
    was withdrawn rather than fixed in place.

    This asks the syntactic question instead, which is the one with an answer:
    a ``for`` or ``with`` at module scope binds its target permanently, so the
    name must not survive import. Both forms, because both bind.
    """
    survivors = []
    for dotted, module in _modules_to_scan():
        source = pathlib.Path(getattr(module, "__file__", "") or "")
        if not source.is_file():
            continue
        bound: set[str] = set()

        def collect(node: ast.AST) -> None:
            """Collect loop and context-manager targets outside any new scope."""
            for child in ast.iter_child_nodes(node):
                if isinstance(
                    child,
                    (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda),
                ):
                    continue
                if isinstance(child, (ast.For, ast.AsyncFor)):
                    bound.update(
                        name.id
                        for name in ast.walk(child.target)
                        if isinstance(name, ast.Name)
                    )
                if isinstance(child, (ast.With, ast.AsyncWith)):
                    for item in child.items:
                        if item.optional_vars is not None:
                            bound.update(
                                name.id
                                for name in ast.walk(item.optional_vars)
                                if isinstance(name, ast.Name)
                            )
                collect(child)

        collect(ast.parse(source.read_text(encoding="utf-8")))
        survivors += [f"{dotted}.{name}" for name in sorted(bound) if hasattr(module, name)]
    assert survivors == [], (
        "these module-scope loop or with targets are still bound after import, "
        f"so the module holds whatever the last iteration left: {survivors}. "
        "Add a ``del`` after the loop, the way ``sdp.ontology`` does."
    )
