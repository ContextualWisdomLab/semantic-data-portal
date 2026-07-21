from __future__ import annotations

import json
from copy import deepcopy
from importlib.resources import files
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from fastapi.testclient import TestClient
from pypdf import PdfWriter
from sdp_core import ActorContext

from sdp import api as api_module
from sdp.api import app
from sdp.document_semantics import (
    ContextualOrchestratorClient,
    EphemeralCredentialRegistry,
    chunk_text,
    extract_document_text,
)

from sdp.file_ontology import (
    FileAsset,
    SemanticAssertion,
    StorageDistribution,
    file_asset_jsonld,
    get_file_asset,
    upsert_file_asset,
    validate_file_asset,
)
from sdp.file_pilot import run_local_pilot
from sdp.graph_store import InMemoryGraphStore
from sdp.storage_readers import AzureBlobReader, FilesystemReader, S3Reader


ASSET_SHA256 = "a" * 64
CHUNK_SHA256 = "b" * 64
client = TestClient(app)


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
        "method": "manual-test",
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


def test_semantic_assertion_requires_extraction_provenance():
    values = sample_assertion().model_dump()
    values.pop("method")

    with pytest.raises(ValueError, match="method"):
        SemanticAssertion(**values)


def test_machine_readable_profile_requires_assertion_provenance():
    root = Path(__file__).resolve().parents[1]
    profile = (root / "ontology" / "cwl-file-profile.ttl").read_text(encoding="utf-8")
    shapes = (root / "ontology" / "cwl-file-shapes.ttl").read_text(encoding="utf-8")

    assert "cwl:extractionMethod a owl:DatatypeProperty" in profile
    assert "sh:path cwl:extractionMethod ; sh:minCount 1" in shapes
    assert "owl:equivalentClass" not in profile
    assert "rdfs:subClassOf dcat:Resource" in profile
    assert "sh:minInclusive 0" in shapes
    assert "sh:maxInclusive 1" in shapes
    assert "sh:lessThan cwl:evidenceEnd" in shapes
    assert "sh:in ( \"proposed\" \"approved\" \"rejected\" )" in shapes


def test_machine_readable_profile_is_packaged_with_the_runtime():
    resources = files("sdp").joinpath("resources")

    assert resources.joinpath("cwl-file-profile.ttl").is_file()
    assert resources.joinpath("cwl-file-shapes.ttl").is_file()


def test_file_asset_validation_executes_shacl_engine():
    report = validate_file_asset(sample_asset())

    assert report["conforms"] is True
    assert report["shacl_engine"] == "pyshacl"


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


def test_distribution_rejects_locator_userinfo_to_avoid_secret_leak():
    with pytest.raises(ValueError, match="userinfo"):
        sample_distribution(locator="https://user:secret@objects.example/report.pdf")


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
        def download_blob(*, offset, length):
            assert offset == 0
            assert length == 21
            return SimpleNamespace(readall=lambda: b"content")

        return SimpleNamespace(download_blob=download_blob)


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


def test_openxml_rejects_oversized_uncompressed_member():
    payload = BytesIO()
    with ZipFile(payload, "w", ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", b"x" * (8 * 1024 * 1024 + 1))

    document = extract_document_text("bomb.docx", payload.getvalue())

    assert document.status == "extraction_failed"
    assert document.error == "ValueError"


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


def fake_orchestrator_transport(captured, *, evidence_quote="효성중공업"):
    def transport(request, timeout):
        payload = json.loads(request.data.decode("utf-8"))
        captured.update(payload)
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        assert request.get_header("Authorization") == "Bearer orchestrator-token"
        return {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": json.dumps(
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
                }
            ],
        }

    return transport


def test_orchestrator_extractor_uses_strict_schema_and_persists_only_evidence_reference():
    captured = {}
    extractor = ContextualOrchestratorClient(
        EphemeralCredentialRegistry(
            {"CONTEXTUAL_ORCHESTRATOR_TOKEN": "orchestrator-token"}
        ),
        base_url="https://orchestrator.example",
        transport=fake_orchestrator_transport(captured),
    )

    assertions = extractor.extract("meeting.docx", chunk_text("효성중공업 C-Cube PoC"))

    assert captured["store"] is False
    assert captured["model"] == "gpt-5-mini-2025-08-07"
    assert captured["response_format"]["type"] == "json_schema"
    assert captured["response_format"]["json_schema"]["strict"] is True
    assert captured["url"] == "https://orchestrator.example/v1/chat/completions"
    assert captured["timeout"] == 60
    assert assertions[0].relation == "usesSystem"
    assert assertions[0].method == "contextual-orchestrator"
    assert assertions[0].evidence_chunk_sha256
    assert assertions[0].evidence_start < assertions[0].evidence_end
    assert "효성중공업" not in assertions[0].model_dump_json()
    assert "orchestrator-token" not in repr(captured)


