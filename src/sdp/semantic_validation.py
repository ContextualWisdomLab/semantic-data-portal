from __future__ import annotations

import unicodedata
from collections.abc import Callable, Mapping
from typing import Any

from sdp_core import MappingStatus
from sdp_core.contracts import REQUIRED_METADATA_FIELDS

from .catalog import get_dataset, list_datasets, validate_metadata
from .graph_store import CONCEPT_NODE_KIND, HIERARCHY_EDGE_TYPES


# The shape catalog is published by ``/catalog/datasets/{id}/semantic-validation``
# and ``/enterprise/shacl-validation``, and none of it was evaluated. A reader
# takes ``required_properties`` for the constraint that produced ``conforms``.
# Measured at HEAD before this repair:
#
#   DistributionShape, a distribution with format="" and endpoint="":
#       conforms = True, violations = []
#   BusinessMappingShape, a mapping with concept="":
#       conforms = True, no violation names "concept"
#   DatasetShape.required_properties
#       = [owner, steward, domain, source_system, schema, distributions]
#   the list actually enforced (REQUIRED_METADATA_FIELDS)
#       additionally requires description, sensitivity, title, update_frequency
#
# So the catalog was wrong in both directions at once: it named properties
# nothing checked, and omitted properties that were checked. What ran instead was
# three hand-written rules - missing metadata fields, "at least one approved
# mapping", "terms recommended" - whose relationship to the published shapes was
# only that two of them borrowed a shape id for the ``shape`` field.
#
# Every published property is now evaluated by the entry that declares it, and
# ``DatasetShape`` derives its list from ``REQUIRED_METADATA_FIELDS`` rather than
# repeating it, so the published and enforced lists cannot drift again (the same
# single-source fix ``metadata_completeness`` already uses).
#
# The approved-mapping rule is a *cardinality* constraint, not a property
# presence check, so it is declared as one instead of hiding inside
# ``required_properties`` - a reader of the old catalog could not have known that
# ``BusinessMappingShape`` enforced "at least one approved" and not
# "concept and status are present".
# Unicode general categories whose members are invisible: separators (Zs line
# Zl paragraph Zp), control (Cc) and format (Cf). A value made only of these is
# not a present value, whatever ``str.strip()`` thinks.
_INVISIBLE_CATEGORIES = frozenset({"Zs", "Zl", "Zp", "Cc", "Cf"})

# The one bound both publication paths use. Imported from the ontology module's
# constant would be a cycle, so the value lives here and ``ontology`` reads it -
# a single source either way, and this is the module that publishes it.
MAX_PUBLISHED_FIELD_LENGTH = 2000

PRESENCE_BASIS = (
    "at least one character outside the Unicode separator (Zs/Zl/Zp) and "
    "control/format (Cc/Cf) categories - str.strip() alone accepts a value "
    "made only of U+200B, U+00AD, U+FEFF or NUL, which renders as blank"
)


def has_visible_character(value: Any) -> bool:
    """Whether a value carries at least one character a reader can see.

    Shared with ``sdp.ontology``, which applies it to the concept **name** for
    the same reason: measured, ``POST /ontology/concepts`` published concepts
    named U+200B, U+FEFF and NUL because the only check was a non-empty
    ``.strip()``.
    """
    if value is None:
        return False
    return any(
        unicodedata.category(character) not in _INVISIBLE_CATEGORIES
        for character in str(value)
    )


