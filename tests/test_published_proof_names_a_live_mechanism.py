"""Two published-proof defects: a self-contradicting payload, and a guard that
cannot see most of what it claims to guard.

**1. One probe response says the adapter is implemented and calls itself
planned.** ``ConnectorCapability.proof`` is published on
``/enterprise/readiness`` and again inside every
``/enterprise/connectors/{connector_id}/probe`` response. Measured across all
four connectors, each against a dataset it backs::

    sql_connector        status=ready_for_demo  adapter_status=implemented
                         proof='/browse/query and /llm/draft-query'
    rdf_connector        status=ready_for_demo  adapter_status=implemented
                         proof='/ontology/search and /catalog/datasets/{dataset_id}/jsonld'
    rest_connector       status=contract_only   adapter_status=implemented
                         proof='planned connector contract in sdp_core.SourceConnector'
    file_lake_connector  status=ready_for_demo  adapter_status=implemented
                         proof='planned connector contract in sdp_core.SourceConnector'

``file_lake_connector``'s row is a single payload disagreeing with itself: it
reports the adapter implemented and the connector ready for demo, and its proof
field calls the thing a planned contract. ``connectors._SOURCE_CONNECTORS``
holds a real ``DemoFileLakeConnector`` and a real ``DemoRESTConnector``, and
``sdp.demo_smoke``'s release gate requires ``file_probe["status"] ==
"ready_for_demo"`` **and** ``rest_probe["adapter_status"] == "implemented"`` -
so the product's own release gate is satisfied by exactly the two connectors a
buyer-facing manifest calls planned. The other two rows name callable routes.

The repair names a callable route for all four, and the guard below is the part
that matters: it derives the claim from the adapter registry rather than from a
hand-written adjective, so the next adapter to land cannot leave its proof
saying "planned".

**2. The dangling-pointer guard sees 35 of 48 published pointers.**
``test_every_published_evidence_endpoint_is_a_real_route`` asserts
``len(endpoint_like) >= 34`` after filtering on ``ref.startswith("/")``. Two
independent gaps, measured::

    pointers the `/`-prefix filter sees                  35
    pointers spelled '<METHOD> /path' (invisible)        13   (8 control, 5 integration)
    control evidence entries read via proof_endpoints     0   of 46

``EnterpriseControl`` has no ``proof_endpoints`` field - its evidence list is
``evidence`` - so ``getattr(item, "proof_endpoints", None) or []`` contributes
nothing, and the controls' eight route pointers were never checked. Those eight
plus the production integrations' five are spelled ``"GET /policy/decisions"``,
which the ``/``-prefix filter drops even when the field name is right. None
dangle today, so this is a guard whose premise is narrower than the thing it
guards - the recurring class here, one layer up - and a ``>= 34`` floor that
understates its own coverage while reading as if it were the coverage.
"""

import re

from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from sdp import catalog, connectors
from sdp.api import app
from sdp_core import (
    enterprise_controls_manifest,
    enterprise_kpi_framework,
    enterprise_production_readiness_manifest,
    enterprise_readiness_manifest,
)
from sdp_core.readiness import connector_registry_manifest
from tests import manifest_pointers

client = TestClient(app)


def _probe_each_connector() -> dict[str, dict]:
    """One probe response per connector, against a dataset that connector backs."""
    probes: dict[str, dict] = {}
    for capability in connector_registry_manifest():
        for dataset in catalog.list_datasets(None):
            response = client.get(
                f"/enterprise/connectors/{capability.id}/probe",
                params={"user": "admin", "dataset_id": dataset.id},
            )
            if response.status_code == 200:
                probes[capability.id] = response.json()
                break
    return probes


