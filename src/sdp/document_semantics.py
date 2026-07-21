"""Ephemeral document text extraction and semantic chunking."""

from __future__ import annotations

import hashlib
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from io import BytesIO
from pathlib import PurePath
from typing import Literal
from zipfile import BadZipFile, ZipFile

from pypdf import PdfReader
from pypdf.errors import PdfReadError


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
