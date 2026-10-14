"""SHACL-compatible dataset semantic validation.

validate_dataset_semantics reports metadata/mapping/term violations that gate a
dataset's readiness. These pin the violation branches (missing required
metadata, no approved business mapping, no searchable terms) and the
missing-dataset guard.
"""

from __future__ import annotations

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sdp import catalog, evidence  # noqa: E402
from sdp.semantic_validation import validate_dataset_semantics  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate_state():
    data = {k: v.model_copy(deep=True) for k, v in catalog._DATA.items()}
    audit = list(catalog._AUDIT_LOG)
    decisions = list(evidence._POLICY_DECISION_LOG)
    try:
        yield
    finally:
        catalog._DATA.clear()
        catalog._DATA.update(data)
        catalog._AUDIT_LOG.clear()
        catalog._AUDIT_LOG.extend(audit)
        evidence._POLICY_DECISION_LOG.clear()
        evidence._POLICY_DECISION_LOG.extend(decisions)


def test_missing_dataset_raises_keyerror() -> None:
    with pytest.raises(KeyError):
        validate_dataset_semantics("__no_such_dataset__")


def test_incomplete_dataset_reports_all_violation_classes() -> None:
    """A dataset with cleared metadata, no approved mapping, and no terms trips
    every violation branch and does not conform."""
    base = catalog._DATA["crm-customer-master"]
    catalog._DATA["incomplete-ds"] = base.model_copy(
        update={"id": "incomplete-ds", "owner": "", "steward": "", "mappings": [], "terms": []}
    )
    report = validate_dataset_semantics("incomplete-ds")
    assert report["conforms"] is False
    shapes = {v["shape"] for v in report["violations"]}
    assert "DatasetShape" in shapes  # missing required metadata (owner/steward)
    assert "BusinessMappingShape" in shapes  # no approved mapping + no terms
    assert report["approved_mapping_count"] == 0
    # The terms shortfall is recorded as a warning, not a hard violation.
    assert any(v["path"] == "terms" and v["severity"] == "warning" for v in report["violations"])


# --------------------------------------------------------------------------- #
# A published shape must be an evaluated shape.
#
# The catalog returned by ``/catalog/datasets/{id}/semantic-validation`` and
# ``/enterprise/shacl-validation`` declares ``required_properties`` per shape,
# and none of it was evaluated. ``conforms`` came from three hand-written rules
# whose only link to the catalog was that two of them borrowed a shape id.
# Measured at HEAD before the repair:
#
#   DistributionShape, a distribution with format="" and endpoint="":
#       conforms = True, violations = []
#   BusinessMappingShape, a mapping with concept="":
#       conforms = True, no violation names "concept"
#   DatasetShape.required_properties omitted description, sensitivity, title and
#       update_frequency, all four of which *were* enforced.
#
# So the catalog was wrong in both directions: it named properties nothing
# checked and omitted properties that were checked.
# --------------------------------------------------------------------------- #

import pytest

from sdp import catalog as catalog_module
from sdp import ontology
from sdp import semantic_validation as sv


def _probe(dataset_id: str, **overrides):
    """A copy of a conforming seeded dataset, with one shape deliberately broken."""
    base = catalog_module._DATA["crm-customer-master"]
    dataset = base.model_copy(deep=True).model_copy(update={"id": dataset_id, **overrides})
    catalog_module._DATA[dataset_id] = dataset
    return sv.validate_dataset_semantics(dataset_id)


def test_every_published_required_property_is_evaluated() -> None:
    """Enumerated over the catalog, so a shape cannot be published unevaluated.

    This is the check that would have caught the defect: breaking each declared
    property in turn and asserting the report names it. Spot-checking one shape
    is how two of the three stayed decorative.

    The probe sets fields through ``model_copy``, which bypasses validation, so
    it can hand the validator a ``None`` list the API cannot produce. That is
    deliberate - it is the cheapest way to enumerate - and the validator is total
    for it rather than raising.
    """
    node_shapes = {
        "BusinessMappingShape": ("mappings", lambda ds: ds.mappings),
        "DistributionShape": ("distributions", lambda ds: ds.distributions),
    }
    unevaluated: list[tuple[str, str]] = []

    for shape in sv._SHACL_COMPATIBLE_SHAPES:
        for prop in shape["required_properties"]:
            if shape["id"] == "DatasetShape":
                report = _probe(f"shape-probe-ds-{prop}", **{prop: None})
                paths = {item["path"] for item in report["violations"]}
                if prop not in paths:
                    unevaluated.append((shape["id"], prop))
                continue
            if shape["id"] == "ConceptShape":
                # A concept, not a dataset node: the same enumeration, against
                # the record shape ``ontology.concept_record`` builds and
                # ``register_concept`` stores. Breaking the property here is
                # what proves the publication gate reads it; see
                # ``tests/test_concept_shape_gate.py`` for the gate itself.
                record = ontology.concept_record(definition="d", aliases=["a"])
                record[prop] = ""
                report = ontology.concept_shape_report("개념형상검사", record)
                if prop not in {item["path"] for item in report["violations"]}:
                    unevaluated.append((shape["id"], prop))
                continue
            field, reader = node_shapes[shape["id"]]
            base = catalog_module._DATA["crm-customer-master"]
            nodes = [node.model_copy(deep=True) for node in reader(base)]
            nodes[0] = nodes[0].model_copy(update={prop: ""})
            report = _probe(f"shape-probe-{shape['id']}-{prop}", **{field: nodes})
            expected = f"{field}[0].{prop}"
            if expected not in {item["path"] for item in report["violations"]}:
                unevaluated.append((shape["id"], prop))

    assert not unevaluated, (
        "these properties are published as required and nothing evaluates them, "
        f"so a reader takes a constraint for granted that does not exist: {unevaluated}"
    )


