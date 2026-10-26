from __future__ import annotations

import json
import os
import threading
import time
from base64 import b64encode
from collections import deque
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse, urlunsplit
from urllib.request import Request as UrlRequest, urlopen
from urllib.request import url2pathname
from uuid import uuid4

from anyio import to_thread

from sdp_core import enterprise_controls_manifest

from .catalog import count_audit_events, list_audit_events, list_datasets
from .evidence import count_policy_decisions, list_policy_decisions


_REQUEST_OBSERVATIONS: deque[dict[str, Any]] = deque(maxlen=500)
_EXPORT_ERRORS: deque[dict[str, Any]] = deque(maxlen=50)


def request_id_header() -> str:
    return os.getenv("SDP_REQUEST_ID_HEADER", "X-Request-Id")


def _header_value(headers: Any, name: str, default: str | None = None) -> str | None:
    if not headers:
        return default

    value = headers.get(name) if hasattr(headers, "get") else None
    if value:
        return str(value)

    lower_name = name.lower()
    try:
        for key, candidate in headers.items():
            if str(key).lower() == lower_name:
                return str(candidate)
    except AttributeError:
        return default

    return default


def request_id_from_headers(headers: Any) -> str:
    return _header_value(headers, request_id_header()) or f"sdp-{uuid4().hex}"


class SinkConfigurationError(ValueError):
    """The configured observability sink can never be written."""


def _file_sink_path(sink_url: str, parsed: Any) -> Path:
    """Resolve a ``file://`` sink to an absolute path, or refuse the configuration.

    This folded a ``file://`` URL's authority into the path
    (``raw_path = f"//{parsed.netloc}{raw_path}"``), and ``_export_to_sink``
    defaulted a scheme-less value to ``file``. So README's own documented value
    did not mean what it reads as:

        file://.local/sdp-requests.jsonl  ->  //.local/sdp-requests.jsonl
        configured                        ->  configured   (a file in the CWD)
        .local/x.jsonl                    ->  .local/x.jsonl

    The first is ``.local`` at the **filesystem root**. The shipped image runs
    ``USER 10001:10001`` with only ``/data`` writable, so the open raises
    ``PermissionError`` on every request, the breaker opens after five, and the
    rest are dropped silently - while ``GET /enterprise/observability`` kept
    reporting ``structured_logs.status: "implemented"`` and a configured sink.
    The reason lived only in ``_EXPORT_ERRORS``, which the manifest withholds,
    so no surface could tell an operator the log was empty. The relative forms
    also explain the stray files that appeared in the repository root during
    development.

    Failing closed at resolution time, with the reason named, is the point: a
    sink that cannot be written is a configuration error, not a per-request
    exception to swallow.
    """
    if os.name == "nt":
        # Windows keeps the UNC and drive-letter forms the original supported.
        if parsed.netloc and not parsed.path:
            return Path(url2pathname(parsed.netloc))
        raw_path = url2pathname(parsed.path or sink_url)
        if len(raw_path) >= 3 and raw_path[0] in {"\\", "/"} and raw_path[2] == ":":
            raw_path = raw_path[1:]
        if parsed.netloc:
            raw_path = f"//{parsed.netloc}{raw_path}"
        return Path(raw_path)

    # None of these messages echo the configured value. ``_sink_status`` is
    # published unauthenticated, and the value carries the sink's internal host
    # and path - the authority component ``_redacted_sink_target`` exists to
    # suppress. The first draft of this repair interpolated ``sink_url`` and a
    # retained test caught it publishing ``logs.internal.corp`` and a tenant
    # path segment.
    if not parsed.scheme:
        raise SinkConfigurationError(
            "SDP_LOG_SINK_URL must name a scheme: use file:///absolute/path for a "
            "local file sink, or an http(s) URL"
        )
    if parsed.netloc:
        raise SinkConfigurationError(
            "a file:// sink must have an empty authority: file://host/path is not "
            "supported, and file://relative/path is not a relative path"
        )
    raw_path = url2pathname(parsed.path or "")
    path = Path(raw_path)
    if not path.is_absolute():
        raise SinkConfigurationError(
            "SDP_LOG_SINK_URL must be an absolute path (file:///data/...)"
        )
    return path


def _http_sink_request_parts(sink_url: str, parsed: Any) -> tuple[str, dict[str, str]]:
    """Resolve an ``http(s)`` sink to a connectable URL plus request headers.

    The whole configured value was handed to ``urlopen``, and
    ``urllib.request.Request`` keeps the authority verbatim - userinfo
    included - as the connection host. So the documented form of a push URL for
    every common log sink (Loki, Elastic, a signed webhook) could not work.
    Measured before the repair with
    ``SDP_LOG_SINK_URL=https://sdp-ingest:s3cr3t-token@logs.example.net/push``::

        urllib connects to      sdp-ingest:s3cr3t-token@logs.example.net
        http.client            -> InvalidURL: nonnumeric port
        _sink_status()         -> {"configured": true, "target": "logs.example.net"}

    Every export failed, the breaker opened after five, and the manifest kept
    reporting a configured sink - the exact "published number disagrees with the
    code enforcing it" shape this product exists to refuse. Worse, the
    ``InvalidURL`` message quotes the authority, so ``str(exc)`` carried the sink
    credential into the retained ``_EXPORT_ERRORS`` ring. Removing the userinfo
    before the value reaches urllib closes that too.

    The credential moves to the header it belongs in: ``Basic`` when a password
    is present, ``Bearer`` when the userinfo is a single token. Both
    subcomponents are percent-decoded, because a password containing ``@`` or
    ``:`` has to be encoded in the URL. The returned URL is rebuilt from the
    parsed parts with the userinfo and fragment dropped, so nothing downstream
    re-derives them.
    """
    try:
        host = parsed.hostname
    except ValueError as exc:  # pragma: no cover - defensive: malformed authority
        raise SinkConfigurationError(
            "SDP_LOG_SINK_URL has an authority that cannot be parsed as a host"
        ) from exc
    if not host:
        raise SinkConfigurationError(
            "an http(s) SDP_LOG_SINK_URL must name a host (https://host/path)"
        )
    try:
        port = parsed.port
    except ValueError as exc:
        raise SinkConfigurationError(
            "SDP_LOG_SINK_URL has a port that is not a number"
        ) from exc

    headers = {"Content-Type": "application/json"}
    username = unquote(parsed.username) if parsed.username else ""
    password = unquote(parsed.password) if parsed.password else ""
    if password:
        credential = b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
        headers["Authorization"] = f"Basic {credential}"
    elif username:
        headers["Authorization"] = f"Bearer {username}"

    url = urlunsplit(
        (parsed.scheme, _authority(host, port), parsed.path, parsed.query, "")
    )
    return url, headers


