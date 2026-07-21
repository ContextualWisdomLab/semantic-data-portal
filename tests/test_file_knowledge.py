from __future__ import annotations

import json
from copy import deepcopy
from io import BytesIO
from types import SimpleNamespace
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from pypdf import PdfWriter

from sdp.document_semantics import (
    EphemeralCredentialRegistry,
    OpenAISemanticExtractor,
    chunk_text,
    extract_document_text,
)

from sdp.file_ontology import (
    FileAsset,
    SemanticAssertion,
    StorageDistribution,
    file_asset_jsonld,
    validate_file_asset,
)
from sdp.storage_readers import AzureBlobReader, FilesystemReader, S3Reader


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


def test_filesystem_reader_stays_inside_root_and_reads_bytes(tmp_path):
    path = tmp_path / "효성중공업 VOC.txt"
    path.write_text("C-Cube PoC", encoding="utf-8")
    (tmp_path / "~$효성중공업 VOC.docx").write_bytes(b"temporary")
    reader = FilesystemReader(tmp_path)

    refs = list(reader.list(name_pattern=r"효성중공업|중공업VOC"))

    assert len(refs) == 1
    assert reader.read(refs[0], max_bytes=1024) == "C-Cube PoC".encode()
    assert refs[0].distribution.provider == "filesystem"
    assert refs[0].distribution.locator == path.resolve().as_uri()


def test_filesystem_reader_rejects_oversized_object(tmp_path):
    path = tmp_path / "중공업VOC.txt"
    path.write_bytes(b"12345")
    reader = FilesystemReader(tmp_path)
    ref = next(reader.list())

    with pytest.raises(ValueError, match="maximum size"):
        reader.read(ref, max_bytes=4)


class FakeS3:
    def get_paginator(self, operation):
        assert operation == "list_objects_v2"
        return SimpleNamespace(
            paginate=lambda **kwargs: [
                {
                    "Contents": [
                        {
                            "Key": f"{kwargs['Prefix']}a.docx",
                            "Size": 7,
                            "ETag": '"etag-a"',
                        }
                    ]
                }
            ]
        )

    def get_object(self, **kwargs):
        assert kwargs == {"Bucket": "voc", "Key": "reports/a.docx"}
        return {"Body": BytesIO(b"content")}


class FakeContainer:
    url = "https://account.blob.core.windows.net/voc"
    container_name = "voc"

    def list_blobs(self, *, name_starts_with):
        return [
            SimpleNamespace(
                name=f"{name_starts_with}a.docx",
                size=7,
                etag="etag-a",
                version_id="version-a",
                last_modified=None,
            )
        ]

    def get_blob_client(self, name, **kwargs):
        assert name == "reports/a.docx"
        assert kwargs == {"version_id": "version-a"}
        return SimpleNamespace(download_blob=lambda: SimpleNamespace(readall=lambda: b"content"))


def test_s3_and_azure_readers_use_injected_clients():
    s3 = S3Reader(FakeS3(), "voc")
    azure = AzureBlobReader(FakeContainer())

    s3_ref = next(s3.list("reports/"))
    azure_ref = next(azure.list("reports/"))

    assert s3_ref.object_key == azure_ref.object_key == "reports/a.docx"
    assert s3.read(s3_ref, max_bytes=20) == b"content"
    assert azure.read(azure_ref, max_bytes=20) == b"content"
    assert s3_ref.distribution.locator == "s3://voc/reports/a.docx"
    assert azure_ref.distribution.container == "voc"


def test_s3_compatible_reader_uses_stable_endpoint_without_credentials():
    reader = S3Reader(
        FakeS3(),
        "voc",
        provider="s3_compatible",
        endpoint_url="https://objects.example",
    )

    ref = next(reader.list("reports/"))

    assert ref.distribution.provider == "s3_compatible"
    assert ref.distribution.locator == "https://objects.example/voc/reports/a.docx"


def make_openxml(member: str, text: str) -> bytes:
    payload = BytesIO()
    with ZipFile(payload, "w", ZIP_DEFLATED) as archive:
        archive.writestr(
            member,
            f'<root xmlns:w="urn:test"><w:t>{text}</w:t></root>',
        )
    return payload.getvalue()


