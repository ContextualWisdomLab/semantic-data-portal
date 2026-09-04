"""Regression contract for the OpenMetadata HTTP application boundary."""

from __future__ import annotations

from fastapi.routing import APIRoute

from sdp import api as api_module


_OPENMETADATA_NORMALIZE_PATH = (
    "/integrations/openmetadata/v1/table-snapshots:normalize"
)


def test_openmetadata_route_is_defined_by_the_application_composition_root() -> None:
    """HTTP decorators and error conversion remain owned by ``sdp.api``."""

    route = next(
        candidate
        for candidate in api_module.app.routes
        if isinstance(candidate, APIRoute)
        and candidate.path == _OPENMETADATA_NORMALIZE_PATH
    )

    assert route.endpoint.__module__ == api_module.__name__
