"""Deterministic identities for OpenMetadata admission candidates and receipts."""

from __future__ import annotations

from datetime import datetime, timezone

from .errors import OpenMetadataContractError
from .structural_digest import DIGEST_PROFILE_ID, structural_sha256

RECEIPT_CONTRACT_VERSION = "1.0.0"


def normalize_observed_at(value: object) -> datetime:
    """Return one timezone-qualified observation instant normalized to UTC."""

    if not isinstance(value, datetime):
        raise OpenMetadataContractError("observed_at must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise OpenMetadataContractError("observed_at must include a timezone")
    return value.astimezone(timezone.utc)


def observation_time_text(value: datetime) -> str:
    """Serialize an observation instant with stable UTC microsecond precision."""

    normalized = normalize_observed_at(value)
    return normalized.isoformat(timespec="microseconds").replace(
        "+00:00",
        "Z",
    )


def build_admission_replay_key(
    *,
    tenant_id: str,
    source_instance_id: str,
    source_authority: str,
    source_release: str,
    compatibility_profile_id: str,
    upstream_repository: str,
    upstream_revision: str,
    external_entity_id: str,
    source_snapshot_digest: str,
    projection_digest: str,
) -> str:
    """Bind one deterministic candidate to source and safe-projection evidence."""

    return structural_sha256(
        {
            "receipt_contract_version": RECEIPT_CONTRACT_VERSION,
            "digest_profile_id": DIGEST_PROFILE_ID,
            "tenant_id": tenant_id,
            "source_instance_id": source_instance_id,
            "source_authority": source_authority,
            "source_release": source_release,
            "compatibility_profile_id": compatibility_profile_id,
            "upstream_repository": upstream_repository,
            "upstream_revision": upstream_revision,
            "external_entity_id": external_entity_id,
            "source_snapshot_digest": source_snapshot_digest,
            "projection_digest": projection_digest,
        },
        "admission replay identity",
    )


def _digest_hex(value: str, field_name: str) -> str:
    """Extract a lowercase SHA-256 payload from a validated digest identifier."""

    prefix = "sha256:"
    if not value.startswith(prefix) or len(value) != len(prefix) + 64:
        raise OpenMetadataContractError(
            f"{field_name} must be a sha256 digest"
        )
    digest_hex = value[len(prefix) :]
    if any(character not in "0123456789abcdef" for character in digest_hex):
        raise OpenMetadataContractError(
            f"{field_name} must be a sha256 digest"
        )
    return digest_hex


def build_admission_candidate_id(
    *,
    tenant_id: str,
    replay_key: str,
) -> str:
    """Build the stable candidate URN from its replay identity."""

    return (
        f"urn:cwl:{tenant_id}:sdp:openmetadata_admission_candidate:"
        f"{_digest_hex(replay_key, 'replay_key')}"
    )


def build_admission_receipt_id(
    *,
    tenant_id: str,
    admission_candidate_id: str,
    observed_at: datetime,
) -> str:
    """Build an idempotent receipt URN for one candidate observation event."""

    event_digest = structural_sha256(
        {
            "receipt_contract_version": RECEIPT_CONTRACT_VERSION,
            "admission_candidate_id": admission_candidate_id,
            "observed_at": observation_time_text(observed_at),
        },
        "admission receipt identity",
    )
    return (
        f"urn:cwl:{tenant_id}:sdp:openmetadata_admission_preview:"
        f"{_digest_hex(event_digest, 'receipt event digest')}"
    )