_SHACL_COMPATIBLE_SHAPES = [
    {
        "id": "DatasetShape",
        "target": "Dataset",
        # Single source with the validator; see REQUIRED_METADATA_FIELDS.
        "required_properties": list(REQUIRED_METADATA_FIELDS),
    },
    {
        "id": "BusinessMappingShape",
        "target": "BusinessMapping",
        "required_properties": ["concept", "status"],
        "min_approved_count": 1,
        "recommended_properties": ["terms"],
    },
    {
        "id": "DistributionShape",
        "target": "DatasetDistribution",
        "required_properties": ["format", "endpoint"],
    },
    # ONT-005's acceptance criterion is "reasoner + SHACL + reviewer 승인 후 병합"
    # and reviewer approval was the whole gate: ``review_patch`` went straight
    # from an approve decision to ``register_concept``, whose checks are
    # non-empty name, length, alias conflict and the vocabulary cap. Nothing
    # looked at the concept being published, and there was no concept-targeting
    # shape in this catalog at all.
    #
    # Measured before this shape, over HTTP:
    #
    #     POST /ontology/concepts {"actor": "admin", "concept": "정의누락개념"}
    #         -> 200, stored definition = ''
    #     GET  /ontology/search?q=정의누락개념   -> count 1, definition = ''
    #     GET  /ontology/concept/정의누락개념    -> definition = ''
    #
    # So the shared glossary every read surface consults could hold a concept
    # with **no definition**, published through an authorized route, and a
    # glossary whose terms have no definitions is not a glossary.
    #
    # ``definition`` is the only property that can honestly be *required*: a
    # top concept legitimately has no ``broader``, and a leaf legitimately has
    # no ``narrower``, so requiring either would refuse correct vocabulary.
    # ``aliases`` is recommended rather than required for the same reason.
    #
    # ``resolvable_hierarchy_targets`` is a ``sh:class``-shaped constraint - a
    # hierarchy target must itself be a Concept - and it is declared at
    # **warning** severity because the shipped vocabulary violates it: measured,
    # 10 of the 19 broader/narrower/related edges in the seed name a target the
    # vocabulary never defines. A constraint that refuses the product's own
    # seed cannot gate publication, and raising it to a violation would make
    # ``conforms`` false for five shipped concepts. Declared and reported is
    # the honest strength.
    {
        "id": "ConceptShape",
        "target": "Concept",
        "required_properties": ["definition"],
        "recommended_properties": ["aliases"],
        "resolvable_hierarchy_targets": ["broader", "narrower", "related"],
        # ``definition`` was mandatory-to-supply and unbounded: measured, a
        # 2,000,000-character definition was accepted and stored in full, in a
        # 500-slot process-lifetime vocabulary. The concept *name* is bounded at
        # MAX_ONTOLOGY_PATCH_FIELD three lines from the gate, and the patch path
        # bounds the same field (a 2001-character suggestion is refused at
        # intake), so this change had made a field required on the one path that
        # did not bound it. The bound is published here and enforced from here,
        # by the single constant both paths use.
        "max_property_length": MAX_PUBLISHED_FIELD_LENGTH,
        # The published rule for "present", because ``str.strip()`` is not it.
        # ``strip`` removes only characters ``str.isspace()`` accepts, and the
        # Unicode format category is not whitespace - measured, a definition of
        # a single U+200B, U+200C, U+00AD, U+200E, U+2060, U+FEFF or NUL passed
        # the first version of this gate and ``/ontology/search`` then served a
        # definition that renders as blank. This is stricter than
        # ``sh:minCount 1`` (which an invisible literal satisfies) and is
        # published so the enforced rule and the declared one are the same rule.
        "required_property_basis": PRESENCE_BASIS,
    },
    # ONT-002's acceptance criterion is "table/dataset이 business class의
    # subclass가 되지 않도록 SHACL/OWL 검증", and no shape, axiom or reasoner
    # expressed a class hierarchy anywhere in this repository - the kinds were
    # modelled and nothing verified them. This is that constraint: a
    # ``sh:class``-shaped rule on **both endpoints** of a subsumption relation.
    #
    # It is a *violation*, not a warning, and the difference from
    # ConceptShape's ``resolvable_hierarchy_targets`` (which is a warning for the
    # documented reason that the shipped vocabulary breaks it 10 times) is that
    # these two constraints answer different questions about the same edge:
    #
    #   target does not exist                 -> unknown, warning
    #   target exists and is a dataset/column -> a class-separation violation
    #
    # Nothing is unknown about the second one, and the shipped graph contains
    # none: measured, all 7 hierarchy edges touching the vocabulary run
    # concept -> concept, and the 2 that name a missing target are the warning
    # case. So this constraint can be a violation without refusing the product's
    # own seed, which is exactly the test the ConceptShape comment applies.
    {
        "id": "ConceptHierarchyShape",
        "target": "ConceptHierarchyEdge",
        # No ``required_properties`` key at all: this shape constrains the
        # *class* of the nodes a relation connects, not the properties they
        # carry, and each entry in this catalog declares only the constraints it
        # has (DatasetShape declares no ``min_approved_count``; DistributionShape
        # no ``recommended_properties``). Declaring an empty list instead would
        # also have widened the derived response contract for every shape's
        # ``required_properties`` from "array of string" to "array of anything".
        "hierarchy_relations": list(HIERARCHY_EDGE_TYPES),
        "required_endpoint_kind": CONCEPT_NODE_KIND,
        "unknown_endpoint_severity": "warning",
    },
]

