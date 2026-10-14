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


def test_every_per_dataset_catalog_route_hides_an_out_of_scope_dataset() -> None:
    """Structural, not per-route: the route list is read from the app.

    Three times now a fix to one catalog read has been bypassed by a sibling.
    ``/catalog/datasets/{id}`` returns 404 for an out-of-scope dataset, but
    ``/jsonld`` still returned its title, owner and description, ``/lineage``
    returned its upstream and downstream ids, and ``/related``, ``/validate``,
    ``/semantic-validation`` and ``/schema-versions`` answered 200 — which is an
    existence oracle for a dataset the detail route just hid. Checking for
    particular strings misses that: the *status code* is the disclosure.

    Enumerating the routes from ``app.routes`` means the next sibling added to
    this prefix is covered without anyone remembering to extend this test.
    """
    paths = sorted(
        route.path
        for route in app.routes
        if getattr(route, "path", "").startswith("/catalog/datasets/{dataset_id}")
        and "GET" in getattr(route, "methods", set())
    )
    assert len(paths) >= 8, paths

    offenders = []
    for path in paths:
        url = path.replace("{dataset_id}", FOREIGN)
        params = {"user": "analyst"}
        if path.endswith("/schema-diff"):
            # Required query params; 422 is schema validation, which precedes auth
            # and discloses nothing, so supply them to reach the scope check.
            params |= {"from_version": "1.0.0", "to_version": "2.0.0"}
        response = client.get(url, params=params)
        if response.status_code != 404:
            offenders.append((path, response.status_code))
    assert not offenders, f"out-of-scope dataset still reachable: {offenders}"


def test_per_dataset_routes_still_serve_the_owning_tenant() -> None:
    """The uniform 404 must not break the legitimate reader.

    A snapshot is recorded first so that a 404 can only mean "refused", never
    "legitimately absent" — ``/schema-history`` answers 404 for a dataset with no
    snapshot yet, which is correct and must not read as a refusal here.
    """
    catalog._record_schema_snapshot(catalog._DATA[FOREIGN])
    paths = sorted(
        route.path
        for route in app.routes
        if getattr(route, "path", "").startswith("/catalog/datasets/{dataset_id}")
        and "GET" in getattr(route, "methods", set())
    )
    broken = []
    for path in paths:
        url = path.replace("{dataset_id}", FOREIGN)
        params = {"user": "external-analyst"}
        if path.endswith("/schema-diff"):
            params |= {"from_version": "1.0.0", "to_version": "2.0.0"}
        response = client.get(url, params=params)
        if response.status_code == 404:
            broken.append(path)
    assert not broken, f"owning tenant refused on: {broken}"


def test_no_per_dataset_route_lets_a_domain_exception_escape_as_500() -> None:
    """``/schema-history`` raised an uncaught ``KeyError('no schema history
    found')`` for any dataset with no snapshot yet, so a legitimate reader asking
    a reasonable question got a 500. This violates the repository's own documented
    mapping (CLAUDE.md: domain modules raise ``KeyError``→404, ``ValueError``→400,
    ``PermissionError``→403, and ``api.py`` converts them).

    Pre-existing, not introduced by the tenant scoping — the structural sweep
    above is what surfaced it. Enumerated from ``app.routes`` for the same reason.
    """
    from fastapi.testclient import TestClient as _TestClient

    quiet = _TestClient(app, raise_server_exceptions=False)
    base = catalog._DATA["crm-customer-master"]
    catalog._DATA["no-history-ds"] = base.model_copy(update={"id": "no-history-ds"})

    failures = []
    for route in app.routes:
        path = getattr(route, "path", "")
        if not path.startswith("/catalog/datasets/{dataset_id}"):
            continue
        if "GET" not in getattr(route, "methods", set()):
            continue
        params = {"user": "analyst"}
        if path.endswith("/schema-diff"):
            params |= {"from_version": "1.0.0", "to_version": "2.0.0"}
        response = quiet.get(path.replace("{dataset_id}", "no-history-ds"), params=params)
        if response.status_code >= 500:
            failures.append((path, response.status_code))
    assert not failures, f"domain exception escaped as a server error: {failures}"