# A caller-supplied observation field is bounded in length, and the evidence-id
# list in count. The ring buffer is bounded at 500 *rows* and the rows were
# unbounded in bytes: uvicorn accepts a header of roughly 64 KB, so one
# unauthenticated request produced a six-figure row. Measured with 500
# ``GET /health`` requests - no credentials, no body, nothing that reaches
# policy evaluation - carrying 60,000-character tenant and actor headers and
# twenty evidence ids:
#
#     rows retained 500   bytes retained 70.2 MB   largest row 137 KB
#
# The deque never shrinks, so that is pinned for the process lifetime, and with
# a sink configured the same bytes go out as POSTs - the service becomes an
# amplifier aimed at the operator's log sink. ``docker-compose.yml`` sets no
# memory limit, so the ceiling is the host's.
# With these caps a row's caller-supplied content is at most
# (3 + 32) * 256 bytes, so the 500-row buffer has a ceiling near 4.5 MB instead
# of none. Measured after the cap, same 500 requests: 3.0 MB retained, largest
# row 6 KB (was 70.2 MB and 137 KB).
MAX_OBSERVATION_FIELD_CHARS = 256
MAX_OBSERVATION_EVIDENCE_IDS = 32
_TRUNCATION_MARKER = "...[truncated]"


def _bounded_field(value: str) -> str:
    """Cap one caller-supplied observation field, marking what was cut.

    The marker keeps the row honest: a silently shortened value reads as the
    whole value.
    """
    if len(value) <= MAX_OBSERVATION_FIELD_CHARS:
        return value
    keep = MAX_OBSERVATION_FIELD_CHARS - len(_TRUNCATION_MARKER)
    return value[:keep] + _TRUNCATION_MARKER


def build_request_observation(
    *,
    method: str,
    route: str,
    status_code: int,
    latency_ms: float,
    headers: Any,
    request_id: str,
    evidence_ids: Sequence[str] = (),
    withheld_evidence_id_count: int = 0,
) -> dict[str, Any]:
    """Build one request observation from server-side facts and request headers.

    ``evidence_ids`` is passed in by the caller because it is the one field here
    that must **not** come from the request: it was read from a caller-supplied
    ``X-SDP-Evidence-Ids`` header, which made the governance log's correlation
    key assertable by the caller the line is about - measured, a governed
    preview exported two forged ids while the decision the server recorded was
    absent. ``evidence.collect_request_evidence_ids`` supplies them now, and
    this function no longer reads that header at all.

    ``tenant_id`` and ``actor`` are still header-derived and still
    caller-asserted; that is why the unauthenticated manifest publishes only
    aggregates of these rows (see ``build_observability_manifest``).
    """
    evidence_ids = list(evidence_ids)
    withheld_evidence_ids = (
        max(0, len(evidence_ids) - MAX_OBSERVATION_EVIDENCE_IDS) + withheld_evidence_id_count
    )
    observation = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "request_id": _bounded_field(request_id),
        "tenant_id": _bounded_field(_header_value(headers, "X-SDP-Tenant", "unknown")),
        "actor": _bounded_field(_header_value(headers, "X-SDP-Actor", "anonymous")),
        "route": route,
        "method": method,
        "status_code": status_code,
        "latency_ms": round(latency_ms, 3),
        "evidence_ids": [
            _bounded_field(item) for item in evidence_ids[:MAX_OBSERVATION_EVIDENCE_IDS]
        ],
    }
    if withheld_evidence_ids:
        # Declared rather than silently dropped, like every other bounded list
        # in this product.
        observation["withheld_evidence_id_count"] = withheld_evidence_ids
    return observation


# The alert conditions below were authored rules before any of them was
# computed, and publishing them as a list named "alerts" next to
# ``alert_webhook_configured: true`` read as monitoring that exists. Every
# surface now says which of them this service computes and which it delivers.
#
# Two of the three are computed in process - ``policy_audit_gap`` by
# ``governed_evidence_gap_report`` and ``connector_probe_failure`` by
# ``connector_probe_failure_report`` - and those two are the routable set.
# ``central_workflow_backlog`` is neither: its condition is about GitHub Actions
# run state this service does not observe, and it says so rather than letting
# the id imply coverage. This comment once claimed that no code computed any of
# them, five lines above the function that computes one, and then carried the
# opposite of the truth about delivery once delivery landed. Both are one
# failure: published prose left asserting the inverse of the code beneath it.
# The phrases are deliberately not quoted here - a guard that scans for them
# would match this very comment, which is how four of this cycle's guards came
# to be checked against their own explanations rather than against the product.
ALERT_EVALUATION_STATUS = "declared_not_evaluated"

# Not every rule has the same answer, so a single blanket status at the top of
# the manifest would be wrong however it was written. The per-rule ``evaluated``
# and ``routable`` flags are the truth; this says to read them.
ALERT_EVALUATION_SCOPE = "per_rule"

# ``policy_audit_gap`` evaluated. The declared condition is "preview/query count
# exceeds policy decision or audit event count"; what is computed is its
# per-request form - a policy-gated route answered 2xx while recording no
# evidence at all - which is the same violation seen at the moment it happens
# and names the route it happened on. It is **narrower** than the declared
# comparison: evidence rows removed out of band after the fact are not visible
# here, and the published rule says so rather than letting the id imply
# coverage it does not have.
#
# This could not be evaluated before the request log's ``evidence_ids`` became a
# server fact: the field was read from a caller-supplied header, so "did this
# request record evidence" had no honest answer in process.
MAX_TRACKED_EVIDENCE_GAP_ROUTES = 32
_OTHER_GAP_ROUTES = "...[other routes]"
_GOVERNED_EVIDENCE_GAPS: dict[str, int] = {}


def note_governed_request_without_evidence(route: str) -> None:
    """Count one policy-gated 2xx that recorded no correlatable evidence.

    Bounded by route, like every other map this module publishes: past the cap
    the counts collapse into one declared bucket rather than letting a caller
    that can reach many templates grow the manifest without limit.
    """
    if route in _GOVERNED_EVIDENCE_GAPS:
        _GOVERNED_EVIDENCE_GAPS[route] += 1
    elif len(_GOVERNED_EVIDENCE_GAPS) < MAX_TRACKED_EVIDENCE_GAP_ROUTES:
        _GOVERNED_EVIDENCE_GAPS[route] = 1
    else:
        _GOVERNED_EVIDENCE_GAPS[_OTHER_GAP_ROUTES] = (
            _GOVERNED_EVIDENCE_GAPS.get(_OTHER_GAP_ROUTES, 0) + 1
        )
    # The evaluation event is the send site. Not the read path: this counter is
    # published by two anonymous routes, so routing from there would turn any
    # anonymous GET into an outbound POST at the operator's endpoint. The three
    # early returns above became one branch for this: a routing call reachable
    # from only one of them would deliver for a first-seen route and stay silent
    # once the map was full, which is the arrangement the branch shape invited.
    _route_alert("policy_audit_gap", observed_increment=True)


def governed_evidence_gap_report() -> dict[str, Any]:
    """What this worker observed for the ``policy_audit_gap`` condition."""
    routes = dict(sorted(_GOVERNED_EVIDENCE_GAPS.items()))
    total = sum(routes.values())
    return {
        "observed_total": total,
        "firing": total > 0,
        "routes": routes,
        "measurement_window": "this worker, since start",
    }


