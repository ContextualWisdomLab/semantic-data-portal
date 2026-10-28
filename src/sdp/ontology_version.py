"""Version identity, a reviewed change log, and a versioned SKOS/RDFS export.

ONT-004 asks for three things over the domain ontology - "ontology version,
change log, reviewer 기록" - and the repository had none of them. The concept
vocabulary was a module-level Python dict with no release identity: two
deployments holding different concepts were indistinguishable, a publication
left no record of what changed, and the only reviewer identity anywhere was
``OntologyPatch.reviewed_by``, which exists solely on the patch path. The other
publication path, ``POST /ontology/concepts``, published into the shared
vocabulary every read surface consults with no review record at all - its one
audit row says ``result: "authorized"`` and is written **before** the mutation,
so it cannot attest that anything was published (measured: an alias-hijack POST
answered 400, published nothing, and left the identical "authorized" row).

The same capability was also published as true elsewhere. The ``rdf_connector``
control ``ontology_version_pin`` reported ``status: implemented`` with
``verification: proof_route_served`` and proof endpoints ``/ontology/search``
and ``/ontology/resolve`` - measured, neither response contained the string
"version" anywhere - while ``ONT-004`` was simultaneously recorded
``not_implemented`` for exactly that reason. Two published claims about one
capability contradicted each other; this module is what makes the connector
control's claim true rather than demoting it.

This module owns all of it, and deliberately does **not** import
``sdp.ontology``: the vocabulary is passed in. The dependency stays one-way
(``ontology`` -> ``ontology_version``) so the lock, the revision counter, the
digest and the serializer can live beside each other without a cycle.

Five honesty rules shape what is published:

* **The revision is process-local and says so.** The vocabulary is in-memory
  state lost on restart (see ``ontology.register_concept``), so ``revision 7``
  is not a durable release number and must not read as one.
  ``revision_is_durable: false`` and ``revision_scope: "process_lifetime"`` are
  published beside it, and the cross-process identity is the content digest.
* **A pin is matched on the digest only.** A client that pinned a revision and
  reconnected after a restart would be told its pin still holds over entirely
  different content - a pin that silently stops pinning. See
  ``version_pin_verdict``.
* **The digest is recomputed from live content, never cached.** A cached digest
  can drift from the dict it claims to describe. Recomputing lets the two be
  compared: ``digest_matches_recorded_revision`` is false exactly when the
  vocabulary was mutated outside the versioned path, which this surface reports
  rather than hides.
* **Only an effective change advances the revision.** ``register_concept`` on an
  already-published concept changes nothing (measured: it discards the whole
  submitted payload and returns the stored record), so it records nothing.
  Eviction at the vocabulary cap *is* a content change - a published term leaves
  the ontology as a side effect of an unrelated caller's success - so it is
  recorded, from inside the evicting function rather than at the routes.
* **A reviewer is never invented.** ``POST /ontology/concepts`` is a direct
  admin publication with nobody reviewing it, so its entry records
  ``reviewer_id: null`` and ``review_basis: "direct_admin_upsert"``, and
  ``record_vocabulary_change`` **refuses** a reviewer on any source that carries
  no review. Only an approved patch names a reviewer. (The same lesson as
  ``catalog.deprecate_dataset``, which used to default ``reason`` to
  ``"deprecated"`` and so reported a reason the caller never gave.)

Two limits of the version itself, declared rather than implied. It covers the
concept vocabulary and its alias index only: the concept-to-dataset map
(``ontology.concept_dataset_index()``) is derived from the catalog on read and no
revision tracks a change to it, so dataset mapping is **not** versioned here.
That map used to be an import-time snapshot as well, which is a different defect
and is fixed: a dataset published after startup never entered it, while the two
routes reading it declared that nothing was withheld. And there is no update event in
the change log because there is no update operation anywhere - a re-publication
of an existing concept is a no-op, not an edit.
"""

from __future__ import annotations

import hashlib
import json
import threading
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any

