"""Read-only object readers for local and injected cloud storage clients."""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Protocol
from urllib.parse import quote, urlsplit

from .file_ontology import StorageDistribution, StorageProvider


def _stable_id(provider: str, locator: str) -> str:
    digest = hashlib.sha256(f"{provider}\0{locator}".encode("utf-8")).hexdigest()[:24]
    return f"{provider}-{digest}"


def _is_link_or_junction(path: Path) -> bool:
    is_junction = getattr(os.path, "isjunction", lambda _: False)
    return path.is_symlink() or bool(is_junction(path))


@dataclass(frozen=True)
class ObjectRef:
    name: str
    object_key: str
    size: int
    modified_at: datetime | None
    distribution: StorageDistribution


class ObjectReader(Protocol):
    def list(
        self, prefix: str = "", *, name_pattern: str | None = None
    ) -> Iterable[ObjectRef]: ...

    def read(self, ref: ObjectRef, *, max_bytes: int) -> bytes: ...


class FilesystemReader:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve(strict=True)
        if not self.root.is_dir():
            raise ValueError("filesystem root must be a directory")
        self.endpoint_id = f"filesystem-{hashlib.sha256(str(self.root).casefold().encode()).hexdigest()[:16]}"

    def _inside_root(self, path: Path) -> Path:
        resolved = path.resolve(strict=True)
        try:
            resolved.relative_to(self.root)
        except ValueError as exc:
            raise ValueError("path escapes configured filesystem root") from exc
        return resolved

    def list(
        self, prefix: str = "", *, name_pattern: str | None = None
    ) -> Iterable[ObjectRef]:
        start = self._inside_root(self.root / prefix)
        pattern = re.compile(name_pattern, re.IGNORECASE) if name_pattern else None
        for current, directories, filenames in os.walk(start, followlinks=False):
            current_path = Path(current)
            directories[:] = [
                name
                for name in directories
                if not _is_link_or_junction(current_path / name)
            ]
            for name in filenames:
                if name.startswith("~$") or (pattern and not pattern.search(name)):
                    continue
                source = current_path / name
                if _is_link_or_junction(source):
                    continue
                resolved = self._inside_root(source)
                stat = resolved.stat()
                locator = resolved.as_uri()
                relative = resolved.relative_to(self.root).as_posix()
                yield ObjectRef(
                    name=name,
                    object_key=relative,
                    size=stat.st_size,
                    modified_at=datetime.fromtimestamp(stat.st_mtime, timezone.utc),
                    distribution=StorageDistribution(
                        id=_stable_id("filesystem", locator),
                        provider="filesystem",
                        locator=locator,
                        endpoint_id=self.endpoint_id,
                    ),
                )

    def read(self, ref: ObjectRef, *, max_bytes: int) -> bytes:
        if ref.distribution.provider != "filesystem":
            raise ValueError("object reference does not belong to the filesystem reader")
        source = self._inside_root(self.root / Path(ref.object_key))
        if _is_link_or_junction(source):
            raise ValueError("symbolic links and junctions are not readable")
        if source.stat().st_size > max_bytes:
            raise ValueError("object exceeds maximum size")
        with source.open("rb") as handle:
            data = handle.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise ValueError("object exceeds maximum size")
        return data


