"""The write echo was replayable, and replaying it deleted the source locator.

``source_system`` is redacted on every published path, and for a string with no
recognizable connection-string structure the redactor fails closed and returns
the marker instead of echoing a value that might itself be a password. That is
the right call - ``PW123`` is in the measured table of leaking forms. What was
not foreseen is that the marker then travels back in through an ordinary
read-modify-write. Measured at ``642c876``::

    declared 'warehouse-postgres'                        -> echo 'redacted'
    declared 'snowflake'                                 -> echo 'redacted'
    declared 'postgresql://warehouse.dw:5432/mkt'        -> echo it, unchanged
    declared 'postgresql://u:PW123@warehouse.dw:5432/mkt'-> echo without the password

    stored source_system after the create                -> 'warehouse-postgres'
    PATCH with the echoed body {..., source_system: 'redacted'} -> 200
    stored source_system after that patch                -> 'redacted'
    audit details -> changes.source_system 'redacted'
                     before.source_system 'redacted'
                     after.source_system  'redacted'

So the least sensitive value - a plain system label with no credential in it - is
the one the product destroys most completely, and the governance ledger records
the destruction as **no change at all**, because both sides of the comparison are
projected through the same lossy function before being written.

Two separate repairs: a write may not store the redaction marker, and the ledger
must say whether the field changed even when its projection cannot show it.
"""

from __future__ import annotations

import pathlib
import re

from typing import Any

from fastapi.testclient import TestClient

from sdp import catalog
from sdp.api import app


client = TestClient(app)


def _create(dataset_id: str, source_system: str) -> dict[str, Any]:
    """Register one dataset and return the response body."""
    body: dict[str, Any] = {
        "id": dataset_id,
        "tenant_id": "demo",
        "title": "에코 프로브",
        "description": "쓰기 에코 재전송을 측정하는 프로브",
        "owner": "data-admin",
        "steward": "data-admin",
        "domain": "고객",
        "source_system": source_system,
        "sensitivity": "low",
        "update_frequency": "daily",
        "quality_score": 0.9,
        "freshness_score": 0.9,
        "schema": [
            {"name": "customer_id", "datatype": "string", "nullable_ratio": 0.0, "distinct_ratio": 1.0}
        ],
        "distributions": [
            {"id": f"{dataset_id}-csv", "format": "csv", "endpoint": "https://files.example.internal/x.csv"}
        ],
        "actor": "data-admin",
        "reason": "probe",
    }
    created = client.post("/catalog/datasets", json=body)
    assert created.status_code == 200, created.text
    return created.json()


def _audit_details(dataset_id: str) -> dict[str, Any]:
    audit = client.get(f"/catalog/datasets/{dataset_id}/audit?user=data-admin").json()
    events = audit if isinstance(audit, list) else audit.get("events", audit.get("items", []))
    assert events, audit
    return events[0].get("details") or {}


def test_the_marker_is_one_constant() -> None:
    """Structural: the refusal and the redactor must mean the same string."""
    assert catalog.SOURCE_SYSTEM_REDACTED
    # Parsed rather than grepped: the docstrings quote the marker as the
    # measurement, and dropping only the lines that carry a ``"""`` delimiter
    # left those quotations in - the fourth time this round that a structural
    # guard tripped on the prose documenting what it guards. An AST walk sees
    # string *expressions*, and a docstring is the first statement of its scope,
    # so it can be excluded exactly.
    import ast

    tree = ast.parse(pathlib.Path(catalog.__file__).read_text(encoding="utf-8"))
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
        and isinstance(node.body[0].value.value, str)
    }
    literals = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and node.value == catalog.SOURCE_SYSTEM_REDACTED
        and id(node) not in docstrings
    ]
    assert len(literals) == 1, (
        "the redaction marker should be written exactly once - the constant's own "
        f"assignment - and is written at lines {literals}"
    )
    assert re.search(r"^SOURCE_SYSTEM_REDACTED = ", pathlib.Path(catalog.__file__).read_text(encoding="utf-8"), re.M)


def test_the_redactor_still_fails_closed_on_an_unstructured_string() -> None:
    """The premise this repair must not weaken: a bare string may be a password."""
    assert catalog.redacted_source_system("PW123") == catalog.SOURCE_SYSTEM_REDACTED
    assert catalog.redacted_source_system("warehouse-postgres") == catalog.SOURCE_SYSTEM_REDACTED


def test_replaying_the_write_echo_does_not_delete_the_locator() -> None:
    """The ordinary read-modify-write loop, with the body the product returned."""
    echoed = _create("echo-replay-probe", "warehouse-postgres")
    dataset = echoed.get("dataset") or echoed
    assert dataset["source_system"] == catalog.SOURCE_SYSTEM_REDACTED, dataset["source_system"]
    stored_before = catalog.get_dataset("echo-replay-probe").source_system
    assert stored_before == "warehouse-postgres"

    replayed = client.patch(
        "/catalog/datasets/echo-replay-probe",
        json={
            "actor": "data-admin",
            "reason": "제목 수정",
            "title": "에코 프로브 v2",
            "source_system": dataset["source_system"],
        },
    )
    assert replayed.status_code == 400, replayed.text
    detail = replayed.json()["detail"]
    text = detail if isinstance(detail, str) else repr(detail)
    assert "source_system" in text, detail
    assert catalog.get_dataset("echo-replay-probe").source_system == stored_before


