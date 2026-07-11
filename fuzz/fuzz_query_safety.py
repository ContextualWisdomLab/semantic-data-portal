"""Atheris fuzz target for governed SQL query safety validation."""
from __future__ import annotations

import sys

import atheris

with atheris.instrument_imports():
    from sdp.orchestrator import _source_table_name, validate_sql_query


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
    query = f"{prefix} {projection} FROM {table_name} {suffix}"

    warnings = validate_sql_query(query, source_system=source_system)
    assert len(warnings) == len(set(warnings))
    if not query.strip().lower().startswith("select "):
        assert "only_select_allowed" in warnings
    if ";" in query:
        assert "single_statement_required" in warnings
    if " drop " in f" {query.lower()} ":
        assert "forbidden_keyword_detected" in warnings


def main() -> None:
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
