"""Atheris fuzz target for governed SQL query safety validation."""
from __future__ import annotations

import sys
from pathlib import Path

# ClusterFuzzLite runs this file as ``python fuzz/fuzz_query_safety.py`` from
# ``/src`` with ``PYTHONPATH=/src/src`` (.clusterfuzzlite/Dockerfile), so
# ``sys.path[0]`` is **this file's directory**, not the repository root. Two
# separate things were wrong about importing the shared oracle below, and the
# image is the only place either one shows: the root was on the path nowhere,
# *and* the image did not contain ``tests`` at all. The oracle stays in
# ``tests/fuzz/invariants.py`` so both engines check one invariant; the image now
# copies ``tests/fuzz`` and the repository root goes on the path here. Moving the
# oracle into ``fuzz/`` instead does not work: ``tests/fuzz`` is itself imported
# as top-level ``fuzz`` under pytest, so it would shadow the new module.
# This file is the one harness ``tests/fuzz/run_atheris.sh`` never runs, so only
# ``tests/test_fuzz_harness_imports.py`` stands between it and silence.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import atheris

with atheris.instrument_imports():
    from sdp.orchestrator import _source_table_name, validate_sql_query
    from tests.fuzz.invariants import (
        COLLIDING_SEPARATORS,
        check_validate_sql_query,
        near_miss_reference,
    )


def _text(provider: atheris.FuzzedDataProvider, max_length: int = 96) -> str:
    return provider.ConsumeUnicodeNoSurrogates(max_length)


def TestOneInput(data: bytes) -> None:
    """Exercise query-safety invariants over arbitrary source/query text."""
    provider = atheris.FuzzedDataProvider(data)
    source_system = _text(provider) or "warehouse/customer_events"
    table_name = _source_table_name(source_system)
    prefix = provider.PickValueInList(["SELECT", "select", "DELETE", "UPDATE", ""])
    projection = provider.PickValueInList(["*", "count(*)", "customer_id", _text(provider, 32) or "*"])
    suffix = _text(provider)

    # ``declared_relation`` became a live input when the allow-list stopped
    # guessing the relation from the connection locator; ``None`` keeps the
    # locator fallback - which this harness is the only caller of - covered.
    declared_relation = provider.PickValueInList([None, _text(provider, 48), table_name])

    # Drawing the FROM target and the declared relation independently never
    # lands on a reference that differs from the authorised name *only* by a
    # character that normalises back onto it - the region where the allow-list
    # certified nine different relations as the declared one. So one mode builds
    # that coincidence instead of waiting for the engine to find it. One
    # separator per input: two "$" would trip the dollar-quote guard first and
    # the refusal would not be the one under test.
    authorised = declared_relation if declared_relation else table_name
    from_target = table_name
    if provider.PickValueInList([True, False]):
        from_target = (
            near_miss_reference(
                authorised,
                provider.PickValueInList(list(COLLIDING_SEPARATORS)),
                provider.ConsumeIntInRange(0, 8),
            )
            or table_name
        )
    query = f"{prefix} {projection} FROM {from_target} {suffix}"

    warnings = validate_sql_query(
        query, source_system=source_system, declared_relation=declared_relation
    )
    assert len(warnings) == len(set(warnings))
    if not query.strip().lower().startswith("select "):
        assert "only_select_allowed" in warnings
    if ";" in query:
        assert "single_statement_required" in warnings
    if " drop " in f" {query.lower()} ":
        assert "forbidden_keyword_detected" in warnings

    # The shared oracle, so this harness and the Hypothesis mirror in
    # ``tests/fuzz`` cannot drift apart on what counts as a violation.
    check_validate_sql_query(query, source_system, declared_relation)


def main() -> None:
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
