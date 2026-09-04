"""Validation for external OpenMetadata installation identifiers."""

from __future__ import annotations

import re

from .errors import OpenMetadataContractError

_SOURCE_INSTANCE_ID_PATTERN = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$"
)


def validate_source_instance_id(source_instance_id: object) -> str:
    """Return a bounded identifier safe for canonical CWL projection URNs."""

    if not isinstance(source_instance_id, str):
        raise OpenMetadataContractError(
            "source_instance_id must be a string"
        )
    if not source_instance_id:
        raise OpenMetadataContractError(
            "source_instance_id is required"
        )
    if not _SOURCE_INSTANCE_ID_PATTERN.fullmatch(source_instance_id):
        raise OpenMetadataContractError(
            "source_instance_id contains unsupported characters"
        )
    return source_instance_id