# --------------------------------------------------------------------------- #
# Alert routing.
#
# For most of this product's life ``SDP_ALERT_WEBHOOK_URL`` was read in exactly
# one place - ``bool()`` of it for the ``alert_webhook_configured`` field - and
# nothing posted to it, which is why it sat in ``production.py``'s
# ``declared_unimplemented_environment``. Delivery is implemented below. Three
# decisions make it safe to hook onto a per-request evaluation event, and each
# is pinned by a test family rather than left to the reader:
#
# 1. *One POST per firing episode, not per increment.* The ``policy_audit_gap``
#    counter is incremented from the request middleware, once per policy-gated
#    2xx that recorded no evidence - and that surface takes no credential.
#    Measured, 25 anonymous probe requests complete in 197.1 ms, so "POST while
#    the rule is firing" evaluated at the increment site is 25 outbound POSTs
#    per 200 ms of uncredentialed traffic, aimed at a URL the operator supplied.
#    So delivery fires on the false->true edge of a rule's own ``firing`` flag
#    and the 2nd..Nth increment is counted and dropped. The bound is a number an
#    operator can budget against: between resets a worker sends at most
#    ``len(ROUTABLE_ALERT_RULE_IDS)`` POSTs however long the burst runs.
#
# 2. *Re-arm follows the rule, not a clock.* ``governed_evidence_gap_report()``
#    reports ``firing`` as ``observed_total > 0`` and nothing decrements that
#    counter, so in a deployed worker a rule that has fired once stays firing
#    until the worker restarts. A minimum-interval rule would therefore re-post
#    forever on a condition that can never clear; "first transition only" would
#    make the next genuine episode silent. The latch is cleared when the rule
#    itself stops firing, which is also what ``reset_alert_routing()`` does.
#
# 3. *Never from the read path.* ``build_observability_manifest`` and
#    ``prometheus_metrics_text`` are reachable anonymously through
#    ``GET /enterprise/observability`` and ``GET /metrics``, and the manifest
#    already publishes each rule's ``firing`` flag - exactly the value a
#    read-path implementation would act on. Routing is called only from the two
#    evaluation sites, so an anonymous GET cannot make this service post
#    anywhere.
#
# What is *not* implemented, stated here rather than left to be inferred from
# the absence of code: there is no retry, no queue, no durable record of a
# failed delivery beyond the bounded ring below, and no delivery at all for
# ``central_workflow_backlog`` - it is published and not routable, because its
# condition is about GitHub Actions run state this service does not observe and
# listing it as routable would promise a delivery that can never be triggered.
# --------------------------------------------------------------------------- #

ALERT_ROUTING_STATUS = "implemented"

# The alert path's own ``urlopen``, kept separate from the log sink's name. A
# shared seam would make a webhook POST indistinguishable from a log export in
# the tests that already assert on what the sink sent.
alert_urlopen = urlopen

# How long the evaluating request waits for the delivery thread before returning.
# The alert path must not charge a governed request for an unreachable webhook:
# measured on the log sink, which the request *does* await, a socket that accepts
# the handshake and never answers cost 507.8-514.5 ms per request at a 500 ms
# timeout. So delivery runs on its own thread and the evaluation site joins it
# only for this budget - long enough that a healthy webhook is observed inline
# (which is what makes "exactly one POST" measurable at all), short enough that a
# wedged one cannot become the response's latency. Past the budget the thread
# keeps going and its outcome lands in the counters below.
ALERT_HANDSHAKE_BUDGET_SECONDS = 0.25

MAX_RETAINED_ALERT_ERRORS = 50

# Per-connector counts of probes whose verdict basis failed for a reason this
# build owns, and the verification mix every returning probe reported. Keyed by
# connector id, which ``connector_registry_manifest()`` bounds at four - dataset
# ids are caller-supplied and a caller that can register datasets could
# otherwise grow a published map without limit.
_CONNECTOR_PROBE_FAILURES: dict[str, int] = {}
_CONNECTOR_PROBE_VERIFICATIONS: dict[str, int] = {}

# The latch and the counters, plus a generation marker. A delivery thread that
# outlives the episode it was started for - a wedged webhook holds one for the
# whole alert timeout - must not write its outcome into a later episode's
# counters, so it carries the generation it started under and
# ``reset_alert_routing`` bumps it.
_ALERT_ROUTING: dict[str, Any] = {
    "generation": 0,
    "latched": set(),
    "transitions": {},
    "suppressed": {},
    "attempted": {},
    "succeeded": {},
    "failed": {},
}
_ALERT_ROUTING_LOCK = threading.Lock()

# Why a failure is retained as a type and a stage rather than as a message:
# measured with the real ``urllib`` on this interpreter, a userinfo-bearing
# webhook never reaches the network - ``urllib.request.Request`` unquotes the
# authority, ``http.client`` splits the whole thing at its last colon and raises
# before connecting - and the message is the decoded credential verbatim::
#
#     https://sdp-alerts:p%40ssw0rd-42@alerts.invalid.example/hook
#       InvalidURL  "nonnumeric port: 'p@ssw0rd-42@alerts.invalid.example'"
#
# ``_alert_request_parts`` lifts the userinfo into an ``Authorization`` header
# before urllib sees it, so that particular message cannot arise; recording
# ``str(exc)`` anyway would still put the operator's paging host into a ring in
# the module whose manifest answers anonymously, one published key away from a
# reader. The exception type and the stage are the diagnosis an operator needs
# and carry no part of the URL.
_ALERT_ERRORS: deque[dict[str, Any]] = deque(maxlen=MAX_RETAINED_ALERT_ERRORS)


def note_connector_probe(
    connector_id: str,
    failure_reason: str,
    verification_counts: dict[str, int],
) -> None:
    """Record one connector probe's verdict for the ``connector_probe_failure`` rule.

    Called from ``connectors.connector_probe`` itself rather than from the route
    or the middleware: ``demo_smoke`` calls that function directly four times
    and twenty-odd tests call it directly too, so a counter hooked at the route
    would miss every one of them.

    ``failure_reason`` is empty for every outcome the seed deployment produces.
    The verification mix is accumulated for every probe that returned, because a
    zero on this rule is not a claim that the controls passed - measured across
    the five pairs that return on seed data, 19 of 20 control rows rest on
    ``proof_route_served``, which is a fact about the route table.
    """
    for level, count in verification_counts.items():
        _CONNECTOR_PROBE_VERIFICATIONS[level] = (
            _CONNECTOR_PROBE_VERIFICATIONS.get(level, 0) + count
        )
    if failure_reason:
        _CONNECTOR_PROBE_FAILURES[connector_id] = (
            _CONNECTOR_PROBE_FAILURES.get(connector_id, 0) + 1
        )
    _route_alert("connector_probe_failure", observed_increment=bool(failure_reason))


def connector_probe_failure_report() -> dict[str, Any]:
    """What this worker observed for the ``connector_probe_failure`` condition."""
    connectors = dict(sorted(_CONNECTOR_PROBE_FAILURES.items()))
    total = sum(connectors.values())
    return {
        "observed_total": total,
        "firing": total > 0,
        "connectors": connectors,
        # Published beside the zero, so "not firing" cannot be read as "every
        # declared control was exercised and passed".
        "control_verification_counts_observed": {
            level: _CONNECTOR_PROBE_VERIFICATIONS.get(level, 0)
            for level in ("runtime_probe_verified", "proof_route_served", "declared_only")
        },
        "measurement_window": "this worker, since start",
    }