class S3Reader:
    def __init__(
        self,
        client: Any,
        bucket: str,
        *,
        provider: StorageProvider = "s3",
        endpoint_url: str | None = None,
    ) -> None:
        if provider not in {"s3", "s3_compatible"}:
            raise ValueError("S3Reader provider must be s3 or s3_compatible")
        if provider == "s3_compatible" and not endpoint_url:
            raise ValueError("S3-compatible storage requires endpoint_url")
        self.client = client
        self.bucket = bucket
        self.provider = provider
        self.endpoint_url = endpoint_url.rstrip("/") if endpoint_url else None
        host = urlsplit(self.endpoint_url).netloc if self.endpoint_url else "aws"
        self.endpoint_id = f"{provider}-{host}"

    def _locator(self, key: str) -> str:
        encoded_key = quote(key, safe="/")
        if self.provider == "s3":
            return f"s3://{quote(self.bucket, safe='')}/{encoded_key}"
        return f"{self.endpoint_url}/{quote(self.bucket, safe='')}/{encoded_key}"

    def list(
        self, prefix: str = "", *, name_pattern: str | None = None
    ) -> Iterable[ObjectRef]:
        pattern = re.compile(name_pattern, re.IGNORECASE) if name_pattern else None
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            for item in page.get("Contents", []):
                key = str(item["Key"])
                name = key.rsplit("/", 1)[-1]
                if not name or name.startswith("~$") or (pattern and not pattern.search(name)):
                    continue
                locator = self._locator(key)
                etag = str(item.get("ETag", "")).strip('"') or None
                yield ObjectRef(
                    name=name,
                    object_key=key,
                    size=int(item.get("Size", 0)),
                    modified_at=item.get("LastModified"),
                    distribution=StorageDistribution(
                        id=_stable_id(self.provider, locator),
                        provider=self.provider,
                        locator=locator,
                        endpoint_id=self.endpoint_id,
                        bucket=self.bucket,
                        object_key=key,
                        etag=etag,
                    ),
                )

    def read(self, ref: ObjectRef, *, max_bytes: int) -> bytes:
        if ref.distribution.provider != self.provider:
            raise ValueError("object reference does not belong to this S3 reader")
        if ref.size > max_bytes:
            raise ValueError("object exceeds maximum size")
        request: dict[str, str] = {"Bucket": self.bucket, "Key": ref.object_key}
        if ref.distribution.version_id:
            request["VersionId"] = ref.distribution.version_id
        body = self.client.get_object(**request)["Body"]
        try:
            data = body.read(max_bytes + 1)
        finally:
            close = getattr(body, "close", None)
            if close:
                close()
        if len(data) > max_bytes:
            raise ValueError("object exceeds maximum size")
        return data


class AzureBlobReader:
    def __init__(self, container_client: Any) -> None:
        self.client = container_client
        self.container = str(container_client.container_name)
        self.container_url = str(container_client.url).rstrip("/")
        self.endpoint_id = f"azure-blob-{urlsplit(self.container_url).netloc}"

    def list(
        self, prefix: str = "", *, name_pattern: str | None = None
    ) -> Iterable[ObjectRef]:
        pattern = re.compile(name_pattern, re.IGNORECASE) if name_pattern else None
        for item in self.client.list_blobs(name_starts_with=prefix):
            key = str(item.name)
            name = key.rsplit("/", 1)[-1]
            if not name or name.startswith("~$") or (pattern and not pattern.search(name)):
                continue
            locator = f"{self.container_url}/{quote(key, safe='/')}"
            yield ObjectRef(
                name=name,
                object_key=key,
                size=int(item.size),
                modified_at=item.last_modified,
                distribution=StorageDistribution(
                    id=_stable_id("azure_blob", locator),
                    provider="azure_blob",
                    locator=locator,
                    endpoint_id=self.endpoint_id,
                    container=self.container,
                    object_key=key,
                    version_id=getattr(item, "version_id", None),
                    etag=str(item.etag).strip('"') if item.etag else None,
                ),
            )

    def read(self, ref: ObjectRef, *, max_bytes: int) -> bytes:
        if ref.distribution.provider != "azure_blob":
            raise ValueError("object reference does not belong to the Azure Blob reader")
        if ref.size > max_bytes:
            raise ValueError("object exceeds maximum size")
        kwargs = (
            {"version_id": ref.distribution.version_id}
            if ref.distribution.version_id
            else {}
        )
        downloader = self.client.get_blob_client(ref.object_key, **kwargs).download_blob(
            offset=0,
            length=max_bytes + 1,
        )
        data = downloader.readall()
        if len(data) > max_bytes:
            raise ValueError("object exceeds maximum size")
        return data
