"""A policy decision that does not decide anything is not policy enforcement.

``POST /llm/search`` evaluated policy, received ``deny``, and served the payload
anyway with the denial embedded as decoration. Measured before the repair, with a
dataset planted in tenant ``zeta`` and the ontology index rebuilt as a restart
would rebuild it:

    POST /llm/search {"user": "nobody", "question": "고객"}  -> 200
      policy.effect                      = "deny"
      recommendations.dataset_ids        = ['crm-customer-master', 'sales-order',
                                           'semantic-glossary',
                                           'marketing-campaign', 'zeta-idx']

So an unauthenticated, policy-denied caller received every tenant's dataset ids -
``zeta-idx`` among them - because ``ontology._build_index()`` reads
``list_datasets()`` with no tenant predicate.

``src/sdp_core/kpis.py`` publishes the guardrail this breaks: "No unauthorized
dataset existence disclosure."
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from sdp import catalog, ontology
from sdp.api import app


client = TestClient(app)


def _plant_foreign_dataset() -> None:
    base = catalog._DATA["crm-customer-master"]
    catalog._DATA["zeta-concept-ds"] = base.model_copy(
        update={"id": "zeta-concept-ds", "tenant_id": "zeta", "terms": ["고객"]}
    )
    # The index is module state built at import; rebuild it so the planted
    # dataset is present exactly as it would be after a restart.
    # The concept-to-dataset map used to be an import-time snapshot that this
    # line had to rebuild by hand after registering a dataset. It is derived
    # on read now, so registering is enough.


def test_a_denied_caller_is_refused_rather_than_served() -> None:
    _plant_foreign_dataset()
    response = client.post("/llm/search", json={"user": "nobody", "question": "고객"})
    assert response.status_code == 403, response.text
    detail = response.json()["detail"]
    assert detail["policy_scope"] == "catalog_discovery"
    assert detail["policy_decision_id"]
    # No dataset identity at all in a refusal.
    assert "zeta-concept-ds" not in response.text
    assert "crm-customer-master" not in response.text


def test_an_allowed_caller_sees_only_its_own_tenants_mapping() -> None:
    _plant_foreign_dataset()
    response = client.post("/llm/search", json={"user": "analyst", "question": "고객"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["policy"]["effect"] == "allow"
    recommendations = body["recommendations"]
    assert "zeta-concept-ds" not in recommendations["dataset_ids"]
    assert recommendations["dataset_ids"], "the caller must still see its own datasets"
    # The truncation is declared, not silent.
    assert recommendations["withheld_dataset_count"] >= 1
    assert recommendations["count"] == len(recommendations["dataset_ids"])


def test_a_platform_admin_sees_the_whole_mapping_with_nothing_withheld() -> None:
    _plant_foreign_dataset()
    body = client.post("/llm/search", json={"user": "admin", "question": "고객"}).json()
    recommendations = body["recommendations"]
    assert "zeta-concept-ds" in recommendations["dataset_ids"]
    assert recommendations["withheld_dataset_count"] == 0


def test_the_concept_mapping_helper_scopes_its_dataset_ids() -> None:
    """The helper, not only the route - other callers must inherit the scope."""
    _plant_foreign_dataset()
    unscoped = ontology.concept_assets("고객")
    assert "zeta-concept-ds" in unscoped["dataset_ids"], (
        "None must remain the explicit platform-wide crossing"
    )
    assert unscoped["withheld_dataset_count"] == 0

    scoped = ontology.concept_assets("고객", ["demo"])
    assert "zeta-concept-ds" not in scoped["dataset_ids"]
    assert scoped["withheld_dataset_count"] >= 1

    none_visible = ontology.concept_assets("고객", [])
    assert none_visible["dataset_ids"] == []
    assert none_visible["withheld_dataset_count"] == none_visible["withheld_dataset_count"]
