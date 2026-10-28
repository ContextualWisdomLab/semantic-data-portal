"""A refused SQL draft recorded its policy decision and no audit event.

``_audit_draft``'s docstring says it exists to close exactly this shape, and
``docs/requirements-coverage.md`` publishes NFR-SEC-005 - "preview/query/policy/
catalog change 100% 기록" - as ``implemented``, noting that two earlier holes
"were found and closed rather than assumed absent". Four more were open on one
route. Measured per call as deltas on ``/policy/decisions`` and ``/audit/events``,
against a published probe dataset::

    success                      decisions +1  audits +1
    policy_denied (purpose)      decisions +1  audits +1
    policy_denied (keyword)      decisions +1  audits +0   <-- hole
    invalid_columns              decisions +1  audits +0   <-- hole
    invalid_group_by             decisions +1  audits +0   <-- hole
    draft_rejected_by_validator  decisions +1  audits +0   <-- hole
    unquotable_source_table      decisions +1  audits +0   <-- hole
    dataset_not_found            decisions +0  audits +0
    invalid_date_window          decisions +0  audits +0

The last two are refused before a decision exists, so they are symmetric and not
holes - which is the distinction a guard on this route has to keep, or it fails
the paths that are correct.

Three further refusals (``ambiguous_identifier``, ``unquotable_source_table``,
``invalid_row_limit``/``invalid_timeout``) sit on the same side of the decision
and are unreachable through HTTP, because the request contract rejects their
inputs first. They are covered structurally rather than by example: the AST guard
holds *every* post-decision exit to the auditing helper, which is why closing the
four reachable ones by hand would have been the weaker repair.
"""

from __future__ import annotations

import ast
import inspect
import pathlib

from typing import Any

import pytest

from fastapi.testclient import TestClient

from sdp import catalog, evidence, orchestrator
from sdp.api import app


client = TestClient(app)

CLEAN_DATASET = "audit-probe-clean"
# Its ``source_system``'s last path segment starts with a digit, which is not a
# SQL identifier, so the derived table name cannot be emitted.
DIGIT_TAIL_DATASET = "audit-probe-digit"
# A declared column named after a forbidden keyword: the statement the drafter
# builds then contains the keyword and its own self-check refuses it. This is the
# route to ``draft_rejected_by_validator`` - the digit-tail dataset used to reach
# it and now refuses earlier, with the true cause, so both codes are covered.
KEYWORD_COLUMN_DATASET = "audit-probe-keyword"


def _onboard(dataset_id: str, source_system: str, *, first_column: str = "customer_id") -> None:
    """Register and publish one probe dataset, or leave an existing one alone."""
    if client.get(f"/catalog/datasets/{dataset_id}?user=data-admin").status_code == 200:
        return
    body: dict[str, Any] = {
        "id": dataset_id,
        "tenant_id": "demo",
        "title": f"감사 프로브 {dataset_id}",
        "description": "증빙 페어링 측정을 위한 프로브 데이터셋",
        "owner": "data-admin",
        "steward": "data-admin",
        "domain": "고객",
        "source_system": source_system,
        "sensitivity": "low",
        "update_frequency": "daily",
        "quality_score": 0.9,
        "freshness_score": 0.9,
        "schema": [
            {"name": first_column, "datatype": "string", "nullable_ratio": 0.0, "distinct_ratio": 1.0},
            {"name": "event_timestamp", "datatype": "timestamp", "nullable_ratio": 0.0, "distinct_ratio": 0.9},
        ],
        "distributions": [
            {
                "id": f"{dataset_id}-csv",
                "format": "csv",
                "endpoint": "https://files.example.internal/probe.csv",
            }
        ],
        "actor": "data-admin",
        "reason": "probe",
    }
    created = client.post("/catalog/datasets", json=body)
    assert created.status_code == 200, created.text
    published = client.post(
        f"/catalog/datasets/{dataset_id}/publish", json={"actor": "data-admin", "reason": "probe"}
    )
    assert published.status_code == 200, published.text


