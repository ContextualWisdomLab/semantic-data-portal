from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List
from uuid import uuid4

from .catalog import list_datasets, mapping_candidates
from .domain import OntologyPatch


_CONCEPT_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    "고객": {
        "aliases": ["customer", "클라이언트", "이용자", "회원"],
        "broader": None,
        "narrower": ["활성 고객", "이탈 고객"],
        "related": ["구매", "거래", "회원가입"],
        "definition": "고객은 특정 조직의 제품 또는 서비스를 이용하는 대상 엔티티 집합이다.",
        "multilingual": ["customer", "client"],
    },
    "활성 고객": {
        "aliases": ["액티브 고객", "유효 고객", "활성 유저"],
        "broader": "고객",
        "narrower": [],
        "related": ["이탈 고객", "휴면 고객", "구매자"],
        "definition": "최근 활성이 확인된 고객의 집합이다.",
        "multilingual": ["active customer"],
    },
    "이탈": {
        "aliases": ["탈퇴", "이탈률", "휴면"],
        "broader": None,
        "narrower": ["이탈 고객"],
        "related": ["활성 고객", "재구매"],
        "definition": "서비스 지속 이용이 끝난 고객 상태 및 변화 패턴의 의미 단위이다.",
        "multilingual": ["churn", "churned"],
    },
    "이탈 고객": {
        "aliases": ["탈퇴 고객", "churn 고객", "휴면 고객"],
        "broader": "고객",
        "narrower": [],
        "related": ["활성 고객", "가입자"],
        "definition": "최근 장기 미접속 또는 해지로 분류된 고객 세그먼트이다.",
        "multilingual": ["churned customer"],
    },
    "매출": {
        "aliases": ["수익", "판매", "매출액"],
        "broader": None,
        "narrower": ["매출 성장", "매출 채널별 집계"],
        "related": ["구매", "가격"],
        "definition": "비즈니스의 경제적 산출 결과를 나타내는 지표군이다.",
        "multilingual": ["revenue", "sales"],
    },
}


def _build_index() -> Dict[str, List[str]]:
    index: Dict[str, List[str]] = {}
    for dataset in list_datasets():
        for concept in dataset.terms:
            index.setdefault(concept, []).append(dataset.id)
    return index


def _normalize_term(value: str) -> str:
    return value.strip().replace("_", " ").lower()


_INDEX = _build_index()
_ONTOLOGY_PATCHES: list[OntologyPatch] = []
_ALIAS_TO_CANONICAL: Dict[str, str] = {}
for base_concept in _CONCEPT_DEFINITIONS:
    _ALIAS_TO_CANONICAL[_normalize_term(base_concept)] = base_concept
    for alias in _CONCEPT_DEFINITIONS[base_concept]["aliases"]:
        _ALIAS_TO_CANONICAL[_normalize_term(alias)] = base_concept
    for alias in _CONCEPT_DEFINITIONS[base_concept]["multilingual"]:
        _ALIAS_TO_CANONICAL[_normalize_term(alias)] = base_concept


@dataclass(frozen=True)
class ConceptTerm:
    concept: str
    aliases: List[str]
    broader: str | None
    narrower: List[str]
    related: List[str]
    definition: str
    multilingual: List[str]


@dataclass(frozen=True)
class Resolution:
    term: str
    score: float
    uri: str
    aliases: List[str]


def _canonicalize_concept(concept: str) -> str:
    return _ALIAS_TO_CANONICAL.get(_normalize_term(concept), concept)


def list_concepts() -> List[str]:
    return sorted(_CONCEPT_DEFINITIONS.keys())


def search_concepts(q: str) -> List[ConceptTerm]:
    q = q.strip().lower()
    if not q:
        return []

    found: dict[str, ConceptTerm] = {}
    for concept, metadata in _CONCEPT_DEFINITIONS.items():
        aliases = [concept] + list(metadata.get("aliases", [])) + list(metadata.get("multilingual", []))
        if q == _normalize_term(concept) or any(_normalize_term(alias) in q for alias in aliases):
            found[concept] = _to_concept_payload(concept)
            continue
        if concept in q:
            found[concept] = _to_concept_payload(concept)

    return list(found.values())


