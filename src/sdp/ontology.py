from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List
from uuid import uuid4

from . import ontology_version
from .catalog import list_datasets, mapping_candidates
from .domain import OntologyPatch
from .semantic_validation import (
    MAX_PUBLISHED_FIELD_LENGTH,
    PRESENCE_BASIS,
    has_visible_character,
    hierarchy_class_separation,
    hierarchy_consistency,
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


def concept_dataset_index() -> Dict[str, List[str]]:
    """The concept-to-dataset map, derived from the catalog on every read.

    This was a module-level snapshot taken at import (``_INDEX =
    _build_index()``), so a dataset registered afterwards never entered it.
    Measured after onboarding and publishing one dataset declaring 고객, as
    ``user=data-admin``::

        GET  /catalog/search?q=고객    -> 6 ids, including the new one
        GET  /ontology/term/고객/graph -> 5 ids, including the new one
        GET  /ontology/concept/고객    -> 4 ids, without it, withheld_dataset_count 0
        POST /llm/search {고객}        -> 4 ids, without it, withheld_dataset_count 0

    So the owner's two documented "which datasets carry this term" entry points
    answered without their dataset while declaring that nothing was withheld, and
    two routes README calls siblings serving the same fact disagreed. That the map
    is outside the *versioned* scope (``sdp:datasetMappingIsVersioned false``)
    stays true; what it no longer does is go stale.

    Deriving it is cheap enough that there is no cache to keep coherent and no new
    module state for ``tests/conftest.py`` to restore: rebuilding costs 3.7 ms per
    2000 calls against ``resolve_terms``'s own 148.9 ms for the same 2000 - 2.5%,
    on 10 keys over 5 datasets. Insertion order still follows ``list_datasets()``,
    so the documented tie-break over this map's order is unchanged.
    """
    index: Dict[str, List[str]] = {}
    for dataset in list_datasets():
        for concept in dataset.terms:
            index.setdefault(concept, []).append(dataset.id)
    return index


def _normalize_term(value: str) -> str:
    return value.strip().replace("_", " ").lower()


_ONTOLOGY_PATCHES: list[OntologyPatch] = []
# Bounds on the process-lifetime proposal queue; see propose_patch.
MAX_ONTOLOGY_PATCHES = 500
MAX_ONTOLOGY_PATCH_FIELD = 2000
# What the cap dropped, for the life of the process. The eviction itself is
# deliberate (``propose_patch`` explains why it is preferred to refusing), but
# it was entirely undeclared: a proposal accepted with 200 and an id answered
# 404 on the only route that can act on it, while ``GET /ontology/patches``
# reported ``count: 500`` as if that were the whole queue. The change log - the
# other evicting store in this package - had been publishing its own
# ``withheld_change_count`` since ONT-004, so the vocabulary existed; only this
# queue was missing it.
_PATCH_QUEUE_STATE: dict[str, int] = {"withheld": 0}
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
    # ``definition.strip()`` raised AttributeError for a non-string, and both
    # routes map only ValueError - so an in-process caller got an unmapped
    # exception type from a function documented to signal refusal with
    # ValueError. Refused rather than coerced: ``str(5)`` would publish "5" as a
    # definition, which is a fabrication, not a repair.
    if not isinstance(definition, str):
        raise ValueError(
            f"definition must be a string, not {type(definition).__name__}"
        )
    return {
        "aliases": list(aliases or []),
        "broader": broader,
        "narrower": list(narrower or []),
        "related": list(related or []),
        "definition": definition.strip(),
        "multilingual": list(multilingual or []),
    }


class ConceptKindConflict(ValueError):
    """A concept name an existing node of another kind already holds.

    A ``ValueError`` subclass on purpose: every existing handler that catches
    ``ValueError`` still catches this, so no caller silently stops refusing.
    Routes that want the precise status catch it first and answer 409, because
    the request is well-formed and the conflict is with state - and both
    publication paths then answer the same status for the same conflict, rather
    than 409 on the upsert route and 400 on the approval route.
    """


def _assert_concept_kind_is_available(canonical: str) -> None:
    """Refuse a concept name that another kind of graph node already holds.

    Asks the store rather than guessing from the shape of the name: a
    name-collision rule would refuse legitimate vocabulary (``semantic-glossary``
    is both a dataset id and a plausible term) and would still miss the case
    where no node exists yet. The question is only ever "is this id already
    something else", which is what the store can answer.

    The store is imported lazily: ``graph_store`` reaches configuration and a
    possible database engine, and this module is imported during application
    start-up well before a request needs either.
    """
    from .graph_store import get_store

    try:
        get_store().assert_node_kind_is_stable(canonical, "concept")
    except ValueError as conflict:
        raise ConceptKindConflict(str(conflict)) from conflict


def _assert_hierarchy_targets_respect_class_separation(
    canonical: str, broader: str | None, narrower: List[str] | None
) -> None:
    """Refuse a concept whose declared parent or child is a data asset.

    ONT-002's edge half reached the vocabulary through this route: measured,
    ``POST /ontology/concepts {"concept": "테스트개념하나", "definition": "정의",
    "broader": "crm-customer-master"}`` answered **200** and the graph then held
    ``broader: 테스트개념하나 -> crm-customer-master``, a business class declared
    a sub-class of a dataset; the same request with
    ``"narrower": ["crm-customer-master:customer_id"]`` put a *column* node in
    the hierarchy.

    Asked **here**, in the designated pre-write validator, and not left to the
    store's own gate, because ``upsert_concept`` writes the concept node and the
    vocabulary record *before* its hierarchy edges. Measured with this call
    removed and the store's gate left in place, the same request answered
    **500** - the route's mirror write is not inside either ``try`` block - with
    the vocabulary record published *and* the graph node served. That is the
    partial-write failure ``validate_concept_registration`` exists to prevent.
    The store's gate stays, because ``POST /graph/edges`` reaches it directly.

    One window remains, and it is the window the kind check already has: a
    concurrent writer that creates the target as a dataset node between this
    check and the mirror write makes the unguarded ``upsert_concept`` raise, so
    the route answers 500. The pre-existing ``assert_node_kind_is_stable`` pair
    has exactly the same shape, so this adds no new class of failure; closing it
    needs the two writes to be one transaction, not a status mapping, because a
    409 there would claim nothing happened while the vocabulary had changed.

    ``related`` is not checked: it is associative in SKOS, not subsumption, so a
    concept related to a dataset asserts no class hierarchy. The rule refuses
    exactly the subsumption claim.
    """
    from .graph_store import get_store

    store = get_store()
    for relation, target in [("broader", broader)] + [
        ("narrower", narrow) for narrow in list(narrower or [])
    ]:
        if target:
            store.assert_hierarchy_respects_class_separation(
                relation, canonical, target
            )


def _assert_declared_hierarchy_stays_acyclic(
    canonical: str, broader: str | None, narrower: List[str] | None
) -> None:
    """Refuse a concept whose declared parent or child closes a hierarchy cycle.

    The companion to ``_assert_hierarchy_targets_respect_class_separation``, and
    here for the same reason: measured, ``POST /ontology/concepts`` published
    ``순환상위`` with ``broader: 고객`` and then ``고객`` with
    ``broader: 순환상위``, both **200**, leaving the glossary asserting that each
    of two distinct terms is a kind of the other. Asked before the first write,
    because ``upsert_concept`` writes the concept node and the vocabulary record
    before its hierarchy edges.

    The declared relations are checked against the stored hierarchy **and
    against each other**, by carrying the pairs already accepted from this same
    submission into each subsequent check. Checking them one at a time against
    stored state alone was a defect, confirmed by adversarial review: a
    submission that is cyclic within itself passed every individual check, and
    the store's gate then refused the *second* edge from inside the route's
    unguarded mirror write. Measured::

        POST /ontology/concepts {"actor": "admin", "concept": "순환개념",
                                 "definition": "정의", "broader": "상대개념",
                                 "narrower": ["상대개념"]}
            -> 500 (not 409), with the vocabulary record published asserting
               that each term is a kind of the other, the graph node written,
               one of the two edges written, every read surface serving it 200,
               the concept in the SKOS export - and
               ``hierarchy_consistency`` reporting conforms: true, because the
               closing edge never landed. A later ``seed_store`` on a fresh
               store raised on that stored record.

    The docstring here previously claimed that residual "is reported by
    ``hierarchy_consistency``". It was not: that report reads graph *edges*, and
    the gate prevents the closing edge from ever being written, so the
    contradiction lived only in the vocabulary record and was structurally
    invisible to it. A disclosed limitation whose named compensating control
    does not exist is still a defect.
    """
    from .graph_store import get_store, subsumption_pair

    store = get_store()
    accepted: list[tuple[str, str]] = []
    for relation, target in [("broader", broader)] + [
        ("narrower", narrow) for narrow in list(narrower or [])
    ]:
        if not target:
            continue
        store.assert_hierarchy_stays_acyclic(
            relation, canonical, target, pending_pairs=tuple(accepted)
        )
        pair = subsumption_pair(relation, canonical, target)
        if pair is not None:
            accepted.append(pair)


def concept_shape_report(
    concept: str, record: Dict[str, Any], *, evaluated_record: str = "submitted"
) -> dict[str, Any]:
    """Evaluate ConceptShape against one record (ONT-005's SHACL gate item).

    ``canonical_concept_or_none`` is injected as the resolver, so a hierarchy
    target that is only an alias resolves to the concept it aliases and one that
    resolves to nothing is reported. The resolver is passed in rather than
    imported by ``semantic_validation``, which would make that module import the
    vocabulary it validates.
    """
    return validate_concept_semantics(
        concept,
        record,
        resolve_concept=canonical_concept_or_none,
        evaluated_record=evaluated_record,
    )


def _vocabulary_hierarchy_edges() -> list[tuple[str, str, str]]:
    """Every hierarchy edge with at least one endpoint in the vocabulary.

    Deduplicated - each edge is found once from each endpoint that is in the
    vocabulary - and sorted, so both reports below publish a stable order and
    read the same set of edges.
    """
    from .graph_store import HIERARCHY_EDGE_TYPES, get_store

    store = get_store()
    found: set[tuple[str, str, str]] = set()
    for concept in concept_vocabulary_snapshot():
        for relation in HIERARCHY_EDGE_TYPES:
            for direction in ("out", "in"):
                for edge in store.edges_for(concept, relation, direction=direction):
                    found.add((edge.edge_type, edge.source_id, edge.target_id))
    return sorted(found)


HIERARCHY_IDENTIFIER_WITHHELD = "<withheld>"


def hierarchy_class_separation_report(
    tenant_ids: list[str] | None = None,
) -> dict[str, Any]:
    """ConceptHierarchyShape conformance over the graph's hierarchy edges.

    Published on ``/enterprise/shacl-validation`` so ONT-002's constraint is
    measurable against the shipped graph and not only at the moment of a write -
    which is what the acceptance criterion's 검증 asks for, and what the write
    gate on its own cannot give: an edge written while both endpoints were
    unknown is permitted, and an endpoint may be created as a dataset
    afterwards.

    Anchored on the **vocabulary**, enumerating each concept's hierarchy edges in
    both directions through the ``edges_for`` primitive both backends already
    implement, rather than on a new "list every edge" store method that would
    need separate SQL only an integration run could exercise. That costs
    O(vocabulary x hierarchy edges), because each call scans the edges: measured
    at the 500-concept vocabulary cap with 9,790 hierarchy edges, this report and
    its class-separation sibling take 0.44s and 0.65s. A graph with far more
    edges than that wants a single-pass primitive, which is a separate change
    because the Postgres half needs its own statement. (The *classifier* is
    linear - see ``hierarchy_consistency`` for the exponential version that
    adversarial review found here, and the measurement that condemned it.) Anchoring there is
    also the honest scope: ONT-002 is about a data asset entering the *business
    class* hierarchy, so every edge it is about has a business class at one end.
    A ``kind="concept"`` node written straight through ``POST /graph/nodes`` is
    not in the vocabulary - the boundary ``CONCEPT_CONFORMANCE_SCOPE`` already
    declares for the concept pass rate - so ``conformance_scope`` says so here
    too rather than letting the count read as covering every edge in the graph.
    """
    from .catalog import get_dataset
    from .graph_store import get_store
    from .policy import graph_node_dataset_id

    store = get_store()
    found = _vocabulary_hierarchy_edges()
    kinds: dict[str, str | None] = {}
    withheld: set[str] = set()

    def _kind_of(node_id: str) -> str | None:
        """This node's kind, or ``None`` when no such node exists."""
        if node_id not in kinds:
            node = store.get_node(node_id)
            kinds[node_id] = node.kind if node else None
        return kinds[node_id]

    def _printable_id(node_id: str) -> str:
        """The identifier this caller may read, or the withholding marker.

        ``ConceptHierarchyShape``'s violation fires exactly when an endpoint is a
        **dataset** node rather than a concept, so the identifier in that finding
        is a dataset id by construction - and this report was unscoped on the
        stated ground that "the edge identifiers it reports are concept names,
        which the ontology surface already serves to any caller". True of the
        warning branch, false of the violation branch, and an unauthenticated
        caller read a foreign tenant's dataset id out of an aggregate evidence
        endpoint that refuses that same caller on every other route (403/404).

        A concept endpoint is shared vocabulary and stays visible: that half of
        the exemption was right. Only a node owned by a dataset outside the
        caller's scope is withheld, and the finding itself - shape, path,
        severity, counts - is published either way, because ONT-002's
        verification half is a platform-wide statement.
        """
        owning_dataset = graph_node_dataset_id(node_id)
        if owning_dataset is None:
            return node_id
        if tenant_ids is None:
            return node_id
        dataset = get_dataset(owning_dataset)
        if dataset is None or dataset.tenant_id in tenant_ids:
            return node_id
        withheld.add(node_id)
        return HIERARCHY_IDENTIFIER_WITHHELD

    report = hierarchy_class_separation(
        [
            {
                "edge_type": edge_type,
                "source_id": _printable_id(source_id),
                "target_id": _printable_id(target_id),
                "source_kind": _kind_of(source_id),
                "target_kind": _kind_of(target_id),
            }
            for edge_type, source_id, target_id in found
        ]
    )
    # Declared rather than silent, the same way ``withheld_report_count`` is on
    # the per-dataset array one key over.
    return {**report, "withheld_identifier_count": len(withheld)}


def hierarchy_consistency_report() -> dict[str, Any]:
    """Whether the published hierarchy is acyclic, over the graph's current state.

    The companion to ``hierarchy_class_separation_report``, but **not** for the
    same reason, and the difference is measured rather than assumed. The
    class-separation gate reads node *kinds*, so an edge written while an
    endpoint is not a node yet escapes it. This gate reads *edges*, and
    ``subsumption_parents`` sees both spellings of every stored subsumption, so
    no single write through ``upsert_edge`` can close a cycle unseen - the
    ordering that defeats the other gate is refused by this one (measured: 409).

    What this report is for is edges the gate never saw: a hierarchy written
    before the gate existed (a long-lived process, or a Postgres database that
    predates the deploy), a future bulk path that appends without going through
    ``upsert_edge``, and - on the Postgres backend only - two concurrent writers
    each adding one edge of the same cycle, because there the reachability walk
    runs outside the write transaction.

    ONT-007 asks for a consistency check whose result a release gate can read.
    This is not a reasoner and the report says so: no OWL axioms exist in this
    repository, and a subsumption cycle makes concepts mutually subsuming rather
    than unsatisfiable, so what is published is the cycle count rather than a
    number called "unsatisfiable classes".
    """
    from .graph_store import subsumption_pair

    return hierarchy_consistency(
        [
            pair
            for edge_type, source_id, target_id in _vocabulary_hierarchy_edges()
            for pair in (subsumption_pair(edge_type, source_id, target_id),)
            if pair is not None
        ]
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
    # Above the already-published branch, and deliberately not inside it. The
    # exemption that branch rests on - "the stored record was validated when it
    # was published" - holds for ``definition`` and ``aliases``, which the
    # registrar discards from a re-submission. It does **not** hold for the
    # hierarchy fields: the route mirrors the *submitted* ``broader``,
    # ``narrower`` and ``related`` into the graph store (it is the only way to
    # update a concept's edges), so those are not discarded and must be gated on
    # both paths. Measured with these two calls below the branch instead:
    # ``POST /ontology/concepts {"concept": "고객", "broader":
    # "crm-customer-master"}`` - 고객 being one of the five seeded concepts -
    # answered **500**, because the mirror write is inside neither ``try``
    # block, where the identical request for an unpublished concept answered
    # 409. One rule, one status, both paths.
    #
    # The name check leads, because it is the more precise diagnosis of the same
    # request: a concept named after an existing dataset is refused for its
    # *name*, and letting the hierarchy rules answer first turned that into "its
    # source is a dataset node" - true, but it describes the hierarchy edge the
    # publication would have written rather than the collision the caller made.
    # It is also safe above the branch: for an already-published concept it asks
    # whether that concept's own id is still a concept node, which it is.
    _assert_concept_kind_is_available(canonical)
    _assert_hierarchy_targets_respect_class_separation(canonical, broader, narrower)
    _assert_declared_hierarchy_stays_acyclic(canonical, broader, narrower)
    if canonical not in _CONCEPT_DEFINITIONS:
        _assert_no_alias_conflict(
            canonical, list(aliases or []) + list(multilingual or [])
        )
    else:
        # An already-published concept's record is **not** replaced: the
        # registrar returns the stored record and discards the whole submission
        # (an approval must not silently rewrite a shipped definition). So the
        # submitted ``definition`` is not what will exist, and requiring it here
        # refused a request that changes nothing in the vocabulary.
        #
        # Measured as a regression this change introduced:
        # ``POST /ontology/concepts {"concept": "고객", "related":
        # ["신규연관개념"], "aliases": ["buyer-side"]}`` went 200 -> 400, and
        # that route is the only way to update the graph-store concept record,
        # its broader/narrower/related edges and its embedding. The caller's only
        # way through was to re-send a definition the vocabulary throws away -
        # which the graph store then stored, so one 200 body carried a graph
        # definition the vocabulary never accepted.
        #
        # The stored record was validated when it was published, so it is not
        # re-gated here; ``concept_shape_report`` on the early-return path
        # reports it with ``evaluated_record: "published_vocabulary"`` so the
        # caller can see which record the verdict is about.
        return canonical
    # A concept may not take an id another kind of node already holds. The check
    # lived only in ``GraphStore.upsert_node``, so it covered the routes that
    # write a graph node and **not** the patch-approval path, which never
    # touches the store: measured, approving a patch named
    # ``crm-customer-master`` answered 200 and put a dataset id into the
    # vocabulary and the open SKOS export. Here it covers both publication
    # paths, which is the same reason the ConceptShape gate lives here.
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


# What a vocabulary write did, for the two routes that perform one. The audit
# rows already distinguished these (``approved_without_publication``,
# ``upserted_without_publication``); the responses said ``published_concept:
# 고객`` with the revision and the content digest unchanged, so the honest label
# existed only in the ledger a curator does not read.
PUBLICATION_PUBLISHED = "published"
PUBLICATION_EXISTING_KEPT = "existing_definition_kept"


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
            "publication_status": PUBLICATION_EXISTING_KEPT,
            "concept_validation": concept_shape_report(
                canonical, existing, evaluated_record="published_vocabulary"
            ),
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
        "publication_status": PUBLICATION_PUBLISHED,
        # Evaluated against the record as **stored**, after the write, so the
        # published report describes published content rather than a submission
        # that could still have been refused.
        "concept_validation": concept_shape_report(
            canonical, record, evaluated_record="published_vocabulary"
        ),
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

    The concept-to-dataset map is built from ``dataset.terms``, which are declared by datasets
    and need not be registered concepts. Measured on the seed, resolution
    published term IRIs for 캠페인, 전환 and 비즈니스 용어 - none of which the
    glossary defines - identically shaped to the IRI of a defined concept, so a
    client could not tell a definition it can look up from an identifier that
    leads nowhere. ``defined_in_vocabulary`` is that distinction; the resolution
    is still returned, because it is a real pointer to a dataset.

    ``aliases`` is the concept's **own** alias set, identical to what the two
    sibling routes publishing a field of that name return
    (``search_concepts`` -> ``ConceptTerm.aliases`` and ``concept_assets``).
    It used to be an accumulator: the concept, its declared aliases found in the
    text, *and the first mapped dataset's business terms found in the text*, all
    in one list. Dataset terms are declared by datasets and are not synonyms of
    anything, so resolving "이탈 고객" published 이탈 as an alias of 고객, of
    활성 고객 and of 비즈니스 용어, and resolving "매출" published 매출 as an
    alias of 전환 - a concept the glossary does not define at all. A glossary or
    synonym-expansion UI built on the field recorded synonymy the vocabulary
    denies. ``matched_terms`` keeps that information under a name that states
    what it is: the names and terms that actually appeared in the text, and so
    caused this concept to score.
    """

    term: str
    score: float
    uri: str
    aliases: List[str]
    matched_terms: List[str]
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
    # ``dict(record)`` is a *shallow* copy, so the aliases/narrower/related/
    # multilingual lists it handed out were the live stored lists. Measured
    # through this accessor alone, with no private access:
    # ``snapshot()["매출"]["narrower"].append("밀수된하위")`` installed an
    # unresolvable hierarchy target into the published vocabulary, and an alias
    # appended the same way takes a term ``_assert_no_alias_conflict`` refuses.
    # A "copy" that aliases its source is worse than no copy, because callers
    # trust the docstring.
    return deepcopy(_CONCEPT_DEFINITIONS)


def published_concept_definition(concept: str) -> str | None:
    """The definition this concept is published with, or ``None`` if it is new.

    The vocabulary is authoritative for a concept's definition - the registrar
    keeps the stored one and discards a re-submission - so a caller mirroring
    the concept into another store needs the published value, not the submitted
    one. Without it the two stores diverged: measured, a re-upsert that omitted
    ``definition`` left ``GET /ontology/term/{term}/graph`` (which reads the
    graph store) serving 고객 with ``definition: ''`` while the vocabulary still
    held the real definition.

    Resolves through the alias index, so a caller naming an alias gets the
    canonical concept's definition rather than ``None``.
    """
    canonical = canonical_concept_or_none(concept)
    if canonical is None:
        return None
    return str(_CONCEPT_DEFINITIONS[canonical].get("definition", ""))


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


def _names_present_in(candidate: ConceptTerm, text: str) -> list[str]:
    """Which of this concept's own names actually appear in the text.

    ``search_concepts`` matches on normalized containment of the concept, its
    aliases or its multilingual labels, so this recomputes that predicate rather
    than guessing: a ``matched_terms`` that named something the match never
    tested would be the contamination it replaces, one field over.
    """
    haystack = _normalize_term(text)
    names = [candidate.concept] + list(candidate.aliases) + list(candidate.multilingual)
    return sorted({name for name in names if _normalize_term(name) in haystack})


def resolve_terms(text: str) -> list[Resolution]:
    text = text.strip()
    if not text:
        return []

    resolved: list[Resolution] = []
    for concept, dataset_ids in concept_dataset_index().items():
        dataset = dataset_ids[0] if dataset_ids else ""
        score = 0.0
        # What appeared in the text, which is *why* this concept scored. The
        # concept's alias set is a property of the vocabulary and is read
        # separately below; see ``Resolution`` for why they were one list.
        matched: list[str] = []

        definition = _CONCEPT_DEFINITIONS.get(concept, {})
        candidate_aliases = [concept] + list(definition.get("aliases", []))

        if concept in text:
            score += 1.0
            matched.append(concept)
        for alias in candidate_aliases:
            if alias in text and alias not in matched:
                score += 0.3
                matched.append(alias)

        if dataset:
            ds = next(ds for ds in list_datasets() if ds.id == dataset)
            for term in ds.terms:
                if term in text:
                    score += 0.5
                    matched.append(term)
            for dataset_term in mapping_candidates(ds, concept):
                if dataset_term in text:
                    score += 0.3

        if score > 0:
            resolved.append(
                Resolution(
                    term=concept,
                    score=min(score, 1.0),
                    uri=ontology_version.concept_iri(concept),
                    aliases=sorted(set(candidate_aliases)),
                    matched_terms=sorted(set(matched)),
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
                    matched_terms=_names_present_in(candidate, text),
                    # ``search_concepts`` only ever yields registered concepts.
                    defined_in_vocabulary=True,
                )
            )

    resolved.sort(key=lambda row: row.score, reverse=True)
    return resolved


def concept_assets(concept: str, tenant_ids: list[str] | None = None) -> Dict[str, Any]:
    """Describe one concept and the datasets it maps to, scoped to the caller.

    The concept vocabulary is shared, but ``dataset_ids`` is dataset identity.
    ``concept_dataset_index()`` is built from ``list_datasets()`` with no tenant predicate, so this
    returned every tenant's dataset ids - and ``POST /llm/search`` served it to a
    caller whose own policy decision said ``deny``. ``withheld_dataset_count``
    declares the truncation so a short list does not read as the whole mapping.
    """
    canonical = _canonicalize_concept(concept)
    datasets = concept_dataset_index().get(canonical, [])
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
    # The same predicate the publication gate applies, because ``suggestion``
    # *is* the definition (``_review_patch_locked`` passes it as one). The route
    # tested ``suggestion.strip()`` while the gate tested visibility, so a
    # suggestion of U+200B, U+FEFF, U+00AD or NUL was accepted into the shared
    # steward queue with 200 and could then **never** be approved: measured,
    # every approval answered 400 and the patch stayed ``proposed`` forever,
    # leaving a reviewer to reject a proposal the product itself accepted. One
    # predicate for one field, applied here so the library seam is covered and
    # not only the route.
    for field, value in (("concept", concept), ("suggestion", suggestion)):
        if not has_visible_character(value):
            raise ValueError(f"{field} must contain {PRESENCE_BASIS}")
    patch = OntologyPatch(
        id=str(uuid4()),
        concept=concept.strip() or "unknown",
        suggestion=suggestion.strip(),
        requestor=requestor,
        # No confidence is computed. ``min(max(len(suggestion) / 220.0, 0.3),
        # 0.95)`` stood here and published the proposal's character count as its
        # quality: measured, the same meaning padded to 208 characters scored
        # 0.94 against the precise 8-character form's 0.3, and 300 repeated
        # characters scored 0.95 - the top row of the unauthenticated
        # ``GET /enterprise/steward-review`` queue. Nothing here can know a
        # proposal's quality, so the row says so.
        confidence=None,
        confidence_basis=PATCH_CONFIDENCE_BASIS,
    )
    _ONTOLOGY_PATCHES.append(patch)
    if len(_ONTOLOGY_PATCHES) > MAX_ONTOLOGY_PATCHES:
        dropped = len(_ONTOLOGY_PATCHES) - MAX_ONTOLOGY_PATCHES
        del _ONTOLOGY_PATCHES[:-MAX_ONTOLOGY_PATCHES]
        _PATCH_QUEUE_STATE["withheld"] = int(_PATCH_QUEUE_STATE["withheld"]) + dropped
    # The queue's state travels with the accept because it is a fact about the
    # write the caller just performed: an accept that arrived at a full queue
    # displaced an older proposal, and no later read attributes that loss to
    # this write.
    #
    # An earlier version of this comment justified it differently - "the
    # proposer is the one party who cannot read the queue later and tell whether
    # their own row survived" - and the product refutes that. Measured: all six
    # subjects seeded in ``authz`` get 200 from both this route and
    # ``GET /ontology/patches``, the two gates resolve to one plane check, and
    # that route returns the whole queue with every row's ``id``, so a proposer
    # holding its own id reads presence or absence directly (a reviewed row
    # stays listed with status ``approved``, so absence means eviction). The
    # claim did not even hold at accept time: a freshly appended row always
    # survives the eviction of the oldest, so these three fields report
    # aggregate loss and never own-row survival. The real gap the counter closes
    # is the one ``review``'s 404 leaves: it cannot distinguish an evicted id
    # from one that never existed, and the aggregate is what distinguishes them.
    return {**patch.model_dump(), **patch_queue_state()}


def patch_queue_state() -> dict[str, Any]:
    """What the proposal queue holds, and what its cap dropped.

    Field-for-field the disclosure ``vocabulary_change_log`` publishes for the
    other evicting store in this package, so the two cannot describe the same
    kind of loss in two vocabularies. ``patch_queue_entry_count`` is the queue
    itself, never a filtered page: a ``?status=`` filter must not make the queue
    look smaller than it is.
    """
    withheld = int(_PATCH_QUEUE_STATE["withheld"])
    return {
        "patch_queue_entry_count": len(_ONTOLOGY_PATCHES),
        "withheld_patch_count": withheld,
        "patch_queue_is_truncated": withheld > 0,
    }


# What the published ``confidence`` on a patch row means, for every surface that
# carries it. One definition, so the route, the queue and the readiness surface
# cannot say different things about the same field.
PATCH_CONFIDENCE_BASIS = "not_measured"


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


def _mirror_concept_into_graph(registration: dict[str, Any]) -> dict[str, Any]:
    """Write the published concept into the graph store, as the direct route does.

    One helper so the two publication paths cannot drift again: whatever a
    publication means for the graph, it means it the same way from a steward
    approval and from a direct upsert. The record comes from the registrar, so
    the node's definition is the one the vocabulary actually holds.
    """
    from .graph_store import get_store

    return get_store().upsert_concept(
        {
            "concept": registration["concept"],
            "definition": registration.get("definition", ""),
            "aliases": list(registration.get("aliases", []) or []),
            "multilingual": list(registration.get("multilingual", []) or []),
            "broader": registration.get("broader"),
            "narrower": list(registration.get("narrower", []) or []),
            "related": list(registration.get("related", []) or []),
        }
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
            # 노출 stops short again, one surface family over. The comment above
            # records closing 제안 -> 승인 -> 노출 for the vocabulary reads, and
            # the registrar is indeed "the same registrar POST /ontology/concepts
            # uses" - but that route does *two* writes, the registrar and the
            # graph mirror, and only the first was shared. Measured: an approved
            # concept was listed by GET /ontology/concepts and present in the
            # JSON-LD export while GET /graph/nodes/<name> answered 404,
            # POST /graph/query and POST /search/semantic could not reach it, and
            # /graph/stats did not move - so the **governed** path produced a
            # concept the graph cannot see while the ungoverned direct upsert
            # produced one it can.
            #
            # Inside the lock, and before the status write, for the reason the
            # block above gives: a mirror that failed after the patch was marked
            # approved would leave 승인 recorded and 노출 missing, which is the
            # break this path exists to close. Lock order is vocabulary -> graph
            # and only ever that way; the store takes no ontology lock.
            #
            # The payload is built from the **registrar's** record rather than
            # the submission, the same correction the direct route carries: the
            # registrar keeps a stored definition and discards a re-submission,
            # so mirroring the proposal would leave the two disagreeing.
            _mirror_concept_into_graph(registration)

        patch.reviewed_by = reviewer
        patch.reviewed_at = datetime.now(timezone.utc)
        patch.review_comment = comment
        patch.status = "approved" if normalized == "approve" else "rejected"
        _ONTOLOGY_PATCHES[idx] = patch
        published = patch.model_dump()
        if registration is not None:
            # ``published_concept`` names a concept only when one was published.
            # It used to name it either way, so an approval that deliberately
            # kept the shipped definition answered ``published_concept: 고객``
            # with the revision and digest unchanged. ``concept`` still names
            # the subject of the review, so nothing is lost.
            published["publication_status"] = registration["publication_status"]
            published["published_concept"] = (
                registration["concept"]
                if registration["publication_status"] == PUBLICATION_PUBLISHED
                else None
            )
            published["concept_already_published"] = registration["already_published"]
            # ONT-005 asks for SHACL before merge. The gate runs inside
            # ``register_concept`` above - so a non-conforming concept raises
            # before the status write and the patch is never marked approved
            # with nothing published - and the report is published here so the
            # evaluation is observable rather than merely asserted.
            published["concept_validation"] = registration["concept_validation"]
        return published
    raise KeyError("patch not found")