# Which shapes this validator actually evaluates. ``shacl_compatible`` was a
# hardcoded ``True``; it is now derived from this set, so publishing a shape
# without evaluating it makes the claim false instead of leaving it unchanged.
_EVALUATED_SHAPE_IDS = frozenset(
    {
        "DatasetShape",
        "BusinessMappingShape",
        "DistributionShape",
        "ConceptShape",
        "ConceptHierarchyShape",
    }
)

# Which shapes each report actually applies. ``shapes`` publishes the whole
# catalog, and this module's own history is the reason that is not enough: a
# reader takes the published shape list for the constraints that produced
# ``conforms``. With a concept shape in the catalog, a dataset report that
# published the catalog alone would read as having validated a dataset against
# ConceptShape. Each report now names the shapes it evaluated.
_DATASET_REPORT_SHAPE_IDS = ("DatasetShape", "BusinessMappingShape", "DistributionShape")
_CONCEPT_REPORT_SHAPE_IDS = ("ConceptShape",)
_HIERARCHY_REPORT_SHAPE_IDS = ("ConceptHierarchyShape",)

# No SHACL engine runs here. ``pyshacl`` is not a dependency of this repository
# (it pulls an RDF stack, and CI installs from hash-pinned requirements), so the
# claim this surface can honestly make is that the published shapes are
# SHACL-expressible and are enforced by equivalent in-process checks - not that a
# SHACL processor validated the graph. Both facts are now published, because
# "shacl_compatible: true" alone reads as the second one.
VALIDATION_ENGINE = "builtin_shape_checks"
SHACL_ENGINE_EXECUTED = False


def _shacl_compatible() -> bool:
    """Whether every published shape is one this validator evaluates."""
    return all(shape["id"] in _EVALUATED_SHAPE_IDS for shape in _SHACL_COMPATIBLE_SHAPES)


def _shape(shape_id: str) -> dict[str, Any]:
    """The published shape with this id."""
    return next(shape for shape in _SHACL_COMPATIBLE_SHAPES if shape["id"] == shape_id)


def _missing_node_properties(
    node: Any, shape_id: str, path_prefix: str
) -> list[dict[str, str]]:
    """Violations for every ``required_properties`` entry absent on one node.

    Paths are indexed (``distributions[0].format``) so a report names which
    member of a repeated property failed, which a bare property name cannot.
    """
    return [
        {
            "shape": shape_id,
            "path": f"{path_prefix}.{prop}",
            "severity": "violation",
            "message": f"required property is missing: {path_prefix}.{prop}",
        }
        for prop in _shape(shape_id)["required_properties"]
        if not getattr(node, prop, None)
    ]


def validate_dataset_semantics(dataset_id: str) -> dict[str, Any]:
    dataset = get_dataset(dataset_id)
    if not dataset:
        raise KeyError(dataset_id)

    violations: list[dict[str, str]] = []
    metadata = validate_metadata(dataset)
    # ``validate_metadata`` enumerates REQUIRED_METADATA_FIELDS, which is exactly
    # DatasetShape.required_properties - one list, read twice.
    for field in metadata["missing"]:
        violations.append(
            {
                "shape": "DatasetShape",
                "path": field,
                "severity": "violation",
                "message": f"required metadata field is missing: {field}",
            }
        )

    # Every repeated node the catalog declares a shape for, evaluated against
    # that shape's own property list. ``or []`` keeps the validator total for a
    # dataset whose list field is ``None``: the API cannot produce one
    # (``Dataset`` declares both as ``list[...]`` with a default factory, and
    # ``patch_dataset`` drops ``None`` before ``model_validate``), but
    # ``validate_metadata`` already tolerates it via its falsy check, and a
    # validator that raises TypeError where its sibling reports a violation is
    # the worse of the two failure modes.
    for index, mapping in enumerate(dataset.mappings or []):
        violations.extend(
            _missing_node_properties(mapping, "BusinessMappingShape", f"mappings[{index}]")
        )
    for index, distribution in enumerate(dataset.distributions or []):
        violations.extend(
            _missing_node_properties(
                distribution, "DistributionShape", f"distributions[{index}]"
            )
        )

    approved_mappings = [mapping for mapping in dataset.mappings if mapping.status == MappingStatus.APPROVED]
    minimum_approved = _shape("BusinessMappingShape")["min_approved_count"]
    if len(approved_mappings) < minimum_approved:
        violations.append(
            {
                "shape": "BusinessMappingShape",
                "path": "mappings",
                "severity": "violation",
                "message": (
                    f"at least {minimum_approved} approved business mapping is required"
                ),
            }
        )

    if not dataset.terms:
        violations.append(
            {
                "shape": "BusinessMappingShape",
                "path": "terms",
                "severity": "warning",
                "message": "at least one searchable business term is recommended",
            }
        )

    return {
        "dataset_id": dataset.id,
        # Derived from the evaluated-shape set, not asserted.
        "shacl_compatible": _shacl_compatible(),
        "validation_engine": VALIDATION_ENGINE,
        "shacl_engine_executed": SHACL_ENGINE_EXECUTED,
        "conforms": not any(item["severity"] == "violation" for item in violations),
        "shapes": _SHACL_COMPATIBLE_SHAPES,
        # Not the whole catalog: ConceptShape targets a concept and is not
        # applied to a dataset. See ``_DATASET_REPORT_SHAPE_IDS``.
        "evaluated_shapes": list(_DATASET_REPORT_SHAPE_IDS),
        "violations": violations,
        "approved_mapping_count": len(approved_mappings),
        "metadata_completeness": dataset.metadata_completeness,
    }


