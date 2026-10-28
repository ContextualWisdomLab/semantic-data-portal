"""POL-003 names three masking bases and asks the decision to carry the rule.

The requirement is "PII, sensitive, confidential tag 기반 masking을 지원해야
한다", with the acceptance criterion "policy decision 결과에 masking rule 포함".
The policy read one of the three bases and published no rule::

    obligations["masking"] = [col.name for col in dataset.schema if col.pii]

So a column classified sensitive or confidential was **released** - there was
nowhere on ``ColumnMetadata`` to classify it and nothing that would have masked
it - and a decision said which columns were masked without saying on what
grounds. An auditor could not tell a PII mask from a confidentiality mask, nor
notice that two of the three declared bases were never consulted.

Three properties these tests hold.

Every declared basis masks, and an **unrecognised** one masks too. Masking is a
withholding control, so the fail-closed direction is to mask what is not
understood: releasing a column because its label was misspelled is the failure
that matters. The rule reports ``unrecognized_classification`` so the decision
says why rather than silently widening.

``pii: true`` and ``classification: ["pii"]`` are the same statement. Either
masks, so the two cannot disagree about the outcome.

``classification`` is governed exactly like ``pii``: a column's sensitivity
label is as disclosing as its PII flag, so ``discovery_column_view`` withholds
it and the schema diff reports that it changed without publishing the value.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from sdp import catalog
from sdp.api import app
from sdp.policy import evaluate
from sdp_core.contracts import (
    MASKING_CLASSIFICATIONS,
    UNRECOGNIZED_CLASSIFICATION_BASIS,
    ColumnMetadata,
    column_masking_bases,
    masked_column_rules,
)

client = TestClient(app)

_DATASET = "crm-customer-master"


def _column(**overrides) -> ColumnMetadata:
    """A clean column unless overridden."""
    base = dict(
        name="probe_column", datatype="string", nullable_ratio=0.0, distinct_ratio=1.0
    )
    base.update(overrides)
    return ColumnMetadata(**base)


def _classify(column_index: int, classification: list[str]) -> None:
    """Set one seeded column's classification through the product route."""
    dataset = catalog.get_dataset(_DATASET)
    assert dataset is not None
    columns = [column.model_dump() for column in dataset.schema]
    columns[column_index]["classification"] = classification
    patched = client.patch(
        f"/catalog/datasets/{_DATASET}",
        json={"actor": "admin", "schema": columns, "reason": "classification 설정"},
    )
    assert patched.status_code == 200, patched.text


def test_the_published_vocabulary_is_the_requirements_three_bases() -> None:
    """The requirement names exactly these; the code must not quietly differ."""
    assert MASKING_CLASSIFICATIONS == ("pii", "sensitive", "confidential")


@pytest.mark.parametrize("basis", MASKING_CLASSIFICATIONS)
def test_every_declared_basis_masks(basis: str) -> None:
    """Two of the three used to mask nothing at all."""
    assert column_masking_bases(_column(classification=[basis])) == [basis]


def test_the_pii_flag_and_the_pii_classification_are_one_statement() -> None:
    """Either masks, and together they do not double-count."""
    assert column_masking_bases(_column(pii=True)) == ["pii"]
    assert column_masking_bases(_column(classification=["pii"])) == ["pii"]
    assert column_masking_bases(_column(pii=True, classification=["pii"])) == ["pii"]


def test_an_unrecognized_classification_masks_and_says_so() -> None:
    """Fail-closed: a misspelled label must not release a column."""
    bases = column_masking_bases(_column(classification=["confidentail"]))
    assert bases == [UNRECOGNIZED_CLASSIFICATION_BASIS]
    # Several unknown labels collapse to one basis rather than repeating it.
    many = column_masking_bases(_column(classification=["a", "b", "c"]))
    assert many == [UNRECOGNIZED_CLASSIFICATION_BASIS]
    # A known label alongside an unknown one keeps both facts.
    mixed = column_masking_bases(_column(classification=["sensitive", "nonsense"]))
    assert mixed == ["sensitive", UNRECOGNIZED_CLASSIFICATION_BASIS]


def test_a_clean_column_is_not_masked() -> None:
    """Otherwise the rules above would pass against a control that masks all."""
    assert column_masking_bases(_column()) == []
    assert column_masking_bases(_column(classification=[])) == []
    # Blank labels are not classifications.
    assert column_masking_bases(_column(classification=["", "   "])) == []
    assert masked_column_rules([_column(), _column(name="other")]) == []


def test_case_and_surrounding_space_do_not_defeat_a_classification() -> None:
    """A label is a label however it was typed."""
    for written in ("Confidential", "CONFIDENTIAL", "  confidential  "):
        assert column_masking_bases(_column(classification=[written])) == [
            "confidential"
        ], written


