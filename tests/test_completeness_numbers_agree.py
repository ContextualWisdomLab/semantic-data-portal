"""One payload published `missing: []`, `is_valid: true` and `0.909` together.

``metadata_completeness`` and ``catalog.validate_metadata`` were unified onto one
list, ``REQUIRED_METADATA_FIELDS`` (ten fields), and the comment above that list
records why: "They were two lists of different lengths, so the published
completeness number could read 1.0 for a dataset the validator calls critically
invalid."

``recompute_scores`` kept a **third** tally - eleven hand-written ``if`` branches
with ``required_total = 11``, including ``tags``, which the validator does not
require. Measured at ``c4ac6b5`` on two datasets whose bodies differ only in
``tags``::

    probe-with-tags  /validate -> required_fields(10) missing: [] is_valid: True
                                  completeness_score: 1.0    metadata_completeness: 1.0
    probe-no-tags    /validate -> required_fields(10) missing: [] is_valid: True
                                  completeness_score: 0.909  metadata_completeness: 1.0

0.909 is 10/11. A diligence reader sees a 90.9% complete dataset with nothing
missing, and the same payload's sibling field says 100%. ``completeness_score`` is
published on ``GET /catalog/search`` rows, the dataset detail and the JSON-LD
(``sdp:completenessScore``); the KPI gate reads ``metadata_completeness``, so the
two numbers disagreed in public while only one of them was gated.
"""

from __future__ import annotations

import inspect
import re

from typing import Any

from fastapi.testclient import TestClient

from sdp.api import app
from sdp_core.contracts import REQUIRED_METADATA_FIELDS, Dataset


client = TestClient(app)


def _register(dataset_id: str, *, tags: list[str]) -> None:
    """Register one dataset that satisfies every required field."""
    body: dict[str, Any] = {
        "id": dataset_id,
        "tenant_id": "demo",
        "title": "완전성 프로브",
        "description": "완전성 숫자 두 개를 비교하는 프로브",
        "owner": "data-admin",
        "steward": "data-admin",
        "domain": "고객",
        "source_system": "s3://analytics/events/orders",
        "sensitivity": "low",
        "update_frequency": "daily",
        "quality_score": 0.9,
        "freshness_score": 0.9,
        "tags": tags,
        "schema": [
            {"name": "customer_id", "datatype": "string", "nullable_ratio": 0.0, "distinct_ratio": 1.0}
        ],
        "distributions": [
            {"id": f"{dataset_id}-csv", "format": "csv", "endpoint": "https://files.example.internal/x.csv"}
        ],
        "actor": "data-admin",
        "reason": "probe",
    }
    created = client.post("/catalog/datasets", json=body)
    assert created.status_code == 200, created.text


def test_tags_is_not_a_required_field() -> None:
    """The premise: the eleventh item was never required."""
    assert "tags" not in REQUIRED_METADATA_FIELDS, REQUIRED_METADATA_FIELDS
    assert len(REQUIRED_METADATA_FIELDS) == 10, REQUIRED_METADATA_FIELDS


def test_nothing_missing_means_complete_on_both_published_numbers() -> None:
    """The contradiction a buyer reads, driven on the dataset that showed it."""
    _register("completeness-no-tags", tags=[])
    validated = client.get("/catalog/datasets/completeness-no-tags/validate?user=data-admin").json()
    assert validated["missing"] == [], validated
    assert validated["is_valid"] is True, validated

    payload = client.get("/catalog/datasets/completeness-no-tags?user=data-admin").json()
    assert payload["metadata_completeness"] == 1.0, payload
    assert payload["completeness_score"] == 1.0, (
        "the validator says nothing is missing and the published completeness says "
        f"{payload['completeness_score']}"
    )


def test_the_two_numbers_agree_on_every_seeded_dataset() -> None:
    """Driven over the catalogue rather than the one probe."""
    listed = client.get("/catalog/datasets?user=admin").json()
    rows = listed["items"] if isinstance(listed, dict) else listed
    assert rows, listed
    for row in rows:
        assert row["completeness_score"] == round(row["metadata_completeness"], 3), row["id"]


def test_adding_a_tag_does_not_change_the_required_coverage_number() -> None:
    """Two datasets differing only in ``tags`` must score the same."""
    _register("completeness-tagged", tags=["고객", "프로브"])
    _register("completeness-untagged", tags=[])
    tagged = client.get("/catalog/datasets/completeness-tagged?user=data-admin").json()
    untagged = client.get("/catalog/datasets/completeness-untagged?user=data-admin").json()
    assert tagged["completeness_score"] == untagged["completeness_score"], (
        tagged["completeness_score"],
        untagged["completeness_score"],
    )
    # And the recommendation number is where a tag *does* count, so the repair is
    # not "tags stop mattering anywhere".
    assert tagged["recommended_score"] > untagged["recommended_score"], (
        tagged["recommended_score"],
        untagged["recommended_score"],
    )


def test_the_score_is_derived_and_carries_no_tally_of_its_own() -> None:
    """Structural: a third hand-written list is what this repair removes."""
    source = inspect.getsource(Dataset.recompute_scores)
    # The docstring records the removed expression as the measurement, so it is
    # stripped along with the comments. Checking the whole source failed on the
    # honest implementation - the third time this round that a guard tripped on
    # the prose documenting what it guards.
    body = source.split('"""')[-1]
    code = "\n".join(
        line for line in body.splitlines() if not line.lstrip().startswith("#")
    )
    assert "required_total" not in code, code
    assert not re.search(r"if self\.\w+:", code), (
        "recompute_scores still tallies fields by hand, which is the drift this "
        f"repair removes: {code}"
    )
    assert "metadata_completeness" in code, code
