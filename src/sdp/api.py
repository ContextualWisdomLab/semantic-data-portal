"""ASGI composition root for Semantic Data Portal routes."""

from __future__ import annotations

from . import core_api as _core_api
from .graph_store import get_store
from .openmetadata_routes import router as openmetadata_router


app = _core_api.app


def _forward_get_store():
    """Preserve tests and embedders that replace ``sdp.api.get_store``."""

    return get_store()


# Existing readiness tests patch the public composition root. Keep that seam
# while the original route collection is separated from new integration routers.
_core_api.get_store = _forward_get_store
app.include_router(openmetadata_router)

__all__ = ["app", "get_store"]
