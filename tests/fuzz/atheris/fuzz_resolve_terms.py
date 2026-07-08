#!/usr/bin/env python3
"""Atheris coverage-guided harness for the free-text ontology resolver.

Targets ``sdp.ontology.resolve_terms`` / ``search_concepts`` / ``concept_graph``
— the surfaces that turn an arbitrary NL question into ranked ontology terms.

Run locally:
    python tests/fuzz/atheris/fuzz_resolve_terms.py -atheris_runs=200000
    python tests/fuzz/atheris/fuzz_resolve_terms.py tests/fuzz/corpus/resolve_terms
"""
import sys

import atheris

with atheris.instrument_imports():
    from tests.fuzz import invariants


def TestOneInput(data: bytes) -> None:
    fdp = atheris.FuzzedDataProvider(data)
    text = fdp.ConsumeUnicodeNoSurrogates(fdp.remaining_bytes())
    invariants.check_resolve_terms(text)
    invariants.check_search_concepts(text)
    invariants.check_concept_graph(text)


def main() -> None:
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
