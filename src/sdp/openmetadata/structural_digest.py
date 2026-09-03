"""Cross-language structural digest profile for admitted JSON values."""

from __future__ import annotations

import math
import struct
from hashlib import sha256

from .errors import OpenMetadataContractError

DIGEST_PROFILE_ID = "cwl-json-structural-sha256-v1"

_MAXIMUM_DEPTH = 64
_MINIMUM_INTEGER = -(2**63)
_MAXIMUM_INTEGER = (2**63) - 1


def _utf8_bytes(value: str, field_name: str) -> bytes:
    """Encode one JSON string as strict UTF-8 or fail with a stable error."""

    try:
        return value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise OpenMetadataContractError(
            f"{field_name} is not deterministic JSON data"
        ) from exc


def _encode_value(
    value: object,
    field_name: str,
    *,
    depth: int,
    active_containers: set[int],
) -> bytes:
    """Encode one supported value using the immutable v1 structural grammar."""

    if depth > _MAXIMUM_DEPTH:
        raise OpenMetadataContractError(
            f"{field_name} nesting exceeds {_MAXIMUM_DEPTH}"
        )
    if value is None:
        return b"n"
    if isinstance(value, bool):
        return b"b1" if value else b"b0"
    if isinstance(value, int):
        if value < _MINIMUM_INTEGER or value > _MAXIMUM_INTEGER:
            raise OpenMetadataContractError(
                f"{field_name} integer exceeds signed 64-bit range"
            )
        return f"i{value};".encode("ascii")
    if isinstance(value, float):
        if not math.isfinite(value):
            raise OpenMetadataContractError(
                f"{field_name} is not deterministic JSON data"
            )
        bits = struct.pack(">d", value).hex()
        return f"f{bits};".encode("ascii")
    if isinstance(value, str):
        encoded = _utf8_bytes(value, field_name)
        prefix = f"s{len(encoded)}:".encode("ascii")
        return prefix + encoded

    if type(value) is list:
        identity = id(value)
        if identity in active_containers:
            raise OpenMetadataContractError(
                f"{field_name} contains a cyclic container"
            )
        active_containers.add(identity)
        try:
            encoded_items = b"".join(
                _encode_value(
                    item,
                    field_name,
                    depth=depth + 1,
                    active_containers=active_containers,
                )
                for item in value
            )
        finally:
            active_containers.remove(identity)
        return (
            f"a{len(value)}[".encode("ascii")
            + encoded_items
            + b"]"
        )

    if type(value) is dict:
        identity = id(value)
        if identity in active_containers:
            raise OpenMetadataContractError(
                f"{field_name} contains a cyclic container"
            )
        if any(not isinstance(key, str) for key in value):
            raise OpenMetadataContractError(
                f"{field_name} JSON object keys must be strings"
            )
        active_containers.add(identity)
        try:
            ordered_keys = sorted(
                value,
                key=lambda key: _utf8_bytes(key, field_name),
            )
            encoded_members = b"".join(
                _encode_value(
                    key,
                    field_name,
                    depth=depth + 1,
                    active_containers=active_containers,
                )
                + _encode_value(
                    value[key],
                    field_name,
                    depth=depth + 1,
                    active_containers=active_containers,
                )
                for key in ordered_keys
            )
        finally:
            active_containers.remove(identity)
        return (
            f"o{len(value)}{{".encode("ascii")
            + encoded_members
            + b"}"
        )

    raise OpenMetadataContractError(
        f"{field_name} is not deterministic JSON data"
    )


def encode_structural_json(value: object, field_name: str) -> bytes:
    """Encode JSON data with the `cwl-json-structural-sha256-v1` grammar.

    The grammar preserves JSON scalar types, signed 64-bit integer text,
    IEEE-754 binary64 bits, strict UTF-8 strings, array order, and object keys
    sorted by their UTF-8 byte sequence. Changing any rule requires a new
    digest profile identifier.
    """

    return _encode_value(
        value,
        field_name,
        depth=0,
        active_containers=set(),
    )


def structural_sha256(value: object, field_name: str) -> str:
    """Return the v1 structural SHA-256 identifier for supported JSON data."""

    digest = sha256(encode_structural_json(value, field_name)).hexdigest()
    return f"sha256:{digest}"
