from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List
from uuid import uuid4

from . import ontology_version
from .catalog import list_datasets, mapping_candidates
from .domain import OntologyPatch
from .semantic_validation import (
    PRESENCE_BASIS,
    has_visible_character,
    validate_concept_semantics,
)


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


def _index_concept_terms(canonical: str, record: Dict[str, Any]) -> None:
    """Point this concept's own name and its aliases at it in the lookup index.

    A concept's **canonical name always maps to itself**, and an alias claims a
    normalized term only if no other concept already holds it. Without those two
    rules the index is last-writer-wins, and one registration could take over a
    term another concept owns - including a canonical concept name. See
    ``_assert_no_alias_conflict`` for the caller-facing refusal; this function is
    what makes the seed loop and the runtime path share one set of rules, so the
    invariant cannot be broken by editing the seed alone.
    """
    _ALIAS_TO_CANONICAL[_normalize_term(canonical)] = canonical
    for alias in list(record.get("aliases", [])) + list(record.get("multilingual", [])):
        normalized = _normalize_term(alias)
        if not normalized:
            continue
        owner = _ALIAS_TO_CANONICAL.get(normalized)
        if owner is not None and owner != canonical:
            continue
        _ALIAS_TO_CANONICAL[normalized] = canonical


for base_concept in _CONCEPT_DEFINITIONS:
    _ALIAS_TO_CANONICAL[_normalize_term(base_concept)] = base_concept
# Canonical names are claimed first, for every concept, so no concept's alias can
# take a name another concept already answers to.
for base_concept in _CONCEPT_DEFINITIONS:
    _index_concept_terms(base_concept, _CONCEPT_DEFINITIONS[base_concept])
del base_concept

# The shipped vocabulary is the baseline the change log counts from. Recorded at
# import, once, because no actor published it: five rows naming no actor would
# be five fabrications of a publication event that never happened. See
# ``ontology_version.record_baseline``.
ontology_version.record_baseline(_CONCEPT_DEFINITIONS)

# The vocabulary that ships with the product, captured before any registration
# can add to it. Eviction at the cap must never reach these: see
# ``register_concept``.
SEEDED_CONCEPTS = frozenset(_CONCEPT_DEFINITIONS)


MAX_REGISTERED_CONCEPTS = 500


def _assert_no_alias_conflict(canonical: str, terms: List[str]) -> None:
    """Refuse a registration whose alias would take a term another concept owns.

    Measured before this check, with one authorized upsert
    (``POST /ontology/concepts`` -> 200) naming a seeded concept as its alias::

        {"actor": "admin", "concept": "침입개념", "aliases": ["고객"]}

        canonicalize("고객")  before -> "고객"
        canonicalize("고객")  after  -> "침입개념"

    Every read surface resolves through that index, so the seeded concept was
    **hijacked**: resolve/search/concept lookups for "고객" answered with the
    intruder. The alias index was last-writer-wins and nothing checked ownership.

    Refusing is the fail-closed choice: the caller is told which term collides
    and can register without it, and no existing concept's identity moves as a
    side effect of someone else's write.
    """
    conflicts: list[str] = []
    for term in terms:
        normalized = _normalize_term(term)
        if not normalized:
            continue
        if normalized == _normalize_term(canonical):
            continue
        owner = _ALIAS_TO_CANONICAL.get(normalized)
        if owner is not None and owner != canonical:
            conflicts.append(f"{term!r} already belongs to {owner!r}")
    if conflicts:
        raise ValueError("alias conflict: " + "; ".join(sorted(conflicts)))


def concept_record(
    *,
    definition: str = "",
    aliases: List[str] | None = None,
    multilingual: List[str] | None = None,
    broader: str | None = None,
    narrower: List[str] | None = None,
    related: List[str] | None = None,
) -> Dict[str, Any]:
    """One concept record in the exact shape the vocabulary stores.

    Built here rather than inline so the shape gate evaluates the **same** six
    keys that ``_register_concept_locked`` writes. A validator checking a record
    assembled a second way is a validator that can pass while the stored record
    fails.
    """
    return {
        "aliases": list(aliases or []),
        "broader": broader,
        "narrower": list(narrower or []),
        "related": list(related or []),
        "definition": definition.strip(),
        "multilingual": list(multilingual or []),
    }