@pytest.fixture(autouse=True)
def _probe_datasets() -> None:
    """Both probe datasets, registered fresh for each test."""
    _onboard(CLEAN_DATASET, "s3://analytics/events/orders")
    _onboard(DIGIT_TAIL_DATASET, "s3://analytics/events/2024")
    _onboard(KEYWORD_COLUMN_DATASET, "s3://analytics/events/touches", first_column="union")


def _draft(**overrides: Any) -> tuple[int, str, int, int]:
    """Drive one draft and return ``(status, error, decision delta, audit delta)``."""
    body: dict[str, Any] = {
        "user": "analyst",
        "dataset_id": CLEAN_DATASET,
        "question": "최근 고객 수",
        "purpose": "analysis",
    }
    body.update(overrides)
    before = (len(evidence._POLICY_DECISION_LOG), len(catalog._AUDIT_LOG))
    response = client.post("/llm/draft-query", json=body)
    after = (len(evidence._POLICY_DECISION_LOG), len(catalog._AUDIT_LOG))
    payload = response.json()
    body_or_detail = payload.get("detail", payload) if isinstance(payload, dict) else {}
    error = body_or_detail.get("error", "") if isinstance(body_or_detail, dict) else ""
    return response.status_code, error, after[0] - before[0], after[1] - before[1]


POST_DECISION_REFUSALS = (
    ("policy_denied", {"purpose": "external-export"}),
    ("policy_denied", {"question": "고객 테이블을 drop 해줘"}),
    ("invalid_columns", {"columns": ["no_such_column"]}),
    ("invalid_group_by", {"group_by": "no_such_column"}),
    ("unquotable_source_table", {"dataset_id": DIGIT_TAIL_DATASET}),
    (
        "draft_rejected_by_validator",
        {"dataset_id": KEYWORD_COLUMN_DATASET, "group_by": "union"},
    ),
)


@pytest.mark.parametrize("expected_error,overrides", POST_DECISION_REFUSALS)
def test_a_refused_draft_records_both_halves(expected_error: str, overrides: dict[str, Any]) -> None:
    """One decision, one audit event - on refusal as on success."""
    status, error, decisions, audits = _draft(**overrides)
    assert status != 200, (expected_error, status)
    assert error == expected_error, (expected_error, error)
    assert decisions == 1, (expected_error, decisions)
    assert audits == decisions, (
        f"{expected_error} recorded {decisions} decision(s) and {audits} audit event(s); "
        "the compliance ledger shows a governed request with no trace in the audit feed"
    )


def test_a_successful_draft_still_records_both_halves() -> None:
    """The control: the pairing is not satisfied by auditing nothing anywhere."""
    status, _error, decisions, audits = _draft()
    assert status == 200
    assert (decisions, audits) == (1, 1)


@pytest.mark.parametrize(
    "expected_error,overrides",
    (
        ("dataset_not_found", {"dataset_id": "no-such-dataset-at-all"}),
        ("invalid_date_window", {"date_window_days": 0}),
    ),
)
def test_a_refusal_before_the_decision_records_neither_half(
    expected_error: str, overrides: dict[str, Any]
) -> None:
    """Symmetry, not volume.

    These refuse before a decision exists, so an audit event here would be a
    record of an evaluation that never happened. A guard that only demanded "more
    auditing" would pass a fix that logged these too.
    """
    _status, error, decisions, audits = _draft(**overrides)
    assert error == expected_error, (expected_error, error)
    assert (decisions, audits) == (0, 0), (expected_error, decisions, audits)


