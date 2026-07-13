from __future__ import annotations

from typing import Any

from . import ontology
from .catalog import list_datasets
from .semantic_validation import enterprise_shacl_validation_summary


def build_steward_review_summary() -> dict[str, Any]:
    validation = enterprise_shacl_validation_summary()
    open_patches = ontology.list_patches(status="proposed")
    status_counts: dict[str, int] = {}
    for dataset in list_datasets():
        status_counts[dataset.status] = status_counts.get(dataset.status, 0) + 1

    validation_items = [
        {
            "type": "semantic_validation",
            "id": report["dataset_id"],
            "status": "needs_review",
            "violations": [item for item in report["violations"] if item["severity"] == "violation"],
        }
        for report in validation["reports"]
        if not report["conforms"]
    ]
    patch_items = [
        {
            "type": "ontology_patch",
            "id": patch["id"],
            "status": patch["status"],
            "concept": patch["concept"],
            "requestor": patch["requestor"],
            "confidence": patch["confidence"],
        }
        for patch in open_patches
    ]
    review_items = validation_items + patch_items

    return {
        "feature_gate": "sdp_enterprise",
        "review_sla": "2 business days",
        "dataset_status_counts": status_counts,
        "validation_pass_rate": validation["validation_pass_rate"],
        "validation_review_count": len(validation_items),
        "ontology_patch_count": len(open_patches),
        "review_queue_count": len(review_items),
        "buyer_handoff_ready": not review_items and validation["validation_pass_rate"] >= validation["target_pass_rate"],
        "proof_endpoints": [
            "/enterprise/shacl-validation",
            "/catalog/datasets/{dataset_id}/semantic-validation",
            "/ontology/patches",
            "/ontology/patches/{patch_id}/review",
        ],
        "review_items": review_items,
    }
