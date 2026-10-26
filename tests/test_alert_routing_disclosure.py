"""Alert routing must not publish the webhook, its host, or the traffic that fired it.

On the parent head ``SDP_ALERT_WEBHOOK_URL`` was declared-unimplemented: its
only read in the package was ``observability._sink_status`` taking ``bool()`` of
it. Routing adds an **outbound credential** and an **alert payload** to a module
whose two published surfaces - ``GET /enterprise/observability`` and
``GET /metrics`` - are both in ``enterprise_evidence.OPEN_PROOF_ENDPOINTS`` and
answer anonymously. The same module already withholds ``_EXPORT_ERRORS`` from
the manifest for exactly this reason: "a sink exception string can quote the
sink URL".

That is not hypothetical for the alert path. Measured with the real
``urllib.request`` on this interpreter, a userinfo-bearing webhook never reaches
the network at all - ``http.client`` folds the whole authority into the host and
raises before connecting - and the exception quotes the secret. Note that
``urllib.request.Request`` **unquotes** the authority first, so what leaks is the
*decoded* credential, split at the last colon of the decoded authority::

    https://sdp-alerts:s3cr3t-token@alerts.invalid.example/hook
      http.client.InvalidURL  "nonnumeric port: 's3cr3t-token@alerts.invalid.example'"

    https://sdp-alerts:p%40ssw0rd-42@alerts.invalid.example/hook
      http.client.InvalidURL  "nonnumeric port: 'p@ssw0rd-42@alerts.invalid.example'"

    https://sdp-alerts:p%40ss%3Aw0rd%2F42@alerts.invalid.example/hook
      http.client.InvalidURL  "nonnumeric port: 'w0rd/42@alerts.invalid.example'"

The third form is why the secret used below contains an ``@`` but no ``:``: a
colon inside the password moves the split and only a suffix of the secret
reaches the message, which would make a scan for the whole secret miss a real
leak. The same URL with the userinfo stripped raises no ``InvalidURL`` at all -
measured, it attempted a connection and timed out - which is the other reason
no test here lets the real ``urlopen`` run.

So the obvious implementation - hand the configured value to ``urlopen``, record
``str(exc)`` on failure - retains the operator's alert credential in a ring
buffer in the same module, one published key away from an anonymous reader.
``_http_sink_request_parts`` exists to lift the userinfo into an
``Authorization`` header before urllib sees it, and its own docstring records
that this "closes that too"; the alert path has to go through it, plus its own
scheme gate, since that helper does not check the scheme.

Measured against a throwaway implementation of exactly that obvious shape
(``alert_urlopen = urlopen``; raw configured value into ``UrlRequest``;
``record_observability_export_error(f"alert delivery failed: {exc}")``; the gap
report enriched with ``list_request_observations(limit=5)``; an
``alert_webhook_target`` published beside the log sink's ``target``):

    test 1  ('decoded secret', 'retained store _EXPORT_ERRORS')
    test 2  tenant_id, actor, request_id and the concrete dataset path, all four
            under $.recent_requests[0]
    test 3  the paging host on GET /enterprise/observability, and a third
            alert_* key in the published sink status - on the file-sink branch
            only, which is why that test is parametrized over both

3 failed, 1 passed against that implementation; 4 failed against current HEAD
(no seam to patch); 4 passed against a stripping implementation that sends only
the gap report and publishes no target.

Each test pairs a **liveness** assertion with a **non-disclosure** assertion,
because a non-disclosure assertion alone passes vacuously against a product that
delivers nothing: on the parent head "the secret is absent from every surface"
was true and measured nothing. The liveness half is that a delivery was
attempted through the module's own seam, which is also what keeps these tests
meaningful if delivery is later removed or short-circuited.

**Why no test here drives delivery through a request.** A fire-and-forget
``asyncio.create_task`` alert POST is cancelled under ``TestClient`` and
completes only under a real server, and every test in this repository uses
``TestClient`` - so a request-driven delivery assertion would measure the test
client, not the product, and a request-driven *non*-delivery assertion would
pass for the wrong reason. These tests therefore call the **evaluation
function** directly, which is where the settled design puts the send:
``note_governed_request_without_evidence`` is synchronous, and the probe rule's
site (``connectors.connector_probe``) is reached from a ``def`` route handler,
which FastAPI already runs off the event loop in a worker thread - the
arrangement ``record_request_observation`` relies on. Routing must not fire from
``build_observability_manifest()`` or ``prometheus_metrics_text()``: both are
reachable anonymously, so sending from the read path would turn any anonymous
GET into an outbound POST to the operator's endpoint. ``_published_surfaces()``
below fetches both of them on every test, so an implementation that sends from
the read path trips the attempt counters these tests assert on.

Names this file pins, because a test cannot observe a seam it cannot address:
``observability.alert_urlopen``, the alert path's own ``urlopen`` seam, separate
from the log sink's ``urlopen`` name. Everything else is reached by enumeration
- the retained stores are discovered by reflection over the module rather than
listed - so a ring added by the routing change is scanned without being named
here, and ``tests/test_module_state_coverage.py`` separately forces it into the
isolation fixture.
"""

