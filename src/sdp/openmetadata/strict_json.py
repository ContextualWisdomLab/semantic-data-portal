"""Strict UTF-8 JSON admission for OpenMetadata HTTP requests."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from .errors import OpenMetadataContractError


class _DuplicateJsonKey(ValueError):
    """Signal that one JSON object repeated a member name."""


class _NonStandardJsonNumber(ValueError):
    """Signal a NaN or infinity token forbidden by standard JSON."""


def _unique_object_pairs(
    pairs: Sequence[tuple[str, Any]],
) -> dict[str, Any]:
    """Build a JSON object while rejecting last-key-wins ambiguity."""

    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonKey(key)
        result[key] = value
    return result


def _reject_non_standard_number(value: str) -> None:
    """Reject constants accepted by Python but forbidden by standard JSON."""

    raise _NonStandardJsonNumber(value)


def validate_strict_json_bytes(payload: bytes) -> object:
    """Parse strict UTF-8 JSON and reject duplicate object members.

    The returned value is used only to prove that the transport body has one
    unambiguous standard-JSON interpretation. FastAPI performs the typed request
    validation from the same cached body afterward.
    """

    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise OpenMetadataContractError(
            "request body must be UTF-8 JSON"
        ) from exc

    try:
        return json.loads(
            text,
            object_pairs_hook=_unique_object_pairs,
            parse_constant=_reject_non_standard_number,
        )
    except _DuplicateJsonKey as exc:
        raise OpenMetadataContractError(
            "request body contains duplicate JSON object key"
        ) from exc
    except _NonStandardJsonNumber as exc:
        raise OpenMetadataContractError(
            "request body contains non-standard JSON number"
        ) from exc
    except json.JSONDecodeError as exc:
        raise OpenMetadataContractError(
            "request body must be strict JSON"
        ) from exc
