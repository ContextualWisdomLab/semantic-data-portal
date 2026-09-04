"""Strict UTF-8 JSON admission for OpenMetadata HTTP requests."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from .errors import OpenMetadataContractError

REQUEST_BODY_MAX_BYTES = 8 * 1024 * 1024


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


def _validate_unicode_scalars(value: object) -> None:
    """Reject lone UTF-16 surrogate code points anywhere in parsed JSON."""

    pending = [value]
    while pending:
        current = pending.pop()
        if isinstance(current, str):
            if any(
                0xD800 <= ord(character) <= 0xDFFF
                for character in current
            ):
                raise OpenMetadataContractError(
                    "request body strings must contain valid Unicode scalar values"
                )
        elif isinstance(current, list):
            pending.extend(current)
        elif isinstance(current, dict):
            pending.extend(current.keys())
            pending.extend(current.values())


def validate_strict_json_bytes(payload: bytes) -> object:
    """Parse bounded strict UTF-8 JSON with unique object member names."""

    if len(payload) > REQUEST_BODY_MAX_BYTES:
        raise OpenMetadataContractError(
            f"request body exceeds {REQUEST_BODY_MAX_BYTES} bytes"
        )
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise OpenMetadataContractError(
            "request body must be UTF-8 JSON"
        ) from exc
    try:
        parsed = json.loads(
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
    except (json.JSONDecodeError, RecursionError) as exc:
        raise OpenMetadataContractError(
            "request body must be strict JSON"
        ) from exc
    _validate_unicode_scalars(parsed)
    return parsed