# The routable rules, as a mapping from id to the report function that answers
# "is this firing". ``ROUTABLE_ALERT_RULE_IDS`` is derived from it rather than
# written out, so a rule cannot be declared routable without a condition this
# service computes.
_ROUTABLE_ALERT_RULES = {
    "policy_audit_gap": governed_evidence_gap_report,
    "connector_probe_failure": connector_probe_failure_report,
}

ROUTABLE_ALERT_RULE_IDS = tuple(sorted(_ROUTABLE_ALERT_RULES))


def _alert_timeout_seconds() -> float:
    """The per-delivery socket timeout, in seconds."""
    return int(os.getenv("SDP_ALERT_TIMEOUT_MS", "500")) / 1000


def _alert_request_parts(webhook_url: str) -> tuple[str, dict[str, str]]:
    """Resolve the configured webhook to a connectable URL plus request headers.

    Two gates, in this order. The scheme must be ``http`` or ``https``:
    ``_http_sink_request_parts`` does not check it, and the sink's wider set is
    wider than an alert webhook needs - ``file://`` is not an outbound POST.
    Then the userinfo is lifted into an ``Authorization`` header by that helper,
    which is the whole reason the alert path goes through it.

    The delegate's messages name ``SDP_LOG_SINK_URL``, so they are re-pointed at
    the variable the operator actually set. None of them quotes the URL.
    """
    parsed = urlparse(webhook_url)
    if parsed.scheme not in {"http", "https"}:
        raise SinkConfigurationError(
            "SDP_ALERT_WEBHOOK_URL must use the http or https scheme"
        )
    try:
        return _http_sink_request_parts(webhook_url, parsed)
    except SinkConfigurationError as exc:
        raise SinkConfigurationError(
            str(exc).replace("SDP_LOG_SINK_URL", "SDP_ALERT_WEBHOOK_URL")
        ) from exc


def _alert_payload(rule_id: str) -> bytes:
    """Serialise the alert body: the rule and its own report, and nothing else.

    What is deliberately absent is the traffic. The context this module holds is
    ``list_request_observations()``, whose rows carry a concrete request path
    plus a caller-asserted ``tenant_id``, ``actor`` and ``request_id`` - the
    three facts ``build_observability_manifest`` names when it refuses to
    publish a per-request feed. An alert webhook is a third-party operator
    endpoint, not an authenticated tenant surface, so attaching those rows would
    re-export one tenant's governed-access activity off-box with the values
    chosen by whoever triggered the alert.

    What a rule's report does carry is already published on the anonymous
    manifest: the gap rule's map is keyed by route **template**, placeholder
    intact, and the probe rule's by registry connector id.
    """
    report = _ROUTABLE_ALERT_RULES[rule_id]()
    body = {
        "service": "semantic-data-portal",
        "alert": "rule_firing",
        "rule_id": rule_id,
        "report": report,
        "delivery": "one POST per firing episode per worker; no retry",
    }
    return json.dumps(body, ensure_ascii=False, sort_keys=True).encode("utf-8")


def _bump_alert_counter(kind: str, rule_id: str, generation: int) -> None:
    """Add one to a per-rule routing counter, unless the episode has been reset."""
    with _ALERT_ROUTING_LOCK:
        if generation != _ALERT_ROUTING["generation"]:
            return
        bucket = _ALERT_ROUTING[kind]
        bucket[rule_id] = bucket.get(rule_id, 0) + 1


def record_alert_routing_error(rule_id: str, stage: str, error_type: str) -> None:
    """Retain one alert-delivery failure, as a type and a stage.

    No message and no URL: see the comment above ``_ALERT_ERRORS``. A failure
    that is swallowed entirely would leave an operator unable to tell a
    suppressed increment from a webhook that never accepted the POST, which is
    the distinction this ring exists to preserve.
    """
    _ALERT_ERRORS.append(
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "rule_id": rule_id,
            "stage": stage,
            "error_type": error_type,
        }
    )


def list_alert_routing_errors(limit: int = MAX_RETAINED_ALERT_ERRORS) -> list[dict[str, Any]]:
    """The retained alert-delivery failures, newest last."""
    return list(_ALERT_ERRORS)[-limit:]


def _deliver_alert(rule_id: str, webhook_url: str, payload: bytes, generation: int) -> None:
    """POST one alert, counting the attempt before it can block.

    Runs on its own thread. The attempt is counted first so that a wedged
    webhook is visible as an attempt rather than as nothing at all; the outcome
    is counted after, and discarded if the episode was reset while this thread
    was waiting.
    """
    _bump_alert_counter("attempted", rule_id, generation)
    stage = "configuration"
    try:
        url, headers = _alert_request_parts(webhook_url)
        request = UrlRequest(url, data=payload, headers=headers, method="POST")
        stage = "delivery"
        # nosemgrep: python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected -- the scheme is allow-listed to {http,https} in _alert_request_parts above
        with alert_urlopen(request, timeout=_alert_timeout_seconds()):
            pass
    except Exception as exc:  # noqa: BLE001 - any delivery failure is the request's to absorb
        # Deliberately broad, and deliberately not ``BaseException``: an alert
        # is a side effect of a governed request, and nothing that happens on
        # the way to the operator's webhook may become that request's response.
        # Measured on the precedent this forecloses - a hook that raised
        # ``OSError`` from inside ``connector_probe`` - the governed probe
        # answered 500 through a real worker and left +1 policy decision with
        # +0 audit events: a decision it never audited.
        _bump_alert_counter("failed", rule_id, generation)
        record_alert_routing_error(rule_id, stage, type(exc).__name__)
    else:
        _bump_alert_counter("succeeded", rule_id, generation)


def _route_alert(rule_id: str, *, observed_increment: bool) -> None:
    """Deliver at most one alert for this rule's current firing episode.

    ``observed_increment`` says whether the caller's own observation moved the
    rule's counter. It is what keeps the suppression count honest: every
    connector probe calls ``note_connector_probe``, most of them reporting no
    failure, and counting those as suppressed increments would publish a
    "thousand gap events suppressed" figure made of healthy traffic.
    """
    firing = bool(_ROUTABLE_ALERT_RULES[rule_id]()["firing"])
    with _ALERT_ROUTING_LOCK:
        latched = _ALERT_ROUTING["latched"]
        if not firing:
            latched.discard(rule_id)
            return
        if rule_id in latched:
            if observed_increment:
                suppressed = _ALERT_ROUTING["suppressed"]
                suppressed[rule_id] = suppressed.get(rule_id, 0) + 1
            return
        latched.add(rule_id)
        transitions = _ALERT_ROUTING["transitions"]
        transitions[rule_id] = transitions.get(rule_id, 0) + 1
        generation = _ALERT_ROUTING["generation"]

    webhook_url = os.getenv("SDP_ALERT_WEBHOOK_URL", "").strip()
    if not webhook_url:
        # The transition is a fact about the rule, not about the operator's
        # configuration: it is counted above either way, and only the delivery
        # is skipped. An unset variable has to make routing a no-op rather than
        # a failed POST - the test suite itself drives this condition, so a rule
        # that posts when unconfigured is a rule that posts from CI.
        return
    worker = threading.Thread(
        target=_deliver_alert,
        args=(rule_id, webhook_url, _alert_payload(rule_id), generation),
        name=f"sdp-alert-{rule_id}",
        daemon=True,
    )
    worker.start()
    worker.join(ALERT_HANDSHAKE_BUDGET_SECONDS)


