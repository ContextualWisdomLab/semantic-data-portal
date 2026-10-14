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
