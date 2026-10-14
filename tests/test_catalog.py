"""Catalog store branch tests: search filters, facets, schema history, and lifecycle.

``catalog`` is the in-memory dataset store behind search/facet/lineage/schema-history
and the register/patch/publish/deprecate mutations. These pin the filter ``continue``
branches, the facet field guards and value counting, the version-bump helpers, the
not-found (``KeyError``/``ValueError``) guards, and the publish idempotency no-op so a
refactor cannot silently drop them. Every mutation records audit and schema-snapshot
evidence, so the in-memory catalog/audit/history/decision stores are snapshot/restored.
"""

from __future__ import annotations

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sdp import catalog, evidence  # noqa: E402
from sdp.domain import DatasetCreateRequest, DatasetPatchRequest  # noqa: E402

_CRM = "crm-customer-master"


@pytest.fixture(autouse=True)
def _isolate_state():
    """Snapshot/restore module-level catalog data, audit log, schema history, and decisions."""
    data = {k: v.model_copy(deep=True) for k, v in catalog._DATA.items()}
    audit = list(catalog._AUDIT_LOG)
    history = {k: list(v) for k, v in catalog._SCHEMA_HISTORY.items()}
    decisions = list(evidence._POLICY_DECISION_LOG)
    audit_events = list(evidence._AUDIT_EVENT_LOG)
    try:
        yield
    finally:
        catalog._DATA.clear()
        catalog._DATA.update(data)
        catalog._AUDIT_LOG.clear()
        catalog._AUDIT_LOG.extend(audit)
        catalog._SCHEMA_HISTORY.clear()
        catalog._SCHEMA_HISTORY.update(history)
        evidence._POLICY_DECISION_LOG.clear()
        evidence._POLICY_DECISION_LOG.extend(decisions)
        evidence._AUDIT_EVENT_LOG.clear()
        evidence._AUDIT_EVENT_LOG.extend(audit_events)


# --- version-bump helper (line 154) --------------------------------------


def test_bump_version_normal_and_malformed() -> None:
    """A dotted triple increments the patch; a malformed version falls back to 1.0.1."""
    assert catalog._bump_version("1.2.3") == "1.2.4"
    assert catalog._bump_version("not-a-version") == "1.0.1"  # line 154 fallback


# --- _term_score empty-token skip (line 167) -----------------------------


def test_term_score_skips_empty_token() -> None:
    """An empty token contributes nothing to the score.

    The skip moved into ``_compiled_query_tokens`` when the regex compile was
    hoisted out of the per-dataset loop, so the contract is pinned at both the
    new seam and the scorer.
    """
    dataset = catalog._DATA[_CRM]
    assert catalog._compiled_query_tokens(["", "customer"]) and len(
        catalog._compiled_query_tokens(["", "customer"])
    ) == 1
    with_empty = catalog._term_score(dataset, catalog._compiled_query_tokens(["", "customer"]), "customer")
    without_empty = catalog._term_score(dataset, catalog._compiled_query_tokens(["customer"]), "customer")
    assert with_empty == without_empty


# --- get_join_candidates skip branches (lines 101, 106) ------------------


def test_join_candidates_skips_unpublished() -> None:
    """A candidate whose status is neither published nor registered is skipped (line 101)."""
    base = catalog._DATA[_CRM]
    # A draft clone that fully overlaps CRM would score high if not filtered on status.
    catalog._DATA["draft-clone"] = base.model_copy(update={"id": "draft-clone", "status": "draft"})
    candidates = catalog.get_join_candidates(_CRM)
    assert "draft-clone" not in {row["dataset_id"] for row in candidates}


def test_join_candidates_skips_zero_overlap() -> None:
    """A published candidate with no term/column overlap scores 0 and is skipped (line 106)."""
    base = catalog._DATA[_CRM]
    catalog._DATA["no-overlap"] = base.model_copy(
        update={
            "id": "no-overlap",
            "status": "published",
            "terms": ["완전무관용어"],
            "schema": [],
        }
    )
    candidates = catalog.get_join_candidates(_CRM)
    assert "no-overlap" not in {row["dataset_id"] for row in candidates}


# --- search_catalog filter continues (lines 224/226/228/230) -------------