from __future__ import annotations

import collections
import http.client
import json
from base64 import b64encode
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import quote, unquote, urlsplit
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sdp import observability as obs  # noqa: E402
from sdp.api import app  # noqa: E402


client = TestClient(app)

# One operator-configured webhook at a host that does not resolve, with a secret
# that needs percent-encoding in a URL - so the encoded and decoded forms differ
# and a scan for one does not accidentally cover the other.
ALERT_HOST = "alerts.invalid.example"
ALERT_USER = "sdp-alerts"
ALERT_SECRET = "p@ssw0rd-42"
ALERT_SECRET_ENCODED = quote(ALERT_SECRET, safe="")
ALERT_WEBHOOK = f"https://{ALERT_USER}:{ALERT_SECRET_ENCODED}@{ALERT_HOST}/hook"

# Every form the secret can take on the way to a surface, enumerated rather than
# assumed to be one string - the method ``tests/test_source_system_redaction.py``
# arrived at after an equality assertion over one DSN form let five others
# through. A scan for the decoded value alone misses the form the configured URL
# is written in; a scan for both misses the header a correct implementation
# builds out of them.
CREDENTIAL_FORMS = [
    ("decoded secret", ALERT_SECRET),
    ("percent-encoded secret", ALERT_SECRET_ENCODED),
    ("userinfo authority", f"{ALERT_USER}:{ALERT_SECRET_ENCODED}@{ALERT_HOST}"),
    ("whole configured url", ALERT_WEBHOOK),
    (
        "basic header payload",
        b64encode(f"{ALERT_USER}:{ALERT_SECRET}".encode("utf-8")).decode("ascii"),
    ),
]

# The firing condition. ``policy_audit_gap`` is the one published rule this
# service already evaluates in process, and its evaluation function is the send
# site the settled design names. Its key is a route **template**: measured,
# ``governed_evidence_gap_report()["routes"]`` holds exactly this string with the
# placeholder intact, never a dataset id.
GAP_ROUTE_TEMPLATE = "GET /catalog/datasets/{dataset_id}"

# A retained observation row, for the fields an alert payload must not carry.
# ``tenant_id`` and ``actor`` are caller-asserted (the manifest declares them in
# ``caller_asserted_fields``) and ``route`` here is a concrete path, not a
# template - the three reasons ``build_observability_manifest`` publishes no
# per-request feed.
ROW_TENANT = "tenant-leak-probe"
ROW_ACTOR = "actor-leak-probe"
ROW_PATH = "/catalog/datasets/crm-customer-master"
ROW_REQUEST_ID = "req-leak-probe"

# ``_sink_status`` returns from two places - an early return when no log sink is
# set, and the full status when one is - and **both** publish the alert fields.
# A key added to one branch is invisible to a test that exercises the other:
# measured against the throwaway implementation, the no-sink branch published
# ['alert_webhook_configured', 'alert_webhook_routing'] while the file-sink
# branch published those plus 'alert_webhook_target'. This is the same
# branch-shaped blindness this module's own history records for the ``file://``
# target, so the published-key test runs over both.
LOG_SINK_BRANCHES = ["no_log_sink", "file_log_sink"]