CONCEPT_CONFORMANCE_SCOPE = (
    "published_vocabulary - concepts in ontology._CONCEPT_DEFINITIONS; a "
    "kind=\"concept\" graph node written directly through POST /graph/nodes is "
    "not in the vocabulary and is not counted"
)


def _concept_hierarchy_targets(record: Mapping[str, Any], relation: str) -> list[str]:
    """One relation's declared targets, as a list in either shape.

    ``broader`` is a scalar or ``None``; ``narrower`` and ``related`` are lists.
    """
    if relation == "broader":
        target = record.get("broader")
        return [target] if target else []
    return [target for target in list(record.get(relation) or []) if target]


def validate_concept_semantics(
    concept: str,
    record: Mapping[str, Any],
    *,
    resolve_concept: Callable[[str], str | None],
    evaluated_record: str = "submitted",
) -> dict[str, Any]:
    """Evaluate ConceptShape against one concept record.

    Pure, and takes its resolver as an argument, so ``sdp.ontology`` can call it
    on the publication path without this module importing the vocabulary it is
    validating.

    ``conforms`` counts violations only, exactly as the dataset report does, so a
    hierarchy target that resolves to nothing is reported without refusing a
    publication - see the ConceptShape comment for why that constraint cannot be
    a violation in this product.
    """
    shape = _shape("ConceptShape")
    violations: list[dict[str, str]] = []

    for prop in shape["required_properties"]:
        if not has_visible_character(record.get(prop)):
            violations.append(
                {
                    "shape": "ConceptShape",
                    "path": prop,
                    "severity": "violation",
                    "message": f"required property is missing: {prop}",
                }
            )
        elif len(str(record.get(prop))) > shape["max_property_length"]:
            violations.append(
                {
                    "shape": "ConceptShape",
                    "path": prop,
                    "severity": "violation",
                    "message": (
                        f"property is longer than "
                        f"{shape['max_property_length']} characters: {prop}"
                    ),
                }
            )

    for prop in shape["recommended_properties"]:
        if not record.get(prop):
            violations.append(
                {
                    "shape": "ConceptShape",
                    "path": prop,
                    "severity": "warning",
                    "message": f"property is recommended: {prop}",
                }
            )

    for relation in shape["resolvable_hierarchy_targets"]:
        for target in _concept_hierarchy_targets(record, relation):
            if resolve_concept(target) is None:
                violations.append(
                    {
                        "shape": "ConceptShape",
                        "path": relation,
                        "severity": "warning",
                        "message": (
                            f"hierarchy target is not a registered concept: "
                            f"{relation} -> {target}"
                        ),
                    }
                )

    return {
        "concept": concept,
        "shacl_compatible": _shacl_compatible(),
        "validation_engine": VALIDATION_ENGINE,
        "shacl_engine_executed": SHACL_ENGINE_EXECUTED,
        "evaluated_shapes": list(_CONCEPT_REPORT_SHAPE_IDS),
        # Which record this verdict is about. On a re-publication the submitted
        # payload is discarded and the stored record is what remains, so a
        # report that did not say which one it read let a 200 response carry
        # ``conforms: true`` about content the caller never sent and
        # ``definition`` about content that was never stored. The same
        # discipline as ``evaluated_shapes``, for the subject rather than the
        # constraints.
        "evaluated_record": evaluated_record,
        "conforms": not any(item["severity"] == "violation" for item in violations),
        "violations": violations,
    }