def test_a_rule_carries_the_column_the_bases_and_the_action() -> None:
    """The acceptance criterion is the *rule*, not a list of names."""
    rules = masked_column_rules(
        [
            _column(name="customer_email", pii=True),
            _column(name="plain_column"),
            _column(name="ledger_note", classification=["confidential"]),
        ]
    )
    assert rules == [
        {"column": "customer_email", "bases": ["pii"], "action": "mask"},
        {"column": "ledger_note", "bases": ["confidential"], "action": "mask"},
    ]


def test_the_decision_publishes_the_rules_and_they_agree_with_the_list() -> None:
    """Two fields describing one set must not be able to disagree."""
    _classify(2, ["confidential"])
    decision = evaluate(
        subject="analyst", resource=_DATASET, action="preview", purpose="analysis"
    )
    assert decision.effect == "allow"
    rules = decision.obligations["masking_rules"]
    assert [rule["column"] for rule in rules] == decision.obligations["masking"]
    bases_by_column = {rule["column"]: rule["bases"] for rule in rules}
    assert bases_by_column["customer_email"] == ["pii"]
    assert bases_by_column["signup_at"] == ["confidential"]


def test_a_classified_non_pii_column_is_actually_masked_in_a_preview() -> None:
    """The end a buyer sees: the value, not the obligation."""
    _classify(2, ["confidential"])
    preview = client.post(
        f"/browse/{_DATASET}/preview",
        json={"user": "analyst", "purpose": "analysis", "limit": 1},
    )
    assert preview.status_code == 200, preview.text
    body = preview.json()
    row = body["rows"][0]
    assert row["signup_at"] == "***", row
    assert row["customer_email"] == "***", row
    assert row["customer_id"] != "***", row
    rules = body["policy_decision"]["obligations"]["masking_rules"]
    assert {rule["column"] for rule in rules} == {"customer_email", "signup_at"}


def test_the_governed_schema_route_reports_the_classified_column_as_masked() -> None:
    """The other governed read, so the two cannot disagree."""
    _classify(2, ["sensitive"])
    response = client.get(
        f"/browse/{_DATASET}/schema", params={"user": "analyst", "purpose": "analysis"}
    )
    assert response.status_code == 200, response.text
    assert "signup_at" in response.json()["masked_columns"]


def test_the_masking_floor_widened_with_the_policy() -> None:
    """``preview`` masks what the dataset declares even if the policy stopped.

    The floor read only ``column.pii``, so a policy that stopped listing a
    confidential column would have released it - a floor narrower than the
    policy is not a floor.
    """
    import inspect

    from sdp import browse

    source = inspect.getsource(browse.preview)
    assert "masked_column_rules(dataset.schema)" in source, (
        "the preview floor does not consult the dataset's own masking rules"
    )
    assert "if column.pii" not in source, (
        "the preview floor still reads only the pii flag"
    )


def test_the_classification_is_governed_like_the_pii_flag() -> None:
    """A sensitivity label is as disclosing as a PII flag."""
    assert "classification" in catalog._GOVERNED_COLUMN_FIELDS
    _classify(2, ["confidential"])
    detail = client.get(
        f"/catalog/datasets/{_DATASET}", params={"user": "analyst"}
    ).json()
    assert "classification" not in json.dumps(detail, ensure_ascii=False, default=str)
    # And the stored snapshot keeps it, so drift detection still sees it.
    dataset = catalog.get_dataset(_DATASET)
    assert dataset is not None
    assert dataset.schema[2].classification == ["confidential"]


def test_a_reclassification_shows_as_drift_without_publishing_the_label() -> None:
    """The same split the PII flag already gets in the schema diff."""
    versions_before = client.get(
        f"/catalog/datasets/{_DATASET}/schema-versions", params={"user": "analyst"}
    ).json()["versions"]
    _classify(1, ["confidential"])
    versions_after = client.get(
        f"/catalog/datasets/{_DATASET}/schema-versions", params={"user": "analyst"}
    ).json()["versions"]
    assert len(versions_after) == len(versions_before) + 1, (
        versions_before,
        versions_after,
    )
    diff = client.get(
        f"/catalog/datasets/{_DATASET}/schema-diff",
        params={
            "user": "analyst",
            "from_version": versions_before[-1],
            "to_version": versions_after[-1],
        },
    )
    assert diff.status_code == 200, diff.text
    serialized = json.dumps(diff.json(), ensure_ascii=False)
    assert "confidential" not in serialized, (
        "the diff published the classification value it is supposed to withhold"
    )
    assert "classification" in serialized, (
        "the diff did not report that a governed field changed"
    )
