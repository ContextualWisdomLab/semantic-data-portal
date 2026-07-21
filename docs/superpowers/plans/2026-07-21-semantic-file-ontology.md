# Semantic File Ontology Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a standards-aligned, provider-neutral file knowledge catalog with read-only filesystem/S3/S3-compatible/Azure Blob ingestion, evidence-bound OpenAI semantic extraction, and a Hyosung Heavy Industries VOC pilot.

**Architecture:** Keep Apache AGE and pgvector as the persistence/search implementation. Represent content-addressed `FileAsset` nodes separately from one-or-many DCAT `Distribution` nodes, project validated LLM assertions into the existing graph, and export JSON-LD. Read document bytes through small injected readers; raw text never enters graph properties or Git.

**Tech Stack:** Python 3.10+, FastAPI, Pydantic 2, existing graph store, stdlib `pathlib`/`zipfile`/`urllib`, pypdf 6.14.2, W3C RDF/OWL/SKOS/SHACL/DCAT/PROV/JSON-LD vocabularies.

## Global Constraints

- File operations are read-only; no move, delete, copy, or remote mutation.
- Providers are exactly `filesystem`, `s3`, `s3_compatible`, and `azure_blob`; Synology is a filesystem deployment.
- Object bytes are capped at 20 MiB; LLM text is chunked at 6,000 characters with 300-character overlap and capped at 24,000 characters per file.
- The pinned default model is `gpt-5-mini-2025-08-07`; Requests API calls set `store: false` and a 60-second timeout.
- OpenAI API keys and cloud credentials come from an injected credential registry/client, never `os.getenv()`, graph properties, logs, CLI arguments, or GitHub fixtures.
- LLM assertions remain `proposed`; structural validation does not imply steward approval.
- Raw chunks and evidence quotations are not persisted. Persist only chunk SHA-256 and character offsets after verifying the quotation exists.
- Existing policy authorization, AGE/pgvector stores, semantic search, and graph traversal are reused.
- CI uses fake transports and fake cloud clients; it makes no OpenAI or cloud call.
- No OCR, HWP, DOC, XLS parser, mandatory cloud SDK, new database, or automatic ontology approval.

---

### Task 1: Machine-readable CWL profile and file contracts

**Files:**
- Create: `ontology/cwl-file-profile.ttl`
- Create: `ontology/cwl-file-shapes.ttl`
- Create: `src/sdp/file_ontology.py`
- Create: `tests/test_file_knowledge.py`

**Interfaces:**
- Produces: `StorageDistribution`, `SemanticAssertion`, `FileAsset`, `validate_file_asset()`, `file_asset_jsonld()`.
- Consumes: Pydantic 2 only.

- [ ] **Step 1: Write failing contract and JSON-LD tests**

```python
def test_file_asset_jsonld_uses_standards_and_redacts_locator():
    asset = sample_asset()
    payload = file_asset_jsonld(asset)
    assert payload["@type"] == ["dcat:Resource", "prov:Entity", "cwl:FileAsset"]
    assert "dcat:accessURL" not in payload["dcat:distribution"][0]
    assert payload["spdx:checksum"]["spdx:checksumValue"] == asset.sha256

def test_file_asset_validation_rejects_unverifiable_evidence():
    asset = sample_asset(assertion_overrides={"evidence_chunk_sha256": "", "evidence_start": 4, "evidence_end": 2})
    report = validate_file_asset(asset)
    assert report["conforms"] is False
```

- [ ] **Step 2: Run tests and confirm import failure**

Run: `$env:PYTHONPATH='src'; py -m pytest tests/test_file_knowledge.py -q`

Expected: FAIL because `sdp.file_ontology` does not exist.

- [ ] **Step 3: Add the minimal contracts and validation**

```python
StorageProvider = Literal["filesystem", "s3", "s3_compatible", "azure_blob"]
AssertionRelation = Literal[
    "belongsToProject", "usesSystem", "hasWorkPhase", "hasArtifactType",
    "hasTopic", "wasDerivedFrom", "previousVersion",
]

class StorageDistribution(BaseModel):
    id: str
    provider: StorageProvider
    locator: str
    endpoint_id: str
    available: bool = True
    bucket: str | None = None
    container: str | None = None
    object_key: str | None = None
    version_id: str | None = None
    etag: str | None = None

class SemanticAssertion(BaseModel):
    relation: AssertionRelation
    target_kind: Literal["business_project", "system", "work_phase", "artifact_type", "topic", "file_asset"]
    target_label: str
    confidence: float = Field(ge=0, le=1)
    evidence_chunk_sha256: str
    evidence_start: int = Field(ge=0)
    evidence_end: int = Field(gt=0)
    method: str = "openai"
    review_status: Literal["proposed", "approved", "rejected"] = "proposed"

class FileAsset(BaseModel):
    sha256: str
    title: str
    media_type: str
    byte_size: int = Field(ge=0)
    modified_at: datetime | None = None
    distributions: list[StorageDistribution]
    assertions: list[SemanticAssertion] = Field(default_factory=list)

    @property
    def asset_id(self) -> str:
        return f"urn:sha256:{self.sha256}"
```