def concept_vocabulary_conformance(
    vocabulary: Mapping[str, Any],
    *,
    resolve_concept: Callable[[str], str | None],
) -> dict[str, Any]:
    """ConceptShape conformance across the whole vocabulary.

    Published on ``/enterprise/shacl-validation`` so the shape's effect is
    measurable platform-wide. Warning counts are published separately from
    conformance, because the shipped vocabulary carries warnings by design and a
    single number would hide which kind of finding it counts.
    """
    reports = [
        validate_concept_semantics(concept, record, resolve_concept=resolve_concept)
        for concept, record in sorted(vocabulary.items())
    ]
    conforming = sum(1 for report in reports if report["conforms"])
    total = len(reports)
    warnings = sum(
        1
        for report in reports
        for violation in report["violations"]
        if violation["severity"] == "warning"
    )
    return {
        "concept_count": total,
        "conforming_concepts": conforming,
        "concept_pass_rate": round(conforming / total, 3) if total else 0.0,
        "concept_warning_count": warnings,
        "evaluated_shapes": list(_CONCEPT_REPORT_SHAPE_IDS),
        # The published vocabulary only. A ``kind="concept"`` node written
        # straight to the graph store through ``POST /graph/nodes`` is not in the
        # vocabulary, so it is not counted here - measured, such a node with
        # ``definition: ""`` is served by ``GET /graph/nodes/{id}`` while this
        # pass rate stays 1.0. Declared rather than letting the number read as
        # covering every concept-shaped thing in the system.
        "conformance_scope": CONCEPT_CONFORMANCE_SCOPE,
        "non_conforming_concepts": [
            report["concept"] for report in reports if not report["conforms"]
        ],
    }


HIERARCHY_CLASS_SEPARATION_SCOPE = (
    "broader/narrower edges with at least one endpoint in "
    "ontology._CONCEPT_DEFINITIONS. An edge whose endpoints are both outside "
    "the published vocabulary is not counted here: the write gate refuses it "
    "when either endpoint is a known data asset, so what escapes both is an "
    "edge written while one endpoint was unknown that later became a data "
    "asset, whose other endpoint is a kind=\"concept\" graph node outside the "
    "vocabulary (measured: POST /graph/nodes writes one, and this count stays 7)"
)


def hierarchy_class_separation(
    edges: list[Mapping[str, Any]],
) -> dict[str, Any]:
    """Evaluate ConceptHierarchyShape over the hierarchy edges the graph holds.

    Pure: each edge arrives as ``{edge_type, source_id, target_id, source_kind,
    target_kind}`` with a ``None`` kind for an endpoint that is not a node, so
    this module stays free of the store it validates - the same split as
    ``validate_concept_semantics`` and its injected resolver. The assembly lives
    in ``sdp.ontology.hierarchy_class_separation_report``.

    This is the half of ONT-002 the write gate cannot cover. A gate reads the
    kinds known at write time, so an edge written while both endpoints are
    unknown is permitted (the seed's load order needs that) and an endpoint may
    become a dataset afterwards; this report reads what the graph *now* holds, so
    that ordering shows up here.

    ``conforms`` counts violations only, exactly as the dataset and concept
    reports do, and ``unknown_endpoint_count`` is published separately for the
    reason the ConceptShape comment gives: the shipped graph carries warnings by
    design, and one number would hide which kind of finding it counts.
    """
    shape = _shape("ConceptHierarchyShape")
    required_kind = shape["required_endpoint_kind"]
    violations: list[dict[str, str]] = []
    conforming = 0
    unknown_endpoints = 0

    for edge in edges:
        edge_findings: list[dict[str, str]] = []
        relation = str(edge["edge_type"])
        printable = f"{relation}: {edge['source_id']} -> {edge['target_id']}"
        for role in ("source", "target"):
            node_id = edge[f"{role}_id"]
            kind = edge[f"{role}_kind"]
            if kind == required_kind:
                continue
            if kind is None:
                unknown_endpoints += 1
                edge_findings.append(
                    {
                        "shape": "ConceptHierarchyShape",
                        "path": f"{relation}.{role}",
                        "severity": shape["unknown_endpoint_severity"],
                        "message": (
                            f"hierarchy {role} is not a graph node: "
                            f"{printable} ({role}={node_id})"
                        ),
                    }
                )
                continue
            edge_findings.append(
                {
                    "shape": "ConceptHierarchyShape",
                    "path": f"{relation}.{role}",
                    "severity": "violation",
                    "message": (
                        f"hierarchy {role} is a {kind!r} node rather than a "
                        f"{required_kind!r}, so a data asset is placed in the "
                        f"business-class hierarchy: {printable} "
                        f"({role}={node_id})"
                    ),
                }
            )
        violations.extend(edge_findings)
        if not any(finding["severity"] == "violation" for finding in edge_findings):
            conforming += 1

    total = len(edges)
    return {
        "hierarchy_relations": list(shape["hierarchy_relations"]),
        "required_endpoint_kind": required_kind,
        "evaluated_shapes": list(_HIERARCHY_REPORT_SHAPE_IDS),
        "hierarchy_edge_count": total,
        "conforming_edge_count": conforming,
        "hierarchy_pass_rate": round(conforming / total, 3) if total else 0.0,
        "unknown_endpoint_count": unknown_endpoints,
        "conforms": not any(item["severity"] == "violation" for item in violations),
        "violations": violations,
        "conformance_scope": HIERARCHY_CLASS_SEPARATION_SCOPE,
    }