def concept_shape_report(concept: str, record: Dict[str, Any]) -> dict[str, Any]:
    """Evaluate ConceptShape against one record (ONT-005's SHACL gate item).

    ``canonical_concept_or_none`` is injected as the resolver, so a hierarchy
    target that is only an alias resolves to the concept it aliases and one that
    resolves to nothing is reported. The resolver is passed in rather than
    imported by ``semantic_validation``, which would make that module import the
    vocabulary it validates.
    """
    return validate_concept_semantics(
        concept, record, resolve_concept=canonical_concept_or_none
    )


def validate_concept_registration(
    concept: str,
    *,
    definition: str = "",
    aliases: List[str] | None = None,
    multilingual: List[str] | None = None,
    broader: str | None = None,
    narrower: List[str] | None = None,
    related: List[str] | None = None,
) -> str:
    """Validate a concept registration and return its canonical (stripped) name.

    Separated from ``register_concept`` so a caller that writes to more than one
    store can validate **before** the first write. ``POST /ontology/concepts``
    wrote the graph node first and called ``register_concept`` second, so an
    invalid concept left the graph node behind *and* answered 500 - the
    ``ValueError`` escaped the route unmapped. Measured: ``{"concept": "   "}``
    raised ``ValueError: concept must not be empty`` out of the endpoint.
    """
    canonical = concept.strip()
    if not canonical:
        raise ValueError("concept must not be empty")
    # ``strip`` removes only ``str.isspace()`` characters, and the Unicode
    # format category is not whitespace - measured, three concepts named
    # U+200B, U+FEFF and NUL were published through ``POST /ontology/concepts``
    # with 200, and a concept whose name no reader can see cannot be resolved,
    # searched for or cited. The same predicate the ConceptShape gate applies to
    # the definition, so the name and its definition are held to one rule.
    if not has_visible_character(canonical):
        raise ValueError(f"concept must contain {PRESENCE_BASIS}")
    if len(canonical) > MAX_ONTOLOGY_PATCH_FIELD:
        raise ValueError(f"concept must be at most {MAX_ONTOLOGY_PATCH_FIELD} characters")
    if canonical not in _CONCEPT_DEFINITIONS:
        _assert_no_alias_conflict(
            canonical, list(aliases or []) + list(multilingual or [])
        )
    # ONT-005's acceptance criterion is "reasoner + SHACL + reviewer 승인 후
    # 병합" and reviewer approval was the whole gate. The shape is evaluated
    # here - the designated pre-write validator, whose ValueError the routes
    # already map to 400 - so **both** publication paths are covered by one
    # gate and a third caller cannot bypass it. Measured before this gate:
    # ``POST /ontology/concepts {"actor": "admin", "concept": "정의누락개념"}``
    # answered 200 and published a concept with ``definition: ''`` into the
    # glossary every read surface consults.
    #
    # Only violations gate. The shape's hierarchy constraint is a warning,
    # because the shipped vocabulary violates it 10 times and a constraint that
    # refuses the product's own seed cannot gate publication.
    report = concept_shape_report(
        canonical,
        concept_record(
            definition=definition,
            aliases=aliases,
            multilingual=multilingual,
            broader=broader,
            narrower=narrower,
            related=related,
        ),
    )
    if not report["conforms"]:
        raise ValueError(
            "ConceptShape violation: "
            + "; ".join(
                item["message"]
                for item in report["violations"]
                if item["severity"] == "violation"
            )
        )
    return canonical