def alert_routing_state() -> dict[str, Any]:
    """The measured delivery facts, so the manifest reports rather than claims."""
    with _ALERT_ROUTING_LOCK:
        counts = {
            kind: sum(_ALERT_ROUTING[kind].values())
            for kind in ("transitions", "suppressed", "attempted", "succeeded", "failed")
        }
    return {
        "webhook_configured": bool(os.getenv("SDP_ALERT_WEBHOOK_URL", "").strip()),
        "routable_rules": len(ROUTABLE_ALERT_RULE_IDS),
        # Derived from the rules themselves rather than read off the latch: a
        # latch left set across a reset would otherwise publish a firing rule
        # whose counter is zero.
        "firing_rules": sorted(
            rule_id
            for rule_id, report in _ROUTABLE_ALERT_RULES.items()
            if report()["firing"]
        ),
        "transitions_observed": counts["transitions"],
        "suppressed_increments": counts["suppressed"],
        "deliveries_attempted": counts["attempted"],
        "deliveries_succeeded": counts["succeeded"],
        "deliveries_failed": counts["failed"],
        "retained_failures": len(_ALERT_ERRORS),
    }


def _alert_delivery_fields(rule_id: str) -> dict[str, Any]:
    """The per-rule delivery facts the manifest publishes next to the condition."""
    if rule_id not in _ROUTABLE_ALERT_RULES:
        return {"routable": False}
    with _ALERT_ROUTING_LOCK:
        return {
            "routable": True,
            "alerts_delivered": _ALERT_ROUTING["attempted"].get(rule_id, 0),
            "alerts_failed": _ALERT_ROUTING["failed"].get(rule_id, 0),
            "increments_suppressed": _ALERT_ROUTING["suppressed"].get(rule_id, 0),
        }


def reset_alert_routing() -> None:
    """Clear the latch, the counters and the retained failures.

    The generation is bumped rather than reset, so a delivery thread still
    waiting on a webhook from the previous episode cannot write its outcome into
    the next one.
    """
    with _ALERT_ROUTING_LOCK:
        _ALERT_ROUTING["generation"] += 1
        _ALERT_ROUTING["latched"] = set()
        for kind in ("transitions", "suppressed", "attempted", "succeeded", "failed"):
            _ALERT_ROUTING[kind] = {}
    _ALERT_ERRORS.clear()
    _CONNECTOR_PROBE_FAILURES.clear()
    _CONNECTOR_PROBE_VERIFICATIONS.clear()


def _authority(host: str, port: int | None) -> str:
    """Reassemble ``host[:port]`` as a URL authority, bracketing IPv6 literals.

    ``urlparse().hostname`` **strips the RFC 3986 brackets** from an IPv6
    literal, and both callers used to rebuild the authority as ``f"{host}:{port}"``
    - which for an IPv6 host produces a string that is not a URL authority at
    all, because the colons in the address are indistinguishable from the port
    separator. Measured before this repair::

        SDP_LOG_SINK_URL=http://[::1]:8000/x
          rebuilt URL           http://::1:8000/x
          urlopen               URLError: [Errno 97] Address family not supported
          _sink_status()        {"configured": true, "target": "::1:8000"}

        SDP_LOG_SINK_URL=http://[2001:db8::1]:9000/push
          rebuilt URL           http://2001:db8::1:9000/push
          _sink_status()        {"configured": true, "target": "2001:db8::1:9000"}

    So every export failed while the manifest reported a configured sink, and
    the published ``target`` was a malformed authority - the exact pair of
    defects ``_http_sink_request_parts``'s own docstring records for the
    userinfo form and was written to eliminate. It survived for the IPv6 form
    because the repair rebuilt the authority by interpolation instead of asking
    one function to do it.

    One function now, used by both, so the next caller cannot get it wrong. A
    bracketed host is detected by the colon an IPv6 literal must contain and a
    registered name must not.
    """
    bracketed = f"[{host}]" if ":" in host else host
    return f"{bracketed}:{port}" if port is not None else bracketed


def _redacted_sink_target(parsed: Any) -> str:
    """Describe a sink endpoint without the credentials its URL may carry.

    ``urlparse().netloc`` keeps the userinfo component, so reporting it would
    publish a sink credential such as ``https://user:token@host/push`` on the
    unauthenticated observability manifest; a query string can carry one too.
    Only the host and port identify the sink, so only those are reported, and an
    authority that cannot be read becomes an explicit redaction marker rather
    than the raw URL.
    """
    try:
        host = parsed.hostname
    except ValueError:  # pragma: no cover - defensive: malformed authority
        return "redacted"
    if not host:
        return "redacted"
    try:
        port = parsed.port
    except ValueError:
        port = None
    return _authority(host, port)


def _sink_status() -> dict[str, Any]:
    sink_url = os.getenv("SDP_LOG_SINK_URL", "").strip()
    alert_webhook_url = os.getenv("SDP_ALERT_WEBHOOK_URL", "").strip()
    if not sink_url:
        return {
            "configured": False,
            "scheme": "memory",
            "target": "in_process_ring_buffer",
            "alert_webhook_configured": bool(alert_webhook_url),
            "alert_webhook_routing": ALERT_ROUTING_STATUS,
        }

    parsed = urlparse(sink_url)
    scheme = parsed.scheme
    # A configuration that can never be written is reported as such, rather than
    # as a configured sink whose failures are invisible outside _EXPORT_ERRORS.
    invalid_reason: str | None = None
    if scheme == "file":
        try:
            _file_sink_path(sink_url, parsed)
        except SinkConfigurationError as exc:
            invalid_reason = str(exc)
    elif scheme in {"http", "https"}:
        # Validated through the same resolver the export uses, so "configured"
        # cannot mean "set but unconnectable" for an http sink either. A
        # credential-bearing URL used to report configured and fail every export.
        try:
            _http_sink_request_parts(sink_url, parsed)
        except SinkConfigurationError as exc:
            invalid_reason = str(exc)
    else:
        invalid_reason = "SDP_LOG_SINK_URL must use the file, http or https scheme"
    if scheme == "file":
        # A file sink published its absolute server path verbatim, and for the UNC
        # form _file_sink_path deliberately supports (file://host/share/...) that
        # path carries the sink's internal hostname - the same authority component
        # _redacted_sink_target exists to suppress. The manifest is
        # unauthenticated, so only the fact that a local sink is configured is
        # published.
        target = "local_file"
    else:
        target = _redacted_sink_target(parsed)

    status = {
        # ``configured`` means "a sink is set AND it can be written". A sink that
        # raises on every export is not a configured sink, and reporting it as
        # one is how an empty audit log went unnoticed.
        "configured": invalid_reason is None,
        "scheme": scheme,
        "target": target,
        "alert_webhook_configured": bool(alert_webhook_url),
        # ``alert_webhook_configured`` reports whether the variable is set, which
        # a reader took for "alerts reach this endpoint". Nothing posts to it, so
        # the capability is stated next to the configuration fact.
        "alert_webhook_routing": ALERT_ROUTING_STATUS,
    }
    if invalid_reason is not None:
        status["invalid_configuration"] = invalid_reason
    return status


