from __future__ import annotations

from copy import deepcopy

import pytest

from sdp.file_ontology import (
    FileAsset,
    SemanticAssertion,
    StorageDistribution,
    file_asset_jsonld,
    validate_file_asset,
)


ASSET_SHA256 = "a" * 64
CHUNK_SHA256 = "b" * 64


def sample_distribution(**overrides: object) -> StorageDistribution:
    values: dict[str, object] = {
        "id": "dist-local",
        "provider": "filesystem",
        "locator": "file:///D:/Documents/report.docx",
        "endpoint_id": "windows-local",
    }
    values.update(overrides)
    return StorageDistribution(**values)


def sample_assertion(**overrides: object) -> SemanticAssertion:
    values: dict[str, object] = {
        "relation": "usesSystem",
        "target_kind": "system",
        "target_label": "C-Cube",
        "confidence": 0.91,
        "evidence_chunk_sha256": CHUNK_SHA256,
        "evidence_start": 3,
        "evidence_end": 9,
    }
    values.update(overrides)
    return SemanticAssertion(**values)


def sample_asset(**overrides: object) -> FileAsset:
    values: dict[str, object] = {
        "sha256": ASSET_SHA256,
        "title": "효성중공업 VOC 종료보고서",
        "media_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "byte_size": 1024,
        "distributions": [sample_distribution()],
        "assertions": [sample_assertion()],
    }
    values.update(overrides)
    return FileAsset(**values)


def test_file_asset_jsonld_uses_standards_and_redacts_locator():
    asset = sample_asset()

    payload = file_asset_jsonld(asset)

    assert payload["@type"] == ["dcat:Resource", "prov:Entity", "cwl:FileAsset"]
    assert "dcat:accessURL" not in payload["dcat:distribution"][0]
    assert payload["spdx:checksum"]["spdx:checksumValue"] == asset.sha256
    assert payload["dcterms:subject"][0]["skos:prefLabel"] == "C-Cube"


def test_file_asset_jsonld_can_include_authorized_locations():
    payload = file_asset_jsonld(sample_asset(), include_locations=True)

    assert payload["dcat:distribution"][0]["dcat:accessURL"] == "file:///D:/Documents/report.docx"


def test_file_asset_validation_rejects_unverifiable_evidence():
    raw = sample_assertion().model_dump()
    raw["evidence_chunk_sha256"] = ""
    raw["evidence_start"] = 4
    raw["evidence_end"] = 2
    asset = sample_asset(assertions=[raw])

    report = validate_file_asset(asset)

    assert report["conforms"] is False
    paths = {violation["path"] for violation in report["violations"]}
    assert {"assertions.evidence_chunk_sha256", "assertions.evidence_end"} <= paths


@pytest.mark.parametrize(
    ("provider", "overrides", "expected_path"),
    [
        ("s3", {"bucket": None, "object_key": "report.pdf"}, "distributions.bucket"),
        ("s3_compatible", {"bucket": "voc", "object_key": None}, "distributions.object_key"),
        ("azure_blob", {"container": None, "object_key": "report.pdf"}, "distributions.container"),
    ],
)
def test_file_asset_validation_checks_provider_coordinates(provider, overrides, expected_path):
    values = deepcopy(sample_distribution().model_dump())
    values.update(
        provider=provider,
        locator="https://objects.example/voc/report.pdf",
        endpoint_id="objects",
        **overrides,
    )
    asset = sample_asset(distributions=[values])

    report = validate_file_asset(asset)

    assert report["conforms"] is False
    assert expected_path in {violation["path"] for violation in report["violations"]}


def test_distribution_rejects_locator_query_to_avoid_secret_leak():
    with pytest.raises(ValueError, match="query or fragment"):
        sample_distribution(locator="https://objects.example/report.pdf?sig=secret")
