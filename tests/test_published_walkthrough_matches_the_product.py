"""Two published claims the product contradicts, pinned to the product.

Both were found by walking the documents exactly as a buyer is told to, and both
are checked here against what the routes actually answer rather than against a
pinned sentence, so the guard moves with the product.

**1. ``docs/enterprise-readiness.md``'s saleability table said "paid pilot
blocker 0건".** Measured at ``94aa785``::

    GET /enterprise/production-readiness
      paid_pilot_ready        False
      paid_pilot_blockers     ['connector_credential_vault', 'oidc_jwks_verification',
                               'postgres_evidence_store', 'request_observability_export']
      configured_integrations []
      per-integration status  all four "implemented"

The row's 구현됨 half is true and its count is false, and the count is
deployment-dependent: the code ships, the configuration does not. The sibling
document had already adjudicated the exact sentence - ``docs/implementation-compliance.md``
carries "**정정**: 이 항목은 '남은 paid-pilot blocker는 0개다'라고 적고 있었습니다 …
따라서 blocker 수는 배포에 따라 달라지며, 설정되지 않은 배포에서 0이 아닙니다" - and
the table was never updated. ``GET /enterprise/demo-plan`` names this file in
``handoff_artifacts``, so it is a product-named buyer artifact.

**2. README's ``GET /audit/events`` bullet carried the ``/policy/decisions``
note verbatim**, and all three of its statements are false for that route.
Measured after one preview and ten ledger reads::

    GET /audit/events?user=admin&limit=500              1 row   {'crm-customer-master': 1}
    GET /policy/decisions?user=admin&limit=500          13 rows {'evidence': 12, 'crm-customer-master': 1}
    GET /audit/events?user=admin&resource=evidence      0 rows

The audit ledger is keyed on a dataset (``catalog.ingest_event(resource=<dataset_id>)``)
and an evidence read is a plane read with no dataset, so no code path can place
an evidence row there. A reader checking "is ledger access itself audited?" at
the route the README pointed to gets an empty feed; the answer is one bullet up.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from fastapi.testclient import TestClient

from sdp.api import app


client = TestClient(app)

REPO_ROOT = Path(__file__).resolve().parents[1]


def _text(relative: str) -> str:
    return (REPO_ROOT / relative).read_text(encoding="utf-8")


def test_the_readiness_table_does_not_contradict_the_blocker_count() -> None:
    """Derived from the route: the claim is refused only while it is false."""
    manifest = client.get("/enterprise/production-readiness").json()
    blockers = manifest["paid_pilot_blockers"]
    table = _text("docs/enterprise-readiness.md")
    if blockers:
        assert "paid pilot blocker 0건" not in table, (
            f"the table claims zero blockers while the product reports {blockers}"
        )
        assert "paid_pilot_blockers" in table, (
            "the table must name where a reader finds the current count"
        )


def test_the_table_still_states_the_half_that_is_true() -> None:
    """The four integrations really are implemented; only the count was wrong."""
    manifest = client.get("/enterprise/production-readiness").json()
    statuses = {item["id"]: item["status"] for item in manifest["integrations"]}
    assert set(statuses.values()) == {"implemented"}, statuses
    assert "구현됨" in _text("docs/enterprise-readiness.md")


def test_the_audit_ledger_really_records_no_evidence_read() -> None:
    """The mechanism behind the README correction, measured not assumed."""
    preview = client.post(
        "/browse/crm-customer-master/preview", json={"user": "admin", "limit": 2}
    )
    assert preview.status_code == 200, preview.text[:200]
    for _ in range(10):
        client.get("/audit/events?user=admin&limit=500")

    events = client.get("/audit/events?user=admin&limit=500").json()
    decisions = client.get("/policy/decisions?user=admin&limit=500").json()
    event_resources = Counter(row["resource"] for row in events)
    decision_resources = Counter(row["resource"] for row in decisions)

    assert "evidence" not in event_resources, event_resources
    assert decision_resources["evidence"] >= 10, decision_resources
    scoped = client.get("/audit/events?user=admin&resource=evidence&limit=500").json()
    assert scoped == [], scoped


def test_the_readme_bullet_does_not_promise_evidence_rows_there() -> None:
    """The claims that belong one bullet up must not be on this one.

    The bullet is located by its own route string rather than by line number, and
    the three borrowed claims are checked inside it only - the identical prose on
    the ``/policy/decisions`` bullet above is correct and must stay.
    """
    readme = _text("README.md")
    marker = "- `GET /audit/events?"
    assert marker in readme, "the /audit/events bullet moved; relocate this guard"
    bullet = readme.split(marker, 1)[1].split("\n- `", 1)[0]
    for borrowed in ("자기 읽기가 섞인다", "31행"):
        assert borrowed not in bullet, (
            f"the /policy/decisions claim {borrowed!r} is on the /audit/events bullet"
        )
    assert "쌓이지 않는다" in bullet, bullet[:300]
