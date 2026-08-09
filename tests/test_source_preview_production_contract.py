"""Production truthfulness contracts for source preview adapters."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from sdp import browse, connectors


def _dataset(source_system: str) -> SimpleNamespace:
    """Return a minimal persisted-looking dataset bound to one source URI."""
    return SimpleNamespace(
        id="dataset_one",
        source_system=source_system,
        schema=[],
        sensitivity="internal",
        quality_score=1.0,
        freshness_score=1.0,
    )


def _allow() -> SimpleNamespace:
    """Return the minimum allow decision consumed by preview policy checks."""
    return SimpleNamespace(
        effect="allow",
        decision_id="decision_one",
        reason="ok",
        obligations={"masking": [], "row_filter": []},
        model_dump=lambda: {
            "effect": "allow",
            "decision_id": "decision_one",
            "reason": "ok",
            "obligations": {"masking": [], "row_filter": []},
        },
    )


def test_generic_browse_preview_fails_closed_without_source_execution(monkeypatch) -> None:
    """Catalog metadata must never be converted into fabricated customer rows."""
    monkeypatch.setattr(browse, "get_dataset", lambda _dataset_id: _dataset("postgresql://warehouse/events"))
    monkeypatch.setattr(browse, "evaluate", lambda **_kwargs: _allow())
    monkeypatch.setattr(browse, "ingest_event", lambda **_kwargs: None)

    with pytest.raises(RuntimeError, match="source_preview_backend_not_configured"):
        browse.preview("dataset_one", user="analyst_one", purpose="analysis", limit=10)


@pytest.mark.parametrize(
    ("connector_type", "source_system"),
    [
        (connectors.DemoRDFConnector, "sparql://knowledge"),
        (connectors.DemoFileLakeConnector, "s3://bucket/events"),
        (connectors.DemoRESTConnector, "https://api.example.test/events"),
    ],
)
def test_demo_connectors_do_not_return_hard_coded_rows(monkeypatch, connector_type, source_system) -> None:
    """Source adapters without provider clients must refuse preview instead of faking data."""
    monkeypatch.setattr(connectors, "get_dataset", lambda _dataset_id: _dataset(source_system))

    connector = connector_type()
    with pytest.raises(RuntimeError, match="source_preview_backend_not_configured"):
        connector.preview("dataset_one", limit=10, offset=0)
