from __future__ import annotations

from typing import Any

from . import ontology
from .catalog import list_datasets
from .semantic_validation import enterprise_shacl_validation_summary


# The fields of a patch record that name a person. The summary carries none of
# them; ``GET /ontology/patches`` serves all four to an authorized actor.
REVIEW_ITEM_IDENTITY_FIELDS = ("requestor", "reviewed_by", "reviewed_at", "review_comment")


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

    The ontology patch half rested on ``GET /ontology/patches`` being open too,
    so republishing proposal detail here disclosed nothing that route withheld.
    That route is now a governed read, which makes this the open surface: with
    one proposal queued, measured, ``GET /enterprise/steward-review`` with no
    actor served ``review_items[0].requestor == "analyst"``. Gating the other
    route while this one republished the same name would have been theatre.

    ``requestor`` is therefore withheld here rather than scoped, and the
    withholding is declared. Withheld, not gated, because this summary is one of
    the published open proof links (``enterprise_evidence.OPEN_PROOF_ENDPOINTS``,
    pinned to resolve below 400 by
    ``test_every_published_proof_link_resolves_as_published``) and because the
    procurement question it answers - how deep is the queue, is the handoff ready
    - does not need the proposer's name. A caller entitled to the name reads the
    governed route, which serves all four identity fields to an authorized actor.

    The field is dropped for **every** caller, including an authorized one. An
    actor-dependent identity field here would have to be decided by a predicate
    that writes no decision row (this route records none today, and must not
    start: no GET in the product answers 200 while billing the ledger), leaving
    an authorization decision with no evidence behind it. One place makes that
    decision, and it is the governed route.
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
        # Declared rather than silently dropped, for the same reason: a reader
        # must be able to tell a withheld field from a queue that carries no
        # such information, and must be told where it is instead.
        #
        # Derived from the items rather than written as ``["requestor"]``. A
        # literal would keep claiming the field is withheld after someone put it
        # back - a published claim disagreeing with the code producing it. This
        # way a reintroduced field drops out of the declaration by itself, and
        # the claim cannot become false while staying green.
        "withheld_review_item_fields": [
            field
            for field in REVIEW_ITEM_IDENTITY_FIELDS
            if not any(field in item for item in patch_items)
        ],
        "withheld_review_item_field_note": (
            "제안자/승인자 신원은 거버닝 읽기에만 있습니다: "
            "`GET /ontology/patches?user=<actor>` 와 "
            "`GET /ontology/change-log?user=<actor>`. "
            "이 요약은 공개 증빙 링크이므로 신원을 담지 않습니다."
        ),
    }
