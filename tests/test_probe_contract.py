"""The operator contract must name the probe that can fail.

``GET /enterprise/observability`` is this service's machine-readable operator
contract, and its only health pointer was ``health_endpoint: "/health"``.
Measured at ``1831e75``::

    published health pointer(s): {'health_endpoint': '/health'}
    '/healthz' anywhere in the manifest: False

    GET /health   -> 200 {'status': 'ok', 'at': ...}        # consults nothing
    GET /healthz  -> 200 {'status': 'ready', 'store': {...}} # 503 when unready

``/health`` returns a hardcoded literal and consults nothing, so it cannot
fail. ``/healthz`` checks the active store and answers 503 when the backend is
unreachable, and it is what the ``Dockerfile`` HEALTHCHECK and both
``docker-compose`` healthchecks already use. So an SRE who wires monitoring, a
load balancer or a Kubernetes probe to the endpoint the platform itself
publishes gets a check that stays green while the portal's backend is down and
every request behind it is failing.

This is the sibling of a defect already closed one layer down:
``docs/product-technical-gap-baseline.md`` records the row "healthcheck |
Dockerfile + compose 2곳이 상수 /health를 조회 — 백엔드 죽은 컨테이너가 healthy".
The container healthchecks were repaired then; the **published contract** that
tells an integrator which endpoint to use was not, so the same wrong endpoint
was still being recommended by the service's own manifest.

Both pointers are published now, each labelled with what it reports, because
dropping ``health_endpoint`` would break a reader who has already wired it and
publishing one ambiguous pointer is what caused this.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sdp.api import app  # noqa: E402
from sdp import observability as obs  # noqa: E402


client = TestClient(app)

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_the_contract_publishes_the_readiness_probe_not_only_liveness() -> None:
    """The endpoint that can answer 503 has to be in the contract."""
    body = client.get("/enterprise/observability").json()

    assert body["health_endpoint"] == "/health", (
        "the liveness pointer is kept, because a reader has already wired it"
    )
    assert body.get("readiness_endpoint") == "/healthz", (
        "the operator contract names no endpoint that can report the backend "
        f"as unready: {sorted(k for k in body if 'health' in k or 'ready' in k)}"
    )


def test_each_published_probe_says_what_it_reports() -> None:
    """A pointer without its meaning is how the wrong one got wired.

    The note is asserted to name the 503 specifically, because "liveness" and
    "readiness" are terms a reader can map either way, and the actionable fact
    is which one changes under failure.
    """
    body = client.get("/enterprise/observability").json()
    note = body.get("probe_semantics")
    assert isinstance(note, dict), f"no probe semantics published: {body.keys()}"
    assert "/health" in note and "/healthz" in note, note
    assert "503" in note["/healthz"], (
        f"the readiness probe's note does not say it can fail: {note['/healthz']}"
    )
    assert "constant" in note["/health"] or "상수" in note["/health"], (
        f"the liveness probe's note does not say it is constant: {note['/health']}"
    )


def test_the_liveness_endpoint_really_is_constant_and_the_other_is_not() -> None:
    """The published claim is checked against the routes, not just asserted.

    ``/health`` must not consult anything (so the note is true) and ``/healthz``
    must report the store (so the recommendation is worth making). Checked by
    behaviour rather than by reading the source: the readiness body carries the
    store's own verdict, the liveness body does not.
    """
    liveness = client.get("/health").json()
    readiness = client.get("/healthz").json()

    assert set(liveness) == {"status", "at"}, (
        f"/health reports more than a constant now: {sorted(liveness)}"
    )
    assert "store" in readiness and "ready" in readiness["store"], (
        f"/healthz no longer reports store readiness: {sorted(readiness)}"
    )


def test_the_containers_and_the_contract_recommend_the_same_endpoint() -> None:
    """The Dockerfile and compose already probe the right one; now they agree.

    The drift this refuses is the one that happened: the containers were fixed
    and the published contract was not, so the two halves of the same advice
    disagreed for as long as nobody compared them.
    """
    body = client.get("/enterprise/observability").json()
    recommended = body["readiness_endpoint"]

    # The path is extracted and compared **exactly**. A substring test reads
    # ``/health`` as agreeing with a container that probes ``/healthz``, so
    # pointing the contract at the constant endpoint would have passed here -
    # measured, and it is why this is a parse rather than an ``in``.
    probed = []
    for name in ("Dockerfile", "docker-compose.yml"):
        text = (REPO_ROOT / name).read_text(encoding="utf-8")
        for line in text.splitlines():
            if "urlopen(" in line and "127.0.0.1" in line:
                match = re.search(r"http://127\.0\.0\.1:\d+(/[A-Za-z0-9_\-/]*)", line)
                assert match, f"{name}: cannot read the probed path from {line.strip()!r}"
                probed.append((name, match.group(1)))
    assert probed, "no container healthcheck was found; re-point this test"
    disagreeing = [(name, path) for name, path in probed if path != recommended]
    assert disagreeing == [], (
        f"the contract recommends {recommended} and these container "
        f"healthchecks probe something else: {disagreeing}"
    )


@pytest.mark.parametrize("key", ["health_endpoint", "readiness_endpoint"])
def test_every_published_probe_path_is_a_real_route(key: str) -> None:
    """A pointer to a path this app does not serve is worse than none."""
    body = client.get("/enterprise/observability").json()
    path = body[key]
    assert client.get(path).status_code in (200, 503), (
        f"{key} publishes {path}, which this build does not serve"
    )
    assert path in {
        route.path for route in app.routes if hasattr(route, "path")
    }, path


def test_the_manifest_builder_publishes_the_same_pair() -> None:
    """Called directly as well as over HTTP, since demo_smoke uses the function."""
    manifest = obs.build_observability_manifest()
    assert manifest["health_endpoint"] == "/health"
    assert manifest["readiness_endpoint"] == "/healthz"