# The hierarchy's acyclicity is a property of the **graph**, not of one node or
# one edge, and SHACL expresses that only through a SPARQL-based constraint. So
# it is deliberately **not** in ``_SHACL_COMPATIBLE_SHAPES``: adding it there
# would make ``shacl_compatible`` - which claims every published shape is one
# this validator evaluates - cover a constraint that is not shape-shaped. It is
# published as its own report, with its own engine declaration, for the same
# reason ``shacl_engine_executed`` exists: "consistency check" alone reads as a
# reasoner having run.
CONSISTENCY_ENGINE = "builtin_graph_checks"
REASONER_EXECUTED = False

# ONT-007's acceptance criterion is "unsatisfiable class 0개가 release gate".
# What is published is the **cycle** count, because that is what is computed and
# what a SKOS-only vocabulary can actually have: a cycle makes concepts mutually
# subsuming, and unsatisfiability needs a disjointness axiom this repository does
# not have. Naming the number after the criterion rather than after the
# computation is the mistake ``shacl_compatible`` already taught here.
HIERARCHY_CONSISTENCY_CONDITIONS = ("acyclic_subsumption",)

HIERARCHY_CONSISTENCY_SCOPE = (
    "the subsumption relation asserted by broader/narrower edges with at least "
    "one endpoint in ontology._CONCEPT_DEFINITIONS, read in one direction "
    "(narrower: A -> B and broader: B -> A are the same assertion). Not "
    "checked: SKOS S27 (skos:related disjoint from skos:broaderTransitive), any "
    "OWL axiom, and any condition needing a reasoner - none runs here"
)


def hierarchy_consistency(
    subsumption_pairs: list[tuple[str, str]],
) -> dict[str, Any]:
    """Whether the subsumption relation these ``(child, parent)`` pairs form is acyclic.

    Pure, like ``hierarchy_class_separation``: the pairs arrive already
    normalized for direction (``sdp.graph_store.subsumption_pair``) and already
    scoped, so this module stays free of the store it validates. The assembly is
    ``sdp.ontology.hierarchy_consistency_report``.

    Each cycle is reported once, as the sorted set of concepts it contains, so
    the same cycle found from three different entry points is one finding rather
    than three, and the pairs themselves are deduplicated because the seed
    states two of its subsumptions from both ends. ``conforms`` is "no cycle": a concept that is broader than itself
    is not a hierarchy, and unlike the unknown-endpoint case there is nothing
    unknown about it - the shipped seed is acyclic (measured), so this can be a
    violation without refusing the product's own data.
    """
    # Deduplicated, because one assertion can arrive twice: the shipped seed
    # states two of its five subsumptions from both ends (``narrower: 고객 ->
    # 활성 고객`` and ``broader: 활성 고객 -> 고객``), so the 7 hierarchy edges
    # carry 5 distinct ``(child, parent)`` assertions. Counting the edges under a
    # key named for pairs would have published 7 for a relation of size 5.
    distinct_pairs = sorted(set(subsumption_pairs))
    parents: dict[str, set[str]] = {}
    for child, parent in distinct_pairs:
        parents.setdefault(child, set()).add(parent)

    cycles: set[tuple[str, ...]] = set()
    for start in sorted(parents):
        # Walk up from ``start``; any path that returns to it is a cycle.
        stack: list[tuple[str, tuple[str, ...]]] = [(start, (start,))]
        while stack:
            current, path = stack.pop()
            for parent in sorted(parents.get(current, ())):
                if parent == start:
                    cycles.add(tuple(sorted(set(path))))
                elif parent not in path:
                    stack.append((parent, path + (parent,)))

    members = sorted({concept for cycle in cycles for concept in cycle})
    return {
        "checked_conditions": list(HIERARCHY_CONSISTENCY_CONDITIONS),
        "consistency_engine": CONSISTENCY_ENGINE,
        "reasoner_executed": REASONER_EXECUTED,
        "subsumption_pair_count": len(distinct_pairs),
        "cycle_count": len(cycles),
        "cycles": [list(cycle) for cycle in sorted(cycles)],
        "concepts_in_a_cycle": members,
        "conforms": not cycles,
        "conformance_scope": HIERARCHY_CONSISTENCY_SCOPE,
    }