Validation must require lowercase 64-hex SHA-256, nonempty distributions, provider-specific bucket/container/object-key values, locator without query/fragment, relation/target-kind consistency, 64-hex chunk hash, and `evidence_end > evidence_start`. `file_asset_jsonld(asset, include_locations=False)` maps DCAT/DCTERMS/PROV/SKOS/SPDX/CWL terms and omits `dcat:accessURL` by default.

- [ ] **Step 4: Add OWL/SKOS/DCAT/SHACL Turtle files and run tests**

The profile defines `cwl:FileAsset` as a subclass of `dcat:Resource` and `prov:Entity`; `cwl:BusinessProject`, `cwl:System`, `cwl:WorkPhase`, and `cwl:ArtifactType` as SKOS concept subclasses; and the seven assertion properties as OWL object properties. The shapes require checksum, title, distribution, confidence, review status, and evidence reference fields.

Run: `$env:PYTHONPATH='src'; py -m pytest tests/test_file_knowledge.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ontology src/sdp/file_ontology.py tests/test_file_knowledge.py
git commit -m "feat: define standards-aligned file ontology"
```

### Task 2: Read-only storage readers

**Files:**
- Create: `src/sdp/storage_readers.py`
- Modify: `tests/test_file_knowledge.py`

**Interfaces:**
- Produces: `ObjectRef`, `ObjectReader`, `FilesystemReader`, `S3Reader`, `AzureBlobReader`.
- Consumes: `StorageDistribution` from Task 1 and caller-injected cloud clients.

- [ ] **Step 1: Write failing reader contract tests**

```python
def test_filesystem_reader_stays_inside_root_and_reads_bytes(tmp_path):
    path = tmp_path / "효성중공업 VOC.txt"
    path.write_text("C-Cube PoC", encoding="utf-8")
    reader = FilesystemReader(tmp_path)
    ref = next(reader.list(name_pattern=r"효성중공업|중공업VOC"))
    assert reader.read(ref, max_bytes=1024) == "C-Cube PoC".encode()
    assert ref.distribution.provider == "filesystem"

def test_s3_and_azure_readers_use_injected_clients():
    assert list(S3Reader(FakeS3(), "voc").list("reports/"))[0].object_key == "reports/a.docx"
    assert list(AzureBlobReader(FakeContainer()).list("reports/"))[0].object_key == "reports/a.docx"
```

- [ ] **Step 2: Run focused tests and confirm failure**

Run: `$env:PYTHONPATH='src'; py -m pytest tests/test_file_knowledge.py -k reader -q`

Expected: FAIL because reader classes do not exist.

- [ ] **Step 3: Implement the three readers**

Define `ObjectReader.list(prefix: str = "", *, name_pattern: str | None = None) -> Iterable[ObjectRef]` and `ObjectReader.read(ref: ObjectRef, *, max_bytes: int) -> bytes`. `FilesystemReader` walks with `followlinks=False`, resolves each file, and checks `relative_to(root)` before opening. `S3Reader` uses `get_paginator("list_objects_v2")` and `get_object()["Body"].read(max_bytes + 1)`. `AzureBlobReader` uses `list_blobs(name_starts_with=prefix)` and `get_blob_client(name).download_blob().readall()`.

Each reader rejects an object larger than `max_bytes`; filesystem traversal prunes symlink/junction directories and temporary Office files beginning `~$`. S3-compatible storage uses `S3Reader(client, bucket, provider="s3_compatible", endpoint_url="https://objects.example")`.

- [ ] **Step 4: Run reader tests**

Run: `$env:PYTHONPATH='src'; py -m pytest tests/test_file_knowledge.py -k reader -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/sdp/storage_readers.py tests/test_file_knowledge.py
git commit -m "feat: add provider-neutral read-only storage readers"
```

### Task 3: Safe document text extraction

**Files:**
- Create: `src/sdp/document_semantics.py`
- Modify: `tests/test_file_knowledge.py`
- Modify: `pyproject.toml`
- Modify: `requirements.txt`
- Modify: `requirements-dev.txt`
- Modify: `requirements-test.in`
- Modify: `requirements-test.txt`

