"""Immutable OpenMetadata release compatibility profiles."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .errors import OpenMetadataContractError

_RELEASE_PATTERN = re.compile(
    r"^2\.(?:0|[1-9]\d*)(?:\.(?:0|[1-9]\d*))?(?:-release)?$"
)


@dataclass(frozen=True, slots=True)
class OpenMetadataReleaseProfile:
    """One exact upstream release verified by CWL contract fixtures."""

    profile_id: str
    canonical_release: str
    accepted_release_labels: tuple[str, ...]
    upstream_repository: str
    upstream_revision: str
    table_schema_path: str
    lineage_schema_path: str


OPENMETADATA_2_0_1_PROFILE = OpenMetadataReleaseProfile(
    profile_id="openmetadata-table-lineage-2.0.1",
    canonical_release="2.0.1",
    accepted_release_labels=("2.0.1", "2.0.1-release"),
    upstream_repository="open-metadata/OpenMetadata",
    upstream_revision="bf621b166ec12e8c99fcb1c1443442723386fa41",
    table_schema_path=(
        "openmetadata-spec/src/main/resources/json/schema/entity/data/table.json"
    ),
    lineage_schema_path=(
        "openmetadata-spec/src/main/resources/json/schema/type/entityLineage.json"
    ),
)

_RELEASE_PROFILES = {
    label: OPENMETADATA_2_0_1_PROFILE
    for label in OPENMETADATA_2_0_1_PROFILE.accepted_release_labels
}


def resolve_openmetadata_release_profile(
    source_release: object,
) -> OpenMetadataReleaseProfile:
    """Return the exact verified profile for a declared OpenMetadata release."""

    if not isinstance(source_release, str):
        raise OpenMetadataContractError("source_release must be a string")
    if not source_release:
        raise OpenMetadataContractError("source_release is required")
    if len(source_release) > 64:
        raise OpenMetadataContractError(
            "source_release exceeds 64 characters"
        )
    if any(ord(character) < 32 for character in source_release):
        raise OpenMetadataContractError(
            "source_release contains control characters"
        )
    if not _RELEASE_PATTERN.fullmatch(source_release):
        raise OpenMetadataContractError(
            "source_release must identify an OpenMetadata 2.x release"
        )
    try:
        return _RELEASE_PROFILES[source_release]
    except KeyError as exc:
        raise OpenMetadataContractError(
            "source_release has no verified OpenMetadata compatibility profile"
        ) from exc
