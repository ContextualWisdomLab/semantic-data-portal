"""Tenant scoping of the catalog discovery surface.

The earlier discovery repair removed governed *fields* from the catalog payloads
but left cross-tenant *existence and ownership* fully open. Measured at HEAD:

    planted hr-salary-confidential  tenant=external  sensitivity=critical
    GET /catalog/search?q=HR            (no actor) -> 200
      {"id": "hr-salary-confidential", "title": "HR 급여 기밀",
       "owner": "hr-owner", "status": "published"}
    GET /catalog/facets?field=owner      (no actor) -> 200
      counts include "hr-owner": 1          <- another tenant's owner identity
    GET /browse/hr-salary-confidential/schema?user=analyst -> 403

The repository publishes the guardrail this violates: ``src/sdp_core/kpis.py:42``
lists **"No unauthorized dataset existence disclosure."** with ``/catalog/search``
among its ``source_endpoints``.

Note on status codes: the discovery surface answers **404** for a dataset in an
inaccessible tenant, deliberately diverging from ``/browse``'s 403. The defect
here *is* existence disclosure, and 403-vs-404 would itself disclose it. On
``/browse`` the caller already names the id and the denial is the audited
evidence, so 403 stays right there.
"""

from __future__ import annotations

from pathlib import Path
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sdp import catalog, evidence  # noqa: E402
from sdp.api import app  # noqa: E402
from sdp_core import kpis  # noqa: E402

client = TestClient(app)
FOREIGN = "hr-salary-confidential"


@pytest.fixture(autouse=True)
def _plant_foreign_dataset():
    data = {k: v.model_copy(deep=True) for k, v in catalog._DATA.items()}
    audit = list(catalog._AUDIT_LOG)
    decisions = list(evidence._POLICY_DECISION_LOG)
    base = catalog._DATA["crm-customer-master"]
    catalog._DATA[FOREIGN] = base.model_copy(
        update={
            "id": FOREIGN,
            "tenant_id": "external",
            "owner": "hr-owner",
            "title": "HR 급여 기밀",
            "sensitivity": "critical",
        }
    )
    try:
        yield
    finally:
        catalog._DATA.clear()
        catalog._DATA.update(data)
        catalog._AUDIT_LOG[:] = audit
        evidence._POLICY_DECISION_LOG[:] = decisions


def test_the_published_guardrail_exists_so_the_contract_is_real() -> None:
    """Pin the claim this module enforces, so it cannot be quietly deleted."""
    framework = kpis.enterprise_kpi_framework()
    guardrails = [
        guardrail
        for kpi in (*framework.primary_kpis, *framework.guardrail_kpis)
        for guardrail in kpi.guardrails
    ]
    assert "No unauthorized dataset existence disclosure." in guardrails


def test_catalog_search_requires_an_authorized_reader() -> None:
    assert client.get("/catalog/search", params={"q": "HR"}).status_code == 403


def test_catalog_search_hides_other_tenants_datasets() -> None:
    response = client.get("/catalog/search", params={"q": "HR", "user": "analyst"})
    assert response.status_code == 200
    assert all(item["id"] != FOREIGN for item in response.json()["items"]), response.json()

    owner = client.get("/catalog/search", params={"q": "HR", "user": "external-analyst"})
    assert owner.status_code == 200
    assert any(item["id"] == FOREIGN for item in owner.json()["items"])


def test_catalog_facets_do_not_aggregate_across_tenants() -> None:
    """An aggregate is a disclosure too: the owner facet named ``hr-owner``."""
    assert client.get("/catalog/facets", params={"field": "owner"}).status_code == 403
    scoped = client.get("/catalog/facets", params={"field": "owner", "user": "analyst"})
    assert scoped.status_code == 200
    assert "hr-owner" not in scoped.json()["counts"], scoped.json()


def test_dataset_list_and_detail_are_tenant_scoped() -> None:
    assert client.get("/catalog/datasets").status_code == 403
    listed = client.get("/catalog/datasets", params={"user": "analyst"})
    assert listed.status_code == 200
    assert all(row["id"] != FOREIGN for row in listed.json())

    # 404, not 403: on the discovery surface the defect being fixed is existence
    # disclosure, so the two answers must be indistinguishable.
    hidden = client.get(f"/catalog/datasets/{FOREIGN}", params={"user": "analyst"})
    assert hidden.status_code == 404
    missing = client.get("/catalog/datasets/no-such-dataset-at-all", params={"user": "analyst"})
    assert missing.status_code == hidden.status_code

    visible = client.get(f"/catalog/datasets/{FOREIGN}", params={"user": "external-analyst"})
    assert visible.status_code == 200


def test_join_candidates_do_not_cross_tenants() -> None:
    """``get_join_candidates`` iterated all of ``_DATA`` with no tenant predicate,
    using an id the caller legitimately owns as a pivot to name its neighbours —
    including their overlapping column names."""
    assert client.get("/catalog/datasets/crm-customer-master/join-candidates").status_code == 403
    scoped = client.get(
        "/catalog/datasets/crm-customer-master/join-candidates", params={"user": "analyst"}
    )
    assert scoped.status_code == 200
    body = scoped.json()
    rows = body["join_candidates"]
    assert all(row.get("dataset_id") != FOREIGN for row in rows), rows


def test_platform_admin_still_sees_every_tenant() -> None:
    response = client.get("/catalog/search", params={"q": "HR", "user": "admin"})
    assert response.status_code == 200
    assert any(item["id"] == FOREIGN for item in response.json()["items"])
