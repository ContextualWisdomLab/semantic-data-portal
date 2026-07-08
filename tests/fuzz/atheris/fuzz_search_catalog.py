#!/usr/bin/env python3
"""Atheris coverage-guided harness for the catalog token/regex search.

Targets ``sdp.catalog.search_catalog``. The search builds a compiled regex per
token; the interesting property is that arbitrary query text (regex
metacharacters, unbalanced brackets, huge inputs) never raises — i.e. tokens are
correctly escaped — and that results stay bounded and score-sorted.

Run locally:
    python tests/fuzz/atheris/fuzz_search_catalog.py -atheris_runs=200000
    python tests/fuzz/atheris/fuzz_search_catalog.py tests/fuzz/corpus/search_catalog
"""
import sys

import atheris

with atheris.instrument_imports():
    from tests.fuzz import invariants


def TestOneInput(data: bytes) -> None:
    fdp = atheris.FuzzedDataProvider(data)
    query = fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(0, 200))
    tags = [
        fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(0, 20))
        for _ in range(fdp.ConsumeIntInRange(0, 3))
    ]
    domain = [
        fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(0, 20))
        for _ in range(fdp.ConsumeIntInRange(0, 3))
    ]
    min_quality = fdp.ConsumeFloatInRange(-1.0, 2.0)
    limit = fdp.ConsumeIntInRange(-3, 50)
    invariants.check_search_catalog(
        query, tags=tags, domain=domain, min_quality=min_quality, limit=limit
    )


def main() -> None:
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
