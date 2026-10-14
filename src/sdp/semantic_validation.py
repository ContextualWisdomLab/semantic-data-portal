from __future__ import annotations

import unicodedata
from collections.abc import Callable, Mapping
from typing import Any

from sdp_core import MappingStatus
from sdp_core.contracts import REQUIRED_METADATA_FIELDS

from .catalog import get_dataset, list_datasets, validate_metadata


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
]

# Which shapes this validator actually evaluates. ``shacl_compatible`` was a
# hardcoded ``True``; it is now derived from this set, so publishing a shape
# without evaluating it makes the claim false instead of leaving it unchanged.
_EVALUATED_SHAPE_IDS = frozenset(
    {"DatasetShape", "BusinessMappingShape", "DistributionShape", "ConceptShape"}
)

# Which shapes each report actually applies. ``shapes`` publishes the whole
# catalog, and this module's own history is the reason that is not enough: a
# reader takes the published shape list for the constraints that produced
# ``conforms``. With a concept shape in the catalog, a dataset report that
# published the catalog alone would read as having validated a dataset against
# ConceptShape. Each report now names the shapes it evaluated.
_DATASET_REPORT_SHAPE_IDS = ("DatasetShape", "BusinessMappingShape", "DistributionShape")
_CONCEPT_REPORT_SHAPE_IDS = ("ConceptShape",)

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
        "non_conforming_concepts": [
            report["concept"] for report in reports if not report["conforms"]
        ],
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
    from .ontology import canonical_concept_or_none, concept_vocabulary_snapshot

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
    }