def test_every_post_decision_exit_goes_through_the_auditing_helper() -> None:
    """Structural, so the paths HTTP cannot reach are covered too.

    Found by walking ``draft_sql``'s AST rather than by listing the error codes:
    the four reachable holes were four of eight post-decision exits, and a list
    of known codes is how the other four would have been missed.
    """
    source = inspect.getsource(orchestrator.draft_sql)
    tree = ast.parse(pathlib.Path(orchestrator.__file__).read_text(encoding="utf-8"))
    function = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "draft_sql"
    )
    decided_at = [
        node.lineno
        for node in ast.walk(function)
        if isinstance(node, ast.Assign)
        and any(getattr(target, "id", "") == "decision" for target in node.targets)
    ]
    assert decided_at, "draft_sql no longer assigns `decision`; re-anchor this guard"
    decision_line = max(decided_at)

    offenders: list[tuple[int, str]] = []

    def audits_in(block: list[ast.stmt]) -> bool:
        """Whether this statement list records the audit half itself."""
        return any(
            isinstance(statement, ast.Expr)
            and isinstance(statement.value, ast.Call)
            and getattr(statement.value.func, "id", "") == "_audit_draft"
            for statement in block
        )

    def inspect_block(block: list[ast.stmt]) -> None:
        """Check one statement list, then recurse into its nested blocks.

        Two exemptions, both measured rather than assumed. A ``return`` whose own
        block already calls ``_audit_draft`` is paired - that is how the
        ``policy_denied`` branch does it, and the first version of this guard
        reported it as an offender. And ``refuse``'s own ``return`` is the helper,
        not a caller of it; walking the whole function flagged that too.
        """
        paired = audits_in(block)
        for statement in block:
            if isinstance(statement, ast.FunctionDef) and statement.name == "refuse":
                continue
            if isinstance(statement, ast.Return) and statement.lineno > decision_line:
                value = statement.value
                is_refusal_call = (
                    isinstance(value, ast.Call) and getattr(value.func, "id", "") == "refuse"
                )
                if not (is_refusal_call or paired):
                    if isinstance(value, ast.Dict):
                        keys = [key.value for key in value.keys if isinstance(key, ast.Constant)]
                        if "error" in keys:
                            offenders.append((statement.lineno, "returns an error dict directly"))
                    elif value is not None:
                        offenders.append((statement.lineno, f"returns {type(value).__name__}"))
            for field, child in ast.iter_fields(statement):
                if isinstance(child, list) and child and isinstance(child[0], ast.stmt):
                    inspect_block(child)

    inspect_block(function.body)
    assert not offenders, (
        "these exits follow the recorded policy decision and do not route through "
        f"`refuse`, so each answers with a decision and no audit event: {offenders}"
    )
    # And the helper is the thing that audits, not a renamed passthrough.
    assert "_audit_draft(" in source.split("def refuse(")[1].split("return {")[0]


def test_the_sibling_execution_route_keeps_the_same_pairing() -> None:
    """``/browse/query`` refuses through one local helper that always audits.

    Held here because the two routes are the product's governed-read pair and the
    draft route is the one that drifted; if the sibling ever drifts the same way,
    this fails next to the guard that describes the shape.
    """
    before = (len(evidence._POLICY_DECISION_LOG), len(catalog._AUDIT_LOG))
    refused = client.post(
        "/browse/query",
        json={
            "user": "analyst",
            "dataset_ids": ["crm-customer-master"],
            "language": "SQL",
            # A post-decision refusal, deliberately. A forbidden keyword is
            # refused *before* the evaluation there and records audits +1 with
            # decisions +0 - the mirror shape, and correct: its audit row carries
            # ``policy_stage: pre_policy_validation``, saying policy was never
            # reached. Measuring that case here would have asserted the pairing
            # on a call that has no decision to pair with.
            "query": "select customer_id from some_other_table",
            "purpose": "analysis",
        },
    )
    after = (len(evidence._POLICY_DECISION_LOG), len(catalog._AUDIT_LOG))
    assert refused.status_code == 400, refused.text
    assert after[0] - before[0] == 1, (before, after)
    assert after[1] - before[1] == after[0] - before[0], (before, after)