def enterprise_shacl_validation_summary(
    tenant_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Summarize SHACL conformance platform-wide, with per-dataset detail scoped.

    The aggregate is deliberately platform-wide: a pass rate against the 0.95
    saleability target is a statement about the platform, and scoping it per
    caller would make procurement's number depend on who asked.

    The per-dataset ``reports`` array is a different thing - it carries dataset
    ids - and it was unscoped, so an unauthenticated caller read every tenant's
    dataset ids out of an aggregate evidence endpoint. That is the same
    disclosure the per-dataset ``/catalog/datasets/{id}/semantic-validation``
    route refuses, reached through a route nobody thought of as a discovery
    surface. ``withheld_report_count`` reports the truncation rather than
    letting a short array read as a complete one.
    """
    # Imported here, not at module scope: ``sdp.ontology`` imports this module
    # for the publication-path gate, so a module-level import would be a cycle.
    from .ontology import (
        canonical_concept_or_none,
        concept_vocabulary_snapshot,
        hierarchy_class_separation_report,
        hierarchy_consistency_report,
    )

    concept_conformance = concept_vocabulary_conformance(
        concept_vocabulary_snapshot(), resolve_concept=canonical_concept_or_none
    )
    all_datasets = list_datasets()
    conforming = sum(
        1 for dataset in all_datasets if validate_dataset_semantics(dataset.id)["conforms"]
    )
    total = len(all_datasets)
    pass_rate = round(conforming / total, 3) if total else 0.0

    visible = list_datasets(tenant_ids)
    reports = [validate_dataset_semantics(dataset.id) for dataset in visible]
    return {
        "shacl_compatible": _shacl_compatible(),
        "validation_engine": VALIDATION_ENGINE,
        "shacl_engine_executed": SHACL_ENGINE_EXECUTED,
        "target_pass_rate": 0.95,
        "validation_pass_rate": pass_rate,
        "dataset_count": total,
        "conforming_datasets": conforming,
        "shape_count": len(_SHACL_COMPATIBLE_SHAPES),
        "evaluated_shapes": list(_DATASET_REPORT_SHAPE_IDS),
        "reports": reports,
        "withheld_report_count": total - len(reports),
        # The vocabulary half, so the concept shape's effect is measurable
        # platform-wide rather than only at the moment of a publication. The
        # vocabulary is shared rather than tenant-owned, so it is not scoped.
        "concept_conformance": concept_conformance,
        # ONT-002's verification half. Also unscoped, and for the same reason:
        # the hierarchy is the shared vocabulary's, and the edge identifiers it
        # reports are concept names, which the ontology surface already serves
        # to any caller - unlike the per-dataset ``reports`` array above, which
        # carries tenant-owned dataset ids and is scoped.
        "hierarchy_class_separation": hierarchy_class_separation_report(),
        # ONT-007's half: a consistency result a release gate can read. Separate
        # from the SHACL block above and carrying its own engine declaration,
        # because acyclicity is a graph property rather than a shape and because
        # no reasoner runs - see ``hierarchy_consistency``.
        "hierarchy_consistency": hierarchy_consistency_report(),
    }