@pytest.mark.parametrize(
    "kwargs",
    [
        {"owner": ["__nomatch__"]},  # line 224
        {"sensitivity": ["__nomatch__"]},  # line 226
        {"status": ["__nomatch__"]},  # line 228
        {"license": ["__nomatch__"]},  # line 230
    ],
)
def test_search_filter_excludes_all(kwargs: dict) -> None:
    """A filter value no dataset satisfies excludes every dataset (per-filter continue)."""
    assert catalog.search_catalog("customer", **kwargs) == []


def test_search_min_freshness_excludes_all() -> None:
    """A min_freshness above the valid 0..1 range excludes every dataset (line 234)."""
    assert catalog.search_catalog("customer", min_freshness=2.0) == []


def test_search_include_inactive_completeness_gate() -> None:
    """A low-metadata-completeness dataset is hidden unless include_inactive is set (line 236)."""
    base = catalog._DATA[_CRM]
    # Two blank required fields drop metadata_completeness to 5/7 (< 0.8).
    catalog._DATA["inactive-ds"] = base.model_copy(
        update={"id": "inactive-ds", "owner": "", "steward": "", "title": "customer inactive dataset"}
    )
    assert catalog._DATA["inactive-ds"].metadata_completeness < 0.8

    default_ids = {row.dataset.id for row in catalog.search_catalog("customer")}
    assert "inactive-ds" not in default_ids  # line 236 continue

    inactive_ids = {row.dataset.id for row in catalog.search_catalog("customer", include_inactive=True)}
    assert "inactive-ds" in inactive_ids


# --- list_facet_counts (lines 248, 251, 258-260, 264-265) ----------------


def test_facet_counts_unsupported_field() -> None:
    """An unsupported facet field raises ValueError (line 248)."""
    with pytest.raises(ValueError):
        catalog.list_facet_counts("not_a_field")


def test_facet_counts_with_query_scores_and_skips_zero() -> None:
    """A query builds tokens (line 251) and datasets scoring <= 0 are skipped (lines 258-260)."""
    base = catalog._DATA[_CRM]
    # A high-sensitivity dataset with no matching text and a unique domain scores 0.
    catalog._DATA["nomatch-ds"] = base.model_copy(
        update={
            "id": "nomatch-ds",
            "title": "zzz",
            "description": "zzz",
            "tags": [],
            "terms": [],
            "mappings": [],
            "sensitivity": "high",
            "domain": "unique-domain-xyz",
        }
    )
    counts = catalog.list_facet_counts("domain", query="customer")
    assert counts  # at least the matching CRM domain is counted
    assert "unique-domain-xyz" not in counts  # scored 0 -> skipped at line 260


def test_facet_counts_list_valued_field() -> None:
    """A list-valued facet attribute counts each element (lines 264-265)."""
    base = catalog._DATA[_CRM]
    catalog._DATA["listy-ds"] = base.model_copy(
        update={"id": "listy-ds", "domain": ["retail", "wholesale"]}
    )
    counts = catalog.list_facet_counts("domain")
    assert counts.get("retail", 0) >= 1
    assert counts.get("wholesale", 0) >= 1


# --- not-found guards (lines 278, 290, 309-310) --------------------------


def test_get_dataset_or_404_missing() -> None:
    """An unknown dataset id raises KeyError (line 278)."""
    with pytest.raises(KeyError):
        catalog.get_dataset_or_404("__missing__")


def test_schema_history_missing_raises() -> None:
    """A dataset present in the store but with no recorded history raises KeyError (line 290)."""
    base = catalog._DATA[_CRM]
    # Insert without recording a schema snapshot so history is empty.
    catalog._DATA["nohist-ds"] = base.model_copy(update={"id": "nohist-ds"})
    with pytest.raises(KeyError):
        catalog.get_dataset_schema_history("nohist-ds")


def test_schema_diff_version_not_found() -> None:
    """A schema diff for versions absent from history raises ValueError (lines 309-310)."""
    with pytest.raises(ValueError):
        catalog.get_dataset_schema_diff(_CRM, "9.9.9", "8.8.8")


# --- register_dataset (lines 381, 386) -----------------------------------