def _export_to_sink(observation: dict[str, Any]) -> None:
    sink_url = os.getenv("SDP_LOG_SINK_URL", "").strip()
    if not sink_url:
        return

    parsed = urlparse(sink_url)
    # No scheme default: a bare value used to be treated as ``file`` and written
    # relative to the working directory.
    scheme = parsed.scheme
    payload = json.dumps(observation, ensure_ascii=False, sort_keys=True)

    if scheme == "file":
        path = _file_sink_path(sink_url, parsed)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(payload + "\n")
        return

    if scheme in {"http", "https"}:
        timeout_ms = int(os.getenv("SDP_LOG_SINK_TIMEOUT_MS", "500"))
        url, headers = _http_sink_request_parts(sink_url, parsed)
        request = UrlRequest(
            url,
            data=payload.encode("utf-8"),
            headers=headers,
            method="POST",
        )
        # nosemgrep: python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected -- scheme is allow-listed to {http,https} at the guard above (file:// et al. raise below)
        with urlopen(request, timeout=timeout_ms / 1000):
            return

    raise ValueError(f"unsupported SDP_LOG_SINK_URL scheme: {scheme}")


def record_observability_export_error(error: dict[str, Any] | str) -> None:
    if isinstance(error, str):
        payload = {"timestamp": datetime.now(timezone.utc).isoformat(), "message": error}
    else:
        payload = dict(error)
        payload.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
    _EXPORT_ERRORS.append(payload)


def record_request_observation(observation: dict[str, Any], *, export: bool = True) -> None:
    """Buffer one request observation and export it to the configured sink.

    This is the synchronous entry point. Callers already on an event loop must
    use :func:`record_request_observation_async` instead: ``_export_to_sink``
    does a blocking socket write or file append, which would otherwise run on
    the loop thread and serialize every concurrent request behind it.
    """
    _REQUEST_OBSERVATIONS.append(dict(observation))
    if not export:
        return
    _export_buffered_observation(observation)


# A telemetry sink that is down must not become an API throughput ceiling.
# Moving the export off the event loop removed the serialization, but every
# request still paid the full SDP_LOG_SINK_TIMEOUT_MS in a worker thread drawn
# from the same bounded anyio pool that serves every sync route: measured against
# a socket that accepts and never answers, 40 concurrent requests took 1.95s at a
# 500ms timeout, and one episode filled all 50 export-error slots.
SINK_FAILURE_THRESHOLD = 5
SINK_COOLDOWN_SECONDS = 30.0
# The breaker had two states, and the missing third one gave back the throughput
# ceiling it was added to remove. Once ``open_until`` elapsed, *every* request
# attempted the sink again, concurrently, each paying the full
# ``SDP_LOG_SINK_TIMEOUT_MS`` from the same bounded anyio threadpool that serves
# every sync route - so a sink that stays down turns each cooldown expiry into a
# fresh stampede. Measured on the real path (``record_request_observation_async``
# -> ``anyio.to_thread``) against a sink that accepts and never answers, 20
# concurrent requests arriving the instant the cooldown expired:
#
#     pool slots   sink attempts (before)   sink attempts (after)
#     8                                8                       1
#     unbounded                       20                       1
#
# Wall-clock for the burst is unchanged (~205ms, one timeout) because the
# attempts run in parallel; what the stampede costs is *threadpool slots* - it
# occupies every free slot of the pool that serves every sync route, for the full
# ``SDP_LOG_SINK_TIMEOUT_MS``, once per cooldown for as long as the outage lasts.
#
# Half-open fixes it: when the cooldown expires on a tripped breaker, exactly one
# caller probes the sink and everyone else keeps skipping until that probe
# answers. Recovery is still immediate - the probe's success closes the breaker
# for all subsequent callers - and it costs one request's timeout per cooldown
# instead of every concurrent request's.
#
# The lock is not optional: exports run in worker threads via
# ``to_thread.run_sync``, so the read-decide-write on these counters is genuinely
# concurrent, and "exactly one probe" cannot be expressed without it.
_SINK_BREAKER: dict[str, Any] = {
    "consecutive_failures": 0,
    "open_until": 0.0,
    "skipped_exports": 0,
    "probe_in_flight": False,
    "probes_started": 0,
}
_SINK_BREAKER_LOCK = threading.Lock()


def sink_breaker_state() -> dict[str, Any]:
    """Report the export breaker, so an outage is visible rather than silent."""
    with _SINK_BREAKER_LOCK:
        return {
            "open": _SINK_BREAKER["open_until"] > time.monotonic(),
            "half_open": _sink_breaker_is_half_open_locked(),
            "consecutive_failures": _SINK_BREAKER["consecutive_failures"],
            "skipped_exports": _SINK_BREAKER["skipped_exports"],
            # How many single-probe recovery attempts the cooldown has allowed.
            # A rising count with the breaker still tripped is a sink that is
            # still down, distinguishable from one that never recovered because
            # nothing retried.
            "probes_started": _SINK_BREAKER["probes_started"],
            "probe_in_flight": _SINK_BREAKER["probe_in_flight"],
            "failure_threshold": SINK_FAILURE_THRESHOLD,
            "cooldown_seconds": SINK_COOLDOWN_SECONDS,
        }


def reset_sink_breaker() -> None:
    """Clear the breaker (used by tests and by reset_request_observability)."""
    with _SINK_BREAKER_LOCK:
        _SINK_BREAKER["consecutive_failures"] = 0
        _SINK_BREAKER["open_until"] = 0.0
        _SINK_BREAKER["skipped_exports"] = 0
        _SINK_BREAKER["probe_in_flight"] = False
        _SINK_BREAKER["probes_started"] = 0


def _sink_breaker_is_half_open_locked() -> bool:
    """Whether a tripped breaker's cooldown has elapsed without a success yet.

    Caller holds ``_SINK_BREAKER_LOCK``.
    """
    return (
        _SINK_BREAKER["consecutive_failures"] >= SINK_FAILURE_THRESHOLD
        and _SINK_BREAKER["open_until"] <= time.monotonic()
    )


def _claim_sink_export() -> bool:
    """Whether this caller may attempt the sink now, counting what it skips.

    Three outcomes, all decided under one lock:

    * closed - the sink has not failed enough to trip; attempt it.
    * open - the cooldown has not elapsed; skip, and count the skip.
    * half-open - the cooldown elapsed on a tripped breaker; the first caller
      claims the single probe, every other caller skips.
    """
    with _SINK_BREAKER_LOCK:
        if _SINK_BREAKER["open_until"] > time.monotonic():
            _SINK_BREAKER["skipped_exports"] += 1
            return False
        if not _sink_breaker_is_half_open_locked():
            return True
        if _SINK_BREAKER["probe_in_flight"]:
            _SINK_BREAKER["skipped_exports"] += 1
            return False
        _SINK_BREAKER["probe_in_flight"] = True
        _SINK_BREAKER["probes_started"] += 1
        return True


