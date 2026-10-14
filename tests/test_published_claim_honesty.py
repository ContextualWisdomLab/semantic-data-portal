"""A published number or grant must agree with the code that enforces it.

Two claims measured as contradicting their own enforcement:

**The RBAC matrix published grants the engine denies.** It declares
``policy_source="sdp.policy.evaluate"`` - it claims to describe what that
engine does - and listed ``review_security_evidence`` and
``administer_tenants`` as allowed. Both are in
``policy.UNMAPPED_CATALOG_ACTIONS``, so ``evaluate`` returns deny with
"이 action은 아직 정책 엔진에 매핑되지 않았습니다." *before any role is
consulted*. Enumerating four roles against the engine with a real in-tenant
dataset: 37 of 40 cells agreed and 3 did not.

**``metadata_completeness`` could read 1.0 for a critically invalid dataset.**
It scored seven fields while ``catalog.validate_metadata`` required ten.
Measured on a dataset registered with ``schema: []`` and ``distributions: []``::

    GET /catalog/datasets/{id}/validate
      -> is_valid: false, critical: true, missing: ["schema", "distributions"]
    the same catalog payload
      -> metadata_completeness: 1.0

The KPI named after that measure states its own guardrail as "Completeness must
not hide failed validation."

Both checks are **enumerations**, not spot checks: every role against every
action, and the two field lists against each other. A single-case assertion is
what let three cells and three fields drift.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from sdp import catalog
from sdp.api import app
from sdp.policy import UNMAPPED_CATALOG_ACTIONS, evaluate
from sdp_core.contracts import REQUIRED_METADATA_FIELDS
from sdp_core.rbac import enterprise_rbac_matrix


client = TestClient(app, raise_server_exceptions=False)

# The seeded subject that holds each published role.
ROLE_SUBJECTS = {
    "data-analyst": "analyst",
    "security": "security",
    "platform-admin": "admin",
    "steward": "steward",
}


def test_every_published_grant_is_one_the_engine_actually_allows() -> None:
    """Enumerated over every role and every action it claims."""
    matrix = enterprise_rbac_matrix()
    assert matrix.policy_source == "sdp.policy.evaluate"

    disagreements = []
    for row in matrix.roles:
        subject = ROLE_SUBJECTS.get(row.role)
        if subject is None:
            continue
        for action in row.allowed_actions:
            decision = evaluate(
                subject=subject,
                resource="crm-customer-master",
                action=action,
                purpose="analysis",
            )
            if decision.effect != "allow":
                disagreements.append((row.role, action, decision.reason))
    assert not disagreements, (
        "the matrix publishes grants sdp.policy.evaluate refuses: " f"{disagreements}"
    )


def test_an_unenforced_action_is_declared_rather_than_published_as_a_grant() -> None:
    """Removing it would hide the intent; listing it as allowed was a false claim."""
    matrix = enterprise_rbac_matrix()
    declared = {
        row.role: set(row.declared_unenforced_actions)
        for row in matrix.roles
        if row.declared_unenforced_actions
    }
    assert declared == {
        "security": {"review_security_evidence"},
        "platform-admin": {"review_security_evidence", "administer_tenants"},
    }, declared

    for row in matrix.roles:
        subject = ROLE_SUBJECTS.get(row.role)
        if subject is None:
            continue
        # Each declared action really is refused, so the declaration is not
        # hiding an action that works.
        for action in row.declared_unenforced_actions:
            decision = evaluate(
                subject=subject,
                resource="crm-customer-master",
                action=action,
                purpose="analysis",
            )
            assert decision.effect != "allow", (row.role, action)
        # and no action is in both lists
        assert not set(row.allowed_actions) & set(row.declared_unenforced_actions)


def test_the_declared_unenforced_set_matches_the_engines_own_set() -> None:
    """``sdp_core`` cannot import the application layer, so this is the guard.

    The literal in ``sdp_core.rbac`` mirrors ``policy.UNMAPPED_CATALOG_ACTIONS``;
    if the engine maps one of them, this fails and the matrix is updated
    deliberately rather than drifting.
    """
    matrix = enterprise_rbac_matrix()
    declared = {
        action
        for row in matrix.roles
        for action in row.declared_unenforced_actions
    }
    assert declared == set(UNMAPPED_CATALOG_ACTIONS), (
        sorted(declared), sorted(UNMAPPED_CATALOG_ACTIONS)
    )


def test_completeness_and_validation_score_the_same_fields() -> None:
    """One list, so the number cannot say complete while the validator says no."""
    assert list(catalog._REQUIRED_METADATA_FIELDS) == list(REQUIRED_METADATA_FIELDS)


@pytest.mark.parametrize("blanked", ["schema", "distributions", "domain"])
def test_a_critically_invalid_dataset_cannot_publish_full_completeness(
    blanked: str,
) -> None:
    """Each field validation requires must move the published number."""
    base = catalog._DATA["crm-customer-master"]
    empty: object = [] if blanked in {"schema", "distributions"} else ""
    dataset_id = f"completeness-{blanked}"
    catalog._DATA[dataset_id] = base.model_copy(
        update={"id": dataset_id, blanked: empty}
    )
    catalog._DATA[dataset_id].recompute_scores()

    validated = client.get(
        f"/catalog/datasets/{dataset_id}/validate", params={"user": "admin"}
    )
    assert validated.status_code == 200, validated.text
    report = validated.json()
    assert report["is_valid"] is False, report
    assert blanked in report["missing"], report

    detail = client.get(
        f"/catalog/datasets/{dataset_id}", params={"user": "admin"}
    ).json()
    assert detail["metadata_completeness"] < 1.0, detail["metadata_completeness"]
    # and the discovery badge agrees with the validator
    assert detail["completeness_badge"] == "invalid", detail["completeness_badge"]


def test_a_fully_described_dataset_still_reaches_one() -> None:
    """Widening the denominator must not make a complete dataset incomplete."""
    for dataset in catalog.list_datasets(None):
        missing = [
            field for field in REQUIRED_METADATA_FIELDS if not getattr(dataset, field, None)
        ]
        if missing:
            continue
        assert dataset.metadata_completeness == 1.0, (dataset.id, missing)
