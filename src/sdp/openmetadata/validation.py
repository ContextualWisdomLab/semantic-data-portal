"""Bounded validators for untrusted OpenMetadata payloads."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any, cast
from urllib.parse import urlparse
from uuid import UUID

from .errors import OpenMetadataContractError

_MAX_PAYLOAD_CONTAINERS = 100_000
_MAX_PAYLOAD_TEXT_BYTES = 8 * 1024 * 1024
_MAX_TEXT_LENGTH = 16_384
_TENANT_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
_RELEASE_PATTERN = re.compile(r"^2\.(?:0|[1-9]\d*)(?:\.(?:0|[1-9]\d*))?(?:-release)?$")


def _require_mapping(value: object, field_name: str) -> Mapping[str, Any]:
    """Return a mapping or raise a stable contract error."""

    if not isinstance(value, Mapping):
        raise OpenMetadataContractError(f"{field_name} must be an object")
    return value


def _optional_mapping(value: object, field_name: str) -> Mapping[str, Any] | None:
    """Return an optional mapping while rejecting wrong container types."""

    if value is None:
        return None
    return _require_mapping(value, field_name)


def _require_list(value: object, field_name: str, *, maximum: int) -> list[Any]:
    """Return a JSON-array-like list with a deterministic size bound."""

    if not isinstance(value, list):
        raise OpenMetadataContractError(f"{field_name} must be an array")
    if len(value) > maximum:
        raise OpenMetadataContractError(f"{field_name} exceeds {maximum} items")
    return value


def _optional_list(value: object, field_name: str, *, maximum: int) -> list[Any]:
    """Return an optional list, treating a missing value as an empty array."""

    if value is None:
        return []
    return _require_list(value, field_name, maximum=maximum)


def _text(
    value: object,
    field_name: str,
    *,
    required: bool = False,
    maximum: int = _MAX_TEXT_LENGTH,
) -> str | None:
    """Validate bounded text without coercing foreign scalar values."""

    if value is None:
        if required:
            raise OpenMetadataContractError(f"{field_name} is required")
        return None
    if not isinstance(value, str):
        raise OpenMetadataContractError(f"{field_name} must be a string")
    if required and not value:
        raise OpenMetadataContractError(f"{field_name} is required")
    if len(value) > maximum:
        raise OpenMetadataContractError(f"{field_name} exceeds {maximum} characters")
    if any(ord(character) < 32 and character not in "\t\n\r" for character in value):
        raise OpenMetadataContractError(f"{field_name} contains control characters")
    return value


def _required_text(value: object, field_name: str, *, maximum: int) -> str:
    """Return required bounded text without relying on runtime assertions."""

    return cast(str, _text(value, field_name, required=True, maximum=maximum))


def _uuid_text(value: object, field_name: str) -> str:
    """Validate an external UUID while preserving its canonical string form."""

    text = _required_text(value, field_name, maximum=64)
    try:
        return str(UUID(text))
    except (ValueError, AttributeError) as exc:
        raise OpenMetadataContractError(f"{field_name} must be a UUID") from exc


def _safe_url(value: object, field_name: str) -> str | None:
    """Allow only bounded HTTP(S) references in the general projection."""

    text = _text(value, field_name, maximum=2_048)
    if text is None:
        return None
    try:
        parsed = urlparse(text)
        username = parsed.username
        password = parsed.password
    except ValueError as exc:
        raise OpenMetadataContractError(f"{field_name} must be an HTTP(S) URL") from exc
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise OpenMetadataContractError(f"{field_name} must be an HTTP(S) URL")
    if username is not None or password is not None:
        raise OpenMetadataContractError(f"{field_name} must not contain credentials")
    return text


def _optional_non_negative_int(value: object, field_name: str) -> int | None:
    """Validate optional non-negative integer aggregates without bool coercion."""

    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise OpenMetadataContractError(f"{field_name} must be a non-negative integer")
    return value


def _epoch_milliseconds(value: object, field_name: str) -> datetime | None:
    """Convert an optional Unix epoch-millisecond timestamp to UTC."""

    milliseconds = _optional_non_negative_int(value, field_name)
    if milliseconds is None:
        return None
    try:
        return datetime.fromtimestamp(milliseconds / 1_000, tz=timezone.utc)
    except (OverflowError, OSError, ValueError) as exc:
        raise OpenMetadataContractError(
            f"{field_name} is outside the supported timestamp range"
        ) from exc


def _validate_source_release(source_release: object) -> str:
    """Limit the first adapter contract to explicitly declared 2.x releases."""

    release = _required_text(source_release, "source_release", maximum=64)
    if not _RELEASE_PATTERN.fullmatch(release):
        raise OpenMetadataContractError(
            "source_release must identify an OpenMetadata 2.x release"
        )
    return release


def _validate_tenant_id(tenant_id: object) -> str:
    """Validate the tenant token embedded in canonical CWL identifiers."""

    value = _required_text(tenant_id, "tenant_id", maximum=128)
    if not _TENANT_ID_PATTERN.fullmatch(value):
        raise OpenMetadataContractError("tenant_id contains unsupported characters")
    return value


def _validate_payload_budget(*payloads: object) -> None:
    """Bound direct-call payload complexity before extracting any metadata."""

    stack: list[tuple[object, int]] = [
        (payload, 1) for payload in payloads if payload is not None
    ]
    seen_containers: set[int] = set()
    container_count = 0
    text_bytes = 0
    while stack:
        value, depth = stack.pop()
        if depth > 64:
            raise OpenMetadataContractError("payload nesting exceeds 64")
        if isinstance(value, str):
            text_bytes += len(value.encode("utf-8"))
            if text_bytes > _MAX_PAYLOAD_TEXT_BYTES:
                raise OpenMetadataContractError(
                    f"payload text exceeds {_MAX_PAYLOAD_TEXT_BYTES} bytes"
                )
            continue
        if isinstance(value, Mapping):
            identity = id(value)
            if identity in seen_containers:
                raise OpenMetadataContractError("payload contains a cyclic container")
            seen_containers.add(identity)
            container_count += 1
            if container_count > _MAX_PAYLOAD_CONTAINERS:
                raise OpenMetadataContractError(
                    f"payload exceeds {_MAX_PAYLOAD_CONTAINERS} containers"
                )
            stack.extend(
                (item, depth + 1) for pair in value.items() for item in pair
            )
            continue
        if isinstance(value, list):
            identity = id(value)
            if identity in seen_containers:
                raise OpenMetadataContractError("payload contains a cyclic container")
            seen_containers.add(identity)
            container_count += 1
            if container_count > _MAX_PAYLOAD_CONTAINERS:
                raise OpenMetadataContractError(
                    f"payload exceeds {_MAX_PAYLOAD_CONTAINERS} containers"
                )
            stack.extend((item, depth + 1) for item in value)


def _stable_unique(values: Sequence[str]) -> list[str]:
    """Deduplicate strings without changing source order."""

    return list(dict.fromkeys(values))