# The scheme every concept IRI is minted under. Kept identical to the term IRI
# ``ontology.resolve_terms`` already publishes, so the vocabulary export and the
# resolution response name the same thing.
ONTOLOGY_SCHEME_IRI = "https://data.example.org/vocabulary/sdp-domain"
ONTOLOGY_TERM_IRI_PREFIX = "https://data.example.org/term/"

# The shipped vocabulary is revision 1, not 0: a reader comparing two
# deployments needs the baseline itself to be a nameable revision.
BASELINE_REVISION = 1

# Bounded like every other process-lifetime store here (see
# ``ontology.MAX_ONTOLOGY_PATCHES`` and ``catalog.MAX_IN_MEMORY_AUDIT_EVENTS``).
# Eviction is declared through ``withheld_change_count`` rather than leaving a
# short log to read as the whole history.
MAX_ONTOLOGY_CHANGE_LOG_ENTRIES = 500

DIGEST_ALGORITHM = "sha256"

# The record fields whose order is **not** content. ``skos:altLabel``,
# ``skos:narrower`` and ``skos:related`` are unordered in RDF and the alias
# index treats a concept's own aliases as a set, so two deployments that list
# one concept's aliases in different orders hold the same vocabulary. Digesting
# the raw lists made them report different versions, which would refuse a
# client's pin over a difference with no meaning.
_UNORDERED_RECORD_FIELDS = ("aliases", "multilingual", "narrower", "related")

DIGEST_BASIS = (
    "sha256 over json.dumps(canonical, sort_keys=True, ensure_ascii=False, "
    "separators=(',', ':')), where `canonical` sorts the concept names and the "
    "multi-valued fields aliases/multilingual/narrower/related - these are "
    "unordered in meaning, so the digest is a semantic content identity rather "
    "than a serialization checksum. A client that pins the digest is pinning "
    "what the vocabulary means, not the order its lists happen to be in."
)

# Ordering a revision against another one is only meaningful within a process,
# and the arithmetic distance between two revisions counts *recorded changes*,
# not net content difference: a concept published at revision 5 and evicted at
# revision 6 moved the number by two and the content back to where it started.
# Identity is the digest; the revision is for ordering the log.
REVISION_COMPARISON_NOTE = (
    "revision ordering is total within one process lifetime only, and the "
    "distance between two revisions counts recorded changes rather than net "
    "content difference - compare content_digest for identity"
)

# ``actor_id`` comes from the request body and is checked against the subject
# table by the policy engine, so it is an **authorized** identity, not an
# authenticated one: this product has no end-user authentication on the write
# path. Published so a reader does not take a name in the log for a proven one.
ACTOR_IDENTITY_BASIS = "authorized_subject_claim"

REVISION_SCOPE = "process_lifetime"

# Every way the vocabulary can change, and what the change is called. Both sets
# are closed: ``record_vocabulary_change`` refuses an unknown value rather than
# recording a change whose kind or origin the reader cannot interpret.
CHANGE_KINDS = ("baseline", "concept_published", "concept_evicted")
CHANGE_SOURCES = ("seed", "concept_upsert", "patch_approval", "cap_eviction")

# What, if anything, reviewed each kind of change. A source with no review says
# so in words rather than leaving the reviewer field to be read as an omission.
REVIEW_BASES = {
    "seed": "shipped_vocabulary",
    "concept_upsert": "direct_admin_upsert",
    "patch_approval": "patch_review",
    "cap_eviction": "capacity_policy",
}

# The sources that carry a reviewer identity at all. ``record_vocabulary_change``
# refuses a reviewer on any other source, so a caller cannot stamp a steward on
# a publication nobody reviewed.
REVIEWED_SOURCES = ("patch_approval",)

# What ``actor_id`` means for each source. It is not the same thing in each: on
# a direct upsert the actor published the concept, but on an approved patch the
# actor *proposed* it and the person who authorized publication is in
# ``reviewer_id``. A reader scanning one column for "who put this in the
# ontology" would answer that wrongly for every approval, so each entry says
# which role its actor held rather than leaving the column to be interpreted.
ACTOR_ROLES = {
    "seed": None,
    "concept_upsert": "publisher",
    "patch_approval": "proposer",
    # Not someone who asked for a deletion: the caller whose own publication
    # filled the vocabulary and forced one out.
    "cap_eviction": "eviction_trigger",
}