def test_no_enterprise_aggregate_route_discloses_a_foreign_tenants_dataset() -> None:
    """The aggregate evidence surface is a discovery surface too.

    ``/enterprise/shacl-validation`` embeds a per-dataset ``reports`` array, so it
    published every tenant's dataset ids to an unauthenticated caller - the same
    disclosure ``/catalog/datasets/{id}/semantic-validation`` refuses, reached
    through a route nobody had classified as discovery. Measured before the fix:

        GET /enterprise/shacl-validation   (no actor) -> 200, reports[] contains
                                                        "acme-secret" (tenant acme)

    Ten of the eleven parameterless ``/enterprise`` GET routes were already clean
    because they publish no dataset identity. The routes are enumerated from
    ``app.routes`` rather than listed, so a new aggregate that starts embedding
    dataset identity fails here instead of shipping.
    """
    base = catalog._DATA["crm-customer-master"]
    catalog._DATA["acme-enterprise-secret"] = base.model_copy(
        update={
            "id": "acme-enterprise-secret",
            "tenant_id": "acme",
            "title": "ACME 기밀 매출",
            "owner": "acme-finance",
        }
    )
    secrets = ("acme-enterprise-secret", "ACME 기밀 매출", "acme-finance")

    paths = sorted(
        {
            route.path
            for route in app.routes
            if getattr(route, "path", "").startswith("/enterprise")
            and "GET" in getattr(route, "methods", set())
            and "{" not in route.path
        }
    )
    assert len(paths) >= 10, f"enterprise surface unexpectedly small: {paths}"

    leaks = []
    for path in paths:
        response = client.get(path)
        disclosed = [secret for secret in secrets if secret in response.text]
        if disclosed:
            leaks.append((path, disclosed))
    assert not leaks, f"enterprise aggregate disclosed a foreign tenant's dataset: {leaks}"


def test_the_shacl_aggregate_stays_platform_wide_while_its_reports_scope() -> None:
    """Scoping the detail must not make the procurement metric caller-dependent.

    ``validation_pass_rate`` is measured against a published 0.95 saleability
    target, so it is a statement about the platform; if it varied by caller the
    number would be meaningless. Only the per-dataset detail is scoped, and the
    truncation is reported rather than left to look complete.
    """
    base = catalog._DATA["crm-customer-master"]
    catalog._DATA["acme-rate-secret"] = base.model_copy(
        update={"id": "acme-rate-secret", "tenant_id": "acme"}
    )

    def summary(actor: str | None) -> dict:
        params = {} if actor is None else {"user": actor}
        response = client.get("/enterprise/shacl-validation", params=params)
        assert response.status_code == 200, response.text
        return response.json()

    anonymous = summary(None)
    tenant_reader = summary("analyst")
    platform_admin = summary("admin")

    # One aggregate for everyone.
    for field in ("validation_pass_rate", "dataset_count", "conforming_datasets", "shape_count"):
        assert anonymous[field] == tenant_reader[field] == platform_admin[field], field

    # Detail scoped, and the gap declared.
    for body in (anonymous, tenant_reader, platform_admin):
        assert len(body["reports"]) + body["withheld_report_count"] == body["dataset_count"]

    assert anonymous["reports"] == []
    assert anonymous["withheld_report_count"] == anonymous["dataset_count"]

    visible_to_tenant = {report["dataset_id"] for report in tenant_reader["reports"]}
    assert "acme-rate-secret" not in visible_to_tenant
    assert visible_to_tenant, "the tenant reader should still see its own datasets"

    visible_to_admin = {report["dataset_id"] for report in platform_admin["reports"]}
    assert "acme-rate-secret" in visible_to_admin
    assert platform_admin["withheld_report_count"] == 0
