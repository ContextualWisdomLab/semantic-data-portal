#!/usr/bin/env python3
"""Atheris coverage-guided harness for the query executor / keyword firewall.

Targets ``sdp.orchestrator.execute_query``. The oracle asserts that any query
containing a forbidden keyword is rejected (never SUCCEEDED) and that the
executor always returns a well-formed ``QueryExecutionResponse``.

Run locally:
    python tests/fuzz/atheris/fuzz_execute_query.py -atheris_runs=200000
    python tests/fuzz/atheris/fuzz_execute_query.py tests/fuzz/corpus/execute_query
"""
import sys

import atheris

with atheris.instrument_imports():
    import pydantic

    from sdp.domain import QueryExecutionRequest
    from tests.fuzz import invariants

_LANGS = ["SQL", "sql", "  SQL  ", "python", "trino"]
_USERS = ["analyst", "anonymous", "admin", "security"]
_PURPOSES = ["analysis", "external-export", "governance"]
_DATASETS = ["crm-customer-master", "crm-event", "marketing-campaign", "missing"]


def TestOneInput(data: bytes) -> None:
    fdp = atheris.FuzzedDataProvider(data)
    ds = [
        fdp.PickValueInList(_DATASETS) for _ in range(fdp.ConsumeIntInRange(1, 3))
    ]
    language = fdp.PickValueInList(_LANGS)
    user = fdp.PickValueInList(_USERS)
    purpose = fdp.PickValueInList(_PURPOSES)
    dry_run = fdp.ConsumeBool()
    query = fdp.ConsumeUnicodeNoSurrogates(fdp.remaining_bytes())
    if not query:
        return  # query has min_length=1
    try:
        req = QueryExecutionRequest(
            language=language,
            user=user,
            purpose=purpose,
            dataset_ids=ds,
            query=query,
            dry_run=dry_run,
        )
    except pydantic.ValidationError:
        return
    invariants.check_execute_query(req)


def main() -> None:
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
