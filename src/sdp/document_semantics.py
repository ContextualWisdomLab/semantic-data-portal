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


OpenAITransport = Callable[[Request, int], dict[str, Any]]

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


def _openai_http_transport(request: Request, timeout: int) -> dict[str, Any]:
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise RuntimeError(f"OpenAI request failed with HTTP {exc.code}") from None
    except URLError:
        raise RuntimeError("OpenAI request could not reach the service") from None


def _response_output_text(response: dict[str, Any]) -> str:
    if response.get("status") != "completed":
        raise ValueError("OpenAI response did not complete")
    for output in response.get("output", []):
        if output.get("type") != "message":
            continue
        for content in output.get("content", []):
            if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                return content["text"]
    raise ValueError("OpenAI response contains no output text")


class OpenAISemanticExtractor:
    def __init__(
        self,
        credentials: CredentialRegistry,
        *,
        transport: OpenAITransport = _openai_http_transport,
        model: str = "gpt-5-mini-2025-08-07",
        timeout: int = 60,
    ) -> None:
        self.credentials = credentials
        self.transport = transport
        self.model = model
        self.timeout = timeout

    def _payload(self, filename: str, chunk: TextChunk) -> dict[str, Any]:
        return {
            "model": self.model,
            "store": False,
            "instructions": (
                "Extract only explicitly evidenced business semantics from the document chunk. "
                "Return Korean labels when the source uses Korean. Do not infer facts absent from the text."
            ),
            "input": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": f"Filename: {filename}\nDocument chunk:\n{chunk.text}",
                        }
                    ],
                }
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "cwl_file_semantics",
                    "strict": True,
                    "schema": _SEMANTIC_SCHEMA,
                }
            },
            "max_output_tokens": 1_500,
        }

    def extract(self, filename: str, chunks: list[TextChunk]) -> list[SemanticAssertion]:
        api_key = self.credentials.get_credential("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OpenAI credential is unavailable")

        merged: dict[tuple[str, str, str], SemanticAssertion] = {}
        for chunk in chunks:
            encoded_payload = json.dumps(
                self._payload(filename, chunk), ensure_ascii=False
            ).encode("utf-8")
            request = Request(
                "https://api.openai.com/v1/responses",
                data=encoded_payload,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            response = self.transport(request, self.timeout)
            try:
                result = json.loads(_response_output_text(response))
                candidates = result["assertions"]
            except (KeyError, TypeError, json.JSONDecodeError) as exc:
                raise ValueError("OpenAI semantic output is malformed") from exc
            if not isinstance(candidates, list):
                raise ValueError("OpenAI semantic output assertions must be a list")

            for candidate in candidates:
                if not isinstance(candidate, dict):
                    raise ValueError("OpenAI semantic assertion must be an object")
                quote_text = candidate.get("evidence_quote")
                if not isinstance(quote_text, str):
                    raise ValueError("OpenAI semantic assertion has no evidence quote")
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
                    )
                except (KeyError, TypeError, ValueError) as exc:
                    raise ValueError("OpenAI semantic assertion is invalid") from exc
                key = (
                    assertion.relation,
                    assertion.target_kind,
                    assertion.target_label.strip().casefold(),
                )
                if key not in merged or assertion.confidence > merged[key].confidence:
                    merged[key] = assertion
        return list(merged.values())
