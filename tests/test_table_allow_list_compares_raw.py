"""The source-table allow-list must compare what the query says, not a rewrite.

``validate_sql_query`` holds the one allow-list that decides whether a
hand-written statement may touch the warehouse. It compared the query's table
references to the catalog's declared relation **after** pushing each reference
through ``_safe_identifier``, which maps every non-alphanumeric byte to ``_``.
The declared relations in this catalogue contain underscores, so normalisation
*manufactured* matches: three references naming three different relations all
collapsed onto one declared name and were certified clean.

Measured against declared ``crm_customer_master`` before the repair - nine
references naming nine different relations, every one certified clean::

    select id from crm_customer_master   []  <- the real one
    select id from crm.customer_master   []  <- a different schema
    select id from crm$customer_master   []  <- not even an identifier
    select id from crm_customer.master   []  <- table "master" in schema "crm_customer"
    select id from crm.customer.master   []  <- three levels
    select id from crm·customer_master   []  <- MIDDLE DOT, a Postgres identifier character
    select id from crm．customer_master   []  <- FULLWIDTH FULL STOP, a "." confusable

``POST /browse/query`` answered ``200`` for the second of those against the
seed dataset ``crm-customer-master``, so this is not an internal-helper
nicety: the governed route certified a statement reading another schema.

The comment above the comparison argued the opposite conclusion from the same
mechanism - "``_safe_identifier`` maps the dot to ``_``, so a qualified name can
never collide with the bare one". That is true only of the case it was written
for (``pg_catalog.customer`` vs bare ``customer``, where normalisation *adds*
characters the expected name lacks). Where the declared name already contains
the character normalisation produces, the mapping is a collision engine, and the
underscore is the one character every relation in this catalogue contains.

The reference is raw text from the caller; the declared relation is resolved by
``source_relation_name``, which has already sanitised it and checked that it
reads back as one table. Normalising the untrusted side to match the trusted one
is backwards: comparing them raw is strictly tighter, and the drafter's own
output still passes because it emits the declared name verbatim.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sdp.api import app
from sdp.orchestrator import (
    _referenced_source_tables,
    _safe_identifier,
    source_relation_name,
    validate_sql_query,
)
from sdp import catalog

DECLARED = "crm_customer_master"
DATASET_ID = "crm-customer-master"

# Every one of these names a relation that is **not** the declared one, and
# every one of them normalises onto it. The set is measured, not guessed: the
# first draft of this list also carried ``crm customer_master``,
# ``crm-customer_master`` and ``crm/customer_master``, and the collision guard
# below rejected them - ``_TABLE_LIST_TOKEN`` is
# ``[A-Za-z_\u0080-\uffff][\w.$\u0080-\uffff]*``, so a space, dash or slash ends
# the token and those three parse as the table ``crm``, already refused for a
# different reason. Only a character the token regex keeps *and*
# ``_safe_identifier`` rewrites can collide: ASCII ``.`` and ``$``, plus any
# non-alphanumeric character above U+007F. ``crm$customer$master`` is excluded
# because two dollars trip ``literal_values_not_allowed`` first.
COLLIDING = [
    "crm.customer_master",      # a different schema
    "crm$customer_master",      # not a valid identifier at all
    "crm_customer.master",      # table "master" in schema "crm_customer"
    "crm_customer$master",
    "crm.customer.master",      # three levels
    "crm.customer$master",      # mixed
    "crm\u00b7customer_master",  # MIDDLE DOT - a real Postgres identifier character
    "crm\u2024customer_master",  # ONE DOT LEADER, a "." confusable
    "crm\uff0ecustomer_master",  # FULLWIDTH FULL STOP, another one
]


def test_the_declared_relation_is_still_accepted() -> None:
    """The premise: tightening must not refuse the catalog's own relation."""
    assert validate_sql_query(
        f"select customer_id from {DECLARED} limit 10",
        source_system="postgresql://analytics.dw/customer",
        declared_relation=DECLARED,
    ) == []


def test_the_catalog_really_declares_this_relation() -> None:
    """Measured, not assumed: the fixture is the product's own seed dataset."""
    dataset = catalog.get_dataset(DATASET_ID)
    assert source_relation_name(dataset) == DECLARED
    assert "_" in DECLARED, "the collision needs the declared name to contain '_'"


@pytest.mark.parametrize("reference", COLLIDING)
def test_a_reference_that_is_not_the_declared_relation_is_refused(reference: str) -> None:
    """The defect: a different relation was certified clean after normalisation."""
    warnings = validate_sql_query(
        f"select customer_id from {reference} limit 10",
        source_system="postgresql://analytics.dw/customer",
        declared_relation=DECLARED,
    )
    assert "unauthorized_table_reference" in warnings, (
        f"{reference!r} is not {DECLARED!r}, yet the allow-list accepted it: {warnings}"
    )


@pytest.mark.parametrize("reference", COLLIDING)
def test_each_case_is_a_normalisation_collision_not_a_parse_failure(reference: str) -> None:
    """Pin *why* these passed, so a parser change cannot make the guard vacuous.

    If a case stopped being read as a table reference at all it would be
    refused for a different reason and this file would still be green while the
    collision it exists for went unexercised.
    """
    referenced = _referenced_source_tables(f"select customer_id from {reference} limit 10")
    assert referenced, reference
    assert reference not in {DECLARED}, reference
    assert {_safe_identifier(table).lower() for table in referenced} == {DECLARED}, (
        f"{reference!r} no longer normalises onto {DECLARED!r}; this case no "
        "longer exercises the defect"
    )