def test_no_probe_response_calls_its_own_implemented_adapter_planned() -> None:
    """The self-contradiction, asserted on the payload that carries both fields."""
    probes = _probe_each_connector()
    assert len(probes) == len(connector_registry_manifest()), sorted(probes)

    contradictions = [
        (connector_id, body["adapter_status"], body["status"], body["proof"])
        for connector_id, body in probes.items()
        if body["adapter_status"] == "implemented" and "planned" in body["proof"]
    ]
    assert not contradictions, contradictions


def test_every_connector_proof_names_a_route_this_build_serves() -> None:
    """A proof a buyer cannot call is not proof.

    Derived from the served route table, so renaming a route breaks this rather
    than leaving the manifest pointing at nothing.
    """
    served = {route.path for route in app.routes if isinstance(route, APIRoute)}
    unreachable = []
    for capability in connector_registry_manifest():
        named = re.findall(r"/[A-Za-z0-9_{}/.-]+", capability.proof)
        assert named, (capability.id, capability.proof)
        for path in named:
            if path.rstrip(".,") not in served:
                unreachable.append((capability.id, path, capability.proof))
    assert not unreachable, unreachable


def test_the_proof_claim_is_derived_from_the_adapter_registry() -> None:
    """The guard that makes the repair durable.

    ``sdp_core`` cannot see ``sdp.connectors`` - the dependency runs the other
    way - so the manifest's ``proof`` is a hand-written string and nothing in
    ``sdp_core`` can check it against the adapters. This test can see both
    layers, so it is where the two are held together: a connector the app layer
    instantiates an adapter for must not be described as planned anywhere.
    """
    instantiated = set(connectors._SOURCE_CONNECTORS)
    assert instantiated, "the registry must be populated for this to measure anything"
    mislabelled = [
        (capability.id, capability.proof)
        for capability in connector_registry_manifest()
        if capability.id in instantiated and "planned" in capability.proof.lower()
    ]
    assert not mislabelled, mislabelled


def test_the_release_gate_and_the_manifest_agree_about_those_two() -> None:
    """``demo_smoke`` gates the release on the two connectors in question."""
    source = (
        __import__("pathlib").Path(__import__("sdp.demo_smoke", fromlist=["x"]).__file__)
        .read_text()
    )
    assert 'file_probe or {}).get("status") == "ready_for_demo"' in source
    assert 'rest_probe or {}).get("adapter_status") == "implemented"' in source

    probes = _probe_each_connector()
    assert probes["file_lake_connector"]["status"] == "ready_for_demo"
    assert probes["rest_connector"]["adapter_status"] == "implemented"
    # And neither is described as planned, which is the point of the pairing.
    for connector_id in ("file_lake_connector", "rest_connector"):
        assert "planned" not in probes[connector_id]["proof"], probes[connector_id]["proof"]


def test_every_published_route_reference_resolves() -> None:
    """Across every field of every manifest, not four field names out of eleven.

    The guard this replaces enumerated ``gates[].evidence``,
    ``kpis[].source_endpoints``, ``controls[].proof_endpoints`` (a field that
    does not exist) and ``integrations[].current_evidence``, and asserted a
    literal floor. Measured at this head, a structural walk finds **83** route
    references across **11** fields of **5** manifests, where the hand-listed
    form reached 48 across 4. The seven fields it could not see:
    ``demo_plan.proof_endpoints`` (11), ``demo_plan.proof`` (4),
    ``demo_plan.handoff_artifacts`` (3), ``readiness.proof`` (6),
    ``production.acceptance_criteria`` (6), ``kpis.measurement_surface`` (4) and
    ``kpis.measurement_gap`` (1).

    None of the 83 dangles, so what was broken was the guard's reach, not the
    data - and the point of widening it structurally is that the next field
    nobody remembers to add is covered by construction.
    """
    served = {route.path for route in app.routes if isinstance(route, APIRoute)}
    references = manifest_pointers.route_references(app)
    assert references, "the walk must find references for this to measure anything"
    dangling = sorted({(m, f, p) for m, f, p, _ in references if p not in served})
    assert not dangling, f"published evidence naming no such route: {dangling}"


