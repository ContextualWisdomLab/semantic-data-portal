from __future__ import annotations

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
]

# Which shapes this validator actually evaluates. ``shacl_compatible`` was a
# hardcoded ``True``; it is now derived from this set, so publishing a shape
# without evaluating it makes the claim false instead of leaving it unchanged.
_EVALUATED_SHAPE_IDS = frozenset({"DatasetShape", "BusinessMappingShape", "DistributionShape"})

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
        "violations": violations,
        "approved_mapping_count": len(approved_mappings),
        "metadata_completeness": dataset.metadata_completeness,
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
        "reports": reports,
        "withheld_report_count": total - len(reports),
    }
