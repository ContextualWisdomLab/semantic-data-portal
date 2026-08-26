"""Shared pytest configuration for explicit demo-only identity behavior."""

from __future__ import annotations

import pytest

from sdp.config import reset_config_cache


@pytest.fixture(autouse=True)
def _allow_demo_subject_header(monkeypatch: pytest.MonkeyPatch) -> None:
    """Opt tests into the demo subject-header path unless a test removes it."""

    monkeypatch.setenv("SDP_ALLOW_UNVERIFIED_SUBJECT_HEADER", "true")
    reset_config_cache()
    yield
    reset_config_cache()
