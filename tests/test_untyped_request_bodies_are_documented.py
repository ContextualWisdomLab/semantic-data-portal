"""An untyped body still has field names, and the document published none.

``sdp.api_request_contract`` repaired the fifteen routes whose bodies had a
contract model. Ten routes remain whose published body schema is
``{"type": "object", "additionalProperties": true}`` - and every one of them
reads named keys out of that dict. Measured at ``5af3adf``::

    POST /catalog/datasets/{id}/publish     actor, reason
    POST /catalog/datasets/{id}/deprecate   actor, reason
    POST /enterprise/auth/oidc-preview      actor, claims, role_map
    POST /ontology/patches                  actor, concept, suggestion
    POST /ontology/patches/{id}/review      actor, comment, decision, reviewer
    POST /browse/{id}/preview               limit, offset, purpose, user
    POST /enterprise/auth/oidc-verify       token
    POST /llm/search                        purpose, question, user
    POST /ontology/resolve                  text (+ the version pin)
    POST /policy/decision                   action, purpose, resource, subject, user

``additionalProperties: true`` makes a body built from the document *valid* and
leaves it unable to make the call - the "schema that cannot be used to make the
call it describes" that ``api_request_contract``'s own docstring names, arriving
through the untyped door rather than the typed one. Five of the ten read the
authorization subject this way, so the call is refused outright without it.

The naming is not uniform either, which is exactly what a document is for: the
subject arrives as ``?user=`` on every GET, as body ``actor`` on five of these
routes and as body ``user`` on three others.

That module's comment said its derived guard "fails if a handler reads a body
key this table does not publish, so the next one cannot be forgotten". The
guard is parametrized over ``REQUEST_BODY_MODELS`` only, so the ten untyped
routes were never in it - a published claim wider than its check. This file is
the missing half.

The AST scanner is imported from ``test_api_request_contract`` rather than
copied: it is the same question about the same module, and a second copy of a
scanner is a second thing to keep in step. This repository has recorded that
cost more than once.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sdp.api import app  # noqa: E402
from sdp.api_request_contract import (  # noqa: E402
    REQUEST_BODY_EXTRA_PROPERTIES,
    REQUEST_BODY_MODELS,
)
from test_api_request_contract import _body_keys_read, _handler_name  # noqa: E402

client = TestClient(app)


def _untyped_body_routes() -> list[tuple[str, str]]:
    """Routes whose published body schema is not a ``$ref``, from the document."""
    spec = client.get("/openapi.json").json()
    found = []
    for path, methods in spec["paths"].items():
        for method, operation in methods.items():
            body = operation.get("requestBody")
            if not body:
                continue
            schema = body["content"]["application/json"]["schema"]
            if "$ref" not in schema:
                found.append((method.upper(), path))
    assert len(found) >= 10, found
    return sorted(found)


UNTYPED = _untyped_body_routes()
IDS = [f"{method} {path}" for method, path in UNTYPED]


def _published_properties(method: str, path: str) -> dict:
    """The properties a client actually reads, from the live document.

    Asserting against ``REQUEST_BODY_EXTRA_PROPERTIES`` is asserting about the
    table. The first version of this file did exactly that, and a mutation that
    made the generator skip untyped routes entirely - publishing none of these
    keys to anyone - left every test green. The table is the source; the
    document is the deliverable, and the deliverable is what a client builds
    from. An ``anyOf`` body (``dict | None``) carries the keys on its object
    member, so both shapes are read here.
    """
    spec = client.get("/openapi.json").json()
    schema = spec["paths"][path][method.lower()]["requestBody"]["content"][
        "application/json"
    ]["schema"]
    members = schema["anyOf"] if "anyOf" in schema else [schema]
    properties: dict = {}
    for member in members:
        if member.get("type") == "object":
            properties.update(member.get("properties", {}))
    return properties


def test_the_untyped_routes_are_the_ones_without_a_model() -> None:
    """The scope, measured: none of these has a contract model to publish."""
    for key in UNTYPED:
        assert key not in REQUEST_BODY_MODELS, f"{key} has a model but publishes none"


@pytest.mark.parametrize("method,path", UNTYPED, ids=IDS)
def test_every_body_key_an_untyped_handler_reads_is_published(
    method: str, path: str
) -> None:
    """The guard the typed half already had, extended to the untyped half."""
    read, unresolved = _body_keys_read(_handler_name(method, path))
    assert not unresolved, (
        f"{method} {path} has body reads this scan cannot resolve, so its "
        f"published schema may be incomplete: {sorted(unresolved)}"
    )
    published = set(_published_properties(method, path))
    missing = read - published
    assert not missing, (
        f"{method} {path} reads {sorted(missing)} from the body and the "
        "document publishes nothing for them, so a client generated from it "
        "cannot make the call"
    )
    # The table is the source the document is built from, so a key reaching the
    # document from anywhere else would be a second source.
    assert published >= read & set(
        REQUEST_BODY_EXTRA_PROPERTIES.get((method, path), {})
    ), (method, path)


@pytest.mark.parametrize("method,path", UNTYPED, ids=IDS)
def test_the_published_schema_still_accepts_other_keys(
    method: str, path: str
) -> None:
    """These bodies stay open on purpose; documenting them is not closing them.

    A route with no contract model has nothing that validates the body, so
    publishing ``additionalProperties: false`` would describe a strictness the
    handler does not enforce - the same lie in the other direction.

    Openness here is not always the literal ``true``: a handler annotated
    ``dict[str, str]`` publishes ``additionalProperties: {"type": "string"}``,
    which is open with a value type. The property is that it is not closed, so
    both shapes pass and ``false`` or a missing key fails.
    """
    spec = client.get("/openapi.json").json()
    schema = spec["paths"][path][method.lower()]["requestBody"]["content"][
        "application/json"
    ]["schema"]
    members = schema["anyOf"] if "anyOf" in schema else [schema]
    objects = [m for m in members if m.get("type") == "object"]
    assert objects, schema
    for member in objects:
        extra = member.get("additionalProperties")
        assert extra is True or isinstance(extra, dict), member


@pytest.mark.parametrize("method,path", UNTYPED, ids=IDS)
def test_each_published_key_carries_a_description(method: str, path: str) -> None:
    """A name with no description is a name a reader has to guess the meaning of."""
    for key, prop in _published_properties(method, path).items():
        assert prop.get("description", "").strip(), f"{method} {path}: {key}"


def test_a_call_built_from_the_published_keys_passes_authorization() -> None:
    """The round trip, on the route whose refusal started this.

    Not "is something published" but "is the published document enough to be
    authorized". Sending only the documented keys must get past the subject
    check - here to a 404 for a patch id that does not exist, which is the
    answer for an authorized caller, rather than the 403 an undocumented body
    earns.
    """
    published = _published_properties("POST", "/ontology/patches/{patch_id}/review")
    assert "actor" in published, sorted(published)

    body = {"actor": "admin", "decision": "approve"}
    assert set(body) <= set(published), sorted(set(body) - set(published))
    response = client.post("/ontology/patches/no-such-patch/review", json=body)
    assert response.status_code == 404, response.text
    assert response.json()["detail"] == "patch not found", response.text


def test_the_version_pin_key_is_the_constant_the_code_reads() -> None:
    """The published name must be the module's constant, not a copy of it.

    ``/ontology/resolve`` reads its pin key as
    ``payload.get(ontology_version.PIN_PARAMETER)``. The table publishes a
    literal, and that literal's own description claims this test holds it to
    the constant - so it does. Renaming the constant without the table fails
    here rather than shipping a document naming a key nothing reads.
    """
    from sdp.ontology_version import PIN_PARAMETER

    published = _published_properties("POST", "/ontology/resolve")
    assert PIN_PARAMETER in published, sorted(published)


def test_the_subject_key_is_published_wherever_a_route_reads_one() -> None:
    """The naming is not uniform, so the document has to say which name.

    Five routes read ``actor`` and three read ``user``; a GET takes neither and
    uses ``?user=``. A client cannot derive that from the path.
    """
    subjects = {}
    for method, path in UNTYPED:
        read, _ = _body_keys_read(_handler_name(method, path))
        for name in ("actor", "user"):
            if name in read:
                subjects[(method, path)] = name
                published = _published_properties(method, path)
                assert name in published, f"{method} {path} reads {name!r} unpublished"
    assert len(subjects) >= 8, subjects
    assert set(subjects.values()) == {"actor", "user"}, subjects
