"""A declared minimum and a default below it cannot both be true.

``QueryExecutionRequest.dataset_ids`` was declared ``Field(default_factory=list,
min_length=1)``. Pydantic does not validate a default, so the two halves
disagreed in practice:

    POST /browse/query  {... "dataset_ids": []}   -> 400  (constraint enforced)
    POST /browse/query  {... dataset_ids omitted} -> 500  Internal Server Error
      IndexError: list index out of range   (src/sdp/orchestrator.py, req.dataset_ids[0])

Both route variants crashed, on a body any client can send. Neither fuzz harness
could reach it: ``tests/fuzz/test_fuzz_properties.py`` generated
``dataset_ids`` with ``min_size=1`` and the Atheris harness with
``ConsumeIntInRange(1, 3)``, so both generators assumed the very constraint the
request path failed to enforce. A generator that assumes a constraint holds
cannot test whether it holds; both now start at zero.

The contradiction is checked here by introspecting every request model's fields,
not by listing the one that broke.
"""

from __future__ import annotations

import inspect

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel, ValidationError

import sdp_core
from sdp import catalog
from sdp.api import app
from sdp.orchestrator import execute_query
from sdp_core import QueryExecutionRequest


client = TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _isolate_catalog():
    """The provenance test plants datasets; they must not outlive it."""
    data = {key: value.model_copy(deep=True) for key, value in catalog._DATA.items()}
    try:
        yield
    finally:
        catalog._DATA.clear()
        catalog._DATA.update(data)


def _request_models() -> list[type[BaseModel]]:
    """Every pydantic model exported by the contracts package."""
    return [
        value
        for value in vars(sdp_core).values()
        if inspect.isclass(value) and issubclass(value, BaseModel) and value is not BaseModel
    ]


def test_no_field_declares_a_minimum_it_defaults_below() -> None:
    """The structural form of the defect, over every exported contract."""
    violations = []
    for model in _request_models():
        for name, field in model.model_fields.items():
            minimum = None
            for item in field.metadata:
                for attribute in ("min_length", "gt", "ge"):
                    if hasattr(item, attribute):
                        minimum = getattr(item, attribute)
            if minimum is None:
                continue
            if field.is_required():
                continue
            try:
                default = field.get_default(call_default_factory=True)
            except TypeError:  # pragma: no cover - factory needing arguments
                continue
            if default is None:
                continue
            size = len(default) if isinstance(default, (list, tuple, set, str, dict)) else default
            if isinstance(size, (int, float)) and size < minimum:
                violations.append(
                    f"{model.__name__}.{name}: default {default!r} (size {size}) "
                    f"is below its declared minimum {minimum}"
                )
    assert not violations, (
        "a field declares a minimum and defaults below it; pydantic does not "
        "validate defaults, so the constraint is unenforced when the field is "
        "omitted:\n  " + "\n  ".join(violations)
    )


@pytest.mark.parametrize("path", ["/browse/query", "/api/v1/browse/query"])
@pytest.mark.parametrize("dataset_ids", [None, []])
def test_a_missing_or_empty_dataset_list_is_a_client_error_that_names_the_field(
    path: str, dataset_ids: list[str] | None
) -> None:
    """Omitted and empty must answer alike, and say which field was wrong."""
    body = {
        "user": "analyst",
        "language": "SQL",
        "query": "select customer_id from customer",
        "purpose": "analysis",
    }
    if dataset_ids is not None:
        body["dataset_ids"] = dataset_ids

    response = client.post(path, json=body)
    assert response.status_code == 400, response.text
    assert "dataset_ids" in response.text, response.text


def test_the_executor_answers_an_empty_request_rather_than_indexing_into_it() -> None:
    """Defense in depth for a programmatically built request."""
    with pytest.raises(ValidationError):
        QueryExecutionRequest(
            language="SQL", user="analyst", purpose="analysis", dataset_ids=[], query="select 1"
        )

    # Bypass validation the way a careless caller might, and confirm the executor
    # still answers instead of raising.
    request = QueryExecutionRequest.model_construct(
        language="SQL",
        user="analyst",
        purpose="analysis",
        dataset_ids=[],
        query="select 1",
        dry_run=False,
    )
    result = execute_query(request)
    assert result.status == "REJECTED"
    assert result.warnings == ["dataset_ids_required"]


