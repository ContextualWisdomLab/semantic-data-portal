"""A mutation refused for *who you are* must not report *what exists*.

Measured at ``0b19c91`` with one unauthenticated caller against one dataset
the seed catalogue owns (``crm-customer-master``)::

    GET   /catalog/datasets/{id}       -> 403 "...인증된 사용자만 가능합니다."
    PATCH /catalog/datasets/{id}       -> 404 "dataset not found"
    POST  /catalog/datasets/{id}/publish   -> 404 "dataset not found"
    POST  /catalog/datasets/{id}/deprecate -> 404 "dataset not found"

One caller, one resource, two different answers to the same question. The read
route says "authenticate"; the three mutations say the dataset does not exist.
It does exist, and the catalogue serves it to an authorized reader in the same
process - so the mutation refusal names a false cause, and a client follows it
to the dataset id instead of to its credentials. That cost four reproduction
attempts in this repository's own session log.

The 404 is deliberate and its reason is recorded in ``api.py``: a *foreign*
dataset must be indistinguishable from an absent one, and an earlier version
leaked that difference through the reason string while both answered 403. That
property is kept here. The reason the unauthenticated case does not need it is
**not** the one this docstring used to give. It said "a subject with no
resolvable tenant is refused by the role check, which never consults the
dataset, so the answer cannot vary with the dataset either way" - and that was
measured false while this file was being written, which is why
``_catalog_mutation_refusal`` evaluates ``resource="catalog"`` instead of the
dataset id::

    evaluate("anonymous", "crm-customer-master", "publish")
      -> deny "tenant boundary denied"
    evaluate("anonymous", "no-such-dataset",     "publish")
      -> deny "존재하지 않는 데이터셋입니다."

The engine *does* consult the dataset for a scope-less subject, and its reason
varies with whether the id exists. The route is oracle-free because it asks a
question that cannot depend on the dataset, not because the engine would have
been safe to ask. Crediting the engine with a property it does not have is how
the next reader concludes the dataset-scoped call is fine to reintroduce.

So: an unauthenticated mutation gets the authorization reason, an authenticated
caller who cannot reach the dataset's tenant keeps the 404, and the
indistinguishability of present and absent is asserted for both.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sdp.api import app  # noqa: E402
from sdp.catalog import get_dataset  # noqa: E402

client = TestClient(app)

PRESENT = "crm-customer-master"
ABSENT = "no-such-dataset-anywhere"

# (method, path template, body). The actor is read from the **body** on these
# routes, so "unauthenticated" means a body with no ``actor`` key.
MUTATIONS = [
    ("PATCH", "/catalog/datasets/{dataset_id}", {"description": "x"}),
    ("POST", "/catalog/datasets/{dataset_id}/publish", {}),
    ("POST", "/catalog/datasets/{dataset_id}/deprecate", {}),
]
IDS = [f"{method} {path.rsplit('/', 1)[-1]}" for method, path, _ in MUTATIONS]


def _call(method: str, path: str, body: dict, dataset_id: str, actor: str | None):
    """One mutation attempt, with or without an actor in the body."""
    payload = dict(body)
    if actor is not None:
        payload["actor"] = actor
    return client.request(method, path.format(dataset_id=dataset_id), json=payload)


def test_the_dataset_the_refusal_denies_actually_exists() -> None:
    """The premise, so a reseed that drops it fails here and not below."""
    assert get_dataset(PRESENT).id == PRESENT
    # ``get_dataset`` returns ``None`` for an unknown id rather than raising;
    # the ``KeyError`` arms in ``api.py`` come from the mutation helpers, not
    # from this lookup.
    assert get_dataset(ABSENT) is None


def test_the_read_route_answers_an_unauthenticated_caller_with_authorization() -> None:
    """The behaviour the mutations have to agree with, measured not assumed."""
    response = client.get(f"/catalog/datasets/{PRESENT}")
    assert response.status_code == 403, response.text
    assert "인증된 사용자만" in response.json()["detail"], response.text


@pytest.mark.parametrize("method,path,body", MUTATIONS, ids=IDS)
def test_an_unauthenticated_mutation_is_refused_for_authorization(
    method: str, path: str, body: dict
) -> None:
    """Not 404: the dataset is there, and the caller is the problem."""
    response = _call(method, path, body, PRESENT, None)
    assert response.status_code == 403, response.text
    detail = response.json()["detail"]
    assert detail != "dataset not found", detail
    # The property is "names authentication, not existence". Asserting the
    # engine's exact sentence here would pin the wording in a second place; what
    # this route owes the caller is that the reason is about *them*.
    assert "인증된 사용자만" in detail, detail
    assert "존재하지 않" not in detail, detail


@pytest.mark.parametrize("method,path,body", MUTATIONS, ids=IDS)
def test_present_and_absent_look_identical_to_an_unauthenticated_caller(
    method: str, path: str, body: dict
) -> None:
    """The property the 404 was protecting, kept on the new answer.

    Status *and* reason, because this repository already shipped a version
    where the status matched and the reason carried the difference.
    """
    present = _call(method, path, body, PRESENT, None)
    absent = _call(method, path, body, ABSENT, None)
    assert present.status_code == absent.status_code, (
        f"{present.status_code} vs {absent.status_code}"
    )
    assert present.json() == absent.json(), (present.text, absent.text)


@pytest.mark.parametrize("method,path,body", MUTATIONS, ids=IDS)
def test_a_cross_tenant_caller_still_cannot_tell_present_from_absent(
    method: str, path: str, body: dict
) -> None:
    """The case the 404 exists for, unchanged.

    ``external-analyst`` resolves to tenant ``external`` and holds only
    ``data-analyst``, so it is authenticated, cannot reach ``demo``, and is
    refused by role as well - exactly the caller the hiding is for.
    """
    present = _call(method, path, body, PRESENT, "external-analyst")
    absent = _call(method, path, body, ABSENT, "external-analyst")
    assert present.status_code == 404, present.text
    assert present.json() == absent.json(), (present.text, absent.text)
    assert present.json()["detail"] == "dataset not found", present.text
