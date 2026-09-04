"""Errors raised by the OpenMetadata anti-corruption layer."""


class OpenMetadataContractError(ValueError):
    """Raised when an OpenMetadata payload violates the bounded contract."""
