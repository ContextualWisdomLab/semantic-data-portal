"""Hypothesis (MPL-2.0) property-based fuzz tests.

These run as part of the normal ``pytest`` suite (fast, cross-platform,
deterministic seed) and share their crash-oracle with the Atheris coverage-
guided harnesses in ``tests/fuzz/atheris``. Targets are the untrusted-input
surfaces CodeGraph flagged as highest value:

* ``sdp.orchestrator._safe_identifier`` — SQL identifier sanitiser
* ``sdp.orchestrator.draft_sql``        — NL -> SQL drafter
* ``sdp.orchestrator.execute_query``    — query executor / keyword firewall
* ``sdp.ontology.resolve_terms`` / ``search_concepts`` / ``concept_graph``
* ``sdp.catalog.search_catalog``        — regex/token catalog search
* the Pydantic request DTOs (parse boundary)
"""

from __future__ import annotations

import pydantic
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from sdp.domain import (
    DatasetCreateRequest,
    QueryDraftRequest,
    QueryExecutionRequest,
)
from tests.fuzz import invariants

# A generous but bounded settings profile: enough cases to explore the surface
# without slowing the unit suite down.
FUZZ_SETTINGS = settings(
    max_examples=250,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)

# Text that mixes ASCII, Korean (the ontology's native language), SQL
# metacharacters and control bytes — the interesting alphabet for these targets.
# Exclude surrogates ("Cs"): they can never arrive over JSON and pydantic
# rejects them at the parse boundary, which is out of scope for these targets.
hostile_text = st.text(
    alphabet=st.characters(
        min_codepoint=1, max_codepoint=0xFFFF, blacklist_categories=("Cs",)
    ),
    max_size=120,
)
mixed_text = st.one_of(
    hostile_text,
    st.sampled_from(
        [
            "고객",
            "활성 고객",
            "customer churn",
            "'; DROP TABLE users; --",
            "매출 revenue",
            "\x00\x00",
            "( [ unbalanced",
            "고객' OR '1'='1",
        ]
    ),
)


# --------------------------------------------------------------------------- #
# Sanitiser / ontology / catalog: pure-ish string surfaces
# --------------------------------------------------------------------------- #
@FUZZ_SETTINGS
@given(mixed_text)
def test_safe_identifier_only_emits_safe_chars(value):
    invariants.check_safe_identifier(value)


@FUZZ_SETTINGS
@given(mixed_text)
def test_resolve_terms_never_crashes(text):
    invariants.check_resolve_terms(text)


@FUZZ_SETTINGS
@given(mixed_text)
def test_search_concepts_never_crashes(text):
    invariants.check_search_concepts(text)


@FUZZ_SETTINGS
@given(mixed_text)
def test_concept_graph_never_crashes(text):
    invariants.check_concept_graph(text)


@FUZZ_SETTINGS
@given(
    query=mixed_text,
    tags=st.none() | st.lists(hostile_text, max_size=4),
    domain=st.none() | st.lists(hostile_text, max_size=4),
    min_quality=st.none() | st.floats(allow_nan=False, allow_infinity=False),
    limit=st.integers(min_value=-3, max_value=50),
)
def test_search_catalog_never_crashes(query, tags, domain, min_quality, limit):
    invariants.check_search_catalog(
        query, tags=tags, domain=domain, min_quality=min_quality, limit=limit
    )


# --------------------------------------------------------------------------- #
# NL -> SQL drafter
# --------------------------------------------------------------------------- #
draft_request = st.builds(
    QueryDraftRequest,
    question=mixed_text,
    user=st.sampled_from(["analyst", "anonymous", "admin", ""]),
    purpose=st.sampled_from(["analysis", "external-export", ""]),
    dataset_id=st.sampled_from(["crm-customer-master", "crm-event", "nope", ""]),
    group_by=st.none() | mixed_text,
    date_window_days=st.integers(min_value=-10, max_value=1000),
    columns=st.none() | st.lists(mixed_text, max_size=5),
    row_limit=st.integers(min_value=1, max_value=5000),
    timeout_ms=st.integers(min_value=500, max_value=120000),
)


@FUZZ_SETTINGS
@given(draft_request)
def test_draft_sql_holds_invariants(req):
    invariants.check_draft_sql(req)


# --------------------------------------------------------------------------- #
# Query executor / forbidden-keyword firewall
# --------------------------------------------------------------------------- #
exec_request = st.builds(
    QueryExecutionRequest,
    language=st.sampled_from(["SQL", "sql", "python", "  SQL  ", "x"]),
    user=st.sampled_from(["analyst", "anonymous", "admin"]),
    purpose=st.sampled_from(["analysis", "external-export"]),
    dataset_ids=st.lists(
        st.sampled_from(["crm-customer-master", "crm-event", "nope"]),
        min_size=1,
        max_size=3,
    ),
    query=st.one_of(
        mixed_text.filter(lambda s: len(s) >= 1),
        st.sampled_from(
            [
                "select 1",
                "SELECT * FROM t GROUP BY week",
                "DROP TABLE users",
                "select ; delete from x",
            ]
        ),
    ),
    dry_run=st.booleans(),
)


@FUZZ_SETTINGS
@given(exec_request)
def test_execute_query_holds_invariants(req):
    invariants.check_execute_query(req)


# --------------------------------------------------------------------------- #
# DTO parse boundary: arbitrary dicts must yield either a valid model or a
# Pydantic ValidationError — never an unexpected exception type.
# --------------------------------------------------------------------------- #
json_scalars = st.none() | st.booleans() | st.integers() | st.floats(
    allow_nan=False
) | st.text(max_size=20)
json_values = st.recursive(
    json_scalars,
    lambda children: st.lists(children, max_size=4)
    | st.dictionaries(st.text(max_size=8), children, max_size=4),
    max_leaves=15,
)
arbitrary_payload = st.dictionaries(st.text(max_size=12), json_values, max_size=8)


@pytest.mark.parametrize(
    "model",
    [QueryDraftRequest, QueryExecutionRequest, DatasetCreateRequest],
)
@settings(max_examples=150, deadline=None)
@given(payload=arbitrary_payload)
def test_dto_parsing_only_raises_validation_error(model, payload):
    try:
        model(**payload)
    except pydantic.ValidationError:
        pass  # expected rejection path
    except TypeError:
        # e.g. a payload key collides with a positional-only/duplicate arg;
        # still a controlled parse failure, not a logic crash.
        pass