def test_the_walk_reaches_every_manifest() -> None:
    """The equality that replaces the literal floor.

    A floor typed into the source goes stale upward in silence: adding one
    pointer to one manifest leaves ``>= 35`` green while the population is 36,
    which is the condition the old ``>= 34`` was diagnosed for, one notch
    higher. A floor *derived from the manifests it guards* is worse - it is
    ``x >= x`` and catches nothing, including the field-name bug this round
    repaired.

    So neither is used. What is asserted is that every manifest contributes to
    the checked set, which is derived from the manifest registry rather than
    from a count, and fails when a whole manifest drops out of the walk - the
    failure mode that let ``controls`` contribute 0 of 46 entries.
    """
    references = manifest_pointers.route_references(app)
    contributing = {manifest for manifest, _f, _p, _t in references}
    assert contributing == set(manifest_pointers.manifest_roots()), (
        sorted(set(manifest_pointers.manifest_roots()) - contributing),
        sorted(contributing),
    )


def test_a_method_prefixed_reference_names_a_method_the_app_serves() -> None:
    """``"GET /policy/decisions"`` must name a route served for that method.

    Case-sensitively: ``"get /policy/decisions"`` is not a spelling this product
    publishes, and accepting it case-insensitively would let a lowercase typo
    pass as a verified pointer.
    """
    pairs = {
        (method, route.path)
        for route in app.routes
        if isinstance(route, APIRoute)
        for method in route.methods
    }
    references = manifest_pointers.route_references(app)
    prefixed = [
        (manifest, field, text)
        for manifest, field, _p, text in references
        if manifest_pointers.METHOD_AND_PATH.match(text)
    ]
    assert prefixed, "the method-prefixed spelling must be present to be guarded"
    wrong = manifest_pointers.unserved_method_references(references, pairs)
    assert not wrong, f"method-prefixed evidence the app does not serve: {wrong}"

    # A lowercase method is not a recognised spelling, so it must not be
    # silently skipped: every string that starts with a word then a space then a
    # served path has to use an upper-case method.
    loose = re.compile(r"^([A-Za-z]+) (/[A-Za-z0-9_{][A-Za-z0-9_{}/.\-]*)$")
    served = {route.path for route in app.routes if isinstance(route, APIRoute)}
    mis_cased = []
    for _m, _f, _p, text in manifest_pointers.route_references(app):
        match = loose.match(text)
        if match and match.group(2) in served and not manifest_pointers.METHOD_AND_PATH.match(text):
            mis_cased.append(text)
    assert not mis_cased, f"route reference with an unrecognised method spelling: {mis_cased}"


def test_the_method_half_of_the_check_rejects_a_near_miss() -> None:
    """The method comparison, exercised against a crafted counterexample.

    A mutation that drops the method from the comparison - matching on the path
    alone, so ``"DELETE /healthz"`` would verify against a GET-only route -
    survives the tests above, because no pointer the manifests publish happens
    to name a wrong method. The check exists and nothing proves it works.

    So it is proven here the way ``a2f50c2`` proved the table allow-list: by
    asserting the predicate rejects a near miss rather than hoping the real data
    contains one. The pair is derived from the route table - a served path and a
    method that path is not served for - so it cannot go stale against it.
    """
    pairs = manifest_pointers.served_pairs(app)
    paths = manifest_pointers.served_paths(app)
    all_methods = {"GET", "POST", "PATCH", "PUT", "DELETE"}

    near_misses = [
        (method, path)
        for path in sorted(paths)
        for method in sorted(all_methods)
        if (method, path) not in pairs
    ]
    assert near_misses, "the app must serve at least one path with a restricted method set"
    method, path = near_misses[0]

    # The path alone verifies; the pair does not. A comparison that ignores the
    # method cannot tell these apart, which is exactly the mutation.
    assert path in paths
    assert (method, path) not in pairs

    # Fed to the guard's own predicate, not to a copy of it. A comparison that
    # ignores the method returns [] here and the assertion below fails.
    crafted = [("crafted", "near_miss", path, f"{method} {path}")]
    caught = manifest_pointers.unserved_method_references(crafted, pairs)
    assert caught == [("crafted", "near_miss", f"{method} {path}")], (caught, method, path)

    # And a reference the build does serve is not flagged, so the predicate is
    # discriminating rather than merely rejecting everything.
    served_method, served_path = sorted(pairs)[0]
    ok = manifest_pointers.unserved_method_references(
        [("crafted", "near_miss", served_path, f"{served_method} {served_path}")], pairs
    )
    assert ok == [], (ok, served_method, served_path)


