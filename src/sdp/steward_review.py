from __future__ import annotations

from typing import Any

from . import ontology
from .catalog import list_datasets
from .semantic_validation import enterprise_shacl_validation_summary


def build_steward_review_summary(tenant_ids: list[str] | None = None) -> dict[str, Any]:
    """Summarize the steward review queue, scoping the per-dataset identity.

    Counts, the pass rate and ``buyer_handoff_ready`` stay platform-wide: they
    are procurement signals about the platform, and a readiness flag that
    depended on who asked would be worthless. ``review_items`` is the opposite -
    each semantic-validation entry's ``id`` *is* a dataset id - so that list is
    scoped to the caller.

    This surface republished what it reads. ``enterprise_shacl_validation_summary``
    was scoped so an unauthenticated caller could no longer read another tenant's
    dataset ids out of it; this caller then called it with no scope and put the
    ids of every *non-conforming* dataset, in any tenant, into ``review_items``.
    Measured before the repair: a planted non-conforming dataset in tenant
    ``zeta`` was absent from ``/enterprise/shacl-validation`` and named in
    ``/enterprise/steward-review`` at the same moment.

    The ontology patch half is deliberately unchanged: ``GET /ontology/patches``
    is itself open, so republishing proposal detail here discloses nothing that
    route withholds. Whether the proposal queue should be public at all is a
    product decision, not a disagreement between two surfaces.
    """
    platform_validation = enterprise_shacl_validation_summary()
    scoped_validation = (
        platform_validation
        if tenant_ids is None
        else enterprise_shacl_validation_summary(tenant_ids)
    )
    open_patches = ontology.list_patches(status="proposed")
    status_counts: dict[str, int] = {}
    for dataset in list_datasets():
        status_counts[dataset.status] = status_counts.get(dataset.status, 0) + 1

    def validation_entries(summary: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            {
                "type": "semantic_validation",
                "id": report["dataset_id"],
                "status": "needs_review",
                "violations": [
                    item for item in report["violations"] if item["severity"] == "violation"
                ],
            }
            for report in summary["reports"]
            if not report["conforms"]
        ]

    platform_validation_items = validation_entries(platform_validation)
    visible_validation_items = validation_entries(scoped_validation)
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
    platform_review_count = len(platform_validation_items) + len(patch_items)
    visible_items = visible_validation_items + patch_items

    return {
        "feature_gate": "sdp_enterprise",
        "review_sla": "2 business days",
        "dataset_status_counts": status_counts,
        "validation_pass_rate": platform_validation["validation_pass_rate"],
        "validation_review_count": len(platform_validation_items),
        "ontology_patch_count": len(open_patches),
        "review_queue_count": platform_review_count,
        "buyer_handoff_ready": (
            not platform_review_count
            and platform_validation["validation_pass_rate"]
            >= platform_validation["target_pass_rate"]
        ),
        "proof_endpoints": [
            "/enterprise/shacl-validation",
            "/catalog/datasets/{dataset_id}/semantic-validation",
            "/ontology/patches",
            "/ontology/patches/{patch_id}/review",
        ],
        "review_items": visible_items,
        # Declared rather than left implicit: a short list must not read as an
        # empty queue.
        "withheld_review_item_count": platform_review_count - len(visible_items),
    }