@pytest.mark.parametrize(
    ("filename", "member"),
    [
        ("meeting.docx", "word/document.xml"),
        ("briefing.pptx", "ppt/slides/slide1.xml"),
        ("feedback.xlsx", "xl/sharedStrings.xml"),
    ],
)
def test_openxml_text_is_extracted_without_office_dependency(filename, member):
    payload = make_openxml(member, "효성중공업 VOC C-Cube")

    document = extract_document_text(filename, payload)

    assert document.status == "extracted"
    assert "효성중공업 VOC C-Cube" in document.text


def test_chunks_are_bounded_overlapped_and_content_addressed():
    chunks = chunk_text("가" * 13_000, max_chars=6_000, overlap=300, max_total_chars=24_000)

    assert len(chunks) == 3
    assert max(len(chunk.text) for chunk in chunks) <= 6_000
    assert all(len(chunk.sha256) == 64 for chunk in chunks)
    assert chunks[1].start == chunks[0].end - 300


def test_pdf_without_extractable_text_is_marked_for_ocr():
    payload = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.write(payload)

    document = extract_document_text("scan.pdf", payload.getvalue())

    assert document.status == "needs_ocr"
    assert document.text == ""


def test_corrupt_pdf_is_reported_without_crashing_the_batch():
    document = extract_document_text("broken.pdf", b"not a pdf")

    assert document.status == "extraction_failed"
    assert document.text == ""


def test_unsupported_legacy_format_is_reported_without_guessing():
    document = extract_document_text("legacy.hwp", b"not parsed")

    assert document.status == "unsupported_format"
    assert document.text == ""


def fake_openai_transport(captured, *, evidence_quote="효성중공업"):
    def transport(request, timeout):
        payload = json.loads(request.data.decode("utf-8"))
        captured.update(payload)
        captured["timeout"] = timeout
        assert request.get_header("Authorization") == "Bearer test-key"
        return {
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "text": json.dumps(
                                {
                                    "assertions": [
                                        {
                                            "relation": "usesSystem",
                                            "target_kind": "system",
                                            "target_label": "C-Cube",
                                            "confidence": 0.93,
                                            "evidence_quote": evidence_quote,
                                        }
                                    ]
                                },
                                ensure_ascii=False,
                            ),
                        }
                    ],
                }
            ],
        }

    return transport


def test_openai_extractor_uses_strict_schema_and_persists_only_evidence_reference():
    captured = {}
    extractor = OpenAISemanticExtractor(
        EphemeralCredentialRegistry({"OPENAI_API_KEY": "test-key"}),
        transport=fake_openai_transport(captured),
    )

    assertions = extractor.extract("meeting.docx", chunk_text("효성중공업 C-Cube PoC"))

    assert captured["store"] is False
    assert captured["model"] == "gpt-5-mini-2025-08-07"
    assert captured["text"]["format"]["type"] == "json_schema"
    assert captured["text"]["format"]["strict"] is True
    assert captured["timeout"] == 60
    assert assertions[0].relation == "usesSystem"
    assert assertions[0].evidence_chunk_sha256
    assert assertions[0].evidence_start < assertions[0].evidence_end
    assert "효성중공업" not in assertions[0].model_dump_json()
    assert "test-key" not in repr(captured)


def test_openai_extractor_rejects_quote_not_present_in_input():
    extractor = OpenAISemanticExtractor(
        EphemeralCredentialRegistry({"OPENAI_API_KEY": "test-key"}),
        transport=fake_openai_transport({}, evidence_quote="invented evidence"),
    )

    assert extractor.extract("meeting.docx", chunk_text("효성중공업 C-Cube PoC")) == []


def test_openai_extractor_fails_closed_without_credential():
    extractor = OpenAISemanticExtractor(EphemeralCredentialRegistry({}), transport=lambda *_: {})

    with pytest.raises(ValueError, match="credential is unavailable"):
        extractor.extract("meeting.docx", chunk_text("효성중공업 C-Cube PoC"))