def test_orchestrator_extractor_rejects_quote_not_present_in_input():
    extractor = ContextualOrchestratorClient(
        EphemeralCredentialRegistry(
            {"CONTEXTUAL_ORCHESTRATOR_TOKEN": "orchestrator-token"}
        ),
        base_url="https://orchestrator.example",
        transport=fake_orchestrator_transport({}, evidence_quote="invented evidence"),
    )

    assert extractor.extract("meeting.docx", chunk_text("효성중공업 C-Cube PoC")) == []


def test_orchestrator_extractor_fails_closed_without_credential():
    extractor = ContextualOrchestratorClient(
        EphemeralCredentialRegistry({}),
        base_url="https://orchestrator.example",
        transport=lambda *_: {},
    )

    with pytest.raises(ValueError, match="credential is unavailable"):
        extractor.extract("meeting.docx", chunk_text("효성중공업 C-Cube PoC"))


def test_orchestrator_client_uses_sync_embeddings_endpoint():
    captured = {}

    def transport(request, timeout):
        captured["url"] = request.full_url
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        assert request.get_header("Authorization") == "Bearer orchestrator-token"
        return {
            "object": "list",
            "data": [
                {"object": "embedding", "index": 1, "embedding": [0.0, 1.0]},
                {"object": "embedding", "index": 0, "embedding": [1.0, 0.0]},
            ],
            "model": "text-embedding-3-small",
            "usage": {"prompt_tokens": 4, "total_tokens": 4},
        }

    client = ContextualOrchestratorClient(
        EphemeralCredentialRegistry(
            {"CONTEXTUAL_ORCHESTRATOR_TOKEN": "orchestrator-token"}
        ),
        base_url="https://orchestrator.example/",
        transport=transport,
        embedding_dimensions=2,
    )

    assert client.embed(["alpha", "beta"]) == [[1.0, 0.0], [0.0, 1.0]]
    assert captured["url"] == "https://orchestrator.example/v1/embeddings"
    assert captured["payload"] == {
        "model": "text-embedding-3-small",
        "input": ["alpha", "beta"],
        "dimensions": 2,
        "metadata": {"service": "semantic-data-portal"},
    }


def test_orchestrator_client_rejects_wrong_embedding_dimension():
    client = ContextualOrchestratorClient(
        EphemeralCredentialRegistry(
            {"CONTEXTUAL_ORCHESTRATOR_TOKEN": "orchestrator-token"}
        ),
        base_url="https://orchestrator.example",
        embedding_dimensions=2,
        transport=lambda *_: {
            "data": [{"index": 0, "embedding": [1.0, 0.0, 0.0]}],
        },
    )

    with pytest.raises(ValueError, match="dimension"):
        client.embed(["alpha"])


def test_graph_store_can_use_orchestrator_embedding_client():
    embedded = []

    def embedder(text):
        embedded.append(text)
        return [1.0, 0.0] if "VOC" in text else [0.0, 1.0]

    store = InMemoryGraphStore(embedder=embedder)
    store.upsert_node("voc", "file_asset", label="효성중공업 VOC")

    assert store.semantic_search("VOC query")[0]["node_id"] == "voc"
    assert embedded == ["효성중공업 VOC", "VOC query"]


def test_local_pilot_deduplicates_content_and_writes_no_raw_text(tmp_path):
    root = tmp_path / "input"
    root.mkdir()
    (root / "효성중공업 VOC.txt").write_text("C-Cube PoC", encoding="utf-8")
    (root / "중공업VOC copy.txt").write_text("C-Cube PoC", encoding="utf-8")
    output = tmp_path / "manifest.json"

    class FakeExtractor:
        def __init__(self):
            self.extract_calls = 0

        def extract(self, filename, chunks):
            self.extract_calls += 1
            chunk = chunks[0]
            return [
                SemanticAssertion(
                    relation="usesSystem",
                    target_kind="system",
                    target_label="C-Cube",
                    confidence=0.9,
                    evidence_chunk_sha256=chunk.sha256,
                    evidence_start=chunk.start,
                    evidence_end=chunk.start + len("C-Cube"),
                    method="fake-extractor",
                )
            ]

        def embed_one(self, text):
            return [1.0, 0.0]

    extractor = FakeExtractor()
    summary = run_local_pilot(
        root,
        output,
        name_pattern=r"효성중공업|중공업VOC",
        extractor=extractor,
    )

    manifest = output.read_text(encoding="utf-8")
    assert summary["files"] == 2
    assert summary["assets"] == 1
    assert summary["distributions"] == 2
    assert extractor.extract_calls == 1
    assert "C-Cube PoC" not in manifest
    assert "evidence_quote" not in manifest
    assert "dcat:accessURL" in manifest


