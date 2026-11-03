"""The one row-level obligation this engine emits is never applied, and every
surface published it as though it were.

Measured at ``dba2403`` on ``crm-event`` (the only ``sensitivity: high`` dataset,
so the only one the obligation reaches)::

    published columns              ['event_id', 'customer_id', 'event_timestamp', 'device_id']
    'business_unit' among them     False
    purpose='analysis'   applied_row_filter=['business_unit = current_user_unit']  row_count=2
    purpose='marketing'  applied_row_filter=None                                   row_count=2
    rows byte-identical            True
    audit details                  {'row_filter': ['business_unit = current_user_unit'],
                                    'returned_rows': 2, ...}
    draft assumptions              ['행 레벨 필터 적용: business_unit = current_user_unit']
    drafted SQL                    SELECT count(*) ... WHERE event_timestamp >= current_date - 90 LIMIT 1000
    'business_unit' in that SQL    False

So the predicate names a column the dataset does not declare, the rows returned
"with the filter" are the same bytes as the rows returned without it, the SQL the
analyst is handed to run omits the predicate its own assumption list asserts, and
the compliance ledger stores the claim beside the row count. The product's PRD
puts row-level filtering in Phase 2 (``docs/prd-trd.md`` §6.2), so the absence of
enforcement is intended - what was not intended is a response field named
``applied_row_filter`` and a ledger row that together let an auditor conclude a
department-scoped read happened.

This file holds the repair as a property rather than as four examples: wherever
the declared predicate is published, its enforcement status is published with it.
That is what makes a fifth surface unable to echo the predicate bare.

The shape is this repository's existing one for a declared-but-inactive rule -
``tests/test_honest_metrics.py::test_each_published_alert_rule_says_whether_it_is_evaluated``
holds the alert rules to the same contract, and ``README.md`` publishes
``SDP_EVIDENCE_RETENTION_DAYS`` as ``unimplemented_environment`` rather than
quietly accepting it. A governance obligation is the surface where that mattered
most and was missing.
"""

from __future__ import annotations

import json
import re

from typing import Any, Iterator

import pytest

from fastapi.testclient import TestClient

from sdp import catalog, policy
from sdp.api import app
from sdp_core import QueryDraftRequest


client = TestClient(app)

# The only dataset the obligation can reach, and the purpose that emits it.
SENSITIVE_DATASET = "crm-event"
EMITTING_PURPOSE = "analysis"
DECLARED_PREDICATE = ["business_unit = current_user_unit"]

# A key whose *name* asserts the predicate governed the read. ``applied_...`` is
# the shape that shipped; the pattern is deliberately wider than that one name so
# a rename to ``row_filter_applied`` or ``enforced_row_filter`` is caught too.
CLAIMS_APPLICATION = re.compile(r"(applied|enforced|effective).*row.?filter|row.?filter.*(applied|enforced)", re.I)

# The marker the decision must carry beside the predicate.
ENFORCEMENT_STATUS = "declared_not_enforced"


def _walk(node: Any, path: str = "") -> Iterator[tuple[str, Any]]:
    """Yield ``(json path, value)`` for every node of a decoded JSON body."""
    yield path, node
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _walk(value, f"{path}.{key}" if path else key)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _walk(value, f"{path}[{index}]")


