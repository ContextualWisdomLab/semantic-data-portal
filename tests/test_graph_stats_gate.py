"""Every graph read goes through policy, including the one that only counts.

``GET /graph/stats`` was the single route in the mutating / browse / query set
with no actor parameter, no ``evaluate()`` call and no evidence row. Measured at
``8cda569``::

    anonymous GET /graph/stats -> 200 {'backend': 'in_memory',
        'stats': {'nodes': 26, 'edges': 78, 'concepts': 5, 'embeddings': 26}}
        policy decisions +0
    anonymous GET /graph/nodes/crm-customer-master -> 403
        '목록 조회는 인증된 사용자만 가능합니다.'

Its three siblings over the same store refuse that caller. The counts are not
harmless, because catalog mutations mirror one node per dataset plus one per
declared column into the graph by design: onboarding a three-column dataset
owned by another tenant moved the anonymous response from ``nodes 26`` to
``nodes 30``, so ``nodes +4`` reads as one dataset plus three columns. An
unauthenticated caller could poll one URL and watch a competitor tenant onboard
governed assets, learning how many datasets they added and how wide each one is.

Two published claims were false while that held. ``CLAUDE.md``'s governance
invariant - omitting policy evaluation and evidence from a browse/query path is
a regression - and the ``policy_audit_coverage`` KPI, which ships
``status="implemented"``, ``target="100 percent"`` and the guardrail **"No
preview or query path may bypass policy."**

The repair is the gate its siblings already use. Scoping the counts *per tenant*
is the larger, separable half and is deliberately not attempted here: the
in-memory backend could filter through ``policy.can_see_graph_node``, but the
SQL backend would need tenant-aware counting, and a half-scoped count published
as scoped would be worse than an authenticated instance-wide one.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sdp.api import app  # noqa: E402
from sdp import evidence  # noqa: E402
from sdp_core import enterprise_kpi_framework  # noqa: E402


client = TestClient(app)

# The graph routes that read the shared store. ``/graph/stats`` belongs with
# them; it was the one that did not behave like them.
GRAPH_READS = ("/graph/stats", "/graph/nodes/crm-customer-master")


@pytest.mark.parametrize("path", GRAPH_READS)
def test_an_anonymous_caller_is_refused_by_every_graph_read(path: str) -> None:
    """No graph read answers 200 to a caller with no credential."""
    response = client.get(path)
    assert response.status_code == 403, (
        f"{path} answered {response.status_code} to an anonymous caller: "
        f"{response.text[:200]}"
    )


def test_the_stats_route_records_a_policy_decision() -> None:
    """The evidence half of the invariant, not only the refusal."""
    before = evidence.count_policy_decisions()[0]
    refused = client.get("/graph/stats")
    after_refusal = evidence.count_policy_decisions()[0]
    assert refused.status_code == 403
    assert after_refusal > before, (
        "the refusal recorded no policy decision, so the governance ledger "
        "cannot explain it"
    )

    allowed = client.get("/graph/stats", params={"actor": "data-admin"})
    after_allow = evidence.count_policy_decisions()[0]
    assert allowed.status_code == 200, allowed.text
    assert after_allow > after_refusal, (
        "the allowed read recorded no policy decision"
    )


def test_an_authorized_reader_still_gets_the_counts() -> None:
    """The gate must not remove the capability, only authenticate it."""
    body = client.get("/graph/stats", params={"actor": "data-admin"}).json()
    assert body["backend"]
    assert set(body["stats"]) >= {"nodes", "edges", "concepts", "embeddings"}
    assert body["stats"]["nodes"] > 0


def test_the_counts_are_published_as_instance_wide_not_tenant_scoped() -> None:
    """The honest limit, stated rather than implied.

    The repair authenticates the reader; it does not scope the counts. Publishing
    them as scoped while they are instance-wide would be the worse defect, so the
    response says which they are and this pins that it keeps saying so.
    """
    body = client.get("/graph/stats", params={"actor": "data-admin"}).json()
    scope = body.get("count_scope")
    assert scope == "instance_wide_all_tenants", (
        "the counts cross tenant boundaries and the response does not say so: "
        f"{sorted(body)}"
    )


def test_the_published_guardrail_names_this_property() -> None:
    """The KPI this route falsified is still the one making the claim.

    If the guardrail is ever reworded or the KPI stops being ``implemented``,
    this test should be re-read rather than silently satisfied.
    """
    framework = enterprise_kpi_framework()
    # Searched across both lists rather than guessed: it is a *primary* KPI, not
    # a guardrail KPI, despite carrying guardrails. Looking in the wrong list
    # first is why this is written as a search.
    published = list(framework.primary_kpis) + list(framework.guardrail_kpis)
    coverage = [kpi for kpi in published if kpi.id == "policy_audit_coverage"]
    assert coverage, [kpi.id for kpi in published]
    guardrails = coverage[0].guardrails
    assert any("bypass policy" in text for text in guardrails), guardrails
    assert coverage[0].status == "implemented", coverage[0].status