def test_a_violation_of_a_published_shape_makes_the_dataset_non_conforming() -> None:
    """The property ``conforms`` is supposed to mean."""
    report = _probe(
        "shape-probe-conforms",
        distributions=[
            catalog_module._DATA["crm-customer-master"]
            .distributions[0]
            .model_copy(update={"format": "", "endpoint": ""})
        ],
    )
    assert report["conforms"] is False
    paths = {item["path"] for item in report["violations"]}
    assert {"distributions[0].format", "distributions[0].endpoint"} <= paths, paths


def test_a_violation_path_names_which_member_failed() -> None:
    """A bare property name cannot say *which* distribution was empty."""
    base = catalog_module._DATA["crm-customer-master"]
    good = base.distributions[0].model_copy(deep=True)
    bad = base.distributions[0].model_copy(update={"format": ""})
    report = _probe("shape-probe-index", distributions=[good, bad])
    paths = {item["path"] for item in report["violations"]}
    assert "distributions[1].format" in paths, paths
    assert "distributions[0].format" not in paths, paths


def test_the_dataset_shape_cannot_drift_from_the_list_it_enforces() -> None:
    """The published and enforced lists are one list, read twice.

    Before: the shape named six properties, the validator enforced ten, and the
    four it did not publish (description, sensitivity, title, update_frequency)
    were enforced anyway.
    """
    from sdp_core.contracts import REQUIRED_METADATA_FIELDS

    shape = sv._shape("DatasetShape")
    assert shape["required_properties"] == list(REQUIRED_METADATA_FIELDS)


def test_the_cardinality_rule_is_declared_as_one() -> None:
    """``BusinessMappingShape`` enforced "at least one approved", not property presence.

    A reader of ``required_properties: [concept, status]`` could not have known
    that. It is declared separately now, and both rules are evaluated.
    """
    shape = sv._shape("BusinessMappingShape")
    assert shape["min_approved_count"] == 1

    base = catalog_module._DATA["crm-customer-master"]
    unapproved = [
        mapping.model_copy(update={"status": "proposed"}) for mapping in base.mappings
    ]
    report = _probe("shape-probe-cardinality", mappings=unapproved)
    assert report["conforms"] is False
    cardinality = [
        item
        for item in report["violations"]
        if item["path"] == "mappings" and "approved" in item["message"]
    ]
    assert len(cardinality) == 1, report["violations"]
    # The per-property rule still holds for the same nodes.
    assert all(mapping.concept for mapping in unapproved)


def test_shacl_compatible_is_derived_rather_than_asserted() -> None:
    """It was a hardcoded ``True`` on both surfaces.

    Publishing a shape nothing evaluates must make the claim false, which is the
    only way the claim carries information.
    """
    assert sv._shacl_compatible() is True
    sv._SHACL_COMPATIBLE_SHAPES.append(
        {"id": "NotEvaluatedShape", "target": "X", "required_properties": ["y"]}
    )
    try:
        assert sv._shacl_compatible() is False
        assert sv.validate_dataset_semantics("crm-customer-master")["shacl_compatible"] is False
        assert sv.enterprise_shacl_validation_summary()["shacl_compatible"] is False
    finally:
        sv._SHACL_COMPATIBLE_SHAPES.pop()
    assert sv._shacl_compatible() is True


def test_no_shacl_engine_is_claimed_to_have_run() -> None:
    """``shacl_compatible: true`` alone reads as "a SHACL processor validated this".

    ``pyshacl`` is not a dependency of this repository, so the honest claim is
    that the shapes are SHACL-expressible and enforced by equivalent in-process
    checks. Both facts are published.
    """
    for report in (
        sv.validate_dataset_semantics("crm-customer-master"),
        sv.enterprise_shacl_validation_summary(),
    ):
        assert report["validation_engine"] == "builtin_shape_checks"
        assert report["shacl_engine_executed"] is False

    assert not any(
        "pyshacl" in str(sv.__dict__.get(name, "")) for name in ("VALIDATION_ENGINE",)
    )
    with pytest.raises(ImportError):
        import pyshacl  # noqa: F401


def test_evaluating_the_shapes_did_not_move_the_published_pass_rate() -> None:
    """The gate measures more and the seed still conforms.

    Stated because it is the thing that makes this a defect fix rather than a
    product decision: ``validation_pass_rate`` gates ``sdp.demo_smoke``'s
    ``ready`` flag at 0.95 and a saleability gate, and every seeded dataset was
    already clean against the published shapes (measured: 5/5, 1.0 before and
    after). If a future seed breaks a shape, this fails and whoever changed it
    decides deliberately.
    """
    summary = sv.enterprise_shacl_validation_summary()
    assert summary["validation_pass_rate"] == 1.0
    assert summary["conforming_datasets"] == summary["dataset_count"]