class _FakeAlertResponse:
    """Stand-in for the object an alert POST returns, usable as a context manager.

    The log sink calls ``with urlopen(request, timeout=...)`` and the alert path
    is expected to mirror that, but a caller that does not use ``with`` must not
    make this recorder lie about whether a send happened, so both shapes work.
    """

    status = 204

    def read(self) -> bytes:
        """Return an empty body, as a webhook acknowledgement normally does."""
        return b""

    def __enter__(self) -> "_FakeAlertResponse":
        """Allow ``with alert_urlopen(...)``."""
        return self

    def __exit__(self, *exc_info: object) -> bool:
        """Never suppress an exception raised inside the ``with`` body."""
        return False


def _invalid_url_failure(url: str) -> http.client.InvalidURL:
    """Reproduce, from the URL the seam was handed, the error real urllib raises.

    Measured: ``urllib.request.Request`` unquotes the authority and
    ``http.client`` then splits the **whole** authority - userinfo included - at
    its last colon and raises ``InvalidURL`` quoting the right-hand side. This
    formula reproduces all three measured messages exactly.

    Derived from the delivered URL rather than hard-coded, which is the
    difference between measuring the product and measuring the test: a
    hard-coded message carrying the secret would fail any implementation that
    merely logs an exception string, including one that correctly stripped the
    credential first. Built here rather than letting urllib run because a test
    must not depend on the DNS or proxy of the machine running it - measured,
    the stripped form of this URL attempts a real connection.
    """
    authority = unquote(urlsplit(url).netloc)
    return http.client.InvalidURL(f"nonnumeric port: {authority.rpartition(':')[2]!r}")


def _install_alert_seam(
    monkeypatch: pytest.MonkeyPatch,
    *,
    failure_from_url: Any = None,
) -> list[dict[str, Any]]:
    """Replace the alert path's ``urlopen`` seam and record what it is handed.

    Returns the list of recorded attempts; each entry carries the ``url`` and
    the request ``body`` as the seam received them. ``failure_from_url`` builds
    the exception to raise after recording, from the URL actually delivered, so
    a test can exercise the failure path - the path that decides what a retained
    error ring ends up holding - while still proving a send was attempted.

    The recorder accepts a ``urllib.request.Request`` or a bare URL string with
    the body in ``data``, because the delivery call shape is the implementer's
    choice and this file is about disclosure, not call style.

    Nothing here touches the network. That is deliberate rather than
    convenient: a test that let the real ``urlopen`` run would depend on the
    DNS and proxy of the machine running it, and the leak under test does not
    need a connection - ``http.client`` raises on the authority before
    connecting.
    """
    attempts: list[dict[str, Any]] = []

    def _record(request: Any, *args: Any, **kwargs: Any) -> _FakeAlertResponse:
        """Record one delivery attempt, then optionally fail it."""
        url = getattr(request, "full_url", None) or str(request)
        body = getattr(request, "data", None)
        if body is None:
            body = kwargs.get("data")
        attempts.append({"url": url, "body": body})
        if failure_from_url is not None:
            raise failure_from_url(url)
        return _FakeAlertResponse()

    # ``raising=True`` on purpose: with routing unimplemented there is no seam,
    # and these tests must fail at the missing capability rather than invent an
    # attribute and then pass a disclosure scan over traffic that never existed.
    monkeypatch.setattr(obs, "alert_urlopen", _record, raising=True)
    return attempts


@pytest.fixture
def configured_alert_webhook(monkeypatch: pytest.MonkeyPatch) -> str:
    """Configure one credential-bearing webhook and no log sink.

    The log sink is removed so nothing written to ``_EXPORT_ERRORS`` during the
    test can have come from the sink path, leaving the alert path as the only
    writer a leak can be attributed to.
    """
    monkeypatch.setenv("SDP_ALERT_WEBHOOK_URL", ALERT_WEBHOOK)
    monkeypatch.delenv("SDP_LOG_SINK_URL", raising=False)
    return ALERT_WEBHOOK


