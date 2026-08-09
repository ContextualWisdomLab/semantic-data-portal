"""Production truthfulness contracts for governed query execution."""

from __future__ import annotations

from types import SimpleNamespace

from sdp.domain import QueryExecutionRequest
from sdp import orchestrator


def _allowed_decision() -> SimpleNamespace:
    """Return the minimum allow decision consumed by the query boundary."""
    return SimpleNamespace(
        effect="allow",
        decision_id="decision_one",
        reason="ok",
        obligations={},
    )


def _published_dataset() -> SimpleNamespace:
    """Return a persisted-looking dataset without granting an execution backend."""
    return SimpleNamespace(
        id="dataset_one",
        source_system="postgresql://warehouse/events",
        profile={"row_count": 42},
    )


def _request(*, dry_run: bool) -> QueryExecutionRequest:
    """Build one query that passes the existing syntax and policy guardrails."""
    return QueryExecutionRequest(
        language="SQL",
        user="analyst_one",
        purpose="analysis",
        dataset_ids=["dataset_one"],
        query="SELECT result FROM events",
        dry_run=dry_run,
    )


def test_dry_run_validates_without_inventing_rows(monkeypatch) -> None:
    """A dry run must never manufacture query results or provider telemetry."""
    monkeypatch.setattr(orchestrator, "get_dataset", lambda _dataset_id: _published_dataset())
    monkeypatch.setattr(orchestrator, "evaluate", lambda **_kwargs: _allowed_decision())
    monkeypatch.setattr(orchestrator, "ingest_event", lambda **_kwargs: None)

    response = orchestrator.execute_query(_request(dry_run=True))

    assert response.status == "VALIDATED"
    assert response.row_count == 0
    assert response.rows == []
    assert response.columns == []
    assert response.execution == {
        "elapsedMs": 0,
        "source": "validation",
        "bytesScanned": 0,
    }
    assert response.warnings == []


def test_live_query_fails_closed_without_a_real_execution_backend(monkeypatch) -> None:
    """Missing production execution must be unavailable, never synthetic success."""
    monkeypatch.setattr(orchestrator, "get_dataset", lambda _dataset_id: _published_dataset())
    monkeypatch.setattr(orchestrator, "evaluate", lambda **_kwargs: _allowed_decision())
    monkeypatch.setattr(orchestrator, "ingest_event", lambda **_kwargs: None)

    response = orchestrator.execute_query(_request(dry_run=False))

    assert response.status == "UNAVAILABLE"
    assert response.row_count == 0
    assert response.rows == []
    assert response.columns == []
    assert response.execution == {
        "elapsedMs": 0,
        "source": "unavailable",
        "bytesScanned": 0,
    }
    assert response.warnings == ["query_execution_backend_not_configured"]
    assert "mock" not in str(response.model_dump()).lower()