def _to_concept_payload(concept: str) -> ConceptTerm:
    metadata = _CONCEPT_DEFINITIONS[concept]
    return ConceptTerm(
        concept=concept,
        aliases=[concept] + list(metadata.get("aliases", [])),
        broader=metadata.get("broader"),
        narrower=list(metadata.get("narrower", [])),
        related=list(metadata.get("related", [])),
        definition=str(metadata.get("definition", "")),
        multilingual=list(metadata.get("multilingual", [])),
    )


def concept_graph(concept: str) -> Dict[str, Any]:
    canonical = _canonicalize_concept(concept)
    if canonical in _CONCEPT_DEFINITIONS:
        return asdict(_to_concept_payload(canonical)) | {"canonical": canonical}
    return {"canonical": concept, "not_found": True, "aliases": []}


def resolve_terms(text: str) -> list[Resolution]:
    text = text.strip()
    if not text:
        return []

    resolved: list[Resolution] = []
    for concept, dataset_ids in _INDEX.items():
        dataset = dataset_ids[0] if dataset_ids else ""
        score = 0.0
        aliases: list[str] = []

        definition = _CONCEPT_DEFINITIONS.get(concept, {})
        candidate_aliases = [concept] + list(definition.get("aliases", []))

        if concept in text:
            score += 1.0
            aliases.append(concept)
        for alias in candidate_aliases:
            if alias in text and alias not in aliases:
                score += 0.3
                aliases.append(alias)

        if dataset:
            ds = next(ds for ds in list_datasets() if ds.id == dataset)
            for term in ds.terms:
                if term in text:
                    score += 0.5
                    aliases.append(term)
            for dataset_term in mapping_candidates(ds, concept):
                if dataset_term in text:
                    score += 0.3

        if score > 0:
            resolved.append(
                Resolution(
                    term=concept,
                    score=min(score, 1.0),
                    uri=f"https://data.example.org/term/{concept.replace(' ', '-')}",
                    aliases=sorted(set(aliases)),
                )
            )

    for candidate in search_concepts(text):
        if not any(item.term == candidate.concept for item in resolved):
            resolved.append(
                Resolution(
                    term=candidate.concept,
                    score=0.55,
                    uri=f"https://data.example.org/term/{candidate.concept.replace(' ', '-')}",
                    aliases=sorted(candidate.aliases),
                )
            )

    resolved.sort(key=lambda row: row.score, reverse=True)
    return resolved


def concept_assets(concept: str) -> Dict[str, Any]:
    canonical = _canonicalize_concept(concept)
    datasets = _INDEX.get(canonical, [])
    metadata = _CONCEPT_DEFINITIONS.get(canonical, {})
    return {
        "concept": canonical,
        "graph": concept_graph(canonical),
        "dataset_ids": datasets,
        "count": len(datasets),
        "aliases": [canonical] + list(metadata.get("aliases", [])),
    }


def propose_patch(concept: str, suggestion: str, *, requestor: str = "anonymous") -> dict[str, Any]:
    patch = OntologyPatch(
        id=str(uuid4()),
        concept=concept.strip() or "unknown",
        suggestion=suggestion.strip(),
        requestor=requestor,
        confidence=min(max(len(suggestion) / 220.0, 0.3), 0.95),
    )
    _ONTOLOGY_PATCHES.append(patch)
    return patch.model_dump()


def list_patches(status: str | None = None) -> list[dict[str, Any]]:
    patches = [patch.model_dump() for patch in _ONTOLOGY_PATCHES]
    if status:
        return [patch for patch in patches if patch["status"] == status]
    return patches


def review_patch(
    patch_id: str,
    decision: str,
    *,
    reviewer: str = "anonymous",
    comment: str = "",
) -> dict[str, Any]:
    normalized = decision.strip().lower()
    if normalized not in {"approve", "reject"}:
        raise ValueError("decision must be approve or reject")

    for idx, patch in enumerate(_ONTOLOGY_PATCHES):
        if patch.id != patch_id:
            continue
        if patch.status != "proposed":
            raise ValueError("patch is not in proposed state")
        patch.reviewed_by = reviewer
        patch.reviewed_at = datetime.now(timezone.utc)
        patch.review_comment = comment
        patch.status = "approved" if normalized == "approve" else "rejected"
        _ONTOLOGY_PATCHES[idx] = patch
        return patch.model_dump()
    raise KeyError("patch not found")