def test_upsert_file_asset_merges_same_content_distributions_and_projects_assertions():
    store = InMemoryGraphStore()
    first = sample_asset()
    second = sample_asset(
        distributions=[
            sample_distribution(
                id="dist-copy",
                locator="file:///D:/Documents/report-copy.docx",
            )
        ]
    )

    upsert_file_asset(store, first)
    merged = upsert_file_asset(store, second)

    assert len(merged.distributions) == 2
    assert get_file_asset(store, first.asset_id) == merged
    graph = store.traverse(first.asset_id, direction="out", max_depth=1)
    assert {edge["edge_type"] for edge in graph["edges"]} >= {
        "DISTRIBUTION",
        "USES_SYSTEM",
    }
    node = store.get_node(first.asset_id)
    assert node is not None
    assert "C-Cube PoC" not in json.dumps(node.properties, ensure_ascii=False)


def test_file_relationship_projects_content_addressed_target_id():
    store = InMemoryGraphStore()
    target_id = f"urn:sha256:{'c' * 64}"
    assertion = sample_assertion(
        relation="previousVersion",
        target_kind="file_asset",
        target_label="이전 VOC 보고서",
        target_asset_id=target_id,
    )

    upsert_file_asset(store, sample_asset(assertions=[assertion]))

    graph = store.traverse(sample_asset().asset_id, direction="out", max_depth=1)
    edge = next(item for item in graph["edges"] if item["edge_type"] == "PREVIOUS_VERSION")
    assert edge["target_id"] == target_id


def test_file_relationship_does_not_overwrite_existing_target_asset():
    store = InMemoryGraphStore()
    target = sample_asset(
        sha256="c" * 64,
        title="원본 VOC 보고서",
        distributions=[
            sample_distribution(id="target-dist", locator="file:///D:/Documents/original.docx")
        ],
        assertions=[],
    )
    upsert_file_asset(store, target)
    before = store.get_node(target.asset_id)
    assertion = sample_assertion(
        relation="previousVersion",
        target_kind="file_asset",
        target_label="이전 VOC 보고서",
        target_asset_id=target.asset_id,
    )

    upsert_file_asset(store, sample_asset(assertions=[assertion]))

    after = store.get_node(target.asset_id)
    assert before is not None and after is not None
    assert after.label == before.label
    assert after.properties["file_asset"] == before.properties["file_asset"]


def test_explicit_steward_review_supersedes_model_confidence():
    store = InMemoryGraphStore()
    proposed = sample_assertion(confidence=0.99, review_status="proposed")
    approved = sample_assertion(confidence=0.60, review_status="approved")

    upsert_file_asset(store, sample_asset(assertions=[proposed]))
    merged = upsert_file_asset(store, sample_asset(assertions=[approved]))

    assert merged.assertions[0].review_status == "approved"
    assert merged.assertions[0].confidence == 0.60


def sample_request() -> dict[str, object]:
    return sample_asset().model_dump(mode="json")


