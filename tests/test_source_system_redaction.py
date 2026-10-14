"""A DSN's secret must not survive redaction, in any connection-string form.

``redacted_source_system`` assumed ``source_system`` is always a URL with an
authority and returned the input unchanged when ``urlsplit`` found no host.
Measured across ten real forms, **six leaked the secret verbatim**::

    postgresql://u:PW123@h:5432/db                    -> postgresql://h:5432/db   ok
    host=h port=5432 user=u password=PW123 dbname=db  -> unchanged                LEAK
    jdbc:postgresql://u:PW123@h:5432/db               -> unchanged                LEAK
    Driver={PostgreSQL};Server=h;Uid=u;Pwd=PW123;     -> unchanged                LEAK
    postgresql://h:5432/db password=PW123             -> unchanged                LEAK
    Server=h;Database=db;User Id=u;Password=PW123;    -> unchanged                LEAK
    PW123                                             -> unchanged                LEAK

``audited_patch_values`` is the only redaction applied to a patched
``source_system``, so a cleartext password was written three times into the
audit event (``changes``, ``before``, ``after``) and returned by
``GET /catalog/datasets/{id}/audit?user=analyst`` — to the ``data-analyst`` and
``security`` roles, for which every read route withholds ``source_system``
entirely. The denial was decorative.

Why the suite did not catch it: the existing contract test patches
``postgresql://user:pass@host/db``, the one form the helper handled. So the
check is now by **form**, enumerated, and the invariant is stated as "the secret
does not appear in the output" rather than "the output equals this string" —
an equality assertion over one form is what let five others through.

The repair is an **allow-list** of locator keys, not a deny-list of
password-ish names. A deny-list leaks the moment a driver uses a key nobody
listed, which is the same mistake one level down.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from sdp import catalog
from sdp.api import app


client = TestClient(app, raise_server_exceptions=False)
SECRET = "PGPASS42"

# (label, connection string carrying SECRET)
DSN_FORMS = [
    ("url userinfo", f"postgresql://svc:{SECRET}@analytics.dw:5432/crm"),
    ("libpq keyword/value", f"host=analytics.dw port=5432 user=svc password={SECRET} dbname=crm"),
    ("jdbc wrapper", f"jdbc:postgresql://svc:{SECRET}@analytics.dw:5432/crm"),
    ("odbc braces", f"Driver={{PostgreSQL}};Server=analytics.dw;Uid=svc;Pwd={SECRET};"),
    ("path-embedded", f"postgresql://analytics.dw:5432/crm password={SECRET}"),
    ("sqlserver style", f"Server=analytics.dw;Database=crm;User Id=svc;Password={SECRET};"),
    ("url query", f"mysql://svc@analytics.dw/crm?password={SECRET}"),
    ("bare value", SECRET),
    ("snowflake", f"snowflake://svc:{SECRET}@account/crm"),
    ("mongodb srv", f"mongodb+srv://svc:{SECRET}@cluster/crm"),
    ("token key", f"https://api.example.internal/crm?apikey={SECRET}"),
]


@pytest.mark.parametrize("label,dsn", DSN_FORMS, ids=[row[0] for row in DSN_FORMS])
def test_no_connection_string_form_survives_with_its_secret(label: str, dsn: str) -> None:
    """The invariant, not an equality: the secret must not appear in the output."""
    redacted = catalog.redacted_source_system(dsn)
    assert SECRET not in redacted, f"{label}: {redacted}"


def test_a_locator_still_survives_for_the_seeded_forms() -> None:
    """Failing closed must not make the connector evidence useless."""
    for dataset in catalog.list_datasets(None):
        redacted = catalog.redacted_source_system(dataset.source_system)
        assert redacted != "redacted", dataset.source_system
        # the host is what the connector evidence is for
        assert redacted.split("//")[-1].split("/")[0], redacted


def test_an_unrecognized_string_is_dropped_rather_than_echoed() -> None:
    """A value with no structure could itself be the secret."""
    assert catalog.redacted_source_system("hunter2") == "redacted"
    assert catalog.redacted_source_system("") == "redacted"


def test_a_patched_dsn_does_not_reach_the_audit_feed() -> None:
    """The path the leak actually took, end to end.

    Three places in one audit event carried it: ``details.changes``,
    ``details.before`` and ``details.after``.
    """
    base = catalog._DATA["crm-customer-master"]
    catalog._DATA["redaction-ds"] = base.model_copy(update={"id": "redaction-ds"})

    patched = client.patch(
        "/catalog/datasets/redaction-ds",
        json={
            "actor": "admin",
            "source_system": (
                f"host=analytics.dw port=5432 user=svc password={SECRET} dbname=crm"
            ),
        },
    )
    assert patched.status_code == 200, patched.text

    for reader in ("analyst", "security", "admin"):
        audit = client.get(
            "/catalog/datasets/redaction-ds/audit", params={"user": reader}
        )
        assert audit.status_code == 200, audit.text
        assert SECRET not in audit.text, f"{reader} can read the secret: {audit.text[:300]}"

    events = client.get("/audit/events", params={"user": "admin", "limit": 50})
    assert events.status_code == 200
    assert SECRET not in events.text


def test_the_connector_probe_does_not_republish_a_secret() -> None:
    """The other caller of the same helper."""
    base = catalog._DATA["crm-customer-master"]
    catalog._DATA["probe-redaction-ds"] = base.model_copy(
        update={
            "id": "probe-redaction-ds",
            "source_system": f"postgresql://analytics.dw:5432/crm password={SECRET}",
        }
    )
    probe = client.get(
        "/enterprise/connectors/sql_connector/probe",
        params={"dataset_id": "probe-redaction-ds", "user": "admin"},
    )
    assert probe.status_code == 200, probe.text
    assert SECRET not in probe.text, probe.text[:300]


# --------------------------------------------------------------------------- #
# The other places a source-system-derived value escapes.
#
# Enumerated rather than fixed one at a time: ``connector_probe`` redacted while
# the adapter methods it advertises as the product's contract
# (``contract_methods: ["inspect_schema", "preview"]``) did not, and the four
# catalog mutations handed the whole DSN back in their response. Eight values
# across the adapters were derived from the raw DSN.
# --------------------------------------------------------------------------- #

CONNECTOR_PLANTS = [
    ("sql_connector", "postgresql://svc:{secret}@analytics.dw:5432/crm"),
    ("rdf_connector", "sparql://graphuser:{secret}@semantic.graph/ci"),
    ("file_lake_connector", "s3://AKIAEXAMPLE:{secret}@analytics/events/crm"),
    ("rest_connector", "https://svc:{secret}@api.example.internal/crm"),
]


@pytest.mark.parametrize(
    "connector_id,dsn_template", CONNECTOR_PLANTS, ids=[row[0] for row in CONNECTOR_PLANTS]
)
@pytest.mark.parametrize("method", ["inspect_schema", "preview"])
def test_no_connector_adapter_method_returns_a_secret(
    connector_id: str, dsn_template: str, method: str
) -> None:
    """Both contract methods, all four adapters.

    ``preview`` recorded ``named_graph``/``manifest_path`` built from the raw
    ``source_system``, so the credential landed in the audit event's details -
    returned by ``GET /audit/events?user=analyst`` to roles the governed read
    routes deny ``source_system`` to. ``inspect_schema`` returned the raw DSN to
    any in-process caller.
    """
    from sdp import connectors

    dataset_id = f"adapter-{connector_id}"
    base = catalog._DATA["crm-customer-master"]
    catalog._DATA[dataset_id] = base.model_copy(
        update={"id": dataset_id, "source_system": dsn_template.format(secret=SECRET)}
    )

    connector = connectors._SOURCE_CONNECTORS[connector_id]
    call = getattr(connector, method)
    result = call(dataset_id) if method == "inspect_schema" else call(
        dataset_id, limit=2, offset=0
    )
    assert SECRET not in repr(result), repr(result)[:400]


MUTATIONS = [
    ("create", "POST", "/catalog/datasets"),
    ("publish", "POST", "/catalog/datasets/{dataset_id}/publish"),
    ("patch", "PATCH", "/catalog/datasets/{dataset_id}"),
    ("deprecate", "POST", "/catalog/datasets/{dataset_id}/deprecate"),
]


@pytest.mark.parametrize(
    "label,method,path", MUTATIONS, ids=[row[0] for row in MUTATIONS]
)
def test_no_mutation_response_republishes_the_dsn(label: str, method: str, path: str) -> None:
    """All four, because fixing one would have left three.

    Measured before the repair on a dataset registered with
    ``postgresql://dsnuser:PGPASS42@analytics.dw:5432/crm?sslcert=TOKENINQUERY``:
    publish, patch and deprecate each returned 200 with the secret *and* the
    query token in the body, while every read surface withheld the field. The
    deprecate request carries no ``source_system`` at all and still handed it
    back.
    """
    dataset_id = f"mutation-{label}-ds"
    base = catalog._DATA["crm-customer-master"]
    dsn = f"postgresql://dsnuser:{SECRET}@analytics.dw:5432/crm?sslcert=TOKENINQUERY"
    catalog._DATA[dataset_id] = base.model_copy(
        update={"id": dataset_id, "source_system": dsn, "status": "draft"}
    )

    if label == "create":
        # ``model_dump()`` leaves pydantic URL objects in place, which the test
        # client cannot serialise; ``model_dump_json`` round-trips to plain JSON.
        body = {
            **json.loads(catalog._DATA[dataset_id].model_dump_json()),
            "id": "mutation-create-new-ds",
            "actor": "admin",
        }
        response = client.post("/catalog/datasets", json=body)
    else:
        resolved = path.format(dataset_id=dataset_id)
        payload = {"actor": "admin"}
        if method == "PATCH":
            payload["owner"] = "new_owner"
        response = client.request(method, resolved, json=payload)

    assert response.status_code == 200, response.text
    assert SECRET not in response.text, response.text[:400]
    assert "TOKENINQUERY" not in response.text
    # The response still confirms the mutation, unlike discovery_view.
    assert response.json()["dataset"]["source_system"]
