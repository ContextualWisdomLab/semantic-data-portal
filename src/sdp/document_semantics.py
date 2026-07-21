"""Ephemeral document text extraction and semantic chunking."""

from __future__ import annotations

import hashlib
import json
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from io import BytesIO
from pathlib import PurePath
from typing import Any, Callable, Literal, Mapping, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from zipfile import BadZipFile, ZipFile

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from .file_ontology import SemanticAssertion


ExtractionStatus = Literal["extracted", "needs_ocr", "unsupported_format", "extraction_failed"]

_PLAIN_SUFFIXES = {".txt", ".md", ".csv", ".json", ".xml"}
_OPENXML_ROOTS = {
    ".docx": ("word/",),
    ".pptx": ("ppt/slides/",),
    ".xlsx": ("xl/sharedStrings.xml", "xl/worksheets/"),
}
_MEDIA_TYPES = {
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".csv": "text/csv",
    ".json": "application/json",
    ".xml": "application/xml",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".pdf": "application/pdf",
}


@dataclass(frozen=True)
class DocumentText:
    status: ExtractionStatus
    text: str
    media_type: str
    error: str | None = None


@dataclass(frozen=True)
class TextChunk:
    text: str
    start: int
    end: int
    sha256: str


class CredentialRegistry(Protocol):
    def get_credential(self, name: str) -> str | None: ...


class EphemeralCredentialRegistry:
    """Process-local credentials supplied by a trusted bootstrap caller."""

    def __init__(self, values: Mapping[str, str]) -> None:
        self._values = dict(values)

    def get_credential(self, name: str) -> str | None:
        return self._values.get(name)

    def __repr__(self) -> str:
        return f"{type(self).__name__}(names={sorted(self._values)})"


def _decode_text(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-16", "cp949"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _xml_text(xml: bytes) -> list[str]:
    root = ET.fromstring(xml)
    return [
        element.text.strip()
        for element in root.iter()
        if element.tag.rsplit("}", 1)[-1] == "t" and element.text and element.text.strip()
    ]


def _openxml_text(suffix: str, data: bytes) -> str:
    roots = _OPENXML_ROOTS[suffix]
    parts: list[str] = []
    with ZipFile(BytesIO(data)) as archive:
        for name in sorted(archive.namelist()):
            if not name.endswith(".xml") or not any(
                name == root or name.startswith(root) for root in roots
            ):
                continue
            parts.extend(_xml_text(archive.read(name)))
    return "\n".join(parts)


def _pdf_text(data: bytes) -> str:
    reader = PdfReader(BytesIO(data), strict=False)
    return "\n".join(filter(None, (page.extract_text() for page in reader.pages)))


def extract_document_text(filename: str, data: bytes) -> DocumentText:
    """Extract text without retaining the source bytes or writing temporary files."""

    suffix = PurePath(filename).suffix.lower()
    media_type = _MEDIA_TYPES.get(suffix, "application/octet-stream")
    if suffix not in _PLAIN_SUFFIXES | set(_OPENXML_ROOTS) | {".pdf"}:
        return DocumentText("unsupported_format", "", media_type)
    try:
        if suffix in _PLAIN_SUFFIXES:
            text = _decode_text(data)
        elif suffix in _OPENXML_ROOTS:
            text = _openxml_text(suffix, data)
        else:
            text = _pdf_text(data)
    except (BadZipFile, ET.ParseError, PdfReadError, ValueError, TypeError) as exc:
        return DocumentText("extraction_failed", "", media_type, type(exc).__name__)

    normalized = "\n".join(line.strip() for line in text.splitlines() if line.strip())
    return DocumentText("extracted" if normalized else "needs_ocr", normalized, media_type)


def chunk_text(
    text: str,
    *,
    max_chars: int = 6_000,
    overlap: int = 300,
    max_total_chars: int = 24_000,
) -> list[TextChunk]:
    """Create bounded, deterministic chunks whose hashes can serve as evidence refs."""

    if max_chars <= 0 or max_total_chars <= 0:
        raise ValueError("chunk limits must be positive")
    if overlap < 0 or overlap >= max_chars:
        raise ValueError("overlap must be non-negative and smaller than max_chars")
    normalized = " ".join(text.split())[:max_total_chars]
    chunks: list[TextChunk] = []
    start = 0
    while start < len(normalized):
        end = min(start + max_chars, len(normalized))
        value = normalized[start:end]
        chunks.append(
            TextChunk(
                text=value,
                start=start,
                end=end,
                sha256=hashlib.sha256(value.encode("utf-8")).hexdigest(),
            )
        )
        if end == len(normalized):
            break
        start = end - overlap
    return chunks


OrchestratorTransport = Callable[[Request, int], dict[str, Any]]

_SEMANTIC_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "assertions": {
            "type": "array",
            "maxItems": 20,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "relation": {
                        "type": "string",
                        "enum": [
                            "belongsToProject",
                            "usesSystem",
                            "hasWorkPhase",
                            "hasArtifactType",
                            "hasTopic",
                            "wasDerivedFrom",
                            "previousVersion",
                        ],
                    },
                    "target_kind": {
                        "type": "string",
                        "enum": [
                            "business_project",
                            "system",
                            "work_phase",
                            "artifact_type",
                            "topic",
                            "file_asset",
                        ],
                    },
                    "target_label": {"type": "string", "minLength": 1, "maxLength": 200},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "evidence_quote": {"type": "string", "minLength": 1, "maxLength": 240},
                },
                "required": [
                    "relation",
                    "target_kind",
                    "target_label",
                    "confidence",
                    "evidence_quote",
                ],
            },
        }
    },
    "required": ["assertions"],
}