def _record_sink_failure(message: str) -> None:
    """Count one export failure and open the breaker once the run is long enough."""
    with _SINK_BREAKER_LOCK:
        _SINK_BREAKER["consecutive_failures"] += 1
        if _SINK_BREAKER["consecutive_failures"] >= SINK_FAILURE_THRESHOLD:
            _SINK_BREAKER["open_until"] = time.monotonic() + SINK_COOLDOWN_SECONDS
        # A failed probe re-arms the cooldown above; releasing the claim here
        # lets the *next* expiry probe again rather than deadlocking recovery.
        _SINK_BREAKER["probe_in_flight"] = False
    record_observability_export_error(message)


def _record_sink_success() -> None:
    with _SINK_BREAKER_LOCK:
        _SINK_BREAKER["consecutive_failures"] = 0
        _SINK_BREAKER["open_until"] = 0.0
        _SINK_BREAKER["probe_in_flight"] = False


def _export_buffered_observation(observation: dict[str, Any]) -> None:
    """Export one already-buffered observation, recording a sink failure.

    While the breaker is open the sink is not attempted at all, so a dead sink
    costs nothing per request instead of a timeout and a threadpool slot. After
    the cooldown it costs exactly one probe, not one per concurrent request.
    """
    if not _claim_sink_export():
        return
    try:
        _export_to_sink(observation)
    except Exception as exc:
        _record_sink_failure(str(exc))
    else:
        _record_sink_success()


async def record_request_observation_async(
    observation: dict[str, Any], *, export: bool = True
) -> None:
    """Buffer one request observation, exporting it off the event loop.

    The ring buffer is appended synchronously so an observation is visible the
    moment the request finishes, with no ordering surprise for readers of
    ``/metrics``. Only the sink write - a blocking ``urlopen`` or file append -
    is moved to a worker thread. Running it inline on the loop blocked every
    other in-flight request for the duration of the sink round-trip: measured at
    8 concurrent requests against a 0.2s sink, the request path took 1.63s
    instead of ~0.2s.

    The response still waits for its own export, bounded by
    ``SDP_LOG_SINK_TIMEOUT_MS``; what this removes is the serialization of
    *other* requests behind it.
    """
    _REQUEST_OBSERVATIONS.append(dict(observation))
    if not export:
        return
    await to_thread.run_sync(_export_buffered_observation, observation)


def list_request_observations(limit: int = 100) -> list[dict[str, Any]]:
    return list(_REQUEST_OBSERVATIONS)[-limit:]


def observation_buffer_capacity() -> int:
    """How many observations the ring buffer retains.

    Published rather than assumed: every latency figure derived from this buffer
    is over a bounded recent window, and a reader cannot judge the figure
    without knowing the window. Read from the deque itself so the published
    number cannot drift from the structure.
    """
    return _REQUEST_OBSERVATIONS.maxlen or 0


def count_request_observations() -> int:
    """Return how many observations the ring buffer actually holds.

    The gauges used ``len()`` of a *page*, so ``sdp_request_observations_total``
    saturated at the page size (25) while the buffer held up to 500. A counter
    that cannot exceed its page is not a counter.
    """
    return len(_REQUEST_OBSERVATIONS)


def list_observability_export_errors(limit: int = 50) -> list[dict[str, Any]]:
    return list(_EXPORT_ERRORS)[-limit:]


def count_observability_export_errors() -> int:
    """Return how many export errors the ring buffer actually holds."""
    return len(_EXPORT_ERRORS)


def reset_request_observability() -> None:
    _REQUEST_OBSERVATIONS.clear()
    _EXPORT_ERRORS.clear()
    _GOVERNED_EVIDENCE_GAPS.clear()
    reset_sink_breaker()
    # The alert latch follows the counters the rules read. Clearing the gap
    # counter without clearing the latch would leave a rule whose
    # ``observed_total`` is zero still latched, which silences the next genuine
    # firing episode; this is also what makes a reset the only false->true->false
    # sequence available in a deployed worker.
    reset_alert_routing()


def _latency_budget_report() -> dict[str, Any]:
    """The latency-budget report, imported at call time to break an import cycle.

    ``latency_budgets`` classifies a concrete request path with the app's own
    compiled route patterns, so it imports ``sdp.api``, which imports this
    module. The local import is the same pattern ``connectors`` uses for its
    served-route check.
    """
    from .latency_budgets import latency_budget_report

    return latency_budget_report()