def _create_request(**over) -> DatasetCreateRequest:
    base = dict(
        title="New Dataset",
        description="A freshly registered dataset",
        owner="data-platform",
        steward="steward",
        domain="customer",
        source_system="postgresql://analytics.dw/newds",
        sensitivity="low",
        update_frequency="daily",
        quality_score=0.9,
        freshness_score=0.9,
    )
    base.update(over)
    return DatasetCreateRequest(**base)


def test_register_dataset_auto_id() -> None:
    """A create request without an id gets an auto-generated dataset-NNN id (line 381)."""
    dataset = catalog.register_dataset(_create_request())
    assert dataset.id.startswith("dataset-")
    assert dataset.id in catalog._DATA


def test_register_dataset_already_exists() -> None:
    """Registering an id that already exists raises ValueError (line 386)."""
    with pytest.raises(ValueError):
        catalog.register_dataset(_create_request(id=_CRM))


# --- patch_dataset (lines 434, 440) --------------------------------------


def test_patch_dataset_skips_none_collection() -> None:
    """A collection field explicitly set to None is skipped, leaving it unchanged (line 434)."""
    before_tags = list(catalog._DATA[_CRM].tags)
    updated = catalog.patch_dataset(_CRM, DatasetPatchRequest(tags=None, title="Renamed CRM"))
    assert updated.title == "Renamed CRM"
    assert updated.tags == before_tags  # None-valued collection patch was ignored


def test_patch_dataset_schema_bumps_schema_version() -> None:
    """Patching the schema through the public request model bumps schema_version."""
    before = catalog._DATA[_CRM].schema_version
    updated = catalog.patch_dataset(
        _CRM,
        DatasetPatchRequest(
            schema=[
                {
                    "name": "new_col",
                    "datatype": "text",
                    "nullable_ratio": 0.0,
                    "distinct_ratio": 1.0,
                }
            ]
        ),
    )
    assert updated.schema_version == catalog._bump_version(before)
    assert [column.name for column in updated.schema] == ["new_col"]


# --- publish_dataset idempotent no-op (lines 471-480) --------------------


def test_publish_dataset_idempotent_noop() -> None:
    """Publishing an already-published dataset records a no-op audit and returns it unchanged."""
    base = catalog._DATA[_CRM]
    assert base.status == "published"
    before_version = base.version
    before_audit = len(catalog._AUDIT_LOG)

    result = catalog.publish_dataset(_CRM)

    assert result.status == "published"
    assert result.version == before_version  # no-op does not bump the version
    assert len(catalog._AUDIT_LOG) == before_audit + 1  # a no-op publish is still audited


# --- audit + related passthroughs (lines 547, 585-586) -------------------


def test_get_dataset_audit_events_returns_list() -> None:
    """get_dataset_audit_events delegates to list_audit_events scoped to the dataset (line 547)."""
    events = catalog.get_dataset_audit_events(_CRM)
    assert isinstance(events, list)


def test_get_related_datasets_returns_unique_list() -> None:
    """get_related_datasets resolves the dataset and returns its de-duplicated relations (585-586)."""
    related = catalog.get_related_datasets(_CRM)
    assert isinstance(related, list)
    assert set(related) == set(catalog._DATA[_CRM].related_datasets)


def test_mutation_audit_events_carry_the_dataset_tenant():
    """A catalog mutation builds its audit event straight from the ``Dataset``,
    so the owning tenant is in hand; it must reach ``details['tenant_id']``,
    which is where the Postgres evidence store scopes the row from."""
    base = catalog._DATA["crm-customer-master"]
    catalog._DATA["external-customer-master"] = base.model_copy(
        update={"id": "external-customer-master", "tenant_id": "external", "status": "draft"}
    )

    before = len(catalog._AUDIT_LOG)
    catalog.publish_dataset("external-customer-master", actor="admin")
    recorded = catalog._AUDIT_LOG[before:]
    assert recorded
    for event in recorded:
        assert event.details["tenant_id"] == "external", event.action


# --- schema history / diff must honour the discovery boundary -------------


def _publish_snapshot(dataset_id: str, **overrides) -> None:
    """Seed a dataset and publish it so a schema-history snapshot exists."""
    base = catalog._DATA["crm-customer-master"]
    catalog._DATA[dataset_id] = base.model_copy(
        update={"id": dataset_id, "status": "draft", **overrides}
    )
    catalog.publish_dataset(dataset_id, actor="admin")


