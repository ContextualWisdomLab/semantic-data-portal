"""Shared pytest configuration for identity and evidence-store isolation."""

from __future__ import annotations

import pytest

from sdp.data_management_store import (
    restore_memory_data_management,
    snapshot_memory_data_management,
)


@pytest.fixture(autouse=True)
def _allow_demo_subject_header(monkeypatch: pytest.MonkeyPatch) -> None:
    """Opt tests into the demo subject-header path unless a test removes it."""

    monkeypatch.setenv("SDP_ALLOW_UNVERIFIED_SUBJECT_HEADER", "true")


@pytest.fixture(autouse=True)
def _isolate_data_management_evidence() -> None:
    """Restore process-local evidence rows after every test."""

    snapshot = snapshot_memory_data_management()
    try:
        yield
    finally:
        restore_memory_data_management(snapshot)
