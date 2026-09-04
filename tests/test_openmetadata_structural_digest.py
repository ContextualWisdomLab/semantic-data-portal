"""Golden vectors for the OpenMetadata structural digest profile."""

from __future__ import annotations

from hashlib import sha256

import pytest

from sdp.openmetadata import (
    DIGEST_PROFILE_ID,
    OpenMetadataContractError,
    encode_structural_json,
    structural_sha256,
)


def test_structural_encoding_has_one_exact_language_neutral_vector() -> None:
    """Every supported JSON scalar and container has a fixed byte encoding."""

    payload = {
        "z": [None, True, False, 1, -2, 1.5, "한"],
        "a": {"b": "x"},
    }
    expected = (
        b"o2{"
        b"s1:a"
        b"o1{s1:bs1:x}"
        b"s1:z"
        b"a7[nb1b0i1;i-2;f3ff8000000000000;s3:\xed\x95\x9c]"
        b"}"
    )

    encoded = encode_structural_json(payload, "payload")

    assert DIGEST_PROFILE_ID == "cwl-json-structural-sha256-v1"
    assert encoded == expected
    assert structural_sha256(payload, "payload") == (
        f"sha256:{sha256(expected).hexdigest()}"
    )


def test_object_order_and_shared_noncyclic_values_are_stable() -> None:
    """UTF-8 key ordering is stable and repeated values are not cycles."""

    shared = ["value"]
    first = {"한": shared, "a": shared}
    second = {"a": shared, "한": shared}

    assert encode_structural_json(first, "payload") == encode_structural_json(
        second,
        "payload",
    )


def test_float_identity_preserves_signed_zero() -> None:
    """IEEE-754 bit identity distinguishes positive and negative zero."""

    positive = structural_sha256(0.0, "payload")
    negative = structural_sha256(-0.0, "payload")

    assert positive != negative
    assert encode_structural_json(0.0, "payload") == (
        b"f0000000000000000;"
    )
    assert encode_structural_json(-0.0, "payload") == (
        b"f8000000000000000;"
    )


@pytest.mark.parametrize(
    ("value", "message"),
    [
        (float("nan"), "not deterministic JSON data"),
        (float("inf"), "not deterministic JSON data"),
        (("foreign",), "not deterministic JSON data"),
        ({1: "value"}, "JSON object keys must be strings"),
        ("\ud800", "not deterministic JSON data"),
        (2**63, "signed 64-bit range"),
        (-(2**63) - 1, "signed 64-bit range"),
    ],
)
def test_unsupported_values_fail_closed(value: object, message: str) -> None:
    """The v1 profile rejects values consumers cannot reproduce exactly."""

    with pytest.raises(OpenMetadataContractError, match=message):
        encode_structural_json(value, "payload")


def test_cycles_and_excessive_depth_fail_closed() -> None:
    """Host-language object graphs cannot exhaust or confuse digest creation."""

    list_cycle: list[object] = []
    list_cycle.append(list_cycle)
    with pytest.raises(OpenMetadataContractError, match="cyclic container"):
        encode_structural_json(list_cycle, "payload")

    dict_cycle: dict[str, object] = {}
    dict_cycle["self"] = dict_cycle
    with pytest.raises(OpenMetadataContractError, match="cyclic container"):
        encode_structural_json(dict_cycle, "payload")

    too_deep: object = None
    for _ in range(66):
        too_deep = [too_deep]
    with pytest.raises(OpenMetadataContractError, match="nesting exceeds 64"):
        encode_structural_json(too_deep, "payload")
