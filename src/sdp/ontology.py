from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from .catalog import list_datasets, mapping_candidates


def _build_index() -> Dict[str, List[str]]:
    index: Dict[str, List[str]] = {}
    for dataset in list_datasets():
        for concept in dataset.terms:
            index.setdefault(concept, []).append(dataset.id)
    return index


_INDEX = _build_index()


@dataclass(frozen=True)
class Resolution:
    term: str
    score: float
    uri: str
    aliases: List[str]


def resolve_terms(text: str) -> list[Resolution]:
    text = text.strip()
    if not text:
        return []
    resolved: list[Resolution] = []

    for concept, dataset_ids in _INDEX.items():
        score = 0.0
        aliases: list[str] = []

        if concept in text:
            score += 1.0
            aliases.append(concept)
        for did in dataset_ids:
            ds = next(ds for ds in list_datasets() if ds.id == did)
            for term in ds.terms:
                if term in text:
                    score += 0.5
                    aliases.append(term)
            for dataset_term in mapping_candidates(ds, concept):
                if dataset_term in text:
                    score += 0.3

        if score > 0.0:
            uri = f"https://data.example.org/term/{concept.replace(' ', '-')}"
            resolved.append(Resolution(term=concept, score=min(score, 1.0), uri=uri, aliases=sorted(set(aliases))))

    resolved.sort(key=lambda row: row.score, reverse=True)
    return resolved


def concept_assets(concept: str) -> Dict[str, Any]:
    datasets = _INDEX.get(concept, [])
    return {"concept": concept, "dataset_ids": datasets, "count": len(datasets)}