def test_the_marker_cannot_be_registered_either() -> None:
    """A create that stores the marker is the same loss, one step earlier."""
    body_response = client.post(
        "/catalog/datasets",
        json={
            "id": "echo-marker-create",
            "tenant_id": "demo",
            "title": "마커 프로브",
            "description": "마커로 등록을 시도",
            "owner": "data-admin",
            "steward": "data-admin",
            "domain": "고객",
            "source_system": catalog.SOURCE_SYSTEM_REDACTED,
            "sensitivity": "low",
            "update_frequency": "daily",
            "quality_score": 0.9,
            "freshness_score": 0.9,
            "schema": [
                {"name": "c", "datatype": "string", "nullable_ratio": 0.0, "distinct_ratio": 1.0}
            ],
            "distributions": [
                {"id": "d", "format": "csv", "endpoint": "https://files.example.internal/x.csv"}
            ],
            "actor": "data-admin",
            "reason": "probe",
        },
    )
    assert body_response.status_code == 400, body_response.text
    assert catalog.get_dataset("echo-marker-create") is None


def test_the_ledger_says_the_field_changed_even_when_the_projection_cannot() -> None:
    """Two plain labels project to the same marker; the change is still a change."""
    _create("echo-ledger-probe", "warehouse-postgres")
    patched = client.patch(
        "/catalog/datasets/echo-ledger-probe",
        json={
            "actor": "data-admin",
            "reason": "소스 교체",
            "source_system": "snowflake-east",
        },
    )
    assert patched.status_code == 200, patched.text
    assert catalog.get_dataset("echo-ledger-probe").source_system == "snowflake-east"

    details = _audit_details("echo-ledger-probe")
    before = (details.get("before") or {}).get("source_system")
    after = (details.get("after") or {}).get("source_system")
    assert before == after == catalog.SOURCE_SYSTEM_REDACTED, details
    assert details.get("source_system_changed") is True, (
        "the stored locator changed and the audit row shows before == after with no "
        f"other signal, so the ledger records the change as none: {details}"
    )


def test_an_unchanged_locator_is_not_reported_as_changed() -> None:
    """The converse, or the flag means nothing."""
    _create("echo-unchanged-probe", "postgresql://warehouse.dw:5432/mkt")
    patched = client.patch(
        "/catalog/datasets/echo-unchanged-probe",
        json={"actor": "data-admin", "reason": "제목만", "title": "제목만 바꿈"},
    )
    assert patched.status_code == 200, patched.text
    details = _audit_details("echo-unchanged-probe")
    assert "source_system" not in (details.get("changes") or {}), details
    assert details.get("source_system_changed") in (None, False), details


def test_resending_the_same_locator_is_not_reported_as_a_change() -> None:
    """The flag has to be false when the field is sent and does not change.

    The first version of this file asserted only the case where ``source_system``
    is absent from the patch, and the flag is absent there - so a mutation that
    hard-coded it to ``True`` went unnoticed. A caller re-sending the value it
    read is the ordinary read-modify-write, and the ledger must not record it as
    a source change.
    """
    _create("echo-resend-probe", "postgresql://warehouse.dw:5432/mkt")
    patched = client.patch(
        "/catalog/datasets/echo-resend-probe",
        json={
            "actor": "data-admin",
            "reason": "같은 값 재전송",
            "title": "제목만 바꿈",
            "source_system": "postgresql://warehouse.dw:5432/mkt",
        },
    )
    assert patched.status_code == 200, patched.text
    details = _audit_details("echo-resend-probe")
    assert "source_system" in (details.get("changes") or {}), details
    assert details.get("source_system_changed") is False, (
        f"re-sending the stored locator was recorded as a source change: {details}"
    )


def test_a_distinguishable_locator_change_is_still_distinguishable() -> None:
    """A URI-shaped change keeps showing its before and after."""
    _create("echo-uri-probe", "postgresql://warehouse.dw:5432/mkt")
    patched = client.patch(
        "/catalog/datasets/echo-uri-probe",
        json={
            "actor": "data-admin",
            "reason": "소스 교체",
            "source_system": "postgresql://lake.dw:5432/sales",
        },
    )
    assert patched.status_code == 200, patched.text
    details = _audit_details("echo-uri-probe")
    assert (details.get("before") or {}).get("source_system") != (
        details.get("after") or {}
    ).get("source_system"), details
    assert details.get("source_system_changed") is True, details
