#!/usr/bin/env python3
"""Atheris coverage-guided harness for the NL -> SQL drafter.

Targets ``sdp.orchestrator.draft_sql``. The oracle (see ``invariants``) asserts
that no forbidden keyword or SQL metacharacter is ever smuggled into the
generated statement through a user-controlled identifier (``group_by`` /
``columns``), and that limits stay bounded.

Run locally:
    python tests/fuzz/atheris/fuzz_draft_sql.py -atheris_runs=200000
    python tests/fuzz/atheris/fuzz_draft_sql.py tests/fuzz/corpus/draft_sql
"""
import sys

import atheris

with atheris.instrument_imports():
    import pydantic

    from sdp.domain import QueryDraftRequest
    from tests.fuzz import invariants

_USERS = ["analyst", "anonymous", "admin", "security"]
_PURPOSES = ["analysis", "external-export", "governance"]
_DATASETS = ["crm-customer-master", "crm-event", "marketing-campaign", "missing"]


def TestOneInput(data: bytes) -> None:
    fdp = atheris.FuzzedDataProvider(data)
    try:
        req = QueryDraftRequest(
            question=fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(0, 120)),
            user=fdp.PickValueInList(_USERS),
            purpose=fdp.PickValueInList(_PURPOSES),
            dataset_id=fdp.PickValueInList(_DATASETS),
            group_by=fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(0, 40))
            or None,
            date_window_days=fdp.ConsumeIntInRange(-10, 1000),
            columns=[
                fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(0, 30))
                for _ in range(fdp.ConsumeIntInRange(0, 4))
            ]
            or None,
            row_limit=fdp.ConsumeIntInRange(1, 5000),
            timeout_ms=fdp.ConsumeIntInRange(500, 120000),
        )
    except pydantic.ValidationError:
        return  # rejected at the parse boundary — expected, not a finding
    invariants.check_draft_sql(req)


def main() -> None:
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