**Interfaces:**
- Produces: `DocumentText`, `TextChunk`, `extract_document_text()`, `chunk_text()`.
- Consumes: raw bytes and filename; does not persist text.

- [ ] **Step 1: Write failing extraction/chunk tests**

```python
def test_openxml_text_is_extracted_without_office_dependency():
    payload = make_openxml("word/document.xml", "<w:t>효성중공업 VOC C-Cube</w:t>")
    assert "효성중공업" in extract_document_text("meeting.docx", payload).text

def test_chunks_are_bounded_and_content_addressed():
    chunks = chunk_text("가" * 13000, max_chars=6000, overlap=300, max_total_chars=24000)
    assert max(len(chunk.text) for chunk in chunks) <= 6000
    assert all(len(chunk.sha256) == 64 for chunk in chunks)
```

- [ ] **Step 2: Run tests and confirm failure**

Run: `$env:PYTHONPATH='src'; py -m pytest tests/test_file_knowledge.py -k 'openxml or chunks or pdf' -q`

Expected: FAIL because extraction functions do not exist.

- [ ] **Step 3: Add `pypdf==6.14.2` and regenerate hashes**

Add `pypdf==6.14.2` to `[project.dependencies]` and `requirements-test.in`.

Run:

```powershell
py -m pip install uv
py -m uv pip compile pyproject.toml --generate-hashes -o requirements.txt
py -m uv pip compile pyproject.toml --extra dev --generate-hashes -o requirements-dev.txt
py -m uv pip compile requirements-test.in --generate-hashes -o requirements-test.txt
py -m pip install pypdf==6.14.2
```

Expected: all four dependency declarations contain pypdf 6.14.2 and hashes.

- [ ] **Step 4: Implement extraction and chunking**

`extract_document_text()` decodes text/Markdown/CSV/JSON/XML, reads XML elements whose local name is `t` from DOCX/PPTX/XLSX ZIP members, and uses `PdfReader(BytesIO(data)).pages[*].extract_text()` for PDF. It returns `status="needs_ocr"` when supported input yields no text and `status="unsupported_format"` for other suffixes. `chunk_text()` normalizes whitespace, uses the exact global limits, records global offsets and SHA-256, and returns no empty chunk.

Run: `$env:PYTHONPATH='src'; py -m pytest tests/test_file_knowledge.py -k 'openxml or chunks or pdf' -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml requirements*.txt src/sdp/document_semantics.py tests/test_file_knowledge.py
git commit -m "feat: extract text from pilot document formats"
```

### Task 4: Evidence-bound OpenAI semantic extraction

**Files:**
- Modify: `src/sdp/document_semantics.py`
- Modify: `tests/test_file_knowledge.py`

**Interfaces:**
- Produces: `CredentialRegistry`, `EphemeralCredentialRegistry`, `OpenAISemanticExtractor.extract()`.
- Consumes: `TextChunk`, injected credential registry, injected JSON HTTP transport.

- [ ] **Step 1: Write a failing fake-transport test**

```python
def test_openai_extractor_uses_strict_schema_and_persists_only_evidence_reference():
    captured = {}
    extractor = OpenAISemanticExtractor(
        EphemeralCredentialRegistry({"OPENAI_API_KEY": "test-key"}),
        transport=fake_openai_transport(captured, evidence_quote="C-Cube"),
    )
    assertions = extractor.extract("meeting.docx", chunk_text("효성중공업 C-Cube PoC"))
    assert captured["store"] is False
    assert captured["text"]["format"]["type"] == "json_schema"
    assert assertions[0].evidence_chunk_sha256
    assert "C-Cube" not in assertions[0].model_dump_json()
    assert "test-key" not in repr(captured)
```

- [ ] **Step 2: Run the test and confirm failure**

Run: `$env:PYTHONPATH='src'; py -m pytest tests/test_file_knowledge.py -k openai -q`

Expected: FAIL because the extractor does not exist.

- [ ] **Step 3: Implement the minimal Responses API client**

Use `urllib.request.Request("https://api.openai.com/v1/responses", data=encoded_payload, headers=headers, method="POST")`, an injected `transport(request, timeout) -> dict`, model `gpt-5-mini-2025-08-07`, `store: false`, and strict JSON Schema fields `relation`, `target_kind`, `target_label`, `confidence`, `evidence_quote`. Reject empty/missing credential, non-completed responses, malformed JSON, unknown relations, and quotations not found verbatim in the input chunk. Convert a verified quote to chunk hash plus global offsets, then discard the quote. Merge duplicate `(relation, target_kind, casefold(target_label))` candidates by highest confidence.

