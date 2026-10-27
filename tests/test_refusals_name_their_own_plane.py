"""One sentence about the catalog answered four planes' refusals.

``policy.evaluate``'s discovery branch keys on the **action**
(``search``/``search_catalog``/``discover``) while its reason named a
**resource plane**. Four planes route through it, so an unauthenticated caller
was told the same thing everywhere. Measured at ``8d104ea``::

    403 '카탈로그 접근은 인증된 사용자만 가능합니다.'  /catalog/search      (true)
    403 '카탈로그 접근은 인증된 사용자만 가능합니다.'  /policy/decisions    (not a catalog read)
    403 '카탈로그 접근은 인증된 사용자만 가능합니다.'  /audit/events        (not a catalog read)
    403 '카탈로그 접근은 인증된 사용자만 가능합니다.'  /ontology/change-log (not a catalog read)
    403 '카탈로그 접근은 인증된 사용자만 가능합니다.'  /ontology/patches    (not a catalog read)
    403 '카탈로그 접근은 인증된 사용자만 가능합니다.'  /graph/nodes/{id}    (not a catalog read)

This is the criterion the previous repair of this same string set for itself and
then met for only one plane: it narrowed ``목록 조회는 ...`` to ``카탈로그 접근은
...`` because the list-only wording "named the wrong action" for a mutation
caller, recording that the replacement is "worded for every caller this branch
refuses". It is not - it is worded for the callers that repair enumerated.

The reason this cannot simply be worded from ``resource``: the branch is also
reached with values that are **assets**, not planes. ``_authorize_graph_read``
passes a node id, and ``evaluate(..., resource="crm-customer-master",
action="search")`` returns this same decision. Echoing the resource would
reopen the existence oracle the dataset routes' 404 exists to close, which is
why the wording comes from a declared plane vocabulary with an asset-free
fallback, and why the oracle is re-asserted here rather than assumed.
"""

from __future__ import annotations

import ast
import io
from pathlib import Path

from fastapi.testclient import TestClient

from sdp import policy
from sdp.api import app


client = TestClient(app)

REPO_ROOT = Path(__file__).resolve().parents[1]
API_SOURCE = REPO_ROOT / "src" / "sdp" / "api.py"
DISCOVERY_ACTIONS = {"search", "search_catalog", "discover"}


def _refusal(url: str) -> str:
    response = client.get(url)
    assert response.status_code == 403, (url, response.status_code, response.text[:200])
    return str(response.json()["detail"])


def test_each_plane_is_refused_in_its_own_words() -> None:
    """None of the five non-catalog refusals may call itself a catalog read."""
    # ``GET /ontology/patches`` is classified by the product as an evidence
    # read, not an ontology one - it runs ``_authorize_evidence_read``, the same
    # gate as the two ledgers, because its rows are field-for-field access
    # records. Asserted as measured rather than as assumed: the first version of
    # this test expected 온톨로지 there and was wrong about the product.
    non_catalog = {
        "/policy/decisions": "증빙",
        "/audit/events": "증빙",
        "/ontology/change-log": "증빙",
        "/ontology/patches": "증빙",
        "/graph/nodes/dataset:crm-customer-master": "그래프",
    }
    for url, expected in non_catalog.items():
        detail = _refusal(url)
        assert "카탈로그" not in detail, (url, detail)
        assert expected in detail, (url, detail)
    # The ontology plane's own wording belongs to the *write* that names it.
    proposal = client.post(
        "/ontology/patches", json={"concept": "고객", "suggestion": "개정 제안"}
    )
    assert proposal.status_code == 403, proposal.text
    assert "온톨로지" in proposal.json()["detail"], proposal.json()


def test_the_catalog_planes_own_wording_is_unchanged() -> None:
    """The plane that *was* right keeps its sentence."""
    for url in ("/catalog/search?q=고객", "/catalog/datasets"):
        assert "카탈로그" in _refusal(url), url


