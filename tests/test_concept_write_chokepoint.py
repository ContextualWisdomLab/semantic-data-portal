"""Every vocabulary write passes the shared validator — asserted, not named.

``tests/test_concept_shape_gate.py`` carries a test called
``test_the_gate_cannot_be_bypassed_by_a_future_caller``, and an adversarial
review found that the name was standing in for the evidence: it only asserted
that ``validate_concept_registration(..., definition="")`` raises, which another
test in the same file already covers, and said nothing about write sites or
callers. The reviewer appended sixteen lines to ``sdp/ontology.py`` -

    def bulk_import_concepts(records):
        for name, payload in records.items():
            record = concept_record(definition=payload.get("definition", ""), ...)
            _CONCEPT_DEFINITIONS[name] = record
            _index_concept_terms(name, record)
        return len(records)

- and measured **1112 passed, 11 skipped** before and after, identical, while
the new function published definition-less concepts into every ontology read
surface (``/ontology/concept/{term}`` served ``definition: ''``,
``/ontology/search`` found it, and ``concept_conformance`` dropped to 0.714).

"Cannot be bypassed" is a property of the *shape of the code*, so it is checked
mechanically here, in the idiom ``tests/test_module_state_coverage.py`` already
uses: enumerate the write sites rather than trusting that the current ones are
all of them.

Reverse-verified with exactly that mutation: both tests below fail on it.
"""

from __future__ import annotations

import ast
import pathlib


SRC = pathlib.Path(__file__).resolve().parents[1] / "src"
VOCABULARY = "_CONCEPT_DEFINITIONS"
GATE = "validate_concept_registration"

# The functions permitted to write the vocabulary, and what makes each safe.
# A new entry here is a deliberate decision with a reason, which is the point:
# the alternative is a new write site nobody notices.
DECLARED_WRITE_SITES = {
    # The one runtime publication. Its first statement is the shared validator.
    "_register_concept_locked": "gated",
    # Removal at the vocabulary cap. A deletion cannot publish unvalidated
    # content, and it records its own change-log entry.
    "_evict_one_registered_concept": "deletion",
    # The shipped vocabulary, a module-level literal evaluated at import.
    "<module>": "seed",
}

# Everything in src/ that may call ``register_concept``. The gate lives in the
# validator rather than in each route precisely so this set can grow without a
# caller forgetting it - but a *new* caller is still a decision to make
# knowingly.
DECLARED_REGISTRAR_CALLERS = {
    "ingest_concept",          # POST /ontology/concepts
    "_review_patch_locked",    # POST /ontology/patches/{id}/review, on approve
}


def _python_files() -> list[pathlib.Path]:
    return sorted(SRC.rglob("*.py"))


def _enclosing_function(tree: ast.Module, node: ast.AST) -> str:
    """The name of the innermost function containing ``node``, or ``<module>``."""
    best = "<module>"
    best_span = None
    for candidate in ast.walk(tree):
        if not isinstance(candidate, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        start = candidate.lineno
        end = getattr(candidate, "end_lineno", start)
        if start <= node.lineno <= end:
            span = end - start
            if best_span is None or span < best_span:
                best, best_span = candidate.name, span
    return best


def _vocabulary_write_sites() -> list[tuple[str, int, str]]:
    """Every statement in ``src/`` that stores into or deletes from the vocabulary."""
    found: list[tuple[str, int, str]] = []
    for path in _python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            targets: list[ast.AST] = []
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = list(getattr(node, "targets", [])) or [node.target]
            elif isinstance(node, ast.Delete):
                targets = list(node.targets)
            elif isinstance(node, ast.AugAssign):
                targets = [node.target]
            for target in targets:
                base = target
                if isinstance(base, ast.Subscript):
                    base = base.value
                name = (
                    base.id
                    if isinstance(base, ast.Name)
                    else getattr(base, "attr", None)
                )
                if name == VOCABULARY:
                    found.append(
                        (
                            str(path.relative_to(SRC)),
                            node.lineno,
                            _enclosing_function(tree, node),
                        )
                    )
            # A mutating method call on the vocabulary is a write too.
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr
                in {"update", "setdefault", "pop", "popitem", "clear"}
            ):
                owner = node.func.value
                owner_name = (
                    owner.id if isinstance(owner, ast.Name) else getattr(owner, "attr", None)
                )
                if owner_name == VOCABULARY:
                    found.append(
                        (
                            str(path.relative_to(SRC)),
                            node.lineno,
                            _enclosing_function(tree, node),
                        )
                    )
    return found


def _first_statement_calls(function: ast.FunctionDef, callee: str) -> bool:
    """Whether ``function``'s first executable statement calls ``callee``."""
    body = list(function.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        body = body[1:]  # the docstring
    if not body:
        return False
    for node in ast.walk(body[0]):
        if isinstance(node, ast.Call):
            name = (
                node.func.id
                if isinstance(node.func, ast.Name)
                else getattr(node.func, "attr", None)
            )
            if name == callee:
                return True
    return False


def test_every_vocabulary_write_site_is_declared() -> None:
    """A new write site must be classified, not merely added.

    The mutation that proved this missing added one: a module-level function
    writing ``_CONCEPT_DEFINITIONS`` directly, with the whole suite green.
    """
    undeclared = sorted(
        {
            (path, line, function)
            for path, line, function in _vocabulary_write_sites()
            if function not in DECLARED_WRITE_SITES
        }
    )
    assert not undeclared, (
        "these statements write the concept vocabulary from a function that is "
        "not declared as a write site, so they do not pass the shared validator: "
        f"{undeclared}"
    )


def test_the_publishing_write_site_validates_first() -> None:
    """The gate is the first thing the publishing function does.

    Checked structurally rather than by reading: a gate moved below the write,
    or wrapped in a conditional, would still be "present in the function".
    """
    publisher = None
    for path in _python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == "_register_concept_locked"
            ):
                publisher = node
    assert publisher is not None, "the publishing function was renamed"
    assert _first_statement_calls(publisher, GATE), (
        f"{publisher.name}'s first statement no longer calls {GATE}, so a write "
        "can reach the vocabulary before the shape gate and the kind check"
    )


def test_the_registrars_callers_are_the_declared_ones() -> None:
    """A third caller is a decision, not an accident.

    The gate's placement in the shared validator is what makes a new caller
    safe; this keeps the set visible so "safe" stays a claim someone checked.
    """
    callers: set[str] = set()
    for path in _python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = (
                node.func.id
                if isinstance(node.func, ast.Name)
                else getattr(node.func, "attr", None)
            )
            if name == "register_concept":
                enclosing = _enclosing_function(tree, node)
                if enclosing != "register_concept":
                    callers.add(enclosing)
    assert callers == DECLARED_REGISTRAR_CALLERS, (
        f"register_concept's callers in src/ are {sorted(callers)}, declared "
        f"{sorted(DECLARED_REGISTRAR_CALLERS)}"
    )


def test_the_enumeration_finds_the_sites_it_is_supposed_to() -> None:
    """Guard the scanner: an enumeration that finds nothing passes vacuously."""
    sites = _vocabulary_write_sites()
    functions = {function for _, _, function in sites}
    assert "_register_concept_locked" in functions, sites
    assert "_evict_one_registered_concept" in functions, sites
    assert len(sites) >= 3, sites