def test_the_controls_evidence_is_read_by_its_real_field_name() -> None:
    """``EnterpriseControl`` has ``evidence``, not ``proof_endpoints``.

    The replaced guard read the controls through ``getattr(item,
    "proof_endpoints", None) or []``, which is always empty, so 0 of the
    controls' 46 evidence entries reached it. The walk reads whatever fields the
    model has, so the name cannot be wrong - and this test pins the fact that
    drove the original mistake.
    """
    controls = enterprise_controls_manifest().controls
    assert controls
    for control in controls:
        assert not hasattr(control, "proof_endpoints"), control.id
        assert control.evidence, control.id

    # The one model in these manifests that *does* have ``proof_endpoints`` -
    # the demo plan's workflow step - which is where the wrong name came from.
    from sdp_core.readiness import buyer_demo_activation_plan

    steps = buyer_demo_activation_plan().workflow
    assert steps
    assert all(hasattr(step, "proof_endpoints") for step in steps)

    walked = {
        (manifest, field)
        for manifest, field, _p, _t in manifest_pointers.route_references(app)
    }
    assert ("controls", "evidence") in walked, sorted(walked)
    assert ("demo_plan", "proof_endpoints") in walked, sorted(walked)


def test_a_capability_without_an_adapter_exercises_nothing() -> None:
    """The branch the derivation exists for, driven through the module's own seam.

    ``exercised_contract_methods`` was a constant written beside the branch that
    fills it: ``["inspect_schema"]`` published unconditionally while the call it
    names runs only ``if source_adapter``. Three verifiers measured that state as
    unreachable through the product - the registry is a module-level literal and
    ``connector_probe`` refuses any id outside it - which is exactly why it needs
    a test rather than an argument: round 18's surviving mutation was a branch
    the tests could not reach, and that is the branch that breaks in the
    deployment that reaches it.

    Driven the way ``configure_evidence_store`` drives the Postgres branch: by
    the module's own registry, restored on the way out.
    """
    probes = _probe_each_connector()
    assert probes["file_lake_connector"]["exercised_contract_methods"] == ["inspect_schema"]

    saved = dict(connectors._SOURCE_CONNECTORS)
    try:
        del connectors._SOURCE_CONNECTORS["file_lake_connector"]
        without = None
        for dataset in catalog.list_datasets(None):
            response = client.get(
                "/enterprise/connectors/file_lake_connector/probe",
                params={"user": "admin", "dataset_id": dataset.id},
            )
            if response.status_code == 200:
                without = response.json()
                break
        assert without is not None, "the probe must still answer for an adapterless capability"
        assert without["adapter_status"] == "planned"
        assert without["exercised_contract_methods"] == []
        assert without["unexercised_contract_methods"] == without["contract_methods"]
        assert without["status"] == "contract_only"
    finally:
        connectors._SOURCE_CONNECTORS.clear()
        connectors._SOURCE_CONNECTORS.update(saved)

    assert dict(connectors._SOURCE_CONNECTORS) == saved
    # And the restore is real: the probe reports the adapter again.
    assert _probe_each_connector()["file_lake_connector"]["adapter_status"] == "implemented"
