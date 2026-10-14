"""The readiness gate must exercise the surface a buyer actually uses.

``sdp.demo_smoke`` decided ``ready`` entirely from direct Python calls - zero
occurrences of any HTTP client in the module. So it reported ``ready: true``
while the HTTP surface was broken in ways a buyer hits immediately:

* the documented draft-then-execute pair rejected every draft it produced,
* ``POST /browse/query`` answered 500 when ``dataset_ids`` was omitted,
* ``/enterprise/console`` reported "evidence load failed" to every viewer.

A gate that does not touch the routes is not evidence about the routes. The
walkthrough is additive: the direct-call checks are unchanged and ``ready`` now
*also* requires the journey to work over HTTP.

Coverage boundary, stated because it was measured rather than assumed: the
walkthrough catches HTTP-contract regressions - status codes, the draft→execute
pair, any 5xx. It does **not** catch client-side breakage. Reverting
``src/sdp/console.py`` to its pre-repair commit leaves the smoke at
``ready: true``, because the console route still returns 200 and the failure was
in its JavaScript. That surface is pinned by
``tests/test_enterprise_console_contract.py`` instead.
"""

from __future__ import annotations

from sdp import demo_smoke


def test_the_walkthrough_covers_the_documented_journey() -> None:
    """The steps a buyer is walked through, not an arbitrary subset."""
    walkthrough = demo_smoke.http_walkthrough()
    steps = {step["step"] for step in walkthrough["steps"]}
    assert {
        "health",
        "console",
        "catalog_search",
        "dataset_detail",
        "governed_schema",
        "governed_preview",
        "connector_probe",
        "draft_query",
        "execute_drafted_query",
        "audit_feed",
        "policy_decisions",
        "malformed_query_is_a_client_error",
    } <= steps, f"walkthrough lost a step: {sorted(steps)}"


def test_every_walkthrough_step_passes_at_head() -> None:
    """If this fails, the buyer-facing HTTP surface is broken, not the test."""
    walkthrough = demo_smoke.http_walkthrough()
    assert walkthrough["failed_steps"] == [], walkthrough["steps"]
    assert walkthrough["server_error_steps"] == [], walkthrough["steps"]
    assert walkthrough["all_steps_passed"] is True


def test_a_drafted_query_is_executed_rather_than_only_drafted() -> None:
    """The pair, not the two halves separately - that is what was broken."""
    walkthrough = demo_smoke.http_walkthrough()
    by_step = {step["step"]: step for step in walkthrough["steps"]}
    assert by_step["draft_query"]["ok"] is True
    executed = by_step["execute_drafted_query"]
    assert executed["ok"] is True, (
        "the drafted SQL was not executable; the documented workflow has no path "
        f"through it: {executed}"
    )
    assert executed["status_code"] == 200


def test_a_malformed_body_is_required_to_be_a_client_error() -> None:
    """The step that pins the 500. A 500 here is a defect, not a rejection."""
    walkthrough = demo_smoke.http_walkthrough()
    by_step = {step["step"]: step for step in walkthrough["steps"]}
    step = by_step["malformed_query_is_a_client_error"]
    assert step["status_code"] == 400, step
    assert step["ok"] is True


def test_the_ready_gate_fails_when_the_walkthrough_fails(monkeypatch) -> None:
    """``ready`` must actually depend on the walkthrough, not merely report it."""
    healthy = demo_smoke.smoke_summary()
    assert healthy["ready"] is True, healthy
    assert healthy["http_walkthrough_passed"] is True

    def broken() -> dict:
        return {
            "steps": [{"step": "governed_preview", "status_code": 500, "expected": 200, "ok": False}],
            "step_count": 1,
            "failed_steps": ["governed_preview"],
            "server_error_steps": ["governed_preview"],
            "all_steps_passed": False,
        }

    monkeypatch.setattr(demo_smoke, "http_walkthrough", broken)
    degraded = demo_smoke.smoke_summary()
    assert degraded["ready"] is False
    assert degraded["http_walkthrough_failed_steps"] == ["governed_preview"]
    assert degraded["http_walkthrough_server_errors"] == ["governed_preview"]
    assert demo_smoke.main() == 1


def test_the_module_no_longer_decides_readiness_without_touching_a_route() -> None:
    """The structural form: the gate expression must consult the walkthrough."""
    import inspect

    source = inspect.getsource(demo_smoke.smoke_summary)
    assert "walkthrough = http_walkthrough()" in source
    assert 'walkthrough["all_steps_passed"]' in source, (
        "the ready gate must depend on the HTTP walkthrough, not just publish it"
    )