- [ ] **Step 4: Run OpenAI tests**

Run: `$env:PYTHONPATH='src'; py -m pytest tests/test_file_knowledge.py -k openai -q`

Expected: PASS with no network call.

- [ ] **Step 5: Commit**

```bash
git add src/sdp/document_semantics.py tests/test_file_knowledge.py
git commit -m "feat: extract evidence-bound semantics with OpenAI"
```

### Task 5: Graph projection and policy-protected API

**Files:**
- Modify: `src/sdp/file_ontology.py`
- Modify: `src/sdp/api.py`
- Modify: `tests/test_file_knowledge.py`
- Modify: `tests/test_graph_engine.py`

**Interfaces:**
- Produces: `upsert_file_asset()`, `get_file_asset()`, four `/file-assets` API routes.
- Consumes: existing `GraphStore`, `policy.evaluate`, graph traversal, semantic search.

- [ ] **Step 1: Write failing graph/API tests**

```python
def test_upsert_file_asset_merges_same_content_distributions_and_projects_assertions():
    store = InMemoryGraphStore()
    first = sample_asset(locator="file:///a.xlsx")
    second = sample_asset(locator="file:///copy.xlsx")
    upsert_file_asset(store, first)
    merged = upsert_file_asset(store, second)
    assert len(merged.distributions) == 2
    graph = store.traverse(first.asset_id, direction="out", max_depth=1)
    assert {edge["edge_type"] for edge in graph["edges"]} >= {"DISTRIBUTION", "HAS_TOPIC"}

def test_file_asset_api_requires_policy_and_redacts_jsonld_locator(client):
    assert client.post("/file-assets", json=sample_request(actor="analyst")).status_code == 403
    created = client.post("/file-assets", json=sample_request(actor="admin"))
    assert created.status_code == 200
    exported = client.get(f"/file-assets/{created.json()['asset_id']}/jsonld", params={"actor": "analyst"})
    assert "dcat:accessURL" not in exported.text
```

- [ ] **Step 2: Run tests and confirm route/function failures**

Run: `$env:PYTHONPATH='src'; py -m pytest tests/test_file_knowledge.py tests/test_graph_engine.py -k file_asset -q`

Expected: FAIL because projection and routes do not exist.

- [ ] **Step 3: Implement graph projection and retrieval**

`upsert_file_asset(store, asset)` validates first, merges existing distributions by id, writes the file node with serializable metadata only, writes distribution and concept/reference nodes, and creates allowlisted uppercase edge labels with `confidence`, `review_status`, and evidence-reference properties. Embedding text is only title plus target labels. `get_file_asset()` reconstructs the Pydantic model from the file node.

- [ ] **Step 4: Add routes with existing authorization**

`POST /file-assets` calls `_authorize_graph_write`; GET/detail/JSON-LD/validate call `_authorize_graph_read`. Locator inclusion requires `include_locations=true` and an admin `create` policy check. Convert `KeyError` to 404, validation `ValueError` to 400, and authorization failure to 403.

Run: `$env:PYTHONPATH='src'; py -m pytest tests/test_file_knowledge.py tests/test_graph_engine.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/sdp/file_ontology.py src/sdp/api.py tests/test_file_knowledge.py tests/test_graph_engine.py
git commit -m "feat: project file knowledge into graph API"
```

### Task 6: Local pilot runner and Hyosung VOC preflight

**Files:**
- Create: `src/sdp/file_pilot.py`
- Modify: `tests/test_file_knowledge.py`

**Interfaces:**
- Produces: `run_local_pilot()`, `python -m sdp.file_pilot`.
- Consumes: filesystem reader, document extraction, optional OpenAI extractor, graph projection, JSON-LD export.

- [ ] **Step 1: Write a failing end-to-end local runner test**

```python
def test_local_pilot_deduplicates_content_and_writes_no_raw_text(tmp_path):
    root = tmp_path / "input"
    root.mkdir()
    (root / "효성중공업 VOC.txt").write_text("C-Cube PoC", encoding="utf-8")
    (root / "중공업VOC copy.txt").write_text("C-Cube PoC", encoding="utf-8")
    output = tmp_path / "manifest.json"
    summary = run_local_pilot(root, output, name_pattern=r"효성중공업|중공업VOC", extractor=FakeExtractor())
    assert summary["files"] == 2 and summary["assets"] == 1 and summary["distributions"] == 2
    assert "C-Cube PoC" not in output.read_text(encoding="utf-8")
```

- [ ] **Step 2: Run the test and confirm failure**