def build_observability_manifest() -> dict[str, Any]:
    datasets = list_datasets()
    audit_events = list_audit_events(limit=500)
    policy_decisions = list_policy_decisions(limit=500)
    audit_event_count, audit_count_is_lower_bound = count_audit_events()
    policy_decision_count, policy_count_is_lower_bound = count_policy_decisions()
    controls = enterprise_controls_manifest()
    request_observations = list_request_observations(limit=25)
    export_errors = list_observability_export_errors()

    return {
        "service": "semantic-data-portal",
        "health_endpoint": "/health",
        "metrics_endpoint": "/metrics",
        "structured_logs": {
            "status": "implemented",
            "request_id_header": request_id_header(),
            "sink": _sink_status(),
            "fields": [
                "request_id",
                "tenant_id",
                "actor",
                "route",
                "method",
                "status_code",
                "latency_ms",
                "evidence_ids",
            ],
            # Which of those fields the server owns. ``evidence_ids`` is the key
            # that ties a row to /policy/decisions and /audit/events, and it was
            # read from the caller-supplied X-SDP-Evidence-Ids header - so the
            # caller a row is about chose the row's correlation key, and the id
            # the server recorded never appeared. It now comes from the two
            # evidence chokepoints (see evidence.collect_request_evidence_ids).
            # ``tenant_id`` and ``actor`` are still caller-asserted, which is why
            # only aggregates of these rows are published here.
            "evidence_id_source": "server_recorded",
            "caller_asserted_fields": ["tenant_id", "actor", "request_id"],
            "body_logging": "disabled",
            "sink_breaker": sink_breaker_state(),
        },
        "metrics": {
            "catalog_datasets_total": len(datasets),
            # Real counts; these were ``len()`` of the 500-row page above and
            # reported 500 for 700 events on three published surfaces.
            "audit_events_observed_total": audit_event_count,
            "policy_decisions_observed_total": policy_decision_count,
            "audit_events_observed_total_is_lower_bound": audit_count_is_lower_bound,
            "policy_decisions_observed_total_is_lower_bound": policy_count_is_lower_bound,
            "enterprise_controls_implemented": controls.implemented_controls,
            "enterprise_controls_planned": controls.planned_controls,
            "enterprise_controls_external": controls.external_controls,
            # Real buffer occupancy, not the size of the page rendered below.
            "request_observations_total": count_request_observations(),
            "observability_export_errors_total": count_observability_export_errors(),
            # The ``policy_audit_gap`` condition as a number, so an operator's
            # own monitoring can alert on it without parsing the manifest.
            "governed_requests_without_evidence_total": governed_evidence_gap_report()[
                "observed_total"
            ],
            # The ``connector_probe_failure`` condition, same reasoning.
            "connector_probe_failures_total": connector_probe_failure_report()[
                "observed_total"
            ],
            "alerts_delivered_total": alert_routing_state()["deliveries_attempted"],
        },
        # No per-request feed on an unauthenticated manifest. Each observation
        # carries the caller's actor and tenant plus the route - which embeds the
        # dataset id - so publishing them made one tenant's governed-access
        # activity readable by anyone. Filtering by the observation's tenant_id
        # would not help: that value comes from the caller-supplied X-SDP-Tenant
        # header, so it is asserted by the very caller whose rows would be
        # filtered. Export errors are withheld for the same reason - a sink
        # exception string can quote the sink URL.
        "recent_request_count": count_request_observations(),
        "export_error_count": count_observability_export_errors(),
        "retention": {
            "local_evidence_store": "SDP_SQLITE_PATH",
            "production_target": "tenant-configurable append-only log sink plus queryable hot store",
        },
        # The PRD's six p95 budgets, compared to what this worker observed.
        "latency_budgets": _latency_budget_report(),
        # Two rules are measured in process, one is still a declared condition
        # an operator implements in their own stack. Read the per-rule flag; the
        # top-level key says so rather than making one claim for all three.
        "alert_evaluation": ALERT_EVALUATION_SCOPE,
        "alert_routing": ALERT_ROUTING_STATUS,
        # The delivery facts, not a delivery claim. Without these an operator
        # reading the manifest after an episode cannot tell a suppressed
        # increment from a webhook that refused the POST - the same rule the
        # sink's ``configured`` field already follows. No alert target is
        # published, redacted or otherwise: the hostname of the operator's
        # paging endpoint is not a fact about this service's governance, and
        # this surface answers anonymously.
        "alert_delivery": alert_routing_state(),
        "alerts": [
            {
                "id": "policy_audit_gap",
                "condition": (
                    "a policy-gated route answered 2xx while recording no policy "
                    "decision and no audit event"
                ),
                "declared_condition": (
                    "preview/query count exceeds policy decision or audit event count"
                ),
                "not_covered": (
                    "evidence rows removed out of band after the request (this counts at "
                    "request time, on the governed surface the refusal contract declares); "
                    "and a governed 2xx that recorded a policy decision but no audit event, "
                    "or an audit event but no policy decision - the count rises only when "
                    "BOTH are absent, and measured, 16 of the 18 probeable governed GET "
                    "routes record a decision and no audit event while this rule correctly "
                    "reports 0"
                ),
                "severity": "critical",
                "evaluated": True,
                "evaluation": "measured_in_process",
                **governed_evidence_gap_report(),
                **_alert_delivery_fields("policy_audit_gap"),
            },
            {
                "id": "connector_probe_failure",
                "condition": (
                    "a connector probe's verdict basis failed for a reason this "
                    "build owns: an adapter the connector registry declares that "
                    "this build does not implement, or a required control whose "
                    "declared proof endpoint this build does not serve"
                ),
                "declared_condition": "connector probe failure",
                # The gap between the declared name and the computed condition,
                # which is the whole reason this rule reports zero on a correct
                # deployment. Measured over the seed catalogue, 4 connectors x 5
                # datasets: 4 pairs ready_for_demo, 1 contract_only, 15 refused
                # for a scheme mismatch. The obvious condition - "count probes
                # that did not reach ready_for_demo" - fires on the shipped demo
                # image, because the one contract_only pair is waiting on an
                # optional secret reference and ``demo_smoke`` reports
                # ``ready: True`` with it in exactly that state.
                "not_covered": (
                    "the optional credential_vault configuration gap (rest_connector "
                    "/marketing-campaign probes contract_only because "
                    "SDP_CONNECTOR_SECRET_* is unset, which is a deployment choice and "
                    "not a build defect - the demo ready gate asserts that state and "
                    "passes); a caller naming a connector whose scheme does not back "
                    "the dataset, or an unsupported connector id, or an unknown dataset "
                    "id - the connector id arrives as a caller-supplied path segment, so "
                    "counting those would put the operator's pager behind a typo; and "
                    "the effect of the controls themselves - measured, 19 of 20 control "
                    "rows on seed data rest on proof_route_served, which is a fact about "
                    "this build's route table and not about what the control does, so a "
                    "zero here is not a claim that every control passed"
                ),
                "severity": "critical",
                "evaluated": True,
                "evaluation": "measured_in_process",
                **connector_probe_failure_report(),
                **_alert_delivery_fields("connector_probe_failure"),
            },
            {
                "id": "central_workflow_backlog",
                "condition": "required workflow queued or in_progress beyond stale threshold",
                "severity": "warning",
                "evaluated": False,
                "evaluation": ALERT_EVALUATION_STATUS,
                "not_evaluated_because": (
                    "the condition is about GitHub Actions run state, which this service "
                    "does not observe"
                ),
                # Published and not routable. Listing it as routable would
                # promise a delivery that can never be triggered, since nothing
                # here can evaluate the condition in the first place.
                **_alert_delivery_fields("central_workflow_backlog"),
            },
        ],
    }


def prometheus_metrics_text() -> str:
    manifest = build_observability_manifest()
    metrics = manifest["metrics"]
    lines = [
        "# HELP sdp_catalog_datasets_total Number of catalog datasets currently registered.",
        "# TYPE sdp_catalog_datasets_total gauge",
        f"sdp_catalog_datasets_total {metrics['catalog_datasets_total']}",
        "# HELP sdp_audit_events_observed_total Number of in-process audit events visible to the API.",
        "# TYPE sdp_audit_events_observed_total gauge",
        f"sdp_audit_events_observed_total {metrics['audit_events_observed_total']}",
        "# HELP sdp_policy_decisions_observed_total Number of policy decisions visible to the API.",
        "# TYPE sdp_policy_decisions_observed_total gauge",
        f"sdp_policy_decisions_observed_total {metrics['policy_decisions_observed_total']}",
        "# HELP sdp_enterprise_controls_implemented Number of implemented enterprise controls.",
        "# TYPE sdp_enterprise_controls_implemented gauge",
        f"sdp_enterprise_controls_implemented {metrics['enterprise_controls_implemented']}",
        "# HELP sdp_enterprise_controls_planned Number of planned enterprise controls.",
        "# TYPE sdp_enterprise_controls_planned gauge",
        f"sdp_enterprise_controls_planned {metrics['enterprise_controls_planned']}",
        "# HELP sdp_request_observations_total Request observations held in the local bounded ring buffer.",
        "# TYPE sdp_request_observations_total gauge",
        f"sdp_request_observations_total {metrics['request_observations_total']}",
        "# HELP sdp_observability_export_errors_total Number of request observation export errors.",
        "# TYPE sdp_observability_export_errors_total gauge",
        f"sdp_observability_export_errors_total {metrics['observability_export_errors_total']}",
        "# HELP sdp_governed_requests_without_evidence_total Policy-gated 2xx responses that recorded no policy decision and no audit event.",
        "# TYPE sdp_governed_requests_without_evidence_total gauge",
        f"sdp_governed_requests_without_evidence_total {metrics['governed_requests_without_evidence_total']}",
        "# HELP sdp_connector_probe_failures_total Connector probes whose verdict basis failed for a reason this build owns.",
        "# TYPE sdp_connector_probe_failures_total gauge",
        f"sdp_connector_probe_failures_total {metrics['connector_probe_failures_total']}",
        "# HELP sdp_alerts_delivered_total Alert deliveries attempted at the configured webhook, one per firing episode per rule.",
        "# TYPE sdp_alerts_delivered_total gauge",
        f"sdp_alerts_delivered_total {metrics['alerts_delivered_total']}",
        "",
    ]
    return "\n".join(lines)
