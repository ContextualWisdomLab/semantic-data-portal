"""Browse-path security tests: input validation, policy-deny propagation, and
PII masking.

``browse.preview``/``browse.schema`` are the policy-gated data-access surface;
these pin the deny/validation branches (bad pagination, missing dataset, policy
denial) and assert that PII columns obligated by policy are masked to ``***``.
Every call records an audit event and a policy decision, so the in-memory
catalog/audit/evidence stores are snapshot/restored for isolation.
"""

from __future__ import annotations

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sdp import browse, catalog, evidence  # noqa: E402
from sdp.policy import evaluate  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate_state():
    """Snapshot/restore module-level catalog data, audit log, and policy decisions."""
    data = {k: v.model_copy(deep=True) for k, v in catalog._DATA.items()}
    audit = list(catalog._AUDIT_LOG)
    decisions = list(evidence._POLICY_DECISION_LOG)
    audit_events = list(evidence._AUDIT_EVENT_LOG)
    try:
        yield
    finally:
        catalog._DATA.clear()
        catalog._DATA.update(data)
        catalog._AUDIT_LOG.clear()
        catalog._AUDIT_LOG.extend(audit)
        evidence._POLICY_DECISION_LOG.clear()
        evidence._POLICY_DECISION_LOG.extend(decisions)
        evidence._AUDIT_EVENT_LOG.clear()
        evidence._AUDIT_EVENT_LOG.extend(audit_events)


@pytest.mark.parametrize(
    "limit,offset",
    [(0, 0), (101, 0), (1, -1)],
)
def test_preview_rejects_out_of_range_pagination(limit: int, offset: int) -> None:
    """preview enforces 1<=limit<=100 and offset>=0 before any data access."""
    with pytest.raises(ValueError):
        browse.preview("crm-customer-master", user="admin", purpose="analysis", limit=limit, offset=offset)


def test_preview_denied_for_a_cross_tenant_subject_reads_as_not_found() -> None:
    """A cross-tenant subject is denied preview, and learns nothing about existence.

    A cross-tenant refusal is now indistinguishable from a missing dataset -
    ``KeyError``, mapped to 404 at the route - because 403-for-foreign plus
    404-for-missing is an existence oracle over an enumerable id space. The
    denial is still recorded: the assertions below check that the ledger keeps
    the real reason.
    """
    before_audit = len(catalog._AUDIT_LOG)
    before_decisions = len(evidence._POLICY_DECISION_LOG)
    with pytest.raises(KeyError):
        browse.preview("crm-customer-master", user="external-analyst", purpose="analysis")

    decisions = evidence._POLICY_DECISION_LOG[before_decisions:]
    assert [decision.effect for decision in decisions] == ["deny"]
    assert decisions[0].reason == "tenant boundary denied"
    audited = catalog._AUDIT_LOG[before_audit:]
    assert [event.reason for event in audited] == ["tenant boundary denied"]


def test_schema_missing_dataset_raises_keyerror() -> None:
    """schema on an unknown dataset raises KeyError (mapped to 404 at the route)."""
    with pytest.raises(KeyError):
        browse.schema("__no_such_dataset__", user="admin")


def test_schema_denied_for_a_cross_tenant_subject_reads_as_not_found() -> None:
    """schema denial (cross-tenant) is still audited, and still discloses nothing.

    A cross-tenant refusal is now indistinguishable from a missing dataset -
    ``KeyError``, mapped to 404 at the route - because 403-for-foreign plus
    404-for-missing is an existence oracle over an enumerable id space. The
    denial is still recorded: the assertions below check that the ledger keeps
    the real reason.
    """
    before = len(catalog._AUDIT_LOG)
    with pytest.raises(KeyError):
        browse.schema("crm-customer-master", user="external-analyst", purpose="analysis")
    audited = catalog._AUDIT_LOG[before:]
    assert len(audited) == 1  # the denial is audited
    assert audited[0].reason == "tenant boundary denied"
    assert audited[0].decision_id, "the audit row must point at a real decision"


def test_a_denial_inside_the_tenant_still_raises_permission_error() -> None:
    """Only the cross-tenant case collapses into "not found".

    A caller who may reach the dataset's tenant may legitimately know it exists,
    so a refusal for any other cause - here critical sensitivity - stays a
    ``PermissionError`` carrying its real reason.
    """
    base = catalog._DATA["crm-customer-master"]
    catalog._DATA["critical-in-tenant"] = base.model_copy(
        update={"id": "critical-in-tenant", "sensitivity": "critical"}
    )
    with pytest.raises(PermissionError) as refusal:
        browse.schema("critical-in-tenant", user="analyst", purpose="analysis")
    assert "critical" in str(refusal.value)


def test_preview_masks_pii_columns() -> None:
    """Any column policy obligates as masked is redacted to '***' in returned rows."""
    # Mark an email-bearing column PII so policy obligates masking for the preview rows.
    base = catalog._DATA["crm-customer-master"]
    schema = [c.model_copy(update={"pii": (c.name == "customer_email")}) for c in base.schema]
    assert any(c.name == "customer_email" for c in schema), (
        "fixture must include customer_email to exercise the preview masking integration"
    )
    catalog._DATA["crm-customer-master"] = base.model_copy(update={"schema": schema})
    result = browse.preview("crm-customer-master", user="admin", purpose="analysis", limit=2)
    assert "customer_email" in result["masking_summary"]["masked_columns"]
    assert all(row["customer_email"] == "***" for row in result["rows"])


def test_apply_mask_noop_without_masked_columns() -> None:
    """apply_mask returns the row unchanged when nothing is obligated masked."""
    row = {"a": "1", "b": "2"}
    assert browse.apply_mask(row, []) == {"a": "1", "b": "2"}


