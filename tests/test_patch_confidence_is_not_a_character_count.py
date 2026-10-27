"""The review queue's `confidence` was the length of the proposal text.

``src/sdp/ontology.py`` computed ``min(max(len(suggestion) / 220.0, 0.3), 0.95)``
and published it on ``POST /ontology/patches``, ``GET /ontology/patches`` and the
**unauthenticated** ``GET /enterprise/steward-review``. Measured at ``dba2403``
with three proposals, two of which say the same thing::

    len=  8  confidence=0.3                 "해지 고객 비율"            (precise)
    len=208  confidence=0.9409090909090909  the same meaning, padded
    len=300  confidence=0.95                "ㅁ" * 300                  (meaningless)

    GET /enterprise/steward-review (no actor) -> highest-confidence row is the
                                                 300 repeated characters

A steward triaging by confidence is sorted away from the precise proposal, and a
buyer reading the open readiness surface sees a queue whose quality signal is
typing volume. The caller cannot supply a confidence either - ``POST
/ontology/patches`` reads ``concept`` and ``suggestion`` and nothing else - so
the product has no basis for the number at all.

The repair is the one this repository already uses for a value it cannot measure:
publish that it is not measured. ``usage_source``/``measurement_status`` on the
spend surfaces, ``unimplemented_environment`` for ``SDP_EVIDENCE_RETENTION_DAYS``
and ``row_filter_summary.filter_enforced`` are the same shape. The field stays
present - ``tests/test_steward_queue_identity_scope.py`` holds it to be proposal
content a steward may read - and says ``null`` with its basis beside it.
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from sdp import ontology
from sdp.api import app


client = TestClient(app)

PRECISE = "해지 고객 비율"
PADDED = PRECISE + " 입니다. " * 40
MEANINGLESS = "ㅁ" * 300


def _propose(concept: str, suggestion: str) -> dict[str, Any]:
    """Queue one proposal through the route a curator uses."""
    response = client.post(
        "/ontology/patches",
        json={"actor": "analyst", "concept": concept, "suggestion": suggestion},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_padding_a_proposal_does_not_change_its_confidence() -> None:
    """The measurement, as a property: length must not be the signal."""
    precise = _propose("C1", PRECISE)
    padded = _propose("C2", PADDED)
    assert len(PADDED) > len(PRECISE) * 10, "the fixture must differ in length"
    assert precise["confidence"] == padded["confidence"], (
        "confidence moved with the character count of the proposal: "
        f"{precise['confidence']} vs {padded['confidence']}"
    )


def test_a_meaningless_proposal_does_not_outrank_a_precise_one() -> None:
    """Driven through the surface a buyer reads without any credential."""
    _propose("A1", PRECISE)
    _propose("A3", MEANINGLESS)
    review = client.get("/enterprise/steward-review")
    assert review.status_code == 200, review.text
    rows = [
        row for row in review.json()["review_items"] if row.get("type") == "ontology_patch"
    ]
    assert rows, review.json()
    scored = [row for row in rows if row.get("confidence") is not None]
    assert not scored, (
        "the open readiness surface publishes a confidence the product cannot "
        f"measure, so a queue can be ranked by typing volume: {scored}"
    )


def test_every_surface_publishing_the_field_publishes_its_basis() -> None:
    """One basis string, on every surface that carries the value."""
    created = _propose("B1", PRECISE)
    listed = client.get("/ontology/patches?user=admin")
    assert listed.status_code == 200, listed.text
    queue = client.get("/enterprise/steward-review")
    assert queue.status_code == 200, queue.text

    carriers: list[tuple[str, dict[str, Any]]] = [("POST /ontology/patches", created)]
    carriers += [
        ("GET /ontology/patches", row) for row in listed.json()["patches"]
    ]
    carriers += [
        ("GET /enterprise/steward-review", row)
        for row in queue.json()["review_items"]
        if row.get("type") == "ontology_patch"
    ]
    assert len(carriers) >= 3, carriers
    for label, row in carriers:
        assert "confidence" in row, (label, sorted(row))
        assert row["confidence"] is None, (label, row["confidence"])
        assert row.get("confidence_basis") == ontology.PATCH_CONFIDENCE_BASIS, (
            label,
            row.get("confidence_basis"),
        )


def test_the_library_seam_fabricates_nothing_either() -> None:
    """The route is not the only caller: ``propose_patch`` is the seam."""
    patch = ontology.propose_patch("D1", MEANINGLESS, requestor="analyst")
    assert patch["confidence"] is None, patch
    assert patch["confidence_basis"] == ontology.PATCH_CONFIDENCE_BASIS, patch
    # Comment lines and the docstring are stripped first: the function's own
    # comment quotes the removed expression as the measurement, and the first
    # version of this assertion failed on that comment. The repository's
    # ``test_purpose_is_normalized_once_at_the_entry_point`` strips comments for
    # the same reason. The length check that bounds the field is kept and is not
    # a score, so it is excluded by name rather than by hope.
    import inspect

    code = "\n".join(
        line
        for line in inspect.getsource(ontology.propose_patch).splitlines()
        if not line.lstrip().startswith("#")
    )
    body = code.split('"""', 2)[-1].replace("len(suggestion) > MAX_ONTOLOGY_PATCH_FIELD", "")
    assert "len(suggestion)" not in body, body
    assert "confidence=None" in body, body


def test_a_supplied_confidence_is_still_representable() -> None:
    """The field is nullable, not removed: a measured value can still be set.

    ``tests/test_concept_shape_gate.py`` constructs a patch with
    ``confidence=0.5`` directly, and a future caller-declared or model-derived
    score has somewhere to go.
    """
    from sdp_core.contracts import OntologyPatch

    patch = OntologyPatch(id="x", concept="c", suggestion="s", confidence=0.5)
    assert patch.confidence == 0.5
    default = OntologyPatch(id="y", concept="c", suggestion="s")
    assert default.confidence is None
    # The model's own default has to agree with the one basis constant, and a row
    # with no value must not claim a measured one. Mutating the default to
    # "measured" was not caught before this: ``propose_patch`` passes the basis
    # explicitly, so the default never showed up on the measured surfaces while
    # still governing every directly constructed patch.
    assert default.confidence_basis == ontology.PATCH_CONFIDENCE_BASIS, default.confidence_basis
    assert "not" in default.confidence_basis, default.confidence_basis
    assert patch.confidence_basis == ontology.PATCH_CONFIDENCE_BASIS