def test_the_governed_route_refuses_the_colliding_reference() -> None:
    """The buyer-visible form: /browse/query certified the other schema's table."""
    client = TestClient(app)
    response = client.post(
        "/browse/query",
        json={
            "user": "analyst",
            "purpose": "analysis",
            "dataset_ids": [DATASET_ID],
            "query": "select customer_id from crm.customer_master limit 10",
        },
    )
    assert response.status_code == 400, (response.status_code, response.json())
    detail = response.json()["detail"]
    assert detail["status"] == "REJECTED", detail
    assert "unauthorized_table_reference" in detail["warnings"], detail


# --------------------------------------------------------------------------
# Both engines have to reach the near-miss region by construction. The shared
# oracle owns that construction so the two cannot drift; these exercise it, and
# then drive the Atheris harness's body - which nothing else here executes,
# since Atheris itself is not installed in this environment.
# --------------------------------------------------------------------------

import contextlib
import importlib.util
import types

from tests.fuzz import invariants


def test_near_miss_reference_builds_a_colliding_name() -> None:
    """Each separator must yield a name that normalises back onto the original."""
    for separator in invariants.COLLIDING_SEPARATORS:
        near_miss = invariants.near_miss_reference(DECLARED, separator, 0)
        assert near_miss is not None and near_miss != DECLARED
        referenced = _referenced_source_tables(f"select 1 from {near_miss}")
        assert referenced == [near_miss], (separator, referenced)
        assert {_safe_identifier(table).lower() for table in referenced} == {DECLARED}


def test_near_miss_reference_declines_a_name_with_no_underscore() -> None:
    """A caller that cannot build a near miss is told so, not handed the original.

    Returning the name unchanged would make every near-miss example a test of
    the authorised name against itself - green, and vacuous.
    """
    assert invariants.near_miss_reference("customer", ".", 0) is None


def test_near_miss_reference_wraps_the_seam_index() -> None:
    """The seam is drawn from a fixed range by both engines, so it must wrap."""
    seams = {invariants.near_miss_reference(DECLARED, ".", seam) for seam in range(9)}
    assert seams == {"crm.customer_master", "crm_customer.master"}, seams


def _load_harness(monkeypatch: pytest.MonkeyPatch) -> types.ModuleType:
    """Import ``fuzz/fuzz_query_safety.py`` with a stub Atheris, never fuzzing.

    ``sys.modules`` is restored by ``monkeypatch`` so importing the harness
    cannot change what a later test file sees - the five-order isolation gate
    would otherwise depend on where this file lands.
    """
    class _Provider:
        """A deterministic stand-in for ``atheris.FuzzedDataProvider``."""

        def __init__(self, data: bytes) -> None:
            self._data = data or b"\x00"
            self._cursor = 0

        def _next(self) -> int:
            value = self._data[self._cursor % len(self._data)]
            self._cursor += 1
            return value

        # A mixed alphabet, not just a-z. The real provider yields arbitrary
        # unicode, and ``_source_table_name`` runs it through
        # ``_safe_identifier``, which maps every non-alphanumeric byte to "_" -
        # so in the image the authorised name is full of underscores and the
        # near-miss mode fires constantly. A letters-only stub produced an
        # authorised name with no underscore on all 64 inputs, so
        # ``near_miss_reference`` returned ``None`` every time and the branch,
        # though entered, did nothing.
        _ALPHABET = "abcdefghijklmnopqrstuvwxyz_-./ 0123456789\u00b7\u00e9"

        def ConsumeUnicodeNoSurrogates(self, length: int) -> str:
            return "".join(
                self._ALPHABET[self._next() % len(self._ALPHABET)]
                for _ in range(self._next() % max(length, 1))
            )

        def PickValueInList(self, values: list) -> object:
            return values[self._next() % len(values)]

        def ConsumeIntInRange(self, low: int, high: int) -> int:
            return low + self._next() % (high - low + 1)

    stub = types.ModuleType("atheris")
    stub.instrument_imports = contextlib.nullcontext
    stub.FuzzedDataProvider = _Provider
    monkeypatch.setitem(sys.modules, "atheris", stub)
    harness_path = Path(__file__).resolve().parents[1] / "fuzz" / "fuzz_query_safety.py"
    spec = importlib.util.spec_from_file_location("harness_under_test", harness_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_harness_body_takes_the_near_miss_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    """The harness's new mode must actually run, and its oracle must hold.

    Driving ``TestOneInput`` here is the only local execution this harness
    gets: Atheris has no wheel in this environment, so a coverage-guided run is
    not part of the evidence for this change. What is verified is that the body
    executes over varied input, reaches the constructed near-miss mode, and
    raises nothing.
    """
    module = _load_harness(monkeypatch)
    reached = []
    original = module.near_miss_reference

    def recording(name: str, separator: str, seam: int) -> str | None:
        result = original(name, separator, seam)
        reached.append((name, separator, result))
        return result

    monkeypatch.setattr(module, "near_miss_reference", recording)
    for seed in range(64):
        module.TestOneInput(bytes([seed, seed * 7 % 251, seed * 13 % 241, 3, 9, 17]))
    assert reached, "no input took the near-miss branch"
    assert any(result is not None for _, _, result in reached), reached