_VOCABULARY_LOCK = threading.RLock()
_CHANGE_LOG: list[dict[str, Any]] = []
_REVISION_STATE: dict[str, Any] = {"revision": 0, "content_digest": "", "withheld": 0}


@contextmanager
def vocabulary_change_lock() -> Iterator[None]:
    """Hold the vocabulary lock across a caller-composed critical section.

    Reentrant, and shared with ``sdp.ontology``: publishing a concept is a
    read-modify-write over three stores (the vocabulary, the alias index and the
    revision counter), and an approval composes a fourth (the patch's status).
    Without one lock spanning all of them, two concurrent publications can read
    the same revision and both write it - so the counter advances once for two
    changes, and the change log and the vocabulary disagree permanently. This is
    the same defect ``catalog.catalog_mutation_lock`` exists to close, measured
    there as 50 concurrent patches advancing the version by 25.
    """
    with _VOCABULARY_LOCK:
        yield


def vocabulary_content_digest(vocabulary: Mapping[str, Any]) -> str:
    """The content identity of a vocabulary, independent of the process.

    This is the part of the version a reader can compare across deployments and
    across restarts; the revision cannot, because it is process-local.
    """
    canonical: dict[str, Any] = {}
    for concept, record in vocabulary.items():
        normalized = dict(record)
        for field in _UNORDERED_RECORD_FIELDS:
            value = normalized.get(field)
            if isinstance(value, list):
                normalized[field] = sorted(str(item) for item in value)
        canonical[concept] = normalized
    serialized = json.dumps(
        canonical, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


# The characters that cannot appear literally in an IRI path segment
# (RFC 3987 ``isegment``), plus ``%`` itself. ``%`` is escaped **first**, so the
# mapping is injective: every ``%`` in the output either introduces one of these
# escapes or is an escaped literal ``%``, and nothing else decodes to it.
_IRI_SEGMENT_ESCAPES = (
    ("%", "%25"),
    (" ", "%20"),
    ("/", "%2F"),
    ("?", "%3F"),
    ("#", "%23"),
    ("[", "%5B"),
    ("]", "%5D"),
)


def concept_iri(concept: str) -> str:
    """The IRI for one concept, minted the one way the product mints them.

    The previous form, ``concept.replace(" ", "-")``, was **not injective**:
    measured, the concept ``활성 고객`` and a separately registrable ``활성-고객``
    mint the identical IRI. In a resolution response that is a confusing
    identifier; in an RDF document it is worse, because two distinct concepts
    collapse into one subject and their definitions, labels and hierarchies
    merge. Percent-escaping the space keeps the two apart.

    ``urllib.parse.quote`` is deliberately not used: it percent-encodes every
    non-ASCII character, so ``고객`` would become ``%EA%B3%A0%EA%B0%9D`` and the
    export a buyer inspects would stop being readable. An IRI may carry Unicode
    (RFC 3987), so only the characters that genuinely cannot appear are escaped.
    """
    segment = concept
    for character, escape in _IRI_SEGMENT_ESCAPES:
        segment = segment.replace(character, escape)
    return f"{ONTOLOGY_TERM_IRI_PREFIX}{segment}"


def _now() -> str:
    """The recording moment, as an explicit UTC ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


def record_baseline(vocabulary: Mapping[str, Any]) -> dict[str, Any]:
    """Record the shipped vocabulary as revision 1. Called once, at import.

    The baseline is one entry rather than one per seeded concept: no actor
    published the shipped vocabulary, so five rows naming no actor would be five
    fabrications of a publication event that never happened. One entry says what
    is true - this content shipped with the product - and carries the concept
    count so a reader can see the baseline's size.
    """
    with _VOCABULARY_LOCK:
        _CHANGE_LOG.clear()
        _REVISION_STATE["revision"] = BASELINE_REVISION
        _REVISION_STATE["content_digest"] = vocabulary_content_digest(vocabulary)
        _REVISION_STATE["withheld"] = 0
        entry = {
            "change_revision": BASELINE_REVISION,
            "change_kind": "baseline",
            "change_source": "seed",
            "concept_name": None,
            "baseline_concept_count": len(vocabulary),
            "actor_id": None,
            "actor_role": ACTOR_ROLES["seed"],
            "reviewer_id": None,
            "review_basis": REVIEW_BASES["seed"],
            "recorded_at": _now(),
            "content_digest": _REVISION_STATE["content_digest"],
        }
        _CHANGE_LOG.append(entry)
        return dict(entry)


def record_vocabulary_change(
    *,
    change_kind: str,
    change_source: str,
    concept_name: str,
    vocabulary: Mapping[str, Any],
    actor_id: str | None = None,
    reviewer_id: str | None = None,
) -> dict[str, Any]:
    """Advance the revision for one effective change and log who made it.

    Call with ``vocabulary_change_lock`` held and **after** the vocabulary has
    been mutated, so the digest stamped into the entry is the content the
    revision names. Called before the mutation, the entry would claim a digest
    the vocabulary does not have, and a mutation that then failed would leave a
    revision describing content that was never published.

    Only an *effective* change gets here. ``register_concept`` on an
    already-published concept changes nothing and returns
    ``already_published: True``; advancing the revision for it would publish
    history for a no-op, the same defect the empty-``PATCH`` and
    already-deprecated guards in ``catalog`` exist to prevent.
    """
    if change_kind not in CHANGE_KINDS:
        raise ValueError(f"change_kind must be one of {CHANGE_KINDS!r}")
    if change_source not in CHANGE_SOURCES:
        raise ValueError(f"change_source must be one of {CHANGE_SOURCES!r}")
    if change_kind == "baseline":
        raise ValueError("the baseline is recorded by record_baseline, once")
    if reviewer_id is not None and change_source not in REVIEWED_SOURCES:
        # A reviewer on an unreviewed source would name a steward who never saw
        # the change. Refused rather than dropped, so the caller is told.
        raise ValueError(
            f"change_source {change_source!r} carries no review, so reviewer_id "
            f"must be None (reviewed sources: {REVIEWED_SOURCES!r})"
        )
    with _VOCABULARY_LOCK:
        revision = int(_REVISION_STATE["revision"]) + 1
        digest = vocabulary_content_digest(vocabulary)
        _REVISION_STATE["revision"] = revision
        _REVISION_STATE["content_digest"] = digest
        entry = {
            "change_revision": revision,
            "change_kind": change_kind,
            "change_source": change_source,
            "concept_name": concept_name,
            "actor_id": actor_id,
            "actor_role": ACTOR_ROLES[change_source],
            "reviewer_id": reviewer_id,
            "review_basis": REVIEW_BASES[change_source],
            "recorded_at": _now(),
            "content_digest": digest,
        }
        _CHANGE_LOG.append(entry)
        if len(_CHANGE_LOG) > MAX_ONTOLOGY_CHANGE_LOG_ENTRIES:
            dropped = len(_CHANGE_LOG) - MAX_ONTOLOGY_CHANGE_LOG_ENTRIES
            del _CHANGE_LOG[:dropped]
            _REVISION_STATE["withheld"] = int(_REVISION_STATE["withheld"]) + dropped
        return dict(entry)


def ontology_version_identity(vocabulary: Mapping[str, Any]) -> dict[str, Any]:
    """The published version identity, with every limitation named.

    Carries no actor or reviewer identity: those live in the change log, which
    is a governed read. This surface is the open half - what version of the
    vocabulary is live, and how far a reader may trust the number.
    """
    with _VOCABULARY_LOCK:
        live_digest = vocabulary_content_digest(vocabulary)
        recorded_digest = str(_REVISION_STATE["content_digest"])
        withheld = int(_REVISION_STATE["withheld"])
        return {
            "ontology_revision": int(_REVISION_STATE["revision"]),
            "baseline_revision": BASELINE_REVISION,
            "content_digest": live_digest,
            "recorded_content_digest": recorded_digest,
            # False exactly when the vocabulary was mutated outside the
            # versioned path. Reported, not hidden: a reader comparing two
            # deployments needs to know the revision stopped describing the
            # content it names.
            "digest_matches_recorded_revision": live_digest == recorded_digest,
            "digest_algorithm": DIGEST_ALGORITHM,
            "digest_basis": DIGEST_BASIS,
            "concept_count": len(vocabulary),
            "revision_scope": REVISION_SCOPE,
            "revision_comparison_note": REVISION_COMPARISON_NOTE,
            # The revision restarts at the baseline on restart, because the
            # vocabulary does. Declared so it cannot read as a release number.
            "revision_is_durable": False,
            "change_log_entry_count": len(_CHANGE_LOG),
            "change_log_capacity": MAX_ONTOLOGY_CHANGE_LOG_ENTRIES,
            "withheld_change_count": withheld,
            "change_log_is_truncated": withheld > 0,
            "known_change_kinds": list(CHANGE_KINDS),
            "known_change_sources": list(CHANGE_SOURCES),
            "reviewed_change_sources": list(REVIEWED_SOURCES),
            "actor_roles_by_change_source": dict(ACTOR_ROLES),
        }


def vocabulary_change_log(limit: int = 100) -> dict[str, Any]:
    """The change log, newest first, bounded by ``limit``.

    Carries actor and reviewer identity per entry, so the route serving it is a
    governed read (see ``api.ontology_change_log``).
    """
    with _VOCABULARY_LOCK:
        page = [dict(entry) for entry in reversed(_CHANGE_LOG[-max(limit, 0):])] if limit > 0 else []
        return {
            "count": len(page),
            "changes": page,
            "change_log_entry_count": len(_CHANGE_LOG),
            "withheld_change_count": int(_REVISION_STATE["withheld"]),
            "change_log_is_truncated": int(_REVISION_STATE["withheld"]) > 0,
            # A name in this log is an authorized claim, not an authenticated
            # one. Declared so a reader does not take it for proof of identity.
            "actor_identity_basis": ACTOR_IDENTITY_BASIS,
        }


# A pinned version is matched on the **content digest only**, never on the
# revision. The revision is process-local: a client that pinned ``revision=3``
# and reconnected after a restart would be told its pin still holds while the
# vocabulary behind it is entirely different content, which is a pin that
# silently stops pinning. The digest is the identity that survives a restart, so
# it is the only thing a caller may pin on.
PIN_PARAMETER = "ontology_content_digest"
PIN_BASIS = "content_digest_only"
PIN_REVISION_IS_PINNABLE = False
_DIGEST_LENGTH = 64
_DIGEST_CHARACTERS = frozenset("0123456789abcdef")


def validate_pinned_digest(requested: str) -> str:
    """Return the requested digest, or raise ``ValueError`` if it is malformed.

    Separated from the comparison because the two refusals mean different
    things and must not share a status: a malformed digest is a bad request
    (400), while a well-formed digest that names another version of the
    vocabulary is a conflict (409). Collapsing them would tell a client with a
    typo that the server holds a different vocabulary, and a client holding a
    genuinely older vocabulary that its request was malformed.
    """
    # Case-folded before the check, and the message says so: a hexadecimal
    # digest is case-insensitive, and a rule that reads "lowercase" while the
    # code accepts upper case is the same published-claim drift this product
    # exists to refuse.
    candidate = requested.strip().lower()
    if len(candidate) != _DIGEST_LENGTH or not set(candidate) <= _DIGEST_CHARACTERS:
        raise ValueError(
            f"{PIN_PARAMETER} must be {_DIGEST_LENGTH} hexadecimal characters, "
            f"case-insensitive ({DIGEST_ALGORITHM})"
        )
    return candidate


def version_pin_verdict(
    requested: str | None, vocabulary: Mapping[str, Any]
) -> dict[str, Any]:
    """Whether a caller's pinned vocabulary digest is the one being served.

    ``ontology_version_pin`` was published as an ``implemented`` connector
    control whose proof endpoints were ``/ontology/search`` and
    ``/ontology/resolve`` - measured, neither response contained the string
    "version" anywhere, so the control's own proof routes proved nothing about
    it, while ``ONT-004`` was simultaneously recorded ``not_implemented`` for
    exactly that reason. Two published claims about the same capability
    contradicted each other.

    This is the predicate behind the real control: the routes stamp the version
    they answered from, and a caller may pin the digest it compiled against and
    be **refused** rather than silently served a different vocabulary. Returned
    rather than raised on a mismatch, so the caller is told both digests.

    A pin can be invalidated by something the pinning client never asked for and
    cannot predict: at the vocabulary cap another caller's publication evicts a
    term, which is a real content change recorded as ``cap_eviction``. The open
    version surface publishes ``known_change_sources`` so that reason is
    discoverable without the governed change log.
    """
    live = vocabulary_content_digest(vocabulary)
    if requested is None:
        return {
            "pin_requested": False,
            "pin_matches": True,
            "live_content_digest": live,
            "pin_basis": PIN_BASIS,
            "revision_is_pinnable": PIN_REVISION_IS_PINNABLE,
        }
    pinned = validate_pinned_digest(requested)
    return {
        "pin_requested": True,
        "pin_matches": pinned == live,
        "requested_content_digest": pinned,
        "live_content_digest": live,
        "pin_basis": PIN_BASIS,
        "revision_is_pinnable": PIN_REVISION_IS_PINNABLE,
    }


def version_pin_is_enforced(vocabulary: Mapping[str, Any]) -> dict[str, Any]:
    """Probe the pin predicate in both directions, for the connector control.

    ``connector_probe`` grades a control ``implemented`` when this build serves
    every route the control names. That is a fact about the build, but it is not
    a fact about the control: ``ontology_version_pin`` passed it while no route
    carried a version at all. This returns a verdict that can come out **false**
    - it pins the live digest (which must match) and a digest that differs by
    one character (which must not) - so the control can be graded
    ``runtime_probe_verified`` on evidence rather than on route existence.
    """
    live = vocabulary_content_digest(vocabulary)
    wrong = ("0" if live[0] != "0" else "1") + live[1:]
    try:
        accepts_live = bool(version_pin_verdict(live, vocabulary)["pin_matches"])
        refuses_other = not version_pin_verdict(wrong, vocabulary)["pin_matches"]
        rejects_malformed = False
        try:
            validate_pinned_digest("not-a-digest")
        except ValueError:
            rejects_malformed = True
    except ValueError:  # pragma: no cover - a live digest is well-formed
        return {
            "enforced": False,
            "gap_reason": "the live content digest is not a valid pin value",
        }
    enforced = accepts_live and refuses_other and rejects_malformed
    verdict: dict[str, Any] = {
        "enforced": enforced,
        "accepts_the_live_digest": accepts_live,
        "refuses_a_different_digest": refuses_other,
        "rejects_a_malformed_digest": rejects_malformed,
        "pin_parameter": PIN_PARAMETER,
        "pin_basis": PIN_BASIS,
    }
    if not enforced:
        verdict["gap_reason"] = "the version pin predicate did not hold in both directions"
    return verdict


# The vocabularies the export uses, inline so the document is self-describing
# and needs no network fetch - the same reason the DCAT export's context is
# inline (``api.JSONLD_CONTEXT``), and the same product namespace.
#
# Only terms with an honest mapping appear. A concept record's ``aliases`` and
# ``multilingual`` lists are both alternate labels, so both map to
# ``skos:altLabel``; nothing in a record expresses an OWL axiom, so no
# ``owl:Class``, ``owl:ObjectProperty`` or restriction is emitted and
# ``owl:versionInfo`` is the only owl: term used. Claiming more would publish a
# formal ontology this product does not have (see ONT-007: no reasoner).
VOCABULARY_JSONLD_CONTEXT: dict[str, Any] = {
    "skos": "http://www.w3.org/2004/02/skos/core#",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "owl": "http://www.w3.org/2002/07/owl#",
    "dcterms": "http://purl.org/dc/terms/",
    "sdp": "https://semantic-data-portal.local/ns#",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
    "label": "rdfs:label",
    "prefLabel": "skos:prefLabel",
    "altLabel": "skos:altLabel",
    "definition": "skos:definition",
    "inScheme": {"@id": "skos:inScheme", "@type": "@id"},
    "hasTopConcept": {"@id": "skos:hasTopConcept", "@type": "@id"},
    "broader": {"@id": "skos:broader", "@type": "@id"},
    "narrower": {"@id": "skos:narrower", "@type": "@id"},
    "related": {"@id": "skos:related", "@type": "@id"},
    "versionInfo": "owl:versionInfo",
    "modified": {"@id": "dcterms:modified", "@type": "xsd:dateTime"},
    # Product-local, because no standard predicate says "this vocabulary names
    # a term it never defines" or "this revision is process-local". Declared in
    # the context so an RDF processor keeps them as triples instead of dropping
    # them as unmapped keys - which is the exact defect the DCAT export was
    # fixed for.
    "ontologyRevision": {"@id": "sdp:ontologyRevision", "@type": "xsd:integer"},
    "contentDigest": "sdp:contentDigest",
    "revisionIsDurable": {"@id": "sdp:revisionIsDurable", "@type": "xsd:boolean"},
    "undefinedHierarchyTarget": "sdp:undefinedHierarchyTarget",
    "undefinedHierarchyTargetCount": {
        "@id": "sdp:undefinedHierarchyTargetCount",
        "@type": "xsd:integer",
    },
    "aliasResolvedHierarchyTarget": "sdp:aliasResolvedHierarchyTarget",
    "datasetMappingIsVersioned": {
        "@id": "sdp:datasetMappingIsVersioned",
        "@type": "xsd:boolean",
    },
}

HIERARCHY_RELATIONS = ("broader", "narrower", "related")


def _hierarchy_targets(record: Mapping[str, Any], relation: str) -> list[str]:
    """The declared targets of one relation, as a list in either shape.

    ``broader`` is a single value or ``None``; ``narrower`` and ``related`` are
    lists. Normalizing here keeps the serializer from branching per relation.
    """
    if relation == "broader":
        target = record.get("broader")
        return [target] if target else []
    return [target for target in list(record.get(relation) or []) if target]


def vocabulary_jsonld(
    vocabulary: Mapping[str, Any],
    *,
    resolve_concept: Any,
) -> dict[str, Any]:
    """Serialize the vocabulary as a versioned SKOS/RDFS JSON-LD document.

    ONT-004's subject is an "OWL/RDFS 기반 도메인 ontology", and before this
    there was no RDF artifact at all: the vocabulary existed only as a Python
    dict, the DCAT export covers datasets rather than concepts, and
    ``mappings[].concept`` in that export is a plain literal, so no triple
    anywhere linked a dataset to a concept. A revision number on a dict is not a
    versioned ontology; this is the artifact the revision names.

    Three deliberate limits, each declared in the document rather than left for
    a reader to discover:

    * **Hierarchy targets that resolve to nothing are not minted.** Measured on
      the shipped vocabulary: 19 ``broader``/``narrower``/``related`` edges name
      13 distinct targets. **10 of the 19 edges name a target the vocabulary
      never defines**, over 9 distinct undefined names (구매 - which two
      concepts both name - 거래, 회원가입, 구매자, 재구매, 가입자, 매출 성장,
      매출 채널별 집계, 가격), and one further edge names an **alias only**
      (활성 고객 related 휴면 고객, an alias of 이탈 고객). Emitting
      ``skos:broader`` to an IRI
      for a concept that does not exist would publish 9 subjects with no
      definition, so the undefined targets are published under
      ``sdp:undefinedHierarchyTarget`` with a count, and the alias is resolved
      through the alias index so the triple points at the real concept.
    * **No dataset ids.** The concept-to-dataset map is built with no tenant predicate,
      and serving it is exactly how ``concept_assets`` leaked every tenant's
      dataset ids to a caller its own policy decision denied. This document is
      open, so it carries the vocabulary only; the concept-to-dataset mapping
      stays a governed read (``GET /ontology/concept/{term}``).
      ``sdp:datasetMappingIsVersioned false`` says so in the document.
    * **The revision is process-local.** ``owl:versionInfo`` carries the content
      digest as well as the revision, because the digest is the part that
      survives a restart, and ``sdp:revisionIsDurable false`` keeps the number
      from reading as a release.
    """
    identity = ontology_version_identity(vocabulary)
    concepts: list[dict[str, Any]] = []
    top_concepts: list[str] = []
    undefined: list[str] = []
    alias_resolved: list[str] = []

    for concept in sorted(vocabulary):
        record = vocabulary[concept]
        node: dict[str, Any] = {
            "@id": concept_iri(concept),
            "@type": "skos:Concept",
            "inScheme": ONTOLOGY_SCHEME_IRI,
            # Both, deliberately: a SKOS consumer reads ``skos:prefLabel`` and
            # an RDFS consumer reads ``rdfs:label``, and the requirement names
            # RDFS as well as the SKOS hierarchy.
            "prefLabel": concept,
            "label": concept,
        }
        definition = str(record.get("definition", "")).strip()
        if definition:
            node["definition"] = definition
        # ``aliases`` and ``multilingual`` both hold alternate labels and they
        # overlap - 고객 declares "customer" in each - so the union is
        # de-duplicated in declaration order rather than publishing the same
        # literal twice.
        #
        # No ``@language`` tag is asserted on any label. The record does not
        # separate labels by language: 고객's ``aliases`` holds 클라이언트 and
        # customer side by side, so tagging the list ``@ko`` would be false for
        # some entries and guessing per entry would be a language claim this
        # product does not make.
        alt_labels: list[str] = []
        for label in list(record.get("aliases") or []) + list(
            record.get("multilingual") or []
        ):
            text = str(label).strip()
            if text and text != concept and text not in alt_labels:
                alt_labels.append(text)
        if alt_labels:
            node["altLabel"] = alt_labels

        for relation in HIERARCHY_RELATIONS:
            resolved: list[str] = []
            for target in _hierarchy_targets(record, relation):
                canonical = resolve_concept(target)
                if canonical is None:
                    undefined.append(f"{concept} {relation} {target}")
                    continue
                if canonical != target:
                    alias_resolved.append(f"{concept} {relation} {target} -> {canonical}")
                iri = concept_iri(canonical)
                if iri not in resolved:
                    resolved.append(iri)
            if resolved:
                node[relation] = resolved

        if not _hierarchy_targets(record, "broader"):
            top_concepts.append(concept_iri(concept))
        concepts.append(node)

    scheme: dict[str, Any] = {
        "@id": ONTOLOGY_SCHEME_IRI,
        "@type": "skos:ConceptScheme",
        "label": "Semantic Data Portal 도메인 어휘",
        "versionInfo": (
            f"revision={identity['ontology_revision']}; "
            f"{DIGEST_ALGORITHM}={identity['content_digest']}"
        ),
        "ontologyRevision": identity["ontology_revision"],
        "contentDigest": identity["content_digest"],
        "revisionIsDurable": False,
        "datasetMappingIsVersioned": False,
        # Edges, not distinct names: 구매 is named by two concepts, so 10 edges
        # carry 9 distinct undefined targets and both numbers are readable (the
        # list is published beside the count).
        "undefinedHierarchyTargetCount": len(undefined),
    }
    if top_concepts:
        scheme["hasTopConcept"] = top_concepts
    if undefined:
        scheme["undefinedHierarchyTarget"] = sorted(undefined)
    if alias_resolved:
        scheme["aliasResolvedHierarchyTarget"] = sorted(alias_resolved)
    last_change = _last_change_moment()
    if last_change:
        scheme["modified"] = last_change

    return {
        "@context": VOCABULARY_JSONLD_CONTEXT,
        "@graph": [scheme, *concepts],
    }


def _last_change_moment() -> str | None:
    """The recording moment of the newest change, or ``None`` on an empty log."""
    with _VOCABULARY_LOCK:
        if not _CHANGE_LOG:
            return None
        return str(_CHANGE_LOG[-1]["recorded_at"])
