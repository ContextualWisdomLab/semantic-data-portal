"""Shared pytest configuration for explicit demo-only identity behavior."""

from __future__ import annotations

import pytest

from sdp.config import override_app_config, reset_config_cache


@pytest.fixture(autouse=True)
def _allow_demo_subject_header(monkeypatch: pytest.MonkeyPatch) -> None:
    """Opt tests into the demo subject-header path unless a test removes it."""

    demo_configuration = override_app_config(allow_unverified_subject_header=True)
    monkeypatch.setattr("sdp.tenant_binding.get_app_config", lambda: demo_configuration)
    monkeypatch.setattr("sdp.authz.get_app_config", lambda: demo_configuration)
    reset_config_cache()
    yield
    reset_config_cache()