def _preview(purpose: str, *, user: str = "admin", limit: int = 100) -> dict[str, Any]:
    """Drive one governed preview of the sensitive dataset."""
    response = client.post(
        f"/browse/{SENSITIVE_DATASET}/preview",
        json={"user": user, "purpose": purpose, "limit": limit},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_the_predicate_names_a_column_this_dataset_does_not_have() -> None:
    """The premise, so a real implementation cannot leave this file asserting a
    stale one: if ``business_unit`` ever becomes a declared column, this fails
    and the enforcement claim must be revisited rather than silently inherited.
    """
    schema = client.get(f"/browse/{SENSITIVE_DATASET}/schema?user=analyst").json()
    columns = [column["name"] for column in schema["schema"]]
    assert "business_unit" not in columns, columns

    rows = _preview(EMITTING_PURPOSE)["rows"]
    assert rows, "the fixture must return rows for this to measure anything"
    for row in rows:
        assert "business_unit" not in row, row


def test_the_rows_are_the_same_bytes_with_and_without_the_obligation() -> None:
    """The behavioural measurement the published claim has to match."""
    with_filter = _preview(EMITTING_PURPOSE)
    without_filter = _preview("marketing")

    assert with_filter["row_count"] == without_filter["row_count"]
    assert json.dumps(with_filter["rows"], sort_keys=True, ensure_ascii=False) == json.dumps(
        without_filter["rows"], sort_keys=True, ensure_ascii=False
    ), "the declared filter selected a different set of rows - revisit the claim"


def test_no_published_field_name_claims_the_filter_governed_the_read() -> None:
    """Structural, over the whole response body rather than one known key."""
    body = _preview(EMITTING_PURPOSE)
    offenders = [path for path, _ in _walk(body) if CLAIMS_APPLICATION.search(path.split(".")[-1])]
    assert not offenders, (
        f"these published fields assert the row filter was applied, and nothing applies it: {offenders}"
    )


def test_wherever_the_predicate_is_published_its_enforcement_status_is_too() -> None:
    """The repair as a property.

    Any object in the response that carries the declared predicate must also
    carry a falsy enforcement flag, so a consumer cannot read the predicate
    without reading that it was not enforced.
    """
    body = _preview(EMITTING_PURPOSE)
    carriers = [
        (path, node)
        for path, node in _walk(body)
        if isinstance(node, dict)
        and any(value == DECLARED_PREDICATE for value in node.values())
    ]
    assert carriers, (
        "the declared predicate is published nowhere in the preview response; the analyst who "
        "meets a governed read can no longer see which obligation the policy declared"
    )
    noted = 0
    for path, node in carriers:
        # The prose note also carries "enforc" in its name, and it is a Korean
        # sentence rather than a status - the first version of this guard demanded
        # the machine token inside it and failed on the honest implementation.
        # Statuses are checked for their value; the note for its presence.
        markers = {
            key: value
            for key, value in node.items()
            if "enforc" in key.lower() and "note" not in key.lower()
        }
        assert markers, (
            f"{path or '<root>'} publishes the predicate with no enforcement marker: {sorted(node)}"
        )
        # A marker may be the machine status the decision carries or the boolean
        # the response carries; either way it must deny enforcement. Anything else
        # under an ``enforc`` name - ``True``, or a status that does not say "not
        # enforced" - is the claim this file exists to refuse.
        for key, value in markers.items():
            if isinstance(value, bool):
                assert value is False, f"{path or '<root>'}.{key} claims enforcement"
            else:
                assert isinstance(value, str) and "not_enforced" in value, (
                    f"{path or '<root>'}.{key} does not deny enforcement: {value!r}"
                )
        noted += any(
            isinstance(value, str) and "note" in key.lower() and value.strip()
            for key, value in node.items()
        )
    assert noted, (
        "no object publishing the predicate tells the caller what to do about it; the "
        "analyst reading a governed read sees a predicate and no instruction"
    )


def test_the_audit_row_does_not_read_as_an_enforced_read() -> None:
    """The ledger an auditor joins to ``decision_id``."""
    before = len(catalog._AUDIT_LOG)
    _preview(EMITTING_PURPOSE)
    # ``ingest_event(event_type=...)`` is recorded under ``action``; reading the
    # keyword name here is how the first version of this guard measured nothing
    # and reported it as a missing audit row.
    new = [
        event
        for event in catalog._AUDIT_LOG[before:]
        if (event if isinstance(event, dict) else event.model_dump()).get("action")
        == "browse.preview"
    ]
    assert new, "the preview must still be audited"
    for event in new:
        record = event if isinstance(event, dict) else event.model_dump()
        details = record.get("details") or {}
        assert "row_filter" not in details, (
            "a bare `row_filter` beside `returned_rows` is the claim an auditor reads as "
            f"a department-scoped read: {details}"
        )
        carriers = [key for key, value in details.items() if value == DECLARED_PREDICATE]
        assert carriers, f"the declared obligation is no longer recorded at all: {details}"
        for key in carriers:
            assert "declared" in key, f"{key!r} names the predicate without saying it is only declared"
        flags = {
            key: value
            for key, value in details.items()
            if isinstance(value, bool) and "enforc" in key.lower()
        }
        assert flags and not any(flags.values()), (
            f"the ledger row does not record that nothing enforced the predicate: {details}"
        )


def test_every_decision_carrying_the_predicate_carries_its_status() -> None:
    """Driven over the catalog rather than the one known case, so a second
    emission site - another action, another sensitivity - cannot skip the marker.
    """
    datasets = [dataset.id for dataset in catalog._DATA.values()]
    assert datasets, "the seeded catalog is empty"
    seen_predicate = False
    for dataset_id in datasets:
        for action in ("preview", "query", "schema", "search"):
            for purpose in (EMITTING_PURPOSE, "Analysis", " analysis\t", "marketing", ""):
                decision = policy.evaluate("admin", dataset_id, action, purpose)
                obligations = decision.obligations or {}
                if "row_filter" not in obligations:
                    continue
                seen_predicate = True
                assert obligations.get("row_filter_enforcement") == ENFORCEMENT_STATUS, (
                    f"{dataset_id}/{action}/{purpose!r} declares a row filter with no "
                    f"enforcement status: {obligations}"
                )
    assert seen_predicate, "no decision emitted a row filter - this guard measured nothing"


@pytest.mark.parametrize("purpose", (EMITTING_PURPOSE, "Analysis", " analysis\t"))
def test_the_draft_assumption_agrees_with_the_sql_it_describes(purpose: str) -> None:
    """The drafter hands the analyst SQL to run, with an assumption list beside it.

    The requirement is derived from the SQL that was actually emitted rather than
    from a fixed string: an assumption may claim the predicate is in the statement
    only if it is.
    """
    from sdp import orchestrator

    draft = orchestrator.draft_sql(
        QueryDraftRequest(
            question="최근 이벤트 건수",
            user="analyst",
            purpose=purpose,
            dataset_id=SENSITIVE_DATASET,
        )
    )
    assert "error" not in draft, draft
    sql = draft["query"]
    predicate_column = "business_unit"
    naming = [line for line in draft["assumptions"] if predicate_column in line]
    assert naming, f"the declared obligation vanished from the draft: {draft['assumptions']}"
    if predicate_column in sql:
        return  # a real implementation: the claim and the statement agree
    for line in naming:
        assert "적용" not in line or "않" in line, (
            f"the assumption says the filter is applied while the SQL omits it: {line!r} / {sql!r}"
        )
        assert "않" in line, (
            f"the assumption must say the predicate is not in this statement: {line!r}"
        )
