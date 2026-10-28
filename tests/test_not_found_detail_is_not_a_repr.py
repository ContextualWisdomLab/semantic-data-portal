"""A 404 body must not carry a Python exception repr.

``POST /ontology/patches/{patch_id}/review`` answered a missing patch with::

    404 {"detail": "'patch not found'"}

The quotes are not part of the message. ``KeyError.__str__`` returns
``repr(args[0])``, so ``detail=str(exc)`` on a caught ``KeyError`` publishes
the Python repr rather than the message - every other 404 in this API answers
``dataset not found`` or ``node not found`` with no quoting, so a client
matching on the string sees this one route disagree with the rest.

Measured at ``bcbaae9``: of 17 probed 404-capable routes exactly **one**
leaks. The construction, though, occurs eight times in ``src/sdp/api.py``.
The other seven are shielded by an earlier existence check
(``_require_scoped_dataset`` raises the clean 404 before the ``try``), so they
are latent rather than fixed - the same body would publish a repr the moment
its ``KeyError`` arrives from anywhere else. One of those routes is a
``PATCH`` and two are mutations, so the shield is a property of today's call
order, not of the handler.

So this file checks the instance *and* the construction: a live probe of the
one reachable route, and a derived check over the module's own syntax tree so
a ninth site cannot be added quietly. The static half is parsed with ``ast``
rather than matched as text, because a guard whose parser nobody measured is
a guard checked against its own assumptions - this cycle recorded that shape
five times.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sdp.api import app  # noqa: E402

client = TestClient(app)

API_SOURCE = Path(__file__).resolve().parents[1] / "src" / "sdp" / "api.py"


def _looks_like_a_python_repr(value: object) -> bool:
    """Whether this detail is a quoted Python repr rather than a message."""
    return (
        isinstance(value, str)
        and len(value) >= 2
        and value[0] == value[-1] == "'"
    )


def test_a_missing_patch_is_reported_without_the_repr_quotes() -> None:
    """The one live instance, driven through the route that reaches it.

    The actor comes from the request **body** on this route (``actor``), not
    from ``?user=``; sending it any other way is refused at authorization and
    never reaches the lookup.
    """
    response = client.post(
        "/ontology/patches/no-such-patch/review",
        json={"actor": "admin", "decision": "approve"},
    )
    assert response.status_code == 404, response.text
    detail = response.json()["detail"]
    assert not _looks_like_a_python_repr(detail), (
        f"the 404 body carries a Python repr: {detail!r}"
    )
    assert detail == "patch not found", detail


def _key_error_handlers() -> list[ast.ExceptHandler]:
    """Every ``except KeyError`` arm in the API module, from its syntax tree."""
    tree = ast.parse(API_SOURCE.read_text())
    handlers = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ExceptHandler)
        and isinstance(node.type, ast.Name)
        and node.type.id == "KeyError"
    ]
    assert len(handlers) >= 8, len(handlers)
    return handlers


def _renders_the_exception(handler: ast.ExceptHandler) -> list[int]:
    """Lines in this handler that render the caught exception into a string.

    ``str(exc)`` is the form the repair removed, and for a ``KeyError`` it
    publishes ``repr(args[0])`` - quotes included. It is not the only form that
    does: ``f"{exc}"``, ``"{}".format(exc)`` and ``"%s" % exc`` all call the
    same ``__str__``. The first version of this detector matched only the
    ``str()`` call, so the guard's claim - that the seven latent sites cannot
    become live - held for one spelling out of four. No handler uses the other
    three today; measured, which is why this closes a hole in the guard rather
    than a defect in the product.

    One function rather than one here and a second copy inside the test that
    checks this one. Two copies of a detector is the drift the rest of this file
    exists to catch.
    """
    name = handler.name
    if name is None:
        return []
    found: list[int] = []
    for node in ast.walk(handler):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "str"
            and len(node.args) == 1
            and isinstance(node.args[0], ast.Name)
            and node.args[0].id == name
        ):
            found.append(node.lineno)
        elif isinstance(node, ast.JoinedStr):
            if any(
                isinstance(part, ast.FormattedValue)
                and isinstance(part.value, ast.Name)
                and part.value.id == name
                for part in node.values
            ):
                found.append(node.lineno)
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "format"
            and any(isinstance(arg, ast.Name) and arg.id == name for arg in node.args)
        ):
            found.append(node.lineno)
        elif (
            isinstance(node, ast.BinOp)
            and isinstance(node.op, ast.Mod)
            and isinstance(node.right, ast.Name)
            and node.right.id == name
        ):
            found.append(node.lineno)
    return sorted(set(found))


def test_no_key_error_arm_publishes_str_of_the_exception() -> None:
    """The construction, so the seven latent sites cannot become live.

    ``str(exc)`` is the defect; the message itself is in ``exc.args``. This is
    about the *handlers*, not about which routes happen to be reachable today.
    """
    offenders = [
        line for handler in _key_error_handlers() for line in _renders_the_exception(handler)
    ]
    assert not offenders, (
        "src/sdp/api.py:"
        + ", ".join(str(line) for line in sorted(offenders))
        + " render a caught KeyError into a string, which publishes "
        "repr(args[0]) - use the message instead"
    )


def test_the_parser_finds_the_pattern_it_claims_to_find() -> None:
    """The guard above is only as good as this; measured on synthetic text.

    A guard that reports zero offenders is indistinguishable from a guard that
    cannot find any, so the parser is driven over text where the answer is
    known - including two near-misses it must *not* report.
    """
    source = "\n".join(
        [
            # Four spellings of the same publication, one per KeyError arm.
            "try:",
            "    f()",
            "except KeyError as exc:",
            "    raise HTTPException(status_code=404, detail=str(exc))",
            "try:",
            "    f()",
            "except KeyError as exc:",
            '    raise HTTPException(status_code=404, detail=f"{exc}")',
            "try:",
            "    f()",
            "except KeyError as exc:",
            '    raise HTTPException(status_code=404, detail="{}".format(exc))',
            "try:",
            "    f()",
            "except KeyError as exc:",
            '    raise HTTPException(status_code=404, detail="%s" % exc)',
            # Near-misses that must NOT be reported.
            "try:",
            "    f()",
            "except KeyError as exc:",
            "    raise HTTPException(status_code=404, detail=exc.args[0])",
            "try:",
            "    f()",
            "except KeyError as exc:",
            '    raise HTTPException(status_code=404, detail="dataset not found")',
            "try:",
            "    f()",
            "except KeyError as exc:",
            '    raise HTTPException(status_code=404, detail=f"{other}")',
            "try:",
            "    f()",
            "except ValueError as exc:",
            "    raise HTTPException(status_code=400, detail=str(exc))",
            "",
        ]
    )
    tree = ast.parse(source)
    found = [
        line
        for handler in ast.walk(tree)
        if isinstance(handler, ast.ExceptHandler)
        and isinstance(handler.type, ast.Name)
        and handler.type.id == "KeyError"
        for line in _renders_the_exception(handler)
    ]
    # Lines 4, 8, 12 and 16 are the four spellings; nothing else.
    assert found == [4, 8, 12, 16], found


@pytest.mark.parametrize(
    "raised, expected",
    [
        (KeyError("patch not found"), "patch not found"),
        (KeyError("no-such-dataset"), "no-such-dataset"),
        (KeyError(), "KeyError"),
        (KeyError("a", "b"), "('a', 'b')"),
    ],
)
def test_the_renderer_unwraps_the_message_for_each_arity(
    raised: KeyError, expected: str
) -> None:
    """Zero, one and two arguments, because ``args[0]`` is not always there."""
    from sdp.api import _missing_resource_detail

    assert _missing_resource_detail(raised) == expected