def _orchestrator_http_transport(request: Request, timeout: int) -> dict[str, Any]:
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise RuntimeError(f"orchestrator request failed with HTTP {exc.code}") from None
    except URLError:
        raise RuntimeError("orchestrator request could not reach the service") from None


def _chat_completion_content(response: dict[str, Any]) -> str:
    try:
        content = response["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError("orchestrator response contains no completion") from exc
    if not isinstance(content, str):
        raise ValueError("orchestrator completion content must be text")
    return content


class ContextualOrchestratorClient:
    """Authenticated LLM and embedding client for contextual-orchestrator."""

    def __init__(
        self,
        credentials: CredentialRegistry,
        *,
        base_url: str,
        transport: OrchestratorTransport = _orchestrator_http_transport,
        semantic_model: str = "gpt-5-mini-2025-08-07",
        embedding_model: str = "text-embedding-3-small",
        timeout: int = 60,
    ) -> None:
        parsed = urlsplit(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("orchestrator base URL must be absolute HTTP(S)")
        if parsed.query or parsed.fragment:
            raise ValueError("orchestrator base URL must not contain query or fragment")
        self.credentials = credentials
        self.base_url = base_url.rstrip("/")
        self.transport = transport
        self.semantic_model = semantic_model
        self.embedding_model = embedding_model
        self.timeout = timeout

    def _payload(self, filename: str, chunk: TextChunk) -> dict[str, Any]:
        return {
            "model": self.semantic_model,
            "store": False,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Extract only explicitly evidenced business semantics from the document chunk. "
                        "Return Korean labels when the source uses Korean. Do not infer facts absent from the text."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Filename: {filename}\nDocument chunk:\n{chunk.text}",
                },
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "cwl_file_semantics",
                    "strict": True,
                    "schema": _SEMANTIC_SCHEMA,
                },
            },
            "max_completion_tokens": 1_500,
        }

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        token = self.credentials.get_credential("CONTEXTUAL_ORCHESTRATOR_TOKEN")
        if not token:
            raise ValueError("orchestrator credential is unavailable")
        request = Request(
            f"{self.base_url}{path}",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        return self.transport(request, self.timeout)

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts or any(not isinstance(text, str) for text in texts):
            raise ValueError("embedding input must be a non-empty list of strings")
        response = self._post(
            "/v1/embeddings",
            {
                "model": self.embedding_model,
                "input": texts,
                "metadata": {"service": "semantic-data-portal"},
            },
        )
        data = response.get("data")
        if not isinstance(data, list) or len(data) != len(texts):
            raise ValueError("orchestrator embedding response is malformed")
        indexed: dict[int, list[float]] = {}
        for item in data:
            if not isinstance(item, dict) or not isinstance(item.get("index"), int):
                raise ValueError("orchestrator embedding item is malformed")
            vector = item.get("embedding")
            if not isinstance(vector, list) or not vector:
                raise ValueError("orchestrator embedding vector is missing")
            try:
                indexed[item["index"]] = [float(component) for component in vector]
            except (TypeError, ValueError) as exc:
                raise ValueError("orchestrator embedding vector is malformed") from exc
        if set(indexed) != set(range(len(texts))):
            raise ValueError("orchestrator embedding indices are malformed")
        return [indexed[index] for index in range(len(texts))]

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]

    def extract(self, filename: str, chunks: list[TextChunk]) -> list[SemanticAssertion]:
        merged: dict[tuple[str, str, str], SemanticAssertion] = {}
        for chunk in chunks:
            response = self._post(
                "/v1/chat/completions", self._payload(filename, chunk)
            )
            try:
                result = json.loads(_chat_completion_content(response))
                candidates = result["assertions"]
            except (KeyError, TypeError, json.JSONDecodeError) as exc:
                raise ValueError("orchestrator semantic output is malformed") from exc
            if not isinstance(candidates, list):
                raise ValueError("orchestrator semantic output assertions must be a list")

            for candidate in candidates:
                if not isinstance(candidate, dict):
                    raise ValueError("orchestrator semantic assertion must be an object")
                quote_text = candidate.get("evidence_quote")
                if not isinstance(quote_text, str):
                    raise ValueError("orchestrator semantic assertion has no evidence quote")
                local_start = chunk.text.find(quote_text)
                if local_start < 0:
                    continue
                try:
                    assertion = SemanticAssertion(
                        relation=candidate["relation"],
                        target_kind=candidate["target_kind"],
                        target_label=candidate["target_label"],
                        confidence=candidate["confidence"],
                        evidence_chunk_sha256=chunk.sha256,
                        evidence_start=chunk.start + local_start,
                        evidence_end=chunk.start + local_start + len(quote_text),
                        method="contextual-orchestrator",
                    )
                except (KeyError, TypeError, ValueError) as exc:
                    raise ValueError("orchestrator semantic assertion is invalid") from exc
                key = (
                    assertion.relation,
                    assertion.target_kind,
                    assertion.target_label.strip().casefold(),
                )
                if key not in merged or assertion.confidence > merged[key].confidence:
                    merged[key] = assertion
        return list(merged.values())
