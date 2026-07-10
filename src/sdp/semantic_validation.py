from __future__ import annotations

from typing import Any

from sdp_core import MappingStatus

from .catalog import get_dataset, list_datasets, validate_metadata


_SHACL_COMPATIBLE_SHAPES = [
    {
        "id": "DatasetShape",
        "target": "Dataset",
        "required_properties": ["owner", "steward", "domain", "source_system", "schema", "distributions"],
    },
    {
        "id": "BusinessMappingShape",
        "target": "BusinessMapping",
        "required_properties": ["concept", "status"],
    },
    {
        "id": "DistributionShape",
        "target": "DatasetDistribution",
        "required_properties": ["format", "endpoint"],
    },
]


def validate_dataset_semantics(dataset_id: str) -> dict[str, Any]:
    dataset = get_dataset(dataset_id)
    if not dataset:
        raise KeyError(dataset_id)

    violations: list[dict[str, str]] = []
    metadata = validate_metadata(dataset)
    for field in metadata["missing"]:
        violations.append(
            {
                "shape": "DatasetShape",
                "path": field,
                "severity": "violation",
                "message": f"required metadata field is missing: {field}",
            }
        )

    approved_mappings = [mapping for mapping in dataset.mappings if mapping.status == MappingStatus.APPROVED]
    if not approved_mappings:
        violations.append(
            {
                "shape": "BusinessMappingShape",
                "path": "mappings",
                "severity": "violation",
                "message": "at least one approved business mapping is required",
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
        "shacl_compatible": True,
        "conforms": not any(item["severity"] == "violation" for item in violations),
        "shapes": _SHACL_COMPATIBLE_SHAPES,
        "violations": violations,
        "approved_mapping_count": len(approved_mappings),
        "metadata_completeness": dataset.metadata_completeness,
    }


def enterprise_shacl_validation_summary() -> dict[str, Any]:
    reports = [validate_dataset_semantics(dataset.id) for dataset in list_datasets()]
    conforming = sum(1 for report in reports if report["conforms"])
    total = len(reports)
    pass_rate = round(conforming / total, 3) if total else 0.0
    return {
        "shacl_compatible": True,
        "target_pass_rate": 0.95,
        "validation_pass_rate": pass_rate,
        "dataset_count": total,
        "conforming_datasets": conforming,
        "shape_count": len(_SHACL_COMPATIBLE_SHAPES),
        "reports": reports,
    }