def register_concept(
    concept: str,
    *,
    change_source: str,
    definition: str = "",
    aliases: list[str] | None = None,
    multilingual: list[str] | None = None,
    broader: str | None = None,
    narrower: list[str] | None = None,
    related: list[str] | None = None,
    actor_id: str | None = None,
    reviewer_id: str | None = None,
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
    # ``change_source`` has no default on purpose. There are exactly two
    # externally-triggered publication paths - a direct admin upsert and an
    # approved patch - and they differ in whether anyone reviewed the change. A
    # default would let a third caller land silently under one of the two
    # labels, and the change log's whole value is that the label is true.
    with ontology_version.vocabulary_change_lock():
        return _register_concept_locked(
            concept,
            change_source=change_source,
            definition=definition,
            aliases=aliases,
            multilingual=multilingual,
            broader=broader,
            narrower=narrower,
            related=related,
            actor_id=actor_id,
            reviewer_id=reviewer_id,
        )


def _register_concept_locked(
    concept: str,
    *,
    change_source: str,
    definition: str = "",
    aliases: list[str] | None = None,
    multilingual: list[str] | None = None,
    broader: str | None = None,
    narrower: list[str] | None = None,
    related: list[str] | None = None,
    actor_id: str | None = None,
    reviewer_id: str | None = None,
) -> dict[str, Any]:
    """Publish one concept. Call with the vocabulary lock held.

    The lock is taken by the public wrapper **before** the existence read below,
    not after. ``existing`` decides new-versus-no-op and the store write happens
    nineteen lines later, so acquiring the lock after the read would leave the
    window open: two concurrent registrations of the same concept could both
    read ``None``, both answer ``already_published: False``, and one overwrite
    the other - two acknowledged publications for one dict entry, and two
    revisions for one change. Forced-interleaving measurement reproduced exactly
    that. This is the same read-modify-write boundary ``catalog._MUTATION_LOCK``
    exists to close.
    """
    canonical = validate_concept_registration(
        concept,
        definition=definition,
        aliases=aliases,
        multilingual=multilingual,
        broader=broader,
        narrower=narrower,
        related=related,
    )

    existing = _CONCEPT_DEFINITIONS.get(canonical)
    if existing is not None:
        # An approval must not silently rewrite a shipped definition; that needs
        # its own explicit path. The record is returned unchanged so the caller
        # can report that nothing was overwritten.
        return {
            "concept": canonical,
            "already_published": True,
            "concept_validation": concept_shape_report(canonical, existing),
            **existing,
        }

    if len(_CONCEPT_DEFINITIONS) >= MAX_REGISTERED_CONCEPTS:
        # Eviction is a content change of its own, recorded by the evicting
        # function rather than here: a published term leaves the ontology as a
        # side effect of this caller's success, and the change log must show the
        # deletion and the publication as two revisions, in that order.
        _evict_one_registered_concept(actor_id=actor_id)

    record: Dict[str, Any] = concept_record(
        definition=definition,
        aliases=aliases,
        multilingual=multilingual,
        broader=broader,
        narrower=narrower,
        related=related,
    )
    _CONCEPT_DEFINITIONS[canonical] = record
    _index_concept_terms(canonical, record)
    # Recorded after both writes, so the digest stamped into the entry is the
    # content the revision names. Recorded before them, the entry would claim a
    # digest the vocabulary does not have.
    ontology_version.record_vocabulary_change(
        change_kind="concept_published",
        change_source=change_source,
        concept_name=canonical,
        vocabulary=_CONCEPT_DEFINITIONS,
        actor_id=actor_id,
        reviewer_id=reviewer_id,
    )
    return {
        "concept": canonical,
        "already_published": False,
        # Evaluated against the record as **stored**, after the write, so the
        # published report describes published content rather than a submission
        # that could still have been refused.
        "concept_validation": concept_shape_report(canonical, record),
        **record,
    }


def _evict_one_registered_concept(*, actor_id: str | None = None) -> None:
    """Make room at the cap by dropping the oldest **caller-added** concept.

    The eviction was ``next(iter(_CONCEPT_DEFINITIONS))``, and the dict is
    insertion-ordered with the shipped vocabulary inserted first - so the
    oldest entry was always a seeded concept. Measured by filling to the cap of
    500 with ``filler-N`` registrations: 3 of the 5 seeded concepts ("고객",
    "활성 고객", "이탈") were destroyed and 2 survived. Anyone able to register
    concepts could therefore delete the product's own vocabulary.

    When nothing caller-added is left to evict the cap is reported as full
    rather than satisfied by deleting shipped data.
    """
    for candidate in _CONCEPT_DEFINITIONS:
        if candidate in SEEDED_CONCEPTS:
            continue
        stale_aliases = [
            term for term, owner in _ALIAS_TO_CANONICAL.items() if owner == candidate
        ]
        for term in stale_aliases:
            del _ALIAS_TO_CANONICAL[term]
        del _CONCEPT_DEFINITIONS[candidate]
        # A deletion with no caller and no audit row was invisible: the only
        # trace of a published term leaving the vocabulary was its absence.
        # ``actor_id`` is whoever's registration forced the eviction, not
        # someone who asked for a deletion - ``review_basis:
        # "capacity_policy"`` says nobody decided it.
        ontology_version.record_vocabulary_change(
            change_kind="concept_evicted",
            change_source="cap_eviction",
            concept_name=candidate,
            vocabulary=_CONCEPT_DEFINITIONS,
            actor_id=actor_id,
        )
        return
    raise ValueError(
        f"concept vocabulary is full ({MAX_REGISTERED_CONCEPTS}) and holds only "
        "seeded concepts, which are never evicted"
    )


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
    """One resolved term, and whether the vocabulary actually defines it.

    ``_INDEX`` is built from ``dataset.terms``, which are declared by datasets
    and need not be registered concepts. Measured on the seed, resolution
    published term IRIs for 캠페인, 전환 and 비즈니스 용어 - none of which the
    glossary defines - identically shaped to the IRI of a defined concept, so a
    client could not tell a definition it can look up from an identifier that
    leads nowhere. ``defined_in_vocabulary`` is that distinction; the resolution
    is still returned, because it is a real pointer to a dataset.
    """

    term: str
    score: float
    uri: str
    aliases: List[str]
    defined_in_vocabulary: bool


def _canonicalize_concept(concept: str) -> str:
    return _ALIAS_TO_CANONICAL.get(_normalize_term(concept), concept)


def list_concepts() -> List[str]:
    return sorted(_CONCEPT_DEFINITIONS.keys())


def concept_vocabulary_snapshot() -> Dict[str, Any]:
    """A copy of the vocabulary, for callers that only need to read it.

    ``ontology_version`` takes the vocabulary as an argument rather than
    importing this module, so the dependency stays one-way. Handing out a copy
    keeps a reader from mutating the live dict behind the revision counter -
    which ``ontology_version_identity`` would then report as
    ``digest_matches_recorded_revision: false``.
    """
    return {concept: dict(record) for concept, record in _CONCEPT_DEFINITIONS.items()}


def ontology_version_identity() -> dict[str, Any]:
    """The live ontology version identity (ONT-004). See ``ontology_version``."""
    return ontology_version.ontology_version_identity(_CONCEPT_DEFINITIONS)


def vocabulary_change_log(limit: int = 100) -> dict[str, Any]:
    """The ontology change log, newest first. Carries actor/reviewer identity."""
    return ontology_version.vocabulary_change_log(limit=limit)


def vocabulary_jsonld() -> dict[str, Any]:
    """The vocabulary as versioned SKOS/RDFS JSON-LD.

    ``canonical_concept_or_none`` is injected as the resolver so a hierarchy
    target that is only an alias (활성 고객 ``related`` 휴면 고객, an alias of
    이탈 고객) points at the real concept's IRI, and one that resolves to
    nothing is declared instead of minting an IRI for a concept that does not
    exist.
    """
    return ontology_version.vocabulary_jsonld(
        _CONCEPT_DEFINITIONS, resolve_concept=canonical_concept_or_none
    )


def canonical_concept_or_none(concept: str) -> str | None:
    """The registered canonical name for this term, or ``None`` if unregistered.

    ``_canonicalize_concept`` returns its input unchanged for a term the
    glossary does not know, which is the right behaviour for resolution but
    cannot distinguish "canonical already" from "not in the glossary". Coverage
    measurement needs that distinction: a business mapping naming a concept the
    ontology never defined is not ontology coverage, and counting it as such is
    how the published number credited three such mappings.
    """
    canonical = _canonicalize_concept(concept)
    return canonical if canonical in _CONCEPT_DEFINITIONS else None


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
                    uri=ontology_version.concept_iri(concept),
                    aliases=sorted(set(aliases)),
                    defined_in_vocabulary=canonical_concept_or_none(concept) is not None,
                )
            )

    for candidate in search_concepts(text):
        if not any(item.term == candidate.concept for item in resolved):
            resolved.append(
                Resolution(
                    term=candidate.concept,
                    score=0.55,
                    uri=ontology_version.concept_iri(candidate.concept),
                    aliases=sorted(candidate.aliases),
                    # ``search_concepts`` only ever yields registered concepts.
                    defined_in_vocabulary=True,
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


# The statuses a patch can hold. `GET /ontology/patches?status=` matched this
# set by string equality with no validation, so an unknown or wrongly-cased
# value simply matched nothing and reported an empty queue.
PATCH_STATUSES = frozenset({"proposed", "approved", "rejected"})


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

    # One lock across the publication *and* the patch's status write. They are
    # two stores, and an approval that published the concept but failed to
    # record the review - or recorded the review while another thread published
    # the same concept - leaves 승인 and 노출 disagreeing, which is the exact
    # break this path exists to close.
    with ontology_version.vocabulary_change_lock():
        return _review_patch_locked(
            patch_id, normalized, reviewer=reviewer, comment=comment
        )


def _review_patch_locked(
    patch_id: str,
    normalized: str,
    *,
    reviewer: str,
    comment: str,
) -> dict[str, Any]:
    """Apply one review decision. Call with the vocabulary lock held."""
    for idx, patch in enumerate(_ONTOLOGY_PATCHES):
        if patch.id != patch_id:
            continue
        if patch.status != "proposed":
            raise ValueError("patch is not in proposed state")
        # The documented workflow is 제안 -> 승인 -> 노출. It stopped at 승인:
        # approving a patch changed nothing in /ontology/search,
        # /ontology/resolve, /ontology/concept or GET /ontology/concepts, and
        # no documented path loaded an approved term into the read surface at
        # all. Approval publishes the concept through the same registrar
        # POST /ontology/concepts uses, and the response says what happened
        # rather than leaving the caller to check.
        #
        # Publication runs **before** the status is written. ``register_concept``
        # can refuse (the vocabulary cap can be full of seeded concepts, which
        # are never evicted); doing it after the mutation left the patch marked
        # "approved" with nothing published and the caller holding an error -
        # 승인 recorded, 노출 missing, which is the exact break this path exists
        # to close.
        registration = None
        if normalized == "approve":
            # ``actor_id`` is the proposer and ``reviewer_id`` the approver, so
            # the change log shows both halves of the 제안 -> 승인 workflow. The
            # reviewer is the authorized actor (``api`` refuses a body-supplied
            # ``reviewer`` outright), and this is the only ``change_source``
            # permitted to carry one.
            registration = register_concept(
                patch.concept,
                change_source="patch_approval",
                definition=patch.suggestion,
                actor_id=patch.requestor,
                reviewer_id=reviewer,
            )

        patch.reviewed_by = reviewer
        patch.reviewed_at = datetime.now(timezone.utc)
        patch.review_comment = comment
        patch.status = "approved" if normalized == "approve" else "rejected"
        _ONTOLOGY_PATCHES[idx] = patch
        published = patch.model_dump()
        if registration is not None:
            published["published_concept"] = registration["concept"]
            published["concept_already_published"] = registration["already_published"]
            # ONT-005 asks for SHACL before merge. The gate runs inside
            # ``register_concept`` above - so a non-conforming concept raises
            # before the status write and the patch is never marked approved
            # with nothing published - and the report is published here so the
            # evaluation is observable rather than merely asserted.
            published["concept_validation"] = registration["concept_validation"]
        return published
    raise KeyError("patch not found")
