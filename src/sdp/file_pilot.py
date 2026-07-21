"""Read-only local runner for the semantic file ontology pilot."""

from __future__ import annotations

import argparse
import getpass
import hashlib
import json
from pathlib import Path
from typing import Protocol

from .config import get_app_config
from .document_semantics import (
    ContextualOrchestratorClient,
    EphemeralCredentialRegistry,
    TextChunk,
    chunk_text,
    extract_document_text,
)
from .file_ontology import FileAsset, SemanticAssertion, file_asset_jsonld, upsert_file_asset
from .graph_store import GraphStore, InMemoryGraphStore
from .storage_readers import FilesystemReader


class PilotExtractor(Protocol):
    def extract(self, filename: str, chunks: list[TextChunk]) -> list[SemanticAssertion]: ...

    def embed_one(self, text: str) -> list[float]: ...


def run_local_pilot(
    root: str | Path,
    output: str | Path,
    *,
    name_pattern: str,
    extractor: PilotExtractor | None = None,
    store: GraphStore | None = None,
    max_files: int = 100,
    max_bytes: int = 20 * 1024 * 1024,
) -> dict[str, int]:
    """Index matching files without moving, deleting, or persisting source text."""

    if max_files <= 0 or max_bytes <= 0:
        raise ValueError("pilot limits must be positive")
    reader = FilesystemReader(root)
    refs = sorted(
        reader.list(name_pattern=name_pattern),
        key=lambda ref: ref.object_key.casefold(),
    )[:max_files]
    assets: dict[str, FileAsset] = {}
    asset_statuses: dict[str, str] = {}
    file_records: list[dict[str, str]] = []

    for ref in refs:
        try:
            data = reader.read(ref, max_bytes=max_bytes)
        except ValueError as exc:
            status = "too_large" if "maximum size" in str(exc) else "read_failed"
            file_records.append(
                {"name": ref.name, "distribution_id": ref.distribution.id, "status": status}
            )
            continue
        except OSError:
            file_records.append(
                {"name": ref.name, "distribution_id": ref.distribution.id, "status": "read_failed"}
            )
            continue

        digest = hashlib.sha256(data).hexdigest()
        asset = assets.get(digest)
        if asset is None:
            document = extract_document_text(ref.name, data)
            assertions: list[SemanticAssertion] = []
            status = document.status
            if document.status == "extracted" and extractor is not None:
                try:
                    assertions = extractor.extract(ref.name, chunk_text(document.text))
                except (RuntimeError, ValueError):
                    status = "semantic_failed"
            asset = FileAsset(
                sha256=digest,
                title=Path(ref.name).stem,
                media_type=document.media_type,
                byte_size=len(data),
                modified_at=ref.modified_at,
                distributions=[ref.distribution],
                assertions=assertions,
            )
            assets[digest] = asset
            asset_statuses[digest] = status
        else:
            distributions = {item.id: item for item in asset.distributions}
            distributions[ref.distribution.id] = ref.distribution
            modified = max(
                filter(None, (asset.modified_at, ref.modified_at)),
                default=None,
            )
            asset = asset.model_copy(
                update={"distributions": list(distributions.values()), "modified_at": modified}
            )
            assets[digest] = asset

        file_records.append(
            {
                "name": ref.name,
                "asset_id": asset.asset_id,
                "distribution_id": ref.distribution.id,
                "status": asset_statuses[digest],
            }
        )

    graph = store or InMemoryGraphStore(
        embedder=extractor.embed_one if extractor is not None else None
    )
    indexed = [upsert_file_asset(graph, asset) for asset in assets.values()]
    summary = {
        "files": len(refs),
        "assets": len(indexed),
        "distributions": sum(len(asset.distributions) for asset in indexed),
        "assertions": sum(len(asset.assertions) for asset in indexed),
    }
    manifest = {
        "profile": "CWL File Knowledge Profile 0.1",
        "summary": summary,
        "assets": [
            file_asset_jsonld(asset, include_locations=True)
            for asset in sorted(indexed, key=lambda item: item.asset_id)
        ],
        "files": file_records,
    }
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--name-regex", required=True)
    parser.add_argument("--max-files", type=int, default=100)
    parser.add_argument("--orchestrator-url")
    parser.add_argument("--semantic-model")
    parser.add_argument("--embedding-model")
    parser.add_argument("--no-llm", action="store_true")
    args = parser.parse_args()

    extractor = None
    if not args.no_llm:
        config = get_app_config()
        orchestrator_url = args.orchestrator_url or config.orchestrator_base_url
        if not orchestrator_url:
            parser.error(
                "--orchestrator-url or KV orchestrator_base_url is required unless --no-llm is used"
            )
        token = getpass.getpass("contextual-orchestrator inference token: ")
        extractor = ContextualOrchestratorClient(
            EphemeralCredentialRegistry({"CONTEXTUAL_ORCHESTRATOR_TOKEN": token}),
            base_url=orchestrator_url,
            semantic_model=args.semantic_model or config.semantic_model,
            embedding_model=args.embedding_model or config.embedding_model,
            embedding_dimensions=config.embedding_dimension,
        )

    summary = run_local_pilot(
        args.root,
        args.output,
        name_pattern=args.name_regex,
        extractor=extractor,
        max_files=args.max_files,
    )
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