def test_schema_history_does_not_publish_per_column_pii_flags() -> None:
    """``catalog.discovery_view()`` withholds the column schema from the ungated
    catalog detail route, but the schema-history snapshot carried the same
    columns — ``pii`` flags included — out of the same unauthenticated surface.
    """
    _publish_snapshot("hist-probe")
    history = catalog.get_dataset_schema_history("hist-probe")
    for entry in history["history"]:
        for column in entry["schema"]:
            assert "pii" not in column, column
            assert "quality_issues" not in column, column
            # The shape a consumer actually needs is still there.
            assert {"name", "datatype"} <= set(column)


def test_schema_history_projection_leaves_the_stored_snapshot_intact() -> None:
    """Drift detection runs on the stored snapshot, so the public projection must
    copy rather than strip in place."""
    _publish_snapshot("hist-probe")
    catalog.get_dataset_schema_history("hist-probe")
    stored = catalog._SCHEMA_HISTORY["hist-probe"]
    assert any("pii" in column for entry in stored for column in entry["schema"])


def test_schema_diff_withholds_governed_column_fields_but_keeps_the_signal() -> None:
    """A ``pii`` reclassification is real schema drift. The diff must still report
    the column as changed — and say which withheld field changed — without
    publishing the classification itself."""
    _publish_snapshot("diff-probe")
    first = catalog.list_dataset_schema_versions("diff-probe")[0]

    # Flip one column's PII classification, then snapshot again.
    dataset = catalog._DATA["diff-probe"]
    flipped = [
        column.model_copy(update={"pii": not column.pii}) if column.name == "customer_email" else column
        for column in dataset.schema
    ]
    catalog._DATA["diff-probe"] = dataset.model_copy(
        update={"schema": flipped, "schema_version": "2.0.0"}
    )
    catalog._record_schema_snapshot(catalog._DATA["diff-probe"])

    diff = catalog.get_dataset_schema_diff("diff-probe", first, "2.0.0")
    changed = {entry["name"]: entry for entry in diff["changed_columns"]}
    assert "customer_email" in changed, diff
    entry = changed["customer_email"]
    assert "pii" not in entry["before"] and "pii" not in entry["after"]
    assert entry["changed_withheld_fields"] == ["pii"]


def test_patch_audit_details_do_not_republish_governed_values() -> None:
    """``patch_dataset`` stored the raw ``before``/``after`` of every patched
    field, so patching ``source_system`` put the DSN in the audit record and
    patching ``schema`` put the per-column ``pii`` flags there — three copies
    each, in ``changes``/``before``/``after``. The audit feed then republished
    exactly what ``discovery_view`` and ``discovery_column_view`` withhold.
    """
    import json

    from sdp.domain import DatasetPatchRequest

    before_count = len(catalog._AUDIT_LOG)
    catalog.patch_dataset(
        "crm-customer-master",
        DatasetPatchRequest(
            source_system="postgresql://svc_catalog:S3cr3t@analytics.dw:5432/customer",
            schema=[
                {
                    "name": "customer_email",
                    "datatype": "string",
                    "nullable_ratio": 0.0,
                    "distinct_ratio": 1.0,
                    "pii": True,
                    "quality_issues": ["null_spike"],
                }
            ],
        ),
        actor="admin",
    )
    recorded = catalog._AUDIT_LOG[before_count:]
    assert recorded
    body = json.dumps([event.model_dump(mode="json") for event in recorded], ensure_ascii=False)
    assert "S3cr3t" not in body
    assert "svc_catalog" not in body
    assert '"pii"' not in body
    assert "null_spike" not in body
    # The change is still auditable: the locator and the column names survive.
    assert "analytics.dw" in body
    assert "customer_email" in body


def test_patch_audit_still_names_which_withheld_field_changed() -> None:
    """Withholding the value must not erase the signal that it changed."""
    from sdp.domain import DatasetPatchRequest

    before_count = len(catalog._AUDIT_LOG)
    catalog.patch_dataset(
        "crm-customer-master",
        DatasetPatchRequest(source_system="postgresql://analytics.dw:5432/other"),
        actor="admin",
    )
    details = catalog._AUDIT_LOG[before_count].details
    assert "source_system" in details["changes"]