def _retained_stores() -> dict[str, Any]:
    """Every module-level mutable container in ``sdp.observability``, by reflection.

    Enumerated rather than listed, for the reason
    ``tests/test_module_state_coverage.py`` gives about the isolation fixture's
    hand-written inventory: a ring added by the routing change is covered here
    without anyone remembering to add it. This is how the request-observation
    rows, the existing export-error ring, the sink breaker and any new
    alert-specific ring and breaker all get scanned by one assertion. Dunder
    attributes are skipped - ``__builtins__`` is a dict of the entire builtins
    namespace and is not state this module retains.
    """
    return {
        name: value
        for name, value in sorted(vars(obs).items())
        if not name.startswith("__")
        and isinstance(value, (collections.deque, dict, list, set))
    }


def _published_surfaces() -> dict[str, str]:
    """Fetch the two anonymous surfaces plus their builders, as text to scan.

    Both routes are in ``enterprise_evidence.OPEN_PROOF_ENDPOINTS`` and are
    fetched with no actor, no tenant header and no credential - the reader this
    family is about. The builders are called directly as well, because the
    manifest is also embedded in the enterprise evidence pack.
    """
    manifest_response = client.get("/enterprise/observability")
    metrics_response = client.get("/metrics")
    assert manifest_response.status_code == 200, manifest_response.text
    assert metrics_response.status_code == 200, metrics_response.text
    return {
        "GET /enterprise/observability": manifest_response.text,
        "GET /metrics": metrics_response.text,
        "build_observability_manifest()": json.dumps(
            obs.build_observability_manifest(), ensure_ascii=False, default=str
        ),
        "prometheus_metrics_text()": obs.prometheus_metrics_text(),
    }


def _as_text(value: Any) -> str:
    """Render one retained store as JSON text, deque and set included."""
    if isinstance(value, (collections.deque, set)):
        value = list(value)
    return json.dumps(value, ensure_ascii=False, default=str)


def _iter_json_strings(value: Any, path: str = "$") -> Iterator[tuple[str, str]]:
    """Walk a decoded payload, yielding ``(json path, text)`` for keys and string leaves.

    Recursive because an alert payload is nested: a check over top-level values
    would miss a tenant id inside a list of enriching observation rows, which is
    exactly the shape the obvious enrichment produces.

    Mapping **keys** are yielded as well as values, which is not a flourish: the
    gap report is a map *keyed by route*, so a payload that carried concrete
    paths would carry them as keys and a leaves-only walk would report a clean
    payload. The first version of this helper walked leaves only and had exactly
    that hole.
    """
    if isinstance(value, dict):
        for key, item in value.items():
            where = f"{path}.{key}"
            if isinstance(key, str):
                yield f"{where} (key)", key
            yield from _iter_json_strings(item, where)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _iter_json_strings(item, f"{path}[{index}]")
    elif isinstance(value, str):
        yield path, value


def _iter_json_keys(value: Any) -> Iterator[str]:
    """Walk a decoded payload, yielding every mapping key at any depth."""
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from _iter_json_keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_json_keys(item)