def test_every_refusal_keeps_the_phrase_the_mutation_guard_reads() -> None:
    """``tests/test_api.py`` asserts ``인증된 사용자만`` on the mutation refusal.

    That refusal is this same decision (``_catalog_mutation_refusal`` answers a
    scope-less caller with it), so the phrase is a contract across every variant
    rather than a property of one string.
    """
    for resource in ("catalog", "evidence", "ontology/patches", "graph", "a-dataset-id"):
        decision = policy.evaluate(
            subject="anonymous", resource=resource, action="search", purpose="discovery"
        )
        assert decision.effect == "deny", (resource, decision)
        assert "인증된 사용자만" in decision.reason, (resource, decision.reason)


def test_the_existence_oracle_stays_closed() -> None:
    """The reason may name the caller's plane; never the asset it asked about."""
    marker = "refusal-plane-probe-marker"
    present = policy.evaluate(
        subject="anonymous", resource="crm-customer-master", action="search", purpose="discovery"
    )
    absent = policy.evaluate(
        subject="anonymous", resource=marker, action="search", purpose="discovery"
    )
    assert present.reason == absent.reason, (present.reason, absent.reason)
    assert marker not in absent.reason, absent.reason
    assert "crm-customer-master" not in present.reason, present.reason
    for forbidden in ("tenant", "존재하지 않"):
        assert forbidden not in absent.reason, (forbidden, absent.reason)


def test_every_plane_the_product_names_has_its_own_wording() -> None:
    """A new plane must not land silently in the asset-free fallback.

    Derived from ``api.py``: every **literal** resource the product hands this
    branch is a plane it has named, so it must have wording. A resource passed
    as a variable is an asset (``_authorize_graph_read`` forwards a node id) and
    legitimately uses the fallback - that asymmetry is the whole point.

    One hop is followed, because the first version of this derivation looked only
    at ``evaluate(resource="...")`` and therefore did not cover ``"graph"`` at
    all: the product passes that literal to ``_authorize_graph_read``, which
    forwards its parameter. Deleting the ``graph`` entry was caught by the
    per-plane test above and **not** by this one, while this docstring claimed it
    covered every literal - a guard whose premise was wider than its code,
    which is the defect this file exists to repair one layer up.
    """
    tree = ast.parse(io.open(API_SOURCE, encoding="utf-8").read())

    def discovery_resource_parameter(function: ast.FunctionDef) -> str | None:
        """The parameter name this function forwards into the discovery branch."""
        for node in ast.walk(function):
            if not isinstance(node, ast.Call):
                continue
            kwargs = {kw.arg: kw.value for kw in node.keywords if kw.arg}
            action, resource = kwargs.get("action"), kwargs.get("resource")
            if not isinstance(action, ast.Constant) or action.value not in DISCOVERY_ACTIONS:
                continue
            if isinstance(resource, ast.Name):
                return resource.id
        return None

    forwarders: dict[str, int] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            parameter = discovery_resource_parameter(node)
            if parameter is not None:
                names = [argument.arg for argument in node.args.args]
                if parameter in names:
                    forwarders[node.name] = names.index(parameter)

    literals: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        kwargs = {kw.arg: kw.value for kw in node.keywords if kw.arg}
        action, resource = kwargs.get("action"), kwargs.get("resource")
        if isinstance(action, ast.Constant) and action.value in DISCOVERY_ACTIONS:
            if isinstance(resource, ast.Constant) and isinstance(resource.value, str):
                literals.add(resource.value)
        callee = node.func.id if isinstance(node.func, ast.Name) else None
        if callee in forwarders:
            index = forwarders[callee]
            if index < len(node.args) and isinstance(node.args[index], ast.Constant):
                value = node.args[index].value
                if isinstance(value, str):
                    literals.add(value)

    assert literals, "the derivation found no discovery call at all"
    assert "graph" in literals, (
        "the one-hop derivation lost the plane it was written for: " f"{sorted(literals)}"
    )
    missing = sorted(name for name in literals if name not in policy.REFUSAL_PLANES)
    assert not missing, (
        f"these planes are named by the product but have no refusal wording: {missing}"
    )