def auth_headers(role: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {role}-token"}


def install_fake_oidc(monkeypatch):
    def verify(token):
        identity = token.removesuffix("-token")
        tenant_id, _, role = identity.partition(":")
        if not role:
            tenant_id, role = "demo", tenant_id
        roles = {
            "admin": ["admin", "data-analyst"],
            "platform-admin": ["platform-admin", "admin", "data-analyst"],
            "analyst": ["data-analyst"],
        }.get(role, ["data-analyst"])
        return ActorContext(subject=identity, tenant_id=tenant_id, roles=roles), {}

    monkeypatch.setattr(api_module.authz, "verify_oidc_jwks_token", verify)


def test_file_asset_api_requires_policy_and_redacts_jsonld_locator(monkeypatch):
    store = InMemoryGraphStore()
    monkeypatch.setattr(api_module, "get_store", lambda: store)
    install_fake_oidc(monkeypatch)

    denied = client.post("/file-assets", json=sample_request(), headers=auth_headers("analyst"))
    impersonation = client.post("/file-assets", json={**sample_request(), "actor": "admin"})
    created = client.post("/file-assets", json=sample_request(), headers=auth_headers("admin"))

    assert denied.status_code == 403
    assert impersonation.status_code == 401
    assert created.status_code == 200
    asset_id = created.json()["asset_id"]
    detail = client.get(f"/file-assets/{asset_id}", headers=auth_headers("analyst"))
    graph_node = client.get(f"/graph/nodes/{asset_id}", headers=auth_headers("analyst"))
    exported = client.get(f"/file-assets/{asset_id}/jsonld", headers=auth_headers("analyst"))
    assert detail.status_code == 200
    assert "file:///" not in detail.text
    assert graph_node.status_code == 200
    assert "file:///" not in graph_node.text
    assert exported.status_code == 200
    assert "dcat:accessURL" not in exported.text

    location_denied = client.get(
        f"/file-assets/{asset_id}/jsonld",
        params={"actor": "admin", "include_locations": True},
        headers=auth_headers("analyst"),
    )
    location_allowed = client.get(
        f"/file-assets/{asset_id}/jsonld",
        params={"include_locations": True},
        headers=auth_headers("admin"),
    )
    detail_location_allowed = client.get(
        f"/file-assets/{asset_id}",
        params={"include_locations": True},
        headers=auth_headers("admin"),
    )
    assert location_denied.status_code == 403
    assert location_allowed.status_code == 200
    assert location_allowed.json()["dcat:distribution"][0]["dcat:accessURL"].startswith("file:")
    assert detail_location_allowed.status_code == 200
    assert detail_location_allowed.json()["distributions"][0]["locator"].startswith("file:")


def test_file_asset_api_exposes_validation_and_404(monkeypatch):
    store = InMemoryGraphStore()
    monkeypatch.setattr(api_module, "get_store", lambda: store)
    install_fake_oidc(monkeypatch)
    created = client.post("/file-assets", json=sample_request(), headers=auth_headers("admin"))
    asset_id = created.json()["asset_id"]

    report = client.get(f"/file-assets/{asset_id}/validate", headers=auth_headers("analyst"))
    missing = client.get(
        f"/file-assets/urn:sha256:{'f' * 64}", headers=auth_headers("analyst")
    )

    assert report.status_code == 200
    assert report.json()["conforms"] is True
    assert missing.status_code == 404


def test_file_asset_api_enforces_tenant_ownership(monkeypatch):
    store = InMemoryGraphStore()
    monkeypatch.setattr(api_module, "get_store", lambda: store)
    install_fake_oidc(monkeypatch)
    created = client.post(
        "/file-assets",
        json=sample_request(),
        headers=auth_headers("demo:admin"),
    )
    asset_id = created.json()["asset_id"]

    denied = client.get(
        f"/file-assets/{asset_id}",
        headers=auth_headers("external:analyst"),
    )
    allowed = client.get(
        f"/file-assets/{asset_id}",
        headers=auth_headers("external:platform-admin"),
    )

    assert denied.status_code == 403
    assert allowed.status_code == 200
    assert get_file_asset(store, asset_id).tenant_id == "demo"


def test_cross_tenant_same_sha_ingest_is_rejected_without_merging(monkeypatch):
    store = InMemoryGraphStore()
    monkeypatch.setattr(api_module, "get_store", lambda: store)
    install_fake_oidc(monkeypatch)
    first = client.post(
        "/file-assets",
        json=sample_request(),
        headers=auth_headers("demo:admin"),
    )
    second_payload = sample_request()
    second_payload["distributions"] = [
        sample_distribution(
            id="external-copy",
            locator="file:///D:/External/report.docx",
        ).model_dump(mode="json")
    ]

    denied = client.post(
        "/file-assets",
        json=second_payload,
        headers=auth_headers("external:admin"),
    )

    assert first.status_code == 200
    assert denied.status_code == 403
    stored = get_file_asset(store, first.json()["asset_id"])
    assert stored is not None
    assert stored.tenant_id == "demo"
    assert [distribution.id for distribution in stored.distributions] == ["dist-local"]


def test_cross_tenant_file_relationship_target_is_rejected(monkeypatch):
    store = InMemoryGraphStore()
    monkeypatch.setattr(api_module, "get_store", lambda: store)
    install_fake_oidc(monkeypatch)
    target = sample_asset(sha256="c" * 64, assertions=[])
    upsert_file_asset(store, target)
    relation = sample_assertion(
        relation="previousVersion",
        target_kind="file_asset",
        target_label="다른 tenant 문서",
        target_asset_id=target.asset_id,
    )
    source = sample_asset(sha256="d" * 64, assertions=[relation]).model_dump(mode="json")

    denied = client.post(
        "/file-assets",
        json=source,
        headers=auth_headers("external:admin"),
    )

    assert denied.status_code == 403
    assert get_file_asset(store, f"urn:sha256:{'d' * 64}") is None


def test_graph_routes_require_oidc_filter_tenant_and_redact_locator(monkeypatch):
    store = InMemoryGraphStore()
    monkeypatch.setattr(api_module, "get_store", lambda: store)
    install_fake_oidc(monkeypatch)
    created = client.post(
        "/file-assets",
        json=sample_request(),
        headers=auth_headers("demo:admin"),
    )
    asset_id = created.json()["asset_id"]

    unauthenticated = client.post(
        "/graph/query",
        json={"start_id": asset_id, "actor": "analyst", "max_depth": 1},
    )
    cross_tenant = client.post(
        "/graph/query",
        json={"start_id": asset_id, "max_depth": 1},
        headers=auth_headers("external:analyst"),
    )
    visible = client.post(
        "/graph/query",
        json={"start_id": asset_id, "max_depth": 1},
        headers=auth_headers("demo:analyst"),
    )
    cross_tenant_search = client.post(
        "/search/semantic",
        json={"query": "효성중공업 VOC 종료보고서", "kind": "file_asset", "limit": 50},
        headers=auth_headers("external:analyst"),
    )

    assert unauthenticated.status_code == 401
    assert cross_tenant.status_code == 403
    assert visible.status_code == 200
    assert "file:///" not in visible.text
    assert asset_id not in {
        item["node_id"] for item in cross_tenant_search.json()["results"]
    }


def test_semantic_search_filters_tenant_before_limit():
    config = SimpleNamespace(
        embedding_dimension=2,
        semantic_search_default_limit=5,
        traversal_max_depth=4,
    )
    store = InMemoryGraphStore(config=config, embedder=lambda _text: [1.0, 0.0])
    for index in range(501):
        store.upsert_node(
            f"external-{index}",
            "file_asset",
            properties={"tenant_id": "external"},
            text="same score",
        )
    store.upsert_node(
        "demo-file",
        "file_asset",
        properties={"tenant_id": "demo"},
        text="same score",
    )

    results = store.semantic_search(
        "same score",
        kind="file_asset",
        limit=1,
        tenant_id="demo",
    )

    assert [item["node_id"] for item in results] == ["demo-file"]


def test_generic_graph_mutation_cannot_create_governed_file_node(monkeypatch):
    install_fake_oidc(monkeypatch)

    response = client.post(
        "/graph/nodes",
        json={"node_id": "forged", "kind": "file_asset"},
        headers=auth_headers("demo:admin"),
    )

    assert response.status_code == 400

    reserved_id = client.post(
        "/graph/nodes",
        json={"node_id": f"urn:sha256:{'e' * 64}", "kind": "concept"},
        headers=auth_headers("demo:admin"),
    )
    reserved_edge = client.post(
        "/graph/edges",
        json={
            "edge_type": "related",
            "source_id": "고객",
            "target_id": f"urn:sha256:{'e' * 64}",
        },
        headers=auth_headers("demo:admin"),
    )

    assert reserved_id.status_code == 400
    assert reserved_edge.status_code == 400


def test_ontology_concept_cannot_overwrite_or_reference_file_identifier(monkeypatch):
    store = InMemoryGraphStore()
    monkeypatch.setattr(api_module, "get_store", lambda: store)
    install_fake_oidc(monkeypatch)
    asset = sample_asset()
    upsert_file_asset(store, asset)

    overwrite = client.post(
        "/ontology/concepts",
        json={"concept": asset.asset_id},
        headers=auth_headers("demo:admin"),
    )
    reference = client.post(
        "/ontology/concepts",
        json={"concept": "안전한 개념", "related": [asset.asset_id]},
        headers=auth_headers("demo:admin"),
    )

    assert overwrite.status_code == 400
    assert reference.status_code == 400
    node = store.get_node(asset.asset_id)
    assert node is not None and node.kind == "file_asset"
    assert node.properties["tenant_id"] == "demo"

    with pytest.raises(ValueError, match="governed file identifiers"):
        store.upsert_concept({"concept": asset.asset_id})
