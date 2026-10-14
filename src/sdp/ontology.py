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
# Bounds on the process-lifetime proposal queue; see propose_patch.
MAX_ONTOLOGY_PATCHES = 500
MAX_ONTOLOGY_PATCH_FIELD = 2000
_ALIAS_TO_CANONICAL: Dict[str, str] = {}
for base_concept in _CONCEPT_DEFINITIONS:
    _ALIAS_TO_CANONICAL[_normalize_term(base_concept)] = base_concept
    for alias in _CONCEPT_DEFINITIONS[base_concept]["aliases"]:
        _ALIAS_TO_CANONICAL[_normalize_term(alias)] = base_concept
    for alias in _CONCEPT_DEFINITIONS[base_concept]["multilingual"]:
        _ALIAS_TO_CANONICAL[_normalize_term(alias)] = base_concept


MAX_REGISTERED_CONCEPTS = 500


def register_concept(
    concept: str,
    *,
    definition: str = "",
    aliases: list[str] | None = None,
    multilingual: list[str] | None = None,
    broader: str | None = None,
    narrower: list[str] | None = None,
    related: list[str] | None = None,
) -> dict[str, Any]:
    """Publish one concept into the vocabulary every read surface consults.

    There were two disconnected concept stores. ``POST /ontology/concepts`` wrote
    to the graph store, while ``/ontology/search``, ``/ontology/resolve``,
    ``/ontology/concept/{term}`` and ``GET /ontology/concepts`` all read the
    module-level ``_CONCEPT_DEFINITIONS``. So the write path and the read paths
    never met. Measured before this change, after a successful upsert:

        POST /ontology/concepts        -> 200
        GET  /graph/nodes/<term>       -> 200      (the node was written)
        GET  /ontology/search?q=<term> -> count=0
        POST /ontology/resolve         -> resolved=[]
        GET  /ontology/concepts        -> does not contain it

    Writing here reaches all six readers, because they read this dict directly -
    no accessor can be forgotten. The store write is kept as well: the graph node
    and its embedding are what ``/graph/*`` serves.

    Bounded like the proposal queue: this is process-lifetime state, so the
    oldest registration is evicted at the cap. **It is not durable** - additions
    are lost on restart, exactly as the in-memory evidence and graph defaults are.
    Durable concept publication needs a store-backed read path, which would mean
    extending the abstract ``GraphStore`` surface and its Postgres
    implementation; that is deliberately not done here rather than shipped
    untested.
    """
    canonical = concept.strip()
    if not canonical:
        raise ValueError("concept must not be empty")
    if len(canonical) > MAX_ONTOLOGY_PATCH_FIELD:
        raise ValueError(f"concept must be at most {MAX_ONTOLOGY_PATCH_FIELD} characters")

    existing = _CONCEPT_DEFINITIONS.get(canonical)
    if existing is not None:
        # An approval must not silently rewrite a shipped definition; that needs
        # its own explicit path. The record is returned unchanged so the caller
        # can report that nothing was overwritten.
        return {"concept": canonical, "already_published": True, **existing}

    if len(_CONCEPT_DEFINITIONS) >= MAX_REGISTERED_CONCEPTS:
        oldest = next(iter(_CONCEPT_DEFINITIONS))
        del _CONCEPT_DEFINITIONS[oldest]

    record: Dict[str, Any] = {
        "aliases": list(aliases or []),
        "broader": broader,
        "narrower": list(narrower or []),
        "related": list(related or []),
        "definition": definition.strip(),
        "multilingual": list(multilingual or []),
    }
    _CONCEPT_DEFINITIONS[canonical] = record
    _ALIAS_TO_CANONICAL[_normalize_term(canonical)] = canonical
    for alias in record["aliases"] + record["multilingual"]:
        _ALIAS_TO_CANONICAL[_normalize_term(alias)] = canonical
    return {"concept": canonical, "already_published": False, **record}


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


def concept_assets(concept: str, tenant_ids: list[str] | None = None) -> Dict[str, Any]:
    """Describe one concept and the datasets it maps to, scoped to the caller.

    The concept vocabulary is shared, but ``dataset_ids`` is dataset identity.
    ``_INDEX`` is built from ``list_datasets()`` with no tenant predicate, so this
    returned every tenant's dataset ids - and ``POST /llm/search`` served it to a
    caller whose own policy decision said ``deny``. ``withheld_dataset_count``
    declares the truncation so a short list does not read as the whole mapping.
    """
    canonical = _canonicalize_concept(concept)
    datasets = _INDEX.get(canonical, [])
    if tenant_ids is not None:
        visible_ids = {dataset.id for dataset in list_datasets(tenant_ids)}
        scoped = [dataset_id for dataset_id in datasets if dataset_id in visible_ids]
    else:
        scoped = list(datasets)
    metadata = _CONCEPT_DEFINITIONS.get(canonical, {})
    return {
        "concept": canonical,
        "graph": concept_graph(canonical),
        "dataset_ids": scoped,
        "count": len(scoped),
        "withheld_dataset_count": len(datasets) - len(scoped),
        "aliases": [canonical] + list(metadata.get("aliases", [])),
    }


def propose_patch(concept: str, suggestion: str, *, requestor: str = "anonymous") -> dict[str, Any]:
    """Queue one ontology patch proposal.

    The queue is process-lifetime state, so both the caller's strings and the
    queue depth are bounded: an unbounded proposal route let a caller hold
    arbitrary memory for the life of the process (a 50,000-character suggestion
    was accepted). The oldest proposal is evicted at the cap rather than refusing
    new ones, so the queue cannot be filled to lock out legitimate proposals.
    """
    if len(concept) > MAX_ONTOLOGY_PATCH_FIELD or len(suggestion) > MAX_ONTOLOGY_PATCH_FIELD:
        raise ValueError(
            f"concept and suggestion must each be at most {MAX_ONTOLOGY_PATCH_FIELD} characters"
        )
    patch = OntologyPatch(
        id=str(uuid4()),
        concept=concept.strip() or "unknown",
        suggestion=suggestion.strip(),
        requestor=requestor,
        confidence=min(max(len(suggestion) / 220.0, 0.3), 0.95),
    )
    _ONTOLOGY_PATCHES.append(patch)
    if len(_ONTOLOGY_PATCHES) > MAX_ONTOLOGY_PATCHES:
        del _ONTOLOGY_PATCHES[:-MAX_ONTOLOGY_PATCHES]
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
        published = patch.model_dump()
        if patch.status == "approved":
            # The documented workflow is 제안 -> 승인 -> 노출. It stopped at 승인:
            # approving a patch changed nothing in /ontology/search,
            # /ontology/resolve, /ontology/concept or GET /ontology/concepts, and
            # no documented path loaded an approved term into the read surface at
            # all. Approval now publishes the concept through the same registrar
            # POST /ontology/concepts uses, and the response says what happened
            # rather than leaving the caller to check.
            registration = register_concept(patch.concept, definition=patch.suggestion)
            published["published_concept"] = registration["concept"]
            published["concept_already_published"] = registration["already_published"]
        return published
    raise KeyError("patch not found")