Run: `$env:PYTHONPATH='src'; py -m pytest tests/test_file_knowledge.py -k local_pilot -q`

Expected: FAIL because the runner does not exist.

- [ ] **Step 3: Implement the runner and CLI**

`run_local_pilot()` groups by SHA-256, merges distributions, extracts/chunks each unique asset once, applies the optional extractor, validates and projects into an `InMemoryGraphStore`, and writes a UTF-8 JSON manifest containing summary, asset JSON-LD with locators, per-file status, and no raw text/quote/API response. CLI arguments are `--root`, `--output`, `--name-regex`, `--model`, `--max-files`, and `--no-llm`; with LLM enabled it obtains the API key via `getpass.getpass()` and an `EphemeralCredentialRegistry`, never a CLI argument or environment variable.

- [ ] **Step 4: Run tests and the 12-file no-LLM preflight**

Run:

```powershell
$env:PYTHONPATH='src'
py -m pytest tests/test_file_knowledge.py -k local_pilot -q
py -m sdp.file_pilot --root 'D:\SynologyDrive\업무자료\Download_정리_2026-07-15\01_문서' --output 'C:\Users\Seongho Bae\Documents\Codex\2026-07-15\plugin-computer-use-openai-bundled-ponytail\outputs\hyosung-voc-file-index.json' --name-regex '효성중공업|중공업VOC' --max-files 12 --no-llm
```

Expected: 12 files, 10 assets, 12 distributions; DOCX/XLSX/PPTX/PDF extraction statuses are `extracted` or explicitly `needs_ocr`.

- [ ] **Step 5: Commit**

```bash
git add src/sdp/file_pilot.py tests/test_file_knowledge.py
git commit -m "feat: add safe local semantic file pilot"
```

### Task 7: Documentation, Codegraph, full verification, and live pilot

**Files:**
- Modify: `README.md`
- Modify: `docs/implementation-compliance.md`
- Modify: `docs/superpowers/plans/2026-07-21-semantic-file-ontology.md`
- Local-only output: `C:/Users/Seongho Bae/Documents/Codex/2026-07-15/plugin-computer-use-openai-bundled-ponytail/outputs/hyosung-voc-file-index.json`

**Interfaces:**
- Produces: documented API/CLI, verified local manifest, current Codegraph index.
- Consumes: all earlier tasks.

- [ ] **Step 1: Document exact operation and security boundary**

Add the four API endpoints, standards profile paths, supported providers/formats, injected-client pattern, interactive key prompt, local pilot command, output privacy warning, and exclusions to README. Add requirement-to-proof rows and test names to the implementation compliance matrix.

- [ ] **Step 2: Run full tests and smoke**

Run:

```powershell
$env:PYTHONPATH='src'
py -m pytest -q
py -m sdp.demo_smoke
git diff --check
```

Expected: pytest passes with only declared integration skips; demo smoke exits 0; diff check is clean.

- [ ] **Step 3: Sync Codegraph and inspect impact**

Run:

```powershell
codegraph sync
codegraph status
codegraph affected src/sdp/file_ontology.py src/sdp/storage_readers.py src/sdp/document_semantics.py src/sdp/file_pilot.py src/sdp/api.py
```

Expected: index is current and affected tests include the new file knowledge tests plus API/graph tests.

- [ ] **Step 4: Run the live OpenAI pilot after secure key entry**

Run the Task 6 pilot command without `--no-llm`, enter the project-scoped key only at the hidden prompt, and verify the output reports proposed assertions with evidence hashes/offsets and no raw chunks. If no key is available, stop at the verified no-LLM manifest and request secure local entry; do not weaken credential handling.

- [ ] **Step 5: Commit final docs and verification evidence**

```bash
git add README.md docs/implementation-compliance.md docs/superpowers/plans/2026-07-21-semantic-file-ontology.md
git commit -m "docs: document semantic file catalog pilot"
git status --short
```

Expected: clean worktree.

## Self-Review

- Spec coverage: standards profile, provider-neutral identity/location split, four providers, safe content extraction, OpenAI evidence binding, SHACL-compatible validation, graph/API reuse, privacy, and 12-file pilot each have a task.
- Placeholder scan: no TBD/TODO/future implementation placeholder is used; exclusions are explicit scope decisions.
- Type consistency: Tasks 2–7 consume the exact `StorageDistribution`, `SemanticAssertion`, `FileAsset`, `ObjectRef`, `TextChunk`, and extractor names produced in earlier tasks.
- Dependency scope: only pypdf is added because the approved pilot includes two PDFs; cloud SDKs and the OpenAI SDK remain injected/stdlib.