def test_preview_rows_never_leave_the_named_dataset_schema():
    """The sample rows were one fixed CRM row set served for every dataset, while
    the masking obligation came from the *named* dataset's ``pii`` flags. Naming a
    dataset with no PII column therefore returned ``customer_email`` in the clear:

        semantic-glossary -> masked=[]  rows[0]['customer_email'] == 'alice@example.com'

    A preview row may only carry columns the named dataset declares, so no
    dataset_id can be used to reach another dataset's PII column.
    """
    for dataset_id, dataset in sorted(catalog._DATA.items()):
        result = browse.preview(dataset_id, user="admin", purpose="analysis", limit=2)
        declared = {column.name for column in dataset.schema}
        assert declared, f"{dataset_id} has no declared schema"
        for row in result["rows"]:
            assert set(row) <= declared, f"{dataset_id} leaked {set(row) - declared}"
        # The advertised column list and the rows must describe the same thing.
        assert set(result["columns"]) == declared


def test_preview_masks_every_declared_pii_column():
    """Masking is a floor, not a best effort: a declared-PII column is never
    emitted in the clear by the preview sample path."""
    for dataset_id, dataset in sorted(catalog._DATA.items()):
        pii_columns = [column.name for column in dataset.schema if column.pii]
        result = browse.preview(dataset_id, user="admin", purpose="analysis", limit=2)
        for row in result["rows"]:
            for column in pii_columns:
                assert row[column] == "***", f"{dataset_id}.{column} was not masked"
        assert set(pii_columns) <= set(result["masking_summary"]["masked_columns"])


def test_preview_masks_declared_pii_even_if_the_obligation_omits_it(monkeypatch):
    """If a policy change ever stopped listing a PII column in the masking
    obligation, the preview must still not emit the value."""
    decision = evaluate(subject="admin", resource="crm-customer-master", action="preview", purpose="analysis")
    stripped = decision.model_copy(update={"obligations": {"masking": []}})
    monkeypatch.setattr(browse, "evaluate", lambda **_kwargs: stripped)

    result = browse.preview("crm-customer-master", user="admin", purpose="analysis", limit=1)
    assert result["rows"][0]["customer_email"] == "***"
    assert "customer_email" in result["masking_summary"]["masked_columns"]


def test_browse_audit_events_carry_the_owning_tenant():
    """``PostgresEvidenceStore`` reads an audit row's tenant from
    ``details['tenant_id']``, and nothing used to write that key — so every audit
    event, including a cross-tenant denial, was stored under the literal
    ``'demo'`` tenant. A tenant-scoped audit query would then miss its own rows
    and return another tenant's.
    """
    base = catalog._DATA["crm-customer-master"]
    catalog._DATA["external-customer-master"] = base.model_copy(
        update={"id": "external-customer-master", "tenant_id": "external"}
    )

    before = len(catalog._AUDIT_LOG)
    # KeyError, not PermissionError: a cross-tenant refusal is indistinguishable
    # from a missing dataset. The audit row this test is about is written either
    # way, which is the point.
    with pytest.raises(KeyError):
        browse.preview("external-customer-master", user="analyst", purpose="analysis")
    browse.preview("external-customer-master", user="external-analyst", purpose="analysis", limit=1)

    recorded = catalog._AUDIT_LOG[before:]
    assert len(recorded) == 2
    for event in recorded:
        assert event.details["tenant_id"] == "external", event.action


def test_dataset_profile_is_gated_like_the_schema_it_profiles():
    """``/catalog/datasets/{id}/profile`` republished exactly what the discovery
    repair withheld: dataset-level ``profile`` (a ``_GOVERNED_DATASET_FIELDS``
    member) as ``row_count``/``quality_issues``, and per-column ``quality_issues``
    (a ``_GOVERNED_COLUMN_FIELDS`` member) inside ``schema_profile`` — with no
    actor. Measured: ``row_count: 1200000`` to an anonymous caller while
    ``discovery_view`` withholds ``profile`` entirely.

    Unlike the discovery routes, the governed content *is* this route's purpose, so
    it belongs behind the gate rather than being stripped to nothing.
    """
    base = catalog._DATA["crm-customer-master"]
    catalog._DATA["external-profile-ds"] = base.model_copy(
        update={"id": "external-profile-ds", "tenant_id": "external"}
    )

    # KeyError: a cross-tenant refusal is indistinguishable from a missing
    # dataset, so the gate this test is about now refuses without disclosing
    # that the dataset exists. The gate itself is what is being checked.
    with pytest.raises(KeyError):
        browse.dataset_profile("external-profile-ds", user="analyst", purpose="analysis")

    allowed = browse.dataset_profile("external-profile-ds", user="external-analyst", purpose="analysis")
    assert allowed["row_count"] is not None
    assert allowed["policy_decision_id"]
    assert any(
        event.action == "browse.profile" and event.details.get("policy_decision_id")
        for event in catalog._AUDIT_LOG
    )


def test_dataset_profile_denial_is_audited():
    """A refused profile read leaves evidence, like every other gated read."""
    base = catalog._DATA["crm-customer-master"]
    catalog._DATA["external-profile-ds"] = base.model_copy(
        update={"id": "external-profile-ds", "tenant_id": "external"}
    )
    before = len(catalog._AUDIT_LOG)
    # The refusal reads as "not found" to the caller; the evidence this test is
    # about is written regardless, and keeps the true reason.
    with pytest.raises(KeyError):
        browse.dataset_profile("external-profile-ds", user="analyst", purpose="analysis")
    recorded = catalog._AUDIT_LOG[before:]
    assert len(recorded) == 1
    assert recorded[0].result == "denied"
    assert recorded[0].reason == "tenant boundary denied"
    assert recorded[0].details["tenant_id"] == "external"