def test_a_credential_bearing_alert_webhook_never_reaches_a_published_surface(
    configured_alert_webhook: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A webhook secret must not survive a failed delivery, in any form.

    The defect this refuses: the obvious routing implementation hands the
    configured value to ``urlopen`` and records ``str(exc)`` when it fails.
    Measured against the real ``urllib`` on this interpreter, a userinfo URL
    raises ``http.client.InvalidURL`` whose message is the decoded authority
    verbatim - ``"nonnumeric port: 'p@ssw0rd-42@alerts.invalid.example'"`` - so the
    operator's alert credential is retained in a ring buffer in the module whose
    manifest answers anonymously. That module already withholds ``_EXPORT_ERRORS``
    from the manifest for this reason, which means one published key is the only
    thing between that string and an anonymous reader.

    The measurement: configure one webhook with a percent-encoded secret at a
    host that does not resolve, fire the one rule this service evaluates, fail
    the delivery with the message urllib really produces **for the URL the
    implementation actually delivered**, then scan five credential forms over
    four published surfaces and every mutable store the module retains.

    Because the failure is derived from the delivered URL, this measures the
    strip and not the logging: an implementation that lifts the userinfo into an
    ``Authorization`` header before the seam leaves nothing for the error text
    to quote, and may record it. One that posts the configured value verbatim
    retains the secret. Measured against the throwaway obvious implementation,
    one hit - the decoded secret in ``_EXPORT_ERRORS`` - and zero against the
    stripping implementation.
    """
    attempts = _install_alert_seam(monkeypatch, failure_from_url=_invalid_url_failure)

    obs.note_governed_request_without_evidence(GAP_ROUTE_TEMPLATE)

    assert attempts, (
        "no delivery was attempted through observability.alert_urlopen, so this "
        "scan would pass over traffic that never existed - alert routing is the "
        "capability under test"
    )

    haystacks = dict(_published_surfaces())
    haystacks.update(
        {
            f"retained store {name}": _as_text(value)
            for name, value in _retained_stores().items()
        }
    )
    haystacks["sink_breaker_state()"] = _as_text(obs.sink_breaker_state())

    leaks = [
        (label, where)
        for label, form in CREDENTIAL_FORMS
        for where, text in haystacks.items()
        if form in text
    ]
    assert not leaks, (
        f"the alert webhook credential appears on {len(leaks)} surface(s): "
        f"{leaks}; scanned {sorted(haystacks)}"
    )


def test_the_alert_payload_carries_no_caller_controlled_or_tenant_identifying_content(
    configured_alert_webhook: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The alert body must carry the rule, not the traffic.

    The defect this refuses: the obvious way to make an alert actionable is to
    attach recent context, and the context this module has is
    ``list_request_observations()`` - rows whose ``route`` is a concrete path
    (``/catalog/datasets/crm-customer-master``) and whose ``tenant_id``,
    ``actor`` and ``request_id`` are caller-asserted. Those are the three facts
    ``build_observability_manifest`` names when it refuses to publish a
    per-request feed, and an alert webhook is a third-party operator endpoint,
    not an authenticated tenant surface - so attaching the rows re-exports one
    tenant's governed-access activity off-box, with the values chosen by whoever
    triggered the alert.

    What is in scope at the send site is safe and must stay the only thing sent:
    measured, ``governed_evidence_gap_report()["routes"]`` is keyed by the route
    **template** ``GET /catalog/datasets/{dataset_id}``, placeholder intact.

    The measurement: retain one row carrying a tenant, an actor, a request id
    and a concrete dataset path; fire the rule; decode the delivered body and
    assert none of those four values appears at any depth **as a value or as a
    key**, that no per-request field name is a payload key, and that any
    route-shaped text keeps its placeholder. Measured against the throwaway
    obvious implementation, four hits, all under ``$.recent_requests[0]``.
    """
    obs.record_request_observation(
        obs.build_request_observation(
            method="GET",
            route=ROW_PATH,
            status_code=200,
            latency_ms=1.0,
            headers={"X-SDP-Tenant": ROW_TENANT, "X-SDP-Actor": ROW_ACTOR},
            request_id=ROW_REQUEST_ID,
            evidence_ids=(),
        ),
        export=False,
    )
    attempts = _install_alert_seam(monkeypatch)

    obs.note_governed_request_without_evidence(GAP_ROUTE_TEMPLATE)

    assert attempts, (
        "no delivery was attempted through observability.alert_urlopen, so there "
        "is no payload to inspect and this test would pass vacuously"
    )
    body = attempts[-1]["body"]
    assert body, f"the delivery carried no body: {attempts[-1]!r}"
    payload = json.loads(body.decode("utf-8") if isinstance(body, bytes) else body)

    forbidden_values = {
        "caller-asserted tenant_id": ROW_TENANT,
        "caller-asserted actor": ROW_ACTOR,
        "caller-asserted request_id": ROW_REQUEST_ID,
        "concrete dataset path": ROW_PATH,
    }
    found = sorted(
        f"{label} at {where}"
        for where, text in _iter_json_strings(payload)
        for label, value in forbidden_values.items()
        if value in text
    )
    assert not found, f"the alert payload carries caller-controlled content: {found}"

    # The field names too, not only this row's values: a payload that carries
    # *some* caller's tenant and actor is the defect, and the row this test
    # retains is only one instance of it.
    per_request_keys = sorted(
        {"tenant_id", "actor", "request_id", "evidence_ids"} & set(_iter_json_keys(payload))
    )
    assert not per_request_keys, (
        f"the alert payload declares per-request fields: {per_request_keys}; a "
        "field the manifest refuses to publish per request must not be a payload key"
    )

    routes = [
        text
        for _, text in _iter_json_strings(payload)
        if text.startswith(("GET /", "POST /", "PATCH /", "DELETE /"))
    ]
    concrete = sorted(route for route in routes if "{" not in route)
    assert not concrete, (
        f"the alert payload names concrete request paths: {concrete}; the gap "
        "report is keyed by route template and the payload must stay that way"
    )


@pytest.mark.parametrize("log_sink_branch", LOG_SINK_BRANCHES)
def test_the_open_manifest_names_no_alert_target_host(
    log_sink_branch: str,
    configured_alert_webhook: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Recommendation, pinned: publish that a webhook is configured, never where it points.

    The log sink publishes a redacted ``target`` (host and port) because an
    operator must be able to tell a misconfigured sink from an unconfigured one,
    and the ``file://`` form is reduced to the constant ``local_file`` precisely
    because a path can carry an internal hostname. The alert webhook has no such
    published target today - only ``alert_webhook_configured: bool`` - and
    adding one would be a **new** internal-topology disclosure on a surface that
    answers anonymously: the hostname of the operator's paging endpoint, which
    is not a fact about this service's governance at all. The diagnostic need is
    already met without a host - ``invalid_configuration`` for a value that can
    never be posted to, ``alert_webhook_routing`` for the capability - so the
    recommendation is **do not publish an alert target, redacted or otherwise**.

    This pins it in the only way that cannot pass vacuously: with routing live
    and a delivery attempted, the webhook-describing keys in the published sink
    status must be exactly the two that exist today, the host must appear
    nowhere on either open surface, and ``alert_routing`` must stop claiming
    nothing is delivered.

    Run over **both** ``_sink_status`` branches. It returns from two places and
    both publish the alert fields, so a key added to one is invisible to a test
    that exercises the other: measured against the throwaway obvious
    implementation, the no-sink branch published two alert keys and the
    file-sink branch published three, the extra one being
    ``alert_webhook_target`` naming the paging host.
    """
    if log_sink_branch == "file_log_sink":
        monkeypatch.setenv(
            "SDP_LOG_SINK_URL", (tmp_path / "requests.jsonl").as_uri()
        )

    attempts = _install_alert_seam(monkeypatch)

    obs.note_governed_request_without_evidence(GAP_ROUTE_TEMPLATE)

    assert attempts, (
        "no delivery was attempted through observability.alert_urlopen, so the "
        "published status could not be describing a live routing path"
    )

    surfaces = _published_surfaces()
    host_leaks = sorted(where for where, text in surfaces.items() if ALERT_HOST in text)
    assert not host_leaks, (
        f"the alert target host appears on {host_leaks}; an open surface must not "
        "name the operator's paging endpoint, even redacted to host and port"
    )

    manifest = obs.build_observability_manifest()
    sink = manifest["structured_logs"]["sink"]
    alert_keys = sorted(key for key in sink if key.startswith("alert"))
    assert alert_keys == ["alert_webhook_configured", "alert_webhook_routing"], (
        f"the sink status grew a webhook-describing key on the {log_sink_branch} "
        f"branch: {alert_keys}; a new key here is published anonymously"
    )
    assert sink["alert_webhook_configured"] is True
    assert manifest["alert_routing"] != "declared_unimplemented", (
        "something posts to the webhook now, so the open surface must not keep "
        "telling an operator that nothing does"
    )