def test_the_audit_ledger_labels_every_unmeasured_execution_figure() -> None:
    """An unlabelled estimate in the compliance ledger is a fabricated measurement.

    The HTTP response carried ``mock_execution_no_real_data`` while the audit row
    carried nothing, so the ledger recorded "2000 rows, 1024 bytes scanned" as
    though a query had run. ``row_count`` is the catalog's own profile estimate
    and ``bytesScanned``/``elapsedMs`` are fixed constants.
    """
    executed = client.post(
        "/browse/query",
        json={
            "user": "analyst",
            "dataset_ids": ["crm-customer-master"],
            "language": "SQL",
            "query": "select customer_id from customer",
            "purpose": "analysis",
        },
    )
    assert executed.status_code == 200, executed.text
    body = executed.json()
    assert "mock_execution_no_real_data" in body["warnings"]
    assert body["execution"]["measurement_status"] == "mock_execution_no_real_data"
    assert body["execution"]["bytes_scanned_source"] == "fixed_mock_constant"

    events = client.get("/audit/events", params={"user": "admin", "limit": 20}).json()
    rows = events if isinstance(events, list) else events.get("events", [])
    queries = [row for row in rows if row.get("action") == "browse.query"]
    assert queries, "the governed query must leave an audit row"
    details = queries[0]["details"]

    assert details["measurement_status"] == "mock_execution_no_real_data"
    # Not ``catalog_profile_estimate``: this dataset's profile says 1,200,000
    # rows and the mock reports 2,000, so the figure is the cap, not the
    # estimate whose provenance the old label claimed - off by a factor of 600.
    assert details["row_count_source"] == "mock_row_cap_below_catalog_profile_estimate"
    assert details["bytes_scanned_source"] == "fixed_mock_constant"
    # The response must carry the same provenance as the ledger. It named the
    # provenance of the two constants and said nothing about the row count,
    # which is the only figure a reader is likely to act on.
    assert body["execution"]["row_count_source"] == details["row_count_source"]
    # The figures are still recorded - labelled, not removed.
    assert details["row_count"] == body["row_count"]
    assert details["bytes_scanned"] == body["execution"]["bytesScanned"]


def test_each_mock_row_count_provenance_has_its_own_label() -> None:
    """Three provenances shared one label, so the ledger asserted the wrong one.

    Measured before the repair, with ``row_count_source`` reading
    ``catalog_profile_estimate`` in both cases::

        crm-customer-master  profile.row_count = 1200000  -> row_count 2000
        a dataset with profile = {}                       -> row_count 1000

    The first is the mock's cap; the second is a hardcoded literal with no
    estimate behind it at all.
    """
    base = catalog._DATA["crm-customer-master"]
    catalog._DATA["profile-free-ds"] = base.model_copy(
        update={"id": "profile-free-ds", "profile": {}}
    )
    catalog._DATA["small-profile-ds"] = base.model_copy(
        update={"id": "small-profile-ds", "profile": {"row_count": 7}}
    )

    def run(dataset_id: str, **extra):
        response = client.post(
            "/browse/query",
            json={
                "user": "analyst",
                "dataset_ids": [dataset_id],
                "language": "SQL",
                "query": "select customer_id from customer",
                "purpose": "analysis",
                **extra,
            },
        )
        assert response.status_code == 200, response.text
        return response.json()

    capped = run("crm-customer-master")
    assert capped["row_count"] == 2000
    assert capped["execution"]["row_count_source"] == (
        "mock_row_cap_below_catalog_profile_estimate"
    )

    unprofiled = run("profile-free-ds")
    assert unprofiled["row_count"] == 1000
    assert unprofiled["execution"]["row_count_source"] == "fixed_default_no_catalog_profile"

    # Only a figure that really is the catalog's own estimate may claim to be one.
    profiled = run("small-profile-ds")
    assert profiled["row_count"] == 7
    assert profiled["execution"]["row_count_source"] == "catalog_profile_estimate"

    dry = run("crm-customer-master", dry_run=True)
    assert dry["execution"]["row_count_source"] == "dry_run_zero"

    labels = {
        capped["execution"]["row_count_source"],
        unprofiled["execution"]["row_count_source"],
        profiled["execution"]["row_count_source"],
        dry["execution"]["row_count_source"],
    }
    assert len(labels) == 4, f"provenances must not share a label: {labels}"


def test_a_dry_run_labels_its_row_count_differently() -> None:
    """A dry run's zero is not a profile estimate, and says so."""
    executed = client.post(
        "/browse/query",
        json={
            "user": "analyst",
            "dataset_ids": ["crm-customer-master"],
            "language": "SQL",
            "query": "select customer_id from customer",
            "purpose": "analysis",
            "dry_run": True,
        },
    )
    assert executed.status_code == 200, executed.text
    events = client.get("/audit/events", params={"user": "admin", "limit": 20}).json()
    rows = events if isinstance(events, list) else events.get("events", [])
    dry = [row for row in rows if row.get("details", {}).get("dry_run") is True]
    assert dry, "the dry run must leave an audit row"
    assert dry[0]["details"]["row_count_source"] == "dry_run_zero"
